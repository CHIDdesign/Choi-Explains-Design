@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem 오류 메시지를 콘솔에서 보고 싶을 때 사용
".venv\Scripts\python.exe" -m studio
pause
