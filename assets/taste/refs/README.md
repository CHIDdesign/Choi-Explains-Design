# 🎯 레퍼런스 분석 결과(공유)

운영자가 '🎯 레퍼런스' 창(또는 `run_reference.bat`)에 사진·영상을 끌어다 놓아 분석한 결과 중, 저장소에 올린 것.
파일 하나 = 레퍼런스 하나(`<slug>.json`): 코드가 잰 측정값(컷 박자·샷 길이·움직임·팔레트·밝기·대비·선 밀도)과 Claude 가 뽑은
규칙(글자·색·도형·모티프·움직임·박자·기법마다 우리 카드 런타임 레시피·우리 채널로 옮길 때·가져오지 않을 것).

- 모든 디자인 역할(스타일 프레임·모션·시그니처·카드 수정·아트 디렉터·장면 심사)이 매번 이 규칙을 읽는다(`studio/agents/reference.py rules_block`).
  운영자 PC 의 로컬 분석(`user/taste/refs`, 저장소 밖)과 합쳐지고 같은 slug 는 로컬이 이긴다.
- 올리는 길: 운영자 PC 에서 '🎯 레퍼런스 › zip 으로 내보내기'(또는 `python -m studio reference --export`) → zip 을 전달 →
  `python -m studio reference --import <zip>` → 커밋. 기본은 JSON 만 — 공개 저장소라 컷 시트(남의 영상 프레임)는 `--with-sheets` 일 때만.
- 원본 사진·영상 파일은 넣지 않는다.
