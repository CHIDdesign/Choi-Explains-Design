## 모션 DSL (MotionSpec) — 모션 디자이너가 쓰는 장면 설계 JSON

코드를 실행하지 않고 렌더러가 안전하게 애니메이션한다.
- 좌표: 장면 상자 기준 **퍼센트**(x 0~100 가로, y 0~100 세로). 요소의 중심 기준(anchor 로 left/right 가능).
- 시간: **장면 시작 기준 초**. 장면 길이는 4~14초.

```
{ "bg": "board|paper|ink|signal|transparent", "grid": false, "label": "괄호 라벨(짧게)", "hero": 2, "elements": [ ... ] }
```

공통 필드:
- `at`: 등장 시각
- `at_word`: 말에 맞춰 도착할 어절(전사본의 어절 그대로, `at` 순서 = 말하는 순서). 앱이 그 낱말 0.2초 전에 다 도착하도록 `at` 을 바꾸고 `out`·`keys` 도 같이 민다(못 찾으면 쓴 `at` 그대로). 표시(`mark`)와 말에 묶인 요소에는 늘 쓴다. `at` 은 대강이어도 된다.
- `dur`: 등장 애니메이션 초(기본 0.4)
- `out`: 퇴장 시각
- `x`, `y`
- `color`: fg | dim | faint | accent | bg | white | ink
- `enter`: fade | up | down | left | right | scale | mask | draw | none.
- `ease`: out | inOut | linear | **enterLarge**(큰 면) | **move**(화면 안 이동: 빨리 떠나 길게 앉는다) | **settle**(미세 정착). `back` 은 쓰지 않는다.
- `ghost`: true 면 0초부터 그 자리에 흐린 윤곽(0.22)으로 서 있다가 `at` 에 채워진다 — 나중에 말할 요소의 자리를 먼저 보여 준다(빈 화면 금지).
- `keys`: 이동 키프레임 `[{t, x?, y?, scale?, rotate?, opacity?}]`. 첫 상태는 요소의 x/y 가 자동으로 들어가며, 화면 안 이동은 자동으로 ease-in-out.

요소 타입:
- `text`: {text, size(장면 높이 대비 %, 제목 9~12 · 본문 5~6 · 라벨 4 이상 — 최종 화면 본문 34px · 라벨 28px 이상), weight, font: sans|display|serif|poster|italic|latin|heavy|round|hand(sans 를 쓴다), maxWidth, align, highlight(강조할 단어), reveal: words|chars|lines|none}. 기본 등장은 마스크 리빌. 줄바꿈은 `\n`.
- `rect`: {w, h, radius, fill, stroke, strokeWidth}. enter:"draw" 면 외곽선이 그려진다.
- `circle`: {r(가로 대비 %), fill, stroke}
- `line` / `arrow`: {x2, y2, curve(-1~1 휘어짐), dashed, strokeWidth}. 기본 등장은 그리기.
- `path`: {d: 0~100 좌표계 SVG path, fill, stroke}
- `dots`: {count, cols, gap, r, highlight:[인덱스], groups:[4,4,4], groupAt:초, groupGap}. groupAt 에 점들이 무리로 다시 모인다(게슈탈트 근접성).
- `counter`: {from, to, prefix, suffix, decimals, size}. 숫자가 카운트업.
- `bar`: {w, h, value(0~1), label}. 가로 막대가 차오른다.
- `image`: {src, w, h, radius, frame, tint}
  - src: `"pixabay:vector:<영어 검색어>"`(투명 배경 오브젝트·아이콘) · `"pixabay:illustration:<검색어>"` · `"pixabay:photo:<검색어>"`
    → 앱이 Pixabay 에서 받아 파일로 바꾼다(못 구하면 그 요소만 빠진다). 이미 확보된 파일은 "images/…".
  - tint: `"ink"` = 잉크 단색(벡터·일러스트는 자동으로 ink — 컬러 클립아트 금지) · `"duotone"` = 잉크→종이 두 색 · `"none"`(실물 사진).
- `mark`: {kind: circle | underline | arrow | bracket | strike, w, h, strokeWidth} — 손으로 친 주석. (x, y) 를 가운데로 한 w×h 상자(가리킬 요소의
  외곽)에 그려 넣는다. 기본 색은 강조색, 그리기로 등장. **강조는 색을 더 칠하는 게 아니라 mark 로** — 그 낱말을 말하는 순간에.

설계 규칙:
1. 한 장면 = 한 가지 생각. 요소 3~10개, 텍스트는 짧게(제목 14자 이내). 요소 전체가 상자의 45% 이상을 채운다.
1-1. 0.5초 안에 제목과 주 요소(또는 그 `ghost`)가 선다. 마지막 요소가 도착한 뒤 `max(1.2초, 마지막 글의 글자 수 ÷ 7)` 동안 멈춘다.
1-2. 크게 움직이는 것은 `hero` 하나. 같은 0.1초에 시작하는 요소는 둘까지. 진입 종류를 섞는다(면은 place, 글은 mask, 선은 draw).
1-3. **같은 시간에 보이는 글·숫자·사진은 서로 겹치지 않는다**(린트 L27) — 자리를 나누거나 `out` 으로 먼저 보낸다.
2. 말하는 순서대로 `at` 을 배치하고, 말에 묶인 요소에는 `at_word` 를 단다. 화자가 그 단어를 말하기 0.2초 전에 도착.
3. 강조색(accent)은 작은 표식 한 곳. 나머지는 fg/dim.
4. 움직임이 곧 설명이어야 한다: 모이기(groups), 이동(keys), 그리기(draw), 차오르기(bar/counter).
5. 면은 둘뿐이다: `bg: paper` = 평면 밝은 면, `bg: ink` = 차콜.

예시(실제 렌더 검증됨)는 `prompts/examples/motion_examples.json` 에서 자동으로 아래에 붙는다.

- **자막 자리**: 전면 무대의 아래 10%(y 가 커서 글자 아래 끝이 90% 를 넘는 자리)에는 글·숫자를 두지 않는다(린트 L28). 마지막 줄 글은 y ≤ 87.
