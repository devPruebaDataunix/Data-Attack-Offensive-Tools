# Despliegue en Kali (E2) — de 0 a operativo

Guía para montar el entorno completo en una **Kali nueva desde cero** (rolling, amd64).

## TL;DR
```bash
git clone <URL-de-tu-repo-privado> data-attack && cd data-attack
chmod +x deploy/*.sh
sudo ./deploy/auto-deploy.sh      # o:  ./deploy/setup.sh  (asistente guiado con gum)
claude            # haz el login Pro (una vez)
cd bot && ./.venv/bin/python bot.py
# panel de control local en terminal:  ./deploy/dash.sh
```

## Qué hace `auto-deploy.sh` (idempotente, re-ejecutable)
| Fase | Acción |
| :--- | :--- |
| 0 Preflight | comprueba Kali/Debian, sudo, internet, disco ≥15GB, RAM ≥4GB |
| 1 Base | git, curl, jq, python3+pipx+`python-is-python3`, golang, **Node LTS** (NodeSource) |
| 2 Claude | `@anthropic-ai/claude-code` (npm) + aviso de login Pro |
| 3 Toolchain | apt **por-paquete** (nmap, sqlmap, metasploit, ffuf, feroxbuster, seclists, **netexec**, gobuster, john, hashcat, amass, proxychains4, **subfinder/naabu/katana/dnsx**, libpcap-dev, jq, unzip) · **rustscan** (.deb del release) · **chisel** · **httpx** (`httpx-toolkit`+symlink) · **pdtm** como *fallback* de las PD tools · impacket · bloodhound.py · **Sliver** (instalador oficial + fallback a binarios del release) |
| 4 RAG | `rag/refresh.py --epss-all` (KEV + **CVE recientes** CVEDetector/cvelistV5 + CVE5 + ExploitDB + MSF + Nuclei + EPSS) + **RAG de conocimiento** Capa 1 (`rag/knowledge/refresh_kb.py`; Capa 2 semántica opt-in con `--semantic-rag`) |
| 5 Bot | venv + dependencias + crea `bot/.env` (te pregunta token y user-id) |
| 6 Verify | `deploy/verify.sh` — presencia + versión de cada herramienta, validadores, RAG, auth |

> El paso 3 instala además **agentsview** (analítica local de coste, binario fijado + SHA256). Se
> instala con el toolchain pero **no se arranca**: el daemon se levanta a propósito con
> `./deploy/agentsview.sh up`. Ver "Analítica de coste/actividad" más abajo.

> **rustscan / chisel / sliver** se bajan de sus **releases oficiales por HTTPS** cuando no están en apt
> (con `apt` como primer intento). A diferencia de agentsview, **no se pinea checksum**: decisión consciente
> por robustez frente a renombrados de asset upstream (que ya rompieron una iteración previa de este deploy);
> el modelo de amenaza es lab/E2 y la descarga es HTTPS desde el repo oficial. Si rustscan/chisel no se
> pueden instalar, los agentes degradan solos a `nmap -sS -p-` / `proxychains`.

> **Deps de la Capa 2 del RAG (semántica) — `sqlite-vec` + `sentence-transformers` (arrastra torch).** Se
> instalan en un **venv AISLADO del RAG** (`rag/knowledge/.venv`), **no** en el `python3` del sistema: en
> Kali (PEP 668) instalarlas al sistema choca con dpkg (p. ej. el `mpmath` de apt —sin registro de pip— que
> no se puede desinstalar para satisfacer a `torch→sympy`). El venv parte de cero y no toca nada de apt, y se
> instala **torch CPU-only** desde el **índice oficial CPU de PyTorch** (un **segundo índice** además de PyPI)
> para evitar ~2,5 GB de stack CUDA inútil sin GPU. **Sin pin de versión ni hash y desde dos índices** (PyPI +
> `download.pytorch.org`): misma decisión consciente que arriba (modelo lab/E2). Requiere **salida HTTPS** a
> ambos y, en el primer uso, la descarga del modelo de embeddings desde **HuggingFace**; en una caja
> **air-gapped de verdad** la descarga falla y la Capa 2 se **omite sin romper nada** (los agentes usan la
> Capa 1). La prepara `auto-deploy.sh --semantic-rag` y `refresh_kb.py --semantic` (con verificación del
> conteo final). Los agentes consultan con `query_kb.py --semantic`, que **se re-ejecuta** con
> `rag/knowledge/.venv/bin/python` (`os.execv`) — es decir, **el pipeline de agentes ejecuta ese intérprete**:
> trátalo como código de confianza (propiedad del operador, como el resto del árbol del repo; `.venv/` está
> gitignored, no se sube nada). El **cron** semanal corre con `--no-install-deps`, y el deploy **devuelve la
> propiedad** de los artefactos del RAG al operador (el cron no es root). La lógica vive en
> `rag/knowledge/_venv.py` (única fuente de verdad). Endurecimiento futuro: pin + hash de wheels y
> `--no-index` desde un espejo local para air-gap real.

Flags: `--update` (todo a lo último), `--skip-tools`, `--no-rag`, `--no-bot`.

## Últimas versiones
- Kali rolling → `apt update` trae lo último del repo.
- ProjectDiscovery → `pdtm -ua`; plantillas Nuclei → `nuclei -update-templates`.
- pipx → `pipx upgrade-all`; Sliver → re-ejecutar el script.
- `./deploy/auto-deploy.sh --update` hace todo eso de una vez.

## Verificación
```bash
./deploy/verify.sh              # tabla OK/faltante + versiones; sale !=0 si falta algo crítico
./deploy/verify.sh --install    # además instala lo que falte (toolchain, claude, PD tools, impacket, opencode)
./deploy/verify.sh --update     # además actualiza todo a su última versión
```
`verify.sh` comprueba también la **réplica opencode** (`tools/verify_opencode.py`: opencode.json
+ 28 agentes + cruce `routing.json`↔provider) y, si el routing enruta a Ollama o a un provider free
(Groq/Cerebras/…), su disponibilidad / que esté exportada su clave de entorno.
Comprueba además (no críticos) `gum`, `textual` y `agentsview` (asistente, panel TUI y analítica de coste).

> **Modelos gratuitos del espejo opencode (LAB-ONLY).** El espejo opencode puede correr agentes
> mecánicos (recon/escaneo/parseo) con modelos **gratuitos** para practicar contra laboratorios
> propios sin gastar. Por defecto van a **Groq/Cerebras** (no entrenan con los prompts). Despliegue
> **no interactivo** (sin `opencode auth login`): `cp .opencode/opencode.example.env
> .opencode/opencode.env`, rellena las claves y cárgalas (`set -a; . .opencode/opencode.env; set +a`).
> **Regla dura:** LAB-ONLY, **jamás** datos de cliente, **nunca** E2/E3. El bot real de engagements
> sigue 100% Anthropic. Detalle y opt-in de más providers en `.opencode/README.md`.
>
> **Autodespliegue del runtime opencode.** El paso "Espejo opencode" del `auto-deploy.sh` **instala el
> binario de opencode** (`ensure_opencode` → `npm i -g opencode-ai`, idempotente) además de escribir la
> config y pedir la clave: deja el espejo **ejecutable**, no solo configurado. El bot de Telegram **no**
> conduce opencode (sigue 100% Anthropic con todos los guardrails, decisión consciente): opencode/NVIDIA
> se usa por CLI para **corroborar el cableado** (perfil `apply_routing.py nvidia-lab`), no como medición.
>
> **Claves de modelos free (interactivas en el auto-deploy).** El paso "Espejo opencode" del
> `auto-deploy.sh` pide **TODAS** las claves free necesarias (`configure_opencode_keys`, en `lib.sh`):
> primero las que **no entrenan** (`GROQ_API_KEY`, `CEREBRAS_API_KEY` — perfil activo — y `NVIDIA_API_KEY`),
> y luego, **opt-in**, las de los providers que **recopilan información/entrenan** con los prompts
> (`DEEPSEEK`/`MINIMAX`/`ZHIPU`/`OPENROUTER`): responder **N** las deja **deshabilitadas** (clave vacía =
> el routing no las usa). Cada una con **Enter para omitir**; idempotente (no clobbera las ya puestas);
> escritura charset-safe (sin `sed`); permisos 600 + propiedad del operador. Sin **TTY** (CI) NO pregunta:
> copia la plantilla y sigue. Todo **lab-only** (jamás cliente/E2/E3). Reconfigura cuando quieras desde
> `setup.sh` → "Configurar claves de modelos free (opencode)".

## Asistente guiado y panel TUI
- **`./deploy/setup.sh`** — asistente interactivo (con [gum](https://github.com/charmbracelet/gum);
  degrada a texto plano). Opciones: **Montaje COMPLETO automático** (despliega todo el entorno de punta a
  punta — base/tools/RAG/bot/opencode + todas las claves free + perfil + scope + verificación — **sin
  detenerse ante un fallo**: reporta cada paso y resume incidencias), despliegue, `bot/.env`, **claves de
  modelos free (opencode)**, `scope.json`, verificación y apertura del panel.
- **`./deploy/dash.sh`** — **panel de control TUI** (Textual), gemelo local del bot: estado,
  hallazgos en vivo y órdenes al Orquestador con la misma aprobación humana y el mismo scope-gate.
  Requiere `textual` (lo instalan `auto-deploy.sh` y `verify.sh --install`).

## Analítica de coste/actividad (agentsview)
[agentsview](https://github.com/kenn-io/agentsview) da dashboards **locales** de coste y actividad por
agente leyendo `~/.claude/projects/`. El `auto-deploy` instala el binario (versión fijada + SHA256); se
arranca a propósito:
```bash
./deploy/agentsview.sh up        # dashboard en http://127.0.0.1:8080 (local-only, telemetria off)
./deploy/agentsview.sh usage     # desglose de coste/uso en la terminal
```
**Local-only por diseño** (los transcripts llevan datos de cliente): vincula a `127.0.0.1`, telemetría
off, **nunca** `--public-url`, máquina del operador. Read-only sobre los transcripts. Detalle en
`docs/cost-optimization.md`.

## Login de Claude (manual, una vez)
El login Pro es interactivo. Ejecuta `claude`, completa el OAuth, y ya queda la sesión en la VM
(la usan tanto la CLI como el bot vía `claude -p`).

> Nota de coste: desde el 15-jun-2026, `claude -p`/Agent SDK en planes de suscripción consumen de
> un crédito mensual de Agent SDK separado del uso interactivo.

## Despliegue en contenedores (Docker) — alternativa reproducible al deploy de host
La suite se puede levantar en Docker para un primer despliegue reproducible. La imagen
(`Dockerfile`, base **Kali rolling**) trae el toolchain ofensivo + Claude Code + el repo,
**reutilizando el mismo `deploy/lib.sh`** que el deploy de host (sin duplicar la lista de tools).

```bash
./deploy/docker.sh up        # build + RAG (si falta) + levanta el bot
./deploy/docker.sh logs      # sigue los logs del bot
./deploy/docker.sh shell     # shell dentro de la imagen (toolchain disponible)
./deploy/docker.sh status    # estado de los contenedores
./deploy/docker.sh down      # para y elimina
```

Requisitos en el host (con Docker):
- **Login Pro de Claude hecho una vez en el host** (`claude` → OAuth). Se reutiliza montando
  `~/.claude` en el contenedor; lo necesitan el bot y los agentes.
- **`bot/.env`** con `TELEGRAM_TOKEN` y `ALLOWED_USER_ID` (créalo con `./deploy/setup.sh`). Se
  **monta**, no se hornea en la imagen.
- Datos de cliente (`contracts/`, `engagements/`, `rag/`, `report/`) se montan como volúmenes →
  persisten fuera de la imagen y nunca se hornean ni se commitean (`.dockerignore`).

Notas:
- El **RAG se puebla en runtime** (`./deploy/docker.sh rag`, o automático en `up`), no se hornea
  (evita CVEs caducos en la imagen).
- Red: el servicio usa `network_mode: host` para alcanzar la VLAN del engagement (lab).
- `~/.claude` se monta en lectura/escritura (Claude Code escribe estado de sesión) → asume un
  **único operador** por máquina.
- El **build requiere Docker** y se hace en el host (no en Windows). `docker.sh` instala
  Docker/Compose si faltan (`ensure_docker`). Es una **alternativa** al deploy de host, no un
  requisito: el modelo nativo sigue siendo Kali + Claude Code.

## Contenedor efímero por-engagement (anillo de aislamiento — mejora "C")
Para procesar **contenido potencialmente hostil** (el **código de cliente white-box** que ingiere
`code-recon`, y en releases posteriores el navegador headless / proxy de interceptación / validación
por visión) hay un **contenedor DESECHABLE que monta SOLO un engagement**, endurecido y sin egress:

```bash
./deploy/docker.sh build                          # una vez: construye data-attack:latest
./deploy/engagement-run.sh <engagement_id>        # shell en el anillo (sin red)
./deploy/engagement-run.sh <engagement_id> -- python rag/context/ingest_context.py -e <engagement_id>
./deploy/engagement-run.sh <engagement_id> --net da-eng     # con una red docker acotada
# variante declarativa (para un id YA validado; el .sh es el entrypoint sancionado que SANEA el id):
ENGAGEMENT_ID=<engagement_id> docker compose -f docker-compose.engagement.yml run --rm engagement
```

Propiedades de aislamiento (**CONSTITUTION §1** aislamiento de cliente, **§6** datos E3):
- Monta **solo `engagements/<id>/`** (rw) — nunca todos los engagements ni el código del repo
  (horneado en la imagen, rootfs **read-only**). Un cliente no puede ver a otro.
- **`scope.json` READ-ONLY** dentro del anillo: el `run_scope` queda **congelado** durante la corrida
  (las puertas no se relajan; encaja con "run_scope inmutable salvo reapertura del operador").
- **Sin red por defecto** (`--network none` / `network_mode: none`): procesar contenido hostil no
  necesita egress. Se puede acotar a una red docker con `--net <red>` para el tooling que sí la use.
- **Efímero** (`--rm`), `cap-drop ALL`, `no-new-privileges`, `pids/mem/cpu` acotados, `/tmp` en tmpfs.
- **`~/.claude` NO se monta**: las credenciales del operador quedan **fuera** del anillo. Solo con
  `--claude-auth` (opt-in) se monta **read-only**, y únicamente si el anillo debe pilotar Claude.

Este anillo **complementa** —no sustituye— el guard en-proceso `.claude/hooks/fs_guard.py`, que bloquea
de forma determinista que una lectura (`Read`/`Grep`/`Glob`) siga un **symlink** o un `..` que escape del
árbol de código de cliente (`engagements/<id>/recon/src/`) o del propio repo. El guard protege aunque se
corra sobre el host sin contenedor; el contenedor da el **confinamiento duro** por namespace de montaje.

## Bot como servicio (opcional, systemd)
```ini
# /etc/systemd/system/databot.service
[Unit]
Description=Data Attack Telegram Bot
After=network-online.target
[Service]
WorkingDirectory=/ruta/data-attack/bot
ExecStart=/ruta/data-attack/bot/.venv/bin/python bot.py
Restart=on-failure
User=kali
[Install]
WantedBy=multi-user.target
```
`sudo systemctl enable --now databot`

## Antes de operar (recordatorio)
1. **Define `contracts/scope.json`** con el alcance autorizado real (sin él, el gate bloquea todo).
2. Una VM E2 **por cliente**; kill-switch de red.
3. El informe sale como borrador → **revisión humana** antes de entregar.
