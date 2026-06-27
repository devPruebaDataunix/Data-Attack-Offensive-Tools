#!/usr/bin/env bash
# =============================================================================
#  verify.sh — Corroboración del entorno: herramientas, versiones, RAG, agentes.
#  Sale con código !=0 si falta algo crítico.
#    ./deploy/verify.sh              # solo verifica
#    ./deploy/verify.sh --install    # instala lo que falte y luego verifica
#    ./deploy/verify.sh --update     # actualiza el toolchain a lo último y luego verifica
# =============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_DIR"
export PATH="$PATH:$(go env GOPATH 2>/dev/null)/bin:$HOME/.local/bin"
# shellcheck source=deploy/banner.sh
. "${SCRIPT_DIR}/banner.sh" 2>/dev/null || true

# ── Flags: instalación / actualización (la lógica vive en deploy/lib.sh) ──────
DO_INSTALL=0; DO_UPDATE=0
for a in "$@"; do case "$a" in
  --install) DO_INSTALL=1 ;;
  --update)  DO_UPDATE=1 ;;
  -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "Flag desconocido: $a (usa --install, --update o sin flags)"; exit 2 ;;
esac; done
if [ "$DO_INSTALL" -eq 1 ] || [ "$DO_UPDATE" -eq 1 ]; then
  # shellcheck source=deploy/lib.sh
  . "${SCRIPT_DIR}/lib.sh"
  [ "$DO_UPDATE" -eq 1 ]  && update_all
  [ "$DO_INSTALL" -eq 1 ] && install_missing
  export PATH="$PATH:$(go env GOPATH 2>/dev/null)/bin:$HOME/.local/bin"
fi
c(){ tput setaf "$1" 2>/dev/null || true; }; r(){ tput sgr0 2>/dev/null || true; }
FAIL=0; OKN=0
chk(){ # chk <nombre> <comando-version>
  local name="$1"; shift
  if command -v "${1%% *}" >/dev/null 2>&1 || command -v "$1" >/dev/null 2>&1; then
    local v; v="$("$@" 2>&1 | head -1 | tr -d '\r' | cut -c1-60)"
    printf "  $(c 2)[OK]$(r)  %-22s %s\n" "$name" "${v:-instalado}"; OKN=$((OKN+1))
  else
    printf "  $(c 1)[--]$(r)  %-22s NO INSTALADO\n" "$name"; FAIL=$((FAIL+1))
  fi
}

command -v da_banner >/dev/null 2>&1 && da_banner || true
echo; echo -e "$(c 6)── Herramientas críticas ──$(r)"
chk "claude"      claude --version
chk "nmap"        nmap --version
chk "rustscan"    rustscan --version
chk "metasploit"  msfconsole --version
chk "sqlmap"      sqlmap --version
chk "nuclei"      nuclei -version
chk "subfinder"   subfinder -version
chk "httpx"       httpx -version
chk "naabu"       naabu -version
chk "katana"      katana -version
chk "dnsx"        dnsx -version
chk "ffuf"        ffuf -V
chk "feroxbuster" feroxbuster --version
chk "netexec"     netexec --version
chk "impacket"    secretsdump.py -h
chk "bloodhound"  bloodhound-python --help
chk "sliver"      sliver-server version
chk "chisel"      chisel --version
chk "proxychains" proxychains4
chk "amass"       amass -version
chk "gobuster"    gobuster version
chk "hashcat"     hashcat --version
chk "john"        john --list=build-info

echo; echo -e "$(c 6)── Componentes del entorno ──$(r)"
cd "$REPO_DIR"
if python3 tools/validate_suite.py >/dev/null 2>&1; then
  printf "  $(c 2)[OK]$(r)  %-22s 0 fallos\n" "validate_suite.py"; OKN=$((OKN+1))
else printf "  $(c 1)[--]$(r)  %-22s con fallos\n" "validate_suite.py"; FAIL=$((FAIL+1)); fi

for _a in CONSTITUTION.md templates/engagement-spec.md tools/analyze_engagement.py; do
  if [ -f "$_a" ]; then printf "  $(c 2)[OK]$(r)  %-22s presente\n" "$(basename "$_a")"; OKN=$((OKN+1))
  else printf "  $(c 1)[--]$(r)  %-22s FALTA\n" "$(basename "$_a")"; FAIL=$((FAIL+1)); fi
done

if command -v claude >/dev/null 2>&1 && claude plugin validate ./plugin >/dev/null 2>&1; then
  printf "  $(c 2)[OK]$(r)  %-22s validación pasada\n" "plugin (claude)"; OKN=$((OKN+1))
else printf "  $(c 3)[??]$(r)  %-22s revisar\n" "plugin (claude)"; fi

# Réplica opencode (estática) — el config debe quedar replicado sin errores.
if python3 tools/verify_opencode.py >/dev/null 2>&1; then
  printf "  $(c 2)[OK]$(r)  %-22s réplica coherente\n" "verify_opencode.py"; OKN=$((OKN+1))
else printf "  $(c 1)[--]$(r)  %-22s con fallos (corre: python3 tools/verify_opencode.py)\n" "verify_opencode.py"; FAIL=$((FAIL+1)); fi

# CLI opencode (runtime, opcional) y — si el routing usa Ollama — disponibilidad de Ollama.
if command -v opencode >/dev/null 2>&1; then
  printf "  $(c 2)[OK]$(r)  %-22s %s\n" "opencode" "$(opencode --version 2>&1 | head -1 | cut -c1-30)"; OKN=$((OKN+1))
else printf "  $(c 3)[??]$(r)  %-22s no instalado (opcional; solo runtime opencode)\n" "opencode"; fi
if grep -q '"ollama/' tools/routing.json 2>/dev/null; then
  if command -v ollama >/dev/null 2>&1; then
    printf "  $(c 2)[OK]$(r)  %-22s %s\n" "ollama (routing)" "$(ollama --version 2>&1 | head -1 | cut -c1-30)"; OKN=$((OKN+1))
  else printf "  $(c 3)[??]$(r)  %-22s el routing enruta a ollama pero no está instalado\n" "ollama (routing)"; fi
fi
# Providers free del espejo opencode (LAB-ONLY): si el routing usa uno, su clave debe estar en el
# entorno (opencode la lee con {env:VAR}). No crítico: solo afecta al runtime opencode de lab.
for _pp in groq:GROQ_API_KEY cerebras:CEREBRAS_API_KEY deepseek:DEEPSEEK_API_KEY \
           minimax:MINIMAX_API_KEY zhipu:ZHIPU_API_KEY openrouter:OPENROUTER_API_KEY; do
  _prov="${_pp%%:*}"; _var="${_pp##*:}"
  if grep -q "\"${_prov}/" tools/routing.json 2>/dev/null; then
    if [ -n "${!_var:-}" ]; then
      printf "  $(c 2)[OK]$(r)  %-22s clave presente\n" "${_prov} (routing)"; OKN=$((OKN+1))
    else printf "  $(c 3)[??]$(r)  %-22s el routing usa %s pero falta %s (ver .opencode/opencode.example.env)\n" "${_prov} (routing)" "$_prov" "$_var"; fi
  fi
done

# Asistente (gum) y panel TUI (textual) — opcionales, mejoran la experiencia (no críticos).
if command -v gum >/dev/null 2>&1; then
  printf "  $(c 2)[OK]$(r)  %-22s %s\n" "gum (asistente)" "$(gum --version 2>&1 | head -1 | cut -c1-30)"; OKN=$((OKN+1))
else printf "  $(c 3)[??]$(r)  %-22s opcional (deploy/setup.sh degrada a texto)\n" "gum (asistente)"; fi
_PYV="${REPO_DIR}/bot/.venv/bin/python"; [ -x "$_PYV" ] || _PYV="$(command -v python3 || command -v python)"
if "$_PYV" -c "import textual" >/dev/null 2>&1; then
  printf "  $(c 2)[OK]$(r)  %-22s instalado\n" "textual (TUI)"; OKN=$((OKN+1))
else printf "  $(c 3)[??]$(r)  %-22s opcional (panel TUI: pip install textual)\n" "textual (TUI)"; fi

# Docker + Compose — opcional (solo para el despliegue en contenedores, deploy/docker.sh).
if command -v docker >/dev/null 2>&1; then
  if docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1; then
    if docker compose -f "${REPO_DIR}/docker-compose.yml" config -q >/dev/null 2>&1; then
      printf "  $(c 2)[OK]$(r)  %-22s %s · compose válido\n" "docker (contenedores)" "$(docker --version 2>&1 | head -1 | cut -c1-22)"; OKN=$((OKN+1))
    else printf "  $(c 2)[OK]$(r)  %-22s %s\n" "docker (contenedores)" "$(docker --version 2>&1 | head -1 | cut -c1-30)"; OKN=$((OKN+1)); fi
  else printf "  $(c 3)[??]$(r)  %-22s docker sí, compose no (instala docker-compose-plugin)\n" "docker compose"; fi
else printf "  $(c 3)[??]$(r)  %-22s opcional (despliegue en contenedores: deploy/docker.sh)\n" "docker"; fi

# agentsview — analitica local de coste/actividad por agente (opcional; el auto-deploy instala el
# binario, se arranca con deploy/agentsview.sh up). NO critico: que falte no impide operar.
if command -v agentsview >/dev/null 2>&1; then
  printf "  $(c 2)[OK]$(r)  %-22s %s\n" "agentsview" "$(agentsview --version 2>&1 | head -1 | cut -c1-30)"; OKN=$((OKN+1))
else printf "  $(c 3)[??]$(r)  %-22s opcional (analitica de coste: deploy/agentsview.sh up)\n" "agentsview"; fi

if [ -f rag/vulns.db ]; then
  n=$(python3 - <<'PY'
import sqlite3;print(sqlite3.connect("rag/vulns.db").execute("SELECT COUNT(*) FROM vulns").fetchone()[0])
PY
)
  [ "${n:-0}" -gt 0 ] && { printf "  $(c 2)[OK]$(r)  %-22s %s CVE\n" "RAG store" "$n"; OKN=$((OKN+1)); } \
                      || { printf "  $(c 1)[--]$(r)  %-22s vacío\n" "RAG store"; FAIL=$((FAIL+1)); }
else printf "  $(c 3)[??]$(r)  %-22s no poblado (corre rag/refresh.py)\n" "RAG store"; fi

# Auth de Claude (no bloqueante)
if claude -p "responde solo: ok" --output-format text >/dev/null 2>&1; then
  printf "  $(c 2)[OK]$(r)  %-22s sesión activa\n" "Claude auth"; OKN=$((OKN+1))
else printf "  $(c 3)[??]$(r)  %-22s ejecuta 'claude' y haz login Pro\n" "Claude auth"; fi

echo; echo -e "$(c 6)──────────────────────────────$(r)"
if [ "$FAIL" -eq 0 ]; then
  echo -e "  $(c 2)RESULTADO: $OKN OK, 0 fallos críticos — entorno listo.$(r)"; exit 0
else
  echo -e "  $(c 1)RESULTADO: $OKN OK, $FAIL fallos críticos — revisa arriba.$(r)"; exit 1
fi
