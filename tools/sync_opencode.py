#!/usr/bin/env python3
"""
sync_opencode.py — Genera el espejo de agentes para opencode desde los de Claude Code.

Lee .claude/agents/**/*.md (formato Claude Code) y escribe .opencode/agent/<name>.md
(formato opencode), manteniendo el MISMO system prompt. Así la suite se mantiene en un
único sitio (.claude/agents) y opencode se regenera con:

    python tools/sync_opencode.py

Sin dependencias externas (parser de frontmatter mínimo).
"""
import os
import re
import glob
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, ".claude", "agents")
DST = os.path.join(ROOT, ".opencode", "agent")
ROUTING = os.path.join(ROOT, "tools", "routing.json")

MODEL_MAP = {
    # IDs completos (formato actual de .claude/agents) -> prefijo de provider opencode
    "claude-fable-5": "anthropic/claude-fable-5",
    "claude-opus-4-8": "anthropic/claude-opus-4-8",
    "claude-sonnet-4-6": "anthropic/claude-sonnet-4-6",
    "claude-haiku-4-5": "anthropic/claude-haiku-4-5-20251001",
    # alias (compatibilidad hacia atrás)
    "fable": "anthropic/claude-fable-5",
    "opus": "anthropic/claude-opus-4-8",
    "sonnet": "anthropic/claude-sonnet-4-6",
    "haiku": "anthropic/claude-haiku-4-5-20251001",
}


def load_routes():
    """Tabla de routing multi-provider del ESPEJO opencode (opcional). Mapea name de agente
    -> modelo opencode 'provider/model'. Ausente/ilegible => {} (sin routing: comportamiento
    por defecto = MODEL_MAP sobre el 'model' Anthropic). Fail-open: jamás rompe la generación.
    Ver tools/routing.json."""
    try:
        with open(ROUTING, "r", encoding="utf-8") as f:
            routes = json.load(f).get("routes", {})
        return routes if isinstance(routes, dict) else {}
    except (OSError, ValueError):
        return {}


ROUTES = load_routes()


def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, text
    raw, body = m.group(1), m.group(2)
    fm = {}
    for line in raw.splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, body


def to_opencode(name, fm, body):
    # Routing opcional: si el agente está en routing.json se usa ese modelo 'provider/model';
    # si no, el modelo Anthropic por defecto (MODEL_MAP sobre su 'model'). Solo afecta a opencode.
    model = ROUTES.get(name) or MODEL_MAP.get(fm.get("model", "claude-opus-4-8"),
                                              "anthropic/claude-opus-4-8")
    tools = [t.strip() for t in fm.get("tools", "").split(",") if t.strip()]
    has = lambda name: name in tools
    # Permisos opencode: por defecto deny; ask para bash (acciones que tocan target).
    perm = {
        "read": "allow",
        "grep": "allow",
        "glob": "allow",
        "edit": "allow" if (has("Write") or has("Edit")) else "deny",
        "bash": "ask" if has("Bash") else "deny",
        "webfetch": "allow" if has("WebFetch") else "deny",
        "websearch": "allow" if has("WebSearch") else "deny",
    }
    lines = ["---"]
    lines.append(f"description: {fm.get('description', '').strip()}")
    lines.append("mode: subagent")
    lines.append(f"model: {model}")
    lines.append("temperature: 0.1")
    lines.append("permission:")
    for k, v in perm.items():
        lines.append(f"  {k}: {v}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + body.strip() + "\n"


def main():
    os.makedirs(DST, exist_ok=True)
    count = 0
    for path in glob.glob(os.path.join(SRC, "**", "*.md"), recursive=True):
        with open(path, "r", encoding="utf-8") as f:
            fm, body = parse_frontmatter(f.read())
        name = fm.get("name")
        if not name:
            continue
        out = to_opencode(name, fm, body)
        with open(os.path.join(DST, name + ".md"), "w", encoding="utf-8") as f:
            f.write(out)
        count += 1
        routed = f"  [routing -> {ROUTES[name]}]" if name in ROUTES else ""
        print(f"  -> .opencode/agent/{name}.md{routed}")
    if ROUTES:
        print(f"Routing activo para {len(ROUTES)} agente(s): {', '.join(sorted(ROUTES))}.")
    print(f"Generados {count} agentes opencode.")


if __name__ == "__main__":
    main()
