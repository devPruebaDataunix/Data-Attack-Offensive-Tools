# Auditoría de configuración (v1.11.0)

Contraste de **toda** la configuración del repo contra la **spec oficial vigente** de Claude Code
(2.1.x, 2026: `code.claude.com/docs`) y de opencode. Objetivo: baseline auditado, sin incongruencias.

## Resultado: la configuración es VÁLIDA y VIGENTE

Confirmado contra la doc oficial de subagentes (campos de frontmatter soportados; solo `name` y
`description` son obligatorios):

| Superficie | Estado |
| :--- | :--- |
| Frontmatter de los 27 agentes (`name`, `description`, `tools`, `model`, `permissionMode`, `effort`, `color`, `memory`) | **Válido** — todos los campos existen en la spec. |
| `model` por agente (IDs completos `claude-opus-4-8`/`-sonnet-4-6`/`-haiku-4-5`) | **Válido** (acepta IDs completos o alias). |
| `settings.json` (`permissions`, `hooks`) | **Válido**; se añadió `$schema` y se quitaron las claves `$comment*` (los settings de proyecto son **estrictos**: un fichero que no valida se rechaza entero). |
| Hooks (PreToolUse/PostToolUse + matchers) | **Válido**; rutas migradas a `${CLAUDE_PROJECT_DIR}` + `python3` (portabilidad). |
| Skills (`SKILL.md`: `name`, `description`) | **Válido**; descripciones muy por debajo del tope (~1.5k chars). |
| Plugin manifest (`.claude-plugin/plugin.json`) | **Válido**; enriquecido con `homepage`/`repository`/`license`/`keywords`. |
| `.opencode/opencode.json` (schema estricto Zod) | **Válido** (sin `$comment`; ver `.opencode/README.md`). |

## Decisiones INTENCIONALES (no son fallos — no se tocan)

- **`effort` ausente en los 6 agentes Haiku**: los niveles de effort dependen del modelo; Haiku no
  los usa. Correcto.
- **Bloque `a2a` solo en los 14 agentes con pareja**: los 7 sin pares pasan por el hub. Correcto.
- **`memory: project` solo en `knowledge-postmortem`**: deliberado por **seguridad** — memoria
  persistente en más agentes filtraría datos entre clientes/engagements. NO se amplía.
- **`permissionMode: default` explícito** en cada agente: válido (redundante pero explícito).

## Cambios aplicados en v1.11.0

- **Hardening de `settings.json`**: `$schema` (autocompletado/validación en editores) y eliminación de
  `$comment`/`$comment_modelos` (el rationale del tier de modelos vive en `docs/cost-optimization.md`).
- **Robustez de hooks**: comandos con `${CLAUDE_PROJECT_DIR}/…` y `python3`.
- **Manifest del plugin** enriquecido (homepage, repository, license, keywords).
- **Supervisión humana configurable** (ver abajo) — enmienda de `CONSTITUTION.md` §2 a **v2.0.0**.

## Modos de supervisión humana (`approval_mode`)

Quién aprueba **por acción** lo decide el operador autorizado. Fuente: `constraints.approval_mode`
en `scope.json`, o la variable `ORCH_APPROVAL_MODE` (gana el entorno). Default **`critical`**.

| Modo | Qué pide aprobación humana | Para qué |
| :--- | :--- | :--- |
| `full` | **Todo lo de riesgo** (tiers ask + crítico) | Máxima supervisión / cliente sensible. |
| `critical` *(def.)* | Solo lo **crítico** (C2/implantes/`msfvenom` = tier *dual*) | Equilibrio: fluye recon/scan/explotación, gated lo peligroso. |
| `auto` | **Nada** | Lab autorizado / operación autónoma. |

**Innegociable, en TODOS los modos** (no es "humano en el bucle", son puertas deterministas):
`scope_guard` (alcance §1), `budget_guard` (kill-switch C13), `secret_scan`, `a2a_guard` y el
no-daño (§5) **se aplican siempre** — un `deny` de un guardarraíl gana sobre cualquier auto-aprobación.

**Enforcement (un solo toggle, dos puntos):**
- CLI: hook `approval_gate.py` (PreToolUse·Bash) → `permissionDecision` allow/ask según el modo.
- Bot/TUI: `bot/intel/runner.py` `_gate` aplica el mismo modo (reusa los tiers de `bot/intel/risk.py`).

Cambiar el modo: edita `constraints.approval_mode` en `scope.json`, exporta `ORCH_APPROVAL_MODE`, o
usa el panel **Acciones** de la TUI (`./deploy/dash.sh`). El modo activo se muestra en la cabecera.
