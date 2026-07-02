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
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import theme as T

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

# Segundos SIN señal del SDK (última narración/tool) tras los que una orden se considera COLGADA y
# la TUI la auto-recupera (libera el lock). Generoso a propósito: un escaneo largo de un solo comando
# puede no emitir señales durante minutos. La recuperación MANUAL (Ctrl+K) es instantánea y primaria;
# esto es solo la red de seguridad para un cuelgue silencioso del SDK (el caso real de tokenaso).
ORDER_STALL_TIMEOUT = 300.0


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


def human_ts(ts: str) -> str:
    """ISO 8601 -> 'YYYY-MM-DD HH:MM' legible (sin microsegundos ni sufijos T/Z). Los timestamps del
    blackboard salían crudos con microsegundos (ilegibles en las tablas). Si no parsea, devuelve el
    texto recortado (escapado por el llamador). '—' si está vacío."""
    s = str(ts or "").strip()
    if not s:
        return "—"
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return _clip(s, 16)


def _esc(s) -> str:
    """Escapa el markup Rich de un texto LIBRE del blackboard (dominios, engagement_id, previews del
    bus A2A, key del presupuesto…): un '[' abriría una etiqueta Rich y CORROMPERÍA el render — y ese
    dato puede venir del target. Convierte '[' en '\\[' (convención de Rich para un corchete literal).
    stdlib: NO importa `rich`, porque state.py se testea sin Textual/Rich en el Windows de desarrollo."""
    return str("" if s is None else s).replace("[", "\\[")


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
            _esc(m.get("from_agent", "?")),
            _esc(m.get("to_agent", "?")),
            A2A_ROLE_ES.get(m.get("role", ""), _esc(m.get("role", ""))),
            str(m.get("hops", 0)),
            _esc(_clip(_msg_text(m), 48)),
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
    # Chips de estado con color (el significado no depende solo del color: cada uno lleva su emoji).
    def _chip(color, emoji, label, n):
        return f"[{color}]{emoji} {label}: {n}[/]"
    return (
        f"{T.panel_title('Bus A2A')}  ({len(msgs)} mensajes)\n"
        f"{_chip(T.WARN, '⏳', A2A_STATUS_ES['pending'], counts['pending'])}   "
        f"{_chip(T.INFO, '📨', A2A_STATUS_ES['delivered'], counts['delivered'])}\n"
        f"{_chip(T.OK, '✅', A2A_STATUS_ES['done'], counts['done'])}   "
        f"{_chip(T.DANGER, '⛔', A2A_STATUS_ES['blocked'], counts['blocked'])}\n"
        f"hops máx: {hops_max}/{ceil}"
        + (f"  [{T.DANGER}](¡cerca del techo!)[/]" if ceil and hops_max >= ceil * 0.8 else "")
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
# El roster plano (roster_rows/_roster_sort_key) fue REEMPLAZADO por el panel Agentes master-detail
# por zonas (zone_of / roster_by_zone / agent_detail, más abajo). Aquí solo queda el catálogo de
# nombres que usa la validación de la delegación dirigida.
def agent_names(cards: list[dict]) -> list[str]:
    return [c.get("name", "") for c in cards if isinstance(c, dict) and c.get("name")]


# ── Zonas de agentes E1/E2/E3 (panel Agentes master-detail) ──────────────────────
# MISMO modelo que ARCHITECTURE_MAP (tools/gen_arch_diagram.py): E1 Recon (sin datos de cliente, riesgo
# bajo) · E2 Explotación (acceso al target, riesgo alto) · E3 Cierre (datos de cliente, riesgo medio).
# El Orquestador va aparte. zone_of es PURA/testeable y reproduce E1=recon / E2=triage+exploitation+
# post-exploitation / E3=reporting (cuadra con los conteos E1=3/E2=16/E3=2 del mapa).
_ZONE_META = {
    "orch": ("🧭", "Orquestador"),
    "E1": ("🟦", "E1 · Reconocimiento"),
    "E2": ("🟥", "E2 · Explotación"),
    "E3": ("🟩", "E3 · Cierre"),
    "otro": ("·", "Otros"),
}
ZONE_ORDER = ["orch", "E1", "E2", "E3", "otro"]


def zone_of(phase: str) -> str:
    """Zona de un agente por su fase, idéntico al mapeo de ARCHITECTURE_MAP: E1=recon ·
    E2=triage/exploitation/post-exploitation · E3=reporting · orchestrator='orch' · resto='otro'."""
    if phase == "orchestrator":
        return "orch"
    if phase == "recon":
        return "E1"
    if phase in ("triage", "exploitation", "post-exploitation"):
        return "E2"
    if phase == "reporting":
        return "E3"
    return "otro"


def zone_label(zone: str) -> str:
    icon, label = _ZONE_META.get(zone, _ZONE_META["otro"])
    return f"{icon} {label}"


def roster_by_zone(cards: list[dict], lab_routes: Optional[dict] = None) -> list[tuple]:
    """Agrupa las cards por zona para el panel Agentes master-detail. Devuelve
    [(zone, [(name, faseES, modelo_bot, modelo_lab, npeers), …]), …] en ZONE_ORDER, alfabético dentro
    de cada zona; OMITE zonas vacías. Filas COMPACTAS (sin descripción: esa va en la ficha de detalle)."""
    lab_routes = lab_routes or {}
    buckets: dict = {z: [] for z in ZONE_ORDER}
    for c in cards:
        if not isinstance(c, dict):
            continue
        z = zone_of(c.get("phase", ""))
        model = (c.get("model") or "—").replace("claude-", "")
        buckets[z].append((
            c.get("name", "?"),
            phase_es(c.get("phase")),
            model,
            lab_routes.get(c.get("name", ""), "—"),
            str(len(c.get("a2a_peers", []) or [])),
        ))
    out = []
    for z in ZONE_ORDER:
        rows = sorted(buckets[z], key=lambda r: r[0])
        if rows:
            out.append((z, rows))
    return out


def find_card(cards: list[dict], name: Optional[str]) -> Optional[dict]:
    if not name:
        return None
    for c in cards:
        if isinstance(c, dict) and c.get("name") == name:
            return c
    return None


def agent_detail(card: Optional[dict], lab_routes: Optional[dict] = None) -> str:
    """Ficha COMPLETA del agente resaltado (descripción SIN truncar + zona + modelos + capacidades +
    peers + tools). Empty-state amable si no hay ninguno resaltado. Resuelve el truncado del roster."""
    if not isinstance(card, dict):
        return f"[{T.MUTED}]Resalta un agente en una tabla para ver su ficha completa.[/]"
    lab_routes = lab_routes or {}
    name = card.get("name", "?")
    z = zone_of(card.get("phase", ""))
    model = (card.get("model") or "—").replace("claude-", "")
    lab = lab_routes.get(name, "—")
    peers = ", ".join(card.get("a2a_peers", []) or []) or "—"
    caps = ", ".join(card.get("capabilities", []) or []) or "—"
    tools = ", ".join(card.get("tools", []) or []) or "—"
    return "\n".join([
        T.panel_title(_esc(name)),
        f"zona: {zone_label(z)}   fase: {phase_es(card.get('phase'))}",
        f"modelo (bot): {_esc(model)}   ·   modelo lab: {_esc(lab)}",
        "",
        f"[b]Qué hace:[/] {_esc(card.get('description', '—'))}",
        "",
        f"[b]Capacidades A2A:[/] {_esc(caps)}",
        f"[b]Peers A2A:[/] {_esc(peers)}",
        f"[b]Tools:[/] {_esc(tools)}",
    ])


# ── Presupuesto / kill-switch ────────────────────────────────────────────────────
def budget_render(count: int, cap: int, key: str) -> str:
    pct = (count / cap) if cap else 0
    filled = min(20, int(pct * 20))
    bar = "█" * filled + "░" * (20 - filled)
    color = T.OK if pct < 0.8 else (T.WARN if pct < 1.0 else T.DANGER)
    return (
        f"{T.panel_title('Presupuesto de acciones (kill-switch C13)')}\n"
        f"engagement: {_esc(key or '—')}\n"
        f"[{color}]{bar}[/] {count}/{cap}  ({pct * 100:.0f}%)\n"
        + (f"[{T.DANGER}]⚠ techo alcanzado: el orquestador se bloquea.[/]" if count > cap else
           f"[{T.WARN}]⚠ cerca del techo.[/]" if pct >= 0.8 else "")
    )


# ── Orden en curso (observabilidad + recuperación del lock) ──────────────────────
# PURO: recibe 'now'/'started'/'last_beat' en reloj MONOTÓNICO (los pasa app.py); así se testea sin
# Textual ni tiempo real. El lock de orden vive en app.py; aquí solo se RENDERIZA y se decide staleness.
def fmt_duration(seconds: float) -> str:
    """Duración humana mm:ss (o h:mm:ss si ≥1h). Negativo/borde -> 00:00."""
    s = int(max(0, seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def order_stale(started: Optional[float], last_beat: Optional[float], now: float,
                timeout: float = ORDER_STALL_TIMEOUT) -> bool:
    """True si la orden lleva más de `timeout` s SIN señal. Mide desde la última señal del SDK
    (`last_beat`: última narración/tool) o, si aún no hubo ninguna, desde el arranque (`started`).
    Así una orden que sigue narrando NO se considera colgada aunque lleve mucho rato."""
    if started is None:
        return False
    ref = last_beat if (isinstance(last_beat, (int, float)) and last_beat > 0) else started
    return (now - ref) > timeout


def order_status_line(task: Optional[str], started: Optional[float], now: float,
                      turns: Optional[int] = None, cost: Optional[float] = None,
                      last_beat: Optional[float] = None,
                      timeout: float = ORDER_STALL_TIMEOUT) -> str:
    """Línea de estado de la orden en curso para la barra bajo el log. Empty-state amable si no hay
    orden. Marca staleness (sin señal) para avisar de un posible cuelgue. Escapa el texto libre."""
    if not task or started is None:
        return f"[{T.MUTED}]· sin orden en curso[/]"
    bits = [f"[b {T.BRAND}]▶ orden en curso[/]",
            f"[{T.INFO}]{_esc(_clip(task, 60))}[/]",
            f"⏱ {fmt_duration(now - started)}"]
    if isinstance(turns, int) and turns > 0:
        bits.append(f"{turns} turnos")
    if isinstance(cost, (int, float)) and cost:
        bits.append(f"${cost:.2f}")
    if order_stale(started, last_beat, now, timeout):
        ref = last_beat if (isinstance(last_beat, (int, float)) and last_beat > 0) else started
        bits.append(f"[{T.DANGER}]⚠ sin señal {fmt_duration(now - ref)} — Ctrl+K para liberar[/]")
    return "  ·  ".join(bits)


class CmdHistory:
    """Historial de órdenes con navegación ↑/↓ estilo shell (LÓGICA PURA, testeable sin Textual).
    El widget HistoryInput de app.py delega aquí toda la lógica de índice/dedup; él solo pinta el valor.
    `_idx` apunta a la posición actual; en `len(items)` = línea en blanco nueva (past-the-end)."""

    def __init__(self) -> None:
        self._items: list[str] = []
        self._idx = 0

    def remember(self, value: str) -> None:
        """Registra una orden enviada. Ignora vacíos y el duplicado consecutivo (como una shell).
        Deja el cursor del historial 'past-the-end' (la próxima ↑ recupera la última)."""
        v = (value or "").strip()
        if v and (not self._items or self._items[-1] != v):
            self._items.append(v)
        self._idx = len(self._items)

    def prev(self) -> Optional[str]:
        """↑ — orden anterior. None si el historial está vacío (no consumir la tecla)."""
        if not self._items:
            return None
        self._idx = max(0, self._idx - 1)
        return self._items[self._idx]

    def next(self) -> Optional[str]:
        """↓ — orden siguiente; '' (línea en blanco) al pasar del final. None si está vacío."""
        if not self._items:
            return None
        self._idx = min(len(self._items), self._idx + 1)
        return "" if self._idx >= len(self._items) else self._items[self._idx]

    def items(self) -> list[str]:
        return list(self._items)


# ── Timeline de fase ─────────────────────────────────────────────────────────────
def phase_es(phase: str) -> str:
    """Etiqueta en español de una fase (la cadena tal cual si es desconocida, '—' si vacía/ausente)."""
    return PHASES_ES.get(phase, _esc(phase)) if phase else "—"


def phase_render(phase: str) -> str:
    # El bullet va SEPARADO de la etiqueta (con un espacio) para que no se "pegue" en el render
    # (antes "○init" se leía como "oinit"). La etiqueta se muestra en español (phase_es).
    if phase not in PHASES:   # fase desconocida/ausente: nada se marca como completado
        return "  →  ".join(f"[{T.MUTED}]○ {phase_es(p)}[/]" for p in PHASES)
    out, reached = [], True
    for p in PHASES:
        label = phase_es(p)
        if p == phase:
            out.append(f"[b {T.BRAND}]● {label}[/]")   # fase activa: rojo de marca ("estás aquí")
            reached = False
        elif reached:
            out.append(f"[{T.OK}]✓ {label}[/]")
        else:
            out.append(f"[{T.MUTED}]○ {label}[/]")
    return "  →  ".join(out)


# ── Navegador de evidencia ───────────────────────────────────────────────────────
def evidence_rows(eng: dict) -> list[tuple]:
    """Filas para la tabla de evidencia: (ts, agent, action, target, artefacto)."""
    rows = []
    for e in eng.get("evidence", []) or []:
        if not isinstance(e, dict):
            continue
        rows.append((
            human_ts(e.get("ts", "")),
            _esc(e.get("agent", "—")),
            _esc(_clip(e.get("action", ""), 28)),
            _esc(_clip(e.get("target", ""), 20)),
            _esc(_clip(e.get("artifact_path") or e.get("output_hash") or "", 28)),
        ))
    return rows


def evidence_header(engagements: list[str]) -> str:
    """Cabecera del panel de evidencia (empty-state amable si aún no hay artefactos)."""
    if not engagements:
        return (T.panel_title("Evidencia") + "\n"
                "Sin artefactos todavía — aparecerán aquí cuando un engagement genere "
                "recon/exploit/loot/evidence.")
    return (T.panel_title("Engagements con artefactos") + ": "
            + ", ".join(_esc(e) for e in engagements)
            + f"\n[{T.MUTED}]artefactos en engagements/<id>/ (recon · exploit · loot · evidence · report)[/]")


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
        return f"[{T.WARN}]RAG sin poblar o ilegible. Refresca con: python rag/refresh.py[/]"
    return (
        f"{T.panel_title('RAG de vulnerabilidades')}\n"
        f"CVEs en store: {store.get('total_cves', '—')}\n"
        f"KEV: {store.get('kev_version', '—')}  (sync {store.get('kev_last_sync', '—')})\n"
        f"EPSS sync:   {store.get('epss_last_sync', '—')}\n"
        f"CVE5 sync:   {store.get('cve5_last_sync', '—')}\n"
        f"ExploitDB:   {store.get('exploitdb_last_sync', '—')}\n"
        f"MSF sync:    {store.get('msf_last_sync', '—')}\n"
        f"Nuclei sync: {store.get('nuclei_last_sync', '—')}"
    )


# ── RAG de conocimiento (Capa 1 kb.db + Capa 2 kb_vec.db) ────────────────────────
def parse_kb_stats(json_str: str) -> Optional[dict]:
    """Extrae el reporte de `rag/knowledge/query_kb.py --stats --json` (RAG de CONOCIMIENTO: Capa 1
    `kb.db` estructurada + Capa 2 `kb_vec.db` semántica). None si el JSON falla o no es el reporte."""
    try:
        data = json.loads(json_str)
    except ValueError:
        return None
    return data if isinstance(data, dict) and "capa1_kb" in data else None


def _fmt_counts(d, top: int = 6) -> str:
    """'clave n · clave n …' ordenado por conteo desc (top N); '—' si vacío. Escapa las claves
    (nombres de fuente/plataforma) por defensa, aunque vengan de nuestras propias DB."""
    if not isinstance(d, dict) or not d:
        return "—"
    items = sorted(d.items(), key=lambda kv: kv[1] if isinstance(kv[1], int) else 0, reverse=True)
    return " · ".join(f"{_esc(k)} {v}" for k, v in items[:top]) + (" · …" if len(items) > top else "")


def kb_render(rep: Optional[dict]) -> str:
    """Render del RAG de CONOCIMIENTO (Capa 1 + Capa 2). Empty-state amable si aún no está poblado
    (típico en el Windows de desarrollo; se puebla en Kali con refresh_kb.py)."""
    c1 = (rep or {}).get("capa1_kb") or {}
    c2 = (rep or {}).get("capa2_kb_vec") or {}
    total1 = c1.get("total", 0)
    if not rep or not total1:
        return (f"[{T.WARN}]RAG de conocimiento sin poblar.[/]\n"
                "Puébla con: python rag/knowledge/refresh_kb.py  (añade --semantic para la Capa 2)")
    out = [
        T.panel_title("RAG de conocimiento"),
        f"Capa 1 (kb.db): {total1} técnicas",
        f"  fuentes:    {_fmt_counts(c1.get('by_source'))}",
        f"  plataformas:{_fmt_counts(c1.get('by_platform'))}",
        f"  categorías: {_fmt_counts(c1.get('by_category'))}",
    ]
    if "total" in c2:
        line = f"Capa 2 (kb_vec.db): {c2['total']} trozos"
        if c2.get("embed_model"):
            line += f"  (modelo {_esc(c2['embed_model'])})"
        out.append(line)
        out.append(f"  fuentes:    {_fmt_counts(c2.get('by_source'))}")
        if isinstance(c2["total"], int) and c2["total"] == 0:
            out.append(f"  [{T.WARN}]⚠ vacía; puébla con: refresh_kb.py --semantic[/]")
        elif isinstance(c2["total"], int) and c2["total"] < 2000:
            out.append(f"  [{T.WARN}]⚠ subset de prueba; repobla entero: refresh_kb.py --semantic[/]")
    else:
        out.append(f"Capa 2 (kb_vec.db): [{T.MUTED}]{_esc(c2.get('status') or c2.get('error') or 'no poblada')}[/]")
    return "\n".join(out)


# ── Estado global (cabecera) ─────────────────────────────────────────────────────
def header_line(eng: dict, count: int, cap: int, cost: Optional[float],
                approval_mode: str = "critical") -> str:
    cost_txt = f"${cost:.2f}" if isinstance(cost, (int, float)) else "—"
    mode_color = {"full": T.OK, "critical": T.WARN, "auto": T.DANGER}.get(approval_mode, T.WARN)
    return (
        f"engagement: [b]{_esc(eng.get('engagement_id', '—'))}[/]   "
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
            f"{T.panel_title('Sin engagement activo')}\n\n"
            "Todavía no hay nada en marcha.\n"
            "Lanza una orden al Orquestador en la línea de abajo\n"
            "(p. ej. [b]haz recon de ejemplo.com[/]).\n\n"
            f"motor: {motor}"
        )
    ins = (snap.scope or {}).get("in_scope", {})
    doms = ", ".join(ins.get("domains", []) or ["—"])
    ips = ", ".join((ins.get("ips", []) or []) + (ins.get("cidrs", []) or []) or ["—"])
    fase = snap.eng.get("phase")
    r_i, r_c = T.finding_bucket("real")     # (icono, color) colorblind-safe por bucket de hallazgos
    w_i, w_c = T.finding_bucket("watch")
    n_i, n_c = T.finding_bucket("noise")
    lines = [
        T.panel_title("Engagement"),
        f"id:   {_esc(eid)}",
        f"fase: {phase_es(fase) if fase else '—'}",
        "",
        T.panel_title("Scope"),
        f"dom: {_esc(doms)}",
        f"ip:  {_esc(ips)}",
        "",
        T.panel_title("Hallazgos"),
        f"[{r_c}]{r_i} reales:[/]  {len(grp['real'])}",
        f"[{w_c}]{w_i} vigilar:[/] {len(grp['watch'])}",
        f"[{n_c}]{n_i} ruido:[/]   {len(grp['noise'])}",
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
