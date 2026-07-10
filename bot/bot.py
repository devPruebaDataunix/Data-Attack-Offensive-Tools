#!/usr/bin/env python3
"""
Data Attack — Bot de Telegram (control remoto inteligente del entorno ofensivo).

Mando a distancia + dashboard de intel del framework de agentes. Solo el/los user-id de la
allowlist pueden usarlo.

Inteligente = sobre el Claude Agent SDK (bot/intel/runner.py):
  - lenguaje humano simple -> orden al Orquestador;
  - si falta/insuficiente el scope, PREGUNTA en vez de adivinar (bot/intel/scope.py);
  - resúmenes EN VIVO por hito mientras trabaja (streaming);
  - distingue ALERTA REAL de ruido de escáner (bot/intel/classify.py) y solo escala la real;
  - pide APROBACIÓN HUMANA por acción para comandos que tocan el target.

Config (bot/.env, ignorado por git):
    TELEGRAM_TOKEN=...
    ALLOWED_USER_ID=123,456
    REPO_DIR=/ruta/al/repo
    ORCH_MODEL=          # opcional: modelo del Orquestador (def.: claude-opus-4-8)
    ORCH_EFFORT=         # opcional: effort del Orquestador low|medium|high|xhigh|max (def.: medium)
    ORCH_MAX_USD=        # opcional: techo de coste por orden en USD; corta al alcanzarlo (def.: sin techo)
"""
import asyncio
import json
import logging
import os
import re
import sys
import time
from functools import wraps
from pathlib import Path
from uuid import uuid4

from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup,
                      BotCommand, BotCommandScopeChat)
from telegram.constants import ChatType
from telegram.error import BadRequest
from telegram.ext import (Application, CommandHandler, MessageHandler,
                          CallbackQueryHandler, ContextTypes, filters)

# El paquete intel (y la lógica pura de tui/state.py) viven junto a este fichero.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from intel import classify as clf       # noqa: E402
from intel import scope as scp           # noqa: E402
from intel.runner import AgentRunner, SDK_OK   # noqa: E402
from tui import state as S               # noqa: E402  (lógica pura compartida con la TUI; sin Textual)
from tui import actions as A             # noqa: E402  (mutadores del OPERADOR: lab scope, config; validados)
import tgfmt as F                        # noqa: E402  (capa de formato Telegram MarkdownV2, fuente única)
import botfmt as BF                      # noqa: E402  (presentación: datos state/intel -> MarkdownV2)

# ── Config ───────────────────────────────────────────────────────────────────
BOT_DIR = Path(__file__).resolve().parent


def _load_env():
    env = {}
    f = BOT_DIR / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


ENV = _load_env()
TOKEN = ENV.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_TOKEN", "")
ALLOWED = {int(x) for x in (ENV.get("ALLOWED_USER_ID") or os.environ.get("ALLOWED_USER_ID", "")).replace(" ", "").split(",") if x}
REPO_DIR = Path(ENV.get("REPO_DIR") or os.environ.get("REPO_DIR", BOT_DIR.parent))
ORCH_MODEL = ENV.get("ORCH_MODEL") or os.environ.get("ORCH_MODEL") or "claude-opus-4-8"
ORCH_EFFORT = ENV.get("ORCH_EFFORT") or os.environ.get("ORCH_EFFORT") or "medium"
_max_usd_raw = (ENV.get("ORCH_MAX_USD") or os.environ.get("ORCH_MAX_USD") or "").strip()
try:
    ORCH_MAX_USD = float(_max_usd_raw) if _max_usd_raw else None
except ValueError:
    ORCH_MAX_USD = None
# Modo de supervisión humana (full|critical|auto). None => el runner lo resuelve (scope/critical).
ORCH_APPROVAL_MODE = ENV.get("ORCH_APPROVAL_MODE") or os.environ.get("ORCH_APPROVAL_MODE") or None
PY = sys.executable or "python3"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[logging.FileHandler(BOT_DIR / "bot.log"), logging.StreamHandler()])
log = logging.getLogger("databot")


# ── Seguridad: allowlist de user-id ──────────────────────────────────────────
def authorized(func):
    @wraps(func)
    async def wrap(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id if update.effective_user else None
        if uid not in ALLOWED:
            log.warning("ACCESO DENEGADO uid=%s", uid)
            if update.effective_message:
                await update.effective_message.reply_text("⛔ No autorizado.")
            return
        log.info("cmd uid=%s: %s", uid, (update.effective_message.text if update.effective_message else "")[:120])
        return await func(update, ctx)
    return wrap


# Secuencias ANSI (color/charset de tput): hay que limpiarlas o Telegram muestra `[32m[OK]`
# crudo. Cubre CSI (\x1b[...m) y designación de charset (\x1b(B), que es lo que emite `tput sgr0`.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\([0-9A-Za-z]")


def _strip_ansi(s):
    return _ANSI_RE.sub("", s)


async def run(cmd, timeout=180):
    """Ejecuta un comando en REPO_DIR y devuelve (rc, salida sin códigos ANSI)."""
    p = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(REPO_DIR),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(p.communicate(), timeout=timeout)
        return p.returncode, _strip_ansi(out.decode("utf-8", "replace"))
    except asyncio.TimeoutError:
        p.kill()
        return 124, "⏱️ Timeout."


def _truncate_body(s, n=3900):
    """Recorta un CUERPO de mensaje largo con sufijo '… (recortado)'. NO es el 'clip' que colapsa
    espacios de state._clip/tgfmt (ese va sobre campos): esto solo capa el tamaño de un bloque grande."""
    return s if len(s) <= n else s[:n] + "\n… (recortado)"


# Cadencia del mini-dashboard EN VIVO de una orden (edición del mensaje de estado + chequeo de cuelgue).
ORDER_TICK_SECS = 4


def _order_line(order):
    """Estado en UNA línea (texto plano, sin markup Rich) de la orden en curso, para Telegram. Reutiliza
    la MISMA lógica que la barra de la TUI (state.order_status_line, plain=True) — un solo sitio que
    formatea; aquí solo sugerimos /kill como comando de recuperación en vez del Ctrl+K de la TUI."""
    runner = order["runner"]
    return S.order_status_line(
        order["task"], order["started"], time.monotonic(),
        turns=runner.live_turns, cost=runner.last_cost_usd, last_beat=runner.last_beat,
        plain=True, stale_hint="/kill")


# Referencias fuertes a las tareas en segundo plano (evita que el GC recolecte una tarea sin await).
_BG_TASKS: set = set()


def _spawn(coro):
    t = asyncio.create_task(coro)
    _BG_TASKS.add(t)
    t.add_done_callback(_BG_TASKS.discard)
    return t


# Red de seguridad: Telegram rechaza mensajes > 4096 caracteres (sea cual sea el emisor).
def _tg(s):
    s = s or ""
    if len(s) <= 4096:
        return s
    cut = s[:4080]
    # No cortar a mitad de un escape de MarkdownV2: un nº IMPAR de '\' colgantes al final = un escape
    # incompleto que haría rechazar el mensaje (→ fallback sin formato). Quita UNA para dejarlo par/válido.
    if (len(cut) - len(cut.rstrip("\\"))) % 2:
        cut = cut[:-1]
    return cut + "\n… (recortado)"


async def say(bot, chat_id, text, reply_markup=None, md=True):
    """Envía con Markdown; si el parser falla, reintenta en texto plano."""
    text = _tg(text)
    try:
        return await bot.send_message(chat_id, text, parse_mode="Markdown" if md else None,
                                      reply_markup=reply_markup, disable_web_page_preview=True)
    except BadRequest:
        return await bot.send_message(chat_id, text, reply_markup=reply_markup,
                                      disable_web_page_preview=True)


async def edit(msg, text, md=False):
    text = _tg(text)
    try:
        await msg.edit_text(text, parse_mode="Markdown" if md else None,
                            disable_web_page_preview=True)
    except BadRequest:
        pass  # "message is not modified" o error de markdown: lo ignoramos


# ── envío MarkdownV2 (capa tgfmt) ─────────────────────────────────────────────
# Los comandos nuevos/migrados construyen el mensaje con tgfmt (F.*) y lo mandan con estos helpers.
# Un solo escaper correcto en vez del Markdown legacy + fallback a plano (frágil). El fallback aquí es
# la RED DE SEGURIDAD: si aun así Telegram rechaza el parseo, se degrada a texto legible sin perder
# contenido (F.plain) en vez de fallar.
async def sayv2(bot, chat_id, md2_text, reply_markup=None):
    body = _tg(md2_text)
    try:
        return await bot.send_message(chat_id, body, parse_mode="MarkdownV2",
                                      reply_markup=reply_markup, disable_web_page_preview=True)
    except BadRequest:
        log.warning("MarkdownV2 rechazado; degrado a texto plano")
        return await bot.send_message(chat_id, F.plain(body), reply_markup=reply_markup,
                                      disable_web_page_preview=True)


async def editv2(msg, md2_text):
    body = _tg(md2_text)
    try:
        await msg.edit_text(body, parse_mode="MarkdownV2", disable_web_page_preview=True)
    except BadRequest as e:
        # "message is not modified" (mismo contenido) es esperado: ni se degrada ni se loguea. Ante un
        # parseo inválido, DEGRADAMOS a texto plano (F.plain, misma red de seguridad que sayv2) en vez de
        # dejar el mensaje sin actualizar: si no, el placeholder de /status·/health·/kb (que EDITAN un
        # "comprobando…") quedaría congelado y el usuario no vería el contenido. Con el escaper correcto
        # casi nunca se activa; es defensa en profundidad.
        if "not modified" in str(e).lower():
            return
        log.warning("MarkdownV2 rechazado en edición; degrado a texto plano: %s", e)
        try:
            await msg.edit_text(F.plain(body), disable_web_page_preview=True)
        except BadRequest as e2:
            log.warning("edición en texto plano también rechazada: %s", e2)


# ── Comandos básicos ─────────────────────────────────────────────────────────
@authorized
async def start(update, ctx):
    mode = "Agent SDK (streaming)" if SDK_OK else "claude -p (degradado)"
    welcome = F.card("Data Attack en línea", F.kv("motor", F.esc(mode)), icon="🛡️")
    await sayv2(ctx.bot, update.effective_chat.id, welcome + "\n\n" + BF.help_card())
    # Registra el menú «/» para ESTE chat autorizado (scope por-chat). Cubre el arranque en frío —una VM
    # recién instalada— donde en `_post_init` el bot aún no conocía el chat. Idempotente y best-effort.
    # SOLO en chats PRIVADOS: `@authorized` filtra por effective_user.id, pero el scope del menú se fija por
    # effective_chat.id — en un grupo, registrarlo expondría la lista de comandos a TODOS sus miembros (fuga
    # de superficie, aunque la ejecución siga bloqueada). En privado chat_id == user_id, así que es seguro.
    if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
        await _register_command_menu(ctx.bot, update.effective_chat.id)


@authorized
async def help_cmd(update, ctx):
    await sayv2(ctx.bot, update.effective_chat.id, BF.help_card())


async def _rag_stats():
    """Lee los dos RAG por subprocess (lecturas SQLite LIGERAS, sin venv/embedder). Devuelve
    (store, kb) — cada uno None si falla o está sin poblar, para que la tarjeta muestre un empty-state
    amable en vez de un error crudo. Mismo cableado que la TUI (app.py): --json / --stats --json."""
    store = kb = None
    try:
        _, out = await run([PY, "rag/query_vulns.py", "--query", "apache", "--json", "--limit", "1"],
                           timeout=40)
        store = S.parse_rag_store(out)
    except Exception as e:  # noqa: BLE001
        log.warning("RAG vulns stats no disponibles: %s", e)
    try:
        _, out = await run([PY, "rag/knowledge/query_kb.py", "--stats", "--json"], timeout=40)
        kb = S.parse_kb_stats(out)
    except Exception as e:  # noqa: BLE001
        log.warning("RAG conocimiento stats no disponibles: %s", e)
    return store, kb


@authorized
async def status(update, ctx):
    """Tarjeta de SALUD estructurada (A3): ✓/⚠ por componente + orden en curso. `full` (o `verify`/
    `toolchain`) corre el chequeo PROFUNDO del toolchain del host (deploy/verify.sh)."""
    args = [a.lower() for a in (ctx.args or [])]
    if args and args[0] in ("full", "verify", "toolchain", "deep"):
        msg = await update.message.reply_text("⏳ Chequeo profundo del toolchain…")
        _, out = await run(["bash", "deploy/verify.sh"], timeout=120)
        await edit(msg, "```\n" + _truncate_body(out, 3500) + "\n```", md=True)
        return
    msg = await ctx.bot.send_message(update.effective_chat.id, "🩺 Comprobando estado…")
    order = ctx.chat_data.get("order")
    scope = S.load_scope(REPO_DIR)
    count, _key = S.action_count(REPO_DIR)
    store, kb = await _rag_stats()
    card = BF.health_card(
        sdk_ok=SDK_OK, eng=S.load_engagement(REPO_DIR), scope=scope, cards=S.load_cards(REPO_DIR),
        actions=(count, S.max_actions(scope)), rag_store=store, kb=kb,
        model=ORCH_MODEL, effort=ORCH_EFFORT,
        order_line=_order_line(order) if order else None)
    await editv2(msg, card)


@authorized
async def kill(update, ctx):
    """Kill-switch: aborta la orden en curso. Cierra el GAP crítico — antes el bot marcaba 'running' pero
    NUNCA abortaba (mismo lock fantasma que la TUI tenía). abort() = deny cooperativo (la próxima acción
    del SDK se rechaza); cancelar la tarea = backup duro para desatascar un await colgado (aprobación/SDK)."""
    order = ctx.chat_data.get("order")
    if not order:
        await update.message.reply_text("No hay ninguna orden en curso. Usa /status para ver el estado.")
        return
    runner = order.get("runner")
    if runner is not None:
        runner.abort()
    t = order.get("aio_task")
    if t is not None and not t.done():
        t.cancel()
    # Liberación DURA del lock: aunque el finally del ejecutor no llegue a correr, el estado queda limpio.
    # El finally usa la identidad de `order` como token, así que no pisará una orden más nueva.
    ctx.chat_data.pop("order", None)
    # Precisión: abort() es un deny COOPERATIVO (se rechaza toda acción NUEVA); una acción ya lanzada
    # (p.ej. un nmap/sqlmap en curso) puede tardar en cortarse. No prometemos más de lo que garantiza.
    await update.message.reply_text(
        "⛔ Orden abortada: se deniega toda acción NUEVA. Una acción ya en curso puede tardar en cortarse.")


@authorized
async def health(update, ctx):
    # /health = alias de /status (A3: una sola tarjeta de salud consolidada).
    await status(update, ctx)


@authorized
async def agents(update, ctx):
    await sayv2(ctx.bot, update.effective_chat.id, BF.agents_card(S.load_cards(REPO_DIR)))


@authorized
async def agent(update, ctx):
    """Ficha de UN agente por nombre: /agent <nombre> (roster completo con /agents)."""
    chat_id = update.effective_chat.id
    if not ctx.args:
        await sayv2(ctx.bot, chat_id, F.card(
            "Uso: /agent <nombre>",
            F.esc("Ejemplo: /agent web-exploit · lista completa con /agents."), icon="👥"))
        return
    name = ctx.args[0].strip().lstrip("@").lower()
    card = next((c for c in S.load_cards(REPO_DIR) if str(c.get("name", "")).lower() == name), None)
    await sayv2(ctx.bot, chat_id, BF.agent_card(card))


@authorized
async def network(update, ctx):
    # /network (alias /hosts): frontera multi-host desde el blackboard (dato crudo -> MD2).
    await sayv2(ctx.bot, update.effective_chat.id, BF.network_card(S.load_engagement(REPO_DIR)))


@authorized
async def pivots(update, ctx):
    await sayv2(ctx.bot, update.effective_chat.id, BF.pivots_card(S.load_engagement(REPO_DIR)))


@authorized
async def creds(update, ctx):
    # Credenciales SIEMPRE referenciadas — creds_card jamás lee secret_ref ni el valor.
    await sayv2(ctx.bot, update.effective_chat.id, BF.creds_card(S.load_engagement(REPO_DIR)))


@authorized
async def evidence(update, ctx):
    """Artefactos y trazas por engagement: evidencia del engagement activo + engagements con carpeta en
    engagements/. Lectura pura (state.py); sin mutación."""
    await sayv2(ctx.bot, update.effective_chat.id,
                BF.evidence_card(S.load_engagement(REPO_DIR), S.engagement_dirs(REPO_DIR)))


@authorized
async def a2a(update, ctx):
    """Bus A2A. Sin arg: resumen + últimos mensajes. Con arg: detalle de un message_id (drill-down)."""
    chat_id = update.effective_chat.id
    eng = S.load_engagement(REPO_DIR)
    args = ctx.args or []
    if args:
        await sayv2(ctx.bot, chat_id, BF.a2a_detail_card(eng, args[0]))
    else:
        await sayv2(ctx.bot, chat_id, BF.a2a_card(eng, S.load_scope(REPO_DIR)))


@authorized
async def kb(update, ctx):
    """RAG de CONOCIMIENTO. Sin args: cobertura (Capa 1+2). Con args: busca técnicas Capa 1 (determinista,
    stdlib, sin venv/embedder — la fiable durante un engagement). La semántica (Capa 2) va aparte a futuro."""
    q = " ".join(ctx.args or []).strip()
    chat_id = update.effective_chat.id
    if not q:
        msg = await ctx.bot.send_message(chat_id, "📚 Leyendo el RAG de conocimiento…")
        _, out = await run([PY, "rag/knowledge/query_kb.py", "--stats", "--json"], timeout=40)
        await editv2(msg, BF.kb_stats_card(S.parse_kb_stats(out)))
        return
    msg = await ctx.bot.send_message(chat_id, "📚 Buscando técnicas…")
    _, out = await run([PY, "rag/knowledge/query_kb.py", "--query", q, "--json", "--limit", "8"], timeout=40)
    try:
        data = json.loads(out)
    except (ValueError, TypeError):
        data = None
    await editv2(msg, BF.kb_results_card(data, q))


@authorized
async def mode(update, ctx):
    """Supervisión humana (approval_mode). Sin arg: muestra actual + opciones. Con arg: la fija en bot/.env
    Y en la global viva (efectiva en la próxima orden). NO relaja las puertas duras (solo el gate de
    aprobación por acción; scope/presupuesto/no-daño se aplican siempre — CONSTITUTION §2)."""
    global ORCH_APPROVAL_MODE
    chat_id = update.effective_chat.id
    args = ctx.args or []
    if not args:
        await sayv2(ctx.bot, chat_id, BF.config_card(
            "Supervisión (approval_mode)", ORCH_APPROVAL_MODE or "", A.APPROVAL_MODES,
            "/mode full|critical|auto"))
        return
    val = args[0].lower()
    ok, msg = A.set_env_var(REPO_DIR, "ORCH_APPROVAL_MODE", val)
    if not ok:
        await sayv2(ctx.bot, chat_id, F.card("Valor inválido", F.esc(msg), icon="⚠️"))
        return
    ORCH_APPROVAL_MODE = val
    await sayv2(ctx.bot, chat_id, BF.config_set_card(
        "supervisión", f"{F.mode_emoji(val)} {F.esc(S.APPROVAL_MODE_ES.get(val, val))}"))


@authorized
async def model(update, ctx):
    """Modelo del Orquestador. Sin arg: actual + opciones. Con arg: lo fija (bot/.env + global viva)."""
    global ORCH_MODEL
    chat_id = update.effective_chat.id
    args = ctx.args or []
    if not args:
        await sayv2(ctx.bot, chat_id, BF.config_card(
            "Modelo del Orquestador", ORCH_MODEL, A.ORCH_MODELS, "/model <modelo>"))
        return
    val = args[0]
    ok, msg = A.set_env_var(REPO_DIR, "ORCH_MODEL", val)
    if not ok:
        await sayv2(ctx.bot, chat_id, F.card("Modelo inválido",
                    F.esc(msg) + F.esc(" Opciones: ") + " ".join(F.code(m) for m in A.ORCH_MODELS),
                    icon="⚠️"))
        return
    ORCH_MODEL = val
    await sayv2(ctx.bot, chat_id, BF.config_set_card("modelo", F.code(val)))


@authorized
async def effort(update, ctx):
    """Effort del Orquestador. Sin arg: actual + opciones. Con arg: lo fija (bot/.env + global viva)."""
    global ORCH_EFFORT
    chat_id = update.effective_chat.id
    args = ctx.args or []
    if not args:
        await sayv2(ctx.bot, chat_id, BF.config_card(
            "Effort del Orquestador", ORCH_EFFORT, A.EFFORTS, "/effort low|medium|high|xhigh|max"))
        return
    val = args[0].lower()
    ok, msg = A.set_env_var(REPO_DIR, "ORCH_EFFORT", val)
    if not ok:
        await sayv2(ctx.bot, chat_id, F.card("Effort inválido", F.esc(msg), icon="⚠️"))
        return
    ORCH_EFFORT = val
    await sayv2(ctx.bot, chat_id, BF.config_set_card("effort", F.code(val)))


@authorized
async def lab(update, ctx):
    """Arranca un lab: IP/CIDR/dominio → contracts/scope.json VALIDADO + lanza el engagement autónomo.
    SENSIBLE: NO relaja ninguna puerta (build_lab_scope rechaza CIDR amplio y FUERZA no-DoS/no-social/
    no-exfil). Nada muta hasta la confirmación (botón ✅): valida ahora, escribe+lanza al confirmar."""
    chat_id = update.effective_chat.id
    args = list(ctx.args or [])
    if not args:
        await sayv2(ctx.bot, chat_id, BF.lab_usage_card())
        return
    # El modo de supervisión es opcional (último token si es válido); el resto son objetivos.
    mode = ORCH_APPROVAL_MODE or "auto"
    if args and args[-1].lower() in ("full", "critical", "auto"):
        mode = args.pop().lower()
    # Objetivos separados por ESPACIO (forma natural en Telegram) o coma: los unimos con coma, que es como
    # classify_targets divide. Así `/lab 10.0.0.5 10.0.0.6` y `/lab 10.0.0.5,10.0.0.6` funcionan igual.
    targets = ",".join(args)
    ok, res = A.build_lab_scope(targets, "", mode, base=S.load_scope(REPO_DIR))   # valida, NO escribe
    if not ok:
        await sayv2(ctx.bot, chat_id, F.card("Lab no válido", F.esc(str(res)), icon="⚠️"))
        return
    ctx.chat_data["pending_lab"] = {"targets": targets, "mode": mode, "eid": res["engagement_id"]}
    kbd = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Fijar y lanzar", callback_data="lab_run"),
        InlineKeyboardButton("✖️ Cancelar", callback_data="lab_cancel")]])
    await sayv2(ctx.bot, chat_id, BF.lab_confirm_card(res, mode), reply_markup=kbd)


@authorized
async def triage(update, ctx):
    q = " ".join(ctx.args)
    if not q:
        await update.message.reply_text("Uso: /triage `<producto> [versión]`", parse_mode="Markdown")
        return
    msg = await update.message.reply_text(f"🔎 Triage de *{q}*…", parse_mode="Markdown")
    rc, out = await run([PY, "rag/query_vulns.py", "--query", q, "--json", "--limit", "5"], timeout=60)
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        await edit(msg, "```\n" + _truncate_body(out) + "\n```", md=True)
        return
    lines = [f"*Triage — {q}*  (store {data['store'].get('kev_version', '?')})"]
    for r in data.get("results", []):
        flags = []
        if r["in_kev"]:
            flags.append("KEV")
        if r["exploit_public"]:
            flags.append("EXPLOIT")
        msf = r["msf_modules"][0]["module"] if r.get("msf_modules") else None
        lines.append(f"• `{r['cve']}` {r['severity'].upper()} CVSS={r['cvss']} EPSS={r['epss']} {' '.join(flags)}")
        if msf:
            lines.append(f"    MSF: `{msf}`")
        if r.get("nuclei_templates"):
            lines.append(f"    Nuclei: `{r['nuclei_templates'][0]}`")
    await edit(msg, _truncate_body("\n".join(lines)), md=True)


@authorized
async def cve(update, ctx):
    chat_id = update.effective_chat.id
    if not ctx.args:
        await sayv2(ctx.bot, chat_id,
                    F.card("Uso", F.esc("/cve <CVE-id> — p. ej. ") + F.code("CVE-2021-44228"), icon="ℹ️"))
        return
    rc, out = await run([PY, "rag/query_vulns.py", "--query", ctx.args[0], "--json", "--limit", "1"], timeout=60)
    try:
        res = json.loads(out).get("results", [])
    except json.JSONDecodeError:
        res = []
    await sayv2(ctx.bot, chat_id, BF.cve_card(res[0] if res else None))


@authorized
async def refresh(update, ctx):
    await update.message.reply_text("🔄 Refrescando el RAG en segundo plano… te aviso al terminar.")

    async def _job():
        rc, out = await run([PY, "rag/refresh.py", "--epss-all"], timeout=1800)
        await ctx.bot.send_message(update.effective_chat.id,
                                   "✅ RAG actualizado." if rc == 0 else "⚠️ Refresh con errores.")
    _spawn(_job())   # ref fuerte (evita que el GC recolecte la tarea de fondo antes de terminar)


@authorized
async def findings(update, ctx):
    eng = S.load_engagement(REPO_DIR)                       # lector único (state.py)
    grp = clf.scan(eng.get("findings", []) or [])
    await sayv2(ctx.bot, update.effective_chat.id, BF.findings_card(grp, eng))


@authorized
async def report(update, ctx):
    reports = sorted((REPO_DIR / "report").glob("INFORME-*.md"))
    if not reports:
        await update.message.reply_text("No hay informe generado. Pídemelo en lenguaje normal (p.ej. \"genera el informe\").")
        return
    latest = reports[-1]
    await update.message.reply_document(document=latest.open("rb"), filename=latest.name)


@authorized
async def scope(update, ctx):
    await sayv2(ctx.bot, update.effective_chat.id, BF.scope_card(S.load_scope(REPO_DIR)))


# ── Lenguaje natural -> Orquestador (con pregunta de scope y confirmación) ────
@authorized
async def freetext(update, ctx):
    text = update.message.text.strip()

    # ¿Estábamos esperando que el operador aclarara el alcance?
    if ctx.chat_data.get("awaiting_scope"):
        base = ctx.chat_data.pop("awaiting_scope")
        await _confirm(update, ctx, f"{base}\n\n[Aclaración de alcance del operador]: {text}")
        return

    scope_cfg = scp.load_scope(REPO_DIR)
    question = scp.scope_question(text, scope_cfg)
    if question:
        ctx.chat_data["awaiting_scope"] = text
        await say(ctx.bot, update.effective_chat.id, "❓ " + question)
        return

    await _confirm(update, ctx, text)


async def _confirm(update, ctx, task):
    ctx.chat_data["pending_task"] = task
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Ejecutar", callback_data="run"),
        InlineKeyboardButton("✖️ Cancelar", callback_data="cancel")]])
    await say(ctx.bot, update.effective_chat.id,
              f"*Orden al Orquestador:*\n> {_truncate_body(task, 400)}\n\n¿Ejecutar?", reply_markup=kb)


# ── Ejecución con streaming + aprobación por acción + alertas ─────────────────
async def _ask_approval(ctx, chat_id, summary):
    """Pide OK humano para una acción que toca el target. Devuelve True/False."""
    fut = asyncio.get_running_loop().create_future()
    aid = uuid4().hex[:8]
    ctx.application.bot_data.setdefault("approvals", {})[aid] = fut
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Autorizar", callback_data=f"appr:{aid}:1"),
        InlineKeyboardButton("⛔ Denegar", callback_data=f"appr:{aid}:0")]])
    safe = summary.replace("`", "'")
    await say(ctx.bot, chat_id,
              f"⚠️ *Acción que toca el target* — necesito tu OK:\n```\n{safe}\n```",
              reply_markup=kb)
    try:
        return await fut
    finally:
        ctx.application.bot_data.get("approvals", {}).pop(aid, None)


async def _alert(ctx, chat_id, v: clf.Verdict):
    if v.level == "real":
        head = f"🔴 *EVIDENCIA REAL* · `{v.finding_id}` [{v.severity.upper()}]"
    else:
        head = f"🟠 *Potencial (sin verificar)* · `{v.finding_id}` [{v.severity.upper()}]"
    body = f"{head}\n*{v.title}* → `{v.target}`\n_{v.reason}_"
    if v.summary:
        body += "\n\n" + v.summary
    await say(ctx.bot, chat_id, _truncate_body(body, 3500))


async def _execute(ctx, chat_id, task):
    if ctx.chat_data.get("order"):
        await ctx.bot.send_message(
            chat_id, "⏳ Ya hay una orden en curso. Mira su estado con /status o abórtala con /kill.")
        return

    # ── Arranque (ANTES de fijar el lock) ─────────────────────────────────────────────────────────
    # _execute corre en segundo plano (fire-and-forget), así que una excepción AQUÍ (Telegram caído,
    # el runner no construye) moriría en silencio dejando al operador con "🚀 Lanzando…" para siempre.
    # La blindamos: se reporta al chat y se sale. El lock se fija AL FINAL, así que si esto falla no se
    # filtra ningún lock (no hay que limpiar nada).
    try:
        status_msg = await ctx.bot.send_message(chat_id, "⏳ Orquestador trabajando…")

        async def emit(text):
            await say(ctx.bot, chat_id, text)

        async def status_upd(text):
            order["last_tool"] = text      # el ticker lo incorpora al mini-dashboard (un solo mensaje)

        async def approve(summary):
            return await _ask_approval(ctx, chat_id, summary)

        async def on_verdict(v, f):
            await _alert(ctx, chat_id, v)

        runner = AgentRunner(REPO_DIR, emit, status_upd, approve, on_verdict, model=ORCH_MODEL,
                             effort=ORCH_EFFORT, max_usd=ORCH_MAX_USD, approval_mode=ORCH_APPROVAL_MODE)
        # El `order` es a la vez el estado observable (lo ven /status y /kill) y el TOKEN del lock: su
        # identidad distingue esta orden de una posterior en el guard anti-carrera del finally.
        order = {
            "runner": runner, "task": task, "started": time.monotonic(),
            "aio_task": asyncio.current_task(), "last_tool": "",
        }
        ctx.chat_data["order"] = order
    except Exception as e:  # noqa: BLE001 - fallo de arranque: repórtalo, no lo tragues en la tarea
        log.exception("execute-setup")
        try:
            await ctx.bot.send_message(chat_id, f"⚠️ No pude arrancar la orden: {e}")
        except Exception:  # noqa: BLE001
            pass
        return

    async def _ticker():
        """Refresca el mensaje de estado (elapsed/turnos/coste + última tool) y AUTO-RECUPERA el lock si
        el SDK lleva demasiado sin dar señal (cuelgue silencioso — el caso real de tokenaso). El aviso de
        inactividad se envía DESDE AQUÍ (antes de cancelar), no dentro del `except CancelledError` del
        ejecutor: así no puede perderse por una carrera de cancelaciones."""
        while True:
            try:
                await asyncio.sleep(ORDER_TICK_SECS)
                tail = f"\n🔧 {_truncate_body(order['last_tool'], 160)}" if order.get("last_tool") else ""
                await edit(status_msg, "⏳ " + _order_line(order) + tail)
                if S.order_stale(order["started"], runner.last_beat, time.monotonic()):
                    try:
                        await ctx.bot.send_message(
                            chat_id, "⚠️ Orden liberada por inactividad (sin señal del SDK). "
                                     "Se deniega toda acción NUEVA.")
                    except Exception:  # noqa: BLE001 - el aviso es best-effort; nunca bloquea la recuperación
                        pass
                    runner.abort()
                    order["aio_task"].cancel()
                    return
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - el ticker es cosmético; nunca debe tumbar la orden
                log.debug("order ticker", exc_info=True)

    ticker = _spawn(_ticker())
    final = None
    try:
        final = await runner.run(task)
    except Exception as e:  # noqa: BLE001 (CancelledError, BaseException, propaga: el finally limpia el lock)
        log.exception("runner")
        final = f"⚠️ Error: {e}"
    finally:
        ticker.cancel()
        if ctx.chat_data.get("order") is order:   # token guard: no pisar una orden más nueva
            ctx.chat_data.pop("order", None)
    if final:
        await say(ctx.bot, chat_id, "🧾 " + _truncate_body(final, 3500))


@authorized
async def on_button(update, ctx):
    q = update.callback_query
    await q.answer()
    data = q.data or ""

    if data.startswith("appr:"):
        _, aid, val = data.split(":")
        fut = ctx.application.bot_data.get("approvals", {}).get(aid)
        if fut and not fut.done():
            fut.set_result(val == "1")
            await edit(q.message, "✅ Autorizado." if val == "1" else "⛔ Denegado.")
        else:
            # El future ya no está: la orden terminó/se abortó (p.ej. /kill) o la solicitud expiró.
            # NO afirmar "Autorizado" (sería engañoso: no se ejecutará nada).
            await edit(q.message, "⏱️ Esa solicitud ya no está activa (orden terminada/abortada o expirada).")
        return

    if data == "cancel":
        ctx.chat_data.pop("pending_task", None)
        await edit(q.message, "Cancelado.")
        return

    if data == "lab_cancel":
        ctx.chat_data.pop("pending_lab", None)
        await edit(q.message, "Cancelado. No se ha tocado el scope.")
        return

    if data == "lab_run":
        pend = ctx.chat_data.pop("pending_lab", None)
        if not pend:
            await edit(q.message, "No hay ningún lab pendiente de confirmar.")
            return
        if ctx.chat_data.get("order"):
            await edit(q.message, "⏳ Ya hay una orden en curso; abórtala con /kill antes de lanzar otra.")
            return
        # Recién AQUÍ se muta: escribe scope.json (atómico + backup .bak) y lanza. build_lab_scope ya
        # validó; set_lab_scope re-valida y no relaja ninguna puerta.
        ok, msg = A.set_lab_scope(REPO_DIR, pend["targets"], pend["eid"], pend["mode"])
        if not ok:
            await edit(q.message, f"⚠️ No pude fijar el scope: {msg}")
            return
        await edit(q.message, "🧪 Scope fijado (backup en scope.json.bak). 🚀 Lanzando el lab…")
        _spawn(_execute(ctx, q.message.chat_id, A.compose_lab_run(pend["targets"])))
        return

    if data == "run":
        task = ctx.chat_data.pop("pending_task", None)
        if not task:
            await edit(q.message, "No hay orden pendiente.")
            return
        if ctx.chat_data.get("order"):
            await edit(q.message, "⏳ Ya hay una orden en curso; abórtala con /kill antes de lanzar otra.")
            return
        await edit(q.message, "🚀 Lanzando al Orquestador…")
        # En segundo plano para que /kill (u otra actualización) pueda correr y CANCELAR esta orden.
        _spawn(_execute(ctx, q.message.chat_id, task))
        return


async def on_error(update, ctx):
    log.error("Error: %s", ctx.error)


async def _register_command_menu(bot, chat_id) -> bool:
    """Registra el menú nativo «/» de Telegram SOLO para un chat de la allowlist (scope POR-CHAT, nunca el
    ámbito por defecto/global). OPSEC: la superficie de comandos de una herramienta ofensiva no debe
    mostrarse a un desconocido que encuentre el bot — con el scope por-chat, quien NO está en la allowlist
    ve un menú VACÍO (aunque la ejecución ya estaba bloqueada por @authorized, esto evita la FUGA de la
    lista de comandos). Best-effort: si Telegram falla (red/rate-limit/chat aún no conocido), se loguea y
    se sigue — el menú es descubrimiento, no una puerta. La lista curada vive en botfmt.command_menu."""
    try:
        cmds = [BotCommand(c, d) for c, d in BF.command_menu()]
        await bot.set_my_commands(cmds, scope=BotCommandScopeChat(chat_id=chat_id))
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("No pude registrar el menú para el chat %s: %s", chat_id, e)
        return False


async def _post_init(app: Application):
    """Al arrancar registra el menú para los chats de la allowlist YA conocidos (los que han escrito antes;
    `BotCommandScopeChat` exige que el bot haya interactuado con el chat). Un chat nunca visto se registra
    en su primer `/start` (ver `start`). NUNCA se toca el ámbito global -> un desconocido ve el menú vacío."""
    n = sum([await _register_command_menu(app.bot, uid) for uid in ALLOWED])
    log.info("Menú de comandos registrado en %d/%d chat(s) de la allowlist.", n, len(ALLOWED))


def _print_banner():
    """Banner de la herramienta en el arranque (consola)."""
    try:
        for _n in ("data-attack.txt", "dataunix.txt"):
            _f = REPO_DIR / "assets" / "banners" / _n
            if _f.exists():
                print(_f.read_text(encoding="utf-8"))
        print("  Offensive Tools · pentest autorizado\n")
    except Exception:  # noqa: BLE001
        pass


def main():
    _print_banner()
    if not TOKEN or not ALLOWED:
        raise SystemExit("Falta TELEGRAM_TOKEN o ALLOWED_USER_ID en bot/.env")
    app = Application.builder().token(TOKEN).concurrent_updates(True).post_init(_post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("kill", kill))
    app.add_handler(CommandHandler("abort", kill))
    app.add_handler(CommandHandler("health", health))
    app.add_handler(CommandHandler("agents", agents))
    app.add_handler(CommandHandler("agent", agent))
    app.add_handler(CommandHandler("network", network))
    app.add_handler(CommandHandler("hosts", network))
    app.add_handler(CommandHandler("pivots", pivots))
    app.add_handler(CommandHandler("creds", creds))
    app.add_handler(CommandHandler("a2a", a2a))
    app.add_handler(CommandHandler("evidence", evidence))
    app.add_handler(CommandHandler("kb", kb))
    app.add_handler(CommandHandler("lab", lab))
    app.add_handler(CommandHandler("mode", mode))
    app.add_handler(CommandHandler("model", model))
    app.add_handler(CommandHandler("effort", effort))
    app.add_handler(CommandHandler("triage", triage))
    app.add_handler(CommandHandler("cve", cve))
    app.add_handler(CommandHandler("refresh", refresh))
    app.add_handler(CommandHandler("findings", findings))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("scope", scope))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, freetext))
    app.add_error_handler(on_error)
    log.info("Bot iniciado. Allowlist: %s · SDK=%s", ALLOWED, SDK_OK)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
