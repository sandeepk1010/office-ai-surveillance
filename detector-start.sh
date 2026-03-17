#!/bin/bash
set -e
cd /home/trinetra-jetson/office-ai-surveillance

# IN detector (channel 2 by default)
RTSP_URL="${DETECTOR_IN_RTSP_URL:-rtsp://admin:India123#@192.168.2.103:554/cam/realmonitor?channel=2&subtype=0}"
MODEL_PATH="${DETECTOR_IN_MODEL:-python-scripts/yolov8n.pt}"
ROI_FILE="${DETECTOR_IN_ROI_FILE:-python-scripts/roi_cam2.json}"
LINE_X_MARGIN="${DETECTOR_IN_LINE_X_MARGIN:-120}"
BACKEND_URL="${DETECTOR_IN_BACKEND:-http://localhost:3001/api/entries}"

exec /usr/bin/python3 -u python-scripts/line_counter.py \
  --url "$RTSP_URL" \
  --model "$MODEL_PATH" \
  --roi-file "$ROI_FILE" \
  --event-mode in \
  --line-x-margin "$LINE_X_MARGIN" \
  --backend "$BACKEND_URL" \
  --post \
  --save-crops python-scripts/crossings \
  --save-faces-only \
  --crossing-only
