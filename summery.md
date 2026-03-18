# Office AI Surveillance - Session Summery

Date: 2026-03-17
Workspace: `/home/trinetra-jetson/office-ai-surveillance`

## 1. What You Asked (Chronological)

1. Keep channel 2 as IN camera; OUT camera support can be added later.
2. Focus on IN only because OUT camera is not mounted yet.
3. Show live detection feed.
4. Adjust ROI/line and face ROI box position.
5. Fix missed IN detections.
6. Show full images in detections panel (crossing-only mode had no periodic detections).
7. Reduce multiple false face boxes.
8. Add unknown person management with face capture ID/image.
9. Avoid duplicate entry events.
10. Set new ROI line and verify loaded values.
11. Check ROI line status.
12. Clean duplicate detector processes.
13. Explain GStreamer pipeline and code.
14. Separate GStreamer frame-source code into a different file.
15. Check how many cameras currently use GStreamer.
16. Check whether current run uses CPU or GPU.
17. Ask how to shift inference to GPU.
18. Ask to create this `summery.md` with full reference context.

## 2. Major Code Changes Made

### Detector startup + services
- `detector-start.sh`
  - Added configurable face recognition flags.
  - Added configurable inference device flag (`DETECTOR_IN_DEVICE`, default `auto`).
- `start-all.sh`
  - Added face recognition env controls.
  - Added detector device env control (`DETECTOR_DEVICE`, default `auto`).
- `office-ai-detector.service`
  - Uses `detector-start.sh`; optional env file support remains.
- `office-ai-detector-out.service` and `detector-start-out.sh`
  - OUT camera scaffolding exists, but OUT remains disabled/inactive as requested.

### Python detector
- `python-scripts/line_counter.py`
  - Face filtering tightened to reduce false positives.
  - One-to-one tracker matching improved.
  - Duplicate crossing suppression added (time + distance window).
  - Event payload expanded with `face_image`.
  - Face recognition flow enabled and used for employee mapping.
  - Added inference device support:
    - CLI arg: `--device auto|cpu|cuda|cuda:0`
    - Logs selected device at startup.
- `python-scripts/frame_sources.py` (new)
  - Extracted from `line_counter.py`:
    - `resolve_gst_launch_bin`
    - `GStreamerFrameSource`
    - `GStreamerCliFrameSource`
    - `OpenCVFrameSource`

### ROI
- `python-scripts/roi_cam2.json`
  - Multiple adjustments done over session.
  - Current values seen in recent logs:
    - `line_fraction ~ 0.4958`
    - runtime `line_y ~ 356`
    - x-range `[664, 1011]`
  - Face ROI updated to approximately:
    - x1=690, y1=109, x2=994, y2=432

### Backend
- `backend/index.js`
  - `entries.face_image` support added in schema/API/selects.
  - Dashboard now includes `face_image` in entries/todayEntries.
  - Health API improved:
    - GStreamer now stays `ok` if frames are flowing and no OpenCV fallback is active, even when startup log line is older than journal window.

### Frontend
- `frontend/src/App.jsx`
  - Detections panel updated to show crossing images when crossing-only mode is enabled.
  - Unknown Person Management now shows captured face ID/image and thumbnail link.

## 3. Data / Mapping Changes

- Known faces folder detected:
  - `python-scripts/known_faces/Aakash/Akash.jpg`
  - `python-scripts/known_faces/Sandeep/sandeep.jpg`
- Added missing employee rows for recognition mapping:
  - `Aakash` (id created: 421)
  - `Sandeep` (id created: 422)

Reason: if a known-face folder name does not match backend employee names, recognition may still appear as unknown/guest due to missing employee mapping.

## 4. Runtime Findings and Diagnostics

### GStreamer
- Active detector logs show:
  - `[GStreamer] Pipeline PLAYING with hardware (nvv4l2decoder)`
- This confirms Jetson hardware decode path is active for video ingest.

### Camera usage
- Current active stream is IN camera on channel 2.
- OUT detector service is inactive.

### CPU vs GPU status
- PyTorch check result:
  - `torch_version = 2.10.0+cpu`
  - `torch.version.cuda = None`
  - `torch.cuda.is_available() = False`
- Conclusion:
  - Decode path: GPU-accelerated (GStreamer nvv4l2decoder)
  - YOLO inference path: CPU (no CUDA-enabled torch installed)

## 5. Process Cleanup History

- Duplicate detector processes appeared multiple times during tests (service + manual runs).
- Cleanup performed using service stop/start + `pkill` to restore single managed process.
- Recommendation: use only systemd service (`office-ai-detector`) for normal operation to avoid duplicate events/resource contention.

## 6. Commands Used (Reference)

Below are representative and important commands executed during this session.

### App/service control
- `./start-all.sh`
- `./stop-all.sh && ./start-all.sh`
- `sudo systemctl stop office-ai-detector`
- `sudo systemctl start office-ai-detector`
- `sudo systemctl restart office-ai-detector`
- `sudo systemctl status office-ai-detector --no-pager`
- `sudo systemctl is-active office-ai-detector`

### Detector process checks
- `ps -ef | grep 'line_counter.py' | grep -v grep`
- `pkill -f 'line_counter.py'`

### Logs/health
- `./check-health.sh`
- `curl -sS http://localhost:3001/api/health`
- `curl -sS http://localhost:3001/api/entries`
- `sudo journalctl -u office-ai-detector --since '... ago' --no-pager`
- `sudo journalctl -u office-ai-detector --since '... ago' --no-pager | grep -E 'Loaded saved ROI|ROI line at y=|Event mode:'`

### Camera/network checks
- `ping -c 2 192.168.2.103 && (nc -zv 192.168.2.103 554 || true)`
- `ffplay -rtsp_transport tcp -fflags nobuffer -flags low_delay -framedrop -sync ext -an -window_title "Office Cam Live" "rtsp://...channel=2..."`

### Manual detector runs
- `python3 python-scripts/line_counter.py --url "rtsp://...channel=2..." --model python-scripts/yolov8n.pt --roi-file python-scripts/roi_cam2.json --event-mode in --line-x-margin 120 --backend http://localhost:3001/api/entries --post --save-crops python-scripts/crossings --save-faces-only --crossing-only`
- `python3 python-scripts/line_counter.py --url "rtsp://...channel=2&subtype=1" --model python-scripts/yolov8n.pt --roi-file python-scripts/roi_cam2.json --event-mode in --line-x-margin 120 --display --crossing-only`
- ROI interactive mode:
  - `python3 python-scripts/line_counter.py --url "rtsp://...channel=2&subtype=1" --model python-scripts/yolov8n.pt --roi-file python-scripts/roi_cam2.json --event-mode in --line-x-margin 120 --roi-setup`

### Backend/frontend
- `cd backend && PORT=3001 npm start`
- `cd frontend && npm run dev -- --host 0.0.0.0 --port 5173`
- `netstat -tulnp 2>/dev/null | grep ':3000\|:5173'`

### Validation
- `python3 -m py_compile python-scripts/line_counter.py`
- `python3 -m py_compile python-scripts/line_counter.py python-scripts/frame_sources.py`
- `node --check backend/index.js`

### GPU checks
- `python3 - <<'PY' ... import torch; print(torch.__version__); print(torch.cuda.is_available()) ... PY`

## 7. Current Known State (At Time of This File)

- IN detector service: active.
- OUT detector service: inactive.
- Camera stream: channel 2.
- GStreamer decode: hardware (`nvv4l2decoder`).
- YOLO inference: CPU (CUDA torch not installed).
- Face recognition: enabled in startup scripts.
- `line_counter.py` now supports `--device` for future GPU forcing.

## 8. Next Actions To Move Inference to GPU

1. Install CUDA-enabled PyTorch matching Jetson JetPack/L4T.
2. Set device env for detector service:
   - create `/etc/default/office-ai-detector` with `DETECTOR_IN_DEVICE=cuda:0`
3. Restart service:
   - `sudo systemctl restart office-ai-detector`
4. Verify:
   - `python3 -c "import torch; print(torch.cuda.is_available())"`
   - check detector logs for selected YOLO device.

---
This file is intended as handoff context so another tool/agent can continue without losing session history.
