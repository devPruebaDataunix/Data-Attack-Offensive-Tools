# Runbook del operador — Data Attack

> ⚠️ **Uso autorizado únicamente.** Nada se ejecuta fuera del alcance de `contracts/scope.json`.
> El hook `scope_guard.py` lo aplica de forma determinista en cada acción; el bot además pide
> aprobación humana por cada comando que toca el target. Operar fuera de scope es ilegal.

Guía de puesta en marcha de extremo a extremo en una **Kali nueva**, y primera prueba en vivo.

---

## 0. Prerrequisitos
- Kali nueva (VM E2 aislada, VLAN por cliente, kill-switch).
- Cuenta Claude **Pro** (el login es manual, lo haces tú).
- Token del bot de Telegram + tu `user-id` (allowlist). **Rota el token en BotFather (`/revoke`)**
  antes de operar en real: el actual se pegó en chat.

## 1. Clonar y desplegar
```bash
git clone https://github.com/devPruebaDataunix/Data-Attack-Offensive-Tools data-attack
cd data-attack
chmod +x deploy/*.sh
sudo ./deploy/auto-deploy.sh        # instala toolchain + Claude Code + RAG + venv del bot
```
`auto-deploy.sh` te pregunta `TELEGRAM_TOKEN` y `ALLOWED_USER_ID` y escribe `bot/.env`
(permisos 600, ignorado por git). Instala el **Claude Agent SDK** vía `bot/requirements.txt`.

> **Asistente guiado:** `./deploy/setup.sh` envuelve todo esto con
> [gum](https://github.com/charmbracelet/gum) (menú: despliegue, configurar `bot/.env`, definir
> `scope.json`, verificar, abrir el panel TUI). Degrada a prompts de texto si gum no está.

## 2. Login de Claude Code (Pro)
```bash
claude            # primer arranque → login interactivo (Pro)
```
El SDK del bot hereda esta sesión. Sin login, el bot cae al modo degradado `claude -p`.

## 3. Definir el alcance REAL (antes de nada)
```bash
cp contracts/scope.example.json contracts/scope.json
$EDITOR contracts/scope.json       # dominios / IPs / CIDR / URLs autorizados + autorización
```
`scope.json` está gitignored (datos de cliente). Sin él, el bot **pregunta** el scope en vez de
adivinar.

> **Test ciego.** Si haces una prueba para validar la autonomía de la suite, el `scope.json` **no
> debe filtrar la identidad del objetivo** (nombre de la máquina, plataforma, dificultad): usa un
> `engagement_id`/`client` neutros y pásale al Orquestador solo la **IP + el objetivo**. Los agentes
> solo conocen el `scope.json` y el encargo; cualquier pista ahí sesga el resultado.

## 4. Verificar antes de operar
```bash
bash deploy/verify.sh              # toolchain + versiones + auth + RAG
claude plugin validate ./plugin    # debe decir: ✔ Validation passed
python tools/validate_suite.py     # debe decir: 0 fallos
python bot/tests/test_intel.py     # 25/25 OK (clasificación / scope / gate)
python dryrun/run_dryrun.py        # cadena completa SIMULADA (sin atacar): scope+RAG+blackboard
```

## 5. Arrancar el bot
```bash
cd bot && ./.venv/bin/python bot.py
# o como servicio (recomendado en E2): ver §Troubleshooting > systemd
```
En Telegram: `/start`. Solo tu `user-id` responde; cualquier otro queda rechazado y logueado.

## 5b. Panel de control local (TUI)
Alternativa **local** al bot, con la MISMA lógica y las MISMAS puertas (scope_guard + aprobación
humana + C11-C13):
```bash
./deploy/dash.sh        # abre el panel Textual en la terminal de la Kali
```
Muestra estado/scope/salud, hallazgos clasificados en vivo (🔴 real / 🟠 vigilar / 🔇 ruido) y una
caja de orden al Orquestador; la aprobación por acción aparece como **modal**. `triage <producto>`
consulta el RAG. El bot de Telegram sigue para el control remoto.

## 6. Primera prueba en vivo (orden sugerido)
1. `/status` y `/health` → salud del sistema y versiones.
2. `/agents` → deben listarse 18.
3. `/scope` → confirma que muestra TU alcance real.
4. `/triage apache 2.4.49` → CVEs priorizados desde el RAG (KEV/MSF/CVSS).
5. **Lenguaje natural**: _"haz recon pasivo de <un dominio EN SCOPE>"_ → el bot pide confirmación
   (✅ Ejecutar) → al lanzar comandos ofensivos te manda **✅ Autorizar / ⛔ Denegar** por acción.
6. Observa los hitos en vivo y, si hay hallazgo confirmado, la alerta **🔴 EVIDENCIA REAL**.
7. `/findings` → resumen clasificado (🔴 real / 🟠 vigilar / 🔇 ruido).
8. _"genera el informe"_ → `reporting` (Opus 4.8) lo redacta; recógelo con `/report`.

## 7. Mantener el RAG al día (zero-days)
```bash
python rag/refresh.py --epss-all   # CISA KEV + EPSS (público)
# Programar a diario:
crontab -e   # → 0 6 * * *  cd /ruta/data-attack && python rag/refresh.py --epss-all
```

---

## Troubleshooting

**El bot no responde / "No autorizado".** Revisa `ALLOWED_USER_ID` en `bot/.env` (tu user-id real).
Logs en `bot/bot.log`.

**El SDK no encuentra `claude` (modo degradado o error).** Bajo systemd el PATH es mínimo. Fija la
ruta del binario:
```bash
echo "CLAUDE_CLI_PATH=$(command -v claude)" >> bot/.env
```
(el runner ya autodetecta `claude` en PATH; esto lo fuerza para servicios).

**Bot como servicio systemd** (`/etc/systemd/system/data-attack-bot.service`):
```ini
[Service]
WorkingDirectory=/ruta/data-attack/bot
ExecStart=/ruta/data-attack/bot/.venv/bin/python bot.py
EnvironmentFile=/ruta/data-attack/bot/.env
Environment=PATH=/usr/local/bin:/usr/bin:/bin
Restart=on-failure
```
`systemctl daemon-reload && systemctl enable --now data-attack-bot`.

**Un modelo da error.** El routing usa IDs completos: `claude-haiku-4-5`, `claude-sonnet-4-6`,
`claude-opus-4-8`. Si tu plan no sirve alguno, ajusta el `model:` del agente o `ORCH_MODEL` en
`bot/.env`. Recuerda: **`effort` no es válido en Haiku** (osint-recon no lo lleva).

**claude-mem.** Desactivado a propósito (su worker no arranca en Windows). No es necesario para
operar; el contexto del proyecto vive en la memoria del asistente, no en claude-mem.

**Sospecha de fuera de scope.** El `scope_guard` bloquea y explica; si una orden menciona un target
nuevo, el bot pregunta antes de tocar nada. Nunca improvises alcance.

---

## Recordatorios de seguridad
- **Doble barrera** sobre el target: aprobación humana por acción (Telegram) **+** hook de scope.
- Secretos solo en `bot/.env` (nunca en el repo). Datos de cliente solo en E2/E3.
- Exfiltración siempre **simulada** (canary), nunca datos reales (`c2-exfil`).
- Al cerrar: `reporting` genera el informe y `knowledge-postmortem` extrae lecciones a memoria.
