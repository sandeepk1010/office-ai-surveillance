const express = require('express');
const cors = require('cors');
const { Pool } = require('pg');
const path = require('path');
const fs = require('fs');

const DATABASE_URL = process.env.DATABASE_URL || 'postgresql://postgres:postgres@localhost:5432/office_ai';
const pool = new Pool({ connectionString: DATABASE_URL });
const CROSSINGS_DIR = path.join(__dirname, '..', 'python-scripts', 'crossings');
const DETECTIONS_DIR = path.join(CROSSINGS_DIR, 'detections');
const FACES_DIR = path.join(CROSSINGS_DIR, 'faces');

const DUMMY_EMPLOYEES = [
  ['EMP001', 'Arun Kumar', 'Engineering', '9876501001', '1993-03-20', '2019-03-25', false, null],
  ['EMP002', 'Priya Nair', 'HR', '9876501002', '1994-03-24', '2020-04-02', false, null],
  ['EMP003', 'Ravi Shankar', 'Security', '9876501003', '1990-03-28', '2018-03-30', false, null],
  ['EMP004', 'Meera Joseph', 'Operations', '9876501004', '1992-04-01', '2021-04-05', false, null],
  ['EMP005', 'Karthik R', 'Admin', '9876501005', '1991-04-04', '2017-04-08', true, 'Annual leave until Friday'],
  ['EMP006', 'Sneha Das', 'Engineering', '9876501006', '1995-04-06', '2022-04-12', false, null],
  ['EMP007', 'Vikram Singh', 'Operations', '9876501007', '1989-04-08', '2016-04-14', false, null],
  ['EMP008', 'Anjali Rao', 'Finance', '9876501008', '1993-04-10', '2019-04-18', false, null],
  ['EMP009', 'Mohit Verma', 'Sales', '9876501009', '1990-04-12', '2018-04-20', false, null],
  ['EMP010', 'Deepa Menon', 'Support', '9876501010', '1994-04-14', '2020-04-22', true, 'Sick leave'],
  ['EMP011', 'Sanjay Patel', 'Engineering', '9876501011', '1991-04-16', '2017-04-24', false, null],
  ['EMP012', 'Nisha Roy', 'Reception', '9876501012', '1996-04-18', '2023-04-26', false, null],
  ['EMP013', 'Harish Babu', 'Security', '9876501013', '1988-04-20', '2015-04-28', false, null],
  ['EMP014', 'Divya Iyer', 'Operations', '9876501014', '1992-04-22', '2021-05-01', false, null],
  ['EMP015', 'Ajay Thomas', 'Logistics', '9876501015', '1990-04-24', '2019-05-03', false, null],
  ['EMP016', 'Keerthi S', 'Engineering', '9876501016', '1995-04-26', '2022-05-05', false, null],
  ['EMP017', 'Rahul Dev', 'Sales', '9876501017', '1993-04-28', '2020-05-07', false, null],
  ['EMP018', 'Pooja Sharma', 'Admin', '9876501018', '1991-04-30', '2018-05-09', false, null],
  ['EMP019', 'Farhan Ali', 'IT Support', '9876501019', '1994-05-02', '2021-05-11', false, null],
  ['EMP020', 'Lakshmi K', 'HR', '9876501020', '1992-05-04', '2017-05-13', true, 'Maternity leave'],
];

function localDayKey(ts) {
  const d = new Date(Number(ts));
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function localDayBounds(ts = Date.now()) {
  const start = new Date(Number(ts));
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return {
    startTs: start.getTime(),
    endTs: end.getTime(),
    dayKey: localDayKey(ts),
  };
}

async function rebuildDailyEntryHistory() {
  const rows = await pool.query('SELECT employee_id, type, ts FROM entries ORDER BY ts ASC');
  const byDay = new Map();

  for (const row of rows.rows) {
    const day = localDayKey(row.ts);
    const current = byDay.get(day) || {
      total_events: 0,
      in_count: 0,
      out_count: 0,
      guest_event_count: 0,
      uniqueEmployees: new Set(),
    };

    current.total_events += 1;
    if (row.type === 'in') current.in_count += 1;
    if (row.type === 'out') current.out_count += 1;
    if (row.employee_id === null || row.employee_id === undefined) {
      current.guest_event_count += 1;
    } else {
      current.uniqueEmployees.add(Number(row.employee_id));
    }

    byDay.set(day, current);
  }

  await pool.query('TRUNCATE TABLE daily_entry_history');

  const nowTs = Date.now();
  for (const [day, stats] of byDay.entries()) {
    await pool.query(
      `INSERT INTO daily_entry_history
         (day, total_events, in_count, out_count, unique_employee_count, guest_event_count, updated_at)
       VALUES ($1, $2, $3, $4, $5, $6, $7)`,
      [
        day,
        stats.total_events,
        stats.in_count,
        stats.out_count,
        stats.uniqueEmployees.size,
        stats.guest_event_count,
        nowTs,
      ]
    );
  }
}

async function upsertDailyHistoryForEntry(client, entry) {
  const { startTs, endTs, dayKey } = localDayBounds(entry.ts);
  const isIn = entry.type === 'in' ? 1 : 0;
  const isOut = entry.type === 'out' ? 1 : 0;
  const isGuest = entry.employee_id === null || entry.employee_id === undefined ? 1 : 0;

  await client.query(
    `INSERT INTO daily_entry_history
       (day, total_events, in_count, out_count, unique_employee_count, guest_event_count, updated_at)
     VALUES ($1, 1, $2, $3, 0, $4, $5)
     ON CONFLICT (day)
     DO UPDATE SET
       total_events = daily_entry_history.total_events + 1,
       in_count = daily_entry_history.in_count + EXCLUDED.in_count,
       out_count = daily_entry_history.out_count + EXCLUDED.out_count,
       guest_event_count = daily_entry_history.guest_event_count + EXCLUDED.guest_event_count,
       updated_at = EXCLUDED.updated_at`,
    [dayKey, isIn, isOut, isGuest, Date.now()]
  );

  const uniqueEmployeeCount = await client.query(
    `SELECT COUNT(DISTINCT employee_id)::INT AS c
     FROM entries
     WHERE ts >= $1 AND ts < $2 AND employee_id IS NOT NULL`,
    [startTs, endTs]
  );

  await client.query(
    'UPDATE daily_entry_history SET unique_employee_count = $2, updated_at = $3 WHERE day = $1',
    [dayKey, uniqueEmployeeCount.rows[0].c, Date.now()]
  );
}

function listRecentImages(dirPath, routePrefix, limit = 20) {
  if (!fs.existsSync(dirPath)) return [];
  const names = fs
    .readdirSync(dirPath)
    .filter((name) => /\.(jpg|jpeg|png)$/i.test(name));

  return names
    .map((name) => {
      const full = path.join(dirPath, name);
      const stat = fs.statSync(full);
      return {
        name,
        ts: stat.mtimeMs,
        url: `${routePrefix}/${encodeURIComponent(name)}`,
      };
    })
    .sort((a, b) => b.ts - a.ts)
    .slice(0, limit);
}

const app = express();
app.use(cors());
app.use(express.json());

if (fs.existsSync(CROSSINGS_DIR)) {
  app.use('/captures/crossings', express.static(CROSSINGS_DIR));
}
if (fs.existsSync(DETECTIONS_DIR)) {
  app.use('/captures/detections', express.static(DETECTIONS_DIR));
}
if (fs.existsSync(FACES_DIR)) {
  app.use('/captures/faces', express.static(FACES_DIR));
}

async function initDatabase() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS employees (
      id SERIAL PRIMARY KEY,
      employee_code TEXT UNIQUE,
      name TEXT NOT NULL,
      mobile TEXT,
      department TEXT,
      birthday DATE,
      join_date DATE,
      on_leave BOOLEAN NOT NULL DEFAULT FALSE,
      leave_note TEXT
    )
  `);

  await pool.query('ALTER TABLE employees ADD COLUMN IF NOT EXISTS employee_code TEXT');
  await pool.query('ALTER TABLE employees ADD COLUMN IF NOT EXISTS department TEXT');
  await pool.query('ALTER TABLE employees ADD COLUMN IF NOT EXISTS birthday DATE');
  await pool.query('ALTER TABLE employees ADD COLUMN IF NOT EXISTS join_date DATE');
  await pool.query('ALTER TABLE employees ADD COLUMN IF NOT EXISTS on_leave BOOLEAN NOT NULL DEFAULT FALSE');
  await pool.query('ALTER TABLE employees ADD COLUMN IF NOT EXISTS leave_note TEXT');
  await pool.query('CREATE UNIQUE INDEX IF NOT EXISTS idx_employees_code ON employees (employee_code)');

  await pool.query(`
    CREATE TABLE IF NOT EXISTS entries (
      id SERIAL PRIMARY KEY,
      employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
      detected_name TEXT,
      type TEXT,
      ts BIGINT NOT NULL
    )
  `);

  await pool.query('ALTER TABLE entries ADD COLUMN IF NOT EXISTS detected_name TEXT');
  await pool.query('ALTER TABLE entries ADD COLUMN IF NOT EXISTS face_image TEXT');

  await pool.query(`
    CREATE TABLE IF NOT EXISTS usage (
      id SERIAL PRIMARY KEY,
      employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
      app TEXT,
      duration_minutes INTEGER,
      ts BIGINT NOT NULL
    )
  `);

  await pool.query(`
    CREATE TABLE IF NOT EXISTS daily_entry_history (
      day DATE PRIMARY KEY,
      total_events INTEGER NOT NULL DEFAULT 0,
      in_count INTEGER NOT NULL DEFAULT 0,
      out_count INTEGER NOT NULL DEFAULT 0,
      unique_employee_count INTEGER NOT NULL DEFAULT 0,
      guest_event_count INTEGER NOT NULL DEFAULT 0,
      updated_at BIGINT NOT NULL
    )
  `);

  await pool.query('CREATE INDEX IF NOT EXISTS idx_entries_ts ON entries (ts DESC)');
  await pool.query('CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage (ts DESC)');
  await pool.query('CREATE INDEX IF NOT EXISTS idx_daily_entry_history_day ON daily_entry_history (day DESC)');

  for (const employee of DUMMY_EMPLOYEES) {
    await pool.query(
      `INSERT INTO employees
         (employee_code, name, department, mobile, birthday, join_date, on_leave, leave_note)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
       ON CONFLICT (employee_code)
       DO UPDATE SET
         name = EXCLUDED.name,
         department = EXCLUDED.department,
         mobile = EXCLUDED.mobile,
         birthday = EXCLUDED.birthday,
         join_date = EXCLUDED.join_date,
         on_leave = EXCLUDED.on_leave,
         leave_note = EXCLUDED.leave_note`,
      employee
    );
  }

  await rebuildDailyEntryHistory();
}

// Intentionally avoid demo seeding in production/local runtime.

// API: list employees
app.get('/api/employees', async (req, res) => {
  try {
    const rows = await pool.query(
      `SELECT id, employee_code, name, mobile, department, birthday, join_date, on_leave, leave_note
       FROM employees
       ORDER BY id ASC`
    );
    res.json(rows.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/employees', async (req, res) => {
  const { employee_code, name, mobile, department, birthday, join_date, on_leave, leave_note } = req.body;
  try {
    const result = await pool.query(
      `INSERT INTO employees (employee_code, name, mobile, department, birthday, join_date, on_leave, leave_note)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
       RETURNING id, employee_code, name, mobile, department, birthday, join_date, on_leave, leave_note`,
      [
        employee_code || null,
        name,
        mobile || null,
        department || null,
        birthday || null,
        join_date || null,
        Boolean(on_leave),
        leave_note || null,
      ]
    );
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// entries
app.get('/api/entries', async (req, res) => {
  try {
    const rows = await pool.query(
            `SELECT e.id, e.employee_id, e.type, e.ts, emp.name AS employee_name
              ,e.detected_name, e.face_image
       FROM entries e
       LEFT JOIN employees emp ON emp.id = e.employee_id
        ORDER BY e.ts DESC`
    );
    res.json(rows.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/entries', async (req, res) => {
  const { employee_id, detected_name, type, face_image } = req.body;
  const ts = Date.now();
  const employeeId = employee_id === null || employee_id === undefined ? null : Number(employee_id);

  if (type !== 'in' && type !== 'out') {
    return res.status(400).json({ error: 'Invalid entry type. Use "in" or "out".' });
  }

  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const result = await client.query(
      `INSERT INTO entries (employee_id, detected_name, face_image, type, ts)
       VALUES ($1, $2, $3, $4, $5)
       RETURNING id, employee_id, detected_name, face_image, type, ts`,
      [employeeId, detected_name || null, face_image || null, type, ts]
    );

    await upsertDailyHistoryForEntry(client, result.rows[0]);
    await client.query('COMMIT');

    res.json(result.rows[0]);
  } catch (err) {
    try {
      await client.query('ROLLBACK');
    } catch (_) {
      // Ignore rollback errors; original failure is returned to caller.
    }
    res.status(500).json({ error: err.message });
  } finally {
    client.release();
  }
});

app.get('/api/history/daily', async (req, res) => {
  const days = Math.min(Math.max(Number(req.query.days || 31), 1), 365);

  try {
    const rows = await pool.query(
      `SELECT day::TEXT AS day,
              total_events,
              in_count,
              out_count,
              unique_employee_count,
              guest_event_count,
              updated_at
       FROM daily_entry_history
       ORDER BY day DESC
       LIMIT $1`,
      [days]
    );
    res.json(rows.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// usage
app.get('/api/usage', async (req, res) => {
  try {
    const rows = await pool.query(
      `SELECT u.id, u.employee_id, u.app, u.duration_minutes, u.ts, emp.name AS employee_name
       FROM usage u
       LEFT JOIN employees emp ON emp.id = u.employee_id
       ORDER BY u.ts DESC
       LIMIT 200`
    );
    res.json(rows.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/usage', async (req, res) => {
  const { employee_id, app: appName, duration_minutes } = req.body;
  const ts = Date.now();
  const employeeId = employee_id === null || employee_id === undefined ? null : Number(employee_id);

  try {
    const result = await pool.query(
      `INSERT INTO usage (employee_id, app, duration_minutes, ts)
       VALUES ($1, $2, $3, $4)
       RETURNING id, employee_id, app, duration_minutes, ts`,
      [employeeId, appName, Number(duration_minutes), ts]
    );
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// dashboard aggregated
app.get('/api/dashboard', async (req, res) => {
  const { startTs } = localDayBounds();

  try {
    const [employees, entries, todayEntries, usageAgg, usageByEmployee, dailyHistory] = await Promise.all([
      pool.query(
        `SELECT id, employee_code, name, mobile, department, birthday, join_date, on_leave, leave_note
         FROM employees
         ORDER BY id ASC`
      ),
      pool.query(
        `SELECT e.id, e.employee_id, e.type, e.ts, emp.name AS employee_name
           ,e.detected_name, e.face_image
         FROM entries e
         LEFT JOIN employees emp ON emp.id = e.employee_id
          ORDER BY e.ts DESC`
      ),
      pool.query(
        `SELECT e.id, e.employee_id, e.type, e.ts, emp.name AS employee_name, e.detected_name, e.face_image
         FROM entries e
         LEFT JOIN employees emp ON emp.id = e.employee_id
         WHERE e.ts >= $1
         ORDER BY e.ts DESC`,
        [startTs]
      ),
      pool.query(
        `SELECT u.app, COALESCE(SUM(u.duration_minutes), 0)::INT AS total_minutes
         FROM usage u
         GROUP BY u.app
         ORDER BY total_minutes DESC
         LIMIT 10`
      ),
      pool.query(
        `SELECT u.employee_id, emp.name AS employee_name, COALESCE(SUM(u.duration_minutes), 0)::INT AS total_minutes
         FROM usage u
         LEFT JOIN employees emp ON emp.id = u.employee_id
         GROUP BY u.employee_id, emp.name
         ORDER BY total_minutes DESC
         LIMIT 10`
      ),
      pool.query(
        `SELECT day::TEXT AS day,
                total_events,
                in_count,
                out_count,
                unique_employee_count,
                guest_event_count,
                updated_at
         FROM daily_entry_history
         ORDER BY day DESC
         LIMIT 60`
      ),
    ]);

    res.json({
      employees: employees.rows,
      entries: entries.rows,
      todayEntries: todayEntries.rows,
      usage: usageAgg.rows,
      usageByEmployee: usageByEmployee.rows,
      historyDaily: dailyHistory.rows,
      dayResetAt: new Date(startTs + 24 * 60 * 60 * 1000).toISOString(),
      recentCrossings: listRecentImages(CROSSINGS_DIR, '/captures/crossings', 12),
      recentDetections: listRecentImages(DETECTIONS_DIR, '/captures/detections', 12),
      recentFaces: listRecentImages(FACES_DIR, '/captures/faces', 12),
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// System health check endpoint
app.get('/api/health', async (req, res) => {
  // eslint-disable-next-line global-require
  const { execSync } = require('child_process');
  const services = [];

  // 1. Backend API
  services.push({ name: 'Backend API', status: 'ok', note: 'Server is running', latency: null });

  // 2. PostgreSQL
  try {
    const dbT0 = Date.now();
    await pool.query('SELECT 1');
    const dbMs = Date.now() - dbT0;
    services.push({ name: 'PostgreSQL', status: 'ok', note: `Connected · ${dbMs} ms`, latency: dbMs });
  } catch (e) {
    services.push({ name: 'PostgreSQL', status: 'error', note: e.message, latency: null });
  }

  // 3. Detector systemd service
  let serviceActive = false;
  let servicePid = null;
  try {
    execSync('systemctl is-active --quiet office-ai-detector', { timeout: 3000 });
    serviceActive = true;
    try {
      servicePid = execSync('systemctl show office-ai-detector --property=MainPID --value', { timeout: 2000 }).toString().trim();
    } catch (_) {}
  } catch (_) {
    serviceActive = false;
  }
  services.push({
    name: 'Detector Service (systemd)',
    status: serviceActive ? 'ok' : 'error',
    note: serviceActive ? `Active · PID ${servicePid}` : 'office-ai-detector.service not active',
    latency: null,
  });

  // 4. Read last 10 min of journal for pipeline details
  let journal = '';
  try {
    journal = execSync('journalctl -u office-ai-detector --since "30 min ago" --no-pager 2>/dev/null', {
      timeout: 6000,
      maxBuffer: 512 * 1024,
    }).toString();
  } catch (_) {}

  // 5. GStreamer pipeline
  const gstLines = [...journal.matchAll(/\[GStreamer\] Pipeline PLAYING with (.+)/g)];
  const lastGstDecoder = gstLines.length ? gstLines[gstLines.length - 1][1].trim() : null;
  const opencvFallback = /Switching to OpenCV RTSP|OpenCV fallback active/.test(journal);
  if (lastGstDecoder) {
    const isHw = /hardware/i.test(lastGstDecoder);
    services.push({
      name: 'GStreamer Pipeline',
      status: 'ok',
      note: `PLAYING · ${lastGstDecoder}${isHw ? ' ✓ Jetson HW' : ''}`,
      latency: null,
    });
  } else if (opencvFallback) {
    services.push({ name: 'GStreamer Pipeline', status: 'warn', note: 'Fell back to OpenCV (appsink stalled)', latency: null });
  } else if (serviceActive) {
    services.push({ name: 'GStreamer Pipeline', status: 'unknown', note: 'Starting or no log in last 10 min', latency: null });
  } else {
    services.push({ name: 'GStreamer Pipeline', status: 'error', note: 'Detector not running', latency: null });
  }

  // 6. OpenCV Fallback
  if (opencvFallback) {
    services.push({ name: 'OpenCV Fallback', status: 'warn', note: 'Active — GStreamer failed over', latency: null });
  } else {
    services.push({
      name: 'OpenCV Fallback',
      status: serviceActive ? 'ok' : 'unknown',
      note: serviceActive ? 'Not needed — GStreamer OK' : 'Detector not running',
      latency: null,
    });
  }

  // 7. YOLO / Frame processing
  const framesMatches = [...journal.matchAll(/frames=(\d+) \| detections=(\d+) tracked=(\d+) \| IN=(\d+) OUT=(\d+)/g)];
  if (framesMatches.length > 0) {
    const last = framesMatches[framesMatches.length - 1];
    services.push({
      name: 'YOLO Frame Processing',
      status: 'ok',
      note: `${last[1]} frames | detections=${last[2]} tracked=${last[3]} | IN=${last[4]} OUT=${last[5]}`,
      latency: null,
    });
  } else if (serviceActive) {
    services.push({ name: 'YOLO Frame Processing', status: 'unknown', note: 'No frame counter logged yet', latency: null });
  } else {
    services.push({ name: 'YOLO Frame Processing', status: 'error', note: 'Detector not running', latency: null });
  }

  // 8. RTSP Camera
  const hasFrames = framesMatches.length > 0;
  const hasBadCseq = /bad cseq/i.test(journal);
  const hasRtspError = /RTSP.*error|connection refused/i.test(journal);
  services.push({
    name: 'RTSP Camera',
    status: hasFrames ? 'ok' : hasRtspError ? 'error' : hasBadCseq ? 'warn' : serviceActive ? 'unknown' : 'error',
    note: hasFrames
      ? 'Streaming · 192.168.2.103:554'
      : hasRtspError
      ? 'Connection error — check camera'
      : hasBadCseq
      ? 'RTP sequence errors (network jitter)'
      : serviceActive
      ? 'No frames confirmed yet'
      : 'Detector not running',
    latency: null,
  });

  // 9. Face detection ROI
  const noFaceMatch = journal.match(/No face detected in face ROI/g);
  const faceFoundMatch = journal.match(/Saving face crop|face_\d+.*saved/g);
  if (faceFoundMatch) {
    services.push({ name: 'Face Detection (ROI)', status: 'ok', note: `${faceFoundMatch.length} face crop(s) saved (last 10 min)`, latency: null });
  } else {
    services.push({
      name: 'Face Detection (ROI)',
      status: serviceActive ? 'ok' : 'unknown',
      note: serviceActive
        ? `Active · ${noFaceMatch ? noFaceMatch.length + ' missed detections' : '0 events in last 10 min'}`
        : 'Detector not running',
      latency: null,
    });
  }

  // 10. Last detection event (from DB)
  try {
    const lastRow = await pool.query('SELECT ts FROM entries ORDER BY ts DESC LIMIT 1');
    if (lastRow.rows.length > 0) {
      const agoSec = Math.floor((Date.now() - Number(lastRow.rows[0].ts)) / 1000);
      const agoLabel =
        agoSec < 60
          ? `${agoSec}s ago`
          : agoSec < 3600
          ? `${Math.floor(agoSec / 60)}m ago`
          : `${Math.floor(agoSec / 3600)}h ${Math.floor((agoSec % 3600) / 60)}m ago`;
      services.push({ name: 'Last Detection Event', status: agoSec < 3600 ? 'ok' : 'warn', note: agoLabel, latency: null });
    } else {
      services.push({ name: 'Last Detection Event', status: 'unknown', note: 'No events in database', latency: null });
    }
  } catch (e) {
    services.push({ name: 'Last Detection Event', status: 'error', note: e.message, latency: null });
  }

  // 11. Face crops storage
  const faceCount = fs.existsSync(FACES_DIR)
    ? fs.readdirSync(FACES_DIR).filter((f) => /\.(jpg|jpeg|png)$/i.test(f)).length
    : 0;
  services.push({ name: 'Face Crops Storage', status: 'ok', note: `${faceCount} files in crossings/faces/`, latency: null });

  res.json({ ts: Date.now(), services });
});

const PORT = process.env.PORT || 3000;

initDatabase()
  .then(() => {
    app.listen(PORT, () => {
      console.log(`Backend listening on http://localhost:${PORT}`);
      console.log(`PostgreSQL URL: ${DATABASE_URL}`);
    });
  })
  .catch((err) => {
    console.error('Failed to initialize PostgreSQL schema:', err.message);
    process.exit(1);
  });
