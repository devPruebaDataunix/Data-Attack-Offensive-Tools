#!/usr/bin/env python3
"""
Tests de la LÓGICA de la TUI de control total (state.py + actions.py) y de los ganchos aditivos
del runner (coste/turnos + abort). Sin Textual: solo la lógica pura, 100% testeable sin terminal.

Corre standalone:  python bot/tests/test_tui.py
(también descubrible por pytest: funciones test_* + asserts). La UI Textual se valida en la Kali.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

import tui.state as S          # noqa: E402
import tui.actions as A        # noqa: E402


def _tmp_engagement(messages=None, phase="recon"):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "contracts"))
    base = {"engagement_id": "T-1", "scope_ref": "contracts/scope.json", "phase": phase,
            "targets": [], "findings": [], "messages": messages or []}
    with open(os.path.join(d, "contracts", "engagement.json"), "w", encoding="utf-8") as f:
        json.dump(base, f)
    return Path(d)


# ── state: lectura ───────────────────────────────────────────────────────────────
def test_read_json_missing_is_none():
    assert S.read_json(Path("/no/existe.json")) is None


def test_action_count_and_max():
    d = _tmp_engagement()
    with open(d / "contracts" / ".action_count", "w", encoding="utf-8") as f:
        json.dump({"key": "T-1", "count": 42}, f)
    assert S.action_count(d) == (42, "T-1")
    assert S.max_actions(None) == 1000
    assert S.max_actions({"constraints": {"max_actions": 250}}) == 250


def test_max_a2a_hops_default_and_override():
    assert S.max_a2a_hops(None) == 50
    assert S.max_a2a_hops({"constraints": {"max_a2a_hops": 12}}) == 12


# ── state: render del bus A2A ────────────────────────────────────────────────────
def _msg(mid, frm, to, status="pending", hops=0, text="hola"):
    return {"message_id": mid, "from_agent": frm, "to_agent": to, "role": "request",
            "status": status, "hops": hops, "parts": [{"kind": "text", "text": text}]}


def test_a2a_rows():
    eng = {"messages": [_msg("M1", "web-exploit", "sqlmap", "delivered", 2, "confirma SQLi")]}
    rows = S.a2a_rows(eng)
    assert len(rows) == 1
    emoji, frm, to, role, hops, preview = rows[0]
    assert frm == "web-exploit" and to == "sqlmap" and hops == "2"
    assert "confirma SQLi" in preview and emoji == "📨"


def test_a2a_summary_counts_and_hops():
    eng = {"messages": [_msg("M1", "a", "b", "pending", 1), _msg("M2", "b", "a", "done", 40)]}
    out = S.a2a_summary(eng, {"constraints": {"max_a2a_hops": 50}})
    assert "pending: 1" in out and "done: 1" in out and "40/50" in out


def test_pending_message_ids():
    eng = {"messages": [_msg("M1", "a", "b", "pending"), _msg("M2", "b", "a", "done")]}
    assert S.pending_message_ids(eng) == ["M1"]


def test_message_detail():
    eng = {"messages": [_msg("M1", "a", "b", "pending", 0, "detalle xyz")]}
    out = S.message_detail(eng, "M1")
    assert "M1" in out and "detalle xyz" in out
    assert "no encontrado" in S.message_detail(eng, "NOPE")


# ── state: roster, presupuesto, fase, evidencia, RAG ─────────────────────────────
def test_roster_rows():
    cards = [{"name": "sqlmap", "phase": "exploitation", "model": "claude-sonnet-4-6",
              "a2a_peers": ["web-exploit"], "description": "SQLi"}]
    rows = S.roster_rows(cards)
    assert rows[0][0] == "sqlmap" and rows[0][2] == "sonnet-4-6" and rows[0][3] == "1"
    assert S.agent_names(cards) == ["sqlmap"]


def test_budget_render():
    out = S.budget_render(900, 1000, "T-1")
    assert "900/1000" in out and "cerca del techo" in out
    over = S.budget_render(1100, 1000, "T-1")
    assert "techo alcanzado" in over


def test_phase_render_marks_current():
    out = S.phase_render("triage")
    assert "●triage" in out
    assert "✓recon" in out and "○exploitation" in out


def test_evidence_rows():
    eng = {"evidence": [{"ts": "2026-01-01T00:00:00Z", "agent": "web-exploit",
                         "action": "verificar XSS", "target": "app", "artifact_path": "x/y.txt"}]}
    rows = S.evidence_rows(eng)
    assert rows[0][1] == "web-exploit" and "x/y.txt" in rows[0][4]


def test_parse_and_render_rag():
    js = json.dumps({"store": {"total_cves": 1622, "kev_version": "2026.06.10",
                               "kev_last_sync": "2026-06-10"}})
    store = S.parse_rag_store(js)
    assert store and store["total_cves"] == 1622
    out = S.rag_render(store)
    assert "1622" in out and "2026.06.10" in out
    assert "sin poblar" in S.rag_render(None)


# ── actions: escritura (override del operador) ───────────────────────────────────
def test_set_phase_writes_and_validates():
    d = _tmp_engagement(phase="recon")
    ok, msg = A.set_phase(d, "exploitation")
    assert ok, msg
    data = json.loads((d / "contracts" / "engagement.json").read_text(encoding="utf-8"))
    assert data["phase"] == "exploitation" and "updated_at" in data


def test_set_phase_invalid():
    d = _tmp_engagement()
    ok, msg = A.set_phase(d, "inventada")
    assert not ok and "inválida" in msg


def test_set_a2a_status():
    d = _tmp_engagement(messages=[_msg("M1", "a", "b", "pending")])
    ok, msg = A.set_a2a_status(d, "M1", "blocked")
    assert ok, msg
    data = json.loads((d / "contracts" / "engagement.json").read_text(encoding="utf-8"))
    assert data["messages"][0]["status"] == "blocked"
    ok2, _ = A.set_a2a_status(d, "NOPE", "done")
    assert not ok2


def test_set_a2a_status_invalid_status():
    d = _tmp_engagement(messages=[_msg("M1", "a", "b")])
    ok, msg = A.set_a2a_status(d, "M1", "weird")
    assert not ok and "inválido" in msg


def test_set_env_var_replaces_and_preserves():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "bot"))
    env = Path(d) / "bot" / ".env"
    env.write_text("TELEGRAM_TOKEN=abc\nORCH_MODEL=claude-opus-4-8\nALLOWED_USER_ID=1\n",
                   encoding="utf-8")
    ok, msg = A.set_env_var(Path(d), "ORCH_MODEL", "claude-sonnet-4-6")
    assert ok, msg
    txt = env.read_text(encoding="utf-8")
    assert "ORCH_MODEL=claude-sonnet-4-6" in txt
    assert "TELEGRAM_TOKEN=abc" in txt and "ALLOWED_USER_ID=1" in txt  # preserva el resto


def test_set_env_var_rejects_unknown():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "bot"))
    ok, _ = A.set_env_var(Path(d), "ORCH_MODEL", "gpt-9")
    assert not ok
    ok2, _ = A.set_env_var(Path(d), "ORCH_EFFORT", "turbo")
    assert not ok2


def test_compose_delegation_and_peers():
    msg = A.compose_delegation("sqlmap", "confirma la SQLi de /login")
    assert "sqlmap" in msg and "hub" in msg and "scope" in msg
    cards = [{"name": "web-exploit", "a2a_peers": ["sqlmap", "web-fuzzing"]}]
    assert A.peers_of(cards, "web-exploit") == ["sqlmap", "web-fuzzing"]
    assert A.peers_of(cards, "desconocido") == []


def test_rag_refresh_cmd():
    assert A.rag_refresh_cmd()[-1].endswith("refresh.py")
    assert "--epss-all" in A.rag_refresh_cmd(epss_all=True)


# ── runner: ganchos aditivos (sin SDK) ───────────────────────────────────────────
def test_runner_cost_attrs_and_abort():
    from intel.runner import AgentRunner

    async def noop(*a):
        return True

    r = AgentRunner(Path(BOT), emit=noop, status=noop, approve=noop, on_verdict=noop)
    assert r.last_cost_usd is None and r.last_turns is None
    assert r._aborted is False
    r.abort()
    assert r._aborted is True


def test_runner_abort_denies_gate():
    from intel.runner import AgentRunner, SDK_OK
    if not SDK_OK:
        print("    (omitido: Claude Agent SDK no instalado)")
        return
    import asyncio

    async def yes(*a):
        return True

    async def _run():
        r = AgentRunner(Path(BOT), emit=yes, status=yes, approve=yes, on_verdict=yes)
        r.abort()
        # tras abort, hasta un comando benigno se deniega
        return await r._gate("Bash", {"command": "ls -la"}, None)

    res = asyncio.run(_run())
    assert res.behavior == "deny"


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
