#!/usr/bin/env python3
"""
enrich_nuclei.py — Mapea CVE -> plantillas Nuclei (projectdiscovery).

Fuente oficial: cves.json (JSONL) del repo nuclei-templates. Una plantilla Nuclei es una
comprobación pública lista para `nuclei -t <ruta>` — muy accionable en bug bounty web.
No implica exploit armado (es detección), así que se registra como fuente/recurso, no
fuerza exploit_public por sí sola.

Uso:
    python rag/enrich_nuclei.py
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone

import db

NUCLEI_URL = ("https://raw.githubusercontent.com/projectdiscovery/nuclei-templates/main/"
              "cves.json")


def fetch_nuclei_map():
    """Devuelve {cve_id: [ruta_plantilla, ...]} desde el cves.json (JSONL)."""
    req = urllib.request.Request(NUCLEI_URL, headers={"User-Agent": "cyberseg-agents/1.0"})
    raw = urllib.request.urlopen(req, timeout=120).read().decode("utf-8", "replace")
    mp = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        cve = o.get("ID")
        path = o.get("file_path")
        if cve and path:
            mp.setdefault(cve, []).append(path)
    return mp


def merge_sources(existing_json, new):
    cur = set(json.loads(existing_json) if existing_json else [])
    cur.update(new)
    return json.dumps(sorted(cur))


def main():
    conn = db.connect()
    now = datetime.now(timezone.utc).isoformat()
    print("[Nuclei] Descargando índice cves.json de plantillas ...")
    mp = fetch_nuclei_map()
    print(f"[Nuclei] {len(mp)} CVE con plantilla Nuclei.")

    store = [r["cve_id"] for r in conn.execute("SELECT cve_id FROM vulns").fetchall()]
    hit = 0
    for cve in store:
        if cve in mp:
            row = conn.execute("SELECT exploit_sources FROM vulns WHERE cve_id=?", (cve,)).fetchone()
            conn.execute(
                "UPDATE vulns SET exploit_sources=?, nuclei_templates=?, updated_at=? WHERE cve_id=?",
                (merge_sources(row["exploit_sources"], ["Nuclei"]),
                 json.dumps(mp[cve]), now, cve),
            )
            hit += 1
    db.set_meta(conn, "nuclei_last_sync", now)
    conn.commit()
    conn.close()
    print(f"[Nuclei] {hit} de {len(store)} CVE del store tienen plantilla Nuclei.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[Nuclei] ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
