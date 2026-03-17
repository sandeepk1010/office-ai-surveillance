r"""
Line-crossing ROI monitor (FFmpeg + Pillow version)

Uses FFmpeg for RTSP stream decoding and Pillow for frame processing
instead of OpenCV to avoid DLL loading issues on Windows.

Usage:
    python line_counter_ffmpeg.py --url 'rtsp://admin:India123%23@192.168.2.103:554/cam/realmonitor?channel=1&subtype=0' --post --display
    python line_counter_ffmpeg.py --video local.mp4 --post --display
"""

import os
import sys
import time
import argparse
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io
import math
import requests

def euclid(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])


class SimpleTracker:
    def __init__(self, max_lost=30, max_distance=50):
        self.next_id = 1
        self.objects = {}  # id -> centroid
        self.lost = {}     # id -> lost frames
        self.max_lost = max_lost
        self.max_distance = max_distance
        self.prev_side = {}  # id -> previous side of line

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


def post_event(backend_url, direction):
    payload = {'employee_id': None, 'type': direction}
    try:
        r = requests.post(backend_url, json=payload, timeout=5)
        print('Posted event:', direction, '->', r.status_code)
    except Exception as e:
        print('Failed to post event:', e)


def open_ffmpeg_stream(source, width, height):
    """Open video stream using FFmpeg"""
    ffmpeg_cmd = [
        'ffmpeg',
        '-rtsp_transport', 'tcp',
        '-i', source,
        '-f', 'rawvideo',
        '-pix_fmt', 'bgr24',
        '-an',
        '-'
    ]
    
    proc = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=10**8
    )
    
    return proc


def mask_from_frame(pil_frame, threshold=50):
    """Detect foreground using simple frame differencing"""
    # Convert to grayscale numpy array
    gray = np.array(pil_frame.convert('L'))
    
    # Simple threshold (could be improved withbackground subtraction)
    _, mask = (gray > threshold, gray <= threshold)
    return (gray > threshold).astype(np.uint8) * 255


def find_centroids(frame_data, width, height, min_area=500):
    """Find centroids from frame data"""
    centroids = []
    
    # Simple blob detection - find white regions
    mask_array = np.frombuffer(frame_data, dtype=np.uint8).reshape((height, width, 3))
    # Convert BGR to grayscale
    gray = (mask_array[:,:,0].astype(float) * 0.299 + 
            mask_array[:,:,1].astype(float) * 0.587 +
            mask_array[:,:,2].astype(float) * 0.114).astype(np.uint8)
    
    # Find moving objects (simplified - any non-black pixels)
    _, binary = (gray > 30, gray <= 30)
    binary_mask = (gray > 50).astype(np.uint8)
    
    # Find contours manually (simple region finding)
    from scipy import ndimage
    labeled, num_features = ndimage.label(binary_mask)
    
    for i in range(1, num_features + 1):
        points = np.where(labeled == i)
        if len(points[0]) < min_area:
            continue
        cy, cx = np.mean(points[0]), np.mean(points[1])
        centroids.append((int(cx), int(cy)))
    
    return centroids


def frame_generator_ffmpeg(source, width, height, is_rtsp=True):
    """Generate frames from FFmpeg"""
    proc = open_ffmpeg_stream(source, width, height)
    frame_size = width * height * 3
    
    while True:
        frame_data = proc.stdout.read(frame_size)
        if len(frame_data) < frame_size:
            break
        
        # Convert BGR array to PIL Image
        frame_array = np.frombuffer(frame_data, dtype=np.uint8).reshape((height, width, 3))
        # BGR to RGB
        frame_array = frame_array[:, :, ::-1]
        frame = Image.fromarray(frame_array, 'RGB')
        yield frame
    
    proc.terminate()


def monitor(source, args):
    is_rtsp = source.startswith('rtsp://') or source.startswith('rtsps://')
    
    width = args.width
    height = args.height
    
    print(f'Opening {"RTSP" if is_rtsp else "video"} source: {source}')
    print(f'Using dimensions: {width}x{height}')
    
    line_y = int(height * args.line_fraction)
    print(f'ROI line at y={line_y}')
    
    tracker = SimpleTracker(max_lost=30, max_distance=args.match_distance)
    
    frame_count = 0
    prev_frame = None
    
    try:
        gen = frame_generator_ffmpeg(source, width, height, is_rtsp)
        
        for frame in gen:
            if prev_frame is None:
                prev_frame = frame
                continue
            
            # Simple frame differencing for motion detection
            prev_array = np.array(prev_frame)
            curr_array = np.array(frame)
            diff = np.abs(prev_array.astype(float) - curr_array.astype(float))
            motion_mask = (np.mean(diff, axis=2) > 10).astype(np.uint8) * 255
            
            # Find centroids from motion
            from scipy import ndimage
            if motion_mask.max() > 0:
                labeled, num_features = ndimage.label(motion_mask)
                centroids = []
                for i in range(1, num_features + 1):
                    points = np.where(labeled == i)
                    if len(points[0]) < args.min_area:
                        continue
                    cy, cx = np.mean(points[0]), np.mean(points[1])
                    centroids.append((int(cx), int(cy)))
            else:
                centroids = []
            
            # Update tracker
            tracker.update(centroids, line_y)
            
            # Check for crossings
            for oid, centroid in tracker.get_objects().items():
                prev = tracker.prev_side.get(oid)
                curr_side = 0 if centroid[1] < line_y else 1
                if prev is not None and curr_side != prev:
                    direction = 'in' if prev == 0 and curr_side == 1 else 'out'
                    ts = int(time.time() * 1000)
                    print(f'Object {oid} crossed: {direction} at {ts}')
                    if args.post:
                        post_event(args.backend or 'http://localhost:3001/api/entries', direction)
                tracker.prev_side[oid] = curr_side
            
            # Display
            if args.display and frame_count % 5 == 0:  # Show every 5th frame to save bandwidth
                vis = frame.copy()
                draw = ImageDraw.Draw(vis)
                # Draw line
                draw.line([(0, line_y), (width, line_y)], fill=(0, 255, 255), width=2)
                # Draw centroids
                for oid, centroid in tracker.get_objects().items():
                    x, y = centroid
                    draw.ellipse([x-6, y-6, x+6, y+6], fill=(255, 0, 0))
                    draw.text((x+5, y-5), str(oid), fill=(255, 255, 255))
                
                # Show using available viewer
                try:
                    vis.show()
                except:
                    pass  # No display available
            
            prev_frame = frame
            frame_count += 1
            
            if frame_count % 100 == 0:
                print(f'Processed {frame_count} frames, tracked {len(tracker.get_objects())} objects')
    
    except KeyboardInterrupt:
        print('Interrupted by user')
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
    
    return 0


def main():
    p = argparse.ArgumentParser(description='Line-crossing ROI monitor using FFmpeg')
    p.add_argument('--url', help='RTSP URL')
    p.add_argument('--video', help='Local video file')
    p.add_argument('--width', type=int, default=1920, help='Stream width')
    p.add_argument('--height', type=int, default=1080, help='Stream height')
    p.add_argument('--line-fraction', type=float, default=0.5, help='ROI line vertical fraction')
    p.add_argument('--min-area', type=int, default=500, help='Minimum object area')
    p.add_argument('--match-distance', type=int, default=60, help='Max tracking distance')
    p.add_argument('--post', action='store_true', help='POST events to backend')
    p.add_argument('--backend', help='Backend URL')
    p.add_argument('--display', action='store_true', help='Show video')
    
    args = p.parse_args()
    
    source = args.video or args.url or os.environ.get('RTSP_URL')
    if not source:
        print('No source provided. Use --video, --url, or set RTSP_URL')
        p.print_help()
        return 2
    
    return monitor(source, args)


if __name__ == '__main__':
    raise SystemExit(main())
