import React, { useEffect, useRef } from 'react'
import { Chart, BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend } from 'chart.js'

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend)

export default function UsageChart({ usage = [] }) {
  const canvasRef = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    const ctx = canvasRef.current.getContext('2d')
    if (chartRef.current) chartRef.current.destroy()
    chartRef.current = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: usage.map(u => u.app),
        datasets: [{ label: 'Minutes', data: usage.map(u => u.total_minutes), backgroundColor: '#3b82f6' }]
      },
      options: { responsive: true, maintainAspectRatio: false }
    })

    return () => {
      if (chartRef.current) chartRef.current.destroy()
    }
  }, [usage])

  return <canvas ref={canvasRef} />
}
