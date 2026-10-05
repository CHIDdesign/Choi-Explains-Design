# Choi Studio 업그레이드 자료

> 저장소 반영 상태(2026-10-01): 문서는 `docs/upgrade/` · `docs/research/`, 스킬은 `.claude/skills/` 로 옮겼다.
> 에이전트 프롬프트(`prompts/…`)는 README 의 주의대로 **스키마·코드와 함께** 넣어야 하므로 `docs/upgrade/prompts/` 에 두고,
> 작업지시서(09)의 WP 를 구현할 때마다 저장소의 `prompts/` 로 옮긴다. 옮긴 항목과 남은 항목은 이 문서 끝 '반영 기록'에 적는다.

`Choi-Explains-Design` 저장소에 넣을 보완 문서 묶음. 2026-10-01 테스트 결과물(롱폼 12:44 · 숏폼 55초)을 실제로 뜯어본 진단에서 출발해,
분야별 리서치 → 설계 → 에이전트 지시문 → Claude Code 작업지시서까지 이어진다.

폴더 구조는 저장소와 같다. **그대로 복사하면 된다**(`claude-skills/` 만 `.claude/skills/` 로).

## 먼저 읽을 세 개

1. [`docs/upgrade/00_테스트영상_진단.md`](docs/upgrade/00_테스트영상_진단.md) — 왜 그렇게 보였는가. 가장 큰 원인은 감각이 아니라 버그였다(같은 대본을 두 번 찍은 원본이 둘 다 들어감).
2. [`docs/upgrade/01_업그레이드_로드맵.md`](docs/upgrade/01_업그레이드_로드맵.md) — 무엇을 어떤 순서로. 오늘 코드 수정 없이 할 수 있는 것부터.
3. [`docs/upgrade/09_Claude_Code_작업지시서.md`](docs/upgrade/09_Claude_Code_작업지시서.md) — Claude Code 에 그대로 붙여 넣는 작업 꾸러미 13개.

## 전체 목록

### 진단·계획 — `docs/upgrade/`
| 파일 | 내용 |
|---|---|
| `00_테스트영상_진단.md` | 리포트·로그·검토 시트·믹스 실측으로 본 증상 → 코드 원인. 부록에 Gemini 시청 결과 |
| `01_업그레이드_로드맵.md` | 0~3단계, 단계별 완료 기준과 재실행 지표 |
| `09_Claude_Code_작업지시서.md` | WP0~WP12 붙여넣기용 지시문 |
| `13_에이전트_팀_v2.md` | 호출 순서, 새 에이전트, 부분 재호출, 등록할 코드 위치, 토큰 예산 |

### 설계 — `docs/upgrade/`
| 파일 | 내용 |
|---|---|
| `02_전체테이크_중복_처리_설계.md` | **P0 버그.** 읽기 회차 감지, 삭제 거절 조건, 두 회차를 B캠으로 |
| `08_품질_게이트.md` | "이상하면 렌더하지 않는다" — 구조·화면·조판·음향·완성본 게이트 |
| `03_자료_조달_엔진_v2.md` | 증거 스키마, 조달 사다리, 되메우기, P0 패치 11개 |
| `03b_자료_트리트먼트_컴포넌트.md` | 전면 hero · 문서 밑줄 · 브라우저 틀 · 자료 카드 등 Remotion 명세 |
| `저작권_위험등급_정책.md` | A/B/C 등급, 크레딧 표기(일반 정보이며 법률 자문이 아님) |
| `04_음악_사운드_엔진_v2.md` | 한 편의 스코어: 큐 시트, 선택, 마디 리타깃, 믹스 체인 |
| `04b_사운드_라이브러리_v2.md` | 매니페스트 v2, 운영자 큐레이션 절차, **지금 조치할 권리 문제** |
| `04c_효과음_팔레트_v2.md` | 종이·문구 폴리 팔레트와 매핑 표 |
| `05_편집_문법_v2.md` | 시퀀스 일곱 유형, 리듬 게이트, 홀드, "8~15초" 문구 교체 |
| `05b_편집_검수_루브릭.md` | 정지 화면이 아니라 타임라인을 보는 검수 |
| `06_모션_그래픽_v2.md` | 한 재질, 무대 구성, 변주 체계, 누수·버그 수정, 숏폼 구성 |
| `06b_모션_토큰_제안.md` | `motion.ts` · `tokens.ts` 에 넣을 코드 |
| `06c_모션_검수_파이프라인.md` | 타이밍 린트, 스트립 프레임 검수 |
| `06d_애니메이션_레시피.md` | Remotion 레시피 카탈로그 |
| `07_영상_룩_v2.md` | 색 교정 규칙, 샷 매칭, 마감, 색 게이트 |
| `07b_자료_하우스_트리트먼트.md` | 스톡·클립아트를 채널 톤으로 통일하는 레시피 |
| `10_썸네일_v2.md` | 프레임 선택, 레이아웃, 글자 규칙 |

### 화자(사람)를 위한 가이드 — `docs/upgrade/`
| 파일 | 내용 |
|---|---|
| `11_기획_대본_촬영_가이드.md` | 논지·2단 AV 스크립트·자료 모으기·대본 태그·촬영 습관 |
| `12_촬영_체크리스트.md` | 조명·노출 고정·배경·프레이밍·마이크 한 장 체크리스트 |

### 리서치 — `docs/research/`
`이미지_자료_조달_리서치.md` · `음악_사운드_리서치.md` · `편집이론_영상에세이_리서치.md` · `모션_시각디자인_이론_리서치.md` · `색보정_필름룩_리서치.md` · `애니메이션_스킬_저장소_리서치.md`
— 각 문서 머리의 "검증 상태"에 직접 확인한 것과 못 한 것이 적혀 있다. `docs/스킬_출처_추가.md` 는 기존 `docs/스킬_출처.md` 에 붙일 출처·라이선스 표.

### 에이전트가 읽는 것 — `prompts/`
| 파일 | 넣는 법 |
|---|---|
| `system_studio_addendum.md` | `system_studio.md` 에 반영할 줄(원칙 4·10 교체, 11~15 추가) |
| `playbook/04_visual_evidence.md` · `05_sequences.md` · `06_anti_template.md` · `07_sound.md` | 폴더에 넣으면 자동으로 들어간다(`playbook_block()` 이 전부 읽음) |
| `skills/motion_craft.md` · `layout_typography.md` · `image_treatment.md` · `editing_craft.md` · `music_direction.md` | `studio_system_prompt()` 의 스킬 로딩을 `sorted(skills/*.md)` 로 바꿔야 들어간다. 옛 `motion_principles.md` · `editing_principles.md` 는 지운다 |
| `agents/visual_researcher.md` · `stock_pick_v2.md` · `art_director_v2.md` · `colorist_v2.md` | 기존 `stock.md` · `stock_pick.md` · `art_director.md` · `colorist.md` 를 대체. **스키마 변경과 같이** 넣어야 한다(지시문만 바꾸면 출력이 스키마와 어긋난다) |
| `agents/music_supervisor.md` | 새 에이전트. `AGENTS` · `schemas.py` 등록 필요 |
| `agents/director_addendum.md` · `editor_addendum.md` · `motion_addendum.md` | 기존 지시문에서 지울 줄 / 더할 줄 |
| `examples/모션_예제_후보.md` | 렌더로 확인한 것만 `motion_examples.json` 에 옮긴다 |

### Claude Code 스킬 — `claude-skills/` → `.claude/skills/`
| 스킬 | 용도 |
|---|---|
| `choi-output-review` | 완성된 작업 폴더를 근거로 진단(리포트 수치 → 검토 시트 → 믹스 실측). 불만이 생기면 규칙을 고치기 전에 먼저 |
| `choi-motion-scene` | 모션 장면 설계·검증(기존 스킬의 개정판) |
| `choi-motion-review` | 완성 작업의 모션을 린트 + 스트립 프레임으로 검수 |

### 그 밖
`CLAUDE_md_추가.md` — 저장소 `CLAUDE.md` 에 붙일 개발 규칙.

## 읽을 때 주의

- **프롬프트 파일만 먼저 넣지 않는다.** 플레이북 네 개는 넣는 즉시 모든 에이전트에 들어가지만, 그 안의 필드(`evidence` · `sequences` · `holds` · 큐 시트)를 받는 스키마·코드가 없으면 에이전트가 낼 곳이 없다. 작업지시서의 순서대로 코드와 함께 넣는다.
- 문서 속 `[제안]` · `[I]` · "(미확인)" · "실행 검증 안 함" 은 **출발값**이라는 뜻이다. 렌더해서 눈으로, 믹스해서 귀로 확정한다.
- 수치·코드 위치는 저장소 HEAD `ce2f323` 과 10/1 작업 폴더 기준이다. 설치본은 그보다 옛 버전이었다.
- 리서치의 일부 출처는 검색 요약 수준이다(조사 중 웹 검색 한도에 걸림). 각 리서치 문서 머리에 구분해 두었다.

## 반영 기록

| WP | 상태 | 커밋·메모 |
|---|---|---|
| 문서·스킬 배치 | 완료 | `docs/upgrade/`, `docs/research/`, `.claude/skills/choi-output-review` · `choi-motion-review` · `choi-motion-scene`(개정판) |
| WP0 픽스처 | 대체 | 10/1 작업 폴더가 저장소에 없어 합성 픽스처로 대체: `tests/test_passes.py`(두 번 읽은 대본), `tests/test_gate.py`(12:44 · 95문장 중복 · 맨얼굴 397초 · 타이틀 06:48 · 'brand'·'스케치북 넘기기'), E2E `--multi retake` |
| WP1 전체 테이크 중복 | 완료 | `studio/text/passes.py`, `ScriptAligner._split_passes`(best_pass/stitch), `covered_elsewhere`, `BRIEF.integrity`(→ `prompts/agents/director.md`), 게이트 A0 로그, `_order_by_script`, 리포트 '읽기 회차'. E2E retake: 본편 32.9초(회차 하나 49.7초), 대본 문장마다 한 번, 주 테이크 파일만 |
| WP2 게이트 A + 화면 글자 | 완료 | `studio/gate.py` A1·A2(경고)·A3·A5·A6·A7·A8·A9 · B3·B4·B5, 수리(`_repair_duplicates`·`_fill_gaps`·`_retime_title`·`scrub_labels`), `work/gate.json` · 편집리포트 첫 절 · `품질게이트_중단.md` · `--force-render`. `TEMPLATE_LABEL` 내부 이름 → 빈 문자열, `merge_plan` P0-2(스톡 `caption` 신설). 남음: A4(커버리지는 대본 충실 보증이 맡음)·A10, B1·B2·B6~B9, C·D·E, 아트 디렉터 `escalate_edit` |
| WP3 자료 P0 | 완료(P0-5 일부) | P0-1 `name_en` 재조회 · P0-3 Openverse NC/ND 필터·attribution · P0-4 이름 카드/자료 카드·잃음 로그·Openverse 1회 · P0-6 아트 디렉터 low 의 글자 줄이기·빼기 반영(`qa_actionable`) · P0-7 실물 자료는 옮긴다(`resolve_overlaps`) · P0-8 오류를 '없음'으로 캐시 안 함 · P0-9 창 ④ 자료 폴더 · P0-11 세로 사진 여백 액자(`broll/mat.py`). P0-5 는 브랜드=로고·사람=초상 후보까지(작품의 media-list 후보는 P1). 픽스처는 합성 응답 |
| WP4 단계 강조·홀드 | 완료 | 8절 1번 `steps` → `stepAt`(GRAPHIC 스키마 · `merge_step_runs` 자동 합침 · `step_times` · `Diagrams.tsx`), 2번 `EDITOR.holds` + 홀드 보호(`_hold_spans`·`_respect_holds`·`build_long_edit(holds=)`·정리 보드·이름 자막·게이트 보충). 프롬프트: `editor.md` holds, `motion.md`·`task_longform.md` steps. 테스트 `tests/test_sequences.py`(10/1 S122·S158–S160 을 옮긴 합성 픽스처). 남음: 3~16번(시퀀스·리듬 린트·진입 오프셋 등) |
| WP6 음악 응급 처치 | 완료(P0 1·2·3·5·6·7·8·10 일부) | 숏폼 업비트 기본 제거·롱폼 곡 물려받기, 챕터 곡 교체 끔(한 곡), 무드 없으면 음악 없이, 목소리 실측 기준 상대 레벨(`bgm_levels`), `lead_silence_s` 건너뜀, 끝→처음 되풀이 없이 앵커에서 다시, 비우기 2.5초·끝은 말 끝부터 코사인, 매니페스트 `enabled`·`commercial_ok`·`license` + 효과음 CC BY 출처. 남음: 4번(본문 음악 없음 — 앵커 구간만), 9번 `sound_report.json`, 마디 단위 끝(박 분석은 P1) |
| WP5 화면 결함 P0 | 완료(최소판) | 액자 샷 끔 · 자유 카드 순백·순흑 → 하우스 토큰 · 0.5초 무대(`stage_first`, ghost DSL 은 P1) · 숏폼은 롱폼 카드·모션을 줄이지 않고 다시 짬(`short_retype`) · `check.mjs` 서체 정규식 · 퇴장 순서(`exitLead`) · 썸네일 프레임(`_thumb_frames` + 눈 대비; 비전 `thumb_pick` 은 10번 문서 2번). 남음: F-7·F-9·F-11~F-14, 숏폼 v2, C 게이트 |
| WP7 자료 조달 v2 | 완료(P1 핵심) | `EVIDENCE`·`EVIDENCE_PICK` 스키마 · `prompts/agents/visual_researcher.md`·`stock_pick_v2.md` · 플레이북 `04_visual_evidence.md` · 스킬 `image_treatment.md` · `studio/assets/`(license · scholar(Crossref) · commons(media-list·depicts·분류) · local(④ 자료 폴더 색인·시트) · library · screenshot(C, 기본 끔) · ladder · graphics) · 자료 → 조달 → 모션 순서(확보 목록·컨택트 시트, `work/evidence.json`) · 보충 호출 1회(B1 어림) · `evidence` 템플릿 세 곳 + `Evidence.tsx`(EvidenceFrame·FocusMove·ArchiveCard·DocHighlight·BrowserFrame·그리드·나란히) · 게이트 B1·B2(`promote_hero`)·B6 · 자료 대장 CSV · 설정 `allow_quote`. 남음(P2): 미술관 6종 · OpenAlex OA · 원리 카탈로그 · Annotate·DetailZoom·Stack·Cutout · pHash·SigLIP · 프레스 허용 목록(B) · PDF 쪽 색인 · 숏폼 reelTop |
| WP11 색·룩 v3 | 완료(P0·P1) | 원본 전부를 한 시트로 컬러리스트 한 번(한 영상 한 톤) · 따뜻한 방 상한(`clamp_to_scene`, 프롬프트 `colorist.md` 따뜻한 방 규칙 — `colorist_v2.md` 내용을 합침) · 노출 감마는 밝기에만 · 화면 속 전등(화이트 늘림·무채색 후보 제외) · 원본 사이 얼굴 Lab 매칭(ΔE > 3 → ±6) · 게이트 F1 얼룩·F3 원본 사이·F4 클리핑·F6 BT.709 태그 · NVENC 실패 이유 · 하우스 트리트먼트 T1~T4(`grade/house.py`, 스톡·모션 클립아트·아카이브). 남음: 디더(10bit 프록시), `cleanup_filters` 의 잡음 측정 개선, 게이트 F2·F5·F7·B8 의 렌더 뒤 측정 |
| WP10 음악·사운드 v2 | 완료(P1 11·13·14·18·19 / 15·16·17 남음) | `MUSIC` 스키마 · 🎼 음악 감독(`music_supervisor.md`, 단계 `music` — 편집 검사 뒤, 검수와 동시에) · `studio/sound/cues.py`(큐 시트 → 초, 침묵·홀드·강도 3 우선, 12초 최소, 4초 틈 잇기, 규칙 폴백) · `normalize_long` 의 `music_cues` 보존 · 믹스 큐 창·역할별 레벨·숏폼 역할 · 효과음 팔레트 v2(문구 7종, 04c 매핑 표, 엄격한 카테고리, 60초 창 3개, 말 시작 피함, 하이라이트 → 본편 `page_turn`) · 게이트 D1·D3·D5·D6·D8·D9·D10 + `work/sound_report.json` + 리포트 '🎼 소리' · 입고 게이트 `scripts/sound_ingest.py` · 플레이북 `07_sound.md`·스킬 `music_direction.md` · `director.md` music.mood/notes. 남음: 키트(판 여러 개) 선택 `pick_kit`, 마디 리타깃(`retarget.py`)·판 크로스페이드, 스템·24bit·룸톤, carved·D1b, D2·D4·D7 측정, 박 앵커(P2) — 곡 입고는 운영자 몫(04b 4절) |
| WP9 재질·모션 v2·모션 검수 | 완료(P1 9·11·14 일부·15·16 일부·17 / F-7·F-9·F-11~F-14) | 토큰 v2(`motion.ts` 역할 이징·스프링·`durFor`·`placeIn` 등, `tokens.ts` `HOUSE`·`LIGHT`·`ELEV`·`paperShadow`·그리드·`TYPE_MIN`) · 하드코딩 그림자 → 광원 하나 · DSL v2(`ghost`·`mark`·`print`·`tint`·`place`/`unfold`/`write`·`hero`, 세 곳) · `studio/motion/lint.py` + `_lint_motion`(error → 수정 1회 → 규칙 보정, `motion_checks`) · 예제 교체(06c 후보 중 렌더·린트 통과 4개 + v2 데모 1개, 크림 종이 — 렌더 스틸로 확인) · `check.mjs` 28px·C4 0.5초 잉크(카드 예제 3개 고침) · 아트 디렉터 v2(R1~R18, `check`·`measured`·`scope`·`blocking`·`escalate_edit`, 스트립 `#seq`·폰 시트) · 게이트 B7 · 스킬·플레이북 투입. [제안] 값은 그대로 출발(`colSpan` 은 06b 의 `span` 이름만 바꿈). 남음: 구성 A~F 컴포넌트(13), 변주 선택기(12의 선택 부분), 진입 가족을 그래픽 템플릿에 적용, 카드 DSL `place`·`mark`·`peel`·숏폼 캔버스(18), 숏폼 구성 S1~S5(23), 스텝·보일(19), 이음매 스트립·작은 글자 크롭(06c P1-2·P2-1), `lint_card`(P1-3) |
| WP8 시퀀스·리듬 | 완료(3~9·11·12 / 10 은 03b 컴포넌트와) | 할당량 문구 7곳 교체 · `editing_craft.md`·`05_sequences.md` 투입(스킬 이름순 로딩) · BRIEF `show`·`function`·`sequences`·`central_question` · EDITOR `rhythm`·`peak_seg` · GRAPHIC·장면·카드 `sequence_id` · 시퀀스 컷(간격 0, 둘째 샷부터 등장 없음) · 역할별 진입·퇴장 · 리듬별 강조 간격 · 뜯어보는 화면 자막 숨김 · 게이트 A11~A17. 남음: `sequence_plan` 의 샷 단위 낱말 컷·내려앉기, `tx_for`·`sfx_for`, 뜯어보기·문서 읽기 렌더(03b) |
| WP12 타임라인 검수·팀 등록 | 완료(검수·게이트 E) | `TIMELINE_QA`(R1~R6 · 발견 종류 13 · 처치) · `prompts/agents/timeline_review.md` · `Studio.review_timeline` · `studio/export/events.py`(이벤트 목록: 컷·그래픽·홀드·시퀀스·효과음·절정) · `gate.gate_e`(가중 ≥ 3.8 · 2점 이하 없음 → 통과, high·blocking → 검토 필요) · `gate_feedback`(게이트는 통과했는데 검수가 잡은 것 → `work/gate_feedback.json`) · `output/⚠검토필요.md` · 창 배너 · 리포트 첫 절 · eta `export@ai` · 설정 `agent_effort`/`agent_models` 키. 남음: 13번 문서의 음악 에이전트·visual_researcher(WP7·WP10), 부분 재호출 블록(`escalate_edit` 와 함께 WP9) |
| 디자인 v3 종이 콜라주(운영자 2026-10-02 요청) | 완료 | `docs/디자인_v3_종이콜라주.md` — 서체 전면 교체(송명·고운바탕·Instrument Serif·Playfair italic, 함렛은 번들만) · 자막(흰 상자 + 검은 테두리 + 오프셋 그림자, Pretendard 500 · 38px) · `collage` 표면 하나(`STYLE_MIX=False`) · `components/press/`(PaperStage·PrintText·YearNumeral·Ground·CutoutImage·Highlighter·NameChip·DocSheet·QuoteOverlay · CollageScene · CollageTitle/Chapter) · 문서 `DocPage` · 보드·키워드·숫자·인용 카드 재디자인 · 오려 내기 `studio/assets/cutout.py` · 리서처 `collage`·`display`·`quote` · 얼굴 15~55%·실물 자료 ≥ 30% · 스톡 10~18개 · 디자인 색(`forest`/`brand`). 남음: 숏폼(ReelShort) 서체·재질 v3, 인물 오려 내기 모델(지금은 GrabCut + 경계 검사), 영상 스톡의 콜라주(움직이는 오린 화면) |
| 14 Claude 총괄 제작(운영자 2026-10-02 요청) | 완료(1차) | `docs/upgrade/14_클로드_총괄_제작.md` — 🔎 리서치 디렉터(웹 조사 단계 `research`, `RESEARCH`, 조사노트.md) · 트리트먼트(`BRIEF.treatment`: 콘셉트·대본 흐름대로의 화면 구성표·시그니처 장면·소리 콘셉트) · 🛠 시그니처 장면 빌더(HTML 카드, Jitter 모션 레퍼런스 프레임을 보고) · 조사 노트의 커먼즈 파일 먼저 · 효과음 directed(실제 파일로 받기 — 예전엔 하나도 안 들림) · 내 음악 폴더에서 음악 감독이 곡 선택 · 실제 응답 모델 확인 · 에이전트별 스킬 노트. 남음: Lottie 라이브러리, 시그니처 장면 렌더→보기→고치기 반복, `_fill_gaps` 를 Claude 보충 호출로 |
| 디자인 v4 모던 모션(운영자 2026-10-02 레퍼런스 8장) | 완료(1차) | `docs/디자인_v4_모던모션.md` — 채널 오렌지 `#FC5400`(`ember` 기본) · 밝은/어두운 무대 · Pretendard 역할표(이탤릭 세리프 강조 한 어절) · `components/modern/`(헤드라인·칩·말풍선·UI 패널·기기 목업·아이소메트릭·큰 숫자·영상 위 글자·오린 장면·화자 카드) · 타이틀/챕터/엔드카드 · 자막 · 표면 기본 `modern` · 배분 v4(얼굴 ≤20%·자료 ≥45%·얼굴 없는 구간 90초, 게이트 A8 8~40%·B1 ≥40%) · 프롬프트 v4 어휘. 남음: Claude GSAP 자유 모션, 숏폼 v4, 콜아웃 재질, 인물 사진 구도 검사 |
| 컷 편집 v2(운영자 2026-10-02: 내용 삭제·헛기침 NG·통째 누락) | 완료 | `studio/text/cut_review.py` — 규칙 판단은 전부 후보, Claude 가 발화마다 최종 결정(점수·회차 표시) · `studio/media/vocal_events.py`(기침·헛기침·숨: 단어 없는 말소리 토막) → `audio_events` 로 자름(AI 없으면 떨어진 파열음만) · `_mark_meta` 66 · 프롬프트 v2(대본과 달라도 내용이면 남김). 남음: 실제 NG 녹음으로 확인(화자 원본 필요) |
| 운영자 2026-10-02 추가 요청 | 완료 | 모션 DSL v4 부품(panel·chip·bubble·device·iso) + 린트 L27 겹침 · 자동 모션 효과음(전환·등장·부품, D5 cap 8) · 설정 창 모델(Fable 5.1 포함)·사고 강도·에이전트별 표 · 사용량 장부 `user/usage.json` + 한도 창(rate_limit_event) 표시 |
| 운영자 2026-10-03 첫 실제 영상 피드백 | 진행 | ① 두 파일이 같은 대본 전체 → **best_take**(`passes.script_units`·`choose_takes`: 대목마다 더 잘 나온 회차, 다른 구도면 교차 — 02 문서 3-2 '문장 단위 교체'+3-3 'B캠'의 구현; `best_pass` 모드는 **대체됨**, 코드는 `_order_by_script`·`_repair_duplicates` 호환용으로만 남음) ② 끊긴 앞부분 `_mark_false_starts` · 소리 NG 의심 단어(`vocal_events kind=word`) ③ 전면 그래픽 사이 화자 플래시(`bridge_fullscreen_gaps`·`LongForm coverSpans`) ④ 숏폼 콜드 오픈 뒤 구간이 잘리던 `quantize` ⑤ 설정 모델·강도 통합(드롭다운, 기본 Opus·xhigh) ⑥ 화면은 말한 것과 같은 것: 로고 = pip 이름표 1회·4초(`to_graphics`·`LOGO_MAX_SEC`), 게이트 B11 같은 장치 되풀이(`motif` 키·제목 구절, 수리 `_trim_motifs`), 프롬프트(감독·모션·자료 리서처·플레이북 06) ⑦ 보충 카드는 개념 구절만(`card_worthy`·`noun_phrase`, 없으면 안 넣음) ⑧ 스톡 재검색(`retry_query_en`, `StockResearcher._pick_round`) ⑨ 💾 디스크 가득(ENOSPC): 렌더가 프록시를 임시 폴더로 복사하지 않음(`render.mjs localMedia`) · 렌더 전용 임시 폴더 · 남은 임시 파일 청소 · 작업 전 공간 점검과 예전 작업 편집본 정리(`studio/storage.py`) ⑩ 🛫 렌더 전 자산 확인(`studio/render/preflight.py`): 모션 기기 화면의 `pixabay:` 가 해석되지 않아 404 로 렌더가 멈춘 것 — 해석을 image·device 둘 다로(`stock_refs`), 검수 뒤 고친 장면도, 렌더 직전 모든 파일 경로 확인 |
| 운영자 2026-10-04 피드백(호흡·스톡·논문 캡처) | 완료 | ① **호흡 설계** `studio/edit/breath.py`(이어 붙인 곳마다 문장 안 0.3 · 문장 0.6 · 문단 1.0 · 여운 1.3초를 원본 무음으로, 말소리·지운 구간·다른 keep·파일 경계는 넘지 않음 — 실측 쉼 중앙값 0.15초 · 0.4초 넘는 쉼 6분에 8곳) · `Pipeline._breathe`(롱폼 `_make_cuts`, 숏폼은 길이 상한 안 `budget`) · calm `max_silence` 1.0 → 1.4초(줄여도 0.75초) · 숏폼 기본 `shorts_calm`(`JobSpec.shorts_pace`, 예전 `shorts` 는 선택) · `EDITOR.pauses`(발화 뒤 0.5~1.6초, `normalize_long` 보존) · 편집 검사 '긴 무음' 기준 `_verify_silence` · 컷 총괄 프롬프트(문장 사이 숨은 자르지 않음) · 리포트 '🫁 호흡'. ② **스톡 = 세계 + 역추상화 + 비전 확인**: `TREATMENT.world`(누구·어디·언제·사물·결·이 세계가 아닌 것) → `world_block` 이 자료 리서처·모션·자막 지시, 비전 선택(`pick_evidence`), 아트 디렉터·타임라인 검수·장면 수정에 · `EVIDENCE.stock.angle`·`alt_queries`(역추상화: literal·detail·process·place·metaphor, 1~4낱말 구체 명사) → `StockHub.search` 가 함께 찾아 섞음 · `query_variants(min_words=2)`(한 낱말 동음이의어 금지) · `rule_choice`(비전이 없거나 실패: 태그에 핵심 낱말, AI·애니·로파이 태그 제외 — 첫 후보를 그냥 쓰지 않음) · 모션 장면 그림 부품 `resolve_images` 를 비전 선택으로(캐시 `img-v2`, 장면의 말·제목, 거절 → 새 검색어 1회 → 부품만 뺌) · 조달 실패는 모션 디자이너 확보 목록에 '비워 두지 않는다'로(`brief_for_motion`). ③ **화면 캡처 가드** `screenshot.blocked_reason`(Cloudflare·CAPTCHA·접근 거부·오류·로그인 벽) + `ink_ratio`(거의 빈 화면) — `screenshot.mjs` 가 제목·주소·본문을 넘기고 봇 확인 화면은 8초까지 기다림 → 버리면 출처 카드. 캡션 낱말 중간 자르기 `clip_words`. ④ 스킬 노트(편집 감독·자료 리서처·숏폼·총괄 감독·아트 디렉터·모션) 리서치 반영 — 출처는 각 노트 끝. 테스트 `tests/test_breath.py` · `test_stock_world.py` · `test_screen_guard.py` |
| 운영자 2026-10-04 피드백(보면서 일하기·토큰·작업 시간) | 완료 | ① 👁 **디자이너 자기 검토** `Pipeline._designer_self_review`(검수 단계 첫머리: 모션 장면·자유 카드·시그니처를 렌더해 만든 역할에게 안착 화면 + 움직임 6칸을 보여 주고 고칠 것이 분명한 것만 고침 — 린트·카드 검사가 나빠지면 되돌림, `prompts/agents/self_review.md`) · 아트 디렉터 지적 수정에 정지 화면 + 움직임 시트(`qa_images`) · 카드 검사 실패 화면(`check.mjs shot`) · 검수 정지 화면 원본 해상도 · 그림 한도 `studio/director/images.py fit_images`(vision 문서: 20장 넘으면 2000px·긴 변 2576·장당 10MB·요청 32MB·실제 형식). claude-eye 는 API 키로 따로 부르는 CLI 라 넣지 않음(같은 일을 구독으로 이미 함). ② 🪶 **토큰**: 디자인 규칙이 필요 없는 역할은 가벼운 시스템(`LEAN_AGENTS`), 반복 역할은 공통 자료를 시스템 끝에(`ctx_in_system`, CLI 시스템 캐시), 같은 역할 동시 호출은 첫 호출 뒤 15초(`_stagger`), 로그에 캐시 읽기·쓰기, '웹 조사' 오집계 수정. ③ 🕒 **작업 시간**: 음성 인식 배치를 여유 VRAM·지난 실측으로(`batch_for_gpu`·`user/asr_tuning.json` — 10/03 19.6분 음성에 12.2분), 대본 맞추기가 🔎 조사를 기다리지 않게(같은 줄 + `_await_stage`), 작업 끝 ⏱ 단계별 시간. 테스트 `tests/test_vision_tokens.py` |
| 운영자 2026-10-04 피드백(자료 출처·구글 이미지·이해의 설계) | 완료 | 실제 API 로 먼저 확인: 커먼즈 일반 검색은 스톡 대용이 못 됨('foam model' → 바다 거품, 익명 호출 한도) → 넣지 않음. ① 🏛 미술관 오픈 액세스 `studio/assets/museums.py`(시카고·메트 v1.1·클리블랜드, CC0, 키 없음, 낱말 맞는 결과만) ② Google 이미지 `studio/stock/google.py`(SerpApi, 재사용 가능 결과는 원문 페이지에서 라이선스 재확인한 것만 · 인용 C 는 tier_max C + 설정 인용일 때만, 공식 페이지 og:image 포함, 출처·사유 표기) — 출처 표기만으로는 권리가 생기지 않아(저작권법 제28조) 스크래핑·무단 사용은 하지 않음 ③ 사다리 `_wider`(후보가 모자라면 넓혀 한 시트로 비전 선택) · 받기 실패 대체는 태그 전부 맞을 때만 ④ 자료 리서처 2-0 '이해를 설계한다'(개념 문장 = 확인된 실제 사례 `role: example`), 고르기 기준 '이해시키는가'. 테스트 `tests/test_web_sources.py` |
| 운영자 2026-10-04 피드백(디자인 taste · 'PPT 같다' · Jitter 공부) | 완료 | 원인 넷: ⓐ `merge_plan` 이 카드·시그니처 장면의 GSAP `timeline` 을 버림(10/04 계획 카드 6개 모두 안무 없음 — 수정, `plan-v7`) ⓑ 예시가 제목 + 목록 → **구도 원형 12**(`prompts/layouts.md`)와 렌더로 확인한 예시 12개(`card_examples.json`) ⓒ 검사가 v3 기준·마스크를 잘림으로·한국어 줄바꿈 → `check.mjs` v4·`data-split-mask`·`aria-hidden`·`keep-all` ⓓ 구도 체계 없음 → `archetype`. 카드 런타임 **GSAP 무료 플러그인**(SplitText·DrawSVG·MorphSVG·MotionPath·CustomEase, 렌더러·검사 같은 등록). 모션 디자이너: 개념 장면의 기본 형식 = 자유 카드 8~14곳, DSL 장면은 보조 0~6. **🎨 스타일 프레임**(영상마다 룩 한 장 + 규칙 → 디자인 역할 전원이 그림으로) · **🎯 레퍼런스 보드·장면 평가 기억**(`user/taste`, 결과 화면 👍/👎, 없으면 하우스 예시 보드) · **🧑‍⚖️ 시안 경쟁**(시그니처 장면 3안 → 렌더 → 심사 → 지적 반영, 설정 `design_variants`) · 아트 디렉터 R12 v4·R20 결. Jitter 템플릿 공개 문서 측정(문서는 저장소 밖) → 움직임 표·스킬 노트. 테스트 `tests/test_taste.py`·`test_card.py`·`test_gui.py`, E2E `e2e_studio.py` |
| 운영자 2026-10-04 피드백(모니터 질감 · 글자 · 떠다니기 · 전환 · 느린 확대 · 하이라이트 길이) | 완료 | ① 🖥 **화면 질감** `ScreenLook.tsx`(릴스 레퍼런스를 확대해 본 층: 흐림 0.6px · 개체 빛 번짐 · 중성 서브픽셀 격자·주사선 · 입자 · 비네트 — soft-light 라 흰 판이 묻히지 않음, 푸른 기운 제거, 설정 `screen_look`) ② **글자 다이어트** `check.mjs too_much_text`(전면 48 · split 32 · overlay 20) + 아이콘 어휘 `prompts/icons.md`(Lucide 71, ISC) + 예시 12개를 아이콘·픽토그램으로 + R21 — 그 과정에서 `clean_card` 가 SVG `viewBox`·`linearGradient`·`clipPath` 를 지우던 버그(소문자 비교) 수정 ③ **되튐 없음·떠다니기** `gentleTimeline`·`data-float`·앰비언트 카메라, 정착 시각은 떠다니기·나가기·장식을 뺀 등장 끝 ④ **안무 전환**(`LongForm Choreo`: 얼굴에서 열리는 원 · 흩어짐 `scatterExit` · 다이브 · 원으로 닫힘, `data-carry` 매치 컷, 디졸브·와이프 없음 — 참고: School of Motion 'six essential transitions', Material motion choreography) ⑤ **인물 확대 아주 느리게**(푸시 +3~6.5%, 들어감 3초 · 빠짐 3.5초, 사인 곡선) ⑥ **하이라이트 20~30초**: 조각 = 이어지는 발화 한 생각(`seg`~`end_seg`), 모자라면 뒤 발화를 붙여 채움(`fit_highlight_runs`), 호흡 설계 거침. 계획 키 `plan-v8`. 테스트 `test_card.py`·`test_core.py`·`test_punch.py`·`test_autopilot.py`, E2E `e2e_studio.py` |
| 운영자 2026-10-04 피드백(AI 슬롭·불안정 · Promptible/HyperFrames 스킬 · 끊긴 앞부분 · 그래픽 타이밍 · 효과음 · 자료 폴더 · 제목 라벨) | 완료 | 두 저장소는 '설치'가 아니라 생각을 옮김: ① 🧑‍⚖️ **독립 장면 심사** `Pipeline._critic_pass`(카드·모션 장면마다 만든 역할이 아닌 심사 — 하드 실패·점수 → 수정 → 재심사 → 탈락이면 키워드 카드, `card_critic`·`critic_verdict`, 설정 `design_critic`) ② **한 세계 + 카메라**(`data-world`·`data-camera`, `camera_world` 원형·예시, 검사 `camera_hold_empty`·배율 곱한 글자 크기) ③ 슬롭 금지 목록(모션 0-4·R22·심사·자기 검토)과 '원형은 상속' ④ 그래픽 등장 −0.35~0.5초·퇴장 +0.6~1.0초·최소 5초 ⑤ 효과음 게인 +7~8 dB, 파일 없으면 경고 ⑥ 절어서 다시 시작한 토막 자르기 ⑦ `topic.py` 라벨 파싱(제목·부제·키워드·썸네일 → 그대로) ⑧ 자료 폴더 전부 배치(안 쓰면 보충 호출·리포트). HyperFrames 레지스트리 블록 이식·렌더 전 '장면 시트 확인' 단계·영상 자료(화면 녹화)·키네틱 자막은 남음 |
| 운영자 2026-10-04 요청(디자인 벤치마킹 도구 — 깃 없이 끌어다 놓기) | 완료 | 🎯 **레퍼런스 분석기** `studio/agents/reference.py` + 창 `studio/gui/reference_dialog.py`(메인 창 '🎯 레퍼런스' · `run_reference.bat` · `python -m studio reference`): 사진·영상(릴스)을 끌어다 놓으면 코드가 재고(컷 `detect_cuts` · 샷 길이 · 움직임 · 팔레트 · 톤 · 선 밀도 → 컷 시트) Claude 가 보고(`REFERENCE` — 스타일 프레임과 같은 `rules` + 기법마다 우리 런타임 레시피 + 가져오지 않을 것) `user/taste/refs/` 에 저장 → `Studio.taste_notes`(규칙 블록)·`taste.board_images`(시트)로 모든 디자인 역할에 자동. 🧪 디자인 벤치는 '최근 작업 › 🧪 디자인 벤치'(기획 새로 · 렌더 없이 · 장면 시트 열기). 테스트 `tests/test_reference.py`. |
