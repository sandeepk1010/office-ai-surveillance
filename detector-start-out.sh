#!/bin/bash
set -e
cd /home/trinetra-jetson/office-ai-surveillance

# OUT detector (set DETECTOR_OUT_RTSP_URL to your new OUT camera)
RTSP_URL="${DETECTOR_OUT_RTSP_URL:-rtsp://admin:India123#@192.168.2.103:554/cam/realmonitor?channel=1&subtype=0}"
MODEL_PATH="${DETECTOR_OUT_MODEL:-python-scripts/yolov8n.pt}"
ROI_FILE="${DETECTOR_OUT_ROI_FILE:-python-scripts/roi_cam_out.json}"
LINE_X_MARGIN="${DETECTOR_OUT_LINE_X_MARGIN:-120}"
BACKEND_URL="${DETECTOR_OUT_BACKEND:-http://localhost:3001/api/entries}"

exec /usr/bin/python3 -u python-scripts/line_counter.py \
  --url "$RTSP_URL" \
  --model "$MODEL_PATH" \
  --roi-file "$ROI_FILE" \
  --event-mode out \
  --line-x-margin "$LINE_X_MARGIN" \
  --backend "$BACKEND_URL" \
  --post \
  --save-crops python-scripts/crossings \
  --save-faces-only \
  --crossing-only
