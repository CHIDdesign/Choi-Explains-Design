# 스킬 — 🎞 자료 리서처(증거 · B롤 · 아카이브 · 검색어)

문장마다 "이 말을 믿거나 이해하려면 무엇을 봐야 하는가"를 정할 때 적용한다(`need` · `treatment` · `stock.query_en` · `label` · `caption` · `display` · `quote`).
운영자 방침은 얼굴(20~35%)보다 시청각 자료를 많이 쓰는 것이다. 그래도 많이 넣는 것이 목표가 아니다. **말한 것을 보여 주는 것**이 목표다.
다큐멘터리 편집자와 영상 에세이 제작자들의 방법을 이 채널(크림 종이 콜라주, 차분한 교육)에 맞게 옮겼다.

## 1. 증거가 먼저, 장식은 없다

1. 화면은 주장을 꾸미는 벽지가 아니라 근거다. 신 풀(ScenePull)의 B롤 가이드는 자판 치는 손, 커피 따르기, 도시 타임랩스 같은 화면이
   주제를 '알릴' 뿐 설명을 한 걸음도 진전시키지 않는다고 지적한다. 악수 장면도 협력·신뢰·협상 중 무엇도 설명하지 못한다.
2. **이름이 나오면 그 물건을 보여 준다.** 인물, 제품, 건축, 책, 브랜드, 장소가 들리면 `entity`·`primary_source`·`screenshot` 으로 실물을 찾는다.
   스톡으로 특정 대상을 대신하지 않는다("브라운 라디오"에 아무 빈티지 라디오를 쓰지 않는다).
3. 문자 그대로가 기본이다. PremiumBeat 가이드는 말하는 대상을 그대로 보여 주는 화면을 먼저 쓰라고 하고,
   은유 화면(빈 의자, 닫히는 문)은 감정을 말할 때만 쓰라고 한다. 이 채널에서 은유 화면은 `role: mood` 이고 영상당 2개 이하다.
   주장이나 사실을 말하는 문장에는 쓰지 않는다.
4. 셜록현준 채널의 자료 화면은 공간을 말할 때 평면도와 단면도를 함께 띄우고, 흰색·미색 이미지로 눈을 편하게 하며,
   반투명 색 상자로 한 곳만 짚는다. 배치·동선·구조를 말하는 문장은 스톡보다 `code_drawn`(선으로 다시 그린 도면)이 맞다.
5. AI 로 만든 '기록 사진'은 쓰지 않는다. 아카이브 프로듀서 연합(APA)의 생성형 AI 지침은 다큐멘터리의 약속을
   '진짜라고 보여 준 것은 진짜'로 요약한다. 재현이 필요하면 손으로 그린 선(`code_drawn`)처럼 재현으로 보이게 한다.

## 2. 증거의 크기와 시간

1. 과정은 한 장이 아니라 **시퀀스**로 고른다. 인사이드 더 에딧(Inside the Edit)은 B롤을 두 가지로 나눈다.
   - 순차 B롤: 사슬처럼 이어져 과정을 보여 주는 샷들.
   - 설명 B롤: 맥락이나 분위기를 주는 한 장.
   과정, 제작, 사용 장면은 순차로 3샷을 고른다: 전체 → 손과 도구 → 결과의 부분(`count` 3, 서로 다른 화각).
2. 같은 촬영본의 다른 각도를 찾는다. 같은 세션 영상은 검색 결과에서 무리 지어 나오므로 톤이 맞는다(Wave.video 가이드).
   `must_show` 에 "같은 촬영의 가까운 샷"처럼 적는다.
3. 움직임이 의미 있으면 영상을 먼저 고른다(`stock.kind: video`). 과정, 현장, 도시, 손으로 하는 일이 그렇다. 정물·구도·형태는 사진이 낫다.
4. 사진은 한 장을 '마스터 샷'처럼 다룬다. 켄 번스는 한 장의 사진 안을 탐색하며, 길이가 의미를 쌓는다고 말한다.
   패닝은 지금 말하는 대상 위에서 멈춘다. 그래서 생김새를 말하는 문장이면 `focus`·`annotations` 에 어디를 볼지 적는다.
5. 유지 시간은 내용의 어려움에 맞춘다. 신 풀의 기준은 이렇다: 맥락 컷은 빨리 읽히고, 도표나 낯선 과정은 오래 걸린다.
   우리 기본값은 맥락 스톡 2.5~4초, 대상 첫 등장 3.5~5초, 문서·화면 5~6초, 비교 5~7초다.

## 3. 스톡 검색어 쓰기(`query_en` · `query_ko`)

1. 영어 3~6낱말을 다음 순서로 쓴다: **주인공 + 행동 + 대상 + 장소 + 화각**.
   앱은 결과가 적으면 뒤에서부터 낱말을 줄인다. 그래서 꼭 남아야 할 명사를 앞에 둔다.
   - 예: "hands sketching chair on tracing paper close up"
   - 예: "industrial designer sanding foam model workshop"
2. 구체적인 명사, 구체적인 장소를 쓴다. Wave.video 가이드는 막연한 "city" 대신 실제 도시 이름을 검색하라고 한다.
   그래야 남들이 다 쓴 화면을 피한다. "seoul subway platform", "tokyo crosswalk aerial" 처럼 쓴다.
3. 화각어를 하나만 붙인다: close up, extreme close up, macro, overhead / top view, aerial, wide shot,
   over the shoulder, POV, slow motion. 콜라주용 오려 낼 물건은 "isolated on white", 글자 자리가 필요하면 "copy space".
4. 쓰지 않는 말:
   - 추상어: innovation, success, creativity, idea, concept, future, technology.
   - 꾸밈말: cinematic, beautiful, amazing, modern.
   이런 말은 뻔한 스톡(전구, 퍼즐, 빛나는 네트워크, 웃는 회의)을 불러온다.
5. 얼굴보다 손을 찾는다. "hands …" 로 시작하면 큰 얼굴과 모델 미소가 줄어든다.
   신원이 드러나는 인물은 초상권 문제가 따로 있다(위키미디어 커먼즈 재사용 안내).
6. 동음이의어와 은유는 문맥의 뜻으로 푼다: 노트북 → laptop, 배 → boat, 다리 → bridge, "머리를 쥐어짜다" → designer thinking at desk.
   `query_ko` 도 뜻이 하나로 정해지게 쓴다("노트북 컴퓨터").
7. 시대 분위기를 스톡의 "vintage" 연출로 대신하지 않는다. 진짜 과거는 아래 아카이브(프렐링어 영화, 박물관 사진)에서 찾는다.
8. `must_show` 에는 꼭 보여야 할 것과 안 되는 것을 함께 쓴다. `avoid` 에는 다른 모델, 복제품, 큰 얼굴, 로고, 형광 3D 배경을 적는다.

## 4. 아카이브 먼저 — 열린 소장처와 쓰임

디자인 고전, 시대, 전시, 제품 계보를 말하는 문장은 스톡보다 아래를 먼저 본다. 앱이 위키·커먼즈·Openverse 를 찾는다.
그 밖의 소장처는 `commons_files` 나 `notes` 에 후보를 남긴다. 화면 출처 줄(`caption`)에는 소장처와 연도를 쓴다.

| 소장처 | 잘 맞는 것 | 권리 | 주의 |
|---|---|---|---|
| 위키미디어 커먼즈 | 인물 초상, 제품, 건축, 로고(위키데이터 연결) | 파일마다 다름(CC0·PD·CC BY·CC BY-SA) | 파일 페이지의 라이선스를 직접 확인. 재단은 보증하지 않는다. 초상권·상표권은 저작권과 별개다 |
| 쿠퍼 휴잇(스미스소니언 디자인 박물관) | 산업디자인 제품, 가구, 포스터, 그래픽, 벽지, 건축 드로잉 | 스미스소니언 오픈 액세스 표시 항목은 CC0 | 이 채널의 1순위. 라이트의 의자, 페리스의 드로잉 같은 원본 |
| 스미스소니언 오픈 액세스 | 기술사·생활사 물건, 3D 스캔 | CC0 | 오픈 액세스 표시가 있는 것만 |
| 메트로폴리탄 미술관(The Met) | 장식미술, 공예, 판화, 고전 형태 | 퍼블릭 도메인 작품 사진은 CC0(2017년 공개 때 37만 5천 점 이상, 커먼즈에도 있음) | 오픈 액세스 표시가 없는 작품은 쓰지 않는다 |
| 레이크스뮤지엄 | 판화, 도자기, 가구, 고해상 디테일 | 퍼블릭 도메인·CC0, 일부 CC BY 4.0 | 상업 이용 가능. 출처 표기를 정중히 요청한다 |
| 미국 의회도서관 Free to Use | WPA 포스터, 지도, 건축 도면, 기록 사진 | '자유 이용' 묶음은 저작권 제약 없음 | 묶음 밖 항목은 권리 표시를 따로 본다 |
| 인터넷 아카이브 프렐링어 | 1940~70년대 산업·광고·교육 영화(움직이는 기록) | 약 65%가 미국 퍼블릭 도메인. 퍼블릭 도메인 마크 | 항목마다 권리 확인. 시대 생활, 공장, 부엌, 소비문화에 강하다 |
| 국립중앙박물관 e뮤지엄 | 한국 공예, 그릇, 가구, 유물 고해상 | 공공누리 제1유형(출처 표시, 상업 이용·변경 가능) | 공공누리 표시가 없는 자료는 사전 협의가 필요하다. 쓰지 않는다 |
| 공유마당(한국저작권위원회) | 만료 저작물, 기증 저작물, 한국 사진 | 만료·기증·CCL·공공누리가 섞여 있다 | 만료 저작물, CC BY, 공공누리 1유형만 고른다 |
| Openverse | 위 소장처들의 메타 검색 | CC 와 퍼블릭 도메인 | 앱이 상업·변형 허용으로 거르고 다시 확인한다 |
| Pixabay · Pexels · Unsplash · Coverr | 현대의 과정·현장·도시 장면 | 각 사이트 라이선스 | 상표와 신원이 드러나는 인물은 피한다 |

## 5. 라이선스 판단

1. 쓰는 것: CC0, 퍼블릭 도메인(PDM), CC BY, CC BY-SA, 공공누리 0·1유형, 스톡 사이트 라이선스.
   CC BY-SA 는 동일 조건 변경 허락이 붙는다. 그래서 오려 붙이기·합성하지 않고 통째로 놓는다(이미지 처리 스킬).
2. 쓰지 않는 것:
   - 비영리 조건(CC BY-NC 계열, 공공누리 2·4유형)
   - 변경 금지(CC BY-ND 계열, 공공누리 3·4유형) — 우리는 색 처리와 자르기를 하므로 변경에 해당한다
   - "보도용", "editorial use only"
   - 출처 불명, 핀터레스트·검색 결과 이미지
3. 저작권이 남은 작품·화면·문헌은 그것 **자체를 설명하는 문장**에서만 C 등급 인용으로 요청한다(`tier_max: C`).
   운영자가 인용을 켰을 때만 조달된다. 꺼져 있으면 출처 카드나 `code_drawn` 으로 간다.
4. 공공누리와 CC BY 는 출처 표시가 조건이다. 국립중앙박물관은 기관명, 누리집 주소, (있으면) 작가명을 요구한다.
   화면 `caption` 은 짧게 쓰고 전문은 앱이 업로드 정보와 자료 대장에 남긴다.

## 6. 화면 글자

1. `label`(14자 이하)은 화자의 말에서 온 **주장 조각**이다. `caption`(24자 이하)은 **사실**이다: 이름, 연도, 작가, 소장처.
   예: label "덜어 낸 라디오", caption "브라운 SK 4 · 디터 람스 · 1956".
2. 사진에 보이지 않을 수 있는 묘사는 쓰지 않는다("밤늦게", "학생들"). 사진이 바뀌면 거짓말이 된다.
3. `display` 는 화자가 그 문장에서 실제로 말한 낱말 하나다. `quote` 는 챕터에 많아야 1개다.
4. 검색어, 연출 메모("…을 보여준다", "…하는 장면", "B-roll"), 내부 이름은 어떤 글자 칸에도 쓰지 않는다.

## 7. 내기 전에 확인

1. 이름이 나온 문장마다 그 대상의 실물(사진, 로고, 문서, 화면)을 요청했는가. 스톡으로 대신한 곳은 없는가.
2. 스톡 검색어가 모두 '보이는 행동 + 대상 + 장소 + 화각'인가. 추상어, 꾸밈말, 뻔한 은유가 없는가.
3. 과정을 말하는 구간은 3샷 시퀀스이고, 그중 하나 이상이 영상인가.
4. 디자인사·시대 문장에서 쿠퍼 휴잇, 메트, 레이크스, 의회도서관, 프렐링어, e뮤지엄 후보를 먼저 떠올렸는가.
5. NC·ND·보도용·출처 불명 자료를 요청하지 않았는가. AI 로 만든 기록 이미지는 없는가.
6. 챕터마다 전면 자료가 있고, 사례·근거 구간에 얼굴만 12초 넘게 이어지는 곳이 없는가.

## 출처
- https://www.scenepull.com/blog/b-roll-footage-guide
- https://www.premiumbeat.com/blog/b-roll-video-edit-guide/
- https://www.insidetheedit.com/blog/b-roll-editing-structure
- https://wave.video/blog/how-to-find-best-stock-footage/
- https://www.cined.com/the-story-behind-the-ken-burns-effect-how-a-phone-call-from-steve-jobs-made-documentarys-most-influential-technique-a-household-name/
- https://en.wikipedia.org/wiki/Ken_Burns_effect
- https://ethicsandjournalism.org/2024/10/11/archival-producers-alliance-best-practices-for-use-of-generative-ai-in-documentaries/
- https://www.openads.co.kr/content/contentDetail?contsId=16056
- https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia
- https://www.cooperhewitt.org/2020/05/28/discover-smithsonian-open-access-with-treasures-from-the-cooper-hewitt-collection/
- https://wikimediafoundation.org/news/2017/02/07/the-met-public-art-creative-commons/
- https://data.rijksmuseum.nl/policy
- https://www.loc.gov/free-to-use/
- https://publicdomainreview.org/collections/source/prelinger-archives/
- https://www.museum.go.kr/MUSEUM/contents/M3304000000.do
- https://gongu.copyright.or.kr/gongu/main/contents.do?menuNo=200023
