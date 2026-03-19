#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT_DIR/python-scripts/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "$ROOT_DIR/python-scripts/.env"
  set +a
fi

if [[ "${DETECTOR_OUT_ENABLED:-false}" != "true" ]]; then
  echo "OUT detector disabled (DETECTOR_OUT_ENABLED=false)."
  exit 0
fi

EXTRA_ARGS=()
if [[ "${DETECTOR_OUT_GSTREAMER_ONLY:-false}" == "true" ]]; then
  EXTRA_ARGS+=(--gstreamer-only)
fi

cd "$ROOT_DIR"
exec python3 python-scripts/line_counter.py \
  --url "${DETECTOR_OUT_RTSP_URL:-rtsp://admin:India123%23@192.168.2.103:554/cam/realmonitor?channel=1&subtype=0}" \
  --model "${DETECTOR_OUT_MODEL:-$ROOT_DIR/python-scripts/yolov8n.pt}" \
  --roi-file "${DETECTOR_OUT_ROI_FILE:-$ROOT_DIR/python-scripts/roi_cam_out.json}" \
  --event-mode out \
  --line-x-margin "${DETECTOR_OUT_LINE_MARGIN:-120}" \
  --backend "${DETECTOR_OUT_BACKEND:-http://localhost:3001/api/entries}" \
  --post \
  --save-crops python-scripts/crossings \
  --save-faces-only \
  --crossing-only \
  "${EXTRA_ARGS[@]}"
