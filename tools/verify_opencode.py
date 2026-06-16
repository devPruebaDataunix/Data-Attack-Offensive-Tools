#!/usr/bin/env python3
"""
verify_opencode.py — Verifica que el espejo opencode queda REPLICADO sin errores.

Comprueba que `.opencode/` está coherente y listo para correr la suite en opencode (control de
calidad de la réplica, estático — los chequeos de runtime como "¿está opencode instalado?" o
"¿responde Ollama?" los hace deploy/verify.sh):

- `opencode.json` válido, con el orquestador `primary` y, si los hay, bloques de `provider`.
- nº de `.opencode/agent/*.md` == nº de agentes en `.claude/agents` (los genera sync_opencode).
- frontmatter sano de cada agente opencode (`mode: subagent` + `model: provider/modelo`).
- CRUCE `routing.json` <-> `opencode.json`: toda ruta a un provider no-Anthropic (p.ej.
  `ollama/...`) exige que ese provider esté declarado en `opencode.json` y que el modelo exista
  en su lista. Así no se enruta un agente a un provider/modelo inexistente (fallo silencioso).

    python tools/verify_opencode.py     # imprime checks; sale 1 si hay fallos
Solo stdlib.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OC = os.path.join(ROOT, ".opencode", "opencode.json")
OC_AGENTS = os.path.join(ROOT, ".opencode", "agent")
CC_AGENTS = os.path.join(ROOT, ".claude", "agents")
ROUTING = os.path.join(ROOT, "tools", "routing.json")

results = []  # (status, msg)


def ok(m):
    results.append(("OK", m))


def fail(m):
    results.append(("FALLO", m))


def parse_fm(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    fm = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    return fm


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def finish():
    fails = [m for s, m in results if s == "FALLO"]
    for s, m in results:
        print(f"  [{s}] {m}")
    print("=" * 60)
    print(f"  verify_opencode: {len(results) - len(fails)} OK, {len(fails)} fallos")
    sys.exit(1 if fails else 0)


def main():
    oc = load_json(OC)
    if oc is None:
        fail(f"opencode.json no existe o no es JSON válido ({os.path.relpath(OC, ROOT)})")
        finish()
    ok("opencode.json es JSON válido")

    # Orquestador primary
    if oc.get("agent", {}).get("orchestrator", {}).get("mode") == "primary":
        ok("orquestador 'primary' declarado")
    else:
        fail("falta el agente 'orchestrator' con mode 'primary' en opencode.json")

    providers = oc.get("provider", {})
    ok(f"providers declarados: {sorted(providers) or '[]'} (anthropic va por defecto)")

    # Espejo coherente con .claude/agents
    oc_files = glob.glob(os.path.join(OC_AGENTS, "*.md"))
    cc_files = glob.glob(os.path.join(CC_AGENTS, "**", "*.md"), recursive=True)
    if len(oc_files) == len(cc_files):
        ok(f"espejo coherente: {len(oc_files)} agentes opencode == {len(cc_files)} en .claude/agents")
    else:
        fail(f"espejo DESINCRONIZADO: {len(oc_files)} opencode vs {len(cc_files)} claude "
             "— corre tools/sync_opencode.py")

    # Frontmatter de cada agente opencode
    bad = []
    for f in oc_files:
        fm = parse_fm(open(f, encoding="utf-8").read())
        if fm.get("mode") != "subagent" or "/" not in fm.get("model", ""):
            bad.append(os.path.basename(f))
    if bad:
        fail(f"agentes opencode con frontmatter inválido (mode/model): {sorted(bad)}")
    else:
        ok(f"frontmatter OK en los {len(oc_files)} agentes (mode subagent + provider/model)")

    # Cruce routing.json <-> providers/modelos declarados
    routes = (load_json(ROUTING) or {}).get("routes", {}) if os.path.isfile(ROUTING) else {}
    if not routes:
        ok("routing.json sin rutas activas (todo Anthropic por defecto)")
    for agent, model in sorted(routes.items()):
        prov, _, mid = model.partition("/")
        if prov == "anthropic":
            ok(f"ruta {agent} -> {model} (anthropic)")
        elif prov not in providers:
            fail(f"ruta {agent} -> {model}: provider '{prov}' NO declarado en opencode.json")
        elif mid and mid not in (providers[prov].get("models", {}) or {}):
            fail(f"ruta {agent} -> {model}: el modelo '{mid}' no está en provider.{prov}.models")
        else:
            ok(f"ruta {agent} -> {model}: provider y modelo declarados")

    finish()


if __name__ == "__main__":
    main()
