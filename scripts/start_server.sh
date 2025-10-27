#!/usr/bin/env bash
set -euo pipefail

# Launches the FeatherFlap diagnostics server inside the repo's virtualenv.
# Creates a PID file so scripts/stop_server.sh can terminate the background process.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

PID_DIR="$REPO_ROOT/.run"
PID_FILE="$PID_DIR/featherflap.pid"
LOG_FILE="${FEATHERFLAP_LOG_FILE:-$REPO_ROOT/featherflap.log}"
VENV_PATH="$REPO_ROOT/.venv"

mkdir -p "$PID_DIR"

if [ -f "$PID_FILE" ]; then
    EXISTING_PID="$(cat "$PID_FILE")"
    if kill -0 "$EXISTING_PID" 2>/dev/null; then
        echo "FeatherFlap server already running (PID $EXISTING_PID). Stop it first." >&2
        exit 1
    fi
    echo "Removing stale PID file."
    rm -f "$PID_FILE"
fi

if [ -f "$REPO_ROOT/.env" ]; then
    # shellcheck disable=SC1091
    set -a
    source "$REPO_ROOT/.env"
    set +a
fi

if [ ! -f "$VENV_PATH/bin/activate" ]; then
    echo "Virtual environment not found at $VENV_PATH. Run 'python -m venv .venv' first." >&2
    exit 1
fi

# shellcheck disable=SC1091
source "$VENV_PATH/bin/activate"

HOST="${FEATHERFLAP_HOST:-0.0.0.0}"
PORT="${FEATHERFLAP_PORT:-8000}"

DEFAULT_CMD=(featherflap serve --host "$HOST" --port "$PORT")
if [ "$#" -gt 0 ]; then
    CMD=(featherflap "$@")
else
    CMD=("${DEFAULT_CMD[@]}")
fi

echo "Starting FeatherFlap server: ${CMD[*]}"
echo "Logs: $LOG_FILE"

nohup "${CMD[@]}" >> "$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

echo "FeatherFlap server running in background (PID $SERVER_PID)."
