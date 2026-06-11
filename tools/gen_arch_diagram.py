#!/usr/bin/env python3
"""
gen_arch_diagram.py — Genera ARCHITECTURE_MAP.md leyendo el ESTADO REAL del proyecto.

Escanea .claude/agents/**, contracts/, rag/, hooks y settings, y produce un mapa
auto-descriptivo (diagrama Mermaid + tablas de inventario) que SIEMPRE refleja la realidad.

Dos modos:
  - Manual:  python tools/gen_arch_diagram.py        (regenera y muestra resumen)
  - Hook:    python tools/gen_arch_diagram.py --hook  (lo invoca Claude Code tras
             Write/Edit/Bash; regenera solo si el cambio afecta a la arquitectura)

Se mantiene SIEMPRE sincronizado: al crear/modificar/eliminar un agente u otro componente,
el hook PostToolUse lo regenera. Sin dependencias externas.
"""
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(ROOT, ".claude", "agents")
OUT = os.path.join(ROOT, "ARCHITECTURE_MAP.md")

# Carpeta de agente -> (zona, etiqueta, color)
ZONES = {
    "recon":        ("E1", "Zona E1 · Recon",        "🟦"),
    "analysis":     ("E2", "Zona E2 · Explotación",  "🟥"),
    "exploitation": ("E2", "Zona E2 · Explotación",  "🟥"),
    "closing":      ("E3", "Zona E3 · Cierre",       "🟩"),
}
ZONE_ORDER = ["E1", "E2", "E3"]
ZONE_LABEL = {"E1": "🟦 Zona E1 · Recon (perfil de red abierto, sin datos de cliente)",
              "E2": "🟥 Zona E2 · Explotación (VLAN del engagement, por cliente, kill-switch)",
              "E3": "🟩 Zona E3 · Cierre (datos de cliente, sin egress, modelo ZDR)"}


def parse_frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, m.group(2)


def load_agents():
    agents = []
    for path in sorted(glob.glob(os.path.join(AGENTS_DIR, "**", "*.md"), recursive=True)):
        with open(path, "r", encoding="utf-8") as f:
            fm, _ = parse_frontmatter(f.read())
        folder = os.path.basename(os.path.dirname(path))
        zone, zlabel, _ = ZONES.get(folder, ("E2", "Zona E2", "🟥"))
        agents.append({
            "name": fm.get("name", os.path.splitext(os.path.basename(path))[0]),
            "folder": folder,
            "zone": zone,
            "model": fm.get("model", "inherit"),
            "tools": fm.get("tools", "(hereda)"),
            "perm": fm.get("permissionMode", "default"),
            "memory": fm.get("memory", "—"),
            "desc": fm.get("description", "").strip(),
        })
    return agents


def nid(name):
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def short(text, n=90):
    text = text.replace("\n", " ").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def build_mermaid(agents):
    L = ["```mermaid", "flowchart TB"]
    L.append('    ORQ["🧭 Orquestador · AGENTS.md<br/>sesión principal (hub) · fable"]')
    L.append('    SG{{"🛡️ scope_guard.py<br/>hook PreToolUse · barrera de alcance"}}')
    L.append('    BB[("🗒️ Blackboard<br/>contracts/engagement.json")]')
    L.append('    RAGDB[("📚 RAG KEV+EPSS<br/>rag/")]')
    for z in ZONE_ORDER:
        zin = [a for a in agents if a["zone"] == z]
        if not zin:
            continue
        L.append(f'    subgraph {z}["{ZONE_LABEL[z]}"]')
        for a in zin:
            L.append(f'        {nid(a["name"])}["{a["name"]}<br/><i>{a["model"]}</i>"]')
        L.append("    end")
    # Aristas (modelo hub-and-spoke + blackboard)
    L.append("    ORQ ==>|delega / recoge| E1")
    L.append("    ORQ ==>|delega / recoge| E2")
    L.append("    ORQ ==>|delega / recoge| E3")
    L.append("    E1 -.->|escribe targets| BB")
    L.append("    E2 -.->|escribe findings| BB")
    L.append("    E3 -.->|escribe lecciones/informe| BB")
    L.append("    BB -.->|reinyecta lecciones| ORQ")
    if any(a["name"] == "vuln-triage" for a in agents):
        L.append("    vuln_triage ==>|consulta CVE| RAGDB")
    L.append("    SG -.->|valida cada comando| E2")
    L.append("    ORQ -.->|lee alcance| SG")
    L.append("```")
    return "\n".join(L)


def build_doc(agents):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    contracts = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "contracts", "*")))
    rag = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "rag", "*.py")))
    hooks = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, ".claude", "hooks", "*.py")))
    n_by_zone = {z: len([a for a in agents if a["zone"] == z]) for z in ZONE_ORDER}

    doc = []
    doc.append("<!-- ⚠️ FICHERO AUTO-GENERADO por tools/gen_arch_diagram.py — NO editar a mano. -->")
    doc.append("<!-- Se regenera solo (hook PostToolUse) al crear/modificar/eliminar un agente. -->")
    doc.append("")
    doc.append("# 🗺️ Mapa de Arquitectura — Cyberseg Agents")
    doc.append("")
    doc.append(f"> **Generado:** {now} · **Refleja el estado real** del proyecto en ese momento.")
    doc.append(f"> Regenerar a mano: `python tools/gen_arch_diagram.py`")
    doc.append("")
    doc.append("## Qué es esto (para reconstruir contexto si se pierde)")
    doc.append("")
    doc.append("Suite de agentes para **pentesting / bug bounty autorizado**. Un **Orquestador** "
               "(sesión principal, `AGENTS.md`) coordina a los agentes especialistas mediante "
               "**hub-and-spoke**: él es el único que delega y recoge resultados; los agentes "
               "**no se hablan entre sí**, se comunican a través del **blackboard** "
               "(`contracts/engagement.json`). Un **hook de alcance** (`scope_guard.py`) bloquea "
               "de forma determinista cualquier comando contra un target fuera de "
               "`contracts/scope.json`. El agente `vuln-triage` consulta el **RAG de "
               "vulnerabilidades** (`rag/`, KEV+EPSS) para priorizar por explotación real.")
    doc.append("")
    doc.append(f"**Estado actual:** {len(agents)} agentes especialistas "
               f"(E1={n_by_zone['E1']}, E2={n_by_zone['E2']}, E3={n_by_zone['E3']}) "
               f"+ Orquestador + hook de alcance.")
    doc.append("")
    doc.append("## Diagrama")
    doc.append("")
    doc.append(build_mermaid(agents))
    doc.append("")
    doc.append("## Las 3 zonas de aislamiento")
    doc.append("")
    doc.append("| Zona | Propósito | Red | Datos | Riesgo |")
    doc.append("| :--- | :--- | :--- | :--- | :--- |")
    doc.append("| 🟦 **E1 Recon** | Mapear superficie de ataque | internet / ruta al target | sin datos de cliente | bajo |")
    doc.append("| 🟥 **E2 Explotación** | Confirmar y explotar | **solo** VLAN del engagement, por cliente, kill-switch | acceso al target | alto |")
    doc.append("| 🟩 **E3 Cierre** | Informe y aprendizaje | sin egress de datos crudos, ZDR | datos de cliente | medio |")
    doc.append("")
    doc.append("## Inventario de agentes (estado real)")
    doc.append("")
    doc.append("| Agente | Zona | Modelo | Permiso | Memoria | Tools | Función |")
    doc.append("| :--- | :---: | :--- | :--- | :--- | :--- | :--- |")
    for z in ZONE_ORDER:
        for a in [a for a in agents if a["zone"] == z]:
            doc.append(f"| **{a['name']}** | {a['zone']} | {a['model']} | {a['perm']} | "
                       f"{a['memory']} | {short(a['tools'], 40)} | {short(a['desc'], 70)} |")
    doc.append("")
    doc.append("## Componentes de soporte (estado real)")
    doc.append("")
    doc.append(f"- **Orquestador (hub):** `AGENTS.md` — sesión principal, no es un subagente.")
    doc.append(f"- **Hook de alcance:** {', '.join(hooks) or '—'} (PreToolUse, bloquea fuera de scope).")
    doc.append(f"- **Blackboard / contratos:** {', '.join(contracts) or '—'}.")
    doc.append(f"- **RAG de vulnerabilidades:** {', '.join(rag) or '—'} (KEV+EPSS, alimenta a vuln-triage).")
    doc.append("")
    doc.append("## Flujo de un engagement (resumen)")
    doc.append("")
    doc.append("1. **Init** → Orquestador lee `scope.json`, crea `engagement.json`.")
    doc.append("2. **Recon (E1)** → `osint-recon` (pasivo) → `active-recon` (activo) escriben `targets[]`.")
    doc.append("3. **Triage (E2)** → `vuln-triage` consulta el RAG, escribe `findings[]` priorizados.")
    doc.append("4. **Explotación (E2)** → `web-exploit`/`network-exploit` → `post-exploit` → "
               "`lateral-discovery` → `c2-exfil`. Cada acción que toca el target requiere aprobación humana.")
    doc.append("5. **Cierre (E3)** → `reporting` genera el informe; `knowledge-postmortem` extrae lecciones.")
    doc.append("")
    doc.append("Detalle: ver `README.md`, `ARCHITECTURE.md` y `docs/comms-protocol.md`.")
    doc.append("")
    return "\n".join(doc)


# ---- Lógica de hook: ¿el cambio afecta a la arquitectura? ----
REL_KEYS = [".claude/agents", "/contracts/", "/rag/", "agents.md",
            ".claude/settings.json", ".claude/hooks"]
DEL_RE = re.compile(r"\b(rm|del|erase|move|mv|remove-item|ri|rmdir|rd)\b", re.I)


def path_is_relevant(p):
    p = (p or "").replace("\\", "/").lower()
    return any(k in p for k in REL_KEYS)


def hook_should_regen(event):
    tool = event.get("tool_name", "")
    ti = event.get("tool_input", {}) or {}
    if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return path_is_relevant(ti.get("file_path", ""))
    if tool == "Bash":
        cmd = ti.get("command", "")
        return bool(DEL_RE.search(cmd)) and any(k in cmd.replace("\\", "/").lower() for k in REL_KEYS)
    return False


def generate():
    agents = load_agents()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(build_doc(agents))
    return agents


def main():
    if "--hook" in sys.argv:
        try:
            event = json.load(sys.stdin)
        except Exception:
            sys.exit(0)
        if not hook_should_regen(event):
            sys.exit(0)  # cambio irrelevante: no regenerar, no hacer ruido
        generate()
        sys.exit(0)
    agents = generate()
    counts = {z: len([a for a in agents if a["zone"] == z]) for z in ZONE_ORDER}
    summary = ", ".join("%s=%d" % (z, counts[z]) for z in ZONE_ORDER)
    print("[map] ARCHITECTURE_MAP.md regenerado con %d agentes (%s)." % (len(agents), summary))


if __name__ == "__main__":
    main()
