import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  Chart,
  DoughnutController,
  Legend,
  LineController,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from 'chart.js'
import { API_BASE_URL, fetchDashboard, fetchSystemHealth } from './api'

Chart.register(
  ArcElement,
  BarController,
  BarElement,
  CategoryScale,
  DoughnutController,
  Legend,
  LineController,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip
)

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'detections', label: 'Detections' },
  { id: 'live', label: 'Live Monitoring' },
  { id: 'employees', label: 'Employees' },
  { id: 'attendance', label: 'Attendance' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'health', label: 'Health' },
  { id: 'settings', label: 'Settings' },
]

const KPI_STYLES = {
  employees: 'kpi-card kpi-blue',
  present: 'kpi-card kpi-green',
  absent: 'kpi-card kpi-orange',
  late: 'kpi-card kpi-red',
  break: 'kpi-card kpi-yellow',
  inOffice: 'kpi-card kpi-teal',
}

function formatDateTime(ts) {
  return new Date(Number(ts)).toLocaleString()
}

function formatHours(value) {
  return `${value.toFixed(2)}h`
}

function formatMonthDay(dateValue) {
  if (!dateValue) return '-'
  const d = new Date(dateValue)
  if (Number.isNaN(d.getTime())) return '-'
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function sameDay(tsA, tsB) {
  const a = new Date(tsA)
  const b = new Date(tsB)
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}

function dayKey(ts) {
  const d = new Date(ts)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function ChartCard({ title, subtitle, type, labels, values, colors }) {
  const canvasRef = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    if (!canvasRef.current) return
    const ctx = canvasRef.current.getContext('2d')
    if (chartRef.current) chartRef.current.destroy()

    const baseDataset = {
      label: title,
      data: values,
      borderWidth: 2,
    }

    let datasets = []
    if (type === 'line') {
      datasets = [{
        ...baseDataset,
        borderColor: colors?.[0] || '#0f766e',
        backgroundColor: 'rgba(15, 118, 110, 0.15)',
        fill: true,
        tension: 0.35,
      }]
    } else if (type === 'doughnut') {
      datasets = [{
        ...baseDataset,
        backgroundColor: colors || ['#0f766e', '#1f2937', '#f59e0b', '#ef4444'],
        borderColor: '#f8fafc',
      }]
    } else {
      datasets = [{
        ...baseDataset,
        backgroundColor: colors || '#0f766e',
        borderColor: '#0f766e',
      }]
    }

    chartRef.current = new Chart(ctx, {
      type,
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: type === 'doughnut' },
          tooltip: { enabled: true },
        },
        scales: type === 'doughnut' ? {} : {
          x: { ticks: { color: '#334155' }, grid: { color: 'rgba(148, 163, 184, 0.18)' } },
          y: { ticks: { color: '#334155' }, grid: { color: 'rgba(148, 163, 184, 0.18)' } },
        },
      },
    })

    return () => {
      if (chartRef.current) chartRef.current.destroy()
    }
  }, [title, type, labels, values, colors])

  return (
    <section className="panel chart-panel">
      <div className="panel-header">
        <h3>{title}</h3>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      <div className="chart-wrap">
        <canvas ref={canvasRef} />
      </div>
    </section>
  )
}

export default function App() {
  const [data, setData] = useState({ employees: [], entries: [], todayEntries: [], usage: [], recentCrossings: [], recentDetections: [], recentFaces: [] })
  const [loading, setLoading] = useState(true)
  const [activeView, setActiveView] = useState('dashboard')

  const [systemHealth, setSystemHealth] = useState(null)
  const [healthChecking, setHealthChecking] = useState(false)
  const [healthLastUpdated, setHealthLastUpdated] = useState(null)

  const refreshHealth = useCallback(async (showSpinner = false) => {
    if (showSpinner) setHealthChecking(true)
    try {
      const h = await fetchSystemHealth()
      // Add frontend status as first row
      const frontendRow = { name: 'Frontend (Vite)', status: 'ok', note: 'This page is running', latency: null }
      setSystemHealth({ ...h, services: [frontendRow, ...h.services] })
      setHealthLastUpdated(new Date())
    } catch (e) {
      setSystemHealth({
        ts: Date.now(),
        services: [
          { name: 'Frontend (Vite)', status: 'ok', note: 'This page is running', latency: null },
          { name: 'Backend API', status: 'error', note: e.message, latency: null },
        ],
      })
      setHealthLastUpdated(new Date())
    } finally {
      if (showSpinner) setHealthChecking(false)
    }
  }, [])

  const load = useCallback(async (opts = {}) => {
    const silent = Boolean(opts.silent)
    if (!silent) setLoading(true)
    try {
      const d = await fetchDashboard()
      setData(d)
    } catch (err) {
      console.error(err)
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    refreshHealth()
  }, [refreshHealth])

  const processed = useMemo(() => {
    const employees = Array.isArray(data.employees) ? data.employees : []
    const entries = (Array.isArray(data.entries) ? data.entries : [])
      .map((e) => ({ ...e, ts: Number(e.ts) }))
      .sort((a, b) => b.ts - a.ts)
    const todayEntries = (Array.isArray(data.todayEntries) ? data.todayEntries : [])
      .map((e) => ({ ...e, ts: Number(e.ts) }))
      .sort((a, b) => b.ts - a.ts)
    const todayStart = new Date()
    todayStart.setHours(0, 0, 0, 0)
    const todayTs = todayStart.getTime()
    const msPerDay = 24 * 60 * 60 * 1000

    const employeeById = new Map(employees.map((e) => [Number(e.id), e]))
    const personMap = new Map()

    const pushEvent = (event) => {
      const id = event.employee_id !== null && event.employee_id !== undefined ? Number(event.employee_id) : null
      const key = id !== null ? `emp:${id}` : `name:${event.detected_name || event.employee_name || `Unknown-${event.id}`}`
      const fallbackName = event.detected_name || event.employee_name || `Unknown ${event.id}`
      const profile = id !== null ? employeeById.get(id) : null
      const label = profile?.name || fallbackName
      const item = personMap.get(key) || {
        key,
        employeeId: id,
        name: label,
        department: profile?.department || 'Operations',
        phone: profile?.mobile || '-',
        timeline: [],
      }
      item.timeline.push(event)
      personMap.set(key, item)
    }

    entries.forEach(pushEvent)

    const people = Array.from(personMap.values()).map((person) => {
      const timelineAsc = person.timeline.slice().sort((a, b) => a.ts - b.ts)
      const todayEvents = timelineAsc.filter((ev) => ev.ts >= todayTs)
      let inOffice = false
      let lastInTs = null
      let workMs = 0
      let breakMs = 0
      let firstInTs = null
      let lastOutTs = null

      for (const ev of todayEvents) {
        if (ev.type === 'in') {
          if (firstInTs === null) firstInTs = ev.ts
          if (inOffice === false && lastOutTs !== null) {
            breakMs += (ev.ts - lastOutTs)
          }
          inOffice = true
          lastInTs = ev.ts
        } else if (ev.type === 'out') {
          if (inOffice && lastInTs !== null) {
            workMs += (ev.ts - lastInTs)
          }
          inOffice = false
          lastOutTs = ev.ts
        }
      }

      if (inOffice && lastInTs !== null) {
        workMs += (Date.now() - lastInTs)
      }

      const lastEvent = timelineAsc[timelineAsc.length - 1] || null
      const status = inOffice ? 'Present' : (lastEvent ? 'Left Office' : 'Absent')
      const lateCutoff = new Date(todayStart)
      lateCutoff.setHours(9, 15, 0, 0)
      const isLate = firstInTs !== null && firstInTs > lateCutoff.getTime()

      return {
        ...person,
        timelineAsc,
        todayEvents,
        status,
        inOffice,
        workHours: workMs / (1000 * 60 * 60),
        breakMinutes: breakMs / (1000 * 60),
        firstInTs,
        lastOutTs,
        isLate,
      }
    })

    const peopleByEmployeeId = new Map(
      people
        .filter((p) => p.employeeId !== null)
        .map((p) => [Number(p.employeeId), p])
    )

    const regularEmployees = employees
      .map((emp) => {
        const id = Number(emp.id)
        const person = peopleByEmployeeId.get(id)
        const timelineAsc = person?.timelineAsc || []
        const todayEvents = timelineAsc.filter((ev) => ev.ts >= todayTs)
        const inOffice = person?.inOffice || false
        const firstInToday = todayEvents.find((ev) => ev.type === 'in') || null
        const lastSeenEvent = timelineAsc[timelineAsc.length - 1] || null
        let status = inOffice ? 'Present' : (lastSeenEvent ? 'Left Office' : 'Absent')
        if (emp.on_leave && !inOffice) status = 'On Leave'

        return {
          key: `regular-${id}`,
          employeeId: id,
          employeeCode: emp.employee_code || `EMP${String(id).padStart(3, '0')}`,
          name: emp.name,
          department: emp.department || 'Operations',
          phone: emp.mobile || '-',
          birthday: emp.birthday || null,
          joinDate: emp.join_date || null,
          onLeave: Boolean(emp.on_leave),
          leaveNote: emp.leave_note || null,
          inOffice,
          status,
          firstInTodayTs: firstInToday?.ts || null,
          lastSeenTs: lastSeenEvent?.ts || null,
          workHours: person?.workHours || 0,
        }
      })
      .sort((a, b) => a.employeeId - b.employeeId)

    const getUpcomingInfo = (dateValue) => {
      if (!dateValue) return null
      const source = new Date(dateValue)
      if (Number.isNaN(source.getTime())) return null
      const next = new Date(todayStart)
      next.setMonth(source.getMonth(), source.getDate())
      if (next.getTime() < todayTs) next.setFullYear(next.getFullYear() + 1)
      const daysAway = Math.round((next.getTime() - todayTs) / msPerDay)
      return {
        dateLabel: next.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
        daysAway,
        source,
      }
    }

    const upcomingBirthdays = regularEmployees
      .map((employee) => {
        const info = getUpcomingInfo(employee.birthday)
        if (!info || info.daysAway > 30) return null
        return { ...employee, ...info }
      })
      .filter(Boolean)
      .sort((a, b) => a.daysAway - b.daysAway)
      .slice(0, 6)

    const upcomingAnniversaries = regularEmployees
      .map((employee) => {
        const info = getUpcomingInfo(employee.joinDate)
        if (!info || info.daysAway > 30) return null
        const years = new Date().getFullYear() - info.source.getFullYear()
        return { ...employee, ...info, years }
      })
      .filter(Boolean)
      .sort((a, b) => a.daysAway - b.daysAway)
      .slice(0, 6)

    const leaveEmployees = regularEmployees
      .filter((employee) => employee.onLeave)
      .slice(0, 8)

    const currentMonthStart = new Date(todayStart)
    currentMonthStart.setDate(1)
    const monthStartTs = currentMonthStart.getTime()
    const guestMap = new Map()

    for (const ev of entries) {
      const hasEmployeeId = ev.employee_id !== null && ev.employee_id !== undefined
      if (hasEmployeeId || ev.ts < monthStartTs) continue

      const guestName = ev.detected_name || ev.employee_name || 'Unknown Guest'
      const item = guestMap.get(guestName) || { name: guestName, inCount: 0, eventCount: 0, lastVisitTs: 0 }
      item.eventCount += 1
      if (ev.type === 'in') item.inCount += 1
      if (ev.ts > item.lastVisitTs) item.lastVisitTs = ev.ts
      guestMap.set(guestName, item)
    }

    const monthlyGuests = Array.from(guestMap.values())
      .map((g) => ({
        ...g,
        visits: g.inCount > 0 ? g.inCount : Math.max(1, Math.round(g.eventCount / 2)),
      }))
      .sort((a, b) => {
        if (b.visits !== a.visits) return b.visits - a.visits
        return b.lastVisitTs - a.lastVisitTs
      })

    const knownEmployeesCount = regularEmployees.length
    const presentCount = regularEmployees.filter((p) => p.inOffice).length
    const leaveCount = leaveEmployees.length
    const absentCount = Math.max(knownEmployeesCount - presentCount - leaveCount, 0)
    const lateCount = people.filter((p) => p.isLate && p.employeeId !== null).length
    const onBreakCount = 0
    const inOfficeCount = presentCount

    const alerts = []
    for (const p of people) {
      if (p.isLate && p.firstInTs) {
        alerts.push({ level: 'warning', text: `${p.name} arrived late at ${formatDateTime(p.firstInTs)}` })
      }
      if (p.breakMinutes > 90) {
        alerts.push({ level: 'critical', text: `${p.name} has high break duration (${Math.round(p.breakMinutes)} min)` })
      }
      if (p.lastOutTs) {
        const lastOut = new Date(p.lastOutTs)
        if (lastOut.getHours() < 17) {
          alerts.push({ level: 'warning', text: `${p.name} exited early at ${lastOut.toLocaleTimeString()}` })
        }
      }
      if (String(p.name).toLowerCase().startsWith('unknown')) {
        alerts.push({ level: 'critical', text: `Unknown face detected (${p.name})` })
      }
    }

    const entriesByDay = new Map()
    for (const ev of entries) {
      const key = dayKey(ev.ts)
      if (!entriesByDay.has(key)) entriesByDay.set(key, [])
      entriesByDay.get(key).push(ev)
    }

    const last7Days = []
    for (let i = 6; i >= 0; i -= 1) {
      const d = new Date(todayStart)
      d.setDate(d.getDate() - i)
      const key = dayKey(d.getTime())
      const list = entriesByDay.get(key) || []
      const unique = new Set(list.map((e) => e.employee_id ?? e.detected_name ?? e.id))
      last7Days.push({ label: `${d.getMonth() + 1}/${d.getDate()}`, value: unique.size })
    }

    const heatmap = []
    for (let i = 27; i >= 0; i -= 1) {
      const d = new Date(todayStart)
      d.setDate(d.getDate() - i)
      const key = dayKey(d.getTime())
      heatmap.push({
        key,
        count: (entriesByDay.get(key) || []).length,
      })
    }

    const recentFaces = Array.isArray(data.recentFaces) ? data.recentFaces : []
    const recentFaceFeed = recentFaces.map((image, index) => {
      let nearestEvent = null
      let nearestDelta = Number.POSITIVE_INFINITY

      for (const entry of entries.slice(0, 80)) {
        const delta = Math.abs(Number(image.ts) - Number(entry.ts))
        if (delta < nearestDelta) {
          nearestDelta = delta
          nearestEvent = entry
        }
      }

      const matchedWithinWindow = nearestEvent && nearestDelta <= 2 * 60 * 1000
      const name = matchedWithinWindow
        ? (nearestEvent.employee_name || nearestEvent.detected_name || 'Unknown')
        : 'Unknown'

      return {
        key: `${image.name}-${index}`,
        imageUrl: `${API_BASE_URL}${image.url}`,
        imageName: image.name,
        name,
        ts: matchedWithinWindow ? nearestEvent.ts : image.ts,
        type: matchedWithinWindow ? (nearestEvent.employee_id ? 'Employee' : nearestEvent.detected_name ? 'Guest' : 'Unknown') : 'Unknown',
      }
    })

    return {
      entries,
      todayEntries,
      people,
      regularEmployees,
      monthlyGuests,
      recentFaceFeed,
      upcomingBirthdays,
      upcomingAnniversaries,
      leaveEmployees,
      metrics: {
        totalEmployees: knownEmployeesCount,
        presentToday: presentCount,
        absent: absentCount,
        lateArrivals: lateCount,
        onBreak: onBreakCount,
        inOffice: inOfficeCount,
        monthlyGuestCount: monthlyGuests.length,
        onLeave: leaveCount,
      },
      alerts,
      charts: {
        dailyAttendance: last7Days,
        breakStatus: [presentCount, onBreakCount, Math.max(people.length - presentCount - onBreakCount, 0)],
        topWorkHours: people
          .slice()
          .sort((a, b) => b.workHours - a.workHours)
          .slice(0, 8),
        lateByEmployee: people.filter((p) => p.isLate).slice(0, 8),
        heatmap,
      },
    }
  }, [data])

  const renderKpi = () => (
    <section className="kpi-grid">
      <article className={KPI_STYLES.employees}><h4>Total Employees</h4><strong>{processed.metrics.totalEmployees}</strong></article>
      <article className={KPI_STYLES.present}><h4>Employees Present Today</h4><strong>{processed.metrics.presentToday}</strong></article>
      <article className={KPI_STYLES.absent}><h4>Employees Absent</h4><strong>{processed.metrics.absent}</strong></article>
      <article className={KPI_STYLES.late}><h4>Late Arrivals</h4><strong>{processed.metrics.lateArrivals}</strong></article>
      <article className={KPI_STYLES.break}><h4>Guests This Month</h4><strong>{processed.metrics.monthlyGuestCount}</strong></article>
      <article className={KPI_STYLES.inOffice}><h4>Currently In Office</h4><strong>{processed.metrics.inOffice}</strong></article>
    </section>
  )

  const renderDashboard = () => (
    <>
      {renderKpi()}
      <section className="grid-two">
        <ChartCard
          title="Daily Attendance Chart"
          subtitle="Unique people seen per day"
          type="line"
          labels={processed.charts.dailyAttendance.map((d) => d.label)}
          values={processed.charts.dailyAttendance.map((d) => d.value)}
          colors={['#0f766e']}
        />
        <ChartCard
          title="Break Time Analytics"
          subtitle="Present / On Break / Left Office"
          type="doughnut"
          labels={['Present', 'On Break', 'Left Office']}
          values={processed.charts.breakStatus}
          colors={['#10b981', '#f59e0b', '#64748b']}
        />
      </section>
      <section className="grid-three">
        <section className="panel">
          <div className="panel-header"><h3>Upcoming Birthdays</h3><p>Next 30 days</p></div>
          {processed.upcomingBirthdays.length ? (
            <div className="mini-list">
              {processed.upcomingBirthdays.map((employee) => (
                <div className="mini-card" key={`birthday-${employee.employeeId}`}>
                  <div className="avatar">{String(employee.name).charAt(0).toUpperCase()}</div>
                  <div>
                    <strong>{employee.name}</strong>
                    <p>{employee.dateLabel} • in {employee.daysAway} day{employee.daysAway === 1 ? '' : 's'}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : <p className="muted">No upcoming birthdays.</p>}
        </section>
        <section className="panel">
          <div className="panel-header"><h3>Work Anniversaries</h3><p>Upcoming milestones</p></div>
          {processed.upcomingAnniversaries.length ? (
            <div className="mini-list">
              {processed.upcomingAnniversaries.map((employee) => (
                <div className="mini-card" key={`anniversary-${employee.employeeId}`}>
                  <div className="avatar guest-avatar">{String(employee.name).charAt(0).toUpperCase()}</div>
                  <div>
                    <strong>{employee.name}</strong>
                    <p>{employee.dateLabel} • {employee.years} year{employee.years === 1 ? '' : 's'}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : <p className="muted">No upcoming anniversaries.</p>}
        </section>
        <section className="panel">
          <div className="panel-header"><h3>Employees On Leave</h3><p>Current leave status</p></div>
          {processed.leaveEmployees.length ? (
            <div className="mini-list">
              {processed.leaveEmployees.map((employee) => (
                <div className="mini-card" key={`leave-${employee.employeeId}`}>
                  <div className="avatar leave-avatar">{String(employee.name).charAt(0).toUpperCase()}</div>
                  <div>
                    <strong>{employee.name}</strong>
                    <p>{employee.leaveNote || 'Leave scheduled'}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : <p className="muted">No employees marked on leave.</p>}
        </section>
      </section>
      <section className="grid-two">
        <section className="panel">
          <div className="panel-header"><h3>Regular Employees (Present)</h3><p>Live list with first in-time and avatar icon</p></div>
          <div className="table-wrap">
            <table className="compact-table">
              <thead>
                <tr>
                  <th>Photo Icon</th>
                  <th>Name</th>
                  <th>Present Since</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {processed.regularEmployees.filter((p) => p.inOffice).slice(0, 20).map((p) => (
                  <tr key={p.key}>
                    <td><div className="avatar">{String(p.name).charAt(0).toUpperCase()}</div></td>
                    <td>{p.name}</td>
                    <td>{p.firstInTodayTs ? formatDateTime(p.firstInTodayTs) : '-'}</td>
                    <td><span className="status-badge status-present">Present</span></td>
                  </tr>
                ))}
                {!processed.regularEmployees.some((p) => p.inOffice) && (
                  <tr>
                    <td colSpan="4" className="muted">No regular employees currently in office.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header"><h3>Guest Visits This Month</h3><p>Frequent visitors (2-3+ visits) and last seen time</p></div>
          <div className="table-wrap">
            <table className="compact-table">
              <thead>
                <tr>
                  <th>Photo Icon</th>
                  <th>Guest</th>
                  <th>Visits</th>
                  <th>Last Visit</th>
                </tr>
              </thead>
              <tbody>
                {processed.monthlyGuests.slice(0, 12).map((g) => (
                  <tr key={g.name}>
                    <td><div className="avatar guest-avatar">{String(g.name).charAt(0).toUpperCase()}</div></td>
                    <td>{g.name}</td>
                    <td>{g.visits}</td>
                    <td>{g.lastVisitTs ? formatDateTime(g.lastVisitTs) : '-'}</td>
                  </tr>
                ))}
                {!processed.monthlyGuests.length && (
                  <tr>
                    <td colSpan="4" className="muted">No guest visits recorded this month.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </section>
      <section className="panel">
        <div className="panel-header"><h3>Recent Face ID Feed</h3><p>Latest face photo with detected name and time</p></div>
        {processed.recentFaceFeed.length ? (
          <div className="face-feed-grid">
            {processed.recentFaceFeed.slice(0, 8).map((face) => (
              <a key={face.key} href={face.imageUrl} target="_blank" rel="noreferrer" className="face-feed-card">
                <img src={face.imageUrl} alt={face.imageName} className="face-feed-image" />
                <div className="face-feed-body">
                  <div className="face-feed-head">
                    <strong>{face.name}</strong>
                    <span className={`status-badge ${face.type === 'Employee' ? 'status-present' : face.type === 'Guest' ? 'status-on-break' : 'status-unknown'}`}>{face.type}</span>
                  </div>
                  <p>{formatDateTime(face.ts)}</p>
                </div>
              </a>
            ))}
          </div>
        ) : <p className="muted">No recent face photos available.</p>}
      </section>
    </>
  )

  const renderLive = () => {
    const recentRows = processed.todayEntries.slice(0, 40)
    return (
      <section className="panel">
        <div className="panel-header"><h3>Live Entry Monitor</h3><p>Most recent gate events</p></div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Employee Photo</th>
                <th>Name</th>
                <th>Entry Time</th>
                <th>Exit Time</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {recentRows.map((e) => {
                const person = processed.people.find((p) => (p.employeeId !== null ? p.employeeId === Number(e.employee_id) : p.name === (e.detected_name || e.employee_name)))
                const name = e.employee_name || e.detected_name || 'Unknown'
                const status = person?.status || (e.type === 'in' ? 'Present' : 'Left Office')
                return (
                  <tr key={e.id}>
                    <td><div className="avatar">{String(name).charAt(0).toUpperCase()}</div></td>
                    <td>{name}</td>
                    <td>{e.type === 'in' ? formatDateTime(e.ts) : '-'}</td>
                    <td>{e.type === 'out' ? formatDateTime(e.ts) : '-'}</td>
                    <td><span className={`status-badge status-${status.toLowerCase().replace(' ', '-')}`}>{status}</span></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>
    )
  }

  const renderDetections = () => (
    <>
      <section className="panel">
        <div className="panel-header"><h3>Recent Detection Images</h3><p>Detection snapshots moved out of dashboard</p></div>
        {data.recentDetections?.length ? (
          <div className="thumb-grid">
            {data.recentDetections.map((img, idx) => (
              <a key={`${img.name}-${idx}`} href={`${API_BASE_URL}${img.url}`} target="_blank" rel="noreferrer" className="thumb-card">
                <img src={`${API_BASE_URL}${img.url}`} alt={img.name} />
                <span>{img.name}</span>
              </a>
            ))}
          </div>
        ) : <p className="muted">No recent detection images.</p>}
      </section>
      <section className="panel">
        <div className="panel-header"><h3>Recent Face Crops</h3><p>Detected faces captured from crossings</p></div>
        {data.recentFaces?.length ? (
          <div className="thumb-grid">
            {data.recentFaces.map((img, idx) => (
              <a key={`${img.name}-${idx}`} href={`${API_BASE_URL}${img.url}`} target="_blank" rel="noreferrer" className="thumb-card">
                <img src={`${API_BASE_URL}${img.url}`} alt={img.name} />
                <span>{img.name}</span>
              </a>
            ))}
          </div>
        ) : <p className="muted">No recent face crops.</p>}
      </section>
    </>
  )

  const renderEmployees = () => {
    const regular = processed.regularEmployees.slice()

    const unknown = processed.people
      .filter((p) => p.employeeId === null)
      .map((p) => ({
        ...p,
        unknownStatus: p.inOffice ? 'Unknown Present' : 'Unverified Visitor',
        lastSeenTs: p.timelineAsc?.length ? p.timelineAsc[p.timelineAsc.length - 1].ts : null,
      }))
      .sort((a, b) => (b.lastSeenTs || 0) - (a.lastSeenTs || 0))

    return (
      <>
        <section className="panel">
          <div className="panel-header">
            <h3>Employee Directory</h3>
            <p>Modern profile cards with live presence state</p>
          </div>

          <div className="employees-summary-row">
            <article className="employees-summary-card">
              <h4>Regular Employees</h4>
              <strong>{regular.length}</strong>
            </article>
            <article className="employees-summary-card">
              <h4>Present Now</h4>
              <strong>{regular.filter((p) => p.inOffice).length}</strong>
            </article>
            <article className="employees-summary-card unknown-summary">
              <h4>Unknown Persons</h4>
              <strong>{unknown.length}</strong>
            </article>
          </div>

          {regular.length ? (
            <div className="employee-card-grid">
              {regular.map((p) => (
                <article className="employee-card" key={p.key}>
                  <div className="employee-head">
                    <div className="employee-avatar">{String(p.name).charAt(0).toUpperCase()}</div>
                    <div>
                      <h4>{p.name}</h4>
                      <p>{p.employeeCode || `EMP${String(p.employeeId).padStart(3, '0')}`} • {p.department}</p>
                    </div>
                  </div>
                  <div className="employee-meta">
                    <span>Phone: {p.phone || '-'}</span>
                    <span>Birthday: {formatMonthDay(p.birthday)}</span>
                    <span>Joined: {formatMonthDay(p.joinDate)}</span>
                    <span>Work: {formatHours(p.workHours)}</span>
                    <span>Last Event: {p.timelineAsc?.length ? formatDateTime(p.timelineAsc[p.timelineAsc.length - 1].ts) : '-'}</span>
                  </div>
                  <div className="employee-foot">
                    <span className={`status-badge status-${p.status.toLowerCase().replace(' ', '-')}`}>{p.status}</span>
                    {p.firstInTs ? <small>First In: {formatDateTime(p.firstInTs)}</small> : <small>No entry today</small>}
                  </div>
                </article>
              ))}
            </div>
          ) : <p className="muted">No regular employees found.</p>}
        </section>

        <section className="panel">
          <div className="panel-header">
            <h3>Unknown Person Management</h3>
            <p>Track unverified faces and current status for follow-up</p>
          </div>
          {unknown.length ? (
            <div className="unknown-card-grid">
              {unknown.map((u) => (
                <article className="unknown-card" key={u.key}>
                  <div className="employee-head">
                    <div className="employee-avatar unknown-avatar">{String(u.name).charAt(0).toUpperCase()}</div>
                    <div>
                      <h4>{u.name}</h4>
                      <p>Unregistered visitor profile</p>
                    </div>
                  </div>
                  <div className="employee-meta">
                    <span>Events: {u.timelineAsc?.length || 0}</span>
                    <span>Last Seen: {u.lastSeenTs ? formatDateTime(u.lastSeenTs) : '-'}</span>
                  </div>
                  <div className="employee-foot">
                    <span className="status-badge status-unknown">{u.unknownStatus}</span>
                    <small>Action: verify face and map to employee</small>
                  </div>
                </article>
              ))}
            </div>
          ) : <p className="muted">No unknown persons detected recently.</p>}
        </section>
      </>
    )
  }

  const renderAttendance = () => (
    <section className="panel">
      <div className="panel-header"><h3>Attendance & Work Hours</h3><p>Total hours, break duration, and timeline</p></div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Total Hours</th>
              <th>Break Duration</th>
              <th>Late Arrival</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {processed.people.map((p) => (
              <tr key={p.key}>
                <td>{p.name}</td>
                <td>{formatHours(p.workHours)}</td>
                <td>{Math.round(p.breakMinutes)} min</td>
                <td>{p.isLate ? 'Yes' : 'No'}</td>
                <td><span className={`status-badge status-${p.status.toLowerCase().replace(' ', '-')}`}>{p.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="timeline-wrap">
        {processed.people.slice(0, 4).map((p) => (
          <article className="timeline-card" key={`timeline-${p.key}`}>
            <h4>{p.name}</h4>
            <ul>
              {p.timelineAsc.slice(-8).map((ev) => (
                <li key={ev.id}>{new Date(ev.ts).toLocaleTimeString()} - {String(ev.type).toUpperCase()}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  )

  const renderAnalytics = () => (
    <>
      <section className="grid-two">
        <ChartCard
          title="Employee Presence Trend"
          subtitle="Today top working hours"
          type="bar"
          labels={processed.charts.topWorkHours.map((p) => p.name)}
          values={processed.charts.topWorkHours.map((p) => Number(p.workHours.toFixed(2)))}
          colors="#1d4ed8"
        />
        <ChartCard
          title="Late Arrival Chart"
          subtitle="Employees flagged as late"
          type="bar"
          labels={processed.charts.lateByEmployee.map((p) => p.name)}
          values={processed.charts.lateByEmployee.map((p) => p.firstInTs ? 1 : 0)}
          colors="#b91c1c"
        />
      </section>
      <section className="panel">
        <div className="panel-header"><h3>Heatmap Calendar</h3><p>Event density for last 28 days</p></div>
        <div className="heatmap-grid">
          {processed.charts.heatmap.map((h) => {
            const level = h.count > 16 ? 4 : h.count > 10 ? 3 : h.count > 5 ? 2 : h.count > 0 ? 1 : 0
            return <div key={h.key} className={`heatbox heat-${level}`} title={`${h.key}: ${h.count} events`} />
          })}
        </div>
      </section>
    </>
  )

  const renderAlerts = () => (
    <section className="panel">
      <div className="panel-header"><h3>Alert Panel</h3><p>Late arrivals, break violations, and unknown faces</p></div>
      {processed.alerts.length ? (
        <ul className="alerts-list">
          {processed.alerts.map((a, idx) => (
            <li key={`${a.level}-${idx}`} className={`alert-${a.level}`}>{a.text}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">No active alerts.</p>
      )}
    </section>
  )

  const renderHealth = () => {
    const groups = [
      {
        title: 'Infrastructure',
        keys: ['Frontend (Vite)', 'Backend API', 'PostgreSQL'],
      },
      {
        title: 'Detector Pipeline',
        keys: ['Detector Service (systemd)', 'GStreamer Pipeline', 'OpenCV Fallback', 'YOLO Frame Processing'],
      },
      {
        title: 'Camera & Detection',
        keys: ['RTSP Camera', 'Face Detection (ROI)', 'Last Detection Event'],
      },
      {
        title: 'Storage',
        keys: ['Face Crops Storage'],
      },
    ]

    const serviceMap = new Map(
      (systemHealth?.services || []).map((s) => [s.name, s])
    )

    const statusIcon = (status) => {
      if (status === 'ok') return '●'
      if (status === 'warn') return '◑'
      if (status === 'error') return '○'
      return '◌'
    }

    return (
      <>
        <section className="panel">
          <div className="panel-header">
            <div>
              <h3>System Health</h3>
              <p>
                Auto-refreshes every 5 s
                {healthLastUpdated ? ` · Last updated: ${healthLastUpdated.toLocaleTimeString()}` : ''}
              </p>
            </div>
            <button
              type="button"
              className="refresh-btn"
              onClick={() => refreshHealth(true)}
              disabled={healthChecking}
            >
              {healthChecking ? 'Refreshing…' : 'Refresh Now'}
            </button>
          </div>

          {!systemHealth ? (
            <p className="muted">Loading health status…</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              {groups.map((group) => {
                const rows = group.keys.map((k) => serviceMap.get(k)).filter(Boolean)
                if (!rows.length) return null
                return (
                  <div key={group.title}>
                    <h4 style={{ margin: '0 0 10px', fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.06em', color: '#64748b' }}>
                      {group.title}
                    </h4>
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Service</th>
                          <th>Status</th>
                          <th>Latency</th>
                          <th>Details</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((s) => (
                          <tr key={s.name}>
                            <td>
                              <span
                                style={{ marginRight: '6px', fontSize: '10px', color: s.status === 'ok' ? '#16a34a' : s.status === 'warn' ? '#d97706' : s.status === 'error' ? '#dc2626' : '#94a3b8' }}
                              >
                                {statusIcon(s.status)}
                              </span>
                              <strong>{s.name}</strong>
                            </td>
                            <td>
                              <span className={`health-badge health-${s.status}`}>
                                {s.status.toUpperCase()}
                              </span>
                            </td>
                            <td>{s.latency != null ? `${s.latency} ms` : '—'}</td>
                            <td className="muted">{s.note}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
              })}

              {/* Any services not in a group (future-proof) */}
              {(() => {
                const knownKeys = new Set(groups.flatMap((g) => g.keys))
                const extra = (systemHealth.services || []).filter((s) => !knownKeys.has(s.name))
                if (!extra.length) return null
                return (
                  <div>
                    <h4 style={{ margin: '0 0 10px', fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.06em', color: '#64748b' }}>
                      Other
                    </h4>
                    <table className="data-table">
                      <thead><tr><th>Service</th><th>Status</th><th>Latency</th><th>Details</th></tr></thead>
                      <tbody>
                        {extra.map((s) => (
                          <tr key={s.name}>
                            <td><strong>{s.name}</strong></td>
                            <td><span className={`health-badge health-${s.status}`}>{s.status.toUpperCase()}</span></td>
                            <td>{s.latency != null ? `${s.latency} ms` : '—'}</td>
                            <td className="muted">{s.note}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
              })()}
            </div>
          )}
        </section>
      </>
    )
  }

  const renderSettings = () => (
    <section className="panel">
      <div className="panel-header"><h3>Settings</h3><p>System integration configuration</p></div>
      <div className="settings-grid">
        <div><strong>API Base URL</strong><p>{API_BASE_URL}</p></div>
        <div><strong>Database</strong><p>PostgreSQL via Docker (office-ai-postgres)</p></div>
        <div><strong>Detection Engine</strong><p>Python · OpenCV + YOLOv8n</p></div>
        <div><strong>Face Recognition</strong><p>face_recognition · known_faces/</p></div>
        <div><strong>Frontend</strong><p>React 18 + Vite · port 5173</p></div>
        <div><strong>RTSP Camera</strong><p>192.168.2.103:554 · channel 2</p></div>
      </div>
      <div className="panel-header" style={{marginTop:'24px'}}><h4>Detection Command</h4></div>
      <pre className="code-block">{`python3 python-scripts/line_counter.py \\
  --url "rtsp://admin:<password>@192.168.2.103:554/cam/realmonitor?channel=2&subtype=0" \\
  --model python-scripts/yolov8n.pt \\
  --roi-file python-scripts/roi_cam2.json \\
  --line-x-margin 120 \\
  --backend http://localhost:3001/api/entries \\
  --post \\
  --save-crops python-scripts/crossings \\
  --save-faces-only \\
  --crossing-only \\
  --face-recognition`}</pre>
    </section>
  )

  const renderView = () => {
    if (activeView === 'dashboard') return renderDashboard()
    if (activeView === 'detections') return renderDetections()
    if (activeView === 'live') return renderLive()
    if (activeView === 'employees') return renderEmployees()
    if (activeView === 'attendance') return renderAttendance()
    if (activeView === 'analytics') return renderAnalytics()
    if (activeView === 'alerts') return renderAlerts()
    if (activeView === 'health') return renderHealth()
    if (activeView === 'settings') return renderSettings()
    return null
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <h1>Nirikshana</h1>
          <p>Workforce Observation</p>
        </div>
        <nav>
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={activeView === item.id ? 'nav-btn active' : 'nav-btn'}
              onClick={() => setActiveView(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="content">
        <header className="topbar panel">
          <div>
            <h2>Nirikshana Entry and Exit Dashboard</h2>
          </div>
          <button type="button" className="refresh-btn" onClick={load} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </header>

        {loading ? (
          <section className="panel"><p className="muted">Loading dashboard data...</p></section>
        ) : renderView()}
      </main>
    </div>
  )
}
