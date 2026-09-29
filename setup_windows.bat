@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title Choi Studio - 설치
cd /d "%~dp0"
echo.
echo ==============================================================
echo   Choi Studio 설치 (Windows + NVIDIA)
echo   Python / Node.js / FFmpeg 확인 후 필요한 패키지를 설치합니다.
echo ==============================================================
echo.

set NEED_RESTART=0

rem ---------- Python ----------
where py >nul 2>nul
if %errorlevel%==0 (
  set PY=py -3
) else (
  where python >nul 2>nul
  if !errorlevel!==0 (
    set PY=python
  ) else (
    echo [설치] Python 3.12 을 설치합니다...
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    set NEED_RESTART=1
  )
)

rem ---------- Node.js ----------
where node >nul 2>nul
if not %errorlevel%==0 (
  echo [설치] Node.js LTS 를 설치합니다...
  winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
  set NEED_RESTART=1
)

rem ---------- FFmpeg ----------
where ffmpeg >nul 2>nul
if not %errorlevel%==0 (
  echo [설치] FFmpeg ^(Gyan full build, NVENC 포함^) 을 설치합니다...
  winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
  set NEED_RESTART=1
)

if "%NEED_RESTART%"=="1" (
  echo.
  echo  새 프로그램이 설치되었습니다. 이 창을 닫고 setup_windows.bat 을 한 번 더 실행해 주세요.
  echo  PATH 는 새 창에서부터 적용됩니다.
  pause
  exit /b 0
)

echo [확인] Python:
%PY% --version
echo [확인] Node.js:
node --version
echo [확인] FFmpeg:
ffmpeg -hide_banner -version | findstr /b "ffmpeg"
ffmpeg -hide_banner -encoders 2>nul | findstr /c:"h264_nvenc" >nul && echo   NVENC 사용 가능 || echo   NVENC 없음 - CPU 인코딩으로 동작

rem ---------- 가상환경 + 파이썬 패키지 ----------
if not exist ".venv\Scripts\python.exe" (
  echo [설치] 파이썬 가상환경 생성...
  %PY% -m venv .venv || goto :fail
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || goto :fail
echo [설치] GPU 음성인식용 CUDA 라이브러리 cuBLAS / cuDNN ...
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

:fail
echo.
echo [오류] 설치 중 문제가 발생했습니다. 위의 메시지를 확인해 주세요.
pause
exit /b 1
