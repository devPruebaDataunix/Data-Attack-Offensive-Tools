"""botfmt.py — Presentación de los comandos del bot: DATOS -> MarkdownV2.

Convierte los datos que leen state.py / intel (blackboard, scope, RAG, clasificación de hallazgos) en
mensajes MarkdownV2 usando la capa de formato tgfmt. Separa la PRESENTACIÓN de los handlers de Telegram
para poder testearla SIN red ni token (bot/tests/test_botfmt.py) — los handlers quedan finos: leen datos
con state.py y llaman aquí. Es el corazón de la unificación bot↔TUI (misma fuente de datos, formato
propio de cada front-end).

REGLA de la capa tgfmt: `kv(label, value)` toma el value como FRAGMENTO ya escapado — aquí envolvemos
todo texto CRUDO en `F.esc(...)` (o `F.code(...)`) antes de pasarlo. OJO: NO reutilizar los renders de
state.py que emiten markup RICH (`agent_detail`, `network_summary`, `a2a_summary`, filas con `[color]…[/]`):
eso es de la TUI. Aquí se consumen los DATOS crudos (dicts/tuplas sin markup) y se formatea para MD2.

stdlib puro: importa solo tgfmt + tui.state (ninguno depende de `telegram`)."""
from __future__ import annotations

from typing import Optional

import tgfmt as F
from tui import state as S


def _num(v, prec: int = 1) -> str:
    return f"{v:.{prec}f}" if isinstance(v, (int, float)) else "—"


def _codelist(items, n: int = 8) -> str:
    """Lista de valores como `code` en línea (dominios/ips/refs). '—' en cursiva si vacía; corta a n."""
    vals = [str(x) for x in (items or []) if x]
    if not vals:
        return F.italic("—")
    tail = F.esc(f"  (+{len(vals) - n})") if len(vals) > n else ""
    return " ".join(F.code(x) for x in vals[:n]) + tail


# ── /cve — ficha de un CVE (antes: json.dumps crudo) ─────────────────────────────
def cve_card(r: Optional[dict]) -> str:
    if not r:
        return F.card("Sin datos", F.esc("Ese CVE no está en el RAG de vulnerabilidades."), icon="ℹ️")
    sev = r.get("severity") or ""
    body = []
    if r.get("title"):
        body.append(F.italic(S._clip(r["title"], 160)))
    prod = " ".join(x for x in (r.get("vendor"), r.get("product")) if x)
    if prod:
        body.append(F.kv("producto", F.esc(prod)))
    body.append(
        F.kv("severidad", f"{F.sev_emoji(sev)} {F.esc((sev or '—').upper())}")
        + "   " + F.kv("CVSS", F.esc(_num(r.get("cvss"))))
        + "   " + F.kv("EPSS", F.esc(_num(r.get("epss"), 3))))
    flags = []
    if r.get("in_kev"):
        flags.append("KEV")
    if r.get("kev_ransomware"):
        flags.append("KEV-ransomware")
    if r.get("exploit_public"):
        flags.append("exploit público")
    if r.get("exploit_maturity"):
        flags.append(str(r["exploit_maturity"]))
    if flags:
        body.append(F.kv("flags", " · ".join(F.bold(x) for x in flags)))
    msf = r.get("msf_modules") or []
    if msf:
        mod = msf[0].get("module") if isinstance(msf[0], dict) else msf[0]
        extra = F.esc(f"  (+{len(msf) - 1} más)") if len(msf) > 1 else ""
        body.append(F.kv("MSF", F.code(mod) + extra))
    nuc = r.get("nuclei_templates") or []
    if nuc:
        body.append(F.kv("Nuclei", F.code(nuc[0])))
    cwe = r.get("cwe") or []
    if cwe:
        body.append(F.kv("CWE", F.esc(", ".join(str(c) for c in cwe[:4]))))
    refs = r.get("source_refs") or []
    if refs:
        # `code` en vez de `link`: una URL de ref (dato del RAG) con '(' o espacio rompería el enlace MD2;
        # en monospace se ve ENTERA (nada de misdirección) y es robusta ante cualquier carácter.
        body.append(F.kv("ref", F.code(refs[0])))
    return F.card(r.get("cve", "CVE"), body, icon="🛡️")


# ── /scope — alcance y restricciones (antes: 2 líneas) ───────────────────────────
def scope_card(scope: Optional[dict]) -> str:
    if not scope:
        return F.card(
            "Sin scope definido",
            F.esc("No hay contracts/scope.json. Define el alcance antes de operar "
                  "(o arranca un lab con /lab <ip>)."),
            icon="⚠️")
    ins = scope.get("in_scope", {}) or {}
    out = scope.get("out_of_scope", {}) or {}
    auth = scope.get("authorization", {}) or {}
    con = scope.get("constraints", {}) or {}
    mode = S.resolve_approval_mode(scope)
    body = [
        F.kv("cliente", F.esc(scope.get("client") or scope.get("engagement_id") or "—")),
        F.kv("autorización", F.esc(f"{auth.get('type', '—')} · ref {auth.get('reference', '—')}")),
    ]
    if auth.get("valid_from") or auth.get("valid_until"):
        body.append(F.kv("vigencia", F.esc(f"{auth.get('valid_from', '—')} → {auth.get('valid_until', '—')}")))
    body += [
        "",
        F.bold("En alcance"),
        F.kv("dominios", _codelist(ins.get("domains"))),
        F.kv("ips/cidr", _codelist((ins.get("ips") or []) + (ins.get("cidrs") or []))),
    ]
    if ins.get("urls"):
        body.append(F.kv("urls", _codelist(ins["urls"])))
    fuera = (out.get("domains") or []) + (out.get("ips") or [])
    if fuera:
        body.append(F.kv("fuera de alcance", _codelist(fuera)))
    guards = [g for g, on in (("no-DoS", con.get("no_dos")),
                              ("no-social", con.get("no_social_engineering")),
                              ("no-exfil-real", con.get("no_data_exfiltration_real"))) if on]
    body += [
        "",
        F.bold("Restricciones"),
        F.kv("supervisión", f"{F.mode_emoji(mode)} {F.esc(S.APPROVAL_MODE_ES.get(mode, mode))}"),
        F.kv("máx acciones", F.esc(S.max_actions(scope))),
    ]
    if guards:
        body.append(F.kv("no-daño", " · ".join(F.bold(g) for g in guards)))
    return F.card("Scope", body, icon="🎯")


# ── /findings — hallazgos clasificados (real / vigilar / ruido) ──────────────────
def _finding_row(v) -> str:
    tgt = f" → {F.code(v.target)}" if getattr(v, "target", None) else ""
    return F.bullet(
        f"{getattr(v, 'emoji', '•')} {F.code(v.finding_id)} "
        f"{F.esc('[' + str(v.severity).upper() + ']')} {F.esc(S._clip(v.title, 60))}{tgt}")


def findings_card(grp: dict, eng: dict) -> str:
    if not eng.get("engagement_id"):
        return F.card("Sin engagement activo",
                      F.esc("No hay engagement en marcha. Lanza una orden al Orquestador "
                            "(p. ej. «haz recon de ejemplo.com»)."), icon="🧩")
    real = grp.get("real", []) or []
    watch = grp.get("watch", []) or []
    noise = grp.get("noise", []) or []
    body = [
        F.kv("engagement", F.esc(eng.get("engagement_id", "—"))) + "   "
        + F.kv("fase", F.esc(S.phase_label(eng.get("phase")))),
        f"🔴 {F.bold('reales')}: {len(real)}   🟠 {F.bold('vigilar')}: {len(watch)}   "
        f"🔇 {F.bold('ruido')}: {len(noise)}",
    ]
    if real:
        body += ["", F.bold("Reales")] + [_finding_row(v) for v in real[:8]]
    if watch:
        body += ["", F.bold("A vigilar")] + [_finding_row(v) for v in watch[:8]]
    if not real and not watch:
        body += ["", F.italic("Sin hallazgos reales ni de vigilancia todavía.")]
    return F.card("Hallazgos", body, icon="🧩")


# ── /agents — roster por zonas E1/E2/E3 (desde el dict CRUDO de agent-cards.json) ─
def agents_card(cards: list, lab_routes=None) -> str:
    """Roster por zonas desde las cards CRUDAS. Reutiliza `S.roster_by_zone` (datos PUROS) — NO el
    render Rich `agent_detail`/roster de la TUI. Cada agente: nombre · modelo Anthropic · nº pares A2A."""
    if not cards:
        return F.card("Sin roster", F.esc("No se pudo leer contracts/agent-cards.json."), icon="👥")
    groups = S.roster_by_zone(cards, lab_routes or {})
    total = sum(len(rows) for _, rows in groups)
    body = [F.italic(f"{total} agentes · usa /agent <nombre> para la ficha")]
    for zone, rows in groups:
        body += ["", F.bold(S.zone_label(zone))]
        for name, _fase, model, _lab, npeers in rows:
            frag = F.code(name) + F.esc(f" · {model}")
            if npeers and npeers != "0":
                frag += F.esc(f" · {npeers} A2A")
            body.append(F.bullet(frag))
    return F.card("Roster de agentes", body, icon="👥")


# ── /agent <nombre> — ficha de UN agente (desde su card CRUDA) ────────────────────
def agent_card(card: Optional[dict]) -> str:
    """Ficha de un agente desde su card CRUDA (name/description/phase/model/tools/a2a_peers/capabilities);
    NO reutiliza el `agent_detail` Rich de la TUI. `None` -> tarjeta 'no encontrado'."""
    if not card:
        return F.card("Agente no encontrado",
                      F.esc("No hay ningún agente con ese nombre. Usa /agents para ver el roster."),
                      icon="👥")
    model = (card.get("model") or "—").replace("claude-", "")
    body = [
        F.italic(S._clip(card.get("description") or "—", 320)),
        "",
        F.kv("zona", F.esc(S.zone_label(S.zone_of(card.get("phase", "")))))
        + "   " + F.kv("fase", F.esc(S.phase_label(card.get("phase", "")))),
        F.kv("modelo", F.code(model)),
    ]
    if card.get("tools"):
        body.append(F.kv("tools", _codelist(card["tools"], 12)))
    if card.get("a2a_peers"):
        body.append(F.kv("A2A", _codelist(card["a2a_peers"], 12)))
    if card.get("capabilities"):
        body.append(F.kv("capacidades", _codelist(card["capabilities"], 10)))
    return F.card(card.get("name", "agente"), body, icon="👥")


# ── /status y /health — tarjeta de SALUD estructurada (sustituye al volcado de verify.sh) ─
_H_OK, _H_WARN = "✅", "⚠️"


def _health_row(ok: bool, label: str, detail: str) -> str:
    """Una fila de salud: glifo ✓/⚠ + etiqueta CRUDA (se escapa) + detalle (fragmento MD2 YA escapado)."""
    return f"{_H_OK if ok else _H_WARN} {F.bold(label)}" + (f" — {detail}" if detail else "")


def health_card(*, sdk_ok: bool, eng: dict, scope: Optional[dict], cards: list,
                actions: tuple, rag_store: Optional[dict], kb: Optional[dict],
                model: str, effort: str, order_line: Optional[str] = None) -> str:
    """Tarjeta de salud (✓/⚠ por componente): motor/SDK · engagement activo · scope+acciones ·
    Orquestador (modelo·effort·supervisión) · agentes por zona · RAG de vulns (+frescura) · RAG de
    conocimiento (Capa 1+2). PURA y testeable: los datos se leen en el handler (state.py + los dos
    query_*.py) y se pasan aquí; empty-states amables por componente (útil en el Windows de desarrollo,
    donde los RAG no están poblados). `order_line` = estado de la orden en curso (texto CRUDO), si la hay.
    Consolida /status y /health en una sola tarjeta (A3)."""
    eng = eng or {}
    eid = eng.get("engagement_id")
    mode = S.resolve_approval_mode(scope)
    count, cap = actions or (0, S.DEFAULT_MAX_ACTIONS)
    body: list = []

    if order_line:
        body += [F.bold("▶️ Orden en curso"), F.esc(order_line), ""]

    body.append(_health_row(sdk_ok, "Motor",
                            F.esc("Agent SDK (streaming)" if sdk_ok else "claude -p (degradado)")))

    if eid:
        body.append(_health_row(True, "Engagement",
                                F.code(eid) + F.esc(f" · fase {S.phase_label(eng.get('phase'))}")))
    else:
        body.append(_health_row(False, "Engagement", F.esc("sin engagement activo")))

    if scope:
        client = scope.get("client") or scope.get("engagement_id") or "definido"
        body.append(_health_row(True, "Scope",
                                F.code(client) + F.esc(f" · {count}/{cap} acciones")))
    else:
        body.append(_health_row(False, "Scope",
                                F.esc("sin definir — usa /lab <ip> o crea contracts/scope.json")))

    body.append(_health_row(True, "Orquestador",
                            F.code((model or "—").replace("claude-", ""))
                            + F.esc(f" · effort {effort} · ")
                            + f"{F.mode_emoji(mode)} {F.esc(S.APPROVAL_MODE_ES.get(mode, mode))}"))

    n = len(cards or [])
    if n:
        zt = " ".join(f"{S.zone_label(z).split()[0]}{len(rows)}" for z, rows in S.roster_by_zone(cards))
        body.append(_health_row(True, "Agentes", F.esc(f"{n}  ") + F.esc(zt)))
    else:
        body.append(_health_row(False, "Agentes", F.esc("no se pudo leer contracts/agent-cards.json")))

    total_cves = (rag_store or {}).get("total_cves")
    if rag_store and total_cves:
        body.append(_health_row(True, "RAG vulns",
                                F.esc(f"{total_cves} CVE · KEV {rag_store.get('kev_version') or '—'}")))
        fresh = " · ".join(x for x in (
            f"EPSS {rag_store['epss_last_sync']}" if rag_store.get("epss_last_sync") else "",
            f"CVE5 {rag_store['cve5_last_sync']}" if rag_store.get("cve5_last_sync") else "",
        ) if x)
        if fresh:
            body.append(F.italic("frescura: " + fresh))
    else:
        body.append(_health_row(False, "RAG vulns", F.esc("sin poblar — python rag/refresh.py")))

    c1 = (kb or {}).get("capa1_kb") or {}
    c2 = (kb or {}).get("capa2_kb_vec") or {}
    t1 = c1.get("total") or 0
    t2 = c2.get("total")
    if t1:
        det = F.esc(f"Capa 1: {t1} técnicas")
        if isinstance(t2, int):
            det += F.esc(f" · Capa 2: {t2} trozos")
        body.append(_health_row(bool(t1 and t2), "RAG conocim.", det))
    else:
        body.append(_health_row(False, "RAG conocim.",
                                F.esc("sin poblar — rag/knowledge/refresh_kb.py (--semantic para Capa 2)")))

    return F.card("Estado de Data Attack", body, icon="🩺")


# ── /help y /start — referencia de comandos (MD2; sustituye al HELP legacy) ───────
def help_card() -> str:
    """Ayuda rica en MarkdownV2 (antes: constante HELP en Markdown legacy). La comparten /help y /start."""
    body = [
        F.italic("Háblame en lenguaje normal («haz recon de app.cliente.com», «prioriza los CVE de "
                 "ese Apache», «genera el informe»): te pido confirmación, aviso por hito en vivo y solo "
                 "escalo alertas reales."),
        "",
        F.bold("Estado"),
        F.bullet(F.code("/status") + F.esc(" — salud del entorno + orden en curso")),
        F.bullet(F.code("/status full") + F.esc(" — chequeo profundo del toolchain")),
        F.bullet(F.code("/findings") + F.esc(" — hallazgos (real / vigilar / ruido)")),
        F.bullet(F.code("/scope") + F.esc(" — alcance y restricciones")),
        "",
        F.bold("Agentes y conocimiento"),
        F.bullet(F.code("/agents") + F.esc(" — roster por zonas E1/E2/E3")),
        F.bullet(F.code("/agent <nombre>") + F.esc(" — ficha de un agente")),
        F.bullet(F.code("/triage <producto>") + F.esc(" — CVE priorizados (KEV/MSF/CVSS)")),
        F.bullet(F.code("/cve <id>") + F.esc(" — ficha de un CVE")),
        F.bullet(F.code("/refresh") + F.esc(" — actualiza el RAG (2º plano)")),
        "",
        F.bold("Órdenes"),
        F.bullet(F.code("/kill") + F.esc(" — aborta la orden en curso (kill-switch)")),
        F.bullet(F.code("/report") + F.esc(" — genera y envía el informe")),
        "",
        F.italic("Las puertas —alcance, presupuesto, aprobación— se aplican SIEMPRE, mande quien mande."),
    ]
    return F.card("Data Attack — control inteligente", body, icon="🧭")
