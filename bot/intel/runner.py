"""
Runner del Orquestador sobre el Claude Agent SDK.

Sustituye el `claude -p` one-shot por una sesión con streaming:
  - emite HITOS en tiempo real (qué subagente arranca, qué fase, resultado);
  - pide APROBACIÓN HUMANA por acción para comandos que tocan el target;
  - detecta EVIDENCIA REAL en cuanto se escribe en contracts/engagement.json y la
    clasifica (real / watch / ruido) para alertar solo de lo que importa.

El gate determinista de scope lo sigue aplicando el hook scope_guard.py (cargado vía
setting_sources=["project"]); esta capa es la supervisión humana por Telegram encima.

Si el SDK no está instalado, cae a `claude -p` (degradado, sin streaming).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

from . import classify as C
from . import risk as R
from .risk import OFFENSIVE  # noqa: F401 - re-exportado para compatibilidad de tests

try:
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        PermissionResultAllow,
        PermissionResultDeny,
        ResultMessage,
        TextBlock,
        ToolUseBlock,
    )
    SDK_OK = True
except Exception:  # pragma: no cover - SDK ausente en algunos entornos
    SDK_OK = False

# La clasificación de riesgo por tiers (safe/normal/sensitive/destructive/critical) y la
# política de aprobación viven en risk.py; OFFENSIVE se re-exporta arriba (compat de tests).

EmitFn = Callable[[str], Awaitable[None]]
StatusFn = Callable[[str], Awaitable[None]]
ApproveFn = Callable[[str], Awaitable[bool]]
VerdictFn = Callable[["C.Verdict", dict], Awaitable[None]]


def _trim(s: str, n: int) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


class AgentRunner:
    """Una ejecución del Orquestador para una orden de Telegram."""

    def __init__(
        self,
        repo: Path,
        emit: EmitFn,
        status: StatusFn,
        approve: ApproveFn,
        on_verdict: VerdictFn,
        model: Optional[str] = None,
        approval_timeout: int = 300,
        status_min_gap: float = 3.0,
        effort: Optional[str] = "medium",
        max_usd: Optional[float] = None,
        approval_mode: Optional[str] = None,
    ):
        self.repo = Path(repo)
        self.emit = emit              # mensaje nuevo: hito importante
        self.status = status          # edición del mensaje de estado (throttled)
        self.approve = approve        # pide confirmación humana -> True/False
        self.on_verdict = on_verdict  # alerta de finding clasificado
        self.model = model
        self.approval_timeout = approval_timeout
        self.status_min_gap = status_min_gap
        self.effort = effort          # effort del Orquestador (coste). None = sin override.
        self.max_usd = max_usd        # techo de coste por run en USD. None = sin techo.
        # Modo de supervisión humana (full|critical|auto). SOLO afecta a la aprobación humana por
        # acción de ESTE gate; NO relaja los hooks deterministas (scope_guard/budget_guard), que
        # siguen denegando por su cuenta. Default 'critical' (solo C2/implantes piden aprobación).
        self.approval_mode = self._resolve_approval_mode(approval_mode)

        self._subagents: dict[str, str] = {}   # tool_use_id (Task) -> subagent_type
        self._seen: dict[str, str] = {}        # finding_id -> último status visto
        self._seen_msgs: set[str] = set()      # message_id A2A ya narrados
        self._eng_mtime = 0.0
        self._last_status = 0.0
        self._final = ""
        # Telemetría de la última orden (la consume la TUI; el bot la ignora). Aditivo.
        self.last_cost_usd: Optional[float] = None
        self.last_turns: Optional[int] = None
        # Telemetría EN VIVO (la lee la TUI en su tick para el feedback y el auto-timeout del lock; el
        # bot la ignora). started_at/last_beat en reloj MONOTÓNICO; live_turns cuenta AssistantMessage.
        # last_beat = 0.0 hasta que arranca run(); la TUI cae a started_at mientras no haya señal.
        self.started_at: Optional[float] = None
        self.last_beat: float = 0.0
        self.live_turns: int = 0
        # Kill-switch cooperativo: si el operador aborta, el gate deniega TODA acción siguiente.
        self._aborted = False

    def _beat(self) -> None:
        """Marca actividad del SDK (última narración/tool/resultado). La TUI usa last_beat para saber
        que la orden sigue viva y NO disparar la auto-recuperación del lock (state.order_stale)."""
        self.last_beat = time.monotonic()

    def abort(self) -> None:
        """Aborta la orden en curso: a partir de aquí el gate deniega cualquier herramienta.
        Lo invoca el kill-switch de la TUI; complementa la cancelación del worker Textual."""
        self._aborted = True

    def _resolve_approval_mode(self, explicit: Optional[str]) -> str:
        """Resuelve el modo de supervisión: explícito > env ORCH_APPROVAL_MODE >
        scope.json constraints.approval_mode > 'critical'. Valor inválido => 'critical'."""
        cand = explicit or os.environ.get("ORCH_APPROVAL_MODE")
        if not cand:
            try:
                sc = json.loads((self.repo / "contracts" / "scope.json").read_text(encoding="utf-8"))
                cand = (sc.get("constraints", {}) or {}).get("approval_mode")
            except Exception:
                cand = None
        cand = str(cand or "critical").strip().lower()
        return cand if cand in ("full", "critical", "auto") else "critical"

    # ---- gate de permiso por acción (por tier de riesgo) ----------------------
    async def _gate(self, tool_name, tool_input, ctx):
        # Kill-switch del operador (TUI): una vez abortada la orden, se deniega TODO.
        if self._aborted:
            return PermissionResultDeny(message="Orden abortada por el operador (kill-switch de la TUI).")
        # Solo gateamos comandos de shell; el resto de tools las decide el modo de permiso.
        if tool_name != "Bash":
            return PermissionResultAllow()
        cmd = tool_input.get("command", "")
        tier, policy = R.classify_command(cmd)
        if policy == "auto":                      # safe / benigno -> sin fricción
            return PermissionResultAllow()
        # Modo de supervisión humana (config del operador, dentro de un engagement AUTORIZADO):
        #   auto      -> sin aprobación por acción (scope_guard/budget_guard siguen activos)
        #   critical  -> solo lo crítico (C2/implantes/msfvenom = policy 'dual') pide aprobación
        #   full      -> aprueba todo lo de riesgo (ask + dual)  [máxima supervisión]
        if self.approval_mode == "auto":
            return PermissionResultAllow()
        if self.approval_mode == "critical" and policy != "dual":
            return PermissionResultAllow()
        needed = 2 if policy == "dual" else 1     # critical (C2/implantes) = doble confirmación
        for i in range(needed):
            extra = "" if needed == 1 else f"  ·  confirmación {i + 1}/{needed}"
            summary = f"[{tier.upper()}] {_trim(cmd, 300)}{extra}"
            try:
                ok = await asyncio.wait_for(self.approve(summary), timeout=self.approval_timeout)
            except asyncio.TimeoutError:
                return PermissionResultDeny(
                    message="Sin respuesta del operador: acción denegada por timeout."
                )
            if not ok:
                return PermissionResultDeny(message="El operador denegó esta acción por Telegram.")
        return PermissionResultAllow()

    def _options(self):
        # El playbook del Orquestador (AGENTS.md) lo carga Claude Code como memoria del proyecto
        # vía CLAUDE.md (que importa @AGENTS.md) + setting_sources=["project"]. NO lo anexamos
        # aquí: hacerlo lo duplicaría en contexto. Este append solo añade lo del canal remoto.
        append = (
            "\n\n## Canal Telegram (operador remoto)\n"
            "Operas a través de un bot de Telegram. Sé conciso. Antes de cada fase anuncia "
            "en UNA frase qué vas a hacer y por qué (el operador lo ve como hito en vivo). "
            "Cuando un agente escriba un finding en contracts/engagement.json, fija `status` "
            "con exactitud (candidate/confirmed/exploited) y rellena `evidence` cuando lo "
            "verifiques: el bot distingue alerta real de ruido por esos campos. No "
            "auto-apruebes acciones que tocan el target."
        )
        # Localiza el binario `claude` explícitamente (systemd arranca con PATH mínimo).
        cli = os.environ.get("CLAUDE_CLI_PATH") or shutil.which("claude")
        opts = dict(
            cwd=str(self.repo),
            setting_sources=["project"],   # carga .claude/agents + hook scope_guard
            permission_mode="default",
            can_use_tool=self._gate,
            system_prompt={"type": "preset", "preset": "claude_code", "append": append},
            model=self.model,
            include_partial_messages=False,
        )
        if cli:
            opts["cli_path"] = cli
        # v1.4.0 — palancas de coste del Orquestador. `effort` y `max_budget_usd` son campos
        # NATIVOS del SDK (verificado en la doc oficial), pero se aplican de forma DEFENSIVA: si
        # la versión instalada no los acepta, se degradan (effort -> flag CLI `--effort`; el techo
        # USD se omite) sin romper la sesión. Se configuran por env (ORCH_EFFORT / ORCH_MAX_USD).
        if self.effort:
            opts["effort"] = self.effort
        if self.max_usd:
            opts["max_budget_usd"] = self.max_usd
        try:
            return ClaudeAgentOptions(**opts)
        except TypeError:
            eff = opts.pop("effort", None)
            opts.pop("max_budget_usd", None)
            if eff:
                opts["extra_args"] = {**(opts.get("extra_args") or {}), "--effort": str(eff)}
            try:
                return ClaudeAgentOptions(**opts)
            except TypeError:
                opts.pop("extra_args", None)
                return ClaudeAgentOptions(**opts)

    # ---- ejecución ------------------------------------------------------------
    async def run(self, task: str) -> str:
        self.started_at = self.last_beat = time.monotonic()   # arranque del reloj de vida de la orden
        if not SDK_OK:
            return await self._run_fallback(task)
        await self._scan(seed=True)   # baseline: no re-alertar lo ya existente
        try:
            async with ClaudeSDKClient(options=self._options()) as client:
                await client.query(task)
                async for msg in client.receive_response():
                    await self._handle(msg)
        except Exception as e:  # noqa: BLE001 - reportamos cualquier fallo al operador
            await self.emit(f"⚠️ Error del runner: {_trim(str(e), 300)}")
        return self._final

    async def _handle(self, msg):
        self._beat()   # cualquier mensaje del SDK = señal de vida (para el auto-timeout del lock)
        if isinstance(msg, AssistantMessage):
            self.live_turns += 1
            sub = self._subagents.get(getattr(msg, "parent_tool_use_id", None) or "")
            for b in msg.content:
                if isinstance(b, ToolUseBlock):
                    await self._on_tool(b)
                elif isinstance(b, TextBlock):
                    txt = b.text.strip()
                    if not txt:
                        continue
                    if sub:                       # narración de un subagente -> estado
                        await self._status(f"{sub}: {txt}")
                    else:                         # narración del Orquestador -> HITO
                        await self.emit(_trim(txt, 600))
            await self._scan()
        elif isinstance(msg, ResultMessage):
            self._final = (getattr(msg, "result", None) or "").strip()
            await self._scan()
            cost = msg.total_cost_usd
            # Telemetría para la TUI (aditivo; el bot no lo usa).
            if isinstance(cost, (int, float)):
                self.last_cost_usd = cost
            self.last_turns = getattr(msg, "num_turns", None)
            tail = f" · ${cost:.2f}" if isinstance(cost, (int, float)) and cost else ""
            flag = "⚠️ con errores" if getattr(msg, "is_error", False) else "✅"
            await self.emit(f"{flag} Completado · {msg.num_turns} turnos{tail}.")

    async def _on_tool(self, b: ToolUseBlock):
        if b.name == "Task":
            st = b.input.get("subagent_type") or "subagente"
            self._subagents[b.id] = st
            desc = b.input.get("description") or b.input.get("prompt", "")
            await self.emit(f"▶️ *{st}* — {_trim(desc, 140)}")
        elif b.name == "Bash":
            await self._status(f"🔧 {_trim(b.input.get('command', ''), 160)}")
        elif b.name in ("Write", "Edit", "MultiEdit"):
            await self._status(f"📝 {b.name} {Path(b.input.get('file_path', '')).name}")
        else:
            await self._status(f"🔧 {b.name}")

    async def _status(self, text: str):
        """Edición de estado con throttle para no saturar Telegram."""
        now = time.monotonic()
        if now - self._last_status < self.status_min_gap:
            return
        self._last_status = now
        await self.status(_trim(text, 180))

    async def _scan(self, seed: bool = False):
        eng = self.repo / "contracts" / "engagement.json"
        if not eng.exists():
            return
        try:
            mt = eng.stat().st_mtime
            if mt == self._eng_mtime:
                return
            self._eng_mtime = mt
            data = json.loads(eng.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for f in data.get("findings", []):
            fid = f.get("finding_id")
            if not fid:
                continue
            prev = self._seen.get(fid)
            status = f.get("status")
            self._seen[fid] = status
            if seed or prev == status:
                continue
            v = C.classify(f)
            if v.level in ("real", "watch"):
                await self.on_verdict(v, f)
        # Bus A2A: narra cada mensaje nuevo entre agentes (X -> Y). En seed solo los registra.
        for m in data.get("messages", []):
            mid = m.get("message_id")
            if not mid or mid in self._seen_msgs:
                continue
            self._seen_msgs.add(mid)
            if seed:
                continue
            frm = m.get("from_agent", "?")
            to = m.get("to_agent", "?")
            role = m.get("role", "")
            intent = next((p.get("text", "") for p in m.get("parts", [])
                           if p.get("kind") == "text" and p.get("text")), "")
            await self.emit(f"✉️ *{frm}* → *{to}* ({role}) {_trim(intent, 140)}".rstrip())

    async def _run_fallback(self, task: str) -> str:
        await self.emit("ℹ️ Agent SDK no disponible: ejecución sin streaming (degradada).")
        await self._scan(seed=True)
        claude = os.environ.get("CLAUDE_CLI_PATH") or shutil.which("claude") or "claude"
        prompt = ("Actúa como Orquestador siguiendo AGENTS.md. Lee contracts/scope.json. "
                  f"Tarea: {task}")
        args = [claude, "-p", prompt, "--permission-mode", "default", "--output-format", "text"]
        if self.model:
            args += ["--model", self.model]
        # effort por variable de entorno (segura: si el CLI no la reconoce, la ignora — al
        # contrario que un flag, que daría error). Replica la palanca de coste del modo SDK.
        env = dict(os.environ)
        if self.effort:
            env.setdefault("CLAUDE_CODE_EFFORT_LEVEL", self.effort)
        p = await asyncio.create_subprocess_exec(
            *args, cwd=str(self.repo), env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await p.communicate()
        await self._scan()
        self._final = out.decode("utf-8", "replace")
        return self._final
