#!/usr/bin/env bash
# Start the terminal web server detached + supervised (auto-restart on crash).
#   start_server.sh            restart with the latest code (default)
#   start_server.sh --ensure   no-op if already healthy, else start
# Used by .devcontainer postStartCommand/postAttachCommand; safe to run repeatedly.
set -uo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8080}"
LOG="${TMPDIR:-/tmp}/pma-server.log"
healthy() { curl -fs -m 2 -o /dev/null "http://localhost:$PORT/"; }

if [[ "${1:-}" == "--ensure" ]] && healthy; then
  echo "PMA already running on port $PORT"; exit 0
fi

# Stop previous supervisor + server (anchored patterns: never match this shell).
pkill -f "^bash .*run_supervised.sh" 2>/dev/null
pkill -f "^python app.py --web" 2>/dev/null
sleep 1

PORT="$PORT" setsid nohup bash scripts/run_supervised.sh </dev/null >"$LOG" 2>&1 &
echo "PMA server starting on port $PORT (log: $LOG)"

for _ in $(seq 1 60); do
  if healthy; then
    echo "PMA ready:  /  (options)   /futures   /portfolio"
    exit 0
  fi
  sleep 0.5
done
echo "Server did not become ready in 30s; last log lines:" >&2
tail -n 20 "$LOG" >&2
exit 1
