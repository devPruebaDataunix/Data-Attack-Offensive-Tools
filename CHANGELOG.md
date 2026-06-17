# Changelog

Todas las novedades reseñables de **Data Attack — Offensive Tools** se documentan aquí.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto
se versiona con [SemVer](https://semver.org/lang/es/).

## [1.4.1] - 2026-06-17
### Added
- **Asistente de despliegue interactivo** `deploy/setup.sh` (con [gum](https://github.com/charmbracelet/gum);
  degrada a prompts de texto): envuelve `auto-deploy.sh`, la configuración de `bot/.env`, la
  generación de `contracts/scope.json` y la verificación. `deploy/lib.sh` añade `ensure_gum` y
  `ensure_textual` (también vía `verify.sh --install`).
- **Panel de control TUI** (`deploy/dash.sh` → `bot/tui/`, Textual): gemelo **local** del bot de
  Telegram. Reusa el MISMO cerebro (`bot/intel`: runner, classify, scope) y pasa por las MISMAS
  puertas (scope_guard + aprobación humana —por modal— + guardarraíles C11–C13). Muestra
  estado/scope/salud, hallazgos clasificados en vivo (🔴/🟠/🔇) y acepta órdenes al Orquestador.
- **Banner de marca** en `assets/banners/` (`data-attack.txt` + `dataunix.txt`) con la paleta de la
  herramienta (cian `#00D4FF`), al inicio de los scripts de deploy, del bot y de la TUI.
### Notes
- Sin cambios en agentes ni guardarraíles: la TUI es un nuevo front-end sobre el Orquestador, no
  reimplementa lógica. `textual` añadido a `bot/requirements.txt`. Verificado: validate_suite 0
  fallos, bot 25/25, verify_opencode 10/0, dryrun OK y `bash -n` de todos los scripts.

## [1.4.0] - 2026-06-17
### Changed
- **Optimización de coste — tier de modelos por agente.** Reparto recalibrado de **5/12/1** a
  **4 opus-4-8 · 8 sonnet · 6 haiku**: opus-4-8 queda solo donde el razonamiento profundo cambia el
  resultado (`web-exploit`, `post-exploit`, `ai-security`, `reporting`). `network-exploit` baja a
  sonnet; `recon-suite`, `active-recon`, `web-fuzzing`, `nuclei` y `knowledge-postmortem` pasan a
  haiku (recon/escaneo/parseo mecánico). El `effort` se omite en los agentes haiku (la API da 400).
- **Orquestador con control de coste.** El runner del bot fija ahora el `effort` (def. `medium`) y
  un techo de coste por orden opcional del Orquestador (opus-4-8), configurables por entorno
  (`ORCH_EFFORT`, `ORCH_MAX_USD`). Aplicación **defensiva**: degrada sin romper la sesión si la
  versión instalada del SDK no expone los campos. El modelo sigue saliendo de `ORCH_MODEL`.
### Added
- **Perfil opencode-lab ampliado**: `tools/routing.json` enruta ahora **5** agentes mecánicos
  (`osint-recon`, `recon-suite`, `active-recon`, `web-fuzzing`, `nuclei`) a modelos locales (Ollama)
  para practicar/desarrollar contra laboratorios a coste cero. Solo afecta al runtime opencode; el
  bot real (engagements) sigue 100% Anthropic. 100% reversible (vaciar `routes`).
- `docs/cost-optimization.md`: el modelo de coste (el Orquestador es el término dominante), el tier
  por agente, cómo **re-medir** el coste real (el bot lo imprime por engagement) y las palancas.
### Notes
- Sin cambios en la seguridad: el gate de alcance, los guardarraíles C11–C13 y la aprobación humana
  por acción quedan intactos. Re-sincronizados el espejo opencode, el plugin y el mapa de arquitectura.

## [1.3.0] - 2026-06-16
### Fixed
- **`scope_guard` ya no confunde ficheros/código con dominios.** `cat contracts/scope.json`,
  `json.load(...)`, `scan.txt` o `run.sh` dejaban de ejecutarse porque el hook los tomaba por un
  "dominio fuera de scope" — era lo que **tumbaba el engagement desde el bot**. Ahora usa una
  allowlist de TLDs reales + un filtro consciente del scope (los dominios listados por el
  operador siguen gateándose aunque su TLD sea exótico).
- **El Orquestador ya puede leer `contracts/scope.json`** (su Regla 0): se quita el `deny` de
  `Read` en `settings.json` y se mantiene el de `Write` (el alcance no se modifica).
- **El bot limpia los códigos ANSI** antes de enviar a Telegram (se veía `[32m[OK]` crudo).
### Added
- `verify.sh --install` (instala lo que falte) y `--update` (actualiza el toolchain), con la
  lógica compartida en `deploy/lib.sh`. Maneja el caso real del conflicto de Go
  (`golang-go`/`gccgo-go` chocan → solo `golang-go`, o el binario oficial como fallback).
- `tools/verify_opencode.py`: verifica la **réplica opencode** (opencode.json + 18 agentes +
  cruce `routing.json` ↔ provider declarado) y checks de runtime (opencode/Ollama) en `verify.sh`.
- Convención de **directorio de salida por engagement** (`engagements/<id>/`, gitignored) en
  `AGENTS.md`: los artefactos crudos no se mezclan con el repo.
### Changed
- `GUARDRAILS.md`: aclarado que el set de guardarraíles corre a **nivel repo** y el plugin solo
  empaqueta `scope_guard` (el único portable).
- `docs/RUNBOOK-operador.md`: 18 agentes y 25/25 tests; regla de **test ciego** (el `scope.json`
  no debe filtrar la identidad del objetivo).

## [1.2.0] - 2026-06-16
### Added
- **Guardarraíles deterministas** mapeados al [OWASP LLM Top 10 (2025)](https://owasp.org/www-project-top-10-for-large-language-model-applications/) en [`GUARDRAILS.md`](GUARDRAILS.md):
  - **C11 · Anti-inyección (LLM01)** — bloque de separación datos/instrucciones en los 9
    agentes que ingieren contenido del target (recon, web/fuzzing, nuclei, sqlmap, vuln-triage,
    ai-security): el contenido del target son DATOS, nunca instrucciones.
  - **C12 · Detector de secretos (LLM02)** — `tools/redactor.py` + hook
    `.claude/hooks/secret_scan.py`: bloquea claves del operador/motor (clave privada, `sk-ant`,
    token del bot) si aparecen en el blackboard, y expone `redact()` para sanear el informe.
    No estorba a las credenciales legítimamente descubiertas del cliente.
  - **C13 · Kill-switch de consumo (LLM10)** — hook `.claude/hooks/budget_guard.py`: cuenta las
    acciones Bash por engagement y corta al superar `constraints.max_actions` (def. 1000).
### Changed
- `dryrun/run_dryrun.py` ejercita ahora los cinco hooks end-to-end (scope, presupuesto, esquema
  del blackboard, secretos) y demuestra el kill-switch en una fase aislada.
- `GUARDRAILS.md`: las brechas LLM01/02/10 pasan de *Pendiente* a *cubiertas* (C11–C13), con el
  diagrama mental y el inventario actualizados.

## [1.1.0] - 2026-06-16
### Added
- **Routing multi-provider (piloto)** del espejo opencode: `tools/routing.json` (tabla
  agente→modelo con *fallback* al comportamiento por defecto) + bloque `provider` Ollama local
  en `.opencode/opencode.json`, leído por `tools/sync_opencode.py` (fail-open).
- `osint-recon` y `recon-suite` se enrutan a modelos **locales** (Ollama): sin sacar datos de
  cliente del equipo y sin gastar cupo Pro. 100% reversible (vaciar `routes`).
### Notes
- Solo afecta al runtime opencode; `.claude/agents` (Anthropic), Claude Code y el bot de Telegram
  quedan intactos.

## [1.0.0] - 2026-06-16
### Added
- Primera versión pública de la suite: **18 agentes** (orquestador hub-and-spoke + 11 de fase +
  7 de herramienta), **RAG** de vulnerabilidades (KEV/EPSS/exploit/CVSS en SQLite offline),
  **bot de Telegram** (Claude Agent SDK, aprobación por tiers de riesgo), **plugin** de VS Code,
  flujo *engagement-driven* (`CONSTITUTION.md` + `analyze_engagement.py`) y `GUARDRAILS.md` con el
  inventario de controles mapeado a OWASP LLM Top 10.
- Controles base: gate de alcance determinista (`scope_guard.py`), validación de esquema del
  blackboard, escritura atómica, zonas de aislamiento E1/E2/E3 y reporting humanizado.

[1.4.1]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.4.1
[1.4.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.4.0
[1.3.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.3.0
[1.2.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.2.0
[1.1.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.1.0
[1.0.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.0.0
