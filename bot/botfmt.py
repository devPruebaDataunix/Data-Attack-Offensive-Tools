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
