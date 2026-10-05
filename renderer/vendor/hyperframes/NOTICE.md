# HyperFrames 에서 가져온 것

이 폴더는 HeyGen 의 오픈소스 **HyperFrames**(https://github.com/heygen-com/hyperframes, Apache License 2.0)의
카드 규약을 Choi Studio 의 Remotion 렌더러 안에서 쓰기 위해 옮겨 적고 고친 것이다.

가져온 것(원문은 `skills/talking-head-recut/SKILL.md` 와 `references/styles/*.html`, `packages/lint`):
- **카드 HTML 계약** — 루트 `<div class="card" data-card-id="…">`, 안쪽 `<style>` 은 그 선택자로 스코프, `<script>`·외부 URL·
  인라인 이벤트 금지, 애니메이션은 `data-anim-*` 선언만.
- **`data-anim` 종류와 GSAP 문장 표** — fade-in · fade-out · slide-in · kinetic-chars · typewriter · count-up · draw-path ·
  grow-x · grow-y · scale-pop · blur-in · mask-reveal · morph-to. `data-anim-at` 은 카드 시작 기준 초, 1/fps 로 양자화.
- **린트 규칙의 이름과 취지** — `font_family_without_font_face`, `gsap_infinite_repeat`, `gsap_css_transform_conflict`,
  `clip_ends_past_root_duration` 같은 검사 항목을 우리 `check`(`renderer/scripts/check.mjs`) 의 항목 이름으로 이어 썼다.
- 레퍼런스 스타일(editorial · academic · whiteboard · swiss · minimal)의 구성 원리를 채널 톤(크림 종이 · 잉크 · 주황 강조 ·
  Pretendard/명조)으로 옮겨 `prompts/examples/card_examples.json` 을 만들었다. 원문 HTML 은 넣지 않았다.

고친 것:
- 카드마다 타임라인을 따로 만들고 **Remotion 의 `useCurrentFrame()` 으로 `seek`** 한다(HyperFrames 는 컴포지션 하나의 마스터
  타임라인을 헤드리스 Chrome 이 재생). 그래서 `window.__timelines` 등록·`class="clip"`·`data-start` 는 쓰지 않는다.
- 모든 트윈에 `lazy:false`, `count-up` 은 콜백 대신 seek 뒤에 값을 직접 써서 프레임 순서와 무관하게 결정론적이다.
- 채널용 종류를 더했다: `highlight`(형광펜 채우기) · `stagger-in`(자식 순차 등장) · `pulse`(한 번 두근).
- 카드는 정해진 캔버스(예: 1920×1080)로 쓰고 렌더러가 상자에 맞춰 축소한다.

원저작권: Copyright HeyGen. Apache License 2.0 전문은 https://www.apache.org/licenses/LICENSE-2.0 에 있다.

## 덧붙임 — 카메라 문법(2026-10-04)

`card-anim.mjs` 의 한 세계 + 카메라(`[data-world]` · `data-camera`)는 Promptible 의 **remotion-motion-graphics-skill**
(https://github.com/Liamrjohnston/remotion-motion-graphics-skill, MIT License, Copyright (c) 2026 Promptible) `cinematic-camera`
스킬의 안무 문법(캔버스보다 큰 세계 하나 · 초점과 배율의 키프레임 · 열기 → 홀드 → 드러내기 → 이동 → 정지)을 옮겨 적은 것이다.
코드는 우리 것(GSAP 트윈으로 다시 씀)이고, 그 저장소의 코드·영상·로고는 넣지 않았다. 슬롭 거절 목록(`prompts/agents/motion.md` 0-4 ·
`card_critic.md`)도 같은 스킬의 `rejected-patterns.md`·`visual-critic.md` 를 이 채널 기준으로 다시 쓴 것이다.
