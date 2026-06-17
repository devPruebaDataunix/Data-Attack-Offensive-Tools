# Changelog

Todas las novedades reseñables de **Data Attack — Offensive Tools** se documentan aquí.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto
se versiona con [SemVer](https://semver.org/lang/es/).

## [1.8.0] - 2026-06-17
### Added
- **agentsview — analítica local de coste/actividad por agente.** Integrado el binario
  [agentsview](https://github.com/kenn-io/agentsview) (Go, MIT, local-first), que lee
  `~/.claude/projects/` y calcula coste/tokens por sesión, día, modelo y agente. `ensure_agentsview`
  en `deploy/lib.sh` lo instala desde el **release fijado `v0.33.1` con verificación SHA256**
  (auditable, sin `curl|bash`) a `~/.local/bin`, y entra en `install_missing` (auto-deploy por
  defecto). Launcher `deploy/agentsview.sh` (`up`/`usage`/`open`/`status`/`down`/`install`).
  `deploy/setup.sh` (opción de menú) y `deploy/verify.sh` (chequeo **no crítico**) integrados.
  **Desbloquea la re-medición de coste.**
### Changed
- Docs alineados: `docs/cost-optimization.md` ("Re-medir el coste con agentsview"), `DEPLOY.md`,
  `docs/RUNBOOK-operador.md` (+ corrige `25/25`→`26/26` tests del bot) y `README.md` (característica
  + despliegue).
### Notes
- **Higiene (innegociable):** los transcripts de `~/.claude/projects/` contienen datos de cliente en
  claro → agentsview es **local-only** (vincula a `127.0.0.1`, telemetría off con
  `AGENTSVIEW_TELEMETRY_ENABLED=0`, **nunca** `--public-url`), read-only sobre los transcripts.
  Instalar ≠ arrancar: el auto-deploy instala el binario; el daemon se levanta a propósito. El
  arranque real se verifica en la Kali (binario Linux); en dev se validó lo estático (`bash -n`,
  validate_suite, etc.). Sin cambios en agentes/guardarraíles.

## [1.7.0] - 2026-06-17
### Added
- **Router A2A reforzado por hook.** Nuevo `.claude/hooks/a2a_router_nudge.py` (PostToolUse sobre
  `Task`): tras cada retorno de subagente, si quedan mensajes A2A `pending` en el blackboard, le
  recuerda al Orquestador ejecutar el ciclo del router (entregar, marcar `delivered`, `hops++`,
  `evidence[]`). No entrega por sí mismo (un hook no invoca agentes); convierte el router de
  instrucción de prompt en un recordatorio **determinista** para que no se pierda ningún relevo.
- **`CLAUDE.md`** que importa `@AGENTS.md`: garantiza que la **CLI** de Claude Code cargue el
  playbook del Orquestador (Claude Code no auto-lee `AGENTS.md`, solo `CLAUDE.md`). El bot/TUI ya lo
  cargaban vía `setting_sources=["project"]`, así que `bot/intel/runner.py` deja de anexarlo a mano
  (evita la doble carga) y conserva solo el addendum del canal Telegram.
- **8 parejas A2A nuevas** (10 en total): `web-exploit↔web-fuzzing`; `vuln-triage↔web-exploit`/
  `network-exploit`/`metasploit`/`ai-security`; `network-exploit↔metasploit`; `post-exploit↔sliver`;
  `lateral-discovery↔netexec`. El resto de relevos siguen pasando por el hub (a propósito).
### Changed
- **C14 endurecido — topología de pares.** `a2a_guard.py` ahora exige que `to_agent` sea un peer
  declarado de `from_agent` (`a2a_peers` del registro) o el hub (`orchestrator`); los relevos fuera
  de pareja van por el Orquestador. `validate_suite.py` comprueba que la topología `a2a_peers` es
  coherente y **bidireccional**.
### Fixed
- **Crash de opencode al arrancar.** `.opencode/opencode.json` llevaba claves `$comment`/
  `$comment_provider` que el validador estricto de opencode (Zod `.strict()`) rechaza
  (`Unrecognized keys`) y, sobre Bun, acaba en `IOT instruction` (SIGABRT). Se eliminan (la
  documentación pasa a `.opencode/README.md`) y `verify_opencode.py` rechaza ahora claves de nivel
  superior desconocidas para que no se repita. (`tools/routing.json` conserva su `$comment`: lo lee
  nuestro propio Python, no opencode.)
### Notes
- Ninguna puerta se relaja: el bus A2A sigue siendo datos auditados (C11/C14/C15) y toda acción
  ofensiva pasa por `scope_guard` + `budget_guard` + aprobación humana. Verificado: validate_suite
  0 fallos, bot 26/26, dryrun con ronda A2A + topología + kill-switches, verify_opencode.

## [1.6.1] - 2026-06-17
### Fixed
- **pdtm `-silent` inexistente.** `pdtm -ia/-ua -silent` imprimía `flag provided but not defined:
  -silent` y abortaba la instalación de las ProjectDiscovery tools en un deploy fresco. Sustituido
  por los flags correctos **`-duc -nc`** (disable-update-check + no-color) en `deploy/auto-deploy.sh`
  y `deploy/lib.sh` (`ensure_pd` y `update_all`). (`nuclei -update-templates -silent` SÍ es válido,
  se mantiene.)
- **Falsos `[ERR]` tras instalar Claude Code.** `auto-deploy.sh` no refrescaba el PATH tras
  `npm install -g @anthropic-ai/claude-code`, así que `claude` parecía no instalado y el verify
  interno (pasos 2 y 6) fallaba y devolvía exit !=0 aunque el entorno estaba correcto. Ahora añade
  el bin global de npm al PATH + `hash -r`, y el aviso de versión es tolerante.
### Notes
- Detectados en el despliegue live en Kali (`dataunix`). El entorno ya estaba operativo
  (verify 31 OK / 0 críticos); estos arreglos dejan el **primer despliegue 100% limpio**. Sin
  cambios funcionales en agentes/guardarraíles.

## [1.6.0] - 2026-06-17
### Added
- **Despliegue en contenedores (Docker).** `Dockerfile` (base Kali rolling) que trae el toolchain
  ofensivo + Claude Code + el repo **reutilizando `deploy/lib.sh install_missing`** (sin duplicar la
  lista de herramientas), `docker-compose.yml` (servicio `bot` + `rag-init` one-shot) y orquestador
  `deploy/docker.sh` (build/rag/up/down/logs/shell/status). El login Pro (`~/.claude`) y `bot/.env`
  se **montan** en runtime, nunca se hornean (`.dockerignore`). Alternativa reproducible al deploy
  de host; el modelo nativo sigue siendo Kali + Claude Code.
- **`ensure_docker` y `ensure_perms`** en `deploy/lib.sh`. `ensure_docker` instala Docker + Compose
  v2 si faltan; `ensure_perms` restablece el bit `+x` de los scripts.
### Changed
- **Permisos de ejecución arreglados de raíz.** El bit `+x` de `deploy/*.sh` ahora se graba en el
  índice de git (modo `100755`), así sobrevive a clones desde Windows/zip; además `auto-deploy.sh`
  y `docker.sh` hacen `chmod +x` en runtime (cinturón y tirantes).
- **Integración**: `deploy/setup.sh` añade la opción "Desplegar en contenedores (Docker)";
  `deploy/verify.sh` añade el chequeo de Docker/Compose (+ validez de `docker-compose.yml`);
  `auto-deploy.sh` menciona la ruta de contenedores; `validate_suite.py` exige los artefactos nuevos.
- **Docs alineados (sin incongruencias)**: README (badge Docker + sección de despliegue), DEPLOY.md
  ("Despliegue en contenedores"), RUNBOOK, y `docs/assets/STYLE_GUIDE.md` aclara que Docker es una
  opción de *despliegue*, no la *arquitectura* (el motor son los subagentes de Claude Code).
### Notes
- El **build de la imagen requiere un host con Docker** (la Kali) y se verifica allí; en el entorno
  de desarrollo se validó todo lo estático (sintaxis bash, validate_suite, bot 26/26, dryrun,
  verify_opencode). `~/.claude` se monta rw (Claude Code escribe estado) → un operador por máquina.

## [1.5.0] - 2026-06-17
### Added
- **Comunicación A2A entre agentes (bus mediado).** Los especialistas ya pueden dirigirse mensajes
  entre sí sin invocarse directamente: dejan un mensaje en `messages[]` del blackboard y el
  **Orquestador-router** lo entrega (sección "Bus A2A" en `AGENTS.md`). Envelope A2A-inspirado
  (`contracts/a2a-message.schema.json`: `message_id/engagement_id/from_agent/to_agent/role/parts/
  ref_finding/ref_message/hops/status`). Parejas iniciales: `web-exploit ↔ sqlmap` y
  `post-exploit ↔ lateral-discovery`.
- **Registro de capacidades (Agent Cards).** Bloque `a2a:` en el frontmatter de cada agente,
  compilado a `contracts/agent-cards.json` por `tools/build_agent_cards.py`
  (`contracts/agent-card.schema.json`). Fuente única sin drift que leen el router y el guard.
- **Guardarraíles A2A** (`.claude/hooks/a2a_guard.py`, PostToolUse): **C14** valida que
  `from_agent`/`to_agent` son agentes conocidos (anti-spoofing) y **C15** acota la conversación
  (techo de mensajes/`hops` por engagement, `constraints.max_a2a_hops`, def. 50 — anti-bucle LLM10).
- **Narración A2A en vivo** en el bot (`✉️ agente X → agente Y`) y en la TUI (contador + log).
### Changed
- **Banner → "DATA ATTACK · HARNESS A2A"** (`assets/banners/data-attack.txt`), ahora coherente con
  la arquitectura. El A2A **no relaja ninguna puerta**: scope_guard + budget_guard + aprobación
  humana siguen aplicando a cada acción ofensiva.
- **Docs alineados**: `README.md`, `ARCHITECTURE.md` (§1 Fallo 1 reescrito), `docs/comms-protocol.md`,
  `SETUP-VSCODE.md`, `docs/engagement-driven.md`, `docs/references.md`, `docs/assets/STYLE_GUIDE.md`
  y `GUARDRAILS.md` (C14/C15) pasan de "ni agentes hablando entre sí" a "bus A2A mediado".
### Notes
- Decisión de seguridad: la **malla peer nativa** (Claude Code *Agent Teams*) queda **lab-only,
  apagada por flag** mientras el payload de los hooks no identifique al teammate
  ([claude-code#24505](https://github.com/anthropics/claude-code/issues/24505)) — rompería la
  atribución por agente en `evidence[]` (C10). El bus mediado preserva trazabilidad y gate único.
- `messages[]` no es obligatorio en el esquema del engagement (retrocompatible). Verificado:
  validate_suite 0 fallos, bot 26/26, dryrun con ronda A2A + kill-switch de hops, verify_opencode.

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

[1.8.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.8.0
[1.7.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.7.0
[1.6.1]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.6.1
[1.6.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.6.0
[1.5.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.5.0
[1.4.1]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.4.1
[1.4.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.4.0
[1.3.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.3.0
[1.2.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.2.0
[1.1.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.1.0
[1.0.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.0.0
