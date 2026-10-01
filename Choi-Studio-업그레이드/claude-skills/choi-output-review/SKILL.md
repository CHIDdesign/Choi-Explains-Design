---
name: choi-output-review
description: Review a finished Choi Studio job (projects/<job>/) like a senior editor and write an evidence-based diagnosis. Use when the user says an output video looks wrong, amateur, "AI-ish", has too few images, bad music, or asks to review/QA/diagnose a rendered longform or short, or before changing editing rules based on a complaint. Reads the edit report, log, plan, stock picks and the 2.5-second contact sheets, measures the audio mix, then maps each symptom to the code or prompt that caused it.
---

# Choi Studio 결과물 검수

완성된 작업 폴더(`projects/<날짜_제목>/`)를 **근거로** 진단한다. 느낌으로 말하지 않는다 — 모든 지적에 시각(MM:SS)과 출처 파일을 붙인다.
규칙을 고치기 전에 반드시 이 검수를 먼저 한다(증상이 편집 규칙이 아니라 버그·입력 문제일 때가 많다).

## 0. 대상 찾기
- 사용자가 폴더를 말하지 않았으면 `projects/` 에서 가장 최근 폴더를 쓴다.
- 읽기만 한다. 작업 폴더의 파일을 고치거나 지우지 않는다.

## 1. 숫자부터(2분)
`output/부가자료/편집리포트.md` 맨 아래 "자동 후반 작업" 줄과 `work/log.txt` 에서 다음을 뽑아 표로 만든다.

| 항목 | 정상 범위 | 어디서 |
|---|---|---|
| 원본 길이 → 롱폼 길이 | 단축률 15~45% | 리포트 첫머리 |
| 롱폼 길이 vs 감독 예상 길이 | 0.8~1.25배 | 팀 메모("최종 길이는 약 …") |
| 원본 개수·묶음 | — | `log.txt` "싱크 …" 줄, `work/sources.json` |
| 리테이크 제거 수 / 삭제 거절 수 | 거절이 10개 넘으면 의심 | 리포트 "대본 충실도" |
| `face_ratio` | 0.35~0.70 | 리포트 "롱폼: shots …" 줄 |
| `max_face_run` | ≤ 25초 | 같은 줄 |
| 그래픽 수와 종류별 개수 | 한 템플릿 ≤ 25% | 리포트 "그래픽" 표 |
| 실물 이미지(photo·broll) 화면 시간 | 본편의 ≥ 15% | 같은 표에서 합산 |
| 풀스크린 실물 이미지 횟수 | 챕터당 ≥ 1 | 같은 표(레이아웃 열) |
| 스톡 요청 → 탈락 → 확보 → 화면 | — | `work/진단.md`, `work/stock.json` |
| 배경음악 곡명·곡 수 | 롱폼 주제곡 1 + 변주 ≤ 2 | `log.txt` "🎚" 줄 |
| 효과음 수 / 분 | 펀치 구간 밖 ≤ 3 | 같은 줄 |
| 아트 디렉터 지적 중 `[high]` | 0 | 리포트 "아트 디렉터 검수" |

**먼저 볼 세 가지**(이 중 하나라도 걸리면 나머지 미학 논의는 뒤로 미룬다):
1. 롱폼 길이가 감독 예상의 1.5배 이상인가 → 같은 대본을 두 번 찍은 원본이 둘 다 들어갔을 가능성(`docs/upgrade/02_전체테이크_중복_처리_설계.md`).
2. 그래픽 표를 시간순으로 볼 때 1분 넘게 비는 구간이 있는가.
3. 아트 디렉터가 `action: none` 인 `[high]` 를 남겼는가.

## 2. 화면을 직접 본다(5분)
`output/부가자료/검토시트_롱폼_NN.jpg`(2.5초 간격 16칸)를 **전부** 읽는다. 숏폼도. 시트마다 한 줄씩 적는다:

- 얼굴만 / 얼굴+옆 그래픽 / 전면 그래픽 / 실물 이미지 — 칸 수
- 화면 재질(배경색·질감)이 몇 가지 나오는가
- 글자가 이 축소판에서 읽히는가(안 읽히면 폰에서도 안 읽힌다)
- 그래픽 상자 안의 빈 공간(상자의 절반 이상이 비면 기록)
- 화면에 내부 이름(`motion` `card` `keyword` `S12` `g7`)·검색어·연출 메모가 글자로 나오는가
- 사진·스톡이 말과 맞는가(라벨과 실제 이미지가 같은 대상인가)
- 같은 구조의 카드가 연달아 나오는가
- 색: 피부·벽에 얼룩, 원본끼리 톤 차이, 그래픽과 영상의 톤 차이

`색보정_전후.jpg`, `썸네일*.jpg` 도 본다.

## 3. 소리를 잰다(1분)
앱의 가상환경 파이썬으로 이 스킬의 스크립트를 돌린다(읽기 전용, 결과는 stdout JSON).

```bash
.venv/Scripts/python.exe .claude/skills/choi-output-review/scripts/audio_probe.py "projects/<job>"
```

| 값 | 뜻 | 기준 |
|---|---|---|
| `voice_minus_music_under_speech_db` | 말하는 동안 목소리 − (음악+효과음) | 16~24 dB |
| `pause_swell_db` | 쉬는 곳에서 음악이 올라오는 양 | 0~6 dB |
| `music_jumps_over_6db_per_min` | 음악 레벨이 1초 사이 6dB 넘게 뛰는 횟수 | ≤ 4 |
| `music_db_per_30s` | 30초 단위 음악 레벨 | 곡 교체 지점에서 4dB 넘게 차이 나면 기록 |

귀로 들어야 하는 것(장르·악기·어울림)은 잴 수 없다. 사용자가 `/watch` 스킬(Gemini 엔진)을 쓸 수 있으면 영상 파일을 그쪽으로 보내 음악 평가를 받는다. 못 쓰면 **곡명과 배포 페이지 분류**만 근거로 쓰고 "듣지 못했다"고 적는다.

## 4. 증상 → 원인 지도
증상마다 코드·프롬프트의 한 지점까지 내려간다. 자주 나오는 것:

| 증상 | 먼저 볼 곳 |
|---|---|
| 길이 2배 · 인사가 한가운데 | `studio/text/align.py _mark_retakes_by_script`(120초 창), `studio/pipeline.py` 삭제 거절, `studio/media/sources.py group_sources` |
| 긴 맨얼굴 구간 | 위 원인, 또는 감독 `beats` 가 그 구간을 비웠는지(`plan.json`) |
| 사진이 없다·틀리다 | `studio/broll/wikipedia.py lookup`(대표 이미지 1장), `stage_broll`(조용히 빼기), `prompts/agents/stock.md` |
| 스톡 라벨이 검색어 | `plan.json` 의 broll `title` ← `query_ko` |
| 화면에 `motion`·`card` 글자 | `renderer/src/design/surfaces.ts TEMPLATE_LABEL` |
| 음악이 안 어울림 | `studio/sound/library.py pick_bgm`(무드 태그 + 무작위), `assets/sound_manifest.json`, 숏폼 기본 무드 |
| 벽·피부 얼룩 | `studio/grade/auto.py skin_guard`·`skin_weight`(설치본이 최신인지 먼저 확인) |
| 설치본이 저장소보다 옛 버전 | 설치 폴더 파일 시각 vs `git log -1` |

## 5. 보고서
`docs/upgrade/00_테스트영상_진단.md` 의 형식을 그대로 따른다: 근거 표 → 심각한 순서의 절(무슨 일 · 화면 증상 · 코드 원인 · 해법 링크) → 한 장 요약 표(증상 → 원인 → 고칠 곳 → 우선순위).

규칙:
- 버그(P0)와 취향(P2)을 섞지 않는다. 버그가 있으면 미학 지적은 "버그를 고친 뒤 다시 본다"고 적는다.
- 사용자가 한 말("AI틱하다")을 그대로 받지 말고 **화면에서 무엇이 그렇게 보이게 하는지**로 바꿔 적는다.
- 잰 것, 본 것, 추론한 것을 구분한다.
- 편집 규칙(`PARAMS`)을 바꾸자고 하기 전에, 그 규칙이 **실제로 적용된 결과인지**(계획엔 있었는데 다른 이유로 빠졌는지) 확인한다.
