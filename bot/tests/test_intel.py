#!/usr/bin/env python3
"""
Tests de los módulos de inteligencia del bot (classify / scope / runner-gate).

Sin dependencias: corre standalone con  `python bot/tests/test_intel.py`
(también es descubrible por pytest si está instalado: funciones `test_*` + asserts).
El test del gate del runner se omite si el Claude Agent SDK no está instalado.
"""
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

from intel import classify as C          # noqa: E402
from intel import scope as S             # noqa: E402
from intel.runner import OFFENSIVE, SDK_OK  # noqa: E402


# ── classify ──────────────────────────────────────────────────────────────────
def test_exploited_with_evidence_is_real():
    v = C.classify({"finding_id": "F1", "status": "exploited", "severity": "critical",
                    "target_id": "web01", "title": "RCE", "evidence": "uid=0(root)",
                    "cve": ["CVE-2021-42013"],
                    "msf_modules": [{"module": "exploit/x/apache_normalize_path_rce"}]})
    assert v.level == "real", v
    assert v.emoji == "🔴"
    assert "uid=0(root)" in v.summary
    assert "CVE-2021-42013" in v.summary
    assert "apache_normalize_path_rce" in v.summary


def test_confirmed_without_evidence_is_real_but_flagged():
    v = C.classify({"finding_id": "F2", "status": "confirmed", "severity": "high",
                    "title": "SQLi", "target_id": "db"})
    assert v.level == "real"
    assert "evidencia" in v.reason.lower()  # avisa de que falta el texto de evidencia


def test_candidate_with_public_exploit_is_watch():
    v = C.classify({"finding_id": "F3", "status": "candidate", "severity": "low",
                    "title": "posible", "exploit_public": True, "cve": ["CVE-2024-1"]})
    assert v.level == "watch", v
    assert v.emoji == "🟠"


def test_candidate_high_sev_with_source_is_watch():
    v = C.classify({"finding_id": "F4", "status": "candidate", "severity": "high",
                    "title": "x", "source_refs": ["NVD"]})
    assert v.level == "watch", v


def test_candidate_with_msf_module_is_watch():
    v = C.classify({"finding_id": "F5", "status": "candidate", "severity": "medium",
                    "title": "x", "msf_modules": [{"module": "exploit/y"}]})
    assert v.level == "watch", v


def test_unbacked_low_candidate_is_noise():
    v = C.classify({"finding_id": "F6", "status": "candidate", "severity": "low",
                    "title": "banner viejo"})
    assert v.level == "noise", v
    assert v.summary == ""        # ruido no lleva resumen


def test_candidate_cve_only_low_is_noise():
    # tiene cve (backed) pero sev baja, epss bajo, sin exploit -> no es 'strong' -> ruido
    v = C.classify({"finding_id": "F7", "status": "candidate", "severity": "low",
                    "title": "x", "cve": ["CVE-2010-0001"], "epss": 0.01})
    assert v.level == "noise", v


def test_false_positive_is_noise():
    v = C.classify({"finding_id": "F8", "status": "false_positive", "severity": "high",
                    "title": "x"})
    assert v.level == "noise"
    assert "falso positivo" in v.reason.lower()


def test_out_of_scope_is_noise():
    v = C.classify({"finding_id": "F9", "status": "out_of_scope", "severity": "high",
                    "title": "x"})
    assert v.level == "noise"
    assert "scope" in v.reason.lower()


def test_scan_groups_by_level():
    grp = C.scan([
        {"finding_id": "A", "status": "exploited", "severity": "high", "evidence": "x"},
        {"finding_id": "B", "status": "candidate", "severity": "high", "exploit_public": True},
        {"finding_id": "C", "status": "candidate", "severity": "low"},
        {"finding_id": "D", "status": "false_positive", "severity": "high"},
    ])
    assert len(grp["real"]) == 1 and grp["real"][0].finding_id == "A"
    assert len(grp["watch"]) == 1 and grp["watch"][0].finding_id == "B"
    assert len(grp["noise"]) == 2


# ── scope ──────────────────────────────────────────────────────────────────────
_SCOPE = {"in_scope": {"domains": ["acme.example", "*.acme.example"],
                       "ips": ["203.0.113.10"], "cidrs": ["198.51.100.0/24"]}}


def test_missing_scope_asks():
    assert S.scope_question("haz recon de algo", None) is not None
    assert S.scope_question("haz recon", {"in_scope": {}}) is not None


def test_in_scope_apex_and_subdomain_ok():
    assert S.scope_question("escanea acme.example", _SCOPE) is None
    assert S.scope_question("escanea app.acme.example y api.acme.example", _SCOPE) is None


def test_in_scope_ip_and_cidr_ok():
    assert S.scope_question("nmap 203.0.113.10 y 198.51.100.55", _SCOPE) is None


def test_out_of_scope_domain_flagged():
    q = S.scope_question("ataca evil.com", _SCOPE)
    assert q is not None and "evil.com" in q


def test_lookalike_domain_not_in_scope():
    # 'evilacme.example' NO es subdominio de acme.example
    q = S.scope_question("toca evilacme.example", _SCOPE)
    assert q is not None and "evilacme.example" in q


def test_out_of_scope_ip_flagged():
    q = S.scope_question("escanea 8.8.8.8", _SCOPE)
    assert q is not None and "8.8.8.8" in q


def test_url_host_extracted_and_checked():
    assert S.scope_question("revisa https://app.acme.example/login", _SCOPE) is None
    q = S.scope_question("revisa https://app.evil.com/login", _SCOPE)
    assert q is not None and "app.evil.com" in q


# ── runner: regex de comandos ofensivos ─────────────────────────────────────────
def test_offensive_regex_matches_tools():
    for cmd in ["nmap -sV 10.0.0.1", "nuclei -u http://x", "sqlmap -u http://x",
                "nxc smb 10.0.0.0/24", "msfconsole -q", "ffuf -u http://x/FUZZ",
                "feroxbuster -u http://x", "hydra -l a -P w ssh://x"]:
        assert OFFENSIVE.search(cmd), f"deberia ser ofensivo: {cmd}"


def test_offensive_regex_ignores_benign():
    for cmd in ["ls -la", "cat scope.json", "python rag/query_vulns.py --query apache",
                "echo hola", "git status", "grep -r foo ."]:
        assert not OFFENSIVE.search(cmd), f"NO deberia ser ofensivo: {cmd}"


# ── runner: gate de permiso (async; requiere SDK) ───────────────────────────────
def test_gate_offensive_requires_approval():
    if not SDK_OK:
        print("    (omitido: Claude Agent SDK no instalado)")
        return
    from intel.runner import AgentRunner

    async def _run():
        approvals = []

        async def approve(summary):
            approvals.append(summary)
            return False   # operador deniega

        # modo 'full' = máxima supervisión: hasta el ofensivo de tier 'ask' (nmap) pide aprobación.
        r = AgentRunner(BOT, emit=None, status=None, approve=approve,
                        on_verdict=None, approval_timeout=5, approval_mode="full")
        # comando ofensivo -> pasa por approve() -> deny
        res_deny = await r._gate("Bash", {"command": "nmap -sV 10.0.0.1"}, None)
        # comando benigno -> allow directo, sin pedir aprobación
        res_allow = await r._gate("Bash", {"command": "ls -la"}, None)
        return approvals, res_deny, res_allow

    approvals, res_deny, res_allow = asyncio.run(_run())
    assert len(approvals) == 1, "el comando ofensivo debe pedir aprobación"
    assert res_deny.behavior == "deny"
    assert res_allow.behavior == "allow"


# ── runner: modos de supervisión (auto/critical) en el gate ─────────────────────
def test_gate_critical_mode_autoallows_noncritical():
    if not SDK_OK:
        print("    (omitido: Claude Agent SDK no instalado)")
        return
    from intel.runner import AgentRunner

    async def _run():
        calls = []

        async def approve(s):
            calls.append(s)
            return True

        # default 'critical': nmap/sqlmap (ask) se auto-aprueban; sliver (dual) pide aprobación.
        r = AgentRunner(BOT, emit=None, status=None, approve=approve, on_verdict=None,
                        approval_timeout=5, approval_mode="critical")
        nmap = await r._gate("Bash", {"command": "nmap -sV 10.0.0.1"}, None)
        sliver = await r._gate("Bash", {"command": "sliver-server"}, None)
        return calls, nmap, sliver

    calls, nmap, sliver = asyncio.run(_run())
    assert nmap.behavior == "allow"
    assert sliver.behavior == "allow"   # approve devuelve True las 2 veces
    assert len(calls) == 2, "en 'critical' solo lo crítico (dual) pide aprobación (2 confirmaciones)"


def test_gate_auto_mode_allows_everything():
    if not SDK_OK:
        print("    (omitido: Claude Agent SDK no instalado)")
        return
    from intel.runner import AgentRunner

    async def _run():
        calls = []

        async def approve(s):
            calls.append(s)
            return True

        r = AgentRunner(BOT, emit=None, status=None, approve=approve, on_verdict=None,
                        approval_mode="auto")
        sliver = await r._gate("Bash", {"command": "sliver-server"}, None)
        return calls, sliver

    calls, sliver = asyncio.run(_run())
    assert sliver.behavior == "allow" and calls == [], "en 'auto' ni lo crítico pide aprobación"


# ── risk: tiers de riesgo y política de aprobación ──────────────────────────────
from intel import risk as R  # noqa: E402


def test_risk_tier_classification():
    cases = {
        "whois acme.example": "safe",
        "subfinder -d acme.example": "safe",
        "nmap -sV 10.0.0.1": "normal",
        "httpx -l hosts.txt": "normal",
        "nuclei -u http://x": "normal",
        "sqlmap -u http://x --batch": "sensitive",
        "hydra -l a -P w ssh://x": "sensitive",
        "nxc smb 10.0.0.0/24": "destructive",
        "secretsdump.py dom/u:p@10.0.0.1": "destructive",
        "evil-winrm -i 10.0.0.1 -u a -p b": "destructive",
        "sliver-server": "critical",
        "msfvenom -p windows/meterpreter/reverse_tcp": "critical",
        "ls -la": "benign",
        "python rag/query_vulns.py --query apache": "benign",
    }
    for cmd, tier in cases.items():
        got, _ = R.classify_command(cmd)
        assert got == tier, f"{cmd!r} -> {got} (esperado {tier})"


def test_risk_policy_mapping():
    assert R.classify_command("subfinder -d x")[1] == "auto"     # recon pasivo
    assert R.classify_command("nmap x")[1] == "ask"
    assert R.classify_command("secretsdump.py x")[1] == "ask"
    assert R.classify_command("sliver-server")[1] == "dual"      # C2 -> doble confirmación
    assert R.classify_command("ls")[1] == "auto"


def test_risk_takes_max_tier():
    # un comando que encadena recon + C2 debe tomar el nivel MÁXIMO
    assert R.classify_command("subfinder -d x && sliver-server")[0] == "critical"


def test_gate_safe_recon_auto_no_approval():
    if not SDK_OK:
        print("    (omitido: Claude Agent SDK no instalado)")
        return
    from intel.runner import AgentRunner

    async def _run():
        calls = []

        async def approve(s):
            calls.append(s)
            return True

        r = AgentRunner(BOT, emit=None, status=None, approve=approve, on_verdict=None)
        res = await r._gate("Bash", {"command": "subfinder -d acme.example"}, None)
        return calls, res

    calls, res = asyncio.run(_run())
    assert res.behavior == "allow"
    assert calls == [], "el recon pasivo NO debe pedir aprobación"


def test_gate_critical_requires_dual_approval():
    if not SDK_OK:
        print("    (omitido: Claude Agent SDK no instalado)")
        return
    from intel.runner import AgentRunner

    async def _run():
        ok_calls = []

        async def approve_yes(s):
            ok_calls.append(s)
            return True

        r = AgentRunner(BOT, emit=None, status=None, approve=approve_yes,
                        on_verdict=None, approval_timeout=5)
        allowed = await r._gate("Bash", {"command": "sliver-server"}, None)

        no_calls = []

        async def approve_second_no(s):   # 1ª confirmación OK, 2ª denegada
            no_calls.append(s)
            return len(no_calls) == 1

        r2 = AgentRunner(BOT, emit=None, status=None, approve=approve_second_no,
                         on_verdict=None, approval_timeout=5)
        denied = await r2._gate("Bash", {"command": "sliver-server"}, None)
        return ok_calls, allowed, no_calls, denied

    ok_calls, allowed, no_calls, denied = asyncio.run(_run())
    assert len(ok_calls) == 2, "critical debe pedir DOBLE confirmación"
    assert allowed.behavior == "allow"
    assert len(no_calls) == 2 and denied.behavior == "deny", "denegar la 2ª confirmación bloquea"


# ── runner: narración del bus A2A (no requiere SDK) ─────────────────────────────
def test_scan_narrates_a2a_messages():
    import json
    import tempfile
    from intel.runner import AgentRunner

    async def _run():
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "contracts"))
        eng = os.path.join(d, "contracts", "engagement.json")
        base = {"engagement_id": "T", "scope_ref": "x", "phase": "exploitation",
                "targets": [], "findings": [], "messages": []}
        with open(eng, "w", encoding="utf-8") as f:
            json.dump(base, f)

        emits = []

        async def emit(t):
            emits.append(t)

        async def noop(*a):
            pass

        r = AgentRunner(d, emit=emit, status=noop, approve=noop, on_verdict=noop)
        await r._scan(seed=True)   # baseline: registra sin narrar
        base["messages"] = [{"message_id": "M-1", "engagement_id": "T",
                             "from_agent": "web-exploit", "to_agent": "sqlmap", "role": "request",
                             "ts": "2026-01-01T00:00:00Z",
                             "parts": [{"kind": "text", "text": "confirma SQLi en /login"}]}]
        with open(eng, "w", encoding="utf-8") as f:
            json.dump(base, f)
        os.utime(eng, (r._eng_mtime + 10, r._eng_mtime + 10))  # fuerza cambio de mtime
        await r._scan()
        return emits

    emits = asyncio.run(_run())
    a2a = [e for e in emits if "→" in e and "web-exploit" in e and "sqlmap" in e]
    assert len(a2a) == 1, f"esperaba 1 narración A2A, vi: {emits}"
    assert "confirma SQLi" in a2a[0]


# ── runner standalone ───────────────────────────────────────────────────────────
def _all_tests():
    return [(n, f) for n, f in sorted(globals().items())
            if n.startswith("test_") and callable(f)]


def main():
    failed = 0
    for name, fn in _all_tests():
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    total = len(_all_tests())
    print(f"\n  {total - failed}/{total} OK" + ("" if not failed else f"  · {failed} FALLOS"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
