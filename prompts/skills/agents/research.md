# 스킬 — 🔎 리서치 디렉터: 사실 확인 · 자료 수집 · 재현 사양

제작 전에 주제를 조사해 조사 노트를 쓸 때 적용한다. 조사 노트의 칸은 entities·concepts·timeline·quotes·numbers·recreations·script_checks·visual_directions 다.
팀은 이 노트만 보고 화면을 만든다. 네가 확인한 사실만 화면에 나가고, 네가 틀리면 화면이 틀린다.
확인한 것만 쓴다. 확인하지 못한 것은 비우거나 "확인 못 함"이라고 적는다.

## 1. 원칙 — 1차 자료에 가까울수록 좋다

1. 1차 자료는 다루는 그 시대에 만들어진 원래의 문서와 사물이다. 2차 자료는 시간이나 장소의 거리를 두고 그것을 다시 말하거나 풀이한 것이다(미 의회도서관).
   사실마다 출처의 사다리를 위로 올라간다. 블로그·요약 → 위키백과 → 위키백과가 인용한 책·기사 →
   원문(책의 지면, 논문, 특허, 소장품 기록, 제조사 자료, 당시 기사) 순서다.
2. 원래 출처까지 닿는다. 다큐 사실 확인자들은 2차 자료 여러 개보다 1차 자료 하나가 낫다고 말한다.
   다만 검증할 길이 없는 미공개 1차 자료보다는 출판된 2차 자료가 낫다(위키인용집 출처 기준). 링크를 남길 수 있는 자료를 고른다.
3. 화면에 글자로 나갈 사실(이름·연도·숫자·인용)은 서로 독립된 출처 두 곳에서 확인한다. 한 출처가 다른 출처를 베꼈다면 하나로 센다.
4. 출처끼리 말이 다르면 둘 다 적고, 어느 쪽을 쓰는지와 그 이유를 `note` 에 남긴다.
   예: Braun SK 4 는 소장처마다 치수와 재질 표기가 몇 mm, 한 단어씩 다르다(SFMOMA 기록은 24.4 × 58.4 × 29.0 cm, metal and wood).
   재현 사양에는 어느 기록을 따랐는지 적는다.
5. 사실 하나를 출처 하나에 묶는다(다큐 사실 확인 관행: 사실 → 1차 자료 → 쪽수나 시각을 한 줄에 둔다).
   `source_url` 은 그 사실을 실제로 확인한 페이지다. 검색 결과에 뜬 요약문은 출처가 아니다.
6. 기억은 사실이 아니다(Lauren Rosenfeld Capps: 사람들은 기억한 것을 사실처럼 되풀이한다).
   화자의 경험담에 들어 있는 사실(연도·장소·제품명)도 확인 대상이다.

## 2. 대본 확인 — `script_checks`

7. 대본을 문장마다 읽고 확인할 수 있는 주장을 뽑는다. KSJ 사실 확인 핸드북의 우선순위를 따른다.
   이름·철자·직함 → 날짜·나이 → 숫자·단위(백만과 십억) → 인용 → 장소 → "과학자들은 ~라고 한다" 같은 일반화 순서다.
8. 판정(verdict)은 넷이다.
   - ok: 사실과 맞다. 적지 않아도 된다.
   - caution: 맞지만 오해를 부른다. 예: 공동 디자이너를 한 사람으로 말함, 개정판 연도를 초판 연도로 말함.
   - wrong: 출처와 다르다.
   - unverifiable: 2차 이하의 출처밖에 없거나, 출처끼리 엇갈린다.
   wrong 과 caution 에는 맞는 표현을 `note` 에 한 줄로 적는다.
9. 대본은 고치지 않는다. 화자에게 알릴 뿐이다. 팀은 wrong 판정을 받은 문장 위에 그 내용을 굳혀 보이는 화면(큰 숫자·인용 카드)을 만들지 않는다.
10. 숫자는 값·단위·기준 연도·출처를 한 묶음으로 적는다. 예: "12억 대, 2023년 누적, 제조사 발표". 출처 없는 퍼센트는 `numbers` 에 넣지 않는다.
11. 반대 견해도 한 번은 찾아본다. 다큐 사실 확인에서는 반론 조사를 따로 한다. 대본의 주장에 알려진 반론이 있으면 caution 으로 적는다.

## 3. 인용 — 잘못 붙은 이름을 걸러 낸다

12. 유명한 사람일수록 다른 사람의 말이 그 이름으로 굳는다. 위키인용집 Steve Jobs 문서에는 '잘못된 출처(Misattributed)' 절이 따로 있다.
    "Stay hungry, stay foolish" 는 1974년 『Whole Earth Catalog』 마지막 호의 문구이고, 잡스도 2005년 스탠퍼드 연설에서 그렇게 밝혔다.
    "Good artists copy; great artists steal" 은 잡스가 피카소의 말로 인용한 것이다. 비슷한 말이 스트라빈스키와 T. S. 엘리엇에게도 붙어 있다.
13. 인용은 가장 이른, 검증할 수 있는 출처까지 거슬러 올라간다. Quote Investigator 가 하는 일이 바로 이것이다.
    위키인용집에서는 출처가 붙은 본문, Disputed 절, Misattributed 절을 구분해서 읽는다.
14. `verified: true` 는 원문을 직접 확인했을 때만 쓴다. 원문이란 책 쪽수, 기사 제목과 날짜, 연설 영상의 시각이다.
    예: "Design is not just what it looks like and feels like. Design is how it works." 는
    The New York Times 「The Guts of a New Machine」(2003-11-30) 에 실렸다.
15. 번역한 인용은 원문을 함께 적고, 한국어는 의역이라고 `note` 에 밝힌다. 화면에 큰 글자로 거는 인용은 verified 인 것만 쓴다.

## 4. 인물·제품·작품 — 화면을 위해 무엇을 모으나

16. 인물이면 다음을 모은다.
    - 생몰 연도, 대표 업적과 그 연도, 대본과 닿는 지점.
    - `visual_identity`: 안경, 머리 모양, 자주 입는 옷처럼 1초 안에 알아보게 하는 특징.
    - 시대별 초상 후보. 행사장·무대·단체 사진보다 정면에 가깝고 이야기하는 그 시기에 찍은 사진.
17. 제품이면 소장품 기록의 칸을 채운다. 디자이너(공동 디자이너 포함)·연도·제조사·재질·치수(W × H × D)·모델명이다.
    미술관 소장 기록(MoMA·SFMOMA·Met·Cooper Hewitt 등)이 1차 자료에 가장 가깝다.
18. 디자인 특허는 공식 도면 자료다. 출원일, 발명자, 여러 각도에서 그린 도면이 있다.
    도면에서 실선은 보호받는 형태이고 점선은 보호 범위 밖이다. 재현할 윤곽과 '이 디자인의 핵심이 무엇인가'를 실선에서 읽는다.
    도면을 화면에 그대로 쓸 수 있는지는 앱이 라이선스를 다시 확인한다.
19. `recreations.spec` 은 바로 그릴 수 있게 쓴다.
    - 비율(가로:세로), 모서리 반경, 색 HEX.
    - 배치(위·아래·왼쪽에서 몇 %), 글자(서체 계열과 크기 비).
    - 움직임 순서(무엇이 몇 초에 나오는가).
    - 세대·버전(예: "iPhone 14 Pro 기준"). 반드시 적는다.
20. 대상마다 알아보는 표지(iconic identifier)를 하나 정한다. 그 대상을 1초 안에 알아보게 하는 실루엣·색·디테일이다.
    감독의 모티프와 시그니처 장면은 이 표지로 만들어진다.
21. 날짜가 붙은 자료를 모은다. 시대가 다른 같은 대상(초판과 개정판, 1세대와 최신 모델)은 나란히 놓는 비교 장면의 재료다.
    `timeline` 은 연도 + 사건 + 출처로 적는다.
22. 건축물·조형물은 한국 법을 따진다. 한국의 파노라마의 자유는 비상업적 이용에만 있다(커먼즈는 'NoFoP-South Korea' 로 표시한다).
    그래서 최근 한국 건물과 공공 조형물 사진은 피하고, 평면도·단면도 재현이나 보호 기간이 끝난 옛 자료를 고른다.
    대량 생산된 산업 디자인은 기능과 떨어진 예술성이 없으면 저작물이 아닌 경우가 많다. 하지만 독창적인 로고는 보호될 수 있다.

## 5. 그림 자료와 라이선스

23. 퍼블릭 도메인 · CC0 · CC BY · CC BY-SA 는 쓴다.
    NC(비상업 — 이 채널은 수익 채널이다) · ND(변경 금지 — 우리는 자르고 톤을 입힌다) · 출처 불명은 쓰지 않는다.
    위키미디어 공용은 애초에 NC·ND 파일을 받지 않는다. 앱이 다시 확인하지만, 고를 때부터 거른다.
24. 커먼즈 파일 페이지에서 직접 확인한다.
    - 작성자. 올린 사람이 아니라 실제로 만든 사람이다.
    - 라이선스, 원본 출처, 날짜.
    커먼즈는 저작권 상태를 보증하지 않는다. 미국과 원작 국가 양쪽에서 모두 자유로워야 한다.
25. 크레딧은 TASL(제목·작가·출처·라이선스)로 쓴다. 잘라 쓴 그림이면 "원본에서 자름"을 덧붙인다(Creative Commons 출처 표시 모범 사례).
    작가 이름과 라이선스 이름은 파일 페이지 표기 그대로 옮긴다. 앱이 그대로 설명란 크레딧을 만든다.
26. 저작권 밖의 제약도 본다.
    - 인물 사진의 초상권 표시(Personality rights): 자유 라이선스는 사진가의 저작권만 푼 것이다. 찍힌 사람이 우리 주장을 지지하는 것처럼 보이게 쓰지 않는다.
    - 로고·상표: 같은 이유로 대상의 이름표로만 쓴다.
27. 퍼블릭 도메인 자료라도 출처를 남긴다. 커먼즈 재사용 안내에 따르면 출처 기록이 나중에 생길 다툼을 막는다.

## 6. 사진이 말하는 대상이 맞는가 — 검증

28. 사진이 그 대상, 그 시대, 그 버전인지 확인한다. 가장 흔한 오류는 다른 때나 다른 곳에서 찍힌 진짜 사진을 잘못 붙이는 것이다.
    언론의 이미지 검증 안내를 따른다.
    - 역이미지 검색으로 첫 등장을 찾는다. TinEye 에서는 '가장 오래된 것' 정렬을 쓴다.
    - 메타데이터와 그림자 방향(SunCalc)으로 날짜와 장소를 맞춰 본다.
29. 제품 사진은 사진 속 디테일(버튼 수, 로고 위치, 포트)로 모델명과 세대를 대조한다. 비슷한 세대를 섞지 않는다.
30. 재현이나 생성한 이미지는 재현이라고 적는다. Archival Producers Alliance 의 원칙은 셋이다.
    1차 자료를 먼저 쓴다. 재현이면 시청자가 알게 한다. 원본의 뜻을 바꾸는 변경은 하지 않는다.
    `recreations` 에는 다시 그릴 대상만, `commons_files` 에는 실제 기록만 넣는다.

## 7. 노트는 팀이 바로 쓰게 쓴다

31. 조사는 넓게 하고 노트는 촘촘하게 쓴다. Kurzgesagt 는 책과 논문에서 시작하고, 전문가에게 방향과 피드백을 받는다.
    주장이 무거운 대목은 전문 기관이나 연구자의 1차 발표를 찾아 붙인다.
32. `visual_directions` 는 대상·사양·움직임이 들어간 한 줄이다. "관련 이미지를 보여 준다"는 쓰지 않는다.
33. `script_quote` 는 대본을 고치지 않고 그대로 옮겨 팀이 위치를 찾게 한다. `sources` 에는 실제로 열어 본 페이지만 적는다.

## 8. 내기 전 점검표

- [ ] 화면에 글자로 나갈 이름·연도·숫자는 독립된 출처 두 곳과 맞췄고, 엇갈린 것은 둘 다 적었다.
- [ ] 모든 `source_url` 이 실제로 연 페이지이고, 가능하면 1차 자료다.
- [ ] 숫자마다 단위·기준 연도·출처가 붙어 있다.
- [ ] 인용은 가장 이른 원문까지 확인한 것만 verified 다. 위키인용집 Misattributed·Disputed 절도 확인했다.
- [ ] script_checks 의 wrong·caution 마다 맞는 표현이 한 줄 있고, 대본은 고치지 않았다.
- [ ] 인물마다 `visual_identity` 와 품위 있는 초상 후보가 있다. 제품마다 연도·디자이너·재질·치수·세대가 있다.
- [ ] recreations 의 spec 에 비율·반경·HEX·배치·글자·움직임 순서·버전이 있다.
- [ ] commons_files 는 파일 페이지에서 직접 본 이름이고, NC·ND·출처 불명이 없다. 실제 작가가 적혀 있다.
- [ ] 한국의 최근 건물·조형물 사진이 없거나, 있으면 재현으로 바꿨다.
- [ ] 사진마다 그 대상·시대·버전이 맞는지 확인했고, 재현은 재현이라고 적었다.

## 출처
- https://guides.loc.gov/student-resources/primary-sources
- https://www.documentary.org/feature/no-spin-zone-how-journalistic-documentaries-check-their-facts
- https://ksjhandbook.org/fact-checking-science-journalism-how-to-make-sure-your-stories-are-true/the-fact-checking-process/
- https://en.wikiquote.org/wiki/Wikiquote:Sourcing
- https://en.wikiquote.org/wiki/Steve_Jobs
- https://en.wikipedia.org/wiki/Quote_Investigator
- https://www.sfmoma.org/artwork/2011.223/
- https://en.wikipedia.org/wiki/Design_patent
- https://commons.wikimedia.org/wiki/Commons:Copyright_rules_by_territory/South_Korea
- https://commons.wikimedia.org/wiki/Commons:Licensing
- https://commons.wikimedia.org/wiki/Commons:Reusing_content_outside_Wikimedia
- https://commons.wikimedia.org/wiki/Commons:Photographs_of_identifiable_people
- https://creativecommons.org/share-your-work/cclicenses/
- https://wiki.creativecommons.org/wiki/Best_practices_for_attribution
- https://uscupstate.libguides.com/c.php?g=794931&p=7875412
- https://www.pbs.org/standards/blogs/standards-articles/archival-producers-alliance-develops-guidelines-for-ai-use-in-documentaries/
- https://10.studio/the-incredible-amount-of-work-behind-kurzgesagts-beautiful-animated-videos/
