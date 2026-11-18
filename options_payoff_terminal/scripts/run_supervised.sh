#!/usr/bin/env bash
# Keep the web server alive: restart it if it ever exits/crashes.
cd "$(dirname "$0")/.."
export PORT="${PORT:-8080}"
while true; do
  python app.py --web
  echo "[supervisor] server exited ($?), restarting in 2s" >&2
  sleep 2
done
