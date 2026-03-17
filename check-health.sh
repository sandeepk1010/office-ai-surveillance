#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-3001}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_URL="${BACKEND_URL:-http://localhost:${BACKEND_PORT}/api/dashboard}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:${FRONTEND_PORT}}"

ok=true

check_port() {
  local port="$1"
  local name="$2"
  if ss -ltn 2>/dev/null | grep -qE ":$port\\b"; then
    echo "[OK] $name port $port is listening"
  else
    echo "[FAIL] $name port $port is not listening"
    ok=false
  fi
}

check_http() {
  local url="$1"
  local name="$2"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$url" || true)"
  if [[ "$code" == "200" ]]; then
    echo "[OK] $name endpoint responded with HTTP 200"
  else
    echo "[FAIL] $name endpoint returned HTTP $code"
    ok=false
  fi
}

check_port "$BACKEND_PORT" "Backend"
check_port "$FRONTEND_PORT" "Frontend"
check_http "$BACKEND_URL" "Backend"
check_http "$FRONTEND_URL" "Frontend"

if [[ "$ok" == true ]]; then
  echo "Health check passed."
  exit 0
fi

echo "Health check failed."
exit 1
