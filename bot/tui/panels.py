"""
panels.py — Paneles Textual (vistas FINAS) de la TUI de control total.

Cada panel SOLO pinta datos de un `state.Snapshot` (o ejecuta acciones de `actions.py`). La
lógica, el parsing y la escritura viven en esos módulos PUROS (testeados en bot/tests/test_tui.py);
aquí no hay reglas ni acceso a disco. Así la superficie no testeable (Textual) queda al mínimo.

Los botones burbujean `Button.Pressed` hasta la App, que los despacha por `button.id` (ver app.py).
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Label, Static

from . import state as S


class DashboardPanel(Vertical):
    """Estado del engagement + tabla de hallazgos (el panel original)."""

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static("", id="dash-status")
            yield DataTable(id="dash-findings")

    def on_mount(self) -> None:
        self.query_one("#dash-findings", DataTable).add_columns("", "ID", "Sev", "Título", "Target")

    def refresh_from(self, snap: S.Snapshot, grp: dict, sdk_ok: bool) -> None:
        self.query_one("#dash-status", Static).update(S.dashboard_status(snap, grp, sdk_ok))
        t = self.query_one("#dash-findings", DataTable)
        t.clear()
        for v in grp["verdicts"]:
            t.add_row(v.emoji, v.finding_id, v.severity.upper(), v.title[:40], v.target)


class A2APanel(Vertical):
    """Inspector del bus A2A: resumen + tabla de mensajes."""

    def compose(self) -> ComposeResult:
        yield Static("", id="a2a-summary")
        yield DataTable(id="a2a-table")

    def on_mount(self) -> None:
        self.query_one("#a2a-table", DataTable).add_columns("", "de", "a", "rol", "hops", "mensaje")

    def refresh_from(self, snap: S.Snapshot) -> None:
        self.query_one("#a2a-summary", Static).update(S.a2a_summary(snap.eng, snap.scope))
        t = self.query_one("#a2a-table", DataTable)
        t.clear()
        for row in S.a2a_rows(snap.eng):
            t.add_row(*row)


class RosterPanel(Vertical):
    """Catálogo de los 18 agentes (+orquestador) desde agent-cards.json."""

    def compose(self) -> ComposeResult:
        yield Static("", id="roster-hdr")
        yield DataTable(id="roster-table")

    def on_mount(self) -> None:
        self.query_one("#roster-table", DataTable).add_columns(
            "agente", "fase", "modelo", "peers", "descripción")

    def refresh_from(self, snap: S.Snapshot) -> None:
        self.query_one("#roster-hdr", Static).update(
            f"[b #00D4FF]Roster[/] — {len(snap.cards)} cards (incl. orquestador)")
        t = self.query_one("#roster-table", DataTable)
        t.clear()
        for row in S.roster_rows(snap.cards):
            t.add_row(*row)


class BudgetPanel(Vertical):
    """Presupuesto/kill-switch + timeline de fase + coste de la última orden."""

    def compose(self) -> ComposeResult:
        yield Static("", id="budget-box")
        yield Static("", id="phase-box")

    def refresh_from(self, snap: S.Snapshot) -> None:
        self.query_one("#budget-box", Static).update(S.budget_render(snap.count, snap.cap, snap.key))
        cost = f"${snap.cost:.2f}" if isinstance(snap.cost, (int, float)) else "—"
        self.query_one("#phase-box", Static).update(
            "[b #00D4FF]Fase[/]\n" + S.phase_render(snap.eng.get("phase", "")) +
            f"\n\n[b #00D4FF]Coste última orden[/]: {cost}\n"
            "Desglose histórico por agente:  ./deploy/agentsview.sh up")


class RagPanel(VerticalScroll):
    """Estado del RAG (última sync KEV/EPSS/…) + refresco manual."""

    def compose(self) -> ComposeResult:
        yield Static("", id="rag-box")
        with Horizontal(id="rag-btns"):
            yield Button("Refrescar RAG", id="rag-refresh", variant="primary")
            yield Button("Refrescar + EPSS completo", id="rag-refresh-epss")

    def refresh_from(self, store) -> None:
        self.query_one("#rag-box", Static).update(S.rag_render(store))


class EvidencePanel(Vertical):
    """Navegador de evidencia: engagements con artefactos + tabla evidence[]."""

    def compose(self) -> ComposeResult:
        yield Static("", id="ev-hdr")
        yield DataTable(id="ev-table")

    def on_mount(self) -> None:
        self.query_one("#ev-table", DataTable).add_columns(
            "ts", "agente", "acción", "target", "artefacto")

    def refresh_from(self, snap: S.Snapshot, engagements: list[str]) -> None:
        self.query_one("#ev-hdr", Static).update(S.evidence_header(engagements))
        t = self.query_one("#ev-table", DataTable)
        t.clear()
        for row in S.evidence_rows(snap.eng):
            t.add_row(*row)


class ActionsPanel(VerticalScroll):
    """Planos de ACCIÓN. Cada botón burbujea a la App, que llama a actions.py (puertas intactas)."""

    def compose(self) -> ComposeResult:
        yield Label("[b #FF4444]Kill-switch[/] — aborta la orden en curso (deniega lo pendiente)")
        yield Button("⛔ ABORTAR orden en curso", id="act-abort", variant="error")

        yield Label("[b #00D4FF]Delegación dirigida[/] — la ejecuta el Orquestador por el hub")
        yield Input(placeholder="agente (p.ej. sqlmap)", id="act-deleg-agent")
        yield Input(placeholder="objetivo concreto", id="act-deleg-obj")
        yield Button("Delegar", id="act-deleg", variant="primary")

        yield Label("[b #00D4FF]Override de fase[/]")
        yield Input(placeholder="fase: init/recon/triage/exploitation/post-exploitation/reporting/closed",
                    id="act-phase")
        yield Button("Cambiar fase", id="act-phase-btn")

        yield Label("[b #00D4FF]Control del bus A2A[/]")
        yield Input(placeholder="message_id", id="act-a2a-id")
        yield Input(placeholder="status: pending/delivered/done/blocked", id="act-a2a-status")
        yield Button("Aplicar status", id="act-a2a-btn")

        yield Label("[b #00D4FF]Modelo / effort del Orquestador[/] — efectivo en la próxima orden")
        yield Input(placeholder="ORCH_MODEL (claude-opus-4-8 / -sonnet-4-6 / -haiku-4-5)", id="act-model")
        yield Button("Fijar modelo", id="act-model-btn")
        yield Input(placeholder="ORCH_EFFORT (low/medium/high/xhigh/max)", id="act-effort")
        yield Button("Fijar effort", id="act-effort-btn")

        yield Label("[b #FF6B35]Supervisión humana[/] (full/critical/auto) — CONSTITUTION §2; "
                    "scope/budget NO se relajan en ningún modo")
        yield Input(placeholder="ORCH_APPROVAL_MODE (full / critical / auto)", id="act-approval")
        yield Button("Fijar supervisión", id="act-approval-btn")
