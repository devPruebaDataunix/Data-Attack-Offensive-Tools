#!/usr/bin/env bash
# =============================================================================
#  Data Attack — Offensive Tools :: auto-deploy
#  Despliega TODO el entorno (E2) en una Kali nueva desde 0.
#  Idempotente y re-ejecutable. Verifica el sistema y las herramientas
#  (con sus últimas versiones) antes y después.
#
#  Uso:
#    sudo ./deploy/auto-deploy.sh                 # despliegue completo
#    sudo ./deploy/auto-deploy.sh --update        # actualiza todo a lo último
#    ./deploy/auto-deploy.sh --skip-tools         # sin toolchain ofensivo
#    ./deploy/auto-deploy.sh --no-bot --no-rag    # solo base + claude
#    ./deploy/auto-deploy.sh -h
# =============================================================================
set -Eeuo pipefail

# ── Rutas ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG="${SCRIPT_DIR}/deploy-$(date +%Y%m%d-%H%M%S).log"

# Banner de la herramienta (helper compartido; degrada a texto plano sin TTY).
# shellcheck source=deploy/banner.sh
. "${SCRIPT_DIR}/banner.sh" 2>/dev/null || true

# ── Flags ────────────────────────────────────────────────────────────────────
DO_TOOLS=1; DO_RAG=1; DO_BOT=1; UPDATE=0
for a in "$@"; do case "$a" in
  --skip-tools) DO_TOOLS=0 ;;
  --no-rag)     DO_RAG=0 ;;
  --no-bot)     DO_BOT=0 ;;
  --update)     UPDATE=1 ;;
  -h|--help)    grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "Flag desconocido: $a"; exit 2 ;;
esac; done

# ── Log + colores ────────────────────────────────────────────────────────────
exec > >(tee -a "$LOG") 2>&1
c(){ tput setaf "$1" 2>/dev/null || true; }; r(){ tput sgr0 2>/dev/null || true; }
info(){ echo -e "$(c 4)[*]$(r) $*"; }
ok(){   echo -e "$(c 2)[OK]$(r) $*"; }
warn(){ echo -e "$(c 3)[!]$(r) $*"; }
err(){  echo -e "$(c 1)[ERR]$(r) $*" >&2; }
step(){ echo; echo -e "$(c 6)══════ $* ══════$(r)"; }
trap 'err "Fallo en la línea $LINENO. Revisa el log: $LOG"' ERR

SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
have(){ command -v "$1" >/dev/null 2>&1; }
# Reintenta apt ante el lock del auto-update de primer arranque o mirrors intermitentes.
apt_retry(){
  local n=0
  until $SUDO apt-get "$@"; do
    n=$((n+1)); [ "$n" -ge 6 ] && { err "apt falló tras 6 intentos: apt-get $*"; return 1; }
    warn "apt ocupado/falló (intento $n/6); reintento en 15s…"; sleep 15
  done
}

# =============================================================================
# 0) PREFLIGHT — corroboración del sistema antes de tocar nada
# =============================================================================
preflight(){
  step "0/6  Preflight — verificación del sistema"
  # SO Debian/Kali
  if [ -r /etc/os-release ]; then . /etc/os-release; fi
  if [[ "${ID:-}" != "kali" && "${ID_LIKE:-}" != *debian* ]]; then
    err "Este instalador es para Kali/Debian. Detectado: ${PRETTY_NAME:-desconocido}"; exit 1
  fi
  ok "SO: ${PRETTY_NAME:-Debian-like}"
  # sudo
  if [ -n "$SUDO" ] && ! sudo -v; then err "Se necesita sudo."; exit 1; fi
  ok "Privilegios: $([ -n "$SUDO" ] && echo 'sudo' || echo 'root')"
  # internet
  if ! curl -fsS --max-time 10 https://github.com >/dev/null; then
    err "Sin conectividad a internet (github.com)."; exit 1; fi
  ok "Conectividad: OK"
  # disco y RAM
  local free_gb ram_gb
  free_gb=$(df -BG --output=avail "$REPO_DIR" | tail -1 | tr -dc '0-9')
  ram_gb=$(awk '/MemTotal/{printf "%d", $2/1024/1024}' /proc/meminfo)
  [ "${free_gb:-0}" -ge 15 ] && ok "Disco libre: ${free_gb}GB" || warn "Disco libre bajo: ${free_gb}GB (recomendado ≥15GB)"
  [ "${ram_gb:-0}" -ge 4 ]   && ok "RAM: ${ram_gb}GB" || warn "RAM baja: ${ram_gb}GB (recomendado ≥4GB)"
  ok "Preflight superado."
}

# =============================================================================
# 1) BASE — dependencias del sistema
# =============================================================================
install_base(){
  step "1/6  Dependencias base"
  # El keyring de Kali caduca y deja los repos sin firmar -> 'paquete no localizable'. Refréscalo.
  $SUDO apt-get install -y --reinstall kali-archive-keyring >/dev/null 2>&1 || true
  apt_retry update -y
  apt_retry install -y --no-install-recommends \
    git curl wget jq ca-certificates gnupg build-essential \
    python3 python3-pip python3-venv pipx python-is-python3 \
    golang-go dnsutils
  pipx ensurepath >/dev/null 2>&1 || true
  # Node.js (≥18) para Claude Code. Prefiere el de Kali; NodeSource solo si hace falta
  # (instalar nodejs de NodeSource sobre el libnode de Kali suele dar 'dpkg: error processing').
  node_major(){ node -v 2>/dev/null | tr -dc '0-9.' | cut -d. -f1; }
  if ! have node || [ "$(node_major)" -lt 18 ]; then
    info "Node <18 o ausente; intento con el nodejs de Kali…"
    apt_retry install -y nodejs npm || true
  fi
  if ! have node || [ "$(node_major)" -lt 18 ]; then
    info "El nodejs de Kali no sirve; instalando Node LTS (NodeSource)…"
    curl -fsSL https://deb.nodesource.com/setup_lts.x | $SUDO -E bash - \
      || warn "NodeSource setup falló (revisa conectividad)."
    apt_retry install -y nodejs || warn "Instalación de Node falló; instálalo a mano (ver DEPLOY.md)."
  fi
  ok "Base lista — node $(node -v 2>/dev/null), python3 $(python3 -V 2>&1 | awk '{print $2}'), go $(go version 2>/dev/null | awk '{print $3}')"
}

# =============================================================================
# 2) CLAUDE CODE — CLI (+ aviso de login Pro)
# =============================================================================
install_claude(){
  step "2/6  Claude Code CLI"
  if have claude && [ "$UPDATE" -eq 0 ]; then
    ok "claude ya instalado ($(claude --version 2>/dev/null))"
  else
    $SUDO npm install -g @anthropic-ai/claude-code \
      || warn "npm install de claude-code falló (¿red?). Reintenta luego: sudo npm install -g @anthropic-ai/claude-code"
    # El bin global de npm puede no estar en el PATH de ESTA shell tras instalar, y bash
    # cachea las rutas de comandos -> 'claude' parecía no instalado y daba falsos [ERR] en
    # los pasos 2 y 6. Añadimos el bin global al PATH (persiste al resto de fases y al verify) + rehash.
    export PATH="$(npm prefix -g 2>/dev/null)/bin:$PATH"; hash -r 2>/dev/null || true
    local _v; _v="$(claude --version 2>/dev/null || true)"
    ok "Instalado: ${_v:-claude (se resolverá en shell nueva; el verify final lo confirma)}"
  fi
  warn "LOGIN PRO (manual, una vez): ejecuta 'claude' y completa el login con tu cuenta Pro."
  warn "El bot usa el Agent SDK / 'claude -p', que requiere esa sesión iniciada en esta máquina."
}

# =============================================================================
# 3) TOOLCHAIN OFENSIVO — últimas versiones
# =============================================================================
install_tools(){
  step "3/6  Toolchain ofensivo"
  info "Paquetes de los repos de Kali…"
  $SUDO apt-get install -y \
    nmap sqlmap metasploit-framework ffuf feroxbuster seclists \
    netexec gobuster john hashcat amass || warn "Algún paquete apt no estaba disponible (revisar)."

  # ProjectDiscovery via pdtm (subfinder, httpx, nuclei, naabu, katana, dnsx…)
  export PATH="$PATH:$(go env GOPATH)/bin"
  # `go install` resuelve por proxy.golang.org/sum.golang.org; si la VM no los resuelve por DNS,
  # caemos a 'direct' (clona de github, cuyo DNS sí resuelve) y desactivamos la checksum DB.
  # El '|direct' ya reintenta solo; el segundo intento explícito es cinturón y tirantes. NO fatal.
  export GOPROXY="${GOPROXY:-https://proxy.golang.org|direct}" GOSUMDB="${GOSUMDB:-off}"
  if ! have pdtm; then
    info "Instalando pdtm (ProjectDiscovery Tool Manager)…"
    go install github.com/projectdiscovery/pdtm/cmd/pdtm@latest \
      || GOPROXY=direct go install github.com/projectdiscovery/pdtm/cmd/pdtm@latest \
      || warn "pdtm no se pudo instalar (¿DNS/red?): faltarán subfinder/httpx/nuclei/naabu/katana/dnsx. Reintenta: GOPROXY=direct GOSUMDB=off go install github.com/projectdiscovery/pdtm/cmd/pdtm@latest"
  fi
  # pdtm NO tiene -silent (daba "flag provided but not defined"); los flags quietos son
  # -duc (no comprobar updates de pdtm) y -nc (sin color, mejor para el log).
  if [ "$UPDATE" -eq 1 ]; then pdtm -ua -duc -nc || true; else pdtm -ia -duc -nc || true; fi
  have nuclei && { info "Actualizando plantillas de Nuclei…"; nuclei -update-templates -silent || true; }

  # gau
  have gau || go install github.com/lc/gau/v2/cmd/gau@latest || true

  # Impacket (pipx)
  if ! have secretsdump.py; then info "Instalando Impacket…"; pipx install impacket || true; fi
  [ "$UPDATE" -eq 1 ] && pipx upgrade-all >/dev/null 2>&1 || true

  # BloodHound.py collector (la GUI CE es opcional vía Docker, ver DEPLOY.md)
  have bloodhound-python || pipx install bloodhound || true

  # Sliver C2 (script oficial)
  if ! have sliver-server; then
    info "Instalando Sliver C2 (script oficial)…"
    curl -fsSL https://sliver.sh/install | $SUDO bash || warn "Instalación de Sliver falló; instálalo manualmente (ver DEPLOY.md)."
  fi
  ok "Toolchain instalado."
}

# =============================================================================
# 4) RAG — poblar el store de vulnerabilidades
# =============================================================================
setup_rag(){
  step "4/6  RAG de vulnerabilidades"
  cd "$REPO_DIR"
  if python3 rag/refresh.py --epss-all; then
    ok "RAG poblado."
  else
    warn "El RAG no se pudo poblar (¿red? CISA KEV/EPSS). Reintenta luego: python3 rag/refresh.py --epss-all"
  fi
}

# =============================================================================
# 5) BOT de Telegram — venv + config
# =============================================================================
setup_bot(){
  step "5/6  Bot de Telegram"
  cd "$REPO_DIR/bot"
  python3 -m venv .venv || warn "No pude crear bot/.venv (¿falta python3-venv?)."
  ./.venv/bin/pip install --quiet --upgrade pip 2>/dev/null || true
  ./.venv/bin/pip install --quiet -r requirements.txt \
    || warn "Dependencias del bot (textual/SDK/telegram) no instaladas del todo (¿red/PyPI?). Reintenta: bot/.venv/bin/pip install -r bot/requirements.txt"
  if [ ! -f .env ]; then
    info "Configuración del bot (no se guarda en el repo)."
    read -rp "  TELEGRAM_TOKEN: " _tok
    read -rp "  ALLOWED_USER_ID: " _uid
    umask 077
    { echo "TELEGRAM_TOKEN=${_tok}"; echo "ALLOWED_USER_ID=${_uid}"; echo "REPO_DIR=${REPO_DIR}"; } > .env
    ok "bot/.env creado (permisos 600, ignorado por git)."
  else
    ok "bot/.env ya existe — se conserva."
  fi
}

# =============================================================================
# 6) VERIFY — corroboración final
# =============================================================================
run_verify(){
  step "6/6  Verificación final"
  bash "${SCRIPT_DIR}/verify.sh" \
    || warn "La verificación reporta faltantes (revisa la tabla de arriba). El despliegue ha CONTINUADO; instala/repara lo señalado y re-ejecuta este script (es idempotente)."
}

# ── Orquestación ─────────────────────────────────────────────────────────────
main(){
  info "Log: $LOG"
  command -v da_banner >/dev/null 2>&1 && da_banner || true
  # Restablece el bit +x de los scripts (se pierde al clonar/copiar desde Windows o un zip).
  chmod +x "${SCRIPT_DIR}"/*.sh 2>/dev/null || true
  preflight
  install_base
  install_claude
  # if/then/else (no 'A && B || C'): así un fallo dentro de la función NO se enmascara
  # como "omitido" y aborta con la línea real (set -e activo dentro de la función).
  if [ "$DO_TOOLS" -eq 1 ]; then install_tools; else warn "Toolchain omitido (--skip-tools)."; fi
  if [ "$DO_RAG"   -eq 1 ]; then setup_rag;      else warn "RAG omitido (--no-rag)."; fi
  if [ "$DO_BOT"   -eq 1 ]; then setup_bot;      else warn "Bot omitido (--no-bot)."; fi
  run_verify
  step "✔ Despliegue completado"
  ok "Arranca el bot:  cd bot && ./.venv/bin/python bot.py"
  ok "O usa la CLI:    claude   (y escribe /agents)"
  ok "Asistente:       ./deploy/setup.sh   (configuración guiada)"
  ok "Panel TUI:       ./deploy/dash.sh    (control local en terminal)"
  ok "Contenedores:    ./deploy/docker.sh up   (despliegue en Docker — alternativa al de host)"
}
main
