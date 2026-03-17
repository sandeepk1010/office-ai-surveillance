#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-3001}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

kill_port() {
  local port="$1"
  local pids=""

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  elif command -v ss >/dev/null 2>&1; then
    pids="$(ss -ltnp 2>/dev/null | grep -E ":$port\\b" | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | sort -u || true)"
  fi

  if [[ -z "$pids" ]]; then
    echo "No listener found on port $port"
    return
  fi

  echo "Stopping processes on port $port: $pids"
  for pid in $pids; do
    kill "$pid" 2>/dev/null || true
  done
}

kill_port "$BACKEND_PORT"
kill_port "$FRONTEND_PORT"

echo "Stop request sent for backend/frontend ports."
