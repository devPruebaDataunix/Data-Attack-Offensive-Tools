#!/usr/bin/env bash
# =============================================================================
#  deploy/docker.sh — Despliegue en CONTENEDORES de Data Attack.
#  Envuelve docker-compose.yml. Requiere Docker en el host (la Kali).
#    ./deploy/docker.sh build     # construye la imagen (data-attack:latest)
#    ./deploy/docker.sh rag       # puebla/actualiza el RAG (one-shot)
#    ./deploy/docker.sh up        # build + RAG (si falta) + levanta el bot
#    ./deploy/docker.sh down      # para y elimina los contenedores
#    ./deploy/docker.sh logs      # sigue los logs del bot
#    ./deploy/docker.sh shell     # shell interactiva dentro de la imagen
#    ./deploy/docker.sh status    # estado de los contenedores
#  Ver DEPLOY.md -> "Despliegue en contenedores".
# =============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_DIR"
# shellcheck source=deploy/banner.sh
. "${SCRIPT_DIR}/banner.sh" 2>/dev/null || true
# shellcheck source=deploy/lib.sh
. "${SCRIPT_DIR}/lib.sh"

ensure_perms
ensure_docker || { echo "[ERR] Docker no disponible; instálalo o revisa DEPLOY.md."; exit 1; }

# Compose v2 ('docker compose') o legacy ('docker-compose').
if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi

warnp(){ printf '  \e[38;2;255;68;68m%s\e[0m\n' "$*"; }

check_env(){
  [ -f "${REPO_DIR}/bot/.env" ] || warnp "Falta bot/.env (token/usuario). Créalo con ./deploy/setup.sh antes de 'up'."
  [ -d "${HOME:-/root}/.claude" ] || warnp "No veo ~/.claude (login Pro). Ejecuta 'claude' y haz login en el host antes de 'up'."
}

command -v da_banner >/dev/null 2>&1 && da_banner || true

cmd="${1:-up}"
case "$cmd" in
  build)  $DC build ;;
  rag)    $DC run --rm rag-init ;;
  up)     check_env
          $DC build \
            && { [ -f "${REPO_DIR}/rag/vulns.db" ] || $DC run --rm rag-init; } \
            && $DC up -d bot \
            && echo "[OK] bot en marcha. Logs: ./deploy/docker.sh logs" ;;
  down)   $DC down ;;
  logs)   $DC logs -f bot ;;
  shell)  $DC run --rm --entrypoint /bin/bash bot ;;
  status) $DC ps ;;
  -h|--help) grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//' ;;
  *) echo "Comando desconocido: $cmd (build|rag|up|down|logs|shell|status)"; exit 2 ;;
esac
