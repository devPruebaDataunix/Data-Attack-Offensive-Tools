# Bot de Telegram — control remoto inteligente del entorno

Mando a distancia + dashboard de intel del framework de agentes, sobre la VM E2. Habla en
**lenguaje natural**; el bot interpreta, te pide confirmación, **resume en vivo** lo que hace y
solo te escala **lo que es alerta real**.

## Motor
Sobre el **Claude Agent SDK** (`claude-agent-sdk`) — `bot/intel/runner.py`. Da streaming (hitos
en tiempo real), `can_use_tool` (aprobación por acción) y hooks. Si el SDK no está instalado, el
bot cae a `claude -p` (modo degradado, sin streaming) automáticamente.

## Lo que lo hace inteligente
1. **Lenguaje humano → acción.** Escribe _"haz recon pasivo de app.cliente.com"_ o _"prioriza
   los CVE de ese Apache y dime cuáles tienen exploit"_. El texto va al Orquestador, que delega
   en los subagentes. (`bot/intel/runner.py`)
2. **Pregunta el scope si falta.** Si no hay `contracts/scope.json`, o la orden menciona un
   objetivo fuera del alcance actual, el bot **pregunta** en vez de fallar o adivinar. Tu
   respuesta se incorpora como contexto. (`bot/intel/scope.py`)
3. **Resúmenes en vivo por hito.** Mientras trabaja te empuja qué subagente arranca, qué fase y
   el resultado — no logs crudos. (streaming del SDK)
4. **Alerta real vs ruido.** Clasifica cada finding del blackboard: `confirmed`/`exploited` →
   🔴 **EVIDENCIA REAL** con resumen claro para humano; candidato con respaldo fuerte
   (exploit/MSF/KEV) → 🟠 vigilar; hit de escáner sin respaldo o falso positivo → 🔇 se cuenta y
   se calla. Solo lo real dispara alerta. (`bot/intel/classify.py`)
5. **Aprobación por acción, configurable** (`approval_mode`: `full`/`critical`/`auto`, def.
   `critical` — ver CONSTITUTION §2). Cada comando se clasifica en un tier (`bot/intel/risk.py`).
   En **`full`** (máxima supervisión): el recon pasivo (subfinder/amass/whois…) se auto-aprueba; el
   escaneo/explotación (nmap, nuclei, sqlmap…) y lo destructivo (netexec, secretsdump, mimikatz…) te
   mandan **✅ Autorizar / ⛔ Denegar**; el **C2/implantes** (sliver…) exige **doble confirmación**.
   En **`critical`** (def.) solo el C2/implantes pide aprobación; en **`auto`**, nada. Timeout →
   denegado. Las puertas deterministas (`scope_guard`, `budget_guard`) siguen aplicando **en todos
   los modos**.

## Seguridad (diseño)
- **Allowlist dura de user-id** (`ALLOWED_USER_ID`): cualquier otro queda rechazado y logueado.
- **Secretos fuera del repo**: token y user-id en `bot/.env` (ignorado por git, permisos 600).
- **Intel local y segura**: `/triage`, `/cve`, `/status`, `/health`, `/findings`, `/report`,
  `/scope` no generan tráfico ofensivo — leen el RAG/estado local.
- **Doble gate sobre el target**: aprobación humana por acción (Telegram) **+** hook de scope
  determinista. Nada que toque el objetivo se auto-ejecuta a ciegas.
- **Audit log** en `bot/bot.log`.

> Rota el token en BotFather (`/revoke`) si alguna vez se expone.

## Comandos
| Comando | Qué hace |
| :--- | :--- |
| `/status` `/health` | tarjeta de **salud** estructurada (✓/⚠ por componente: motor · engagement · scope · Orquestador · agentes · ambos RAG) + orden en curso |
| `/status full` | chequeo **profundo** del toolchain del host (`deploy/verify.sh`) |
| `/agents` `/agent <n>` | roster por zonas E1/E2/E3 · ficha de un agente |
| `/network` `/hosts` · `/pivots` · `/creds` | frontera multi-host: hosts · túneles de pivoting · credenciales (**siempre referenciadas**) |
| `/a2a` · `/a2a <id>` | bus de mensajes entre agentes (resumen + últimos) · detalle de un mensaje |
| `/evidence` | artefactos y trazas por engagement (evidencia del activo + engagements con carpeta) |
| `/triage <producto> [versión]` | CVEs priorizados (KEV/exploit/MSF/CVSS) desde el RAG |
| `/cve <CVE-id>` | detalle de un CVE |
| `/kb` · `/kb <consulta>` | RAG de **conocimiento**: cobertura (Capa 1+2) · busca técnicas accionables (GTFOBins/LOLBAS/ATT&CK/Atomic) |
| `/refresh` | actualiza el RAG en segundo plano |
| `/findings` | hallazgos **clasificados** (🔴 real / 🟠 vigilar / 🔇 ruido) |
| `/report` | envía el último informe |
| `/scope` | muestra el alcance actual |
| `/lab <ip\|cidr\|dominio> [modo]` | arranca un lab: fija el scope **validado** + lanza (rechaza CIDR amplio, fuerza el no-daño; confirma antes de mutar) |
| `/mode` · `/model` · `/effort` | consulta/cambia supervisión (full/critical/auto), modelo y effort del Orquestador (efectivo en la próxima orden) |
| _texto libre_ | orden en lenguaje natural al Orquestador (pregunta scope si falta → confirma → ejecuta con streaming) |

## Ejecutar
```bash
cd bot
./.venv/bin/python bot.py          # el auto-deploy crea el venv, instala deps y el .env
# o como servicio systemd (ver DEPLOY.md)
```

## Notas operativas
- **Una orden a la vez** por chat (las órdenes nuevas esperan a que termine la actual).
- Para añadir objetivos a `scope.json` de forma persistente, pídeselo explícitamente al
  Orquestador (lo escribe él, y el hook lo recoge en la siguiente acción).
- `ORCH_MODEL` en `.env` fuerza el modelo del Orquestador del bot (por defecto, el del proyecto).
