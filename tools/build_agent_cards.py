#!/usr/bin/env python3
"""
build_agent_cards.py — Compila el registro de Agent Cards (A2A) desde los agentes.

Lee .claude/agents/**/*.md y escribe contracts/agent-cards.json: UNA card por agente con
sus capacidades A2A. La verdad vive PEGADA al agente (bloque `a2a:` en su frontmatter, junto
a tools/model); aquí solo se COMPILA a un registro único sin drift, que leen el router
(AGENTS.md) y el guard a2a_guard.py (C14, valida que from_agent/to_agent son agentes conocidos).

Regenera con:   python tools/build_agent_cards.py

No se edita agent-cards.json a mano (lo sobrescribe esta herramienta). Solo stdlib; mismo
parser de frontmatter que sync_opencode.py, con soporte para el bloque anidado `a2a:`.
"""
import os
import re
import glob
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, ".claude", "agents")
OUT = os.path.join(ROOT, "contracts", "agent-cards.json")
VERSION_FILE = os.path.join(ROOT, "VERSION")

# Fase por agente (campo informativo de la card). a2a.phase en el frontmatter lo sobreescribe.
NAME_PHASE = {
    "osint-recon": "recon", "active-recon": "recon", "recon-suite": "recon", "api-recon": "recon",
    "vuln-triage": "triage", "nuclei": "triage",
    "web-exploit": "exploitation", "network-exploit": "exploitation", "ai-security": "exploitation",
    "metasploit": "exploitation", "sqlmap": "exploitation", "web-fuzzing": "exploitation",
    "netexec": "exploitation", "api-exploit": "exploitation",
    "post-exploit": "post-exploitation", "lateral-discovery": "post-exploitation",
    "c2-exfil": "post-exploitation", "sliver": "post-exploitation",
    "reporting": "reporting", "knowledge-postmortem": "reporting",
}


def repo_version():
    try:
        with open(VERSION_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


def _parse_list(v):
    """'[a, b, c]' -> ['a','b','c']; cualquier otra cosa se devuelve como string pelado."""
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [x.strip().strip("\"'") for x in inner.split(",") if x.strip()]
    return v.strip("\"'")


def parse_frontmatter(text):
    """Frontmatter line-based con UN nivel de anidamiento (para el bloque `a2a:`).
    Devuelve un dict; el valor de `a2a` es a su vez un dict con listas/escalares."""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return {}
    fm = {}
    block = None  # clave del bloque anidado en curso (p.ej. 'a2a')
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        if not line.startswith(" ") and ":" in line:
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if v == "":
                fm[k] = {}
                block = k
            else:
                fm[k] = v
                block = None
        elif line.startswith(" ") and block and ":" in line:
            k, v = line.strip().split(":", 1)
            fm[block][k.strip()] = _parse_list(v.strip())
    return fm


def build_card(fm, version):
    name = fm.get("name")
    if not name:
        return None
    a2a = fm.get("a2a") if isinstance(fm.get("a2a"), dict) else {}

    def _list(key):
        val = a2a.get(key, [])
        return val if isinstance(val, list) else [val] if val else []

    return {
        "name": name,
        "description": (fm.get("description") or "").strip(),
        "phase": a2a.get("phase") or NAME_PHASE.get(name, "any"),
        "model": fm.get("model", ""),
        "version": version,
        "capabilities": _list("capabilities"),
        "consumes": _list("consumes"),
        "produces": _list("produces"),
        "tools": [t.strip() for t in fm.get("tools", "").split(",") if t.strip()],
        "a2a_peers": _list("peers"),
    }


def orchestrator_card(version):
    """El Orquestador no es un subagente (vive en AGENTS.md) pero es un destino A2A válido
    ('to_agent: orchestrator' = devolver al hub). El guard C14 debe reconocerlo."""
    return {
        "name": "orchestrator",
        "description": "Sesión principal (AGENTS.md). Planifica, delega, valida handoffs y enruta el bus A2A mediado.",
        "phase": "orchestrator",
        "model": "claude-opus-4-8",
        "version": version,
        "capabilities": ["route-a2a", "delegate", "validate-handoff", "chain-attack"],
        "consumes": ["scope.json", "messages:*"],
        "produces": ["engagement.json", "messages:delivered"],
        "tools": ["Task", "Read", "Write", "Edit", "Bash"],
        "a2a_peers": [],
    }


def main():
    version = repo_version()
    cards = [orchestrator_card(version)]
    for path in glob.glob(os.path.join(SRC, "**", "*.md"), recursive=True):
        with open(path, "r", encoding="utf-8") as f:
            card = build_card(parse_frontmatter(f.read()), version)
        if card:
            cards.append(card)
    cards.sort(key=lambda c: c["name"])

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"version": version, "cards": cards}, f, indent=2, ensure_ascii=False)
        f.write("\n")

    peers = sum(1 for c in cards if c["a2a_peers"])
    print(f"Generadas {len(cards)} agent cards -> contracts/agent-cards.json "
          f"({peers} con pares A2A directos).")


if __name__ == "__main__":
    main()
