#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

activate_nvm_node() {
  local nvm_dir
  nvm_dir="${NVM_DIR:-$HOME/.nvm}"

  if [[ -s "$nvm_dir/nvm.sh" ]]; then
    # shellcheck source=/dev/null
    . "$nvm_dir/nvm.sh"
    if command -v nvm >/dev/null 2>&1; then
      nvm use --silent default >/dev/null 2>&1 || nvm use --silent 20 >/dev/null 2>&1 || true
    fi
  fi
}

activate_nvm_node

if ! command -v pm2 >/dev/null 2>&1; then
  echo "pm2 not found; nothing to stop via PM2."
  exit 0
fi

cd "$ROOT_DIR"

if pm2 describe backend >/dev/null 2>&1 || pm2 describe frontend >/dev/null 2>&1 || pm2 describe detector-in >/dev/null 2>&1 || pm2 describe detector-out >/dev/null 2>&1; then
  pm2 delete ecosystem.config.js >/dev/null 2>&1 || true
  echo "Stopped PM2 services from ecosystem.config.js"
else
  echo "No PM2 services from ecosystem.config.js are running."
fi

pm2 save >/dev/null 2>&1 || true
echo "Done."
