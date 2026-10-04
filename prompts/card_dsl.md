## 자유 HTML 카드 (cards) — 템플릿보다 더 '편집 디자인'다운 핵심 장면

챕터마다 **가장 중요한 개념 1~3곳**(영상 전체 그래픽의 40% 이하)은 템플릿·모션 DSL 대신 **HTML 카드**로 직접 디자인한다.
HyperFrames 의 talking-head 카드 규약을 따르며(스크립트 없음, 애니메이션은 `data-anim-*` 선언만), 앱이 검사(`check`)해서
렌더러가 안전하게 붙인다. 카드는 정해진 캔버스 크기로 쓰고 렌더러가 상자에 맞춰 축소한다.

### 카드 계약(어기면 카드가 통째로 빠진다)
```html
<div class="card" data-card-id="c-질문">
  <style>
    .card[data-card-id="c-질문"] .root { … }      /* 모든 규칙은 이 접두사로 시작 */
    .card[data-card-id="c-질문"] .title { … }
  </style>
  <div class="root">
    <span class="kicker" data-anim="fade-in" data-anim-at="0.1" data-anim-duration="0.4">오늘의 개념</span>
    <h2 class="title" data-anim="kinetic-chars" data-anim-at="0.35" data-anim-duration="0.5" data-anim-stagger="0.035">질문이 <span class="hl">먼저</span>다</h2>
  </div>
</div>
```
- 루트는 `<div class="card" data-card-id="…">` 하나. 안에 `<style>` 하나와 `.root` 하나(`.root { width:100%; height:100%; position:relative; overflow:hidden; }`).
- **금지**: `<script>` · `<iframe>` · `<video>` · 외부 URL(`src`·`href`·`url()`) · `on*` 이벤트 · `@import` · `@font-face` · `@keyframes` ·
  `transition` · `animation` · `position:fixed`. 이미지는 앱이 준 로컬 경로(`images/…`)만.
- 글꼴은 **변수만** 쓴다(`var(--font-head)` …). 글꼴 이름을 직접 쓰면 번들에 없는 것은 본문 글꼴로 바뀐다.
- 크기 상한: HTML 24KB · CSS 24KB · 요소 260개. 한 카드 = 한 생각, 글자 수 60자 이내(🛠 시그니처 장면의 UI 재현은 화면 속 글자를 빼고 셈).

### 캔버스(px) — layout 별
| layout | 캔버스 | 쓰임 |
|---|---|---|
| `fullscreen` | 1920×1080 | 카드가 화면 전체(배경 포함). 얼굴은 잠시 사라진다 |
| `split` | 1080×792 | 화자 옆 패널 안. 배경은 칠판(`--board`)이나 종이(`--paper`) |
| `overlay` | 1728×810 | 얼굴 위 투명 층. `.root` 는 배경 없이, 카드 요소를 아래 ⅓에 놓고 위는 비운다 |

### 채널 토큰(CSS 변수) — 색은 이것만
| 변수 | 값 | 쓰임 |
|---|---|---|
| `--paper` `--bg` | 밝은 무대(흰 #F7F8F6) | 카드 배경(overlay 는 배경 없음) · 흰 둥근 카드는 `--white` |
| `--paper-line` | 옅은 회갈색 선 | 괘선·테두리 |
| `--ink` `--ink-soft` | 잉크 검정 | 제목·본문 |
| `--muted` | 회색 잉크 | 보조문·주석 |
| `--accent` `--accent-deep` `--accent-light` `--accent-soft` | 채널 강조색(기본 숲 초록 — 고급 설정 '디자인 색')·진한·밝은·반투명 | **카드당 1~2곳**. 밝은 배경(종이·흰색) 위 **글자**는 `--accent-deep`(밝은 강조색 글자는 대비 검사에 걸린다), 룰·블록·형광펜은 `--accent`/`--accent-soft`, 칠판 위 글자는 `--accent-light` |
| `--board` `--board-edge` `--chalk` `--chalk-dim` | 칠판 짙은 배경·크림 분필 | `board` 스타일·split 패널 |
| `--white` | 흰색 | 흰 상자 |
| `--font-head` | Pretendard 800(자간 −0.035em) | 제목·큰 글자(디자인 v4 — 굵고 자간 좁은 산세리프) |
| `--font-body` | Pretendard(400~600) | 본문·라벨 |
| `--font-serif` | Pretendard 500 | **문장**: 인용·주장·본문(명조는 쓰지 않는다 — 강조 한 어절만 `--font-italic`) |
| `--font-editorial` | Pretendard 800 | 전면 카드 헤드라인(100~150px) |
| `--font-poster` | Pretendard 900 | 한 방(짧은 낱말 120px 이상) |
| `--font-italic` | Instrument Serif 이탤릭 | 영문 원어·인용 출처·작은 킥커(32px 이상) |
| `--font-latin` | Anton | 좁은 고딕 숫자(표·데이터). 연도·큰 숫자는 `--font-numeral` 이 기본 |
| `--font-heavy` | Black Han Sans(굵기 하나) | **한 방**: 1~4어절 90px 이상의 선언·키워드 |
| `--font-round` | Jua(둥근 메모체, 굵기 하나) | 메모처럼 붙인 2~8어절 40~70px, 반전 상자 문구 |
| `--font-numeral` | Playfair Display italic 400·700·900 | **연도·큰 숫자**(레퍼런스의 '1853' — 900 italic, 140px 이상)·본문 옆 작은 연도 |
| `--font-hand` | Nanum Pen Script(손글씨) | 종이 위 주석·각주, **26px 이상만** |
| `--font-mono` | 고정폭 | 시간·메타 |

서체는 카드당 **세 가족까지**(docs/롱폼_무대_디자인.md 6장 역할표).
- 한국어 줄바꿈은 앱이 어절 단위(`word-break: keep-all`)로 맞춘다 — 줄을 직접 나누려면 `<br>` 이나 블록.
- `--accent-deep` 글자는 **40px 이상만**(밝은 무대 위 대비 4.08:1 — 작은 글자는 검사에 걸린다). 작은 강조는 잉크 글자 + 오렌지 밑줄.
- 뒤에 크게 깔린 장식 글자(연도·워터마크)는 `aria-hidden="true"` — 대비 검사에서 빠진다. 읽어야 하는 글에는 쓰지 않는다.

### 타이포 크기(1920×1080 기준 · split 은 ×0.75)
제목 96–132px · 본문 32–40px · 라벨/킥커 26–30px · 큰 숫자 160–240px(`--font-head` 900, 구두점만 강조색) · 인용 32–40px(강조 한 어절만 이탤릭 세리프).
**최소 26px**. 한 줄 22자 이내, 본문 두 줄 이내. 여백은 캔버스의 6~8%(fullscreen 은 padding 100~140px).
**아래 170px 은 자막 자리** — fullscreen·overlay 카드에서는 그 안에 글자를 두지 않는다(자막이 위에 얹힌다). 장식·점·룰은 괜찮다.

### `data-anim` 종류(닫힌 목록 — 이 밖의 값은 무시된다)
| kind | 무엇 | 파라미터(`data-anim-…`) |
|---|---|---|
| `fade-in` / `fade-out` | 등장/퇴장 | `at`, `duration`(기본 0.5), `ease` |
| `slide-in` | 밀려 들어옴 | `from=left\|right\|top\|bottom`, `distance`(px, 기본 80) |
| `kinetic-chars` | 글자마다 팝(제목) | `stagger`(기본 0.04), `pattern=pop\|fade` — 앱이 글자를 `.char` 로 나눈다 |
| `typewriter` | 글자마다 나타남 | `stagger`(기본 0.06) |
| `count-up` | 숫자 세기 | `from`, `to`, `format=.0f\|.1f\|.2f\|,d`, `prefix`, `suffix` |
| `draw-path` | SVG 선 그리기 | 요소가 `<path>` 또는 path 를 가진 `<svg>` |
| `grow-x` / `grow-y` | 막대·룰 자라기 | `target-w` / `target-h`(px) |
| `scale-pop` | 튀어나옴 | — |
| `blur-in` | 흐림→선명 | — |
| `mask-reveal` | 잘라내며 드러남 | `direction=left\|right\|top\|bottom` |
| `morph-to` | 아무 CSS 로 트윈 | `props='{"x":40,"opacity":0.5}'`(x y scale rotate opacity width height color backgroundColor letterSpacing borderRadius 만) |
| `highlight` | 형광펜 채우기(핵심어) | — (강조색 반투명이 왼쪽에서 채워진다) |
| `stagger-in` | 자식 순서대로 등장(목록) | `stagger`(기본 0.09) |
| `pulse` | 한 번 두근 | `scale`(기본 1.05) |
| `split-words` | **어절이 마스크 안에서 아래로부터 올라옴**(쇼릴 제목의 기본 — Jitter 'sliding text reveal') | `stagger`(기본 0.06), `duration` 0.6~0.8, ease 기본 `expo.out` |
| `split-lines` | 줄 단위로 마스크 안에서 올라옴(본문·인용 두세 줄) | `stagger`(기본 0.1) |
| `split-chars` | 글자 단위로 올라옴(짧은 한 방 낱말·숫자) | `stagger`(기본 0.025) |
| `draw-svg` | SVG 선·도형이 그려짐(DrawSVG — path·line·polyline·circle·rect 모두) | `origin=start\|center\|end`(가운데서 양쪽으로 = center), `stagger`(여러 선) |
| `morph-svg` | 한 `<path>` 가 다른 path 모양으로 바뀜(MorphSVG — 원 → 사각, 스케치 → 완성) | `target="#id"`(카드 안 다른 path, `fill="none" stroke="none"` 로 숨겨 둔다) |
| `follow-path` | 요소가 SVG 경로를 따라 이동(MotionPath — 과정·여정·흐름) | `path="#id"`(카드 안 path) |

`ease`: `power2.out`(기본) · `power2.inOut` · `power3.out` · `expo.out` · `back.out(1.6)` · `sine.inOut` · `none`.

### 타이밍 규칙
- `data-anim-at` 은 **카드 시작 기준 초**. 말하는 순서대로, 화자가 그 말을 하기 0.2초 전에 도착. 등장 0.35~0.6초.
- 모든 애니메이션은 **카드 길이 − 1.2초** 안에 끝난다(마지막 1.2초는 정지 — 읽는 시간). 카드 자체의 등장·퇴장은 렌더러가 한다.
- 한 카드에 애니메이션 3~8개. 같은 순간에 두 개 이상 튀지 않게(0.15초 이상 간격).

### 스타일(`style`) — 채널 톤으로 옮긴 5가지 + 칠판
| style | 인상 | 배경 | 글꼴 | 강조 |
|---|---|---|---|---|
| `editorial` | 잡지 표지 — 큰 제목, 굵은 룰, 한 낱말만 강조색 | `--paper` | 제목 `--font-head` 900 · 인용 `--font-serif` | 강조색 블록·룰 |
| `academic` | 노트 — 옅은 격자, 밑줄 강조 | `--paper` + 격자(`repeating-linear-gradient`) | `--font-head` 700 제목 | 형광펜 `highlight`(옅은 강조색) |
| `whiteboard` | UI 패널 — 흰 둥근 카드(반경 28·부드러운 그림자) + 둥근 행(아이콘·라벨·값) | `--white` 카드, 행은 `--paper` | `--font-head` 800 | 강조색 칩·체크 |
| `swiss` | 스위스 그리드 — 굵은 산세리프, 위아래 굵은 룰(`grow-x`), 큰 숫자 | `--paper` | `--font-head` 900 · 숫자도 `--font-head` 900 | 룰·구두점만 강조색 |
| `minimal` | 잉크 — 따뜻한 잉크 바탕, 종이색 큰 글자 하나 | `--ink`(따뜻한 잉크 — 순흑 없음) | `--font-head` 900 | 흰색(강조색 최소) |
| `board` | 칠판 — 채널 도식 톤(짙은 배경, 크림 분필, 손으로 긋는 선) | `--board` | `--chalk` 색 `--font-body` | `--accent-light` |

콘텐츠 종류가 아니라 **톤**으로 고른다: 선언·인용은 editorial, 정의·원리는 academic, 과정·스케치는 whiteboard, 숫자·비교는 swiss,
한 문장 한 방은 minimal, 도식은 board.

### 렌더 전 검사(check) — 이 이름으로 수정 요청이 온다
`font_family_not_bundled` · `font_not_loaded` · `text_overflow`(글이 상자·캔버스를 넘침) · `outside_canvas` · `text_in_caption_zone`(아래 170px 안의 글자) ·
`text_too_small`(28px 미만 — 라벨·출처도 28px 이상, 본문 34px 이상을 권한다) · `low_contrast`(글자와 배경 대비 4.5:1 미만, 40px 이상은 3:1) · `runtime_error` · `anim_unknown_kind` · `anim_ends_too_late` ·
`anim_first_frame_empty`(시작 0.5초 프레임이 완성 프레임의 35%보다 비어 있음 — 제목과 주 요소는 0~0.3초에 세우고, 말에 맞춰 오는 것은 강조·숫자·마지막 한 줄만). 수정 라운드에서도 실패하면 그 카드는 템플릿(keyword/definition)으로 대체된다.
`scale-pop` 은 펀치 구간의 한 방에만 — 롱폼 본문 카드의 등장은 `fade-in`·`slide-in`·`kinetic-chars`·`draw-path` 로.

### 7. 직접 쓰는 GSAP 타임라인(`timeline`) — 디자인 v4, 쇼릴 수준의 움직임
`data-anim` 선언으로 모자라면(겹치는 트윈, 어절·글자 단위 안무, 경로·스케일·회전의 조합, 하위 타임라인) **GSAP 코드를 직접 쓴다.**
`timeline` 은 함수 본문 문자열이고 앱이 `fn(tl, q, gsap, ctx)` 로 부른다:
- `tl` — 이 카드의 **일시정지된** 타임라인. 모든 트윈은 `tl.to / tl.from / tl.fromTo / tl.set / tl.add` 로 여기에만 얹는다(위치 인자 `0`, `0.4`, `"<"`, `"+=0.2"` 로 겹침·순서).
- `q(selector)` — 카드 안 요소 배열(`q('.word')`, `q('.row')[2]`). `gsap.utils`(interpolate·mapRange·clamp·snap·distribute…)·`gsap.parseEase`·`gsap.timeline(vars)`(부모 `tl` 에 자동으로 붙는 하위 타임라인)만 있다.
- `ctx` — `{duration, fps, w, h}`(카드 길이·캔버스).
- **플러그인**(GSAP 3.13+ 무료 — 렌더와 검사에 등록돼 있다):
  - `gsap.splitText(target, {type: 'words'|'lines'|'chars'|'words,chars', mask: 'words'|'lines'|'chars'})` → `{words, lines, chars}`
    (target 은 선택자 문자열이나 `q()` 결과). 마스크를 주면 각 조각이 넘침 감춤 상자에 들어가 `yPercent: 110 → 0` 으로 '올라온다'.
  - `gsap.customEase('M0,0 C0.12,0.9 0.2,1 1,1')` → ease 이름(트윈의 `ease` 에). 이 채널 기본 곡선은 위 값(빠르게 출발해 길게 안착).
  - 트윈 값: `drawSVG: '0% 100%'`(선 그리기, `'50% 50%'` 에서 시작하면 가운데서 양쪽으로) · `morphSVG: q('#target')[0]` ·
    `motionPath: {path: q('#route')[0], align: q('#route')[0], alignOrigin: [0.5, 0.5], start: 0, end: 1}`.
- 결정론: 값은 `seek(t)` 로만 정해진다. **금지**: 콜백(onUpdate·onComplete…), `Date`·난수·타이머·`window`·`document`·네트워크·`eval`·`import`·`while`. 6000자 이하. 쓰면 카드가 거절된다.
- 길이: 마지막 1초는 멈춰 보여야 한다(`anim_ends_too_late` — 검사가 카드 끝 −1.0초와 끝의 화면을 비교한다). 머무는 동안의 느린 흐름(16px 이하 이동 · 긴 변의 4% 이하 크기 변화 · 1~2° 회전)은 끝까지 이어져도 된다 — 등장·강조·선 그리기·불투명도 변화는 `ctx.duration - 1.0` 전에 끝낸다. 카드 길이는 말의 길이로 정해져 짧을 수 있으니 마지막 박자는 `Math.min(4.3, ctx.duration - 1.6)` 처럼 `ctx.duration` 기준으로 둔다. 0.3초 안에 판·제목이 서 있어야 한다(`anim_first_frame_empty`).
- `data-anim` 과 같이 써도 된다(선언이 먼저 붙고, 코드가 그 뒤에 얹힌다). 숫자 카운트업은 `data-anim="count-up"` 으로.
예(플러그인):
```js
const head = gsap.splitText('.headline', {type: 'words', mask: 'words'});
const glide = gsap.customEase('M0,0 C0.12,0.9 0.2,1 1,1');
tl.from(head.words, {yPercent: 110, duration: 0.75, ease: glide, stagger: 0.06}, 0.1);
tl.fromTo(q('.diagram path'), {drawSVG: '50% 50%'}, {drawSVG: '0% 100%', duration: 1.1, ease: 'power2.inOut', stagger: 0.12}, 0.5);
tl.to(q('#sketch')[0], {morphSVG: q('#final')[0], duration: 0.8, ease: 'power2.inOut'}, 2.0);
```
예(기본):
```js
const words = q('.headline .w');
tl.set(words, {opacity: 0, yPercent: 110});
tl.to(words, {opacity: 1, yPercent: 0, duration: 0.55, ease: 'expo.out', stagger: 0.06}, 0.1);
tl.fromTo(q('.panel'), {y: 40, opacity: 0}, {y: 0, opacity: 1, duration: 0.6, ease: 'power3.out'}, 0.35);
tl.fromTo(q('.row'), {x: -24, opacity: 0}, {x: 0, opacity: 1, duration: 0.45, ease: 'power2.out', stagger: 0.08}, 0.7);
tl.fromTo(q('.chip'), {scale: 0.8, opacity: 0}, {scale: 1, opacity: 1, duration: 0.5, ease: 'back.out(1.4)'}, 1.4);
tl.to(q('.bubble'), {y: -6, duration: 1.2, ease: 'sine.inOut', yoyo: true, repeat: 1}, 2.0);
```

### 내야 하는 것(`cards[]`)
`start_seg`·`end_seg`·`start_word`(카드가 도착할 단어) · `layout` · `style` · `title`(로그·검수용 한 줄) · `html`(위 계약대로 카드 조각 전체) · `timeline`(직접 쓴 GSAP 코드, 없으면 "") · `reason`.
