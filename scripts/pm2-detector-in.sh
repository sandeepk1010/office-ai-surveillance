#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -f "$ROOT_DIR/python-scripts/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "$ROOT_DIR/python-scripts/.env"
  set +a
fi

if [[ "${DETECTOR_ENABLED:-true}" != "true" ]]; then
  echo "Detector disabled (DETECTOR_ENABLED=false)."
  exit 0
fi

EXTRA_ARGS=()
if [[ "${DETECTOR_GSTREAMER_ONLY:-true}" == "true" ]]; then
  EXTRA_ARGS+=(--gstreamer-only)
fi
if [[ "${DETECTOR_FACE_RECOGNITION:-true}" == "true" ]]; then
  EXTRA_ARGS+=(
    --face-recognition
    --face-db-dir "${DETECTOR_FACE_DB_DIR:-$ROOT_DIR/python-scripts/known_faces}"
    --employee-api "${DETECTOR_EMPLOYEE_API:-http://localhost:3001/api/employees}"
    --face-match-threshold "${DETECTOR_FACE_MATCH_THRESHOLD:-0.45}"
  )
fi

cd "$ROOT_DIR"
exec python3 python-scripts/line_counter.py \
  --url "${DETECTOR_RTSP_URL:-rtsp://admin:India123%23@192.168.2.103:554/cam/realmonitor?channel=2&subtype=0}" \
  --model "${DETECTOR_MODEL:-$ROOT_DIR/python-scripts/yolov8n.pt}" \
  --roi-file "${DETECTOR_ROI_FILE:-$ROOT_DIR/python-scripts/roi_cam2.json}" \
  --event-mode in \
  --device "${DETECTOR_DEVICE:-cuda:0}" \
  --yolo-imgsz "${DETECTOR_YOLO_IMGSZ:-640}" \
  --yolo-half "${DETECTOR_YOLO_HALF:-auto}" \
  --line-x-margin "${DETECTOR_LINE_MARGIN:-120}" \
  --backend "${DETECTOR_BACKEND:-http://localhost:3001/api/entries}" \
  --post \
  --save-crops python-scripts/crossings \
  --save-faces-only \
  --crossing-only \
  "${EXTRA_ARGS[@]}"
