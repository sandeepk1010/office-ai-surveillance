# RTSP Monitoring - GStreamer + YOLO Setup Guide

## Current Stack

The office in/out detector now uses:
- GStreamer for RTSP/video decoding
- YOLO (Ultralytics) for person detection
- A centroid line-crossing tracker for IN/OUT events

## Why This Change

OpenCV has been removed from the office in/out detection path to avoid dependency and codec issues. The primary runtime path is now GStreamer + YOLO.

## Solutions

### 1. Install GStreamer (Required)

#### On Windows:
1. **Download GStreamer 1.x**:
   - Visit: https://gstreamer.freedesktop.org/download/
   - Install both Runtime and Development packages (MSVC x86_64)

2. **Unzip and add to PATH**:
   - Add GStreamer bin path to `PATH`
   - Example: `C:\gstreamer\1.0\msvc_x86_64\bin`
   - Test in PowerShell:
     ```powershell
     gst-launch-1.0 --version
     ```

### 2. Install Python Dependencies (Required)

From `python-scripts`:

```powershell
pip install -r requirements.txt
```

This installs `ultralytics`, `PyGObject`, `numpy`, and `requests`.

### 3. Optional: Install FFmpeg (Debugging Only)

FFmpeg is optional now, but useful for independent RTSP validation.

Alternative - Use Scoop:
   ```powershell
   scoop install ffmpeg
   ```

Alternative - Use Chocolatey:
   ```powershell
   choco install ffmpeg
   ```

## Testing

Verify setup:

```bash
# Run diagnostic again
python diagnose.py

# Test with your camera
python line_counter.py --url 'rtsp://admin:India123%23@192.168.1.245:554/cam/realmonitor?channel=1&subtype=0' --post --model yolov8n.pt
```

## Alternative (No External Dependencies)

For local video files testing:

```bash
python line_counter.py --video sample.mp4 --model yolov8n.pt
```

## Troubleshooting

### "No module named gi"
- PyGObject is missing in the active Python environment.
- Solution: install `PyGObject` and make sure GStreamer runtime is installed.

### GStreamer pipeline errors
- Confirm `gst-launch-1.0 --version` works in the same shell.
- Ensure your RTSP URL is correct and reachable.
- Try reducing resolution with `--width 1280 --height 720`.

### YOLO model download/runtime issues
- First run may download model weights (internet needed).
- Pre-download model and pass local path with `--model`.

## Files in this directory

- `line_counter.py` - Main script (requires FFmpeg for RTSP)
- `diagnose.py` - System diagnostic tool
- `monitor.py` - Alternative monitoring script (if available)
- `requirements.txt` - Python dependencies
- `run_line_counter.bat` - Batch script launcher
- `run_line_counter.ps1` - PowerShell launcher

## Next Steps

1. **Install GStreamer + PyGObject**  
2. **Run diagnosis**: `python diagnose.py`
3. **Test**: `python line_counter.py --url 'rtsp://...' --model yolov8n.pt`
4. **Tune**: adjust `--conf`, `--match-distance`, and `--line-fraction`

## Support

For issues with:
- **GStreamer**: verify installation and PATH configuration
- **YOLO**: verify package and model availability
- **RTSP**: confirm camera URL and network connectivity
- **Camera auth**: URL-encode special characters in credentials

Example with encoded password:
```
Python:
  '--url', 'rtsp://admin:India123%23@192.168.1.245:554/...'

Environment variable:
  $env:RTSP_URL='rtsp://admin:India123%23@192.168.1.245:554/...'
```
