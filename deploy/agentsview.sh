#!/usr/bin/env bash
# =============================================================================
#  deploy/agentsview.sh — analitica LOCAL de sesiones (coste/actividad por agente).
#  Envuelve el binario `agentsview` (lee ~/.claude/projects/, sirve una UI en 127.0.0.1:8080).
#  LOCAL-ONLY por diseno: los transcripts contienen datos de cliente -> NUNCA --public-url,
#  telemetria desactivada. Instalar != exponer: el auto-deploy instala el binario; aqui se
#  ARRANCA a proposito.
#    ./deploy/agentsview.sh up        # servidor en 127.0.0.1:8080 (foreground, telemetria off)
#    ./deploy/agentsview.sh usage     # imprime el coste/uso (re-medir coste); pasa --agent/--since/--breakdown
#    ./deploy/agentsview.sh open      # abre el dashboard en el navegador
#    ./deploy/agentsview.sh status    # ¿esta escuchando el :8080?
#    ./deploy/agentsview.sh down      # para el servidor
#    ./deploy/agentsview.sh install   # instala/verifica el binario fijado (si falta)
#  Ver docs/cost-optimization.md -> "Re-medir el coste".
# =============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_DIR"
# shellcheck source=deploy/banner.sh
. "${SCRIPT_DIR}/banner.sh" 2>/dev/null || true
# shellcheck source=deploy/lib.sh
. "${SCRIPT_DIR}/lib.sh"

export PATH="$PATH:$HOME/.local/bin"
PORT="8080"   # agentsview vincula a 127.0.0.1:8080 por defecto (no hay flag de host/puerto; no lo forzamos)
# Local-only + sin telemetria. NUNCA --public-url: expondria transcripts con datos de cliente.
export AGENTSVIEW_TELEMETRY_ENABLED=0

warnp(){ printf '  \e[38;2;255;68;68m%s\e[0m\n' "$*"; }
need(){ ensure_agentsview || { echo "[ERR] agentsview no disponible; corre: ./deploy/agentsview.sh install"; exit 1; }; }

command -v da_banner >/dev/null 2>&1 && da_banner || true

cmd="${1:-up}"
case "$cmd" in
  install) ensure_agentsview && echo "[OK] $(agentsview --version 2>/dev/null | head -1 || echo 'agentsview instalado')" ;;
  up)      need
           [ -d "${HOME}/.claude/projects" ] || warnp "No veo ~/.claude/projects (¿aun no has usado Claude Code aqui?). El panel saldra vacio."
           echo "[*] agentsview en http://127.0.0.1:${PORT}  (local-only, telemetria off). Ctrl-C para parar."
           exec agentsview serve --no-update-check ;;
  usage)   need; shift; agentsview usage daily "$@" ;;
  open)    if command -v xdg-open >/dev/null 2>&1; then xdg-open "http://127.0.0.1:${PORT}" >/dev/null 2>&1 &
           else echo "Abre http://127.0.0.1:${PORT} en el navegador."; fi ;;
  status)  if curl -fsS "http://127.0.0.1:${PORT}" >/dev/null 2>&1; then
             echo "[OK] agentsview escuchando en 127.0.0.1:${PORT}"
           else echo "[--] agentsview no responde en 127.0.0.1:${PORT} (arranca con: ./deploy/agentsview.sh up)"; fi ;;
  down)    pkill -f "agentsview serve" 2>/dev/null && echo "[OK] agentsview parado" || echo "[--] no habia servidor de agentsview" ;;
  -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//' ;;
  *) echo "Comando desconocido: $cmd (up|usage|open|status|down|install)"; exit 2 ;;
esac
