#!/usr/bin/env python3
"""
subagent_stop.py — Hook SubagentStop: AUDITORÍA forense del ciclo de vida de subagentes.

Cada vez que un especialista termina, Claude Code dispara SubagentStop en la sesión principal.
Este hook deja un registro JSONL **inmutable por anexado** (quién terminó, cuándo, en qué sesión y
engagement) para la **trazabilidad** del encargo (CONSTITUTION §C10). Complementa, no duplica, a
`a2a_router_nudge.py` (ese refuerza el router del bus A2A; este solo audita).

NO es una puerta de seguridad y NO bloquea: la finalización de un subagente jamás se interrumpe por
la auditoría. Las puertas duras siguen siendo scope_guard / budget_guard / approval_gate / secret_scan
/ a2a_guard, y NINGUNA se relaja. Esto solo AÑADE observabilidad.

Destino del registro (en este orden):
  1. env ORCH_AUDIT_DIR            -> <ORCH_AUDIT_DIR>/subagents.jsonl   (sandbox / test)
  2. engagement_id en el blackboard-> engagements/<id>/evidence/subagents.jsonl  (junto al loot)
  3. fallback                      -> .claude/audit/subagents.jsonl      (gitignored)

Protocolo Claude Code (SubagentStop): lee JSON por stdin (agent_type, agent_id, session_id,
transcript_path, ...). Aquí SIEMPRE salimos 0 sin decisión (observacional).
FAIL-SAFE: ante CUALQUIER error (JSON a medias, disco, permisos) se sale 0 en silencio — la
auditoría nunca rompe un engagement.
"""
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGAGEMENT = os.path.join(ROOT, "contracts", "engagement.json")


def engagement_id():
    """engagement_id del blackboard, o None si no existe / está a medio escribir."""
    try:
        with open(ENGAGEMENT, encoding="utf-8") as f:
            return json.load(f).get("engagement_id")
    except Exception:
        return None


def audit_file(eid):
    """Resuelve el fichero de auditoría y garantiza su directorio. Ver orden en el docstring."""
    override = os.environ.get("ORCH_AUDIT_DIR")
    if override:
        base = override
    elif eid:
        base = os.path.join(ROOT, "engagements", str(eid), "evidence")
    else:
        base = os.path.join(ROOT, ".claude", "audit")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "subagents.jsonl")


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # sin payload utilizable

    # Registrado solo para SubagentStop; si llega otro evento, no auditamos (mantiene el log limpio).
    if event.get("hook_event_name") not in (None, "SubagentStop"):
        sys.exit(0)

    eid = engagement_id()
    record = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": "SubagentStop",
        "agent_type": event.get("agent_type"),
        "agent_id": event.get("agent_id"),
        "session_id": event.get("session_id"),
        "engagement_id": eid,
        "transcript_path": event.get("transcript_path"),
    }
    try:
        with open(audit_file(eid), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # la auditoría jamás rompe el engagement
    sys.exit(0)


if __name__ == "__main__":
    main()
