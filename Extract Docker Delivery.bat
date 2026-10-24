@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0extract-from-docker.ps1" -ImageTar "%~dp0citefjord-delivery.tar"
if errorlevel 1 (
  echo.
  echo Extraction failed. Please copy the error shown above.
) else (
  echo.
  echo Extraction complete. Open the CiteFjord folder and run CiteFjord.exe.
)
pause
