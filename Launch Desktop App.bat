@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Python environment not found. See README.md for setup.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "desktop_app.py"
