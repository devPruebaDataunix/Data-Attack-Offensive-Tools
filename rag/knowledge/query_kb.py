#!/usr/bin/env python3
"""
query_kb.py — Retrieval del RAG de CONOCIMIENTO para los agentes (Capa 1, determinista, SOLO stdlib).

Dado un contexto (binario/servicio/keywords + plataforma/categoría/MITRE), devuelve técnicas
accionables rankeadas. Pensado para llamarse vía Bash y consumir su JSON, igual que query_vulns.py.

    python query_kb.py --query "env"                        # técnicas para el binario env
    python query_kb.py --query "tar" --category privesc --json
    python query_kb.py --mitre T1548.001 --platform linux
"""
import argparse
import json
import sys

import kb

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def score(row, terms):
    name = (row["name"] or "").lower()
    sub = (row["subtype"] or "").lower()
    blob = " ".join(str(row[k] or "").lower()
                    for k in ("name", "subtype", "category", "tags", "description", "command"))
    s = 0
    for t in terms:
        if t == name:
            s += 100
        elif t in name:
            s += 50
        elif t == sub:
            s += 40
        elif t in blob:
            s += 8
    if row["category"] == "privesc":   # el objetivo típico de un lab Linux
        s += 15
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", "-q", default="", help="binario/servicio/keywords")
    ap.add_argument("--platform", default=None, help="linux/windows/multi")
    ap.add_argument("--category", default=None, help="privesc/execution/file-read/...")
    ap.add_argument("--mitre", default=None, help="ID MITRE, p.ej. T1548.001")
    ap.add_argument("--source", default=None, help="gtfobins/attack/lolbas/...")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    terms = [t for t in args.query.lower().split() if len(t) > 1]
    conn = kb.connect()
    total = conn.execute("SELECT COUNT(*) c FROM techniques").fetchone()["c"]
    if total == 0:
        msg = "KB de conocimiento vacío. Ejecuta: python rag/knowledge/refresh_kb.py"
        print(json.dumps({"error": msg}) if args.json else f"[!] {msg}")
        sys.exit(2)

    where, params = [], []
    if args.platform:  # 'multi' = técnica cross-plataforma -> vale para cualquier filtro
        where.append("(platform=? OR platform='multi')")
        params.append(args.platform)
    for col, val in (("category", args.category), ("mitre_id", args.mitre), ("source", args.source)):
        if val:
            where.append(f"{col}=?")
            params.append(val)
    sql = "SELECT * FROM techniques" + (" WHERE " + " AND ".join(where) if where else "")
    rows = conn.execute(sql, params).fetchall()

    if terms:
        scored = [(score(r, terms), r) for r in rows]
        ranked = [r for sc, r in sorted(scored, key=lambda x: x[0], reverse=True) if sc > 0][: args.limit]
    else:
        ranked = rows[: args.limit]

    results = [{
        "source": r["source"], "platform": r["platform"], "category": r["category"],
        "mitre_id": r["mitre_id"], "name": r["name"], "subtype": r["subtype"],
        "preconditions": r["preconditions"], "command": r["command"],
        "description": r["description"], "source_ref": r["source_ref"],
    } for r in ranked]

    if args.json:
        print(json.dumps({"query": args.query, "matches": len(results),
                          "store_total": total, "results": results}, indent=2, ensure_ascii=False))
    else:
        print(f"KB conocimiento: {total} técnicas | query {args.query!r} -> {len(results)} resultados\n")
        for r in results:
            mid = f" [{r['mitre_id']}]" if r["mitre_id"] else ""
            print(f"  [{(r['category'] or '?').upper():9}] {r['source']}:{r['name']} ({r['subtype']}){mid}")
            if r["preconditions"]:
                print(f"      pre: {r['preconditions']}")
            if r["command"]:
                print(f"      cmd: {r['command'].splitlines()[0][:100]}")
            print(f"      ref: {r['source_ref']}")


if __name__ == "__main__":
    main()
