#!/usr/bin/env python3
"""
secret_scan.py — Hook PostToolUse que vigila secretos DEL OPERADOR en el blackboard (control
C12, OWASP LLM02 Sensitive Information Disclosure).

Cuando se escribe contracts/engagement.json, escanea su contenido en busca de secretos que
casi con seguridad son del OPERADOR/motor (clave privada, API key de Anthropic, token del
bot) — esos jamás deberían acabar en el engagement de un cliente. Si aparece alguno, devuelve
feedback correctivo al Orquestador para que lo quite/redacte. NO bloquea ante credenciales
que el equipo descubre del CLIENTE (eso es un hallazgo legítimo): por eso usa operator_only.

Mismo contrato que validate_blackboard.py:
- Recibe JSON por stdin (tool_name / tool_input.file_path).
- Para señalar: imprime {"decision":"block","reason":...} y sale 0.
- Cualquier ambigüedad (no es engagement.json, sin secretos, error) => sale 0 (fail-open).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGAGEMENT = os.path.join(ROOT, "contracts", "engagement.json")


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if event.get("tool_name") not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)

    fp = (event.get("tool_input") or {}).get("file_path", "") or ""
    if not fp:
        sys.exit(0)
    # Ancla a NUESTRO engagement.json (no a un fichero homónimo de otro repo).
    try:
        same = os.path.realpath(fp) == os.path.realpath(ENGAGEMENT)
    except Exception:
        same = False
    if not same:
        sys.exit(0)

    if not os.path.isfile(ENGAGEMENT):
        sys.exit(0)
    try:
        with open(ENGAGEMENT, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        sys.exit(0)

    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from redactor import scan
        labels = scan(text, operator_only=True)
    except Exception:
        sys.exit(0)  # si el detector falla, jamás bloqueamos el flujo

    if labels:
        reason = ("Se detectaron posibles secretos del OPERADOR/motor en el blackboard "
                  "(contracts/engagement.json), que no deberían acabar ahí: "
                  + ", ".join(labels) + ". Quítalos o sustitúyelos por [REDACTED] antes de "
                  "seguir. (Las credenciales DESCUBIERTAS del cliente sí van en el hallazgo, "
                  "pero no claves del propio motor/operador.)")
        print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    main()
