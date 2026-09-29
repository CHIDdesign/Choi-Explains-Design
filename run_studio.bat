@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo 먼저 setup_windows.bat 을 실행해 주세요.
  pause
  exit /b 1
)
rem setup 이 tools\ 에 설치한 Node.js·FFmpeg 를 먼저 쓴다
set "PATH=%~dp0tools\node;%~dp0tools\ffmpeg\bin;%PATH%"
start "" ".venv\Scripts\pythonw.exe" -m studio
