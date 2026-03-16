# Office-AI Tools, Versions, Dependencies, and Usage

## 1. Project Structure

- backend: Node.js + Express + SQLite API server
- frontend: React + Vite dashboard UI
- python-scripts: RTSP detection, line crossing, face/person capture, posting events to backend

---

## 2. Runtime Tools and Versions

These are the versions currently used in this workspace environment.

### System/CLI

- Node.js: `v25.5.0`
- npm: `11.8.0`
- GStreamer (`gst-launch-1.0`): `1.28.0`

### Python (detector venv)

- Python: `3.12.10`
- numpy: `2.4.2`
- requests: `2.32.5`
- opencv-python (`cv2`): `4.10.0`
- ultralytics: `8.4.21`

---

## 3. Frontend Dependencies

File: `frontend/package.json`

### Dependencies

- react: `^18.2.0`
- react-dom: `^18.2.0`
- chart.js: `^4.4.0`

### Dev Dependencies

- vite: `^5.1.0`
- @vitejs/plugin-react: `^4.2.1`

### Purpose

- React: UI rendering
- Chart.js: usage visualization chart
- Vite: fast dev server and build tool

### Frontend Commands

```powershell
cd frontend
npm install
npm run dev
```

- Dev URL: `http://localhost:5173`
- Frontend reads dashboard data from backend endpoint:
  - `GET http://localhost:3000/api/dashboard`

---

## 4. Backend Dependencies

File: `backend/package.json`

### Dependencies

- express: `^4.18.2`
- cors: `^2.8.5`
- sqlite3: `^5.1.6`

### Purpose

- Express: REST API server
- CORS: allows frontend access from different port
- sqlite3: local database storage (`backend/data.db`)

### Backend Commands

```powershell
cd backend
npm install
npm start
```

- Backend URL: `http://localhost:3000`

### Main API Endpoints

- `GET /api/dashboard`
- `GET /api/employees`
- `POST /api/employees`
- `GET /api/entries`
- `POST /api/entries`
- `GET /api/usage`
- `POST /api/usage`

### Static Image Endpoints

- `/captures/crossings`
- `/captures/detections`
- `/captures/faces`

---

## 5. Python Scripts Dependencies

File: `python-scripts/requirements.txt`

### Required Packages (declared)

- numpy
- requests
- ultralytics

### Also Used by Current Scripts

- opencv-python (imported as `cv2`)
- GStreamer CLI (`gst-launch-1.0`) for stream pipeline fallback path

### Install Commands

```powershell
cd python-scripts
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If OpenCV is missing:

```powershell
.\.venv\Scripts\python.exe -m pip install opencv-python
```

---

## 6. What We Use and How (End-to-End Flow)

1. `line_counter.py` connects to RTSP stream.
2. YOLO (ultralytics) detects persons.
3. Tracker assigns object IDs and detects crossing over ROI line.
4. On crossing:
   - logs CSV event
   - saves crossing image(s)
   - saves face crop (or person fallback crop)
   - posts `in/out` event to backend (`/api/entries`) when `--post` is enabled
5. Backend stores entry in SQLite and serves dashboard API + image URLs.
6. Frontend polls dashboard API every few seconds and shows:
   - recent entries
   - usage charts
   - crossing images
   - detection snapshots
   - face crops

---

## 7. Python Script Usage (Important Commands)

### ROI setup (custom crossing line)

```powershell
cd python-scripts
.\.venv\Scripts\python.exe .\line_counter.py --url "rtsp://USER:PASS@HOST:554/cam/realmonitor?channel=2&subtype=0" --model .\yolov8n.pt --roi-setup --roi-file .\roi_cam2.json
```

- Left-drag: move ROI Y line
- Right-drag: set ROI X-range (door segment)
- Press `S` to save, `Q` to quit

### Run live detection with dashboard posting

```powershell
cd python-scripts
.\.venv\Scripts\python.exe .\line_counter.py --url "rtsp://admin:India123%23@192.168.2.103:554/cam/realmonitor?channe2=1&subtype=0" --model .\yolov8n.pt --conf 0.18 --roi-file .\roi_cam2.json --line-x-margin 120 --display --post --backend "http://localhost:3000/api/entries" --save-crops .\crossings --save-faces-only --crossing-only
```

Flags used above:

- `--display`: live window with overlays
- `--post`: send IN/OUT events to backend
- `--save-crops`: save crossing images
- `--save-faces-only`: prioritize face/person crops on crossing
- `--crossing-only`: disable periodic snapshots; save only on crossing events

---

## 8. Data and Artifacts

- Backend database: `backend/data.db`
- CSV logs: `python-scripts/events_*.csv`
- ROI config: `python-scripts/roi_cam2.json`
- ROI preview: `python-scripts/roi_cam2_preview.jpg`
- Crossing images: `python-scripts/crossings/`
- Face/person crops: `python-scripts/crossings/faces/`
- Periodic detections (if enabled): `python-scripts/crossings/detections/`

---

## 9. Notes

- RTSP passwords containing `#` should be URL-safe encoded (`%23`) when needed.
- Current pipeline automatically falls back to OpenCV capture if GStreamer frame read fails.
- Keep credentials out of source files; use environment variables or secure config in production.
