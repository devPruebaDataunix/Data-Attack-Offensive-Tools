#!/usr/bin/env python3
"""
ingest_kev.py — Descarga el catálogo CISA KEV y lo carga/actualiza en el store local.

KEV = Known Exploited Vulnerabilities: vulnerabilidades con explotación CONFIRMADA en el
mundo real. Es la señal de máxima prioridad para un pentester. Feed público, sin auth.

Uso:
    python rag/ingest_kev.py
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone

import db

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"


def fetch_kev(url=KEV_URL):
    req = urllib.request.Request(url, headers={"User-Agent": "cyberseg-agents/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def main():
    print(f"[KEV] Descargando {KEV_URL} ...")
    data = fetch_kev()
    vulns = data.get("vulnerabilities", [])
    version = data.get("catalogVersion", "?")
    print(f"[KEV] catalogVersion={version}  entradas={len(vulns)}")

    conn = db.connect()
    now = datetime.now(timezone.utc).isoformat()
    n = 0
    for v in vulns:
        ransom = 1 if str(v.get("knownRansomwareCampaignUse", "")).lower() == "known" else 0
        conn.execute(
            """
            INSERT INTO vulns
              (cve_id, vendor, product, name, description, cwes,
               date_added_kev, due_date, required_action, in_kev, ransomware, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,1,?,?)
            ON CONFLICT(cve_id) DO UPDATE SET
              vendor=excluded.vendor, product=excluded.product, name=excluded.name,
              description=excluded.description, cwes=excluded.cwes,
              date_added_kev=excluded.date_added_kev, due_date=excluded.due_date,
              required_action=excluded.required_action, in_kev=1,
              ransomware=excluded.ransomware, updated_at=excluded.updated_at
            """,
            (
                v.get("cveID"), v.get("vendorProject"), v.get("product"),
                v.get("vulnerabilityName"), v.get("shortDescription"),
                json.dumps(v.get("cwes", [])), v.get("dateAdded"), v.get("dueDate"),
                v.get("requiredAction"), ransom, now,
            ),
        )
        n += 1
    db.set_meta(conn, "kev_version", version)
    db.set_meta(conn, "kev_last_sync", now)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) c FROM vulns").fetchone()["c"]
    kev = conn.execute("SELECT COUNT(*) c FROM vulns WHERE in_kev=1").fetchone()["c"]
    conn.close()
    print(f"[KEV] Upsert de {n} entradas. Store: {total} CVE totales, {kev} en KEV.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[KEV] ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
