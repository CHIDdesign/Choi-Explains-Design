# 저장소 `CLAUDE.md` 에 더할 내용

Claude Code 가 이 저장소에서 일할 때 읽는 개발 메모(`CLAUDE.md`)에 붙일 블록이다. `## 규칙` 절 끝과 `## 확인` 절에 각각 더한다.
(업그레이드 문서를 `docs/upgrade/` 로 옮겼다는 전제의 경로다.)

---

## `## 규칙` 에 더할 줄

```markdown
- **대본 문장은 최종본에 정확히 한 번.** 빠져도 안 되고 두 번 나와도 안 된다. 감독의 삭제 요청은 "그 대본 구간이 남는 다른 발화로 덮이는가"
  (`covered_elsewhere`)로 판정한다 — 대본과 맞는다는 이유만으로 거절하지 않는다. 원본이 여럿이면 읽기 회차(`studio/text/passes.py`)를 먼저 가린다.
  설계: `docs/upgrade/02_전체테이크_중복_처리_설계.md`. 동작을 바꾸면 `tests/test_passes.py` 에 실제 사례를 더한다.
- **렌더 전에 게이트를 통과한다**(`studio/gate.py`, `docs/upgrade/08_품질_게이트.md`). 새 통계를 만들면 게이트 기준도 같이 정한다.
  `block` 게이트는 자동 수리 뒤에도 실패하면 렌더하지 않고 멈춘다. 게이트를 끄는 옵션을 기본값으로 두지 않는다.
- **화면 글자 위생.** 화면에 나가는 문자열에 검색어·연출 메모·내부 이름(템플릿 이름, `S\d+`, `g\d+`)이 섞이지 않게 한다.
  렌더러의 기본 라벨은 한국어 역할명이거나 빈 문자열이다(`renderer/src/design/surfaces.ts TEMPLATE_LABEL` 에 영어 템플릿 이름을 두지 않는다).
  스톡·사진의 `title` 에 `query_ko`/`query_en` 을 넣지 않는다. 게이트 B3~B5 가 잡는다.
- **자료는 조용히 빼지 않는다.** 못 구하면 사다리의 다음 단(다른 출처 → 화면 캡처 → 코드로 그린 도식 → 타이포 카드)으로 내려가고, 어디서 멈췄는지 `work/evidence.json` 과 리포트에 남긴다.
  "틀린 사진보다 없는 게 낫다"는 **맞지 않는 후보를 쓰지 않는다**는 뜻이지 **빈 화면으로 둔다**는 뜻이 아니다.
- **한 영상 한 재질.** 전면 배경색은 토큰(크림 종이·웜 잉크·시그널)에서만 온다. 자유 HTML 카드의 순백 `#FFF`·순흑 `#000` 전면 배경은 `card.py clean_card` 가 토큰으로 바꾼다.
- **음악은 큐 시트로.** 곡 선택·진입·퇴장·비우기는 음악 감독의 큐 시트(`plan.long.music_cues`)가 정하고, 믹서는 그것을 실행만 한다.
  챕터마다 다른 곡으로 바꾸지 않는다(주제곡 하나 + 변주). 곡을 잇거나 되풀이할 때는 마디 경계에서. 설계: `docs/upgrade/04_음악_사운드_엔진_v2.md`.
- **제3자 음원의 라이선스를 매니페스트에 적는다**(`license` · `attribution` · `content_id` · `commercial_ok`). 이 필드가 비어 있거나 `commercial_ok: false` 인 항목은 라이브러리가 싣지 않는다.
- **에이전트를 더하면 다섯 곳**: `studio/agents/studio.py AGENTS` · `studio/agents/schemas.py` · `prompts/agents/<이름>.md` · `tests/fake_claude.py`(가짜 응답) · `studio/eta.py`. 스키마에 키를 더하면 `director/plan.py` 정규화에서 보존한다(기존 규칙).
- **결과물에 대한 불만은 검수부터.** 편집 규칙(`PARAMS`)이나 프롬프트를 고치기 전에 `.claude/skills/choi-output-review` 로 그 작업 폴더를 진단한다 — 증상이 규칙이 아니라 버그·입력·옛 설치본에서 올 때가 많다.
- **설치본과 저장소를 구분한다.** 사용자가 돌리는 폴더는 ZIP 으로 푼 설치본이라 `git` 이 없다. 증상을 볼 때 설치본의 파일 시각과 저장소 HEAD 의 커밋 시각을 먼저 비교한다
  (2026-10-01 테스트는 색보정 얼룩 수정 `ce2f323` 이전 설치본으로 돌았다).
```

## `## 확인` 에 더할 줄

```markdown
- `python -m pytest tests/test_gate.py tests/test_passes.py -q` (게이트 · 읽기 회차)
- `python tests/e2e_synthetic.py --browser <chrome> --multi retake` (같은 대본을 두 번 찍은 원본 2개 → 길이가 두 배가 되지 않고, 같은 대본 문장이 한 번만 나오는지)
- 결과 검수: `.claude/skills/choi-output-review/SKILL.md` 의 절차(리포트 수치 → 검토 시트 전부 보기 → `audio_probe.py`)
```

## `## 구조` 에 더할 줄(구현한 뒤)

```markdown
- `studio/gate.py` — 품질 게이트(A 구조 · B 화면 · C 조판 · D 음향 · E 완성본). 검사는 순수 함수, 결과는 `work/gate.json` + 리포트 첫 절.
- `studio/text/passes.py` — 대본 읽기 회차 감지(`detect_passes`) · 주 테이크 고르기(`choose_main_pass`).
```
