#!/usr/bin/env bash
# Start (or restart) the terminal web server in the background.
# Used by .devcontainer postAttachCommand; safe to run repeatedly.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8080}"
LOG="${TMPDIR:-/tmp}/pma-server.log"

# Stop any previous instance so a re-attach always serves the latest code.
if pkill -f "^python app.py --web" 2>/dev/null; then sleep 1; fi

PORT="$PORT" setsid nohup python app.py --web </dev/null >"$LOG" 2>&1 &
echo "PMA server starting on port $PORT (log: $LOG)"

for _ in $(seq 1 30); do
  if curl -fs -o /dev/null "http://localhost:$PORT/"; then
    echo "PMA ready:  / (options)   /futures (futures)"
    exit 0
  fi
  sleep 1
done
echo "Server did not become ready in 30s; last log lines:" >&2
tail -n 20 "$LOG" >&2
exit 1
