#!/usr/bin/env python3
"""
db.py — Capa de almacenamiento del RAG de vulnerabilidades (SQLite, sin dependencias).

Store local que alimenta al agente vuln-triage. Una sola tabla `vulns` con los datos de
CISA KEV + enriquecimiento EPSS (+ CVSS opcional vía NVD). Portable y verificable offline.
"""
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vulns.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS vulns (
    cve_id            TEXT PRIMARY KEY,
    vendor            TEXT,
    product           TEXT,
    name              TEXT,
    description       TEXT,
    cwes              TEXT,          -- JSON array serializado
    date_added_kev    TEXT,          -- fecha en KEV (NULL si no está en KEV)
    due_date          TEXT,
    required_action   TEXT,
    in_kev            INTEGER DEFAULT 0,
    ransomware        INTEGER DEFAULT 0,
    epss              REAL,          -- probabilidad 0-1 (NULL si no enriquecido)
    epss_percentile   REAL,
    cvss              REAL,          -- base score
    cvss_severity     TEXT,
    cvss_vector       TEXT,
    cvss_source       TEXT,          -- origen del CVSS: cvelistV5 / vulncheck / eip / nvd
    ssvc              TEXT,          -- decisión SSVC de CISA (JSON: exploitation/automatable/impact)
    exploit_public    INTEGER,       -- 1 si hay exploit/PoC público conocido
    exploit_sources   TEXT,          -- JSON: ["ExploitDB","Metasploit","Nuclei",...]
    exploit_maturity  TEXT,          -- p.ej. weaponized / poc / unproven
    vulncheck_kev     INTEGER,       -- KEV de VulnCheck (más amplia que CISA KEV)
    updated_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_product ON vulns(product);
CREATE INDEX IF NOT EXISTS idx_vendor  ON vulns(vendor);
CREATE INDEX IF NOT EXISTS idx_kev     ON vulns(in_kev);
CREATE INDEX IF NOT EXISTS idx_epss    ON vulns(epss);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


# Columnas añadidas tras la v1 (migración idempotente para stores existentes).
MIGRATIONS = {
    "cvss_vector": "TEXT", "cvss_source": "TEXT", "ssvc": "TEXT",
    "exploit_public": "INTEGER", "exploit_sources": "TEXT",
    "exploit_maturity": "TEXT", "vulncheck_kev": "INTEGER",
    "msf_modules": "TEXT",       # JSON: módulos Metasploit (fullname/type/rank)
    "nuclei_templates": "TEXT",  # JSON: rutas de plantillas Nuclei
    "published_date": "TEXT",    # fecha de publicación del CVE (de feeds recientes: CVEDetector/OpenCVE)
    "source_feed": "TEXT",       # JSON: feeds que surfacearon el CVE (kev/cvedetector/opencve)
}


def connect(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(vulns)")}
    for col, typ in MIGRATIONS.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE vulns ADD COLUMN {col} {typ}")
    conn.commit()
    return conn


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default
