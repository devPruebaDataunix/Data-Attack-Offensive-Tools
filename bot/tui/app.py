"""
Panel de control TUI (Textual) — gemelo LOCAL del bot de Telegram, ahora con CONTROL TOTAL.

Reusa EXACTAMENTE el mismo cerebro que el bot (bot/intel: runner, classify, scope) y pasa por
las MISMAS puertas: el hook scope_guard (vía setting_sources del runner), la APROBACIÓN HUMANA
por acción (modal) y los guardarraíles C11-C19. La TUI NO puede saltarse ninguna puerta: los
planos de acción son overrides del operador sobre el blackboard/config, o delegaciones que el
Orquestador ejecuta por el hub (con todas las puertas).

Arranque:  ./deploy/dash.sh     (o, desde bot/:  python -m tui)

Estructura: pestañas (Panel · Bus A2A · Agentes · Presupuesto · RAG · Evidencia · Acciones) sobre
un log de eventos y una línea de orden persistentes. La lógica vive en state.py/actions.py (puros,
testeados en bot/tests/test_tui.py); aquí solo está el cableado Textual.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (Button, Footer, Header, Input, Label, RichLog,
                             Select, Static, TabbedContent, TabPane)

# El paquete intel vive en bot/ (un nivel por encima de tui/).
BOT_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BOT_DIR.parent
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

from intel import classify as C            # noqa: E402
from intel import scope as scp             # noqa: E402
from intel.runner import AgentRunner, SDK_OK  # noqa: E402

from . import actions as A                 # noqa: E402
from . import panels as P                  # noqa: E402
from . import sessionlog as SL             # noqa: E402  (log de narración persistente, F0)
from . import state as S                   # noqa: E402
from . import theme as T                   # noqa: E402  (tokens de color: única fuente)
from .commands import DataAttackCommands   # noqa: E402  (paleta de dominio en español)

PY = sys.executable or "python3"


def _load_env() -> dict:
    env = {}
    f = BOT_DIR / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _read_cfg() -> tuple[str, str, "float | None"]:
    """Relee la config del Orquestador en CADA orden (el panel de acciones puede cambiarla)."""
    env = _load_env()

    def g(k, d):
        return env.get(k) or os.environ.get(k) or d

    mx = (g("ORCH_MAX_USD", "") or "").strip()
    try:
        max_usd = float(mx) if mx else None
    except ValueError:
        max_usd = None
    return g("ORCH_MODEL", "claude-opus-4-8"), g("ORCH_EFFORT", "medium"), max_usd


def _approval_mode() -> "str | None":
    """Modo de supervisión de bot/.env (o entorno). None => el runner lo resuelve (scope/critical)."""
    env = _load_env()
    return (env.get("ORCH_APPROVAL_MODE") or os.environ.get("ORCH_APPROVAL_MODE") or "").strip() or None


def _stall_timeout() -> float:
    """Segundos SIN señal del SDK tras los que la TUI auto-recupera el lock. Override por env
    ORCH_STALL_TIMEOUT (bot/.env o entorno) para afinar en Kali si aparece un escaneo largo legítimo
    de un solo comando (sin señales intermedias); default = state.ORDER_STALL_TIMEOUT. Inválido/≤0 => default."""
    raw = (os.environ.get("ORCH_STALL_TIMEOUT") or _load_env().get("ORCH_STALL_TIMEOUT") or "").strip()
    try:
        v = float(raw)
        return v if v > 0 else S.ORDER_STALL_TIMEOUT
    except ValueError:
        return S.ORDER_STALL_TIMEOUT


class HistoryInput(Input):
    """Línea de orden con historial ↑/↓ estilo shell (el Input de Textual no lo trae). Toda la lógica
    de índice/dedup vive en state.CmdHistory (pura, testeada); aquí solo se cablea a las flechas.
    Se usan BINDINGS (no on_key) para NO interferir con la escritura de caracteres del Input base;
    el Input base no vincula ↑/↓ (es de una sola línea), así que estas bindings no chocan."""

    BINDINGS = [
        Binding("up", "history_prev", "Orden anterior", show=False),
        Binding("down", "history_next", "Orden siguiente", show=False),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._hist = S.CmdHistory()

    def remember(self, value: str) -> None:
        self._hist.remember(value)

    def action_history_prev(self) -> None:
        val = self._hist.prev()
        if val is not None:                # None = historial vacío -> no hacemos nada
            self.value = val
            self.cursor_position = len(val)

    def action_history_next(self) -> None:
        val = self._hist.next()
        if val is not None:                # '' (blanco) sí se aplica; None solo si está vacío
            self.value = val
            self.cursor_position = len(val)


class DetailModal(ModalScreen[None]):
    """Modal de solo-lectura para el drill-down (p.ej. el detalle de un mensaje del bus A2A). Se cierra
    con Esc o el botón. El cuerpo ya viene con markup escapado desde state.py."""

    BINDINGS = [Binding("escape", "close", "Cerrar", key_display="Esc")]

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-box"):
            yield Label(self._title, id="detail-title")
            with VerticalScroll(id="detail-scroll"):
                yield Static(self._body, id="detail-body")
            yield Button("Cerrar", id="detail-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

    def action_close(self) -> None:
        self.dismiss()


class ApprovalModal(ModalScreen[bool]):
    """Aprobación/confirmación humana modal (Autorizar/Denegar → bool). La usa el callback `approve` del
    runner (acción que toca el target) y también la confirmación de escritura de scope (title propio)."""

    def __init__(self, summary: str,
                 title: str = "⚠  Acción que toca el target — ¿autorizar?") -> None:
        super().__init__()
        self._summary = summary
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="appr-box"):
            yield Label(self._title, id="appr-title")
            yield Static(self._summary, id="appr-cmd")
            with Horizontal(id="appr-btns"):
                yield Button("Autorizar", variant="success", id="yes")
                yield Button("Denegar", variant="error", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class DataAttackTUI(App[None]):
    CSS_PATH = "app.tcss"
    # key_display: el footer muestra "Ctrl+K" en vez de la notación caret "^k" de Textual.
    BINDINGS = [
        Binding("q", "quit", "Salir", key_display="q"),
        Binding("r", "refresh", "Refrescar", key_display="r"),
        Binding("ctrl+k", "abort", "Kill-switch", key_display="Ctrl+K"),
        # Ctrl+L: maximiza/restaura el REGISTRO (log) para leer toda la narración sin que el auto-scroll
        # te arrastre al final (el panel Textual no se redimensiona con el ratón como una terminal).
        Binding("ctrl+l", "toggle_log", "Registro", key_display="Ctrl+L"),
        # Renombra la etiqueta del command-palette a español SIN desactivarlo: un Binding propio con
        # action="command_palette" reemplaza el de sistema (Textual de-duplica por ACCIÓN, no por id).
        # OJO: nada de kwarg id= aquí — no existe en Binding hasta Textual 0.82 y el pin es >=0.80.
        Binding("ctrl+p", "command_palette", "paleta", key_display="Ctrl+P"),
        # Teclas 1–8: salto directo a cada pestaña (no interfieren con la escritura: el Input consume
        # los dígitos cuando tiene el foco; estas solo actúan si el foco NO está en un campo de texto).
        *[Binding(str(i), f"show_tab({i})", show=False) for i in range(1, 9)],
    ]
    # Orden de las pestañas (= app.compose y commands.TABS). La tecla N va a TAB_IDS[N-1].
    TAB_IDS = ["tab-dash", "tab-a2a", "tab-roster", "tab-net", "tab-budget", "tab-rag", "tab-ev", "tab-act"]
    # Paleta (Ctrl+P): SOLO los comandos de DOMINIO en español (reemplaza los genéricos ingleses de
    # Textual: Keys/Quit/Theme/…). Definidos en bot/tui/commands.py; los ejecuta run_palette_command.
    COMMANDS = {DataAttackCommands}

    _running = False

    def get_css_variables(self) -> dict[str, str]:
        """Inyecta los tokens de theme.py como variables CSS ($brand/$info/…) para que app.tcss los
        use sin repetir el hex. La ÚNICA fuente de color de la TUI = bot/tui/theme.py."""
        variables = super().get_css_variables()
        variables.update(T.CSS_VARS)
        return variables

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="hdr")
        with TabbedContent():
            with TabPane("Panel", id="tab-dash"):
                yield P.DashboardPanel()
            with TabPane("Bus A2A", id="tab-a2a"):
                yield P.A2APanel()
            with TabPane("Agentes", id="tab-roster"):
                yield P.RosterPanel()
            with TabPane("Red", id="tab-net"):
                yield P.NetworkPanel()
            with TabPane("Presupuesto", id="tab-budget"):
                yield P.BudgetPanel()
            with TabPane("RAG", id="tab-rag"):
                yield P.RagPanel()
            with TabPane("Evidencia", id="tab-ev"):
                yield P.EvidencePanel()
            with TabPane("Acciones", id="tab-act"):
                yield P.ActionsPanel()
        yield RichLog(id="log", highlight=True, markup=True, wrap=True, max_lines=2000)
        yield Static("", id="order-status")   # estado en vivo de la orden en curso (lock observable)
        yield HistoryInput(
            placeholder="Orden al Orquestador (p.ej. 'haz recon de ...')  ·  'triage <producto>'  ·  ↑/↓ historial",
            id="cmd")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "DATA ATTACK"
        self.sub_title = "control total · mismas puertas que el bot"
        self._seen_msgs: set[str] = set()
        self._seeded = False
        self._runner: "AgentRunner | None" = None
        self._last_cost: "float | None" = None
        # Lock de orden OBSERVABLE (A1): metadatos de la orden en curso. `_order_token` es un objeto
        # único por invocación que evita que una orden ya reemplazada (exclusive) limpie el lock de la
        # nueva (defensa contra la carrera del finally). "en curso" == `_running`.
        self._order_task: "str | None" = None
        self._order_started: "float | None" = None   # reloj monotónico
        self._order_token: "object | None" = None
        self._order_worker = None                    # Worker Textual (para cancelarlo en la recuperación)
        self._stall_timeout = _stall_timeout()       # umbral de auto-recuperación (env ORCH_STALL_TIMEOUT)
        self._eid: "str | None" = None               # engagement activo: destino del log de sesión (F0)
        # Refs de paneles (todos viven montados aunque su pestaña esté oculta).
        self._dash = self.query_one(P.DashboardPanel)
        self._a2a = self.query_one(P.A2APanel)
        self._roster = self.query_one(P.RosterPanel)
        self._network = self.query_one(P.NetworkPanel)
        self._budget = self.query_one(P.BudgetPanel)
        self._rag = self.query_one(P.RagPanel)
        self._evidence = self.query_one(P.EvidencePanel)
        self._actions = self.query_one(P.ActionsPanel)
        if not SDK_OK:
            self._log(f"[{T.WARN}]Agent SDK no instalado aquí: las órdenes al Orquestador se "
                      "ejecutan en la Kali. El panel sí muestra estado, hallazgos y triage.[/]")
        self.refresh_state()               # fija self._eid del engagement activo
        self._replay_session_log()         # F0: reproduce el histórico persistido (sobrevive a reinicios)
        self._fetch_rag_status()
        self._fetch_kb_status()
        self.set_interval(5.0, self.refresh_state)
        self.set_interval(2.0, self._order_tick)   # refresco fino del estado de la orden + auto-timeout

    # ── refresco global (lector único) ───────────────────────────────────────────
    def refresh_state(self) -> None:
        snap = S.build_snapshot(REPO_DIR, self._last_cost, _approval_mode())
        self._eid = snap.eng.get("engagement_id") or None   # destino del log de sesión (F0)
        grp = C.scan(snap.eng.get("findings", []))
        self.query_one("#hdr", Static).update(
            S.header_line(snap.eng, snap.count, snap.cap, snap.cost, snap.approval_mode))
        self._dash.refresh_from(snap, grp, SDK_OK)
        self._a2a.refresh_from(snap)
        self._roster.refresh_from(snap)
        self._network.refresh_from(snap)
        self._budget.refresh_from(snap)
        self._evidence.refresh_from(snap, S.engagement_dirs(REPO_DIR))
        self._actions.refresh_from(snap)   # puebla el Select de agente una vez (catálogo estático)
        # Bus A2A: narra en el log los mensajes nuevos (el primer refresco solo los registra).
        for m in snap.eng.get("messages", []) or []:
            mid = m.get("message_id") if isinstance(m, dict) else None
            if not mid or mid in self._seen_msgs:
                continue
            self._seen_msgs.add(mid)
            if not self._seeded:
                continue
            frm, to, role = m.get("from_agent", "?"), m.get("to_agent", "?"), m.get("role", "")
            intent = next((p.get("text", "") for p in m.get("parts", []) or []
                           if p.get("kind") == "text" and p.get("text")), "")
            self._log(f"✉️ [b]{S._esc(frm)}[/] → [b]{S._esc(to)}[/] "
                      f"({S._esc(role)}) {S._esc(intent[:120])}")
        self._seeded = True

    def action_refresh(self) -> None:
        self.refresh_state()
        self._fetch_rag_status()
        self._fetch_kb_status()
        self._log(f"[{T.OK}]Estado refrescado.[/]")

    def action_abort(self) -> None:
        self._abort_order()

    def action_show_tab(self, n: int) -> None:
        if 1 <= n <= len(self.TAB_IDS):
            self.query_one(TabbedContent).active = self.TAB_IDS[n - 1]

    def action_toggle_log(self) -> None:
        """Maximiza/restaura el registro (Ctrl+L). Al maximizar PAUSA el auto-scroll (para leer la
        historia sin que un hito nuevo te arrastre al final) y le da el foco; al restaurar lo reanuda."""
        log = self.query_one("#log", RichLog)
        maxed = self.screen.has_class("logmax")
        self.screen.set_class(not maxed, "logmax")
        log.auto_scroll = maxed          # entra a maximizado -> False (leer) · sale -> True (seguir)
        if not maxed:
            log.focus()

    def show_detail(self, title: str, body: str) -> None:
        """Abre el modal de detalle (drill-down). Lo invocan los paneles vía self.app.show_detail(...)."""
        self.push_screen(DetailModal(title, body))

    def run_palette_command(self, key: str) -> None:
        """Despacha un comando de la paleta (bot/tui/commands.py) a su acción. Son ATAJOS a acciones
        que ya existen; NO saltan ninguna puerta (scope/budget/aprobación siguen igual)."""
        if key.startswith("tab:"):
            self.query_one(TabbedContent).active = key.split(":", 1)[1]
        elif key == "refresh":
            self.action_refresh()
        elif key == "focus-cmd":
            self.query_one("#cmd", Input).focus()
        elif key == "abort":
            self._abort_order()
        elif key == "rag-refresh":
            self._run_rag_refresh(False)
        elif key == "rag-refresh-epss":
            self._run_rag_refresh(True)
        elif key.startswith("approval:"):
            self._do_action(A.set_env_var(REPO_DIR, "ORCH_APPROVAL_MODE", key.split(":", 1)[1]))
        elif key == "quit":
            self.exit()
        else:
            self._log(f"[{T.WARN}]Comando de paleta desconocido: {key}[/]")

    def _log(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)
        SL.append(REPO_DIR, self._eid, msg)   # F0: persiste la narración (no-op sin engagement)

    def _replay_session_log(self) -> None:
        """F0: al arrancar REPRODUCE la narración persistida del engagement activo. El RichLog es
        efímero pero engagements/<id>/session.log sobrevive a reinicios; sin esto, tras un cuelgue/
        reinicio el registro salía vacío aunque el engagement seguía. Escribe DIRECTO al widget (no
        vía _log) para no re-persistir lo que ya está en disco."""
        entries = SL.tail(REPO_DIR, self._eid) if self._eid else []
        if not entries:
            return
        log = self.query_one("#log", RichLog)
        log.write(f"[{T.MUTED}]── historial de la sesión · "
                  f"engagements/{S._esc(self._eid)}/session.log ──[/]")
        for e in entries:
            clock = SL.fmt_clock(e.get("ts"))
            log.write((f"[{T.MUTED}]{clock}[/] " if clock else "") + str(e.get("text", "")))
        log.write(f"[{T.MUTED}]── fin del historial · en vivo ──[/]")

    # ── entrada de órdenes (solo el input #cmd) ──────────────────────────────────
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "cmd":
            return                       # los inputs del panel de acciones no lanzan órdenes
        task = event.value.strip()
        if task and isinstance(event.input, HistoryInput):
            event.input.remember(task)   # ↑/↓ recuperará esta orden (incl. las que rebota el scope)
        event.input.value = ""
        if not task:
            return
        low = task.lower()
        if low.startswith("triage ") or low.startswith("/triage "):
            self.run_triage(task.split(" ", 1)[1].strip())
            return
        question = scp.scope_question(task, scp.load_scope(REPO_DIR))
        if question:
            self._log(f"[{T.WARN}]{question}[/]")
            return
        self._log(f"[b {T.INFO}]Orden:[/] {task}")
        self._order_worker = self.run_order(task)

    # ── botones de los paneles ────────────────────────────────────────────────────
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "act-abort":
            self._abort_order()
        elif bid == "act-lab-scope":
            self._lab_scope_flow(launch=False)
        elif bid == "act-lab-run":
            self._lab_scope_flow(launch=True)
        elif bid == "act-deleg":
            agent = self.query_one("#act-deleg-agent", Select).value
            obj = self.query_one("#act-deleg-obj", Input).value.strip()
            if agent is Select.BLANK or not agent or not obj:
                self._log(f"[{T.WARN}]Delegación: elige un agente e indica el objetivo.[/]")
                return
            agent = str(agent)   # el Select solo ofrece agentes válidos del catálogo (sin typos)
            self.query_one("#act-deleg-obj", Input).value = ""
            order = A.compose_delegation(agent, obj)
            self._log(f"[b {T.INFO}]Delegación dirigida → {agent}[/]")
            self._order_worker = self.run_order(order)
        elif bid == "act-phase-btn":
            phase = self.query_one("#act-phase", Select).value
            if phase is Select.BLANK or not phase:
                self._log(f"[{T.WARN}]Elige una fase en el desplegable primero.[/]")
            else:
                self._do_action(A.set_phase(REPO_DIR, str(phase)))
        elif bid == "act-a2a-btn":
            mid = self.query_one("#act-a2a-id", Input).value.strip()
            st = self.query_one("#act-a2a-status", Input).value.strip()
            self._do_action(A.set_a2a_status(REPO_DIR, mid, st))
        elif bid == "act-model-btn":
            self._do_action(A.set_env_var(REPO_DIR, "ORCH_MODEL",
                                          self.query_one("#act-model", Input).value.strip()))
        elif bid == "act-effort-btn":
            self._do_action(A.set_env_var(REPO_DIR, "ORCH_EFFORT",
                                          self.query_one("#act-effort", Input).value.strip()))
        elif bid == "act-approval-btn":
            self._do_action(A.set_env_var(REPO_DIR, "ORCH_APPROVAL_MODE",
                                          self.query_one("#act-approval", Input).value.strip()))
        elif bid == "rag-refresh":
            self._run_rag_refresh(False)
        elif bid == "rag-refresh-epss":
            self._run_rag_refresh(True)

    def _do_action(self, result: "tuple[bool, str]") -> None:
        ok, msg = result
        self._log((f"[{T.OK}]✓ " if ok else f"[{T.DANGER}]✗ ") + msg + "[/]")
        if ok:
            self.refresh_state()

    def _abort_order(self) -> None:
        # Kill-switch (Ctrl+K / botón / paleta): recuperación MANUAL e instantánea del lock.
        if self._running:
            self._release_lock("kill-switch del operador")
        else:
            self._log(f"[{T.MUTED}]No hay ninguna orden en curso.[/]")

    def _release_lock(self, reason: str) -> None:
        """Recuperación del lock de orden: aborta el runner (deny cooperativo), CANCELA el worker (para
        desatascar un `await` colgado) y libera el lock DURAMENTE aunque el finally del worker no llegue
        a correr. Manual (Ctrl+K) o automática (auto-timeout por inactividad del SDK). Idempotente."""
        if not self._running:
            return
        if self._runner is not None:
            self._runner.abort()
            self._last_cost = self._runner.last_cost_usd   # conserva el coste parcial si lo hubo
        w = self._order_worker
        if w is not None:
            try:
                w.cancel()
            except Exception:  # noqa: BLE001 - cancelar un worker ya terminado no debe romper la TUI
                pass
        # Liberación dura: si el worker sigue vivo, su finally verá un token distinto y NO tocará nada.
        self._running = False
        self._order_token = None
        self._order_task = None
        self._order_started = None
        self._runner = None
        self._order_worker = None
        self._update_order_status()
        self.refresh_state()
        self._log(f"[{T.DANGER}]⛔ Orden liberada: {reason} — se deniega toda acción pendiente.[/]")
        try:
            self.notify(f"Orden liberada: {reason}", severity="warning", timeout=5)
        except Exception:  # noqa: BLE001 - notify es cosmético; nunca debe romper la recuperación
            pass

    def _update_order_status(self) -> None:
        """Pinta la barra #order-status con el estado en vivo de la orden (task/elapsed/turnos/coste)."""
        turns = getattr(self._runner, "live_turns", None)
        cost = getattr(self._runner, "last_cost_usd", None)
        beat = getattr(self._runner, "last_beat", None)
        self.query_one("#order-status", Static).update(
            S.order_status_line(self._order_task, self._order_started, time.monotonic(),
                                turns=turns, cost=cost, last_beat=beat, timeout=self._stall_timeout))

    def _order_tick(self) -> None:
        """Tick de 2 s: refresca el estado en vivo y AUTO-RECUPERA el lock si el SDK lleva demasiado
        tiempo sin dar señal (cuelgue silencioso). La recuperación manual (Ctrl+K) es instantánea."""
        if not self._running:
            return
        self._update_order_status()
        beat = getattr(self._runner, "last_beat", None)
        if S.order_stale(self._order_started, beat, time.monotonic(), self._stall_timeout):
            self._release_lock("sin señal del SDK (auto-recuperación por inactividad)")

    # ── arranque de lab: objetivo → scope.json (+ lanzar) ─────────────────────────
    @work(exclusive=True, group="labscope")
    async def _lab_scope_flow(self, launch: bool) -> None:
        """Define el alcance del lab desde la TUI: pre-valida, PIDE CONFIRMACIÓN (escribir scope.json es
        tocar la frontera de confianza), escribe (atómico + backup + auditado) y, si se pidió, lanza el
        engagement completo por run_order (todas las puertas siguen activas). NO relaja ninguna puerta."""
        targets = self.query_one("#act-lab-targets", Input).value.strip()
        eid = self.query_one("#act-lab-eid", Input).value.strip()
        approval = self.query_one("#act-lab-approval", Input).value.strip() or "auto"
        if not targets:
            self._log(f"[{T.WARN}]Arranque de lab: indica al menos un objetivo (IP/CIDR/dominio).[/]")
            return
        # pre-valida SIN escribir para mostrar un resumen fiel en el modal de confirmación
        ok, res = A.build_lab_scope(targets, eid, approval, base=S.load_scope(REPO_DIR))
        if not ok:
            self._log(f"[{T.DANGER}]✗ {res}[/]")
            return
        summary = (f"Se ESCRIBIRÁ contracts/scope.json (con backup .bak):\n"
                   f"  objetivos:   {S._esc(targets)}\n"
                   f"  supervisión: {approval}\n"
                   f"  engagement:  {S._esc(res['engagement_id'])}\n"
                   + ("\n▶ y se LANZARÁ el lab completo de inmediato." if launch
                      else "\n(no se lanza nada; solo se define el alcance)"))
        confirmed = await self.push_screen_wait(
            ApprovalModal(summary, title="⚠  Vas a definir el ALCANCE (scope.json) — ¿confirmar?"))
        if not confirmed:
            self._log(f"[{T.MUTED}]Arranque de lab cancelado; el alcance no se ha tocado.[/]")
            return
        ok, msg = A.set_lab_scope(REPO_DIR, targets, eid, approval)
        self._do_action((ok, msg))
        if not ok:
            return
        for wid in ("#act-lab-targets", "#act-lab-eid", "#act-lab-approval"):
            self.query_one(wid, Input).value = ""
        if launch:
            order = A.compose_lab_run(targets)
            self._log(f"[b {T.BRAND}]▶️ lanzando el lab completo (supervisión {approval})…[/]")
            self._order_worker = self.run_order(order)

    # ── triage (RAG) ──────────────────────────────────────────────────────────────
    @work(exclusive=True, group="triage")
    async def run_triage(self, query: str) -> None:
        if not query:
            return
        self._log(f"[b {T.INFO}]Triage:[/] {query}")
        proc = await asyncio.create_subprocess_exec(
            PY, "rag/query_vulns.py", "--query", query, "--json", "--limit", "5",
            cwd=str(REPO_DIR), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        try:
            results = json.loads(out.decode("utf-8", "replace")).get("results", [])
        except ValueError:
            self._log(f"[{T.DANGER}]Sin resultados (¿RAG poblado?).[/]")
            return
        if not results:
            self._log("Sin coincidencias en el RAG.")
        for r in results:
            flags = " ".join(f for f, c in (("KEV", r.get("in_kev")),
                                            ("EXPLOIT", r.get("exploit_public"))) if c)
            self._log(f"  • {r.get('cve')} {str(r.get('severity', '')).upper()} "
                      f"CVSS={r.get('cvss')} EPSS={r.get('epss')} {flags}")

    # ── RAG: estado y refresco ────────────────────────────────────────────────────
    @work(exclusive=True, group="ragstatus")
    async def _fetch_rag_status(self) -> None:
        proc = await asyncio.create_subprocess_exec(
            PY, "rag/query_vulns.py", "--query", "apache", "--json", "--limit", "1",
            cwd=str(REPO_DIR), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        self._rag.refresh_from(S.parse_rag_store(out.decode("utf-8", "replace")))

    @work(exclusive=True, group="kbstatus")
    async def _fetch_kb_status(self) -> None:
        # RAG de CONOCIMIENTO (Capa 1 kb.db + Capa 2 kb_vec.db) — --stats es SQLite plano (sin venv/embedder).
        proc = await asyncio.create_subprocess_exec(
            PY, "rag/knowledge/query_kb.py", "--stats", "--json",
            cwd=str(REPO_DIR), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        self._rag.refresh_kb(S.parse_kb_stats(out.decode("utf-8", "replace")))

    @work(exclusive=True, group="ragrefresh")
    async def _run_rag_refresh(self, epss_all: bool) -> None:
        self._log(f"[{T.INFO}]Refrescando el RAG… (puede tardar)[/]")
        proc = await asyncio.create_subprocess_exec(
            *A.rag_refresh_cmd(epss_all), cwd=str(REPO_DIR),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        await proc.communicate()
        self._log(f"[{T.OK}]RAG refrescado.[/]" if proc.returncode == 0
                  else f"[{T.DANGER}]Fallo al refrescar el RAG (revisa la Kali).[/]")
        self._fetch_rag_status()

    # ── orden al Orquestador ──────────────────────────────────────────────────────
    # exclusive=True: una nueva orden CANCELA la anterior en curso (nunca se rechaza en falso). Con un
    # solo worker en el grupo "order" nunca corren dos Orquestadores sobre el mismo blackboard.
    @work(exclusive=True, group="order")
    async def run_order(self, task: str) -> None:
        if not SDK_OK:
            self._log(f"[{T.WARN}]No puedo lanzar el Orquestador aquí (Agent SDK ausente). "
                      "Ejecuta la orden desde la Kali.[/]")
            return
        if self._running:   # el exclusive ya está cancelando la anterior; solo informamos
            self._log(f"[{T.WARN}]↻ Reemplazo la orden anterior en curso por esta nueva.[/]")

        token = object()   # identidad única de ESTA orden (para el guard anti-carrera del finally)
        self._order_token = token
        self._order_task = task
        self._order_started = time.monotonic()
        self._running = True
        self._update_order_status()
        self._log(f"[b {T.BRAND}]▶️ orden lanzada:[/] {S._esc(task)}")
        try:
            self.notify(f"Orden lanzada: {task[:60]}", timeout=4)
        except Exception:  # noqa: BLE001 - notify es cosmético
            pass

        async def emit(text):
            self._log(text)
            self._update_order_status()   # feedback vivo: cada hito refresca turnos/coste/elapsed

        async def status(text):
            self.sub_title = (text or "")[:60]

        async def approve(summary):
            return await self.push_screen_wait(ApprovalModal(summary))

        async def on_verdict(verdict, finding):
            self._log(f"{verdict.emoji} [b]{S._esc(verdict.finding_id)}[/] {S._esc(verdict.title[:50])}")
            self.refresh_state()

        model, effort, max_usd = _read_cfg()
        runner = AgentRunner(REPO_DIR, emit, status, approve, on_verdict,
                             model=model, effort=effort, max_usd=max_usd,
                             approval_mode=_approval_mode())
        self._runner = runner
        final = None
        try:
            final = await runner.run(task)
        except Exception as exc:  # noqa: BLE001 - se reporta al panel, no se traga
            self._log(f"[{T.DANGER}]Error del runner: {exc}[/]")
        finally:
            # Solo libero el lock si SIGO siendo la orden vigente: si otra orden me reemplazó (exclusive)
            # o el operador me liberó (Ctrl+K), el token ya cambió y NO debo pisar su estado.
            if self._order_token is token:
                self._running = False
                self._order_token = None
                self._order_task = None
                self._order_started = None
                self._runner = None
                self._last_cost = runner.last_cost_usd
                self._order_worker = None
                self._update_order_status()
                self.refresh_state()
        if final and self._order_token is None:   # no ensuciar el log si ya arrancó otra orden encima
            self._log(f"[{T.OK}]Resultado:[/] {final[:1500]}")


def main() -> None:
    DataAttackTUI().run()


if __name__ == "__main__":
    main()
