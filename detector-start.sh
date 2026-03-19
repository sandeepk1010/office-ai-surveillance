#!/bin/bash
set -e
cd /home/trinetra-jetson/office-ai-surveillance

# IN detector (channel 2 by default)
RTSP_URL="${DETECTOR_IN_RTSP_URL:-rtsp://admin:India123%23@192.168.2.103:554/cam/realmonitor?channel=2&subtype=0}"
MODEL_PATH="${DETECTOR_IN_MODEL:-python-scripts/yolov8n.pt}"
ROI_FILE="${DETECTOR_IN_ROI_FILE:-python-scripts/roi_cam2.json}"
LINE_X_MARGIN="${DETECTOR_IN_LINE_X_MARGIN:-120}"
BACKEND_URL="${DETECTOR_IN_BACKEND:-http://localhost:3001/api/entries}"
DEVICE="${DETECTOR_IN_DEVICE:-auto}"
FACE_DB_DIR="${DETECTOR_IN_FACE_DB_DIR:-python-scripts/known_faces}"
EMPLOYEE_API="${DETECTOR_IN_EMPLOYEE_API:-http://localhost:3001/api/employees}"
FACE_MATCH_THRESHOLD="${DETECTOR_IN_FACE_MATCH_THRESHOLD:-0.45}"
FACE_RECOGNITION_ENABLED="${DETECTOR_IN_FACE_RECOGNITION_ENABLED:-true}"

FACE_RECOGNITION_ARGS=()
if [[ "${FACE_RECOGNITION_ENABLED}" == "true" ]]; then
  FACE_RECOGNITION_ARGS+=(
    --face-recognition
    --face-db-dir "$FACE_DB_DIR"
    --employee-api "$EMPLOYEE_API"
    --face-match-threshold "$FACE_MATCH_THRESHOLD"
  )
fi

exec /usr/bin/python3 -u python-scripts/line_counter.py \
  --url "$RTSP_URL" \
  --model "$MODEL_PATH" \
  --roi-file "$ROI_FILE" \
  --event-mode in \
  --device "$DEVICE" \
  --line-x-margin "$LINE_X_MARGIN" \
  --backend "$BACKEND_URL" \
  --post \
  --save-crops python-scripts/crossings \
  --save-faces-only \
  --crossing-only \
  "${FACE_RECOGNITION_ARGS[@]}"
