@echo off
REM Quick launcher for dual camera monitoring
cd /d "%~dp0"
call ..\\.venv\Scripts\activate.bat
python dual_camera_monitor.py --post --display
pause
