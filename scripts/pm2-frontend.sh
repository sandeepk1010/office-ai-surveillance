#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT_DIR/frontend/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "$ROOT_DIR/frontend/.env"
  set +a
fi

FRONTEND_PORT="${FRONTEND_PORT:-5173}"

cd "$ROOT_DIR/frontend"
exec npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" --strictPort
