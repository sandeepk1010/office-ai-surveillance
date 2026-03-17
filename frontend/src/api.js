export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:3001'

export async function fetchDashboard() {
  const res = await fetch(`${API_BASE_URL}/api/dashboard`)
  if (!res.ok) throw new Error('Failed to fetch dashboard')
  return res.json()
}

export async function fetchSystemHealth() {
  const res = await fetch(`${API_BASE_URL}/api/health`)
  if (!res.ok) throw new Error('Health check failed')
  return res.json()
}
