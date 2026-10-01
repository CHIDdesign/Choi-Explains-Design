## 모션 DSL (MotionSpec) — 모션 디자이너가 쓰는 장면 설계 JSON

코드를 실행하지 않고 렌더러가 안전하게 애니메이션한다.
- 좌표: 장면 상자 기준 **퍼센트**(x 0~100 가로, y 0~100 세로). 요소의 중심 기준(anchor 로 left/right 가능).
- 시간: **장면 시작 기준 초**. 장면 길이는 4~12초.

```
{ "bg": "board|paper|ink|signal|transparent", "grid": false, "label": "괄호 라벨(짧게)", "elements": [ ... ] }
```

공통 필드:
- `at`: 등장 시각
- `dur`: 등장 애니메이션 초(기본 0.4)
- `out`: 퇴장 시각
- `x`, `y`
- `color`: fg | dim | faint | accent | bg | white | ink
- `enter`: fade | up | down | left | right | scale | mask | draw | pop | none
- `ease`: out | inOut | back
- `keys`: 이동 키프레임 `[{t, x?, y?, scale?, rotate?, opacity?}]`. 첫 상태는 요소의 x/y 가 자동으로 들어가며, 화면 안 이동은 자동으로 ease-in-out.

요소 타입:
- `text`: {text, size(장면 높이 대비 %, 제목 7~10 · 본문 4~5), weight, font: sans|display|serif|latin|heavy|round|hand(heavy=Black Han Sans 한 방 · round=Jua 둥근 메모체 · hand=손글씨 주석, 셋은 굵기 하나), maxWidth, align, highlight(강조할 단어), reveal: words|chars|lines|none}. 기본 등장은 마스크 리빌. 줄바꿈은 `\n`.
- `rect`: {w, h, radius, fill, stroke, strokeWidth}. enter:"draw" 면 외곽선이 그려진다.
- `circle`: {r(가로 대비 %), fill, stroke}
- `line` / `arrow`: {x2, y2, curve(-1~1 휘어짐), dashed, strokeWidth}. 기본 등장은 그리기.
- `path`: {d: 0~100 좌표계 SVG path, fill, stroke}
- `dots`: {count, cols, gap, r, highlight:[인덱스], groups:[4,4,4], groupAt:초, groupGap}. groupAt 에 점들이 무리로 다시 모인다(게슈탈트 근접성).
- `counter`: {from, to, prefix, suffix, decimals, size}. Anton 숫자가 카운트업.
- `bar`: {w, h, value(0~1), label}. 가로 막대가 차오른다.
- `image`: {src, w, h, radius, frame}
  - src: `"pixabay:vector:<영어 검색어>"`(투명 배경 오브젝트·아이콘) · `"pixabay:illustration:<검색어>"` · `"pixabay:photo:<검색어>"`
    → 앱이 Pixabay 에서 받아 파일로 바꾼다(못 구하면 그 요소만 빠진다). 이미 확보된 파일은 "images/…".
  - frame: `"torn"` = 찢어진 흰 액자(사진, 채널의 종이 콜라주 스타일) · `"cutout"` = 오려 붙인 듯 그림자만(투명 PNG) · `"none"`.

설계 규칙:
1. 한 장면 = 한 가지 생각. 요소 3~10개, 텍스트는 짧게(제목 14자 이내).
2. 말하는 순서대로 `at` 을 배치한다. 화자가 그 단어를 말하기 0.2초 전에 등장.
3. 강조색(accent)은 장면당 1~2곳. 나머지는 fg/dim.
4. 움직임이 곧 설명이어야 한다: 모이기(groups), 이동(keys), 그리기(draw), 차오르기(bar/counter).
5. 칠판(board) 위의 크림색 선이 기본 톤이다. 데이터는 ink, 선언은 signal.

예시(실제 렌더 검증됨)는 `prompts/examples/motion_examples.json` 에서 자동으로 아래에 붙는다.
