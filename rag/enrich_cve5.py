#!/usr/bin/env python3
"""
enrich_cve5.py — Enriquece CVSS + SSVC desde registros CVE 5.0 (MITRE CVE Services).

POR QUÉ NO EL NVD: desde 2024 el NVD tiene un backlog masivo y desde el 15-abr-2026 solo
enriquece CVEs de alto riesgo; su severidad es errónea el ~88% de las veces (Inspector
General). Fuente fiable hoy: el registro CVE 5.0, donde el **CNA** publica el CVSS y el
contenedor **CISA-ADP (Vulnrichment)** publica SSVC y confirmación KEV. Público, sin clave.

Uso:
    python rag/enrich_cve5.py            # enriquece CVEs del store sin CVSS
    python rag/enrich_cve5.py --all      # re-procesa todos
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

import db

CVE5_URL = "https://cveawg.mitre.org/api/cve/"
CVSS_PREF = ["cvssV4_0", "cvssV3_1", "cvssV3_0", "cvssV2_0"]  # preferencia de versión


def fetch_cve(cve_id):
    req = urllib.request.Request(CVE5_URL + cve_id, headers={"User-Agent": "cyberseg-agents/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def extract_cvss(metrics):
    """Devuelve (score, severity, vector) del CVSS de mayor versión disponible."""
    best = None
    for m in metrics or []:
        for key in CVSS_PREF:
            if key in m:
                v = m[key]
                rank = CVSS_PREF.index(key)
                if best is None or rank < best[0]:
                    best = (rank, v.get("baseScore"), v.get("baseSeverity"),
                            v.get("vectorString"))
    if best and best[1] is not None:
        return best[1], (best[2] or "").lower() or None, best[3]
    return None, None, None


def extract_adp(containers):
    """Saca CVSS de respaldo, SSVC y KEV del contenedor CISA-ADP."""
    cvss = (None, None, None)
    ssvc = None
    vc_kev = None
    for adp in containers.get("adp", []):
        if adp.get("providerMetadata", {}).get("shortName") != "CISA-ADP":
            continue
        c = extract_cvss(adp.get("metrics"))
        if c[0] is not None:
            cvss = c
        for m in adp.get("metrics", []):
            other = m.get("other", {})
            if other.get("type") == "ssvc":
                ssvc = other.get("content")
    return cvss, ssvc, vc_kev


def main():
    refresh_all = "--all" in sys.argv
    conn = db.connect()
    if refresh_all:
        rows = conn.execute("SELECT cve_id FROM vulns").fetchall()
    else:
        rows = conn.execute("SELECT cve_id FROM vulns WHERE cvss IS NULL").fetchall()
    cves = [r["cve_id"] for r in rows if r["cve_id"]]
    if not cves:
        print("[CVE5] Nada que enriquecer.")
        return
    print(f"[CVE5] Enriqueciendo CVSS/SSVC de {len(cves)} CVE desde CVE 5.0 "
          f"(uno a uno; puede tardar varios minutos) ...", flush=True)

    now = datetime.now(timezone.utc).isoformat()
    got_cvss = got_ssvc = 0
    for i, cve in enumerate(cves, 1):
        try:
            d = fetch_cve(cve)
        except Exception as e:
            # 404 o transitorio: seguir sin romper el lote
            continue
        containers = d.get("containers", {})
        score, sev, vec = extract_cvss(containers.get("cna", {}).get("metrics"))
        (adp_cvss, adp_ssvc, _) = extract_adp(containers)
        if score is None and adp_cvss[0] is not None:
            score, sev, vec = adp_cvss
        ssvc_json = json.dumps(adp_ssvc, ensure_ascii=False) if adp_ssvc else None
        if score is not None:
            got_cvss += 1
        if ssvc_json:
            got_ssvc += 1
        conn.execute(
            "UPDATE vulns SET cvss=?, cvss_severity=?, cvss_vector=?, cvss_source=?, "
            "ssvc=COALESCE(?, ssvc), updated_at=? WHERE cve_id=?",
            (score, sev, vec, ("cvelistV5" if score is not None else None),
             ssvc_json, now, cve),
        )
        if i % 50 == 0:
            conn.commit()
            print(f"[CVE5]  {i}/{len(cves)} (cvss={got_cvss}, ssvc={got_ssvc})", flush=True)
        time.sleep(0.15)  # cortesía con el servicio público
    db.set_meta(conn, "cve5_last_sync", now)
    conn.commit()
    conn.close()
    print(f"[CVE5] Hecho. CVSS añadido a {got_cvss} CVE, SSVC a {got_ssvc}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[CVE5] ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
