#!/usr/bin/env python3
"""Tests de E (Shannon) — evals de verticales web/API en el eval-harness. Incluye los casos
ADVERSARIOS que exigió el council (is_lab_target es la ÚNICA barrera del modo autónomo de run_gate).

- run_eval.grade type web/api: findings CONFIRMED (proof-by-exploitation) + cobertura OWASP por CLASE
  (no substring: API1 != API10) + evidencia CAPTURADA obligatoria (evidence_regex, no status auto-declarado).
- run_gate.is_lab_target / _target_host: URL-aware (urlsplit), userinfo @, IPv6, link-local/metadata excluido.
- Los evals nuevos (juice-shop/crapi/dvwa) parsean, target LAB, y tienen evidence_regex.

Sin pytest: `python benchmark/test_web_eval.py` (sale 1 si algo falla).
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import run_eval as RE   # noqa: E402
import run_gate as RG   # noqa: E402

_fail = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _fail.append(name)


def _eng(findings):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "engagement.json")
    json.dump({"engagement_id": "T", "scope_ref": "x", "phase": "reporting",
               "targets": [], "findings": findings}, open(p, "w", encoding="utf-8"))
    return p


def _f(fid, status, owasp, evidence=""):
    return {"finding_id": fid, "target_id": "t1", "title": fid, "status": status,
            "severity": "high", "owasp": owasp, "evidence": evidence}


MARK = "PROOF-abc123"   # marcador "capturado del target"
WEB_EV = {"id": "x", "success_criteria": {"type": "web", "min_confirmed": 2,
          "require_owasp": ["A01", "A03"], "min_findings": 3, "evidence_regex": MARK}}


def t_grade_web():
    # PASS: 3 findings, 2 confirmed cubriendo A01 y A03, con evidencia capturada
    p = _eng([_f("F1", "confirmed", "A01:2021-Broken Access Control", MARK),
              _f("F2", "exploited", "A03:2021-Injection"),
              _f("F3", "candidate", "A05:2021-Misconfig")])
    ok, det = RE.grade(WEB_EV, p, None)
    check("web PASS (2 confirmed A01+A03 + evidencia)", ok is True)
    # FAIL: todo candidate (no proof-by-exploit)
    p = _eng([_f("F1", "candidate", "A01:2021", MARK), _f("F2", "candidate", "A03:2021"),
              _f("F3", "candidate", "A03:2021")])
    ok, det = RE.grade(WEB_EV, p, None)
    check("web FAIL si todo candidate", ok is False and det["confirmed_ok"] is False)
    # FAIL: 2 confirmed pero ambos A03 (falta A01)
    p = _eng([_f("F1", "confirmed", "A03:2021", MARK), _f("F2", "confirmed", "A03:2021"),
              _f("F3", "confirmed", "A03:2021")])
    ok, det = RE.grade(WEB_EV, p, None)
    check("web FAIL si falta clase OWASP (A01)", ok is False and det["owasp_missing"] == ["a01"])
    # FAIL (council): status confirmed pero SIN evidencia capturada (auto-declarado) -> no pasa
    p = _eng([_f("F1", "confirmed", "A01:2021"), _f("F2", "confirmed", "A03:2021"),
              _f("F3", "confirmed", "A03:2021")])
    ok, det = RE.grade(WEB_EV, p, None)
    check("web FAIL si confirmado sin evidencia (proof-by-exploit)", ok is False and det["proof_ok"] is False)
    # FAIL (council): eval sin evidence_regex NO es un gate válido -> no pasa aunque todo cuadre
    noregex = {"id": "z", "success_criteria": {"type": "web", "min_confirmed": 1,
               "require_owasp": ["A03"], "min_findings": 1}}
    p = _eng([_f("F1", "confirmed", "A03:2021", MARK)])
    ok, det = RE.grade(noregex, p, None)
    check("web FAIL sin evidence_regex (gate auto-graduado)", ok is False and det["has_regex"] is False)
    # API1 != API10 (council: substring casaba de más). require API1; confirmado solo API10 -> FAIL
    apiev = {"id": "y", "success_criteria": {"type": "api", "min_confirmed": 1,
             "require_owasp": ["API1"], "min_findings": 1, "evidence_regex": MARK}}
    p = _eng([_f("F1", "confirmed", "API10:2023-Unsafe Consumption", MARK)])
    ok, det = RE.grade(apiev, p, None)
    check("api FAIL: API10 NO satisface API1 (token delimitado)", ok is False and det["owasp_missing"] == ["api1"])
    p = _eng([_f("F1", "confirmed", "API1:2023-BOLA", MARK)])
    ok, det = RE.grade(apiev, p, None)
    check("api PASS: API1 confirmado + evidencia", ok is True)


def t_lab_target():
    for t in ("http://127.0.0.1:3000", "http://localhost:4280", "https://10.10.10.5:8888/api",
              "127.0.0.1", "juice.htb", "192.168.1.10", "http://[::1]:3000", "http://8.8.8.8@127.0.0.1/"):
        check(f"is_lab_target LAB: {t}", RG.is_lab_target(t) is True)
    for t in ("http://example.com:3000", "https://target.optus.com.au", "http://8.8.8.8",
              "RELLENAR: maquina lab", "http://127.0.0.1@8.8.8.8/", "http://169.254.169.254/",
              "http://[fe80::1]/", "http://2130706433/", "http://0.0.0.0/"):
        check(f"is_lab_target NO-lab: {t}", RG.is_lab_target(t) is False)
    check("_target_host URL -> host real", RG._target_host("http://127.0.0.1:3000/x") == "127.0.0.1")
    check("_target_host userinfo -> host tras @", RG._target_host("http://8.8.8.8@127.0.0.1/") == "127.0.0.1")


def t_evals_parse():
    for name in ("juice-shop", "crapi", "dvwa"):
        d = json.load(open(os.path.join(HERE, "evals", name + ".json"), encoding="utf-8"))
        sc = d["success_criteria"]
        check(f"eval {name} type web/api", sc["type"] in ("web", "api"))
        check(f"eval {name} target es LAB", RG.is_lab_target(d["target"]) is True)
        check(f"eval {name} exige confirmados", sc.get("min_confirmed", 0) >= 1)
        check(f"eval {name} ancla a evidencia (evidence_regex)", bool(sc.get("evidence_regex")))


if __name__ == "__main__":
    print("== grade web/api =="); t_grade_web()
    print("== is_lab_target (adversario) =="); t_lab_target()
    print("== evals parsean =="); t_evals_parse()
    print()
    if _fail:
        print(f"FALLOS: {len(_fail)} -> {_fail}")
        sys.exit(1)
    print("TODOS OK")
