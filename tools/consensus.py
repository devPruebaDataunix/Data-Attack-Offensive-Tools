#!/usr/bin/env python3
"""
consensus.py — Consenso multi-persona para el triage (control blando, v2.57 — idea de BugTraceAI,
AGPL → solo la idea, reimplementación limpia).

Endurece `vuln-triage` operacionalizando la regla anti-sesgos "genera ≥2 hipótesis y busca REFUTAR":
para un candidato, se evalúan ≥2 PERSONAS independientes (p.ej. ATACANTE "por qué es explotable" vs
ESCÉPTICO/DEFENSOR "por qué podría ser falso positivo / honeypot / inalcanzable"). Si CONVERGEN (ambas
lo ven real) sube la confianza para priorizarlo; si DIVERGEN, es un candidato DISPUTADO: se
despriorriza y se busca más evidencia antes de gastar explotación (reduce falsos positivos y cebos).

`outcome` es DETERMINISTA (se computa de las hipótesis, no se afirma): `validate_blackboard` puede
recomputarlo y rechazar un `outcome` incoherente — así una persona no puede "lavar" un candidato
disputado como convergente. NO sustituye el gate de proof-state (F): el consenso es de TRIAGE (reduce
FP antes de explotar); la reportabilidad sigue decidiéndola la prueba dinámica. Solo stdlib, puro.
"""
VERDICTS = ("real", "false-positive", "uncertain")
_DECISIVE = ("real", "false-positive")


def _norm(v):
    return str(v or "").strip().lower()


def evaluate(hypotheses):
    """Computa el `outcome` de una lista de hipótesis [{persona, verdict, ...}]:
    - `single`   = menos de 2 hipótesis (una sola voz, sin consenso posible).
    - `converge` = ≥2 hipótesis, ≥2 con verdict DECISIVO (real/false-positive) y TODAS las decisivas
      coinciden (las `uncertain` no bloquean, pero tampoco cuentan como acuerdo).
    - `diverge`  = hay desacuerdo decisivo (real vs false-positive) o no hay ≥2 voces decisivas
      (convicción insuficiente → tratar como disputado).
    Puro y determinista."""
    if not isinstance(hypotheses, list):
        return "single"
    verdicts = [_norm(h.get("verdict")) for h in hypotheses if isinstance(h, dict)]
    if len(verdicts) < 2:
        return "single"
    decisive = [v for v in verdicts if v in _DECISIVE]
    if len(decisive) >= 2 and len(set(decisive)) == 1:
        return "converge"
    return "diverge"


def structural_violations(consensus):
    """Lista de problemas estructurales de un bloque `consensus` (para validate_blackboard). Vacía = OK.
    Comprueba: hipótesis con persona+verdict válido, y coherencia del `outcome` declarado con el
    computado. No exige `consensus` (es opt-in)."""
    out = []
    if not isinstance(consensus, dict):
        return ["consensus no es un objeto"]
    hyps = consensus.get("hypotheses")
    if not isinstance(hyps, list) or not hyps:
        return ["consensus.hypotheses ausente o vacío"]
    for i, h in enumerate(hyps):
        if not isinstance(h, dict) or not h.get("persona") or _norm(h.get("verdict")) not in VERDICTS:
            out.append(f"consensus.hypotheses[{i}] necesita persona + verdict∈{list(VERDICTS)}")
    declared = _norm(consensus.get("outcome"))
    if declared:
        computed = evaluate(hyps)
        if declared != computed:
            out.append(f"consensus.outcome declarado '{declared}' ≠ computado '{computed}' "
                       f"(el outcome se DERIVA de las hipótesis; no lo afirmes a mano)")
    return out
