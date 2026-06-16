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
ensure_pd(){
  ensure_go || { echo "[ERR] sin Go no se pueden instalar las PD tools."; return 1; }
  export PATH="$PATH:$(gobin)"
  have pdtm || go install github.com/projectdiscovery/pdtm/cmd/pdtm@latest
  export PATH="$PATH:$(gobin)"
  pdtm -ia -silent 2>/dev/null || true
  have nuclei && { nuclei -update-templates -silent 2>/dev/null || true; }
  have gau || go install github.com/lc/gau/v2/cmd/gau@latest 2>/dev/null || true
}

ensure_impacket(){
  have secretsdump.py && return 0
  have pipx || apt_retry install -y pipx
  pipx install impacket 2>/dev/null || true
}

ensure_claude(){ have claude || $SUDO npm install -g @anthropic-ai/claude-code; }
ensure_opencode(){ have opencode || $SUDO npm install -g opencode-ai; }

# Instala SOLO lo que falte (cada paso comprueba antes; apt es idempotente).
install_missing(){
  echo "── Instalando lo que falte ──"
  apt_retry update -y
  for p in nmap sqlmap metasploit-framework ffuf feroxbuster seclists \
           netexec gobuster john hashcat amass; do
    apt_retry install -y "$p" || echo "[!] '$p' no disponible vía apt (revisar)."
  done
  ensure_claude
  ensure_pd
  ensure_impacket
  ensure_opencode
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
    have pdtm && { pdtm -ua -silent 2>/dev/null || true; }
  fi
  have nuclei && { nuclei -update-templates -silent 2>/dev/null || true; }
  have pipx && { pipx upgrade-all 2>/dev/null || true; }
  have npm && { $SUDO npm update -g @anthropic-ai/claude-code opencode-ai 2>/dev/null || true; }
  echo "── Actualización terminada ──"
}
