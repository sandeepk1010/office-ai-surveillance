@echo off
REM Windows CMD wrapper for line_counter.py
REM Usage examples:
REM   run_line_counter.bat --url "rtsp://..." --post --display --line-fraction 0.45
REM   run_line_counter.bat --video ..\some_test_video.mp4 --display

SETLOCAL ENABLEDELAYEDEXPANSION
set "ARGS="
:parse
if "%~1"=="" goto done
if "%~1"=="--url" (
  set "RTSP_URL=%~2"
  shift
  shift
  goto parse
)
set "ARGS=!ARGS! %~1"
shift
goto parse
:done
if defined RTSP_URL (
  set "RTSP_URL=%RTSP_URL%"
)
echo Running with RTSP_URL=%RTSP_URL%
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Missing local virtual environment at %PYTHON_EXE%
  echo Create it with: python -m venv .venv
  exit /b 1
)
"%PYTHON_EXE%" "%~dp0line_counter.py" %ARGS%
ENDLOCAL
