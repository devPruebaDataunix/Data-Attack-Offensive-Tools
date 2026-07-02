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
import tui.commands as CMD     # noqa: E402  (catálogo puro; el Provider Textual es opcional)
import tui.theme as T          # noqa: E402  (tokens de color: única fuente)


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
    assert role == "solicitud"   # i18n: rol A2A en español (request -> solicitud)
    assert "confirma SQLi" in preview and emoji == "📨"


def test_a2a_summary_counts_and_hops():
    eng = {"messages": [_msg("M1", "a", "b", "pending", 1), _msg("M2", "b", "a", "done", 40)]}
    out = S.a2a_summary(eng, {"constraints": {"max_a2a_hops": 50}})
    assert "pendiente: 1" in out and "hecho: 1" in out and "40/50" in out   # i18n status A2A
    assert T.WARN in out and T.OK in out    # chips con color por estado (B2)


def test_a2a_message_ids_align_with_rows():
    eng = {"messages": [_msg("M1", "a", "b"), "basura", _msg("M2", "c", "d")]}
    ids = S.a2a_message_ids(eng)
    assert ids == ["M1", "M2"]                       # ignora los no-dict, igual que a2a_rows
    assert len(ids) == len(S.a2a_rows(eng))          # misma longitud/orden -> zip seguro (drill-down)


def test_pending_message_ids():
    eng = {"messages": [_msg("M1", "a", "b", "pending"), _msg("M2", "b", "a", "done")]}
    assert S.pending_message_ids(eng) == ["M1"]


def test_message_detail():
    eng = {"messages": [_msg("M1", "a", "b", "pending", 0, "detalle xyz")]}
    out = S.message_detail(eng, "M1")
    assert "M1" in out and "detalle xyz" in out
    assert "no encontrado" in S.message_detail(eng, "NOPE")


def test_message_detail_escapes_markup():
    # el cuerpo del mensaje (parts) puede traer datos del target: un '[' NO debe romper el modal Rich
    eng = {"messages": [_msg("M1", "a", "b", "pending", 0, "probar [xss] en http://a[b].com")]}
    out = S.message_detail(eng, "M1")
    assert "\\[xss]" in out and "a\\[b].com" in out          # texto libre del mensaje escapado
    assert "\\[evil]" in S.message_detail({}, "[evil]")      # el id no encontrado también se escapa


# ── state: roster, presupuesto, fase, evidencia, RAG ─────────────────────────────
def test_agent_names():
    cards = [{"name": "sqlmap", "phase": "exploitation"}, {"phase": "recon"}]
    assert S.agent_names(cards) == ["sqlmap"]   # ignora cards sin nombre (validación de delegación)


def test_load_lab_routes():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "tools"))
    with open(os.path.join(d, "tools", "routing.nvidia-lab.json"), "w", encoding="utf-8") as f:
        json.dump({"routes": {"sqlmap": "nvidia/openai/gpt-oss-120b",
                              "osint-recon": "nvidia/meta/llama-3.3-70b-instruct"}}, f)
    routes = S.load_lab_routes(Path(d))
    assert routes["sqlmap"] == "gpt-oss-120b"                  # último segmento de la ruta
    assert routes["osint-recon"] == "llama-3.3-70b-instruct"
    assert S.load_lab_routes(Path(tempfile.mkdtemp())) == {}   # sin fichero -> {}


# ── state: panel Agentes por zonas E1/E2/E3 (master-detail, B1) ──────────────────
def test_zone_of():
    assert S.zone_of("recon") == "E1"                       # E1 = recon
    assert S.zone_of("triage") == "E2" and S.zone_of("exploitation") == "E2"
    assert S.zone_of("post-exploitation") == "E2"           # E2 = triage/exploitation/post-exploitation
    assert S.zone_of("reporting") == "E3"                   # E3 = reporting
    assert S.zone_of("orchestrator") == "orch"
    assert S.zone_of("any") == "otro" and S.zone_of("") == "otro"


def test_roster_by_zone_groups_and_counts():
    cards = [
        {"name": "orchestrator", "phase": "orchestrator"},
        {"name": "osint-recon", "phase": "recon", "model": "claude-haiku-4-5"},
        {"name": "sqlmap", "phase": "exploitation", "a2a_peers": ["web-exploit"]},
        {"name": "vuln-triage", "phase": "triage"},
        {"name": "reporting", "phase": "reporting"},
    ]
    grouped = S.roster_by_zone(cards, {"sqlmap": "gpt-oss-120b"})
    assert [z for z, _ in grouped] == ["orch", "E1", "E2", "E3"]   # ZONE_ORDER, sin zonas vacías
    d = dict(grouped)
    assert [r[0] for r in d["E2"]] == ["sqlmap", "vuln-triage"]    # alfabético dentro de la zona
    assert d["E2"][0][3] == "gpt-oss-120b"                         # 4ª col: modelo lab
    assert d["E1"][0][2] == "haiku-4-5"                            # modelo bot sin 'claude-'


def test_agent_detail_full_description():
    desc = "Explota inyecciones SQL con sqlmap y confirma el vector antes de escalar. " * 3
    card = {"name": "sqlmap", "phase": "exploitation", "model": "claude-sonnet-4-6",
            "a2a_peers": ["web-exploit"], "description": desc,
            "capabilities": ["confirmar-sqli"], "tools": ["Bash"]}
    out = S.agent_detail(card, {"sqlmap": "gpt-oss-120b"})
    assert desc in out                                            # descripción COMPLETA, SIN truncar
    assert "sqlmap" in out and "E2" in out and "gpt-oss-120b" in out
    assert "web-exploit" in out and "confirmar-sqli" in out
    assert "Resalta un agente" in S.agent_detail(None)            # empty-state amable


# ── state: pestaña Red multi-host (Paso C) ───────────────────────────────────────
def test_network_rows():
    eng = {"targets": [
        {"asset": "10.0.0.5", "asset_type": "ip", "in_scope": True, "access_level": "root",
         "reachable_via": "direct", "defenses": [{"type": "waf", "confidence": "high"}]},
        {"asset": "10.0.0.9", "asset_type": "ip", "in_scope": True}]}
    rows = S.network_rows(eng)
    assert rows[0][0] == "10.0.0.5" and rows[0][2] == "✓"
    assert "root" in rows[0][3] and T.DANGER in rows[0][3]        # comprometido -> peligro (color)
    assert "waf" in rows[0][5]                                    # defensas resumidas
    assert "none" in rows[1][3] and rows[1][4] == "direct"        # defaults: acceso none, alcance direct


def test_pivot_rows():
    eng = {"pivots": [{"pivot_id": "P1", "tool": "ligolo-ng", "via_target": "10.0.0.5",
                       "status": "up", "reaches_cidr": ["10.1.0.0/24"]}]}
    rows = S.pivot_rows(eng)
    assert rows[0][0] == "P1" and rows[0][1] == "ligolo-ng"
    assert "up" in rows[0][3] and T.OK in rows[0][3] and "10.1.0.0/24" in rows[0][4]


def test_credential_rows_never_leaks_secret():
    eng = {"credentials": [{"cred_id": "C1", "principal": "admin", "type": "ntlm-hash",
                            "secret_ref": "loot/hash.txt", "source_target": "10.0.0.5",
                            "privilege": "admin", "validated_on": ["10.0.0.9"]}]}
    r = S.credential_rows(eng)[0]
    assert r[0] == "C1" and r[1] == "admin" and r[2] == "ntlm-hash" and r[3] == "admin"
    assert r[4] == "10.0.0.5" and r[5] == "1"                     # origen + nº de hosts validados
    assert "loot/hash.txt" not in " ".join(str(x) for x in r)    # NUNCA el secret_ref en la tabla


def test_network_summary_counts_and_empty():
    eng = {"targets": [{"asset": "a", "access_level": "root"}, {"asset": "b"}],
           "pivots": [{"pivot_id": "P1", "status": "up"}],
           "credentials": [{"cred_id": "C1"}]}
    out = S.network_summary(eng)
    assert "hosts: 2" in out and "comprometidos: 1" in out and "pivots activos: 1/1" in out
    assert "Sin hosts" in S.network_summary({})                  # empty-state amable


def test_budget_caption():
    out = S.budget_caption(900, 1000, "T-1")
    assert "900/1000" in out and "cerca del techo" in out
    over = S.budget_caption(1100, 1000, "T-1")
    assert "techo alcanzado" in over


def test_phase_render_marks_current():
    out = S.phase_render("triage")
    assert "● triaje" in out                              # bullet SEPARADO + español (fix glitch "oinit")
    assert "✓ reconocimiento" in out and "○ explotación" in out


def test_phase_es_labels():
    assert S.phase_es("post-exploitation") == "post-explotación"
    assert S.phase_es("desconocida") == "desconocida"    # fase fuera del catálogo: se devuelve tal cual
    assert S.phase_es("ex[b]") == "ex\\[b]"              # fase desconocida con markup: se escapa (defensa)


def test_dashboard_status_empty_and_active():
    grp = {"real": [], "watch": [], "noise": [], "verdicts": []}
    empty = S.dashboard_status(S.Snapshot(eng={}), grp, True)
    assert "Sin engagement" in empty                     # empty-state amable, no un muro de "—"
    snap = S.Snapshot(eng={"engagement_id": "E-1", "phase": "recon"},
                      scope={"in_scope": {"domains": ["a.com"]}})
    out = S.dashboard_status(snap, grp, True)
    assert "E-1" in out and "reconocimiento" in out and "a.com" in out


def test_evidence_header_empty_and_full():
    assert "Sin artefactos" in S.evidence_header([])
    full = S.evidence_header(["GATE-1"])
    assert "GATE-1" in full and "engagements/<id>/" in full   # pista de carpeta (B2)


def test_human_ts():
    assert S.human_ts("2026-07-02T13:42:05.123456Z") == "2026-07-02 13:42"   # sin microsegundos ni Z
    assert S.human_ts("2026-07-02T13:42:05+00:00") == "2026-07-02 13:42"
    assert S.human_ts("") == "—"
    assert S.human_ts("no-es-fecha") == "no-es-fecha"                        # no parsea -> original


def test_evidence_rows():
    eng = {"evidence": [{"ts": "2026-01-01T00:00:00Z", "agent": "web-exploit",
                         "action": "verificar XSS", "target": "app", "artifact_path": "x/y.txt"}]}
    rows = S.evidence_rows(eng)
    assert rows[0][0] == "2026-01-01 00:00"                                   # ts humanizado (B2)
    assert rows[0][1] == "web-exploit" and "x/y.txt" in rows[0][4]


def test_parse_and_render_rag():
    js = json.dumps({"store": {"total_cves": 1622, "kev_version": "2026.06.10",
                               "kev_last_sync": "2026-06-10"}})
    store = S.parse_rag_store(js)
    assert store and store["total_cves"] == 1622
    out = S.rag_render(store)
    assert "1622" in out and "2026.06.10" in out
    assert "sin poblar" in S.rag_render(None)


# ── state: RAG de CONOCIMIENTO (Capa 1 + Capa 2) — panel B.2 ─────────────────────
def test_parse_kb_stats():
    js = json.dumps({"capa1_kb": {"total": 500, "by_source": {"gtfobins": 300, "attack": 200}}})
    rep = S.parse_kb_stats(js)
    assert rep and rep["capa1_kb"]["total"] == 500
    assert S.parse_kb_stats("no json") is None
    assert S.parse_kb_stats(json.dumps({"otro": 1})) is None      # sin capa1_kb -> None


def test_kb_render_populated_both_layers():
    rep = {"capa1_kb": {"total": 512, "by_source": {"gtfobins": 300, "attack": 212},
                        "by_platform": {"linux": 400, "multi": 112}, "by_category": {"privesc": 200}},
           "capa2_kb_vec": {"total": 8123, "by_source": {"hacktricks": 5000, "cyber-skills": 3123},
                            "embed_model": "bge-small-en-v1.5"}}
    out = S.kb_render(rep)
    assert "Capa 1 (kb.db): 512" in out and "gtfobins 300" in out
    assert "Capa 2 (kb_vec.db): 8123" in out and "cyber-skills 3123" in out
    assert "bge-small-en-v1.5" in out


def test_kb_render_empty_and_capa2_unpopulated():
    assert "sin poblar" in S.kb_render(None)                       # nada -> empty-state amable
    assert "sin poblar" in S.kb_render({"capa1_kb": {"total": 0}})  # capa1 vacía -> empty-state
    rep = {"capa1_kb": {"total": 10, "by_source": {"gtfobins": 10}},
           "capa2_kb_vec": {"status": "no poblada (kb_vec.db no existe)"}}
    out = S.kb_render(rep)
    assert "Capa 1 (kb.db): 10" in out and "no poblada" in out     # capa2 sin poblar NO rompe el render


def test_kb_render_capa2_subset_warns():
    rep = {"capa1_kb": {"total": 10, "by_source": {"gtfobins": 10}},
           "capa2_kb_vec": {"total": 5, "by_source": {"hacktricks": 5}, "embed_model": "bge"}}
    out = S.kb_render(rep)
    assert "subset de prueba" in out and "vacía" not in out        # 0<total<2000 -> aviso de subset
    # total==0 es "vacía", no "subset" (un vec DB con 0 trozos está vacío, no es un subset de prueba)
    rep0 = {"capa1_kb": {"total": 10, "by_source": {"gtfobins": 10}},
            "capa2_kb_vec": {"total": 0, "by_source": {}, "embed_model": "bge"}}
    out0 = S.kb_render(rep0)
    assert "vacía" in out0 and "subset de prueba" not in out0


# ── state: orden en curso (observabilidad + recuperación del lock) — A1 ──────────
def test_fmt_duration():
    assert S.fmt_duration(0) == "00:00"
    assert S.fmt_duration(62) == "01:02"
    assert S.fmt_duration(3723) == "1:02:03"      # ≥1h -> h:mm:ss
    assert S.fmt_duration(-5) == "00:00"          # borde negativo -> 00:00


def test_order_stale():
    assert S.order_stale(None, None, 100.0) is False              # sin orden -> nunca stale
    assert S.order_stale(0.0, None, 10.0, timeout=300.0) is False  # arranque reciente, sin beats
    assert S.order_stale(0.0, None, 400.0, timeout=300.0) is True  # sin beats y pasó el timeout
    assert S.order_stale(0.0, 390.0, 400.0, timeout=300.0) is False  # beat reciente -> NO stale
    assert S.order_stale(0.0, 5.0, 400.0, timeout=300.0) is True   # último beat viejo -> stale


def test_order_status_line_idle_and_running():
    assert "sin orden" in S.order_status_line(None, None, 100.0)   # empty-state amable
    out = S.order_status_line("haz recon de a[b].com", started=0.0, now=65.0,
                              turns=3, cost=0.12, last_beat=60.0)
    assert "orden en curso" in out and "01:05" in out              # elapsed 65s -> 01:05
    assert "3 turnos" in out and "$0.12" in out
    assert "a\\[b].com" in out                                     # texto libre escapado (markup Rich)
    stale = S.order_status_line("x", started=0.0, now=400.0, last_beat=5.0, timeout=300.0)
    assert "sin señal" in stale                                    # marca el posible cuelgue


# ── state: historial de órdenes ↑/↓ (A3) ────────────────────────────────────────
def test_cmd_history_navigation():
    h = S.CmdHistory()
    assert h.prev() is None and h.next() is None          # vacío -> no navega (no consume la tecla)
    h.remember("uno"); h.remember("dos")
    assert h.prev() == "dos"                               # ↑ desde el final -> la última
    assert h.prev() == "uno"                               # ↑ -> anterior
    assert h.prev() == "uno"                               # ↑ en el tope -> se queda en la primera
    assert h.next() == "dos"                               # ↓ -> siguiente
    assert h.next() == ""                                  # ↓ pasado el final -> línea en blanco
    assert h.next() == ""                                  # ↓ ya en blanco -> sigue en blanco


def test_cmd_history_dedup_and_blank():
    h = S.CmdHistory()
    h.remember("   ")
    assert h.items() == []                                 # en blanco no se guarda
    h.remember("a"); h.remember("a")
    assert h.items() == ["a"]                              # duplicado consecutivo no se repite
    h.remember("b"); h.remember("a")
    assert h.items() == ["a", "b", "a"]                    # no consecutivo sí se guarda
    assert h.prev() == "a"                                 # tras remember, ↑ empieza por la última


# ── seguridad de render: escape de markup Rich en texto libre del blackboard ─────
def test_esc_neutralizes_rich_markup():
    assert S._esc("a[b]c") == "a\\[b]c"          # '[' -> '\[' (no abre una etiqueta Rich)
    assert S._esc(None) == "" and S._esc("plain") == "plain"


def test_free_text_is_escaped_in_renders():
    # un id/dominio/key/preview con '[' NO debe inyectar markup Rich en la UI (puede venir del target)
    h = S.header_line({"engagement_id": "E[x]", "phase": "recon"}, 1, 10, None, "critical")
    assert "E\\[x]" in h                          # engagement_id escapado en la cabecera
    snap = S.Snapshot(eng={"engagement_id": "E1", "phase": "recon"},
                      scope={"in_scope": {"domains": ["a[b].com"]}})
    d = S.dashboard_status(snap, {"real": [], "watch": [], "noise": [], "verdicts": []}, True)
    assert "a\\[b].com" in d                      # dominio escapado
    assert "K\\[1]" in S.budget_caption(1, 10, "K[1]")        # key del presupuesto
    assert "\\[evil]" in S.evidence_header(["[evil]"])       # nombre de engagement
    rows = S.a2a_rows({"messages": [_msg("M1", "a", "b", "pending", 0, "x[y]z")]})
    assert rows[0][5] == "x\\[y]z"               # preview del bus A2A escapado
    ev = S.evidence_rows({"evidence": [{"ts": "t", "agent": "web-exploit",
                                        "action": "probar [xss]", "target": "a[b].com",
                                        "artifact_path": "x.txt"}]})
    assert ev[0][2] == "probar \\[xss]" and ev[0][3] == "a\\[b].com"   # acción/target escapados


# ── theme: tokens de color (única fuente) y primitivas ───────────────────────────
def test_theme_tokens_are_valid_hex():
    import re
    hexre = re.compile(r"^#[0-9a-fA-F]{6}$")
    for name in ("BRAND", "INFO", "OK", "WARN", "DANGER", "MUTED", "FG", "BG", "SURFACE"):
        val = getattr(T, name)
        assert hexre.match(val), f"{name}={val!r} no es un hex #rrggbb"
    assert T.BRAND != T.DANGER    # el rojo de MARCA y el rojo de PELIGRO son distintos (no se confunden)


def test_theme_css_vars_cover_tokens():
    # cada variable CSS que inyecta app.py apunta a un token real (misma fuente para CSS y markup)
    assert T.CSS_VARS["brand"] == T.BRAND and T.CSS_VARS["info"] == T.INFO
    assert T.CSS_VARS["danger"] == T.DANGER and T.CSS_VARS["ok"] == T.OK
    for name in ("brand", "info", "ok", "warn", "danger", "muted", "fg", "bg", "surface2"):
        assert name in T.CSS_VARS and T.CSS_VARS[name].startswith("#")


def test_panel_title_is_bold_info():
    assert T.panel_title("Bus A2A") == f"[b {T.INFO}]Bus A2A[/]"   # cabecera única: azul info, negrita


def test_finding_bucket_icon_and_color():
    assert T.finding_bucket("real") == ("●", T.DANGER)
    assert T.finding_bucket("watch") == ("▲", T.WARN)
    assert T.finding_bucket("noise") == ("·", T.MUTED)
    icons = {T.finding_bucket(k)[0] for k in ("real", "watch", "noise")}
    assert len(icons) == 3       # colorblind-safe: 3 iconos DISTINTOS (el significado no es solo el color)


def test_phase_render_active_is_brand():
    out = S.phase_render("triage")
    assert f"[b {T.BRAND}]● triaje[/]" in out       # fase activa: rojo de marca ("estás aquí")
    assert f"[{T.OK}]✓ reconocimiento[/]" in out     # completada: verde
    assert f"[{T.MUTED}]○ explotación[/]" in out     # pendiente: atenuado


def test_dashboard_kpis_uses_bucket_icons():
    snap = S.Snapshot(eng={"engagement_id": "E-1", "phase": "recon"},
                      scope={"in_scope": {"domains": ["a.com"]}}, cost=0.5)
    kpis = S.dashboard_kpis(snap, {"real": [1], "watch": [], "noise": [], "verdicts": []})
    assert len(kpis) == 5                                                     # fase·reales·vigilar·ruido·coste
    joined = " ".join(kpis)
    assert "● reales" in joined and "▲ vigilar" in joined and "· ruido" in joined
    assert T.DANGER in joined and T.WARN in joined                            # color de token por bucket
    assert "1" in kpis[1] and "$0.50" in kpis[4]                              # 1 real · coste formateado


def test_budget_caption_uses_token_colors():
    assert T.OK in S.budget_caption(1, 1000, "T")          # holgado -> verde
    assert T.WARN in S.budget_caption(900, 1000, "T")      # cerca del techo -> ámbar
    assert T.DANGER in S.budget_caption(1100, 1000, "T")   # techo superado -> coral


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


# ── actions: arranque de lab (objetivo → scope.json, A2) ─────────────────────────
def test_classify_targets():
    ips, cidrs, domains, bad = A.classify_targets("172.17.0.2, 10.0.0.0/24, ejemplo.com, ; ")
    assert ips == ["172.17.0.2"] and cidrs == ["10.0.0.0/24"] and domains == ["ejemplo.com"]
    assert bad == []
    _, _, _, bad2 = A.classify_targets("no_valido, 999.1.1.1")
    assert "no_valido" in bad2 and "999.1.1.1" in bad2       # dominio falso e IP fuera de rango
    ips3, _, _, _ = A.classify_targets("1.1.1.1, 1.1.1.1")    # sin duplicados, conserva orden
    assert ips3 == ["1.1.1.1"]


def test_classify_targets_rejects_broad_cidr():
    # un CIDR de ruta por defecto / demasiado amplio abriría scope_guard a rangos enormes -> se rechaza
    _, cidrs, _, bad = A.classify_targets("10.0.0.0/24, 0.0.0.0/0, ::/0, 10.0.0.0/8, 172.16.0.0/12")
    assert cidrs == ["10.0.0.0/24"]                          # solo el /24 de lab sobrevive
    for broad in ("0.0.0.0/0", "::/0", "10.0.0.0/8", "172.16.0.0/12"):
        assert broad in bad
    _, cidrs6, _, _ = A.classify_targets("fd00::/64")        # /64 IPv6 sí es aceptable
    assert cidrs6 == ["fd00::/64"]


def test_build_lab_scope_valid_and_forces_no_harm():
    ok, sc = A.build_lab_scope("172.17.0.2", "TOKENASO", "auto")
    assert ok
    assert sc["in_scope"]["ips"] == ["172.17.0.2"] and sc["engagement_id"] == "TOKENASO"
    assert sc["constraints"]["approval_mode"] == "auto"
    # no-daño NUNCA se relaja desde el panel: forzado a True aunque no se pida
    assert sc["constraints"]["no_dos"] is True
    assert sc["constraints"]["no_social_engineering"] is True
    assert sc["constraints"]["no_data_exfiltration_real"] is True


def test_build_lab_scope_default_eid_and_rejections():
    ok, sc = A.build_lab_scope("10.10.10.5", "", "auto")
    assert ok and sc["engagement_id"] == "LAB-10.10.10.5"     # eid por defecto desde el 1er objetivo
    bad_mode, m1 = A.build_lab_scope("10.10.10.5", "x", "turbo")
    assert not bad_mode and "supervisión" in m1
    no_t, _ = A.build_lab_scope("   ", "x", "auto")
    assert not no_t                                           # sin objetivos válidos
    bad_eid, _ = A.build_lab_scope("10.10.10.5", "bad id!", "auto")
    assert not bad_eid                                        # eid con caracteres inválidos


def test_build_lab_scope_forces_no_dos_and_isolates_client_data():
    ok, sc = A.build_lab_scope("10.0.0.1", "L", "critical",
                               base={"client": "ACME Corp",
                                     "constraints": {"no_dos": False, "max_actions": 250},
                                     "out_of_scope": {"ips": ["10.0.0.9"], "domains": [], "notes": "n"}})
    assert ok
    assert sc["constraints"]["no_dos"] is True                # peligroso -> se fuerza, no se relaja
    assert sc["constraints"]["max_actions"] == 250            # cap operativo no peligroso -> se preserva
    assert sc["constraints"]["approval_mode"] == "critical"
    # higiene de datos: un lab NO hereda client ni out_of_scope de un engagement anterior
    assert sc["client"] == "L"
    assert sc["out_of_scope"] == {"domains": [], "ips": [], "notes": ""}


def test_set_lab_scope_writes_backup_and_audits():
    d = _tmp_engagement()                                     # crea contracts/engagement.json válido
    (d / "contracts" / "scope.json").write_text(
        '{"engagement_id":"OLD","in_scope":{"ips":["1.1.1.1"]}}', encoding="utf-8")
    ok, msg = A.set_lab_scope(d, "172.17.0.2, 10.0.0.0/24", "TOKENASO", "auto")
    assert ok, msg
    sc = json.loads((d / "contracts" / "scope.json").read_text(encoding="utf-8"))
    assert sc["in_scope"]["ips"] == ["172.17.0.2"] and sc["in_scope"]["cidrs"] == ["10.0.0.0/24"]
    assert sc["constraints"]["approval_mode"] == "auto"
    bak = json.loads((d / "contracts" / "scope.json.bak").read_text(encoding="utf-8"))
    assert bak["engagement_id"] == "OLD"                      # backup del scope anterior
    eng = json.loads((d / "contracts" / "engagement.json").read_text(encoding="utf-8"))
    assert any(e.get("agent") == "operator" and "set_lab_scope" in e.get("action", "")
               for e in eng.get("evidence", []))             # auditado en evidence[]


def test_set_lab_scope_rejects_invalid_without_writing():
    d = _tmp_engagement()
    ok, _ = A.set_lab_scope(d, "no-es-target", "x", "auto")
    assert not ok
    assert not (d / "contracts" / "scope.json").exists()      # no escribe nada si es inválido


def test_compose_lab_run_mentions_scope_and_targets():
    t = A.compose_lab_run("172.17.0.2")
    assert "172.17.0.2" in t and "scope.json" in t.lower() and "AGENTS.md" in t


# ── commands: catálogo de la paleta de dominio (Ctrl+P) ──────────────────────────
def test_command_specs_cover_tabs_and_approval():
    specs = CMD.command_specs()
    keys = [s.key for s in specs]
    assert len(keys) == len(set(keys))                       # claves únicas
    for tab_id, label in CMD.TABS:                           # navegación a cada pestaña
        assert f"tab:{tab_id}" in keys
        assert any(s.title == f"Ir a: {label}" for s in specs)
    for mode in A.APPROVAL_MODES:                            # un comando por modo de supervisión
        assert f"approval:{mode}" in keys
    for k in ("refresh", "abort", "rag-refresh", "rag-refresh-epss", "focus-cmd", "quit"):
        assert k in keys                                     # atajos de dominio presentes


def test_command_specs_are_spanish_and_described():
    specs = CMD.command_specs()
    for s in specs:
        assert s.title.strip() and s.help.strip()            # nada vacío
    joined = " ".join((s.title + " " + s.help).lower() for s in specs)
    for english in ("quit", "theme", "search", "keys", "screenshot", "maximize", "palette"):
        assert english not in joined                         # sin los genéricos ingleses (título + ayuda)


# ── runner: ganchos aditivos (sin SDK) ───────────────────────────────────────────
def test_runner_cost_attrs_and_abort():
    from intel.runner import AgentRunner

    async def noop(*a):
        return True

    r = AgentRunner(Path(BOT), emit=noop, status=noop, approve=noop, on_verdict=noop)
    assert r.last_cost_usd is None and r.last_turns is None
    # telemetría en vivo (A1): arranca en cero; _beat() marca actividad para el auto-timeout del lock
    assert r.live_turns == 0 and r.last_beat == 0.0 and r.started_at is None
    r._beat()
    assert r.last_beat > 0.0
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


# ── supervisión configurable: resolución de modo (runner, sin SDK) ───────────────
def test_runner_resolves_approval_mode_default_and_env():
    from intel.runner import AgentRunner

    async def noop(*a):
        return True

    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "contracts"))   # repo sin scope.json -> default
    prev = os.environ.pop("ORCH_APPROVAL_MODE", None)
    try:
        assert AgentRunner(Path(d), noop, noop, noop, noop).approval_mode == "critical"
        os.environ["ORCH_APPROVAL_MODE"] = "auto"
        assert AgentRunner(Path(d), noop, noop, noop, noop).approval_mode == "auto"
        os.environ["ORCH_APPROVAL_MODE"] = "weird"   # inválido -> critical
        assert AgentRunner(Path(d), noop, noop, noop, noop).approval_mode == "critical"
        # explícito gana sobre env
        assert AgentRunner(Path(d), noop, noop, noop, noop, approval_mode="full").approval_mode == "full"
    finally:
        os.environ.pop("ORCH_APPROVAL_MODE", None)
        if prev is not None:
            os.environ["ORCH_APPROVAL_MODE"] = prev


def test_runner_approval_mode_from_scope():
    from intel.runner import AgentRunner

    async def noop(*a):
        return True

    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "contracts"))
    with open(os.path.join(d, "contracts", "scope.json"), "w", encoding="utf-8") as f:
        json.dump({"constraints": {"approval_mode": "full"}}, f)
    prev = os.environ.pop("ORCH_APPROVAL_MODE", None)
    try:
        assert AgentRunner(Path(d), noop, noop, noop, noop).approval_mode == "full"
    finally:
        if prev is not None:
            os.environ["ORCH_APPROVAL_MODE"] = prev


# ── supervisión configurable: hook approval_gate.py (subproceso real, sin SDK) ────
def _gate(mode, command, tool="Bash"):
    import subprocess
    hook = Path(BOT).parent / ".claude" / "hooks" / "approval_gate.py"
    env = dict(os.environ); env["ORCH_APPROVAL_MODE"] = mode
    p = subprocess.run([sys.executable, str(hook)],
                       input=json.dumps({"tool_name": tool, "tool_input": {"command": command}}),
                       capture_output=True, text=True, cwd=str(Path(BOT).parent), env=env)
    out = (p.stdout or "").strip()
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else None


def test_approval_gate_auto_allows_risky():
    assert _gate("auto", "nmap -sV 10.0.0.1") == "allow"


def test_approval_gate_critical_allows_normal_but_asks_critical():
    assert _gate("critical", "nmap -sV 10.0.0.1") == "allow"      # normal -> auto-aprobado
    assert _gate("critical", "sqlmap -u http://x --batch") == "allow"  # sensitive -> auto-aprobado
    assert _gate("critical", "sliver-server") == "ask"            # crítico -> aprobación


def test_approval_gate_full_asks_risky():
    assert _gate("full", "nmap -sV 10.0.0.1") == "ask"
    assert _gate("full", "sliver-server") == "ask"


def test_approval_gate_safe_always_allows():
    assert _gate("full", "subfinder -d acme.example") == "allow"
    assert _gate("critical", "whois acme.example") == "allow"


def test_approval_gate_ignores_non_bash():
    assert _gate("full", "anything", tool="Read") is None


def test_state_resolve_approval_mode():
    assert S.resolve_approval_mode(None) == "critical"
    assert S.resolve_approval_mode({"constraints": {"approval_mode": "auto"}}) == "auto"
    assert S.resolve_approval_mode({"constraints": {"approval_mode": "raro"}}) == "critical"
    # override (p.ej. bot/.env) gana sobre el scope
    assert S.resolve_approval_mode({"constraints": {"approval_mode": "full"}}, "auto") == "auto"


def test_header_line_shows_supervision_mode():
    out = S.header_line({"engagement_id": "T", "phase": "recon"}, 5, 100, 1.23, "critical")
    assert "supervisión" in out and "crítica" in out   # i18n: modo de supervisión en español
    assert "reconocimiento" in out   # i18n: la fase se muestra en español en la cabecera


def test_set_env_var_approval_mode():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "bot"))
    ok, _ = A.set_env_var(Path(d), "ORCH_APPROVAL_MODE", "auto")
    assert ok
    bad, _ = A.set_env_var(Path(d), "ORCH_APPROVAL_MODE", "turbo")
    assert not bad


# ── auditoría de subagentes: hook subagent_stop.py (subproceso real) ──────────────
def _subagent_stop(payload, audit_dir):
    import subprocess
    hook = Path(BOT).parent / ".claude" / "hooks" / "subagent_stop.py"
    env = dict(os.environ); env["ORCH_AUDIT_DIR"] = str(audit_dir)
    body = payload if isinstance(payload, str) else json.dumps(payload)
    p = subprocess.run([sys.executable, str(hook)], input=body,
                       capture_output=True, text=True, cwd=str(Path(BOT).parent), env=env)
    log = Path(audit_dir) / "subagents.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return p.returncode, lines


def test_subagent_stop_writes_audit_line():
    rc, lines = _subagent_stop(
        {"hook_event_name": "SubagentStop", "agent_type": "sliver",
         "agent_id": "a-123", "session_id": "s-1", "transcript_path": "/t.jsonl"},
        tempfile.mkdtemp())
    assert rc == 0 and len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["event"] == "SubagentStop" and rec["agent_type"] == "sliver"
    assert rec["agent_id"] == "a-123" and rec.get("ts")


def test_subagent_stop_appends():
    d = tempfile.mkdtemp()
    _subagent_stop({"hook_event_name": "SubagentStop", "agent_type": "nuclei"}, d)
    rc, lines = _subagent_stop({"hook_event_name": "SubagentStop", "agent_type": "sqlmap"}, d)
    assert rc == 0 and len(lines) == 2


def test_subagent_stop_failsafe_on_bad_input():
    rc, lines = _subagent_stop("{not json", tempfile.mkdtemp())
    assert rc == 0 and lines == []


def test_subagent_stop_ignores_other_events():
    rc, lines = _subagent_stop({"hook_event_name": "PreToolUse", "agent_type": "x"},
                               tempfile.mkdtemp())
    assert rc == 0 and lines == []


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
