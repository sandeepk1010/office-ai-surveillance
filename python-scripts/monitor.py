"""
Simple Python monitor script that fetches the dashboard data
from the backend and prints a short summary. Requires Python 3.7+.

Usage:
    python monitor.py

"""
import sys
import json
import os
from urllib.request import urlopen, Request

API = os.environ.get('DASHBOARD_API_URL', 'http://localhost:3001/api/dashboard')

def fetch_dashboard():
    req = Request(API, headers={"User-Agent": "python-monitor/1.0"})
    with urlopen(req, timeout=10) as resp:
        return json.load(resp)

def summarize(d):
    out = []
    out.append(f"Employees: {len(d.get('employees', []))}")
    out.append(f"Recent entries: {len(d.get('entries', []))}")
    usage = d.get('usage', [])
    top = ', '.join([f"{u['app']}({u['total_minutes']}m)" for u in usage[:5]]) or 'none'
    out.append(f"Top usage: {top}")
    return '\n'.join(out)

def main():
    try:
        d = fetch_dashboard()
    except Exception as e:
        print('Failed to fetch dashboard:', e)
        sys.exit(2)
    print(summarize(d))

if __name__ == '__main__':
    main()
