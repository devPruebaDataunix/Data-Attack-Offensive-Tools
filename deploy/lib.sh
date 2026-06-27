#!/usr/bin/env bash
# =============================================================================
#  deploy/lib.sh — helpers de instalación/actualización del toolchain.
#  Lo carga verify.sh (--install / --update). Pensado para Kali/Debian, como root o con sudo.
#  Sin 'set -e' aquí: quien hace `source` decide su propia política de errores; estas funciones
#  son tolerantes (un componente que falle no debe abortar al resto).
# =============================================================================

SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
have(){ command -v "$1" >/dev/null 2>&1; }

# Reintenta apt ante el lock del auto-update de primer arranque o mirrors intermitentes.
apt_retry(){
  local n=0
  until $SUDO apt-get "$@"; do
    n=$((n+1)); [ "$n" -ge 6 ] && { echo "[ERR] apt falló tras 6 intentos: apt-get $*"; return 1; }
    echo "[!] apt ocupado/falló (intento $n/6); reintento en 15s…"; sleep 15
  done
}

gobin(){ echo "$(go env GOPATH 2>/dev/null)/bin"; }

# Go: instala SOLO golang-go. OJO: golang-go y gccgo-go ENTRAN EN CONFLICTO si se piden juntos
# (fue el fallo real al desplegar). Si apt no lo sirve, cae al binario oficial de go.dev.
ensure_go(){
  have go && return 0
  echo "[*] Instalando Go (golang-go)…"
  apt_retry install -y golang-go && have go && return 0
  echo "[!] golang-go no disponible vía apt; instalando el binario oficial de go.dev…"
  local ver tgz
  ver="$(curl -fsSL 'https://go.dev/VERSION?m=text' 2>/dev/null | head -1)"
  [ -z "$ver" ] && ver="go1.26.0"
  tgz="${ver}.linux-amd64.tar.gz"
  ( cd /tmp && curl -fsSLO "https://go.dev/dl/${tgz}" \
    && $SUDO rm -rf /usr/local/go && $SUDO tar -C /usr/local -xzf "$tgz" ) || return 1
  export PATH="$PATH:/usr/local/go/bin"
  grep -q '/usr/local/go/bin' "$HOME/.bashrc" 2>/dev/null \
    || echo 'export PATH="$PATH:/usr/local/go/bin"' >> "$HOME/.bashrc"
  have go
}

# ProjectDiscovery: pdtm + sus tools (subfinder/httpx/naabu/katana/dnsx…), binarios prebuilt.
# `go install` puede fallar si la VM no resuelve proxy.golang.org/sum.golang.org por DNS: forzamos el
# fallback a 'direct' (clona de github, cuyo DNS sí resuelve) y desactivamos la checksum DB. NO fatal.
ensure_pd(){
  ensure_go || { echo "[ERR] sin Go no se pueden instalar las PD tools."; return 1; }
  export PATH="$PATH:$(gobin)"
  export GOPROXY="${GOPROXY:-https://proxy.golang.org|direct}" GOSUMDB="${GOSUMDB:-off}"
  if ! have pdtm; then
    go install github.com/projectdiscovery/pdtm/cmd/pdtm@latest 2>/dev/null \
      || GOPROXY=direct go install github.com/projectdiscovery/pdtm/cmd/pdtm@latest 2>/dev/null \
      || echo "[!] pdtm NO instalado (¿DNS/red?): faltarán subfinder/httpx/nuclei/naabu/katana/dnsx." \
              "Manual: GOPROXY=direct GOSUMDB=off go install github.com/projectdiscovery/pdtm/cmd/pdtm@latest"
  fi
  export PATH="$PATH:$(gobin)"
  have pdtm && { pdtm -ia -duc -nc 2>/dev/null || true; }   # pdtm no tiene -silent; -duc/-nc = quietos
  have nuclei && { nuclei -update-templates -silent 2>/dev/null || true; }
  have gau || go install github.com/lc/gau/v2/cmd/gau@latest 2>/dev/null \
    || GOPROXY=direct go install github.com/lc/gau/v2/cmd/gau@latest 2>/dev/null || true
}

ensure_impacket(){
  have secretsdump.py && return 0
  have pipx || apt_retry install -y pipx
  pipx install impacket 2>/dev/null || true
}

# Kali gatea los postinstall de npm (warn 'allow-scripts'), pero el binario de claude lo crea npm
# igualmente; si el install falla (red), avisamos sin abortar.
ensure_claude(){
  have claude && return 0
  $SUDO npm install -g @anthropic-ai/claude-code \
    || echo "[!] claude no se instaló (¿npm/red?). Reintenta: sudo npm install -g @anthropic-ai/claude-code"
}
# Espejo opencode. Los providers free (Groq/Cerebras/… ver .opencode/opencode.json) leen su clave
# de {env:VAR} en runtime → deploy NO interactivo, sin 'opencode auth login'. El operador exporta
# las claves (cp .opencode/opencode.example.env .opencode/opencode.env; rellena; carga el env).
ensure_opencode(){
  have opencode && return 0
  $SUDO npm install -g opencode-ai \
    || echo "[!] opencode no se instaló (lab-only; ¿npm/red?). Reintenta: sudo npm install -g opencode-ai"
}

# gum (Charm) — para el asistente interactivo deploy/setup.sh. Vía el repo apt de Charm;
# si no se puede, deja que setup.sh degrade a prompts de texto (no es crítico).
ensure_gum(){
  have gum && return 0
  echo "[*] Instalando gum (Charm)…"
  $SUDO mkdir -p /etc/apt/keyrings
  curl -fsSL https://repo.charm.sh/apt/gpg.key 2>/dev/null | $SUDO gpg --dearmor -o /etc/apt/keyrings/charm.gpg 2>/dev/null || true
  echo "deb [signed-by=/etc/apt/keyrings/charm.gpg] https://repo.charm.sh/apt/ * *" \
    | $SUDO tee /etc/apt/sources.list.d/charm.list >/dev/null 2>&1 || true
  apt_retry update -y >/dev/null 2>&1 || true
  apt_retry install -y gum >/dev/null 2>&1 || true
  have gum || { echo "[!] gum no disponible; el asistente usará prompts de texto."; return 1; }
}

# Permisos de ejecución de los scripts de deploy. El bit +x se PIERDE al clonar/copiar desde
# Windows o desde un zip (git lo guarda en el modo del índice, no en .gitattributes). Esto lo
# restablece en runtime — cinturón y tirantes junto al modo 100755 ya grabado en el repo.
ensure_perms(){
  local d; d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  chmod +x "$d"/*.sh 2>/dev/null || true
}

# Docker + Compose v2 (para el despliegue en contenedores: deploy/docker.sh, docker-compose.yml).
# Solo se necesita para la ruta de contenedores; NO va en install_missing (el deploy de host no
# lo requiere). En Kali/Debian: docker.io + el plugin compose; arranca el servicio.
ensure_docker(){
  if have docker && docker compose version >/dev/null 2>&1; then return 0; fi
  echo "[*] Instalando Docker + Compose v2…"
  apt_retry install -y docker.io docker-compose-plugin 2>/dev/null \
    || apt_retry install -y docker.io docker-compose 2>/dev/null || true
  $SUDO systemctl enable --now docker 2>/dev/null || $SUDO service docker start 2>/dev/null || true
  have docker || { echo "[!] Docker no disponible; instálalo a mano (ver DEPLOY.md)."; return 1; }
  docker compose version >/dev/null 2>&1 || echo "[!] 'docker compose' (v2) no disponible; usa 'docker-compose' o instala el plugin."
}

# textual (panel TUI) — SIEMPRE en el venv del bot. Kali es PEP 668 ('externally-managed'): NO se
# puede pip-instalar al python del sistema. Si el venv no existe (p.ej. ruta verify --install, que no
# pasa por el setup_bot del auto-deploy), se crea aquí. Reporta el error real si pip falla.
ensure_textual(){
  local repo venv py req errf
  repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  venv="$repo/bot/.venv"; py="$venv/bin/python"; req="$repo/bot/requirements.txt"
  if [ ! -x "$py" ]; then
    echo "[*] Creando el venv del bot…"
    python3 -m venv "$venv" 2>/dev/null \
      || { echo "[!] No pude crear bot/.venv (instala 'python3-venv'); la TUI no abrirá."; return 1; }
  fi
  "$py" -c "import textual" 2>/dev/null && return 0
  echo "[*] Instalando dependencias del bot (textual + SDK + telegram) en el venv…"
  errf="$(mktemp 2>/dev/null || echo /tmp/da_pip_err)"
  "$py" -m pip install --quiet --upgrade pip 2>/dev/null || true
  [ -f "$req" ] && { "$py" -m pip install --quiet -r "$req" 2>"$errf" || true; }
  "$py" -c "import textual" 2>/dev/null || "$py" -m pip install --quiet textual 2>"$errf" || true
  if "$py" -c "import textual" 2>/dev/null; then rm -f "$errf"; return 0; fi
  echo "[!] textual no instalado (la TUI no abrirá): $(tail -1 "$errf" 2>/dev/null)"
  rm -f "$errf"; return 1
}

# agentsview — analítica local-first de sesiones de Claude Code (coste/actividad por agente).
# Binario standalone (Go, MIT). VERSIÓN FIJADA + verificación SHA256 (auditable, sin curl|bash).
# Lee ~/.claude/projects/ y sirve una UI en 127.0.0.1:8080 (local-only). Aquí SOLO se instala el
# binario (instalar != exponer datos de cliente): el daemon se arranca a propósito con
# deploy/agentsview.sh up. Un fallo de red NO debe tumbar el deploy (no crítico).
AGENTSVIEW_VERSION="0.33.1"
ensure_agentsview(){
  have agentsview && return 0
  local arch tgz base dest tmp bin
  case "$(uname -m)" in
    x86_64|amd64)  arch="amd64" ;;
    aarch64|arm64) arch="arm64" ;;
    *) echo "[!] arquitectura $(uname -m) no soportada por agentsview; omito (no crítico)."; return 1 ;;
  esac
  tgz="agentsview_${AGENTSVIEW_VERSION}_linux_${arch}.tar.gz"
  base="https://github.com/kenn-io/agentsview/releases/download/v${AGENTSVIEW_VERSION}"
  dest="$HOME/.local/bin"; mkdir -p "$dest"
  tmp="$(mktemp -d)" || return 1
  echo "[*] Instalando agentsview ${AGENTSVIEW_VERSION} (binario de release + verificación SHA256)…"
  if ! ( cd "$tmp" \
         && curl -fsSLO "${base}/${tgz}" \
         && curl -fsSLO "${base}/SHA256SUMS" \
         && grep " ${tgz}\$" SHA256SUMS | sha256sum -c - >/dev/null ); then
    echo "[!] descarga/verificación de agentsview falló; omito (no crítico)."; rm -rf "$tmp"; return 1
  fi
  tar -C "$tmp" -xzf "$tmp/${tgz}" 2>/dev/null || true
  bin="$(find "$tmp" -type f -name agentsview 2>/dev/null | head -1)"
  [ -n "$bin" ] || { echo "[!] binario agentsview no hallado en el paquete; omito."; rm -rf "$tmp"; return 1; }
  install -m 0755 "$bin" "$dest/agentsview" 2>/dev/null || { cp "$bin" "$dest/agentsview"; chmod +x "$dest/agentsview"; }
  rm -rf "$tmp"
  export PATH="$PATH:$dest"
  have agentsview || echo "[!] agentsview instalado en $dest, pero ~/.local/bin no está en el PATH (añádelo)."
}

# Instala SOLO lo que falte (cada paso comprueba antes; apt es idempotente).
install_missing(){
  echo "── Instalando lo que falte ──"
  apt_retry update -y
  for p in nmap rustscan sqlmap metasploit-framework ffuf feroxbuster seclists \
           netexec gobuster john hashcat amass chisel proxychains4; do
    apt_retry install -y "$p" || echo "[!] '$p' no disponible vía apt (revisar)."
  done
  ensure_claude
  ensure_pd
  ensure_impacket
  ensure_opencode
  ensure_gum
  ensure_textual
  ensure_agentsview
  have bloodhound-python || { have pipx && pipx install bloodhound 2>/dev/null; } || true
  have sliver-server || { curl -fsSL https://sliver.sh/install | $SUDO bash || \
    echo "[!] Sliver falló; instálalo a mano (ver DEPLOY.md)."; }
  echo "── Instalación terminada ──"
}

# Actualiza todo a su última versión.
update_all(){
  echo "── Actualizando a lo último ──"
  apt_retry update -y && apt_retry upgrade -y
  if have go; then
    export PATH="$PATH:$(gobin)"
    have pdtm && { pdtm -ua -duc -nc 2>/dev/null || true; }
  fi
  have nuclei && { nuclei -update-templates -silent 2>/dev/null || true; }
  have pipx && { pipx upgrade-all 2>/dev/null || true; }
  have npm && { $SUDO npm update -g @anthropic-ai/claude-code opencode-ai 2>/dev/null || true; }
  echo "── Actualización terminada ──"
}
