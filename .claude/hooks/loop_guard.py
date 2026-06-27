#!/usr/bin/env python3
"""
loop_guard.py — Hook PreToolUse: control determinista ANTI-BUCLE (control C19).

Un agente atascado puede repetir el MISMO comando una y otra vez (thrashing) o oscilar entre
dos (A,B,A,B) sin progresar — quema presupuesto, genera ruido y no avanza. Este hook lleva un
historial corto de comandos normalizados por engagement y BLOQUEA cuando un comando se ha
repetido demasiadas veces, o cuando detecta oscilación de periodo 2. Obliga a CAMBIAR de
hipótesis/técnica o a escalar, en vez de insistir. Complementa a C13 (kill-switch global) y a
C15 (techo de hops A2A): esto es anti-bucle a nivel de ACCIÓN.

Solo cuenta repeticiones IDÉNTICAS (normalizadas) de acciones potencialmente ofensivas; las
utilidades de sondeo/espera/inspección (nc -z, ping, sleep, curl/wget de estado, ls, cat…) están
EXENTAS, porque repetirlas es legítimo (esperar una reverse shell, hacer poll de un job, listar
loot). Un loop de ataque real suele variar parámetros (otra normalización) y no se contabiliza como
repetición — el riesgo dominante aquí es el FALSO POSITIVO de sondeo, no el bucle ofensivo.

Configuración (contracts/scope.json -> constraints):
- `max_repeat` (int, def. 5): repeticiones idénticas toleradas en la ventana antes de bloquear.

Estado en contracts/.cmd_history (gitignored), keyed por engagement_id; se reinicia solo al
cambiar de engagement (o borrando el fichero).

Protocolo Claude Code (idéntico a budget_guard.py):
- Recibe JSON por stdin: {"tool_name":"Bash","tool_input":{"command":"..."}, ...}.
- Para BLOQUEAR: imprime la decisión `deny` y sale 0.
- Cualquier error => sale 0 (FAIL-OPEN).
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HIST_FILE = os.path.join(ROOT, "contracts", ".cmd_history")
ENGAGEMENT = os.path.join(ROOT, "contracts", "engagement.json")
SCOPE = os.path.join(ROOT, "contracts", "scope.json")

WINDOW = 12          # nº de comandos recientes que se conservan/evalúan
DEFAULT_MAX_REPEAT = 5

# Utilidades de sondeo/espera/inspección: repetirlas es legítimo (poll de un job, esperar una
# shell, listar loot) => EXENTAS del conteo anti-bucle. Se comparan por basename del ejecutable.
BENIGN = {
    "nc", "ncat", "socat", "ping", "ping6", "sleep", "watch", "ss", "netstat", "ps", "ls",
    "cat", "stat", "id", "whoami", "pwd", "date", "echo", "tail", "head", "grep", "awk",
    "sed", "wc", "env", "which", "find", "dig", "host", "nslookup", "curl", "wget", "tput",
}
# Wrappers que preceden al ejecutable real (se saltan para hallar el basename de la utilidad).
WRAPPERS = {"sudo", "proxychains", "proxychains4", "stdbuf", "nice", "nohup", "time", "env",
            "timeout", "doas"}


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def current_key():
    for p in (ENGAGEMENT, SCOPE):
        try:
            with open(p, "r", encoding="utf-8") as f:
                eid = json.load(f).get("engagement_id")
            if eid:
                return str(eid)
        except Exception:
            continue
    return "default"


def max_repeat():
    try:
        with open(SCOPE, "r", encoding="utf-8") as f:
            v = json.load(f).get("constraints", {}).get("max_repeat")
        if isinstance(v, int) and v > 0:
            return v
    except Exception:
        pass
    return DEFAULT_MAX_REPEAT


def normalize(cmd):
    """Forma canónica para comparar 'el mismo comando': minúsculas, espacios colapsados y se
    quitan tokens volátiles (timestamps largos, temporales aleatorios) que no cambian la INTENCIÓN.
    Los puertos y flags se conservan (no se tocan dígitos cortos)."""
    s = cmd.lower().strip()
    s = re.sub(r"/tmp/\S+", "/tmp/X", s)        # temporales aleatorios
    s = re.sub(r"\b\d{8,}\b", "N", s)           # timestamps/epoch/PIDs largos (no puertos)
    s = re.sub(r"\s+", " ", s)
    return s


def base_util(norm):
    """Basename del primer ejecutable real del comando (salta wrappers y env VAR=val)."""
    for tok in norm.split():
        if "=" in tok:                 # env VAR=val
            continue
        base = tok.split("/")[-1]      # quita la ruta: /usr/bin/nc -> nc
        if base in WRAPPERS:
            continue
        if base.isdigit():             # argumento numérico de timeout/nice
            continue
        return base
    return ""


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if event.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = (event.get("tool_input", {}) or {}).get("command", "")
    if not cmd or not cmd.strip():
        sys.exit(0)

    key = current_key()
    norm = normalize(cmd)

    if base_util(norm) in BENIGN:      # sondeo/espera/inspección legítimos: ni se cuentan ni bloquean
        sys.exit(0)

    recent = []
    try:
        with open(HIST_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)
        if st.get("key") == key:
            recent = list(st.get("recent", []))
    except Exception:
        recent = []

    cap = max_repeat()

    # 1) Repetición idéntica: ya ejecutado `cap` veces en la ventana => bloquea la siguiente.
    if recent.count(norm) >= cap:
        deny(f"ANTI-BUCLE (C19): este comando se ha repetido {recent.count(norm)} veces sin progreso "
             f"en el engagement '{key}'. Detente y CAMBIA de hipótesis/técnica o escala al operador; "
             f"no insistas. (Umbral constraints.max_repeat={cap}; borra contracts/.cmd_history para reiniciar.)")

    # 2) Oscilación de periodo 2 (A,B,A,B): los últimos >=4 alternan entre exactamente 2 comandos.
    tail = (recent + [norm])[-4:]
    if len(tail) >= 4 and len(set(tail)) == 2 and all(tail[i] != tail[i + 1] for i in range(len(tail) - 1)):
        deny(f"ANTI-BUCLE (C19): oscilación detectada (alternas entre dos comandos sin avanzar) en el "
             f"engagement '{key}'. Rompe el ciclo: cambia de enfoque o escala al operador.")

    # Registra y persiste (atómico), conservando solo la ventana.
    recent.append(norm)
    recent = recent[-WINDOW:]
    try:
        tmp = HIST_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"key": key, "recent": recent}, f)
        os.replace(tmp, HIST_FILE)
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
