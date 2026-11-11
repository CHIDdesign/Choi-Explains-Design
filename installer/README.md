# ChoiStudio.exe — 설치·업데이트·실행 하나로

- 처음 실행: 설치 위치를 고르면 GitHub `main` 의 최신 커밋을 zip 으로 받아 풀고 `setup_windows.bat` 을 자동 모드(`CHOI_SETUP_AUTO=1` — Pixabay 키 질문·모델 질문·마지막 pause 없음)로 돌린 뒤 실행한다. 자신을 설치 폴더에 `ChoiStudio.exe` 로 복사하고 위치를 `HKCU\Software\ChoiStudio\InstallDir` 에 적는다. 바탕화면 바로가기는 setup 이 이 exe 로 만든다.
- 다음부터: 받은 커밋(`.choi_version`)보다 새 커밋이 있으면 업데이트를 묻고 덮어쓴다(`key\`·`user\`·`projects\`·`.venv`·`models\`·`tools\` 는 zip 에 없어 그대로; 저장소에서 지운 파일은 남는다). 그다음 `run_studio.bat`(패키지 늘었으면 자동 설치).
- 옵션: `--dir <폴더>`(고르는 창 없이) · `--no-launch`(설치·업데이트만).
- 관리자 권한(manifest `requireAdministrator`) — .bat 들이 따로 다시 올리지 않게.

## 빌드(Windows 기본 .NET Framework 4 의 csc, 설치할 것 없음)

PowerShell 에서 저장소 폴더 기준:

```
& C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe -nologo -codepage:65001 -optimize -target:winexe -out:installer\ChoiStudio.exe -win32icon:assets\choi_studio.ico -win32manifest:installer\app.manifest -r:System.IO.Compression.dll -r:System.IO.Compression.FileSystem.dll -r:System.Windows.Forms.dll installer\ChoiStudio.cs
```

`assets\choi_studio.ico` 는 `python -m studio.gui.icon assets\choi_studio.ico` 로 만든다(gitignore). csc 는 C# 5 문법만 받는다(문자열 보간·`?.` 금지).
