# Despliegue en Kali (E2) — de 0 a operativo

Guía para montar el entorno completo en una **Kali nueva desde cero** (rolling, amd64).

## TL;DR
```bash
git clone <URL-de-tu-repo-privado> data-attack && cd data-attack
chmod +x deploy/*.sh
sudo ./deploy/auto-deploy.sh
claude            # haz el login Pro (una vez)
cd bot && ./.venv/bin/python bot.py
```

## Qué hace `auto-deploy.sh` (idempotente, re-ejecutable)
| Fase | Acción |
| :--- | :--- |
| 0 Preflight | comprueba Kali/Debian, sudo, internet, disco ≥15GB, RAM ≥4GB |
| 1 Base | git, curl, jq, python3+pipx+`python-is-python3`, golang, **Node LTS** (NodeSource) |
| 2 Claude | `@anthropic-ai/claude-code` (npm) + aviso de login Pro |
| 3 Toolchain | apt (nmap, sqlmap, metasploit, ffuf, feroxbuster, seclists, **netexec**, gobuster, john, hashcat, amass) · **pdtm** (subfinder, httpx, nuclei, naabu, katana, dnsx) · impacket · bloodhound.py · **Sliver** |
| 4 RAG | `rag/refresh.py --epss-all` (KEV+CVE5+ExploitDB+MSF+Nuclei+EPSS) |
| 5 Bot | venv + dependencias + crea `bot/.env` (te pregunta token y user-id) |
| 6 Verify | `deploy/verify.sh` — presencia + versión de cada herramienta, validadores, RAG, auth |

Flags: `--update` (todo a lo último), `--skip-tools`, `--no-rag`, `--no-bot`.

## Últimas versiones
- Kali rolling → `apt update` trae lo último del repo.
- ProjectDiscovery → `pdtm -ua`; plantillas Nuclei → `nuclei -update-templates`.
- pipx → `pipx upgrade-all`; Sliver → re-ejecutar el script.
- `./deploy/auto-deploy.sh --update` hace todo eso de una vez.

## Verificación
```bash
./deploy/verify.sh     # tabla OK/faltante + versiones; sale !=0 si falta algo crítico
```

## Login de Claude (manual, una vez)
El login Pro es interactivo. Ejecuta `claude`, completa el OAuth, y ya queda la sesión en la VM
(la usan tanto la CLI como el bot vía `claude -p`).

> Nota de coste: desde el 15-jun-2026, `claude -p`/Agent SDK en planes de suscripción consumen de
> un crédito mensual de Agent SDK separado del uso interactivo.

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
