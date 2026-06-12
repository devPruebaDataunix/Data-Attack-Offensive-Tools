#!/usr/bin/env bash
# =============================================================================
#  verify.sh — Corroboración del entorno: herramientas, versiones, RAG, agentes.
#  Sale con código !=0 si falta algo crítico. Se puede ejecutar solo:
#    ./deploy/verify.sh
# =============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PATH="$PATH:$(go env GOPATH 2>/dev/null)/bin:$HOME/.local/bin"
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

echo; echo -e "$(c 6)── Herramientas críticas ──$(r)"
chk "claude"      claude --version
chk "nmap"        nmap --version
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
