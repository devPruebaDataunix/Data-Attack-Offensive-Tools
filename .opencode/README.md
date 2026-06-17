# Espejo opencode de Data Attack

Esta carpeta es el **espejo opencode** de la suite. Los agentes (`agent/*.md`) los GENERA
`tools/sync_opencode.py` desde `.claude/agents/` — no los edites a mano. `opencode.json` es la
config de opencode (estatica).

> **No metas claves de documentacion tipo `$comment` en `opencode.json`.** opencode valida el
> fichero con un esquema estricto (Zod `.strict()`) y **aborta** (`Configuration is invalid ...
> Unrecognized keys`, y sobre Bun puede acabar en `IOT instruction`/SIGABRT) ante cualquier clave
> que no reconozca. Solo `$schema` esta permitida. Documenta aqui, no en el JSON.
> `tools/verify_opencode.py` rechaza claves de nivel superior desconocidas para que no vuelva a
> colarse. (Nota: `tools/routing.json` SI puede llevar `$comment` porque lo lee nuestro propio
> Python, no opencode.)

## opencode.json — notas

- **Orquestador**: es el agente `primary` (`agent.orchestrator`, `claude-opus-4-8`); los 18
  especialistas son `subagents` en `agent/*.md`. Ver `AGENTS.md`.
- **Provider Ollama (local)**: declarado para el piloto de routing (ver `tools/routing.json`).
  Keyless: habla OpenAI-compatible contra el daemon local (`http://localhost:11434/v1`). Inerte
  hasta que un agente referencie `ollama/...`; el Orquestador y los agentes no enrutados siguen en
  `anthropic/*`. Requiere `ollama serve` + `ollama pull <modelo>`. Si las tool-calls fallan, sube
  `num_ctx` en Ollama (~16k-32k).
- **A2A**: el bus A2A (mensajes entre agentes) es del runtime Claude Code / bot, no del espejo
  opencode — `sync_opencode.py` no propaga el bloque `a2a:` del frontmatter. opencode es un espejo
  de desarrollo/laboratorio para practicar con modelos locales, no para correr engagements con A2A.
