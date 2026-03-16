const API = 'http://localhost:3000/api';

async function fetchDashboard() {
  const res = await fetch(API + '/dashboard');
  return res.json();
}

function renderEntries(entries) {
  const el = document.getElementById('entries');
  if (!entries || entries.length === 0) return (el.innerText = 'No entries yet');
  el.innerHTML = '';
  const ul = document.createElement('ul');
  ul.className = 'divide-y';
  entries.slice(0, 30).forEach(e => {
    const li = document.createElement('li');
    li.className = 'py-2 flex justify-between items-center';
    const left = document.createElement('div');
    left.innerText = `${e.employee_name || 'Unknown'} — ${e.type}`;
    const right = document.createElement('div');
    right.className = 'text-xs text-gray-500';
    right.innerText = new Date(e.ts).toLocaleString();
    li.appendChild(left);
    li.appendChild(right);
    ul.appendChild(li);
  });
  el.appendChild(ul);
}

function renderEmployees(employees) {
  const el = document.getElementById('employees');
  if (!employees || employees.length === 0) return (el.innerText = 'No employees');
  const table = document.createElement('table');
  table.className = 'w-full text-sm';
  table.innerHTML = `<thead class="text-left text-xs text-gray-500"><tr><th class="p-2">ID</th><th class="p-2">Name</th><th class="p-2">Mobile</th></tr></thead>`;
  const tbody = document.createElement('tbody');
  employees.forEach(emp => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td class="p-2">${emp.id}</td><td class="p-2">${emp.name}</td><td class="p-2">${emp.mobile || ''}</td>`;
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  el.innerHTML = '';
  el.appendChild(table);
}

let usageChart = null;
function renderUsage(usage) {
  const ctx = document.getElementById('usageChart').getContext('2d');
  const labels = usage.map(u => u.app);
  const data = usage.map(u => u.total_minutes);
  if (usageChart) usageChart.destroy();
  usageChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{ label: 'Minutes', data, backgroundColor: '#3b82f6' }]
    },
    options: { responsive: true, maintainAspectRatio: false }
  });
}

async function init() {
  try {
    const d = await fetchDashboard();
    renderEntries(d.entries);
    renderEmployees(d.employees);
    renderUsage(d.usage || []);
  } catch (err) {
    console.error(err);
    document.body.insertAdjacentHTML('beforeend', '<div class="p-4 text-red-600">Failed to load dashboard. Is the backend running?</div>');
  }
}

init();
