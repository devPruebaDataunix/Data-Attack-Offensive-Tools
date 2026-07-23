#!/usr/bin/env python3
"""
attack_path.py — Exporta el GRAFO DE ATAQUE del engagement (mejora v2.59; idea de VulneraMCP, MIT →
reimplementación limpia, solo stdlib). El blackboard (`contracts/engagement.json`) YA ES el grafo: los
`targets[]` son nodos, `findings[].target_id` los cuelga de su activo, los `pivots[]` (via_target →
reachable_via) trazan el movimiento lateral y las `credentials[]` (source_target → validated_on[]) la
propagación de credenciales. Este exportador lo VUELCA a un formato estándar (JSON node/edge o **GraphML**)
para que el dashboard lo RENDERICE (extiende `NetworkGraph`, modo cadena) sin re-derivar la topología.

Determinista y SOLO-LECTURA (no toca la red, no muta el blackboard). Reusa el gate de la mejora F
(`blackboard.effective_proof_state`/`is_reportable`) para etiquetar cada finding con su grado de prueba y
si es reportable — misma verdad que el informe, sin divergir.

Seguridad / zona:
- **Sin fugas E3.** Se exporta por WHITELIST de campos ESTRUCTURALES (ids, asset, título, severidad,
  estado, proof_state, access_level, puertos/servicios, tipos de defensa). NUNCA `evidence`,
  `reproduction`, `impact`, `remediation`, `notes`, ni ninguna `*_ref`/`secret_ref`/valor de credencial —
  el grafo es una vista de topología, no un volcado de material sensible.
- **Escritura confinada.** Por defecto emite a STDOUT (compón con `>`); con `--out` escribe SOLO bajo
  `engagements/` del repo (realpath-confinado, rechaza traversal/symlink), donde ya viven los artefactos.
- **GraphML con escape.** Todo texto va escapado (XML) — un `asset`/título hostil (`<script>`, `]]>`, `&`)
  no puede romper el documento ni inyectar marcado. El consumidor (dashboard `NetworkGraph`) DEBE pintar
  `label` como TEXTO (nunca `innerHTML`): el JSON no escapa (no lo necesita), la seguridad del render es
  suya.
- **Campos de identidad sin secretos.** `asset`/título/`cred_id` NO deben portar credenciales; como
  cinturón, `_redact_label` colapsa el userinfo de una URL (`scheme://user:pass@host` → `scheme://host`)
  antes de exportar. Un secreto mal ubicado en un `cred_id` es responsabilidad de disciplina del operador.

Uso:
    python tools/attack_path.py                         # JSON a stdout (blackboard por defecto)
    python tools/attack_path.py --format graphml
    python tools/attack_path.py --format graphml --out engagements/<id>/report/attack-path.graphml
    python tools/attack_path.py --engagement contracts/engagement.json --format json
"""
import argparse
import json
import os
import re
import sys
from xml.sax.saxutils import escape, quoteattr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGAGEMENT = os.path.join(ROOT, "contracts", "engagement.json")

sys.path.insert(0, os.path.join(ROOT, "tools"))
try:
    from blackboard import effective_proof_state, is_reportable
except Exception:  # noqa: BLE001 — sin blackboard, no etiquetamos proof_state (fail-soft, no bloquea)
    effective_proof_state = is_reportable = None

_DIRECT = ("", "direct", None)
# Credenciales embebidas en una URL de identidad (scheme://user:pass@host). Los campos de identidad
# (asset/título) NO deben portar secretos; esto es un cinturón por si acaso, porque el grafo va al
# dashboard (audiencia MÁS amplia que el informe).
_USERINFO_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*://)[^/@\s]*@")


def _redact_label(s):
    """Redacta el userinfo de una URL de identidad (scheme://user:pass@host -> scheme://host)."""
    return _USERINFO_RE.sub(r"\1", s) if isinstance(s, str) else s


def _svc(t):
    """Resumen NO sensible de puertos abiertos: 'port/proto service' (sin banners crudos)."""
    out = []
    for p in (t.get("open_ports") or []):
        if not isinstance(p, dict):
            continue
        port, proto, svc = p.get("port"), p.get("protocol", "tcp"), p.get("service", "")
        if port is not None:
            out.append(f"{port}/{proto}" + (f" {svc}" if svc else ""))
    return out


def _defenses(t):
    """Tipos de defensa + confianza (sin el texto de `evidence`, que puede llevar detalle sensible)."""
    out = []
    for d in (t.get("defenses") or []):
        if isinstance(d, dict) and d.get("type"):
            out.append({"type": d.get("type"), "confidence": d.get("confidence", "")})
    return out


def build_graph(data):
    """Blackboard -> {'nodes': [...], 'edges': [...]}. Puro y determinista (respeta el orden de entrada).

    Nodos: operator (raíz única), target, finding, pivot. Aristas: direct-access (operator→target
    alcanzable directo), reaches (pivot→target interno), pivots-through (target comprometido→pivot),
    has-finding (target→finding), cred-reuse (source_target→validated_on por credencial)."""
    if not isinstance(data, dict):
        raise ValueError("el blackboard no es un objeto JSON")
    nodes, edges = [], []
    seen = set()  # espacio ÚNICO de ids del grafo: dedup para no emitir <node> duplicados (GraphML exige id único)
    eid = data.get("engagement_id", "engagement")

    def add_node(node):
        if node["id"] in seen:
            return
        seen.add(node["id"])
        nodes.append(node)

    # Raíz: el operador.
    add_node({"id": "operator", "type": "operator", "label": "operator", "engagement": eid})

    for t in (data.get("targets") or []):
        if not isinstance(t, dict):
            continue
        tid = t.get("target_id")
        if not tid:
            continue
        reach = t.get("reachable_via")
        add_node({
            "id": tid, "type": "target", "label": _redact_label(t.get("asset", tid)),
            "asset_type": t.get("asset_type", ""), "in_scope": bool(t.get("in_scope")),
            "access_level": t.get("access_level", "none"),
            "reachable_via": reach if reach not in _DIRECT else "direct",
            "services": _svc(t), "defenses": _defenses(t),
        })
        if reach in _DIRECT:
            edges.append({"source": "operator", "target": tid, "relation": "direct-access"})
        elif reach != tid:  # reachable_via == pivot_id ⇒ el pivot ALCANZA este host interno (sin self-loop)
            edges.append({"source": reach, "target": tid, "relation": "reaches"})

    for p in (data.get("pivots") or []):
        if not isinstance(p, dict):
            continue
        pid = p.get("pivot_id")
        if not pid:
            continue
        add_node({
            "id": pid, "type": "pivot", "label": p.get("tool", pid),
            "tool": p.get("tool", ""), "status": p.get("status", ""),
            "reaches_cidr": list(p.get("reaches_cidr") or []),
        })
        via = p.get("via_target")
        if via:  # el host comprometido que se atraviesa
            edges.append({"source": via, "target": pid, "relation": "pivots-through"})

    for f in (data.get("findings") or []):
        if not isinstance(f, dict):
            continue
        fid = f.get("finding_id")
        if not fid:
            continue
        node = {
            "id": fid, "type": "finding", "label": _redact_label(f.get("title", fid)),
            "severity": f.get("severity", ""), "status": f.get("status", ""),
            "confidence": f.get("confidence", ""), "cwe": f.get("cwe", ""),
            "owasp": f.get("owasp", ""), "attack_technique": f.get("attack_technique", ""),
        }
        if effective_proof_state is not None:
            node["proof_state"] = effective_proof_state(f) or ""
            node["reportable"] = bool(is_reportable(f))
        ns = f.get("next_step")
        if isinstance(ns, dict) and (ns.get("suggested_agent") or ns.get("technique")):
            node["next_step"] = {"suggested_agent": ns.get("suggested_agent", ""),
                                 "technique": ns.get("technique", "")}
        cons = f.get("consensus")
        if isinstance(cons, dict) and cons.get("outcome"):
            node["consensus"] = cons.get("outcome")
        add_node(node)
        tgt = f.get("target_id")
        if tgt:
            edges.append({"source": tgt, "target": fid, "relation": "has-finding"})

    for c in (data.get("credentials") or []):
        if not isinstance(c, dict):
            continue
        src = c.get("source_target")
        cid = c.get("cred_id", "")
        for dst in (c.get("validated_on") or []):
            if src and dst and src != dst:
                edges.append({"source": src, "target": dst, "relation": "cred-reuse",
                              "cred_id": cid, "cred_type": c.get("type", "")})

    # Integridad referencial: descarta aristas COLGANTES (endpoints sin nodo declarado). El blackboard
    # puede traer FKs rotas — `validate_blackboard` solo exige PRESENCIA de campos, no integridad FK — y
    # una arista a un id inexistente generaría nodos fantasma sin type/label en el dashboard.
    edges = [e for e in edges if e["source"] in seen and e["target"] in seen]
    return {"engagement_id": eid, "nodes": nodes, "edges": edges}


def to_json(graph):
    return json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True)


# Atributos que emitimos como <key> de GraphML (id, for, tipo).
_NODE_KEYS = [("type", "string"), ("label", "string"), ("asset_type", "string"),
              ("access_level", "string"), ("reachable_via", "string"), ("severity", "string"),
              ("status", "string"), ("proof_state", "string"), ("reportable", "boolean"),
              ("confidence", "string"), ("consensus", "string")]
_EDGE_KEYS = [("relation", "string"), ("cred_type", "string")]


def _gml_val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def to_graphml(graph):
    """GraphML (dirigido) bien formado y con TODO texto escapado. Solo emite los atributos escalares del
    whitelist (las listas services/defenses/reaches_cidr no van al GraphML: se ven en el JSON)."""
    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">']
    for k, typ in _NODE_KEYS:
        L.append(f'  <key id="n_{k}" for="node" attr.name={quoteattr(k)} attr.type="{typ}"/>')
    for k, typ in _EDGE_KEYS:
        L.append(f'  <key id="e_{k}" for="edge" attr.name={quoteattr(k)} attr.type="{typ}"/>')
    L.append(f'  <graph id={quoteattr(str(graph.get("engagement_id", "engagement")))} '
             f'edgedefault="directed">')
    for n in graph["nodes"]:
        L.append(f'    <node id={quoteattr(str(n["id"]))}>')
        for k, _typ in _NODE_KEYS:
            if k in n and n[k] != "":
                L.append(f'      <data key="n_{k}">{escape(_gml_val(n[k]))}</data>')
        L.append('    </node>')
    for i, e in enumerate(graph["edges"]):
        L.append(f'    <edge id="e{i}" source={quoteattr(str(e["source"]))} '
                 f'target={quoteattr(str(e["target"]))}>')
        for k, _typ in _EDGE_KEYS:
            if k in e and e[k] != "":
                L.append(f'      <data key="e_{k}">{escape(_gml_val(e[k]))}</data>')
        L.append('    </edge>')
    L.append('  </graph>')
    L.append('</graphml>')
    return "\n".join(L)


def _confined_out(path):
    """Resuelve `--out` confinado bajo engagements/ del repo (realpath; rechaza traversal/symlink).
    Los artefactos del engagement viven ahí; no dejamos escribir el grafo en cualquier sitio."""
    base = os.path.realpath(os.path.join(ROOT, "engagements"))
    real = os.path.realpath(path if os.path.isabs(path) else os.path.join(ROOT, path))
    # realpath del PADRE (el fichero puede no existir aún); comprobamos que el dir destino está confinado.
    parent = os.path.realpath(os.path.dirname(real))
    if parent != base and not parent.startswith(base + os.sep):
        raise ValueError(f"--out debe estar bajo engagements/ del repo (no '{path}')")
    return real


def main(argv=None):
    ap = argparse.ArgumentParser(description="Exporta el grafo de ataque del blackboard (JSON/GraphML).",
                                 allow_abbrev=False)
    ap.add_argument("--engagement", default=ENGAGEMENT, help="ruta al blackboard (def.: contracts/engagement.json).")
    ap.add_argument("--format", choices=["json", "graphml"], default="json")
    ap.add_argument("--out", default=None, help="fichero de salida bajo engagements/ (def.: stdout).")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.engagement):
        print(f"attack_path: no existe el blackboard '{args.engagement}'", file=sys.stderr)
        return 2
    try:
        with open(args.engagement, encoding="utf-8") as f:
            data = json.load(f)
        graph = build_graph(data)
        text = to_graphml(graph) if args.format == "graphml" else to_json(graph)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"attack_path: {e}", file=sys.stderr)
        return 2

    if args.out:
        try:
            dst = _confined_out(args.out)
        except ValueError as e:
            print(f"attack_path: {e}", file=sys.stderr)
            return 3
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError as e:
            print(f"attack_path: no se pudo escribir '{args.out}': {e}", file=sys.stderr)
            return 3
        print(os.path.relpath(dst, ROOT).replace("\\", "/"))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
