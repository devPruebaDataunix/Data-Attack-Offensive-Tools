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

## Modelos gratuitos (LAB-ONLY) — v1.9.0

El espejo opencode declara varios providers **gratuitos** para practicar/desarrollar contra
**laboratorios propios sin gastar**. Solo afectan a opencode; el bot real de engagements sigue
**100% Anthropic**. **Reglas duras (innegociables):** LAB-ONLY, **jamás datos de cliente**, **nunca
en E2/E3** (air-gapped). En el perfil ACTIVO se enrutan solo agentes mecánicos (recon/escaneo/parseo);
nunca triage/explotación/reporting — **salvo** el perfil *NVIDIA LAB completo* (más abajo), que enruta
toda la cadena a NVIDIA (no entrena s/ ToS) solo para smoke-test de cableado contra labs sintéticos.

| provider | npm | env var | clase |
| :--- | :--- | :--- | :--- |
| `groq` | `@ai-sdk/openai-compatible` | `GROQ_API_KEY` | **no entrena** ✅ (perfil activo) |
| `cerebras` | `@ai-sdk/openai-compatible` | `CEREBRAS_API_KEY` | **no entrena** ✅ (perfil activo) |
| `nvidia` (NIM) | `@ai-sdk/openai-compatible` | `NVIDIA_API_KEY` | no entrena *(s/ ToS)* ✅ · 100+ modelos (opt-in) |
| `deepseek` | `@ai-sdk/openai-compatible` | `DEEPSEEK_API_KEY` | entrena/residencia ⚠️ (opt-in) |
| `minimax` | `@ai-sdk/anthropic` | `MINIMAX_API_KEY` | entrena/residencia ⚠️ (opt-in) |
| `zhipu` (GLM) | `@ai-sdk/anthropic` | `ZHIPU_API_KEY` | entrena/residencia ⚠️ (opt-in) |
| `openrouter` | `@ai-sdk/openai-compatible` | `OPENROUTER_API_KEY` | los `:free` entrenan ⚠️ (opt-in) |

- **Perfil activo (`tools/routing.json`)**: los 5 agentes mecánicos van a **Groq/Cerebras**, que **no
  entrenan** con los prompts (riesgo de fuga menor). El resto de providers quedan **declarados pero
  NO enrutados** (opt-in manual: añade su `provider/model` a `routing.json` y exporta su clave).
- **NVIDIA NIM (opt-in, no entrena)**: una sola clave (`NVIDIA_API_KEY`) da acceso a 100+ modelos
  gratis, incluidos varios de **razonamiento** (DeepSeek-R1, Llama-3.3-Nemotron-Super-49B). Útil para
  **smoke-test del pipeline contra laboratorios propios sin gastar Anthropic**. Su ToS (API Catalog)
  declara que no entrena con los prompts (stateless), pero NVIDIA *disclaim* PII/PHI/PCI → **LAB-ONLY
  igual** (jamás cliente/E2/E3). El `auto-deploy.sh` la pide de forma interactiva (la escribe en
  `.opencode/opencode.env`, gitignored). Para enrutar un agente a razonamiento NVIDIA, p.ej.:
  `"vuln-triage": "nvidia/deepseek-ai/deepseek-r1"` (recuerda el gotcha del `/`: provider `nvidia`,
  modelo `deepseek-ai/deepseek-r1`, que debe existir en `provider.nvidia.models`).

### Perfil NVIDIA LAB completo (smoke-test del GATE)

Para correr **toda** la cadena con modelos free de NVIDIA (validar el cableado del pipeline contra
**laboratorios sintéticos propios** sin gastar Anthropic), pega este `routes` en `tools/routing.json`
y re-corre `python tools/sync_opencode.py`. Análisis modelo↔agente en
[`docs/cost-optimization.md`](../docs/cost-optimization.md).

```json
"routes": {
  "osint-recon":      "nvidia/meta/llama-3.3-70b-instruct",
  "active-recon":     "nvidia/meta/llama-3.3-70b-instruct",
  "recon-suite":      "nvidia/meta/llama-3.3-70b-instruct",
  "web-fuzzing":      "nvidia/meta/llama-3.3-70b-instruct",
  "nuclei":           "nvidia/meta/llama-3.3-70b-instruct",
  "vuln-triage":      "nvidia/deepseek-ai/deepseek-r1",
  "sqlmap":           "nvidia/openai/gpt-oss-120b",
  "metasploit":       "nvidia/openai/gpt-oss-120b",
  "netexec":          "nvidia/openai/gpt-oss-120b",
  "sliver":           "nvidia/openai/gpt-oss-120b",
  "c2-exfil":         "nvidia/openai/gpt-oss-120b",
  "lateral-discovery":"nvidia/nvidia/llama-3.3-nemotron-super-49b-v1",
  "network-exploit":  "nvidia/nvidia/llama-3.3-nemotron-super-49b-v1",
  "web-exploit":      "nvidia/deepseek-ai/deepseek-r1",
  "post-exploit":     "nvidia/deepseek-ai/deepseek-r1",
  "ai-security":      "nvidia/deepseek-ai/deepseek-r1",
  "reporting":        "nvidia/nvidia/llama-3.3-nemotron-super-49b-v1"
}
```

> **Solo cableado, no medición.** Sirve para depurar que el flujo end-to-end corre sin errores; **la
> corrida OFICIAL del GATE se mide con Claude** (los free degradan calidad y topan a ~40 RPM/modelo, lo
> que con 18 agentes en paralelo puede throttlear). `knowledge-postmortem` se deja FUERA a propósito
> (escribe lecciones a memoria → conserva Anthropic). **LAB-ONLY**: jamás cliente, nunca E2/E3. Exporta
> `NVIDIA_API_KEY` (el `auto-deploy.sh` la pide). Revertir = perfil activo (5 mecánicos) o `routes: {}`.
> Tras pegar el perfil, corre `python tools/verify_opencode.py` para validar el cruce ruta↔provider↔modelo
> (este bloque del README no lo valida nadie automáticamente; el verify solo cruza el `routing.json` activo).
- **Claves por entorno, sin `auth login`**: opencode lee `{env:VAR}` en runtime. Copia
  `opencode.example.env` → `opencode.env`, rellénalo y cárgalo (`set -a; . ./opencode.env; set +a`).
  `opencode.env` (y todo `*.env`) está gitignored; la plantilla `*.example.env` sí se versiona.
- **Gotcha OpenRouter / GPT-OSS**: sus IDs llevan `/` (p.ej. `deepseek/deepseek-chat-v3-0324:free`,
  `openai/gpt-oss-120b`). En `routing.json` el valor se parte por el **primer** `/`
  (`openrouter/deepseek/deepseek-chat-v3-0324:free` → provider `openrouter`, modelo
  `deepseek/deepseek-chat-v3-0324:free`), y ese modelo debe existir como clave en
  `provider.<x>.models` de `opencode.json`.
- **MiniMax/GLM son Anthropic-compatible** (`@ai-sdk/anthropic` + `baseURL` propio), no
  OpenAI-compatible. DeepSeek/Groq/Cerebras/OpenRouter sí son OpenAI-compatible.
- **Los IDs de modelo y los free-tier CAMBIAN**: re-confirma contra la doc de cada provider /
  [models.dev](https://models.dev) antes de enrutar. `tools/verify_opencode.py` valida el cruce
  ruta↔provider↔modelo, así que un id inexistente **no pasa silenciosamente**.
- **Revertir** a 100% Anthropic: vacía `routes` (`{}`) en `routing.json` y re-corre
  `python tools/sync_opencode.py`.
