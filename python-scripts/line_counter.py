"""
Office in/out detector using GStreamer + YOLO.

This script reads frames through a GStreamer appsink pipeline, runs YOLO person
detection on each frame, tracks centroids, and emits in/out events when tracked
objects cross a horizontal ROI line.
"""

import os
import csv
import json
import math
import time
import argparse
import importlib
import threading
from datetime import datetime
from urllib.parse import quote, unquote
import cv2

import numpy as np
import requests
from frame_sources import (
    GStreamerCliFrameSource,
    GStreamerFrameSource,
    OpenCVFrameSource,
    resolve_gst_launch_bin,
)

Gst = None


def euclid(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


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
        matched_detection_indexes = set()

        # Build all viable object/detection matches and assign greedily by distance.
        candidate_pairs = []
        for det_index, det in enumerate(detections):
            for oid, centroid in self.objects.items():
                d = euclid(det, centroid)
                if d <= self.max_distance:
                    candidate_pairs.append((d, oid, det_index, det))

        candidate_pairs.sort(key=lambda item: item[0])

        matched_object_ids = set()
        for _distance, oid, det_index, det in candidate_pairs:
            if oid in matched_object_ids or det_index in matched_detection_indexes:
                continue
            assigned[oid] = det
            matched_object_ids.add(oid)
            matched_detection_indexes.add(det_index)

        # Create new tracked objects for any unmatched detections.
        for det_index, det in enumerate(detections):
            if det_index in matched_detection_indexes:
                continue
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


def detect_person_centroids(model, frame, conf_threshold, device):
    """Returns (centroids, raw_boxes) where raw_boxes is list of (x1,y1,x2,y2) ints."""
    results = model.predict(frame, classes=[0], conf=conf_threshold, verbose=False, device=device)
    boxes = results[0].boxes
    centroids = []
    raw_boxes = []

    if boxes is None or boxes.xyxy is None:
        return centroids, raw_boxes

    xyxy = boxes.xyxy.cpu().numpy()
    for x1, y1, x2, y2 in xyxy:
        cx = int((x1 + x2) / 2.0)
        cy = int((y1 + y2) / 2.0)
        centroids.append((cx, cy))
        raw_boxes.append((int(x1), int(y1), int(x2), int(y2)))

    return centroids, raw_boxes



def _normalize_rect(rect, width, height):
    if rect is None:
        return None
    x1, y1, x2, y2 = rect
    x1 = max(0, min(int(x1), width - 1))
    x2 = max(0, min(int(x2), width - 1))
    y1 = max(0, min(int(y1), height - 1))
    y2 = max(0, min(int(y2), height - 1))
    if x1 > x2:
        x1, x2 = x2, x1
    if y1 > y2:
        y1, y2 = y2, y1
    return (x1, y1, x2, y2)


def _rect_intersects(a, b):
    if a is None or b is None:
        return False
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return ax1 <= bx2 and ax2 >= bx1 and ay1 <= by2 and ay2 >= by1


def _rect_intersection(a, b):
    if a is None or b is None:
        return None
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return None
    return (ix1, iy1, ix2, iy2)


def detect_faces_in_crop(frame, face_cascade, person_box=None, priority_roi=None, profile_cascade=None):
    """Detect faces ONLY within priority_roi (magenta box). Strict boundaries.
    Returns list of (x, y, w, h) in full-frame coordinates."""
    if face_cascade is None:
        return []  # Face detection disabled

    # ONLY search within priority_roi (magenta box) - strict boundary
    if priority_roi is None:
        return []  # No priority ROI defined, skip face detection

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    roi_norm = _normalize_rect(priority_roi, frame.shape[1], frame.shape[0])

    if roi_norm is None:
        return []

    # Narrow search area around the detected person's upper body when available.
    # This avoids multiple false positives in a large doorway ROI.
    search_rect = roi_norm
    if person_box is not None:
        px1, py1, px2, py2 = _normalize_rect(person_box, frame.shape[1], frame.shape[0])
        pw = max(1, px2 - px1)
        ph = max(1, py2 - py1)
        upper_body_rect = _normalize_rect(
            (
                px1 - int(0.12 * pw),
                py1,
                px2 + int(0.12 * pw),
                py1 + int(0.62 * ph),
            ),
            frame.shape[1],
            frame.shape[0],
        )
        intersected = _rect_intersection(roi_norm, upper_body_rect)
        if intersected is not None:
            search_rect = intersected

    rx1, ry1, rx2, ry2 = search_rect
    roi = gray[ry1:ry2, rx1:rx2]

    if roi.size == 0:
        return []

    # Equalise histogram to improve detection in varying light/distance
    roi = cv2.equalizeHist(roi)

    # Pass 1 — frontal face, relaxed params (catches faces at distance/angle)
    raw = face_cascade.detectMultiScale(
        roi, scaleFactor=1.06, minNeighbors=2, minSize=(20, 20)
    )

    # Pass 2 — profile cascade fallback if frontal found nothing
    # (handles side-on and angled views common in doorway cameras)
    if len(raw) == 0 and profile_cascade is not None:
        raw = profile_cascade.detectMultiScale(
            roi, scaleFactor=1.05, minNeighbors=1, minSize=(15, 15)
        )

    # Return detections fully inside the search ROI.
    results = []
    for (fx, fy, fw, fh) in raw:
        face_x1 = rx1 + fx
        face_y1 = ry1 + fy
        face_x2 = face_x1 + fw
        face_y2 = face_y1 + fh
        if face_x1 >= rx1 and face_y1 >= ry1 and face_x2 <= rx2 and face_y2 <= ry2:
            results.append((face_x1, face_y1, fw, fh))

    # Reject false positives and keep one best face per person.
    if person_box is not None and results:
        px1, py1, px2, py2 = _normalize_rect(person_box, frame.shape[1], frame.shape[0])
        pw = max(1, px2 - px1)
        ph = max(1, py2 - py1)
        head_center_x = px1 + 0.5 * pw
        head_center_y = py1 + 0.25 * ph

        valid = []
        for (fx, fy, fw, fh) in results:
            cx = fx + fw / 2.0
            cy = fy + fh / 2.0
            ar = fw / float(max(1, fh))
            rel_w = fw / float(pw)
            rel_h = fh / float(ph)
            rel_top = (fy - py1) / float(ph)

            # Human-face-like geometry + expected head region.
            if ar < 0.70 or ar > 1.55:
                continue
            if rel_w < 0.12 or rel_w > 0.62:
                continue
            if rel_h < 0.10 or rel_h > 0.60:
                continue
            if rel_top < -0.05 or rel_top > 0.60:
                continue

            dist = ((cx - head_center_x) ** 2 + (cy - head_center_y) ** 2) ** 0.5
            size_score = fw * fh
            pos_penalty = dist * 1.7
            score = size_score - pos_penalty
            valid.append((score, (fx, fy, fw, fh)))

        if valid:
            valid.sort(key=lambda item: item[0], reverse=True)
            results = [valid[0][1]]
        else:
            results = []

    return results


ROI_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roi.json")


def resolve_roi_config_path(args):
    """Return ROI config path from CLI arg or default file."""
    if getattr(args, "roi_file", None):
        return args.roi_file
    return ROI_CONFIG_PATH


def _sanitize_rtsp_for_cv2(source):
    """Encode RTSP credentials so OpenCV/FFmpeg can parse special chars like #."""
    if not (source.startswith("rtsp://") or source.startswith("rtsps://")):
        return source

    scheme, sep, rest = source.partition("://")
    if not sep:
        return source

    auth, at, tail = rest.rpartition("@")
    if not at:
        return source

    if ":" in auth:
        user, password = auth.split(":", 1)
        # Normalize first so both '#' and '%23' inputs work without double encoding.
        user = unquote(user)
        password = unquote(password)
        auth_enc = f"{quote(user, safe='')}:{quote(password, safe='')}"
    else:
        auth_enc = quote(unquote(auth), safe="")

    return f"{scheme}://{auth_enc}@{tail}"


def load_employee_lookup(employee_api_url):
    """Fetch employees from backend and build a case-insensitive name lookup."""
    try:
        response = requests.get(employee_api_url, timeout=5)
        response.raise_for_status()
        employees = response.json()
    except Exception as exc:
        print(f"Could not load employees from {employee_api_url}: {exc}")
        return {}

    lookup = {}
    for emp in employees:
        name = str(emp.get("name") or "").strip()
        if not name:
            continue
        lookup[name.lower()] = {"id": emp.get("id"), "name": name}
    return lookup


class FaceIdentifier:
    """Optional face recognition helper based on the face_recognition package.

    Known faces are loaded from subfolders under face_db_dir.
    Folder names are treated as employee names.
    """

    def __init__(self, enabled, face_db_dir, employee_api_url, threshold):
        self.enabled = bool(enabled)
        self.face_db_dir = face_db_dir
        self.threshold = float(threshold)
        self.employee_lookup = load_employee_lookup(employee_api_url) if self.enabled else {}
        self._fr = None
        self.known_names = []
        self.known_encodings = []

        if not self.enabled:
            return

        try:
            self._fr = importlib.import_module("face_recognition")
        except Exception as exc:
            print("Face recognition requested, but 'face_recognition' package is unavailable.")
            print(f"Details: {exc}")
            self.enabled = False
            return

        self._load_known_faces()
        if not self.known_encodings:
            print(f"No usable known faces found in: {self.face_db_dir}")
            self.enabled = False

    def _load_known_faces(self):
        if not os.path.isdir(self.face_db_dir):
            print(f"Known faces directory not found: {self.face_db_dir}")
            return

        for person_name in sorted(os.listdir(self.face_db_dir)):
            person_dir = os.path.join(self.face_db_dir, person_name)
            if not os.path.isdir(person_dir):
                continue

            for filename in sorted(os.listdir(person_dir)):
                if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue
                image_path = os.path.join(person_dir, filename)
                try:
                    img = self._fr.load_image_file(image_path)
                    encodings = self._fr.face_encodings(img)
                    if not encodings:
                        continue
                    self.known_names.append(person_name)
                    self.known_encodings.append(encodings[0])
                except Exception:
                    continue

        print(f"Loaded {len(self.known_encodings)} known face embeddings from {self.face_db_dir}")

    def identify(self, bgr_face_image):
        if not self.enabled or bgr_face_image is None or bgr_face_image.size == 0:
            return None

        rgb = cv2.cvtColor(bgr_face_image, cv2.COLOR_BGR2RGB)
        encodings = self._fr.face_encodings(rgb)
        if not encodings:
            return None

        face_encoding = encodings[0]
        distances = self._fr.face_distance(self.known_encodings, face_encoding)
        if len(distances) == 0:
            return None

        best_idx = int(np.argmin(distances))
        best_distance = float(distances[best_idx])
        if best_distance > self.threshold:
            return None

        name = self.known_names[best_idx]
        employee = self.employee_lookup.get(name.lower(), {})
        return {
            "name": employee.get("name", name),
            "employee_id": employee.get("id"),
            "distance": best_distance,
        }



# ---------------------------------------------------------------------------
# Interactive ROI setup  (uses cv2.VideoCapture / FFmpeg — always shows live)
# ---------------------------------------------------------------------------

def roi_setup(source, args):
    """Interactive ROI line setter.
    Opens a live window using cv2.VideoCapture (FFmpeg backend).
    Click or drag to move the red line.  S = save.  Q / ESC = quit.
    """
    # Load existing saved ROI value if present
    roi_config_path = resolve_roi_config_path(args)

    line_y = [int(args.height * args.line_fraction)]
    x1 = [int(args.width * args.line_x1_fraction)]
    x2 = [int(args.width * args.line_x2_fraction)]
    face_roi = [
        int(args.width * args.face_roi_x1_fraction),
        int(args.height * args.face_roi_y1_fraction),
        int(args.width * args.face_roi_x2_fraction),
        int(args.height * args.face_roi_y2_fraction),
    ]
    door_click_stage = [0]
    face_click_stage = [0]
    if os.path.isfile(roi_config_path):
        try:
            with open(roi_config_path) as f:
                saved = json.load(f)
            if saved.get("height") == args.height:
                line_y[0] = int(saved["line_y"])
            if saved.get("width") == args.width:
                x1[0] = int(saved.get("line_x1", x1[0]))
                x2[0] = int(saved.get("line_x2", x2[0]))
                face_roi[0] = int(saved.get("face_roi_x1", face_roi[0]))
                face_roi[1] = int(saved.get("face_roi_y1", face_roi[1]))
                face_roi[2] = int(saved.get("face_roi_x2", face_roi[2]))
                face_roi[3] = int(saved.get("face_roi_y2", face_roi[3]))
                print(
                    f"Loaded saved ROI: y={line_y[0]} "
                    f"(fraction={saved.get('line_fraction')}) from {roi_config_path}"
                )
        except Exception:
            pass

    cv2_source = _sanitize_rtsp_for_cv2(source)
    print("Connecting to camera (OpenCV RTSP)...")
    cap = cv2.VideoCapture(cv2_source, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap = cv2.VideoCapture(cv2_source)
    if not cap.isOpened():
        print("ERROR: cv2.VideoCapture could not open the source.")
        return 2

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    print("Camera opened. Waiting for first frame...")

    # Background reader thread so the display loop never blocks
    latest_frame = [None]
    reader_running = [True]
    frame_lock = threading.Lock()

    def _reader():
        while reader_running[0]:
            try:
                ret, frame = cap.read()
            except cv2.error:
                # Stream may throw while UI is closing; stop reader cleanly.
                break
            if ret and frame is not None:
                with frame_lock:
                    latest_frame[0] = frame

    reader_thread = threading.Thread(target=_reader, daemon=True)
    reader_thread.start()

    win = "ROI Setup  |  S = Save  |  Q = Quit"

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            with frame_lock:
                f = latest_frame[0]
            h_now = f.shape[0] if f is not None else args.height
            line_y[0] = max(1, min(y, h_now - 1))
        elif event == cv2.EVENT_MOUSEMOVE and (flags & cv2.EVENT_FLAG_LBUTTON):
            with frame_lock:
                f = latest_frame[0]
            h_now = f.shape[0] if f is not None else args.height
            line_y[0] = max(1, min(y, h_now - 1))

        # Right click can place 2 points for door X-range; drag still works.
        if event == cv2.EVENT_RBUTTONDOWN:
            with frame_lock:
                f = latest_frame[0]
            w_now = f.shape[1] if f is not None else args.width
            xx = max(0, min(x, w_now - 1))
            if door_click_stage[0] == 0:
                x1[0] = xx
                x2[0] = xx
                door_click_stage[0] = 1
            else:
                x2[0] = xx
                door_click_stage[0] = 0
        elif event == cv2.EVENT_MOUSEMOVE and (flags & cv2.EVENT_FLAG_RBUTTON):
            with frame_lock:
                f = latest_frame[0]
            w_now = f.shape[1] if f is not None else args.width
            xx = max(0, min(x, w_now - 1))
            x2[0] = xx

        # Middle click can place 2 corners for face ROI; drag still works.
        if event == cv2.EVENT_MBUTTONDOWN:
            with frame_lock:
                f = latest_frame[0]
            w_now = f.shape[1] if f is not None else args.width
            h_now = f.shape[0] if f is not None else args.height
            xx = max(0, min(x, w_now - 1))
            yy = max(0, min(y, h_now - 1))
            if face_click_stage[0] == 0:
                face_roi[0] = xx
                face_roi[1] = yy
                face_roi[2] = xx
                face_roi[3] = yy
                face_click_stage[0] = 1
            else:
                face_roi[2] = xx
                face_roi[3] = yy
                face_click_stage[0] = 0
        elif event == cv2.EVENT_MOUSEMOVE and (flags & cv2.EVENT_FLAG_MBUTTON):
            with frame_lock:
                f = latest_frame[0]
            w_now = f.shape[1] if f is not None else args.width
            h_now = f.shape[0] if f is not None else args.height
            face_roi[2] = max(0, min(x, w_now - 1))
            face_roi[3] = max(0, min(y, h_now - 1))

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, args.width, args.height)
    cv2.setMouseCallback(win, on_mouse)

    waited_ms = 0
    while True:
        with frame_lock:
            frame = latest_frame[0]
        if frame is not None:
            print("Camera feed live — ROI window active.")
            break
        cv2.waitKey(100)
        waited_ms += 100
        if waited_ms % 3000 == 0:
            print(f"  still waiting... ({waited_ms // 1000}s)")
        if waited_ms > 30000:
            print("Timeout: no frames received after 30 s.")
            reader_running[0] = False
            cap.release()
            cv2.destroyAllWindows()
            return 2

    try:
        while True:
            with frame_lock:
                frame = latest_frame[0]

            if frame is not None:
                display = frame.copy()
                h, w = display.shape[:2]
                fraction = line_y[0] / h
                rx1 = max(0, min(x1[0], w - 1))
                rx2 = max(0, min(x2[0], w - 1))
                if rx1 > rx2:
                    rx1, rx2 = rx2, rx1
                fx1, fy1, fx2, fy2 = _normalize_rect(face_roi, w, h)
                lbl_y = line_y[0] - 14 if line_y[0] > 40 else line_y[0] + 30
                cv2.line(display, (rx1, line_y[0]), (rx2, line_y[0]), (0, 0, 255), 3)
                cv2.line(display, (rx1, max(0, line_y[0] - 40)), (rx1, min(h - 1, line_y[0] + 40)), (0, 255, 255), 2)
                cv2.line(display, (rx2, max(0, line_y[0] - 40)), (rx2, min(h - 1, line_y[0] + 40)), (0, 255, 255), 2)
                cv2.rectangle(display, (fx1, fy1), (fx2, fy2), (255, 0, 255), 2)
                line_dot_x = int((rx1 + rx2) / 2)
                cv2.circle(display, (line_dot_x, line_y[0]), 6, (0, 0, 255), -1)
                cv2.circle(display, (rx1, line_y[0]), 5, (0, 255, 255), -1)
                cv2.circle(display, (rx2, line_y[0]), 5, (0, 255, 255), -1)
                cv2.circle(display, (fx1, fy1), 5, (255, 0, 255), -1)
                cv2.circle(display, (fx2, fy2), 5, (255, 0, 255), -1)
                cv2.putText(display,
                            f"y={line_y[0]} ({fraction:.3f})  x1={rx1} x2={rx2}",
                            (10, lbl_y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                cv2.putText(display,
                            f"face-roi=({fx1},{fy1})-({fx2},{fy2})",
                            (10, min(h - 42, lbl_y + 36)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
                cv2.rectangle(display, (0, h - 34), (w, h), (0, 0, 0), -1)
                cv2.putText(display, "Left click=line   Right 2 clicks=door range   Middle 2 clicks=face ROI   S=Save   Q=Quit",
                            (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
                cv2.imshow(win, display)

            key = cv2.waitKey(30) & 0xFF
            if key in (ord('q'), ord('Q'), 27):
                print("Quit without saving.")
                break
            elif key in (ord('s'), ord('S')):
                with frame_lock:
                    snap = latest_frame[0]
                h_actual = snap.shape[0] if snap is not None else args.height
                w_actual = snap.shape[1] if snap is not None else args.width
                fraction = line_y[0] / h_actual
                sx1 = max(0, min(x1[0], w_actual - 1))
                sx2 = max(0, min(x2[0], w_actual - 1))
                if sx1 > sx2:
                    sx1, sx2 = sx2, sx1
                fx1, fy1, fx2, fy2 = _normalize_rect(face_roi, w_actual, h_actual)
                data = {
                    "line_fraction": round(fraction, 4),
                    "line_y": line_y[0],
                    "height": h_actual,
                    "line_x1_fraction": round(sx1 / w_actual, 4),
                    "line_x2_fraction": round(sx2 / w_actual, 4),
                    "line_x1": sx1,
                    "line_x2": sx2,
                    "face_roi_x1_fraction": round(fx1 / w_actual, 4),
                    "face_roi_y1_fraction": round(fy1 / h_actual, 4),
                    "face_roi_x2_fraction": round(fx2 / w_actual, 4),
                    "face_roi_y2_fraction": round(fy2 / h_actual, 4),
                    "face_roi_x1": fx1,
                    "face_roi_y1": fy1,
                    "face_roi_x2": fx2,
                    "face_roi_y2": fy2,
                    "width": w_actual,
                }
                with open(roi_config_path, "w") as f:
                    json.dump(data, f, indent=2)
                print(f"ROI saved  -->  --line-fraction {fraction:.4f}  (y={line_y[0]})")
                print(f"Door segment saved  -->  x1={sx1}, x2={sx2}")
                print(f"Face ROI saved  -->  x1={fx1}, y1={fy1}, x2={fx2}, y2={fy2}")
                print(f"Config: {roi_config_path}")
                if snap is not None:
                    lbl_y2 = line_y[0] - 14 if line_y[0] > 40 else line_y[0] + 30
                    prev = snap.copy()
                    cv2.line(prev, (sx1, line_y[0]), (sx2, line_y[0]), (0, 0, 255), 3)
                    cv2.line(prev, (sx1, max(0, line_y[0] - 40)), (sx1, min(prev.shape[0] - 1, line_y[0] + 40)), (0, 255, 255), 2)
                    cv2.line(prev, (sx2, max(0, line_y[0] - 40)), (sx2, min(prev.shape[0] - 1, line_y[0] + 40)), (0, 255, 255), 2)
                    cv2.rectangle(prev, (fx1, fy1), (fx2, fy2), (255, 0, 255), 2)
                    cv2.putText(prev,
                                f"ROI y={line_y[0]}  x1={sx1} x2={sx2}",
                                (10, lbl_y2), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
                    preview_path = roi_config_path.replace(".json", "_preview.jpg")
                    cv2.imwrite(preview_path, prev)
                    print(f"Preview image saved: {preview_path}")
                print(
                    f"\nRun detector with: --line-fraction {fraction:.4f} "
                    f"--line-x1-fraction {sx1 / w_actual:.4f} --line-x2-fraction {sx2 / w_actual:.4f} "
                    f"--face-roi-x1-fraction {fx1 / w_actual:.4f} --face-roi-y1-fraction {fy1 / h_actual:.4f} "
                    f"--face-roi-x2-fraction {fx2 / w_actual:.4f} --face-roi-y2-fraction {fy2 / h_actual:.4f}"
                )
                break
    except KeyboardInterrupt:
        print("Interrupted")
    finally:
        reader_running[0] = False
        cap.release()
        cv2.destroyAllWindows()

    return 0


# ---------------------------------------------------------------------------
# Detection / counting loop
# ---------------------------------------------------------------------------

def post_event(backend_url, direction, employee_id=None, detected_name=None, face_image=None):
    payload = {
        "employee_id": employee_id,
        "detected_name": detected_name,
        "face_image": face_image,
        "type": direction,
    }
    try:
        response = requests.post(backend_url, json=payload, timeout=5)
        print(f"Posted event: {direction} -> {response.status_code}")
    except Exception as exc:
        print(f"Failed to post event: {exc}")


def monitor(source, args):
    is_rtsp = source.startswith("rtsp://") or source.startswith("rtsps://")
    line_y = int(args.height * args.line_fraction)
    line_x1 = int(args.width * args.line_x1_fraction)
    line_x2 = int(args.width * args.line_x2_fraction)
    line_x_margin = max(0, int(getattr(args, "line_x_margin", 40)))
    crossing_ref = getattr(args, "crossing_ref", "centroid")
    face_roi = _normalize_rect(
        (
            int(args.width * args.face_roi_x1_fraction),
            int(args.height * args.face_roi_y1_fraction),
            int(args.width * args.face_roi_x2_fraction),
            int(args.height * args.face_roi_y2_fraction),
        ),
        args.width,
        args.height,
    )
    event_mode = getattr(args, "event_mode", "both")
    if line_x1 > line_x2:
        line_x1, line_x2 = line_x2, line_x1

    display_enabled = bool(getattr(args, "display", False))
    display_window = "Live Detection  |  Q / ESC to quit"
    save_faces_only = bool(getattr(args, "save_faces_only", False))
    crossing_only = bool(getattr(args, "crossing_only", False))
    allow_person_fallback = bool(getattr(args, "allow_person_fallback", False))
    gstreamer_only = bool(getattr(args, "gstreamer_only", False))
    face_identifier = FaceIdentifier(
        getattr(args, "face_recognition", False),
        getattr(args, "face_db_dir", os.path.join(os.path.dirname(os.path.abspath(__file__)), "known_faces")),
        getattr(args, "employee_api", "http://localhost:3001/api/employees"),
        getattr(args, "face_match_threshold", 0.45),
    )

    print(f"Opening {'RTSP' if is_rtsp else 'video'} source: {source}")
    print(f"Stream size target: {args.width} x {args.height}")
    print(f"ROI line at y={line_y}, x-range=[{line_x1}, {line_x2}], margin={line_x_margin}px")
    print(f"Crossing reference point: {crossing_ref}")
    print(f"Event mode: {event_mode.upper()}")
    print(f"Face ROI: x1={face_roi[0]}, y1={face_roi[1]}, x2={face_roi[2]}, y2={face_roi[3]}")
    if display_enabled:
        print("Live display enabled. Press Q or ESC in the video window to stop.")
    if save_faces_only:
        print("Face-only save mode enabled: only face crops will be saved on crossing events.")
    if not allow_person_fallback:
        print("Person fallback disabled: only ROI-face detections will be saved.")
    if crossing_only:
        print("Crossing-only mode enabled: periodic detection snapshots are disabled.")
    if gstreamer_only:
        print("GStreamer-only mode enabled: OpenCV fallback is disabled.")
    if face_identifier.enabled:
        print(f"Face recognition enabled (threshold={face_identifier.threshold:.2f}).")

    # ---- optional detection snapshots (not only crossings) ----
    detections_dir = getattr(args, "save_detections", None)
    if crossing_only:
        detections_dir = None
    detection_cooldown = float(getattr(args, "detection_cooldown", 2.0) or 2.0)
    last_detection_save_ts = 0.0
    if detections_dir:
        os.makedirs(detections_dir, exist_ok=True)
        print(f"Saving detection snapshots to: {detections_dir} (cooldown={detection_cooldown}s)")

    # ---- log file setup ----
    log_file_path = getattr(args, "log_file", None)
    if not log_file_path:
        cam_tag = ""
        roi_f = getattr(args, "roi_file", None)
        if roi_f:
            cam_tag = "_" + os.path.splitext(os.path.basename(roi_f))[0]
        date_str = datetime.now().strftime("%Y%m%d")
        log_file_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            f"events{cam_tag}_{date_str}.csv"
        )
    log_is_new = not os.path.isfile(log_file_path)
    log_fh = open(log_file_path, "a", newline="", encoding="utf-8")
    log_writer = csv.writer(log_fh)
    if log_is_new:
        log_writer.writerow(["timestamp", "direction", "object_id", "frame", "face_saved", "employee_id", "employee_name", "match_distance"])
    print(f"Logging events to: {log_file_path}")

    # ---- crops dir setup ----
    crops_dir = getattr(args, "save_crops", None)
    faces_dir = None
    if crops_dir:
        os.makedirs(crops_dir, exist_ok=True)
        faces_dir = os.path.join(crops_dir, "faces")
        os.makedirs(faces_dir, exist_ok=True)
        print(f"Saving crossing images to: {crops_dir}")
        print(f"Saving face crops to: {faces_dir}")

    # ---- face detector (OpenCV Haar cascade, built-in — no extra files needed) ----
    # Fallback: try multiple paths since cv2.data may not be available in all builds
    cascade_file = None
    cascade_paths = [
        'haarcascade_frontalface_default.xml',
        '/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml',
        '/usr/local/share/opencv4/haarcascades/haarcascade_frontalface_default.xml',
    ]
    try:
        if hasattr(cv2, 'data') and hasattr(cv2.data, 'haarcascades'):
            cascade_paths.insert(0, cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    except:
        pass
    
    for path in cascade_paths:
        if os.path.exists(path):
            cascade_file = path
            break
    
    if cascade_file:
        face_cascade = cv2.CascadeClassifier(cascade_file)
    else:
        print("Warning: Haar cascade file not found. Face detection will be disabled.")
        face_cascade = None

    # Profile / side-face cascade as fallback
    profile_cascade = None
    try:
        profile_paths = []
        if hasattr(cv2, 'data') and hasattr(cv2.data, 'haarcascades'):
            profile_paths.append(cv2.data.haarcascades + 'haarcascade_profileface.xml')
        profile_paths += [
            '/usr/share/opencv4/haarcascades/haarcascade_profileface.xml',
            '/usr/local/share/opencv4/haarcascades/haarcascade_profileface.xml',
        ]
        for p in profile_paths:
            if os.path.exists(p):
                profile_cascade = cv2.CascadeClassifier(p)
                break
    except Exception:
        pass

    # ---- counters ----
    count_in = 0
    count_out = 0

    ultralytics = importlib.import_module("ultralytics")
    torch = importlib.import_module("torch")

    requested_device = str(getattr(args, "device", "auto")).strip().lower()
    if requested_device == "auto":
        infer_device = "cuda:0" if torch.cuda.is_available() else "cpu"
    else:
        infer_device = requested_device
        if requested_device.startswith("cuda") and not torch.cuda.is_available():
            print("CUDA requested but unavailable in current PyTorch build; falling back to CPU.")
            infer_device = "cpu"

    print(f"YOLO inference device: {infer_device}")
    model = ultralytics.YOLO(args.model)
    tracker = SimpleTracker(max_lost=30, max_distance=args.match_distance)

    save_preview = getattr(args, "save_preview", None)
    stream = None
    if Gst is not None:
        stream = GStreamerFrameSource(source, args.width, args.height, is_rtsp, Gst)
    else:
        gst_launch_bin = resolve_gst_launch_bin()
        if not gst_launch_bin:
            print("GStreamer CLI binary not found: gst-launch-1.0")
            print("Install GStreamer 1.x and ensure gst-launch-1.0.exe is on PATH,")
            print("or set GST_LAUNCH_BIN to the full executable path.")
            log_fh.close()
            return 2
        print(f"Using GStreamer CLI: {gst_launch_bin}")
        stream = GStreamerCliFrameSource(source, args.width, args.height, is_rtsp, gst_launch_bin)

    frame_count = 0
    centroids = []
    switched_to_opencv = False
    no_frame_switch_threshold = 20

    def _switch_to_opencv(current_stream):
        nonlocal switched_to_opencv
        if gstreamer_only:
            print("No frames from GStreamer and --gstreamer-only is set. Exiting to allow service restart.")
            raise RuntimeError("GStreamer frame timeout in gstreamer-only mode")
        if switched_to_opencv:
            return current_stream
        print("No frames from GStreamer. Switching to OpenCV RTSP capture fallback...")
        try:
            current_stream.close()
        except Exception:
            pass
        cv_stream = OpenCVFrameSource(source, args.width, args.height, is_rtsp)
        cv_stream.open()
        switched_to_opencv = True
        print("OpenCV fallback active.")
        return cv_stream

    try:
        stream.open()

        if save_preview:
            print("Capturing preview frame...")
            ok, frame = False, None
            for _ in range(30):
                ok, frame = stream.read()
                if ok and frame is not None:
                    break
            if (not ok or frame is None) and is_rtsp and not switched_to_opencv:
                stream = _switch_to_opencv(stream)
                for _ in range(60):
                    ok, frame = stream.read()
                    if ok and frame is not None:
                        break
            if ok and frame is not None:
                cv2.line(frame, (0, line_y), (frame.shape[1], line_y), (0, 0, 255), 3)
                cv2.putText(frame, f"ROI y={line_y}  (--line-fraction {args.line_fraction:.2f})",
                            (10, line_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                cv2.imwrite(save_preview, frame)
                print(f"Preview saved to: {save_preview}")
            else:
                print("Could not capture a frame for preview.")
            log_fh.close()
            return 0

        no_frame_streak = 0
        recent_crossings = []
        crossing_dedupe_seconds = 2.5
        crossing_dedupe_pixels = 90
        while True:
            ok, frame = stream.read()
            if not ok:
                no_frame_streak += 1
                if is_rtsp and no_frame_streak > no_frame_switch_threshold and not switched_to_opencv:
                    stream = _switch_to_opencv(stream)
                    no_frame_streak = 0
                if not is_rtsp:
                    print("End of video stream")
                    break
                continue

            no_frame_streak = 0

            centroids, raw_boxes = detect_person_centroids(model, frame, args.conf, infer_device)
            centroid_box_map = {c: b for c, b in zip(centroids, raw_boxes)}

            # Optional capture on any person detection (independent of line crossing).
            if detections_dir and raw_boxes and not save_faces_only:
                now_ts = time.time()
                if now_ts - last_detection_save_ts >= detection_cooldown:
                    det_img = frame.copy()
                    for bx1, by1, bx2, by2 in raw_boxes:
                        cv2.rectangle(det_img, (bx1, by1), (bx2, by2), (0, 255, 255), 2)
                    cv2.line(det_img, (line_x1, line_y), (line_x2, line_y), (0, 0, 255), 2)
                    name = f"det_{int(now_ts * 1000)}_n{len(raw_boxes)}.jpg"
                    cv2.imwrite(os.path.join(detections_dir, name), det_img)
                    last_detection_save_ts = now_ts

            tracker.update(centroids, line_y)

            for oid, centroid in tracker.get_objects().items():
                # Find closest person box to this tracked object.
                best_box = None
                if frame is not None:
                    best_d = None
                    for c, b in centroid_box_map.items():
                        d = euclid(c, centroid)
                        if best_d is None or d < best_d:
                            best_d = d
                            best_box = b

                # Crossing side can be measured by centroid or bbox foot point.
                # Centroid is safer default because foot point can stay below the
                # line for the entire trajectory in some camera angles.
                ref_x, ref_y = centroid[0], centroid[1]
                if crossing_ref == "foot" and best_box is not None:
                    bx1, by1, bx2, by2 = best_box
                    ref_x = int((bx1 + bx2) / 2)
                    ref_y = int(by2)

                in_x_zone = (line_x1 - line_x_margin) <= ref_x <= (line_x2 + line_x_margin)
                if not in_x_zone:
                    continue

                prev = tracker.prev_side.get(oid)
                curr_side = 0 if ref_y < line_y else 1
                if prev is not None and curr_side != prev:
                    direction = "in" if prev == 0 and curr_side == 1 else "out"

                    # Suppress duplicate events caused by tracker fragmentation or
                    # nearly identical re-detections of the same person.
                    now_ts = time.time()
                    recent_crossings = [
                        item for item in recent_crossings
                        if now_ts - item["ts"] <= crossing_dedupe_seconds
                    ]
                    is_duplicate_crossing = any(
                        item["direction"] == direction and
                        abs(item["x"] - ref_x) <= crossing_dedupe_pixels and
                        abs(item["y"] - ref_y) <= crossing_dedupe_pixels
                        for item in recent_crossings
                    )
                    if is_duplicate_crossing:
                        print(
                            f"Suppressed duplicate {direction.upper()} event for object {oid} "
                            f"near ({ref_x}, {ref_y})"
                        )
                        tracker.prev_side[oid] = curr_side
                        continue

                    if event_mode != "both" and direction != event_mode:
                        print(
                            f"Crossing detected for object {oid} as {direction.upper()}, "
                            f"but ignored because event mode is {event_mode.upper()}"
                        )
                        tracker.prev_side[oid] = curr_side
                        continue
                    if direction == "in":
                        count_in += 1
                    else:
                        count_out += 1
                    recent_crossings.append({"ts": now_ts, "direction": direction, "x": ref_x, "y": ref_y})
                    ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ts_ms = int(time.time() * 1000)
                    print(f"[{ts_str}] Person {direction.upper()}  (object {oid})  |  total IN={count_in} OUT={count_out}")

                    # Face detection + face crop save
                    face_rects = []
                    face_saved = ""
                    recognized = None
                    if frame is not None and (faces_dir is not None or face_identifier.enabled):
                        priority_roi = face_roi if best_box is None or _rect_intersects(best_box, face_roi) else None
                        face_rects = detect_faces_in_crop(frame, face_cascade, best_box, priority_roi=priority_roi, profile_cascade=profile_cascade)
                        if face_rects:
                            # Pick the largest detected face
                            fx, fy, fw, fh = max(face_rects, key=lambda r: r[2] * r[3])
                            pad = int(fw * 0.30)
                            fx1 = max(0, fx - pad)
                            fy1 = max(0, fy - pad)
                            fx2 = min(frame.shape[1], fx + fw + pad)
                            fy2 = min(frame.shape[0], fy + fh + pad)
                            face_crop = frame[fy1:fy2, fx1:fx2]
                            if face_identifier.enabled:
                                recognized = face_identifier.identify(face_crop)
                            if faces_dir is not None:
                                face_name = f"face_{direction}_{ts_ms}_{oid}.jpg"
                                cv2.imwrite(os.path.join(faces_dir, face_name), face_crop)
                                face_saved = face_name
                                print(f"  Face captured: {face_name}")
                        else:
                            # By default, do not save person-box fallback to avoid out-of-ROI captures.
                            if allow_person_fallback and best_box is not None:
                                bx1, by1, bx2, by2 = best_box
                                pad_x = max(10, int((bx2 - bx1) * 0.10))
                                cx1 = max(0, bx1 - pad_x)
                                cx2 = min(frame.shape[1], bx2 + pad_x)
                                cy1 = max(0, by1)
                                cy2 = min(frame.shape[0], by2)
                                person_crop = frame[cy1:cy2, cx1:cx2]
                                if person_crop.size > 0:
                                    if face_identifier.enabled:
                                        recognized = face_identifier.identify(person_crop)
                                    if faces_dir is not None:
                                        face_name = f"person_{direction}_{ts_ms}_{oid}.jpg"
                                        cv2.imwrite(os.path.join(faces_dir, face_name), person_crop)
                                        face_saved = face_name
                                        print(f"  Person crop saved (no face detected): {face_name}")
                            else:
                                print("  No face detected in face ROI; skipping fallback person crop.")

                    employee_id = recognized.get("employee_id") if recognized else None
                    employee_name = recognized.get("name") if recognized else ""
                    match_distance = recognized.get("distance") if recognized else ""
                    if recognized:
                        print(
                            f"  Recognized: {employee_name}"
                            f" (employee_id={employee_id}, distance={match_distance:.3f})"
                        )

                    # Log to CSV (includes face filename if captured)
                    log_writer.writerow([
                        ts_str,
                        direction,
                        oid,
                        frame_count,
                        face_saved,
                        employee_id,
                        employee_name,
                        match_distance,
                    ])
                    log_fh.flush()

                    # Save full-frame crossing snapshot with annotations (always, even in save_faces_only mode)
                    captured_image_name = face_saved or ""
                    if crops_dir and frame is not None:
                        snap = frame.copy()
                        color = (0, 255, 0) if direction == "in" else (0, 0, 255)
                        cv2.line(snap, (line_x1, line_y), (line_x2, line_y), (0, 0, 255), 2)
                        if best_box is not None:
                            bx1, by1, bx2, by2 = best_box
                            cv2.rectangle(snap, (bx1, by1), (bx2, by2), color, 3)
                            cv2.putText(snap, f"{direction.upper()} {ts_str}",
                                        (bx1, max(by1 - 10, 20)),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                        else:
                            cx, cy = centroid
                            cv2.circle(snap, (cx, cy), 20, color, 3)
                        # Draw face boxes on the full frame snapshot (cyan)
                        for (fx, fy, fw, fh) in face_rects:
                            cv2.rectangle(snap, (fx, fy), (fx + fw, fy + fh), (255, 255, 0), 2)
                            cv2.putText(snap, "face", (fx, max(fy - 5, 12)),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                        img_name = f"{direction}_{ts_ms}_{oid}.jpg"
                        cv2.imwrite(os.path.join(crops_dir, img_name), snap)
                        if not captured_image_name:
                            captured_image_name = img_name

                    if args.post:
                        post_event(
                            args.backend,
                            direction,
                            employee_id=employee_id,
                            detected_name=employee_name or None,
                            face_image=captured_image_name or None,
                        )
                tracker.prev_side[oid] = curr_side

            if display_enabled and frame is not None:
                vis = frame.copy()
                h_vis, w_vis = vis.shape[:2]
                y_line = max(0, min(line_y, h_vis - 1))
                x1_vis = max(0, min(line_x1, w_vis - 1))
                x2_vis = max(0, min(line_x2, w_vis - 1))
                if x1_vis > x2_vis:
                    x1_vis, x2_vis = x2_vis, x1_vis

                # ROI line and segment limits
                cv2.line(vis, (x1_vis, y_line), (x2_vis, y_line), (0, 0, 255), 3)
                cv2.line(vis, (x1_vis, max(0, y_line - 35)), (x1_vis, min(h_vis - 1, y_line + 35)), (0, 255, 255), 2)
                cv2.line(vis, (x2_vis, max(0, y_line - 35)), (x2_vis, min(h_vis - 1, y_line + 35)), (0, 255, 255), 2)
                fx1_vis, fy1_vis, fx2_vis, fy2_vis = _normalize_rect(face_roi, w_vis, h_vis)
                cv2.rectangle(vis, (fx1_vis, fy1_vis), (fx2_vis, fy2_vis), (255, 0, 255), 2)
                cv2.putText(vis, f"Mode: {event_mode.upper()}",
                            (w_vis - 180, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

                # Person detection boxes (yellow)
                for bx1, by1, bx2, by2 in raw_boxes:
                    cv2.rectangle(vis, (bx1, by1), (bx2, by2), (0, 255, 255), 2)

                # Tracker IDs and centroids
                for oid, c in tracker.get_objects().items():
                    cx, cy = c
                    in_zone = (x1_vis - line_x_margin) <= cx <= (x2_vis + line_x_margin)
                    color = (0, 255, 0) if in_zone else (140, 140, 140)
                    cv2.circle(vis, (cx, cy), 5, color, -1)
                    cv2.putText(vis, f"ID {oid}", (cx + 8, max(18, cy - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                # Status text
                cv2.rectangle(vis, (0, 0), (w_vis, 64), (0, 0, 0), -1)
                cv2.putText(vis, f"Detections: {len(raw_boxes)}  Tracked: {len(tracker.get_objects())}",
                            (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
                cv2.putText(vis, f"IN: {count_in}  OUT: {count_out}",
                            (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)

                cv2.imshow(display_window, vis)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord('q'), ord('Q'), 27):
                    print("Display window closed by user.")
                    break

            frame_count += 1
            if frame_count % 60 == 0:
                print(
                    f"  frames={frame_count} | detections={len(centroids)} "
                    f"tracked={len(tracker.get_objects())} | IN={count_in} OUT={count_out}"
                )

    except KeyboardInterrupt:
        print(f"\nInterrupted. Final counts: IN={count_in}  OUT={count_out}")
    finally:
        stream.close()
        if display_enabled:
            cv2.destroyAllWindows()
        log_fh.close()
        print(f"Log saved: {log_file_path}")

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    global Gst

    try:
        gi = importlib.import_module("gi")
        gi.require_version("Gst", "1.0")
        Gst = importlib.import_module("gi.repository.Gst")
        Gst.init(None)
    except Exception as exc:
        print("PyGObject not available, falling back to gst-launch-1.0 CLI mode.")
        print(f"Details: {exc}")
        Gst = None

    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="Full RTSP URL")
    parser.add_argument("--video", help="Local video file")
    parser.add_argument("--line-fraction", type=float, default=0.5, help="ROI line fraction (0..1)")
    parser.add_argument("--line-x1-fraction", type=float, default=0.0,
                        help="ROI line start X as frame fraction (0..1)")
    parser.add_argument("--line-x2-fraction", type=float, default=1.0,
                        help="ROI line end X as frame fraction (0..1)")
    parser.add_argument("--line-x-margin", type=int, default=40,
                        help="Extra pixel tolerance on both sides of ROI X-range for crossing detection")
    parser.add_argument("--event-mode", choices=["both", "in", "out"], default="both",
                        help="Record both directions or only one direction for this camera")
    parser.add_argument("--crossing-ref", choices=["centroid", "foot"], default="centroid",
                        help="Reference point used for crossing side calculation")
    parser.add_argument("--match-distance", type=int, default=60, help="Max centroid match distance")
    parser.add_argument("--width", type=int, default=1280, help="Frame width requested from pipeline")
    parser.add_argument("--height", type=int, default=720, help="Frame height requested from pipeline")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO model path/name")
    parser.add_argument("--conf", type=float, default=0.35, help="YOLO confidence threshold")
    parser.add_argument("--post", action="store_true", help="POST in/out events to backend")
    parser.add_argument("--backend", default="http://localhost:3001/api/entries", help="Backend entries endpoint")
    parser.add_argument("--display", action="store_true",
                        help="Show live camera feed with ROI line, detections, tracker IDs, and counters")
    parser.add_argument("--save-preview", metavar="PATH", default=None,
                        help="Capture one frame with ROI line drawn, save to image file, then exit")
    parser.add_argument("--roi-setup", action="store_true",
                        help="Open interactive window to set ROI line; click to move, S=save, Q=quit")
    parser.add_argument("--roi-file", default=None,
                        help="Path to ROI JSON file (use different files for different cameras)")
    parser.add_argument("--face-roi-x1-fraction", type=float, default=0.0,
                        help="Door face ROI start X as frame fraction (0..1)")
    parser.add_argument("--face-roi-y1-fraction", type=float, default=0.0,
                        help="Door face ROI start Y as frame fraction (0..1)")
    parser.add_argument("--face-roi-x2-fraction", type=float, default=1.0,
                        help="Door face ROI end X as frame fraction (0..1)")
    parser.add_argument("--face-roi-y2-fraction", type=float, default=1.0,
                        help="Door face ROI end Y as frame fraction (0..1)")
    parser.add_argument("--log-file", default=None, metavar="PATH",
                        help="CSV file to append crossing events (default: auto-named events_<cam>_YYYYMMDD.csv)")
    parser.add_argument("--save-crops", default=None, metavar="DIR",
                        help="Directory to save a snapshot image each time someone crosses the line")
    parser.add_argument("--save-faces-only", action="store_true",
                        help="Save only face crops on crossing events (skip full-frame and periodic detection images)")
    parser.add_argument("--allow-person-fallback", action="store_true",
                        help="When no face is found, save person bbox crop as fallback (may be outside face ROI)")
    parser.add_argument("--crossing-only", action="store_true",
                        help="Disable periodic detection snapshots and save images only when crossing event occurs")
    parser.add_argument("--gstreamer-only", action="store_true",
                        help="Disable OpenCV fallback and require GStreamer frame source")
    parser.add_argument("--save-detections", default=None, metavar="DIR",
                        help="Directory to save periodic snapshots whenever any person is detected")
    parser.add_argument("--detection-cooldown", type=float, default=2.0,
                        help="Seconds between periodic detection snapshots (used with --save-detections)")
    parser.add_argument("--face-recognition", action="store_true",
                        help="Enable face recognition for named employee identification on crossing events")
    parser.add_argument("--face-db-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "known_faces"),
                        help="Directory of known faces organized as <dir>/<Employee Name>/*.jpg")
    parser.add_argument("--employee-api", default="http://localhost:3001/api/employees",
                        help="Backend employees endpoint used to map recognized names to employee IDs")
    parser.add_argument("--face-match-threshold", type=float, default=0.45,
                        help="Lower is stricter for face matching (typical range 0.35-0.60)")
    parser.add_argument("--device", default="auto",
                        help="YOLO inference device: auto, cpu, cuda, cuda:0")
    parser.add_argument("--min-area", type=int, default=500, help="Deprecated; kept for CLI compatibility")
    args = parser.parse_args()

    import sys
    roi_config_path = resolve_roi_config_path(args)
    explicit_line_fraction = "--line-fraction" in sys.argv
    explicit_x1_fraction = "--line-x1-fraction" in sys.argv
    explicit_x2_fraction = "--line-x2-fraction" in sys.argv
    explicit_face_x1_fraction = "--face-roi-x1-fraction" in sys.argv
    explicit_face_y1_fraction = "--face-roi-y1-fraction" in sys.argv
    explicit_face_x2_fraction = "--face-roi-x2-fraction" in sys.argv
    explicit_face_y2_fraction = "--face-roi-y2-fraction" in sys.argv
    if os.path.isfile(roi_config_path):
        try:
            with open(roi_config_path) as f:
                saved = json.load(f)

            saved_h = saved.get("height", args.height)
            saved_w = saved.get("width", args.width)

            if not explicit_line_fraction:
                if "line_fraction" in saved:
                    args.line_fraction = float(saved["line_fraction"])
                elif "line_y" in saved and saved_h:
                    args.line_fraction = float(saved["line_y"]) / float(saved_h)
                print(f"Loaded saved ROI: --line-fraction {args.line_fraction:.4f} (from {roi_config_path})")

            if not explicit_x1_fraction:
                if "line_x1_fraction" in saved:
                    args.line_x1_fraction = float(saved["line_x1_fraction"])
                elif "line_x1" in saved and saved_w:
                    args.line_x1_fraction = float(saved["line_x1"]) / float(saved_w)
            if not explicit_x2_fraction:
                if "line_x2_fraction" in saved:
                    args.line_x2_fraction = float(saved["line_x2_fraction"])
                elif "line_x2" in saved and saved_w:
                    args.line_x2_fraction = float(saved["line_x2"]) / float(saved_w)

            if not explicit_face_x1_fraction:
                if "face_roi_x1_fraction" in saved:
                    args.face_roi_x1_fraction = float(saved["face_roi_x1_fraction"])
                elif "face_roi_x1" in saved and saved_w:
                    args.face_roi_x1_fraction = float(saved["face_roi_x1"]) / float(saved_w)
            if not explicit_face_y1_fraction:
                if "face_roi_y1_fraction" in saved:
                    args.face_roi_y1_fraction = float(saved["face_roi_y1_fraction"])
                elif "face_roi_y1" in saved and saved_h:
                    args.face_roi_y1_fraction = float(saved["face_roi_y1"]) / float(saved_h)
            if not explicit_face_x2_fraction:
                if "face_roi_x2_fraction" in saved:
                    args.face_roi_x2_fraction = float(saved["face_roi_x2_fraction"])
                elif "face_roi_x2" in saved and saved_w:
                    args.face_roi_x2_fraction = float(saved["face_roi_x2"]) / float(saved_w)
            if not explicit_face_y2_fraction:
                if "face_roi_y2_fraction" in saved:
                    args.face_roi_y2_fraction = float(saved["face_roi_y2_fraction"])
                elif "face_roi_y2" in saved and saved_h:
                    args.face_roi_y2_fraction = float(saved["face_roi_y2"]) / float(saved_h)

            print(
                f"Loaded saved ROI X-range: "
                f"[{args.line_x1_fraction:.4f}, {args.line_x2_fraction:.4f}] "
                f"(from {roi_config_path})"
            )
            print(
                f"Loaded saved face ROI: "
                f"[{args.face_roi_x1_fraction:.4f}, {args.face_roi_y1_fraction:.4f}] -> "
                f"[{args.face_roi_x2_fraction:.4f}, {args.face_roi_y2_fraction:.4f}] "
                f"(from {roi_config_path})"
            )

            if saved_h != args.height or saved_w != args.width:
                print(
                    "ROI file resolution differs from runtime stream. "
                    "Using normalized fractions (scaled automatically)."
                )
        except Exception:
            pass

    source = args.video or args.url or os.environ.get("RTSP_URL")
    if not source:
        print("No video source provided. Use --video, --url, or set RTSP_URL env var")
        parser.print_help()
        return 2

    if args.roi_setup:
        return roi_setup(source, args)

    return monitor(source, args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        raise SystemExit(130)
