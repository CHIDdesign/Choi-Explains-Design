---
name: agentcompany
description: Choi Studio 의 AI 에이전트 회사 운영법 — 역할(총괄 감독·컷 총괄·편집 감독·숏폼 PD·카피·모션·심사·그림 고르기 …)마다 일의 무게와 적합도에 맞는 Claude 모델(Fable 5.1 / Opus 5.5 / Sonnet 5.5 / Haiku 4.5)과 사고 강도(effort)를 자동 배정하는 표(studio/agents/studio.py ROUTING)를 읽고 고치는 절차, 그리고 Claude Code 가 이 저장소에서 일할 때 서브에이전트(Agent 도구)에 모델을 나눠 쓰는 법. 에이전트를 새로 추가하거나, "이 역할은 더 싼/더 센 모델로", "사고 강도 자동", "토큰·한도가 너무 빨리 찬다", "컷/기획 품질이 모델 탓인가", "/agents", 모델 배정·effort·라우팅·비용을 말하면 반드시 이 스킬을 먼저 쓴다.
---

# 🏢 agentcompany — 일마다 맞는 모델과 사고 강도

Choi Studio 의 기획·편집·디자인은 Claude 에이전트 20여 명이 나눠 한다. 모두에게 같은 최상위 모델을 쓰면 구독 한도(5시간·7일 창)가 금방 차고,
모두에게 싼 모델을 쓰면 영상 전체를 좌우하는 판단(기획·컷)이 무너진다. 그래서 **결과에 대한 영향 × 판단의 난도**로 배정한다.

## 1. 지금의 배정(설정 `agent_routing="auto"`, 기본)

코드: `studio/agents/studio.py` `ROUTING` · `route()` · `Studio.call`. 설정 창 'AI 연결 › 배정' 에서 자동/전역 하나를 고른다.

| 등급 | 모델 · 강도 | 역할 | 이유 |
|---|---|---|---|
| S — 영상 전체를 좌우 | Fable 5.1 · xhigh | `director`(총괄 기획·트리트먼트·훅 구조) · `cut_editor`(발화마다 남김/뺌 — 컷 정확도) | 한 번 틀리면 뒤의 모든 단계가 그 위에 쌓인다. 한 작업에 한 번씩만 부른다 |
| A — 짓고 고르는 창작 판단 | Opus 5.5 · xhigh | `editor`(하이라이트·홀드·호흡) · `shorts`(바이럴 구간) · `copy`(제목·썸네일 문구) · `setpiece` · `motion` · `style_frame` | 시청 지속·클릭을 직접 만든다 |
| B — 조사·심사·수정 | Opus 5.5 · high | `research` · `stock`(자료 계획) · `timeline_review` · `art_director` · `card_critic` · `design_judge` · `card_revise` · `motion_revise` | 기준이 분명한 판단 — xhigh 의 추가 사고가 점수를 거의 바꾸지 않는다 |
| C — 반복·측정값 읽기 | Sonnet 5.5 · high/medium/low | `captions`·`music`(high) · `colorist`·`stock_pick`(medium) · `portrait_pick`(low) | 한 작업에 수십 번 부르거나 숫자를 보고 고르는 일 |
| — | Haiku 4.5 | 한도 확인(`probe_quota`)만 | 영상 품질에 닿는 판단에는 쓰지 않는다 |

**사고 강도 자동 조절**: 공통 자료(대본·전사·조사)가 `BIG_CTX`(15만 자, 대략 40분 넘는 녹화)보다 길면 한 단계 올린다(low→medium→high→xhigh).
`max` 는 자동으로 쓰지 않는다 — 느리고, 측정상 xhigh 대비 이득이 작다.

**우선순위**(높은 것이 이긴다): 설정 파일의 `agent_models`/`agent_effort` 역할별 덮어쓰기 → `ROUTING` → 설정의 전역 모델·강도 → `Agent.effort`.

**안전망**: 배정한 모델을 그 계정·CLI 버전이 못 쓰면(오류 문구에 'model') 전역 모델로 한 번 더 부른다(로그 `🏢 배정 모델 … 을 못 씀`).
Fable 을 못 쓰는 구독이어도 작업이 멈추지 않는다.

## 2. 배정을 바꿀 때

1. **증상부터 본다.** "컷이 이상하다"는 대개 모델이 아니라 입력·규칙·프롬프트 문제다 — 먼저 `choi-output-review` 로 작업 폴더를 진단한다.
   모델 탓이라고 말할 수 있는 신호: 같은 입력으로 상위 모델이 확실히 다른(나은) 결정을 낸다, 스키마는 맞는데 판단이 얕다(이유 칸이 초안 되풀이).
2. **실측을 본다.** `user/usage.json`(작업별 호출·토큰·API 환산 비용)과 로그의 `📊`·'캐시 읽기' 줄. 한 역할이 토큰 대부분을 쓰면 그 역할이 후보.
3. **한 칸씩 바꾼다.** `ROUTING` 의 한 줄만 바꾸고 🧪 디자인 벤치(`python -m studio rerender <작업폴더> --until design --replan`)나
   같은 작업의 재실행으로 전후를 비교한다. 여러 칸을 한꺼번에 바꾸면 무엇이 효과였는지 모른다.
4. 내리는 방향(Opus→Sonnet)은 **반복 호출 역할**부터, 올리는 방향은 **한 번 부르고 뒤가 그 위에 쌓이는 역할**부터.
5. `tests/test_routing.py` 의 기대값을 같이 고치고 `python -m pytest tests/test_routing.py -q`.

## 3. 새 에이전트를 추가할 때

`AGENTS` 에 `Agent(...)` 를 넣으면서 같은 커밋에서:
- `ROUTING` 에 등급을 정해 한 줄 — 위 표의 질문으로: "이 판단이 틀리면 뒤의 몇 단계가 망가지는가?"(많으면 S·A), "한 작업에 몇 번 부르는가?"(수십 번이면 C).
- 디자인을 짓거나 심사하면 `DESIGN_AGENTS`, 디자인 규칙이 필요 없으면 `LEAN_AGENTS`, 여러 번 부르면 `REPEATED_AGENTS`(CLAUDE.md 🪶 토큰 절).
- 이 표(1절)와 설정 창 힌트(`studio/gui/settings_dialog.py` '배정' 아래 문구)를 갱신한다.

## 4. Claude Code 가 이 저장소에서 일할 때(개발용 서브에이전트)

같은 원리를 개발 작업에도 쓴다 — Agent 도구의 `model` 로:
- 넓게 찾기·파일 위치 찾기·로그 훑기 → `Explore` 또는 `model: "haiku"`/`"sonnet"`(읽기만, 결론만 받는다).
- 웹 조사·깃허브 비교·문서 요약 → `general-purpose` + `"sonnet"`.
- 컷 로직(`studio/text/*`, `fidelity.py`, `breath.py`)·프롬프트 설계·디자인 판단 → 직접 하거나 `"opus"`. 이 부분은 싸게 위임하지 않는다.
- 독립 검토(내 판단에 묶이지 않은 눈) → 결론이 아니라 코드를 주고 `"opus"`.
진짜 claude CLI 를 부르는 E2E 는 금지(CLAUDE.md '확인' 절) — 배정 변경은 가짜 클라이언트 테스트로 확인한다.
