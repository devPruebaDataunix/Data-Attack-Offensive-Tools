#!/usr/bin/env python3
"""
test_blackboard_guard.py — Pruebas del guard C21 (anti-escritura del blackboard por Bash).

Bloquea las vías comunes de mutar contracts/engagement.json por Bash (que esquivarían
validate_blackboard/secret_scan), pero NO la lectura. Lógica pura + contrato del hook por stdin.

    python tests/test_blackboard_guard.py    (sale 1 si algo falla).
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))

import blackboard_guard as bg  # noqa: E402

PASS, FAIL = 0, 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [FALLO] {msg}")


# --- ESCRITURAS que DEBEN bloquearse -------------------------------------------------------
BLOCK = [
    'echo "{}" > contracts/engagement.json',
    'echo "{}" >> contracts/engagement.json',
    "cat foo.json > contracts/engagement.json",
    "jq '.x=1' contracts/engagement.json > tmp && mv tmp contracts/engagement.json",
    "sed -i 's/a/b/' contracts/engagement.json",
    "tee contracts/engagement.json < foo",
    "cp loot/x contracts/engagement.json",
    "python3 -c \"open('contracts/engagement.json','w').write('x')\"",
    "truncate -s0 contracts/engagement.json",
    # Idiomas Python COMUNES no ofuscados (M2 del council de seguridad):
    'python3 -c "from pathlib import Path; Path(\'contracts/engagement.json\').write_text(d)"',
    'python3 -c "import shutil; shutil.copy(\'loot/x\', \'contracts/engagement.json\')"',
    'python3 -c "import shutil; shutil.move(\'tmp.json\', \'contracts/engagement.json\')"',
]
for cmd in BLOCK:
    ok(bg.blocking_reason(cmd) is not None, f"bloquea: {cmd[:50]}")

# --- LECTURAS / no-blackboard que NO deben bloquearse --------------------------------------
ALLOW = [
    "cat contracts/engagement.json",
    "jq '.findings' contracts/engagement.json",
    "grep identity contracts/engagement.json",
    "python3 -c \"import json; json.load(open('contracts/engagement.json'))\"",
    "echo hola > salida.txt",
    "cat contracts/scope.json > /tmp/s.json",
    "ls contracts/",
    # LEER el blackboard para copiarlo a otro sitio NO es escribirlo (el BB va en los args, no es el destino):
    'python3 -c "p.write_bytes(open(\'contracts/engagement.json\',\'rb\').read())"',
]
for cmd in ALLOW:
    ok(bg.blocking_reason(cmd) is None, f"permite: {cmd[:50]}")

ok(bg.blocking_reason("") is None, "vacío => None")
ok(bg.blocking_reason(None) is None, "None => None")

# --- contrato del hook por stdin -----------------------------------------------------------
hook = os.path.join(ROOT, ".claude", "hooks", "blackboard_guard.py")
ev = {"tool_name": "Bash", "tool_input": {"command": "echo x > contracts/engagement.json"}}
p = subprocess.run([sys.executable, hook], input=json.dumps(ev), capture_output=True, text=True)
try:
    denied = json.loads(p.stdout).get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
except Exception:
    denied = False
ok(denied, "hook: escritura por Bash => permissionDecision=deny")

ev_read = {"tool_name": "Bash", "tool_input": {"command": "cat contracts/engagement.json"}}
p2 = subprocess.run([sys.executable, hook], input=json.dumps(ev_read), capture_output=True, text=True)
ok(p2.stdout.strip() == "", "hook: lectura del blackboard => permitido (sin salida)")

ev_other = {"tool_name": "Write", "tool_input": {"file_path": "contracts/engagement.json", "content": "{}"}}
p3 = subprocess.run([sys.executable, hook], input=json.dumps(ev_other), capture_output=True, text=True)
ok(p3.stdout.strip() == "", "hook: Write (no Bash) => no interfiere (esa vía SÍ pasa por los guards PostToolUse)")

print(f"\n  RESUMEN test_blackboard_guard:  {PASS} OK   {FAIL} fallos")
sys.exit(1 if FAIL else 0)
