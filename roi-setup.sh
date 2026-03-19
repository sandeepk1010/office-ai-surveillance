#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v pm2 >/dev/null 2>&1; then
  pm2 stop detector-in >/dev/null 2>&1 || true
fi

if [[ -f "$ROOT_DIR/python-scripts/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "$ROOT_DIR/python-scripts/.env"
  set +a
fi

cd "$ROOT_DIR"

python3 python-scripts/line_counter.py \
  --url "${DETECTOR_RTSP_URL:-rtsp://admin:India123%23@192.168.2.103:554/cam/realmonitor?channel=2&subtype=0}" \
  --model "${DETECTOR_MODEL:-python-scripts/yolov8n.pt}" \
  --roi-file "${DETECTOR_ROI_FILE:-python-scripts/roi_cam2.json}" \
  --event-mode in \
  --line-x-margin "${DETECTOR_LINE_MARGIN:-120}" \
  --roi-setup

echo
echo "ROI setup finished. Restart detector with: pm2 restart detector-in"
