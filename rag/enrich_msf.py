#!/usr/bin/env python3
"""
enrich_msf.py — Mapea CVE -> módulos de Metasploit Framework (rapid7).

Fuente oficial: db/modules_metadata_base.json del repo de Metasploit. Para un pentester,
saber que existe un módulo MSF (y su rank/fiabilidad) es de las señales más accionables:
indica exploit ARMADO, no solo PoC. Se sincroniza offline al store local.

Uso:
    python rag/enrich_msf.py
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone

import db

MSF_URL = ("https://raw.githubusercontent.com/rapid7/metasploit-framework/master/"
           "db/modules_metadata_base.json")

# Rank numérico de MSF -> etiqueta.
RANK = {0: "manual", 100: "low", 200: "average", 300: "normal",
        400: "good", 500: "great", 600: "excellent"}


def fetch_msf_map():
    """Devuelve {cve_id: [ {module, type, rank}, ... ]}."""
    req = urllib.request.Request(MSF_URL, headers={"User-Agent": "cyberseg-agents/1.0"})
    data = json.loads(urllib.request.urlopen(req, timeout=120).read())
    mp = {}
    for meta in data.values():
        cves = [r for r in meta.get("references", []) if isinstance(r, str) and r.startswith("CVE-")]
        if not cves:
            continue
        entry = {
            "module": meta.get("fullname"),
            "type": meta.get("type"),
            "rank": RANK.get(meta.get("rank"), str(meta.get("rank"))),
        }
        for cve in cves:
            mp.setdefault(cve, []).append(entry)
    return mp


def merge_sources(existing_json, new):
    cur = set(json.loads(existing_json) if existing_json else [])
    cur.update(new)
    return json.dumps(sorted(cur))


def main():
    conn = db.connect()
    now = datetime.now(timezone.utc).isoformat()
    print("[MSF] Descargando metadata de módulos de Metasploit ...")
    mp = fetch_msf_map()
    print(f"[MSF] {len(mp)} CVE con módulo Metasploit en el framework.")

    store = [r["cve_id"] for r in conn.execute("SELECT cve_id FROM vulns").fetchall()]
    hit = 0
    for cve in store:
        if cve in mp:
            row = conn.execute("SELECT exploit_sources FROM vulns WHERE cve_id=?", (cve,)).fetchone()
            conn.execute(
                "UPDATE vulns SET exploit_public=1, exploit_maturity='weaponized', "
                "exploit_sources=?, msf_modules=?, updated_at=? WHERE cve_id=?",
                (merge_sources(row["exploit_sources"], ["Metasploit"]),
                 json.dumps(mp[cve]), now, cve),
            )
            hit += 1
    db.set_meta(conn, "msf_last_sync", now)
    conn.commit()
    conn.close()
    print(f"[MSF] {hit} de {len(store)} CVE del store tienen módulo Metasploit.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[MSF] ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
