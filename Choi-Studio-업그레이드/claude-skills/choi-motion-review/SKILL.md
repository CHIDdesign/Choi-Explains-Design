---
name: choi-motion-review
description: Review the MOTION of a finished Choi Studio job (projects/<job>/) scene by scene - not the settled stills, the movement. Use when the user says the motion graphics look amateur, templated, empty, frozen, too small or badly timed; when asked to review or QA motion scenes or HTML cards of a rendered longform or short; or before changing motion tokens, the motion DSL or the motion-designer prompt based on a complaint. Reads the plan's motion specs and card HTML, runs the timing lint against real word timings, inspects frame strips (0.5 s, 15 %, 40 %, settle, event, pre-exit), and reports per-scene findings with concrete spec fixes. Read-only on the job folder.
---

# Choi Studio 모션 검수

완성된 작업의 **움직임**을 장면 단위로 검수한다. 영상 전체의 진단(길이·이미지 비율·음악)은 `choi-output-review` 가 한다. 이 스킬은 모션 장면과 카드만 본다.
안착한 스틸만 보고 판단하지 않는다 — 안착 프레임은 가장 좋은 순간이고, 결함은 그 앞과 뒤에 있다(`docs/upgrade/06c_모션_검수_파이프라인.md` 1장).

## 0. 대상

- 사용자가 폴더를 말하지 않았으면 `projects/` 에서 가장 최근 폴더를 쓴다.
- **작업 폴더는 읽기만 한다.** 스틸·표는 저장소의 `out/motion_review/<job>/` 이나 임시 폴더에 쓴다.
- 쓰는 파일: `output/부가자료/plan.json`(모션 스펙 · 카드 HTML · 아트 디렉터 기록), `render/props_long.json` · `props_short_*.json`(그래픽의 시작·끝, 단어 시각), `output/부가자료/검토시트_*.jpg`, `work/qa/r*/g*.jpg`(아트 디렉터가 본 스틸).

## 1. 린트를 돌린다(1분)

저장소 루트에서(앱의 가상환경 파이썬). 읽기 전용이고 결과는 표준 출력이다.

```bash
.venv/Scripts/python.exe .claude/skills/choi-motion-review/scripts/motion_lint.py "projects/<job>"
.venv/Scripts/python.exe .claude/skills/choi-motion-review/scripts/motion_lint.py "projects/<job>" --json > out/motion_review/lint.json
```

장면마다 `metrics`(외접 상자 · 잉크 · 0.5초 잉크 · 가장 큰 요소 · 가장 작은 글자 px)와 위반 목록이 나온다. 규칙 표는 `06c` 4장.
먼저 볼 것:

| 규칙 | 뜻 | 흔한 원인 |
|---|---|---|
| `L02_open_empty` · `L03_stage_late` · `L12_sparse_long` | 0.5초에 무대가 없다 | 말에만 맞춰 하나씩 옴. 자리 표시가 없음 |
| `L17_text_small` · `L19_ink_cover` · `L20_no_hero` | 작다 | `size` 4 미만, 점 `r` 1.6, 주인공 없음 |
| `L07_final_hold` · `L11_late_vs_speech` | 읽을 시간이 없다 · 화자가 지나갔다 | `at` 을 초로 추정함 |
| `L08_frozen_tail` · `L09_no_second_act` | 얼어 있다 · 사건이 없다 | 쌓기만 하는 장면. 숏폼이 롱폼 스펙을 더 길게 씀 |
| `L15_pop` · `L23_clipart` · `L22_accent` | 채널 톤 위반 | 예시를 따라 함 |

**숏폼은 따로 돌린다.** 숏폼 그래픽(`props_short_*.json` 의 `s1g…`)은 롱폼 스펙을 다른 길이로 쓴다. 스크립트는 롱폼만 읽으므로, 숏폼은 길이만 바꿔 `lint(spec, 숏폼 길이)` 를 직접 부른다(`choi-motion-scene` 3번의 조각).

## 2. 카드를 계산한다(5분)

카드(`plan.long.graphics[].card`)는 린트 스크립트가 아직 읽지 않는다. `html` 의 `data-anim`·`data-anim-at`·`data-anim-duration` 과 `css` 의 글자 크기로 표를 만든다.

| 볼 것 | 기준 |
|---|---|
| 가장 큰 글자(주인공)가 다 도착하는 시각 | ≤ 1.0초. 말에 맞춰 늦게 와야 하면 자리 표시가 있는가 |
| 0.5초 · 2.0초 시점에 떠 있는 글자의 양 | 0.5초에 35% 이상 |
| `fade-in` 의 비율 | 절반 이하 |
| 마지막 선언이 끝나는 시각 | 카드 길이 − `max(1.2, 글자 수 ÷ 7)` 이전 |
| 가장 작은 글자 | 본문 34px · 라벨 28px 이상(전면 카드) |
| `.root` 배경 | `--paper` 계열. `--white` · `--ink` 전면은 재질 위반(`06` 3장, 게이트 B9) |

## 3. 프레임 스트립을 본다

### 3-1. 이미 있는 것부터

- `검토시트_롱폼_NN.jpg`(2.5초 간격)에서 그 그래픽이 떠 있는 칸을 **전부** 본다. 그래픽의 시작·끝은 `props_long.json` 의 `graphics[].start/end`.
- `work/qa/r1/g*.jpg` 는 아트 디렉터가 본 안착 스틸이다. 최종 스펙과 다를 수 있다(수정 라운드 전).
- 숏폼 검토 시트에서는 같은 장면이 몇 칸 동안 그대로인지 센다(한 칸 = 2.5초).

### 3-2. 모자라면 여섯 프레임을 뽑는다

그래픽마다(시작 프레임 `F = round(start × 30)`, 길이 `D`):

```
F+15 · F+0.15D · F+0.40D · 마지막 요소 도착+2 · 사건의 가운데(없으면 F+0.70D) · F+D−12
```

```bash
cd renderer
npx remotion still src/index.ts LongForm ../out/motion_review/<job>/g25_f.png \
  --props="../projects/<job>/render/props_long.json" --public-dir="../projects/<job>/render/public_src" \
  --frame=<n> --scale=0.5 --overwrite
```

이 명령은 이 스킬을 쓸 때 **실행으로 확인하지 않았다**. 작업의 미디어 경로가 맞지 않아 실패하면 3-1 의 검토 시트로 판단하고, 보고서에 "스트립을 뽑지 못했다"고 적는다. 영상 전체를 렌더하지 않는다.

### 3-3. 프레임마다 묻는다

1. 지금 시청자의 눈은 어디에 있는가. 한 곳인가.
2. 이 칸에서 화자가 하는 말과 화면의 강조가 같은가.
3. 앞 칸과 비교해 새로 나타난 것이 둘 이상인가.
4. 세 칸(스트립) 또는 두 칸(검토 시트, 5초) 넘게 아무것도 안 바뀌는데 말은 계속되는가.
5. 폭 480px 로 줄였을 때 라벨이 읽히는가.
6. 그림은 실물인가 기호인가. 컬러 클립아트인가.

움직이는 중인 프레임의 흐림·잘림은 결함이 아니다. 빈 화면과 작은 글자가 결함이다.

## 4. 보고서

장면마다 한 블록. 지적에는 **근거(규칙 id 또는 프레임 시각) · 잰 값 · 고칠 값**을 붙인다. "더 크게"라고 쓰지 않는다.

```
### g25 고착 실험 도식 (09:33~09:46, 12.45초, 종이 챕터)
사건: 없음(쌓기만 함) — L09
| 지적 | 근거 | 잰 값 | 고칠 값 |
| 0.5초에 제목 하나 | L02, 검토시트 12 의 09:35.0 | 요소 1개, 잉크 21% | 두 그룹의 판을 at 0.3·0.6 에 먼저 세운다 |
| 글자가 작다 | L17 | 3.8% = 24px ×2, 4.0% = 26px | size 4.6 이상(상자 644) |
| 컬러 클립아트 | L23, 09:40.0 | 초록 로고 커피컵 | 주황 테두리 상자 + '예시' 글자, 또는 실험 자극 스케치 |
| pop 2개 | L15 | 컵, X | enter 를 scale / draw 로 |
대체안: prompts/examples/모션_예제_후보.md 의 fixation_two_groups(같은 구간, 린트 0건)
```

끝에 한 장 요약: 규칙 × 장면 표(✗/·), 그리고 **프롬프트·예시·렌더러 중 어디를 고쳐야 하는가**. 같은 규칙이 장면의 절반 넘게 걸리면 장면이 아니라 지시나 예시의 문제다.

규칙:

- 잰 것, 본 것, 추론한 것을 구분해 적는다. 프레임을 보지 못한 것은 "스펙에서 계산"이라고 적는다.
- 린트가 걸지 않은 것도 적는다(무엇이 원인이 **아닌지**가 다음 수정의 범위를 줄인다).
- 채널 톤을 넘는 처방(바운스, 휩, 플래시, 1.15배 넘는 펀치인)을 내지 않는다.
- 모션 토큰이나 DSL 을 바꾸자고 하기 전에, 그 문제가 오늘의 DSL 로 풀리는지 먼저 확인한다(`모션_예제_후보.md` 가 그 증거다).
