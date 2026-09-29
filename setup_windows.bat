@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Choi Studio - 설치
cd /d "%~dp0"
echo.
echo ==============================================================
echo   Choi Studio 설치 (Windows + NVIDIA)
echo   Python / Node.js / FFmpeg 를 확인하고, 없으면 직접 내려받아 설치합니다.
echo   (winget·관리자 권한 필요 없음. 처음에는 약 5~6GB 를 내려받아 20~40분 걸립니다)
echo ==============================================================
echo.

rem Node.js·FFmpeg 는 이 폴더의 tools\ 에 설치해서 이 창에서 바로 쓴다(재시작 불필요)
set "TOOLS=%CD%\tools"
set "PATH=%TOOLS%\node;%TOOLS%\ffmpeg\bin;%PATH%"
set "PS=powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\install_tools.ps1""

rem ---------- Python 3.10~3.13 ----------
call :find_python
if not defined PY (
  echo [설치] Python 3.12 를 내려받아 설치합니다...
  %PS% -Python || goto :fail
  call :find_python
)
if not defined PY (
  echo [오류] Python 을 찾지 못했습니다. https://www.python.org/downloads/ 에서 3.12 를 설치할 때
  echo        "Add python.exe to PATH" 를 체크한 뒤 이 파일을 다시 실행해 주세요.
  goto :fail
)

rem ---------- Node.js 18 이상 ----------
set "NODE_OK=0"
node -e "process.exit(+process.versions.node.split('.')[0]>=18?0:1)" >nul 2>nul && set "NODE_OK=1"
if "!NODE_OK!"=="0" (
  echo [설치] Node.js LTS 를 tools\node 에 설치합니다...
  %PS% -Node || goto :fail
)

rem ---------- FFmpeg ----------
set "FF_OK=0"
ffmpeg -hide_banner -version >nul 2>nul && set "FF_OK=1"
if "!FF_OK!"=="0" (
  echo [설치] FFmpeg ^(NVENC 포함^) 을 tools\ffmpeg 에 설치합니다...
  %PS% -Ffmpeg || goto :fail
)

echo.
echo [확인] Python:
%PY% --version || goto :fail
echo [확인] Node.js:
node --version || goto :fail
echo [확인] FFmpeg:
ffmpeg -hide_banner -version | findstr /b "ffmpeg" || goto :fail
ffmpeg -hide_banner -encoders 2>nul | findstr /c:"h264_nvenc" >nul && echo   NVENC 사용 가능 || echo   NVENC 없음 - CPU 인코딩으로 동작
echo.

rem ---------- 가상환경 + 파이썬 패키지 ----------
if not exist ".venv\Scripts\python.exe" (
  echo [설치] 파이썬 가상환경 생성...
  %PY% -m venv .venv || goto :fail
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || goto :fail
echo [설치] GPU 음성인식용 CUDA 라이브러리 cuBLAS / cuDNN ^(약 1.5GB^)...
python -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"

rem ---------- 렌더러(Remotion) ----------
echo [설치] 렌더러 패키지 npm install ...
pushd renderer
call npm install --no-audit --no-fund || (popd & goto :fail)
echo [설치] 렌더링용 Chrome Headless Shell...
call npx remotion browser ensure
popd

rem ---------- Whisper 모델 미리 받기 ----------
echo.
choice /c YN /m "Whisper large-v3 음성인식 모델 약 3GB 를 지금 미리 받을까요"
if %errorlevel%==1 (
  python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cpu', compute_type='int8'); print('모델 준비 완료')"
)

echo.
echo ==============================================================
echo   설치 완료!  run_studio.bat 을 더블클릭하면 창이 열립니다.
echo ==============================================================
pause
exit /b 0

rem ---------------------------------------------------------------
rem 쓸 수 있는 Python(3.10~3.13) 찾기. Microsoft Store 가짜 python.exe 는 걸러진다.
:find_python
set "PY="
for %%V in (312 313 311 310) do (
  if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
)
if not defined PY (
  py -3.12 -c "import sys" >nul 2>nul && set "PY=py -3.12"
)
if not defined PY (
  py -3 -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>nul && set "PY=python"
)
exit /b 0

:fail
echo.
echo [오류] 설치 중 문제가 발생했습니다. 위의 메시지를 확인해 주세요.
echo        인터넷 연결을 확인하고(학교·회사망은 다운로드가 막힐 수 있음) 다시 실행하면 이어서 설치합니다.
pause
exit /b 1
