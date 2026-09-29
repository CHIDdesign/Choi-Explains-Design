@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 오류 메시지를 콘솔에서 보고 싶을 때 사용
if not exist ".venv\Scripts\python.exe" (
  echo 먼저 setup_windows.bat 을 실행해 주세요.
  pause
  exit /b 1
)
set "PATH=%~dp0tools\node;%~dp0tools\ffmpeg\bin;%PATH%"
".venv\Scripts\python.exe" -m studio
pause
