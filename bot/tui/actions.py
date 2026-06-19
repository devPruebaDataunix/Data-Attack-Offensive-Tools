"""
actions.py — Acciones de control de la TUI (SIN dependencia de Textual).

Lógica de los planos de ACCIÓN (escritura) separada de la presentación para poder testearla
sin terminal. Cada función:
  - valida la entrada,
  - escribe de forma ATÓMICA reutilizando tools/blackboard.py (no reimplementa nada),
  - devuelve (ok: bool, mensaje: str) para que el panel lo muestre y audite.

PRINCIPIO: la TUI NO relaja ninguna puerta. Estas acciones son overrides del OPERADOR sobre el
blackboard (datos de cliente, gitignored) y la config local; no tocan al target por sí mismas
(eso sigue pasando por scope_guard + budget_guard + aprobación humana cuando el orquestador actúe).
La "delegación dirigida" NO invoca al agente directamente: compone una orden para el Orquestador,
que delega por el hub (se ejecuta por el camino normal con todas las puertas).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Reutiliza los helpers deterministas del blackboard (escritura atómica + validación de esquema).
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "tools") not in sys.path:
    sys.path.insert(0, str(_REPO / "tools"))
import blackboard as bb  # noqa: E402

from . import state as S  # noqa: E402

ORCH_MODELS = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5", "claude-fable-5"]
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
A2A_STATUSES = ["pending", "delivered", "done", "blocked"]
APPROVAL_MODES = ["full", "critical", "auto"]   # supervisión humana (ver CONSTITUTION §2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _engagement_path(repo: Path) -> Path:
    return Path(repo) / "contracts" / "engagement.json"


# ── override de fase ─────────────────────────────────────────────────────────────
def set_phase(repo: Path, phase: str) -> tuple[bool, str]:
    if phase not in S.PHASES:
        return False, f"Fase inválida: {phase!r} (válidas: {', '.join(S.PHASES)})."
    path = _engagement_path(repo)
    data = S.read_json(path)
    if data is None:
        return False, "No hay engagement.json (inicia un engagement antes)."
    prev = data.get("phase", "—")
    data["phase"] = phase
    data["updated_at"] = _now_iso()
    violations = bb.validate_engagement(data)
    if violations:
        return False, "El cambio dejaría el blackboard inválido: " + "; ".join(violations[:3])
    bb.atomic_write_json(str(path), data)
    return True, f"Fase: {prev} → {phase}."


# ── control manual del bus A2A ───────────────────────────────────────────────────
def set_a2a_status(repo: Path, message_id: str, status: str) -> tuple[bool, str]:
    if status not in A2A_STATUSES:
        return False, f"Status inválido: {status!r} (válidos: {', '.join(A2A_STATUSES)})."
    if not message_id:
        return False, "Falta el message_id."
    path = _engagement_path(repo)
    data = S.read_json(path)
    if data is None:
        return False, "No hay engagement.json."
    if not bb.set_message_status(data, message_id, status):
        return False, f"Mensaje {message_id} no encontrado en el bus."
    bb.atomic_write_json(str(path), data)
    return True, f"Mensaje {message_id} → {status}."


# ── selector de modelo / effort del Orquestador (persistente en bot/.env) ─────────
def set_env_var(repo: Path, key: str, value: str) -> tuple[bool, str]:
    """Fija KEY=value en bot/.env (crea/reemplaza la línea; conserva el resto). Afecta a la
    PRÓXIMA orden (el runner lee la config al instanciarse)."""
    if key == "ORCH_MODEL" and value not in ORCH_MODELS:
        return False, f"Modelo desconocido: {value!r}."
    if key == "ORCH_EFFORT" and value not in EFFORTS:
        return False, f"Effort desconocido: {value!r}."
    if key == "ORCH_APPROVAL_MODE" and value not in APPROVAL_MODES:
        return False, f"Modo de supervisión desconocido: {value!r} (full/critical/auto)."
    env = Path(repo) / "bot" / ".env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    out, found = [], False
    for ln in lines:
        if ln.strip().startswith(f"{key}=") and not ln.strip().startswith("#"):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(ln)
    if not found:
        out.append(f"{key}={value}")
    env.write_text("\n".join(out) + "\n", encoding="utf-8")
    return True, f"{key}={value} (efectivo en la próxima orden)."


# ── delegación dirigida (NO bypass: compone una orden para el Orquestador) ────────
def compose_delegation(agent: str, objetivo: str) -> str:
    return (
        f"Delega en `{agent}` esta tarea concreta: {objetivo.strip()}. "
        "Pásale los inputs del blackboard que apliquen (targets[]/findings[]), recuérdale el "
        "alcance y exige criterio de done. No te saltes el hub ni el gate de scope."
    )


def peers_of(cards: list[dict], agent: str) -> list[str]:
    for c in cards:
        if isinstance(c, dict) and c.get("name") == agent:
            return list(c.get("a2a_peers", []) or [])
    return []


# ── RAG refresh (el panel lo lanza en background) ────────────────────────────────
def rag_refresh_cmd(epss_all: bool = False) -> list[str]:
    cmd = [sys.executable or "python3", "rag/refresh.py"]
    if epss_all:
        cmd.append("--epss-all")
    return cmd
