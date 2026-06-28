#!/usr/bin/env python3
"""
ingest_corpus.py — Ingesta de PROSA larga (Markdown) al RAG semántico (Capa 2).

Trocea documentos Markdown por ENCABEZADOS (conservando la ruta de headings como contexto), calcula
embeddings LOCALES por lotes (embed.py) y los guarda en kb_vec.db (kb_vec.py). Pensado para corpus de
metodología: HackTricks, PayloadsAllTheThings, PEASS-ng. Idempotente (dedup por hash de contenido).

ANTI-INYECCIÓN: TODO el contenido del corpus es DATO. Aquí solo se trocea y se indexa como texto inerte;
NUNCA se ejecuta ni se interpreta como instrucción. Los agentes que luego lo lean lo tratan igual.

Uso:
    python ingest_corpus.py --source hacktricks --src <repo> --repo HackTricks-wiki/hacktricks
    python ingest_corpus.py --source payloads   --src <repo> --repo swisskyrepo/PayloadsAllTheThings
    python ingest_corpus.py --source peass       --src <repo> --repo carlospolop/PEASS-ng
"""
import argparse
import glob
import hashlib
import os
import re
import sys
from datetime import datetime, timezone

import kb_vec
from embed import Embedder

HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


def platform_hint(relpath):
    p = relpath.lower()
    if "active-directory" in p or "/ad/" in p or "windows" in p or "/winpeas" in p:
        return "windows"
    if "linux" in p or "/linpeas" in p:
        return "linux"
    if any(w in p for w in ("/web", "xss", "sql-injection", "ssrf", "ssti", "http")):
        return "web"
    return ""


def chunk_markdown(text, max_chars=1200, overlap=150, min_chars=60):
    """Genera (heading_path, chunk_text). Acumula por sección de encabezado; las secciones largas se
    parten en ventanas con solapamiento. Conserva el código (es valioso)."""
    lines = text.replace("\r\n", "\n").split("\n")
    stack, buf, out = [], [], []
    title = ""

    def heading_path():
        return " > ".join(h for _, h in stack)

    def flush():
        body = "\n".join(buf).strip()
        if len(body) < min_chars:
            buf.clear()
            return
        hp = heading_path()
        if len(body) <= max_chars:
            out.append((hp, body))
        else:
            i = 0
            while i < len(body):
                out.append((hp, body[i:i + max_chars]))
                i += max_chars - overlap
        buf.clear()

    for ln in lines:
        m = HEADING.match(ln)
        if m:
            flush()
            level = len(m.group(1))
            htext = m.group(2).strip()
            if not title:
                title = htext
            stack[:] = [(lv, h) for (lv, h) in stack if lv < level]
            stack.append((level, htext))
        else:
            buf.append(ln)
    flush()
    return title, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="etiqueta de la fuente (hacktricks/payloads/peass)")
    ap.add_argument("--src", required=True, help="ruta al repo clonado")
    ap.add_argument("--repo", default="", help="slug GitHub para construir la URL (owner/name)")
    ap.add_argument("--branch", default="master")
    ap.add_argument("--glob", default="**/*.md")
    ap.add_argument("--batch", type=int, default=256, help="trozos por lote de embedding")
    ap.add_argument("--max-files", type=int, default=0, help="(debug) limita nº de ficheros; 0 = todos")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.src, args.glob), recursive=True))
    files = [f for f in files if os.path.isfile(f)]
    if args.max_files:
        files = files[: args.max_files]
    if not files:
        print(f"[corpus:{args.source}] sin .md en {args.src}", file=sys.stderr)
        sys.exit(2)

    print(f"[corpus:{args.source}] {len(files)} ficheros .md -> troceando y embebiendo en CPU por lotes de "
          f"{args.batch}. La 1a vez TARDA; es incremental (un Ctrl+C no pierde lo ya hecho: al relanzar "
          f"retoma). Progreso por lote:", flush=True)
    emb = Embedder()
    conn = kb_vec.connect(emb.dim)
    kb_vec.set_meta(conn, "embed_model", emb.model_name)
    now = datetime.now(timezone.utc).isoformat()

    pending = []  # (text, meta)
    n_chunks = n_new = files_done = 0

    def flush_batch():
        nonlocal n_new
        if not pending:
            return
        # Incremental: NO re-embebas lo que ya está (dedup por chash ANTES de embeber). Así un refresh
        # sin cambios no recalcula embeddings (clave en corpus grandes como HackTricks).
        chashes = [m["chash"] for _, m in pending]
        existing = set()
        for i in range(0, len(chashes), 900):  # límite de variables SQLite
            part = chashes[i:i + 900]
            rows = conn.execute(
                "SELECT chash FROM chunks WHERE chash IN (%s)" % ",".join("?" * len(part)), part)
            existing.update(r[0] for r in rows)
        todo = [(t, m) for (t, m) in pending if m["chash"] not in existing]
        if todo:
            vectors = emb.encode([t for t, _ in todo], is_query=False, batch_size=args.batch)
            for (text, meta), vec in zip(todo, vectors):
                if kb_vec.add_chunk(conn, embedding=vec, text=text, updated_at=now, **meta):
                    n_new += 1
            conn.commit()
        # Progreso visible (sin esto el embedding masivo en CPU "parece colgado" — lección de v2.1.2).
        print(f"[corpus:{args.source}]   ficheros {files_done}/{len(files)} · {n_chunks} trozos · "
              f"{n_new} nuevos", flush=True)
        pending.clear()

    for f in files:
        files_done += 1
        rel = os.path.relpath(f, args.src).replace("\\", "/")
        try:
            raw = open(f, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        title, chunks = chunk_markdown(raw)
        plat = platform_hint(rel)
        url = (f"https://github.com/{args.repo}/blob/{args.branch}/{rel}") if args.repo else rel
        for hp, body in chunks:
            chash = hashlib.sha1(f"{args.source}|{rel}|{hp}|{body}".encode("utf-8")).hexdigest()
            pending.append((body, {
                "source": args.source, "platform": plat, "doc": rel,
                "title": title or os.path.basename(rel), "heading": hp, "url": url, "chash": chash,
            }))
            n_chunks += 1
            if len(pending) >= args.batch:
                flush_batch()
    flush_batch()

    total, by_src = kb_vec.counts(conn)
    conn.close()
    print(f"[corpus:{args.source}] {len(files)} ficheros, {n_chunks} trozos ({n_new} nuevos). "
          f"Store kb_vec: {total} | {by_src}")


if __name__ == "__main__":
    main()
