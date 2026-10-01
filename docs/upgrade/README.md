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
| WP8 시퀀스·리듬 | 완료(3~9·11·12 / 10 은 03b 컴포넌트와) | 할당량 문구 7곳 교체 · `editing_craft.md`·`05_sequences.md` 투입(스킬 이름순 로딩) · BRIEF `show`·`function`·`sequences`·`central_question` · EDITOR `rhythm`·`peak_seg` · GRAPHIC·장면·카드 `sequence_id` · 시퀀스 컷(간격 0, 둘째 샷부터 등장 없음) · 역할별 진입·퇴장 · 리듬별 강조 간격 · 뜯어보는 화면 자막 숨김 · 게이트 A11~A17. 남음: `sequence_plan` 의 샷 단위 낱말 컷·내려앉기, `tx_for`·`sfx_for`, 뜯어보기·문서 읽기 렌더(03b) |
