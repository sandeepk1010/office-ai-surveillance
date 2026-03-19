#!/bin/bash
set -e
cd /home/trinetra-jetson/office-ai-surveillance

# OUT detector (set DETECTOR_OUT_RTSP_URL to your new OUT camera)
RTSP_URL="${DETECTOR_OUT_RTSP_URL:-rtsp://admin:India123%23@192.168.2.103:554/cam/realmonitor?channel=1&subtype=0}"
MODEL_PATH="${DETECTOR_OUT_MODEL:-python-scripts/yolov8n.pt}"
ROI_FILE="${DETECTOR_OUT_ROI_FILE:-python-scripts/roi_cam_out.json}"
LINE_X_MARGIN="${DETECTOR_OUT_LINE_X_MARGIN:-120}"
BACKEND_URL="${DETECTOR_OUT_BACKEND:-http://localhost:3001/api/entries}"
DEVICE="${DETECTOR_OUT_DEVICE:-cuda:0}"
YOLO_IMGSZ="${DETECTOR_OUT_YOLO_IMGSZ:-640}"
YOLO_HALF="${DETECTOR_OUT_YOLO_HALF:-auto}"
GSTREAMER_ONLY="${DETECTOR_OUT_GSTREAMER_ONLY:-true}"

EXTRA_ARGS=()
if [[ "${GSTREAMER_ONLY}" == "true" ]]; then
  EXTRA_ARGS+=(--gstreamer-only)
fi

exec /usr/bin/python3 -u python-scripts/line_counter.py \
  --url "$RTSP_URL" \
  --model "$MODEL_PATH" \
  --roi-file "$ROI_FILE" \
  --event-mode out \
  --device "$DEVICE" \
  --yolo-imgsz "$YOLO_IMGSZ" \
  --yolo-half "$YOLO_HALF" \
  --line-x-margin "$LINE_X_MARGIN" \
  --backend "$BACKEND_URL" \
  --post \
  --save-crops python-scripts/crossings \
  --save-faces-only \
  --crossing-only \
  "${EXTRA_ARGS[@]}"
