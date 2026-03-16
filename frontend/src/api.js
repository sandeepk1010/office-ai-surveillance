export async function fetchDashboard() {
  const res = await fetch('http://localhost:3000/api/dashboard')
  if (!res.ok) throw new Error('Failed to fetch dashboard')
  return res.json()
}
