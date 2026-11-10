## 자유 HTML 카드 (cards) — 실물이 보여 줄 수 없는 메커니즘을 그리는 도구

HyperFrames talking-head 카드 규약을 따른다(스크립트 없음). 앱이 검사(`check`)하고 렌더러가 상자에 맞춰 붙인다.

### 카드 계약(어기면 카드가 통째로 빠진다)
```html
<div class="card" data-card-id="c-단면">
  <style>
    .root { width:100%; height:100%; position:relative; overflow:hidden; }
    .tag { position:absolute; left:140px; top:120px; padding:14px 26px; font:600 44px/1.2 var(--font-body); color:var(--ink); }
  </style>
  <div class="root" data-surface="parchment">
    <div class="tag" data-surface="memo" data-tape data-anim="blur-in" data-anim-at="0.1" data-anim-duration="0.3">반지하</div>
  </div>
</div>
```
- 루트는 `<div class="card" data-card-id="…">` 하나. 안에 `<style>` 하나와 `.root` 하나. 선택자는 앱이 그 카드로 스코프한다 — `.root`·`.tag` 처럼 짧게 쓴다.
- **금지**: `<script>` · `<iframe>` · `<video>` · 외부 URL(`src`·`href`·`url()`) · `on*` 이벤트 · `@import` · `@font-face` · `@keyframes` · `transition` · `animation` · `position:fixed` · CSS 그라디언트 · `backdrop-filter`(유리).
- **이미지**: 확보 목록에 있는 로컬 경로만(`<img src="images/…">`, `object-fit:cover`). 사진·도면·지도·문서가 있으면 카드의 바탕이다.
- 글꼴은 변수만(`var(--font-head)` · `var(--font-body)`). 글꼴 이름을 직접 쓰면 번들에 없는 것은 빠진다.
- 크기 상한: HTML·CSS 24KB, 요소 260개. 한 카드 = 한 메커니즘.
- 읽는 글자는 원형마다 예산이 있다(공백·`aria-hidden` 제외, 넘으면 `too_much_text`). `document_line` 과 `<blockquote>` 는 `<mark>` 안의 글자만 센다.

### 캔버스 — layout 별
| layout | 캔버스 | 쓰임 |
|---|---|---|
| `fullscreen` | 1920×1080 | 카드가 화면 전체. 기본 |
| `split` | 1080×792 | 화자 옆 패널. 비교할 때만 |
| `overlay` | 1728×810 | 얼굴 위 투명 층. `.root` 는 배경 없이, 아래 ⅓에 놓고 위는 비운다 |

### 토큰(CSS 변수) — 색은 이것만
| 변수 | 쓰임 |
|---|---|
| `--paper` | 밝은 도식 면 |
| `--board` · `--chalk` · `--chalk-dim` | 차콜 도식 면과 그 위 글자·선 |
| `--ink` · `--muted` | 밝은 면 위 글자·선 |
| `--band` | 짙은 숲색 띠(흰 글자) — 이름표의 판 |
| `--accent` | 지금 말하는 곳의 작은 표식·밑줄 |
| `--accent-soft` | 도면·사진 위 반투명 표시 상자, `<mark>` 형광 |
| `--white` | 흰 글자 |
| `--font-head` / `--font-body` | Pretendard 800 / 400~600 |
| `--font-quote` | 명조 — 인용·조문·제호에만 |
| `--font-pen` | 손글씨 — 메모지 위 짧은 글에만, 60px 이상 |
| `--lift-1` · `--lift-2` · `--lift-3` | `box-shadow` 값(접촉 + 넓은 그림자, 광원 위 왼쪽) |

### 재질 — 종이는 CSS 로 흉내 내지 않는다
요소에 속성을 달면 런타임이 실제 텍스처를 깐다(글자 아래 층). 배경 `url()`·그라디언트는 쓸 수 없다.
| 속성 | 뜻 |
|---|---|
| `data-surface="eggshell\|parchment\|graph\|memo\|kraft\|newsprint\|desk"` | 그 재질의 종이. 카드 전체를 덮는 요소는 바탕, 그보다 작으면 접촉 + 넓은 그림자로 들뜬 조각 |
| `data-torn="top right bottom left"` | 적은 변이 찢기고 흰 섬유 단면이 보인다(값이 없으면 bottom). 그림자가 `filter` 라서 이 요소에 `blur-in`·filter 트윈을 쓰지 않는다 |
| `data-tape` | 주황 마스킹 테이프가 위 가운데에 붙는다. 그 요소에 `overflow:hidden` 을 쓰지 않는다 |

흰 테두리 오림 그림 = `<div data-surface="memo" style="padding:12px"><img …></div>`. 기울임은 `transform:rotate(-1.4deg)`(±3° 안). 종이 조각에는 늘 내용이 있다.
그림자: `box-shadow`·`text-shadow`·`filter:drop-shadow` 는 어두운 무채색, 48px 안(`--lift-N` 을 먼저). 흐림: `filter:blur(…)` 24px 안 — 뒤 사진·초점 창 밖에. 정착한 글자에 걸리면 `text_blurred`. `filter` 는 blur·grayscale·saturate·brightness·contrast·sepia·drop-shadow 만.

### 크기(1920×1080 · split 은 ×0.75)
라벨 34~44px · 이름표 48~64px · 문서 본문 34~40px. 렌더 후 28px 아래는 `text_too_small`. **아래 170px 은 자막 자리** — fullscreen·overlay 카드에서 글자를 두지 않는다. 대비: 본문 4.5:1, 40px 이상 3:1(사진 위 글자는 종이 조각이나 어두운 상자 위에).

### `data-anim` 종류
| kind | 무엇 | 파라미터(`data-anim-…`) |
|---|---|---|
| `fade-in` | 등장 | `at`, `duration`(기본 0.5), `ease` |
| `blur-in` | 올라오며 페이드 + 흐림 → 선명 | `at`, `duration`(0.3) |
| `slide-in` | 밀려 들어옴 | `from=left\|right\|top\|bottom`, `distance`(px) |
| `split-words` / `split-lines` | 어절·줄이 마스크 안에서 올라옴 | `stagger` |
| `draw-svg` | SVG 선·도형 그리기(path·line·polyline·circle·rect) | `origin=start\|center\|end`, `stagger` |
| `follow-path` | 요소가 SVG 경로를 따라 이동 | `path="#id"` |
| `grow-x` / `grow-y` | 막대·룰 자라기 | `target-w` / `target-h`(px) |
| `mask-reveal` | 잘라내며 드러남 | `direction=left\|right\|top\|bottom` |
| `highlight` | 형광 채우기 | — |
| `count-up` | 숫자 세기 | `from`, `to`, `format=.0f\|.1f\|.2f\|,d`, `prefix`, `suffix` |

`ease`: `power2.out`(기본) · `power2.inOut` · `power3.out` · `expo.out` · `sine.inOut` · `none`. 되튀는 곡선은 런타임이 감속으로 바꾼다.

### 타이밍
- 표시는 말한 낱말에 착지한다: `data-at-word="낱말"`(전사본의 어절 그대로, 문서 순서 = 말하는 순서)을 쓰면 앱이 그 낱말 0.2초 전 시각으로 바꾼다.
- 낱말이 없는 요소는 `data-anim-at`(카드 시작 기준 초).
- 첫 0.5초에 바탕과 첫 표시가 서 있어야 한다(`anim_first_frame_empty`).
- 모든 등장·표시 이동은 카드 끝 1.0초 전에 끝난다(`anim_ends_too_late`). 정착하면 멈춘다. 나가는 움직임은 쓰지 않는다.
- 두 표시가 반투명하게 겹친 채 바뀌지 않는다 — 표시는 하나가 옮겨 간다.

### 스타일(`style`)
밝은 종이면 `editorial`, 어두운 책상이면 `board`. 그 밖의 값은 쓰지 않는다.

### 한 번 다가가기(`data-world` · `data-camera`) — 지도에서 그곳으로
`.root` 안에 `<div class="world" data-world data-camera='[{"t":0,"x":960,"y":540,"z":1},{"t":0.3,"x":960,"y":540,"z":1},{"t":1.3,"x":1240,"y":610,"z":1.9},{"t":6,"x":1240,"y":610,"z":1.9}]'>` — CSS 는 `position:absolute;left:0;top:0;width:1920px;height:1080px`. `t` 초 · `x`,`y` = 화면 가운데에 올 세계 좌표 · `z` 배율. 지도·도면에서 그 자리로 한 번 다가갈 때만. 표식·이름표는 세계 밖에 둔다.

### 렌더 전 검사 — 이 이름으로 수정 요청이 온다
`font_family_not_bundled` · `font_not_loaded` · `text_overflow` · `outside_canvas` · `text_in_caption_zone` · `too_much_text` · `text_too_small` · `text_overlap`(글자끼리 겹침) · `low_contrast` · `text_blurred` · `page_chrome`(구석의 작은 라벨, 자간 넓힌 대문자, 'n / m' 쪽번호) · `runtime_error` · `anim_unknown_kind` · `anim_ends_too_late` · `anim_first_frame_empty` · `camera_hold_empty`.
수정 라운드에서도 실패하면 그 카드는 빠지고 화자가 화면을 맡는다.

### 직접 쓰는 GSAP 타임라인(`timeline`)
표시 이동·겹치는 트윈은 코드로 쓴다. `timeline` 은 함수 본문 문자열이고 앱이 `fn(tl, q, gsap, ctx)` 로 부른다.
- `tl` — 일시정지된 타임라인. 모든 트윈은 `tl.to / tl.from / tl.fromTo / tl.set` 으로 여기에만(위치 인자 `0`, `0.4`, `"<"`, `"+=0.2"`).
- `q(selector)` — 카드 안 요소 배열. `ctx` — `{duration, fps, w, h}`.
- `gsap.splitText(target, {type:'words'|'lines', mask:'words'|'lines'})` → `{words, lines}`. 트윈 값 `drawSVG:'0% 100%'` · `motionPath:{path:q('#route')[0], align:q('#route')[0], alignOrigin:[0.5,0.5]}`. `gsap.utils`(interpolate·mapRange·clamp…)도 있다.
- 결정론: 콜백(onUpdate·onComplete…), `Date`·난수·타이머·`window`·`document`·네트워크·`eval`·`import`·`while` 은 금지. 6000자 이하.
- 카드 길이는 말의 길이로 정해진다 — 마지막 박자는 `Math.min(4.3, ctx.duration - 1.6)` 처럼 `ctx.duration` 기준으로.
```js
tl.fromTo(q('.mark'), {scaleX: 0}, {scaleX: 1, transformOrigin: '0 50%', duration: 0.4, ease: 'power2.out'}, 0.3);
tl.to(q('.mark'), {y: 200, duration: 0.5, ease: 'power2.inOut'}, Math.min(3.0, ctx.duration - 1.8));
tl.fromTo(q('.axis'), {drawSVG: '0% 0%'}, {drawSVG: '0% 100%', duration: 0.9, ease: 'power2.inOut'}, 0.1);
```

### 내야 하는 것(`cards[]`)
`start_seg`·`end_seg`·`start_word`(카드가 도착할 단어) · `layout` · `style` · `archetype` · `title`(로그용 한 줄) · `html` · `timeline`(없으면 "") · `why_not_evidence`(왜 실물 자료 대신 이 그림인가 한 문장) · `reason`.
