# Cyberseg Agents — Suite de agentes para pentesting / bug bounty autorizado

> ⚠️ **USO AUTORIZADO ÚNICAMENTE.** Todos estos agentes están diseñados para operar
> exclusivamente dentro del alcance de un contrato de pentest firmado o de un programa
> de bug bounty con scope explícito. El fichero `contracts/scope.json` es la fuente de
> verdad del alcance y un *hook* lo aplica de forma determinista antes de cada acción.
> Operar fuera de scope es ilegal. No lo hagas.

Suite de **17 agentes especialistas (de fase + de herramienta) + orquestador + guardián de
alcance (hook) + RAG de vulnerabilidades + bot de Telegram**, para asistir todas las fases de
un engagement ofensivo. Construida sobre el sistema nativo de **subagentes de Claude Code** y
replicada para **opencode**.

## 🚀 Despliegue en Kali (E2)
Una Kali nueva desde 0 → entorno completo con un comando:
```bash
git clone <URL-de-tu-repo-privado> data-attack && cd data-attack
chmod +x deploy/*.sh && sudo ./deploy/auto-deploy.sh
```
Instala y **verifica** todo el toolchain (nmap, ProjectDiscovery, ffuf, sqlmap, metasploit,
netexec, sliver, BloodHound…), Claude Code, el RAG y el **bot de Telegram**. Ver **[DEPLOY.md](DEPLOY.md)**
y **[bot/README.md](bot/README.md)**.

## Plataformas soportadas

| Plataforma | Cómo se carga | Estado |
| :--- | :--- | :--- |
| **Claude Code** (CLI + extensión VS Code) | `.claude/agents/*.md` + `.claude/settings.json` | ✅ Objetivo principal |
| **opencode** | `.opencode/agent/*.md` + `opencode.json` | ✅ Espejo equivalente |
| VS Code (extensión Claude Code) | Usa la misma carpeta `.claude/` del workspace | ✅ Sin cambios |

> **Nota sobre "VS Code Agent v1.123.0":** la forma correcta de tener estos agentes
> en VS Code es a través de la **extensión Claude Code**, que lee esta misma carpeta
> `.claude/`. No hace falta opencode salvo que prefieras su runtime. Claude Code ya
> incorpora de forma nativa exactamente lo que buscabas (subagentes especializados,
> con tools/permremiso/modelo/memoria por agente y orquestación hub-and-spoke).

## Instalación rápida (Claude Code)

```powershell
# 1. Copia el contenido en la raíz de tu workspace de engagement
#    (la carpeta .claude/ debe quedar en la raíz del proyecto)
# 2. Define el alcance autorizado ANTES de nada:
copy contracts\scope.example.json contracts\scope.json
#    edita contracts\scope.json con los dominios/IPs/CIDR del engagement
# 3. Abre Claude Code en esa carpeta y verifica los agentes:
#    /agents
# 4. Verifica que el hook de scope está activo:
#    revisa .claude/settings.json -> hooks.PreToolUse
```

## Estructura

```
cyberseg-agents/
├── README.md                 ← este fichero
├── ARCHITECTURE.md           ← auditoría crítica + modelo de comunicación + zonas
├── ARCHITECTURE_MAP.md       ← 🗺️ mapa AUTO-GENERADO (se regenera solo en cada cambio)
├── AGENTS.md                 ← playbook del ORQUESTADOR (agente principal)
├── contracts/                ← el "blackboard": esquemas de estado compartido
│   ├── scope.example.json    ← plantilla de alcance autorizado
│   ├── engagement.schema.json
│   ├── finding.schema.json
│   └── target.schema.json
├── docs/
│   ├── references.md         ← referentes mundiales (con fechas)
│   ├── comms-protocol.md     ← protocolo de handoff hub-and-spoke
│   ├── reporting-guide.md    ← cómo redactan los profesionales (alimenta a reporting)
│   └── humanizer-checklist.md← evitar que el informe lea como generado por IA
├── templates/
│   └── report-template.md    ← esqueleto del informe que rellena reporting
├── report/                   ← salida de informes (SAMPLE + INFORME del dry run)
├── dryrun/                   ← prueba end-to-end segura (run_dryrun.py, sin atacar)
├── rag/                      ← RAG de vulnerabilidades KEV+EPSS (alimenta vuln-triage)
│   ├── README.md             ← uso + ruta de producción Supabase/n8n
│   ├── db.py · ingest_kev.py · enrich_epss.py · query_vulns.py · refresh.py
├── .claude/
│   ├── settings.json         ← hooks (scope guard), permisos, modelo de subagentes
│   ├── hooks/
│   │   └── scope_guard.py    ← gate determinista PreToolUse
│   └── agents/               ← los 10 subagentes especialistas
│       ├── recon/
│       ├── analysis/
│       ├── exploitation/
│       └── closing/
└── .opencode/
    └── agent/                ← espejo de los agentes para opencode
```

## El bucle de aprendizaje basado en errores

El agente `knowledge-postmortem` tiene `memory: project` activado: tras cada intento
(funcionó / falló / por qué) escribe lecciones en su memoria persistente y en
`contracts/engagement.json`. El Orquestador reinyecta esas lecciones a los agentes de
explotación en el siguiente target. **El modelo no se reentrena** — el aprendizaje vive
en la memoria + RAG, igual que un `WF_PostMortem`.

Ver `ARCHITECTURE.md` para el detalle completo.

## Mapa de arquitectura auto-actualizable

`ARCHITECTURE_MAP.md` es un mapa **auto-generado** (diagrama Mermaid + inventario real de
agentes) que se explica a sí mismo para reconstruir el contexto si se pierde. Se **regenera
solo** vía hook `PostToolUse` cada vez que se **crea, modifica o elimina** un agente, hook,
contrato o módulo del RAG — así siempre refleja el estado real. Regenerar a mano:

```powershell
python tools\gen_arch_diagram.py
```

## Mantenerse al día con zero-days / vulnerabilidades

El módulo `rag/` mantiene a `vuln-triage` al día con lo que de verdad se explota, sin
reentrenar el modelo. Arráncalo y prográmalo a diario:

```powershell
python rag\refresh.py --epss-all                 # descarga CISA KEV + scores EPSS
schtasks /Create /SC DAILY /ST 06:00 /TN "cyberseg-rag-refresh" /TR "python <ruta>\rag\refresh.py --epss-all"
```

Ver `rag/README.md` (incluye la ruta de producción a Supabase + n8n para tu equipo).
