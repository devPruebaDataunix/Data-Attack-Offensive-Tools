#!/usr/bin/env python3
"""Tests del RAG de POLÍTICA DE PROGRAMA (v2.56, track de integración — idea de bug-reaper).

Cubre:
- Dataset curado/versionado `rag/triage/policy_data.json`: _meta (versión/disclaimer/fuentes),
  plataformas, reglas do_not_report (con exception) y clases de aceptación.
- policy.classify_finding: PRECISIÓN (un XSS/CSRF/info-disclosure REAL no cae en la regla de bajo
  valor; solo la clase específica —self-xss, csrf-logout— casa), aceptación (idor/rce), y advisory.
- CLI query_triage.py (--stats, --class ... --json) por subprocess.
- Adapters por plataforma + scope.example.program + cableado en reporting/vuln-triage.

Sin pytest: `python tests/test_triage_rag.py` (sale 1 si algo falla).
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "rag", "triage"))
_fail = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _fail.append(name)


def _read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def t_dataset():
    data = json.loads(_read("rag/triage/policy_data.json"))
    meta = data.get("_meta", {})
    check("policy_data _meta con versión", bool(meta.get("version")))
    check("policy_data _meta con disclaimer (PREVALECE + advisory)",
          "PREVALECE" in (meta.get("disclaimer") or "") and "proof-state" in (meta.get("disclaimer") or ""))
    check("policy_data _meta con fuentes fechadas",
          isinstance(meta.get("sources"), list) and all("retrieved" in s and "url" in s for s in meta["sources"]))
    check("policy_data 4 plataformas (h1/bugcrowd/intigriti/ywh)",
          set(data.get("platforms", {})) >= {"hackerone", "bugcrowd", "intigriti", "yeswehack"})
    dnr = data.get("do_not_report", [])
    check("do_not_report: >=8 reglas, todas con exception", len(dnr) >= 8 and all(r.get("exception") for r in dnr))
    check("acceptance: incluye idor/rce", any("idor" in (a.get("class") or "") for a in data.get("acceptance", []))
          and any(a.get("class") == "rce" for a in data.get("acceptance", [])))


def t_classify_precision():
    import policy as p
    data = p.load_policy()

    def v(f):
        return p.classify_finding(f, policy=data)

    # La regla de bajo valor SOLO casa por clase ESPECÍFICA:
    check("self-xss -> not-reportable + exception",
          v({"class": "self-xss"})["verdict"] == "not-reportable" and v({"class": "self-xss"}).get("exception"))
    # PRECISIÓN: un XSS real NO cae en self-xss (aunque comparta CWE-79 / la palabra 'xss').
    check("XSS reflejado/almacenado real -> NO not-reportable (precisión)",
          v({"class": "xss", "title": "Stored XSS en comentarios"})["verdict"] == "unknown")
    check("csrf-logout -> not-reportable ; CSRF sensible -> unknown (precisión)",
          v({"class": "csrf-logout"})["verdict"] == "not-reportable"
          and v({"class": "csrf", "title": "CSRF cambia el email"})["verdict"] == "unknown")
    check("info-disclosure de PII real -> unknown (no cae en banner/verbose)",
          v({"class": "information-disclosure", "title": "fuga de PII"})["verdict"] == "unknown")
    check("missing-headers / weak-cipher -> not-reportable",
          v({"class": "missing-headers"})["verdict"] == "not-reportable"
          and v({"class": "weak-cipher"})["verdict"] == "not-reportable")
    # Aceptación de alto valor:
    check("idor -> acceptable ; rce -> acceptable(critical)",
          v({"class": "idor"})["verdict"] == "acceptable"
          and v({"class": "rce"}).get("typical_severity") == "critical")
    # PRECISIÓN REAL (bloqueante del council de corrección): una palabra cotidiana en el TÍTULO no
    # debe disparar una regla do_not_report de una sola palabra y eclipsar la clase de aceptación.
    # El título solo cuenta como pista si NO hay clase/vector.
    check("idor con 'banner' en el título sigue acceptable (título no dispara reglas)",
          v({"class": "idor", "title": "IDOR leaks banner config of other tenants"})["verdict"] == "acceptable")
    check("rce con 'autocomplete' en el título sigue acceptable",
          v({"class": "rce", "title": "RCE via autocomplete field parser"})["verdict"] == "acceptable")
    check("auth-takeover con 'spf' en el título sigue acceptable",
          v({"class": "auth-takeover", "title": "SPF-based account takeover chain"})["verdict"] == "acceptable")
    # Pero SIN clase, el título sí es la única pista (fallback): un título con una clase de una
    # palabra ('rce') sí casa aceptación. (Nota: un guion en el título se trocea, así que
    # 'self-xss' en una frase NO se produce como token — falla SEGURO a 'unknown'.)
    check("sin clase, el título con 'rce' casa aceptación (fallback)",
          v({"title": "RCE in the upload endpoint"})["verdict"] == "acceptable")
    # Sin regla -> unknown (lo decide el analista + proof-state):
    check("clase desconocida -> unknown", v({"class": "quantum-bug"})["verdict"] == "unknown")
    # Advisory: todo veredicto lleva el disclaimer.
    check("todo veredicto incluye disclaimer (advisory)",
          all(v(f).get("disclaimer") for f in ({"class": "idor"}, {"class": "self-xss"}, {"class": "x"})))
    # Fail-open: dataset ausente -> {} y classify no revienta.
    check("load_policy fail-open ante ruta mala", p.load_policy("/no/existe.json") == {})


def t_cli():
    q = os.path.join(ROOT, "rag", "triage", "query_triage.py")
    r = subprocess.run([sys.executable, q, "--stats", "--json"], capture_output=True, text=True)
    check("CLI --stats --json sale 0 y trae versión", r.returncode == 0 and "version" in r.stdout)
    r2 = subprocess.run([sys.executable, q, "--class", "self-xss", "--platform", "hackerone", "--json"],
                        capture_output=True, text=True)
    ok = False
    try:
        ok = json.loads(r2.stdout)["recommendation"]["verdict"] == "not-reportable"
    except Exception:
        ok = False
    check("CLI --class self-xss --json -> not-reportable", ok)


def t_adapters_and_wiring():
    for plat in ("hackerone", "bugcrowd", "intigriti", "yeswehack"):
        md = _read(f"templates/report-adapters/{plat}.md")
        check(f"adapter {plat}: menciona proof-state F y query_triage",
              "proof-state" in md and "query_triage" in md)
    sc = json.loads(_read("contracts/scope.example.json"))
    check("scope.example: program.platform + nota de que la política oficial PREVALECE",
          sc.get("program", {}).get("platform") and "PREVALECE" in (sc["program"].get("notes") or ""))
    rep = _read(".claude/agents/closing/reporting.md")
    check("reporting.md: RAG de política advisory + adapters + no anula proof_state",
          "query_triage.py" in rep and "report-adapters" in rep and "ADVISORY" in rep)
    vt = _read(".claude/agents/analysis/vuln-triage.md")
    check("vuln-triage.md: RAG de política advisory (prioriza, no borra)",
          "query_triage.py" in vt and "ADVISORY" in vt)


if __name__ == "__main__":
    print("== dataset =="); t_dataset()
    print("== classify (precisión + advisory) =="); t_classify_precision()
    print("== CLI =="); t_cli()
    print("== adapters + cableado =="); t_adapters_and_wiring()
    print()
    if _fail:
        print(f"FALLOS: {len(_fail)} -> {_fail}")
        sys.exit(1)
    print("TODOS OK")
