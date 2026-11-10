# 측정은 Opus 를 가리키고, 영상 판단은 미검증이다

Fable 5.1 이 Opus 5.5 보다 낫다는 독립 측정은 없고, 공개된 종합 지표는 거의 모두 **Opus 5.5 가 같거나 앞선다**고 보여 준다. 사람이 두 웹앱을 놓고 고르는 Arena 에서도 Opus 5.5 가 약 60점 앞선다. Fable 이 측정으로 앞선 곳은 문장의 자연스러움을 재는 AA-PersonalityBench 하나다. 그러나 **모션 그래픽, GSAP 코드, 영상 연출, 컷 판단, 미감 심사를 두 모델로 직접 비교한 공개 자료는 찾지 못했다.** 이 영역에서는 어느 쪽이 낫다고 말할 근거가 없고, 지금 나와 있는 것은 웹앱 투표와 한두 사람의 시험에서 끌어온 간접 증거다. 사람들이 Opus 를 쓰는 주된 이유도 취향이 아니라 토큰 단가 2.5배 차이, 요금제 접근성, 기본 모델 지위다. 따라서 **전역 Opus 5.5 는 근거가 충분하지만, 총괄 감독과 컷 총괄의 Fable 5.1 배정은 입증되지 않은 가설**이다. 호출이 두 번뿐이라 비용이 작고 되돌리기도 쉬우므로 잠정 유지하되, Fable 을 다른 역할로 넓히지 말고 컷 총괄부터 A/B 로 판정하기를 권한다.

## 종합 측정은 Opus 쪽이고, Fable 의 측정 우위는 문장 결 하나다

Artificial Analysis(AA) 수치는 여러 판이 돌아다녀서 섞으면 결론이 틀어진다. 출시 기사는 Fable 5.1 을 66(개정 전, Opus 5 는 63)으로 적었고 ([AA 기사](https://artificialanalysis.ai/articles/claude-fable-5-1)), 다른 요약은 53(v4.3)과 50(v5.0, xhigh)을 인용하며, 한 2차 자료는 Opus 5.5 58 대 Fable 5.1 53 이라고 적었다 ([LMSPedia](https://lmspedia.org/claude-opus-5-5-vs-fable-5-1/)). 이 보고서는 두 모델을 **같은 페이지·같은 조건(Max, Default Fallback)** 으로 나란히 놓은 AA 비교 페이지 값 하나만 쓴다. 조사 시점에 이 페이지의 지수 판 번호와 날짜는 확인되지 않았으므로 절대값보다 같은 조건 안의 차이로 읽어야 한다.

| AA 비교 페이지 (Max, Default Fallback) | Opus 5.5 | Fable 5.1 |
|---|---|---|
| Intelligence Index | **59** | 49 |
| Terminal-Bench 4.0 | 59.6% | 52.0% |
| FrontierCode 2.0 | 46.4% | 31.6% |
| HLE-Diamond | 67.9% | 60.1% |
| AA-Omniscience | 48 | 46 |
| GDP.pdf | 26.2% | 26.2% |
| 작업당 비용 | $10.04 | $12.99 |
| 작업당 출력 토큰 (그중 사고) | 173k (120k) | 118k (71.4k) |
| 평균 종료까지 시간 | 831초 | **428초** |
| PersonalityBench 웅변·자연스러움·어휘 다양성 선호 | 8%·10%·24% | **92%·90%·76%** |

출처는 모두 [AA 비교 페이지](https://artificialanalysis.ai/models/comparisons/claude-opus-5-5-vs-claude-fable-5-1)이고, 한 가지가 눈에 띈다. **Fable 은 단가가 2.5배인데 작업당 비용은 약 1.3배**다. Opus 5.5 가 Max 에서 훨씬 오래 생각하기 때문이다. 단, 이 값은 AA 의 벤치마크 과제에서 Max 로 잰 것이고 Choi Studio 의 xhigh·high 호출에 그대로 옮길 수는 없다. PersonalityBench 가 어떤 언어로 평가됐는지는 노트에서 확인되지 않아, 한국어 카피에 대한 증거로 쓸 수 없다.

사람의 선호를 직접 재는 쪽도 방향이 같다. 2026-09-23 Code Arena WebDev 스냅숏에서 Opus 5.5(Max)는 **1818 ±21**, Fable 5.1(Max)은 **1755 ±11** 이고, Frontend 는 1848 ±25 대 1789 ±12, React 는 1851 ±26 대 1804 ±13 으로 구간이 겹치지 않는다. 다만 Opus 쪽 표는 1,219표로 Fable 의 4,916표보다 적다 ([AI IDE List](https://aiidelist.com/blog/claude-opus-5-5-code-arena-webdev)). 10월 26일 수치는 1807 대 1742 로 격차가 유지된다 ([FullStack](https://www.fullstack.com/blog/claude-opus-5-5-vs-fable-5-1-when-is-fable-worth-it)). 이는 지금까지 나온 가장 강한 시각 관련 측정이지만, 재는 것은 **웹앱 한 벌의 첫인상**이지 시간축 안무나 영상 안의 위계가 아니다. Arena Text 는 1509 대 1503 으로 사실상 동률인데 표본 수가 공개되지 않았다 (같은 FullStack 글). Design Arena 의 Opus 5.5 1466 대 1334 는 Fable 5 와의 비교이고 검색 요약으로만 확인돼 결론에서 뺐다.

벤더 수치는 측정이 아니라 벤더 주장으로 읽어야 한다. Anthropic 표는 Terminal-Bench 4.0 을 66.4 대 55.8 로 적었는데, AA 재측정은 59.6 대 52.0 이다. 방향은 같고 절대값과 격차는 줄었다 ([Anthropic](https://www.anthropic.com/news/claude-opus-5-5), 요약 도구로 전달된 값). 이 표의 항목은 코딩·에이전트·지식 작업이며 미감이나 연출은 없다. 또 Anthropic 이 Fable 의 강점으로 내세운 장기 자율 작업은 Opus 5.5 와 나란히 잰 숫자 없이 서술로만 제시된다.

## 다섯 과제 모두 직접 증거가 없고, 간접 증거는 서로 엇갈린다

모션 그래픽과 영상 연출에 대해서는 **시각 결과물과 표본 수를 공개한 GSAP·Canvas·모션·영상 나란히 비교를 찾지 못했다.** 존재하는 시각 비교는 표본이 한두 개이고, 같은 방향을 가리키지도 않는다. Simon Willison 의 SVG 펠리컨 시험에서 Opus 5.5 Max 는 두 번 모두 128,000 출력 토큰 한도에 걸려 답을 내지 못했고, 다른 날 시험한 Fable 5.1 Max 는 그가 본 Anthropic 모델 중 최고의 펠리컨을 냈다 ([9월 22일](https://simonwillison.net/2026/Sep/22/opus-and-sol-and-luna/), [9월 1일](https://simonwillison.net/2026/Sep/1/claude-fable-5-1/)). 프롬프트 하나의 결과이고, 다른 강도의 Opus 는 답을 냈다. Every 의 약 일주일 시험에서는 디자이너 Tyler Nishida 가 제약·스타일 가이드·시각 개념을 지키게 조종하는 데 Opus 5.5 가 Fable 보다 훨씬 낫다고 했고, Kieran Klaassen 은 3D 장면에서 Opus xhigh 를 더 높게 봤다. 반면 같은 글의 Mike Taylor 는 브랜드 지침을 지키는 슬라이드에서 Opus 가 로고와 색을 틀렸고 Fable 이 더 잘했다고 했으며, 글쓰기와 큰 문제에는 Fable 을 선호한다고 했다 ([Every](https://every.to/vibe-check/vibe-check-opus-5-5-is-pulling-our-codex-converts-back-to-claude)). 모두 이름 있는 개인의 판단이며 건수가 없다.

| 과제 | 직접 증거 | 가장 가까운 간접 증거 | 판단 |
|---|---|---|---|
| 영상 기획·이야기 구조 | **없음** | Anthropic 의 장기 추론 포지셔닝(벤더, Fable), Taylor 의 선호(개인, Fable), HLE·지수(측정, Opus, 관련성 약함) | 판정 불가 |
| 컷·편집 판단 | **없음** | 위와 같음. 긴 문서 대조를 잰 공개 비교도 없음 | 판정 불가 |
| 정적 디자인·조종성 | 표본 2~3건, 방향 엇갈림 | Arena Frontend·WebDev(측정, Opus) | Opus 약우세, 표본 빈약 |
| HTML·GSAP 모션 코드 | **없음** | Arena WebDev(움직임 품질 측정 아님), Terminal-Bench(코드 정확성) | Opus 쪽으로 기우나 미검증 |
| 이미지 심사·미감 판정 | **없음** | Chartography 89.0 대 88.4(벤더, 차트 판독) | 사실상 동률, 미감은 미검증 |

이미지 쪽의 차이는 작고 재는 대상도 다르다. Anthropic 은 Opus 5.5 가 공간적 의미, 즉 화살표가 어떤 상자를 잇는지나 두 도식의 차이를 더 잘 읽는다고 문서화했고 ([Opus 5.5 프롬프팅](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5.md)), Fable 은 자르고 확대하는 도구로 반복 확인할 때 최선이라고 적었다 ([Fable 5.1 프롬프팅](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1.md)). 어느 쪽도 그림이 아름다운지를 판단하는 능력을 주장하지 않는다. 디자인에서 더 쓸모 있는 문서는 다른 대목이다. Anthropic 은 Opus 5.5 가 지시 없는 프론트엔드에서 몇 가지 기본 스타일로 돌아가며, 막연한 금지보다 구체 패턴을 이름 대어 막는 것이 효과적이라고 적고, 크림색 배경·헤드라인의 이탤릭 강조어·알약 버튼 금지를 예로 든다 (같은 Opus 5.5 페이지). 이 항목은 `CLAUDE.md` 가 설명하는 v4 디자인의 이탤릭 세리프 강조 어절과 알약 라벨, 하우스 재질의 크림 종이와 겹친다(진행 중인 v5 기준은 확인하지 않았다). 'AI 느낌' 불만의 일부는 모델 등급이 아니라 **하우스 스타일이 모델의 기본값과 겹치는 데서 올 수 있고**, 그렇다면 Fable 로 바꿔도 풀리지 않는다. 이는 추론이며 측정된 사실은 아니다.

## 사람들은 취향보다 가격과 접근성 때문에 Opus 를 쓴다

증거 강도 순으로 보면 첫째가 가격이다. 입력·출력 토큰당 Opus 5.5 는 $4/$20, Fable 5.1 은 $10/$50 이다 ([Opus 5.5 개요](https://platform.claude.com/docs/en/models/opus-5-5/overview.md), [Fable 5.1 개요](https://platform.claude.com/docs/en/models/fable-5-1/overview.md)). 둘째는 요금제다. Pro 에서는 Fable 이 사용량 크레딧으로만 돌아가고, Max 에서는 주간 한도의 최대 50%까지 쓸 수 있으며 다른 모델보다 한도를 빨리 소모한다 ([지원 문서](https://support.claude.com/en/articles/15424964-claude-fable-5-on-your-plan)). 소모 배수는 공개되지 않았다. 셋째는 기본값과 공식 권고다. Anthropic 은 모델이 불확실하면 Opus 5.5 로 시작하고, Fable 은 까다로운 추론·장기 작업이거나 Opus 를 높은 강도로 돌려도 평가를 통과하지 못할 때 쓰라고 안내한다 ([모델 개요](https://platform.claude.com/docs/en/about-claude/models/overview.md)). 이름과 가격이 곧 측정 순위는 아니라는 뜻이다.

취향은 가장 얇은 이유다. Every 의 디자이너 한 명과 Arena 투표가 전부다. 영상을 코드로 만드는 두 저장소 [lemo-opuscar](https://github.com/lemomo-ai/lemo-opuscar) 와 [awesome-opus5-5-videos](https://github.com/yihui-dev/awesome-opus5-5-videos) 는 Opus 5.5 로 만들었다고 밝히지만 Fable 과 비교한 기록이 없다. 'Opus 에 맞춰 조율했다'는 말은 작성자의 작업 방식에 대한 진술이지 Opus 가 낫다는 증거가 아니다. 속도는 이유로 삼기 어렵다. Anthropic 은 Fable 을 더 느리다고 분류하고 초당 토큰도 Opus 가 많지만(114 대 87), AA 의 Max 측정에서는 사고가 길어 Opus 의 완료 시간이 약 두 배다. Fable 의 약점으로 거론되는 큰 작업의 느림과 장황함도 있지만 ([CodeRabbit](https://coderabbit.ai/blog/fable-5-1-model-review), 검색 요약), 장황함은 AA 의 문장 선호 결과와 상충하며, Fable 5 시절 불만이 5.1 에 섞여 있다.

## Choi Studio 에서 Fable 의 문서상 강점은 두 호출에 그대로 닿지 않는다

현재 `studio/agents/studio.py` 의 `ROUTING` 과 `user/settings.json` 을 확인한 결과, 지시하신 설정대로 전역은 Opus 5.5 xhigh, Fable 5.1 은 `director`·`cut_editor` 두 역할뿐이다(둘 다 xhigh). 이 두 역할은 영상의 구조와 컷 정확도를 정하므로 가장 중요한 자리라는 직관은 합리적이다. 그러나 Anthropic 이 말하는 Fable 의 강점은 긴 자율 실행과 크롭 도구를 쓰는 반복 시각 확인인데, **두 역할은 작업당 한 번, 웹·크롭 도구 없는 구조화 호출**이다. 그 강점이 이 호출에서 살아난다는 근거는 없다. 또 Anthropic 문서 사본은 이전 모델용의 세세한 프롬프트가 Fable 품질을 떨어뜨릴 수 있으니 단계 나열을 빼고 A/B 하라고 권한다(번들 `shared/model-migration.md`, 라이브 페이지에서 해당 문장을 재확인하지 못함). 그래서 Fable 이 지금 프롬프트로 지더라도 '이 프롬프트의 Fable'이 졌다는 뜻일 뿐이다. 코드 주석에 남은 2026-11-09 감사도 규칙량이 취향을 밀어낸다는 비슷한 우려를 적고 있다.

| 역할 | 현재 | 권고 | 근거 수준 |
|---|---|---|---|
| `director` | Fable xhigh | **잠정 유지, A/B 2단계** | 직접 증거 없음 |
| `cut_editor` | Fable xhigh | **잠정 유지, A/B 1단계** | 직접 증거 없음, 사람이 채점 가능 |
| `editor`·`shorts` | Opus xhigh | 유지 | 직접 증거 없음, 바꿀 근거도 없음 |
| `copy` | Opus xhigh | 유지. Fable 시험 시 첫 후보 | Fable 문장 신호는 있으나 한국어 미확인 |
| `setpiece`·`motion`·`style_frame` | Opus xhigh | 유지. Fable 로 넓히지 않음 | 모션 직접 증거 없음, Arena 는 Opus |
| `card_revise`·`motion_revise` | Opus high | 유지 | 반복 호출이 많아 단가 영향 큼 |
| `art_director`·`card_critic`·`design_judge`·`timeline_review` | Opus high | 유지 | 미감 증거 없음, 도구 없는 호출 |
| `research`·`stock` | Opus high | 유지 | 비교 증거 없음 |
| `captions`·`music`·`colorist`·`stock_pick`·`portrait_pick` | Sonnet | 변경 없음 | 이번 조사 범위 밖 |

비용은 **실측이 없다.** `user/usage.json` 의 기록은 E2E 가짜 CLI 값이다. 프롬프트 크기로 추정하면 두 역할의 Fable 추가 비용은 같은 토큰을 쓴다고 가정할 때 API 환산 약 $2.6(범위 $1.5~$4)이고, 전체 작업 $15~35(역시 신뢰도 낮은 추정)의 10~15%다. AA 의 작업당 비율 1.3배를 그대로 대입하면 추가 비용은 $0.5 수준까지 줄어든다. 실제 사용 경로는 Claude 구독이므로 돈이 아니라 5시간·주간 한도로 나타나며, 이 소모 비율은 측정되지 않았다. 거절 안전장치는 두 모델 공통의 문제지만, 현재 `Studio.call` 은 영문 "model" 이 들어간 오류만 전역 모델로 다시 부르므로 API 경로의 한국어 거절 메시지는 재시도되지 않는다. 또 응답 모델 불일치 경고는 Opus 요청에만 걸려 Fable 요청에 다른 모델이 답해도 경고가 뜨지 않는다. 이 두 지점은 수정 제안이며 코드는 바꾸지 않았다.

## 결론: 현재 설정은 잠정 유지하고, 컷 총괄부터 판정한다

**전역 Opus 5.5 는 유지한다. `director`·`cut_editor` 의 Fable 5.1 도 지금은 유지하되 '검증 대기' 상태로 두고, 다른 역할로 넓히지 않는다.** 교체할 측정도, 유지할 측정도 없고, 변경 비용은 두 줄이며, 두 호출의 비용은 전체에서 작기 때문이다. 다만 입증 책임은 Fable 쪽에 있다. 아래 시험에서 기준을 넘지 못하거나 다음 몇 작업 안에 시험을 돌리지 못한 채 한도 압박이 생기면 Opus 5.5 로 돌리는 것이 기본값이다. 지금 근거만으로 Fable 이 영상 기획이나 컷을 더 잘한다고 말할 수 없고, Opus 가 더 잘한다고도 말할 수 없다.

### 판정을 내릴 공정한 A/B

두 역할은 **따로** 시험해야 한다. 컷 총괄의 결과가 `self.utts` 를 거쳐 총괄 감독의 공통 자료로 들어가므로, 함께 바꾸면 어느 역할의 효과인지 분리되지 않는다. 입력은 같은 작업 폴더를 복사해 고정하고, 강도는 양쪽 모두 xhigh 로 맞춘다. `user/settings.json` 은 설치본 전역 파일이라 복사본마다 다르게 둘 수 없으므로, 회차마다 `agent_models`·`agent_effort` 를 바꾸고 **동시에 돌리지 않는다.** temperature 를 고정할 수 없으니 팔마다 3회씩, Fable 과 Opus 를 번갈아 실행해 같은 모델 안의 흔들림도 함께 잰다. 매 회차 로그의 실제 응답 모델을 사람이 확인한다. 서로 성격이 다른 녹화 두 편, 예컨대 깨끗한 원본과 리테이크가 많은 원본을 쓰면 일반화가 낫다. 한 편이면 그 대본에 대한 판정에 그친다.

1단계 컷 시험은 회차 전마다 `work/cut_review.json` 을 지운다. 캐시 키에 모델이 없어 지우지 않으면 옛 결과를 읽는다. 현재 CLI 에는 컷 총괄 직후 멈추는 옵션이 없고 `--until plan` 은 컷 결정이 달라지면 기획 키가 바뀌어 전문가까지 다시 부르므로, 파일이 써진 시점에 작업을 취소하거나 멈춤 옵션을 하나 추가해야 비용을 아낄 수 있다. 2단계 기획 시험은 같은 `cut_review.json` 을 남겨 둔 채 `rerender <복사본> --until plan --replan` 으로 돌린다. 시험 비용은 API 환산 추정으로 컷 6회 약 $8, 기획 6회의 총괄 감독 호출 약 $10 에 하류 전문가 호출 $30~70 이 더 붙으므로 컷을 먼저 한다.

| 시험 | 채점 (모델명을 가리고) | 미리 정한 판정 |
|---|---|---|
| 컷 총괄 | 두 팔에서 남김·뺌이 갈린 발화 30~60개를 앞뒤 소리까지 듣고 맞고 틀림 기록. `fidelity` 복원·누락, 게이트 A1·A3, 기침 오삭제, 실패 횟수를 보조 지표로 | Fable 의 사람 판정 오류가 **20% 이상 적고** 3회 중 2회 이상 같은 방향이면 유지, 아니면 Opus |
| 총괄 감독 | BRIEF 를 맹검으로 읽고 논지의 날카로움, 챕터 구조, 시그니처 장면의 실제성, 이 영상 전용성을 미리 정한 점수표로 채점. 게이트 A6~A17, B1, B7, B11 은 열세 확인용 | Fable 이 **3판 중 2판 이상** 선호되고 하류 게이트 열세가 없으면 유지, 아니면 Opus |
| 공통 | 같은 모델 3회의 편차와 두 모델의 차이를 비교 | 같은 모델 안 편차가 더 크면 '차이 없음'으로 보고 더 싼 Opus |

3회 반복은 통계적 유의성을 주지 못한다. 이 시험이 주는 것은 증명이 아니라 사전에 정한 규칙에 따른 운영 결정이며, 실제 표본은 컷 시험의 발화별 판정이다. Fable 이 지면 목표 중심으로 줄인 프롬프트와 Fable `high` 강도를 각각 한 변수씩 추가로 시험할 수 있다. Fable 의 기본 강도는 `high` 다. 모션까지 판정하려면 별도로 `setpiece`·`motion` 만 바꿔 `--until design --replan` 을 돌리고, 장면 시트 맹검과 `check.mjs` 통과율을 비교해야 한다. 그 시험을 돌리기 전까지 모션에서 어느 모델이 낫다는 말에는 증거가 없다.
