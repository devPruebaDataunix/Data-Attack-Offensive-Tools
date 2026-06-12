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
    ORCH_MODEL=          # opcional: fuerza un modelo para el Orquestador (def.: el del proyecto)
"""
import asyncio
import json
import logging
import os
import sys
from functools import wraps
from pathlib import Path
from uuid import uuid4

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (Application, CommandHandler, MessageHandler,
                          CallbackQueryHandler, ContextTypes, filters)

# El paquete intel vive junto a este fichero.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from intel import classify as clf       # noqa: E402
from intel import scope as scp           # noqa: E402
from intel.runner import AgentRunner, SDK_OK   # noqa: E402

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
ORCH_MODEL = ENV.get("ORCH_MODEL") or os.environ.get("ORCH_MODEL") or None
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


async def run(cmd, timeout=180):
    """Ejecuta un comando en REPO_DIR y devuelve (rc, salida)."""
    p = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(REPO_DIR),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(p.communicate(), timeout=timeout)
        return p.returncode, out.decode("utf-8", "replace")
    except asyncio.TimeoutError:
        p.kill()
        return 124, "⏱️ Timeout."


def clip(s, n=3900):
    return s if len(s) <= n else s[:n] + "\n… (recortado)"


async def say(bot, chat_id, text, reply_markup=None, md=True):
    """Envía con Markdown; si el parser falla, reintenta en texto plano."""
    try:
        return await bot.send_message(chat_id, text, parse_mode="Markdown" if md else None,
                                      reply_markup=reply_markup, disable_web_page_preview=True)
    except BadRequest:
        return await bot.send_message(chat_id, text, reply_markup=reply_markup,
                                      disable_web_page_preview=True)


async def edit(msg, text, md=False):
    try:
        await msg.edit_text(text, parse_mode="Markdown" if md else None,
                            disable_web_page_preview=True)
    except BadRequest:
        pass  # "message is not modified" o error de markdown: lo ignoramos


# ── Comandos básicos ─────────────────────────────────────────────────────────
HELP = (
    "*Data Attack — control inteligente*\n"
    "Háblame en lenguaje normal: _\"haz recon de app.cliente.com\"_, _\"prioriza los CVE de "
    "ese Apache\"_, _\"genera el informe\"_. Te pido confirmación, te aviso por hito en vivo, "
    "y solo escalo las alertas reales.\n\n"
    "/status — salud del sistema y del RAG\n"
    "/health — versiones del toolchain\n"
    "/agents — lista de agentes\n"
    "/triage `<producto> [versión]` — CVEs priorizados (KEV/MSF/CVSS)\n"
    "/cve `<CVE-id>` — detalle de un CVE\n"
    "/refresh — actualiza el RAG (en segundo plano)\n"
    "/findings — hallazgos clasificados (real / vigilar / ruido)\n"
    "/report — genera y envía el informe\n"
    "/scope — muestra el alcance actual\n"
)


@authorized
async def start(update, ctx):
    mode = "Agent SDK (streaming)" if SDK_OK else "claude -p (degradado)"
    await update.message.reply_text(f"🛡️ *Data Attack* en línea — motor: {mode}.\n\n" + HELP,
                                    parse_mode="Markdown")


@authorized
async def help_cmd(update, ctx):
    await update.message.reply_text(HELP, parse_mode="Markdown")


@authorized
async def status(update, ctx):
    msg = await update.message.reply_text("⏳ Comprobando…")
    rc, out = await run(["bash", "deploy/verify.sh"], timeout=120)
    await edit(msg, "```\n" + clip(out, 3500) + "\n```", md=True)


@authorized
async def health(update, ctx):
    await status(update, ctx)


@authorized
async def agents(update, ctx):
    files = sorted((REPO_DIR / ".claude" / "agents").rglob("*.md"))
    names = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("name:"):
                names.append(line.split(":", 1)[1].strip())
                break
    await update.message.reply_text(f"*{len(names)} agentes:*\n" + ", ".join(names), parse_mode="Markdown")


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
        await edit(msg, "```\n" + clip(out) + "\n```", md=True)
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
    await edit(msg, clip("\n".join(lines)), md=True)


@authorized
async def cve(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Uso: /cve `<CVE-id>`", parse_mode="Markdown")
        return
    cid = ctx.args[0]
    rc, out = await run([PY, "rag/query_vulns.py", "--query", cid, "--json", "--limit", "1"], timeout=60)
    try:
        res = json.loads(out).get("results", [])
    except json.JSONDecodeError:
        res = []
    if not res:
        await update.message.reply_text(f"Sin datos para `{cid}` en el RAG.", parse_mode="Markdown")
        return
    await update.message.reply_text(clip("```json\n" + json.dumps(res[0], indent=1, ensure_ascii=False) + "\n```"), parse_mode="Markdown")


@authorized
async def refresh(update, ctx):
    await update.message.reply_text("🔄 Refrescando el RAG en segundo plano… te aviso al terminar.")

    async def _job():
        rc, out = await run([PY, "rag/refresh.py", "--epss-all"], timeout=1800)
        await ctx.bot.send_message(update.effective_chat.id,
                                   "✅ RAG actualizado." if rc == 0 else "⚠️ Refresh con errores.")
    asyncio.create_task(_job())


@authorized
async def findings(update, ctx):
    eng = REPO_DIR / "contracts" / "engagement.json"
    if not eng.exists():
        await update.message.reply_text("No hay engagement activo.")
        return
    d = json.loads(eng.read_text(encoding="utf-8"))
    grp = clf.scan(d.get("findings", []))
    lines = [f"*Engagement {d.get('engagement_id', '?')}* — fase {d.get('phase', '?')}",
             f"🔴 reales: {len(grp['real'])}  🟠 vigilar: {len(grp['watch'])}  🔇 ruido: {len(grp['noise'])}"]
    for v in grp["real"][:6]:
        lines.append(f"🔴 `{v.finding_id}` [{v.severity.upper()}] {v.title[:60]} → {v.target}")
    for v in grp["watch"][:6]:
        lines.append(f"🟠 `{v.finding_id}` [{v.severity.upper()}] {v.title[:60]}")
    await update.message.reply_text(clip("\n".join(lines)), parse_mode="Markdown")


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
    d = scp.load_scope(REPO_DIR)
    if not d:
        await update.message.reply_text("⚠️ No hay `contracts/scope.json`. Defínelo antes de operar.")
        return
    ins = d.get("in_scope", {})
    await update.message.reply_text(
        f"*Scope* — {d.get('client', d.get('engagement_id', '?'))}\n"
        f"dominios: `{', '.join(ins.get('domains', []) or ['—'])}`\n"
        f"ips/cidr: `{', '.join((ins.get('ips', []) or []) + (ins.get('cidrs', []) or []) or ['—'])}`",
        parse_mode="Markdown")


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
              f"*Orden al Orquestador:*\n> {clip(task, 400)}\n\n¿Ejecutar?", reply_markup=kb)


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
    await say(ctx.bot, chat_id, clip(body, 3500))


async def _execute(ctx, chat_id, task):
    if ctx.chat_data.get("running"):
        await ctx.bot.send_message(chat_id, "⏳ Ya hay una orden en curso; espera a que termine.")
        return
    ctx.chat_data["running"] = True
    status_msg = await ctx.bot.send_message(chat_id, "⏳ Orquestador trabajando…")

    async def emit(text):
        await say(ctx.bot, chat_id, text)

    async def status_upd(text):
        await edit(status_msg, "⏳ " + text)

    async def approve(summary):
        return await _ask_approval(ctx, chat_id, summary)

    async def on_verdict(v, f):
        await _alert(ctx, chat_id, v)

    runner = AgentRunner(REPO_DIR, emit, status_upd, approve, on_verdict, model=ORCH_MODEL)
    try:
        final = await runner.run(task)
    except Exception as e:  # noqa: BLE001
        log.exception("runner")
        final = f"⚠️ Error: {e}"
    finally:
        ctx.chat_data["running"] = False
    if final:
        await say(ctx.bot, chat_id, "🧾 " + clip(final, 3500))


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
        return

    if data == "cancel":
        ctx.chat_data.pop("pending_task", None)
        await edit(q.message, "Cancelado.")
        return

    if data == "run":
        task = ctx.chat_data.pop("pending_task", None)
        if not task:
            await edit(q.message, "No hay orden pendiente.")
            return
        await edit(q.message, "🚀 Lanzando al Orquestador…")
        await _execute(ctx, q.message.chat_id, task)
        return


async def on_error(update, ctx):
    log.error("Error: %s", ctx.error)


def main():
    if not TOKEN or not ALLOWED:
        raise SystemExit("Falta TELEGRAM_TOKEN o ALLOWED_USER_ID en bot/.env")
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("health", health))
    app.add_handler(CommandHandler("agents", agents))
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
