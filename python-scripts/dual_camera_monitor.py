r"""
Dual-camera line-crossing ROI monitor

Monitors two RTSP cameras simultaneously, tracking people crossing lines
and posting entry/exit events to the backend.

Usage:
    python dual_camera_monitor.py --post --display
    
    # Or configure custom URLs:
    python dual_camera_monitor.py --cam1 'rtsp://...' --cam2 'rtsp://...' --post --display
"""

import os
import sys
import time
import argparse
import threading
import queue
from collections import defaultdict
import math
import subprocess
import numpy as np

import cv2
import requests


def euclid(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])


class SimpleTracker:
    def __init__(self, max_lost=30, max_distance=50):
        self.next_id = 1
        self.objects = {}
        self.lost = {}
        self.max_lost = max_lost
        self.max_distance = max_distance
        self.prev_side = {}

    def update(self, detections, line_y):
        assigned = {}
        for det in detections:
            best_id = None
            best_dist = None
            for oid, centroid in self.objects.items():
                d = euclid(det, centroid)
                if d <= self.max_distance and (best_dist is None or d < best_dist):
                    best_dist = d
                    best_id = oid

            if best_id is not None:
                assigned[best_id] = det
            else:
                oid = self.next_id
                self.next_id += 1
                self.objects[oid] = det
                self.lost[oid] = 0
                self.prev_side[oid] = 0 if det[1] < line_y else 1

        for oid, centroid in assigned.items():
            self.objects[oid] = centroid
            self.lost[oid] = 0

        for oid in list(self.objects.keys()):
            if oid not in assigned:
                self.lost[oid] = self.lost.get(oid, 0) + 1
                if self.lost[oid] > self.max_lost:
                    del self.objects[oid]
                    del self.lost[oid]
                    if oid in self.prev_side:
                        del self.prev_side[oid]

    def get_objects(self):
        return dict(self.objects)


def find_centroids(mask, min_area=500):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    centroids = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area:
            continue
        M = cv2.moments(c)
        if M['m00'] == 0:
            continue
        cx = int(M['m10']/M['m00'])
        cy = int(M['m01']/M['m00'])
        centroids.append((cx, cy))
    return centroids


def post_event(backend_url, direction, camera_id):
    payload = {
        'employee_id': None,
        'type': direction,
        'camera_id': camera_id
    }
    try:
        r = requests.post(backend_url, json=payload, timeout=5)
        print(f'[Camera {camera_id}] Posted event: {direction} -> {r.status_code}')
    except Exception as e:
        print(f'[Camera {camera_id}] Failed to post event: {e}')


def monitor_camera(source, camera_id, args, stop_event, line_fraction=None):
    """Monitor a single camera in a thread"""
    print(f'[Camera {camera_id}] Starting monitor for: {source}')
    
    # Open video capture
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f'[Camera {camera_id}] ERROR: Failed to open source')
        return
    
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
    print(f'[Camera {camera_id}] Stream size: {width}x{height}')
    
    # Use camera-specific line fraction if provided, otherwise use default
    if line_fraction is None:
        line_fraction = args.line_fraction
    line_y = int(height * line_fraction)
    print(f'[Camera {camera_id}] ROI line at y={line_y} ({line_fraction*100:.0f}% of frame height)')
    
    backSub = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=25, detectShadows=True)
    tracker = SimpleTracker(max_lost=30, max_distance=args.match_distance)
    
    window_name = f'Camera {camera_id} - ROI Monitor'
    frame_count = 0
    
    try:
        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                print(f'[Camera {camera_id}] Frame read failed - reconnecting...')
                cap.release()
                time.sleep(2)
                cap = cv2.VideoCapture(source)
                continue
            
            fg = backSub.apply(frame)
            _, fg = cv2.threshold(fg, 244, 255, cv2.THRESH_BINARY)
            fg = cv2.medianBlur(fg, 5)
            fg = cv2.dilate(fg, None, iterations=2)
            
            centroids = find_centroids(fg, min_area=args.min_area)
            tracker.update(centroids, line_y)
            
            # Check for crossings
            for oid, centroid in tracker.get_objects().items():
                prev = tracker.prev_side.get(oid)
                curr_side = 0 if centroid[1] < line_y else 1
                if prev is not None and curr_side != prev:
                    direction = 'in' if prev == 0 and curr_side == 1 else 'out'
                    ts = int(time.time() * 1000)
                    print(f'[Camera {camera_id}] Object {oid} crossed: {direction} at {ts}')
                    if args.post:
                        post_event(args.backend, direction, camera_id)
                tracker.prev_side[oid] = curr_side
            
            # Display
            if args.display:
                vis = frame.copy()
                cv2.line(vis, (0, line_y), (width, line_y), (0, 255, 255), 2)
                for oid, centroid in tracker.get_objects().items():
                    cv2.circle(vis, centroid, 6, (0, 0, 255), -1)
                    cv2.putText(vis, str(oid), (centroid[0]+5, centroid[1]-5), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)
                
                # Add camera label
                cv2.putText(vis, f'Camera {camera_id}', (10, 30), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                
                cv2.imshow(window_name, vis)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    stop_event.set()
                    break
            
            frame_count += 1
            
            if frame_count % 100 == 0:
                print(f'[Camera {camera_id}] Processed {frame_count} frames, '
                      f'tracking {len(tracker.get_objects())} objects')
    
    except KeyboardInterrupt:
        print(f'[Camera {camera_id}] Interrupted')
    except Exception as e:
        print(f'[Camera {camera_id}] ERROR: {e}')
        import traceback
        traceback.print_exc()
    finally:
        cap.release()
        if args.display:
            cv2.destroyWindow(window_name)
        print(f'[Camera {camera_id}] Monitor stopped')


def main():
    p = argparse.ArgumentParser(description='Dual-camera line-crossing monitor')
    p.add_argument('--cam1', 
                   default='rtsp://admin:India123%23@192.168.1.245:554/cam/realmonitor?channel=1&subtype=0',
                   help='Camera 1 RTSP URL (Channel 1)')
    p.add_argument('--cam2',
                   default='rtsp://admin:India123%23@192.168.1.245:554/cam/realmonitor?channel=2&subtype=0',
                   help='Camera 2 RTSP URL (Channel 2)')
    p.add_argument('--line-fraction', type=float, default=0.5,
                   help='Default vertical fraction for ROI line (0..1)')
    p.add_argument('--line1', type=float, default=None,
                   help='Camera 1 ROI line fraction (overrides --line-fraction)')
    p.add_argument('--line2', type=float, default=None,
                   help='Camera 2 ROI line fraction (overrides --line-fraction)')
    p.add_argument('--min-area', type=int, default=500,
                   help='Minimum contour area')
    p.add_argument('--match-distance', type=int, default=60,
                   help='Max distance to match centroids')
    p.add_argument('--post', action='store_true',
                   help='POST events to backend')
    p.add_argument('--backend', default='http://localhost:3000/api/entries',
                   help='Backend entries endpoint')
    p.add_argument('--display', action='store_true',
                   help='Show video windows with overlays')
    
    args = p.parse_args()
    
    # Allow env var overrides
    cam1_url = os.environ.get('RTSP_URL_CAM1') or args.cam1
    cam2_url = os.environ.get('RTSP_URL_CAM2') or args.cam2
    
    # Determine line fractions for each camera
    line1_fraction = args.line1 if args.line1 is not None else args.line_fraction
    line2_fraction = args.line2 if args.line2 is not None else args.line_fraction
    
    print('=' * 60)
    print('DUAL CAMERA LINE-CROSSING MONITOR')
    print('=' * 60)
    print(f'Camera 1: {cam1_url}')
    print(f'  ROI Line: {line1_fraction*100:.0f}% from top')
    print(f'Camera 2: {cam2_url}')
    print(f'  ROI Line: {line2_fraction*100:.0f}% from top')
    print(f'Backend: {args.backend}')
    print(f'Display: {args.display}')
    print(f'Post events: {args.post}')
    print('=' * 60)
    print('Press Ctrl+C to stop all cameras')
    print('Press Q in video window to quit')
    print('=' * 60)
    
    stop_event = threading.Event()
    
    # Start monitoring threads
    thread1 = threading.Thread(target=monitor_camera, 
                               args=(cam1_url, 1, args, stop_event, line1_fraction),
                               daemon=True)
    thread2 = threading.Thread(target=monitor_camera,
                               args=(cam2_url, 2, args, stop_event, line2_fraction),
                               daemon=True)
    
    thread1.start()
    thread2.start()
    
    try:
        # Keep main thread alive
        while thread1.is_alive() or thread2.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print('\n\nStopping all cameras...')
        stop_event.set()
    
    # Wait for threads to finish
    thread1.join(timeout=3)
    thread2.join(timeout=3)
    
    if args.display:
        cv2.destroyAllWindows()
    
    print('\nAll cameras stopped. Goodbye!')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
