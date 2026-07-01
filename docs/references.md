# Referentes mundiales (investigación, junio 2026)

Esta arquitectura se basa en los patrones actuales de agentes de seguridad ofensiva y en
la documentación oficial vigente de las plataformas. Fechas indicadas donde son recientes.

## Frameworks multi-agente de pentesting (estado del arte)

- **PentAGI** — el proyecto de pentest con IA más estrellado de GitHub (~14.7k ★). Go +
  React. Patrón de **coordinador central + 4 sub-agentes** (Searcher, Coder, Installer,
  Pentester). Es el referente directo del patrón hub-and-spoke que usamos.
  https://github.com/vxcontrol/pentagi
- **CAI (Cybersecurity AI)** — Alias Robotics. Framework abierto, "de facto" para AI
  Security, basado en agentes y patrones agénticos. Miles de usuarios.
  https://github.com/aliasrobotics/CAI
- **HexStrike AI** — servidor MCP que conecta LLMs (Claude/GPT/Copilot) con 150+
  herramientas (Nmap, Burp, Ghidra, Metasploit). Modelo de "MCP de herramientas" que
  complementa nuestros agentes si quieres tooling real cableado.
  https://github.com/0x4m4/hexstrike-ai
- **VulnBot, D-CIPHER, MAPTA, Incalmo** — frameworks multi-agente citados en la literatura
  2025-2026 ("the swarm era"): planner + recon + exploit + reporter en paralelo.
- **awesome-cybersecurity-agentic-ai** — índice curado de proyectos del sector.
  https://github.com/raphabot/awesome-cybersecurity-agentic-ai

## Análisis y guías recientes (≤ ~1 mes)

- Help Net Security — "AI red teaming agents change how LLMs get tested" (21 may 2026).
  https://www.helpnetsecurity.com/2026/05/21/ai-red-teaming-agents-research/
- Help Net Security — "Training an AI agent to attack LLM applications like a real
  adversary" (Novee, 25 mar 2026).
  https://www.helpnetsecurity.com/2026/03/25/novee-ai-pentesting-agent/
- Cloud Security Alliance — "Agentic AI in Penetration Testing" (5 feb 2026).
  https://cloudsecurityalliance.org/blog/2026/02/05/ai-agents-and-how-they-are-used-in-pentesting
- Penligent — "The 2026 Ultimate Guide to AI Penetration Testing: The Era of Agentic Red
  Teaming". https://www.penligent.ai/hackinglabs/the-2026-ultimate-guide-to-ai-penetration-testing-the-era-of-agentic-red-teaming/
- arXiv 2512.09882 — "Comparing AI Agents to Cybersecurity Professionals in Real-World
  Penetration Testing".
- arXiv 2505.02077 — "Open Challenges in Multi-Agent Security: Towards Secure Systems of
  Interacting AI Agents" (base de nuestras decisiones de aislamiento y comms).

## Documentación de plataforma (formato de los agentes)

- **Claude Code — Subagentes** (objetivo principal). Formato `.claude/agents/*.md` con
  frontmatter (name, description, tools, model, permissionMode, memory, hooks...).
  https://code.claude.com/docs/en/sub-agents
- **Claude Code — Agent teams / background agents**: sesiones con buzón peer-to-peer y
  ejecución en paralelo. En Data Attack lo adoptamos como **bus A2A mediado** por el blackboard
  (el Orquestador enruta); la malla peer nativa queda **lab-only** por la atribución de hooks
  (ver `ARCHITECTURE.md §1`). https://code.claude.com/docs/en/agent-teams
- **opencode — Agents**: `.opencode/agent/*.md`, frontmatter (description, mode, model,
  temperature, permission). https://opencode.ai/docs/agents/
- **VoltAgent/awesome-claude-code-subagents** — 100+ ejemplos de subagentes.
  https://github.com/VoltAgent/awesome-claude-code-subagents

## Fuentes del RAG de vulnerabilidades / CVE (`rag/vulns.db`)

Base — qué es vulnerable y qué se explota de verdad:

- **CISA KEV** — vulnerabilidades explotadas activamente: https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- **EPSS (FIRST)** — probabilidad de explotación: https://www.first.org/epss/api
- **CVE 5.0 (MITRE CVE Services)** — CVSS del CNA + SSVC de CISA-ADP: https://cveawg.mitre.org/
- **ExploitDB** — exploits públicos: https://gitlab.com/exploit-database/exploitdb
- **Metasploit Framework** — módulos (db/modules_metadata_base.json): https://github.com/rapid7/metasploit-framework
- **Nuclei Templates** — plantillas de detección (cves.json): https://github.com/projectdiscovery/nuclei-templates

Frescura — CVE recién publicados (KEV va con meses de retraso); `rag/ingest_recent.py`:

- **CVEDetector** — canal de Telegram de CVE recientes; ingerimos su preview web público (sin auth):
  https://t.me/CVEDetector
- **MITRE cvelistV5** — `cves/deltaLog.json`, sin auth (la fuente que OpenCVE agrega por debajo):
  https://github.com/CVEProject/cvelistV5
- **OpenCVE** — API v2; opcional, requiere cuenta (`OPENCVE_USERNAME`/`OPENCVE_PASSWORD`):
  https://app.opencve.io/

Otras fuentes relevantes (opcionales, documentadas para ampliar): PoC-in-GitHub
(nomi-sec), trickest/cve, VulnCheck KEV/NVD++, Vulners, Sploitus, ENISA EUVD, InTheWild.

## Fuentes del RAG de conocimiento (`rag/knowledge/`)

El *cómo* (privesc, payloads, cadenas de ataque), complementario al RAG de vulnerabilidades. Todo el
corpus se indexa como **DATO inerte** (anti-inyección, C11): se descarga, se limpia y se busca; nunca se
ejecuta ni se interpreta como instrucción. Ingesta con `rag/knowledge/refresh_kb.py`.

**Capa 1 — estructurada** (`kb.db`, comando por técnica; stdlib):

- **GTFOBins** — binarios Unix para bypass/privesc: https://github.com/GTFOBins/GTFOBins.github.io
- **LOLBAS** — binarios/scripts legítimos de Windows (LOLBins): https://github.com/LOLBAS-Project/LOLBAS
- **Atomic Red Team** (Red Canary) — comandos por técnica ATT&CK: https://github.com/redcanaryco/atomic-red-team
- **MITRE ATT&CK** — STIX de `attack-stix-data` (la taxonomía también guía el flujo; aquí es la fuente de
  datos que ingerimos): https://github.com/mitre-attack/attack-stix-data

**Capa 2 — semántica** (`kb_vec.db`, recuperación por significado; `refresh_kb.py --semantic`):

- **HackTricks** — wiki de pentest/privesc: https://github.com/HackTricks-wiki/hacktricks
- **PayloadsAllTheThings** (swisskyrepo) — payloads y bypasses por categoría: https://github.com/swisskyrepo/PayloadsAllTheThings
- **PEASS-ng** (carlospolop) — enumeración de privesc (linPEAS/winPEAS): https://github.com/carlospolop/PEASS-ng
- **Anthropic-Cybersecurity-Skills** (mukul975) — 817 skills de ciberseguridad MITRE-mapeadas, con avisos de
  autorización/ROE en su prosa (corpus PASIVO: no gatea la recuperación); se ingieren solo los `SKILL.md`.
  **Licencia Apache-2.0.** https://github.com/mukul975/Anthropic-Cybersecurity-Skills
- **Feeds de frescura**: **0dayfans** (RSS curado de DayZeroSec, https://0dayfans.com/feed.rss),
  **Hacker News** (minado por keywords vía API Algolia, https://hn.algolia.com/api) y la prosa de
  **CVEDetector** (https://t.me/CVEDetector).
- **Motor de embeddings** (local, sin nube): `sentence-transformers` con
  **BAAI/bge-small-en-v1.5** (https://huggingface.co/BAAI/bge-small-en-v1.5) + KNN con
  **sqlite-vec** (https://github.com/asg017/sqlite-vec).

## Marcos de metodología incorporados

- **MITRE ATT&CK** (Enterprise) — taxonomía de tácticas que estructura los agentes de E2.
- **OWASP WSTG / Top 10** — base del agente `web-exploit`.
- **CISA KEV** — catálogo de vulnerabilidades explotadas activamente (prioridad nº1 en
  `vuln-triage`). https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- **PTES** — fases de pentest que inspiran el flujo del Orquestador.
