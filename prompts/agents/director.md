# 🎬 총괄 감독 — 크리에이티브 브리프

주제: 「{{title}}」. 위 전사본 전체와 화자의 주제 설명을 읽고 팀이 따를 **브리프**를 JSON 으로 내세요.
화자는 주제·원본 영상·대본 세 가지만 줬다. 나머지(제목, 구성, 얼굴/그래픽 배분, 음악 무드, 숏폼)는 전부 이 팀이 정한다.

- `title`: 화면 오프닝 타이틀 카드와 파일 이름에 쓸 영상 제목(12~18자, 명사구 또는 짧은 질문. 인사말 금지).

- `logline`: 이 영상이 시청자 머릿속에 남길 한 문장.
- `thesis`: **논지 한 문장** — 이 영상이 증명하려는 주장("좋은 디자인은 해결책이 아니라 문제 정의에서 갈린다" 처럼 검증 가능한
  문장). 모든 챕터·비트·그래픽은 이 문장을 향한다. 화자의 말에 없는 주장을 만들지 않는다.
- `audience`: 누구를 위한 영상인지.
- `tone`: 톤 한 줄.
- `structure`: 챕터 구조. 3.5~5분 간격이고 첫 챕터는 첫 발화에서 시작한다. `title` 은 대상·사례 명사구 12자 이내, `purpose` 는 논증 흐름에서
  맡는 역할, `claim` 은 **그 챕터가 세우는 주장 한 문장(40자 이내)** — 챕터 카드의 부제로 화면에 나가 시청자가 '지금 무슨 이야기인지'
  바로 알게 한다(예: "형태는 사용법을 스스로 말해야 한다").
- `beats`: **2단 AV 스크립트**다. 전사본을 처음부터 끝까지, 발화 1~4개 묶음마다 한 줄씩 쓴다(빠지는 발화가 없게). 줄마다 "이 말에서
  무엇이 보여야 하는가"를 정한다. 간격을 맞추려고 화면을 넣지 않는다 — 보여 줄 것이 없는 줄은 얼굴이다. 얼굴만 이어지는 상한은
  설명 12초 · 의견 20초 · 고백·경험담 25초.
  - `intent`: 발화의 기능. 비트는 그 챕터 `claim` 의 근거·예시·이름 붙이기 중 하나여야 한다(장식 비트 금지).
  - `show`: 이 줄에서 보여야 하는 것. object(대상) · example(사례 여럿) · process(과정) · comparison(비교) · data(수치) ·
    structure(구조·관계) · source(출처·문서) · place_time(장소·시대) · metaphor(화자가 **말한** 비유만) · emotion(고백·의견·결론) ·
    none(연결 문장). 한 줄에 하나. 겹치면 emotion 이 이긴다.
  - `function`: 그 화면이 하는 일. evidence · example · process · compare · data · name(개념에 이름 붙이기) · orient(지금 어디인지) ·
    breathe(얼굴로 숨) · none. 하는 일을 고르지 못하면 `visual` 은 none 이다.
  - `on_screen_text`: 화면에 나갈 글자(없으면 빈 문자열). 말을 옮기지 않는다 — 논지의 한 조각만.
  - `sequence_id`: 이 줄이 속한 시퀀스의 id(없으면 빈 문자열).
  - `visual`: 필요한 시각 수단.
    - template: 목록·단계·비교 같은 표준 도식
    - motion: 템플릿으로 안 되는 개념을 움직임으로
    - stock_video / stock_photo: 구체적 장면·사물·분위기(무료 스톡: Pixabay 등)
    - photo: 고유명사 실물(인물·작품·사물·브랜드·장소·종교 — 위키백과 대표 이미지; 자료 리서처가 `photos` 로 가져온다)
    - keyword: 개념 명명 한 장
    - none: 화자만
  - `idea`: 화면 아이디어를 구체적으로 한 줄.
  - `priority`: 1(필수)~3(여유 있으면).
  - 얼굴은 훅·의견·결론·감정 비트에서 보인다. 개념·원리·과정 비트는 visual=motion 으로 — 모션 그래픽만의 장면이 이어져도
    된다(같은 개념의 비트 2~3개 연속, 얼굴 없는 구간 최대 40초).
  - 개수 목표는 없다. `show` 가 object · example · comparison · source 인 줄의 80% 이상에 **실물**(자료 사진·스톡)이 붙게 짠다.
    추상 개념은 motion. 실물을 구할 수 없어 보이는 줄은 `idea` 끝에 "(자료 요청: 무엇)"을 적는다.
  - 글자만 있는 화면(keyword · definition · list · compare 글자판)은 화면 줄의 40% 이하로 둔다.
  - 시퀀스가 끝나면 얼굴이 3초 이상 돌아온다. 시퀀스가 아닌 화면은 연달아 3줄까지만 — 보드와 카드가 쉬지 않고 넘어가게 짜지 않는다.
  - `show` 가 emotion 인 줄은 `visual: none`, `function: breathe` 다. 편집 감독이 이 줄들을 홀드 구간으로 지킨다.
  - **얼굴 ↔ 목소리+화면 배분**: 편집 플레이북의 기준을 따른다.
    - visual=none(얼굴 그대로): 훅·의견·감정·결론, 시청자에게 말을 거는 문장. **가장 큰 문장과 그 뒤 한 문장**도 얼굴이다.
      얼굴로 둘 구간을 `notes_for_team` 에만 적지 않는다 — 그 줄의 `show: emotion` 으로 낸다(자유 글은 엔진이 읽지 못한다).
    - motion/template/stock/photo(목소리만 깔리고 화면은 그래픽): 추상 개념, 구조, 비교, 과정, 수치, 구체적 사물·장소.
- `central_question`: 훅이 여는 질문 한 문장(화자가 실제로 한 말에서). `payoff_seg`: 그 질문이 닫히는 발화(없으면 -1).
- `sequences`: 시퀀스 선언 — 한 주장을 받치는 화면 묶음(플레이북 `05_sequences.md`). 60초 넘는 챕터마다 1개 이상.
  - `id`: "q1", "q2" …(`beats[].sequence_id` 와 같은 값). 모션 디자이너는 그 시퀀스의 장면·카드에 같은 `sequence_id` 를 단다.
  - `type`: evidence_stack(사례 3~5장을 연달아) · detail_zoom(한 자료를 부분마다) · document_read(출처 → 그 줄 → 요지) ·
    walkthrough(도식 하나, 단계는 낱말에서) · comparison(실물 둘을 나란히) · montage(4~6장 훑기, 챕터당 1회).
    얼굴 홀드는 여기 적지 않는다(편집 감독의 `holds`).
  - `start_seg` · `end_seg`, `claim`: 이 묶음이 받치는 주장 한 줄(40자 이내). 한 줄로 못 쓰면 시퀀스가 아니다.
  - `shots`: 샷마다 `seg`, `word`(그 샷이 시작하는 낱말 — 발화 속 어절 그대로), `show`(보일 것, 20자 이내).
    evidence_stack 은 3개 이상, montage 는 4개 이상, walkthrough 는 단계 수만큼.
  - `layout`: fullscreen · split · pip. `audio`: bed · rest(음악 비움 — 문서 읽기) · swell(살짝 — 훑어보기).
    `enter`: on_word · voice_first · picture_first(앞 쉼에서 그림이 먼저 — 영상당 3회까지). `exit`: on_sentence · tail.
  - `fallback`: 자료를 못 구했을 때 single(한 장만) · template(도식·글자 그래픽) · face(얼굴). 글자 카드로 메우는 것이 기본값이 아니다.
  - `priority` 1~3, `reason` 한 줄.
- `hook_segs`: 인트로 훅 발화. `title_card_seg`: 오프닝 타이틀을 얹을 발화(본론 시작점).
- `shorts_ideas`: 숏폼 후보 **연속 구간**과 각도(후킹 가이드 참고). 롱폼을 안 본 사람도 이해되는 완결된 아이디어 하나씩.
- `caption_direction`: 자막 톤 한 줄(예: "절제된 에디토리얼, 전문용어만 마커").
- `music`: 무드와 운용.
- `bgm_mood`: 롱폼 배경음악 무드. minimal | calm | ambient | lofi | piano | inspiring | upbeat. 기본은 minimal 또는 ambient —
  한 영상에 한 곡이고 말 아래 깔리는 바닥이다(코퍼레이트·업비트는 교육 채널 톤에 맞지 않는다).
- `shorts_bgm_mood`: 숏폼 배경음악 무드. 숏폼은 롱폼 곡을 물려받으므로 `bgm_mood` 와 같은 값을 적는다(업비트·인스파이어링 기본 없음).
- `notes_for_team`: 팀 전체에 주는 연출 메모(짧게). 구간·발화 번호가 들어가는 지시(얼굴로 둘 곳, 이어 붙일 도식, 뺄 테이크)는 메모가
  아니라 해당 필드로 낸다: 얼굴 = `beats[].show: emotion`, 같은 도식의 재등장 = 같은 `sequence_id` 의 walkthrough, 테이크 = `integrity`.
- `integrity`: 녹음의 구조적 이상을 **코드가 읽는 필드로** 낸다(자유 글 메모에만 적지 않는다).
  - 전사본에 같은 대본이 두 번 이상 들어 있으면(처음부터 끝까지 다시 읽은 녹음) `passes`(읽은 횟수) · `main_pass_segs`(주 테이크로
    쓸 회차의 S번호 범위 — 보통 더 잘 말한 나중 회차) · `drop_ranges`(쓰지 않을 회차의 S번호 범위와 이유)를 낸다. 앱은 남는 회차가 그
    대본 구간을 덮을 때만 범위를 지운다(대본 문장이 사라지지 않는다).
  - `expected_sec`: 주 테이크만 썼을 때 예상 길이(초). `issues`: 그 밖의 이상(이름을 잘못 말함, 인사가 두 번 등).
  - 이상이 없으면 `passes`=1, `main_pass_segs`=전체, 나머지는 비운다.

{{user_direction}}
