import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

try {
	// global handlers to surface runtime issues in the page
	window.addEventListener('error', (ev) => {
		const msg = document.createElement('pre')
		msg.style.color = 'red'
		msg.textContent = 'Runtime error: ' + (ev.error && ev.error.stack ? ev.error.stack : ev.message)
		document.body.innerHTML = ''
		document.body.appendChild(msg)
	})
	window.addEventListener('unhandledrejection', (ev) => {
		const msg = document.createElement('pre')
		msg.style.color = 'red'
		msg.textContent = 'Unhandled rejection: ' + (ev.reason && ev.reason.stack ? ev.reason.stack : ev.reason)
		document.body.innerHTML = ''
		document.body.appendChild(msg)
	})
	console.log('main.jsx loaded')
	const el = document.getElementById('root')
	if (!el) throw new Error('Root element not found')
	const root = createRoot(el)
	root.render(<App />)
} catch (err) {
	console.error('Render error', err)
	const msg = document.createElement('pre')
	msg.style.color = 'red'
	msg.textContent = 'Frontend render error: ' + err.stack
	document.body.innerHTML = ''
	document.body.appendChild(msg)
}
