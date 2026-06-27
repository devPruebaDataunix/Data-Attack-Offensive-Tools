#!/usr/bin/env bash
# =============================================================================
#  deploy/dash.sh — Lanza el panel de control TUI (Textual) con el venv del bot.
#  El panel es el gemelo LOCAL del bot de Telegram: mismo cerebro (bot/intel) y
#  las MISMAS puertas (scope_guard + aprobación humana + C11-C19).
#    ./deploy/dash.sh
# =============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PY="${REPO_DIR}/bot/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then echo "[ERR] No encuentro Python. Despliega el entorno (deploy/setup.sh)."; exit 1; fi

# El paquete tui vive en bot/ y reusa 'intel'; se arranca con cwd=bot.
cd "${REPO_DIR}/bot" && exec "$PY" -m tui
