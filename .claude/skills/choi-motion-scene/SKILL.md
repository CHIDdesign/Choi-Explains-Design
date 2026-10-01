---
name: choi-motion-scene
description: Design, validate and preview a MotionSpec motion-graphics scene for Choi Studio (the design-theory channel's Remotion renderer). Use when the user wants a new concept animation (Gestalt principles, visual hierarchy, proportion, before/after, data, an experiment, a process) for a long-form or shorts video, wants to fix a motion scene the art director or the timing lint flagged, or wants to add a verified example to prompts/examples/motion_examples.json. Storyboard first (event, hero, reads timing sheet), then coordinates, then clean_spec + timing lint, then a still AND a frame strip.
---

# Choi Studio 모션 장면 설계

Choi Studio 의 🎨 모션 디자이너 에이전트가 쓰는 **MotionSpec(JSON)** 을 사람이나 Claude Code 가 직접 설계·검증·미리보기 하는 절차.
순서를 지킨다: **스토리보드 → 좌표 → 검증 → 스틸과 스트립 → (렌더로 확인한 것만) 예제 등록.** 좌표부터 쓰지 않는다.

## 0. 읽을 것

- 문법: `prompts/motion_dsl.md`(좌표는 장면 상자 기준 %, 시간은 장면 시작 기준 초)
- 모션 규칙: `prompts/skills/motion_craft.md`(없으면 `motion_principles.md`)
- 구성·크기·토큰: `docs/upgrade/06_모션_그래픽_v2.md` 4장 · 6장
- 검수 규칙: `docs/upgrade/06c_모션_검수_파이프라인.md` 4장(린트 26규칙)
- 레시피: `docs/upgrade/06d_애니메이션_레시피.md`
- 예제: `prompts/examples/motion_examples.json`(렌더 검증됨), `prompts/examples/모션_예제_후보.md`(검증 통과 · 렌더 전)

## 1. 스토리보드 — 좌표보다 먼저 쓴다

장면마다 아래 다섯 줄을 먼저 쓴다. 한 줄이라도 못 쓰면 그 장면은 아직 설계되지 않은 것이다.

```
사건(event):  첫 프레임과 끝 프레임 사이에 무엇이 바뀌는가. 한 문장.
              예: "B 그룹의 점들이 예시 상자 쪽으로 끌려가 뭉친다"
              "제목과 도형 셋이 차례로 나온다"는 사건이 아니다 → 키워드 카드로 내린다.
주인공(hero): 화면에서 가장 큰 요소 하나. 상자의 8% 이상.
무대(stage):  0.5초 안에 서 있어야 하는 것 — 제목 + 주인공 + 나중에 올 것의 자리 표시(흐린 윤곽 도형).
움직임(move): 크게 움직이는 것은 하나. 왜 그렇게 움직이는지 한 문장.
이음매(seam): 앞 그래픽에서 이어받는 것, 다음 그래픽으로 넘겨줄 것.
```

그다음 **reads 타이밍 표**를 쓴다. 시청자가 이해해야 할 것을 말의 순서대로 적는다.

| 초 | 그때 하는 말 | 화면에 오는 것 | 시청자가 읽어야 할 것 |
|---|---|---|---|
| 0.1~0.9 | (앞말) | 제목 + 빈 판 둘 | 두 집단을 비교한다 |
| 3.9~4.9 | 한 그룹에만 | A 머리글, 점 6개 | A 는 문제만 받았다 |
| … | | | |

표를 점검한다.

1. read 가 겹치지 않는가 — 글이 안착한 뒤 다음 글까지 `0.4 + 글자 수 ÷ 12`초.
2. 글자는 그 낱말이 나올 때 **도착**하는가(시작이 아니라 도착. 늦어도 0.5초 안).
3. 마지막 움직임 뒤 `max(1.2초, 글자 수 ÷ 7)` 가 남는가. 모자라면 글자를 줄인다.
4. 8초 넘는 장면인데 등장 말고 바뀌는 것이 없지 않은가.
5. 화면에 3초 넘게 요소가 둘 이하인 구간이 없는가.

단어 시각은 작업 폴더의 `render/props_long.json` → `captions[].lines[][]`(`start`, `end`, `text`)에 있다. 그래픽은 첫 낱말보다 약 0.45초 먼저 시작한다.

## 2. 좌표 쓰기 — 지킬 수치

| 무엇 | 값 |
|---|---|
| 채움 | 요소 전체의 외접 상자 ≥ 상자의 45%. 작은 요소를 넓게 흩어 놓지 않는다(잉크 면적 ≥ 16%) |
| 글자 | 제목 `size` 9~12, 본문 5~6, 라벨 4.5 이상. 최종 화면에서 본문 34px · 라벨 28px 이상 |
| 도형 | 점 `r` ≥ 3, 원 `r` ≥ 8, 주인공 이미지 `w` ≥ 30 |
| 첫 요소 | `at` ≤ 0.3. 0.5초 시점에 요소 2개 이상, 잉크 35% 이상 |
| 동시 등장 | 0.1초 안에 둘까지, 0.5초 안에 세 묶음까지 |
| 스태거 | 같은 종류 여럿이 말과 무관하게 차례로 올 때 합쳐서 0.5초 이하 |
| 강조색 | 한 곳. 제목 `highlight` 와 주황 요소를 같이 쓰지 않는다 |
| 쓰지 않는다 | `enter: "pop"` · `ease: "back"`(펀치 구간·숏폼 훅만) · `color: "faint"` 글자 · 컬러 클립아트(`pixabay:vector`·`illustration`·`cutout`) · `bar.label` |

오늘의 렌더러에서 알아 둘 것(코드에서 확인):

- **`keys` 는 `at` 에서 첫 키까지 서서히 보간한다.** 가만히 있다가 바뀌게 하려면 키를 둘 쓴다: `{"t": 4.4, "opacity": 1}`(여기까지 유지) + `{"t": 4.9, "opacity": 0.35}`(도착).
- **요소 배열의 순서가 겹침 순서**다(`at` 과 무관). 뒤에 깔릴 판은 배열 앞에, 그 위 글자는 뒤에.
- `bar` 는 `x` 에서 오른쪽으로 자란다(가운데 기준이 아니다). `bar.label` 은 막대 높이의 0.8배(최소 18px)로 그려져 너무 작다 — `text` 로 따로 적는다.
- `path`·`line` 의 `keys` 는 `x`·`y` 로 옮겨지지 않는다(불투명도·배율·회전만).
- 채운 `circle` 에 `enter: "draw"` 를 주면 채움이 먼저 보인다. `scale` 을 쓴다.
- `path` 의 채움을 서서히 보이려면 `enter: "fade"`, `stroke: "none"`.
- `reveal: "words"`(기본)는 띄어쓰기 단위 = 어절 단위 리빌이다. 음절 단위(`chars`)는 10음절 이하 제목에만.
- 자리 표시(`ghost`)는 아직 없다. 흐린 윤곽 도형(`stroke: "dim"`, 채움 없음 또는 `fill: "faint"`)을 먼저 세운다.

## 3. 검증 — 모양과 타이밍 둘 다

```bash
.venv/Scripts/python.exe - <<'PY'
import json, sys
sys.path.insert(0, ".claude/skills/choi-motion-review/scripts")
from studio.motion.spec import clean_spec
import motion_lint as L

DUR = 8.0                                             # 장면 길이(초)
raw = json.load(open("my_scene.json", encoding="utf-8"))
spec = clean_spec(raw, DUR)
assert spec, "clean_spec 실패: 허용 타입·색·범위를 벗어났다"
assert len(spec["elements"]) == len(raw["elements"]), "요소가 빠졌다"
for name, box in L.BOXES.items():                     # 종이 860x644 · 보드 1069x644 · 책상 1048x700
    for i in L.lint(spec, DUR, None, box):            # 단어 시각이 있으면 [(t0, t1, "낱말"), …] 을 넘긴다
        print(name, i.level, i.rule, i.msg, i.els)
print(L.metrics(spec, DUR))
PY
```

- `error` 가 하나라도 있으면 고친다. `warn` 은 이유를 댈 수 있을 때만 남긴다.
- 숏폼에도 쓸 장면이면 **숏폼 길이로 한 번 더** 돌린다(같은 장면이 더 길게 떠 있어 얼어붙는다).
- 린트는 근사다. 통과해도 4번을 건너뛰지 않는다.

## 4. 미리보기 — 스틸 한 장과 스트립 여섯 장

`renderer/src/samples.ts` 의 롱폼 샘플 그래픽에 `{"template": "motion", "layout": "split", "data": {"spec": …}}` 를 넣는다(전면으로 볼 때는 `"fullscreen"`).
그래픽 시작 프레임을 `F`, 길이를 `D` 프레임이라 할 때 여섯 프레임을 뽑는다.

```bash
cd renderer
for f in $((F+15)) $((F+D*15/100)) $((F+D*40/100)) <마지막 요소 도착+2> $((F+D*70/100)) $((F+D-12)); do
  npx remotion still src/index.ts LongForm out/scene_$f.png --frame=$f --overwrite
done
```

| 프레임 | 본다 |
|---|---|
| `F+15`(0.5초) | 무대가 섰는가. 제목 하나뿐이면 실패다 |
| 15% | 구도가 한쪽 구석에만 차 있지 않은가 |
| 40% | 지금 말하는 것과 화면의 강조가 같은가. 강조가 둘이 아닌가 |
| 도착 | 넘침, 겹침, 글자가 읽히는가(폭 480px 로 줄여서도 본다) |
| 70% 또는 사건의 가운데 | 사건이 실제로 보이는가 |
| `F+D−12` | 말이 끝나기 전에 사라지지 않는가 |

앞의 세 장은 움직이는 중일 수 있다. 흐림·잘림은 결함이 아니다. **비어 있는 것**이 결함이다.
도착 프레임만 보고 끝내지 않는다 — 이번 테스트 영상의 결함은 전부 도착 전과 도착 뒤에 있었다.

## 5. 예제로 등록

`prompts/examples/motion_examples.json` 에는 **렌더해서 눈으로 확인한 장면만** 넣는다(CLAUDE.md). 조건:

1. `clean_spec` 통과, 린트 `error` 0건(세 상자 모두).
2. 4번의 여섯 프레임을 직접 보고 문제없음.
3. 이미 있는 예제와 **구조가 다르다**(사건의 종류, 주인공, 구도 가운데 둘 이상). 같은 구조를 또 넣으면 에이전트가 그 구조만 되풀이한다.
4. 스펙과 함께 `event` 한 문장과 reads 표를 주석 문서(`prompts/examples/모션_예제_후보.md`)에 남긴다.

`모션_예제_후보.md` 의 10개는 1번까지만 끝난 후보다. 2번을 거친 것부터 옮긴다.
