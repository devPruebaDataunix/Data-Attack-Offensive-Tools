#!/usr/bin/env python3
"""
query_kb.py — Retrieval del RAG de CONOCIMIENTO para los agentes (Capa 1, determinista, SOLO stdlib).

Dado un contexto (binario/servicio/keywords + plataforma/categoría/MITRE), devuelve técnicas
accionables rankeadas. Pensado para llamarse vía Bash y consumir su JSON, igual que query_vulns.py.

    python query_kb.py --query "env"                        # técnicas para el binario env
    python query_kb.py --query "tar" --category privesc --json
    python query_kb.py --mitre T1548.001 --platform linux
    python query_kb.py --semantic "privesc cuando sudo permite tar" --k 6   # Capa 2 (prosa/metodología)
"""
import argparse
import json
import os
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


def semantic_query(args):
    """Capa 2: recupera por SIGNIFICADO sobre kb_vec.db (prosa: HackTricks/PaTT/PEASS/cyber-skills/feeds)."""
    import _venv
    _venv.reexec_in_venv_if_available()  # si las deps viven en el venv del RAG, se re-ejecuta ahí
    try:
        import kb_vec
        from embed import Embedder
    except ImportError as e:
        msg = (f"Capa 2 no disponible (falta dependencia: {e}). Puébla/instala con: "
               f"python rag/knowledge/refresh_kb.py --semantic")
        print(json.dumps({"error": msg}) if args.json else f"[!] {msg}")
        sys.exit(3)
    if not os.path.isfile(kb_vec.DB_PATH):
        msg = "kb_vec.db no existe. Puébla la Capa 2: python rag/knowledge/refresh_kb.py --semantic"
        print(json.dumps({"error": msg}) if args.json else f"[!] {msg}")
        sys.exit(2)
    emb = Embedder()
    conn = kb_vec.connect(emb.dim)
    qvec = emb.encode(args.semantic, is_query=True)
    rows = kb_vec.search(conn, qvec, k=args.k, source=args.source, platform=args.platform)
    total, by_src = kb_vec.counts(conn)
    results = [{
        "source": r["source"], "platform": r["platform"], "title": r["title"],
        "heading": r["heading"], "score": round(1.0 - r["distance"] / 2.0, 3),
        "text": r["text"], "url": r["url"],
    } for r in rows]
    if args.json:
        print(json.dumps({"semantic": args.semantic, "matches": len(results),
                          "store_total": total, "results": results}, indent=2, ensure_ascii=False))
    else:
        print(f"KB Capa 2 (semántica): {total} trozos {by_src} | {args.semantic!r} -> {len(results)}\n")
        for r in results:
            loc = " > ".join(x for x in (r["title"], r["heading"]) if x)
            print(f"  [{r['score']:.3f}] {r['source']}: {loc}")
            snippet = " ".join(r["text"].split())[:200]
            print(f"      {snippet}")
            print(f"      ref: {r['url']}")
    sys.exit(0)


def stats(args):
    """Cobertura de AMBOS RAG de conocimiento. Para VERIFICAR la población (sobre todo la Capa 2 entera
    en Kali). No carga sqlite-vec ni el embedder: la tabla `chunks` es SQLite normal."""
    here = os.path.dirname(os.path.abspath(__file__))
    rep = {"capa1_kb": {}, "capa2_kb_vec": {}}

    conn = kb.connect()
    grp = lambda q: {(r[0] if r[0] not in (None, "") else "?"): r[1] for r in conn.execute(q).fetchall()}
    rep["capa1_kb"]["total"] = conn.execute("SELECT COUNT(*) FROM techniques").fetchone()[0]
    rep["capa1_kb"]["by_source"] = grp("SELECT source, COUNT(*) FROM techniques GROUP BY source ORDER BY 2 DESC")
    rep["capa1_kb"]["by_platform"] = grp("SELECT platform, COUNT(*) FROM techniques GROUP BY platform ORDER BY 2 DESC")
    rep["capa1_kb"]["by_category"] = grp("SELECT category, COUNT(*) FROM techniques GROUP BY category ORDER BY 2 DESC")

    import sqlite3
    vdb = os.path.join(here, "kb_vec.db")
    if os.path.isfile(vdb):
        try:
            c = sqlite3.connect(vdb)
            rep["capa2_kb_vec"]["total"] = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            rep["capa2_kb_vec"]["by_source"] = {r[0]: r[1] for r in c.execute(
                "SELECT source, COUNT(*) FROM chunks GROUP BY source ORDER BY 2 DESC").fetchall()}
            try:
                m = c.execute("SELECT value FROM meta WHERE key='embed_model'").fetchone()
                rep["capa2_kb_vec"]["embed_model"] = m[0] if m else None
            except sqlite3.Error:
                pass
            c.close()
        except sqlite3.Error as e:
            rep["capa2_kb_vec"] = {"error": f"kb_vec.db presente pero ilegible: {e}"}
    else:
        rep["capa2_kb_vec"] = {"status": "no poblada (kb_vec.db no existe) — corre rag/knowledge/refresh_kb.py --semantic"}

    if args.json:
        print(json.dumps(rep, indent=2, ensure_ascii=False))
    else:
        c1 = rep["capa1_kb"]
        print("RAG de conocimiento — cobertura\n")
        print(f"Capa 1 (kb.db): {c1['total']} técnicas")
        print(f"  por fuente:    {c1['by_source']}")
        print(f"  por plataforma:{c1['by_platform']}")
        print(f"  por categoría: {c1['by_category']}")
        c2 = rep["capa2_kb_vec"]
        if "total" in c2:
            print(f"Capa 2 (kb_vec.db): {c2['total']} trozos  (modelo {c2.get('embed_model')})")
            print(f"  por fuente:    {c2['by_source']}")
            if c2["total"] < 2000:
                print("  ⚠️  pocas entradas: parece el SUBSET de prueba. Repoblar entero: refresh_kb.py --semantic")
        else:
            print(f"Capa 2 (kb_vec.db): {c2.get('status') or c2.get('error')}")
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", "-q", default="", help="binario/servicio/keywords")
    ap.add_argument("--platform", default=None, help="linux/windows/multi")
    ap.add_argument("--category", default=None, help="privesc/execution/file-read/...")
    ap.add_argument("--mitre", default=None, help="ID MITRE, p.ej. T1548.001")
    ap.add_argument("--source", default=None, help="gtfobins/attack/lolbas/... (Capa 1) o hacktricks/payloads/peass/cyber-skills/0dayfans/hackernews (Capa 2)")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--semantic", default=None, help="consulta SEMÁNTICA en prosa (Capa 2, embeddings)")
    ap.add_argument("--k", type=int, default=8, help="nº de trozos a devolver en modo --semantic")
    ap.add_argument("--stats", action="store_true", help="cobertura de ambos RAG (verificar población)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.stats:
        return stats(args)
    if args.semantic:
        return semantic_query(args)

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
