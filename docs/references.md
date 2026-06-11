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
- **Claude Code — Agent teams / background agents**: para sesiones que se comunican entre
  sí y ejecución en paralelo monitorizada.
  https://code.claude.com/docs/en/agent-teams
- **opencode — Agents**: `.opencode/agent/*.md`, frontmatter (description, mode, model,
  temperature, permission). https://opencode.ai/docs/agents/
- **VoltAgent/awesome-claude-code-subagents** — 100+ ejemplos de subagentes.
  https://github.com/VoltAgent/awesome-claude-code-subagents

## Fuentes de exploits/CVE de la ingesta (RAG)

- **CISA KEV** — vulnerabilidades explotadas activamente: https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- **EPSS (FIRST)** — probabilidad de explotación: https://www.first.org/epss/api
- **CVE 5.0 (MITRE CVE Services)** — CVSS del CNA + SSVC de CISA-ADP: https://cveawg.mitre.org/
- **ExploitDB** — exploits públicos: https://gitlab.com/exploit-database/exploitdb
- **Metasploit Framework** — módulos (db/modules_metadata_base.json): https://github.com/rapid7/metasploit-framework
- **Nuclei Templates** — plantillas de detección (cves.json): https://github.com/projectdiscovery/nuclei-templates
- Otras fuentes relevantes (opcionales, documentadas para ampliar): PoC-in-GitHub
  (nomi-sec), trickest/cve, VulnCheck KEV/NVD++, Vulners, Sploitus, ENISA EUVD, InTheWild.

## Marcos de metodología incorporados

- **MITRE ATT&CK** (Enterprise) — taxonomía de tácticas que estructura los agentes de E2.
- **OWASP WSTG / Top 10** — base del agente `web-exploit`.
- **CISA KEV** — catálogo de vulnerabilidades explotadas activamente (prioridad nº1 en
  `vuln-triage`). https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- **PTES** — fases de pentest que inspiran el flujo del Orquestador.
