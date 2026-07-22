#!/usr/bin/env python3
"""
policy.py — Capa de consulta del RAG de POLÍTICA DE PROGRAMA / triage (mejora del track de
integración, idea de bug-reaper). Dataset CURADO y VERSIONADO en git (`policy_data.json`,
fuente+fecha+disclaimer), no un store scrapeado — orienta qué clases suele ACEPTAR o RECHAZAR un
programa de bug bounty (HackerOne / Bugcrowd / Intigriti / YesWeHack).

IMPORTANTE — es ADVISORY, no un gate:
- ORIENTA la priorización (`vuln-triage`) y el filtrado del informe (`reporting`); NUNCA sustituye
  el criterio del analista ni la barrera determinista de proof-state (mejora F, `tools/blackboard.py`).
- La política OFICIAL del programa PREVALECE siempre (lo dice el disclaimer del dataset). Una regla
  genérica "do-not-report" NO descarta un hallazgo de impacto real: cada regla trae su `exception`.
- No decide reportabilidad por sí sola: `reporting` aplica PRIMERO el gate de F (`is_reportable`) y
  solo DESPUÉS usa esto para encuadrar/priorizar. Este módulo devuelve una recomendación etiquetada.

Solo stdlib. Funciones puras (no tocan red; leen un JSON versionado del repo).
"""
import json
import os
import re

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy_data.json")

# Verdictos posibles (advisory). Una regla puede además fijar su propio `default` en el dataset
# (p.ej. "low-value" en open-redirect), que se devuelve tal cual.
NOT_REPORTABLE = "not-reportable"   # clase típicamente rechazada salvo que aplique la excepción
ACCEPTABLE = "acceptable"           # clase de alto valor esperada por los programas
UNKNOWN = "unknown"                 # sin regla que aplique -> decide el analista/proof-state


def load_policy(path=DATA_PATH):
    """Carga el dataset de política. Devuelve el dict (o {} si falta/ilegible — fail-open advisory)."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _tokens(*values):
    """Normaliza a un conjunto de tokens en minúscula (palabras y guiones) de los valores dados."""
    out = set()
    for v in values:
        if not v:
            continue
        if isinstance(v, (list, tuple)):
            for x in v:
                out |= _tokens(x)
            continue
        s = str(v).lower()
        out.add(s)
        for tok in re.split(r"[^a-z0-9]+", s):
            if len(tok) > 1:
                out.add(tok)
    return out


def finding_class_tokens(finding):
    """Deriva los tokens de CLASE de un finding para casar contra las reglas. Usa la CLASE
    autoritativa (`class`/`vector`); el `title` SOLO como fallback cuando NO hay clase. Si el título
    alimentara siempre el match, una palabra cotidiana ('banner', 'spf', 'autocomplete') dispararía
    una regla `do_not_report` de una sola palabra y ECLIPSARÍA la clase de aceptación real —un IDOR/
    RCE real cuyo título mencione 'banner' pasaría a 'not-reportable' en triage, antes de que exista
    la red de proof-state (F). Casamos por NOMBRE DE CLASE, nunca por cwe/owasp (una clase genérica
    como CWE-79 la comparten self-XSS y XSS reflejado). PRECISIÓN sobre recall: solo se recomienda
    descartar cuando la CLASE ESPECÍFICA (p.ej. `self-xss`) casa explícitamente."""
    if not isinstance(finding, dict):
        return set()
    toks = _tokens(finding.get("class"), finding.get("vector"))
    if not toks:                       # sin clase/vector: el título es la única pista disponible
        toks = _tokens(finding.get("title"))
    return toks


def _full(values):
    """Conjunto de strings COMPLETOS en minúscula (sin trocear) — para el lado REGLA del match:
    la regla 'self-xss' NO debe casar un finding cuya clase es 'xss' (que troceado incluiría 'xss')."""
    out = set()
    for v in (values or []):
        if v:
            out.add(str(v).lower())
    return out


def _rule_matches(rule, toks):
    """¿Aplica esta regla al finding? Solo por NOMBRE DE CLASE específico: alguna de las `classes`
    de la regla (comparada como string COMPLETO) debe estar en los tokens del finding."""
    return "class" if _full(rule.get("classes")) & toks else None


def classify_finding(finding, platform=None, policy=None):
    """Recomendación ADVISORY de reportabilidad de un finding según la política de programa.

    Devuelve un dict con: verdict (not-reportable/low-value/acceptable/unknown), matched (id de
    regla o clase de aceptación), reason, exception (cuándo SÍ se reporta), platform (+su nota) y
    disclaimer. NUNCA es una decisión final: úsalo para PRIORIZAR y ENCUADRAR; el gate de
    reportabilidad es proof-state (mejora F) + el criterio humano."""
    policy = policy if policy is not None else load_policy()
    toks = finding_class_tokens(finding)
    plat = (policy.get("platforms", {}) or {}).get(platform) if platform else None
    base = {
        "platform": platform,
        "platform_note": (plat or {}).get("note"),
        "disclaimer": (policy.get("_meta", {}) or {}).get("disclaimer"),
    }

    # 1) ¿Es una clase típicamente NO reportable? (con su excepción)
    for rule in policy.get("do_not_report", []) or []:
        if _rule_matches(rule, toks):
            return dict(base, verdict=rule.get("default", NOT_REPORTABLE), matched=rule.get("id"),
                        title=rule.get("title"), reason=rule.get("rationale"),
                        exception=rule.get("exception"))

    # 2) ¿Es una clase de aceptación de alto valor?
    for acc in policy.get("acceptance", []) or []:
        if _full([acc.get("class")] + (acc.get("aka") or [])) & toks:
            return dict(base, verdict=ACCEPTABLE, matched=acc.get("class"),
                        reason=acc.get("note"), requires_proof=acc.get("requires_proof"),
                        typical_severity=acc.get("typical_severity"))

    # 3) Sin regla que aplique: lo decide el analista + proof-state.
    return dict(base, verdict=UNKNOWN, matched=None,
                reason="Sin regla de política aplicable — decide el analista y el gate de proof-state (F).")
