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
rem 음성인식 모델·임시 파일은 프로그램 폴더 안에(C 드라이브 용량 절약)
set "HF_HOME=%~dp0models\hf"
if not exist "%~dp0tools\tmp" mkdir "%~dp0tools\tmp"
set "TEMP=%~dp0tools\tmp"
set "TMP=%~dp0tools\tmp"
".venv\Scripts\python.exe" -m studio
pause
