#!/usr/bin/env python3
"""
validate_blackboard.py — Hook PostToolUse que valida el blackboard tras cada escritura.

Cuando se modifica contracts/engagement.json (Write/Edit/MultiEdit), comprueba de forma
DETERMINISTA que cada finding/target/lesson/evidence tiene sus campos obligatorios (esquemas
en contracts/*.schema.json). Si falta alguno, devuelve feedback al Orquestador para que lo
corrija — sin romper la herramienta ni depender de ningún LLM. Es el control C5 de GUARDRAILS.md.

Protocolo Claude Code (PostToolUse):
- Recibe JSON por stdin con tool_name / tool_input (incluye file_path) / tool_response.
- Para señalar un problema: imprime {"decision":"block","reason":...} y sale 0 (el motivo se
  reinyecta al modelo para que corrija).
- Cualquier situación ambigua (no es engagement.json, JSON a medio escribir, validador
  ausente) => sale 0 sin interferir (fail-open).
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
    # Ancla a NUESTRO engagement.json (no a un contracts/engagement.json de otro repo).
    try:
        same = os.path.realpath(fp) == os.path.realpath(ENGAGEMENT)
    except Exception:
        same = False
    if not same:
        sys.exit(0)  # otra edición: no nos incumbe

    if not os.path.isfile(ENGAGEMENT):
        sys.exit(0)
    try:
        with open(ENGAGEMENT, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        sys.exit(0)  # a medio escribir o no parseable: no interferir

    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from blackboard import validate_engagement
        violations = validate_engagement(data)
    except Exception:
        sys.exit(0)  # si el validador falla, jamás bloqueamos el flujo

    if violations:
        reason = ("El blackboard (contracts/engagement.json) viola el esquema tras esta "
                  "escritura. Corrige estos campos obligatorios antes de seguir:\n- "
                  + "\n- ".join(violations))
        print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    main()
