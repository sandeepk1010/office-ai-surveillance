# Office Entry/Exit & Employee Mobile Usage Monitor

This is a minimal fullstack prototype with:
- Express + PostgreSQL backend
- React + Vite frontend dashboard

Quick start (Linux/macOS/WSL):

1. Start backend on port `3001`

```bash
cd backend
npm install
PORT=3001 npm start
```

2. Start frontend (Vite on `5173`)

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

3. Open `http://localhost:5173`

One-command helpers (from project root):

```bash
./start-all.sh
./check-health.sh
./stop-all.sh
```

Dual camera entry/exit (recommended):

- `channel=2` can stay dedicated for `IN` detection via `detector-start.sh`.
- A second camera can run as `OUT` detection via `detector-start-out.sh`.

Systemd setup for both detectors:

```bash
# IN detector (existing)
sudo cp office-ai-detector.service /etc/systemd/system/

# OUT detector (new)
sudo cp office-ai-detector-out.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now office-ai-detector
sudo systemctl enable --now office-ai-detector-out
```

Configure OUT camera URL/ROI without editing code:

```bash
sudo cp office-ai-detector.env.example /etc/default/office-ai-detector
sudo cp office-ai-detector-out.env.example /etc/default/office-ai-detector-out
sudo nano /etc/default/office-ai-detector-out
sudo systemctl restart office-ai-detector office-ai-detector-out
```

Local run with `start-all.sh`:

```bash
DETECTOR_OUT_ENABLED=true \
DETECTOR_OUT_RTSP_URL='rtsp://admin:India123%23@YOUR_OUT_CAM_IP:554/cam/realmonitor?channel=1&subtype=0' \
DETECTOR_OUT_ROI_FILE='python-scripts/roi_cam_out.json' \
./start-all.sh
```

Environment files:
- `backend/.env.example` contains `PORT=3001`
- `frontend/.env` and `frontend/.env.example` contain `VITE_API_BASE_URL=http://localhost:3001`

Windows (PowerShell) backend example:

```powershell
cd backend
npm install
$env:PORT='3001'
npm start
```

Endpoints:
- `GET /api/dashboard` — aggregated employees, recent entries, top app usage
- `GET /api/employees` — list employees
- `POST /api/employees` — add employee { name, mobile }
- `GET /api/entries` — recent entries
- `POST /api/entries` — add entry { employee_id, type }
- `GET /api/usage` — usage records
- `POST /api/usage` — add usage { employee_id, app, duration_minutes }

Next steps I can help with:
- Add authentication and role-based access
- Persist to PostgreSQL and add migrations
- Build a React/Vite frontend with richer UI and filtering
