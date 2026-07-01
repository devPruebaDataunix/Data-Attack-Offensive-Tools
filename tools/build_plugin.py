#!/usr/bin/env python3
"""
build_plugin.py — Empaqueta la suite como un VS Code Agent Plugin (formato 1.124).

Genera plugin/ con la estructura oficial (plugin.json + agents/ + hooks/ + .mcp.json + scripts/)
a partir de los agentes de .claude/agents. Compatible con la ventana de Agents de VS Code y
con Copilot CLI (formato compartido). Selecciona el harness Claude en Session Type.

    python tools/build_plugin.py

Las skills (skills/) se mantienen a mano (no se regeneran).
"""
import glob
import json
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "plugin")
AGENTS_SRC = os.path.join(ROOT, ".claude", "agents")
VERSION_FILE = os.path.join(ROOT, "VERSION")


def repo_version():
    """Versión = fichero VERSION (fuente única, igual que build_agent_cards.py): evita hardcodear y
    que el manifiesto del plugin se quede atrás (o regrese) en cada bump."""
    try:
        with open(VERSION_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


def parse_fm(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    return (m.group(1), m.group(2)) if m else ("", text)


# Campos de frontmatter permitidos para agentes EMPAQUETADOS en un plugin (spec Claude Code).
# permissionMode/hooks/mcpServers no se soportan en plugins; color no está en la lista.
PLUGIN_AGENT_FIELDS = {"name", "description", "model", "effort", "maxTurns", "tools",
                       "disallowedTools", "skills", "memory", "background", "isolation"}


def build_agents():
    dst = os.path.join(PLUGIN, "agents")
    os.makedirs(dst, exist_ok=True)
    names = []
    for f in sorted(glob.glob(os.path.join(AGENTS_SRC, "**", "*.md"), recursive=True)):
        fm, body = parse_fm(open(f, encoding="utf-8").read())
        kept = []
        name = None
        for line in fm.splitlines():
            key = line.split(":", 1)[0].strip()
            if key == "name":
                name = line.split(":", 1)[1].strip()
            if key in PLUGIN_AGENT_FIELDS:
                kept.append(line)
        name = name or os.path.splitext(os.path.basename(f))[0]
        out_text = "---\n" + "\n".join(kept) + "\n---\n" + body
        with open(os.path.join(dst, f"{name}.agent.md"), "w", encoding="utf-8") as out:
            out.write(out_text)
        names.append(name)
    return names


def build_hooks():
    """Solo el hook de alcance (safety-critical). El regen del mapa es una util de repo,
    no se incluye en el plugin para evitar dependencias de rutas del repo."""
    os.makedirs(os.path.join(PLUGIN, "hooks"), exist_ok=True)
    os.makedirs(os.path.join(PLUGIN, "scripts"), exist_ok=True)
    shutil.copy(os.path.join(ROOT, ".claude", "hooks", "scope_guard.py"),
                os.path.join(PLUGIN, "scripts", "scope_guard.py"))
    hooks = {
        "hooks": {
            "PreToolUse": [{
                "matcher": "Bash",
                "hooks": [{"type": "command",
                           "command": 'python "${CLAUDE_PLUGIN_ROOT}/scripts/scope_guard.py"'}],
            }],
        }
    }
    json.dump(hooks, open(os.path.join(PLUGIN, "hooks", "hooks.json"), "w", encoding="utf-8"),
              indent=2)


def build_mcp():
    # Vacío a propósito: los MCP de un plugin ARRANCAN SOLOS al habilitarlo. eip-mcp no está
    # instalado, así que no se incluye aquí (daría error de arranque). Sigue como opt-in en el
    # .mcp.json.example de la raíz; el operador lo añade self-hosted cuando lo tenga.
    mcp = {"mcpServers": {}}
    json.dump(mcp, open(os.path.join(PLUGIN, ".mcp.json"), "w", encoding="utf-8"), indent=2)


def build_manifest(names):
    # Sin campos de componentes: agents/, skills/, hooks/hooks.json y .mcp.json están en las
    # ubicaciones por defecto, así que Claude Code los AUTO-DESCUBRE. Declararlos como ruta-string
    # es 'Invalid input' para `claude plugin validate`. El manifest solo lleva metadatos.
    manifest = {
        "name": "cyberseg-agents",
        "description": f"Suite de pentesting/bug bounty autorizado: orquestador + {len(names)} "
                       "especialistas, RAG de vulnerabilidades (KEV/EPSS/exploit/CVSS), "
                       "gate de alcance y reporting humanizado.",
        "version": repo_version(),
        "author": {"name": "Cyberseg"},
        "homepage": "https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools",
        "repository": "https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools",
        "license": "LicenseRef-Proprietary",
        "keywords": ["pentesting", "bug-bounty", "offensive-security", "red-team",
                     "claude-code", "agents", "rag", "kev", "epss"],
    }
    blob = json.dumps(manifest, indent=2, ensure_ascii=False)
    # Doble ubicación para máxima compatibilidad:
    #  - plugin.json (raíz): formato de Agent Plugins de VS Code 1.124.
    #  - .claude-plugin/plugin.json: ubicación canónica de Claude Code.
    open(os.path.join(PLUGIN, "plugin.json"), "w", encoding="utf-8").write(blob)
    os.makedirs(os.path.join(PLUGIN, ".claude-plugin"), exist_ok=True)
    open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"), "w", encoding="utf-8").write(blob)


def main():
    os.makedirs(PLUGIN, exist_ok=True)
    names = build_agents()
    build_hooks()
    build_mcp()
    build_manifest(names)
    skills = [os.path.basename(os.path.dirname(p))
              for p in glob.glob(os.path.join(PLUGIN, "skills", "*", "SKILL.md"))]
    print(f"[plugin] generado en plugin/  ->  {len(names)} agentes, "
          f"{len(skills)} skills, hook de alcance, .mcp.json")
    print(f"[plugin] agentes: {', '.join(names)}")
    print(f"[plugin] skills:  {', '.join(skills) or '(ninguna aún)'}")


if __name__ == "__main__":
    main()
