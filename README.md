<!-- BANNER -->
<p align="center">
  <img src="docs/assets/banner.png" alt="Data Attack — suite de agentes para pentesting y bug bounty autorizado" width="100%">
</p>

<h1 align="center">Data Attack — Offensive Tools</h1>

<p align="center">
  <b>Suite de 18 agentes especialistas para pentesting y bug bounty autorizado.</b><br>
  Orquestación hub-and-spoke con bus A2A mediado sobre los subagentes nativos de Claude Code,
  con guardián de alcance determinista, RAG de vulnerabilidades y control remoto por Telegram.
</p>

<!-- BADGES — actividad del repo -->
<!--<p align="center">
  <a href="https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/stargazers"><img src="https://img.shields.io/github/stars/devPruebaDataunix/Data-Attack-Offensive-Tools?style=for-the-badge&logo=github&color=FFD700&labelColor=0D1117" alt="Stars"></a>
  <a href="https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/network/members"><img src="https://img.shields.io/github/forks/devPruebaDataunix/Data-Attack-Offensive-Tools?style=for-the-badge&logo=github&color=00D4FF&labelColor=0D1117" alt="Forks"></a>
  <a href="https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/issues"><img src="https://img.shields.io/github/issues/devPruebaDataunix/Data-Attack-Offensive-Tools?style=for-the-badge&logo=github&color=FF6B35&labelColor=0D1117" alt="Issues"></a>
  <a href="https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/commits"><img src="https://img.shields.io/github/last-commit/devPruebaDataunix/Data-Attack-Offensive-Tools?style=for-the-badge&logo=git&logoColor=white&color=3FB950&labelColor=0D1117" alt="Último commit"></a>
  <a href="https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases"><img src="https://img.shields.io/github/v/release/devPruebaDataunix/Data-Attack-Offensive-Tools?style=for-the-badge&logo=github&color=8957E5&labelColor=0D1117&label=versi%C3%B3n" alt="Última versión"></a>
</p> -->

<!-- BADGES — identidad y stack real -->
<p align="center">
  <img src="https://img.shields.io/badge/Plataforma-Kali_Linux-557C94?style=for-the-badge&logo=kalilinux&logoColor=white&labelColor=0D1117" alt="Kali">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white&labelColor=0D1117" alt="Python">
  <img src="https://img.shields.io/badge/Shell-Bash-4EAA25?style=for-the-badge&logo=gnubash&logoColor=white&labelColor=0D1117" alt="Bash">
  <img src="https://img.shields.io/badge/Motor-Claude_Code-FF6B35?style=for-the-badge&logo=anthropic&logoColor=white&labelColor=0D1117" alt="Claude Code">
  <img src="https://img.shields.io/badge/RAG-SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white&labelColor=0D1117" alt="SQLite">
  <img src="https://img.shields.io/badge/Deploy-Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white&labelColor=0D1117" alt="Docker (deploy opcional)">
</p>

<!-- BADGES — capacidades -->
<p align="center">
  <img src="https://img.shields.io/badge/Agentes-18_especialistas-00D4FF?style=flat-square&labelColor=0D1117" alt="18 agentes">
  <img src="https://img.shields.io/badge/Orquestaci%C3%B3n-Hub--and--Spoke_%2B_A2A-00D4FF?style=flat-square&labelColor=0D1117" alt="Hub-and-spoke + A2A">
  <img src="https://img.shields.io/badge/Vulns-KEV%2BEPSS-00D4FF?style=flat-square&labelColor=0D1117" alt="RAG KEV+EPSS">
  <img src="https://img.shields.io/badge/Alcance-scope--guarded-3FB950?style=flat-square&labelColor=0D1117" alt="Scope guarded">
  <img src="https://img.shields.io/badge/Control-humano_en_el_bucle-3FB950?style=flat-square&labelColor=0D1117" alt="Humano en el bucle">
  <img src="https://img.shields.io/badge/Guardarra%C3%ADles-OWASP_LLM_Top_10-3FB950?style=flat-square&labelColor=0D1117" alt="Guardarraíles OWASP LLM Top 10">
</p>

<!-- BADGES — legal -->
<p align="center">
  <img src="https://img.shields.io/badge/Licencia-Propietaria-D29922?style=flat-square&labelColor=0D1117" alt="Licencia propietaria">
  <img src="https://img.shields.io/badge/Uso-autorizado_%C3%BAnicamente-FF4444?style=flat-square&labelColor=0D1117" alt="Uso autorizado únicamente">
</p>

> [!WARNING]
> **USO AUTORIZADO ÚNICAMENTE.**
> Estos agentes operan exclusivamente dentro del alcance de un contrato de pentest firmado o de un programa de bug bounty con scope explícito.
> `contracts/scope.json` es la fuente de verdad del alcance y un *hook* lo aplica de forma
> determinista antes de cada acción.
> Operar fuera de scope es ilegal.
>       No lo hagas.

---

## Tabla de contenidos

- [Qué es](#qué-es)
- [Características clave](#características-clave)
- [Arquitectura](#arquitectura)
- [Despliegue en Kali (E2)](#despliegue-en-kali-e2)
- [Actualizar](#actualizar)
- [Plataformas soportadas](#plataformas-soportadas)
- [Instalación rápida (Claude Code)](#instalación-rápida-claude-code)
- [Los 18 agentes](#los-18-agentes)
- [Bot de Telegram](#bot-de-telegram)
- [RAG de vulnerabilidades](#rag-de-vulnerabilidades-kevepss)
- [Flujo engagement-driven](#flujo-engagement-driven)
- [Las tres zonas de aislamiento](#las-tres-zonas-de-aislamiento)
- [Seguridad](#seguridad)
- [Referencia de comandos](#referencia-de-comandos)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Licencia](#licencia)

---

## Qué es Data Attack

Data Attack es una suite de **18 agentes especialistas** (de fase y de herramienta), un **orquestador**, un
**guardián de alcance** (hook determinista), un **RAG de vulnerabilidades** KEV+EPSS y un
**bot de Telegram** para conducir todo desde el móvil. Cubre las fases de un engagement
ofensivo —recon, análisis, explotación y cierre— sobre el sistema nativo de **subagentes de
Claude Code**, con un espejo equivalente para **opencode**.

Manda un **orquestador** (la sesión principal, `AGENTS.md`): planifica, delega y **enruta**.
Los agentes ahora pueden **dirigirse mensajes entre sí** por un **bus A2A mediado**, pero no se
invocan directamente —dejan el mensaje en el **blackboard** (`contracts/engagement.json`) y el
orquestador lo entrega—, así todo queda auditado y gateado. No hay malla peer-to-peer en el
camino de cliente (decisión de seguridad; ver [`ARCHITECTURE.md`](ARCHITECTURE.md)). Cada comando
que toca un objetivo pasa antes por `scope_guard.py`, que lo bloquea si el target no está en
`contracts/scope.json`, y cada mensaje A2A por `a2a_guard.py` (emisor/destino válidos + techo de
hops anti-bucle).

## Características clave

| | Capacidad | Qué aporta |
| :---: | :--- | :--- |
| 🧭 | **Hub-and-spoke + bus A2A** | Un orquestador delega por fases y enruta; los agentes se dirigen mensajes A2A entre sí por el blackboard (mediado, auditado y con techo de hops), sin malla directa. |
| 🤖 | **18 agentes especialistas** | Recon, triage, explotación web/red/AD, C2 simulado, red team de IA/LLM, informe y postmortem. |
| 📚 | **RAG KEV+EPSS** | `vuln-triage` prioriza por lo que de verdad se explota (CISA KEV, EPSS, exploit público), sin reentrenar el modelo. |
| 🛡️ | **Guardián de alcance** | `scope_guard.py` bloquea de forma determinista cualquier acción fuera de `scope.json`. |
| 🙋 | **Supervisión configurable** | Aprobación humana por acción en modo `full`/`critical`/`auto` (def. `critical`); el alcance y el no-daño **NO** se relajan en ningún modo. |
| 🔒 | **Mínimo privilegio por agente** | Cada especialista acota sus turnos (`maxTurns`) y no puede spawnear subagentes (`disallowedTools: Agent, Task`, malla hub-and-spoke); el cierre (reporting/postmortem) además sin `Bash`. El fin de cada subagente se audita (`SubagentStop`). |
| 📱 | **Bot de Telegram** | Control remoto en lenguaje natural, resúmenes en vivo y aprobación por nivel de riesgo. |
| 🖥️ | **Panel TUI de control total** | Terminal (Textual) por pestañas: estado, **bus A2A**, roster de agentes, **presupuesto/coste**, RAG, evidencia y **acciones** (kill-switch, delegación dirigida, override de fase) — con las mismas puertas que el bot. |
| 📊 | **Analítica de coste local** | [agentsview](https://github.com/kenn-io/agentsview) (local-first) lee `~/.claude/projects/` → coste y actividad por agente en `127.0.0.1:8080`. Re-medir el gasto sin sacar datos. |
| 🧠 | **Aprendizaje por errores** | `knowledge-postmortem` guarda lecciones de cada intento en memoria persistente y en el blackboard. |
| 🧩 | **Multiplataforma** | Claude Code (CLI + extensión de VS Code) y espejo para opencode. |

## Arquitectura

El orquestador delega por fases hacia tres zonas de aislamiento (E1 recon, E2 explotación,
E3 cierre) y hace de **router del bus A2A** entre agentes. Los agentes escriben hallazgos y
mensajes en el blackboard; `vuln-triage` consulta el RAG; y cada acción que toca al objetivo pasa
por los **guardarraíles deterministas** (alcance, presupuesto, bus A2A) **+ aprobación humana**.

```mermaid
flowchart TB
    OP["👤 Operador<br/>Telegram · TUI de control total"]
    ORQ["🧭 Orquestador · AGENTS.md<br/>sesión principal · hub + router A2A"]
    subgraph GATES["🛡️ Guardarraíles deterministas (hooks)"]
        SG["scope_guard"]
        BG["budget_guard"]
        AG["a2a_guard"]
    end
    BB[("🗒️ Blackboard · engagement.json<br/>targets · findings · mensajes A2A · evidencia")]
    RAGDB[("📚 RAG KEV+EPSS<br/>SQLite")]
    subgraph E1["🟦 E1 · Recon (3)"]
        R["osint-recon · active-recon · recon-suite"]
    end
    subgraph E2["🟥 E2 · Explotación (13)"]
        X["vuln-triage · nuclei · web-exploit · web-fuzzing · sqlmap<br/>network-exploit · metasploit · netexec<br/>post-exploit · lateral-discovery · sliver · c2-exfil · ai-security"]
    end
    subgraph E3["🟩 E3 · Cierre (2)"]
        C["reporting · knowledge-postmortem"]
    end
    OP -->|órdenes · aprobación humana| ORQ
    ORQ -->|delega y enruta| E1
    ORQ -->|delega y enruta| E2
    ORQ -->|delega y enruta| E3
    ORQ -.->|cada acción pasa por| GATES
    E1 -.->|targets| BB
    E2 -.->|findings · A2A| BB
    E3 -.->|informe · lecciones| BB
    BB -.->|reinyecta lecciones| ORQ
    X -->|consulta CVE| RAGDB
```

> El mapa completo y siempre al día vive en [ARCHITECTURE_MAP.md](ARCHITECTURE_MAP.md) — se
> regenera solo (hook `PostToolUse`) cada vez que cambia un agente, hook, contrato o módulo
> del RAG. La auditoría crítica y el modelo de comunicación, en [ARCHITECTURE.md](ARCHITECTURE.md).

## Despliegue en Kali (E2)

Despliegue completo sobre una Kali desde cero. Ejecuta los pasos **en orden**; el detalle técnico
ampliado está en [DEPLOY.md](DEPLOY.md).

### Requisitos previos

- 🐉 **Kali Linux** como host de trabajo (la zona "E2"), nativa o en máquina virtual. Si partes de
  cero, descarga una imagen oficial desde [kali.org/get-kali](https://www.kali.org/get-kali/) y
  reserva **≥ 4 GB de RAM** y **≥ 15 GB de disco**.
- 🌐 **Salida a internet** desde la Kali.
- 📱 **Credenciales del bot de Telegram**: registra un bot con [@BotFather](https://t.me/BotFather)
  (`/newbot`) y guarda su **token**, junto con tu **ID de usuario** numérico
  ([@userinfobot](https://t.me/userinfobot)). El bot es el canal de control remoto.
- 🔑 **Sesión de Claude Pro** activa: es el modelo que razona y ejecuta los agentes.

### Despliegue paso a paso

**1. Clona el repositorio**
```bash
git clone https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools.git data-attack
cd data-attack
```

**2. Despliega el entorno completo**
```bash
chmod +x deploy/*.sh
sudo ./deploy/auto-deploy.sh
```
Instala y verifica el toolchain ofensivo (nmap, sqlmap, Metasploit, NetExec, Sliver,
ProjectDiscovery…), Claude Code, el RAG de vulnerabilidades y el bot. El instalador es
**idempotente** —puedes relanzarlo sin riesgo si se interrumpe— y solicita el **token de Telegram**
y tu **ID** durante la ejecución. Finaliza con `✔ Despliegue completado`.

> 🔐 **Autenticación inicial (una vez):** ejecuta `claude` e inicia sesión con tu cuenta Pro. El bot
> opera sobre esa sesión, por lo que debe quedar autenticada en la máquina.

**3. Declara el alcance autorizado**
```bash
cp contracts/scope.example.json contracts/scope.json
nano contracts/scope.json
```
`scope.json` define los dominios e IPs **en alcance**. Cumpliméntalo con los del engagement. Toda
acción contra un objetivo ausente de ese fichero la bloquea `scope_guard.py`; operar fuera de alcance
es ilegal y recae sobre el operador.

**4. Inicia el control** (una de estas vías)

| Vía | Comando |
| :--- | :--- |
| 📱 Bot de Telegram (remoto) | `cd bot && ./.venv/bin/python bot.py` |
| 🖥️ Panel TUI (terminal) | `./deploy/dash.sh` |
| ⌨️ CLI de Claude Code | `claude` → `/agents` |

**5. Verifica el entorno**
```bash
./deploy/verify.sh
```
Devuelve un cuadro de estado (✅/faltante) y termina con error si falta algún componente crítico.

### Resolución de problemas

- **El despliegue se interrumpe:** revisa la conectividad y **relanza** `sudo ./deploy/auto-deploy.sh`
  (es idempotente, no deja el entorno a medias).
- **El bot no responde:** confirma la sesión de `claude` y que `bot/.env` contiene el token y tu ID;
  regenéralo con `./deploy/setup.sh` si procede.
- **Falta alguna herramienta:** `./deploy/verify.sh --install` instala los componentes pendientes.

### Variantes de despliegue

- 🧭 **Asistente guiado:** `./deploy/setup.sh` cubre despliegue, `bot/.env`, `scope.json` y
  verificación mediante menús ([gum](https://github.com/charmbracelet/gum)).
- 🐳 **Contenedores:** `./deploy/docker.sh up` construye la imagen y levanta el bot sin instalar el
  toolchain en el host (monta tu sesión Pro `~/.claude` y `bot/.env`; no se incrustan en la imagen).
  Ver [DEPLOY.md](DEPLOY.md) → "Despliegue en contenedores".
- 💰 **Coste:** `./deploy/agentsview.sh up` expone un panel **local** de coste/actividad por agente
  ([agentsview](https://github.com/kenn-io/agentsview); lee `~/.claude/projects/`, sirve en
  `127.0.0.1:8080`, telemetría desactivada — nunca expuesto a internet).

> Detalle técnico completo en [DEPLOY.md](DEPLOY.md) y [bot/README.md](bot/README.md).

## Actualizar

¿Tienes el repositorio clonado en una versión antigua? Estos pasos lo llevan a la última
**conservando tus datos de runtime** (`contracts/scope.json`, `contracts/engagement.json`,
`bot/.env`, `rag/vulns.db` y `engagements/` están en `.gitignore` y no se tocan).

**1. Comprueba cómo de atrás vas**
```bash
cd data-attack
git fetch origin
git log --oneline -1                  # tu versión actual
git log --oneline -1 origin/master    # la última publicada
```

**2. Actualiza el código**
```bash
git pull --ff-only origin master
```
Si tienes ediciones locales y `--ff-only` se queja, apártalas y vuelve a aplicarlas:
```bash
git stash && git pull --ff-only origin master && git stash pop
```
*(Opción de fuerza —descarta cambios locales del código, no tus datos—:* `git reset --hard origin/master`*.)*

**3. Instala lo nuevo y reverifica**
```bash
chmod +x deploy/*.sh
./deploy/verify.sh --install     # instala solo lo que falte (TUI/textual, agentsview, opencode, toolchain)
./deploy/verify.sh               # tabla de estado: todo en ✅
```
Para **actualizar además todo el toolchain** a su última versión: `sudo ./deploy/auto-deploy.sh --update`.

> El despliegue es **idempotente** y **tolerante a fallos de red**: si un componente no se puede
> instalar (p. ej. un fallo de DNS), te avisa y **continúa con el resto** en vez de abortar;
> re-ejecútalo cuando se resuelva. Lo que ha cambiado entre versiones, en [CHANGELOG.md](CHANGELOG.md).

## Plataformas soportadas

| Plataforma | Cómo se carga | Estado |
| :--- | :--- | :--- |
| **Claude Code** (CLI + extensión de VS Code) | `.claude/agents/*.md` + `.claude/settings.json` | ✅ Objetivo principal |
| **opencode** | `.opencode/agent/*.md` + `opencode.json` | ✅ Espejo equivalente · routing multi-modelo con modelos **gratuitos** (Groq/Cerebras/… `tools/routing.json`) para lab — ver nota |
| **VS Code** | Misma carpeta `.claude/` del workspace, vía extensión Claude Code | ✅ Sin cambios |

> **Nota (modelos gratuitos del espejo opencode).** El espejo puede correr los agentes mecánicos
> (recon/escaneo/parseo) con modelos **gratuitos** para practicar contra **laboratorios propios** sin
> gastar (por defecto Groq/Cerebras, que no entrenan con los prompts; claves por entorno, sin `auth
> login`). Es **LAB-ONLY**: jamás datos de cliente, nunca en E2/E3. El bot real de engagements sigue
> **100% Anthropic**. Detalle, opt-in de más providers y reglas en [`.opencode/README.md`](.opencode/README.md).

## Instalación rápida (Claude Code)

```powershell
# 1. Copia el contenido en la raíz de tu workspace de engagement
#    (la carpeta .claude/ debe quedar en la raíz del proyecto)

# 2. Define el alcance autorizado ANTES de nada:
copy contracts\scope.example.json contracts\scope.json
#    edita scope.json con los dominios/IPs/CIDR del engagement

# 3. Abre Claude Code en esa carpeta y verifica los agentes:
#    /agents

# 4. Comprueba que el hook de alcance está activo:
#    revisa .claude/settings.json -> hooks.PreToolUse
```

## Los 18 agentes

Repartidos por zona de aislamiento. Cada agente trae su modelo, sus tools y su permiso ya
fijados; el orquestador decide a quién llamar en cada fase.

<details>
<summary><b>🟦 Zona E1 · Recon (3)</b></summary>

| Agente | Modelo | Función |
| :--- | :--- | :--- |
| **osint-recon** | haiku-4-5 | Recon pasivo: mapea la superficie sin tocar al objetivo. |
| **active-recon** | haiku-4-5 | Recon activo: enumeración y escaneo de puertos/servicios. |
| **recon-suite** | haiku-4-5 | Toolkit moderno: subfinder, amass, dnsx, httpx. |

</details>

<details>
<summary><b>🟥 Zona E2 · Explotación (13)</b></summary>

| Agente | Modelo | Función |
| :--- | :--- | :--- |
| **vuln-triage** | sonnet-4-6 | Prioriza vulnerabilidades consultando el RAG (KEV/exploit/EPSS/CVSS). |
| **nuclei** | haiku-4-5 | Escaneo de vulnerabilidades con plantillas de ProjectDiscovery. |
| **web-exploit** | opus-4-8 | Explotación de aplicaciones web (capa 7 HTTP/S). |
| **web-fuzzing** | haiku-4-5 | Descubrimiento de contenido y fuzzing con ffuf/feroxbuster. |
| **sqlmap** | sonnet-4-6 | Inyección SQL automatizada, operador senior de sqlmap. |
| **network-exploit** | sonnet-4-6 | Explotación de servicios de red e infraestructura no-HTTP. |
| **post-exploit** | opus-4-8 | Post-explotación sobre un host ya comprometido en scope. |
| **lateral-discovery** | sonnet-4-6 | Descubrimiento interno y movimiento lateral desde un punto de apoyo. |
| **metasploit** | sonnet-4-6 | Operador senior de Metasploit Framework. |
| **netexec** | sonnet-4-6 | NetExec (nxc) + Impacket para entornos Windows/AD. |
| **sliver** | sonnet-4-6 | Operador de Sliver C2 (open source) para post-explotación. |
| **c2-exfil** | sonnet-4-6 | Simulación controlada de C2, exfiltración e impacto. |
| **ai-security** | opus-4-8 | Red teaming de aplicaciones con IA/LLM (OWASP LLM Top 10). |

</details>

<details>
<summary><b>🟩 Zona E3 · Cierre (2)</b></summary>

| Agente | Modelo | Función |
| :--- | :--- | :--- |
| **reporting** | opus-4-8 | Redacta el informe: CVSS 3.1 + vector, MITRE ATT&CK, cadena de ataque. |
| **knowledge-postmortem** | haiku-4-5 | Aprende de cada intento; escribe lecciones en memoria persistente. |

</details>

## Bot de Telegram

Mando a distancia y dashboard de intel del framework, sobre la VM E2. Le hablas en lenguaje
natural, interpreta, te pide confirmación, resume en vivo lo que hace y solo te escala lo que
es alerta real. Corre sobre el **Claude Agent SDK** (con caída a `claude -p` si el SDK no
está). Detalle en [bot/README.md](bot/README.md).

> **Panel TUI de control total** (`./deploy/dash.sh`): el mismo cerebro (`bot/intel`) y las mismas
> puertas que el bot, en la terminal de la Kali, organizado en **pestañas** — *Panel* (estado/hallazgos),
> *Bus A2A* (inspector de mensajes + hops), *Agentes* (roster), *Presupuesto* (kill-switch + coste),
> *RAG*, *Evidencia* y *Acciones* (abortar la orden en curso, delegación dirigida, override de fase,
> control del bus A2A, modelo/effort). Ninguna acción se salta el scope ni la aprobación humana. El
> bot de Telegram queda para el control remoto.

<details>
<summary><b>Aprobación por niveles de riesgo</b></summary>

Cada comando se clasifica en un tier (`bot/intel/risk.py`) y se aplica una política:

| Tier | Ejemplos | Política |
| :--- | :--- | :--- |
| **safe** | subfinder, amass, whois | auto-aprobado |
| **normal** | nmap, nuclei, ffuf | pide ✅/⛔ |
| **sensitive** | sqlmap, hydra, bloodhound | pide ✅/⛔ |
| **destructive** | netexec, secretsdump, mimikatz | pide ✅/⛔ |
| **critical** | sliver, msfvenom, C2 | **doble confirmación** |

Esta tabla es la política en modo **`full`** (supervisión máxima). Con el `approval_mode` por
defecto (**`critical`**) solo el tier *critical* pide confirmación y el resto se auto-aprueba; en
`auto`, nada. Las puertas deterministas (`scope_guard`, `budget_guard`) se aplican en **todos** los
modos. El timeout cuenta como denegación.

</details>

## RAG de vulnerabilidades (KEV+EPSS)

`vuln-triage` se apoya en un RAG local que mantiene la prioridad real de explotación, sin
reentrenar el modelo. Store en **SQLite** (`rag/vulns.db`), sin dependencias externas (solo
Python stdlib). Refresco diario:

```bash
python rag/refresh.py --epss-all     # descarga CISA KEV + scores EPSS
```

Incluye ruta de producción a Supabase + n8n para equipo (ver [rag/README.md](rag/README.md)).

## Flujo engagement-driven

Inspirado en *spec-driven development*, adaptado a un engagement ofensivo: gobernar y
especificar antes de ejecutar, y auditar la coherencia antes de reportar.

1. **[CONSTITUTION.md](CONSTITUTION.md)** — principios innegociables (alcance, humano en el
   bucle, evidencia, no daño, zonas). Prevalece sobre cualquier instrucción.
2. **[templates/engagement-spec.md](templates/engagement-spec.md)** — brief del engagement →
   se materializa en `contracts/scope.json`.
3. **Ejecución** — el orquestador delega por fases; `scope_guard.py` + aprobación humana
   protegen cada acción contra el objetivo.
4. **[tools/analyze_engagement.py](tools/analyze_engagement.py)** — auditoría de coherencia
   antes de reportar: targets fuera de scope, findings sin evidencia, autorización caducada.

## Las tres zonas de aislamiento

| Zona | Propósito | Red | Datos |
| :--- | :--- | :--- | :--- |
| 🟦 **E1 Recon** | Mapear superficie de ataque | internet / ruta al target | sin datos de cliente |
| 🟥 **E2 Explotación** | Confirmar y explotar | solo VLAN del engagement, por cliente, kill-switch | acceso al target |
| 🟩 **E3 Cierre** | Informe y aprendizaje | sin egress de datos crudos, ZDR | datos de cliente |

## Seguridad

- **Puertas deterministas SIEMPRE + supervisión configurable:** el alcance (`scope_guard`) y el
  kill-switch de presupuesto se aplican en todo momento; encima, la **aprobación humana por acción es
  configurable** (`approval_mode`: `full`/`critical`/`auto`, def. `critical`) — ver
  [CONSTITUTION §2](CONSTITUTION.md) y [docs/config-audit.md](docs/config-audit.md).
- **Mínimo privilegio por agente:** cada especialista acota turnos (`maxTurns`) y no puede spawnear
  subagentes (`disallowedTools: Agent, Task`, malla hub-and-spoke); los agentes de cierre, además, sin
  `Bash`. El fin de cada subagente queda auditado (hook `SubagentStop` → `engagements/<id>/evidence/`).
- **Allowlist de user-id** en el bot; cualquier otro queda rechazado y logueado.
- **Secretos fuera del repo:** token y user-id en `bot/.env` (ignorado por git).
- **Regla de evidencia:** sin fuente, no se explota; sin evidencia, no es un hallazgo.
- **Gobierno por [CONSTITUTION.md](CONSTITUTION.md)** y auditoría de coherencia previa al informe.
- **Capa de guardarraíles deterministas** (gate de alcance, validación del blackboard, anti-inyección en 16 agentes, detector de secretos, kill-switch de consumo, **validador del bus A2A** —emisor/destino conocidos + topología de pares + techo de hops— y **auditoría de subagentes**) mapeada a OWASP LLM Top 10 — ver [GUARDRAILS.md](GUARDRAILS.md).
- **Historial de versiones** en [CHANGELOG.md](CHANGELOG.md) (SemVer) y en las [releases](https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/releases).

## Referencia de comandos

Chuleta de todo lo ejecutable, por categoría. Salvo que se indique otra cosa, los comandos se lanzan
**desde la raíz del proyecto** (`data-attack/`).

### 🚀 Despliegue
| Comando | Qué hace |
| :--- | :--- |
| `sudo ./deploy/auto-deploy.sh` | Instala y verifica **todo** en una Kali desde cero (toolchain + Claude Code + RAG + bot). |
| `sudo ./deploy/auto-deploy.sh --update` | Lo mismo, actualizando todo a su última versión. |
| `./deploy/auto-deploy.sh --skip-tools` · `--no-rag` · `--no-bot` | Despliegue parcial (omite toolchain / RAG / bot). |
| `./deploy/setup.sh` | Asistente interactivo (menús): despliegue, `bot/.env`, `scope.json` y verificación. |

### ✅ Verificar y mantener
| Comando | Qué hace |
| :--- | :--- |
| `./deploy/verify.sh` | Tabla del entorno (✅/faltante); sale con error si falta algo crítico. |
| `./deploy/verify.sh --install` | Además instala lo que falte. |
| `./deploy/verify.sh --update` | Además actualiza el toolchain a lo último. |

### ▶️ Operar
| Comando | Qué hace |
| :--- | :--- |
| `cd bot && ./.venv/bin/python bot.py` | Arranca el **bot de Telegram** (control remoto). |
| `./deploy/dash.sh` | **Panel TUI de control total** (pestañas: A2A, agentes, presupuesto, RAG, evidencia, acciones). |
| `claude` → `/agents` | Abre la **CLI de Claude Code** y lista los 18 agentes. |

### 💰 Coste (agentsview · local)
| Comando | Qué hace |
| :--- | :--- |
| `./deploy/agentsview.sh up` | Dashboard de coste/actividad por agente en `127.0.0.1:8080`. |
| `./deploy/agentsview.sh usage` | Desglose de coste/uso en la terminal (acepta `--agent`, `--since`…). |
| `./deploy/agentsview.sh open` · `status` · `down` | Abrir en el navegador · ¿activo? · parar. |
| `./deploy/agentsview.sh install` | Instala/verifica el binario fijado (con SHA256). |

### 📚 RAG de vulnerabilidades
| Comando | Qué hace |
| :--- | :--- |
| `python rag/refresh.py` | Refresca la base (CISA KEV + EPSS + exploits + plantillas). |
| `python rag/refresh.py --epss-all` | Re-calcula los scores EPSS de todo (cambian a diario). |

### 🐳 Docker (alternativa al despliegue de host)
| Comando | Qué hace |
| :--- | :--- |
| `./deploy/docker.sh up` | Construye la imagen + puebla el RAG + levanta el bot. |
| `./deploy/docker.sh build` · `rag` | Solo construir la imagen · solo poblar el RAG. |
| `./deploy/docker.sh logs` · `status` · `down` | Seguir los logs del bot · estado · parar y eliminar. |
| `./deploy/docker.sh shell` | Shell interactiva dentro de la imagen. |

<details>
<summary><b>🧪 Desarrollo y validación (para contribuir al proyecto)</b></summary>

| Comando | Qué hace |
| :--- | :--- |
| `python tools/validate_suite.py` | Valida hooks, esquemas, agentes y la topología A2A. |
| `python tools/verify_opencode.py` | Verifica el espejo opencode (config + 18 agentes + cruce routing↔provider). |
| `python tools/sync_opencode.py` | Regenera el espejo `.opencode/agent/*.md` desde `.claude/agents/`. |
| `python tools/build_plugin.py` | Empaqueta el plugin de Claude Code (carpeta `plugin/`). |
| `python tools/build_agent_cards.py` | Regenera `contracts/agent-cards.json` (parejas A2A). |
| `python tools/analyze_engagement.py [id]` | Auditoría de coherencia previa al informe. |
| `python dryrun/run_dryrun.py` | Prueba end-to-end segura (ejercita los guardarraíles, sin atacar). |

</details>

## Estructura del repositorio

```
cyberseg-agents/
├── README.md · ARCHITECTURE.md · ARCHITECTURE_MAP.md · AGENTS.md · CONSTITUTION.md
├── contracts/      → blackboard: scope, engagement y esquemas de findings/targets
├── docs/           → referencias, protocolo de handoff, guía de informe, humanizer
│   └── assets/     → banner y guía de estilo visual
├── templates/      → plantilla de informe + brief del engagement
├── tools/          → análisis de coherencia + generador del mapa de arquitectura
├── rag/            → RAG de vulnerabilidades KEV+EPSS (SQLite)
├── bot/            → bot de Telegram (Claude Agent SDK) + clasificador de riesgo
├── deploy/         → auto-deploy y verificación del toolchain en Kali (+ Docker: Dockerfile/compose)
├── dryrun/         → prueba end-to-end segura (sin atacar)
├── .claude/        → settings, hooks (alcance, presupuesto, supervisión, blackboard, secretos, A2A, auditoría de subagentes) y los 18 subagentes
└── .opencode/      → espejo de los agentes para opencode
```

## Licencia

Software **propietario** — uso autorizado únicamente. Pentesting / bug bounty dentro del
alcance de un contrato firmado o un programa con scope explícito. Ver [LICENSE](LICENSE).

---

<p align="center">
  <img src="https://img.shields.io/badge/DataUnix-Data--Attack-FF6B35?style=for-the-badge&labelColor=0D1117" alt="DataUnix · Data Attack"><br>
  <sub>Suite de agentes ofensivos sobre Claude Code · uso autorizado</sub><br><br>
  <a href="https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools/stargazers"><b>⭐ Si te resulta útil, deja una estrella</b></a>
</p>
