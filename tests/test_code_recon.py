#!/usr/bin/env python3
"""Tests de A (Shannon) — vertical white-box `code-recon`, ENDURECIDA tras el council de 3 lentes.

Cubre el diseño y los arreglos del council (seguridad · corrección · simplicidad):
- Esquema: target.source_hints[] (kind SIN `dependency`; secret_ref con `pattern` loot/), retrocompat;
  finding.code_ref (renombrado desde source_ref para no colisionar con source_refs[]).
- scope.example.source_repos[] (código en E3, local, no de red).
- Agente: toolset Read/Grep/Glob/Write/Edit (con Write/Edit para escribir por vía gateada; SIN Bash
  para no clonar/ejecutar), disallowed Agent+Task+Bash, memoria local, peers incl. api-recon, y las
  reglas duras (LEAD≠prueba, E3, secretos referenciados, anti-inyección white-box).
- agent-cards: topología A2A bidireccional (web/api-exploit, api-recon, vuln-triage <-> code-recon).
- AGENTS.md: delegación white-box + roster 28 + code_ref + clúster.
- BARRERAS deterministas del council:
  * validate_engagement: un finding con code_ref no puede ir confirmed/exploited sin evidence.
  * memory_guard: bloquea referencias file:line de código en la memoria del agente.
  * secret_scan: bloquea un secreto pegado en source_hints.label / kind:secret sin secret_ref->loot/.

Sin pytest: `python tests/test_code_recon.py` (sale 1 si algo falla).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_fail = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _fail.append(name)


def _load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def t_target_schema():
    sch = json.loads(_load("contracts/target.schema.json"))
    sh = sch["properties"].get("source_hints")
    check("target.schema tiene 'source_hints'", sh is not None)
    if not sh:
        return
    item = sh["items"]
    check("source_hints.items.required = kind/source_ref",
          set(item["required"]) == {"kind", "source_ref"})
    enum = set(item["properties"]["kind"]["enum"])
    check("kind enum = route/sink/authz-logic/secret/entrypoint (sin 'dependency', council)",
          enum == {"route", "sink", "authz-logic", "secret", "entrypoint"})
    check("source_hints NO en required (retrocompatible)",
          "source_hints" not in sch.get("required", []))
    check("secret_ref con pattern loot/ (council: enforce, no solo docs)",
          item["properties"]["secret_ref"].get("pattern") == "^engagements/.+/loot/")

    try:
        import jsonschema
    except Exception:
        print("  (jsonschema ausente: se omite la validación estructural)")
        return
    valid = {"kind": "sink", "source_ref": "app-backend:src/db/users.ts:42",
             "label": "raw SQL string-concat", "maps_to": "GET /api/users/{id}"}
    try:
        jsonschema.validate(valid, item); check("source_hint VÁLIDO valida", True)
    except jsonschema.ValidationError as e:
        check(f"source_hint VÁLIDO valida ({e.message})", False)
    for bad, why in (({"kind": "dependency", "source_ref": "x:y:1"}, "kind 'dependency' retirado"),
                     ({"kind": "route"}, "sin source_ref"),
                     ({"kind": "secret", "source_ref": "r:f:1", "secret_ref": "AKIAIOSFODNN7EXAMPLE"},
                      "secret_ref que NO es ref a loot/")):
        try:
            jsonschema.validate(bad, item); check(f"source_hint inválido RECHAZADO ({why})", False)
        except jsonschema.ValidationError:
            check(f"source_hint inválido RECHAZADO ({why})", True)


def t_finding_schema():
    sch = json.loads(_load("contracts/finding.schema.json"))
    props = sch["properties"]
    check("finding.schema tiene 'code_ref' (renombrado de source_ref, council)",
          props.get("code_ref", {}).get("type") == "string")
    check("finding.schema ya NO tiene 'source_ref' (colisión resuelta)", "source_ref" not in props)
    check("code_ref distinto de source_refs[] (procedencia vs respaldo)",
          "source_refs" in props and props["source_refs"]["type"] == "array")
    check("code_ref exige corroboración dinámica (candidate hasta evidence)",
          "candidate" in props["code_ref"]["description"] and
          "DINÁMICA" in props["code_ref"]["description"])


def t_scope_example():
    sc = json.loads(_load("contracts/scope.example.json"))
    repos = sc.get("source_repos")
    check("scope.example tiene 'source_repos'", isinstance(repos, list) and len(repos) >= 1)
    if not repos:
        return
    r = repos[0]
    check("source_repo tiene repo_id + local_path", "repo_id" in r and "local_path" in r)
    check("source_repo local_path bajo engagements/ (código en E3, no de red)",
          r["local_path"].startswith("engagements/"))
    check("source_repo mapea a targets en vivo", "maps_to_targets" in r)


def t_agent_file():
    md = _load(".claude/agents/recon/code-recon.md")
    check("code-recon: name en frontmatter", "name: code-recon" in md)
    check("code-recon: fase recon", "phase: recon" in md)
    # Council (corrección): DEBE poder escribir el blackboard por la vía gateada.
    check("code-recon: toolset con Write y Edit (escribe por vía gateada)",
          "tools: Read, Grep, Glob, Write, Edit" in md)
    # Council (seguridad): SIN Bash -> no clona de red ni ejecuta.
    check("code-recon: Bash prohibido (no clona/ejecuta)",
          "disallowedTools: Agent, Task, Bash" in md and "No tienes `Bash`" in md)
    check("code-recon: memoria local", "memory: local" in md)
    check("code-recon: peers incl. api-recon (council: drift arreglado)",
          "web-exploit" in md and "api-exploit" in md and "api-recon" in md and "vuln-triage" in md)
    check("code-recon: LEAD != prueba, nunca confirmed desde código",
          "LEAD" in md and "nunca `confirmed`" in md.replace("**", ""))
    check("code-recon: código = dato de cliente E3 (§6)", "E3" in md and "§6" in md)
    check("code-recon: secretos referenciados, nunca en claro",
          "NUNCA pongas el valor" in md and "secret_ref" in md)
    check("code-recon: anti-inyección white-box (código = DATO, no amplía scope)",
          "Anti-inyeccion" in md and "DATO, no instrucciones" in md and
          "autorización vive en `scope.json`" in md)


def t_agent_cards():
    c = json.loads(_load("contracts/agent-cards.json"))
    p = {x["name"]: set(x.get("a2a_peers") or []) for x in c["cards"]}
    check("agent-cards: code-recon registrado", "code-recon" in p)
    check("agent-cards: code-recon -> web/api-exploit + api-recon + vuln-triage",
          {"web-exploit", "api-exploit", "api-recon", "vuln-triage"} <= p.get("code-recon", set()))
    for a in ("web-exploit", "api-exploit", "api-recon", "vuln-triage"):
        check(f"agent-cards: {a} declara code-recon (bidireccional, sin drift C14)",
              "code-recon" in p.get(a, set()))
    check("agent-cards: 28 agentes (excl. orchestrator)",
          len([x for x in c["cards"] if x["name"] != "orchestrator"]) == 28)


def t_agents_md():
    md = _load("AGENTS.md")
    check("AGENTS.md: roster 28 (18 de fase)", "28 agentes" in md and "18 de fase" in md)
    check("AGENTS.md: delegación white-box a code-recon",
          "code-recon" in md and "white-box" in md.lower() and "source_repos" in md)
    check("AGENTS.md: usa code_ref, confirmación DINÁMICA y menciona sin Bash",
          "code_ref" in md and "confirmación DINÁMICA" in md and "`Bash`" in md)
    check("AGENTS.md: clúster A2A white-box incl. api-recon",
          "Clúster white-box" in md and "code-recon ↔ api-recon" in md)


# ── Barreras deterministas (council) ─────────────────────────────────────────────
def t_guard_validate_engagement():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import importlib
    bb = importlib.import_module("blackboard")
    base = {"engagement_id": "E", "scope_ref": "s", "phase": "exploitation", "targets": [], "findings": []}

    def _one(f):
        d = dict(base, findings=[f]); return bb.validate_engagement(d)
    ok_cand = _one({"finding_id": "F1", "target_id": "t", "title": "x", "status": "candidate",
                    "severity": "high", "code_ref": "app:src/a.ts:1"})
    check("hipótesis code_ref en 'candidate' es VÁLIDA", not any("F1" in v for v in ok_cand))
    bad = _one({"finding_id": "F2", "target_id": "t", "title": "x", "status": "confirmed",
                "severity": "high", "code_ref": "app:src/a.ts:1"})
    check("code_ref + confirmed SIN evidence -> BLOQUEADO", any("F2" in v for v in bad))
    ok_ev = _one({"finding_id": "F3", "target_id": "t", "title": "x", "status": "confirmed",
                  "severity": "high", "code_ref": "app:src/a.ts:1", "evidence": "HTTP 200 dump del PoC"})
    check("code_ref + confirmed CON evidence -> OK", not any("F3" in v for v in ok_ev))


def t_guard_memory():
    sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
    import importlib
    mg = importlib.import_module("memory_guard")
    v_leak = mg.find_violations("Truco: en app-backend, getUser concatena SQL en src/db/user.ts:42.", None)
    check("memory_guard bloquea file:line de código (fuga E3)",
          any(x.startswith("code_ref:") for x in v_leak))
    v_ok = mg.find_violations("Truco: en Express, app.use('/api', r) esconde el prefijo; grep el router raíz.", None)
    check("memory_guard NO bloquea técnica generalizada (sin file:line)",
          not any(x.startswith("code_ref:") for x in v_ok))


def t_guard_secret_scan():
    sys.path.insert(0, os.path.join(ROOT, ".claude", "hooks"))
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import importlib
    ss = importlib.import_module("secret_scan")
    leaked = json.dumps({"targets": [{"target_id": "t", "source_hints": [
        {"kind": "secret", "source_ref": "app:cfg.py:3", "secret_ref": "AKIAIOSFODNN7EXAMPLE"}]}]})
    check("secret_scan bloquea kind:secret sin secret_ref->loot/",
          ss.source_hint_reason(leaked) is not None)
    good = json.dumps({"targets": [{"target_id": "t", "source_hints": [
        {"kind": "sink", "source_ref": "app:src/db.ts:1", "label": "raw SQL concat", "maps_to": "GET /u/{id}"}]}]})
    check("secret_scan NO bloquea una pista limpia (label no sensible)",
          ss.source_hint_reason(good) is None)


if __name__ == "__main__":
    print("== target.schema source_hints =="); t_target_schema()
    print("== finding.schema code_ref =="); t_finding_schema()
    print("== scope.example source_repos =="); t_scope_example()
    print("== agente code-recon =="); t_agent_file()
    print("== agent-cards topología =="); t_agent_cards()
    print("== AGENTS.md white-box =="); t_agents_md()
    print("== guard: validate_engagement =="); t_guard_validate_engagement()
    print("== guard: memory_guard =="); t_guard_memory()
    print("== guard: secret_scan =="); t_guard_secret_scan()
    print()
    if _fail:
        print(f"FALLOS: {len(_fail)} -> {_fail}")
        sys.exit(1)
    print("TODOS OK")
