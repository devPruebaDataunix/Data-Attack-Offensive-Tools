#!/usr/bin/env python3
"""
ingest_context.py — Puebla el RAG de CONTEXTO de UN engagement (embeddings LOCALES, en-zona).

Indexa los artefactos ACUMULADOS del engagement (engagements/<id>/{recon,exploit,evidence,notes},
NUNCA loot/) en engagements/<id>/context.db, para que los agentes recuperen por SIGNIFICADO lo que ya
se sabe de ESTE objetivo. Reusa el store vectorial (kb_vec), el embedder local (embed) y el troceador
(ingest_corpus.chunk_markdown) del RAG de conocimiento — pero el DATO vive EN-ZONA y JAMÁS se mezcla con
kb_vec.db (aislamiento de cliente, CONSTITUTION §1; lo garantiza context_paths).

Embeddings LOCALES (offline): ningún dato del cliente sale de la zona. Idempotente (dedup por hash).

    python rag/context/ingest_context.py --engagement LAB-2026-009
"""
import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)                                  # context_paths
sys.path.insert(0, os.path.join(ROOT, "rag", "knowledge"))  # kb_vec / embed / _venv / ingest_corpus
sys.path.insert(0, os.path.join(ROOT, "tools"))           # redactor (stdlib)

import context_paths as cp  # noqa: E402  (solo stdlib — seguro antes del venv)
import redactor  # noqa: E402  (stdlib; redacta secretos en claro ANTES de embeber — defensa en profundidad)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engagement", "-e", required=True, help="engagement_id (etiqueta, no una ruta)")
    ap.add_argument("--repo-root", default=ROOT)
    ap.add_argument("--batch", type=int, default=128)
    args = ap.parse_args()

    # Aislamiento primero (stdlib, sin venv): resuelve y VALIDA la zona antes de tocar embeddings.
    try:
        db_path = cp.context_db_path(args.repo_root, args.engagement, create=True)
    except ValueError as e:
        print(f"[context] engagement inválido: {e}", file=sys.stderr)
        sys.exit(2)

    files = list(cp.iter_indexable_files(args.repo_root, args.engagement))
    if not files:
        print(f"[context:{args.engagement}] sin artefactos indexables en "
              f"engagements/{args.engagement}/{{recon,exploit,evidence,notes}} (nada que hacer).")
        sys.exit(0)

    # Deps pesadas (venv aislado con torch CPU-only), igual que la Capa 2 del RAG de conocimiento.
    import _venv
    _venv.reexec_in_venv_if_available()
    try:
        import kb_vec
        from embed import Embedder
        from ingest_corpus import chunk_markdown
    except ImportError as e:
        print(f"[context] deps de embeddings no disponibles ({e}). Prepáralas con: "
              f"python rag/knowledge/refresh_kb.py --ensure-deps", file=sys.stderr)
        sys.exit(3)

    emb = Embedder()
    conn = kb_vec.connect(emb.dim, path=db_path)
    kb_vec.set_meta(conn, "embed_model", emb.model_name)
    kb_vec.set_meta(conn, "engagement_id", args.engagement)
    now = datetime.now(timezone.utc).isoformat()
    base = cp.engagement_dir(args.repo_root, args.engagement)

    print(f"[context:{args.engagement}] {len(files)} artefactos -> troceando y embebiendo en CPU. "
          f"Incremental (dedup por hash).", flush=True)
    pending, n_chunks, n_new = [], 0, 0

    def flush():
        nonlocal n_new
        if not pending:
            return
        chashes = [m["chash"] for _, m in pending]
        existing = set()
        for i in range(0, len(chashes), 900):
            part = chashes[i:i + 900]
            existing.update(r[0] for r in conn.execute(
                "SELECT chash FROM chunks WHERE chash IN (%s)" % ",".join("?" * len(part)), part))
        todo = [(t, m) for (t, m) in pending if m["chash"] not in existing]
        if todo:
            vectors = emb.encode([t for t, _ in todo], is_query=False, batch_size=args.batch)
            for (text, meta), vec in zip(todo, vectors):
                if kb_vec.add_chunk(conn, embedding=vec, text=text, updated_at=now, **meta):
                    n_new += 1
            conn.commit()
        pending.clear()

    for sub, path in files:
        rel = os.path.relpath(path, base).replace("\\", "/")
        try:
            raw = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        title, chunks = chunk_markdown(raw)
        for hp, body in chunks:
            # Defensa en profundidad: redacta cualquier secreto en claro (token/clave/cookie) que se colara
            # en recon/evidence/notes ANTES de embeber y guardar — ni el vector ni el texto lo retienen.
            body = redactor.redact(body)
            chash = hashlib.sha1(f"{args.engagement}|{rel}|{hp}|{body}".encode("utf-8")).hexdigest()
            pending.append((body, {"source": sub, "platform": "", "doc": rel,
                                   "title": title or os.path.basename(rel), "heading": hp,
                                   "url": rel, "chash": chash}))
            n_chunks += 1
            if len(pending) >= args.batch:
                flush()
    flush()
    total, by_src = kb_vec.counts(conn)
    conn.close()
    print(f"[context:{args.engagement}] {len(files)} artefactos, {n_chunks} trozos ({n_new} nuevos). "
          f"Store: {total} | {by_src}  ->  {os.path.relpath(db_path, args.repo_root)}")


if __name__ == "__main__":
    main()
