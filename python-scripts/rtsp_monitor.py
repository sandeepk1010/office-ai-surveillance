"""
RTSP monitor: connects to an RTSP stream, logs status, and saves periodic snapshots.

Usage examples (PowerShell):

# Option A: provide a full RTSP URL
# $env:RTSP_URL='rtsp://admin:India123%23@192.168.1.245:554/cam/realmonitor?channel=1&subtype=0'
# python python-scripts\rtsp_monitor.py

# Option B: provide components and let the script build the URL
$env:RTSP_USER='admin'
$env:RTSP_PASS='India123#'
$env:RTSP_HOST='192.168.1.245'
$env:RTSP_PORT='554'
# channel and subtype are optional; defaults shown below
# python python-scripts\rtsp_monitor.py --channel 1 --subtype 0

Note: when embedding passwords containing special characters in a URL, percent-encode them (e.g. '#' -> '%23').
This script does NOT store credentials; prefer environment variables for safety.
"""

import os
import time
import argparse
from urllib.parse import quote
import cv2


def build_url_from_env(channel, subtype):
    user = os.environ.get('RTSP_USER')
    pwd = os.environ.get('RTSP_PASS')
    host = os.environ.get('RTSP_HOST')
    port = os.environ.get('RTSP_PORT', '554')
    if not (user and pwd and host):
        raise SystemExit('Set RTSP_URL or RTSP_USER/RTSP_PASS/RTSP_HOST in environment')
    pwd_enc = quote(pwd, safe='')
    return f'rtsp://{user}:{pwd_enc}@{host}:{port}/cam/realmonitor?channel={channel}&subtype={subtype}'


def monitor(url, out_dir='snapshots', interval=5, max_snapshots=0):
    os.makedirs(out_dir, exist_ok=True)
    print(f'Connecting to {url}')
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        print('Failed to open stream')
        return 1

    print('Stream opened — capturing frames')
    count = 0
    start = time.time()
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print('Frame read failed — retrying in 1s')
                time.sleep(1)
                continue

            # save snapshot every `interval` seconds
            now = time.time()
            if now - start >= interval:
                filename = os.path.join(out_dir, f'shot_{int(now)}.jpg')
                cv2.imwrite(filename, frame)
                print('Saved', filename)
                start = now
                count += 1
                if max_snapshots and count >= max_snapshots:
                    print('Reached max snapshots, exiting')
                    break

            # small sleep to avoid busy loop; adjust as needed
            time.sleep(0.1)

    except KeyboardInterrupt:
        print('Interrupted by user')
    finally:
        cap.release()
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--url', help='Full RTSP URL')
    p.add_argument('--channel', default='1', help='Camera channel')
    p.add_argument('--subtype', default='0', help='Stream subtype (0=main,1=sub)')
    p.add_argument('--interval', type=int, default=5, help='Snapshot interval seconds')
    p.add_argument('--out', default='snapshots', help='Output directory for snapshots')
    p.add_argument('--max', type=int, default=0, help='Max snapshots to capture (0 = unlimited)')
    args = p.parse_args()

    url = args.url or os.environ.get('RTSP_URL')
    if not url:
        try:
            url = build_url_from_env(args.channel, args.subtype)
        except SystemExit as e:
            print(e)
            p.print_help()
            return 2

    return monitor(url, out_dir=args.out, interval=args.interval, max_snapshots=args.max)


if __name__ == '__main__':
    raise SystemExit(main())
