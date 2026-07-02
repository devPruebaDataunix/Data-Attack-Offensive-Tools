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

import ipaddress
import re
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


# ── arranque de lab: objetivo(s) → scope.json (IP→autogestión) ───────────────────
# El OPERADOR define el alcance desde la TUI (proceso Python que escribe con atomic_write, NO por la
# tool Write del agente — el deny de settings.json es para el AGENTE, no para el operador; = el
# human-in-the-loop de la CONSTITUTION). NO relaja NINGUNA puerta: escribe valores VÁLIDOS y los
# guards deterministas (scope_guard/budget_guard/…) siguen decidiendo en runtime. no_dos/no_social/
# no_exfil se FUERZAN a True (no-daño nunca se relaja). Espejo de scope_guard: escribe in_scope.ips/
# cidrs/domains exactamente como el guard los lee.
_LAB_DOMAIN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$", re.I)
_LAB_EID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def classify_targets(raw: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """Clasifica una lista de objetivos separada por comas (o ';') en (ips, cidrs, domains, invalidos).
    Un token con '/' y red válida -> cidr; IP válida -> ip; dominio con TLD -> domain; si no -> invalido.
    Conserva el orden y quita duplicados."""
    ips: list[str] = []
    cidrs: list[str] = []
    domains: list[str] = []
    bad: list[str] = []
    for tok in (raw or "").replace(";", ",").split(","):
        t = tok.strip()
        if not t:
            continue
        if "/" in t:
            try:
                net = ipaddress.ip_network(t, strict=False)
            except ValueError:
                bad.append(t)
                continue
            # Rechaza la ruta por defecto (0.0.0.0/0, ::/0) y CIDRs demasiado amplios: un /0../8 mal
            # tecleado abriría scope_guard a rangos enormes por error (Regla 0 innegociable de la
            # CONSTITUTION). Umbral: /16 IPv4 (permite un /24 de lab), /64 IPv6.
            min_prefix = 16 if net.version == 4 else 64
            if net.prefixlen < min_prefix or int(net.network_address) == 0:
                bad.append(t)
                continue
            if t not in cidrs:
                cidrs.append(t)
            continue
        try:
            ipaddress.ip_address(t)
            if t not in ips:
                ips.append(t)
            continue
        except ValueError:
            pass
        if _LAB_DOMAIN.match(t):
            t = t.lower()
            if t not in domains:
                domains.append(t)
        else:
            bad.append(t)
    return ips, cidrs, domains, bad


def build_lab_scope(raw_targets: str, engagement_id: str = "", approval_mode: str = "auto",
                    base: Optional[dict] = None) -> "tuple[bool, object]":
    """Construye (SIN escribir) un scope.json VÁLIDO para un lab desde objetivos IP/CIDR/dominio.
    Devuelve (True, scope_dict) o (False, mensaje de error). Preserva las constraints NO peligrosas de
    `base` (p.ej. max_actions), fija in_scope + approval_mode, y FUERZA no_dos/no_social/no_exfil=True."""
    if approval_mode not in APPROVAL_MODES:
        return False, f"Modo de supervisión inválido: {approval_mode!r} (full/critical/auto)."
    ips, cidrs, domains, bad = classify_targets(raw_targets)
    if bad:
        return False, f"Objetivos inválidos (no son IP/CIDR/dominio): {', '.join(bad[:5])}."
    if not (ips or cidrs or domains):
        return False, "Indica al menos un objetivo (IP, CIDR o dominio)."
    first = (ips or cidrs or domains)[0].replace("/", "_")
    eid = (engagement_id or "").strip() or f"LAB-{first}"
    if not _LAB_EID.match(eid):
        return False, f"engagement_id inválido: {eid!r} (letras/números/.-_ , máx 64)."
    base = base if isinstance(base, dict) else {}
    base_c = base.get("constraints") or {}
    # Higiene de datos: un lab NO hereda `client`/`out_of_scope`/`authorization` de un engagement anterior
    # (podrían ser de un cliente real). Solo se preservan los CAPS operativos NO peligrosos (max_actions/
    # max_a2a_hops). no_dos/no_social/no_exfil se FUERZAN a True (no-daño nunca se relaja desde el panel).
    def _pos_int(v, dflt):
        return v if isinstance(v, int) and v > 0 else dflt
    constraints = {
        "no_dos": True,
        "no_social_engineering": True,
        "no_data_exfiltration_real": True,
        "max_actions": _pos_int(base_c.get("max_actions"), S.DEFAULT_MAX_ACTIONS),
        "max_a2a_hops": _pos_int(base_c.get("max_a2a_hops"), S.DEFAULT_MAX_A2A_HOPS),
        "approval_mode": approval_mode,
    }
    today = _now_iso()[:10]
    scope = {
        "engagement_id": eid,
        "client": eid,
        "authorization": {"type": "lab", "reference": eid, "valid_from": today, "valid_until": today},
        "in_scope": {"domains": domains, "ips": ips, "cidrs": cidrs, "urls": []},
        "out_of_scope": {"domains": [], "ips": [], "notes": ""},
        "constraints": constraints,
    }
    return True, scope


def _audit_operator(repo: Path, action: str, target: str) -> None:
    """Registra una acción del OPERADOR en engagement.evidence[] (trazabilidad inmutable). Best-effort:
    si no hay engagement.json (lab sin arrancar) o quedaría inválido, no bloquea la acción principal."""
    path = _engagement_path(repo)
    data = S.read_json(path)
    if not isinstance(data, dict):
        return
    ev = data.get("evidence")
    if ev is None:
        ev = data["evidence"] = []
    if not isinstance(ev, list):
        return
    ev.append({"ts": _now_iso(), "agent": "operator", "action": action[:300], "target": target[:200]})
    if not bb.validate_engagement(data):
        bb.atomic_write_json(str(path), data)


def set_lab_scope(repo: Path, raw_targets: str, engagement_id: str = "",
                  approval_mode: str = "auto") -> tuple[bool, str]:
    """Escribe contracts/scope.json para un lab de forma ATÓMICA, con backup .bak (gitignored) del scope
    anterior y auditoría en engagement.evidence[]. No relaja ninguna puerta (ver build_lab_scope)."""
    ok, res = build_lab_scope(raw_targets, engagement_id, approval_mode, base=S.load_scope(repo))
    if not ok:
        return False, str(res)
    scope = res  # dict válido
    scope_path = Path(repo) / "contracts" / "scope.json"
    if scope_path.exists():
        try:   # backup best-effort del scope anterior (gitignored): permite revertir
            (scope_path.parent / "scope.json.bak").write_text(
                scope_path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass
    bb.atomic_write_json(str(scope_path), scope)
    ins = scope["in_scope"]
    tgt = ", ".join(ins["ips"] + ins["cidrs"] + ins["domains"])
    _audit_operator(repo, f"set_lab_scope approval_mode={approval_mode} engagement={scope['engagement_id']}", tgt)
    n = len(ins["ips"]) + len(ins["cidrs"]) + len(ins["domains"])
    return True, (f"scope.json escrito: {n} objetivo(s) [{tgt}], supervisión={approval_mode}, "
                  f"engagement={scope['engagement_id']}. Backup en scope.json.bak.")


def compose_lab_run(targets_summary: str) -> str:
    """Orden autónoma para completar un lab. Se lanza por run_order (todas las puertas siguen activas)."""
    return (
        f"Completa el lab objetivo ({targets_summary}) de principio a fin siguiendo AGENTS.md: "
        "recon → triaje → explotación → post-explotación → informe. Estás autorizado por "
        "contracts/scope.json. Opera de forma autónoma respetando el alcance, el presupuesto y las "
        "puertas deterministas; deja findings y evidencia en el blackboard."
    )
