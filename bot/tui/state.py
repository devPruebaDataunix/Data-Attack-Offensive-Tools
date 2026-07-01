"""
state.py — Lector ÚNICO del estado para la TUI (SIN dependencia de Textual).

Centraliza la lectura del blackboard (contracts/engagement.json), el scope, el catálogo de
agentes (contracts/agent-cards.json), el contador de acciones (.action_count) y los metadatos
del RAG, y ofrece funciones de RENDER PURAS (devuelven str con markup Rich o listas de filas)
que los paneles Textual pintan tal cual.

Al ser stdlib puro y no importar Textual, es 100% testeable sin terminal (ver bot/tests/).
Ningún panel debe leer ficheros por su cuenta: todos pasan por aquí (un solo sitio que parsea).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Fases del engagement (enum de contracts/engagement.schema.json), en orden. La CLAVE canónica
# se queda en inglés (es el enum del esquema y lo que se guarda en engagement.json); solo la
# ETIQUETA visible se traduce (i18n) — ver PHASES_ES / phase_es().
PHASES = ["init", "recon", "triage", "exploitation", "post-exploitation", "reporting", "closed"]

# Etiquetas en español para MOSTRAR. El valor interno nunca cambia.
PHASES_ES = {
    "init": "inicio",
    "recon": "reconocimiento",
    "triage": "triaje",
    "exploitation": "explotación",
    "post-exploitation": "post-explotación",
    "reporting": "informe",
    "closed": "cerrado",
    # Valores de fase que aparecen en agent-cards.json (Roster), fuera del timeline del engagement:
    "orchestrator": "orquestador",
    "any": "cualquiera",
}

# Status de un mensaje A2A (enum de contracts/a2a-message.schema.json) -> emoji para la tabla.
A2A_STATUS_EMOJI = {"pending": "⏳", "delivered": "📨", "done": "✅", "blocked": "⛔"}

# Etiquetas en español de los enums visibles (i18n). La clave canónica sigue en inglés (enum del esquema):
A2A_STATUS_ES = {"pending": "pendiente", "delivered": "entregado", "done": "hecho", "blocked": "bloqueado"}
A2A_ROLE_ES = {"request": "solicitud", "response": "respuesta", "handoff": "traspaso",
               "finding": "hallazgo", "status": "estado"}
APPROVAL_MODE_ES = {"full": "completa", "critical": "crítica", "auto": "automática"}

DEFAULT_MAX_ACTIONS = 1000   # igual que budget_guard.py (DEFAULT_MAX)
DEFAULT_MAX_A2A_HOPS = 50    # igual que blackboard.py (DEFAULT_MAX_A2A_HOPS)


# ── lecturas crudas ────────────────────────────────────────────────────────────
def read_json(path: Path) -> Optional[dict]:
    """Lee un JSON; devuelve None si no existe o está corrupto (nunca lanza)."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_engagement(repo: Path) -> dict:
    return read_json(Path(repo) / "contracts" / "engagement.json") or {}


def load_scope(repo: Path) -> Optional[dict]:
    return read_json(Path(repo) / "contracts" / "scope.json")


def load_cards(repo: Path) -> list[dict]:
    data = read_json(Path(repo) / "contracts" / "agent-cards.json") or {}
    cards = data.get("cards", [])
    return cards if isinstance(cards, list) else []


def load_lab_routes(repo: Path) -> dict:
    """Mapa {agente: modelo_lab_corto} del perfil NVIDIA LAB (tools/routing.nvidia-lab.json), para la
    2ª columna del Roster. LAB-ONLY: es el espejo opencode que el bot NO usa (el bot es 100% Anthropic);
    solo sirve para ver con qué modelo free de NVIDIA correría cada agente. `{}` si el fichero no existe.
    El modelo corto = último segmento de la ruta 'nvidia/<vendor>/<modelo>'."""
    data = read_json(Path(repo) / "tools" / "routing.nvidia-lab.json") or {}
    routes = data.get("routes", {})
    if not isinstance(routes, dict):
        return {}
    return {name: str(route).rsplit("/", 1)[-1] for name, route in routes.items() if route}


def action_count(repo: Path) -> tuple[int, str]:
    """(count, key) del contador de acciones Bash. (0, '') si no existe/corrupto."""
    data = read_json(Path(repo) / "contracts" / ".action_count") or {}
    try:
        return int(data.get("count", 0)), str(data.get("key", ""))
    except (TypeError, ValueError):
        return 0, ""


def max_actions(scope: Optional[dict]) -> int:
    c = ((scope or {}).get("constraints", {}) or {}).get("max_actions")
    return c if isinstance(c, int) and c > 0 else DEFAULT_MAX_ACTIONS


def max_a2a_hops(scope: Optional[dict]) -> int:
    c = ((scope or {}).get("constraints", {}) or {}).get("max_a2a_hops")
    return c if isinstance(c, int) and c > 0 else DEFAULT_MAX_A2A_HOPS


def _clip(s, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _msg_text(m: dict) -> str:
    """Primer fragmento de texto de un mensaje A2A (parts[].kind == 'text')."""
    for p in m.get("parts", []) or []:
        if isinstance(p, dict) and p.get("kind") == "text" and p.get("text"):
            return p["text"]
    return ""


# ── Bus A2A ─────────────────────────────────────────────────────────────────────
def a2a_rows(eng: dict) -> list[tuple]:
    """Filas para la tabla del bus A2A: (emoji, from, to, role, hops, preview)."""
    rows = []
    for m in eng.get("messages", []) or []:
        if not isinstance(m, dict):
            continue
        status = m.get("status", "pending")
        rows.append((
            A2A_STATUS_EMOJI.get(status, "•"),
            m.get("from_agent", "?"),
            m.get("to_agent", "?"),
            A2A_ROLE_ES.get(m.get("role", ""), m.get("role", "")),
            str(m.get("hops", 0)),
            _clip(_msg_text(m), 48),
        ))
    return rows


def a2a_summary(eng: dict, scope: Optional[dict]) -> str:
    """Resumen del bus: recuento por status + hops máx / techo."""
    msgs = [m for m in eng.get("messages", []) or [] if isinstance(m, dict)]
    counts = {k: 0 for k in A2A_STATUS_EMOJI}
    for m in msgs:
        counts[m.get("status", "pending")] = counts.get(m.get("status", "pending"), 0) + 1
    hops_max = max((int(m.get("hops", 0) or 0) for m in msgs), default=0)
    ceil = max_a2a_hops(scope)
    return (
        f"[b #00D4FF]Bus A2A[/]  ({len(msgs)} mensajes)\n"
        f"⏳ {A2A_STATUS_ES['pending']}: {counts['pending']}   "
        f"📨 {A2A_STATUS_ES['delivered']}: {counts['delivered']}\n"
        f"✅ {A2A_STATUS_ES['done']}: {counts['done']}   "
        f"⛔ {A2A_STATUS_ES['blocked']}: {counts['blocked']}\n"
        f"hops máx: {hops_max}/{ceil}"
        + ("  [#FF4444](¡cerca del techo!)[/]" if ceil and hops_max >= ceil * 0.8 else "")
    )


def message_detail(eng: dict, message_id: str) -> str:
    """Volcado legible de un mensaje A2A por message_id (para el modal de detalle)."""
    for m in eng.get("messages", []) or []:
        if isinstance(m, dict) and m.get("message_id") == message_id:
            parts = "\n".join(
                f"  · {p.get('kind', '?')}: {_clip(p.get('text') or p.get('data') or '', 300)}"
                for p in m.get("parts", []) or [] if isinstance(p, dict)
            )
            return (
                f"message_id: {m.get('message_id')}\n"
                f"{m.get('from_agent', '?')} → {m.get('to_agent', '?')}  ({m.get('role', '')})\n"
                f"status: {m.get('status', 'pending')}   hops: {m.get('hops', 0)}\n"
                f"ref_finding: {m.get('ref_finding', '—')}   ref_message: {m.get('ref_message', '—')}\n"
                f"parts:\n{parts or '  (sin partes)'}"
            )
    return f"Mensaje {message_id} no encontrado."


def pending_message_ids(eng: dict) -> list[str]:
    return [m.get("message_id") for m in eng.get("messages", []) or []
            if isinstance(m, dict) and m.get("status", "pending") == "pending" and m.get("message_id")]


# ── Roster de agentes ────────────────────────────────────────────────────────────
def _roster_sort_key(card: dict) -> tuple:
    """Orden del Roster: el orquestador PRIMERO, luego por fase del engagement, y alfabético
    dentro de cada fase (antes salían mezclados alfabéticamente)."""
    phase = card.get("phase", "")
    if phase == "orchestrator":
        rank = -1
    elif phase in PHASES:
        rank = PHASES.index(phase)
    else:
        rank = len(PHASES)   # fases fuera del catálogo, al final
    return (rank, card.get("name", ""))


def roster_rows(cards: list[dict], lab_routes: Optional[dict] = None) -> list[tuple]:
    """Filas del roster: (name, fase, modelo bot, modelo lab, #peers, descripción), ordenadas por fase
    (orquestador primero). `modelo lab` viene del perfil NVIDIA LAB (o '—' si el agente no se enruta ahí:
    el bot es 100% Anthropic; el perfil lab es un espejo opencode que el bot NO usa)."""
    lab_routes = lab_routes or {}
    rows = []
    for c in sorted((c for c in cards if isinstance(c, dict)), key=_roster_sort_key):
        model = (c.get("model") or "—").replace("claude-", "")
        rows.append((
            c.get("name", "?"),
            phase_es(c.get("phase")),   # i18n: misma etiqueta española que el resto de la UI
            model,
            lab_routes.get(c.get("name", ""), "—"),   # 2ª col: modelo del perfil lab (NVIDIA) o '—'
            str(len(c.get("a2a_peers", []) or [])),
            _clip(c.get("description", ""), 60),
        ))
    return rows


def agent_names(cards: list[dict]) -> list[str]:
    return [c.get("name", "") for c in cards if isinstance(c, dict) and c.get("name")]


# ── Presupuesto / kill-switch ────────────────────────────────────────────────────
def budget_render(count: int, cap: int, key: str) -> str:
    pct = (count / cap) if cap else 0
    filled = min(20, int(pct * 20))
    bar = "█" * filled + "░" * (20 - filled)
    color = "#3FB950" if pct < 0.8 else ("#FF6B35" if pct < 1.0 else "#FF4444")
    return (
        f"[b #00D4FF]Presupuesto de acciones (kill-switch C13)[/]\n"
        f"engagement: {key or '—'}\n"
        f"[{color}]{bar}[/] {count}/{cap}  ({pct * 100:.0f}%)\n"
        + ("[#FF4444]⚠ techo alcanzado: el orquestador se bloquea.[/]" if count > cap else
           "[#FF6B35]⚠ cerca del techo.[/]" if pct >= 0.8 else "")
    )


# ── Timeline de fase ─────────────────────────────────────────────────────────────
def phase_es(phase: str) -> str:
    """Etiqueta en español de una fase (la cadena tal cual si es desconocida, '—' si vacía/ausente)."""
    return PHASES_ES.get(phase, phase) if phase else "—"


def phase_render(phase: str) -> str:
    # El bullet va SEPARADO de la etiqueta (con un espacio) para que no se "pegue" en el render
    # (antes "○init" se leía como "oinit"). La etiqueta se muestra en español (phase_es).
    if phase not in PHASES:   # fase desconocida/ausente: nada se marca como completado
        return "  →  ".join(f"[#6E7681]○ {phase_es(p)}[/]" for p in PHASES)
    out, reached = [], True
    for p in PHASES:
        label = phase_es(p)
        if p == phase:
            out.append(f"[b #00D4FF]● {label}[/]")
            reached = False
        elif reached:
            out.append(f"[#3FB950]✓ {label}[/]")
        else:
            out.append(f"[#6E7681]○ {label}[/]")
    return "  →  ".join(out)


# ── Navegador de evidencia ───────────────────────────────────────────────────────
def evidence_rows(eng: dict) -> list[tuple]:
    """Filas para la tabla de evidencia: (ts, agent, action, target, artefacto)."""
    rows = []
    for e in eng.get("evidence", []) or []:
        if not isinstance(e, dict):
            continue
        rows.append((
            _clip(e.get("ts", ""), 19),
            e.get("agent", "—"),
            _clip(e.get("action", ""), 28),
            _clip(e.get("target", ""), 20),
            _clip(e.get("artifact_path") or e.get("output_hash") or "", 28),
        ))
    return rows


def evidence_header(engagements: list[str]) -> str:
    """Cabecera del panel de evidencia (empty-state amable si aún no hay artefactos)."""
    if not engagements:
        return ("[b #00D4FF]Evidencia[/]\n"
                "Sin artefactos todavía — aparecerán aquí cuando un engagement genere "
                "recon/exploit/loot/evidence.")
    return "[b #00D4FF]Engagements con artefactos[/]: " + ", ".join(engagements)


def engagement_dirs(repo: Path) -> list[str]:
    """IDs de engagement con carpeta de artefactos en engagements/."""
    base = Path(repo) / "engagements"
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


# ── RAG ──────────────────────────────────────────────────────────────────────────
def parse_rag_store(json_str: str) -> Optional[dict]:
    """Extrae el bloque 'store' de la salida JSON de rag/query_vulns.py. None si falla."""
    try:
        data = json.loads(json_str)
    except ValueError:
        return None
    store = data.get("store")
    return store if isinstance(store, dict) else None


def rag_render(store: Optional[dict]) -> str:
    if not store:
        return "[#FF6B35]RAG sin poblar o ilegible. Refresca con: python rag/refresh.py[/]"
    return (
        f"[b #00D4FF]RAG de vulnerabilidades[/]\n"
        f"CVEs en store: {store.get('total_cves', '—')}\n"
        f"KEV: {store.get('kev_version', '—')}  (sync {store.get('kev_last_sync', '—')})\n"
        f"EPSS sync:   {store.get('epss_last_sync', '—')}\n"
        f"CVE5 sync:   {store.get('cve5_last_sync', '—')}\n"
        f"ExploitDB:   {store.get('exploitdb_last_sync', '—')}\n"
        f"MSF sync:    {store.get('msf_last_sync', '—')}\n"
        f"Nuclei sync: {store.get('nuclei_last_sync', '—')}"
    )


# ── Estado global (cabecera) ─────────────────────────────────────────────────────
def header_line(eng: dict, count: int, cap: int, cost: Optional[float],
                approval_mode: str = "critical") -> str:
    cost_txt = f"${cost:.2f}" if isinstance(cost, (int, float)) else "—"
    mode_color = {"full": "#3FB950", "critical": "#FF6B35", "auto": "#FF4444"}.get(approval_mode, "#FF6B35")
    return (
        f"engagement: [b]{eng.get('engagement_id', '—')}[/]   "
        f"fase: [b]{phase_es(eng.get('phase')) if eng.get('phase') else '—'}[/]   "
        f"acciones: {count}/{cap}   "
        f"coste: {cost_txt}   "
        f"supervisión: [{mode_color}]{APPROVAL_MODE_ES.get(approval_mode, approval_mode)}[/]"
    )


# ── Panel principal (dashboard) ──────────────────────────────────────────────────
def dashboard_status(snap: "Snapshot", grp: dict, sdk_ok: bool) -> str:
    """Bloque de estado del panel principal. Empty-state amable si aún no hay engagement."""
    motor = "Agent SDK" if sdk_ok else "remoto (Kali)"
    eid = snap.eng.get("engagement_id")
    if not eid:
        return (
            "[b #00D4FF]Sin engagement activo[/]\n\n"
            "Todavía no hay nada en marcha.\n"
            "Lanza una orden al Orquestador en la línea de abajo\n"
            "(p. ej. [b]haz recon de ejemplo.com[/]).\n\n"
            f"motor: {motor}"
        )
    ins = (snap.scope or {}).get("in_scope", {})
    doms = ", ".join(ins.get("domains", []) or ["—"])
    ips = ", ".join((ins.get("ips", []) or []) + (ins.get("cidrs", []) or []) or ["—"])
    fase = snap.eng.get("phase")
    lines = [
        "[b #00D4FF]Engagement[/]",
        f"id:   {eid}",
        f"fase: {phase_es(fase) if fase else '—'}",
        "",
        "[b #00D4FF]Scope[/]",
        f"dom: {doms}",
        f"ip:  {ips}",
        "",
        "[b #00D4FF]Hallazgos[/]",
        f"[#FF4444]reales:[/]  {len(grp['real'])}",
        f"[#FF6B35]vigilar:[/] {len(grp['watch'])}",
        f"ruido:   {len(grp['noise'])}",
        "",
        f"motor: {motor}",
    ]
    return "\n".join(lines)


# ── Snapshot (una sola lectura por refresco, compartida por todos los paneles) ───
@dataclass
class Snapshot:
    eng: dict = field(default_factory=dict)
    scope: Optional[dict] = None
    cards: list = field(default_factory=list)
    count: int = 0
    key: str = ""
    cap: int = DEFAULT_MAX_ACTIONS
    cost: Optional[float] = None
    approval_mode: str = "critical"
    lab_routes: dict = field(default_factory=dict)


def resolve_approval_mode(scope: Optional[dict], override: Optional[str] = None) -> str:
    """Modo de supervisión: override (p.ej. bot/.env) > scope.constraints.approval_mode > 'critical'.
    Valor inválido => 'critical'."""
    m = override or ((scope or {}).get("constraints", {}) or {}).get("approval_mode")
    m = str(m or "critical").strip().lower()
    return m if m in ("full", "critical", "auto") else "critical"


def build_snapshot(repo, cost: Optional[float] = None, approval_mode: Optional[str] = None) -> Snapshot:
    """Lee TODO el estado de una vez (el 'lector único'): blackboard, scope, cards y contador.
    Los paneles consumen este Snapshot; ninguno vuelve a tocar disco en el refresco."""
    eng = load_engagement(repo)
    scope = load_scope(repo)
    count, key = action_count(repo)
    return Snapshot(
        eng=eng,
        scope=scope,
        cards=load_cards(repo),
        count=count,
        key=key,
        cap=max_actions(scope),
        cost=cost,
        approval_mode=resolve_approval_mode(scope, approval_mode),
        lab_routes=load_lab_routes(repo),
    )
