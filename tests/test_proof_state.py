#!/usr/bin/env python3
"""Tests de F (Shannon) — proof-state reconciliado con ROE.

Cubre el diseño de la mejora F: dos ejes ortogonales por finding (`status` = ciclo de vida,
`proof_state` = grado de prueba) y el GATE de informe que descarta solo `speculative` pero
CONSERVA `roe-capped` (real pero no explotado por ROE — el caso "los 12 Citrix").

- Esquema: finding.proof_state (enum 4 valores) + confidence (enum low/medium/high), retrocompat.
- tools/blackboard.py: effective_proof_state (explícito + derivación de status), is_reportable
  (speculative fuera, roe-capped dentro, false_positive/out_of_scope fuera), finding_has_source.
- validate_engagement (barrera write-time, OPT-IN): evidenced/proven-by-exploit sin evidence -> bloqueo;
  roe-capped sin fuente -> bloqueo; proof_state inválido -> bloqueo; legacy sin proof_state -> intacto;
  regla code_ref legacy sigue viva.
- tools/analyze_engagement.py (audit): importa el gate, cuenta roe-capped, no exige evidence a roe-capped.
- Consumidores/doc: reporting.md, report-template.md, docs/reporting-guide.md, AGENTS.md.

Sin pytest: `python tests/test_proof_state.py` (sale 1 si algo falla).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
_fail = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _fail.append(name)


def _load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


# ── esquema ────────────────────────────────────────────────────────────────────
def t_schema():
    sch = json.loads(_load("contracts/finding.schema.json"))
    props = sch["properties"]
    ps = props.get("proof_state", {})
    check("finding.schema tiene 'proof_state'", ps.get("type") == "string")
    check("proof_state enum = speculative/evidenced/proven-by-exploit/roe-capped",
          set(ps.get("enum", [])) == {"speculative", "evidenced", "proven-by-exploit", "roe-capped"})
    check("proof_state describe roe-capped como INCLUIDO y speculative DESCARTADO",
          "roe-capped" in ps.get("description", "") and "descarta" in ps.get("description", "").lower())
    conf = props.get("confidence", {})
    check("finding.schema tiene 'confidence' (low/medium/high)",
          set(conf.get("enum", [])) == {"low", "medium", "high"})
    check("proof_state/confidence NO son obligatorios (retrocompatible)",
          "proof_state" not in sch.get("required", []) and "confidence" not in sch.get("required", []))

    try:
        import jsonschema
    except Exception:
        print("  (jsonschema ausente: se omite la validación estructural)")
        return
    base = {"finding_id": "F", "target_id": "t", "title": "x", "status": "candidate", "severity": "high"}
    ok = dict(base, proof_state="roe-capped", confidence="high")
    try:
        jsonschema.validate(ok, sch); check("finding con proof_state/confidence válidos valida", True)
    except jsonschema.ValidationError as e:
        check(f"finding con proof_state/confidence válidos valida ({e.message})", False)
    for bad, why in ((dict(base, proof_state="maybe"), "proof_state fuera de enum"),
                     (dict(base, confidence="very-high"), "confidence fuera de enum")):
        try:
            jsonschema.validate(bad, sch); check(f"finding inválido RECHAZADO ({why})", False)
        except jsonschema.ValidationError:
            check(f"finding inválido RECHAZADO ({why})", True)


# ── helpers de blackboard.py ─────────────────────────────────────────────────────
def t_helpers():
    import importlib
    bb = importlib.import_module("blackboard")

    # effective_proof_state: explícito manda
    check("effective: proof_state explícito manda",
          bb.effective_proof_state({"proof_state": "roe-capped", "status": "candidate"}) == "roe-capped")
    # derivación de status cuando falta
    check("effective: exploited -> proven-by-exploit (derivado)",
          bb.effective_proof_state({"status": "exploited"}) == "proven-by-exploit")
    check("effective: confirmed -> evidenced (derivado)",
          bb.effective_proof_state({"status": "confirmed"}) == "evidenced")
    check("effective: candidate -> speculative (derivado)",
          bb.effective_proof_state({"status": "candidate"}) == "speculative")
    check("effective: false_positive -> None",
          bb.effective_proof_state({"status": "false_positive"}) is None)
    check("effective: proof_state inválido cae a la derivación de status",
          bb.effective_proof_state({"proof_state": "xx", "status": "confirmed"}) == "evidenced")

    # is_reportable: el corazón de F
    check("reportable: proven-by-exploit -> True", bb.is_reportable({"proof_state": "proven-by-exploit"}))
    check("reportable: evidenced -> True", bb.is_reportable({"proof_state": "evidenced"}))
    check("reportable: roe-capped -> True (CONSERVADO, no se pierde)",
          bb.is_reportable({"proof_state": "roe-capped", "status": "candidate"}))
    check("reportable: speculative -> False (DESCARTADO)",
          not bb.is_reportable({"proof_state": "speculative"}))
    check("reportable: candidate legacy (sin proof_state) -> False",
          not bb.is_reportable({"status": "candidate"}))
    check("reportable: confirmed legacy -> True", bb.is_reportable({"status": "confirmed"}))
    check("reportable: false_positive gana aunque proof_state diga proven",
          not bb.is_reportable({"status": "false_positive", "proof_state": "proven-by-exploit"}))
    check("reportable: out_of_scope -> False",
          not bb.is_reportable({"status": "out_of_scope", "proof_state": "evidenced"}))

    # finding_has_source
    check("has_source: cve cuenta", bb.finding_has_source({"cve": ["CVE-2023-1"]}))
    check("has_source: source_refs cuenta", bb.finding_has_source({"source_refs": ["KEV"]}))
    check("has_source: vacío -> False", not bb.finding_has_source({"title": "x"}))


# ── validate_engagement (barrera write-time) ─────────────────────────────────────
def t_validate():
    import importlib
    bb = importlib.import_module("blackboard")
    base = {"engagement_id": "E", "scope_ref": "s", "phase": "exploitation", "targets": [], "findings": []}

    def viol(f):
        return bb.validate_engagement(dict(base, findings=[f]))

    F = {"finding_id": "F1", "target_id": "t", "title": "x", "status": "candidate", "severity": "high"}

    # evidenced/proven sin evidence -> bloqueo. Uso status COHERENTE (confirmed/exploited) para AISLAR
    # la regla de evidencia de la de incoherencia (si dejara F en 'candidate' saltarían ambas y la
    # aserción no probaría en aislamiento que se exige evidencia — NIT del council de corrección).
    v = bb.validate_engagement(dict(base, findings=[dict(F, status="confirmed", proof_state="evidenced")]))
    check("evidenced (status coherente) SIN evidence -> BLOQUEADO por evidencia (aislado)",
          any("F1" in x and "evidence" in x for x in v) and not any("INCOHERENTE" in x for x in v))
    v = bb.validate_engagement(dict(base, findings=[dict(F, status="exploited", proof_state="proven-by-exploit")]))
    check("proven-by-exploit (status coherente) SIN evidence -> BLOQUEADO por evidencia (aislado)",
          any("F1" in x and "evidence" in x for x in v) and not any("INCOHERENTE" in x for x in v))
    # evidenced exige status dinámico: con evidence Y status confirmed -> OK
    v = bb.validate_engagement(dict(base, findings=[dict(F, status="confirmed",
                                                         proof_state="evidenced", evidence="par 200/403")]))
    check("evidenced + confirmed + evidence -> OK", not any("F1" in x for x in v))

    # roe-capped sin fuente -> bloqueo; con fuente -> OK
    v = viol(dict(F, proof_state="roe-capped"))
    check("roe-capped SIN fuente -> BLOQUEADO", any("F1" in x and "FUENTE" in x for x in v))
    v = viol(dict(F, proof_state="roe-capped", cve=["CVE-2023-3519"]))
    check("roe-capped CON fuente (cve) -> OK", not any("F1" in x for x in v))
    v = viol(dict(F, proof_state="roe-capped", source_refs=["KEV:Citrix"]))
    check("roe-capped CON fuente (source_refs) -> OK", not any("F1" in x for x in v))
    # roe-capped NO exige evidence (por definición no se explotó)
    v = viol(dict(F, proof_state="roe-capped", cve=["CVE-2023-3519"]))
    check("roe-capped NO exige evidence", not any("F1" in x and "evidence" in x for x in v))

    # proof_state inválido -> bloqueo
    v = viol(dict(F, proof_state="mostly-sure"))
    check("proof_state inválido -> BLOQUEADO", any("F1" in x and "inválido" in x for x in v))

    # OPT-IN: legacy sin proof_state no dispara nada nuevo
    v = viol(dict(F))
    check("legacy candidate sin proof_state -> intacto (opt-in)", not any("F1" in x for x in v))
    v = viol({"finding_id": "F9", "target_id": "t", "title": "x", "status": "confirmed",
              "severity": "high", "evidence": "PoC"})
    check("legacy confirmed con evidence -> OK", not any("F9" in x for x in v))

    # regla code_ref legacy sigue viva
    v = viol({"finding_id": "FC", "target_id": "t", "title": "x", "status": "confirmed",
              "severity": "high", "code_ref": "app:src/a.ts:1"})
    check("code_ref + confirmed sin evidence -> BLOQUEADO (regla A intacta)", any("FC" in x for x in v))

    # COHERENCIA status<->proof_state (cierra la relajación de evidencia y el "exploited desaparecido")
    v = bb.validate_engagement(dict(base, findings=[dict(F, status="exploited",
                                                         proof_state="roe-capped", cve=["CVE-1"])]))
    check("exploited + roe-capped -> INCOHERENTE (no relaja la evidencia)",
          any("F1" in x and "INCOHERENTE" in x for x in v))
    v = bb.validate_engagement(dict(base, findings=[dict(F, status="exploited",
                                                         proof_state="speculative")]))
    check("exploited + speculative -> INCOHERENTE (no se pierde del informe)",
          any("F1" in x and "INCOHERENTE" in x for x in v))
    v = bb.validate_engagement(dict(base, findings=[dict(F, status="candidate",
                                                         proof_state="roe-capped", cve=["CVE-1"])]))
    check("candidate + roe-capped -> coherente (par canónico)",
          not any("F1" in x for x in v))
    v = bb.validate_engagement(dict(base, findings=[dict(F, status="exploited",
                                                         proof_state="proven-by-exploit", evidence="PoC")]))
    check("exploited + proven-by-exploit + evidence -> coherente", not any("F1" in x for x in v))


# ── analyze_engagement (audit) ───────────────────────────────────────────────────
def t_analyze():
    import importlib
    ae = importlib.import_module("analyze_engagement")
    check("analyze_engagement importa el gate real (is_reportable)",
          ae.is_reportable({"proof_state": "roe-capped"}) is True)
    check("analyze_engagement: PROOF_NEEDS_EVIDENCE no incluye roe-capped",
          "roe-capped" not in ae.PROOF_NEEDS_EVIDENCE)
    check("analyze_engagement: speculative no es reportable",
          ae.is_reportable({"proof_state": "speculative"}) is False)
    # Regresión: el gate real RESPETA el proof_state explícito (el fallback divergente lo ignoraba y
    # habría descartado un roe-capped+candidate del informe — el fallo que F existe para evitar).
    check("analyze_engagement respeta proof_state explícito (roe-capped+candidate reportable)",
          ae.is_reportable({"status": "candidate", "proof_state": "roe-capped"}) is True)
    # M1 del council de seguridad: el audit REPLICA el check de coherencia (defensa en profundidad).
    check("analyze_engagement porta el check de coherencia (_PROOF_STATUS_OK)",
          hasattr(ae, "_PROOF_STATUS_OK") and ae._PROOF_STATUS_OK.get("roe-capped") == {"candidate"})


# ── consumidores / documentación ─────────────────────────────────────────────────
def t_docs():
    rep = _load(".claude/agents/closing/reporting.md")
    check("reporting.md: gate por proof_state (incluye roe-capped, descarta speculative)",
          "proof_state" in rep and "roe-capped" in rep and "speculative" in rep)
    check("reporting.md: regla de no omitir roe-capped",
          "Nunca omitas un `roe-capped`" in rep or "NO se degradan" in rep)

    tpl = _load("templates/report-template.md")
    check("report-template: fila 'Verificación' con 'Limitado por ROE'",
          "Verificación" in tpl and "Limitado por ROE" in tpl)

    guide = _load("docs/reporting-guide.md")
    check("reporting-guide: sección de proof_state",
          "proof_state" in guide and "roe-capped" in guide)

    ag = _load("AGENTS.md")
    check("AGENTS.md: modelo proof_state en el cierre (is_reportable, 12 Citrix)",
          "proof_state" in ag and "roe-capped" in ag and "is_reportable" in ag)

    vt = _load(".claude/agents/analysis/vuln-triage.md")
    check("vuln-triage.md: default speculative + elevación a roe-capped",
          "speculative" in vt and "roe-capped" in vt)
    for a in ("web-exploit", "api-exploit"):
        md = _load(f".claude/agents/exploitation/{a}.md")
        check(f"{a}.md: fija proof_state (proven/evidenced/roe-capped)",
              "proof_state" in md and "roe-capped" in md and "proven-by-exploit" in md)


if __name__ == "__main__":
    print("== finding.schema proof_state/confidence =="); t_schema()
    print("== blackboard helpers =="); t_helpers()
    print("== validate_engagement (write-time) =="); t_validate()
    print("== analyze_engagement (audit) =="); t_analyze()
    print("== consumidores / doc =="); t_docs()
    print()
    if _fail:
        print(f"FALLOS: {len(_fail)} -> {_fail}")
        sys.exit(1)
    print("TODOS OK")
