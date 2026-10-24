@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0package-docker.ps1"
if errorlevel 1 (
  echo.
  echo Packaging failed. Please copy the error shown above.
) else (
  echo.
  echo Packaging complete.
)
pause
