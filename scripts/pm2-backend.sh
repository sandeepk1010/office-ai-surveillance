#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT_DIR/backend/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "$ROOT_DIR/backend/.env"
  set +a
fi

cd "$ROOT_DIR/backend"
exec npm start
