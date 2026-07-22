#!/usr/bin/env python3
"""Tests del CONSENSO multi-persona (v2.57 — idea de BugTraceAI): endurece vuln-triage.

Cubre `tools/consensus.py` (evaluate + structural_violations), el campo `consensus` del esquema, la
invariante en validate_engagement (recomputa el outcome → una persona no puede lavar un disputado como
'converge'), y el cableado en vuln-triage/AGENTS.

    python tests/test_consensus.py    (sale 1 si algo falla).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import consensus as c  # noqa: E402

_fail = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _fail.append(name)


def _read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


def H(persona, verdict):
    return {"persona": persona, "verdict": verdict, "rationale": "x"}


# ── evaluate ─────────────────────────────────────────────────────────────────────
check("1 hipótesis -> single", c.evaluate([H("attacker", "real")]) == "single")
check("2 real -> converge", c.evaluate([H("attacker", "real"), H("skeptic", "real")]) == "converge")
check("2 false-positive -> converge",
      c.evaluate([H("attacker", "false-positive"), H("skeptic", "false-positive")]) == "converge")
check("real + false-positive -> diverge",
      c.evaluate([H("attacker", "real"), H("skeptic", "false-positive")]) == "diverge")
check("real + uncertain -> diverge (una sola voz decisiva)",
      c.evaluate([H("attacker", "real"), H("skeptic", "uncertain")]) == "diverge")
check("2 real + 1 uncertain -> converge (2 decisivas coinciden)",
      c.evaluate([H("a", "real"), H("b", "real"), H("c", "uncertain")]) == "converge")
check("2 uncertain -> diverge (sin convicción)",
      c.evaluate([H("a", "uncertain"), H("b", "uncertain")]) == "diverge")
check("no-lista -> single", c.evaluate(None) == "single")

# ── structural_violations ──────────────────────────────────────────────────────────
ok_block = {"hypotheses": [H("attacker", "real"), H("skeptic", "real")], "outcome": "converge"}
check("bloque coherente -> sin violaciones", c.structural_violations(ok_block) == [])
bad_outcome = {"hypotheses": [H("attacker", "real"), H("skeptic", "false-positive")], "outcome": "converge"}
check("outcome declarado 'converge' con hipótesis divergentes -> violación",
      any("≠ computado" in v or "computado" in v for v in c.structural_violations(bad_outcome)))
bad_hyp = {"hypotheses": [{"persona": "attacker", "verdict": "maybe"}]}
check("verdict fuera de enum -> violación", c.structural_violations(bad_hyp) != [])
check("sin hipótesis -> violación", c.structural_violations({"hypotheses": []}) != [])

# ── esquema ────────────────────────────────────────────────────────────────────────
sch = json.loads(_read("contracts/finding.schema.json"))
cons = sch["properties"].get("consensus", {})
check("finding.schema tiene 'consensus'", cons.get("type") == "object")
check("consensus.outcome enum single/converge/diverge",
      set(cons.get("properties", {}).get("outcome", {}).get("enum", [])) == {"single", "converge", "diverge"})
hv = cons.get("properties", {}).get("hypotheses", {}).get("items", {})
check("consensus.hypotheses.items requiere persona+verdict", set(hv.get("required", [])) == {"persona", "verdict"})
check("consensus NO en required (retrocompatible)", "consensus" not in sch.get("required", []))

# ── invariante en validate_engagement ───────────────────────────────────────────────
import blackboard as bb  # noqa: E402
base = {"engagement_id": "E", "scope_ref": "s", "phase": "triage", "targets": [], "findings": []}


def viol(consensus_block):
    f = {"finding_id": "F1", "target_id": "t", "title": "x", "status": "candidate",
         "severity": "high", "consensus": consensus_block}
    return bb.validate_engagement(dict(base, findings=[f]))


check("validate: consensus incoherente (converge sobre disputado) -> BLOQUEADO",
      any("F1" in v for v in viol(bad_outcome)))
check("validate: consensus coherente -> OK", not any("F1" in v for v in viol(ok_block)))
check("validate: finding SIN consensus -> intacto (opt-in)",
      not any("F1" in v for v in bb.validate_engagement(dict(base, findings=[
          {"finding_id": "F1", "target_id": "t", "title": "x", "status": "candidate", "severity": "high"}]))))

# ── cableado ─────────────────────────────────────────────────────────────────────────
vt = _read(".claude/agents/analysis/vuln-triage.md")
check("vuln-triage.md: protocolo de consenso (attacker/escéptico, diverge despriorriza)",
      "consensus" in vt and "ESCÉPTICO" in vt and "diverge" in vt)
ag = _read("AGENTS.md")
check("AGENTS.md: consenso en triage (outcome determinista)",
      "consensus" in ag and "diverge" in ag)

print()
if _fail:
    print(f"FALLOS: {len(_fail)} -> {_fail}")
    sys.exit(1)
print("TODOS OK")
