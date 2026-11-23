@echo off
cd /d "%~dp0"
title PAYFLOW Launcher
echo ============================================================
echo   PAYFLOW - Windows Launcher
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found.
  echo Install Python 3 from https://www.python.org/downloads/
  echo IMPORTANT: tick "Add python.exe to PATH" during installation.
  echo.
  pause
  exit /b 1
)

python --version
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Could not create virtual environment.
    pause
    exit /b 1
  )
) else (
  echo [1/4] Virtual environment already exists.
)

echo [2/4] Activating...
call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo [ERROR] Could not activate virtual environment.
  pause
  exit /b 1
)

echo [3/4] Installing dependencies ^(first run takes a minute^)...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Dependency installation failed.
  echo Copy the RED error text above and send it for help.
  pause
  exit /b 1
)

echo [4/4] Running tests...
python -m pytest backend/tests -q
if errorlevel 1 (
  echo [WARNING] Some tests failed, but starting the server anyway.
)

echo.
echo ============================================================
echo   Starting PAYFLOW at http://127.0.0.1:8000/
echo   Login: aditi_sharma / Customer@123
echo   Press Ctrl+C to stop.
echo ============================================================
echo.
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

echo.
echo Server stopped.
pause
