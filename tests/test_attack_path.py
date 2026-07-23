#!/usr/bin/env python3
"""Tests del EXPORTADOR DE ATTACK-PATH (mejora v2.59 — idea de VulneraMCP).

Cubre `tools/attack_path.py`: construcción determinista del grafo (nodos/aristas), reuso del gate F
(proof_state/reportable), NO fuga de datos E3 (whitelist), GraphML bien formado + escape XML, y el
confinamiento de `--out` a engagements/ (por subprocess).

    python tests/test_attack_path.py    (sale 1 si algo falla).
"""
import json
import os
import subprocess
import sys
from xml.etree import ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
_fail = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _fail.append(name)


import attack_path as ap  # noqa: E402

# Blackboard de muestra: cadena multi-host con pivot, credencial reusada y findings con E3 en campos
# que NO deben exportarse (evidence/secret_ref/notes).
BB = {
    "engagement_id": "ENG-1",
    "scope_ref": "s", "phase": "post-exploitation",
    "targets": [
        {"target_id": "t-dmz", "asset": "app.acme.example", "asset_type": "url", "in_scope": True,
         "discovered_by": "active-recon", "access_level": "root", "reachable_via": "direct",
         "open_ports": [{"port": 443, "protocol": "tcp", "service": "https", "banner": "SECRET-BANNER"}],
         "defenses": [{"type": "waf", "confidence": "high", "evidence": "CF-RAY leaked xyz"}]},
        {"target_id": "t-internal", "asset": "10.0.0.5", "asset_type": "ip", "in_scope": True,
         "discovered_by": "lateral-discovery", "access_level": "none", "reachable_via": "piv-1"},
    ],
    "pivots": [
        {"pivot_id": "piv-1", "tool": "ligolo-ng", "via_target": "t-dmz", "status": "up",
         "reaches_cidr": ["10.0.0.0/24"]},
    ],
    "credentials": [
        {"cred_id": "c-1", "type": "ntlm-hash", "source_target": "t-dmz",
         "secret_ref": "engagements/ENG-1/loot/hash.txt", "validated_on": ["t-internal"]},
    ],
    "findings": [
        {"finding_id": "F1", "target_id": "t-dmz", "title": "SQLi en /buscar", "status": "exploited",
         "severity": "critical", "evidence": "SUPER-SECRET-DUMP", "reproduction": "paso privado",
         "notes": "cliente confidencial", "next_step": {"suggested_agent": "post-exploit", "technique": "T1059"}},
        {"finding_id": "F2", "target_id": "t-internal", "title": "versión vulnerable", "status": "candidate",
         "severity": "high"},  # speculative -> NO reportable
        {"finding_id": "F3", "target_id": "t-dmz", "title": "Citrix CVE-2023-x", "status": "candidate",
         "severity": "high", "proof_state": "roe-capped", "cve": ["CVE-2023-x"]},  # roe-capped -> reportable
    ],
}

g = ap.build_graph(BB)
nodes = {n["id"]: n for n in g["nodes"]}
edges = g["edges"]


def has_edge(s, t, rel):
    return any(e["source"] == s and e["target"] == t and e["relation"] == rel for e in edges)


# ── nodos ────────────────────────────────────────────────────────────────────────
check("nodo operator raíz", nodes.get("operator", {}).get("type") == "operator")
check("nodo target t-dmz", nodes.get("t-dmz", {}).get("type") == "target")
check("nodo pivot piv-1", nodes.get("piv-1", {}).get("type") == "pivot")
check("nodo finding F1", nodes.get("F1", {}).get("type") == "finding")
check("target lleva access_level", nodes["t-dmz"]["access_level"] == "root")
check("servicios resumidos (sin banner crudo)",
      nodes["t-dmz"]["services"] == ["443/tcp https"])
check("defensas: tipo+confianza sin evidence", nodes["t-dmz"]["defenses"] == [{"type": "waf", "confidence": "high"}])

# ── aristas: cadena multi-host ─────────────────────────────────────────────────────
check("operator -> t-dmz (direct-access)", has_edge("operator", "t-dmz", "direct-access"))
check("t-internal NO es direct (va por pivot)", not has_edge("operator", "t-internal", "direct-access"))
check("t-dmz -> piv-1 (pivots-through)", has_edge("t-dmz", "piv-1", "pivots-through"))
check("piv-1 -> t-internal (reaches)", has_edge("piv-1", "t-internal", "reaches"))
check("t-dmz -> F1 (has-finding)", has_edge("t-dmz", "F1", "has-finding"))
check("cred-reuse t-dmz -> t-internal", has_edge("t-dmz", "t-internal", "cred-reuse"))

# ── reuso del gate F ───────────────────────────────────────────────────────────────
check("F1 proof_state proven-by-exploit + reportable",
      nodes["F1"].get("proof_state") == "proven-by-exploit" and nodes["F1"].get("reportable") is True)
check("F2 speculative -> NO reportable", nodes["F2"].get("reportable") is False)
check("F3 roe-capped -> reportable (rescatado)",
      nodes["F3"].get("proof_state") == "roe-capped" and nodes["F3"].get("reportable") is True)
check("F1 next_step exportado", nodes["F1"].get("next_step", {}).get("suggested_agent") == "post-exploit")

# ── NO fuga E3: whitelist ──────────────────────────────────────────────────────────
blob = ap.to_json(g)
leaks = ["SUPER-SECRET-DUMP", "SECRET-BANNER", "engagements/ENG-1/loot/hash.txt", "paso privado",
         "cliente confidencial", "CF-RAY leaked", "secret_ref", "evidence", "reproduction"]
check("JSON no filtra evidence/secret_ref/notes/banner (whitelist)",
      not any(s in blob for s in leaks))

# ── determinismo ───────────────────────────────────────────────────────────────────
check("build_graph determinista", ap.to_json(ap.build_graph(BB)) == blob)

# ── GraphML: bien formado + escape ─────────────────────────────────────────────────
BB_X = dict(BB, targets=[{"target_id": "tx", "asset": "<script>&\"]]>", "in_scope": True,
                          "discovered_by": "active-recon"}], pivots=[], credentials=[], findings=[])
xml = ap.to_graphml(ap.build_graph(BB_X))
try:
    root = ET.fromstring(xml)
    well_formed = True
except ET.ParseError:
    well_formed = False
check("GraphML con asset hostil (<script>/&/]]>) es XML bien formado", well_formed)
check("GraphML no filtra E3 en el grafo grande",
      not any(s in ap.to_graphml(g) for s in ["SUPER-SECRET-DUMP", "SECRET-BANNER", "loot/hash.txt"]))

# ── CLI + confinamiento de --out (subprocess) ───────────────────────────────────────
scr = os.path.join(ROOT, "tools", "attack_path.py")
bb_tmp = os.path.join(ROOT, "engagements", "_test_attack_path.json")
os.makedirs(os.path.dirname(bb_tmp), exist_ok=True)
with open(bb_tmp, "w", encoding="utf-8") as f:
    json.dump(BB, f)
try:
    r = subprocess.run([sys.executable, scr, "--engagement", bb_tmp, "--format", "graphml"],
                       capture_output=True, text=True)
    check("CLI graphml a stdout -> exit 0 + <graphml>", r.returncode == 0 and "<graphml" in r.stdout)
    # --out fuera de engagements/ -> rechazado
    r2 = subprocess.run([sys.executable, scr, "--engagement", bb_tmp, "--out", "tools/pwned.json"],
                        capture_output=True, text=True)
    check("--out fuera de engagements/ -> rechazado (exit 3)", r2.returncode == 3)
    check("no se escribió el fichero fuera de zona", not os.path.exists(os.path.join(ROOT, "tools", "pwned.json")))
    # --out con traversal -> rechazado
    r3 = subprocess.run([sys.executable, scr, "--engagement", bb_tmp,
                         "--out", "engagements/../tools/pwned2.json"], capture_output=True, text=True)
    check("--out con traversal (..) -> rechazado", r3.returncode == 3
          and not os.path.exists(os.path.join(ROOT, "tools", "pwned2.json")))
    # --out válido bajo engagements/ -> escribe
    r4 = subprocess.run([sys.executable, scr, "--engagement", bb_tmp, "--format", "json",
                         "--out", "engagements/_ap_out/graph.json"], capture_output=True, text=True)
    check("--out bajo engagements/ -> exit 0 + fichero creado",
          r4.returncode == 0 and os.path.exists(os.path.join(ROOT, "engagements", "_ap_out", "graph.json")))
finally:
    for p in [bb_tmp, os.path.join(ROOT, "engagements", "_ap_out", "graph.json")]:
        try:
            os.remove(p)
        except OSError:
            pass
    try:
        os.rmdir(os.path.join(ROOT, "engagements", "_ap_out"))
    except OSError:
        pass

# ── integridad referencial: aristas colgantes descartadas (corrección MENOR-1) ──────
BB_DANGLE = {
    "engagement_id": "E", "scope_ref": "s", "phase": "recon",
    "targets": [{"target_id": "t1", "asset": "a", "in_scope": True, "discovered_by": "active-recon",
                 "reachable_via": "piv-GHOST"}],
    "pivots": [], "credentials": [{"cred_id": "c", "type": "token", "source_target": "t-GHOST",
                                   "validated_on": ["t1"]}],
    "findings": [{"finding_id": "F", "target_id": "t-NOPE", "title": "x", "status": "candidate",
                  "severity": "low"}],
}
gd = ap.build_graph(BB_DANGLE)
ids_d = {n["id"] for n in gd["nodes"]}
check("ninguna arista cuelga de un nodo inexistente",
      all(e["source"] in ids_d and e["target"] in ids_d for e in gd["edges"]))

# ── dedup de ids (corrección MENOR-2): GraphML con id único ──────────────────────────
BB_DUP = {"engagement_id": "E", "scope_ref": "s", "phase": "recon",
          "targets": [{"target_id": "X", "asset": "a", "in_scope": True, "discovered_by": "active-recon"},
                      {"target_id": "X", "asset": "b", "in_scope": True, "discovered_by": "active-recon"}],
          "pivots": [{"pivot_id": "X", "tool": "chisel", "via_target": "X", "status": "up"}],
          "findings": []}
gdup = ap.build_graph(BB_DUP)
check("ids de nodo únicos (dedup) -> sin <node> duplicados",
      len([n["id"] for n in gdup["nodes"]]) == len({n["id"] for n in gdup["nodes"]}))

# ── false_positive / out_of_scope -> reportable False (corrección hueco #3) ──────────
BB_FP = dict(BB, findings=[{"finding_id": "FP", "target_id": "t-dmz", "title": "x",
                            "status": "false_positive", "severity": "high"},
                           {"finding_id": "OOS", "target_id": "t-dmz", "title": "y",
                            "status": "out_of_scope", "severity": "high"}])
nfp = {n["id"]: n for n in ap.build_graph(BB_FP)["nodes"]}
check("false_positive -> reportable False", nfp["FP"].get("reportable") is False)
check("out_of_scope -> reportable False", nfp["OOS"].get("reportable") is False)

# ── grafo vacío (sin targets) -> JSON+GraphML válidos con solo operator ──────────────
ge = ap.build_graph({"engagement_id": "E", "scope_ref": "s", "phase": "init", "targets": [], "findings": []})
check("grafo vacío -> solo nodo operator", [n["id"] for n in ge["nodes"]] == ["operator"])
try:
    ET.fromstring(ap.to_graphml(ge))
    empty_ok = True
except ET.ParseError:
    empty_ok = False
check("grafo vacío -> GraphML bien formado", empty_ok)

# ── redacción de userinfo en labels (seguridad MENOR-1) ─────────────────────────────
BB_CREDS = dict(BB, targets=[{"target_id": "tc", "asset": "http://admin:S3cr3t@app.example",
                              "in_scope": True, "discovered_by": "active-recon"}],
                pivots=[], credentials=[], findings=[])
nc = {n["id"]: n for n in ap.build_graph(BB_CREDS)["nodes"]}
check("label redacta user:pass@ de la URL",
      nc["tc"]["label"] == "http://app.example" and "S3cr3t" not in ap.to_json(ap.build_graph(BB_CREDS)))

# ── CLI: JSON inválido / no-dict -> exit 2 (corrección hueco #6) ─────────────────────
bad = os.path.join(ROOT, "engagements", "_bad_ap.json")
os.makedirs(os.path.dirname(bad), exist_ok=True)
try:
    with open(bad, "w", encoding="utf-8") as f:
        f.write("{not json")
    rb = subprocess.run([sys.executable, scr, "--engagement", bad], capture_output=True, text=True)
    check("CLI con JSON inválido -> exit 2", rb.returncode == 2)
    with open(bad, "w", encoding="utf-8") as f:
        f.write("[1,2,3]")  # JSON válido pero no-dict
    rb2 = subprocess.run([sys.executable, scr, "--engagement", bad], capture_output=True, text=True)
    check("CLI con JSON no-dict -> exit 2", rb2.returncode == 2)
finally:
    try:
        os.remove(bad)
    except OSError:
        pass

print()
if _fail:
    print(f"FALLOS: {len(_fail)} -> {_fail}")
    sys.exit(1)
print("TODOS OK")
