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

require_command() {
  local cmd="$1"
  local hint="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}"
    printf "%b\n" "$hint"
    exit 127
  fi
}

activate_nvm_node

require_command "node" "Install Node.js 18+ and retry ./start-all.sh"
require_command "npm" "Install npm and retry ./start-all.sh"
require_command "pm2" "Install PM2 and retry:\n  npm install -g pm2"
require_command "python3" "Install Python 3 and retry ./start-all.sh"

cd "$ROOT_DIR"

pm2 start ecosystem.config.js
pm2 save

echo "PM2 services started."
echo "View status: pm2 status"
echo "View logs  : pm2 logs"
echo "Live monitor: pm2 monit"
