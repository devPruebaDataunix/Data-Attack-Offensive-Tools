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

# ProjectDiscovery (subfinder/naabu/katana/dnsx/httpx): PRIMARIO = apt de Kali (binarios en /usr/bin,
# en el PATH; fiable). Esta función es el FALLBACK para lo que apt no dejara (no-Kali, o repos sin esos
# paquetes): pdtm/go install — frágil (DNS a proxy.golang.org/sum.golang.org y PATH del go-bin). gau NO
# está en apt -> siempre por go. Quien llama mete las PD tools en la lista apt ANTES de invocar esto.
ensure_pd(){
  if have subfinder && have naabu && have katana && have dnsx && { have httpx || have httpx-toolkit; }; then
    ensure_gau; return 0       # apt ya las dejó; solo falta gau (no empaquetado)
  fi
  ensure_go || { echo "[ERR] faltan PD tools y sin Go no puedo instalarlas (prueba: apt install subfinder naabu katana dnsx httpx)."; return 1; }
  export PATH="$PATH:$(gobin)"
  export GOPROXY="${GOPROXY:-https://proxy.golang.org|direct}" GOSUMDB="${GOSUMDB:-off}"
  if ! have pdtm; then
    go install github.com/projectdiscovery/pdtm/cmd/pdtm@latest 2>/dev/null \
      || GOPROXY=direct go install github.com/projectdiscovery/pdtm/cmd/pdtm@latest 2>/dev/null \
      || echo "[!] pdtm NO instalado (¿DNS/red?): instala las PD tools por apt (subfinder naabu katana dnsx httpx)."
  fi
  export PATH="$PATH:$(gobin)"
  have pdtm && { pdtm -ia -duc -nc 2>/dev/null || true; }   # pdtm no tiene -silent; -duc/-nc = quietos
  have nuclei && { nuclei -update-templates -silent 2>/dev/null || true; }
  ensure_gau
}
# gau (lc/gau): no está en apt -> go install (con fallback a GOPROXY=direct).
ensure_gau(){
  have gau && return 0
  ensure_go || return 1
  export PATH="$PATH:$(gobin)" GOPROXY="${GOPROXY:-https://proxy.golang.org|direct}" GOSUMDB="${GOSUMDB:-off}"
  go install github.com/lc/gau/v2/cmd/gau@latest 2>/dev/null \
    || GOPROXY=direct go install github.com/lc/gau/v2/cmd/gau@latest 2>/dev/null || true
}
# httpx (ProjectDiscovery): en Kali el paquete es 'httpx-toolkit' (evita el choque con la lib python3-httpx)
# y su binario es 'httpx-toolkit'. Los agentes invocan 'httpx' -> si solo está httpx-toolkit, lo symlinkeamos.
ensure_httpx(){
  have httpx && return 0
  $SUDO apt-get install -y httpx-toolkit 2>/dev/null || true
  if ! have httpx && have httpx-toolkit; then
    $SUDO ln -sf "$(command -v httpx-toolkit)" /usr/local/bin/httpx 2>/dev/null || true
  fi
  have httpx && return 0
  echo "[*] httpx no quedó por apt (httpx-toolkit); lo intentará pdtm/go en ensure_pd."; return 1
}

# rustscan: NO está en los repos apt de Debian/Kali (binario Rust). 1 intento apt (por si una Kali futura
# lo empaqueta); si no, el release oficial publica el .deb DENTRO de un zip (asset 'rustscan.deb.zip',
# verificado en la API) -> bajar, unzip, dpkg. El .deb es amd64; en arm64 dpkg lo rechaza y los agentes
# caen a 'nmap -sS -p-' (degradación documentada en la skill stealth-recon).
ensure_rustscan(){
  have rustscan && return 0
  $SUDO apt-get install -y rustscan 2>/dev/null && have rustscan && return 0   # 1 intento (no retry): se espera que falle
  { have jq && have unzip; } || { echo "[!] rustscan: faltan jq/unzip para bajar el release; los agentes usarán nmap."; return 1; }
  echo "[*] rustscan no está en apt; bajando el .deb del último release (viene dentro de un .zip)…"
  local url tmp deb
  url="$(curl -fsSL https://api.github.com/repos/RustScan/RustScan/releases/latest 2>/dev/null | jq -r '.assets[]?|select(.name|test("\\.deb\\.zip$"))|.browser_download_url' 2>/dev/null | head -1)"
  [ -z "$url" ] && { echo "[!] rustscan: no hallé el .deb en el release; instálalo a mano o vía cargo. Los agentes usarán nmap."; return 1; }
  tmp="$(mktemp -d)" || return 1
  ( cd "$tmp" && curl -fsSLO "$url" && unzip -o -q ./*.zip && deb="$(ls ./*.deb 2>/dev/null | head -1)" && [ -n "$deb" ] && $SUDO dpkg -i "$deb" 2>/dev/null ); $SUDO apt-get install -y -f 2>/dev/null || true
  rm -rf "$tmp"
  have rustscan || { echo "[!] rustscan no se pudo instalar (¿arm64? el .deb es amd64); los agentes de recon usarán 'nmap -sS -p-'."; return 1; }
}

# chisel (pivoting): en Kali está en apt; fallback al binario (gz) del último release de jpillora/chisel.
ensure_chisel(){
  have chisel && return 0
  $SUDO apt-get install -y chisel 2>/dev/null && have chisel && return 0       # 1 intento (no retry)
  local arch url tmp
  case "$(uname -m)" in x86_64|amd64) arch="(amd64|x86_64)";; aarch64|arm64) arch="(arm64|aarch64)";; *) echo "[!] chisel: arch no soportada; pivoting usará proxychains/ligolo."; return 1;; esac
  echo "[*] chisel no está en apt; bajando el binario del release…"
  url="$(curl -fsSL https://api.github.com/repos/jpillora/chisel/releases/latest 2>/dev/null | jq -r --arg a "$arch" '.assets[]?|select(.name|test("linux_"+$a+"\\.gz$"))|.browser_download_url' 2>/dev/null | head -1)"
  [ -z "$url" ] && { echo "[!] chisel: no hallé el binario; pivoting usará proxychains/ligolo."; return 1; }
  tmp="$(mktemp -d)" || return 1
  ( cd "$tmp" && curl -fsSLO "$url" && gunzip -f ./*.gz && $SUDO install -m0755 ./chisel* /usr/local/bin/chisel ) 2>/dev/null || true
  rm -rf "$tmp"
  have chisel || { echo "[!] chisel no se pudo instalar; pivoting usará proxychains/ligolo."; return 1; }
}

# Sliver C2: instalador oficial; si falla, binarios del último release a /usr/local/bin. Assets reales
# (BishopFox/sliver, verificado en la API): sliver-server_linux-amd64 / sliver-client_linux-amd64 (+ .minisig).
ensure_sliver(){
  have sliver-server && return 0
  echo "[*] Instalando Sliver C2 (instalador oficial)…"
  curl -fsSL https://sliver.sh/install 2>/dev/null | $SUDO bash 2>/dev/null || true
  have sliver-server && return 0
  have jq || { echo "[!] Sliver: falta jq para el fallback; instálalo a mano (ver DEPLOY.md)."; return 1; }
  echo "[*] El instalador oficial falló; bajando los binarios del último release…"
  local sarch api us uc
  case "$(uname -m)" in x86_64|amd64) sarch="amd64";; aarch64|arm64) sarch="arm64";; *) echo "[!] Sliver: arch $(uname -m) no soportada aquí; ver DEPLOY.md."; return 1;; esac
  api="$(curl -fsSL https://api.github.com/repos/BishopFox/sliver/releases/latest 2>/dev/null)"
  us="$(printf '%s' "$api" | jq -r --arg a "$sarch" '.assets[]?|select(.name=="sliver-server_linux-"+$a)|.browser_download_url' 2>/dev/null | head -1)"
  uc="$(printf '%s' "$api" | jq -r --arg a "$sarch" '.assets[]?|select(.name=="sliver-client_linux-"+$a)|.browser_download_url' 2>/dev/null | head -1)"
  [ -n "$us" ] && { $SUDO curl -fsSL "$us" -o /usr/local/bin/sliver-server 2>/dev/null && $SUDO chmod +x /usr/local/bin/sliver-server; }
  [ -n "$uc" ] && { $SUDO curl -fsSL "$uc" -o /usr/local/bin/sliver-client 2>/dev/null && $SUDO chmod +x /usr/local/bin/sliver-client; }
  have sliver-server || { echo "[!] Sliver no se pudo instalar; instálalo a mano (ver DEPLOY.md)."; return 1; }
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
  # PD tools subfinder/naabu/katana/dnsx van por apt: en Kali es la vía fiable (antes dependían solo de
  # pdtm/go y fallaban por DNS). httpx NO por apt (colisiona con la lib python 'httpx'): de base/ensure_pd.
  # naabu necesita libpcap-dev. rustscan NO está en apt -> aparte (ensure_rustscan).
  for p in nmap sqlmap metasploit-framework ffuf feroxbuster seclists \
           netexec gobuster john hashcat amass proxychains4 \
           subfinder naabu katana dnsx libpcap-dev jq unzip; do
    apt_retry install -y "$p" || echo "[!] '$p' no disponible vía apt (revisar)."
  done
  ensure_claude
  ensure_httpx       # httpx-toolkit (apt) + symlink 'httpx'
  ensure_pd          # completa por pdtm/go lo que apt no dejara, + gau
  ensure_rustscan    # .deb del release (no está en apt)
  ensure_chisel      # apt o binario del release
  ensure_impacket
  ensure_opencode
  ensure_gum
  ensure_textual
  ensure_agentsview
  have bloodhound-python || { have pipx && pipx install bloodhound 2>/dev/null; } || true
  ensure_sliver      # instalador oficial + fallback a binarios del release
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
