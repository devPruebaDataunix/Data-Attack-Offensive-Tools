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
import re
import shutil
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

from . import classify as C

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

# Comandos/herramientas que tocan al objetivo -> requieren confirmación humana por acción.
OFFENSIVE = re.compile(
    r"\b(nmap|masscan|rustscan|naabu|nuclei|sqlmap|msfconsole|msfvenom|msfcli|"
    r"netexec|nxc|crackmapexec|cme|secretsdump|psexec|wmiexec|smbexec|atexec|"
    r"evil-winrm|ffuf|feroxbuster|gobuster|dirb|wfuzz|hydra|medusa|patator|"
    r"wpscan|nikto|responder|ntlmrelayx|sliver|metasploit|amass|httpx|katana|"
    r"enum4linux|ldapsearch|kerbrute|certipy|bloodhound|getuserspns|getnpusers)\b",
    re.I,
)

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
    ):
        self.repo = Path(repo)
        self.emit = emit              # mensaje nuevo: hito importante
        self.status = status          # edición del mensaje de estado (throttled)
        self.approve = approve        # pide confirmación humana -> True/False
        self.on_verdict = on_verdict  # alerta de finding clasificado
        self.model = model
        self.approval_timeout = approval_timeout
        self.status_min_gap = status_min_gap

        self._subagents: dict[str, str] = {}   # tool_use_id (Task) -> subagent_type
        self._seen: dict[str, str] = {}        # finding_id -> último status visto
        self._eng_mtime = 0.0
        self._last_status = 0.0
        self._final = ""

    # ---- gate de permiso por acción ------------------------------------------
    async def _gate(self, tool_name, tool_input, ctx):
        cmd = tool_input.get("command", "") if tool_name == "Bash" else ""
        if tool_name == "Bash" and OFFENSIVE.search(cmd):
            try:
                ok = await asyncio.wait_for(
                    self.approve(_trim(cmd, 320)), timeout=self.approval_timeout
                )
            except asyncio.TimeoutError:
                return PermissionResultDeny(
                    message="Sin respuesta del operador: acción denegada por timeout."
                )
            if ok:
                return PermissionResultAllow()
            return PermissionResultDeny(message="El operador denegó esta acción por Telegram.")
        return PermissionResultAllow()

    def _options(self):
        append = ""
        persona = self.repo / "AGENTS.md"
        if persona.exists():
            append = persona.read_text(encoding="utf-8")
        append += (
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
        return ClaudeAgentOptions(**opts)

    # ---- ejecución ------------------------------------------------------------
    async def run(self, task: str) -> str:
        if not SDK_OK:
            return await self._run_fallback(task)
        await self._scan_findings(seed=True)   # baseline: no re-alertar lo ya existente
        try:
            async with ClaudeSDKClient(options=self._options()) as client:
                await client.query(task)
                async for msg in client.receive_response():
                    await self._handle(msg)
        except Exception as e:  # noqa: BLE001 - reportamos cualquier fallo al operador
            await self.emit(f"⚠️ Error del runner: {_trim(str(e), 300)}")
        return self._final

    async def _handle(self, msg):
        if isinstance(msg, AssistantMessage):
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
            await self._scan_findings()
        elif isinstance(msg, ResultMessage):
            self._final = (getattr(msg, "result", None) or "").strip()
            await self._scan_findings()
            cost = msg.total_cost_usd
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

    async def _scan_findings(self, seed: bool = False):
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

    async def _run_fallback(self, task: str) -> str:
        await self.emit("ℹ️ Agent SDK no disponible: ejecución sin streaming (degradada).")
        await self._scan_findings(seed=True)
        claude = shutil.which("claude") or "claude"
        prompt = ("Actúa como Orquestador siguiendo AGENTS.md. Lee contracts/scope.json. "
                  f"Tarea: {task}")
        p = await asyncio.create_subprocess_exec(
            claude, "-p", prompt, "--permission-mode", "default", "--output-format", "text",
            cwd=str(self.repo),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await p.communicate()
        await self._scan_findings()
        self._final = out.decode("utf-8", "replace")
        return self._final
