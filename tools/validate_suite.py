#!/usr/bin/env python3
"""
validate_suite.py — Linter de la suite Cyberseg Agents.

Verifica que todo está correcto y coherente para que cargue sin sorpresas en Claude Code /
opencode: agentes, settings, hooks, MCP, esquemas JSON, scripts y referencias cruzadas.

    python tools/validate_suite.py
Salida: lista de checks con OK/FALLO y un resumen. Código de salida 1 si hay fallos.
"""
import glob
import json
import os
import re
import py_compile
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OK, FAIL, WARN = "OK", "FALLO", "aviso"
results = []  # (status, msg)


def check(cond, ok_msg, fail_msg, warn=False):
    if cond:
        results.append((OK, ok_msg))
    else:
        results.append((WARN if warn else FAIL, fail_msg))
    return cond


KNOWN_TOOLS = {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Glob", "Grep",
               "Bash", "WebSearch", "WebFetch", "Task", "Agent"}
KNOWN_MODELS = {
    # IDs completos (formato actual de .claude/agents)
    "claude-fable-5", "claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5",
    # alias y especiales
    "fable", "opus", "sonnet", "haiku", "inherit",
}
KNOWN_EFFORT = {"low", "medium", "high", "xhigh", "max"}
# effort NO está soportado en Haiku 4.5 ni Sonnet 4.5 (la API devuelve 400).
EFFORT_UNSUPPORTED = {"haiku", "claude-haiku-4-5"}


def parse_fm(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return None, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, m.group(2)


def validate_agents():
    files = glob.glob(os.path.join(ROOT, ".claude", "agents", "**", "*.md"), recursive=True)
    check(len(files) > 0, f"Agentes encontrados: {len(files)}", "No hay agentes")
    names = {}
    for f in files:
        rel = os.path.relpath(f, ROOT)
        raw = open(f, encoding="utf-8").read()
        fm, body = parse_fm(raw)
        if not check(fm is not None, f"{rel}: frontmatter OK", f"{rel}: frontmatter inválido"):
            continue
        # Heurística YAML: un valor sin comillas con ': ' embebido rompe el parseo real.
        fm_block = raw.split("---", 2)[1] if raw.startswith("---") else ""
        risky = [ln.split(":", 1)[0].strip() for ln in fm_block.splitlines()
                 if re.match(r"^\w[\w-]*:\s+\S", ln) and ": " in ln.split(":", 1)[1]
                 and not ln.split(":", 1)[1].strip().startswith(('"', "'"))]
        check(not risky, f"{rel}: frontmatter sin ': ' embebido (YAML seguro)",
              f"{rel}: ': ' embebido en {risky} rompe el YAML — entrecomilla o reformula")
        check("name" in fm and "description" in fm, f"{rel}: name+description OK",
              f"{rel}: falta name o description")
        check(len(fm.get("description", "")) <= 1024, f"{rel}: description longitud OK",
              f"{rel}: description muy larga", warn=True)
        if "model" in fm:
            check(fm["model"] in KNOWN_MODELS, f"{rel}: model '{fm.get('model')}' OK",
                  f"{rel}: model desconocido '{fm.get('model')}'", warn=True)
        if "effort" in fm:
            check(fm["effort"] in KNOWN_EFFORT, f"{rel}: effort '{fm['effort']}' OK",
                  f"{rel}: effort inválido '{fm['effort']}' (usa {sorted(KNOWN_EFFORT)})")
            check(fm.get("model") not in EFFORT_UNSUPPORTED,
                  f"{rel}: effort compatible con el modelo",
                  f"{rel}: effort no soportado en '{fm.get('model')}' (Haiku/Sonnet-4.5 dan 400)")
        tools = [t.strip() for t in fm.get("tools", "").split(",") if t.strip()]
        unknown = [t for t in tools if t not in KNOWN_TOOLS]
        check(not unknown, f"{rel}: tools OK", f"{rel}: tools desconocidas {unknown}", warn=True)
        # Hardening v2.0.0: cota de turnos (todo agente acotado) + denylist de tools.
        mt = fm.get("maxTurns")
        if check(mt is not None, f"{rel}: maxTurns declarado",
                 f"{rel}: falta maxTurns (todo agente debe acotar turnos)"):
            check(mt.isdigit() and int(mt) > 0, f"{rel}: maxTurns '{mt}' OK",
                  f"{rel}: maxTurns inválido '{mt}' (entero positivo)")
        disallowed = [t.strip() for t in fm.get("disallowedTools", "").split(",") if t.strip()]
        bad_dis = [t for t in disallowed if t not in KNOWN_TOOLS and not t.startswith("mcp__")]
        check(not bad_dis, f"{rel}: disallowedTools OK",
              f"{rel}: disallowedTools desconocidas {bad_dis}", warn=True)
        # Invariante de arquitectura: ningún especialista puede spawnear subagentes (hub-and-spoke).
        check("Agent" in disallowed and "Task" in disallowed,
              f"{rel}: deniega Agent+Task (hub-and-spoke)",
              f"{rel}: debe denegar Agent y Task en disallowedTools (malla hub-and-spoke)")
        if "memory" in fm:
            check(fm["memory"] in {"user", "project", "local"}, f"{rel}: memory OK",
                  f"{rel}: memory inválida '{fm['memory']}'")
        n = fm.get("name")
        if n in names:
            check(False, "", f"Nombre de agente DUPLICADO: {n} ({rel} y {names[n]})")
        names[n] = rel
    return set(names)


def validate_json(path, label):
    full = os.path.join(ROOT, path)
    if not os.path.isfile(full):
        check(False, "", f"{label}: no existe ({path})", warn=True)
        return None
    try:
        data = json.load(open(full, encoding="utf-8"))
        check(True, f"{label}: JSON válido", "")
        return data
    except Exception as e:
        check(False, "", f"{label}: JSON inválido — {e}")
        return None


def validate_hooks(settings):
    if not settings:
        return
    hooks = settings.get("hooks", {})
    cmds = []
    for ev in hooks.values():
        for matcher in ev:
            for h in matcher.get("hooks", []):
                cmds.append(h.get("command", ""))
    for c in cmds:
        # Normaliza la variable de Claude Code (${CLAUDE_PROJECT_DIR}) antes de localizar el script,
        # para aceptar tanto `python .claude/hooks/x.py` como `python3 ${CLAUDE_PROJECT_DIR}/.../x.py`.
        c_norm = c.replace("${CLAUDE_PROJECT_DIR}", "").replace("$CLAUDE_PROJECT_DIR", "")
        m = re.search(r"([\w./\\-]+\.py)", c_norm)
        if m:
            rel = m.group(1).lstrip("/\\")
            p = os.path.join(ROOT, rel)
            check(os.path.isfile(p), f"hook -> {rel} existe",
                  f"hook apunta a script inexistente: {rel}")


def validate_refs():
    """Referencias cruzadas: ficheros que los agentes/docs citan deben existir."""
    must_exist = [
        "AGENTS.md", "docs/reporting-guide.md", "docs/humanizer-checklist.md",
        "templates/report-template.md", "contracts/finding.schema.json",
        "contracts/target.schema.json", "contracts/engagement.schema.json",
        "contracts/scope.example.json", "rag/query_vulns.py", "rag/refresh.py",
        # RAG de política de programa + adapters de informe (v2.56, track de integración)
        "rag/triage/policy.py", "rag/triage/query_triage.py", "rag/triage/policy_data.json",
        "templates/report-adapters/hackerone.md", "templates/report-adapters/bugcrowd.md",
        "templates/report-adapters/intigriti.md", "templates/report-adapters/yeswehack.md",
        ".claude/hooks/scope_guard.py", ".claude/hooks/a2a_guard.py",
        ".claude/hooks/a2a_router_nudge.py", ".claude/hooks/memory_guard.py",
        ".claude/hooks/fs_guard.py", ".claude/hooks/blackboard_guard.py",
        ".claude/hooks/circuit_breaker.py", "tools/consensus.py", "tools/screenshot.py",
        "tools/attack_path.py", "tools/diff_scope.py", "tools/http_proxy.py", "CLAUDE.md",
        "contracts/a2a-message.schema.json", "contracts/agent-card.schema.json",
        "contracts/agent-cards.json", "tools/build_agent_cards.py",
        # Despliegue en contenedores (v1.6.0)
        "Dockerfile", "docker-compose.yml", ".dockerignore", "deploy/docker.sh",
        "deploy/auto-deploy.sh", "deploy/lib.sh", "deploy/verify.sh", "deploy/setup.sh",
        "deploy/agentsview.sh",
        # Contenedor efímero por-engagement (mejora C, v2.53.0)
        "docker-compose.engagement.yml", "deploy/engagement-run.sh",
        # Gobierno / flujo engagement-driven (adaptado de spec-driven)
        "CONSTITUTION.md", "templates/engagement-spec.md", "tools/analyze_engagement.py",
        "docs/engagement-driven.md",
    ]
    for rel in must_exist:
        check(os.path.isfile(os.path.join(ROOT, rel)), f"referencia '{rel}' existe",
              f"falta fichero referenciado: {rel}")


def validate_python():
    for f in glob.glob(os.path.join(ROOT, "**", "*.py"), recursive=True):
        if "__pycache__" in f:
            continue
        rel = os.path.relpath(f, ROOT)
        try:
            py_compile.compile(f, doraise=True)
            check(True, f"py compila: {rel}", "")
        except py_compile.PyCompileError as e:
            check(False, "", f"py NO compila: {rel} — {e}")


PLUGIN_AGENT_FORBIDDEN = {"permissionMode", "hooks", "mcpServers"}


def validate_plugin():
    pdir = os.path.join(ROOT, "plugin")
    if not os.path.isdir(pdir):
        return
    # Manifest en ambas ubicaciones (VS Code raíz + Claude .claude-plugin/).
    for rel in ["plugin/plugin.json", "plugin/.claude-plugin/plugin.json"]:
        d = validate_json(rel, f"plugin manifest {os.path.basename(os.path.dirname(rel)) or 'raíz'}")
        if d:
            check("name" in d, f"{rel}: tiene 'name'", f"{rel}: falta 'name' (requerido)")
    # hooks.json con envoltorio "hooks".
    h = validate_json("plugin/hooks/hooks.json", "plugin hooks.json")
    if h is not None:
        check("hooks" in h, "plugin hooks.json: envoltorio 'hooks' presente",
              "plugin hooks.json: falta el envoltorio 'hooks' (la spec lo exige)")
    validate_json("plugin/.mcp.json", "plugin .mcp.json")
    # Agentes empaquetados: frontmatter sin campos prohibidos para plugins.
    for f in glob.glob(os.path.join(pdir, "agents", "*.agent.md")):
        rel = os.path.relpath(f, ROOT)
        fm, _ = parse_fm(open(f, encoding="utf-8").read())
        bad = [k for k in PLUGIN_AGENT_FORBIDDEN if k in (fm or {})]
        check(not bad, f"{rel}: frontmatter de plugin OK",
              f"{rel}: campos no permitidos en plugin: {bad}")
    # Skills con name + description.
    for f in glob.glob(os.path.join(pdir, "skills", "*", "SKILL.md")):
        rel = os.path.relpath(f, ROOT)
        fm, _ = parse_fm(open(f, encoding="utf-8").read())
        ok = fm and "name" in fm and "description" in fm
        check(bool(ok), f"{rel}: SKILL.md con name+description", f"{rel}: SKILL.md incompleto")


def validate_a2a_peers(cards):
    """Topología A2A coherente: cada peer declarado existe y la relación es BIDIRECCIONAL
    (si A lista a B, B debe listar a A). Es lo que el guard C14 usa para permitir el par."""
    if not cards:
        return
    by_name = {c.get("name"): set(c.get("a2a_peers") or []) for c in cards.get("cards", [])}
    for name, peers in sorted(by_name.items()):
        for p in sorted(peers):
            if not check(p in by_name, f"a2a_peers: '{name}' -> '{p}' es un agente conocido",
                         f"a2a_peers: '{name}' apunta a peer inexistente '{p}'"):
                continue
            check(name in by_name.get(p, set()),
                  f"a2a_peers: relación {name} <-> {p} bidireccional",
                  f"a2a_peers: '{name}' lista a '{p}' pero '{p}' no lista a '{name}' (asimétrico)")


def main():
    agent_names = validate_agents()
    s = validate_json(".claude/settings.json", "settings.json")
    validate_hooks(s)
    validate_json(".mcp.json.example", ".mcp.json.example")
    validate_json(".opencode/opencode.json", "opencode.json")
    for sch in ["finding", "target", "engagement", "a2a-message", "agent-card"]:
        validate_json(f"contracts/{sch}.schema.json", f"esquema {sch}")
    validate_json("contracts/agent-cards.json", "registro agent-cards")
    validate_json("contracts/scope.example.json", "scope.example.json")
    validate_json("contracts/examples/engagement.sample.json", "engagement.sample.json")
    validate_refs()
    # CLAUDE.md debe importar AGENTS.md: así la CLI carga el playbook del Orquestador (Claude Code
    # no auto-lee AGENTS.md, solo CLAUDE.md). El bot/TUI lo cargan vía setting_sources=["project"].
    claude_md = os.path.join(ROOT, "CLAUDE.md")
    if os.path.isfile(claude_md):
        check("@AGENTS.md" in open(claude_md, encoding="utf-8").read(),
              "CLAUDE.md importa @AGENTS.md",
              "CLAUDE.md no importa @AGENTS.md (el Orquestador no cargaría su playbook en la CLI)")
    validate_plugin()
    validate_python()

    # Coherencia opencode <-> claude (mismo nº de agentes)
    oc = glob.glob(os.path.join(ROOT, ".opencode", "agent", "*.md"))
    check(len(oc) == len(agent_names),
          f"espejo opencode coherente ({len(oc)} = {len(agent_names)} agentes)",
          f"espejo opencode DESINCRONIZADO ({len(oc)} vs {len(agent_names)}) — corre tools/sync_opencode.py",
          warn=True)

    # Coherencia registro A2A <-> agentes (cards = agentes + orquestador)
    cards = validate_json("contracts/agent-cards.json", "registro agent-cards (coherencia)")
    if cards:
        ncards = len(cards.get("cards", []))
        check(ncards == len(agent_names) + 1,
              f"registro agent-cards coherente ({ncards} = {len(agent_names)} agentes + orquestador)",
              f"registro agent-cards DESINCRONIZADO ({ncards} vs {len(agent_names)}+1) — corre tools/build_agent_cards.py",
              warn=True)
        validate_a2a_peers(cards)

    # Resumen
    fails = [m for st, m in results if st == FAIL]
    warns = [m for st, m in results if st == WARN]
    oks = [m for st, m in results if st == OK]
    print("\n".join(f"  [{st}] {m}" for st, m in results if st != OK))
    print("\n" + "=" * 60)
    print(f"  RESUMEN:  {len(oks)} OK   {len(warns)} avisos   {len(fails)} fallos")
    print("=" * 60)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
