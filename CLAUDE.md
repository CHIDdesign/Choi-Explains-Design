# Choi Studio — 개발 메모 (Claude Code 용)

디자인 이론 교육 영상 **오토파일럿**. 입력은 주제 설명 · 원본 영상 · 대본 세 가지뿐 → 롱폼 1 + 숏폼 2 + 썸네일 + 업로드 정보 + 검토 시트.
Python(PySide6 창 + 파이프라인) → Remotion(React) 무음 렌더 → FFmpeg 음향 믹스·마스터링.

## 구조
- `studio/pipeline.py` — 단계 오케스트레이션(probe → audio → asr → align → face → grade → director → proxy → verify → broll → stock → sound → qa → render → master → export), 단계별 캐시는 `projects/<job>/work/`(`log.txt`·`진단.md` 포함). 결과는 `output/`(영상 3편 + 업로드정보.txt) · `output/부가자료/`(썸네일·자막·XML·리포트·색보정 전후·검토시트·진단자료.zip).
- `studio/text/takes.py` — **단어 단위 실수 정리**: 쉼·문장 끝·추임새 뒤에서 가까운 앞의 시도와 같은 말로 다시 시작하면 앞의 시도를 지움(마지막 시도가 남음), 떨어진 추임새 삭제. 꼬리에 '끝난 다른 문장'이 있으면 되풀이가 아님(NG 말 제외). 쉼은 VAD 로 잰다(`vad_pause`). 동작 변경 시 `tests/test_takes.py` 에 실제 사례를 추가.
- `studio/text/align.py` — ASR↔대본 정렬, 리테이크 묶음에서 **가장 또렷한 테이크**(`take_score`) 선택, NG 제거, 태그 고정. 동작 변경 시 `tests/test_core.py` 갱신.
- `studio/edit/cuts.py` · `studio/edit/verify.py` — keep 구간(단어 끝을 VAD 말소리 끝까지 연장, 긴 무음 정리), **편집 오류 검사**(잘라 붙인 목소리를 Whisper 로 다시 받아 적어 남은 되풀이·추임새·긴 무음을 원본 시간으로 되돌려 한 번 더 자름, 최대 2회, `work/verify.json`).
- `studio/edit/grammar.py` — **편집 문법 엔진**: AI 가 정한 강조 순간·그래픽 → 프레이밍(카메라)·강조(glide)·전환·키워드 콜아웃·효과음 큐·음악 스웰/교체/비우기. 수치는 `PARAMS` 한 곳(근거는 `prompts/playbook/`, `docs/research/*리서치.md`, 채널 피드백). 교육 영상이라 **젠틀하게**: 프레이밍 100↔106% 는 NG 점프·챕터·그래픽 복귀에서만, 같은 프레이밍 점프컷은 소프트 컷, 강조는 0.7초 글라이드, 전환은 blur/push/wipe/leak, 효과음은 템플릿별(`SFX_FOR_TEMPLATE`).
- `studio/grade/auto.py` — 자동 색보정: 프레임 분석 → 교정(WB·노출·명암·채도, 피부 보호) → 레퍼런스 색 맞춤(`ref_match`, CIELAB, `REFERENCE_LAB` 또는 `user/reference_frames/`) → 룩(기본 `warm_rich`) → 33³ LUT → 프록시에 굽는다. 🎨 컬러리스트(비전)가 비교 시트에서 룩 선택.
- `studio/sound/` — `library.py`(assets/sound_manifest.json 의 효과음·음악·RNNoise 모델을 처음 실행 때 내려받음, 실패 시 `synth.py` 절차적 효과음), `studio/media/mix.py`(보이스 + 덕킹 음악(챕터마다 곡 교체) + 효과음 → 2-pass -14 LUFS, 무음 렌더 영상과 합치기). 원본의 영상·소리 시작 차이(`MediaInfo.av_offset`)는 보이스 트랙에서 보정.
- `studio/net.py` — 막힘에 강한 HTTP(requests → urllib(브라우저 UA) → curl, 라운드별 재시도, 호스트별 간격 — Pixabay CDN 은 몰아서 받으면 403), 실패 이유 기록 → `studio/diag.py` 진단.
- `studio/agents/` — 🎬 AI 스튜디오. `studio.py`(감독 → 병렬 전문가 → `merge_plan` → 기존 LONG_PLAN 모양), `schemas.py`(에이전트별 스키마). 프롬프트는 `prompts/system_studio.md` + `prompts/agents/*.md`. 그래픽 밀도 목표는 8–15초에 하나.
- `studio/stock/` — 제공처(`pixabay.py` 기본, `unsplash.py`, `coverr.py`, `pexels.py`, 키 없는 `openverse.py`; 공통 `base.py`), 통합 검색 `providers.py`(StockHub: 검색어 줄여 가며 재검색, `StockError.fatal` 인 키 오류만 제공처를 끄고 일시 오류는 쉬었다가 계속), 후보 시트·비전 선택·다운로드(`research.py`), 모션 장면 안 `pixabay:<vector|illustration|photo>:<검색어>` 이미지 해석(`resolve_images`), 소재 정리(`process.py`). 결과 캐시 `work/stock.json`(에이전트가 뺀 것만 '없음'으로 확정).
- `studio/motion/spec.py` — 모션 DSL 검증(화이트리스트·범위 제한). 렌더러는 `renderer/src/components/motion/MotionScene.tsx`, 문법 문서는 `prompts/motion_dsl.md` — 세 곳을 같이 바꾼다.
- `studio/director/` — `catalog.py`(템플릿 목록, TS 와 동기화), `schema.py`(구조화 출력 스키마: 모든 object 는 additionalProperties=false + 전체 required), `plan.py`(검증·시간 변환), `claude.py`(API 호출), `fallback.py`(키 없을 때).
- `studio/director/claude_code.py` — 기본 AI 연결: 로컬 Claude Code `claude -p`(stream-json 입력·--json-schema·--system-prompt-file·--tools "", ANTHROPIC_API_KEY 제거). `claude.py` 는 API 키 방식. 둘은 같은 `structured()` 인터페이스.
- `prompts/*.md` — 편집 감독 프롬프트. 채널 톤 조정은 여기서. `prompts/playbook/*.md` = 레퍼런스 연구에서 뽑은 편집 문법(모든 에이전트 시스템 프롬프트에 들어감).
- `renderer/src/lib/types.ts` ↔ `studio/render/props.py` — props 계약. 한쪽을 바꾸면 다른 쪽도.
- `studio/render/props.py` — props 생성 + 편집 결과 반영(`apply_edit`, `mark_soft_cuts`), 한두 마디 자막(`text/captions.py build_phrase_cues`, VAD 시작에 맞춤), 화면 그래픽과 같은 말인 자막 숨김(`dedupe_captions` → cue `hidden`, SRT 에는 남김), 숏폼 개념 텍스트(`short_beats`), 종이 스킨 배치(`paper_layouts`).
- `studio/eta.py` — 남은 시간 예측: 단계별 시간 모델(원본 길이·fps·GPU·AI·출력 프레임, 첫 작업은 넉넉히) + 진행 중 실측 보정 + `user/eta_history.json` 에 이 PC 속도 학습. 단계를 추가하면 `DEFAULTS`·`GROUPS` 도.
- `studio/review.py` — 완성 영상 검토 시트(2.5초마다 한 장, 시간·자막) → `부가자료/검토시트_*.jpg`.
- `studio/gui/` — 오토파일럿 창: `app.py`(① 주제 ② 원본 영상 ③ 대본 → 진행 화면(남은 시간·실시간 미리보기) → 결과 화면), `winshell.py`(관리자 창에서 탐색기 끌어다 놓기: WM_DROPFILES 허용), `poster.py`, `icon.py`, `theme.py`, `settings_dialog.py`(고급 설정 — 브랜드 탭에 화면 스타일·숏폼 구성).
- `renderer/src/components/graphics/` — 템플릿. 새 템플릿은 types.ts TemplateName + graphics/index.tsx + director/catalog.py 세 곳에 추가.
- **화면 스킨**(props `skin`, 설정 `Settings.skin`):
  - `classic`(기본) = 에디토리얼 디자인(칠판 패널·잉크·시그널) + 사용자 템플릿에서 가져온 부분: 얼굴 옆 찢어진 액자 사진·개념 텍스트(pip/overlay), 개념 카드 글 위계(split), 타이틀(글 왼쪽 + 화자 액자), 우상단 출처, 엔드카드 '오늘의 정리'. 공통 부분은 `components/paper/PaperGraphic.tsx referenceGraphic`.
  - `paper` = 템플릿 전체: 구겨진 짙은 종이(`studio/render/assets.py make_paper`, 절차적)·회색 거친 테두리·액자 샷(`CameraShot.framed`, paper 일 때만 생성). 부품은 `components/paper/`(`Paper.tsx`·`Collage.tsx`·`PaperGraphic.tsx`·`PaperShort.tsx`).
- **숏폼 구성**(props `layout`, 설정 `Settings.shorts_layout`): `reel`(기본, `components/shorts/ReelShort.tsx` — 위 큰 카드가 그래픽·개념 텍스트(`beats`)로 바뀌고 아래는 얼굴, 이음새에 한두 마디 굵은 자막, 사진이 있으면 첫 2.2초 부채꼴 카드 + 큰 제목) · `window` · `full` · `framed`. 숏폼은 기획의 그래픽 + 그 구간의 롱폼 그래픽(`Pipeline._short_graphics`).

## 규칙
- 모션은 `renderer/src/design/motion.ts` 토큰(EASE·DUR·STAGGER·SPRING)만 쓴다. 자막 프리셋은 `components/captions/`(기본 `paper`: 흰 종이 상자 + 핵심어 굵게).
- 계획에 새 키를 추가하면 `director/plan.py` 의 `_clean_graphic`/`normalize_long`/`normalize_shorts` 에서 보존해야 한다(재실행 시 plan.json 을 다시 정규화함).
- Claude 모델 기본값 `claude-opus-5-5`, 적응형 사고 + `output_config.effort` + `output_config.format`(json_schema). 거절 폴백은 beta `server-side-fallback-2026-07-01` + `fallbacks: "default"`.
- Remotion 은 4.0.530 고정. 애니메이션은 `useCurrentFrame()` + `interpolate()` 로만(CSS transition 금지).
- 영상 컷은 Remotion 이 CFR 프록시에서 프레임 단위로(`OffthreadVideo trimBefore`), 음성은 FFmpeg 로 샘플 단위 컷. 싱크를 깨는 변경 금지.
- 편집은 젠틀하게(교육 영상): 하드컷 줌·휩·플래시 금지, 강조는 `glide`, 같은 프레이밍 점프컷은 `Clip.soft`(0.1초 섞기, 길이 불변), 컷이 아닌 곳의 프레이밍 변화는 `CameraShot.glide`.
- 렌더는 **무음**(`RenderItem.muted`), 음향은 `stage_master` 에서 믹스. 영상 길이를 바꾸는 전환(xfade·TransitionSeries) 금지 — 전환은 컷 지점 중심 오버레이(`components/fx/Transitions.tsx`).
- Windows 가 1차 타깃: 경로는 pathlib, 서브프로세스는 `util.run_process`(콘솔 창 숨김), 긴 filter 는 `FFmpeg.filter_script_args`(FFmpeg 7+ `-/filter_complex`).
- `.bat` 은 모두 첫머리에서 **관리자 권한으로 자동 재실행**(fltmc 확인 → `Start-Process -Verb RunAs`). 새 .bat 을 만들면 같은 블록을 넣는다. 실행 .bat 은 requirements.txt 가 바뀌면 패키지를 다시 설치한다(`.venv\.req_stamp`). 관리자 창에는 OLE 드래그 앤 드롭이 안 들어오므로 GUI 는 클릭·Ctrl+V·WM_DROPFILES 로 받는다.
- 진행 화면 미리보기는 `Pipeline(preview=…)` 로 보낸다. 렌더 중 프레임은 props `peekEvery` → `components/fx/LivePeek.tsx`(`Artifact.Thumbnail`) → `render.mjs` onArtifact → `peek` 이벤트(`run_render(on_peek=…)`). 결과 영상에는 영향 없음.
- 제3자 효과음·음악 파일은 저장소에 넣지 않는다(`assets/sound/` 는 gitignore, 목록만 `assets/sound_manifest.json`). 사용자가 준 레퍼런스 이미지도 넣지 않는다(측정값만 코드에).
- 진단 자료에는 키 값을 넣지 않는다(있음/없음만).

## 확인
- `python -m pytest tests -q`
- `cd renderer && npx tsc --noEmit`
- `python tests/e2e_synthetic.py --browser <chrome-headless-shell> [--face 얼굴클립.mp4]` (Whisper·AI 없이 전체 파이프라인, --face 로 실제 얼굴 영상 반복 사용)
- `python tests/e2e_realistic.py --face 얼굴클립.mp4` (gTTS 한국어 음성 + 실제 faster-whisper 로 되풀이·추임새·무음 정리와 편집 오류 검사 확인)
- `python tests/e2e_studio.py --browser <chrome-headless-shell>` (가짜 Claude Code CLI·Pixabay·Unsplash 로 스튜디오·스톡·검수 전체, `--backend api` 는 가짜 API 서버)
- E2E·테스트에서 **진짜 claude CLI 를 부르지 않도록** 반드시 `settings.claude_code_path` 를 가짜 CLI 로 지정하거나 `ai_backend="api"` 로.
- 결과 훑어보기: `부가자료/검토시트_*.jpg`. 템플릿 시각 확인: `cd renderer && npx remotion render src/index.ts LongForm out/f --sequence --frames=160,330 --image-format=jpeg`
