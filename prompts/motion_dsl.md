## 모션 DSL (MotionSpec) — 모션 디자이너가 쓰는 장면 설계 JSON

코드를 실행하지 않고 렌더러가 안전하게 애니메이션한다.
- 좌표: 장면 상자 기준 **퍼센트**(x 0~100 가로, y 0~100 세로). 요소의 중심 기준(anchor 로 left/right 가능).
- 시간: **장면 시작 기준 초**. 장면 길이는 4~16초(풀스크린 = 모션 그래픽만의 장면, 얼굴 없이 화면 전체).

```
{ "bg": "board|paper|ink|signal|transparent", "grid": false, "label": "괄호 라벨(짧게)", "hero": 2, "elements": [ ... ] }
```

공통 필드:
- `at`: 등장 시각
- `dur`: 등장 애니메이션 초(기본 0.4)
- `out`: 퇴장 시각
- `x`, `y`
- `color`: fg | dim | faint | accent | bg | white | ink
- `enter`: fade | up | down | left | right | scale | mask | draw | none | **place**(붙이기: 살짝 떠 있다가 회전·그림자가 정착 — 메모·사진·쪽지)
  | **unfold**(펼치기: 위 변을 축으로 열린다 — 접힌 메모·아래 띠) | **write**(손글씨처럼 왼→오, 4프레임 스텝 — 손 주석 글자). `pop` 은 펀치 구간·숏폼 훅에서만.
- `ease`: out | inOut | linear | **enterLarge**(큰 면) | **move**(화면 안 이동: 빨리 떠나 길게 앉는다) | **settle**(미세 정착). `back` 은 쓰지 않는다.
- `ghost`: true 면 0초부터 그 자리에 흐린 윤곽(0.22)으로 서 있다가 `at` 에 채워진다 — 나중에 말할 요소의 자리를 먼저 보여 준다(빈 화면 금지).
- `keys`: 이동 키프레임 `[{t, x?, y?, scale?, rotate?, opacity?}]`. 첫 상태는 요소의 x/y 가 자동으로 들어가며, 화면 안 이동은 자동으로 ease-in-out.

요소 타입:
- `text`: {text, size(장면 높이 대비 %, 제목 9~12 · 본문 5~6 · 라벨 4 이상 — 최종 화면 본문 34px · 라벨 28px 이상), weight, font: sans|display|serif|poster|italic|latin|heavy|round|hand(디자인 v3 종이 콜라주: display=고운바탕 700 명조 제목(기본) · serif=고운바탕 본문 명조 · poster=송명 포스터 명조(굵기 하나) · italic=Instrument Serif 이탤릭(영문·연도·숫자, 굵기 하나) · heavy=Black Han Sans 한 방 · round=도장 명조(고운바탕 700) · hand=손글씨 주석 — 한 장면에 세 가족까지, 고딕(sans)은 라벨·작은 본문만), maxWidth, align, highlight(강조할 단어), reveal: words|chars|lines|none}. 기본 등장은 마스크 리빌. 줄바꿈은 `\n`.
- `rect`: {w, h, radius, fill, stroke, strokeWidth}. enter:"draw" 면 외곽선이 그려진다.
- `circle`: {r(가로 대비 %), fill, stroke}
- `line` / `arrow`: {x2, y2, curve(-1~1 휘어짐), dashed, strokeWidth}. 기본 등장은 그리기.
- `path`: {d: 0~100 좌표계 SVG path, fill, stroke}
- `dots`: {count, cols, gap, r, highlight:[인덱스], groups:[4,4,4], groupAt:초, groupGap}. groupAt 에 점들이 무리로 다시 모인다(게슈탈트 근접성).
- `counter`: {from, to, prefix, suffix, decimals, size}. Anton 숫자가 카운트업.
- `bar`: {w, h, value(0~1), label}. 가로 막대가 차오른다.
- `image`: {src, w, h, radius, frame, tint}
  - src: `"pixabay:vector:<영어 검색어>"`(투명 배경 오브젝트·아이콘) · `"pixabay:illustration:<검색어>"` · `"pixabay:photo:<검색어>"`
    → 앱이 Pixabay 에서 받아 파일로 바꾼다(못 구하면 그 요소만 빠진다). 이미 확보된 파일은 "images/…".
  - frame: `"print"` = 종이 위에 붙인 프린트(얇은 종이 테두리 + 그림자 + 살짝 기운 각도 — 사진·문서의 기본) · `"torn"` = 찢어진 흰 액자(뜯은 메모에만)
    · `"cutout"` = 오려 붙인 듯 그림자만(투명 PNG) · `"none"`.
  - tint: `"ink"` = 잉크 단색(벡터·일러스트는 자동으로 ink — 컬러 클립아트 금지) · `"duotone"` = 잉크→종이 두 색 · `"none"`(실물 사진).
- **디자인 v4 모던 부품**(레퍼런스: 테크 설명 영상의 UI 모션 — 스스로 등장하므로 `enter` 는 쓰지 않는다, `at` 만):
  - `panel`: {title, rows: ["라벨|값", "라벨"], w(가로 %), size(행 글자 장면 높이 %, 기본 2.6), tilt(살짝 기운 3D), on(강조할 행 번호)} — 흰 둥근 카드 + 제목 줄 + 둥근 행(아이콘 · 라벨 · 값). 행마다 3f 간격으로 들어온다.
  - `chip`: {text, size, icon: check|dot|gear|none, fill: card|tint|accent} — '✓ 라벨' 알약(정착 곡선으로 튀어나옴). 확인·상태·태그.
  - `bubble`: {text, sub, size, tail: bottom|left|none, icon} — 말풍선(값 + 작은 설명 + 꼬리). 지도·그림 위의 수치·질문.
  - `device`: {kind: monitor|laptop|phone, w, src(화면 안 이미지) 또는 rows(화면 안 UI 행), title} — 기기 목업 안의 화면.
  - `iso`: {cols, rows, seed, road, opacity} — 흰 블록 도시 + 옅은 색 길(장면 전체 배경). 다른 요소보다 먼저(at 0).
- `mark`: {kind: circle | underline | arrow | bracket | strike, w, h, strokeWidth} — 손으로 친 주석. (x, y) 를 가운데로 한 w×h 상자(가리킬 요소의
  외곽)에 그려 넣는다. 기본 색은 강조색, 그리기로 등장. **강조는 색을 더 칠하는 게 아니라 mark 로** — 그 낱말을 말하는 순간에.

설계 규칙:
1. 한 장면 = 한 가지 생각. 요소 3~10개, 텍스트는 짧게(제목 14자 이내). 요소 전체가 상자의 45% 이상을 채운다.
1-1. 0.5초 안에 제목과 주 요소(또는 그 `ghost`)가 선다. 마지막 요소가 도착한 뒤 `max(1.2초, 마지막 글의 글자 수 ÷ 7)` 동안 멈춘다.
1-2. 크게 움직이는 것은 `hero` 하나. 같은 0.1초에 시작하는 요소는 둘까지. 진입 종류를 섞는다(면은 place, 글은 mask, 선은 draw).
1-3. **같은 시간에 보이는 글·숫자·패널·칩·말풍선·기기·사진은 서로 겹치지 않는다**(상자가 12% 넘게 겹치면 린트 L27 오류) — 자리를 나누거나 `out` 으로 먼저 보낸다. 글이 사진 위에 놓일 때만 예외.
2. 말하는 순서대로 `at` 을 배치한다. 화자가 그 단어를 말하기 0.2초 전에 등장.
3. 강조색(accent)은 장면당 1~2곳. 나머지는 fg/dim.
4. 움직임이 곧 설명이어야 한다: 모이기(groups), 이동(keys), 그리기(draw), 차오르기(bar/counter).
5. 무대는 둘뿐이다(디자인 v4): `bg: paper` = 밝은 무대(흰 + 옅은 디자인 색 번짐), `bg: ink` = 어두운 무대(차콜) — 데이터·한 방에만. 강조색(채널 오렌지)은 한 화면에 한 곳.

예시(실제 렌더 검증됨)는 `prompts/examples/motion_examples.json` 에서 자동으로 아래에 붙는다.
