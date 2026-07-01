# Changelog

Todas las novedades reseñables de **Data Attack — Offensive Tools** se documentan aquí.
El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto
se versiona con [SemVer](https://semver.org/lang/es/).

## [2.14.1] - 2026-07-01
### Fixed
- **Escape de markup Rich en el texto libre del blackboard (TUI).** Un `[` en un `engagement_id`, dominio,
  IP, `key` de presupuesto, preview del bus A2A, o acción/target de evidencia/finding abría una etiqueta Rich
  y **corrompía el render** de la TUI — y ese texto puede venir del **target**. Nuevo helper `state._esc()`
  (stdlib, sin `rich`) aplicado a **todas** las rutas de render activas: `header_line`, `dashboard_status`
  (id/dominios/ips), `budget_render` (key), `evidence_header`, `a2a_rows` (de/a/preview), `evidence_rows`
  (acción/target/artefacto), la tabla de findings del Panel **y la narración del log en vivo** (`app.py`: bus
  A2A + veredictos, que interpolan los mismos datos influidos por el target). Deuda pre-existente que marcó el auditor de
  seguridad en la Fase A.2 (paso 0 del plan de la TUI: correctness antes que cosmética).
### Notes
- Casi todo en `state.py` (lógica PURA) + una línea en `panels.py` (findings); tests nuevos que prueban que un
  `[` queda neutralizado (`\\[`) en cada ruta. test_tui **45/45** (+2), validate_suite 464/0/0. El timestamp
  `ts` (formato controlado) se deja sin escapar a propósito. `message_detail` (aún sin cablear) se escapará al
  cablear el drill-down (Paso 4 del plan).

## [2.14.0] - 2026-07-01
### Added
- **TUI v2 · Fase B (panel Agentes) — 2ª columna «modelo lab» + orden por fase.** El Roster (pestaña
  Agentes) muestra ahora DOS columnas de modelo: **modelo (bot)** = el modelo Anthropic REAL con que corre
  cada agente, y **modelo lab** = el modelo free de NVIDIA del perfil `tools/routing.nvidia-lab.json` (espejo
  opencode, LAB-ONLY) con que ese agente correría, o «—» si no se enruta ahí (el bot es **100% Anthropic**).
  Aclara de un vistazo qué es Anthropic y qué es el lab (el orquestador y `knowledge-postmortem` salen «—»).
  Además el roster se **ordena por fase** (orquestador primero, luego recon→…→informe, alfabético dentro);
  antes salían mezclados alfabéticamente.
### Notes
- Todo en `state.py` (lógica PURA): `load_lab_routes` + `roster_rows` con la columna lab + `_roster_sort_key`;
  `Snapshot.lab_routes` lo carga el lector único. `panels.py` añade la columna y una leyenda que aclara el
  significado (responde a la duda «¿qué agentes usan NVIDIA?»: ninguno en el bot; el perfil lab es opencode).
  validate_suite **464/0/0**, test_tui **43/43** (+2). El render se valida en Kali con captura.

## [2.13.0] - 2026-07-01
### Added
- **TUI v2 · Fase A.3 — paleta de comandos de dominio en español (Ctrl+P).** Nueva `bot/tui/commands.py`
  (`CommandProvider` de Textual) que **reemplaza** la paleta por defecto (genérica y en inglés:
  Keys/Quit/Theme/Screenshot…) por **16 comandos de dominio en español**: ir a cada una de las 7 pestañas,
  refrescar estado, escribir una orden al Orquestador, kill-switch, refrescar el RAG (normal / recalcular
  EPSS), fijar la supervisión (`full`/`critical`/`auto`) y salir. Son **atajos** a acciones que ya existen:
  **no relajan ninguna puerta** (scope/budget/aprobación siguen igual).
### Notes
- El catálogo (`command_specs`) es lógica PURA y testeada; el envoltorio Textual (`Provider`/`search`/
  `discover`) se importa de forma OPCIONAL para que el catálogo siga siendo testeable en el Windows de
  desarrollo (sin Textual). Cableado en `app.py`: `COMMANDS = {DataAttackCommands}` + `run_palette_command`.
- validate_suite **464/0/0**, test_tui **41/41** (+2). El render de la paleta se valida en Kali con captura.

## [2.12.2] - 2026-07-01
### Added
- **Perfil NVIDIA LAB — clúster de AD.** `tools/routing.nvidia-lab.json` enruta ahora también
  `ad-enum`/`kerberos`/`adcs` a NVIDIA NIM free (`openai/gpt-oss-120b`, tool-driving, igual que `netexec`):
  el perfil pasa de **17 → 20 agentes** de recon/explotación, para poder corroborar la **cadena de AD
  completa** con NVIDIA sin gastar Anthropic. LAB-ONLY / opt-in (`apply_routing.py nvidia-lab`); el routing
  ACTIVO (`routing.json`, 5 agentes) y el bot de engagements siguen intactos, y el Orquestador +
  `knowledge-postmortem` se quedan en Anthropic a propósito. `verify_opencode` **31/0**.
### Changed
- **docs/agent-skill-audit.md** — refrescado al estado actual con un banner "al día" (**21 agentes / 13
  skills**; C11 en **19**), conservando el informe datado de la auditoría de calidad de v2.1.0 como registro.
- Conteo del perfil NVIDIA LAB "17" → "20" en `routing.nvidia-lab.json`, `apply_routing.py` y `.opencode/README.md`.

## [2.12.1] - 2026-07-01
### Fixed
- **Coherencia de docs — conteos que envejecieron tras v2.11.0 (18→21 agentes).** Verificación
  exhaustiva de obsolescencia contra la config real (frontmatter de los agentes) y corrección de los
  conteos de estado ACTUAL que habían quedado atrás:
  - **README.md** — cobertura anti-inyección C11 "en 16 agentes" → **19** (los 3 agentes de AD añadieron
    el bloque C11 en v2.11.0; total 19 = los 21 menos los 2 de cierre).
  - **GUARDRAILS.md** — misma cifra C11 "en los 9 agentes" → **19** (mapa OWASP LLM01).
  - **ARCHITECTURE.md** — "hoy 18" → **hoy 21**.
  - **docs/config-audit.md** — "frontmatter de los 18 agentes" → **21**; "a2a solo en 11 agentes con
    pareja" → **14** (los 7 sin pares se mantienen).
  - **docs/assets/STYLE_GUIDE.md** — ejemplo "los 13 agentes de E2" → **16**.
  Se **conservan** a propósito los conteos de artefactos DATADOS (CHANGELOG histórico y
  `docs/agent-skill-audit.md`, informe de calidad de v2.1.0 con su narrativa "9 → 16"), y los conteos
  de subconjunto correctos (perfil free "5 agentes mecánicos", perfil NVIDIA LAB "17 agentes"). Sin
  cambios de código ni de comportamiento.

## [2.12.0] - 2026-07-01
### Added
- **Biblioteca de skills de ciberseguridad en el RAG de conocimiento (Capa 2).** `refresh_kb.py --semantic`
  ingiere ahora **817 skills** de [`mukul975/Anthropic-Cybersecurity-Skills`](https://github.com/mukul975/Anthropic-Cybersecurity-Skills)
  (MITRE-mapeadas, con avisos de autorización/ROE en su prosa, **Apache-2.0**) como nueva fuente de corpus
  `cyber-skills` —corpus PASIVO: no gatea la recuperación; el gate real sigue en scope_guard/approval—, junto a
  HackTricks/PayloadsAllTheThings/PEASS. Amplía el *cómo* que consultan los 21 agentes vía
  `query_kb.py --semantic` (AD/ADCS/Kerberos, evasión/C2, cloud/K8s, acceso inicial, LLM red team…),
  **sin reentrenar** ningún modelo.
### Changed
- **`ingest_corpus.py` acepta `--glob`/`--branch` por fuente** y la tabla `CORPUS` de `refresh_kb.py` pasa a
  spec (`url`/`slug` obligatorios + `glob`/`branch` opcionales): la nueva fuente indexa **solo los `SKILL.md`**
  (no las `references/*.md`) desde la rama `main`. Las 3 fuentes previas no cambian (retrocompatible).
- **Coherencia de docs** (verificación de obsolescencia): README (×3), `rag/knowledge/README.md`,
  `docs/references.md` (atribución Apache-2.0), la skill `rag-technique-lookup`, `deploy/auto-deploy.sh` y
  las cadenas de `query_kb.py`/`kb_vec.py`/`ingest_corpus.py`. ARCHITECTURE_MAP.md regenerado.
### Notes
- El corpus **NO se versiona en el repo** (solo se referencia la fuente para clonarla en el poblado; LAB-ONLY,
  `kb_vec.db` gitignored). Smoke-test local de la ruta completa (glob→chunk→embed→store→recuperación KNN)
  verde: 5 `SKILL.md` → 96 trozos, recuperación semántica score 0.75. El **poblado real** (venv
  `rag/knowledge/.venv` + `bge-small`) se corre en Kali con `refresh_kb.py --semantic`.
- **validate_suite 463/0/0**, verify_opencode 28/0, test_intel 28/28, test_tui 39/39. Plugin/agent-cards/
  opencode/arch-map regenerados con la nueva versión.

## [2.11.0] - 2026-07-01
### Added
- **Capacidad de Active Directory — 3 agentes nuevos (ROE-gated).** La suite pasa de 18 a **21
  especialistas** (11 de fase + 10 de herramienta) con tres agentes de AD en la Zona E2, **solo
  operables con ROE que autorice explotacion de dominio** (heredan el gate por herramienta como `netexec`: aprobacion por
  accion solo bajo `approval_mode: full`; en `critical`/default la proteccion efectiva es scope_guard +
  budget_guard):
  - **`ad-enum`** — reconocimiento interno de AD con **BloodHound CE** (SharpHound/`bloodhound-python`),
    analisis de grafo (Cypher) y priorizacion de rutas a Domain Admin (ACLs, kerberoast, AS-REP,
    DCSync, delegaciones). Descubre `targets[]` internos.
  - **`kerberos`** — **Kerberoasting** (`GetUserSPNs`/Rubeus), **AS-REP Roasting** (`GetNPUsers`), abuso
    de **delegaciones** (unconstrained/constrained/RBCD) y cracking offline (hashcat).
  - **`adcs`** — **AD Certificate Services** con **Certipy**: enumeracion y explotacion de **ESC1-ESC16**
    (SAN abuse, ESC8 NTLM relay a web enrollment, golden certificate, shadow credentials).
  Forman un **cluster A2A** (`ad-enum <-> kerberos <-> adcs`) + enlace `ad-enum <-> netexec`; escriben
  credenciales **referenciadas** (nunca en claro), respetan el multi-host/pivot y traen `memory: local`
  + bloque anti-inyeccion C11. Contenido tecnico basado en playbooks MITRE-mapeados.
### Changed
- **`risk.py`** (clasificacion de aprobacion): nuevos tokens de AD para que sus comandos hereden el gate
  — `rubeus`/`coercer`/`petitpotam` (destructive) y `sharphound`/`azurehound`/`gettgt`/`getst`/
  `finddelegation` (sensitive). `certipy`/`getuserspns`/`getnpusers`/`bloodhound`/`kerbrute` ya estaban.
- **Esquema**: `target.schema.json` anade `ad-enum` al enum `discovered_by`.
- **Coherencia de docs** (verificacion de obsolescencia): README (conteos 18->21, tabla E2, ancla TOC),
  AGENTS.md (herramienta 7->10 + parejas A2A del cluster AD), ARCHITECTURE/ENTORNO-LISTO/DEPLOY/
  SETUP-VSCODE/.opencode/STYLE_GUIDE/cost-optimization (conteos 18->21, reparto de modelos 8->11 sonnet).
  ARCHITECTURE_MAP.md regenerado (21 agentes, E1=3/E2=16/E3=2).
### Notes
- Espejo opencode + agent-cards + plugin regenerados. **validate_suite 463/0/0**, verify_opencode 28/0,
  test_intel 28/28. A2A bidireccional verificado. La medicion real de la capacidad AD se hace en un lab
  de AD/Windows (fuera de este repo).

## [2.10.1] - 2026-06-30
### Changed
- **TUI v2 — i18n de los enums visibles restantes** (completa la traducción iniciada en v2.10.0; los huecos se
  detectaron en las capturas de Kali del panel "Bus A2A" y la cabecera, que aún mostraban valores en inglés).
  Ahora se muestran en español manteniendo la **clave canónica interna en inglés** (enum del esquema): los
  **estados del Bus A2A** (`pendiente`/`entregado`/`hecho`/`bloqueado`) en el resumen; el **rol** de cada mensaje
  A2A (`solicitud`/`respuesta`/`traspaso`/`hallazgo`/`estado`) en la tabla; y el **modo de supervisión** en la
  cabecera (`completa`/`crítica`/`automática`). Nuevos mapas `A2A_STATUS_ES`/`A2A_ROLE_ES`/`APPROVAL_MODE_ES`.
### Notes
- Mismo patrón que las fases de v2.10.0 (mapa ES + clave canónica inglesa; el runner y los guards usan siempre el
  valor inglés). test_tui 39/39, validate_suite 405/0/0. Verificación determinista (extensión trivial de un patrón
  ya revisado por el council en v2.10.0; precedente v2.8.1/v2.8.2). Pendientes ya planificados: paleta de comandos
  en español (A.3); Roster sin truncar + 2ª columna modelo lab; `ts`→`fecha` humanizada en Evidencia (Fase B).

## [2.10.0] - 2026-06-30
### Changed
- **TUI v2 — Fase A.2 (i18n español + empty-states + marca).** Segundo incremento del rediseño visual de
  `bot/tui/`: (1) **i18n de las fases** — nuevo `PHASES_ES` + `phase_es()`; la cabecera, el timeline de fase
  y la columna de fase del **Roster** se muestran en español (`inicio`/`reconocimiento`/`triaje`/`explotación`/
  `post-explotación`/`informe`/`cerrado`; + `orquestador`/`cualquiera` para los agent-cards), manteniendo la
  **clave canónica interna en inglés** (enum del esquema, lo que se guarda en `engagement.json`). (2) **Fix del glitch de render** del timeline: el bullet va ahora **separado** de la
  etiqueta (`○ inicio` en vez de `○inicio`, que se leía "oinit"). (3) **Empty-states amables**: el panel
  principal muestra un mensaje guía cuando no hay engagement (en vez de un muro de `—`) y el de Evidencia
  indica que aún no hay artefactos; la lógica del dashboard se movió a `state.py` (`dashboard_status` /
  `evidence_header`) para poder testearla. (4) **Marca DataUnix sobria**: el wordmark del `Header` y el borde
  de la línea de orden en rojo de marca `#e02c41`. Sin cambios en los guardrails; el bot sigue 100% Anthropic.
### Notes
- Cambio visual + lógica pura: la UI Textual se verifica en KALI (no renderiza en Windows); la lógica nueva
  queda cubierta por tests. py_compile OK, **test_tui 39/39** (36 + 3 nuevos: `phase_es`, `dashboard_status`,
  `evidence_header`), test_intel 28/28, **validate_suite 405/0/0**. Siguen: paleta de comandos de dominio en
  español (A.3), 2ª columna modelo lab + RAG de conocimiento + selects en Acciones + multi-host (Fase B).

## [2.9.0] - 2026-06-29
### Changed
- **TUI v2 — Fase A.1 (layout + footer).** Primer incremento del rediseño visual del panel `bot/tui/`:
  (1) las tablas/paneles ahora **llenan el espacio vertical** (`DataTable`/`#dash-status`/`#dash-findings`
  a `height: 1fr` en `app.tcss`) — antes el contenido quedaba arriba con un gran vacío negro debajo; el
  log de eventos baja a 8 líneas. (2) El **footer muestra `Ctrl+K`/`Ctrl+P`** en vez de la notación caret
  `^k`/`^p` de Textual (`Binding(..., key_display="Ctrl+K")` + `COMMAND_PALETTE_DISPLAY="Ctrl+P"`).
  Sin cambios en la lógica pura (`state.py`/`actions.py`) ni en los guardrails; el bot sigue 100% Anthropic.
### Notes
- Cambio solo visual (Textual/CSS): se verifica en KALI (Textual no renderiza en Windows). py_compile OK,
  validate_suite 405/0/0. Primer paso de la "TUI v2"; siguen i18n español + paleta de dominio + 2ª columna
  modelo lab + RAG conocimiento + selects en Acciones + empty-states + color de marca (ver tui-overhaul-plan).

## [2.8.2] - 2026-06-29
### Added
- **El GATE archiva el blackboard por-lab y arranca limpio.** `run_gate.py`, al lanzar una corrida REAL:
  (1) si `contracts/engagement.json` es de OTRO engagement, lo **archiva** en `engagements/<id>/engagement.json`
  y empieza con un blackboard LIMPIO (no mezcla labs ni el grader cuenta findings rancios de una corrida
  anterior); si es del MISMO `GATE-<id>`, lo **conserva** (corrida resumible). (2) Tras graduar, **copia el
  blackboard final** dentro de `engagements/GATE-<id>/engagement.json` → cada lab queda **autocontenido**
  (artefactos `recon/exploit/loot/evidence/report` + su `engagement.json` en su propia carpeta). Responde a
  "¿dónde se almacena la info de cada lab?": en `engagements/GATE-<id>/` (gitignored). No toca nada en `--dry-run`.
### Notes
- Verificado con test funcional (4 casos: distinto-lab→archiva+reinicia, mismo-lab→conserva, snapshot, sin-bb→
  no-op), py_compile, validate_suite 405/0/0. Cambio pequeño y bien acotado → verificación determinista
  (precedente v2.7.1/v2.8.1). Complementa el reset de contadores de v2.8.1.

## [2.8.1] - 2026-06-29
### Fixed
- **El GATE (`run_gate.py`) acumulaba el contador del kill-switch entre corridas del MISMO eval.**
  `budget_guard` cuenta acciones Bash por `engagement_id` (= `GATE-<id>`) y persiste en
  `contracts/.action_count`; re-lanzar el mismo eval **continuaba** el contador y podía disparar el
  KILL-SWITCH antes de tiempo (falso corte durante la iteración del GATE). Ahora `run_gate.py` **reinicia
  `.action_count` y `.cmd_history`** al arrancar una corrida REAL (no en `--dry-run`), para que cada
  intento empiece de cero. Detectado en la auditoría pre-GATE.
### Notes
- **Auditoría pre-GATE (verificación exhaustiva del entorno antes de correr el GATE).** Confirmado LISTO:
  el grader (`run_eval.py`) es correcto (single-host: regex de root + min_findings; multi_host: hosts_rooted
  + root_proofs + pivots_up≥1 + findings); la **autonomía headless es sólida** — en `approval_mode=auto`
  (que `run_gate` fija) `approval_gate` emite `allow`, así que la corrida NO se cuelga **sin** `--yolo` y
  los guards deterministas (scope/budget/C18/C19) **siguen activos** (mejor que `--yolo`, que los apaga);
  el RAG está cableado en 5 agentes (vuln-triage/lateral-discovery/network-exploit/post-exploit/web-exploit)
  y la Capa 2 es usable (query_kb se re-ejecuta en el venv). validate_suite 405/0/0, verify_opencode 28/0.

## [2.8.0] - 2026-06-28
### Added
- **El auto-deploy pide TODAS las claves de modelos free, no solo NVIDIA.** Nueva función compartida
  `configure_opencode_keys` (en `lib.sh`, única fuente de verdad) que pide en el paso "Espejo opencode":
  las que **no entrenan** (`GROQ`/`CEREBRAS` —perfil activo— + `NVIDIA`) y, **opt-in**, las que
  **recopilan información/entrenan** (`DEEPSEEK`/`MINIMAX`/`ZHIPU`/`OPENROUTER`). Responder **N** las deja
  **deshabilitadas dinámicamente** (clave vacía = el routing no las usa). Idempotente (solo pide claves
  vacías; no clobbera), escritura charset-safe sin `sed`, guard de TTY (no cuelga CI), permisos 600 +
  propiedad del operador. **Cierra la incongruencia**: el perfil activo usa Groq/Cerebras pero el deploy
  solo pedía NVIDIA.
- **`setup.sh`: opción "Montaje COMPLETO automático"** (`full_mount`) que despliega el entorno de punta a
  punta (base/tools/RAG/bot/opencode + todas las claves free + perfil + scope + verificación) **con manejo
  de errores**: NO se detiene ante un fallo, reporta cada paso y resume incidencias. + opción "Configurar
  claves de modelos free (opencode)" para reconfigurar/deshabilitar providers cuando quieras.
### Changed
- **`_own_env` y la lógica de claves se centralizan en `lib.sh`** (las reusan `auto-deploy.sh` y `setup.sh`):
  `setup_opencode_env` queda en `ensure_opencode` + `configure_opencode_keys` (fin de la duplicación; sin
  incongruencias). Sin cambios en el comportamiento del bot (sigue 100% Anthropic con guardrails).
### Notes
- Verificado: `bash -n` en lib.sh/auto-deploy.sh/setup.sh; test funcional de los helpers
  (`_oc_set_key`/`_oc_prompt_key`: escribe válidas, rechaza charset inválido, conserva las ya puestas, no
  clobbera ni duplica); validate_suite 405/0/0, verify_opencode 28/0; `_own_env`/`configure_opencode_keys`
  con una sola definición (lib.sh) y sus usos cruzados. LAB-ONLY.

## [2.7.1] - 2026-06-28
### Fixed
- **El `auto-deploy.sh` no instalaba el BINARIO de opencode.** Configuraba el espejo (opencode.json,
  `opencode.env`, perfil NVIDIA) pero el runtime `opencode` solo se instalaba vía `verify.sh --install`
  → "autodespliegue en opencode" dejaba el espejo configurado pero NO ejecutable. Ahora el paso "Espejo
  opencode" llama a `ensure_opencode` (de `lib.sh`: `npm i -g opencode-ai`, idempotente, no aborta el
  deploy) para dejar el espejo **ejecutable**.
### Notes
- **Decisiones de alcance (tras analizar las opciones):** se DESCARTA construir un bot de Telegram sobre
  opencode con modelos free — el espejo opencode no ejecuta los hooks deterministas (scope_guard/C1–C19;
  bug upstream #5894 salta incluso a los subagentes), así que un bot que corre tooling ofensivo sin gate
  de alcance es inaceptable. El bot sigue **100% Anthropic con todos los guardrails**. El Orquestador
  sigue en Anthropic (no se fuerza a NVIDIA). Sin rotación multi-cuenta NVIDIA (una sola clave; el límite
  ~40 RPM es global por clave). opencode/NVIDIA queda como **corroboración de cableado por CLI**, no
  medición ni runtime del bot. Cambio mínimo verificado: bash -n, validate_suite 0 fallos, source de
  `lib.sh` bajo `set -e` sin abortar.

## [2.7.0] - 2026-06-28
### Added
- **Perfil "NVIDIA LAB" como fichero versionado + aplicador reversible.** `tools/routing.nvidia-lab.json`
  (única fuente de verdad) enruta los **17 agentes** de recon/explotación a su mejor modelo NVIDIA free
  (mecánicos→`llama-3.3-70b`; razona-medio→`nemotron-super-49b`; razona-profundo→`deepseek-r1`;
  `gpt-oss-120b` para tool-driving). **`tools/apply_routing.py nvidia-lab`** lo aplica (respaldando el
  routing activo en `tools/routing.json.bak`, gitignored) y regenera el espejo; **`apply_routing.py
  default`** revierte. Sirve para **corroborar que la suite se conduce solo con NVIDIA sin gastar
  Anthropic**.
- **Opción en `auto-deploy.sh` para montarlo:** flag **`--opencode-nvidia`** + **pregunta interactiva**
  (guard de TTY) en el despliegue → aplica el perfil. El Orquestador (`opencode.json`) y
  `knowledge-postmortem` se quedan en Anthropic a propósito.
### Changed
- **`verify_opencode.py`** valida ahora **también los perfiles alternativos** (`tools/routing.*.json`),
  no solo el `routing.json` activo: un model ID inexistente en el perfil NVIDIA-lab se caza antes de
  aplicarlo (evita el fallo silencioso en runtime).
- **Docs** (`.opencode/README.md`, `docs/cost-optimization.md`): el bloque copy-paste se sustituye por el
  fichero versionado + el aplicador (sin duplicación que pueda divergir).
### Notes
- **Corroboración ≠ medición oficial.** El espejo opencode **no ejecuta los hooks deterministas**
  (`scope_guard`/C1–C19) **ni el bus A2A** — es inherente a opencode (cualquier provider), no a NVIDIA.
  El perfil NVIDIA-lab valida que los modelos conducen agentes+tools+RAG; la **medición OFICIAL del GATE
  (con guardrails) sigue siendo Claude** vía `benchmark/run_gate.py` (lanza `claude`, no opencode).
  Verificado: espejo sin drift (18==18), `verify_opencode` valida el perfil, validate_suite 0 fallos,
  test funcional de apply/revert. **LAB-ONLY.**

## [2.6.1] - 2026-06-28
### Fixed
- **`bot/.env` quedaba propiedad de root e ilegible para el operador.** `setup_bot()` corre bajo `sudo`
  y creaba `bot/.env` con `umask 077` (modo 600) propiedad de **root**; pero el bot se arranca como el
  operador no-root (`cd bot && ./.venv/bin/python bot.py`), que **no podía leer el `.env`** (no cargaba
  `TELEGRAM_TOKEN`/`ALLOWED_USER_ID`). Ahora `setup_bot()` devuelve la propiedad al operador con el
  helper `_own_env` (la misma corrección que ya se aplicó a los artefactos del RAG en v2.5.3 y a
  `.opencode/opencode.env` en v2.6.0). Detectado durante la auditoría del repo de v2.6.0.
### Added
- **Análisis de coste modelo↔agente con NVIDIA NIM (`docs/cost-optimization.md`).** NVIDIA es el único
  provider free con modelos de **razonamiento** (DeepSeek-R1, Nemotron-Super-49B), lo que permite —en
  laboratorio— llevar **toda** la cadena (no solo los 5 mecánicos) a free para **smoke-test del pipeline
  del GATE sin gastar Anthropic**. Tabla tier↔modelo NVIDIA recomendado + perfil **"NVIDIA LAB completo"**
  (bloque `routes` copy-paste en `.opencode/README.md`). Caveat: solo valida el cableado; la medición
  OFICIAL del GATE se corre con Claude. LAB-ONLY (jamás cliente/E2/E3).
### Changed
- **`tools/routing.json`** (`$comment`) menciona ahora NVIDIA NIM y el perfil LAB completo (antes solo
  listaba deepseek/minimax/glm/openrouter como opt-in). El routing activo **no cambia** (sigue en los 5
  agentes mecánicos a Groq/Cerebras).

## [2.6.0] - 2026-06-28
### Added
- **Provider NVIDIA NIM en el espejo opencode (LAB-ONLY).** Nuevo provider `nvidia`
  (`@ai-sdk/openai-compatible` → `https://integrate.api.nvidia.com/v1`, clave `{env:NVIDIA_API_KEY}`):
  una sola clave da acceso a 100+ modelos gratis, incluidos varios de **razonamiento** (DeepSeek-R1,
  Llama-3.3-Nemotron-Super-49B). Mismo patrón que Groq/Cerebras. Pensado para **smoke-test del pipeline
  contra laboratorios propios sin gastar Anthropic**. NIM no entrena con los prompts (ToS API Catalog,
  stateless) pero *disclaim* PII/PHI/PCI → **LAB-ONLY igual** (jamás cliente/E2/E3). Queda **declarado
  pero NO enrutado** por defecto (opt-in, como deepseek/openrouter): el perfil activo probado sigue en
  Groq/Cerebras.
- **`auto-deploy.sh` pide `NVIDIA_API_KEY` de forma interactiva** (paso "Espejo opencode") y la escribe
  en `.opencode/opencode.env` (permisos 600, gitignored, propiedad del operador). Idempotente (no
  reescribe un `.env` existente) y con **guard de TTY**: un deploy sin terminal (CI/desatendido) NO se
  cuelga — copia la plantilla y continúa. Enter deja la clave vacía para rellenarla luego.
### Changed
- **`verify.sh`** añade `nvidia:NVIDIA_API_KEY` al chequeo de claves del espejo opencode (solo avisa si
  el routing enruta a `nvidia/`; no es crítico).
- **Docs** (`.opencode/README.md`, `README.md`, `DEPLOY.md`): fila NVIDIA en la tabla de providers,
  ejemplo de opt-in de routing a razonamiento NVIDIA (gotcha del `/`) y nota de la clave interactiva.
### Notes
- Council 4-roles pre-push → **GO con must-fix** aplicado: el prompt de la clave ya **no usa `sed`**
  (un paste con `&`/`|`/`\` corrompía el valor en silencio y un salto de línea abortaba el deploy bajo
  `set -e`); ahora valida el charset de la clave (`[A-Za-z0-9_.-]`) y reescribe la línea con
  `grep`+`printf` (atómico). Should aplicados: rutas absolutas (sin `cd`), `cp` que degrada sin abortar,
  `chown` con grupo + `chmod 600` explícito, y el badge de una línea "no entrena" matizado a *s/ ToS*.

## [2.5.4] - 2026-06-28
### Fixed
- **El poblado de la Capa 2 "parecía colgado".** `refresh_kb.py --semantic` clona HackTricks (~989 `.md`) y
  embebe decenas de miles de chunks en CPU; lo hacía **sin imprimir nada** entre la carga del modelo y el
  mensaje final, así que parecía bloqueado (mismo patrón que v2.1.2 con el RAG de CVEs) y el operador lo
  mataba creyéndolo muerto. Ahora `ingest_corpus.py` imprime **progreso por lote** (`ficheros N/total ·
  trozos · nuevos`, con flush) + un aviso inicial de que la 1.ª vez TARDA y es **incremental** (un `Ctrl+C`
  no pierde lo hecho: al relanzar retoma por hash).
- **`FutureWarning` de `embed.py`** (`get_sentence_embedding_dimension` quedó deprecado en
  sentence-transformers 5.x): ahora se prueba primero `get_embedding_dimension` (el nuevo), con el viejo de
  fallback.
### Notes
- Diagnóstico confirmado con datos del operador (8 cores, ~5,6 GiB RAM libre, swap casi sin usar): **no era
  un cuelgue** — el embedding avanzaba, solo faltaba feedback. Recomendado correr el primer poblado en
  `tmux`/`screen`; opcional `HF_TOKEN` para evitar el aviso de rate-limit del modelo.

## [2.5.3] - 2026-06-28
### Fixed
- **Capa 2 del RAG (semántica): instalación que de verdad funciona en Kali.** v2.5.2 dejó visible la causa
  raíz (al quitar el `2>/dev/null`): instalar `sentence-transformers`/`torch` al `python3` del **sistema**
  es inviable en Kali — choca con dpkg (`torch→sympy` pide `mpmath<1.4`, pero apt tiene `mpmath 1.4.1` sin
  registro de pip, que ni `--break-system-packages` puede desinstalar → `uninstall-no-record-file`; el
  fallback sin el flag cae en `externally-managed-environment`). Además `torch` arrastraba **~2,5 GB de stack
  CUDA** inútil en una caja sin GPU.
- **Solución: venv AISLADO del RAG + torch CPU-only.** Las deps de la Capa 2 se instalan ahora en
  `rag/knowledge/.venv` (parte de cero, no toca apt) con **torch CPU-only** (índice oficial CPU de PyTorch).
  Nuevo `rag/knowledge/_venv.py` = **única fuente de verdad** (crea el venv, instala, verifica el import);
  `deploy/lib.sh` la **invoca** (deja de duplicar la lógica en Bash). Los agentes siguen llamando
  `python3 rag/knowledge/query_kb.py --semantic`: el script se **re-ejecuta solo** con el python del venv
  (os.execv); el poblado lanza los ingesters de la Capa 2 con ese python. `--ensure-deps` solo prepara el
  venv; `--no-install-deps` no lo crea. `verify.sh` comprueba las deps en el venv del RAG.
### Notes
- `--break-system-packages` al python del sistema queda **retirado** para estas deps (era la causa del
  fallo). Siguen **sin pin de versión/hash** (decisión consciente lab/E2; requieren egress a PyPI + el
  modelo de embeddings desde HuggingFace en el primer uso). Ver DEPLOY.md.
- En un Windows-dev con las libs ya en el python del sistema, se usan tal cual (no se crea venv).
- **Council de 4 roles pre-push:** el deploy **devuelve la propiedad** de los artefactos del RAG al operador
  (el cron corre como no-root; evita que las DB queden root-owned y el cron las deje obsoletas en silencio);
  `refresh_kb.py` sale con **código de error** si se pidió la Capa 2 y no se pobló (el cron avisa en vez de
  rotar callado, y el deploy entra en su rama de *warn*); el 2.º `pip` usa `--extra-index-url` CPU (evita
  re-traer un torch CUDA). El `os.execv` al `.venv/bin/python` y el segundo índice quedan documentados en
  DEPLOY.md como decisión consciente.

## [2.5.2] - 2026-06-28
### Fixed
- **RAG de conocimiento Capa 2 (semántica): poblado fiable de un paso.** `refresh_kb.py --semantic` ahora
  **auto-instala** sus dependencias (`sqlite-vec` + `sentence-transformers`, que arrastra torch) cuando
  faltan, con método **portable** (Kali/Debian son PEP 668 `externally-managed` → `pip install
  --break-system-packages`, con fallback sin él) y **verificación real del import** después (no un falso
  "instalado"). Antes, correr el comando con las deps ausentes dejaba la Capa 2 sin poblar (`kb_vec.db` no
  se creaba, como vio el operador). Desactivable con `--no-install-deps` (p. ej. cron estricto).
- **Mensajes de instalación correctos en Kali.** `refresh_kb.py`, `query_kb.py --semantic` y
  `rag/knowledge/README.md` ya no sugieren `pip install …` a secas (falla por PEP 668): apuntan a
  `refresh_kb.py --semantic` o al `pip install --break-system-packages`.
- **Deploy sin fallo silencioso.** Las deps de Capa 2 se instalan ahora por `ensure_semantic_deps` (en
  `deploy/lib.sh`, reutilizable como el resto de `ensure_*`), que **verifica que importan** antes de dar
  "OK"; `auto-deploy.sh --semantic-rag` la usa. `verify.sh` reporta el estado de las deps de Capa 2 (opcional).
### Notes
- Las deps de Capa 2 van al `python3` del SISTEMA (no a un venv): los agentes las consultan en runtime por
  Bash. Su ausencia no es crítica — los agentes degradan a la Capa 1 estructurada.
- **Tras un council de 4 roles:** el **cron** semanal corre con `--no-install-deps` (no auto-instala sin
  supervisión; además correría como no-root y no podría escribir en el `python` del sistema);
  `refresh_kb.py --semantic` ahora **verifica el conteo real de `kb_vec.db`** tras poblar y avisa si quedó
  vacío (p. ej. si no se pudo bajar el modelo de embeddings de HuggingFace) en vez de dar un falso "OK";
  `pip` corre con `--no-input` + `timeout`. Las deps van **sin pin de versión/hash** — decisión consciente
  lab/E2 (como los demás instaladores de release) y **requieren egress a PyPI** (en air-gap real fallan y la
  Capa 2 se omite sin romper nada). Ver DEPLOY.md.

## [2.5.1] - 2026-06-27
### Fixed
- **Despliegue: herramientas que no se instalaban (subfinder/naabu/katana/dnsx/sliver) + regresión de
  rustscan de v2.5.0.** Las ProjectDiscovery tools dependían solo de `pdtm`/`go install` (frágil: fallaba por
  DNS a proxy.golang.org y por el PATH del go-bin) → ahora **subfinder/naabu/katana/dnsx por apt de Kali**
  (vía fiable, binarios en `/usr/bin`); `pdtm`/go queda como fallback. **httpx**: en Kali el paquete es
  `httpx-toolkit` (y su binario) → `ensure_httpx` lo instala y crea el symlink `httpx` que invocan los
  agentes. **rustscan** se había metido en v2.5.0 en la línea apt masiva — como no está en los repos de
  Debian/Kali, **rompía toda la línea** (no instalaba ni nmap): ahora en `ensure_rustscan` (1 intento apt →
  el release publica el `.deb` dentro de un `.zip`, `rustscan.deb.zip` → descarga + `unzip` + `dpkg`).
  **Sliver**: instalador oficial → fallback a los binarios del release con el **nombre real**
  `sliver-server_linux-amd64`/`-client` (amd64/arm64). **chisel**: apt → `.gz` del release. La línea apt pasa
  a **bucle por-paquete** (un paquete ausente no bloquea al resto) + `libpcap-dev` (naabu), `jq`, `unzip`.
  `auto-deploy.sh` ahora **carga `lib.sh`** (una sola implementación, sin duplicar).
- **`verify.sh`** comprueba ahora **rustscan**, **chisel** y **proxychains**.
### Notes
- Los nombres de asset de los releases se verificaron contra la API de GitHub **en vivo** (un council de 4
  roles cazó que los parsers iniciales no casaban los assets reales: `rustscan.deb.zip`, `sliver-server_linux-amd64`).
- Degradación segura: si rustscan no se instala, los agentes de recon caen a `nmap -sS -p-` (skill
  `stealth-recon`); si falta chisel, el pivoting usa proxychains/ligolo.
- Los instaladores de release bajan por HTTPS desde el repo oficial **sin pin de checksum** (decisión
  consciente: robustez frente a renombrados de asset upstream; modelo de amenaza de lab/E2). Ver DEPLOY.md.

## [2.5.0] - 2026-06-27
### Added
- **Recon sigiloso full-range + priorización de puertos altos** — `active-recon`/`recon-suite` usan
  **rustscan** como front-end de descubrimiento (barre los 65535 a ritmo acotado) → `nmap -sV -sC`
  **dirigido** solo a los puertos abiertos (menos huella que `nmap -p-`). Se deja de depender de
  `--top-ports 1000`: los servicios que las empresas mueven a puertos altos (SSH→2222, paneles→8443/9000)
  ya no se pierden, y `vuln-triage` los **prioriza** (suelen estar menos endurecidos). `deploy` instala
  rustscan (+ chisel/proxychains4). Nueva skill **`stealth-recon`**.
- **Detección de honeypots/honeytraps** — nueva skill **`honeypot-detection`** con fingerprints de
  honeypots conocidos (Cowrie/Kippo, Dionaea, Conpot, Glastopf, T-Pot) + heurísticas conductuales,
  enganchada en recon/triage. Construye sobre `target.defenses[]` (v2.4.0): confianza alta ⇒ abortar el
  vector (no perder tiempo ni delatarse).
- **Postura BURNED → OSINT pasivo** — nueva rama del modelo de decisión: si la detección es activa y de
  confianza alta (IP baneada/IPS cortando), se **para lo intrusivo**, se pasa a **OSINT no atribuible** +
  cool-down y se avisa; el host quemado sale de la frontera activa (no rompe el cierre). `osint-recon` gana
  OPSEC (rotación de user-agent/perfil/egress proxychains-Tor; solo fuentes públicas; dentro de scope —
  refuerza §1/§5). Nueva skill **`opsec-osint`**.
- **Disciplina anti-sesgos (epistémica)** — sección en `AGENTS.md` + refuerzo en triage/explotación: ≥2
  hipótesis, buscar evidencia que refute, no fiarse a ciegas de tool/RAG, "demasiado fácil" = sospechoso,
  cambiar de hipótesis en vez de repetir. Refuerza §3/§4 (es juicio, no determinista).
### Changed
- **`noise_guard` (C18) cubre rustscan** — bloquea `--batch-size`/`--ulimit` excesivos y, en `stealth`,
  rustscan sin acotar el ritmo → el front-end rápido no es una vía para evadir el anti-alboroto.
### Notes
- Sin cambios en CONSTITUTION (las novedades operan §3/§5/§9 desde el modelo de decisión). Skills 10→13.

## [2.4.0] - 2026-06-27
### Added
- **Capacidad multi-host (pivoting + cadena de credenciales)** — el salto que faltaba para cerrar máquinas
  encadenadas tipo "Grandma" de forma autónoma. El estado multi-host vive en el blackboard (resumible), no
  en el contexto del modelo:
  - **Esquemas:** `engagement.schema.json` gana `pivots[]` (túneles establecidos: tool/via_target/reaches_cidr/
    proxy/status) y `credentials[]` (vault REFERENCIADO, nunca en claro: secret_ref/source_target/validated_on/
    privilege). `target.schema.json` gana `reachable_via` (`direct` o un `pivot_id`) y `access_level`
    (none→user→root/…). Todo opcional y retrocompatible.
  - **`lateral-discovery` dueño del transporte de pivot:** ligolo-ng primario (chisel/proxychains de respaldo;
    reutiliza el SOCKS de Metasploit/Sliver si ya hay sesión). Registra el túnel en `pivots[]`, fija
    `reachable_via` en los hosts internos y prioriza reuso de credenciales antes de crackear. La ruta del
    túnel se añade **solo al CIDR en scope** y se desmonta al cierre (reversible).
  - **Orquestador (`AGENTS.md`):** nueva sección "Orquestación multi-host" — frontera de hosts, bucle por
    host, inyección del pivot activo como contexto a `network/web-exploit`/`metasploit`, propagación de
    credenciales (reuso/PtH/spray ANTES de crackear) y resumibilidad estilo Context-Relay desde el blackboard.
  - **`netexec`/`network-exploit`/`post-exploit`:** conscientes de pivot (enrutan por el túnel cuando
    `reachable_via` es un pivot), reuso de `credentials[]` antes de spray ciego, y escritura de credenciales
    SIEMPRE referenciada (loot/ + memory_guard/secret_scan).
- **Gate multi-host — `benchmark/evals/grandma-gate.json`** + grader `type: multi_host` en `run_eval.py`
  (cuenta hosts a privilegio en `targets[].access_level`, exige ≥1 pivot `up` y N pruebas de root).
  `run_gate.py` acepta `scope_extra` (segmentos internos del lab, validados LAB-only) para que `scope_guard`
  permita los hosts detrás del pivot.
- **Operación defensa-consciente y de bajo ruido (CONSTITUTION §9 nuevo, 2.1.0)** — el sistema **descarta el
  ruido** (determinista) y **detecta/respeta** las defensas del objetivo (heurística best-effort del agente):
  - **Detección de defensas (heurística del agente, best-effort — NO determinista, a diferencia de C18/C19):**
    `active-recon`/`recon-suite`/`nuclei` identifican WAF/IDS/IPS/tarpit/rate-limit; `vuln-triage` y los
    agentes de explotación detectan **honeypots** y **falsos positivos de honeypot** (hallazgo "demasiado
    fácil"/incoherente); `post-exploit`/`lateral-discovery` marcan hosts honeypot (canary/too-clean). Se
    registran en el nuevo `target.defenses[]` (type/confidence/evidence); un honeypot de confianza alta
    **sale de la frontera activa** (no bloquea el cierre).
  - **Anti-alboroto (C18, `.claude/hooks/noise_guard.py`):** hook determinista PreToolUse que bloquea el
    escaneo ruidoso/DoS-adjacent (`nmap -T5`, `masscan`/`zmap` sin `--rate` o sobre cap, fuerza bruta/
    fuzzing con hilos excesivos); `constraints.stealth` endurece, `constraints.allow_noisy` lo libera si la
    ROE autoriza ruido.
  - **Anti-bucle (C19, `.claude/hooks/loop_guard.py`):** hook determinista que corta el thrashing (mismo
    comando) y la oscilación A/B tras `constraints.max_repeat` (def. 3) — anti-bucle a nivel de ACCIÓN
    (complementa C13 global y C15 de hops A2A).
  - **Modelo de decisión** en `AGENTS.md`: señales (WAF/IDS/honeypot) → decisión {proceder / evadir / bajar
    ruido / abortar vector / escalar}. Honeypot de confianza alta ⇒ abortar el vector y avisar.
  - `GUARDRAILS.md` documenta C18/C19 (+ modelo mermaid); `CONSTITUTION.md` sube a **2.1.0** (§9 bajo ruido
    y conciencia de defensas).
### Changed
- **Enum profunda explícita (estilo PEASS/linpeas·winpeas) en `post-exploit`** con bucle ReAct
  (enumera→observa→adapta); los servicios en loopback se marcan como pistas de pivot.
- **RAG de conocimiento cableado a `lateral-discovery` y `network-exploit`** (`query_kb.py` + `--semantic`),
  además de los ya existentes post-exploit/web-exploit.
- **`maxTurns` ampliado** en los agentes que ahora hacen estrictamente más por invocación (pivot/enum
  profunda/propagación): lateral-discovery 35→45, network-exploit 35→40, post-exploit 50→60, netexec 30→40.
  El `budget_guard` sigue limitando las acciones ofensivas reales; re-tune con `tune_maxturns.py` tras medir.
- **`linux-hard-gate.json`** reposicionado como **checkpoint single-host** (paso previo a `grandma-gate`);
  evidence_regex alineado (incluye `/root/proof.txt|flag`).
### Notes
- **El multi-host NO relaja ninguna puerta:** cada host detrás de un pivot pasa por `scope_guard` igual; el
  pivot da transporte, no alcance. Credenciales referenciadas bajo memory_guard/secret_scan.
- Reforzar-primero: **el GATE no se corre todavía**; esta versión es verificación local (validate_suite,
  py_compile, espejos plugin/opencode, agent-cards).
- **Higiene de espejos:** al regenerar `plugin/` se corrige un drift previo — 6 espejos de agentes
  (`ai-security`, `knowledge-postmortem`, `metasploit`, `sqlmap`, `vuln-triage`, `web-fuzzing`) no se
  habían re-mirrorizado al plugin tras añadir `memory: local` en v2.2.0; ahora el plugin queda al día con
  la fuente (`.claude/agents`). Cambio puramente aditivo (0 borrados), sin tocar comportamiento.

## [2.3.1] - 2026-06-26
### Fixed
- **Fuga potencial de scope de cliente (repo PÚBLICO).** El backup que `benchmark/run_gate.py` hace de
  `contracts/scope.json` antes de lanzar (`scope.json.pre-gate-*.bak`) NO estaba en `.gitignore`: un `git add`
  despistado podía subir nombre de cliente + IPs/dominios in-scope. Ahora `contracts/*.bak` está gitignored y
  el backup se **elimina** tras restaurar (no queda `.bak` con datos de cliente en el árbol de trabajo).
### Changed
- **`run_gate.py` endurecido.** (a) Escritura **atómica** de `scope.json` (temp + `os.replace`): nunca un
  scope a medias si el proceso muere a mitad. (b) `LAB_SUFFIXES` reducido a labs inequívocos
  (`htb/thm/vulnhub/dockerlabs/lab`): se quitan `internal/local/test/example`, que son TLDs de
  infraestructura interna REAL y un guard LAB-only no debe aceptarlos. (c) El prompt del Orquestador ya no
  siembra el ejemplo literal `uid=0` (el grader hace grep de `uid=0(root)`; sembrarlo permitía un PASS por
  eco) — ahora pide la PRUEBA REAL capturada del target. (d) `--yolo` documenta EXPLÍCITAMENTE que añade
  `--dangerously-skip-permissions` y con ello DESACTIVA `scope_guard.py` (única contención de alcance en
  runtime) → solo lab privado/aislado.
- **`tune_maxturns.py`:** deduplica por `transcript_path` para no contar dos veces un run que aparezca en
  `engagements/**` y en `.claude/audit/` a la vez. (El conteo por mensajes `assistant` se mantiene: en los
  transcripts de Claude Code cada respuesta del asistente es una línea ≈ un turno; es el proxy correcto.)
- **`build_plugin.py`** lee la versión de `VERSION` (como `build_agent_cards.py`) en vez de hardcodearla,
  evitando regresiones del manifiesto del plugin en futuros bumps.
### Notes
- Arreglos surgidos de la revisión (claude-council local, 4 roles) del diff de v2.3.0. Sin cambios
  funcionales en agentes/hooks; `validate_suite` verde.

## [2.3.0] - 2026-06-23
### Added
- **Auto-lanzador del GATE — `benchmark/run_gate.py`.** Cierra el cableado que faltaba: además de graduar
  (`run_eval.py`), ahora LANZA el engagement end-to-end contra un lab (escribe un `scope.json` acotado en
  `approval_mode=auto`, crea `engagements/GATE-<id>/`, arranca el Orquestador headless `claude -p` y gradúa
  con pass@k). **LAB-ONLY**: rechaza cualquier target que no sea de laboratorio (IP privada/loopback o dominio
  .htb/.thm/.dockerlabs/…) y respalda/restaura el `scope.json` previo. `--dry-run` enseña el plan sin tocar
  nada; `--yolo` añade `--dangerously-skip-permissions` (lab desatendido).
- **Cobertura de los RAG de conocimiento — `query_kb.py --stats`.** Reporta el volumen de la Capa 1 (`kb.db`,
  por fuente/plataforma/categoría) y la Capa 2 (`kb_vec.db`, por fuente) **sin cargar sqlite-vec ni el
  embedder**; avisa si la Capa 2 parece el subset de prueba → verifica la población completa (sobre todo en Kali).
- **Recomendador de `maxTurns` — `tools/tune_maxturns.py`.** Cruza la auditoría de SubagentStop
  (`subagents.jsonl`) con los transcripts y calcula los turnos REALES por agente (p50/p95/máx); compara con el
  `maxTurns` declarado y sugiere subir (si topa el techo) o bajar (si sobra holgura), con margen. Sin datos sale 0.
### Notes
- Las tres piezas **habilitan y miden** el trabajo que se EJECUTA en Kali (correr el GATE de capacidad, poblar
  la Capa 2 entera, re-tunear `maxTurns` con datos reales). Sin cambios funcionales en agentes/hooks; `validate_suite` verde.

## [2.2.0] - 2026-06-23
### Added
- **RAG de conocimiento (técnicas ofensivas) — `rag/knowledge/`.** Segundo RAG local, complementario al de
  CVEs, para el *"cómo explotar/escalar"*. Lo consultan los agentes de explotación vía la skill
  `rag-technique-lookup`.
  - **Capa 1 (estructurada, `kb.db`, stdlib):** ingesters de **GTFOBins · LOLBAS · Atomic Red Team ·
    MITRE ATT&CK (STIX)**; `query_kb.py` devuelve la técnica/comando accionable (privesc/credenciales/…).
  - **Capa 2 (semántica, `kb_vec.db`):** embeddings **locales** (sentence-transformers) + **sqlite-vec**
    sobre **HackTricks · PayloadsAllTheThings · PEASS** + feeds (**0dayfans · Hacker News · CVEDetector**);
    `query_kb.py --semantic`. Ingesta incremental y con anti-inyección (todo el corpus = DATO).
  - Cableado en `post-exploit` y `web-exploit`; `auto-deploy.sh` puebla la Capa 1 (Capa 2 opt-in con
    `--semantic-rag`).
- **Frescura del RAG de vulnerabilidades.** El store estaba anclado a KEV (meses de retraso); `rag/ingest_recent.py`
  añade los **CVE recién publicados** desde **CVEDetector** (Telegram, sin auth) y **MITRE cvelistV5**
  (`deltaLog`, sin auth; **OpenCVE** opcional con credenciales). `enrich_cve5.py` rellena además
  nombre/descripción/producto; nuevas columnas `published_date`/`source_feed`; corre dentro de `rag/refresh.py`.
- **Eval-harness / GATE — `benchmark/`** (EDD + pass@k) para medir el cierre autónomo.
- **Ingesta pasiva (cron).** `auto-deploy.sh` programa el refresco de los RAG en el crontab del usuario
  operador (vulnerabilidades a diario, conocimiento semanal; log en `rag/.refresh.log`), idempotente y con
  `--no-cron` para omitirlo. Mantiene ambos RAG al día sin intervención.
- **Memoria de aprendizaje por agente (`memory: local`) + guard de sanitización (nuevo control C17).**
  Los 10 agentes de explotación/triage (web-exploit, sqlmap, network-exploit, metasploit, netexec,
  ai-security, web-fuzzing, lateral-discovery, post-exploit, vuln-triage) acumulan su propia memoria de
  **técnica generalizada** per-operador (`.claude/agent-memory-local/`, gitignored), con sección
  "Memoria de aprendizaje" en su prompt (anti-sobreajuste `times_observed ≥ 3`, dedup, cura de tamaño).
  - **`memory_guard.py`** (PreToolUse, determinista) **bloquea** escribir secretos, identificadores del
    scope (IPs/dominios in/out), IPs públicas enrutables o loot (hashes) en `.claude/agent-memory*/` —
    cubre la memoria `local` **y** la `project` (que se comparte por git): convierte "sin datos de
    cliente en memoria" en **garantía de código** (aislamiento de cliente, CONSTITUTION §1). Reutiliza
    `tools/redactor.py` y los helpers de `scope_guard`.
  - `knowledge-postmortem` pasa a **meta-curador**: consolida/poda la memoria de cada agente al cierre.
  - Pruebas: `tests/test_memory_guard.py` (20/0). Espejo opencode regenerado. `validate_suite` 396/0/0.
### Changed
- Diagramas de arquitectura (`README.md`, `ARCHITECTURE_MAP.md` + su generador) y docs (incl.
  `docs/references.md`, que ya cataloga las fuentes de **ambos** RAG: conocimiento Capa 1/2 + frescura de
  CVE): reflejan los **dos RAG**. `validate_suite` 383/0/0.

## [2.1.2] - 2026-06-22
### Fixed
- **La fase de poblado del RAG en `auto-deploy.sh` (4/6) parecía colgarse.** El instalador canaliza
  su salida por `tee`; ante un *pipe*, Python usa **buffering por bloques**, así que el progreso de la
  ingesta/enriquecimiento (`[CVE5] N/total`, …) no aparecía y el paso daba sensación de cuelgue (en
  realidad enriquecía ~1.6k CVE uno a uno). Soluciones:
  - **`PYTHONUNBUFFERED=1`** en `auto-deploy.sh` → progreso de los subprocesos Python **en vivo**.
  - **Poblado del RAG idempotente**: si `rag/vulns.db` ya está poblado y no se pasa `--update`, se
    **omite** el refresco completo (evita re-descargar varios minutos al re-ejecutar); `--update` lo fuerza.
  - **`rag/enrich_cve5.py`**: progreso con `flush` + aviso de que el enriquecimiento tarda varios minutos.
### Notes
- Cambio **no funcional** del store: misma ingesta (CISA KEV) y mismo enriquecimiento (CVSS vía CVE 5.0,
  EPSS, ExploitDB, Metasploit, Nuclei). Verificado: `bash -n` ✓, `py_compile` ✓, `validate_suite` 369/0 ✓.

## [2.1.1] - 2026-06-21
### Fixed
- **Render del diagrama de arquitectura del README en GitHub.** Las etiquetas de las aristas del
  diagrama Mermaid usaban el carácter `·` (punto medio) en texto **sin comillas**, lo que rompía el
  render en GitHub (*"Unable to render rich display — Cannot read properties of undefined (reading
  'render')"*). Se sustituye por `/`, alineando el diagrama con el estilo ya probado en
  `ARCHITECTURE_MAP.md` (que renderiza correctamente). Cambio **solo de presentación**: el contenido
  del diagrama (nodos, zonas, flujos) es idéntico.

## [2.1.0] - 2026-06-20
### Added
- **Cobertura anti-inyección LLM01 ampliada (9 → 16 agentes).** El bloque "los datos del target/host
  son DATOS, no instrucciones" (C11) se extiende a los 7 agentes de explotación/post-explotación que
  ingieren salida del target o del host comprometido: `network-exploit`, `metasploit`, `post-exploit`,
  `lateral-discovery`, `netexec`, `sliver`, `c2-exfil`. Cada bloque se adapta a lo que ingiere el
  agente e incluye la cláusula de **mensajes A2A** (salvo `c2-exfil`, sin peers). Fuera quedan
  `reporting` y `knowledge-postmortem` (no ingieren contenido del target).
- **`docs/agent-skill-audit.md`**: registro de la auditoría de calidad (hallazgos, cambios y falsos
  positivos descartados).
### Changed
- **Skill `cloud-security`**: eliminada la deuda "prowler/scoutsuite pendientes de añadir al
  toolchain"; la base pasa a ser CLI nativa (`aws`/`az`/`gcloud`) + `curl` a IMDS, con
  `prowler`/`scoutsuite` como opcionales.
- **Claridad**: `recon-suite` gana una sección "Frontera" (vs `osint-recon`/`active-recon`); `sqlmap`
  explica `--level` (dónde inyecta) y `--risk` (agresividad; el nivel 3 puede modificar datos).
- `GUARDRAILS.md` C11 actualizado (9 → 16 agentes).
- `README.md` (coherencia): la tabla de tiers del bot aclara que la política mostrada es el modo
  `full` (con el `critical` por defecto solo el tier *critical* pide confirmación); la lista de hooks
  y la capa de guardarraíles incluyen ahora supervisión (`approval_gate`) y auditoría de subagentes
  (`subagent_stop`, C16).
### Notes
- Minor **aditivo** (la suite ya era de alta calidad): auditados los 18 prompts + 9 skills; los
  "scripts/ficheros inciertos" del barrido resultaron falsos positivos (los garantiza
  `validate_suite → validate_refs()`). Verificado: validate_suite 369/0, test_tui 36/36, test_intel
  28/28, verify_opencode 11/0, dryrun, `claude plugin validate` ✓. Espejo opencode regenerado.
- La **memoria de aprendizaje por agente** se diseña aparte en **v2.2.0** (cambio de arquitectura con
  aislamiento de cliente).

## [2.0.0] - 2026-06-19
### Added
- **Mínimo privilegio por agente (defensa en profundidad).** Los 18 especialistas declaran ahora
  `disallowedTools` y `maxTurns` en su frontmatter (fuente `.claude/agents`, propagado al plugin):
  - **`disallowedTools: Agent, Task`** en los 18 → candado de la malla **hub-and-spoke**: ningún
    especialista puede spawnear subagentes; solo el Orquestador delega (refuerza el bus A2A mediado y
    `a2a_guard`). `reporting` y `knowledge-postmortem` (cierre, datos E3) deniegan además **`Bash`**:
    no ejecutan comandos aunque sufran inyección.
  - **`maxTurns`** acota los turnos de cada subagente (15–50 según rol/modelo) → complementa el
    kill-switch por coste (`budget_guard`, C13) con una cota por nº de turnos (anti-bucle, anti-bloat).
- **Auditoría forense del ciclo de vida de subagentes.** Nuevo hook `.claude/hooks/subagent_stop.py`
  (`SubagentStop`, registrado en `.claude/settings.json`): deja un registro **JSONL por anexado**
  (agente, id, sesión, engagement, transcript) en `engagements/<id>/evidence/subagents.jsonl` (o
  fallback `.claude/audit/`). **Observacional y NO bloqueante** (la finalización jamás se interrumpe;
  fail-safe a exit 0) — trazabilidad C10, no una puerta.
### Changed
- **`tools/validate_suite.py`** valida los campos nuevos e **impone invariantes**: todo agente acota
  `maxTurns` (entero positivo) y deniega `Agent`+`Task` (hub-and-spoke); `disallowedTools` solo admite
  tools conocidas o patrones `mcp__*`.
- **`CONSTITUTION.md` sin cambios** (sigue v2.0.0): el mínimo privilegio y la auditoría de subagentes
  **operacionalizan** principios ya vigentes (defensa en profundidad, trazabilidad C10, alcance §1);
  no se añade ni enmienda ningún principio, así que la constitución no sube de versión.
### Fixed
- **Manifest del plugin: `repository` como string.** El enriquecimiento del manifest en v1.11.0 lo dejó
  como objeto `{type,url}` (convención npm), pero el esquema de plugin de Claude Code exige **string**:
  `claude plugin validate` fallaba con `repository: expected string, received object`. Corregido en
  `tools/build_plugin.py` (regenera `plugin/plugin.json` y `plugin/.claude-plugin/plugin.json`).
### Notes
- **MAJOR honesto (cambio de comportamiento en runtime):** `maxTurns` puede **terminar** un subagente
  que antes corría sin cota, y `disallowedTools` **retira** la capacidad de spawnear subagentes. Las
  puertas deterministas (scope/budget/approval/secret/a2a/no-daño) **no se relajan**.
- Verificado: validate_suite **369/0**, test_tui **36/36** (incluye el hook por subproceso), test_intel
  **28/28**, `claude plugin validate`, dryrun, py_compile, JSON válido. La auditoría del hook en la CLI
  se valida en la Kali. Espejo opencode regenerado (no arrastra los campos nuevos: frontmatter propio).
- **La auditoría profunda de calidad de los 18 prompts + 9 skills llega aparte en v2.1.0** (pulido
  aditivo, no rompiente).

## [1.11.0] - 2026-06-18
### Added
- **Supervisión humana configurable** (`approval_mode`: `full`/`critical`/`auto`, **por defecto
  `critical`**). Quién aprueba por acción lo decide el operador autorizado vía
  `scope.json` `constraints.approval_mode` o la variable `ORCH_APPROVAL_MODE`:
  - `full` pide aprobación para todo lo de riesgo · `critical` solo para lo crítico
    (C2/implantes/`msfvenom`) · `auto` para nada.
  - Un solo toggle gobierna CLI **y** bot/TUI: nuevo hook `.claude/hooks/approval_gate.py`
    (PreToolUse·Bash; reusa los tiers de `bot/intel/risk.py`) + `bot/intel/runner.py` `_gate`.
  - **Las puertas DETERMINISTAS NO se relajan en ningún modo**: `scope_guard` (alcance),
    `budget_guard` (kill-switch), `secret_scan`, `a2a_guard` y el no-daño siguen activos (un `deny`
    gana sobre cualquier auto-aprobación). El modo se ve en la cabecera de la TUI y se cambia desde
    el panel **Acciones** (o por env/scope).
- **`CONSTITUTION.md` → v2.0.0**: enmienda del **§2** (supervisión humana obligatoria → configurable;
  alcance/no-daño/presupuesto siguen **innegociables**). MAJOR de la constitución (su versionado propio).
- **`docs/config-audit.md`**: resultado de la auditoría + referencia de los modos de supervisión.
### Changed
- **Auditoría de configuración** contra la spec oficial (Claude Code 2.1.x): la config es **válida y
  vigente**. Fixes: `.claude/settings.json` añade `$schema` y **quita las claves `$comment*`** (los
  settings de proyecto son estrictos y se rechazan enteros si no validan); hooks con
  `${CLAUDE_PROJECT_DIR}` + `python3`; manifest del plugin enriquecido
  (`homepage`/`repository`/`license`/`keywords`).
- `contracts/scope.example.json`: documenta `constraints.approval_mode`/`max_actions`/`max_a2a_hops`.
- Docs alineados: `CONSTITUTION.md`, `AGENTS.md`, `GUARDRAILS.md` (C2), `README.md`,
  `docs/RUNBOOK-operador.md`.
### Notes
- **Cambio de comportamiento por defecto del bot/TUI**: con `critical`, el recon/escaneo/explotación
  de tier `ask` (nmap/sqlmap/nxc/secretsdump…) **se auto-aprueba**; solo lo crítico (C2/implantes)
  pide confirmación. Para la supervisión máxima anterior, fija `approval_mode: full`. El alcance y el
  no-daño se aplican igual en todos los modos.
- No rompiente a nivel de software (repo **v1.11.0**, minor). Verificado: test_tui 32/32, test_intel
  28/28, py_compile, validate_suite, JSON válido, bash -n. La UI Textual y el flujo del hook en la
  CLI se validan en la Kali.

## [1.10.1] - 2026-06-18
### Fixed
- **Despliegue resiliente a fallos de red/DNS.** `deploy/auto-deploy.sh` ya NO aborta a mitad si un
  paso de red falla: `pdtm` (ProjectDiscovery), `npm i` de Claude Code, `rag/refresh.py` y el `pip`
  del bot ahora **avisan y continúan**. Antes, un `go install` de pdtm fallido por no resolver
  `proxy.golang.org` por DNS mataba todo el deploy en el paso 3/6 (vía `set -e` + trap ERR).
- **Go tras DNS roto.** `go install` (pdtm/gau) usa `GOPROXY=https://proxy.golang.org|direct` +
  `GOSUMDB=off` con reintento a `direct`: si la máquina no resuelve `proxy.golang.org`/`sum.golang.org`,
  clona directamente de GitHub.
- **`ensure_textual` robusto** (`deploy/lib.sh`): **crea el venv del bot si falta** (en vez de caer al
  Python del sistema, que en Kali falla por PEP 668 *externally-managed*), instala `requirements.txt`
  completo y **reporta el error real** de pip en vez de ocultarlo.
- **Diagrama de Arquitectura del README**: corregido el render (se retira la arista etiquetada con
  destino múltiple `&` que GitHub no renderiza) y **actualizado al estado actual** (bus A2A + router,
  los tres guardarraíles, conteos por zona, entrada del operador Telegram/TUI).
### Added
- **README — apartado "Actualizar"**: pasos exactos para llevar un clon antiguo a la última versión
  conservando los datos de runtime.
### Notes
- `npm warn allow-scripts` (Kali no corre los *postinstall* de npm por política) es benigno: el
  binario de `claude` lo crea npm igualmente y funciona. Sin cambios en agentes/hooks/bot.

## [1.10.0] - 2026-06-18
### Added
- **TUI de control total** (`bot/tui/`): el panel local (Textual) pasa de pantalla única a una
  interfaz por **pestañas** que cubre todos los planos de control del engagement, **sin relajar
  ninguna puerta**:
  - **Bus A2A** — inspector de mensajes (de→a, rol, status, hops, preview) + resumen y techo de hops.
  - **Agentes** — roster de los 18 (+orquestador) desde `agent-cards.json` (fase, modelo, peers).
  - **Presupuesto** — barra del kill-switch C13 (`.action_count`/`max_actions`) + coste de la última
    orden + timeline de fase.
  - **RAG** — estado del store (última sync KEV/EPSS/…) + refresco manual.
  - **Evidencia** — engagements con artefactos + tabla `evidence[]`.
  - **Acciones** (overrides del operador, auditados) — kill-switch (aborta la orden en curso),
    delegación dirigida (la ejecuta el Orquestador por el hub), override de fase, control manual del
    bus A2A (status de un mensaje) y selección de modelo/effort del Orquestador (persistente en `.env`).
- **Separación lógica/presentación**: `bot/tui/state.py` (lector único + renders puros) y
  `bot/tui/actions.py` (escrituras vía `tools/blackboard`) son stdlib puro y quedan cubiertos por una
  nueva suite `bot/tests/test_tui.py` (22 tests). El CSS se extrae a `bot/tui/app.tcss`.
### Changed
- `bot/intel/runner.py` (aditivo, no afecta al bot): expone `last_cost_usd`/`last_turns` de la última
  orden y un `abort()` cooperativo que el gate respeta (kill-switch).
- `README.md`: "Panel TUI de control total" (característica + nota + referencia de comandos).
### Notes
- **Ninguna puerta se relaja**: las acciones que tocan el target siguen pasando por `scope_guard` +
  `budget_guard` + aprobación humana; la "delegación dirigida" NO invoca al subagente directamente
  (lo hace el Orquestador por el hub). Lógica verificada (test_tui 22/22, test_intel 26/26,
  validate_suite, py_compile + revisión de código); la interacción Textual se valida en la Kali
  (Textual no corre en el host de desarrollo Windows).

## [1.9.2] - 2026-06-18
### Changed
- **README — registro de la sección "Despliegue en Kali (E2)" elevado.** Mismos pasos y comandos,
  pero con vocabulario más preciso y profesional sin perder accesibilidad: subsecciones "Requisitos
  previos", "Despliegue paso a paso", "Resolución de problemas" y "Variantes de despliegue". Se
  retira el tono coloquial/hand-holding (metáforas, pulsaciones de teclas de `nano`, "copia y pega
  tal cual") en favor de terminología del dominio (toolchain ofensivo, idempotente, alcance/
  `scope_guard.py`, credenciales, sesión autenticada).
### Notes
- Cambio **solo de documentación** (redacción). Sin cambios funcionales ni de comandos.

## [1.9.1] - 2026-06-18
### Changed
- **README — sección "Despliegue en Kali (E2)" reescrita para personas no técnicas**: requisitos
  previos en lenguaje llano (Kali/VM, bot de Telegram con @BotFather, login Pro), montaje **paso a
  paso** copy-paste (qué hace y qué verás en cada paso), tabla de formas de arranque, checklist de
  "¿funcionó?" y mini-guía de "si algo falla".
- **README — nuevo apartado "Referencia de comandos"**: chuleta con tablas agrupadas (Despliegue ·
  Verificar/mantener · Operar · Coste · RAG · Docker · Desarrollo/validación) con el comando exacto y
  su propósito; añadido a la tabla de contenidos. Los comandos de desarrollo van en un `<details>`.
### Notes
- Cambios **solo de documentación** (presentación). Sin cambios funcionales en agentes, hooks, bot,
  RAG ni en el espejo opencode.

## [1.9.0] - 2026-06-18
### Added
- **opencode multi-modelo con modelos gratuitos (LAB-ONLY) + auto-deploy por entorno.** El espejo
  opencode declara 6 providers **gratuitos** en `.opencode/opencode.json`: `groq` y `cerebras`
  (OpenAI-compatible, **no entrenan** con los prompts), `deepseek`, `openrouter` (OpenAI-compatible)
  y `minimax`/`zhipu` (**Anthropic-compatible**, `@ai-sdk/anthropic`). Todas las claves vía
  `{env:VAR}` → despliegue **no interactivo**, sin `opencode auth login`. Nueva plantilla
  `.opencode/opencode.example.env` (versionada; los `*.env` reales siguen gitignored).
- **Perfil de routing free no-train (activo).** `tools/routing.json` enruta los 5 agentes mecánicos
  (recon/escaneo/parseo) a **Groq/Cerebras**. DeepSeek/MiniMax/GLM/OpenRouter `:free` quedan
  **declarados pero NO enrutados** (opt-in manual; entrenan/residencia sensible). Ollama local sigue
  disponible como alternativa offline.
- **`deploy/verify.sh`**: chequeo (no crítico) de que, si el routing usa un provider free, su clave
  de entorno está exportada (paralelo al de Ollama).
### Changed
- Docs alineadas: `.opencode/README.md` (sección "Modelos gratuitos" con tabla provider/env/clase,
  *gotcha* de IDs con `/` y Anthropic- vs OpenAI-compatible, activar/revertir), `docs/cost-optimization.md`
  ("Modelos gratis" reescrita), `DEPLOY.md`, `docs/RUNBOOK-operador.md` y `README.md` (fila opencode +
  nota lab-only). `deploy/lib.sh`: nota en `ensure_opencode` (claves por entorno).
- Corregido conteo obsoleto en `docs/cost-optimization.md` (subagentes: **6** mecánicos en haiku, no 5).
### Notes
- **Reglas duras (innegociables):** todo el free es **LAB-ONLY** — jamás datos de cliente, **nunca**
  en E2/E3, y solo agentes mecánicos (nunca triage/explotación/reporting). El **bot real de
  engagements sigue 100% Anthropic** (sin free cloud, decisión deliberada: rate-limits, sin fallback,
  *quirks* de tool-protocol). Revertir = vaciar `routes` (`{}`) + `python tools/sync_opencode.py`.
- `verify_opencode.py` ya validaba el cruce ruta↔provider↔modelo (sin cambios de lógica): un id de
  modelo inexistente **no pasa**. Los IDs free y los free-tier **cambian** → re-confirmar contra la
  doc del provider / models.dev al desplegar. JSON estricto (sin `$comment` en `opencode.json`).

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

[2.1.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v2.1.0
[2.0.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v2.0.0
[1.11.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.11.0
[1.10.1]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.10.1
[1.10.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.10.0
[1.9.2]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.9.2
[1.9.1]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.9.1
[1.9.0]: https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases/tag/v1.9.0
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
