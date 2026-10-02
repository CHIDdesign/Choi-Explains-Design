# 스킬 — 🎨 모션 디자이너(움직임이 설명이 되게)

모션 DSL 장면, 자유 HTML 카드, 템플릿 그래픽의 움직임을 정할 때 적용한다. 먼저 이 움직임이 무슨 관계를 설명하는지 한 문장으로 정한다.
그다음 아래 숫자로 이징, 길이, 순서, 정지를 고른다. 기준은 30fps(1f ≈ 33ms)다. DSL `at`·`dur` 과 카드 `data-anim-*` 는 초로 적는다.

## 1. 움직임의 일 — 네 기둥 중 하나를 맡긴다

1. 모든 움직임은 Issara Willenskomer(UX in Motion)의 네 기둥 가운데 하나를 맡는다: **예상**(무엇이 될지 미리 보인다) · **연속**(앞 화면과
   같은 것이다) · **서사**(무엇이 먼저인가) · **관계**(무엇이 무엇에 속하는가). `motion_reason` 첫머리에 기둥 이름을 적는다
   (예: "관계: 흩어진 12점이 세 무리가 된다"). 어느 기둥도 맡지 않는 움직임은 fade 로 바꾸거나 지운다.
2. Mayer 의 시간 근접 원칙대로 그림을 말에 붙인다. 요소는 그 낱말보다 0.2초 먼저 도착한다. 말이 다음 대상으로 넘어가기 전에는 다음 요소를 시작하지 않는다.
3. 화면 글자는 말의 요약이다. 내레이션 문장을 그대로 띄우면 이해가 떨어진다(Mayer 의 중복 원칙). 말한 문장을 옮기는 일은 자막이 한다.
4. 볼 곳은 신호로 가리킨다(Mayer 의 신호 원칙). 손 주석 `mark`(circle·underline·arrow·bracket) 하나나 강조색 한 곳을 그 낱말에 맞춰 쓴다.
   색을 여기저기 칠해서 가리키지 않는다.

## 2. UX in Motion 12원칙을 우리 도구로

5. **이징**: 곡선은 역할로 고른다(4장).
6. **오프셋·지연**: 히어로가 먼저 오고 부품이 뒤따른다. 늦게 오는 것이 덜 중요해 보이므로, 등장 순서가 곧 위계다.
7. **부모 관계**: 사진이 움직이면 그 사진의 테이프, 이름표, `mark` 도 같이 움직인다. DSL 은 자식에게 같은 변화량의 `keys` 를 주고,
   카드는 자식을 컨테이너 하나에 넣어 컨테이너를 움직인다.
8. **변형**: 개념이 바뀌면 새 요소를 띄우지 않고 있던 요소를 바꾼다. 점이 무리가 되고(`dots.groups`·`groupAt`), 칩이 판이 된다(카드 `morph-to` width·height·borderRadius).
   Material 의 container transform 과 같은 생각이다. 상자가 다음 상자의 크기와 모양으로 자라면서 안의 내용이 바뀐다.
9. **값 변화**: 숫자와 비율은 `counter`·`bar`·`count-up` 으로 실제 값까지 간다. 끝값은 정확하게 맞추고(`decimals`·`format`), 도착한 뒤에는 흔들지 않는다.
10. **마스킹**: 글자는 마스크 리빌로, 사진은 종이 띠 안에서 드러낸다. 마스크의 가장자리가 곧 종이의 가장자리다. 흐린 마스크는 쓰지 않는다.
11. **오버레이**: 새 메모가 앞 메모 위에 놓이면 '덧붙임'이다. 아래 장은 지우지 말고 흐리게(opacity 0.5~0.6) 남겨 쌓인 논리를 보여 준다.
12. **복제**: 하나가 여럿이 되는 개념(분류, 파생)은 복제본이 원본 자리에서 시작해 `keys` 로 갈라져 나가게 한다.
13. **가림**: 초점을 옮길 때는 나머지를 `dim`·`faint` 로 내린다(밝기 30~40% 낮춤). 흐림(blur)으로 가리지 않는다.
14. **시차**: 콜라주의 층마다 밀리는 양을 다르게 준다. 바탕 종이는 0~1%, 사진은 3.5%, 큰 글자는 5% 안팎이다.
    지금 읽히고 있는 글자 층은 0% 로 둔다.
15. **입체감**: 종이는 들렸다가 놓인다. `place` 는 그림자 높이가 3에서 1로 내려앉는 진입이고, `unfold` 는 위 변을 축으로 펼쳐진다.
    3D 회전과 원근은 쓰지 않는다.
16. **달리·줌**: 4~8% 푸시인은 사진과 문서에만, 장면 길이 전체에 걸쳐 천천히 준다. 글자 판에는 쓰지 않는다.

## 3. Disney 12원칙을 종이 위에서

17. **슬로 인·슬로 아웃**: 위치와 크기에는 늘 이징을 건다. 일정한 속도는 기계처럼 읽힌다(Jitter BM-03). linear 는 타자기, 숫자 틱, 끝없는 회전에만 쓴다.
18. **호**: 대각선 이동은 휘게 만든다. 우리 `keys` 는 구간마다 inOut 이징이라 중간점을 넣으면 그 점에서 멈칫한다. 대신 x 와 y 의
    도착 시각을 0.1~0.2초 어긋나게 둔다(y 를 먼저 끝내면 볼록한 호). 선과 화살표는 `curve` 0.15~0.3.
19. **예비 동작**: 이동 거리가 20% 이상인 히어로에만 준다. 반대 방향으로 거리의 3~5% 를 3~4f 동안 물러난 뒤 출발한다.
    예비 동작의 크기는 본동작에 비례해야 한다(School of Motion). 글자와 작은 부품에는 주지 않는다.
20. **무대 연출**: 한 순간에는 한 동작만 한다. 히어로가 움직이는 동안 나머지는 멈추거나 2% 이하로만 움직인다.
21. **포즈 투 포즈**: 먼저 안착한 마지막 프레임을 완성본 품질로 설계한다. 진입은 거기서 거꾸로 짠다.
22. **팔로 스루·겹침**: 한 물체의 부품은 1~2f 씩 늦게 멈춘다(SoM 의 프레임 오프셋).
    본체 0 → 그림자 +2f → 테이프 +3f → 이름표 +4f → 손 주석 +6f 순서다.
23. **부수 동작**: 테이프가 붙고 그림자가 가라앉는 정도로 본동작의 3분의 1 이하로 작게 준다. 본동작과 같은 프레임에 끝내지 않는다.
24. **스쿼시·스트레치**: 종이는 찌그러지지 않는다. 칩, 배지, 테이프만 `settlePaper` 오버슈트 4% 이하. 글자 늘리기는 펀치 구간의
    한 방에만, 가로를 x% 늘리면 세로를 x% 줄인다(부피 보존 — Josh Comeau 도 실제로는 아주 작은 값을 권한다).
25. **과장**: 롱폼 본문에서는 과장하지 않는다. 과장은 펀치 구간과 숏폼 훅에서만 한다.
26. **탄탄한 드로잉**: 광원은 위 왼쪽 하나다. 그림자는 dx:dy = 2:3, 높이는 3단(ELEV)이다. 그림자 방향이 다른 요소가 하나도 없어야 한다.
27. **매력**: 결국 조판이다. 정렬선, 크기 대비, 모아 둔 여백이 움직임보다 먼저 눈에 들어온다.

## 4. 이징과 간격(spacing) — 곡선 모양을 안다

28. 곡선은 역할 이름으로 고른다: `enter`(작은 요소) · `enterText`(글자, expo-out) · `enterLarge`(큰 면, M3 emphasized-decelerate) ·
    `move`(화면 안 이동, M3 standard) · `exit`(M3 emphasized-accelerate) · `settle`(+1.2%) · `settlePaper`(+4%).
    카드는 `power3.out`·`expo.out` 이 진입, `power2.inOut`·`sine.inOut` 이 이동이다. `back.out` 은 쓰지 않는다.
29. **눈에 보이는 도착은 길이의 3분의 1 지점이다.** enter 곡선은 시간 25% 에 거리의 76%, 시간 50% 에 96% 를 간다.
    12f 진입이면 4f 만에 '도착했다'고 보인다. 그래서 낱말에 맞출 때는 `at + dur/3` 이 그 낱말 시각보다 앞서게 둔다.
30. **퇴장은 시간의 앞 절반에 15% 만 움직이고 끝에서 빨라진다.** 그래서 퇴장은 진입의 0.75배로 짧게 둔다. 길게 두면 머뭇거리는 것처럼 보인다.
31. **화면 안 이동은 빨리 떠나 길게 앉는다.** move 곡선은 처음 25% 시간에 61% 를 간다. 출발점을 보여 주고 싶으면 이동 대신 '자리 표시 → 채움'으로 짠다.
32. 한 영상 안에서 같은 역할에는 같은 곡선을 쓴다. 속도와 방식이 들쭉날쭉하면 바로 아마추어로 보인다.
33. Remotion 스프링의 기본값(damping 10)은 출렁인다. 스프링을 쓰려면 `overshootClamping` 을 켜거나 damping 을 20 이상으로 두어 오버슈트를 4% 이하로 묶는다.

## 5. 길이 — 거리와 면적이 정한다

34. 기준 길이(30fps): 제자리 변화(색, 밑줄 채움) 4~6f · 5% 미만 이동 8f · 메모·줄 리빌 10~12f · 판 쓸기 14~18f · 전면 22~26f · 상한 30f.
    UI 문헌의 100~500ms(NN/g, Val Head)와 M3 의 50~1000ms 토큰을, 화면 전체로 시선이 옮겨 다니는 영상에 맞게 늘린 값이다.
35. 거리가 두 배여도 길이는 두 배가 아니다(Carbon: 거리에 비선형으로 늘린다). 거리 10% 는 10f, 40% 는 16f, 80% 는 22f 정도다(`durFor`).
36. 퇴장은 진입의 0.75배다. NN/g 는 등장 300ms 에 퇴장 200~250ms 를 권하고, M3 container transform 은 300/250ms 다.
37. 다 짠 뒤 한 번 더 줄인다(Jitter BM-04: "거의 너무 빠르다" 싶을 때까지 다듬고 다시 본다). 줄이는 것은 움직임이지 읽는 시간이 아니다.
38. 읽는 시간은 따로 잡는다. 마지막 진입이 끝난 뒤 `max(1.2초, 글자 수 ÷ 7)` 동안 멈춘다.
    영상 글자는 두 번 읽을 수 있을 만큼 둔다는 SSW 규칙과 같다(넷플릭스 한국어 자막 초당 12자를 두 번 읽으면 초당 6~7자).
39. 데이터 전환 한 단계는 약 1초다. Heer & Robertson 이 권하고 실험에서 쓴 길이다. 단계 사이에는 0.3초 쉰다.

## 6. 오프셋·스태거·겹침

40. 모든 요소가 같이 시작하면 납작하고 시끄럽다(Jitter BM-01). 주 요소가 먼저 오고 보조 요소가 그 뒤를 따른다.
41. 간격은 글자 1f, 낱말 2f, 줄 3f, 블록 4~5f 다. 목록 항목은 간격이 아니라 그 항목을 말하는 순간에 맞춘다.
    말과 무관한 장식 스태거는 합쳐서 15f 를 넘기지 않는다.
42. 앞 요소가 60~70% 진행했을 때 다음 요소를 시작한다. 앞 요소가 다 멈추길 기다리면 죽은 순간이 생긴다(Jitter BM-02).
    다만 같은 0.1초 안에 시작하는 요소는 둘까지다.
43. 스태거 순서는 읽는 순서를 따른다: 왼쪽 → 오른쪽, 위 → 아래, 큰 것 → 작은 것. 목록을 아래에서 위로 쌓지 않는다.
44. 셋 이상이 서로 가리며 지나가면 눈이 따라가지 못한다. Heer 의 원칙대로 가림을 줄이고 출발을 어긋나게 한다.

## 7. 키네틱 타이포그래피

45. 한 화면에서는 한 단위만 움직인다. 글자 단위, 낱말 단위, 줄 단위를 한꺼번에 섞으면 읽히지 않는다.
46. 헤드라인은 줄 마스크(아래 → 위, 줄 간격 3f, `enterText`), 본문과 출처는 fade 다. 음절 리빌(`kinetic-chars` pattern fade)은
    10음절 이하 제목에, 영상당 2회까지.
47. 키네틱 글자는 정착한 뒤 0.5초 이상 완전히 멈춘다. 보통은 38번의 읽는 시간을 따른다. 글자의 이동은 읽기 방향을 따른다(오른쪽에서 들어와 왼쪽에 멈춘다 — legibility.info).
48. 강조어는 크기, 굵기, 서체, 색 가운데 둘을 함께 바꾼다. 형광펜(`highlight`, 민트 #86D9B5)은 핵심어 한 곳에, 그 말을 하는 순간에만 쓴다.
49. 글자에는 블러, 모션블러, 흔들림, 글로우를 쓰지 않는다. 26px 미만 글자는 움직이지 않는다.
50. 서체는 디자인 v3 역할대로: 한 방 `heavy`(Black Han Sans, 인쇄 얼룩) · 연도 Playfair 900 italic · 제목 고운바탕 700 또는 송명 ·
    주석 `hand`. 한 장면에 세 가족까지다.

## 8. 정보 디자인 — 차트는 지어진다

51. 한 장면에는 생각 하나, 한 그래프에는 주장 하나다. 제목은 축 이름이 아니라 결론 문장이다("2배가 됐다" — Datawrapper).
52. 짓는 순서: 틀(축, 기준선, `ghost` 막대) 0초 → 데이터(말에 맞춰) → 강조(한 막대만 강조색, 나머지 dim) → 주석(`mark` + 짧은 글) → 정지.
    Nussbaumer 도 빈 그래프에 점 하나를 놓고, 그 맥락을 말한 뒤 변화를 보여 준다.
53. 범례 대신 데이터 바로 옆에 라벨을 단다(공간 근접). 라벨은 28px 이상이고, 주석이 10어절을 넘으면 왼쪽 정렬한다.
54. 한 단계에서는 하나만 바꾼다. 축 눈금이 바뀌는 단계에서는 값을 움직이지 않는다.
    Heer 의 실험에서 축 변경과 값 변경을 나눈 단계 전환이 더 정확히 읽혔다. 회전보다 이동과 확대가 읽기 쉽다.
55. 막대는 0 기준선에서 시작한다. 눈금은 0·5·10 처럼 익숙한 간격을 쓴다. 쓸모없는 소수점은 빼고, 숫자와 단위는 붙인다(Apple 차트 지침).
56. 카운터는 0.8~1.2초 동안 세고 끝에서 멈춘다(DSL `settle`, 카드 `power3.out`). 숫자가 주인공이면 Playfair 900 italic 160px 이상에, 옆에 명조 한 줄을 붙인다.

## 9. Jitter 템플릿 어휘를 우리 도구로

57. **쌓이는 카드**: 종이 3~4장을 4~5f 간격으로 `place`, 회전은 장마다 다르게 ±1~3°. 새 장이 오면 앞 장들은 `keys` 로 2~3% 위로
    밀리고 opacity 0.6 으로 내려간다.
58. **중첩 마스크 깊이**: 바깥 종이 띠가 마스크로 열리는 동안 안의 사진은 108% 에서 100% 로 줄며 들어온다.
    반대 방향의 두 움직임이 깊이를 만든다(Jitter nested mask). 카드에서는 바깥에 `mask-reveal`, 안쪽에 시작 배율 1.08 + `morph-to {"scale":1}` 을 쓴다.
59. **모프**: 점이 무리로, 원이 막대로, 칩이 판으로 바뀐다. 색이나 위치 가운데 하나는 이어져야 모프로 읽힌다.
60. **궤도**: 순환이나 생태계를 말할 때만. 컨테이너에 `morph-to {"rotate":120}`, 자식에 `{"rotate":-120}` — 반대 회전으로 글자가
    똑바로 선다(Jitter orbit carousel). 한 번 돌고 멈춘다. 끝없이 도는 장식은 쓰지 않는다.
61. **늘어나는 글자**: 자간 트윈으로 대신한다(`morph-to {"letterSpacing":"-0.01em"}`, 시작 0.3em 에서도 상자 안, 0.5초, power3.out). 세로로 늘리는 효과는 펀치 구간의 heavy 한 낱말에만 쓴다.
62. **매치 컷**: 같은 시퀀스의 다음 장면이 앞 장면 마지막 요소와 같은 자리, 크기, 색에서 시작하면 컷이 하나의 움직임으로 이어 읽힌다(Jitter BM-05).
    영상당 2~3번, 하이라이트로만 쓴다.
63. UI, 기기 목업, 정밀한 데이터 장면은 🛠 시그니처 장면이 맡는다. 모션 장면 안에서는 단순화한 종이 프린트로 그린다.
64. 그라디언트 오브, 유리 블러, 글리치, 네온, 스크램블은 우리 재질이 아니다. Jitter 에서는 움직임의 구조만 가져오고, 표면은 언제나 종이와 잉크다.

## 10. '템플릿'이 아니라 '디자인'으로 보이게

65. 장면마다 사건이 하나 있다. 무엇이 무엇으로 바뀌는 순간(모임, 갈라짐, 채워짐, 그어짐)이다. 사건 없이 요소가 차례로 뜨기만 하면 슬라이드다.
66. 구도는 비대칭으로 짠다. 히어로를 3분할 교점에 두고 여백은 한쪽에 모은다. 가운데 정렬 3단 스택(킥커 → 큰 글자 → 작은 글자)은 만들지 않는다.
67. 실물이 기호보다 먼저다. 자료가 있으면 `frame: "print"` 사진이 주인공이고, 그 위에 `mark` 로 볼 곳을 가리킨다.
68. 직전 장면과 구도나 진입 가운데 하나는 바꾼다. 챕터의 키(종이 무늬 + 주 진입)는 그 챕터 그래픽의 60% 이상이 따른다.
69. 움직임의 양보다 정지의 질이 중요하다. 큰 움직임 뒤에 1.2초 이상 멈춘 화면이 리듬을 만든다.

## 체크리스트

- [ ] 모든 `motion_reason` 이 기둥(예상·연속·서사·관계)으로 시작하고, 장면에 사건이 하나 있다.
- [ ] 0.5초 프레임에 제목, 주 요소, `ghost` 가 서 있다(완성의 35% 이상).
- [ ] 히어로 하나만 크게 움직이고, 같은 0.1초에 시작하는 요소는 둘 이하다.
- [ ] 진입·이동·퇴장·정착의 곡선이 역할에 맞다. linear 는 틱과 회전에만 썼다.
- [ ] 길이가 거리 표에 맞고(30f 이하), 퇴장이 진입의 0.75배이며, 대각선이 휜다.
- [ ] 부품이 1~2f 씩 늦게 멈추고, 장식 스태거 합계가 15f 이하다.
- [ ] 마지막 진입 뒤 `max(1.2초, 글자 ÷ 7)` 동안 정지하고, 읽히는 중인 글자는 움직이지 않는다.
- [ ] 차트: 결론 제목, 0 기준선, 직접 라벨, 한 단계 한 변화, 강조 막대 하나.
- [ ] 오버슈트 4% 이하, pop·stretch 는 펀치 구간에만, 글자에 블러가 없다.
- [ ] 직전 장면과 구도나 진입이 다르고, 표면은 종이·잉크·강조색 한 곳이다.

## 출처
- https://ixd.prattsi.org/2017/04/creating-usability-with-motion-the-ux-in-motion-manifest/
- https://www.studio2a.co/12-principles-of-motion-design/
- https://schoolofmotion.com/blog/intro-to-the-graph-editor-in-after-effects
- https://schoolofmotion.com/blog/understanding-the-principles-of-anticipation
- https://schoolofmotion.com/blog/animation-tricks-follow-through-after-effects
- https://raw.githubusercontent.com/material-components/material-components-android/master/docs/theming/Motion.md
- https://www.nngroup.com/articles/animation-duration/
- https://valhead.com/2016/05/05/how-fast-should-your-ui-animations-be/
- https://carbondesignsystem.com/elements/motion/overview/
- https://help.jitter.video/en/articles/16072573-bm-01-staggering-the-motion-trick-that-changes-everything
- https://help.jitter.video/en/articles/16072579-bm-02-overlap-animations-to-create-momentum-and-continuity
- https://help.jitter.video/en/articles/16072578-bm-03-fix-robotic-animations-with-the-right-easing-curve
- https://help.jitter.video/en/articles/16072577-bm-04-nailing-the-rhythm-and-speed-of-your-animations
- https://help.jitter.video/en/articles/16072575-bm-05-match-cuts
- https://help.jitter.video/en/articles/16072568-create-a-nested-mask-depth-effect
- https://help.jitter.video/en/articles/16072571-create-an-orbit-carousel-animation
- https://jitter.video/templates/all/
- https://legibility.info/rules-for-text-in-videos
- https://www.ssw.com.au/rules/post-production-do-you-give-enough-time-to-read-texts-in-your-videos
- https://idl.cs.washington.edu/files/2007-AnimatedTransitions-InfoVis.pdf
- https://datavizblog.com/2015/04/02/cole-nussbaumer-storytelling-with-data/
- https://www.datawrapper.de/blog/text-in-data-visualizations
- https://developer.apple.com/tutorials/data/design/human-interface-guidelines/charts.json
- https://www.elevatelearning.org/insights/mayers-twelve-principles-of-multimedia/
- https://www.joshwcomeau.com/animation/squash-and-stretch/
- https://www.remotion.dev/docs/spring
