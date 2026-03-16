import React, { useEffect, useState } from 'react'
import UsageChart from './chart/UsageChart'
import { fetchDashboard } from './api'

export default function App() {
  const [data, setData] = useState({ employees: [], entries: [], usage: [] })
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState(null)

  useEffect(() => {
    let alive = true

    const load = async () => {
      try {
        const d = await fetchDashboard()
        if (!alive) return
        setData(d)
        setLastUpdated(new Date())
      } catch (err) {
        console.error(err)
      } finally {
        if (alive) setLoading(false)
      }
    }

    load()
    const timer = setInterval(load, 3000)

    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])

  return (
    <div className="max-w-6xl mx-auto p-6">
      <h1 className="text-3xl font-bold mb-4">Office — Entry/Exit & Mobile Usage Dashboard</h1>
      <div className="text-xs text-gray-500 mb-4">
        Auto-refresh: every 3s{lastUpdated ? ` | Last updated: ${lastUpdated.toLocaleTimeString()}` : ''}
      </div>

      {loading ? (
        <div>Loading…</div>
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="col-span-2 bg-white rounded shadow p-4">
              <h2 className="font-semibold mb-2">Entries (recent)</h2>
              <div className="text-sm text-gray-700">
                {data.entries && data.entries.length ? (
                  <ul className="divide-y">
                    {data.entries.slice(0, 30).map(e => (
                      <li key={e.id} className="py-2 flex justify-between items-center">
                        <div>{e.employee_name || 'Unknown'} — {e.type}</div>
                        <div className="text-xs text-gray-500">{new Date(e.ts).toLocaleString()}</div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div>No entries yet</div>
                )}
              </div>
            </div>

            <div className="bg-white rounded shadow p-4">
              <h2 className="font-semibold mb-2">Top App Usage</h2>
              <div style={{ height: 200 }}>
                <UsageChart usage={data.usage || []} />
              </div>
              <h3 className="font-medium mt-4">Top Mobile Users</h3>
              <div className="text-sm mt-2">
                {data.usageByEmployee && data.usageByEmployee.length ? (
                  <ul className="divide-y">
                    {data.usageByEmployee.map(u => (
                      <li key={u.employee_id} className="py-2 flex justify-between">
                        <div>{u.employee_name || `#${u.employee_id}`}</div>
                        <div className="text-xs text-gray-500">{u.total_minutes} min</div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="text-xs text-gray-500">No mobile usage data</div>
                )}
              </div>
            </div>
          </div>

          <div className="mt-6 bg-white rounded shadow p-4">
            <h2 className="font-semibold mb-2">Employees</h2>
            {data.employees && data.employees.length ? (
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-gray-500"><tr><th className="p-2">ID</th><th className="p-2">Name</th><th className="p-2">Mobile</th></tr></thead>
                <tbody>
                  {data.employees.map(emp => (
                    <tr key={emp.id}><td className="p-2">{emp.id}</td><td className="p-2">{emp.name}</td><td className="p-2">{emp.mobile || ''}</td></tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div>No employees</div>
            )}
          </div>

          <div className="mt-6 bg-white rounded shadow p-4">
            <h2 className="font-semibold mb-2">Recent Crossing Images</h2>
            {data.recentCrossings && data.recentCrossings.length ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {data.recentCrossings.map((img, idx) => (
                  <a key={`${img.name}-${idx}`} href={`http://localhost:3000${img.url}`} target="_blank" rel="noreferrer" className="block border rounded overflow-hidden">
                    <img src={`http://localhost:3000${img.url}`} alt={img.name} className="w-full h-28 object-cover" />
                    <div className="text-[11px] p-1 text-gray-600 truncate">{img.name}</div>
                  </a>
                ))}
              </div>
            ) : (
              <div className="text-xs text-gray-500">No crossing images yet</div>
            )}
          </div>

          <div className="mt-6 bg-white rounded shadow p-4">
            <h2 className="font-semibold mb-2">Recent Detection Snapshots</h2>
            {data.recentDetections && data.recentDetections.length ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {data.recentDetections.map((img, idx) => (
                  <a key={`${img.name}-${idx}`} href={`http://localhost:3000${img.url}`} target="_blank" rel="noreferrer" className="block border rounded overflow-hidden">
                    <img src={`http://localhost:3000${img.url}`} alt={img.name} className="w-full h-28 object-cover" />
                    <div className="text-[11px] p-1 text-gray-600 truncate">{img.name}</div>
                  </a>
                ))}
              </div>
            ) : (
              <div className="text-xs text-gray-500">No detection snapshots yet</div>
            )}
          </div>

          <div className="mt-6 bg-white rounded shadow p-4">
            <h2 className="font-semibold mb-2">Recent Face Crops</h2>
            {data.recentFaces && data.recentFaces.length ? (
              <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
                {data.recentFaces.map((img, idx) => (
                  <a key={`${img.name}-${idx}`} href={`http://localhost:3000${img.url}`} target="_blank" rel="noreferrer" className="block border rounded overflow-hidden">
                    <img src={`http://localhost:3000${img.url}`} alt={img.name} className="w-full h-24 object-cover" />
                    <div className="text-[11px] p-1 text-gray-600 truncate">{img.name}</div>
                  </a>
                ))}
              </div>
            ) : (
              <div className="text-xs text-gray-500">No face crops yet</div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
