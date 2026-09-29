# 🎬 총괄 감독 — 크리에이티브 브리프

가제 「{{title}}」. 위 전사본 전체를 읽고 팀이 따를 **브리프**를 JSON 으로 내세요.

- `logline`: 이 영상이 시청자 머릿속에 남길 한 문장.
- `audience`: 누구를 위한 영상인지.
- `tone`: 톤 한 줄.
- `structure`: 챕터 구조. 3.5~5분 간격이고 첫 챕터는 첫 발화에서 시작한다. `title` 은 대상·사례 명사구 12자 이내, `purpose` 는 논증 흐름에서 맡는 역할.
- `beats`: 연출 비트 목록. 영상 전체에 걸쳐 20~40초마다 하나 정도.
  - `intent`: 발화의 기능.
  - `visual`: 필요한 시각 수단.
    - template: 목록·단계·비교 같은 표준 도식
    - motion: 템플릿으로 안 되는 개념을 움직임으로
    - stock_video / stock_photo: 구체적 장면·사물·분위기(Pexels)
    - photo: 고유명사 실물(위키미디어)
    - keyword: 개념 명명 한 장
    - none: 화자만
  - `idea`: 화면 아이디어를 구체적으로 한 줄.
  - `priority`: 1(필수)~3(여유 있으면).
  - 비트 사이에 visual=none 인 '정적' 구간을 둔다.
- `hook_segs`: 인트로 훅 발화. `title_card_seg`: 오프닝 타이틀을 얹을 발화(본론 시작점).
- `shorts_ideas`: 숏폼 후보 구간과 각도(후킹 가이드 참고).
- `caption_direction`: 자막 톤 한 줄(예: "절제된 에디토리얼, 전문용어만 마커").
- `music`: 무드와 운용.
- `notes_for_team`: 팀 전체에 주는 연출 메모(짧게).

{{user_direction}}
