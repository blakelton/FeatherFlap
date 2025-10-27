#!/usr/bin/env bash
set -euo pipefail

# Stops the FeatherFlap diagnostics server, whether it was launched via
# scripts/start_server.sh or managed by systemd.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$REPO_ROOT/.run/featherflap.pid"
SERVICE_NAME="featherflap.service"
SYSTEMCTL_BIN="$(command -v systemctl || true)"

if [ -n "$SYSTEMCTL_BIN" ]; then
    if "$SYSTEMCTL_BIN" is-active --quiet "$SERVICE_NAME"; then
        echo "Stopping systemd unit $SERVICE_NAME..."
        sudo "$SYSTEMCTL_BIN" stop "$SERVICE_NAME"
        if "$SYSTEMCTL_BIN" is-active --quiet "$SERVICE_NAME"; then
            echo "Failed to stop $SERVICE_NAME via systemd. Check service logs." >&2
            exit 1
        fi
        echo "Systemd service stopped."
        exit 0
    fi
fi

if [ ! -f "$PID_FILE" ]; then
    echo "No PID file found at $PID_FILE. Is the server running?" >&2
    exit 1
fi

SERVER_PID="$(cat "$PID_FILE")"

if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "No running process with PID $SERVER_PID. Removing stale PID file."
    rm -f "$PID_FILE"
    exit 0
fi

echo "Stopping FeatherFlap server (PID $SERVER_PID)..."
kill "$SERVER_PID"

for _ in {1..10}; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        rm -f "$PID_FILE"
        echo "Server stopped."
        exit 0
    fi
    sleep 1
done

echo "Server did not exit after 10s; sending SIGKILL."
kill -9 "$SERVER_PID" 2>/dev/null || true
rm -f "$PID_FILE"
echo "Server force-stopped."
