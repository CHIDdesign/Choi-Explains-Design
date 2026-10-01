# `prompts/agents/director.md` 고칠 곳 — 비트를 2단 AV 스크립트로, 시퀀스를 선언

지울 줄·바꿀 줄·더할 줄만 적었다(나머지는 그대로). 스키마는 `docs/upgrade/05_편집_문법_v2.md` 6-1, 규칙은 플레이북 `05_sequences.md`.
`integrity`(대본을 두 번 읽은 경우)는 `docs/upgrade/13_에이전트_팀_v2.md` 2-1, `visual` 의 `evidence` 안내는 `visual_researcher` 쪽 문서를 따른다 — 여기서 다시 쓰지 않는다.

---

## 1. `beats` 첫 줄 — 할당량을 지운다

### 지금
> - `beats`: 연출 비트 목록. 영상 전체에 걸쳐 **8~15초마다 하나**(얼굴만 보이는 구간은 최대 12초). 예전 기준(20~40초)은 너무 드물어
>   "그래픽이 너무 없다"는 피드백을 받았다.

### 바꿈
> - `beats`: **2단 AV 스크립트**다. 전사본을 처음부터 끝까지, 발화 1~4개 묶음마다 한 줄씩 쓴다(빠지는 발화가 없게). 줄마다 "이 말에서 무엇이 보여야 하는가"를 정한다.
>   간격을 맞추려고 화면을 넣지 않는다 — 보여 줄 것이 없는 줄은 얼굴이다. 얼굴만 이어지는 상한은 설명 12초 · 의견 20초 · 고백·경험담 25초.

## 2. `beats` 항목 — 필드를 더한다

### 더함(`intent` 줄 바로 뒤)
> - `show`: 이 줄에서 보여야 하는 것. object(대상) · example(사례 여럿) · process(과정) · comparison(비교) · data(수치) · structure(구조·관계) · source(출처·문서) ·
>   place_time(장소·시대) · metaphor(화자가 **말한** 비유만) · emotion(고백·의견·결론) · none(연결 문장). 한 줄에 하나. 겹치면 emotion 이 이긴다.
> - `function`: 그 화면이 하는 일. evidence · example · process · compare · data · name(개념에 이름 붙이기) · orient(지금 어디인지) · breathe(얼굴로 숨) · none.
>   하는 일을 고르지 못하면 `visual` 은 none 이다.
> - `on_screen_text`: 화면에 나갈 글자(없으면 빈 문자열). 말을 옮기지 않는다 — 논지의 한 조각만.
> - `sequence_id`: 이 줄이 속한 시퀀스의 id(없으면 빈 문자열).

### 지금
> - 비트 사이에는 얼굴이 보이는 3~6초 숨 고르기를 둔다(길게 비우지 않는다).

### 바꿈
> - 시퀀스가 끝나면 얼굴이 3초 이상 돌아온다. 시퀀스가 아닌 화면은 연달아 3줄까지만 — 보드와 카드가 쉬지 않고 넘어가게 짜지 않는다.
> - `show` 가 emotion 인 줄은 `visual: none`, `function: breathe` 다. 편집 감독이 이 줄들을 홀드 구간으로 지킨다.

### 지금
> - 구체적인 사물·장면·사례가 나오면 stock_photo / stock_video 를 적극적으로(영상당 6~14개). 추상 개념은 motion.

### 바꿈
> - 개수 목표는 없다. `show` 가 object · example · comparison · source 인 줄의 80% 이상에 **실물**이 붙게 짠다. 추상 개념은 motion.
>   실물을 구할 수 없어 보이는 줄은 `idea` 끝에 "(자료 요청: 무엇)"을 적는다 — 검토 시트의 자료 요청 목록으로 간다.
> - 글자만 있는 화면(keyword · definition · list · compare 글자판)은 전체 화면 줄의 40% 이하로 둔다.
> - 개념에 이름을 붙이는 줄(`function: name`) 앞 15초 안에 그 개념의 구체 사례가 보이게 한다. 대본 순서는 바꾸지 않는다 — 뒤에 나올 사례 이미지를 앞에서 1.5초 미리 보여 주는 방식으로 맞춘다.

## 3. `structure` — 챕터 사이의 관계

### 더함(`claim` 설명 뒤)
> `link` 는 앞 챕터와의 관계다: start(첫 챕터) · therefore(그래서) · but(하지만) · and(그리고).
> and 가 두 번 이어지면 나열이다 — 그대로 적는다(순서를 바꾸지는 않는다. 화자에게 가는 피드백이 된다).

## 4. 새 필드 — 질문, 주인공 자료, 시퀀스

### 더함(`thesis` 뒤)
> - `central_question`: 훅이 여는 질문 한 문장(화자가 실제로 한 말에서). `payoff_seg`: 그 질문이 닫히는 발화(없으면 -1).
> - `hero`: 이 영상의 **주인공 자료** — 논지를 가장 직접 보여 주는 실물 하나(화자의 과제물, 그 책의 그 쪽, 그 제품). `what` 에 무엇인지,
>   `first_seg` 에 본론에서 처음 뜯어보는 발화, `callback_seg` 에 결론에서 다시 부를 발화. 없으면 `""` · -1 · -1.
>   훅 구간의 `beats` 한 줄에 이 자료를 1.5~3초 예고하는 화면을 넣는다.

### 더함(`beats` 뒤)
> - `sequences`: 시퀀스 선언. 한 주장을 받치는 화면 묶음이다(플레이북 `05_sequences.md`). 60초 넘는 챕터마다 1개 이상.
>   - `id`: "q1", "q2" … (`beats[].sequence_id` 와 같은 값)
>   - `type`: evidence_stack(사례 3~5장을 연달아) · detail_zoom(한 자료를 부분마다) · document_read(출처 → 그 줄 → 요지) ·
>     walkthrough(도식 하나, 단계는 낱말에서) · comparison(실물 둘을 나란히) · montage(4~6장 훑기, 챕터당 1회).
>     얼굴 홀드는 여기 적지 않는다(편집 감독의 `holds`).
>   - `start_seg` · `end_seg`, `claim`: 이 묶음이 받치는 주장 한 줄(40자 이내). 한 줄로 못 쓰면 시퀀스가 아니다.
>   - `shots`: 샷마다 `seg`, `word`(그 샷이 시작하는 낱말 — 발화 속 어절 그대로), `show`(보일 것, 20자 이내).
>     evidence_stack 은 3개 이상, montage 는 4개 이상, walkthrough 는 단계 수만큼.
>   - `layout`: fullscreen · split · pip. 뜯어보기·문서 읽기·훑어보기는 fullscreen 이 기본이다.
>   - `audio`: bed(음악 그대로) · rest(음악을 비움 — 문서 읽기) · swell(살짝 올림 — 훑어보기).
>   - `enter`: on_word(그 낱말에서) · voice_first(화자가 얼굴로 문장을 시작한 뒤 컷) · picture_first(앞의 쉼에서 그림이 먼저 — 영상당 3회까지).
>     `exit`: on_sentence · tail(다음 문장 첫머리까지 남김).
>   - `fallback`: 자료를 못 구했을 때. single(한 장만) · template(도식·글자 그래픽) · face(얼굴). 글자 카드로 메우는 것이 기본값이 아니다.
>   - `priority` 1~3, `reason` 한 줄.

## 5. 얼굴 ↔ 화면 배분 문단 — 한 줄 더하기

### 지금
> - visual=none(얼굴 그대로): 훅·의견·감정·결론, 시청자에게 말을 거는 문장.

### 바꿈
> - visual=none(얼굴 그대로): 훅·의견·감정·결론, 시청자에게 말을 거는 문장. **가장 큰 문장과 그 뒤 한 문장**도 얼굴이다.
>   얼굴로 둘 구간을 `notes_for_team` 에만 적지 않는다 — 그 줄의 `show: emotion` 으로 낸다(자유 글은 엔진이 읽지 못한다).

## 6. `notes_for_team` — 쓰지 말아야 할 것

### 더함
> 구간·발화 번호가 들어가는 지시(얼굴로 둘 곳, 이어 붙일 도식, 뺄 테이크)는 메모가 아니라 해당 필드로 낸다:
> 얼굴 = `beats[].show: emotion`, 같은 도식의 재등장 = 같은 `sequence_id` 계열의 walkthrough, 테이크 = `integrity`.
