# Choi Studio — 개발 메모 (Claude Code 용)

디자인 이론 교육 영상 자동 편집기. Python(PySide6 GUI + 파이프라인) → Remotion(React) 렌더.

## 구조
- `studio/pipeline.py` — 단계 오케스트레이션(probe → audio → asr → align → face → director → proxy → broll → stock → qa → render → export), 단계별 캐시는 `projects/<job>/work/`.
- `studio/agents/` — 🎬 AI 스튜디오. `studio.py`(감독 → 병렬 전문가 → `merge_plan` → 기존 LONG_PLAN 모양), `schemas.py`(에이전트별 스키마). 프롬프트는 `prompts/system_studio.md` + `prompts/agents/*.md`.
- `studio/stock/` — Pexels(`pexels.py`), 후보 시트·비전 선택·다운로드(`research.py`), 소재 정리(`process.py`). 결과 캐시 `work/stock.json`.
- `studio/motion/spec.py` — 모션 DSL 검증(화이트리스트·범위 제한). 렌더러는 `renderer/src/components/motion/MotionScene.tsx`, 문법 문서는 `prompts/motion_dsl.md` — 세 곳을 같이 바꾼다.
- `studio/text/align.py` — ASR↔대본 정렬, 리테이크/NG 제거, 태그 고정. 동작 변경 시 `tests/test_core.py` 갱신.
- `studio/director/` — `catalog.py`(템플릿 목록, TS 와 동기화), `schema.py`(구조화 출력 스키마: 모든 object 는 additionalProperties=false + 전체 required), `plan.py`(검증·시간 변환), `claude.py`(API 호출), `fallback.py`(키 없을 때).
- `prompts/*.md` — 편집 감독 프롬프트. 채널 톤 조정은 여기서.
- `renderer/src/lib/types.ts` ↔ `studio/render/props.py` — props 계약. 한쪽을 바꾸면 다른 쪽도.
- `renderer/src/components/graphics/` — 템플릿. 새 템플릿은 types.ts TemplateName + graphics/index.tsx + director/catalog.py 세 곳에 추가.

## 규칙
- 모션은 `renderer/src/design/motion.ts` 토큰(EASE·DUR·STAGGER·SPRING)만 쓴다. 자막 프리셋은 `components/captions/`.
- 계획에 새 키를 추가하면 `director/plan.py` 의 `_clean_graphic`/`normalize_long` 에서 보존해야 한다(재실행 시 plan.json 을 다시 정규화함).
- Claude 모델 기본값 `claude-opus-5-5`, 적응형 사고 + `output_config.effort` + `output_config.format`(json_schema). 거절 폴백은 beta `server-side-fallback-2026-07-01` + `fallbacks: "default"`.
- Remotion 은 4.0.530 고정. 애니메이션은 `useCurrentFrame()` + `interpolate()` 로만(CSS transition 금지).
- 영상 컷은 Remotion 이 CFR 프록시에서 프레임 단위로(`OffthreadVideo trimBefore`), 음성은 FFmpeg 로 샘플 단위 컷. 싱크를 깨는 변경 금지.
- Windows 가 1차 타깃: 경로는 pathlib, 서브프로세스는 `util.run_process`(콘솔 창 숨김), 긴 filter 는 `FFmpeg.filter_script_args`(FFmpeg 7+ `-/filter_complex`).

## 확인
- `python -m pytest tests -q`
- `cd renderer && npx tsc --noEmit`
- `python tests/e2e_synthetic.py --browser <chrome-headless-shell>` (Whisper 없이 전체 파이프라인)
- `python tests/e2e_studio.py --browser <chrome-headless-shell>` (가짜 Claude·Pexels 로 스튜디오·스톡·검수 전체)
- 템플릿 시각 확인: `cd renderer && npx remotion render src/index.ts LongForm out/f --sequence --frames=160,330 --image-format=jpeg`
