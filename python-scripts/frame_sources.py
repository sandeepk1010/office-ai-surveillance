"""Frame source backends for line_counter.

Contains GStreamer (PyGObject), gst-launch CLI, and OpenCV fallback readers.
"""

import os
import shutil
import subprocess
from urllib.parse import quote, unquote

import cv2
import numpy as np


def resolve_gst_launch_bin():
    """Resolve gst-launch binary from env, PATH, or common Windows install paths."""
    env_bin = os.environ.get("GST_LAUNCH_BIN")
    if env_bin and os.path.isfile(env_bin):
        return env_bin

    on_path = shutil.which("gst-launch-1.0")
    if on_path:
        return on_path

    candidates = [
        r"C:\gstreamer\1.0\msvc_x86_64\bin\gst-launch-1.0.exe",
        r"C:\gstreamer\1.0\mingw_x86_64\bin\gst-launch-1.0.exe",
        r"C:\Program Files\gstreamer\1.0\msvc_x86_64\bin\gst-launch-1.0.exe",
        r"C:\Program Files\gstreamer\1.0\mingw_x86_64\bin\gst-launch-1.0.exe",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    return None


def _sanitize_rtsp_for_cv2(source):
    if not source:
        return source

    try:
        scheme, rest = source.split("://", 1)
    except ValueError:
        return source

    if "@" not in rest:
        return source

    auth, tail = rest.split("@", 1)
    if ":" not in auth:
        return source

    user, pwd = auth.split(":", 1)
    return f"{scheme}://{user}:{quote(unquote(pwd), safe='')}@{tail}"


class GStreamerFrameSource:
    def __init__(self, source, width, height, is_rtsp, gst_module):
        if gst_module is None:
            raise RuntimeError("GStreamer module is required for GStreamerFrameSource")
        self.source = source
        self.width = width
        self.height = height
        self.is_rtsp = is_rtsp
        self.gst = gst_module
        self.pipeline = None
        self.sink = None

    def _build_pipeline(self, use_hw_decoder=True):
        if self.is_rtsp:
            if use_hw_decoder:
                # Jetson hardware HEVC decoder (nvv4l2decoder + nvvidconv)
                return (
                    f'rtspsrc location="{self.source}" protocols=tcp latency=50 '
                    '! rtph265depay ! h265parse '
                    '! nvv4l2decoder ! nvvidconv '
                    f'! video/x-raw,format=BGRx,width={self.width},height={self.height} '
                    '! videoconvert ! video/x-raw,format=BGR '
                    '! appsink name=sink emit-signals=false sync=false max-buffers=1 drop=true'
                )
            # Software HEVC decoder fallback (avdec_h265)
            return (
                f'rtspsrc location="{self.source}" protocols=tcp latency=50 '
                '! rtph265depay ! h265parse ! avdec_h265 ! videoconvert ! videoscale '
                f'! video/x-raw,format=BGR,width={self.width},height={self.height} '
                '! appsink name=sink emit-signals=false sync=false max-buffers=1 drop=true'
            )

        escaped_path = self.source.replace("\\", "\\\\")
        return (
            f'filesrc location="{escaped_path}" ! decodebin ! videoconvert '
            f"! video/x-raw,format=BGR,width={self.width},height={self.height} "
            "! appsink name=sink emit-signals=false sync=false max-buffers=1 drop=true"
        )

    def open(self):
        for use_hw in (True, False):
            pipeline_str = self._build_pipeline(use_hw_decoder=use_hw)
            self.pipeline = self.gst.parse_launch(pipeline_str)
            self.sink = self.pipeline.get_by_name("sink")
            if self.sink is None:
                self.pipeline.set_state(self.gst.State.NULL)
                continue
            self.pipeline.set_state(self.gst.State.PLAYING)
            ret, _state, _pending = self.pipeline.get_state(3 * self.gst.SECOND)
            if ret in (self.gst.StateChangeReturn.SUCCESS, self.gst.StateChangeReturn.ASYNC):
                label = "hardware (nvv4l2decoder)" if use_hw else "software (avdec_h265)"
                print(f"[GStreamer] Pipeline PLAYING with {label}", flush=True)
                return
            self.pipeline.set_state(self.gst.State.NULL)
        raise RuntimeError("Failed to initialize GStreamer appsink (tried hw + sw HEVC decoders)")

    def read(self):
        # Some PyGObject builds do not expose try_pull_sample directly.
        if hasattr(self.sink, "try_pull_sample"):
            sample = self.sink.try_pull_sample(500 * self.gst.MSECOND)
        else:
            sample = self.sink.emit("try-pull-sample", 500 * self.gst.MSECOND)
        if sample is None:
            return False, None

        buf = sample.get_buffer()
        caps = sample.get_caps().get_structure(0)
        width = caps.get_value("width")
        height = caps.get_value("height")

        ok, map_info = buf.map(self.gst.MapFlags.READ)
        if not ok:
            return False, None

        try:
            frame = np.frombuffer(map_info.data, dtype=np.uint8)
            frame = frame.reshape((height, width, 3))
            return True, frame
        finally:
            buf.unmap(map_info)

    def close(self):
        if self.pipeline is not None:
            self.pipeline.set_state(self.gst.State.NULL)


class GStreamerCliFrameSource:
    def __init__(self, source, width, height, is_rtsp, gst_launch_bin):
        self.source = source
        self.width = width
        self.height = height
        self.is_rtsp = is_rtsp
        self.gst_launch_bin = gst_launch_bin
        self.proc = None

    def _build_command(self):
        if self.is_rtsp:
            return [
                self.gst_launch_bin, "-q",
                "rtspsrc", f"location={self.source}", "protocols=tcp", "latency=200",
                "!", "rtph265depay",
                "!", "h265parse",
                "!", "avdec_h265",
                "!", "videoconvert",
                "!", f"video/x-raw,format=BGR,width={self.width},height={self.height}",
                "!", "fdsink", "fd=1",
            ]

        escaped_path = self.source.replace("\\", "/")
        return [
            self.gst_launch_bin, "-q",
            "filesrc", f"location={escaped_path}",
            "!", "decodebin",
            "!", "videoconvert",
            "!", f"video/x-raw,format=BGR,width={self.width},height={self.height}",
            "!", "fdsink", "fd=1",
        ]

    def open(self):
        cmd = self._build_command()
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def read(self):
        frame_size = self.width * self.height * 3
        if self.proc is None or self.proc.stdout is None:
            return False, None
        frame_data = self.proc.stdout.read(frame_size)
        if len(frame_data) < frame_size:
            return False, None
        frame = np.frombuffer(frame_data, dtype=np.uint8).reshape((self.height, self.width, 3))
        return True, frame

    def close(self):
        if self.proc is not None:
            self.proc.terminate()


class OpenCVFrameSource:
    """Fallback frame source using cv2.VideoCapture (FFmpeg backend when possible)."""

    def __init__(self, source, width, height, is_rtsp):
        self.source = source
        self.width = width
        self.height = height
        self.is_rtsp = is_rtsp
        self.cap = None

    def open(self):
        src = _sanitize_rtsp_for_cv2(self.source) if self.is_rtsp else self.source
        self.cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(src)
        if not self.cap.isOpened():
            raise RuntimeError("OpenCV VideoCapture could not open source")
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self):
        if self.cap is None:
            return False, None
        ok, frame = self.cap.read()
        if not ok or frame is None:
            return False, None
        if frame.shape[1] != self.width or frame.shape[0] != self.height:
            frame = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_LINEAR)
        return True, frame

    def close(self):
        if self.cap is not None:
            self.cap.release()
