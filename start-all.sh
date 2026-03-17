#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-3001}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
API_BASE_URL="${VITE_API_BASE_URL:-http://localhost:${BACKEND_PORT}}"

# Detector configuration
DETECTOR_ENABLED="${DETECTOR_ENABLED:-true}"
DETECTOR_RTSP_URL="${DETECTOR_RTSP_URL:-rtsp://admin:India123%23@192.168.2.103:554/cam/realmonitor?channel=2&subtype=0}"
DETECTOR_MODEL="${DETECTOR_MODEL:-${ROOT_DIR}/python-scripts/yolov8n.pt}"
DETECTOR_ROI_FILE="${DETECTOR_ROI_FILE:-${ROOT_DIR}/python-scripts/roi_cam2.json}"
DETECTOR_LINE_MARGIN="${DETECTOR_LINE_MARGIN:-120}"
DETECTOR_BACKEND="${DETECTOR_BACKEND:-http://localhost:${BACKEND_PORT}/api/entries}"
DETECTOR_GSTREAMER_ONLY="${DETECTOR_GSTREAMER_ONLY:-false}"

# Optional OUT detector (second camera)
DETECTOR_OUT_ENABLED="${DETECTOR_OUT_ENABLED:-false}"
DETECTOR_OUT_RTSP_URL="${DETECTOR_OUT_RTSP_URL:-rtsp://admin:India123%23@192.168.2.103:554/cam/realmonitor?channel=1&subtype=0}"
DETECTOR_OUT_MODEL="${DETECTOR_OUT_MODEL:-${ROOT_DIR}/python-scripts/yolov8n.pt}"
DETECTOR_OUT_ROI_FILE="${DETECTOR_OUT_ROI_FILE:-${ROOT_DIR}/python-scripts/roi_cam_out.json}"
DETECTOR_OUT_LINE_MARGIN="${DETECTOR_OUT_LINE_MARGIN:-120}"
DETECTOR_OUT_BACKEND="${DETECTOR_OUT_BACKEND:-http://localhost:${BACKEND_PORT}/api/entries}"
DETECTOR_OUT_GSTREAMER_ONLY="${DETECTOR_OUT_GSTREAMER_ONLY:-false}"

is_port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -qE ":${port}\\b"
    return $?
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  return 1
}

cleanup() {
  echo
  echo "Stopping services..."
  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [[ -n "${DETECTOR_PID:-}" ]] && kill -0 "$DETECTOR_PID" 2>/dev/null; then
    kill "$DETECTOR_PID" 2>/dev/null || true
  fi
  if [[ -n "${DETECTOR_OUT_PID:-}" ]] && kill -0 "$DETECTOR_OUT_PID" 2>/dev/null; then
    kill "$DETECTOR_OUT_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

if is_port_in_use "$BACKEND_PORT"; then
  echo "Port ${BACKEND_PORT} is already in use."
  echo "Run ./stop-all.sh first, then retry ./start-all.sh."
  exit 1
fi

if is_port_in_use "$FRONTEND_PORT"; then
  echo "Port ${FRONTEND_PORT} is already in use."
  echo "Run ./stop-all.sh first, then retry ./start-all.sh."
  exit 1
fi

echo "Starting backend on port ${BACKEND_PORT}..."
(
  cd "$ROOT_DIR/backend"
  PORT="$BACKEND_PORT" npm start
) &
BACKEND_PID=$!

echo "Starting frontend on port ${FRONTEND_PORT} (API: ${API_BASE_URL})..."
(
  cd "$ROOT_DIR/frontend"
  VITE_API_BASE_URL="$API_BASE_URL" npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" --strictPort
) &
FRONTEND_PID=$!

echo

if [[ "$DETECTOR_ENABLED" == "true" ]]; then
  echo "Starting detector (RTSP: ${DETECTOR_RTSP_URL%'?'*}...)..."
  (
    cd "$ROOT_DIR"
    EXTRA_ARGS=()
    if [[ "$DETECTOR_GSTREAMER_ONLY" == "true" ]]; then
      EXTRA_ARGS+=(--gstreamer-only)
      echo "Detector mode: GStreamer-only"
    else
      echo "Detector mode: GStreamer + OpenCV fallback"
    fi

    python3 python-scripts/line_counter.py \
      --url "$DETECTOR_RTSP_URL" \
      --model "$DETECTOR_MODEL" \
      --roi-file "$DETECTOR_ROI_FILE" \
      --event-mode in \
      --line-x-margin "$DETECTOR_LINE_MARGIN" \
      --backend "$DETECTOR_BACKEND" \
      --post \
      --save-crops python-scripts/crossings \
      --save-faces-only \
      --crossing-only \
      "${EXTRA_ARGS[@]}"
  ) &
  DETECTOR_PID=$!
else
  echo "Detector disabled (set DETECTOR_ENABLED=true to enable)."
fi

if [[ "$DETECTOR_OUT_ENABLED" == "true" ]]; then
  echo "Starting OUT detector (RTSP: ${DETECTOR_OUT_RTSP_URL%'?'*}...)..."
  (
    cd "$ROOT_DIR"
    EXTRA_OUT_ARGS=()
    if [[ "$DETECTOR_OUT_GSTREAMER_ONLY" == "true" ]]; then
      EXTRA_OUT_ARGS+=(--gstreamer-only)
      echo "OUT detector mode: GStreamer-only"
    else
      echo "OUT detector mode: GStreamer + OpenCV fallback"
    fi

    python3 python-scripts/line_counter.py \
      --url "$DETECTOR_OUT_RTSP_URL" \
      --model "$DETECTOR_OUT_MODEL" \
      --roi-file "$DETECTOR_OUT_ROI_FILE" \
      --event-mode out \
      --line-x-margin "$DETECTOR_OUT_LINE_MARGIN" \
      --backend "$DETECTOR_OUT_BACKEND" \
      --post \
      --save-crops python-scripts/crossings \
      --save-faces-only \
      --crossing-only \
      "${EXTRA_OUT_ARGS[@]}"
  ) &
  DETECTOR_OUT_PID=$!
else
  echo "OUT detector disabled (set DETECTOR_OUT_ENABLED=true to enable)."
fi

echo

echo "Frontend: http://localhost:${FRONTEND_PORT}"
echo "Backend : http://localhost:${BACKEND_PORT}"
echo "Press Ctrl+C to stop all services."

wait -n "$BACKEND_PID" "$FRONTEND_PID"
status=$?
echo "One of the services exited (status=${status}). Stopping other services."
exit "$status"
