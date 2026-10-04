# 스킬 — 🎬 총괄 감독: 구성 · AV 스크립트 · 트리트먼트

브리프(논지·챕터·비트·시퀀스·`treatment`)를 쓸 때 적용한다. 대본 문장은 바꾸지 않는다. 감독이 정하는 것은 두 가지다.
그 문장 아래에 무엇이 보이는가, 그리고 어떤 순서로 궁금하게 만들고 답하는가.
화면의 재료는 조사 노트에 있는 사실·커먼즈 파일·재현 사양이다. 기억에 기대 그림을 지어내지 않는다. 소리 콘셉트의 세부는 소리 노트를 따른다.

## 1. 구조 — 질문으로 열고, 답으로 닫고, 일상으로 돌아온다

1. 영상의 뼈대는 레퍼런스 채널식 다섯 칸이다. 일상의 장면 → 질문 → 원리 → 개념에 이름 붙이기 → 다시 일상.
   영상 전체가 이 순서로 큰 한 바퀴를 돌고, 챕터마다 작은 한 바퀴를 돈다. 챕터가 어느 칸에서 시작해 어느 칸에서 끝나는지 `purpose` 에 적는다.
2. 정의로 시작하지 않는다. 사례와 사물을 먼저 보여 주고 개념의 이름은 그 뒤에 붙인다(Grant Sanderson: 구체가 먼저, 추상은 나중.
   정의는 출발점이 아니라 도착점이다). 같은 개념이라면 `show: example/object` 비트가 `function: name` 비트보다 앞에 와야 한다.
3. 첫 30초 안에 "왜 이걸 봐야 하나"가 서야 한다(3Blue1Brown SoME 심사 기준 '동기'). `central_question` 은 화자가 실제로 한 말에서 고른다.
   훅 비트의 `on_screen_text` 에 그 질문을 넣어 첫 15초 안에 화면 글자로 띄운다.
4. 흔한 오해가 있는 주제는 오해부터 세운다(Derek Muller 의 박사 연구: 바른 설명만 하면 오해는 그대로 남고 확신만 커진다).
   오해를 말하는 문장에는 '그럴듯한 오답'의 실물을 보여 준다. 뒤집는 문장에서는 새 그림을 띄우지 말고 같은 화면을 고쳐 쓴다(교정 표시·취소선·밑줄).
5. 호기심은 거의 알 것 같은 간격에서 가장 크다(Loewenstein 의 정보 격차 이론. 2024년 실험에서는 지식의 빈칸을 눈에 보이게 하자
   정보를 더 찾았고, 효과는 중간 정도의 빈칸에서 가장 컸다). 훅에서는 익숙한 사물을 보여 주고 원리의 이름은 숨긴다.
   아무도 모르는 것(빈칸이 너무 큼)이나 누구나 아는 것(빈칸이 없음)으로 열지 않는다.
6. 결과는 과정보다 늦게 보여 준다. Vox 의 Joss Fong 은 블랙홀 첫 사진을 바로 보여 주지 않았다. 먼저 망원경들의 규모를 보여 주고 그다음에 사진을 냈다.
   완성품·정답 이미지는 "왜 어려운가"를 보여 준 비트 뒤에 둔다.
7. 비트를 "그리고 나서"로 잇지 않는다. 챕터 `claim` 들을 차례로 읽으며 사이에 "그런데"나 "그래서"가 들어가는지 본다
   (Trey Parker·Matt Stone 의 but/therefore 규칙. Every Frame a Painting 의 Tony Zhou 가 영상 에세이 분석에 옮겨 썼다). "그리고"만 들어가면 그 claim 을 다시 쓴다.
8. 열린 질문은 동시에 두 개까지만 연다. 연 질문은 같은 챕터 안이나 `payoff_seg` 에서 반드시 닫는다.
   닫는 비트에는 연 비트와 같은 화면(같은 사물, 같은 도식)을 돌려보내서 닫혔다는 것이 눈에 보이게 한다.
9. 챕터 첫머리는 다시 붙잡는 자리다(MrBeast 제작 지침: 3분 무렵과 6분 무렵에 다시 몰입시키는 장면을 둔다). 챕터는 3.5~5분 간격이다.
   챕터마다 첫 10초 안에 그 챕터에서 가장 강한 실물이나 시그니처 장면을 두고, `claim` 이 그 챕터가 답할 질문을 품게 쓴다.
10. 답(payoff)은 영상의 60~75% 지점 근처에 둔다. 그 뒤에는 일상으로 짧게 돌아와 끝낸다. 결론 뒤에 새 정보를 늘어놓지 않는다.
11. 로그라인을 한 문장으로 쓰고, 비트를 고를 때마다 그 문장에 비춰 본다(Nate Ptacek: 로그라인은 영화의 논지이니 자주 돌아가 본다).
    로그라인을 받치지 않는 비트는 `priority: 3` 이다.

## 2. 줄마다 화면 — AV 스크립트 쓰는 법

12. `beats` 는 2단 AV 스크립트다. 말 맞은편에 적힌 것이 그 말 아래에서 재생된다. 두 칸이 어긋난 곳이 완성본이 무너지는 곳이다(2단 스크립트 작법).
    줄마다 "이 말이 들릴 때 시청자 눈앞에 무엇이 있는가"를 명사로 적는다. "관련 이미지"처럼 대상을 가리키지 않는 말은 쓰지 않는다.
13. 대본과 화면을 함께 쓴다(Johnny Harris: 대본을 쓰는 동시에 화면을 연출하고, 화면 자산과 사실 확인을 색으로 표시해 둔다).
    전사본을 끝까지 읽은 뒤 그림을 붙이지 않는다. 발화 1~4개마다 그 자리에서 화면을 정하며 읽어 내려간다.
    화면이 떠오르지 않는 줄은 얼굴로 둔다. 장식으로 메우지 않는다.
14. 그림을 먼저, 맥락은 나중에 준다(Johnny Harris 의 '시각적 닻이 먼저'). 영상에서 가장 강한 실물 세 곳은 설명보다 먼저 들어오게 한다.
    `enter: picture_first` 는 영상당 3곳까지다. 그림이 "이것 보세요"를 대신 말하게 둔다.
15. 이것이 글이 아니라 영상이어야 하는 이유를 화면으로 보인다(Cleo Abram 은 대본보다 화면 계획을 먼저 세우고, 왜 글이 아니라 영상인지를 늘 묻는다).
    챕터마다 적어도 하나는 글로는 못 하는 장면을 둔다. 재현한 시연, 움직이는 도식, 실물 둘의 비교 같은 것이다.
16. 말과 그림은 같은 순간에 맞는다(Mayer 의 시간 근접 원리). 사물의 이름이 들리는 어절에 그 사물이 들어오도록 `shots[].word` 를 어절 그대로 적는다.
17. 화면 글자는 말을 받아 적지 않는다(Mayer 의 중복 원리: 그림과 말 위에 같은 글자를 겹치면 오히려 덜 배운다).
    `on_screen_text` 에는 논지의 조각, 이름, 숫자만 14자 안팎으로 넣는다.
18. 하는 일이 없는 그림은 뺀다(Mayer 의 일관성 원리). 그 비트의 `function` 을 한 낱말로 말할 수 없으면 `visual` 은 none 이다.
19. 얼굴은 화면에 있는 것만으로 학습을 늘리지 않는다(Mayer 의 이미지 원리). 그래도 얼굴을 다 지우지는 않는다. 격식 없이 말하는 얼굴이 들어간 강의 영상이 더 끝까지 보였다(Guo 외, edX 시청 690만 회 분석).
    그래서 얼굴은 전체의 20~35%만 쓰고, 훅·의견·고백·결론·시청자에게 말을 거는 문장에 둔다.
20. 자료는 증거로 쓴다(Every Frame a Painting 에서 클립은 장식이 아니라 증명이었다. 한 기법을 골라 끝까지 파고들었다).
    비교할 때는 실물 둘을 나란히 놓는다(`comparison`). 한 사물을 깊게 볼 때는 한 장을 부분마다 짚는다(`detail_zoom`).
21. 레퍼런스 채널의 장치를 우리 화면 언어로 옮긴다. 공간·구조를 말하면 평면도나 단면도를 말 옆에 둔다. 지금 말하는 부분만 반투명 색 상자로 덮는다.
    판서 영역은 화면 한쪽에 칠판처럼 두고, 그래픽은 화자 시선의 반대쪽 빈 칸에 놓는다.

## 3. 트리트먼트 — 이 주제에만 맞는 시각 설계

22. 트리트먼트는 기법 목록이 아니다. 고른 기법마다 이 주제에 왜 맞는지 한 줄을 붙인다(다큐 트리트먼트의 '시각 스타일' 절: 그럴듯해 보여서 넣은 기법은 뺀다).
23. `concept` 는 대상이 실제로 가진 재료·질감·시대에서 출발한다. 다 쓰면 concept 문장에서 주제 이름을 지워 본다.
    그래도 다른 영상에 그대로 붙는다면 다시 쓴다.
24. `motifs` 는 3~5개로 하고, 하나마다 3~5번 돌아오게 계획한다(StudioBinder 의 모티프 설계).
    처음에는 조용히 깔고, 전환점마다 다시 불러오며, 돌아올 때마다 크기·상태·색·함께 놓인 것 가운데 하나를 바꾼다.
    한 번만 나오는 것은 모티프가 아니라 은유다.
25. 모티프는 화면 장치로 적는다. 예: "빨간 교정 표시가 챕터마다 하나씩 쌓인다", "같은 의자 실루엣이 챕터마다 다른 시대의 재질로 바뀐다",
    "연표 띠가 챕터 카드 밑에서 한 칸씩 늘어난다". "따뜻한 감성" 같은 형용사는 모티프가 아니다.
26. 시그니처 장면 3~6개는 공을 가장 많이 들일 곳이다. Kurzgesagt 는 대본이 끝나면 영상 전체를 장면 단위로 스토리보드에 펼친다.
    거기서 생각과 생각을 잇는 시각 은유와 전환을 먼저 찾는다(10분 영상에 그림 약 200장).
    시그니처는 훅, 챕터마다 핵심 원리가 이름을 얻는 순간, payoff 에 둔다. 장면끼리 `kind` 가 겹치지 않게 한다.
27. 시그니처 `brief` 에는 조사 노트의 재현 사양(비율·HEX·글자·움직임 순서)을 그대로 옮기고 길이는 5~12초로 잡는다. 사양이 없는 대상은 시그니처로 고르지 않는다.
28. `segments` 의 레이아웃 비율을 세어 본다. face 계열(face·face_callout·face_photo)은 20~35%,
    실물 자료(collage·photo_full·document·stock_video·quote_over_footage)는 30% 이상, 나머지는 motion·board·timeline·compare·signature 다.
    시퀀스 밖에서 같은 레이아웃이 3단락 넘게 이어지지 않게 한다.
29. 손으로 만든 질감을 고른다. Johnny Harris 계열 화면은 종이 질감, 벽에 꽂은 사진, 미끄러지기보다 '놓이는' 움직임, 종이 소리로 손맛을 낸다.
    우리 하우스 스타일(크림 종이·오린 사진·명조)이 이미 그 언어이니, 매끈한 3D·유리 질감·네온으로 벗어나지 않는다.
30. `sound_concept` 는 음악이 들어오고 빠지는 자리로 쓴다(Joss Fong: 곡의 시작과 끝은 감정의 신호이자 주의를 끄는 신호다).
    예: "훅과 타이틀에 주제 → 문서를 읽는 동안 비움 → 정점 앞에서 비움 → 엔딩에서 다시". 분위기 형용사만 적지 않는다.

## 3-1. 세계와 리듬 — 이 사람의 세계 안에서, 정지 박자를 처방한다

31. `treatment.world` 는 팀 전원의 필터다. 자료 리서처의 검색어·비전 선택·모션 그림 부품·검수가 모두 받는다(2026-10-04: '학교'에
    아이 공책·색연필 스톡 — 맥락은 미대 산업디자인과였다). 누구(나이·전공)·어디·언제·사물·**이 세계가 아닌 것**을 구체 명사로 쓴다.
    Getty VisualGPS: "Go to real places and photograph real people." 억지스러운 그림은 바로 티가 난다.
32. 대본-화면 2열 표처럼 생각한다(Vox 출신 제작자: "Put your script on the left side and use the column on the right to lay out visual
    idea"). Kurzgesagt 는 스케치 단계에서 장면마다 가장 좋은 시각 은유를 두고 고민하고, 내레이션이 애니메이션의 타이밍을 준다.
33. 영화는 "visual music"이다(Murch) — 구절의 교대와 전개. 챕터 하나의 틀: 질문(얼굴) → 근거(자료·도식, 밀도 높음) → **정지 박자**
    (쉼 1~1.5초, 오래 잡는 이미지나 얼굴) → 전환. 정보가 몰린 구간 바로 뒤에 정지 박자를 하나씩 처방한다 — Joss Fong 의 경고:
    "There's a really high risk of charging forward and not realizing that the viewer is not with you."
34. 결정적 자료는 그 의미가 선 다음에 보여 준다(Jacob Bricca, ACE: "Delay Gratification", "Say what you mean in the most direct
    way you can. Simple is better."). Fong 도 블랙홀 사진을 영상 중간까지 미뤄 왜 중요한지 먼저 이해시켰다.
35. 화면을 바꿀지 검토하는 신호는 정적인 문장이 두 개쯤 이어질 때다 — "a prompt to evaluate, not a quota". 시계로 바꾸지 않는다.

## 4. 다큐멘터리 시각 문법 — 자료를 다루는 법

31. 사진 한 장도 움직이며 읽힌다(Ken Burns 효과: 천천히 밀거나 훑는다). 움직임은 화자가 지금 말하는 대상 위에서 멈춰야 한다.
    단체 사진이나 제품 여럿이 찍힌 사진이면 "누구·어느 것"을 말하는 어절을 `shots[].word` 로 준다.
32. 문서·논문·특허는 세 박자로 보인다. 출처(표지·서지) → 그 줄로 다가감 → 형광펜으로 요지. 이것이 `document_read` 다.
    읽어야 하는 화면 위에서는 음악을 비우고 자막을 숨긴다.
33. 장소·시대 비트(`place_time`)는 연표나 지도로 '지금 어디쯤인가'를 알려 준다. 연도는 숫자 서체로 크게 쓰고, 사진에는 촬영 연도를 붙인다.
34. 실물이 있으면 실물이 재현보다 먼저다. 재현은 실물이 없을 때(옛 UI, 사라진 제품)나 부분을 움직여 보여야 할 때만 쓴다.
35. 재현은 재현이라고 보이게 한다(Archival Producers Alliance: 1차 자료를 먼저 쓰고, 재현이나 생성한 그림은 하단 문구·다른 틀·색으로 구별한다).
    다시 그린 사물은 선과 면의 그림으로 보이게 하고, 사진처럼 꾸며 진짜 기록인 척하지 않는다.
36. 큰 글자 인용(`quote_over_footage`)은 조사 노트에서 `verified: true` 인 인용에만 쓴다. 확인하지 못한 말을 영상에서 가장 큰 글자로 걸지 않는다.

## 5. 내기 전 점검표

- [ ] 로그라인과 논지가 각각 한 문장이고, 모든 챕터 `claim` 이 논지를 받친다.
- [ ] 첫 30초 안에 중심 질문이 말과 화면 글자로 나온다. 정의로 시작하지 않는다.
- [ ] 챕터 `claim` 사이가 "그런데" 또는 "그래서"로 이어진다. "그리고 나서"로만 이어지는 곳이 없다.
- [ ] 오해가 있는 주제면 오해를 먼저 세우고, 같은 화면을 고쳐 쓰며 뒤집는다.
- [ ] 연 질문이 모두 닫힌다. payoff 는 60~75% 근처에 있고, 끝은 일상으로 돌아온다.
- [ ] 비트가 첫 발화부터 끝 발화까지 빠짐없이 있고, 화면이 있는 비트마다 `function` 이 있다.
- [ ] `show` 가 object·example·comparison·source 인 비트의 80% 이상에 실물이 붙는다.
- [ ] 얼굴은 20~35%, 글자만 있는 화면은 화면 비트의 40% 이하, 같은 레이아웃은 3단락 넘게 연달아 나오지 않는다.
- [ ] 모티프 3~5개가 각각 3번 이상 돌아오고, 돌아올 때마다 하나씩 바뀐다.
- [ ] 시그니처 장면 3~6개가 훅·핵심 원리·payoff 에 있고, `brief` 에 재현 사양이 있다.
- [ ] concept 문장에서 주제 이름을 지우면 다른 영상에는 맞지 않는다.
- [ ] 재현 그림은 재현으로 보이고, 큰 글자 인용은 모두 확인된 인용이다.

## 출처
- https://www.3blue1brown.com/blog/some1/
- https://www.3blue1brown.com/blog/some1-results/
- https://www.bobvanvliet.com/notes/designing-effective-multimedia-for-physics-education/
- https://www.scientificamerican.com/article/how-youtube-star-derek-muller-of-veritasium-is-challenging-scientific/
- https://journalofcognition.org/articles/10.5334/joc.501
- https://www.theopennotebook.com/2020/01/07/videogram-how-a-vox-video-explains-the-science-behind-the-first-photo-of-a-black-hole/
- https://perell.com/note/but-therefore-rule/
- https://www.studiobinder.com/blog/every-frame-a-painting/
- https://www.danielscrivner.com/how-to-succeed-in-mrbeast-production-summary/
- http://nateptacek.com/notes-from-the-field/2018/12/26/editing-a-documentary-film-read-this-first
- https://scriptcut.io/blog/what-is-a-two-column-script
- https://podwise.ai/dashboard/episodes/3299864
- https://chengweihu.com/io/visual-before-context/
- https://podwise.ai/episodes/2768285
- https://www.digitallearninginstitute.com/blog/mayers-principles-multimedia-learning
- https://pg.ucsd.edu/publications/edX-MOOC-video-production-and-engagement_LAS-2014.txt
- https://www.openads.co.kr/content/contentDetail?contsId=16056
- https://brunch.co.kr/@eunhamansion/71
- https://blog.celtx.com/documentary-treatment
- https://www.studiobinder.com/blog/what-is-a-motif-in-film/
- https://10.studio/the-incredible-amount-of-work-behind-kurzgesagts-beautiful-animated-videos/
- https://en.wikipedia.org/wiki/Ken_Burns_effect
- https://www.pbs.org/standards/blogs/standards-articles/archival-producers-alliance-develops-guidelines-for-ai-use-in-documentaries/
- https://www.gettyimages.com/visualgps/creative-trends/culture/on-authenticity
- https://jea.org/digital-media/video-explainers-engage-readers/
- https://kurzgesagt.org/youtube/
- https://www.npr.org/transcripts/4994411
- https://blogs.chapman.edu/dodge/2016/11/03/documentary-editing-workshop-gave-tips/
- https://www.theopennotebook.com/2020/01/07/videogram-how-a-vox-video-explains-the-science-behind-the-first-photo-of-a-black-hole/
- https://jupitrr.com/how-to/add-b-roll-to-talking-head-videos
