#!/usr/bin/env python3
"""
kb_vec.py — Almacén VECTORIAL del RAG de conocimiento (Capa 2, semántica), sobre SQLite + sqlite-vec.

Mientras la Capa 1 (kb.py / kb.db) es un catálogo ESTRUCTURADO y determinista (el comando concreto),
la Capa 2 indexa PROSA larga (HackTricks, PayloadsAllTheThings, PEASS, feeds de intel) por SIGNIFICADO:
trozos de texto + su embedding, con KNN por similitud. Responde el "CÓMO razonar/metodología".

Diseño coherente con el resto del RAG: un fichero SQLite (`kb_vec.db`, gitignored, se reconstruye con
refresh_kb.py --semantic). Los embeddings son LOCALES (sentence-transformers, ver embed.py) -> offline,
ningún dato sale de la zona. El store guarda el modelo/dim usados en `meta` para detectar desajustes.
"""
import os
import sqlite3
import struct

import sqlite_vec

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kb_vec.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source     TEXT NOT NULL,     -- hacktricks / payloads / peass / 0dayfans / hackernews
    platform   TEXT,              -- linux / windows / multi / web / '' (heurística)
    doc        TEXT,              -- ruta del fichero o id del feed
    title      TEXT,              -- título del documento
    heading    TEXT,              -- ruta de encabezados dentro del documento
    text       TEXT NOT NULL,     -- el trozo de texto indexado
    url        TEXT,              -- referencia (fuente)
    chash      TEXT UNIQUE,       -- hash de contenido (dedup idempotente)
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_source   ON chunks(source);
CREATE INDEX IF NOT EXISTS idx_chunks_platform ON chunks(platform);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def _pack(vec):
    return struct.pack("%df" % len(vec), *vec)


def connect(dim, path=DB_PATH):
    """Abre el store, carga la extensión sqlite-vec y crea el esquema + la tabla vectorial de dimensión
    `dim`. Si ya existía con otra dimensión, lo señala (hay que reconstruir tras cambiar de modelo)."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.executescript(SCHEMA)
    prev = get_meta(conn, "embed_dim")
    if prev is not None and int(prev) != int(dim):
        raise SystemExit(
            f"[kb_vec] kb_vec.db usa dim={prev} pero el modelo actual da dim={dim}. "
            f"Borra rag/knowledge/kb_vec.db y repuebla (cambiaste de modelo de embeddings)."
        )
    conn.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding float[{int(dim)}])")
    set_meta(conn, "embed_dim", dim)
    conn.commit()
    return conn


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def add_chunk(conn, source, text, embedding, chash, platform="", doc="", title="",
              heading="", url="", updated_at=""):
    """Inserta un trozo + su embedding de forma idempotente (dedup por chash). Mantiene
    chunks.id == vec_chunks.rowid. Devuelve True si insertó, False si ya existía."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO chunks(source,platform,doc,title,heading,text,url,chash,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (source, platform, doc, title, heading, text, url, chash, updated_at),
    )
    if cur.rowcount == 0:
        return False  # ya estaba: no re-embebemos
    conn.execute("INSERT INTO vec_chunks(rowid, embedding) VALUES(?, ?)",
                 (cur.lastrowid, _pack(embedding)))
    return True


def search(conn, embedding, k=8, source=None, platform=None):
    """KNN por similitud. Si se filtra por source/platform, sobre-pide y filtra en Python (robusto
    entre versiones de sqlite-vec). Devuelve filas con distancia ascendente (más cercano primero)."""
    over = k * 5 if (source or platform) else k
    # sqlite-vec exige la constraint especial `k = ?` (no LIMIT) en KNN sobre vec0.
    rows = conn.execute(
        "SELECT c.source, c.platform, c.title, c.heading, c.text, c.url, v.distance "
        "FROM vec_chunks v JOIN chunks c ON c.id = v.rowid "
        "WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance",
        (_pack(embedding), over),
    ).fetchall()
    out = []
    for r in rows:
        if source and r["source"] != source:
            continue
        if platform and platform not in (r["platform"] or "") and (r["platform"] or "") != "multi":
            continue
        out.append(r)
        if len(out) >= k:
            break
    return out


def counts(conn):
    total = conn.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
    by_src = {r["source"]: r["c"]
              for r in conn.execute("SELECT source, COUNT(*) c FROM chunks GROUP BY source")}
    return total, by_src
