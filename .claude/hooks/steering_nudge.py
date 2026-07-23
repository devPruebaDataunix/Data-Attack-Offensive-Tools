#!/usr/bin/env python3
"""
steering_nudge.py — Hook PostToolUse (matcher Task) que REFUERZA el pilotaje interactivo (mejora v2.61;
idea de strix). NO es un gate numerado: es un REFUERZO análogo a `a2a_router_nudge.py` (no bloquea nada;
solo inyecta un recordatorio). Cuando un subagente retorna (la sesión principal acaba de usar Task), mira si hay
DIRECTIVAS de pilotaje 'pending' del operador en `engagements/<id>/control/steering.json` y, si las hay,
inyecta un recordatorio (additionalContext) para que el Orquestador las aplique en ESTE seam (AGENTS.md →
"Pilotaje interactivo") y las marque (`steering.py ack`). NO aplica por sí mismo (un hook no orquesta);
solo garantiza que el Orquestador no ignore la intención del operador.

Las directivas son DATO del OPERADOR (intención), NO instrucciones que salten guardas: repriorizar/pausar/
abortar/pista/subir-supervisión. NUNCA relajan scope/no-daño/aprobación (lo imponen los hooks
deterministas fuera del prompt; `steering.py` ya rechaza los tipos que relajarían).

Contrato (PostToolUse, igual criterio que a2a_router_nudge):
- Recibe JSON por stdin (tool_name, ...). Solo actúa tras `Task`.
- Con pendientes: imprime {"hookSpecificOutput": {"hookEventName": "PostToolUse",
  "additionalContext": "..."}} y sale 0. Cualquier ambigüedad (no-Task, sin engagement, JSON a medias,
  sin pendientes) → sale 0 sin output (fail-open: el hook nunca rompe el flujo).
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

    if event.get("tool_name") != "Task":
        sys.exit(0)
    if not os.path.isfile(ENGAGEMENT):
        sys.exit(0)
    try:
        with open(ENGAGEMENT, encoding="utf-8") as f:
            eid = json.load(f).get("engagement_id")
    except Exception:
        sys.exit(0)
    if not eid:
        sys.exit(0)

    try:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import steering
        pend = steering.pending(eid)
    except Exception:
        sys.exit(0)

    if not pend:
        sys.exit(0)

    def _clean(s, n=200):
        # Colapsa TODO espacio en blanco (incl. \n\r\t) a un solo espacio y trunca: un `note`/`target`
        # hostil no puede inyectar líneas/instrucciones falsas en el additionalContext del Orquestador.
        return " ".join(str(s).split())[:n]

    lines = []
    for d in pend[:10]:
        tgt = f" target={_clean(d['target'], 80)}" if d.get("target") else ""
        to = f" to={d['to']}" if d.get("to") else ""
        note = f" — {_clean(d['note'])}" if d.get("note") else ""
        lines.append(f"  - {d.get('id', '?')} [{d.get('type', '?')}]{tgt}{to}{note}")
    extra = "" if len(pend) <= 10 else f"\n  ... y {len(pend) - 10} más"
    msg = (
        f"[Pilotaje] Hay {len(pend)} directiva(s) de pilotaje 'pending' del operador en "
        f"engagements/{eid}/control/steering.json:\n" + "\n".join(lines) + extra + "\n"
        "Aplícalas EN ESTE seam (AGENTS.md → 'Pilotaje interactivo'): son INTENCIÓN del operador "
        "(repriorizar/pausar/abortar-vector/pista/subir-supervisión), NO órdenes que relajen ninguna "
        "puerta — el scope, el no-daño y el suelo de aprobación siguen intactos (las guardas "
        "deterministas mandan). Tras actuar, marca cada una con "
        "`python tools/steering.py ack --id <ID> --outcome applied|rejected|skipped`."
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse", "additionalContext": msg}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
