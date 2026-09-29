@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo 먼저 setup_windows.bat 을 실행해 주세요.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m studio
