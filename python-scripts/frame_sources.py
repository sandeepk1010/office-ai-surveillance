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

    def _build_rtsp_pipeline(self, codec, use_hw_decoder=True):
        depay = "rtph264depay" if codec == "h264" else "rtph265depay"
        parse = "h264parse" if codec == "h264" else "h265parse"
        sw_dec = "avdec_h264" if codec == "h264" else "avdec_h265"

        if use_hw_decoder:
            return (
                f'rtspsrc location="{self.source}" protocols=tcp latency=200 '
                f'! rtpjitterbuffer ! {depay} ! {parse} '
                '! nvv4l2decoder ! nvvidconv '
                '! video/x-raw,format=BGRx '
                '! videoconvert ! video/x-raw,format=BGR '
                '! appsink name=sink sync=false max-buffers=1 drop=true'
            )

        return (
            f'rtspsrc location="{self.source}" protocols=tcp latency=200 '
            f'! rtpjitterbuffer ! {depay} ! {parse} ! {sw_dec} ! videoconvert ! videoscale '
            f'! video/x-raw,format=BGR,width={self.width},height={self.height} '
            '! appsink name=sink emit-signals=false sync=false max-buffers=1 drop=true'
        )

    def _build_pipeline(self, use_hw_decoder=True, codec="h264"):
        if self.is_rtsp:
            return self._build_rtsp_pipeline(codec=codec, use_hw_decoder=use_hw_decoder)

        escaped_path = self.source.replace("\\", "\\\\")
        return (
            f'filesrc location="{escaped_path}" ! decodebin ! videoconvert '
            f"! video/x-raw,format=BGR,width={self.width},height={self.height} "
            "! appsink name=sink emit-signals=false sync=false max-buffers=1 drop=true"
        )

    def _get_pipeline_error(self):
        if self.pipeline is None:
            return None
        bus = self.pipeline.get_bus()
        if bus is None:
            return None
        msg = bus.timed_pop_filtered(
            0,
            self.gst.MessageType.ERROR | self.gst.MessageType.WARNING,
        )
        if msg is None:
            return None
        if msg.type == self.gst.MessageType.ERROR:
            err, debug = msg.parse_error()
            return f"ERROR: {err}; debug={debug}"
        if msg.type == self.gst.MessageType.WARNING:
            warn, debug = msg.parse_warning()
            return f"WARNING: {warn}; debug={debug}"
        return None

    def open(self):
        attempts = [
            ("h264", True),
            ("h264", False),
            ("h265", True),
            ("h265", False),
        ]

        for codec, use_hw in attempts:
            pipeline_str = self._build_pipeline(use_hw_decoder=use_hw, codec=codec)
            self.pipeline = self.gst.parse_launch(pipeline_str)
            self.sink = self.pipeline.get_by_name("sink")
            if self.sink is None:
                print(f"[GStreamer] Missing appsink for {codec} {'hw' if use_hw else 'sw'} pipeline", flush=True)
                self.pipeline.set_state(self.gst.State.NULL)
                continue
            self.pipeline.set_state(self.gst.State.PLAYING)
            ret, _state, _pending = self.pipeline.get_state(3 * self.gst.SECOND)
            if ret in (self.gst.StateChangeReturn.SUCCESS, self.gst.StateChangeReturn.ASYNC):
                label = "hardware (nvv4l2decoder)" if use_hw else f"software (avdec_{codec})"
                print(f"[GStreamer] Pipeline PLAYING with {label}", flush=True)
                return
            err = self._get_pipeline_error()
            if err:
                print(f"[GStreamer] Failed {codec} {'hw' if use_hw else 'sw'}: {err}", flush=True)
            self.pipeline.set_state(self.gst.State.NULL)
        raise RuntimeError("Failed to initialize GStreamer appsink (tried h264/h265 with hw + sw decoders)")

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

    def _build_command(self, codec="h264"):
        if self.is_rtsp:
            depay = "rtph264depay" if codec == "h264" else "rtph265depay"
            parse = "h264parse" if codec == "h264" else "h265parse"
            sw_dec = "avdec_h264" if codec == "h264" else "avdec_h265"
            return [
                self.gst_launch_bin, "-q",
                "rtspsrc", f"location={self.source}", "protocols=tcp", "latency=200",
                "!", "rtpjitterbuffer",
                "!", depay,
                "!", parse,
                "!", sw_dec,
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
        if not self.is_rtsp:
            cmd = self._build_command()
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return

        last_err = None
        for codec in ("h264", "h265"):
            cmd = self._build_command(codec=codec)
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # Validate quickly by trying to read one frame payload chunk.
            ok, _ = self.read()
            if ok:
                print(f"[GStreamer CLI] Pipeline PLAYING with software (avdec_{codec})", flush=True)
                return
            if self.proc is not None:
                try:
                    if self.proc.stderr is not None:
                        err_bytes = self.proc.stderr.read(2048)
                        if err_bytes:
                            last_err = err_bytes.decode(errors="ignore")
                except Exception:
                    pass
                self.proc.terminate()
                self.proc = None

        raise RuntimeError(
            "Failed to initialize gst-launch appsink equivalent output "
            f"(tried h264/h265 software decoders). Last stderr: {last_err or 'n/a'}"
        )

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
