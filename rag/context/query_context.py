#!/usr/bin/env python3
"""
query_context.py — Retrieval del RAG de CONTEXTO per-engagement para los agentes.

Dado un engagement y una consulta en lenguaje natural, devuelve por SIGNIFICADO lo que ya se sabe de
ESTE objetivo (de sus propios artefactos recon/evidence/notes). Es el "context awareness": antes de
disparar, el agente pregunta "¿qué se ha observado ya en este endpoint/host?" en vez de releer todo.

AISLAMIENTO (CONSTITUTION §1): solo abre engagements/<id>/context.db de ESE engagement (lo garantiza
context_paths); jamás toca el store de otro ni el RAG de conocimiento. Embeddings LOCALES.

    python rag/context/query_context.py -e LAB-2026-009 --semantic "auth observada en /orders" --k 6 --json
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "rag", "knowledge"))

import context_paths as cp  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engagement", "-e", required=True, help="engagement_id (etiqueta, no una ruta)")
    ap.add_argument("--semantic", "-s", required=True, help="consulta en lenguaje natural")
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--source", default=None, help="filtra por artefacto: recon/exploit/evidence/notes")
    ap.add_argument("--repo-root", default=ROOT)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        db_path = cp.context_db_path(args.repo_root, args.engagement)
    except ValueError as e:
        print(json.dumps({"error": str(e)}) if args.json else f"[!] engagement inválido: {e}")
        sys.exit(2)
    if not os.path.isfile(db_path):
        msg = (f"No hay contexto para {args.engagement} todavía (engagements/{args.engagement}/context.db "
               f"no existe). Puéblalo: python rag/context/ingest_context.py -e {args.engagement}")
        print(json.dumps({"error": msg}) if args.json else f"[!] {msg}")
        sys.exit(2)

    import _venv
    _venv.reexec_in_venv_if_available()
    try:
        import kb_vec
        from embed import Embedder
    except ImportError as e:
        msg = (f"Deps de embeddings no disponibles ({e}). Prepáralas con: "
               f"python rag/knowledge/refresh_kb.py --ensure-deps")
        print(json.dumps({"error": msg}) if args.json else f"[!] {msg}")
        sys.exit(3)

    emb = Embedder()
    conn = kb_vec.connect(emb.dim, path=db_path)
    qvec = emb.encode(args.semantic, is_query=True)
    rows = kb_vec.search(conn, qvec, k=args.k, source=args.source)
    total, by_src = kb_vec.counts(conn)
    results = [{"source": r["source"], "doc": r["url"], "title": r["title"], "heading": r["heading"],
                "score": round(1.0 - r["distance"] / 2.0, 3), "text": r["text"]} for r in rows]
    if args.json:
        print(json.dumps({"engagement": args.engagement, "semantic": args.semantic,
                          "matches": len(results), "store_total": total, "results": results},
                         indent=2, ensure_ascii=False))
    else:
        print(f"Contexto[{args.engagement}]: {total} trozos {by_src} | {args.semantic!r} -> {len(results)}\n")
        for r in results:
            loc = " > ".join(x for x in (r["source"] + ":" + (r["doc"] or ""), r["heading"]) if x)
            print(f"  [{r['score']:.3f}] {loc}")
            print(f"      {' '.join(r['text'].split())[:200]}")


if __name__ == "__main__":
    main()
