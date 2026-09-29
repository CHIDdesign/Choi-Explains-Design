# Choi Studio — 개발 메모 (Claude Code 용)

디자인 이론 교육 영상 **오토파일럿**. 입력은 주제 설명 · 원본 영상 · 대본 세 가지뿐 → 롱폼 1 + 숏폼 2 + 썸네일 + 업로드 정보.
Python(PySide6 창 + 파이프라인) → Remotion(React) 무음 렌더 → FFmpeg 음향 믹스·마스터링.

## 구조
- `studio/pipeline.py` — 단계 오케스트레이션(probe → audio → asr → align → face → grade → director → proxy → broll → stock → sound → qa → render → master → export), 단계별 캐시는 `projects/<job>/work/`. 결과는 `output/`(영상 3편 + 업로드정보.txt) · `output/부가자료/`(썸네일·자막·XML·리포트·색보정 전후).
- `studio/edit/grammar.py` — **편집 문법 엔진**: AI 가 정한 강조 순간·그래픽 → 점프컷 앵글(카메라)·펀치인·전환·키워드 콜아웃·효과음 큐·음악 스웰/교체/비우기. 수치는 `PARAMS` 한 곳(근거는 `prompts/playbook/`, `docs/research/*리서치.md`).
- `studio/grade/auto.py` — 자동 색보정: 프레임 분석 → 교정(WB·노출·명암·채도, 피부 보호) + 룩 4종 → 33³ LUT → 프록시에 굽는다. 🎨 컬러리스트(비전)가 비교 시트에서 룩 선택.
- `studio/sound/` — `library.py`(assets/sound_manifest.json 의 효과음·음악·RNNoise 모델을 처음 실행 때 내려받음, 실패 시 `synth.py` 절차적 효과음), `studio/media/mix.py`(보이스 + 덕킹 음악(챕터마다 곡 교체) + 효과음 → 2-pass -14 LUFS, 무음 렌더 영상과 합치기).
- `studio/agents/` — 🎬 AI 스튜디오. `studio.py`(감독 → 병렬 전문가 → `merge_plan` → 기존 LONG_PLAN 모양), `schemas.py`(에이전트별 스키마). 프롬프트는 `prompts/system_studio.md` + `prompts/agents/*.md`.
- `studio/stock/` — 제공처(`pixabay.py` 기본, `unsplash.py`, `coverr.py`, `pexels.py`; 공통 `base.py`), 통합 검색 `providers.py`(StockHub), 후보 시트·비전 선택·다운로드(`research.py`), 소재 정리(`process.py`). 결과 캐시 `work/stock.json`.
- `studio/motion/spec.py` — 모션 DSL 검증(화이트리스트·범위 제한). 렌더러는 `renderer/src/components/motion/MotionScene.tsx`, 문법 문서는 `prompts/motion_dsl.md` — 세 곳을 같이 바꾼다.
- `studio/text/align.py` — ASR↔대본 정렬, 리테이크 묶음에서 **가장 또렷한 테이크**(`take_score`) 선택, NG 제거, 태그 고정. 동작 변경 시 `tests/test_core.py` 갱신.
- `studio/director/` — `catalog.py`(템플릿 목록, TS 와 동기화), `schema.py`(구조화 출력 스키마: 모든 object 는 additionalProperties=false + 전체 required), `plan.py`(검증·시간 변환), `claude.py`(API 호출), `fallback.py`(키 없을 때).
- `prompts/*.md` — 편집 감독 프롬프트. 채널 톤 조정은 여기서. `prompts/playbook/*.md` = 레퍼런스 연구에서 뽑은 편집 문법(모든 에이전트 시스템 프롬프트에 들어감).
- `renderer/src/lib/types.ts` ↔ `studio/render/props.py` — props 계약. 한쪽을 바꾸면 다른 쪽도.
- `studio/eta.py` — 남은 시간 예측: 단계별 시간 모델(원본 길이·fps·GPU·AI·출력 프레임, 첫 작업은 넉넉히) + 진행 중 실측 보정 + `user/eta_history.json` 에 이 PC 속도 학습. 단계를 추가하면 `DEFAULTS`·`GROUPS` 도.
- `studio/gui/` — 오토파일럿 창: `app.py`(① 주제 ② 원본 영상 ③ 대본 → 진행 화면(남은 시간·실시간 미리보기) → 결과 화면), `winshell.py`(관리자 창에서 탐색기 끌어다 놓기: WM_DROPFILES 허용), `poster.py`, `icon.py`, `theme.py`, `settings_dialog.py`(고급 설정).
- `studio/director/claude_code.py` — 기본 AI 연결: 로컬 Claude Code `claude -p`(stream-json 입력·--json-schema·--system-prompt-file·--tools "", ANTHROPIC_API_KEY 제거). `claude.py` 는 API 키 방식. 둘은 같은 `structured()` 인터페이스.
- `renderer/src/components/graphics/` — 템플릿. 새 템플릿은 types.ts TemplateName + graphics/index.tsx + director/catalog.py 세 곳에 추가.

## 규칙
- 모션은 `renderer/src/design/motion.ts` 토큰(EASE·DUR·STAGGER·SPRING)만 쓴다. 자막 프리셋은 `components/captions/`.
- 계획에 새 키를 추가하면 `director/plan.py` 의 `_clean_graphic`/`normalize_long` 에서 보존해야 한다(재실행 시 plan.json 을 다시 정규화함).
- Claude 모델 기본값 `claude-opus-5-5`, 적응형 사고 + `output_config.effort` + `output_config.format`(json_schema). 거절 폴백은 beta `server-side-fallback-2026-07-01` + `fallbacks: "default"`.
- Remotion 은 4.0.530 고정. 애니메이션은 `useCurrentFrame()` + `interpolate()` 로만(CSS transition 금지).
- 영상 컷은 Remotion 이 CFR 프록시에서 프레임 단위로(`OffthreadVideo trimBefore`), 음성은 FFmpeg 로 샘플 단위 컷. 싱크를 깨는 변경 금지.
- Windows 가 1차 타깃: 경로는 pathlib, 서브프로세스는 `util.run_process`(콘솔 창 숨김), 긴 filter 는 `FFmpeg.filter_script_args`(FFmpeg 7+ `-/filter_complex`).
- `.bat` 은 모두 첫머리에서 **관리자 권한으로 자동 재실행**(fltmc 확인 → `Start-Process -Verb RunAs`). 새 .bat 을 만들면 같은 블록을 넣는다. 관리자 창에는 OLE 드래그 앤 드롭이 안 들어오므로 GUI 는 클릭·Ctrl+V·WM_DROPFILES 로 받는다.
- 진행 화면 미리보기는 `Pipeline(preview=…)` 로 보낸다. 렌더 중 프레임은 props `peekEvery` → `components/fx/LivePeek.tsx`(`Artifact.Thumbnail`) → `render.mjs` onArtifact → `peek` 이벤트(`run_render(on_peek=…)`). 결과 영상에는 영향 없음.
- 렌더는 **무음**(`RenderItem.muted`), 음향은 `stage_master` 에서 믹스. 영상 길이를 바꾸는 전환(xfade·TransitionSeries) 금지 — 전환은 컷 지점 중심 오버레이(`components/fx/Transitions.tsx`).
- 제3자 효과음·음악 파일은 저장소에 넣지 않는다(`assets/sound/` 는 gitignore, 목록만 `assets/sound_manifest.json`).

## 확인
- `python -m pytest tests -q`
- `cd renderer && npx tsc --noEmit`
- `python tests/e2e_synthetic.py --browser <chrome-headless-shell> [--face 얼굴클립.mp4]` (Whisper·AI 없이 전체 파이프라인, --face 로 실제 얼굴 영상 반복 사용)
- `python tests/e2e_studio.py --browser <chrome-headless-shell>` (가짜 Claude Code CLI·Pixabay·Unsplash 로 스튜디오·스톡·검수 전체, `--backend api` 는 가짜 API 서버)
- E2E·테스트에서 **진짜 claude CLI 를 부르지 않도록** 반드시 `settings.claude_code_path` 를 가짜 CLI 로 지정하거나 `ai_backend="api"` 로.
- 템플릿 시각 확인: `cd renderer && npx remotion render src/index.ts LongForm out/f --sequence --frames=160,330 --image-format=jpeg`
