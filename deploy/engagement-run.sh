#!/usr/bin/env bash
# =============================================================================
#  deploy/engagement-run.sh — CONTENEDOR EFÍMERO POR-ENGAGEMENT (mejora "C" Shannon).
#
#  El anillo de aislamiento por-cliente: un contenedor DESECHABLE que monta SOLO el
#  engagement indicado (no todos), endurecido y sin egress por defecto. Es el hogar
#  designado para procesar CONTENIDO HOSTIL (código de cliente white-box hoy; navegador
#  headless / proxy de interceptación / validación por visión en releases posteriores).
#  Complementa —no sustituye— el guard en-proceso .claude/hooks/fs_guard.py: el guard
#  bloquea escapes por symlink/`..`; este contenedor da el confinamiento DURO (el proceso
#  del engagement solo VE `engagements/<id>/`, nunca el repo, otros clientes ni ~/.claude).
#
#    ./deploy/engagement-run.sh <engagement_id>                 # shell en el anillo (sin red)
#    ./deploy/engagement-run.sh <engagement_id> -- <cmd...>     # corre <cmd> y sale
#    ./deploy/engagement-run.sh <engagement_id> --net da-eng    # con una red docker acotada
#    ./deploy/engagement-run.sh <engagement_id> --claude-auth   # monta ~/.claude ro (opt-in)
#
#  Propiedades de aislamiento (CONSTITUTION §1 aislamiento de cliente, §6 datos E3):
#   - Monta SOLO engagements/<id>/ (rw) — nunca todos los engagements ni el código del repo.
#   - scope.json montado READ-ONLY: el run_scope queda CONGELADO (las puertas no se relajan).
#   - Sin red por defecto (--network none): el procesado de contenido hostil no necesita egress.
#   - --rm (desechable), rootfs read-only, cap-drop ALL, no-new-privileges, pids/mem/cpu acotados.
#   - ~/.claude (login del operador) NO se monta salvo --claude-auth explícito (creds fuera del anillo).
#  Este script y `docker-compose.engagement.yml` duplican el endurecimiento a propósito (el .sh
#  necesita saneo del id, montajes condicionales, --net y `-- cmd` difíciles en compose puro): si
#  cambias caps/límites/tmpfs aquí, cámbialo también en el compose.
#  Lab-only. Requiere Docker en el host. Ver DEPLOY.md -> "Contenedor efímero por-engagement".
# =============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_DIR"
# shellcheck source=deploy/lib.sh
. "${SCRIPT_DIR}/lib.sh" 2>/dev/null || true

warnp(){ printf '  \e[38;2;255;68;68m%s\e[0m\n' "$*"; }
die(){ echo "[ERR] $*" >&2; exit 1; }

[ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] && { grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

EID="${1:-}"; shift || true
[ -n "$EID" ] || die "Falta <engagement_id>. Uso: $0 <engagement_id> [--net N] [--claude-auth] [-- cmd...]"
# Sanitiza el id: un ÚNICO segmento de ruta (evita montar fuera de engagements/). Rechaza vacío,
# separadores, `..`, y también `.`/`..` exactos (un solo `.` montaría engagements/ ENTERO).
case "$EID" in
  "" | "." | ".." | *[!A-Za-z0-9._-]* | *..* ) die "engagement_id inválido: '$EID' (usa [A-Za-z0-9._-], un solo segmento, sin '.'/'..' ni '/')." ;;
esac
[ "$(basename -- "$EID")" = "$EID" ] || die "engagement_id debe ser un hijo directo de engagements/ (sin rutas)."

NET="none"; CLAUDE_AUTH=0; CMD=()
while [ $# -gt 0 ]; do
  case "$1" in
    --net) NET="${2:-}"; shift 2 || die "--net requiere un valor (none|<red docker>)" ;;
    --claude-auth) CLAUDE_AUTH=1; shift ;;
    --) shift; CMD=("$@"); break ;;
    *) die "Argumento desconocido: $1" ;;
  esac
done

ENG_DIR="${REPO_DIR}/engagements/${EID}"
[ -d "$ENG_DIR" ] || die "No existe engagements/${EID}/. Créalo (mkdir -p engagements/${EID}/{recon,exploit,loot,evidence,notes,report}) antes de aislarlo."

command -v da_banner >/dev/null 2>&1 && da_banner || true
if declare -f ensure_docker >/dev/null 2>&1; then
  ensure_docker || die "Docker no disponible; instálalo o revisa DEPLOY.md."
else
  command -v docker >/dev/null 2>&1 || die "Docker no disponible."
fi
docker image inspect data-attack:latest >/dev/null 2>&1 \
  || die "Falta la imagen data-attack:latest. Constrúyela: ./deploy/docker.sh build"

# Montajes MÍNIMOS (aislamiento por-engagement). El código del repo va HORNEADO en la imagen
# (rootfs read-only); aquí solo el engagement + el blackboard + scope congelado + RAG ro.
MOUNTS=(
  -v "${ENG_DIR}:/opt/data-attack/engagements/${EID}:rw"
  -v "${REPO_DIR}/rag:/opt/data-attack/rag:ro"
)
[ -f "${REPO_DIR}/contracts/scope.json" ] \
  && MOUNTS+=(-v "${REPO_DIR}/contracts/scope.json:/opt/data-attack/contracts/scope.json:ro")
[ -f "${REPO_DIR}/contracts/engagement.json" ] \
  && MOUNTS+=(-v "${REPO_DIR}/contracts/engagement.json:/opt/data-attack/contracts/engagement.json:rw")
if [ "$CLAUDE_AUTH" = "1" ]; then
  warnp "--claude-auth: se monta ~/.claude (login del operador) READ-ONLY en el anillo. Úsalo solo si"
  warnp "el contenedor debe pilotar Claude; recuerda que el código de cliente es contenido hostil."
  MOUNTS+=(-v "${HOME:-/root}/.claude:/root/.claude:ro")
fi

# Endurecimiento del anillo efímero.
HARDEN=(
  --rm
  --name "data-attack-eng-${EID}"
  --hostname "engagement-${EID}"
  --network "$NET"
  --read-only
  --tmpfs /tmp:rw,noexec,nosuid,size=256m
  --cap-drop ALL
  --security-opt no-new-privileges
  --pids-limit 512
  --memory 4g
  --cpus 2
  -w "/opt/data-attack"
)

echo "[*] Anillo efímero para engagement '${EID}'  (red=${NET}, claude-auth=${CLAUDE_AUTH})"
if [ "${#CMD[@]}" -gt 0 ]; then
  exec docker run "${HARDEN[@]}" "${MOUNTS[@]}" --entrypoint /bin/bash data-attack:latest -lc "$(printf '%q ' "${CMD[@]}")"
else
  exec docker run -it "${HARDEN[@]}" "${MOUNTS[@]}" --entrypoint /bin/bash data-attack:latest -l
fi
