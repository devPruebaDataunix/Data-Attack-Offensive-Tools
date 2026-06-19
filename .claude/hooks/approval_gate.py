#!/usr/bin/env python3
"""
approval_gate.py — Hook PreToolUse: aplica el MODO DE SUPERVISIÓN humana (full|critical|auto).

NO es una puerta de seguridad dura. Las puertas duras son scope_guard.py (alcance, §1) y
budget_guard.py (kill-switch, §C13): deniegan por su cuenta y NUNCA se relajan — en Claude Code un
`deny` de cualquier hook GANA sobre el `allow` de este. Este hook SOLO decide si una acción Bash de
RIESGO necesita aprobación HUMANA por acción, según el modo elegido por el operador (engagement
AUTORIZADO):

  full      -> pide aprobación para TODO lo de riesgo (ask + crítico).      [máxima supervisión]
  critical  -> auto-aprueba salvo lo crítico (C2/implantes/msfvenom).        [default]
  auto      -> auto-aprueba todo (confía en scope_guard + budget_guard).

Modo = env ORCH_APPROVAL_MODE > contracts/scope.json constraints.approval_mode > 'critical'.
La clasificación por tier la da bot/intel/risk.py (única fuente de verdad).

Protocolo Claude Code (PreToolUse): lee JSON por stdin; imprime `permissionDecision`:
  - "allow" -> auto-aprueba (se salta el prompt; scope/budget aún pueden denegar aparte).
  - "ask"   -> fuerza aprobación humana.
  - (sin salida / exit 0) -> deja el flujo normal de permisos.
FAIL-SAFE: ante CUALQUIER duda o error, exige aprobación ("ask"), nunca menos supervisión.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCOPE = os.path.join(ROOT, "contracts", "scope.json")


def resolve_mode():
    m = os.environ.get("ORCH_APPROVAL_MODE")
    if not m:
        try:
            with open(SCOPE, encoding="utf-8") as f:
                m = json.load(f).get("constraints", {}).get("approval_mode")
        except Exception:
            m = None
    m = str(m or "critical").strip().lower()
    return m if m in ("full", "critical", "auto") else "critical"


def policy_of(cmd):
    """(tier, policy) del comando vía risk.py. Fail-safe: si no se puede clasificar, ('unknown','ask')
    para exigir aprobación (más supervisión)."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "bot"))
        from intel import risk
        return risk.classify_command(cmd)
    except Exception:
        return ("unknown", "ask")


def _emit(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)  # sin payload utilizable: no decidimos (flujo normal)
    if event.get("tool_name") != "Bash":
        sys.exit(0)

    cmd = (event.get("tool_input") or {}).get("command", "")
    mode = resolve_mode()
    _, policy = policy_of(cmd)

    if policy == "auto":                       # recon pasivo / benigno: sin fricción en todo modo
        _emit("allow", "acción benigna (recon pasivo / solo lectura).")
    if mode == "auto":
        _emit("allow", "supervisión 'auto' (operador): sin aprobación por acción; "
                       "scope_guard y budget_guard siguen activos.")
    if mode == "critical" and policy != "dual":
        _emit("allow", "supervisión 'critical': acción no crítica auto-aprobada; "
                       "scope_guard y budget_guard siguen activos.")
    # full (cualquier riesgo) o critical+crítico (C2/implantes): exige aprobación humana.
    _emit("ask", f"requiere aprobación humana (supervisión '{mode}', tier de riesgo).")


if __name__ == "__main__":
    main()
