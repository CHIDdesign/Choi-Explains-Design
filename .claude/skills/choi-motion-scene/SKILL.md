---
name: choi-motion-scene
description: Design, validate and preview a MotionSpec motion-graphics scene for Choi Studio (the design-theory channel's Remotion renderer). Use when the user wants a new concept animation (Gestalt principles, visual hierarchy, proportion, before/after, data) for a long-form or shorts video, wants to fix a motion scene the 🧐 art director flagged, or wants to add a verified example to prompts/examples/motion_examples.json.
---

# Choi Studio 모션 장면 설계

Choi Studio 의 🎨 모션 디자이너 에이전트가 쓰는 **MotionSpec(JSON)** 을 사람이나 Claude Code 가 직접 설계·검증·미리보기 하는 절차.

## 1. 문법과 원칙 읽기
- 문법: `prompts/motion_dsl.md` (좌표는 장면 상자 기준 %, 시간은 장면 시작 기준 초)
- 모션 원칙: `prompts/skills/motion_principles.md` (ease-out 등장 / 퇴장은 등장의 75% / stagger 토큰)
- 채널 톤: `prompts/style_guide.md`, `docs/디자인_시스템.md` (칠판 board 위 크림색 선, 강조색 한두 곳)
- 검증된 예제: `prompts/examples/motion_examples.json`

## 2. 설계
1. 한 장면 = 한 가지 생각. 움직임이 곧 설명이 되게(모이기 `dots.groups`, 이동 `keys`, 그리기 `enter:"draw"`, 차오르기 `bar`/`counter`).
2. 화자가 그 단어를 말하기 0.2초 전에 `at`.
3. 요소 3~10개, 제목 14자 이내, accent 는 1~2곳.

## 3. 검증(파이썬)
```bash
python - <<'PY'
import json
from studio.motion.spec import clean_spec
spec = json.load(open("my_scene.json", encoding="utf-8"))
out = clean_spec(spec, 8.0)   # 장면 길이(초)
print("OK" if out else "INVALID", len(out["elements"]) if out else "")
PY
```
`clean_spec` 이 `None` 이면 렌더되지 않는다(허용 타입·색·범위를 벗어남).

## 4. 미리보기(Remotion)
`renderer/src/samples.ts` 의 롱폼 샘플 그래픽에 `{"template": "motion", "layout": "fullscreen", "data": {"spec": …}}` 를 넣고:
```bash
cd renderer
npx remotion still src/index.ts LongForm out/scene.png --frame=<장면 시작 프레임 + 도착 시점>
```
모든 요소가 도착한 뒤의 프레임(정지 상태)을 본다. 움직이는 중간 프레임을 결함으로 판단하지 않는다.

## 5. 예제로 등록
렌더를 눈으로 확인한 장면만 `prompts/examples/motion_examples.json` 에 이름을 붙여 추가한다. 에이전트 시스템 프롬프트에 자동으로 들어간다.
