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
#    ./deploy/auto-deploy.sh --semantic-rag       # + RAG Capa 2 semantica (pesado: torch + embeddings)
#    ./deploy/auto-deploy.sh --no-cron            # no programar la ingesta pasiva (cron)
#    ./deploy/auto-deploy.sh --opencode-nvidia    # monta el perfil NVIDIA en el espejo opencode (lab)
#    ./deploy/auto-deploy.sh -h
# =============================================================================
set -Eeuo pipefail

# Salida de Python SIN buffer: este script canaliza todo por 'tee' (ver más abajo). Ante un pipe,
# Python usa buffering por bloques y los pasos largos (RAG) no muestran progreso -> PARECE colgado.
export PYTHONUNBUFFERED=1

# ── Rutas ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG="${SCRIPT_DIR}/deploy-$(date +%Y%m%d-%H%M%S).log"

# Banner de la herramienta (helper compartido; degrada a texto plano sin TTY).
# shellcheck source=deploy/banner.sh
. "${SCRIPT_DIR}/banner.sh" 2>/dev/null || true

# ── Flags ────────────────────────────────────────────────────────────────────
DO_TOOLS=1; DO_RAG=1; DO_BOT=1; UPDATE=0; DO_SEMANTIC=0; DO_CRON=1; DO_OC_NVIDIA=0
for a in "$@"; do case "$a" in
  --skip-tools)     DO_TOOLS=0 ;;
  --no-rag)         DO_RAG=0 ;;
  --no-bot)         DO_BOT=0 ;;
  --update)         UPDATE=1 ;;
  --semantic-rag)   DO_SEMANTIC=1 ;;
  --no-cron)        DO_CRON=0 ;;
  --opencode-nvidia) DO_OC_NVIDIA=1 ;;
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

# Helpers de instalación COMPARTIDOS con verify.sh (ensure_pd/ensure_rustscan/ensure_chisel/
# ensure_sliver/ensure_go…). Se cargan ANTES de redefinir SUDO/have/apt_retry abajo, para que ganen
# las versiones con color de este script. Evita duplicar la lógica de instalación entre los dos scripts.
# shellcheck source=deploy/lib.sh
. "${SCRIPT_DIR}/lib.sh"

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
    python3 python3-pip python3-venv pipx python-is-python3 python3-yaml \
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
  info "Paquetes de los repos de Kali (uno a uno: un paquete ausente no bloquea al resto)…"
  apt_retry update -y || true
  # Las PD tools subfinder/naabu/katana/dnsx van por APT: en Kali es la vía fiable. Antes dependían solo
  # de pdtm/go install y fallaban por DNS a proxy.golang.org -> aparecían "NO INSTALADO". httpx NO se mete
  # por apt (su paquete colisiona con la lib python 'httpx'): viene en Kali de base / lo completa ensure_pd.
  # naabu necesita libpcap-dev. rustscan NO está en apt (binario Rust) -> se instala aparte (ensure_rustscan).
  for p in nmap sqlmap metasploit-framework ffuf feroxbuster seclists \
           netexec gobuster john hashcat amass proxychains4 \
           subfinder naabu katana dnsx libpcap-dev jq unzip; do
    apt_retry install -y "$p" || warn "'$p' no disponible vía apt (se intentará por otra vía si aplica)."
  done

  info "rustscan (no está en apt: .deb del último release oficial)…"; ensure_rustscan || true
  ensure_chisel || true
  ensure_httpx || true   # httpx-toolkit (apt) + symlink 'httpx' (los agentes invocan 'httpx')
  # Completa por pdtm/go SOLO las PD tools que apt no dejara (no-Kali / repos sin ellas), + gau (no apt).
  info "ProjectDiscovery: completando lo que falte (pdtm/go) + gau…"; ensure_pd || true
  [ "$UPDATE" -eq 1 ] && have pdtm && { pdtm -ua -duc -nc || true; }
  have nuclei && { info "Actualizando plantillas de Nuclei…"; nuclei -update-templates -silent || true; }

  # Impacket (pipx)
  if ! have secretsdump.py; then info "Instalando Impacket…"; pipx install impacket || true; fi
  [ "$UPDATE" -eq 1 ] && pipx upgrade-all >/dev/null 2>&1 || true

  # BloodHound.py collector (la GUI CE es opcional vía Docker, ver DEPLOY.md)
  have bloodhound-python || pipx install bloodhound || true

  # Sliver C2 — instalador oficial con fallback a los binarios del release (ver lib.sh)
  info "Sliver C2…"; ensure_sliver || true
  ok "Toolchain instalado."
}

# =============================================================================
# 4) RAG — poblar el store de vulnerabilidades
# =============================================================================
setup_rag(){
  step "4/6  RAG (vulnerabilidades + conocimiento)"
  cd "$REPO_DIR"
  # Idempotencia: si el store ya está poblado y no se fuerza --update, NO re-descargues ~1.6k CVE
  # (el refresco completo tarda varios minutos). Acelera re-ejecuciones y respeta un vulns.db restaurado.
  local _n=0
  [ -f rag/vulns.db ] && _n="$(python3 -c 'import sqlite3
try: print(sqlite3.connect("rag/vulns.db").execute("SELECT COUNT(*) FROM vulns").fetchone()[0])
except Exception: print(0)' 2>/dev/null || echo 0)"
  if [ "$UPDATE" -eq 0 ] && [ "${_n:-0}" -gt 0 ]; then
    ok "RAG ya poblado (${_n} CVE) — omito el refresco (fuerza con --update)."
    return 0
  fi
  info "Poblando el RAG desde fuentes públicas (CISA KEV · CVE 5.0 · ExploitDB · Metasploit · Nuclei · EPSS)."
  info "Enriquece ~1.6k CVE uno a uno: puede tardar VARIOS MINUTOS — verás progreso '[CVE5] N/total'. (Sáltalo con --no-rag.)"
  if python3 rag/refresh.py --epss-all; then
    ok "RAG poblado."
  else
    warn "El RAG no se pudo poblar del todo (¿red? CISA KEV/EPSS/MITRE). Reintenta luego: python3 rag/refresh.py --epss-all"
  fi

  # --- RAG de CONOCIMIENTO (técnicas: GTFOBins · LOLBAS · Atomic Red Team · MITRE ATT&CK) ---
  # Lo consultan los agentes (post-exploit/web-exploit) vía rag/knowledge/query_kb.py. Idempotente.
  local _k=0
  [ -f rag/knowledge/kb.db ] && _k="$(python3 -c 'import sqlite3
try: print(sqlite3.connect("rag/knowledge/kb.db").execute("SELECT COUNT(*) FROM techniques").fetchone()[0])
except Exception: print(0)' 2>/dev/null || echo 0)"
  if [ "$UPDATE" -eq 0 ] && [ "${_k:-0}" -gt 0 ]; then
    ok "RAG de conocimiento ya poblado (${_k} técnicas) — omito (fuerza con --update)."
  else
    info "Poblando el RAG de conocimiento (clona GTFOBins/LOLBAS/Atomic + baja el STIX de ATT&CK; puede tardar)."
    if python3 rag/knowledge/refresh_kb.py; then
      ok "RAG de conocimiento poblado."
    else
      warn "El RAG de conocimiento no se pobló del todo (¿red/git?). Reintenta luego: python3 rag/knowledge/refresh_kb.py"
    fi
  fi

  # --- Capa 2 SEMÁNTICA (HackTricks · PayloadsAllTheThings · PEASS · feeds) — OPT-IN (--semantic-rag) ---
  # Pesada: venv AISLADO del RAG (torch CPU-only) + embeddings locales de un corpus grande (TARDA bastante).
  # Las deps NO van al python3 del sistema (chocan con dpkg en Kali): viven en rag/knowledge/.venv; la
  # lógica está en rag/knowledge/_venv.py y los agentes consultan en runtime vía query_kb (se redirige solo).
  if [ "$DO_SEMANTIC" -eq 1 ]; then
    info "Capa 2 (semántica): preparando el venv del RAG (torch CPU) y poblando embeddings. Esto TARDA."
    if ensure_semantic_deps; then
      if python3 rag/knowledge/refresh_kb.py --semantic-only --no-install-deps; then
        ok "Capa 2 (semántica) poblada."
      else
        warn "Capa 2 no se pobló del todo. Reintenta: python3 rag/knowledge/refresh_kb.py --semantic-only"
      fi
    else
      warn "Capa 2 omitida: no se pudieron instalar/verificar sus deps. Reintenta luego: python3 rag/knowledge/refresh_kb.py --semantic"
    fi
  else
    info "Capa 2 (semántica) omitida (actívala con --semantic-rag; requiere torch + tiempo de embeddings)."
  fi

  # Propiedad de los artefactos del RAG -> OPERADOR. El cron de ingesta corre como ${SUDO_USER} (no-root);
  # si el deploy los pobló como root, el cron no podría reescribir las DB y quedarían obsoletas EN SILENCIO
  # (los ingesters se tragan el error). Devolver la propiedad evita ese "OK" falso. Solo aplica con sudo.
  if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ]; then
    for _p in rag/vulns.db rag/vulns.db-* rag/knowledge/kb.db rag/knowledge/kb.db-* \
              rag/knowledge/kb_vec.db rag/knowledge/kb_vec.db-* rag/knowledge/.cache \
              rag/knowledge/.venv rag/.refresh.log; do
      [ -e "$_p" ] && chown -R "${SUDO_USER}" "$_p" 2>/dev/null || true
    done
    info "Propiedad de los artefactos del RAG devuelta a '${SUDO_USER}' (el cron los refresca como ese usuario)."
  fi

  # --- INGESTA PASIVA: programa el refresco con cron (idempotente) ------------------------------
  # Mantiene los RAG al día solos: vulnerabilidades a diario (incluye CVE recientes) y conocimiento
  # semanal. Se instala en el crontab del usuario OPERADOR (no root), con un marcador para no duplicar.
  if [ "$DO_CRON" -eq 1 ]; then
    if command -v crontab >/dev/null 2>&1; then
      local _uarg="" _cuser
      if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ]; then
        _uarg="-u ${SUDO_USER}"; _cuser="${SUDO_USER}"
      else
        _cuser="$(id -un)"
      fi
      local _py _mark _log _kb _daily _weekly _cur
      _py="$(command -v python3 || echo python3)"
      _mark="# data-attack-rag"
      _log="${REPO_DIR}/rag/.refresh.log"
      _kb="rag/knowledge/refresh_kb.py"
      # El cron NO auto-instala deps (--no-install-deps): corre como el operador (no-root) y un
      # 'pip --break-system-packages' al python del sistema fallaría por permisos; las deps las dejó el
      # deploy (ensure_semantic_deps, como root). Si se rompieran, refresh_kb avisa en el log, no reinstala.
      [ "$DO_SEMANTIC" -eq 1 ] && _kb="rag/knowledge/refresh_kb.py --semantic --no-install-deps"
      _daily="0 6 * * * cd ${REPO_DIR} && ${_py} rag/refresh.py --epss-all >> ${_log} 2>&1 ${_mark}"
      _weekly="0 4 * * 0 cd ${REPO_DIR} && ${_py} ${_kb} >> ${_log} 2>&1 ${_mark}"
      # Idempotente: descarta las líneas gestionadas previas (por marcador) y reescribe.
      _cur="$( (crontab ${_uarg} -l 2>/dev/null || true) | grep -vF "${_mark}" || true )"
      if printf '%s\n%s\n%s\n' "${_cur}" "${_daily}" "${_weekly}" | sed '/^[[:space:]]*$/d' | crontab ${_uarg} - 2>/dev/null; then
        ok "Ingesta pasiva programada (cron de '${_cuser}'): vulns diario 06:00, conocimiento domingos 04:00. Log: ${_log}"
      else
        warn "No pude instalar el cron para '${_cuser}'. Prográmalo a mano (ver rag/README.md → Programación)."
      fi
    else
      warn "crontab no disponible; omito la ingesta pasiva. Prográmala a mano (ver rag/README.md → Programación)."
    fi
  else
    info "Ingesta pasiva (cron) omitida (--no-cron). Prográmala a mano si la quieres (ver rag/README.md)."
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
    # Propiedad al OPERADOR: el bot se arranca como ${SUDO_USER} no-root (cd bot && ./.venv/bin/python
    # bot.py); un .env 600 propiedad de root NO sería legible por él (no podría cargar el token).
    _own_env "$REPO_DIR/bot/.env"
    ok "bot/.env creado (permisos 600, ignorado por git)."
  else
    ok "bot/.env ya existe — se conserva."
  fi
}

# =============================================================================
#  Espejo opencode (LAB-ONLY) — claves de los modelos FREE. Pide la de NVIDIA.
#  El espejo opencode corre agentes mecánicos contra LABORATORIOS PROPIOS con modelos gratis (jamás
#  cliente/E2). NVIDIA NIM da 100+ modelos de razonamiento gratis con UNA sola clave; la pedimos aquí
#  para dejar el entorno autoconfigurado. Idempotente; NO cuelga un deploy desatendido (guard de TTY).
# =============================================================================
# Propiedad del .env al OPERADOR (no-root): opencode lo lee desde su shell. Modo 600. Solo con sudo.
_own_env(){ # _own_env <ruta>
  chmod 600 "$1" 2>/dev/null || true
  [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ] && chown "${SUDO_USER}:" "$1" 2>/dev/null || true
}
setup_opencode_env(){
  step "Espejo opencode — runtime + claves de modelos free (LAB-ONLY)"
  # Instala el BINARIO de opencode (idempotente, lab-only) para que el espejo quede EJECUTABLE, no solo
  # configurado: 'autodespliegue en opencode'. ensure_opencode viene de lib.sh (npm i -g opencode-ai;
  # no-op si ya está; nunca aborta el deploy). Sin él, el operador tendría el opencode.json/perfil pero
  # no el runtime para correrlo.
  ensure_opencode
  local _tmpl="${REPO_DIR}/.opencode/opencode.example.env" _env="${REPO_DIR}/.opencode/opencode.env"
  if [ ! -f "$_tmpl" ]; then
    warn "No encuentro ${_tmpl}; omito la config del espejo opencode."; return 0
  fi
  if [ -f "$_env" ]; then
    ok "${_env} ya existe — se conserva (edítalo a mano para añadir/rotar claves)."; return 0
  fi
  # Crea el .env desde la plantilla. NO es crítico: si el cp falla, avisa y SIGUE (no abortes el deploy).
  # umask en subshell para no filtrar el cambio al resto del script.
  ( umask 077; cp "$_tmpl" "$_env" ) || { warn "No pude crear ${_env}; rellena las claves a mano."; return 0; }
  _own_env "$_env"
  # Sin TTY (deploy desatendido/CI): NO preguntamos para no colgar. Dejamos la plantilla copiada.
  if [ ! -t 0 ]; then
    info "Sin terminal interactiva: creado ${_env} desde la plantilla (rellena las claves a mano)."; return 0
  fi
  info "El espejo opencode usa modelos GRATIS solo para LABORATORIOS PROPIOS (jamás cliente/E2/E3)."
  info "NVIDIA NIM (build.nvidia.com) ofrece 100+ modelos gratis (DeepSeek-R1, Nemotron…) con una clave."
  local _nv=""
  read -rp "  NVIDIA_API_KEY (Enter para dejarla vacía y rellenar luego): " _nv || true
  if [ -z "$_nv" ]; then
    ok "${_env} creado desde la plantilla (NVIDIA_API_KEY vacía; rellénala cuando quieras)."
  else
    case "$_nv" in
      # Una clave nvapi real es [A-Za-z0-9_.-]. Si trae otros caracteres (espacio/salto/paste sucio),
      # NO la escribimos: evita corromper el valor en silencio y abortar el deploy. Se rellena a mano.
      *[!A-Za-z0-9_.-]*)
        warn "La clave tiene caracteres inesperados (¿paste con espacio/salto?). NO la escribo; rellena NVIDIA_API_KEY a mano en ${_env}." ;;
      *)
        # Reescribe la línea SIN sed (un &/|/\\ de un paste corrompería el reemplazo de sed): filtra la
        # vieja con grep y añade la nueva con printf (no interpreta metacaracteres). Atómico vía .t + mv.
        if grep -v '^NVIDIA_API_KEY=' "$_env" > "${_env}.t" 2>/dev/null \
           && printf 'NVIDIA_API_KEY=%s\n' "$_nv" >> "${_env}.t" \
           && mv "${_env}.t" "$_env"; then
          _own_env "$_env"
          ok "Clave de NVIDIA guardada en ${_env} (permisos 600, ignorado por git)."
        else
          rm -f "${_env}.t" 2>/dev/null || true
          warn "No pude escribir la clave en ${_env}; rellénala a mano."
        fi ;;
    esac
  fi
  info "Carga las claves en tu shell:  set -a; . \"${REPO_DIR}/.opencode/opencode.env\"; set +a"
}

# Opción: montar el perfil NVIDIA en el espejo opencode (17 agentes recon/explotación → modelos NVIDIA
# free) para CORROBORAR que la suite se conduce con NVIDIA sin gastar Anthropic. Reversible. NO es la
# medición oficial (esa = Claude, run_gate.py): opencode no ejecuta los hooks deterministas ni el A2A.
mount_opencode_profile(){
  local _mount="${DO_OC_NVIDIA:-0}"
  if [ "$_mount" -eq 0 ] && [ -t 0 ]; then
    local _ans=""
    read -rp "  ¿Montar el perfil NVIDIA en el espejo opencode para corroborar el cableado (17 agentes free)? [y/N]: " _ans || true
    case "$_ans" in [yYsS]) _mount=1 ;; esac
  fi
  [ "$_mount" -eq 1 ] || return 0
  step "Espejo opencode — perfil NVIDIA (corroboración, LAB-ONLY)"
  if python3 "${REPO_DIR}/tools/apply_routing.py" nvidia-lab; then
    ok "Perfil NVIDIA montado (17 agentes). Revertir: python3 tools/apply_routing.py default"
    warn "opencode NO ejecuta hooks (scope_guard/C1-C19) ni A2A → corrobora cableado, NO es la medición oficial (esa = Claude, run_gate.py). Exporta NVIDIA_API_KEY antes de usarlo."
  else
    warn "No pude montar el perfil NVIDIA. Reintenta: python3 tools/apply_routing.py nvidia-lab"
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
  setup_opencode_env
  mount_opencode_profile
  run_verify
  step "✔ Despliegue completado"
  ok "Arranca el bot:  cd bot && ./.venv/bin/python bot.py"
  ok "O usa la CLI:    claude   (y escribe /agents)"
  ok "Asistente:       ./deploy/setup.sh   (configuración guiada)"
  ok "Panel TUI:       ./deploy/dash.sh    (control local en terminal)"
  ok "Contenedores:    ./deploy/docker.sh up   (despliegue en Docker — alternativa al de host)"
}
main
