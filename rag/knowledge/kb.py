#!/usr/bin/env python3
"""
kb.py — Almacenamiento del RAG de CONOCIMIENTO ofensivo (técnicas/playbooks accionables), SQLite.

Complementa al RAG de CVEs (rag/vulns.db, "QUÉ es vulnerable") con el "CÓMO explotar/escalar":
un catálogo DETERMINISTA de técnicas (GTFOBins, MITRE ATT&CK, LOLBAS, Atomic Red Team...). Esta es
la **Capa 1** (estructurada, sin dependencias en runtime). La Capa 2 (semántica/embeddings sobre
HackTricks/writeups/feeds) se construye aparte. La QUERY (query_kb.py) es solo stdlib; los
ingesters pueden usar parsers (PyYAML) porque son un paso OFFLINE.
"""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kb.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS techniques (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,         -- gtfobins / attack / lolbas / atomic / payloads
    platform      TEXT,                  -- linux / windows / multi
    category      TEXT,                  -- privesc / execution / file-read / persistence / lateral ...
    tactic        TEXT,                  -- táctica MITRE (si aplica)
    mitre_id      TEXT,                  -- T#### (si aplica)
    name          TEXT NOT NULL,         -- nombre corto (binario / técnica)
    subtype       TEXT,                  -- p.ej. función GTFOBins: suid/sudo/capabilities
    preconditions TEXT,                  -- requisitos (SUID activo, sudo NOPASSWD, capability...)
    command       TEXT,                  -- comando / PoC accionable
    description   TEXT,
    tags          TEXT,                  -- JSON array de keywords para búsqueda
    source_ref    TEXT,                  -- URL de la fuente
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_kb_name     ON techniques(name);
CREATE INDEX IF NOT EXISTS idx_kb_platform ON techniques(platform);
CREATE INDEX IF NOT EXISTS idx_kb_category ON techniques(category);
CREATE INDEX IF NOT EXISTS idx_kb_mitre    ON techniques(mitre_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_kb ON techniques(source, name, subtype, command);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def connect(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
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
