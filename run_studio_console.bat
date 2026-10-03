@echo off
chcp 65001 >nul
rem ---- 관리자 권한으로 자동 재실행(더블클릭만 하면 됨) ----
fltmc >nul 2>&1
if errorlevel 1 (
  if /i "%~1"=="--elevated" goto :elev_skip
  echo 관리자 권한으로 다시 엽니다. '사용자 계정 컨트롤' 창이 뜨면 [예]를 눌러 주세요.
  set "CHOI_SELF=%~f0"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Start-Process -FilePath $env:CHOI_SELF -ArgumentList '--elevated' -Verb RunAs -ErrorAction Stop } catch { exit 1 }"
  if errorlevel 1 (
    echo.
    echo [안내] 관리자 권한 실행이 취소되었습니다.
    echo        이 파일을 마우스 오른쪽 버튼으로 눌러 '관리자 권한으로 실행' 을 골라도 됩니다.
    pause
  )
  exit /b
)
goto :elev_ok
:elev_skip
echo [경고] 관리자 권한을 얻지 못해 일반 권한으로 계속합니다.
:elev_ok
cd /d "%~dp0"
rem 오류 메시지를 콘솔에서 보고 싶을 때 사용
if not exist ".venv\Scripts\python.exe" (
  echo 먼저 setup_windows.bat 을 실행해 주세요.
  pause
  exit /b 1
)
rem 이 .venv 가 이 PC 에 없는 파이썬을 가리키면(다른 PC·계정에서 복사·동기화된 폴더) setup 이 새로 만든다
".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
if errorlevel 1 (
  echo 파이썬 가상환경^(.venv^)이 이 PC 에 없는 파이썬을 가리킵니다^(다른 PC·계정에서 복사하거나 OneDrive 로 동기화된 폴더^).
  echo setup_windows.bat 을 다시 실행하면 새로 만듭니다.
  pause
  exit /b 1
)
set "PATH=%~dp0tools\node;%~dp0tools\ffmpeg\bin;%PATH%"
rem 음성인식 모델·임시 파일은 프로그램 폴더 안에(C 드라이브 용량 절약)
set "HF_HOME=%~dp0models\hf"
rem 단 프로그램 폴더가 OneDrive 안이면 임시 파일(렌더용 브라우저 프로필 등)은 OneDrive 밖에 — 동기화가 계속 올리지 않게
set "CHOI_TMP=%~dp0tools\tmp"
echo "%~dp0" | find /i "\OneDrive" >nul && set "CHOI_TMP=%LOCALAPPDATA%\Temp\ChoiStudio"
if not exist "%CHOI_TMP%" mkdir "%CHOI_TMP%"
set "TEMP=%CHOI_TMP%"
set "TMP=%CHOI_TMP%"
fc /b "requirements.txt" ".venv\.req_stamp" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt && copy /y "requirements.txt" ".venv\.req_stamp" >nul
)
fc /b "renderer\package.json" "renderer\node_modules\.pkg_stamp" >nul 2>&1
if errorlevel 1 (
  pushd renderer
  call npm install --no-audit --no-fund && copy /y "package.json" "node_modules\.pkg_stamp" >nul
  popd
)
".venv\Scripts\python.exe" -m studio
pause
