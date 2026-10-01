# 09. Claude Code 작업지시서 — 그대로 붙여 넣어 시키는 순서

저장소(`Choi-Explains-Design`)에서 Claude Code 를 열고, 아래 블록을 **하나씩** 붙여 넣는다. 한 번에 하나의 작업 꾸러미(WP)만 시킨다.
전제: 이 폴더의 `docs/upgrade/` · `docs/research/` · `prompts/` · `claude-skills/` 를 저장소의 같은 경로에 복사해 뒀다
(`claude-skills/*` 는 `.claude/skills/` 아래로, `CLAUDE_md_추가.md` 의 내용은 `CLAUDE.md` 에 붙인다).

공통 규칙(모든 WP 끝에 자동으로 지키게 `CLAUDE.md` 에 이미 있다): `python -m pytest tests -q` · `cd renderer && npx tsc --noEmit` 통과,
props 계약(`types.ts` ↔ `props.py`)·카탈로그 세 곳·계획 정규화 보존 규칙 준수, E2E 는 가짜 CLI 로.

---

## WP0 — 픽스처 만들기(먼저 한 번)

```
docs/upgrade/00_테스트영상_진단.md 를 읽어라.
projects/20261001_2028_… 작업의 다음 파일을 tests/fixtures/run_20261001/ 로 복사해 테스트 픽스처로 만든다(영상·음성 파일은 넣지 않는다):
output/부가자료/plan.json, work/plan_raw.json, work/stock.json, work/sources.json, work/align.json, output/부가자료/롱폼_자막.srt,
output/부가자료/편집리포트.md, 그리고 work/stock_cache/ 의 openverse_*.json.
개인 경로·키 값이 들어 있으면 지운다. 이 픽스처를 읽는 도우미 tests/fixtures/__init__.py(load_run_20261001())를 만든다.
코드는 아직 고치지 않는다.
```

## WP1 — 중복 테이크(P0 버그)

```
docs/upgrade/02_전체테이크_중복_처리_설계.md 를 읽고 4절 표의 1~6번을 구현하라(7번 B캠은 하지 않는다).
순서: (1) pipeline.py 의 삭제 거절에 covered_elsewhere 조건 + drop 뒤 커버리지 재검 → (2) studio/text/passes.py(detect_passes, choose_main_pass)
→ (3) align.py 가 회차를 써서 리테이크를 거리 제한 없이 묶기 → (4) sources.json 에 role 기록 → (5) 리포트·GUI 한 줄.
docs/upgrade/13_에이전트_팀_v2.md 2-1 의 BRIEF.integrity 도 같이 넣는다(schemas.py, director.md 한 문단, plan.py 보존, fallback.py).
테스트: tests/test_passes.py 신규(문서 4절의 다섯 사례), tests/test_review_fixes.py 에 "전체 2회차 + 감독 drop" 사례,
tests/e2e_synthetic.py 에 --multi retake 모드(문서 5절의 단언 그대로). 회차가 1개일 때 기존 테스트가 전부 그대로 통과해야 한다.
끝나면 WP0 픽스처의 align.json 으로 detect_passes 가 2회차를 찾는지 보여 줘라.
```

## WP2 — 품질 게이트 A + 화면 글자 위생

```
docs/upgrade/08_품질_게이트.md 를 읽고 studio/gate.py 를 만든다: GateResult, 게이트 A1·A3·A5·A6·A7·A8·A9, B3·B4·B5.
파이프라인에서 _make_edit 뒤에 게이트 A 를, 렌더 props 확정 뒤에 B3~B5 를 부른다. block 이 수리 뒤에도 실패하면 렌더하지 않고
사유를 로그·GUI 에 띄운다("그래도 만들기"는 CLI 플래그 --force-render 로만). 결과는 work/gate.json 과 편집리포트 첫 절.
같이 고친다(docs/upgrade/06_모션_그래픽_v2.md 8절, docs/upgrade/03_자료_조달_엔진_v2.md P0-2):
renderer/src/design/surfaces.ts TEMPLATE_LABEL 의 영어 내부 이름을 한국어 역할명 또는 빈 문자열로,
studio/agents/studio.py merge_plan 이 사진의 kind·스톡의 query_ko·purpose 를 title/body 에 넣지 않게.
테스트: tests/test_gate.py 신규 — WP0 픽스처로 A1·A3·A5·A6·A7·A8·A9 가 실패하는지, B3·B5 가 "스케치북 넘기기"·"brand"·"motion" 을 잡는지.
```

## WP3 — 구한 자료를 버리지 않기 + 라이선스

```
docs/upgrade/03_자료_조달_엔진_v2.md 의 10절 P0 패치 목록을 구현하라: P0-1, P0-3, P0-4, P0-5, P0-6, P0-7, P0-8, P0-9, P0-11
(P0-2 는 WP2 에서 했다. P0-10 은 게이트 B2 와 함께 넣는다).
각 항목의 테스트 이름은 표에 있다. Openverse 필터는 실제 응답 픽스처(WP0 의 openverse_*.json)로 NC/ND 가 걸러지는지 본다.
GUI "④ 자료 폴더"는 선택 입력이고 비어 있어도 지금과 똑같이 동작해야 한다.
```

## WP4 — 늦는 단계 강조·덮이는 고백

```
docs/upgrade/05_편집_문법_v2.md 8절 표의 1번(steps → stepAt)과 2번(EDITOR.holds + 홀드 보호)을 구현하라.
prompts/agents/editor_addendum.md · director_addendum.md 에서 이 두 항목에 해당하는 줄만 prompts/agents/editor.md · director.md 에 반영한다.
테스트: tests/test_sequences.py 신규(표의 pytest 이름). WP0 픽스처의 S122(더블 다이아몬드)에서 단계 강조가 낱말 ±0.5초 안에 오는지,
S158–S160 홀드 구간에 정리 보드가 안 들어가는지 단언한다.
```

## WP5 — 눈에 띄는 화면 결함

```
docs/upgrade/06_모션_그래픽_v2.md 10절의 P0 항목을 구현하라. 최소: 액자 샷 끄기(framed_every 0), 자유 카드의 순백·순흑 전면 배경을 토큰으로 강제,
0프레임에 무대가 서도록(게이트 C4), 숏폼에서 롱폼 카드를 0.458배로 줄여 넣지 않게(숏폼 전용 크기 또는 재조판), check.mjs 글꼴 정규식 수정,
퇴장 중 얼굴 가림(화자 확대 시작 시점과 그래픽 퇴장 시점 맞추기).
docs/upgrade/10_썸네일_v2.md 의 프레임 선택 규칙(주 테이크에서만, 눈 뜬·정면·말하지 않는 프레임)도 넣는다.
각 항목의 승인 기준(렌더할 스틸 또는 수치)은 문서에 있다. 스틸을 실제로 렌더해 눈으로 확인하고 결과 이미지를 보여 줘라.
```

## WP6 — 음악 응급 처치

```
docs/upgrade/04_음악_사운드_엔진_v2.md 11절의 첫 단계만 구현하라: 숏폼 기본 upbeat/inspiring 제거(롱폼과 같은 계열), 챕터마다 곡 교체 끄기(한 곡),
맞는 무드가 없을 때 아무 곡이나 고르는 폴백 제거(음악 없이), 음악 게인을 목소리 실측 라우드니스 기준 상대값으로, lead_silence_s 건너뛰기,
끝은 3초 임의 페이드 대신 문서의 방식.
docs/upgrade/04b_사운드_라이브러리_v2.md 7절의 권리 문제(Content ID · CC BY-NC · 크레딧)를 매니페스트에 필드로 적고, commercial_ok 가 false 인 항목은 싣지 않는다.
테스트는 문서의 pytest 이름. 믹스 뒤 claude-skills/choi-output-review/scripts/audio_probe.py 를 돌려 수치를 보여 줘라.
```

## ── 여기서 멈추고 재렌더 ──

```
같은 원본 2개(IMG_9597.MOV, IMG_9596.MOV)와 같은 대본으로 다시 만든 뒤, .claude/skills/choi-output-review 스킬로 그 작업 폴더를 검수해
docs/upgrade/00_테스트영상_진단.md 와 같은 형식의 진단을 projects/<새 작업>/output/부가자료/진단.md 로 써라.
docs/upgrade/01_업그레이드_로드맵.md 의 "재실행으로 확인할 지표" 표를 채워라.
```

## WP7 — 자료 조달 엔진 v2

```
docs/upgrade/03_자료_조달_엔진_v2.md 11절 P1 을 구현하라. 순서: EVIDENCE 스키마·merge_plan·plan.py 보존·catalog 의 evidence 템플릿(세 곳 동기화)
→ prompts/agents/visual_researcher.md · stock_pick_v2.md 로 교체, 플레이북 04_visual_evidence.md · 스킬 image_treatment.md 투입
→ studio/assets/(local · entity · commons · wikipedia_media · scholar + 출처 카드 · screenshot · license · ladder)
→ 되메우기 루프(게이트 B1·B2·B6) → docs/upgrade/03b_자료_트리트먼트_컴포넌트.md 의 P1 컴포넌트.
권리는 docs/upgrade/저작권_위험등급_정책.md 를 따른다(C 등급은 기본 끔).
docs/upgrade/13_에이전트_팀_v2.md 2-2 대로 자료 조달을 모션 디자이너 앞으로 옮기고, 확보 목록(work/evidence.json)과 컨택트 시트를 모션 디자이너에게 준다.
tests/fake_claude.py · tests/e2e_studio.py 에 새 스키마의 가짜 응답을 더한다.
```

## WP8 — 시퀀스와 리듬

```
docs/upgrade/05_편집_문법_v2.md 8절 표의 3~12번을 구현하라(1·2번은 WP4 에서 했다).
"8~15초마다 하나" 문구 일곱 곳은 7절의 표대로 바꾼다. 플레이북 05_sequences.md, 스킬 editing_craft.md 를 넣고
studio_system_prompt() 의 스킬 로딩을 sorted(skills/*.md) 로 바꾼다(prompts/system_studio_addendum.md "적용 순서").
리듬 게이트 A11~A17 은 gate.py 에 더하고, WP0 픽스처에서 문서 4-2 표의 '실제' 열대로 실패하는지 단언한다.
```

## WP9 — 한 재질·무대 구성·모션 검수

```
docs/upgrade/06_모션_그래픽_v2.md 10절 P1 과 docs/upgrade/06b_모션_토큰_제안.md 를 구현하라: 하우스 재질(크림 종이 + 웜 잉크 책상), 무대 구성 여섯 가지,
변주 체계, 모션 토큰 v2, DSL 추가(spec.py · MotionScene.tsx · motion_dsl.md 세 곳, 카드는 card-anim.mjs · card.py · card_dsl.md 세 곳).
prompts/skills/motion_craft.md · layout_typography.md · playbook/06_anti_template.md 투입, prompts/agents/motion_addendum.md 를 motion.md 에 반영,
art_director.md 를 art_director_v2.md 로 교체하고 QA 스키마에 escalate_edit·scope·blocking 추가.
이어서 docs/upgrade/06c_모션_검수_파이프라인.md 의 P0·P1(타이밍 린트, 스트립 프레임 검수)과 08 문서의 게이트 C 를 모든 그래픽으로 확장한다.
[제안] 표시가 붙은 수치는 스틸을 렌더해 눈으로 확인한 뒤 확정하고, 바꾼 값은 문서에 되적어라.
```

## WP10 — 음악·사운드 v2

```
docs/upgrade/04_음악_사운드_엔진_v2.md 11절의 나머지 단계를 구현하라: MUSIC 스키마와 🎼 음악 감독(prompts/agents/music_supervisor.md, AGENTS 등록은 13 문서 3절),
큐 시트 → 시각(studio/sound/cues.py), 키트 선택, 마디 경계 리타깃, 믹스 체인, 게이트 D.
docs/upgrade/04b_사운드_라이브러리_v2.md 의 매니페스트 v2 와 입고 게이트(scripts/sound_ingest.py)를 만든다 — 곡을 고르는 것은 운영자가 한다(4절 절차).
docs/upgrade/04c_효과음_팔레트_v2.md 의 매핑 표대로 SFX_FOR_TEMPLATE · SFX_FOR_TX 를 바꾼다.
플레이북 07_sound.md · 스킬 music_direction.md 투입(03_craft.md 의 대체되는 줄은 07_sound.md 머리말에 적혀 있다).
```

## WP11 — 색·룩

```
docs/upgrade/07_영상_룩_v2.md 의 P0·P1 을 구현하라: 따뜻한 방 + 웜 룩 규칙, 원본 간 샷 매칭, 색 태그·디더, cleanup_filters 를 필요할 때만,
색 게이트 F. prompts/agents/colorist.md 를 colorist_v2.md 로 교체.
docs/upgrade/07b_자료_하우스_트리트먼트.md 를 studio/stock/process.py 와 모션 장면 이미지 경로에 넣는다(게이트 B8).
색보정 테스트는 tests/test_autopilot.py 의 기존 사례(파란 방·회색 방·스튜디오·노란/초록 얼굴)가 그대로 통과해야 한다.
```

## WP12 — 팀 재편과 타임라인 검수

```
docs/upgrade/13_에이전트_팀_v2.md 3절의 등록 표를 끝까지 반영하고(부분 재호출 블록, eta.py, settings 키, report.py),
docs/upgrade/05b_편집_검수_루브릭.md 의 타임라인 검수(TIMELINE_QA, prompts/agents/timeline_review.md, 게이트 E)를 구현하라.
렌더 뒤 검토 시트를 재사용하고, ok:false 면 결과 폴더와 GUI 에 "검토 필요"를 붙인다.
```

---

## 시킬 때의 요령

- **WP 하나가 끝나면 바로 커밋**하고 다음으로 간다. 여러 WP 를 한 세션에 몰지 않는다(문맥이 섞인다).
- Claude Code 가 문서와 다른 판단을 하면 **문서를 고치게** 한다(코드와 문서가 어긋난 채 두지 않는다).
- `[제안]`·`[I]`·"(미확인)"·"실행 검증 안 함" 표시가 붙은 값은 **출발값**이다. 구현하면서 실제로 돌려 본 값으로 바꾸게 한다.
- 결과물이 마음에 안 들면 규칙을 고치라고 하기 전에 `choi-output-review` 스킬부터 돌린다.
