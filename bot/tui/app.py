"""
Panel de control TUI (Textual) — gemelo LOCAL del bot de Telegram.

Reusa EXACTAMENTE el mismo cerebro que el bot (bot/intel: runner, classify, scope) y pasa por
las MISMAS puertas de seguridad: el hook determinista scope_guard (vía setting_sources del runner),
la APROBACIÓN HUMANA por acción (aquí un modal en vez del teclado de Telegram) y los guardarraíles
C11-C13. No reimplementa lógica: es otro front-end sobre el Orquestador. La TUI NO puede saltarse
ninguna puerta.

Arranque:  ./deploy/dash.sh     (o, desde bot/:  python -m tui)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (Button, DataTable, Footer, Header, Input, Label,
                             RichLog, Static)

# El paquete intel vive en bot/ (un nivel por encima de tui/).
BOT_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BOT_DIR.parent
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

from intel import classify as C            # noqa: E402
from intel import scope as scp             # noqa: E402
from intel.runner import AgentRunner, SDK_OK  # noqa: E402

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


_ENV = _load_env()


def _cfg(key: str, default: str) -> str:
    return _ENV.get(key) or os.environ.get(key) or default


ORCH_MODEL = _cfg("ORCH_MODEL", "claude-opus-4-8")
ORCH_EFFORT = _cfg("ORCH_EFFORT", "medium")
_mx = _cfg("ORCH_MAX_USD", "").strip()
try:
    ORCH_MAX_USD = float(_mx) if _mx else None
except ValueError:
    ORCH_MAX_USD = None


def _banner() -> str:
    parts = []
    for name in ("data-attack.txt", "dataunix.txt"):
        f = REPO_DIR / "assets" / "banners" / name
        if f.exists():
            parts.append(f.read_text(encoding="utf-8").rstrip("\n"))
    return "\n".join(parts) if parts else "DATA ATTACK"


class ApprovalModal(ModalScreen[bool]):
    """Aprobación humana por acción — mapea el callback `approve` del runner."""

    def __init__(self, summary: str) -> None:
        super().__init__()
        self._summary = summary

    def compose(self) -> ComposeResult:
        with Vertical(id="appr-box"):
            yield Label("⚠  Acción que toca el target — ¿autorizar?", id="appr-title")
            yield Static(self._summary, id="appr-cmd")
            with Horizontal(id="appr-btns"):
                yield Button("Autorizar", variant="success", id="yes")
                yield Button("Denegar", variant="error", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class DataAttackTUI(App[None]):
    CSS = """
    Screen { background: #0D1117; }
    #banner { color: #00D4FF; height: auto; padding: 0 1; }
    #status { width: 40; border: round #00D4FF; padding: 0 1; }
    #findings { border: round #00D4FF; }
    #log { height: 12; border: round #3FB950; padding: 0 1; }
    #cmd { border: tall #00D4FF; }
    #appr-box { background: #161B22; border: thick #FF4444; padding: 1 2; width: 76; height: auto; }
    #appr-title { color: #FF4444; text-style: bold; }
    #appr-cmd { color: #C9D1D9; padding: 1 0; }
    #appr-btns { height: auto; align: center middle; }
    Button { margin: 0 2; }
    """
    BINDINGS = [("q", "quit", "Salir"), ("r", "refresh", "Refrescar")]

    _running = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(_banner(), id="banner")
        with Horizontal():
            yield Static("", id="status")
            yield DataTable(id="findings")
        yield RichLog(id="log", highlight=True, markup=True, wrap=True)
        yield Input(placeholder="Orden al Orquestador (p.ej. 'haz recon de ...')  ·  'triage <producto>'",
                    id="cmd")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#findings", DataTable)
        table.add_columns("", "ID", "Sev", "Título", "Target")
        self._seen_msgs: set[str] = set()  # message_id A2A ya narrados
        self._seeded = False               # primer refresco = solo registra, no narra
        self.title = "DATA ATTACK"
        self.sub_title = "control local · mismas puertas que el bot"
        if not SDK_OK:
            self._log("[#FF6B35]Agent SDK no instalado aquí: las órdenes al Orquestador "
                      "se ejecutan en la Kali. El panel sí muestra estado, hallazgos y triage.[/]")
        self.refresh_state()
        self.set_interval(5.0, self.refresh_state)

    # ── estado / blackboard ──────────────────────────────────────────────────
    def refresh_state(self) -> None:
        sc = scp.load_scope(REPO_DIR)
        eng = REPO_DIR / "contracts" / "engagement.json"
        data = {}
        if eng.exists():
            try:
                data = json.loads(eng.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        grp = C.scan(data.get("findings", []))
        msgs = data.get("messages", [])
        ins = (sc or {}).get("in_scope", {})
        doms = ", ".join(ins.get("domains", []) or ["—"])
        ips = ", ".join((ins.get("ips", []) or []) + (ins.get("cidrs", []) or []) or ["—"])
        lines = [
            "[b #00D4FF]Engagement[/]",
            f"id:   {data.get('engagement_id', '—')}",
            f"fase: {data.get('phase', '—')}",
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
            "[b #00D4FF]Bus A2A[/]",
            f"mensajes: {len(msgs)}",
            "",
            f"motor: {'Agent SDK' if SDK_OK else 'remoto (Kali)'}",
        ]
        self.query_one("#status", Static).update("\n".join(lines))
        table = self.query_one("#findings", DataTable)
        table.clear()
        for v in grp["verdicts"]:
            table.add_row(v.emoji, v.finding_id, v.severity.upper(), v.title[:40], v.target)
        # Bus A2A: narra los mensajes nuevos en el log (el primer refresco solo los registra).
        for m in msgs:
            mid = m.get("message_id")
            if not mid or mid in self._seen_msgs:
                continue
            self._seen_msgs.add(mid)
            if not self._seeded:
                continue
            frm, to, role = m.get("from_agent", "?"), m.get("to_agent", "?"), m.get("role", "")
            intent = next((p.get("text", "") for p in m.get("parts", [])
                           if p.get("kind") == "text" and p.get("text")), "")
            self._log(f"✉️ [b]{frm}[/] → [b]{to}[/] ({role}) {intent[:120]}")
        self._seeded = True

    def action_refresh(self) -> None:
        self.refresh_state()
        self._log("[#3FB950]Estado refrescado.[/]")

    def _log(self, msg: str) -> None:
        self.query_one("#log", RichLog).write(msg)

    # ── entrada de órdenes ─────────────────────────────────────────────────────
    def on_input_submitted(self, event: Input.Submitted) -> None:
        task = event.value.strip()
        event.input.value = ""
        if not task:
            return
        low = task.lower()
        if low.startswith("triage ") or low.startswith("/triage "):
            self.run_triage(task.split(" ", 1)[1].strip())
            return
        # Pre-chequeo de scope (NO sustituye al hook scope_guard; solo avisa si falta).
        question = scp.scope_question(task, scp.load_scope(REPO_DIR))
        if question:
            self._log(f"[#FF6B35]{question}[/]")
            return
        self._log(f"[b #00D4FF]Orden:[/] {task}")
        self.run_order(task)

    @work(exclusive=True, group="triage")
    async def run_triage(self, query: str) -> None:
        if not query:
            return
        self._log(f"[b #00D4FF]Triage:[/] {query}")
        proc = await asyncio.create_subprocess_exec(
            PY, "rag/query_vulns.py", "--query", query, "--json", "--limit", "5",
            cwd=str(REPO_DIR), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await proc.communicate()
        try:
            results = json.loads(out.decode("utf-8", "replace")).get("results", [])
        except json.JSONDecodeError:
            self._log("[#FF4444]Sin resultados (¿RAG poblado?).[/]")
            return
        if not results:
            self._log("Sin coincidencias en el RAG.")
        for r in results:
            flags = " ".join(f for f, c in (("KEV", r.get("in_kev")),
                                            ("EXPLOIT", r.get("exploit_public"))) if c)
            self._log(f"  • {r.get('cve')} {str(r.get('severity', '')).upper()} "
                      f"CVSS={r.get('cvss')} EPSS={r.get('epss')} {flags}")

    @work(group="order")
    async def run_order(self, task: str) -> None:
        # Sin exclusive: una segunda orden NO cancela la que corre; el guard la rechaza
        # (igual que el bot: una orden a la vez por sesión).
        if self._running:
            self._log("[#FF6B35]Ya hay una orden en curso; espera a que termine.[/]")
            return
        if not SDK_OK:
            self._log("[#FF6B35]No puedo lanzar el Orquestador aquí (Agent SDK ausente). "
                      "Ejecuta la orden desde la Kali.[/]")
            return

        async def emit(text):
            self._log(text)

        async def status(text):
            self.sub_title = (text or "")[:60]

        async def approve(summary):
            return await self.push_screen_wait(ApprovalModal(summary))

        async def on_verdict(verdict, finding):
            self._log(f"{verdict.emoji} [b]{verdict.finding_id}[/] {verdict.title[:50]}")
            self.refresh_state()

        self._running = True
        runner = AgentRunner(REPO_DIR, emit, status, approve, on_verdict,
                             model=ORCH_MODEL, effort=ORCH_EFFORT, max_usd=ORCH_MAX_USD)
        try:
            final = await runner.run(task)
        except Exception as exc:  # noqa: BLE001 - se reporta al panel, no se traga
            self._log(f"[#FF4444]Error del runner: {exc}[/]")
            return
        finally:
            self._running = False
            self.refresh_state()
        if final:
            self._log(f"[#3FB950]Resultado:[/] {final[:1500]}")


def main() -> None:
    DataAttackTUI().run()


if __name__ == "__main__":
    main()
