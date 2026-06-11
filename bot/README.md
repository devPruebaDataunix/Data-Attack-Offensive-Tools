# Bot de Telegram — control remoto del entorno

Mando a distancia + dashboard de intel del framework de agentes, sobre la VM E2.

## Seguridad (diseño)
- **Allowlist dura de user-id** (`ALLOWED_USER_ID`): cualquier otro queda rechazado y logueado.
- **Secretos fuera del repo**: token y user-id en `bot/.env` (ignorado por git, permisos 600).
- **Intel local y segura**: `/triage`, `/cve`, `/status`, `/health`, `/findings`, `/report` no
  generan tráfico ofensivo — leen el RAG/estado local.
- **Órdenes al Orquestador con confirmación** (botón inline) y permisos por defecto: las acciones
  que tocan el target **se supervisan en terminal/GUI** (donde la aprobación por acción funciona),
  no se auto-ejecutan a ciegas desde el chat.
- **Audit log** en `bot/bot.log`.

> Rota el token en BotFather (`/revoke`) si alguna vez se expone.

## Comandos
| Comando | Qué hace |
| :--- | :--- |
| `/status` `/health` | salud del sistema + versiones del toolchain (corre `deploy/verify.sh`) |
| `/agents` | lista los agentes cargados |
| `/triage <producto> [versión]` | CVEs priorizados (KEV/exploit/MSF/CVSS) desde el RAG |
| `/cve <CVE-id>` | detalle de un CVE |
| `/refresh` | actualiza el RAG en segundo plano |
| `/findings` | resumen de hallazgos del engagement |
| `/report` | envía el último informe |
| `/scope` | muestra el alcance actual |
| _texto libre_ | orden al Orquestador (pide confirmación) |

## Ejecutar
```bash
cd bot
./.venv/bin/python bot.py          # el auto-deploy crea el venv y el .env
# o como servicio systemd (ver DEPLOY.md)
```

## Ampliación (Agent SDK)
Para **aprobación por acción desde Telegram** (botones Approve/Deny en cada comando que toca el
target), migra el puente de `claude -p` (subprocess) al **Claude Agent SDK** de Python con un
callback `can_use_tool` que reenvíe la decisión al chat. Estructura ya preparada en `on_button`.
