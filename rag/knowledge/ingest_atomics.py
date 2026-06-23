#!/usr/bin/env python3
"""
ingest_atomics.py — Ingesta Atomic Red Team (comandos accionables por técnica ATT&CK) al RAG de conocimiento.

Atomic Red Team aporta lo que a ATT&CK le falta: el COMANDO concreto por técnica (lo que ejecuta un
operador), por plataforma y executor. Fuente: repo redcanaryco/atomic-red-team → `atomics/T<id>/T<id>.yaml`.
Formato:
  attack_technique: T1003.008
  atomic_tests:
    - name: Access /etc/shadow (Local)
      supported_platforms: [linux]
      input_arguments: { output_file: { default: /tmp/x } }
      executor: { name: bash, command: "cat /etc/shadow > #{output_file}", elevation_required: true }

Los `#{var}` se sustituyen por su `default` de input_arguments. Solo se ingieren tests linux/windows
(descarta macos-only, iaas/azure/containers/office-365) y con comando (descarta executor 'manual').

Uso:
    python ingest_atomics.py --src <ruta al repo atomic-red-team clonado>
(PyYAML solo en ingesta; la query es stdlib.)
"""
import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

import yaml  # solo ingesta (paso offline)

import kb

ATOMIC_URL = "https://github.com/redcanaryco/atomic-red-team/blob/master/atomics/"
SUBST = re.compile(r"#\{([^}]+)\}")

# Prefijo de técnica ATT&CK -> (category, tactic) para etiquetar el comando. Cubre lo común en labs.
TACTIC_BY_PREFIX = [
    ("T1548", ("privesc", "privilege-escalation")), ("T1068", ("privesc", "privilege-escalation")),
    ("T1078", ("privesc", "privilege-escalation")), ("T1134", ("privesc", "privilege-escalation")),
    ("T1543", ("persistence", "persistence")), ("T1547", ("persistence", "persistence")),
    ("T1053", ("persistence", "persistence")), ("T1136", ("persistence", "persistence")),
    ("T1505", ("persistence", "persistence")), ("T1098", ("persistence", "persistence")),
    ("T1003", ("credential-access", "credential-access")), ("T1555", ("credential-access", "credential-access")),
    ("T1552", ("credential-access", "credential-access")), ("T1110", ("credential-access", "credential-access")),
    ("T1558", ("credential-access", "credential-access")), ("T1056", ("credential-access", "credential-access")),
    ("T1082", ("discovery", "discovery")), ("T1083", ("discovery", "discovery")),
    ("T1057", ("discovery", "discovery")), ("T1018", ("discovery", "discovery")),
    ("T1046", ("discovery", "discovery")), ("T1087", ("discovery", "discovery")),
    ("T1069", ("discovery", "discovery")), ("T1049", ("discovery", "discovery")),
    ("T1021", ("lateral", "lateral-movement")), ("T1570", ("lateral", "lateral-movement")),
    ("T1210", ("lateral", "lateral-movement")),
    ("T1070", ("defense-evasion", "defense-evasion")), ("T1027", ("defense-evasion", "defense-evasion")),
    ("T1562", ("defense-evasion", "defense-evasion")), ("T1112", ("defense-evasion", "defense-evasion")),
    ("T1218", ("defense-evasion", "defense-evasion")), ("T1140", ("defense-evasion", "defense-evasion")),
    ("T1105", ("ingress", "command-and-control")), ("T1571", ("ingress", "command-and-control")),
    ("T1041", ("exfil", "exfiltration")), ("T1048", ("exfil", "exfiltration")),
    ("T1059", ("execution", "execution")), ("T1106", ("execution", "execution")),
    ("T1204", ("execution", "execution")), ("T1569", ("execution", "execution")),
]


def categorize(tid):
    for prefix, (cat, tactic) in TACTIC_BY_PREFIX:
        if tid.startswith(prefix):
            return cat, tactic
    return "execution", "execution"


def substitute(command, input_args):
    defaults = {}
    if isinstance(input_args, dict):
        for k, v in input_args.items():
            if isinstance(v, dict) and v.get("default") is not None:
                defaults[k] = str(v["default"])

    def repl(m):
        return defaults.get(m.group(1), m.group(0))
    return SUBST.sub(repl, command)


def platform_of(supported):
    sp = {str(p).lower() for p in (supported or [])}
    lin, win = "linux" in sp, "windows" in sp
    if lin and win:
        return "multi"
    if lin:
        return "linux"
    if win:
        return "windows"
    return None  # macos-only / cloud / containers -> fuera de alcance


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="ruta al repo atomic-red-team clonado")
    args = ap.parse_args()
    adir = os.path.join(args.src, "atomics")
    files = sorted(glob.glob(os.path.join(adir, "T*", "T*.yaml")))
    if not files:
        print(f"[Atomic] No encuentro ficheros en {adir}", file=sys.stderr)
        sys.exit(2)

    conn = kb.connect()
    now = datetime.now(timezone.utc).isoformat()
    n_tech = n_test = 0
    for f in files:
        try:
            data = yaml.safe_load(open(f, encoding="utf-8", errors="replace"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        tid = str(data.get("attack_technique") or "").strip()
        if not tid:
            continue
        category, tactic = categorize(tid)
        url = ATOMIC_URL + tid + "/" + tid + ".md"
        n_tech += 1
        for test in (data.get("atomic_tests") or []):
            if not isinstance(test, dict):
                continue
            platform = platform_of(test.get("supported_platforms"))
            if platform is None:
                continue
            ex = test.get("executor") or {}
            exname = str(ex.get("name") or "").strip().strip('"')
            command = ex.get("command")
            if not command or exname == "manual":
                continue
            command = substitute(str(command), test.get("input_arguments")).strip()
            if not command:
                continue
            tname = (test.get("name") or "").strip()
            desc = (test.get("description") or "").strip().replace("\n", " ")[:500]
            precond = "elevación requerida" if ex.get("elevation_required") else ""
            tags = json.dumps(sorted({tid.lower(), exname, category, "atomic",
                                      *(w for w in re.split(r"\W+", tname.lower()) if len(w) > 3)}))
            conn.execute(
                "INSERT OR IGNORE INTO techniques(source,platform,category,tactic,mitre_id,name,"
                "subtype,preconditions,command,description,tags,source_ref,updated_at) "
                "VALUES('atomic',?,?,?,?,?,?,?,?,?,?,?,?)",
                (platform, category, tactic, tid, tname or tid, exname, precond,
                 command, desc, tags, url, now),
            )
            n_test += 1
    kb.set_meta(conn, "atomic_last_sync", now)
    kb.set_meta(conn, "atomic_techniques", n_tech)
    conn.commit()
    total = conn.execute("SELECT COUNT(*) c FROM techniques").fetchone()["c"]
    atom = conn.execute("SELECT COUNT(*) c FROM techniques WHERE source='atomic'").fetchone()["c"]
    conn.close()
    print(f"[Atomic] {n_tech} técnicas, {n_test} tests (upsert). Store: {total} ({atom} atomic).")


if __name__ == "__main__":
    main()
