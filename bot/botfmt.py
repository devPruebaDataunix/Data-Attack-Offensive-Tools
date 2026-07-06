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


# ── /network · /pivots · /creds — frontera multi-host (pestaña "Red" del bot) ─────
# Consume el DATO CRUDO del blackboard (targets[]/pivots[]/credentials[]); NO reutiliza los renders
# Rich de state.py (network_rows/pivot_rows/credential_rows llevan markup Textual `[color]…[/]`).
# INVARIANTE DURA: las credenciales van SIEMPRE referenciadas — aquí solo se leen campos NO-secretos
# (cred_id/principal/type/privilege/source_target/validated_on); NUNCA `secret_ref` ni valor alguno
# (el secreto vive en engagements/<id>/loot/, fuera de git, y lo imponen memory_guard/secret_scan).
_ACCESS_EMOJI = {"none": "⚪", "user": "🟠", "root": "🔴", "admin": "🔴",
                 "system": "🔴", "domain-admin": "🔴"}
_PIVOT_EMOJI = {"up": "🟢", "planned": "🟡", "down": "🔴"}
_DEF_EMOJI = {"waf": "🛡", "ids": "📡", "ips": "📡", "honeypot": "🍯", "tarpit": "🐌",
              "edr": "🛡", "ratelimit": "⏱", "unknown": "❓"}
_PRIV_HOT = {"root", "admin", "system", "domain-admin"}


def _defenses_frag(defenses) -> str:
    """Defensas de un host como fragmento MD2: 'icono tipo·conf' por cada una; '' si ninguna."""
    if not isinstance(defenses, list) or not defenses:
        return ""
    parts = []
    for d in defenses:
        if isinstance(d, dict):
            icon = _DEF_EMOJI.get(d.get("type", "unknown"), "❓")
            conf = str(d.get("confidence", ""))[:1]
            parts.append(icon + F.esc(f"{d.get('type', '')}·{conf}" if conf else str(d.get("type", ""))))
    return " ".join(parts)


def _net_counts(eng: dict):
    targets = [t for t in (eng or {}).get("targets", []) or [] if isinstance(t, dict)]
    pivots = [p for p in (eng or {}).get("pivots", []) or [] if isinstance(p, dict)]
    creds = [c for c in (eng or {}).get("credentials", []) or [] if isinstance(c, dict)]
    owned = sum(1 for t in targets if (t.get("access_level") or "none") != "none")
    up = sum(1 for p in pivots if p.get("status") == "up")
    return targets, pivots, creds, owned, up


def network_card(eng: dict) -> str:
    """/network (alias /hosts): frontera de hosts + resumen. Acceso coloreado (comprometido = 🔴)."""
    targets, pivots, creds, owned, up = _net_counts(eng)
    if not targets:
        return F.card("Red (multi-host)",
                      F.esc("Sin hosts todavía — aparecen al hacer recon; los internos, al pivotar."),
                      icon="🌐")
    body = [
        f"🖧 hosts {F.bold(len(targets))}   🔴 comprometidos {F.bold(owned)}   "
        f"🟢 pivots {F.bold(f'{up}/{len(pivots)}')}   🔑 creds {F.bold(len(creds))}",
        F.italic("credenciales SIEMPRE referenciadas · el secreto vive en loot/ (fuera de git)"),
        "", F.bold("Hosts"),
    ]
    for t in targets[:15]:
        acc = t.get("access_level", "none") or "none"
        emoji = _ACCESS_EMOJI.get(acc, "⚪")
        via = t.get("reachable_via", "direct") or "direct"
        frag = (F.code(S._clip(t.get("asset", "?"), 40))
                + F.esc(f" · {t.get('asset_type', '—')} · {acc} · vía {via}"))
        defs = _defenses_frag(t.get("defenses"))
        if defs:
            frag += F.esc("  ") + defs
        if not t.get("in_scope"):
            frag += F.esc("  ⚠️ fuera de alcance")
        body.append(F.bullet(f"{emoji} {frag}"))
    if len(targets) > 15:
        body.append(F.italic(f"(+{len(targets) - 15} hosts más)"))
    body += ["", F.italic("detalle: /pivots (túneles) · /creds (credenciales)")]
    return F.card("Red (multi-host)", body, icon="🌐")


def pivots_card(eng: dict) -> str:
    """/pivots: túneles de pivoting (estado up/planned/down + qué CIDR alcanzan)."""
    eng = eng or {}
    pivots = [p for p in eng.get("pivots", []) or [] if isinstance(p, dict)]
    if not pivots:
        return F.card("Pivots (túneles)",
                      F.esc("Sin pivots — lateral-discovery los levanta al descubrir red interna."),
                      icon="🔀")
    body = []
    for p in pivots[:20]:
        st = p.get("status", "planned")
        emoji = _PIVOT_EMOJI.get(st, "⚪")
        frag = (F.code(S._clip(p.get("pivot_id", "?"), 24))
                + F.esc(f" · {p.get('tool', '—')} · vía {S._clip(p.get('via_target', '—'), 24)} · {st}"))
        reaches = ", ".join(p.get("reaches_cidr", []) or [])
        if reaches:
            frag += F.esc(f" → {S._clip(reaches, 44)}")
        body.append(F.bullet(f"{emoji} {frag}"))
    if len(pivots) > 20:
        body.append(F.italic(f"(+{len(pivots) - 20} más)"))
    return F.card("Pivots (túneles)", body, icon="🔀")


def creds_card(eng: dict) -> str:
    """/creds: credenciales del engagement — SIEMPRE referenciadas. Lee SOLO campos NO-secretos;
    NUNCA `secret_ref` ni valor (el secreto vive en engagements/<id>/loot/, fuera de git). El principal
    va en `code` (los principales AD tipo DOMAIN\\usuario llevan '\\', que `esc` NO escapa pero `code` sí)."""
    eng = eng or {}
    creds = [c for c in eng.get("credentials", []) or [] if isinstance(c, dict)]
    if not creds:
        return F.card("Credenciales", F.esc("Sin credenciales recolectadas todavía."), icon="🔑")
    body = [F.italic("referenciadas · el secreto vive en loot/ (fuera de git), nunca aquí")]
    for c in creds[:20]:
        priv = c.get("privilege", "unknown")
        emoji = "🔴" if priv in _PRIV_HOT else "🔑"
        frag = (F.code(S._clip(c.get("cred_id", "?"), 24)) + F.esc(" · ")
                + F.code(S._clip(c.get("principal", "—"), 24))
                + F.esc(f" · {c.get('type', '—')} · {priv}"))
        src = c.get("source_target")
        if src:
            frag += F.esc(f" · de {S._clip(src, 20)}")
        nval = len(c.get("validated_on", []) or [])
        if nval:
            frag += F.esc(f" · validada×{nval}")
        body.append(F.bullet(f"{emoji} {frag}"))
    if len(creds) > 20:
        body.append(F.italic(f"(+{len(creds) - 20} más)"))
    return F.card("Credenciales", body, icon="🔑")


# ── /kb — RAG de CONOCIMIENTO (Capa 1 kb.db + Capa 2 kb_vec.db) ───────────────────
# `/kb` = cobertura (query_kb --stats --json → parse_kb_stats). `/kb <q>` = técnicas Capa 1
# (query_kb --query --json, determinista/stdlib, sin venv). NO reutiliza el render Rich `kb_render`
# de state.py (lleva markup Textual); consume el dict CRUDO y formatea para MD2.
def _counts_frag(d, top: int = 6) -> str:
    """'clave n · clave n …' (top N por conteo desc); '—' si vacío. Fragmento MD2 ya escapado."""
    if not isinstance(d, dict) or not d:
        return F.italic("—")
    items = sorted(d.items(), key=lambda kv: kv[1] if isinstance(kv[1], int) else 0, reverse=True)
    frag = " · ".join(F.esc(f"{k} {v}") for k, v in items[:top])
    return frag + (F.esc(" · …") if len(items) > top else "")


def kb_stats_card(rep: Optional[dict]) -> str:
    """Cobertura del RAG de conocimiento (ambas capas) desde `parse_kb_stats`. Empty-state amable si aún
    no está poblado (típico en el Windows de desarrollo; se puebla en Kali con refresh_kb.py)."""
    c1 = (rep or {}).get("capa1_kb") or {}
    c2 = (rep or {}).get("capa2_kb_vec") or {}
    t1 = c1.get("total") or 0
    if not rep or not t1:
        return F.card("RAG de conocimiento",
                      F.esc("Sin poblar. Puébla con: python rag/knowledge/refresh_kb.py "
                            "(añade --semantic para la Capa 2)."), icon="📚")
    body = [
        F.kv("Capa 1 (kb.db)", F.esc(f"{t1} técnicas")),
        F.bullet(F.kv("fuentes", _counts_frag(c1.get("by_source")))),
        F.bullet(F.kv("plataformas", _counts_frag(c1.get("by_platform")))),
        F.bullet(F.kv("categorías", _counts_frag(c1.get("by_category")))),
        "",
    ]
    t2 = c2.get("total")
    if isinstance(t2, int):
        head = F.esc(f"{t2} trozos") + (F.esc(f"  · modelo {c2['embed_model']}") if c2.get("embed_model") else "")
        body += [F.kv("Capa 2 (kb_vec.db)", head),
                 F.bullet(F.kv("fuentes", _counts_frag(c2.get("by_source"))))]
        if t2 == 0:
            body.append(F.italic("⚠ Capa 2 vacía — refresh_kb.py --semantic"))
        elif t2 < 2000:
            body.append(F.italic("⚠ subset de prueba — repobla entero: refresh_kb.py --semantic"))
    else:
        body.append(F.kv("Capa 2 (kb_vec.db)",
                         F.italic(c2.get("status") or c2.get("error") or "no poblada")))
    return F.card("RAG de conocimiento", body, icon="📚")


def kb_results_card(data: Optional[dict], query: str) -> str:
    """Técnicas Capa 1 para `/kb <q>` desde el JSON de `query_kb --query`. Cada resultado: categoría ·
    fuente:nombre (subtipo) [MITRE] · precondiciones · comando (1ª línea) · ref. `command`/`ref`/`fuente:
    nombre` en `code` (contienen `|`/`>`/`$`/`\\`, que ahí van literales)."""
    if data is None:
        return F.card("RAG de conocimiento",
                      F.esc("No disponible (RAG sin poblar o ilegible). Puébla: rag/knowledge/refresh_kb.py."),
                      icon="📚")
    if data.get("error"):
        return F.card("RAG de conocimiento", F.italic(str(data["error"])), icon="📚")
    results = data.get("results") or []
    if not results:
        return F.card("RAG de conocimiento",
                      F.esc(f"Sin técnicas para «{query}». Prueba otro binario/servicio/keyword."), icon="📚")
    body = [F.italic(f"{len(results)} técnica(s) para «{S._clip(query, 60)}»")]
    for r in results[:8]:
        cat = (r.get("category") or "?").upper()
        mid = f" [{r['mitre_id']}]" if r.get("mitre_id") else ""
        body += ["", F.bullet(F.bold(cat) + F.esc(" · ")
                              + F.code(f"{r.get('source', '?')}:{r.get('name', '?')}")
                              + F.esc(f" ({r.get('subtype') or '—'}){mid}"))]
        if r.get("preconditions"):
            body.append(F.esc("   pre: ") + F.italic(S._clip(r["preconditions"], 120)))
        if r.get("command"):
            body.append(F.esc("   cmd: ") + F.code(r["command"].splitlines()[0][:120]))
        if r.get("source_ref"):
            body.append(F.esc("   ref: ") + F.code(S._clip(r["source_ref"], 80)))
    if len(results) > 8:
        body.append(F.italic(f"(+{len(results) - 8} más — afina la consulta)"))
    return F.card(f"RAG conocimiento · {S._clip(query, 40)}", body, icon="📚")


# ── /lab — arranque IP→autogestión (escribe scope + lanza; SENSIBLE) ─────────────
# La VALIDACIÓN (rechazo de CIDR amplio, forzado de no-daño) vive en actions.build_lab_scope (probada en
# test_tui.py). Aquí SOLO la presentación de la confirmación: nada muta hasta que el operador pulsa ✅.
def lab_confirm_card(scope: dict, mode: str) -> str:
    """Ficha de confirmación de `/lab`: engagement + objetivos (ya clasificados y validados) + supervisión,
    recordando que el no-daño se fuerza y las puertas NO se relajan. `scope` = dict de `build_lab_scope`."""
    ins = (scope or {}).get("in_scope", {}) or {}
    tgt = (ins.get("ips") or []) + (ins.get("cidrs") or []) + (ins.get("domains") or [])
    body = [
        F.kv("engagement", F.code(scope.get("engagement_id", "—"))),
        F.kv("objetivos", " ".join(F.code(t) for t in tgt[:12]) or F.italic("—")),
        F.kv("supervisión", f"{F.mode_emoji(mode)} {F.esc(S.APPROVAL_MODE_ES.get(mode, mode))}"),
        "",
        F.italic("Se FUERZAN no-DoS · no-social · no-exfil; las puertas (alcance/presupuesto/aprobación) "
                 "NO se relajan."),
        F.esc("Voy a fijar contracts/scope.json (con backup .bak) y lanzar el lab de forma autónoma. "
              "¿Confirmar?"),
    ]
    return F.card("Arrancar lab", body, icon="🧪")


def lab_usage_card() -> str:
    return F.card("Uso de /lab",
                  F.esc("/lab <ip|cidr|dominio> [full|critical|auto] — p. ej. ") + F.code("/lab 10.10.10.5")
                  + F.esc(". Fija el scope y lanza el lab (rechaza CIDR amplio; el no-daño se fuerza)."),
                  icon="🧪")


# ── /mode · /model · /effort — config remota del Orquestador ─────────────────────
def config_card(title: str, current: str, options: list, cmd: str, icon: str = "⚙️") -> str:
    """Ficha de un parámetro de config: valor actual + opciones válidas + cómo cambiarlo. `current` vacío
    ⇒ 'por defecto'. Las opciones/valor van en `code` (identificadores)."""
    body = [
        F.kv("actual", F.code(current) if current else F.italic("por defecto (según scope)")),
        F.kv("opciones", " ".join(F.code(str(o)) for o in options)),
        F.italic(f"cambia con: {cmd}"),
    ]
    return F.card(title, body, icon=icon)


def config_set_card(label: str, value_frag: str) -> str:
    """Confirmación de un cambio de config. `value_frag` = fragmento MD2 ya formateado (code/chip)."""
    return F.card("Config actualizada",
                  F.kv(label, value_frag) + F.esc("  · efectivo en la próxima orden"), icon="✅")


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
        F.bold("Red (multi-host)"),
        F.bullet(F.code("/network") + F.esc(" — frontera de hosts (alias /hosts)")),
        F.bullet(F.code("/pivots") + F.esc(" — túneles de pivoting")),
        F.bullet(F.code("/creds") + F.esc(" — credenciales (siempre referenciadas)")),
        "",
        F.bold("Agentes y conocimiento"),
        F.bullet(F.code("/agents") + F.esc(" — roster por zonas E1/E2/E3")),
        F.bullet(F.code("/agent <nombre>") + F.esc(" — ficha de un agente")),
        F.bullet(F.code("/triage <producto>") + F.esc(" — CVE priorizados (KEV/MSF/CVSS)")),
        F.bullet(F.code("/cve <id>") + F.esc(" — ficha de un CVE")),
        F.bullet(F.code("/kb") + F.esc(" — RAG de conocimiento (cobertura) · ") + F.code("/kb <consulta>")
                 + F.esc(" busca técnicas")),
        F.bullet(F.code("/refresh") + F.esc(" — actualiza el RAG (2º plano)")),
        "",
        F.bold("Config"),
        F.bullet(F.code("/mode") + F.esc(" — supervisión (full/critical/auto)") + F.esc(" · ")
                 + F.code("/model") + F.esc(" · ") + F.code("/effort")),
        "",
        F.bold("Órdenes"),
        F.bullet(F.code("/lab <ip>") + F.esc(" — fija el scope de un lab y lo lanza (no relaja puertas)")),
        F.bullet(F.code("/kill") + F.esc(" — aborta la orden en curso (kill-switch)")),
        F.bullet(F.code("/report") + F.esc(" — genera y envía el informe")),
        "",
        F.italic("Las puertas —alcance, presupuesto, aprobación— se aplican SIEMPRE, mande quien mande."),
    ]
    return F.card("Data Attack — control inteligente", body, icon="🧭")
