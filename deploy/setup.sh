#!/usr/bin/env bash
# =============================================================================
#  deploy/setup.sh — Asistente interactivo de despliegue y configuración.
#  ENVUELVE lo que ya existe (auto-deploy.sh / verify.sh / bot.env / scope.json)
#  con gum; si gum no está, degrada a prompts de texto plano. No reescribe nada.
#    ./deploy/setup.sh
# =============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=deploy/banner.sh
. "${SCRIPT_DIR}/banner.sh"
# shellcheck source=deploy/lib.sh
. "${SCRIPT_DIR}/lib.sh"

HAVE_GUM=0
if command -v gum >/dev/null 2>&1; then HAVE_GUM=1
else ensure_gum >/dev/null 2>&1 && command -v gum >/dev/null 2>&1 && HAVE_GUM=1; fi

note() { printf '\n  \e[1;38;2;0;212;255m%s\e[0m\n' "$*"; }
warnp(){ printf '  \e[38;2;255;68;68m%s\e[0m\n' "$*"; }

ask()        { if [ "$HAVE_GUM" = 1 ]; then gum input --placeholder "$1" --value "${2:-}"
               else local a; read -rp "  $1: " a; echo "${a:-${2:-}}"; fi; }
ask_secret() { if [ "$HAVE_GUM" = 1 ]; then gum input --password --placeholder "$1"
               else local a; read -rsp "  $1: " a; echo >&2; echo "$a"; fi; }
confirm()    { if [ "$HAVE_GUM" = 1 ]; then gum confirm "$1"
               else local a; read -rp "  $1 [s/N]: " a; [[ "$a" =~ ^[sSyY] ]]; fi; }
choose()     { if [ "$HAVE_GUM" = 1 ]; then gum choose "$@"
               else local i=1 o; for o in "$@"; do printf '   %d) %s\n' "$i" "$o" >&2; i=$((i+1)); done
                    local n; read -rp "  Opción: " n; echo "${@:${n:-0}:1}"; fi; }

setup_env() {
  local env="${REPO_DIR}/bot/.env"
  if [ -f "$env" ] && ! confirm "Ya existe bot/.env. ¿Sobrescribir?"; then note "Conservado."; return; fi
  local tok uid
  tok=$(ask_secret "TELEGRAM_TOKEN (de BotFather)")
  uid=$(ask "ALLOWED_USER_ID (varios separados por coma)")
  [ -z "$tok" ] && { warnp "Token vacío; cancelo."; return; }
  umask 077
  { echo "TELEGRAM_TOKEN=${tok}"; echo "ALLOWED_USER_ID=${uid}"; echo "REPO_DIR=${REPO_DIR}"; } > "$env"
  note "bot/.env escrito (permisos 600, ignorado por git)."
}

setup_scope() {
  local sc="${REPO_DIR}/contracts/scope.json" ex="${REPO_DIR}/contracts/scope.example.json"
  if [ -f "$sc" ] && ! confirm "Ya existe scope.json. ¿Sobrescribir?"; then note "Conservado."; return; fi
  local client doms ips cidrs urls
  client=$(ask "Cliente / referencia de autorización")
  doms=$(ask  "Dominios en scope (coma)")
  ips=$(ask   "IPs en scope (coma)")
  cidrs=$(ask "CIDRs en scope (coma)")
  urls=$(ask  "URLs en scope (coma)")
  python3 - "$ex" "$sc" "$client" "$doms" "$ips" "$cidrs" "$urls" <<'PY'
import json, sys
ex, sc, client, doms, ips, cidrs, urls = sys.argv[1:8]
lst = lambda s: [x.strip() for x in s.split(",") if x.strip()]
try:
    data = json.load(open(ex, encoding="utf-8"))
except Exception:
    data = {"authorization": {}, "constraints": {}}
data["client"] = client or data.get("client", "")
data.setdefault("authorization", {})["reference"] = client or data.get("authorization", {}).get("reference", "")
data["in_scope"] = {"domains": lst(doms), "ips": lst(ips), "cidrs": lst(cidrs), "urls": lst(urls)}
data["out_of_scope"] = {"domains": [], "ips": [], "notes": ""}
open(sc, "w", encoding="utf-8").write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
print("ok")
PY
  note "contracts/scope.json escrito. REVÍSALO (fechas de autorización, out_of_scope) antes de operar."
}

# ── Montaje COMPLETO automático (todo el entorno, con manejo de errores) ───────
# Orquesta el despliegue de punta a punta SIN detener el asistente ante un fallo: cada paso reporta y
# se cuentan incidencias para un resumen final. El auto-deploy ya pide el token del bot, TODAS las
# claves de modelos free (configure_opencode_keys) y ofrece el perfil opencode; aquí añadimos el
# alcance y la verificación final. Idempotente: re-ejecutar corrige lo que falló.
full_mount() {
  note "Montaje COMPLETO automático — entorno listo de principio a fin (con manejo de errores)."
  local fails=0
  note "1/3 · Desplegando (te pedirá el token del bot, TODAS las claves de modelos free y el perfil opencode)…"
  if sudo "${SCRIPT_DIR}/auto-deploy.sh"; then note "Despliegue OK."
  else warnp "El despliegue terminó con incidencias — revisa el log (deploy/deploy-*.log)."; fails=$((fails + 1)); fi
  if confirm "2/3 · ¿Definir el alcance (scope.json) ahora?"; then setup_scope; fi
  note "3/3 · Verificación final del entorno…"
  if bash "${SCRIPT_DIR}/verify.sh"; then note "Verificación: sin fallos críticos."
  else warnp "La verificación reporta faltantes (revisa la tabla de arriba)."; fails=$((fails + 1)); fi
  if [ "$fails" -eq 0 ]; then note "✔ Entorno COMPLETO montado sin incidencias. Arranca el bot o el panel (TUI)."
  else warnp "Terminado con ${fails} incidencia(s) — el asistente NO se detuvo; corrige lo señalado y re-ejecuta (es idempotente)."; fi
}

# ── Menú ──────────────────────────────────────────────────────────────────────
da_banner
[ "$HAVE_GUM" = 1 ] || warnp "gum no disponible: uso prompts de texto plano."
note "Asistente de Data Attack — ¿qué quieres hacer?"
action=$(choose \
  "Montaje COMPLETO automático (todo el entorno)" \
  "Despliegue completo (auto-deploy)" \
  "Desplegar en contenedores (Docker)" \
  "Configurar bot (.env)" \
  "Configurar claves de modelos free (opencode)" \
  "Definir alcance (scope.json)" \
  "Verificar entorno" \
  "Abrir panel de control (TUI)" \
  "Analítica de coste/actividad (agentsview)" \
  "Salir")

case "$action" in
  "Montaje COMPLETO"*)           full_mount ;;
  "Despliegue completo"*)        exec sudo "${SCRIPT_DIR}/auto-deploy.sh" ;;
  "Desplegar en contenedores"*)  exec bash "${SCRIPT_DIR}/docker.sh" up ;;
  "Configurar bot"*)             setup_env ;;
  "Configurar claves de modelos"*) configure_opencode_keys ;;
  "Definir alcance"*)            setup_scope ;;
  "Verificar entorno"*)          bash "${SCRIPT_DIR}/verify.sh" ;;
  "Abrir panel de control"*)     exec bash "${SCRIPT_DIR}/dash.sh" ;;
  "Analítica de coste"*)         exec bash "${SCRIPT_DIR}/agentsview.sh" up ;;
  *)                             note "Hasta luego."; exit 0 ;;
esac
