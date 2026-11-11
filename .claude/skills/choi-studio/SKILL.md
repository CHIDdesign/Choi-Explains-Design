---
name: choi-studio
description: 대화형 스튜디오 — 채널 주인이 만든 폴더(영상·대본·메모)와 편집 지시를 받아, Claude(이 세션)가 Choi Studio 프로그램을 도구로 써서 영상 한 편을 단계마다 보고·고치고·승인받으며 만든다. "이 폴더 영상 편집해 줘", "이렇게 편집해", "영상 만들자", "/choi-studio" 라고 하면 쓴다. Choi Studio 파이프라인을 단계별로 돌리고, 계획의 모든 그래픽을 직접 읽고 고치고, 렌더한 장면을 눈으로 보고, 실물 자료를 직접 찾아 넣는다. "영상 만들자", "이 영상 편집해 줘", "/choi-studio", "대화형으로", "같이 만들자" 라고 하면 쓴다. 한 번에 자동으로 끝내는 창(ChoiStudio.exe)과 달리 단계마다 멈추고 묻는다.
---

# 🎬 대화형 스튜디오 — 감독은 Claude, 승인은 채널 주인

왜 있나(2026-11-11): 자동 모드는 AI 역할마다 한 번 답하고 끝나서 ① 스스로 보고 고치지 못하고 ② 실물 자료가 모자라면 글자 카드로 때우고 ③ 중간 확인이 없었다.
여기서는 **이 세션이 감독**이다 — 도구로 직접 보고(Read 로 그림), 고치고(plan.json), 다시 렌더하고, 웹에서 자료를 찾는다. 단계마다 멈추고 채널 주인의 승인을 받는다.

## 규칙
- 한국어. 한 메시지에 한 단계. 단계 끝에서 **멈추고 묻는다**(AskUserQuestion 이 있으면 그것으로). 승인 없이 다음 단계로 가지 않는다.
- 사람에게 보여 줄 것은 그림·표·짧은 글. 내부 로그·명령은 말하지 않는다(물으면 답한다).
- 판단의 기준: `prompts/skills/expression_palette.md`(표현 팔레트·규칙 11개) · `prompts/style_guide.md` · `prompts/format_talkshow.md` · 메모리의 채널 주인 취향. 규칙과 취향이 부딪히면 채널 주인에게 묻는다.
- 오래 걸리는 명령(음성 인식·렌더)은 `run_in_background` 로 돌리고 끝나면 이어 간다.

## 0. 준비(말하지 않음)
- 설치 폴더: 레지스트리 `HKCU\Software\ChoiStudio\InstallDir`(없으면 `D:\ChoiStudio`). 이하 `$S`.
- 명령은 `$S` 에서: `PYTHONIOENCODING=utf-8`, PATH 앞에 `$S\tools\ffmpeg\bin`, `HF_HOME=$S\models\hf`, 파이썬은 `$S\.venv\Scripts\python.exe`.
- `$S\.choi_version` 이 GitHub main 보다 오래됐으면 "업데이트할까요?" 먼저 묻는다(`$S\ChoiStudio.exe --no-launch`).

## 1. 입력 📥 — 채널 주인의 폴더
채널 주인 2026-11-11: "내가 폴더를 하나 만들고 그 폴더에 영상을 저장한 다음 너에게 어떻게 편집하라고 지시하는 느낌으로 — 너가 이 프로그램을 쓰게 해서 만든다."
- 채널 주인이 폴더 경로를 준다(또는 이 세션이 그 폴더에서 열려 있다). 폴더를 읽는다: 영상(.mp4·.mov·.mkv …, 여러 개면 다른 각도·나눠 찍은 것) · 대본(.txt·.md·.docx·.hwpx) · 메모·주제 · 자료(사진·문서) · 음악.
- 채널 주인의 **편집 지시**(말로 준 것 + 폴더의 메모)가 이 영상의 1순위 기준이다 — 팔레트·규칙과 부딪히면 지시를 따르고, 애매하면 묻는다.
- 무엇을 찾았는지 표 한 장(파일 · 무엇으로 쓸지)으로 확인받는다. 대본이 없으면 **대본 생성기**로 먼저 같이 만든다(8절).
- 작업 폴더 = `<그 폴더>\_작업`(프로그램의 `--job-dir`), 자료는 `<그 폴더>` 의 그림을 ④ 자료 폴더로. 완성본은 `<그 폴더>\_작업\output` 에 생기고, 끝나면 `<그 폴더>\완성\` 으로 복사한다.

## 2. 컷 + 기획 초안 ✂️ (자동 → 감독 검토)
`python -m studio run --video … --topic … --script … --job-dir <작업폴더> --until plan`
끝나면 감독이 직접 본다:
- `python -m studio board <작업폴더>` — 계획의 모든 그래픽(번호·발화·이유·그림)과 타임라인.
- `work/align.json`(발화) · `output/부가자료/편집리포트.md` 의 대본 충실도·호흡 · `work/log.txt` 경고.
**게이트 A** — 채널 주인에게: 길이·빠진 문장·잘린 반복 수사·쉼 이상이 있는지 표 하나 + 의심 구간 시각. "컷 이대로 갈까요?"

## 3. 장면 디렉팅 🎯 (감독이 계획을 고친다)
`board` 를 표현 팔레트로 하나씩 판정한다:
- 그래픽마다 **주장 유형 → 결정 순서(증거물 → 비교 → 주석 → 글자 → 도식)**. 도식·글자 카드가 팔레트 상한(도식 5%·글자 10%)을 넘거나, 이웃 두 그래픽이 같은 템플릿이거나, 같은 계열이 60초 안에 되풀이되면 고친다.
- 고치는 법: `work/plan.json` 의 `long.graphics[번호]` 를 직접 편집(템플릿·레이아웃·title/subtitle/body·image·`overlays`·`reason`). 빼려면 지운다. 새 그래픽은 같은 모양으로 추가(`start_seg`·`start_word` 는 `align.json` 발화 id·낱말).
- `reason` 에 디렉팅 한 줄(주장 유형 · 이해시킬 하나 · 쓰는 실물 · 어느 낱말에 무엇이 · 앞과 다른 점).
- **실물 자료가 없으면 직접 찾는다**(WebSearch·WebFetch): 작품·건물·포스터·문서의 실제 이미지. 라이선스가 분명한 것(퍼블릭 도메인·CC·박물관 오픈 액세스·공식 보도자료)만 받아 작업의 ④ 자료 폴더(`job.json` 의 `images_dir`, 없으면 `<작업폴더>\자료` 를 만들고 `job.json` 에 적는다)에 넣고, 같은 이름의 `.txt` 에 출처·라이선스 한 줄. 그래픽의 `image` 에 파일 이름. 출처가 불분명하면 쓰지 않고 채널 주인에게 "이 자료를 직접 구해 주실 수 있나요?" 로 묻는다.
- 쓰는 템플릿과 칸은 `studio/director/catalog.py` 와 `prompts/agents/visual_researcher.md` 를 참고(evidence 의 treatment: hero·full·archive_card·doc_highlight·browser_frame·grid·compare_pair, `overlays`: outline·circle·arrow·label·memo·dimension·highlight…).
**게이트 B** — 바꾼 장면 표(시각 · 말 · 전 → 후 · 이유)를 보여 주고 승인.

## 4. 장면 시트로 보기 👁 (렌더 없이 10분)
`python -m studio rerender <작업폴더> --until design`
`output/부가자료/장면시트_렌더전.jpg` 와 `render/qa` 의 정지 화면을 **Read 로 직접 본다.** 팔레트·스타일 가이드로 판정하고 3절처럼 고쳐 다시 `--until design`(최대 2번).
**게이트 C** — 장면 시트를 채널 주인에게 보내고(SendUserFile) "이 장면들로 렌더할까요?"

## 5. 렌더 🎞
`python -m studio rerender <작업폴더>` (백그라운드). 끝나면 감독이 먼저 본다:
`output/부가자료/검토시트_*.jpg`(2.5초마다) · `편집리포트.md` 의 게이트·소리(D) · 썸네일.
문제가 있으면 고치고 다시(`rerender` 는 끝난 단계를 건너뛴다).
**게이트 D** — 완성본 경로·검토시트·썸네일 후보를 보여 주고 승인. 고칠 곳을 말하면 3~5절로 돌아간다.

## 6. 마무리 ✅
업로드 정보(`output/업로드정보.txt`)·출처·썸네일을 표로 정리해 전한다. 채널 주인이 고친 취향은 메모리(`design-taste-2026-11`)에 더한다.

## 7. 실패할 때
- 단계가 오류로 멈추면 `work/log.txt` 끝과 `진단.md` 를 읽고 원인을 한 줄로 말한 뒤 고칠 방법을 묻는다.
- 품질 게이트가 렌더를 막으면(`output/품질게이트_중단.md`) 이유를 읽어 주고, 고칠지 `--force-render` 할지 묻는다.

## 8. 대본 생성기 ✍
아이디어·메모(파일 또는 글) → `python -m studio script --idea <…> [--minutes N]` → `output` 에 대본 초안. 감독이 읽고 채널 주인과 한 번 이상 고친 뒤 1절의 대본으로 쓴다. 훅·말투 기준은 `prompts/agents/scriptwriter.md`.
