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
setlocal EnableDelayedExpansion
title Choi Studio - 설치
cd /d "%~dp0"
echo.
echo ==============================================================
echo   Choi Studio 설치 (Windows + NVIDIA)
echo   Python / Node.js / FFmpeg / Claude Code 를 확인하고, 없으면 직접 내려받아 설치합니다.
echo   (관리자 권한으로 자동 실행 · winget 불필요 · 처음에는 약 6GB 를 내려받아 20~40분 걸립니다)
echo ==============================================================
echo.

rem Node.js·FFmpeg 는 이 폴더의 tools\ 에 설치해서 이 창에서 바로 쓴다(재시작 불필요)
set "TOOLS=%CD%\tools"
set "PATH=%TOOLS%\node;%TOOLS%\ffmpeg\bin;%PATH%"
set "PS=powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\install_tools.ps1""
rem 무거운 임시 파일·캐시·음성인식 모델은 C 드라이브 사용자 폴더 대신 이 프로그램 폴더 안에 둔다
set "ORIG_TEMP=%TEMP%"
if not exist "%TOOLS%\tmp" mkdir "%TOOLS%\tmp"
set "TEMP=%TOOLS%\tmp"
set "TMP=%TOOLS%\tmp"
set "PIP_NO_CACHE_DIR=1"
set "npm_config_cache=%TOOLS%\npm-cache"
set "HF_HOME=%CD%\models\hf"

rem ---------- 디스크 여유 공간 ----------
echo [확인] 디스크 여유 공간 · 실제 쓰기 테스트^(각 256MB^)
%PS% -DiskCheck -NeedGB 7 -ExtraPaths "%ORIG_TEMP%;%USERPROFILE%"
set "DISK=%errorlevel%"
if "%DISK%"=="2" (
  echo.
  echo [중단] 위 표에서 WRITE FAILED 이거나 공간이 모자란 곳이 있습니다.
  echo        설치를 끝내려면 이 폴더가 있는 드라이브에 7GB 이상, 영상 작업까지 20GB 이상이 필요합니다.
  echo   - 다른 드라이브에는 공간이 많은데 C: 만 가득 찼거나, 사용자 폴더에 용량 제한^(할당량^)이 있을 수 있습니다.
  echo     이때는 이 폴더를 여유 있는 드라이브^(예: D:\ChoiStudio^)로 옮겨 다시 실행하면 됩니다.
  echo   - 휴지통 비우기, 다운로드 폴더 정리, Windows 검색에서 '디스크 정리' 실행^(시스템 파일 정리 포함^)
  echo   - 또는 여유가 있는 다른 드라이브^(예: D:\ChoiStudio^)로 이 폴더를 옮긴 뒤 거기서 다시 실행
  echo     ^(옮긴 뒤 이 폴더를 지우면 이미 설치된 용량도 돌려받습니다^)
  pause
  exit /b 1
)
if "%DISK%"=="3" (
  echo [안내] 설치는 되지만 여유 공간이 20GB 보다 적습니다. 영상 작업 전에 공간을 더 비워 두세요.
)
echo.

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
python -m pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" || goto :fail

rem ---------- 렌더러(Remotion) ----------
echo [설치] 렌더러 패키지 npm install ...
pushd renderer
call npm install --no-audit --no-fund || (popd & goto :fail)
echo [설치] 렌더링용 Chrome Headless Shell...
call npx remotion browser ensure || (popd & goto :fail)
popd

rem ---------- Claude Code (Pro/Max 구독으로 AI 편집 - API 결제 불필요) ----------
echo.
call :find_claude
if not defined CLAUDE_EXE (
  echo [설치] Claude Code 를 설치합니다 ^(Anthropic 공식 설치 스크립트^)...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"
  call :find_claude
)
if defined CLAUDE_EXE (
  echo [확인] Claude Code:
  %CLAUDE_EXE% --version
  %CLAUDE_EXE% auth status --json 2>nul | findstr /r /c:"loggedIn.*true" >nul
  if errorlevel 1 (
    echo.
    echo [로그인] 곧 브라우저가 열립니다. Claude Pro/Max 구독 계정으로 로그인하고 '승인'을 누르세요.
    echo          로그인하면 AI 편집이 구독 사용량으로 동작합니다^(API 결제 불필요^).
    %CLAUDE_EXE% auth login --claudeai
  ) else (
    echo   이미 로그인되어 있습니다.
  )
) else (
  echo [안내] Claude Code 설치에 실패했습니다. 프로그램 설정 - AI 에서 다시 설치하거나 API 키를 쓸 수 있습니다.
)

rem ---------- 효과음·배경음악·잡음 제거 모델(처음 한 번, 약 80MB) ----------
echo.
echo [설치] 효과음·배경음악^(Pixabay 등^)과 목소리 잡음 제거 모델을 내려받습니다...
python -c "from studio.sound.library import SoundLibrary; lib=SoundLibrary(log=print).ensure(); print('  효과음', len(lib.sfx), '개 · 배경음악', len(lib.bgm), '곡')"

rem ---------- (선택) Pixabay 키: 스톡 '영상' B-roll ----------
python -c "from studio.settings import Settings; import sys; sys.exit(0 if Settings.load().pixabay_api_key else 1)" >nul 2>nul
if errorlevel 1 (
  echo.
  echo [선택] Pixabay API 키가 있으면 스톡 '영상' B-roll 도 자동으로 가져옵니다.
  echo        없어도 사진 B-roll·효과음·음악은 동작합니다. https://pixabay.com/api/docs/ 에서 무료 가입 후 키 확인.
  set "PIXKEY="
  set /p PIXKEY="  Pixabay 키를 붙여넣고 Enter ^(없으면 그냥 Enter^): "
  if defined PIXKEY python -c "from studio.settings import Settings; s=Settings.load(); s.pixabay_api_key='!PIXKEY!'.strip(); s.save(); print('  저장했습니다.')"
)

rem ---------- 바탕화면 바로가기(항상 관리자 권한으로 실행) ----------
python -m studio.gui.icon "%CD%\assets\choi_studio.ico" >nul 2>nul
%PS% -Shortcut -Target "%CD%\run_studio.bat" -Icon "%CD%\assets\choi_studio.ico"

rem ---------- Whisper 모델 미리 받기 ----------
echo.
choice /c YN /m "Whisper large-v3 음성인식 모델 약 3GB 를 지금 미리 받을까요"
if %errorlevel%==1 (
  python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3', device='cpu', compute_type='int8'); print('모델 준비 완료')"
)

echo.
echo ==============================================================
echo   설치 완료!  바탕화면의 'Choi Studio' 또는 run_studio.bat 을 더블클릭하면 창이 열립니다.
echo ==============================================================
pause
exit /b 0

rem ---------------------------------------------------------------
rem Claude Code 실행 파일 찾기(공식 설치 위치 우선)
:find_claude
set "CLAUDE_EXE="
if exist "%USERPROFILE%\.local\bin\claude.exe" set CLAUDE_EXE="%USERPROFILE%\.local\bin\claude.exe"
if not defined CLAUDE_EXE (
  where claude >nul 2>nul && set "CLAUDE_EXE=claude"
)
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
echo   - "No space left" / "ENOSPC" / "not enough space" 가 보이면 디스크 공간이 부족한 것입니다.
echo     공간을 비우거나 여유 있는 드라이브로 폴더를 옮긴 뒤 다시 실행하세요.
echo   - 다운로드 오류면 인터넷 연결을 확인하세요^(학교·회사망은 막힐 수 있음^).
echo   다시 실행하면 이미 설치된 것은 건너뛰고 이어서 설치합니다.
pause
exit /b 1
