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
from textual.widgets import Button, DataTable, Input, Label, Select, Static

from . import state as S
from . import theme as T


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
            # el título/target de un finding pueden traer texto influido por el target: escapar el markup
            t.add_row(v.emoji, v.finding_id, v.severity.upper(),
                      S._esc(v.title[:40]), S._esc(v.target))


class A2APanel(Vertical):
    """Inspector del bus A2A: resumen + tabla de mensajes. Seleccionar una fila (Enter/clic) abre el
    detalle del mensaje (drill-down sobre state.message_detail)."""

    def compose(self) -> ComposeResult:
        yield Static("", id="a2a-summary")
        yield DataTable(id="a2a-table")

    def on_mount(self) -> None:
        self._eng: dict = {}
        t = self.query_one("#a2a-table", DataTable)
        t.add_columns("", "de", "a", "rol", "hops", "mensaje")
        t.cursor_type = "row"       # selección por fila -> drill-down (RowSelected)

    def refresh_from(self, snap: S.Snapshot) -> None:
        self._eng = snap.eng
        self.query_one("#a2a-summary", Static).update(S.a2a_summary(snap.eng, snap.scope))
        t = self.query_one("#a2a-table", DataTable)
        t.clear()
        for mid, row in zip(S.a2a_message_ids(snap.eng), S.a2a_rows(snap.eng)):
            t.add_row(*row, key=mid or None)   # key = message_id (para el drill-down)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        mid = event.row_key.value if event.row_key else None
        if mid:
            self.app.show_detail("Mensaje A2A", S.message_detail(self._eng, mid))


class RosterPanel(Vertical):
    """Agentes agrupados por ZONA E1/E2/E3 (master) + ficha COMPLETA del agente resaltado (detalle).
    Resuelve el truncado/ilegibilidad del roster plano anterior: la descripción va ENTERA en la ficha
    (derecha), no en una celda cortada. Una tabla por zona (orquestador · E1🟦 · E2🟥 · E3🟩); al
    resaltar una fila (RowHighlighted) se muestra su ficha. Toda la lógica es de state.py (pura)."""

    _ZONES = ["orch", "E1", "E2", "E3", "otro"]

    def compose(self) -> ComposeResult:
        yield Static("", id="roster-hdr")
        with Horizontal(id="roster-body"):
            with VerticalScroll(id="roster-zones"):
                for z in self._ZONES:
                    yield Static("", id=f"roster-title-{z}", classes="roster-zone-title")
                    yield DataTable(id=f"roster-tbl-{z}", classes="roster-zone-tbl")
            with VerticalScroll(id="roster-detail-wrap"):
                yield Static("", id="roster-detail")

    def on_mount(self) -> None:
        self._cards: list = []
        self._lab: dict = {}
        for z in self._ZONES:
            t = self.query_one(f"#roster-tbl-{z}", DataTable)
            t.add_columns("agente", "fase", "modelo (bot)", "modelo lab", "peers")
            t.cursor_type = "row"       # resaltado por FILA -> dispara RowHighlighted al navegar
        self.query_one("#roster-detail", Static).update(S.agent_detail(None))

    def refresh_from(self, snap: S.Snapshot) -> None:
        self._cards = snap.cards
        self._lab = snap.lab_routes
        self.query_one("#roster-hdr", Static).update(
            f"{T.panel_title('Agentes por zona')} — {len(snap.cards)} (incl. orquestador)\n"
            f"[{T.MUTED}]E1🟦 recon · E2🟥 explotación · E3🟩 cierre · modelo (bot)=Anthropic real · "
            "modelo lab=perfil NVIDIA (LAB-ONLY, el bot NO lo usa) · resalta una fila para ver su ficha[/]")
        grouped = dict(S.roster_by_zone(snap.cards, snap.lab_routes))
        for z in self._ZONES:
            title = self.query_one(f"#roster-title-{z}", Static)
            tbl = self.query_one(f"#roster-tbl-{z}", DataTable)
            rows = grouped.get(z, [])
            title.display = tbl.display = bool(rows)   # oculta las zonas vacías (típicamente 'otro')
            if not rows:
                continue
            title.update(f"[b]{S.zone_label(z)}[/] ({len(rows)})")
            tbl.clear()
            for r in rows:
                tbl.add_row(*r, key=r[0])              # key = nombre del agente (para la ficha)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        name = event.row_key.value if event.row_key else None
        self.query_one("#roster-detail", Static).update(
            S.agent_detail(S.find_card(self._cards, name), self._lab))


class BudgetPanel(Vertical):
    """Presupuesto/kill-switch + timeline de fase + coste de la última orden."""

    def compose(self) -> ComposeResult:
        yield Static("", id="budget-box")
        yield Static("", id="phase-box")

    def refresh_from(self, snap: S.Snapshot) -> None:
        self.query_one("#budget-box", Static).update(S.budget_render(snap.count, snap.cap, snap.key))
        cost = f"${snap.cost:.2f}" if isinstance(snap.cost, (int, float)) else "—"
        self.query_one("#phase-box", Static).update(
            T.panel_title("Fase") + "\n" + S.phase_render(snap.eng.get("phase", "")) +
            f"\n\n{T.panel_title('Coste última orden')}: {cost}\n"
            "Desglose histórico por agente:  ./deploy/agentsview.sh up")


class RagPanel(VerticalScroll):
    """RAG de VULNS (sync KEV/EPSS/…) + RAG de CONOCIMIENTO (Capa 1 kb.db + Capa 2 kb_vec.db) + refresco."""

    def compose(self) -> ComposeResult:
        yield Static("", id="rag-box")
        yield Static("", id="kb-box")
        with Horizontal(id="rag-btns"):
            yield Button("Refrescar RAG", id="rag-refresh", variant="primary")
            yield Button("Refrescar + EPSS completo", id="rag-refresh-epss")

    def refresh_from(self, store) -> None:
        self.query_one("#rag-box", Static).update(S.rag_render(store))

    def refresh_kb(self, rep) -> None:
        self.query_one("#kb-box", Static).update(S.kb_render(rep))


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


class NetworkPanel(VerticalScroll):
    """Pestaña Red — topología multi-host: hosts (frontera de ataque), pivots (túneles) y credenciales
    (SIEMPRE referenciadas; el secreto vive en loot/, fuera de git). Todo el render es de state.py."""

    def compose(self) -> ComposeResult:
        yield Static("", id="net-summary")
        yield Static("", id="net-hosts-title")
        yield DataTable(id="net-hosts")
        yield Static("", id="net-pivots-title")
        yield DataTable(id="net-pivots")
        yield Static("", id="net-creds-title")
        yield DataTable(id="net-creds")

    def on_mount(self) -> None:
        self.query_one("#net-hosts", DataTable).add_columns(
            "host", "tipo", "scope", "acceso", "alcance", "defensas")
        self.query_one("#net-pivots", DataTable).add_columns(
            "pivot", "herramienta", "vía", "estado", "alcanza")
        self.query_one("#net-creds", DataTable).add_columns(
            "cred", "principal", "tipo", "privilegio", "origen", "validada")

    def refresh_from(self, snap: S.Snapshot) -> None:
        self.query_one("#net-summary", Static).update(S.network_summary(snap.eng))
        self.query_one("#net-hosts-title", Static).update(T.panel_title("Hosts (frontera de ataque)"))
        self.query_one("#net-pivots-title", Static).update(T.panel_title("Pivots (túneles)"))
        self.query_one("#net-creds-title", Static).update(T.panel_title("Credenciales (referenciadas)"))
        self._fill("#net-hosts", S.network_rows(snap.eng))
        self._fill("#net-pivots", S.pivot_rows(snap.eng))
        self._fill("#net-creds", S.credential_rows(snap.eng))

    def _fill(self, selector: str, rows: list) -> None:
        t = self.query_one(selector, DataTable)
        t.clear()
        for r in rows:
            t.add_row(*r)


class ActionsPanel(VerticalScroll):
    """Planos de ACCIÓN. Cada botón burbujea a la App, que llama a actions.py (puertas intactas)."""

    def compose(self) -> ComposeResult:
        yield Label(f"[b {T.DANGER}]Kill-switch[/] — aborta la orden en curso (deniega lo pendiente)")
        yield Button("⛔ ABORTAR orden en curso", id="act-abort", variant="error")

        yield Label(f"{T.panel_title('Arranque de lab (objetivo → alcance → autogestión)')} — define el "
                    "alcance y, si quieres, lanza el engagement completo en un paso")
        yield Input(placeholder="objetivo(s): IP / CIDR / dominio, separados por coma (p.ej. 172.17.0.2)",
                    id="act-lab-targets")
        yield Input(placeholder="engagement id (opcional; por defecto LAB-<objetivo>)", id="act-lab-eid")
        yield Input(placeholder="supervisión al operar (auto / critical / full; por defecto auto)",
                    id="act-lab-approval")
        with Horizontal(id="act-lab-btns"):
            yield Button("Definir alcance", id="act-lab-scope", variant="warning")
            yield Button("Definir alcance + LANZAR lab", id="act-lab-run", variant="primary")

        yield Label(f"{T.panel_title('Delegación dirigida')} — la ejecuta el Orquestador por el hub")
        yield Input(placeholder="agente (p.ej. sqlmap)", id="act-deleg-agent")
        yield Input(placeholder="objetivo concreto", id="act-deleg-obj")
        yield Button("Delegar", id="act-deleg", variant="primary")

        yield Label(T.panel_title("Override de fase"))
        # Select (no texto libre): opciones = las fases del esquema con etiqueta en español; el valor
        # enviado es la clave canónica en inglés. Evita typos que rechazaría set_phase.
        yield Select([(S.phase_es(p), p) for p in S.PHASES], id="act-phase", prompt="Elige una fase…")
        yield Button("Cambiar fase", id="act-phase-btn")

        yield Label(T.panel_title("Control del bus A2A"))
        yield Input(placeholder="message_id", id="act-a2a-id")
        yield Input(placeholder="status: pending/delivered/done/blocked", id="act-a2a-status")
        yield Button("Aplicar status", id="act-a2a-btn")

        yield Label(f"{T.panel_title('Modelo / effort del Orquestador')} — efectivo en la próxima orden")
        yield Input(placeholder="ORCH_MODEL (claude-opus-4-8 / -sonnet-4-6 / -haiku-4-5)", id="act-model")
        yield Button("Fijar modelo", id="act-model-btn")
        yield Input(placeholder="ORCH_EFFORT (low/medium/high/xhigh/max)", id="act-effort")
        yield Button("Fijar effort", id="act-effort-btn")

        yield Label(f"[b {T.WARN}]Supervisión humana[/] (full/critical/auto) — CONSTITUTION §2; "
                    "scope/budget NO se relajan en ningún modo")
        yield Input(placeholder="ORCH_APPROVAL_MODE (full / critical / auto)", id="act-approval")
        yield Button("Fijar supervisión", id="act-approval-btn")
