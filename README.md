# Office Entry/Exit & Employee Mobile Usage Monitor

This is a minimal fullstack prototype: an Express + SQLite backend and a static frontend dashboard.

Quick start (Windows):

1. Install backend dependencies

```powershell
cd backend
npm install
npm start
```

2. Open the frontend: open `frontend/index.html` in your browser (double-click or use `start`)

Optional: Serve the `frontend` directory with a static server (e.g., `npx serve frontend`) if needed.

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
