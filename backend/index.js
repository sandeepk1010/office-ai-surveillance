const express = require('express');
const cors = require('cors');
const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const fs = require('fs');

const DB_PATH = path.join(__dirname, 'data.db');
const db = new sqlite3.Database(DB_PATH);
const CROSSINGS_DIR = path.join(__dirname, '..', 'python-scripts', 'crossings');
const DETECTIONS_DIR = path.join(CROSSINGS_DIR, 'detections');
const FACES_DIR = path.join(CROSSINGS_DIR, 'faces');

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

// Initialize DB
db.serialize(() => {
  db.run(
    `CREATE TABLE IF NOT EXISTS employees (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      mobile TEXT
    )`
  );
  db.run(
    `CREATE TABLE IF NOT EXISTS entries (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      employee_id INTEGER,
      type TEXT,
      ts INTEGER,
      FOREIGN KEY(employee_id) REFERENCES employees(id)
    )`
  );
  db.run(
    `CREATE TABLE IF NOT EXISTS usage (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      employee_id INTEGER,
      app TEXT,
      duration_minutes INTEGER,
      ts INTEGER,
      FOREIGN KEY(employee_id) REFERENCES employees(id)
    )`
  );
});

// Seed small sample if no employees
db.get('SELECT COUNT(1) as cnt FROM employees', (err, row) => {
  if (!err && row && row.cnt === 0) {
    const now = Date.now();
    db.run('INSERT INTO employees (name, mobile) VALUES (?,?)', ['Alice Johnson', '+15550001']);
    db.run('INSERT INTO employees (name, mobile) VALUES (?,?)', ['Bob Smith', '+15550002']);
    db.run('INSERT INTO entries (employee_id, type, ts) VALUES (?,?,?)', [1, 'in', now - 1000 * 60 * 60 * 8]);
    db.run('INSERT INTO entries (employee_id, type, ts) VALUES (?,?,?)', [1, 'out', now - 1000 * 60 * 60 * 2]);
    db.run('INSERT INTO usage (employee_id, app, duration_minutes, ts) VALUES (?,?,?,?)', [2, 'WhatsApp', 45, now - 1000 * 60 * 60 * 3]);
    db.run('INSERT INTO usage (employee_id, app, duration_minutes, ts) VALUES (?,?,?,?)', [2, 'Browser', 120, now - 1000 * 60 * 60 * 4]);
  }
});

// API: list employees
app.get('/api/employees', (req, res) => {
  db.all('SELECT * FROM employees', (err, rows) => {
    if (err) return res.status(500).json({ error: err.message });
    res.json(rows);
  });
});

app.post('/api/employees', (req, res) => {
  const { name, mobile } = req.body;
  db.run('INSERT INTO employees (name, mobile) VALUES (?,?)', [name, mobile], function (err) {
    if (err) return res.status(500).json({ error: err.message });
    res.json({ id: this.lastID, name, mobile });
  });
});

// entries
app.get('/api/entries', (req, res) => {
  db.all('SELECT e.*, emp.name as employee_name FROM entries e LEFT JOIN employees emp ON emp.id = e.employee_id ORDER BY ts DESC LIMIT 100', (err, rows) => {
    if (err) return res.status(500).json({ error: err.message });
    res.json(rows);
  });
});

app.post('/api/entries', (req, res) => {
  const { employee_id, type } = req.body;
  const ts = Date.now();
  db.run('INSERT INTO entries (employee_id, type, ts) VALUES (?,?,?)', [employee_id, type, ts], function (err) {
    if (err) return res.status(500).json({ error: err.message });
    res.json({ id: this.lastID, employee_id, type, ts });
  });
});

// usage
app.get('/api/usage', (req, res) => {
  db.all('SELECT u.*, emp.name as employee_name FROM usage u LEFT JOIN employees emp ON emp.id = u.employee_id ORDER BY ts DESC LIMIT 200', (err, rows) => {
    if (err) return res.status(500).json({ error: err.message });
    res.json(rows);
  });
});

app.post('/api/usage', (req, res) => {
  const { employee_id, app: appName, duration_minutes } = req.body;
  const ts = Date.now();
  db.run('INSERT INTO usage (employee_id, app, duration_minutes, ts) VALUES (?,?,?,?)', [employee_id, appName, duration_minutes, ts], function (err) {
    if (err) return res.status(500).json({ error: err.message });
    res.json({ id: this.lastID, employee_id, app: appName, duration_minutes, ts });
  });
});

// dashboard aggregated
app.get('/api/dashboard', (req, res) => {
  const result = {};
  db.all('SELECT * FROM employees', (err, employees) => {
    if (err) return res.status(500).json({ error: err.message });
    result.employees = employees;
    db.all('SELECT e.*, emp.name as employee_name FROM entries e LEFT JOIN employees emp ON emp.id = e.employee_id ORDER BY ts DESC LIMIT 100', (err2, entries) => {
      if (err2) return res.status(500).json({ error: err2.message });
      result.entries = entries;
      db.all('SELECT u.app, SUM(u.duration_minutes) as total_minutes FROM usage u GROUP BY u.app ORDER BY total_minutes DESC LIMIT 10', (err3, usageAgg) => {
        if (err3) return res.status(500).json({ error: err3.message });
        result.usage = usageAgg;
        // aggregate usage by employee
        db.all('SELECT u.employee_id, emp.name as employee_name, SUM(u.duration_minutes) as total_minutes FROM usage u LEFT JOIN employees emp ON emp.id = u.employee_id GROUP BY u.employee_id ORDER BY total_minutes DESC LIMIT 10', (err4, usageByEmployee) => {
          if (err4) return res.status(500).json({ error: err4.message });
          result.usageByEmployee = usageByEmployee;
          result.recentCrossings = listRecentImages(CROSSINGS_DIR, '/captures/crossings', 12);
          result.recentDetections = listRecentImages(DETECTIONS_DIR, '/captures/detections', 12);
          result.recentFaces = listRecentImages(FACES_DIR, '/captures/faces', 12);
          res.json(result);
        });
      });
    });
  });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Backend listening on http://localhost:${PORT}`));
