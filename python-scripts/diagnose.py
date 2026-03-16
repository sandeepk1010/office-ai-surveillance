#!/usr/bin/env python
"""
Diagnostic script for GStreamer + YOLO RTSP office in/out detection.
Checks system dependencies and provides setup guidance.
"""

import sys
import platform
import subprocess
import importlib.util


def check_gstreamer():
    """Check GStreamer Python bindings and core runtime."""
    print("=" * 60)
    print("🔍 CHECKING GSTREAMER...")
    print("=" * 60)

    try:
        if importlib.util.find_spec('gi') is None:
            raise ImportError('gi (PyGObject) is not installed')
        gi = importlib.import_module('gi')
        gi.require_version('Gst', '1.0')
        Gst = importlib.import_module('gi.repository.Gst')
        Gst.init(None)
        version = Gst.version()
        print(f"✓ GStreamer is available ({version[0]}.{version[1]}.{version[2]})")
        return True
    except ImportError as e:
        print(f"✗ GStreamer import error: {e}")
        return False
    except Exception as e:
        print(f"✗ GStreamer runtime error: {e}")
        return False


def check_yolo():
    """Check YOLO (ultralytics) installation."""
    print("\n" + "=" * 60)
    print("🔍 CHECKING YOLO...")
    print("=" * 60)

    try:
        if importlib.util.find_spec('ultralytics') is None:
            raise ImportError('ultralytics is not installed')
        ultralytics = importlib.import_module('ultralytics')
        print(f"✓ ultralytics {ultralytics.__version__} is installed")
        return True
    except ImportError as e:
        print(f"✗ ultralytics import error: {e}")
        return False


def check_ffmpeg():
    """Check if FFmpeg is installed."""
    print("\n" + "=" * 60)
    print("🔍 CHECKING FFMPEG...")
    print("=" * 60)
    
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, timeout=5)
        if result.returncode == 0:
            print("✓ FFmpeg is installed")
            lines = result.stdout.decode().split('\n')[0]
            print(f"  {lines}")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    print("✗ FFmpeg is NOT installed")
    return False


def check_imageio():
    """Check imageio for alternative video handling."""
    print("\n" + "=" * 60)
    print("🔍 CHECKING IMAGEIO...")
    print("=" * 60)
    
    try:
        if importlib.util.find_spec('imageio') is None:
            raise ImportError('imageio is not installed')
        imageio = importlib.import_module('imageio')
        print(f"✓ imageio {imageio.__version__} is installed")
        return True
    except ImportError:
        print("✗ imageio is NOT installed")
        return False


def check_system_info():
    """Print system information."""
    print("\n" + "=" * 60)
    print("📋 SYSTEM INFORMATION...")
    print("=" * 60)
    print(f"OS: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version}")
    print(f"Python executable: {sys.executable}")


def main():
    print("\n" + "=" * 60)
    print("OFFICE-AI GSTREAMER + YOLO DIAGNOSTIC TOOL")
    print("=" * 60 + "\n")
    
    check_system_info()
    
    gstreamer_ok = check_gstreamer()
    yolo_ok = check_yolo()
    ffmpeg_ok = check_ffmpeg()
    imageio_ok = check_imageio()
    
    print("\n" + "=" * 60)
    print("📊 DIAGNOSIS & SOLUTIONS")
    print("=" * 60)
    
    if gstreamer_ok and yolo_ok:
        print("\n✓ All systems ready for office in/out detection!")
        print("  Run: python line_counter.py --url 'rtsp://...' --display")

    elif not gstreamer_ok and yolo_ok:
        print("\n⚠️  YOLO is available but GStreamer is missing")
        print("\nSOLUTION: Install GStreamer runtime + Python bindings")
        print("  1. Install GStreamer 1.x (runtime + plugins)")
        print("  2. Install PyGObject for your Python environment")
        print("  3. Re-run: python diagnose.py")

    elif gstreamer_ok and not yolo_ok:
        print("\n⚠️  GStreamer is available but YOLO package is missing")
        print("\nSOLUTION: Install ultralytics")
        print("  pip install ultralytics")

    elif not gstreamer_ok and not yolo_ok:
        print("\n✗ Neither GStreamer nor YOLO are properly configured")
        print("\nRECOMMENDED SOLUTION:")
        print("  1. Install GStreamer runtime/plugins")
        print("  2. Install Python deps:")
        print("     pip install -r requirements.txt")
        print("  3. Then run: python line_counter.py --url 'rtsp://...' --display")
    
    print("\n" + "=" * 60)
    print("For local video files (testing):")
    print("  python line_counter.py --video sample.mp4 --display")
    print("=" * 60 + "\n")
    
    if not ffmpeg_ok:
        print("\nNote: FFmpeg is optional for the new detector, but still useful for stream debugging.")
    if not imageio_ok:
        print("Note: imageio is optional.")

    return 0 if gstreamer_ok and yolo_ok else 1


if __name__ == '__main__':
    sys.exit(main())
