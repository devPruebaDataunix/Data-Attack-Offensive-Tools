#!/usr/bin/env python3
"""
budget_guard.py — Hook PreToolUse: kill-switch determinista de consumo (control C13, OWASP
LLM10 Unbounded Consumption).

Cuenta las invocaciones Bash por engagement y BLOQUEA cuando se supera un techo. Es la red
contra un bucle desbocado (relevante con cupo Pro y con un C2/exploit que itere sin fin). El
techo sale de contracts/scope.json -> constraints.max_actions (si está), si no DEFAULT_MAX.
El contador se guarda en contracts/.action_count (gitignored) y se REINICIA solo cuando cambia
el engagement_id. Para reiniciarlo a mano, basta con borrar ese fichero.

Protocolo Claude Code (idéntico a scope_guard.py):
- Recibe JSON por stdin: {"tool_name":"Bash","tool_input":{"command":"..."}, ...}.
- Para BLOQUEAR: imprime la decisión y sale 0.
- Cualquier error (sin stdin, contador ilegible/no escribible) => sale 0 (FAIL-OPEN: el
  kill-switch nunca debe romper el entorno por sí mismo).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COUNT_FILE = os.path.join(ROOT, "contracts", ".action_count")
ENGAGEMENT = os.path.join(ROOT, "contracts", "engagement.json")
SCOPE = os.path.join(ROOT, "contracts", "scope.json")
DEFAULT_MAX = 1000  # techo por defecto; súbelo con constraints.max_actions en scope.json


def deny(reason):
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(out))
    sys.exit(0)


def current_key():
    """Clave del contador = engagement_id (de engagement.json o, en su defecto, scope.json)."""
    for p in (ENGAGEMENT, SCOPE):
        try:
            with open(p, "r", encoding="utf-8") as f:
                eid = json.load(f).get("engagement_id")
            if eid:
                return str(eid)
        except Exception:
            continue
    return "default"


def ceiling():
    try:
        with open(SCOPE, "r", encoding="utf-8") as f:
            c = json.load(f).get("constraints", {}).get("max_actions")
        if isinstance(c, int) and c > 0:
            return c
    except Exception:
        pass
    return DEFAULT_MAX


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if event.get("tool_name") != "Bash":
        sys.exit(0)

    key = current_key()
    cap = ceiling()

    count = 0
    try:
        with open(COUNT_FILE, "r", encoding="utf-8") as f:
            st = json.load(f)
        if st.get("key") == key:  # mismo engagement => acumula; si cambió => reinicia
            count = int(st.get("count", 0))
    except Exception:
        count = 0  # ausente/corrupto => empezamos de cero

    count += 1
    try:
        tmp = COUNT_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"key": key, "count": count}, f)
        os.replace(tmp, COUNT_FILE)
    except Exception:
        pass  # si no se puede persistir, no bloqueamos por ello

    if count > cap:
        deny(f"KILL-SWITCH (LLM10): alcanzado el límite de {cap} acciones Bash en el engagement "
             f"'{key}'. Detente y revisa con el operador antes de seguir. Sube el techo con "
             f"constraints.max_actions en contracts/scope.json, o borra contracts/.action_count "
             f"para reiniciar el contador.")
    sys.exit(0)


if __name__ == "__main__":
    main()
