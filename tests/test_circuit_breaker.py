#!/usr/bin/env python3
"""Tests del CIRCUIT-BREAKER por target (control C22, v2.57 — idea de BugTraceAI).

Cubre la lógica pura (clasificación de salida, máquina de estado abrir/cerrar/cooldown) y el
contrato del hook por stdin (PostToolUse cuenta fallos → PreToolUse bloquea al abrir → 'up' cierra).
Clave de diseño verificada: un HTTP 4xx/5xx NO abre el breaker (el host responde); solo los fallos de
CONEXIÓN (rechazo/timeout/DNS/host-down) cuentan.

    python tests/test_circuit_breaker.py    (sale 1 si algo falla).
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
import circuit_breaker as cb  # noqa: E402

PASS, FAIL = 0, 0


def ok(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [FALLO] {msg}")


# ── classify (fallos de conexión en STDERR; host-vivo/tool-self en el completo) ──────────────
# Fallos de conexión: van por STDERR (curl/ssh los emiten ahí).
for err in ("curl: (7) Failed to connect to 10.0.0.5 port 80: Connection refused",
            "ssh: connect to host 10.0.0.5 port 22: Connection timed out",
            "curl: (6) Could not resolve host: app.lab.test"):
    ok(cb.classify(err, err) == "fail", f"fail(stderr): {err[:40]}")
# Frases de host-caído de tools de scan: SOLO cuentan si el COMANDO es un escáner (nmap/ping).
ok(cb.classify("", "Note: Host seems down (0 hosts up)", "nmap -sn 10.0.0.5") == "fail",
   "fail(tool): nmap '0 hosts up' con comando nmap")
ok(cb.classify("", "ping: 100% packet loss", "ping -c 4 10.0.0.5") == "fail",
   "fail(tool): ping '100% packet loss' con comando ping")
# SEGURIDAD (auto-evasión tool-self, bloqueante del council): la MISMA frase en el BODY de un curl
# (comando NO escáner) NO cuenta — el target no dispara su breaker metiendo 'host seems down' en su HTML.
ok(cb.classify("", "<pre>host seems down</pre>\n0 hosts up", "curl http://x/") == "neutral",
   "auto-evasión: frase tool-self en body de curl (no escáner) NO cuenta")
ok(cb.classify("", "destination host unreachable", "wget http://x/") == "neutral",
   "auto-evasión: frase tool-self en salida de wget NO cuenta")

for full in ("HTTP/1.1 500 Internal Server Error",     # responde => vivo, aunque sea 5xx
             "HTTP/2 403 Forbidden",
             "Host is up (0.012s latency). 22/tcp open ssh",
             "< HTTP/1.1 200 OK"):
    ok(cb.classify("", full) == "up", f"up: {full[:40]}")

ok(cb.classify("", "total 12\ndrwxr-xr-x 2 root root") == "neutral", "neutral: salida sin señal")
ok(cb.classify("", "") == "neutral", "neutral: vacío")
# La señal de host-vivo GANA sobre un timeout suelto en el mismo output.
ok(cb.classify("connection timed out on 81", "22/tcp open ssh") == "up",
   "up gana a un timeout suelto (host respondió en otro puerto)")
# SEGURIDAD (auto-evasión): un fallo de conexión en el BODY (stdout), con stderr vacío, NO cuenta —
# el target no puede disparar el breaker devolviendo 'Connection refused' en su respuesta.
ok(cb.classify("", "connection refused\nno route to host") == "neutral",
   "auto-evasión: 'connection refused' en el body (stdout) NO dispara el breaker")

# ── record_outcome / open_breaker_target (máquina de estado, pura) ───────────────────────────
st = {}
for i in range(5):
    cb.record_outcome(st, {"10.0.0.5"}, "fail", now=1000 + i, threshold=5)
ok(st["10.0.0.5"]["fails"] == 5 and st["10.0.0.5"]["opened_at"] == 1004, "5 fallos => breaker ABIERTO")
h, rec = cb.open_breaker_target(st, {"10.0.0.5"}, now=1100, cooldown=300)
ok(h == "10.0.0.5", "dentro del cooldown => bloquea")
h2, _ = cb.open_breaker_target(st, {"10.0.0.5"}, now=1004 + 301, cooldown=300)
ok(h2 is None, "pasado el cooldown => medio-abierto (no bloquea, permite sondeo)")
# 4 fallos aún NO abren.
st2 = {}
for i in range(4):
    cb.record_outcome(st2, {"h"}, "fail", now=i, threshold=5)
ok(st2["h"]["opened_at"] is None, "4 fallos (<umbral) NO abren")
# 'up' cierra/resetea.
cb.record_outcome(st, {"10.0.0.5"}, "up", now=2000, threshold=5)
ok(st["10.0.0.5"]["fails"] == 0 and st["10.0.0.5"]["opened_at"] is None, "'up' cierra el breaker")
# 'neutral' no toca el estado.
before = dict(st2["h"])
cb.record_outcome(st2, {"h"}, "neutral", now=99, threshold=5)
ok(st2["h"] == before, "'neutral' no modifica el estado")
# Multi-host: un verdict se aplica a TODOS los hosts del comando (imprecisión conocida, dirección
# segura: un 'up' de un host vivo resetea también al caído — nunca falso bloqueo).
stm = {}
cb.record_outcome(stm, {"up-host", "down-host"}, "fail", now=1, threshold=5)
ok(stm["up-host"]["fails"] == 1 and stm["down-host"]["fails"] == 1, "multi-host: fail cuenta en ambos")
cb.record_outcome(stm, {"up-host", "down-host"}, "up", now=2, threshold=5)
ok(stm["up-host"]["fails"] == 0 and stm["down-host"]["fails"] == 0, "multi-host: 'up' resetea ambos")

# _split_response robusto a la forma de tool_response (dict / string plano / None).
ok(cb._split_response({"tool_response": {"stdout": "body", "stderr": "err"}}) == ("err", "body\nerr"),
   "_split_response dict -> (stderr, stdout+stderr)")
ok(cb._split_response({"tool_response": "salida combinada"}) == ("", "salida combinada"),
   "_split_response string plano -> stderr vacío (conservador)")
ok(cb._split_response({}) == ("", ""), "_split_response sin tool_response -> vacío")

# ── contrato del hook por stdin (Post cuenta, Pre bloquea) ───────────────────────────────────
hook = os.path.join(ROOT, ".claude", "hooks", "circuit_breaker.py")
state_file = os.path.join(ROOT, "contracts", ".circuit_state")
_backup = None
if os.path.exists(state_file):
    _backup = open(state_file, encoding="utf-8").read()
    os.remove(state_file)


def run(event):
    p = subprocess.run([sys.executable, hook], input=json.dumps(event), capture_output=True, text=True)
    return p.stdout.strip()


TARGET = "203.0.113.77"  # IP literal, sin dependencia de scope
post_fail = {"tool_name": "Bash", "hook_event_name": "PostToolUse",
             "tool_input": {"command": f"curl http://{TARGET}/"},
             "tool_response": {"stdout": "", "stderr": f"curl: (7) Failed to connect to {TARGET}: Connection refused"}}
for _ in range(5):
    run(post_fail)
pre = {"tool_name": "Bash", "hook_event_name": "PreToolUse", "tool_input": {"command": f"nmap {TARGET}"}}
out = run(pre)
denied = False
try:
    denied = json.loads(out).get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
except Exception:
    denied = False
ok(denied, "hook: 5 fallos de conexión por Post => Pre BLOQUEA el target")

# Un 'up' cierra y desbloquea.
run({"tool_name": "Bash", "hook_event_name": "PostToolUse", "tool_input": {"command": f"curl http://{TARGET}/"},
     "tool_response": {"stdout": "HTTP/1.1 200 OK"}})
ok(run(pre) == "", "hook: tras 'up' el breaker se cierra => Pre permite")

# SEGURIDAD end-to-end: un target hostil que devuelve el fallo en el BODY (stdout, stderr vacío) NO
# debe abrir su breaker (5 respuestas así y sigue permitido).
EVIL = "198.51.100.9"
evasion = {"tool_name": "Bash", "hook_event_name": "PostToolUse",
           "tool_input": {"command": f"curl http://{EVIL}/"},
           "tool_response": {"stdout": "connection refused\nno route to host\nconnection timed out", "stderr": ""}}
for _ in range(6):
    run(evasion)
pre_evil = {"tool_name": "Bash", "hook_event_name": "PreToolUse", "tool_input": {"command": f"nmap {EVIL}"}}
ok(run(pre_evil) == "", "auto-evasión e2e: 6 fallos en el BODY no abren el breaker (target no se auto-protege)")

# SEGURIDAD e2e (tool-self en body, bloqueante del council): frase de host-caído en el BODY de un curl.
EVIL2 = "198.51.100.23"
evasion2 = {"tool_name": "Bash", "hook_event_name": "PostToolUse",
            "tool_input": {"command": f"curl http://{EVIL2}/"},
            "tool_response": {"stdout": "host seems down\n0 hosts up\n100% packet loss", "stderr": ""}}
for _ in range(6):
    run(evasion2)
ok(run({"tool_name": "Bash", "hook_event_name": "PreToolUse", "tool_input": {"command": f"nmap {EVIL2}"}}) == "",
   "auto-evasión e2e: frase tool-self en body de curl no abre el breaker")

# Sin target de red => nunca interfiere.
ok(run({"tool_name": "Bash", "hook_event_name": "PreToolUse", "tool_input": {"command": "ls -la"}}) == "",
   "hook: comando sin target => no interfiere")

# restaura el estado previo
try:
    os.remove(state_file)
except OSError:
    pass
if _backup is not None:
    with open(state_file, "w", encoding="utf-8") as f:
        f.write(_backup)

print(f"\n  RESUMEN test_circuit_breaker:  {PASS} OK   {FAIL} fallos")
sys.exit(1 if FAIL else 0)
