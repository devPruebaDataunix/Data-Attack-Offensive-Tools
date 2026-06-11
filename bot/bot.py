#!/usr/bin/env python3
"""
Data Attack — Bot de Telegram (control remoto del entorno ofensivo).

Mando a distancia + dashboard de intel del framework de agentes. Solo el/los user-id de la
allowlist pueden usarlo. Las tareas de intel (triage/cve/health) corren local y seguras; las
órdenes al Orquestador piden confirmación y corren con permisos por defecto (las acciones que
tocan el target se gestionan supervisadas en terminal/GUI — ver bot/README.md).

Config (bot/.env, ignorado por git):
    TELEGRAM_TOKEN=...
    ALLOWED_USER_ID=123,456
    REPO_DIR=/ruta/al/repo
"""
import asyncio
import json
import logging
import os
import subprocess
from functools import wraps
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, MessageHandler,
                          CallbackQueryHandler, ContextTypes, filters)

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

# ── Comandos básicos ─────────────────────────────────────────────────────────
HELP = (
    "*Data Attack — control*\n"
    "/status — salud del sistema y del RAG\n"
    "/health — versiones del toolchain\n"
    "/agents — lista de agentes\n"
    "/triage `<producto> [versión]` — CVEs priorizados (KEV/MSF/CVSS)\n"
    "/cve `<CVE-id>` — detalle de un CVE\n"
    "/refresh — actualiza el RAG (en segundo plano)\n"
    "/findings — resumen de hallazgos del engagement\n"
    "/report — genera y envía el informe\n"
    "/scope — muestra el alcance actual\n"
    "_Texto libre_ → orden al Orquestador (pide confirmación)\n"
)

@authorized
async def start(update, ctx):
    await update.message.reply_text("🛡️ *Data Attack* en línea.\n\n" + HELP, parse_mode="Markdown")

@authorized
async def help_cmd(update, ctx):
    await update.message.reply_text(HELP, parse_mode="Markdown")

@authorized
async def status(update, ctx):
    msg = await update.message.reply_text("⏳ Comprobando…")
    rc, out = await run(["bash", "deploy/verify.sh"], timeout=120)
    await msg.edit_text("```\n" + clip(out, 3500) + "\n```", parse_mode="Markdown")

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
                names.append(line.split(":", 1)[1].strip()); break
    await update.message.reply_text(f"*{len(names)} agentes:*\n" + ", ".join(names), parse_mode="Markdown")

@authorized
async def triage(update, ctx):
    q = " ".join(ctx.args)
    if not q:
        await update.message.reply_text("Uso: /triage `<producto> [versión]`", parse_mode="Markdown"); return
    msg = await update.message.reply_text(f"🔎 Triage de *{q}*…", parse_mode="Markdown")
    rc, out = await run(["python3", "rag/query_vulns.py", "--query", q, "--json", "--limit", "5"], timeout=60)
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        await msg.edit_text("```\n" + clip(out) + "\n```", parse_mode="Markdown"); return
    lines = [f"*Triage — {q}*  (store {data['store'].get('kev_version','?')})"]
    for r in data.get("results", []):
        flags = []
        if r["in_kev"]: flags.append("KEV")
        if r["exploit_public"]: flags.append("EXPLOIT")
        msf = r["msf_modules"][0]["module"] if r.get("msf_modules") else None
        lines.append(f"• `{r['cve']}` {r['severity'].upper()} CVSS={r['cvss']} EPSS={r['epss']} {' '.join(flags)}")
        if msf: lines.append(f"    MSF: `{msf}`")
        if r.get("nuclei_templates"): lines.append(f"    Nuclei: `{r['nuclei_templates'][0]}`")
    await msg.edit_text(clip("\n".join(lines)), parse_mode="Markdown")

@authorized
async def cve(update, ctx):
    if not ctx.args:
        await update.message.reply_text("Uso: /cve `<CVE-id>`", parse_mode="Markdown"); return
    cid = ctx.args[0]
    rc, out = await run(["python3", "rag/query_vulns.py", "--query", cid, "--json", "--limit", "1"], timeout=60)
    try:
        res = json.loads(out).get("results", [])
    except json.JSONDecodeError:
        res = []
    if not res:
        await update.message.reply_text(f"Sin datos para `{cid}` en el RAG.", parse_mode="Markdown"); return
    await update.message.reply_text(clip("```json\n" + json.dumps(res[0], indent=1, ensure_ascii=False) + "\n```"), parse_mode="Markdown")

@authorized
async def refresh(update, ctx):
    await update.message.reply_text("🔄 Refrescando el RAG en segundo plano… te aviso al terminar.")
    async def _job():
        rc, out = await run(["python3", "rag/refresh.py", "--epss-all"], timeout=1800)
        await ctx.bot.send_message(update.effective_chat.id,
                                   "✅ RAG actualizado." if rc == 0 else "⚠️ Refresh con errores.")
    asyncio.create_task(_job())

@authorized
async def findings(update, ctx):
    eng = REPO_DIR / "contracts" / "engagement.json"
    if not eng.exists():
        await update.message.reply_text("No hay engagement activo."); return
    d = json.loads(eng.read_text(encoding="utf-8"))
    fs = d.get("findings", [])
    by = {}
    for f in fs:
        by[f.get("severity", "?")] = by.get(f.get("severity", "?"), 0) + 1
    lines = [f"*Engagement {d.get('engagement_id','?')}* — fase {d.get('phase','?')}",
             f"Findings: {len(fs)}  ({', '.join(f'{k}:{v}' for k,v in by.items())})"]
    for f in fs[:10]:
        lines.append(f"• `{f.get('finding_id')}` [{f.get('severity')}] {f.get('title','')[:60]}")
    await update.message.reply_text(clip("\n".join(lines)), parse_mode="Markdown")

@authorized
async def report(update, ctx):
    reports = sorted((REPO_DIR / "report").glob("INFORME-*.md"))
    if not reports:
        await update.message.reply_text("No hay informe generado. Pídeselo al Orquestador con texto libre."); return
    latest = reports[-1]
    await update.message.reply_document(document=latest.open("rb"), filename=latest.name)

@authorized
async def scope(update, ctx):
    f = REPO_DIR / "contracts" / "scope.json"
    if not f.exists():
        await update.message.reply_text("⚠️ No hay `contracts/scope.json`. Defínelo antes de operar."); return
    d = json.loads(f.read_text(encoding="utf-8"))
    await update.message.reply_text(
        f"*Scope* — {d.get('client','?')}\nin: `{json.dumps(d.get('in_scope',{}))[:300]}`",
        parse_mode="Markdown")

# ── Texto libre → Orquestador (con confirmación) ─────────────────────────────
@authorized
async def freetext(update, ctx):
    task = update.message.text.strip()
    ctx.chat_data["pending_task"] = task
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Ejecutar", callback_data="run"),
        InlineKeyboardButton("✖️ Cancelar", callback_data="cancel")]])
    await update.message.reply_text(f"Orden al Orquestador:\n> {clip(task,300)}\n\n¿Ejecutar?", reply_markup=kb)

@authorized
async def on_button(update, ctx):
    q = update.callback_query
    await q.answer()
    if q.data == "cancel":
        await q.edit_message_text("Cancelado."); return
    task = ctx.chat_data.get("pending_task")
    if not task:
        await q.edit_message_text("No hay orden pendiente."); return
    await q.edit_message_text("⏳ Orquestador trabajando… (las acciones que tocan el target se "
                              "supervisan en terminal/GUI)")
    prompt = ("Actúa como Orquestador siguiendo AGENTS.md. Lee contracts/scope.json. "
              f"Tarea: {task}")
    rc, out = await run(["claude", "-p", prompt, "--permission-mode", "default",
                         "--output-format", "text"], timeout=600)
    await ctx.bot.send_message(q.message.chat_id, clip(out or "(sin salida)"))

async def on_error(update, ctx):
    log.error("Error: %s", ctx.error)

def main():
    if not TOKEN or not ALLOWED:
        raise SystemExit("Falta TELEGRAM_TOKEN o ALLOWED_USER_ID en bot/.env")
    app = Application.builder().token(TOKEN).build()
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
    log.info("Bot iniciado. Allowlist: %s", ALLOWED)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
