#!/usr/bin/env python3
"""
enrich_epss.py — Enriquece el store con scores EPSS (FIRST.org).

EPSS = probabilidad (0-1) de que un CVE sea explotado en los próximos 30 días. Complementa
a KEV: KEV te dice "ya se explota"; EPSS te dice "qué probable es que se explote". Best
practice 2026: priorizar por KEV > EPSS > CVSS.

Uso:
    python rag/enrich_epss.py            # enriquece todos los CVE del store sin EPSS
    python rag/enrich_epss.py --all      # re-enriquece todos (scores cambian a diario)
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import db

EPSS_URL = "https://api.first.org/data/v1/epss"
BATCH = 50  # CVEs por petición (lista separada por comas)


def fetch_epss(cve_ids):
    q = urllib.parse.urlencode({"cve": ",".join(cve_ids), "limit": len(cve_ids)})
    req = urllib.request.Request(f"{EPSS_URL}?{q}", headers={"User-Agent": "cyberseg-agents/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r).get("data", [])


def main():
    refresh_all = "--all" in sys.argv
    conn = db.connect()
    if refresh_all:
        rows = conn.execute("SELECT cve_id FROM vulns").fetchall()
    else:
        rows = conn.execute("SELECT cve_id FROM vulns WHERE epss IS NULL").fetchall()
    cves = [r["cve_id"] for r in rows if r["cve_id"]]
    if not cves:
        print("[EPSS] Nada que enriquecer.")
        return
    print(f"[EPSS] Enriqueciendo {len(cves)} CVE en lotes de {BATCH} ...")

    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    for i in range(0, len(cves), BATCH):
        batch = cves[i:i + BATCH]
        for attempt in range(3):
            try:
                data = fetch_epss(batch)
                break
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"[EPSS] reintento lote {i//BATCH} ({type(e).__name__}) ...")
                time.sleep(2 * (attempt + 1))
        for d in data:
            conn.execute(
                "UPDATE vulns SET epss=?, epss_percentile=?, updated_at=? WHERE cve_id=?",
                (float(d["epss"]), float(d["percentile"]), now, d["cve"]),
            )
            updated += 1
        conn.commit()
        time.sleep(0.3)  # cortesía con la API pública
    db.set_meta(conn, "epss_last_sync", now)
    conn.commit()
    conn.close()
    print(f"[EPSS] {updated} CVE actualizados con score EPSS.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[EPSS] ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
