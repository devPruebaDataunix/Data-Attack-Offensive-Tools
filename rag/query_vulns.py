#!/usr/bin/env python3
"""
query_vulns.py — Retrieval híbrido para el agente vuln-triage.

Dado un producto/servicio (y opcionalmente versión/keywords), devuelve los CVE más
relevantes RANKEADOS por prioridad de explotación real (best practice 2026):

    KEV (explotado de verdad)  >  EPSS (probabilidad)  >  CVSS (severidad)  >  relevancia textual

Pensado para ser llamado por el agente vía Bash y consumir su salida JSON:
    python rag/query_vulns.py --query "Apache Log4j" --json
    python rag/query_vulns.py --query "Fortinet FortiOS SSL VPN" --kev-only --limit 10
"""
import argparse
import json
import sys

import db

# Salida UTF-8 robusta (evita UnicodeEncodeError en consolas Windows cp1252).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

NVD = "https://nvd.nist.gov/vuln/detail/"
EPSS_REF = "https://www.first.org/epss/"
KEV_REF = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"


def tier(row):
    in_kev = row["in_kev"]
    ransom = row["ransomware"]
    epss = row["epss"] or 0
    cvss = row["cvss"] or 0
    expl = row["exploit_public"]
    if in_kev and (ransom or expl or epss >= 0.5):
        return "critical"
    if in_kev or expl or epss >= 0.5 or cvss >= 9.0:
        return "high"
    if epss >= 0.1 or cvss >= 7.0:
        return "medium"
    return "low"


# Términos demasiado genéricos para anclar relevancia por sí solos (pero suman si hay más).
STOPWORDS = {"ssl", "vpn", "server", "service", "manager", "system", "software",
             "web", "remote", "secure", "client", "agent", "core", "data", "and"}


def relevance(row, terms):
    """Etapa 1: ¿este CVE pertenece de verdad al producto consultado?
    Pondera coincidencias en los campos de IDENTIDAD (vendor/product/name) muy por
    encima de la descripción. Devuelve (relevancia, nº de coincidencias de identidad)."""
    identity = " ".join(str(row[k] or "").lower() for k in ("vendor", "product", "name"))
    desc = str(row["description"] or "").lower()
    rel = 0.0
    id_hits = 0
    for t in terms:
        if t in identity:
            rel += 20 if t in STOPWORDS else 50
            id_hits += 1
        elif t in desc:
            rel += 5
    return rel, id_hits


def exploit_priority(row):
    """Etapa 2: dentro de lo relevante, prioriza por explotación real.
    Criterio: KEV > módulo MSF (armado) > exploit público > VulnCheck KEV > ransomware > EPSS > CVSS."""
    p = 0.0
    if row["in_kev"]:
        p += 1000
    if row["msf_modules"]:        # módulo Metasploit = exploit armado, señal fuerte
        p += 600
    if row["exploit_public"]:
        p += 500
    if row["vulncheck_kev"]:
        p += 400
    if row["ransomware"]:
        p += 300
    if row["nuclei_templates"]:   # plantilla de detección lista para escanear
        p += 150
    p += (row["epss_percentile"] or 0) * 200
    p += (row["epss"] or 0) * 100
    p += (row["cvss"] or 0) * 8
    return p


def score(row, terms):
    """Relevancia DOMINA sobre prioridad: un match exacto de producto siempre supera a
    un CVE de otro producto que solo comparta una palabra genérica."""
    rel, _ = relevance(row, terms)
    return rel * 10000 + exploit_priority(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", "-q", required=True, help="producto/servicio/keywords")
    ap.add_argument("--version", default=None, help="versión (best-effort, informativo)")
    ap.add_argument("--kev-only", action="store_true", help="solo CVE en KEV")
    ap.add_argument("--min-epss", type=float, default=0.0, help="umbral mínimo de EPSS")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--json", action="store_true", help="salida JSON para el agente")
    args = ap.parse_args()

    terms = [t for t in args.query.lower().split() if len(t) > 1]
    if args.version:
        terms.append(args.version.lower())

    conn = db.connect()
    total = conn.execute("SELECT COUNT(*) c FROM vulns").fetchone()["c"]
    if total == 0:
        msg = "Store vacío. Ejecuta: python rag/ingest_kev.py && python rag/enrich_epss.py"
        print(json.dumps({"error": msg}) if args.json else f"[!] {msg}")
        sys.exit(2)

    # Prefiltro SQL: filas que matcheen al menos un término en algún campo de texto.
    like = " OR ".join(
        ["LOWER(vendor) LIKE ? OR LOWER(product) LIKE ? OR LOWER(name) LIKE ? "
         "OR LOWER(description) LIKE ? OR LOWER(cve_id) LIKE ?"] * len(terms)
    )
    params = []
    for t in terms:
        params += [f"%{t}%"] * 5
    sql = f"SELECT * FROM vulns WHERE ({like})"
    if args.kev_only:
        sql += " AND in_kev=1"
    if args.min_epss > 0:
        sql += " AND COALESCE(epss,0) >= " + str(args.min_epss)
    rows = conn.execute(sql, params).fetchall()

    # Gate de relevancia: descarta filas que solo matchean en la descripción (ruido).
    # Si NINGUNA fila tiene match de identidad, caemos a las que matchean en descripción
    # para no devolver vacío en consultas atípicas.
    gated = [r for r in rows if relevance(r, terms)[1] >= 1]
    candidates = gated if gated else rows

    ranked = sorted(candidates, key=lambda r: score(r, terms), reverse=True)[: args.limit]

    results = []
    for r in ranked:
        results.append({
            "cve": r["cve_id"],
            "title": r["name"],
            "vendor": r["vendor"],
            "product": r["product"],
            "severity": tier(r),
            "published_date": r["published_date"],
            "source_feed": json.loads(r["source_feed"] or "[]"),
            "in_kev": bool(r["in_kev"]),
            "kev_ransomware": bool(r["ransomware"]),
            "kev_due_date": r["due_date"],
            "vulncheck_kev": bool(r["vulncheck_kev"]),
            "exploit_public": bool(r["exploit_public"]),
            "exploit_sources": json.loads(r["exploit_sources"] or "[]"),
            "exploit_maturity": r["exploit_maturity"],
            "msf_modules": json.loads(r["msf_modules"] or "[]"),
            "nuclei_templates": json.loads(r["nuclei_templates"] or "[]"),
            "epss": r["epss"],
            "epss_percentile": r["epss_percentile"],
            "cvss": r["cvss"],
            "cvss_vector": r["cvss_vector"],
            "cvss_source": r["cvss_source"],
            "ssvc": json.loads(r["ssvc"]) if r["ssvc"] else None,
            "cwe": json.loads(r["cwes"] or "[]"),
            "required_action": r["required_action"],
            "source_refs": [KEV_REF if r["in_kev"] else NVD + r["cve_id"],
                            NVD + r["cve_id"], EPSS_REF],
        })

    if args.json:
        out = {
            "query": args.query,
            "version": args.version,
            "store": {
                "total_cves": total,
                "kev_version": db.get_meta(conn, "kev_version"),
                "kev_last_sync": db.get_meta(conn, "kev_last_sync"),
                "epss_last_sync": db.get_meta(conn, "epss_last_sync"),
                "cve5_last_sync": db.get_meta(conn, "cve5_last_sync"),
                "exploitdb_last_sync": db.get_meta(conn, "exploitdb_last_sync"),
                "msf_last_sync": db.get_meta(conn, "msf_last_sync"),
                "nuclei_last_sync": db.get_meta(conn, "nuclei_last_sync"),
            },
            "matches": len(candidates),
            "results": results,
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"Query: {args.query!r}  (store: {total} CVE, KEV {db.get_meta(conn,'kev_version')})")
        print(f"Coincidencias: {len(candidates)}  | mostrando top {len(results)}\n")
        for r in results:
            flags = []
            if r["in_kev"]:
                flags.append("KEV")
            if r["exploit_public"]:
                flags.append("EXPLOIT(" + ",".join(r["exploit_sources"] or ["?"]) + ")")
            if r["kev_ransomware"]:
                flags.append("RANSOMWARE")
            ep = f"{r['epss']:.3f}" if r["epss"] is not None else "-"
            cv = f"{r['cvss']:.1f}" if r["cvss"] is not None else "-"
            print(f"  [{r['severity'].upper():8}] {r['cve']:18} EPSS={ep:6} CVSS={cv:4} "
                  f"{r['vendor']} {r['product']}")
            print(f"             {r['title']}")
            if flags:
                print(f"             > {'  '.join(flags)}")
            for m in (r["msf_modules"] or [])[:2]:
                print(f"             > MSF: {m['module']}  (rank: {m['rank']})")
            if r["nuclei_templates"]:
                print(f"             > Nuclei: {r['nuclei_templates'][0]}")
    conn.close()


if __name__ == "__main__":
    main()
