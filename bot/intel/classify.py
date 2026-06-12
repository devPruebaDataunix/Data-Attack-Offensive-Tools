"""
Clasificación de hallazgos: distingue EVIDENCIA REAL de ruido de escáner.

Criterio (alineado con contracts/finding.schema.json y la regla de AGENTS.md
"sin fuente no se explota"):

- real  : status confirmed/exploited -> un agente lo verificó. Hay impacto demostrado.
          Es lo único que dispara la alerta roja.
- watch : candidate con respaldo fuerte (exploit público / módulo MSF / EPSS alto /
          severidad high-critical con fuente) pero AÚN sin verificar. Se vigila.
- noise : false_positive, out_of_scope, o candidate sin respaldo (hit suelto de un
          escáner). Se cuenta y se calla; no se alerta.

El texto para humano es deliberadamente plano y concreto (ver docs/humanizer-checklist.md):
frases cortas, datos verificables, sin relleno.
"""
from __future__ import annotations

from dataclasses import dataclass

REAL_STATUS = {"confirmed", "exploited"}
DEAD_STATUS = {"false_positive", "out_of_scope"}
SEV_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class Verdict:
    finding_id: str
    level: str       # real | watch | noise
    emoji: str
    title: str
    target: str
    severity: str
    reason: str      # por qué cae en este nivel (una línea, para humano)
    summary: str     # explicación clara (solo real/watch; vacío en noise)


def _trim(s: str, n: int) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _backed(f: dict) -> bool:
    return bool(
        f.get("exploit_public")
        or f.get("msf_modules")
        or f.get("exploit_sources")
        or f.get("source_refs")
        or f.get("cve")
    )


def _human_summary(f: dict) -> str:
    parts = []
    sev = (f.get("severity") or "?").upper()
    cvss = f.get("cvss")
    parts.append(f"Severidad {sev}" + (f" · CVSS {cvss}" if cvss is not None else "") + ".")

    cves = f.get("cve") or []
    if cves:
        parts.append("CVE: " + ", ".join(cves[:4]) + ".")

    why = []
    if f.get("exploit_public"):
        why.append("exploit público")
    if f.get("msf_modules"):
        m = f["msf_modules"][0]
        mod = m.get("module") if isinstance(m, dict) else m
        why.append(f"módulo Metasploit ({mod})")
    if f.get("source_refs"):
        why.append("respaldado por fuente")
    if why:
        parts.append("Respaldo: " + ", ".join(why) + ".")

    ev = (f.get("evidence") or "").strip()
    if ev:
        parts.append("Evidencia: " + _trim(ev, 420))
    impact = (f.get("impact") or "").strip()
    if impact:
        parts.append("Impacto: " + _trim(impact, 260))
    repro = (f.get("reproduction") or "").strip()
    if repro:
        parts.append("Reproducción: " + _trim(repro, 260))
    return "\n".join(parts)


def classify(f: dict) -> Verdict:
    fid = f.get("finding_id", "?")
    status = (f.get("status") or "candidate").lower()
    sev = (f.get("severity") or "info").lower()
    target = f.get("target_id", "?")
    title = f.get("title", "(sin título)")
    evidence = (f.get("evidence") or "").strip()
    epss = float(f.get("epss") or 0)

    if status in DEAD_STATUS:
        reason = "marcado falso positivo" if status == "false_positive" else "fuera de scope"
        return Verdict(fid, "noise", "🔇", title, target, sev, reason, "")

    if status in REAL_STATUS:
        reason = ("explotado: impacto demostrado" if status == "exploited"
                  else "confirmado por el agente de explotación")
        if not evidence:
            reason += " — ojo: sin texto de evidencia adjunto"
        return Verdict(fid, "real", "🔴", title, target, sev, reason, _human_summary(f))

    # status == candidate (u otro no terminal)
    strong = _backed(f) and (
        SEV_RANK.get(sev, 0) >= 3 or epss >= 0.5
        or f.get("exploit_public") or f.get("msf_modules")
    )
    if strong:
        return Verdict(fid, "watch", "🟠", title, target, sev,
                       "candidato con respaldo (exploit/MSF/KEV) — sin verificar aún",
                       _human_summary(f))
    return Verdict(fid, "noise", "🔇", title, target, sev,
                   "candidato sin respaldo verificable (probable ruido de escáner)", "")


def scan(findings: list[dict]) -> dict:
    """Clasifica una lista de findings y agrupa por nivel."""
    verdicts = [classify(f) for f in findings]
    return {
        "verdicts": verdicts,
        "real": [v for v in verdicts if v.level == "real"],
        "watch": [v for v in verdicts if v.level == "watch"],
        "noise": [v for v in verdicts if v.level == "noise"],
    }
