# Optimización de coste (v1.4.0)

Cómo se reparte el gasto del framework y qué palancas hay para reducirlo **sin perder capacidad
de resolver la box**. Resumen: el grueso del coste está en el **Orquestador**, no en los subagentes.

## Modelo de coste

| Componente | Por qué pesa |
| :--- | :--- |
| **Orquestador** (sesión principal del bot / `claude -p`) | Corre en **cada turno** con el contexto creciente (AGENTS.md + preset + blackboard). Es el **término dominante**. |
| **Subagentes** | Uno por `Task`; coste acotado a su tarea. 9 mecánicos en haiku, 11 en sonnet, 7 en opus. |
| **Prompt caching** | **Automático** en Claude Code / Agent SDK (system prompt + tools + defs de agente + contexto estático). No hay que activarlo. Cambiar de modelo/effort a media sesión **invalida** la caché. |

> El bot **ya imprime el coste real** al terminar cada orden: `✅ Completado · N turnos · $X.XX`
> (`bot/intel/runner.py`). Re-medir = correr un engagement y leer esa línea. No hace falta instrumentar nada.

## Re-medir el coste con agentsview (v1.8.0)

Para un desglose **histórico y por agente** (más allá del total por orden que imprime el bot), la
suite integra [agentsview](https://github.com/kenn-io/agentsview): analítica **local-first** que lee
`~/.claude/projects/` y calcula coste/tokens por sesión, día, modelo y agente. El `auto-deploy`
instala el binario (versión fijada + verificación SHA256); el daemon se arranca a propósito:

```bash
./deploy/agentsview.sh up        # dashboard en http://127.0.0.1:8080 (local-only, telemetria off)
./deploy/agentsview.sh usage     # desglose de coste/uso por dia en la terminal (--agent, --since…)
```

**Higiene (innegociable):** los transcripts de `~/.claude/projects/` contienen **datos de cliente** en
claro → agentsview se usa **siempre local** (vincula a `127.0.0.1`, telemetría off con
`AGENTSVIEW_TELEMETRY_ENABLED=0`), **nunca** con `--public-url`, y en una máquina del operador. Es
read-only sobre los transcripts. Decláralo en el NDA/ROE como índice local de sesiones.

## Tier de modelos por agente (7 opus · 11 sonnet · 9 haiku)

| Tier | Agentes | Criterio |
| :--- | :--- | :--- |
| `claude-opus-4-8` | web-exploit, api-exploit, mobile-exploit, firmware-exploit, post-exploit, ai-security, reporting | razonamiento profundo que **rompe la box** / calidad del informe |
| `claude-sonnet-4-6` | vuln-triage, sqlmap, metasploit, netexec, ad-enum, kerberos, adcs, sliver, lateral-discovery, c2-exfil, network-exploit | tool-driving con juicio; el RAG hace el trabajo pesado |
| `claude-haiku-4-5` | osint-recon, recon-suite, active-recon, api-recon, mobile-recon, firmware-recon, web-fuzzing, nuclei, knowledge-postmortem | recon/escaneo/parseo mecánico (sin `effort`: Haiku da 400) |

Principio: opus solo donde un peor razonamiento te hace **fallar la box** (y gastar MÁS turnos
rehaciendo). Bajar de tier un agente mecánico no cambia el resultado y abarata cada llamada.

## Palancas del Orquestador (env, reversibles)

| Variable | Efecto | Defecto |
| :--- | :--- | :--- |
| `ORCH_MODEL` | Modelo del Orquestador | `claude-opus-4-8` |
| `ORCH_EFFORT` | `effort` del Orquestador (`low`…`max`); más bajo = menos tokens y menos preámbulo | `medium` |
| `ORCH_MAX_USD` | Techo de coste por orden en USD; corta al alcanzarlo | sin techo |

Se aplican de forma **defensiva**: si la versión instalada del SDK no expone `effort`/`max_budget_usd`,
el runner degrada (effort → flag CLI; techo USD se omite) **sin romper la sesión**.

## Modelos gratis (espejo opencode · v1.9.0)

- **Free cloud no-train (perfil ACTIVO).** `tools/routing.json` enruta los 5 agentes mecánicos
  (recon/escaneo/parseo) a **Groq y Cerebras**, providers gratuitos que **no entrenan** con los
  prompts. Solo afecta al runtime **opencode** — sirve para practicar/desarrollar contra
  **laboratorios propios** sin gastar. Claves por entorno (`GROQ_API_KEY`/`CEREBRAS_API_KEY`, ver
  `.opencode/opencode.example.env`); opencode las lee con `{env:VAR}`, sin `auth login`.
- **Más catálogo (opt-in manual).** `DeepSeek`, `MiniMax`, `GLM (zhipu)` y `OpenRouter :free` están
  **declarados** en `.opencode/opencode.json` pero **NO enrutados** (entrenan/residencia sensible).
  Para usar uno: pon su `provider/model` en `routing.json` y exporta su clave. Detalle y *gotchas*
  (IDs con `/`, Anthropic-compatible vs OpenAI-compatible) en `.opencode/README.md`.
- **Alternativa offline.** Cambia la ruta a `ollama/<modelo>` (coste cero, el dato no sale del
  equipo; requiere `ollama serve` + `ollama pull`).
- **Reglas duras (innegociables).** Todo lo anterior es **LAB-ONLY**: **jamás** datos de cliente,
  **nunca** en E2/E3. En el **perfil ACTIVO** solo van a free los agentes **mecánicos** (nunca
  triage/explotación/reporting): el riesgo de fuga es mayor en providers que entrenan. La **única
  excepción** es el perfil *NVIDIA LAB completo* (ver abajo) — NVIDIA no entrena (s/ ToS) y se usa solo
  para **smoke-test de cableado contra labs sintéticos** (la medición oficial del GATE sigue en Claude).
  Revertir a 100% Anthropic = vaciar `routes` (`{}`) + `python tools/sync_opencode.py`.
- **El bot real sigue 100% Anthropic.** El free cloud **en el bot** sigue **sin implementar**
  (decisión deliberada): los free-tier tienen rate-limits agresivos, Claude Code **no tiene
  fallback** (si el proveedor corta, la llamada muere a mitad de run) y los modelos no-Claude dan
  *quirks* de tool-protocol. Para engagements con datos de cliente → 100% Anthropic.

## Modelos free de RAZONAMIENTO — NVIDIA NIM (espejo opencode · v2.6.0)

Groq/Cerebras solo ofrecen modelos **no-razonadores**, por eso el perfil activo solo enruta los 5
agentes **mecánicos**. **NVIDIA NIM cambia eso**: una sola clave (`NVIDIA_API_KEY`) da modelos de
**razonamiento gratis** (DeepSeek-R1, Llama-3.3-Nemotron-Super-49B) + generalistas (Llama-3.3-70B,
GPT-OSS-120B). Eso permite, **en laboratorio**, llevar a free **toda** la cadena —no solo recon— para
**smoke-test del pipeline del GATE sin gastar Anthropic**.

**Análisis modelo↔agente (qué modelo NVIDIA encaja con cada tier):**

| Tier (modelo Anthropic) | Agentes | Modelo NVIDIA free recomendado | Por qué |
| :--- | :--- | :--- | :--- |
| haiku (mecánico) | osint-recon, active-recon, recon-suite, api-recon, mobile-recon, firmware-recon, web-fuzzing, nuclei | `meta/llama-3.3-70b-instruct` | recon/escaneo/parseo: rápido y suficiente |
| sonnet (tool-driving) | sqlmap, metasploit, netexec, sliver, c2-exfil | `openai/gpt-oss-120b` | conduce tools con juicio; el RAG hace lo pesado |
| sonnet (razona-medio) | vuln-triage, lateral-discovery, network-exploit | `nvidia/llama-3.3-nemotron-super-49b-v1` | correlación/decisión con razonamiento |
| opus (razona-profundo) | web-exploit, api-exploit, mobile-exploit, firmware-exploit, post-exploit, ai-security | `deepseek-ai/deepseek-r1` | razonamiento que **rompe la box** |
| opus (informe) | reporting | `nvidia/llama-3.3-nemotron-super-49b-v1` | redacción estructurada |
| — (memoria) | knowledge-postmortem | *(se queda en Anthropic)* | escribe lecciones a memoria; no arriesgar calidad |

> **Caveat innegociable.** Este perfil "NVIDIA LAB completo" es **solo para smoke-test del cableado**
> del pipeline contra **laboratorios sintéticos propios** (validar que el flujo end-to-end corre sin
> errores). **La medición OFICIAL de capacidad del GATE se corre con Claude** — los free-tier degradan
> calidad y tienen rate-limits (~40 RPM). Sigue siendo **LAB-ONLY**: jamás datos de cliente, nunca
> E2/E3; el bot real de engagements es **100% Anthropic**. **El espejo opencode NO ejecuta los hooks
> deterministas (scope_guard/C1–C21) ni el bus A2A** (es inherente a opencode, no a NVIDIA): corrobora
> el cableado, no es la medición oficial. El perfil vive en el fichero versionado
> `tools/routing.nvidia-lab.json`; aplícalo con **`python tools/apply_routing.py nvidia-lab`** (revierte
> con `python tools/apply_routing.py default`), o el `auto-deploy.sh` lo ofrece (`--opencode-nvidia` /
> interactivo). El Orquestador y `knowledge-postmortem` se quedan en Anthropic.

## Qué NO se tocó

El gate de alcance (`scope_guard`), los guardarraíles deterministas (C11–C21) y la aprobación humana
por acción quedan intactos. La optimización es de **coste**, no de seguridad.
