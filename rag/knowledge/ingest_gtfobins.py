#!/usr/bin/env python3
"""
ingest_gtfobins.py — Ingesta GTFOBins (abuso de binarios Unix: privesc/exec/lectura) al RAG de conocimiento.

GTFOBins = binarios legítimos abusables (SUID, sudo, capabilities, file-read/write, shells...). Para
un operador es señal directa de privesc. Fuente: repo GTFOBins.github.io → ficheros `_gtfobins/<bin>`
(Jekyll collection, normalmente SIN extensión) con frontmatter YAML. Formato:
  functions:
    <acción p.ej. shell/file-read>:
      - code: <comando base>
        contexts: { sudo: , suid: {code: ...}, capabilities: , unprivileged: }
Los CONTEXTOS sudo/suid/capabilities/limited-suid son la señal de PRIVESC.

Uso:
    python ingest_gtfobins.py --src <ruta al repo GTFOBins.github.io>
(El refresh clona el repo; aquí se parsea. PyYAML solo en ingesta; la query es stdlib.)
"""
import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

import yaml  # solo ingesta (paso offline)

import kb

GTFO_URL = "https://gtfobins.github.io/gtfobins/"

# Contexto de PRIVILEGIO de GTFOBins -> (mitre_id, precondición). Señal directa de privesc.
PRIV_CTX = {
    "suid": ("T1548.001", "binario con bit SUID activo (propietario root)"),
    "limited-suid": ("T1548.001", "binario con SUID; usa shell con -p para no dropear privilegios"),
    "sudo": ("T1548.003", "sudo permite ejecutar el binario (ideal: NOPASSWD)"),
    "capabilities": ("T1548", "binario con capability peligrosa (p.ej. cap_setuid+ep)"),
}
# Tipo de ACCIÓN de GTFOBins -> (category, mitre_id)
ACTION_MAP = {
    "shell": ("execution", "T1059"), "command": ("execution", "T1059"),
    "reverse-shell": ("execution", "T1059"), "non-interactive-reverse-shell": ("execution", "T1059"),
    "bind-shell": ("execution", "T1059"), "non-interactive-bind-shell": ("execution", "T1059"),
    "file-read": ("file-read", "T1005"), "file-write": ("file-write", "T1565"),
    "file-download": ("ingress", "T1105"), "file-upload": ("exfil", "T1041"),
    "library-load": ("hijack", "T1574"),
}


def parse_frontmatter(text):
    # GTFOBins son YAML puro (--- ... ...). yaml.safe_load maneja los marcadores --- y ...
    try:
        doc = yaml.safe_load(text)
        if isinstance(doc, dict):
            return doc
    except Exception:
        pass
    # fallback: Jekyll con cuerpo -> extraer solo el frontmatter entre el primer --- y el cierre
    s = text.lstrip("﻿").lstrip()
    if s.startswith("---"):
        body = s[3:]
        cut = len(body)
        for marker in ("\n---", "\n..."):
            i = body.find(marker)
            if i != -1:
                cut = min(cut, i)
        try:
            doc = yaml.safe_load(body[:cut])
            return doc if isinstance(doc, dict) else None
        except Exception:
            return None
    return None


def rows_from_entry(functype, entry):
    """Aplana una entrada GTFOBins en (functype, contexto, code, desc). Soporta el modelo con
    `contexts` (acción + privilegio) y el plano (la propia función es el privilegio)."""
    if not isinstance(entry, dict):
        return [(functype, None, str(entry).strip(), "")]
    base_code = (entry.get("code") or "").strip()
    base_desc = (entry.get("description") or "").strip()
    contexts = entry.get("contexts")
    if isinstance(contexts, dict) and contexts:
        out = []
        for ctx, cval in contexts.items():
            if isinstance(cval, dict):
                code = (cval.get("code") or base_code or "").strip()
                desc = (cval.get("description") or base_desc or "").strip()
            else:  # contexto vacío -> hereda el code base
                code, desc = base_code, base_desc
            out.append((functype, ctx, code, desc))
        return out
    return [(functype, None, base_code, base_desc)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="ruta al repo GTFOBins.github.io clonado")
    args = ap.parse_args()
    gdir = os.path.join(args.src, "_gtfobins")
    files = sorted(f for f in glob.glob(os.path.join(gdir, "*")) if os.path.isfile(f))
    if not files:
        print(f"[GTFOBins] No encuentro ficheros en {gdir}", file=sys.stderr)
        sys.exit(2)

    conn = kb.connect()
    now = datetime.now(timezone.utc).isoformat()
    n_bin = n_tech = 0
    for f in files:
        binname = os.path.splitext(os.path.basename(f))[0]
        try:
            raw = open(f, encoding="utf-8", errors="replace").read()
        except OSError:
            continue  # symlink/alias roto u otro problema de E/S (p.ej. en Windows)
        data = parse_frontmatter(raw)
        if not data or "functions" not in data:
            continue
        n_bin += 1
        for functype, entries in (data.get("functions") or {}).items():
            if not isinstance(entries, list):
                entries = [entries]
            for entry in entries:
                for (ft, ctx, code, desc) in rows_from_entry(functype, entry):
                    if not code:
                        continue
                    priv = ctx if ctx in PRIV_CTX else (ft if ft in PRIV_CTX else None)
                    if priv:
                        category, mitre = "privesc", PRIV_CTX[priv][0]
                        precond, subtype = PRIV_CTX[priv][1], priv
                    else:
                        category, mitre = ACTION_MAP.get(ft, ("misc", None))
                        precond = ""
                        subtype = ft if ctx in (None, "unprivileged") else f"{ft}/{ctx}"
                    tags = json.dumps(sorted({binname, ft, subtype, category, "gtfobins", "linux"}))
                    conn.execute(
                        "INSERT OR IGNORE INTO techniques(source,platform,category,tactic,mitre_id,name,"
                        "subtype,preconditions,command,description,tags,source_ref,updated_at) "
                        "VALUES('gtfobins','linux',?,?,?,?,?,?,?,?,?,?,?)",
                        (category, None, mitre, binname, subtype, precond, code, desc, tags,
                         GTFO_URL + binname + "/", now),
                    )
                    n_tech += 1
    kb.set_meta(conn, "gtfobins_last_sync", now)
    kb.set_meta(conn, "gtfobins_binaries", n_bin)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) c FROM techniques").fetchone()["c"]
    priv = conn.execute("SELECT COUNT(*) c FROM techniques WHERE category='privesc'").fetchone()["c"]
    conn.close()
    print(f"[GTFOBins] {n_bin} binarios, {n_tech} técnicas (upsert). Store: {total} ({priv} privesc).")


if __name__ == "__main__":
    main()
