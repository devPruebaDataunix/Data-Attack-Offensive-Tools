# Optimización de coste (v1.4.0)

Cómo se reparte el gasto del framework y qué palancas hay para reducirlo **sin perder capacidad
de resolver la box**. Resumen: el grueso del coste está en el **Orquestador**, no en los subagentes.

## Modelo de coste

| Componente | Por qué pesa |
| :--- | :--- |
| **Orquestador** (sesión principal del bot / `claude -p`) | Corre en **cada turno** con el contexto creciente (AGENTS.md + preset + blackboard). Es el **término dominante**. |
| **Subagentes** | Uno por `Task`; coste acotado a su tarea. 5 mecánicos en haiku, 8 en sonnet, 4 en opus. |
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

## Tier de modelos por agente (4 opus · 8 sonnet · 6 haiku)

| Tier | Agentes | Criterio |
| :--- | :--- | :--- |
| `claude-opus-4-8` | web-exploit, post-exploit, ai-security, reporting | razonamiento profundo que **rompe la box** / calidad del informe |
| `claude-sonnet-4-6` | vuln-triage, sqlmap, metasploit, netexec, sliver, lateral-discovery, c2-exfil, network-exploit | tool-driving con juicio; el RAG hace el trabajo pesado |
| `claude-haiku-4-5` | osint-recon, recon-suite, active-recon, web-fuzzing, nuclei, knowledge-postmortem | recon/escaneo/parseo mecánico (sin `effort`: Haiku da 400) |

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

## Modelos gratis

- **opencode-lab (cableado).** `tools/routing.json` enruta 5 agentes mecánicos a **Ollama local**
  (coste cero, el dato no sale del equipo). Solo afecta al runtime **opencode** — sirve para
  practicar/desarrollar contra laboratorios sin gastar. El bot real (engagements) **no** lo usa.
- **Free cloud en el bot (NO implementado, decisión deliberada).** Es viable en fase lab (sin datos
  de cliente) vía un gateway LiteLLM (`ANTHROPIC_BASE_URL`) con un toggle reversible, PERO: los
  free-tier tienen rate-limits agresivos, Claude Code **no tiene fallback** (si el proveedor corta, la
  llamada muere a mitad de run) y los modelos no-Claude dan *quirks* de tool-protocol. Secuencia
  recomendada: aplicar las palancas de arriba, **re-medir**, y montar el gateway free **solo si sigue
  caro**. Cuando se usen datos de cliente reales → el bot vuelve a 100% Anthropic.

## Qué NO se tocó

El gate de alcance (`scope_guard`), los guardarraíles C11–C13 y la aprobación humana por acción
quedan intactos. La optimización es de **coste**, no de seguridad.
