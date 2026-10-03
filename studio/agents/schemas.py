"""스튜디오 에이전트별 구조화 출력 스키마(모든 object 는 additionalProperties=false + 전체 required)."""
from __future__ import annotations

from ..director.catalog import LAYOUTS, TEMPLATE_NAMES
from ..director.schema import BOOL, GRAPHIC, HOOK_TYPES, INT, INT_LIST, NUM, SHORTS_PLAN, STR, STR_LIST, _obj

INTENTS = ["hook", "context", "explain", "example", "name_concept", "story", "data", "compare", "transition",
           "return_to_life", "payoff"]
VISUALS = ["none", "template", "motion", "evidence", "keyword",
           "stock_video", "stock_photo", "photo"]      # 뒤 셋은 저장된 계획 호환용 — 프롬프트에서는 evidence 만 안내
# ✂️ 편집 감독이 표시하는 '강조 순간' — 편집 문법 엔진(studio/edit/grammar.py)이 강조 글라이드·콜아웃·강조 자막·효과음으로 옮긴다
MOMENT_KINDS = ["punchline", "reveal", "shift", "conclusion", "question", "number", "joke"]
BGM_MOODS = ["minimal", "calm", "ambient", "lofi", "piano", "inspiring", "upbeat"]
LOOKS = ["warm_rich", "natural", "warm_film", "clean_bright", "cinematic"]

# 시퀀스와 리듬(docs/upgrade/05_편집_문법_v2.md 2·4·6장) — 화면을 바꾸는 이유는 시계가 아니라 문장의 내용(show)
SHOWS = ["object", "example", "process", "comparison", "data", "structure", "source", "place_time",
         "metaphor", "emotion", "none"]
FUNCTIONS = ["evidence", "example", "process", "compare", "data", "name", "orient", "breathe", "none"]
SEQ_TYPES = ["evidence_stack", "detail_zoom", "document_read", "walkthrough", "comparison", "montage"]
SEQ_AUDIO = ["bed", "rest", "swell"]
SEQ_ENTER = ["on_word", "voice_first", "picture_first"]
SEQ_EXIT = ["on_sentence", "tail"]
SEQ_FALLBACK = ["single", "template", "face"]
RHYTHM = ["slow", "steady", "fast"]
SEQUENCE = _obj({
    "id": STR,                                           # "q1", "q2" …
    "type": {"type": "string", "enum": SEQ_TYPES},
    "start_seg": INT, "end_seg": INT,
    "claim": STR,                                        # 이 묶음이 받치는 주장 한 줄(40자 이내)
    "shots": {"type": "array", "items": _obj({"seg": INT, "word": STR, "show": STR})},
    "layout": {"type": "string", "enum": ["fullscreen", "split", "pip"]},
    "audio": {"type": "string", "enum": SEQ_AUDIO},
    "enter": {"type": "string", "enum": SEQ_ENTER},
    "exit": {"type": "string", "enum": SEQ_EXIT},
    "fallback": {"type": "string", "enum": SEQ_FALLBACK},
    "priority": INT,
    "reason": STR,
})

# 🎬 총괄 감독 — 크리에이티브 브리프
# 🎨 트리트먼트(docs/upgrade/14 — Claude 총괄 제작): 조사 노트를 바탕으로 이 영상만의 시각·소리 설계
PLAN_LAYOUTS = ["face", "face_callout", "face_photo", "collage", "photo_full", "stock_video", "quote_over_footage",
                "document", "motion", "signature", "board", "timeline", "compare"]
# 모션 그래픽에서 흔히 쓰는 효과음(매니페스트의 Pixabay·Mixkit 실제 파일) + 문구 팔레트(실제 파일로 대신 받는다)
SFX_KINDS = ["none", "whoosh_soft", "swoosh_short", "swipe", "pop", "click", "typing", "camera_shutter", "paper", "ding",
             "bell_soft", "notification", "paper_slide", "page_turn", "pencil_tick", "stamp"]
SIGNATURE_KINDS = ["ui_recreation", "object_recreation", "data_story", "diagram", "timeline", "document", "collage"]
TREATMENT = _obj({
    "concept": STR,                        # 이 영상만의 시각 콘셉트(조사에 근거한 한 문단)
    "motifs": STR_LIST,                    # 되풀이되는 시각 장치 3~5개(예: '밀까 당길까 문 손잡이', '빨간 펜 교정 표시')
    "texture_note": STR,                   # 종이 콜라주 안에서 이 주제의 질감·색 쓰임(강조색 설정은 그대로)
    "type_note": STR,                      # 서체 역할 중 이 영상에서 앞세울 것과 이유
    "sound_concept": STR,                  # 음악·효과음이 할 일(효과음은 아래 sfx 로 고른 곳에만 들어간다)
    # 대본의 흐름 그대로 — 단락(발화 범위)마다 화면 구성. 빈틈 없이 처음부터 끝까지
    "segments": {"type": "array", "items": _obj({
        "start_seg": INT, "end_seg": INT,
        "layout": {"type": "string", "enum": PLAN_LAYOUTS},
        "show": STR,                       # 화면에 무엇을(구체적인 대상·자료 이름 — '관련 이미지' 금지)
        "asset": STR,                      # 조사 노트의 무엇(인물·제품 이름·커먼즈 파일·재현 대상) — 없으면 ""
        "motion": STR,                     # 움직임·전환 아이디어 한 줄
        "sfx": {"type": "string", "enum": SFX_KINDS},
        "why": STR,
    })},
    # 이 영상의 시그니처 장면 3~6개 — 🛠 시그니처 장면 빌더가 HTML 로 정밀하게 재현한다(UI·제품·데이터 이야기)
    "signature_scenes": {"type": "array", "items": _obj({
        "id": STR, "start_seg": INT, "end_seg": INT, "start_word": STR,
        "kind": {"type": "string", "enum": SIGNATURE_KINDS},
        "title": STR,
        "brief": STR,                      # 무엇을 어떻게 — 재현 사양(치수·색·배치·글자)과 움직임 순서
        "research_ref": STR,               # 조사 노트의 근거(recreations·entities 이름)
        "motion_ref": STR,                 # 모션 레퍼런스 목록(Jitter)의 slug — 그 움직임을 참고해 다시 짓는다(없으면 "")
        "sfx": {"type": "string", "enum": SFX_KINDS},
    })},
})

BRIEF = _obj({
    "title": STR,          # 화면 타이틀 카드·파일 이름에 쓰는 영상 제목(18자 이내)
    "logline": STR,
    "thesis": STR,         # 논지 한 문장 — 이 영상이 증명하려는 주장(모든 챕터·그래픽이 이 문장을 향한다)
    "audience": STR,
    "tone": STR,
    # claim: 그 챕터가 세우는 주장 한 문장(≤40자) — 챕터 카드 부제로 화면에 나가 '지금 무슨 이야기인지' 알려 준다
    "structure": {"type": "array", "items": _obj({"title": STR, "start_seg": INT, "end_seg": INT, "purpose": STR,
                                                   "claim": STR})},
    "beats": {"type": "array", "items": _obj({
        "start_seg": INT, "end_seg": INT,
        "intent": {"type": "string", "enum": INTENTS},
        "show": {"type": "string", "enum": SHOWS},            # 이 문장이 보여야 할 것(emotion = 얼굴)
        "function": {"type": "string", "enum": FUNCTIONS},    # 이 화면이 하는 일 — 못 고르면 none(화면 없음)
        "visual": {"type": "string", "enum": VISUALS},
        "idea": STR,
        "on_screen_text": STR,                                # 화면에 나갈 글자(말을 옮기지 않는다, 없으면 "")
        "sequence_id": STR,                                   # 속한 시퀀스(없으면 "")
        "priority": INT,
    })},
    "central_question": STR,                                  # 훅이 여는 질문 한 문장
    "payoff_seg": INT,                                        # 그 질문이 닫히는 발화(-1 = 없음)
    "sequences": {"type": "array", "items": SEQUENCE},        # 한 주장을 받치는 연속 화면 묶음(플레이북 05_sequences)
    "hook_segs": INT_LIST,
    "title_card_seg": INT,
    "shorts_ideas": {"type": "array", "items": _obj({"segments": INT_LIST, "angle": STR})},
    "caption_direction": STR,
    "music": _obj({"mood": STR, "notes": STR}),
    "bgm_mood": {"type": "string", "enum": BGM_MOODS},
    "shorts_bgm_mood": {"type": "string", "enum": BGM_MOODS},
    "notes_for_team": STR,
    # 녹음의 구조적 이상(대본을 두 번 읽음·이름을 잘못 말함 등) — 자유 글 메모가 아니라 코드가 읽는 필드(docs/upgrade/13 2-1)
    "integrity": _obj({
        "passes": INT,                                                   # 대본을 처음부터 끝까지 읽은 횟수(보통 1)
        "main_pass_segs": _obj({"start_seg": INT, "end_seg": INT}),      # 주 테이크 범위(passes=1 이면 전체)
        "drop_ranges": {"type": "array", "items": _obj({"start_seg": INT, "end_seg": INT, "reason": STR})},
        "expected_sec": INT,                                             # 주 테이크만 썼을 때 예상 길이(초)
        "issues": STR_LIST,
    }),
    "treatment": TREATMENT,
})

# ✂️ 편집 감독
EDITOR = _obj({
    "drop": {"type": "array", "items": _obj({"seg": INT, "reason": STR})},
    "moments": {"type": "array", "items": _obj({
        "seg": INT, "word": STR,
        "kind": {"type": "string", "enum": MOMENT_KINDS},
        "intensity": INT,   # 1(작게) ~ 3(가장 큰 한 방)
        "callout": STR,     # 화자 옆에 크게 띄울 2줄 문구(줄바꿈 \n, 줄당 4~9자) — 없으면 빈 문자열
        "label": STR,       # 콜아웃 위 작은 맥락 라벨(2~8자, 예: "핵심", "게슈탈트 원리")
    })},
    # ⚡ 펀치 구간: 크리에이터식 펀치 편집(하드 펀치인·큰 단어 슬램·휩 전환·임팩트 효과음)을 허용하는 특정 구간 —
    # 훅·클라이맥스·빠른 열거. 0~3개, 전체의 20% 이하. 그 밖은 젠틀 규칙 그대로
    "energy_spans": {"type": "array", "items": _obj({"start_seg": INT, "end_seg": INT, "reason": STR})},
    # 🙂 얼굴 홀드: 건드리지 않을 구간 — 그 안과 뒤 1.5초에 그래픽·정리 보드·콜아웃·전환·효과음이 없다(고백·결론·질문 뒤).
    # 영상당 4~8곳, 한 곳 6~25초(docs/upgrade/05 4-3)
    "holds": {"type": "array", "items": _obj({"start_seg": INT, "end_seg": INT, "reason": STR})},
    # 리듬(밀도) 수준 — slow(새 화면 사이 12초+) · steady(6~10초) · fast(시퀀스 안 1.2~2.5초). 이웃은 한 단계씩
    "rhythm": {"type": "array", "items": _obj({"start_seg": INT, "end_seg": INT,
                                               "level": {"type": "string", "enum": RHYTHM}, "reason": STR})},
    "peak_seg": INT,                                          # 영상에서 가장 큰 순간(-1 = 없음)
    # 🎬 오프닝 하이라이트(콜드 오픈): 본편 앞에 붙일 가장 임팩트 있는 문장 2~4개(각 7초 이내, 합쳐 20초 이내).
    # 결론·반전·질문·숫자처럼 앞뒤 없이도 서는 문장. 첫 두 발화는 제외(바로 뒤에 다시 나온다)
    "highlights": {"type": "array", "items": _obj({"seg": INT, "reason": STR})},
    "pacing_notes": STR,
})

# 🎨 컬러리스트 — 비교 시트(원본 + 룩 5가지, 모두 레퍼런스 매칭 포함)를 보고 고른다
GRADE = _obj({
    "look": {"type": "string", "enum": LOOKS},
    "strength": NUM,      # 0~1
    "exposure": NUM,      # -0.15~0.15
    "warmth": NUM,        # -0.4~0.4
    "saturation": NUM,    # 0.85~1.15
    "reason": STR,
})

# 🃏 자유 HTML 카드의 스타일(prompts/card_dsl.md · studio/motion/card.py STYLES 와 같게)
CARD_STYLES = ["editorial", "academic", "whiteboard", "swiss", "minimal", "board"]

# 🎨 모션 디자이너 — 템플릿 그래픽 + 직접 설계한 모션 장면(spec_json 은 MotionSpec JSON 문자열) + 자유 HTML 카드(html 은 카드 조각)
MOTION = _obj({
    "graphics": {"type": "array", "items": GRAPHIC},
    "scenes": {"type": "array", "items": _obj({
        "start_seg": INT, "end_seg": INT, "start_word": STR,
        "layout": {"type": "string", "enum": ["fullscreen", "split"]},
        "title": STR,
        "spec_json": STR,
        "sequence_id": STR,          # 감독 브리프의 시퀀스(없으면 "")
        "hero": INT,                 # 크게 움직이는 주 요소의 번호(elements 인덱스, 없으면 −1)
        "motion_reason": STR,        # 왜 그렇게 움직이는지 한 문장(motion_craft 1번)
        "layout_name": {"type": "string", "enum": ["side", "desk", "sheet", "evidence", "stack", "strip"]},
        "motif": STR,                # 되풀이하는 도식·사물의 이름(같은 장치는 같은 이름, 영상당 2회까지, 없으면 "")
        "reason": STR,               # 첫머리에 챕터 키 "[키: 모눈 · 붙이기]"
    })},
    "cards": {"type": "array", "items": _obj({
        "start_seg": INT, "end_seg": INT, "start_word": STR,
        "layout": {"type": "string", "enum": ["fullscreen", "split", "overlay"]},
        "style": {"type": "string", "enum": CARD_STYLES},
        "title": STR,
        "html": STR,
        "timeline": STR,          # 직접 쓴 GSAP 타임라인 본문(card_dsl.md 7절) — 없으면 ""
        "sequence_id": STR,
        "layout_name": {"type": "string", "enum": ["side", "desk", "sheet", "evidence", "stack", "strip"]},
        "canvas": {"type": "string", "enum": ["long", "short"]},   # 숏폼용 카드는 숏폼 캔버스로 따로 쓴다
        "motif": STR,                                              # 되풀이하는 도식·사물의 이름(영상당 2회까지, 없으면 "")
        "reason": STR,
    })},
})

# 🎞 자료 리서처 — 무료 스톡 요청(Pixabay·Unsplash·Coverr·Pexels) + 고유명사 자료 사진(위키백과 대표 이미지)
PHOTO_KINDS = ["person", "work", "object", "brand", "place", "religion", "other"]
STOCK = _obj({
    "requests": {"type": "array", "items": _obj({
        "start_seg": INT, "end_seg": INT, "start_word": STR,
        "kind": {"type": "string", "enum": ["video", "photo"]},
        "query_en": STR, "query_ko": STR,
        "layout": {"type": "string", "enum": list(LAYOUTS)},
        "purpose": STR,      # 앱 내부 메모 — 화면에 나오지 않는다
        "must_show": STR,
        "caption": STR,      # 화면 라벨(선택): 그 문장의 주장 2~12자 — 검색어·연출 메모 금지(게이트 B3·B4)
    })},
    "photos": {"type": "array", "items": _obj({
        "start_seg": INT, "start_word": STR,
        "name_ko": STR,      # 대본 표기(화면 라벨)
        "name_en": STR,      # 위키백과 문서 제목에 가까운 원어/영어 표기(없으면 빈 문자열)
        "kind": {"type": "string", "enum": PHOTO_KINDS},
        "layout": {"type": "string", "enum": ["pip", "split", "fullscreen"]},
        "reason": STR,
    })},
})

# 🎞 자료 리서처(2단계) — 썸네일을 보고 고르기
STOCK_PICK = _obj({
    "picks": {"type": "array", "items": _obj({"request": INT, "candidate": INT, "reason": STR})},
})

# 🎞 자료 리서처 v2 — 증거 계획(docs/upgrade/03_자료_조달_엔진_v2.md 6-1). 문장마다 '무엇을 봐야 하는가'(need)를 먼저 정하고
# 앱이 need 별 사다리로 조달한다(studio/assets/ladder.py). STOCK·STOCK_PICK 은 저장된 plan.json 재실행용으로 한 버전 남긴다
NEEDS = ["own_material", "entity", "primary_source", "screenshot", "code_drawn", "stock"]
EV_ROLES = ["proof", "example", "context", "process", "mood"]
EV_KINDS = ["person", "work", "product", "brand", "site_app", "place", "organization", "publication", "other"]
EV_SHOTS = ["subject", "screen", "logo", "portrait", "detail", "context", "first_page", "figure", "cover"]
TREATMENTS = ["hero", "full", "pip", "sequence", "grid", "stack", "cutout", "archive_card",
              "doc_highlight", "browser_frame", "detail_zoom", "annotate", "compare_pair", "collage"]
TIERS = ["A", "B", "C"]
FALLBACKS = ["type_card", "code_drawn", "stock", "face"]

EVIDENCE = _obj({
    "items": {"type": "array", "items": _obj({
        "start_seg": INT, "end_seg": INT, "start_word": STR,
        "claim": STR,                    # 이 자료가 뒷받침하는 화자의 말(40자 이내)
        "need": {"type": "string", "enum": NEEDS},
        "role": {"type": "string", "enum": EV_ROLES},
        "subject": _obj({
            "name_ko": STR, "name_en": STR,              # 대본 표기 / 원어 표기(모르면 "")
            "kind": {"type": "string", "enum": EV_KINDS},
            "shot": {"type": "string", "enum": EV_SHOTS},
            "creator_en": STR, "year": STR, "qid": STR,  # 모르면 ""
        }),
        "source": _obj({                 # primary_source·screenshot 일 때만, 아니면 전부 ""
            "citation": STR, "doi": STR, "url": STR,
            "as_of": STR,                # "2012-03" — 과거 시점 화면
            "locator": STR,              # 밑줄 칠 문장·그림 번호
        }),
        "stock": _obj({"kind": {"type": "string", "enum": ["video", "photo"]}, "query_en": STR, "query_ko": STR}),
        "local_file": STR,               # own_material: 자료 폴더의 파일명(없으면 "")
        "must_show": STR, "avoid": STR,
        "count": INT,                    # 1~5
        "label": STR,                    # 화면 제목(14자 이내, 주장의 한 조각). 없으면 ""
        "caption": STR,                  # 사실 캡션(24자 이내: 연도·작가·출처). 없으면 ""
        "display": STR,                  # 콜라주: 사진 뒤 큰 글자(2~8자, 그 문장의 핵심 낱말). 없으면 ""
        "commons_files": STR_LIST,       # 조사 노트가 확인한 위키미디어 공용 파일 이름('File:' 없이) — 사다리가 먼저 쓴다
        "quote": STR,                    # full(영상·사진 전면) 위 인용 한 줄(화자의 말을 줄인 것, 36자 이내). 없으면 ""
        "treatment": {"type": "string", "enum": TREATMENTS},
        "focus": STR,                    # detail_zoom·annotate 대상(말로)
        "annotations": {"type": "array", "items": _obj({
            "type": {"type": "string", "enum": ["circle", "arrow", "underline", "bracket", "label"]},
            "target": STR, "text": STR, "at_word": STR})},
        "pair": _obj({"name_ko": STR, "name_en": STR, "label": STR}),   # compare_pair 가 아니면 전부 ""
        "tier_max": {"type": "string", "enum": TIERS},
        "fallback": {"type": "string", "enum": FALLBACKS},
        "priority": INT,                 # 1(필수) ~ 3
        "sequence_id": STR,              # 05 문서: 속한 시퀀스("" = 단발)
    })},
    "notes": STR,
})

# 🎞 자료 리서처(후보 고르기 v2) — 0~3점 채점, 2점 이상만 쓴다(게이트 B6)
EVIDENCE_PICK = _obj({
    "picks": {"type": "array", "items": _obj({
        "request": INT,
        "choices": {"type": "array", "items": _obj({
            "candidate": INT,
            "score": INT,                                 # 0~3
            "main_subject": BOOL,
            "cliche": BOOL,
            "shows": STR,                                 # 실제로 보이는 것 한 줄
            "focus_box": {"type": "array", "items": NUM},  # [x, y, w, h] 0~1, 없으면 []
        })},
        "reason": STR,
        "retry_query_en": STR,     # 2점 이상이 없을 때: 맞는 자료를 찾을 영어 검색어 3~6낱말(다른 대상·행동·화각), 아니면 ""
    })},
})

# 🎼 음악 감독 — 큐 시트(docs/upgrade/04_음악_사운드_엔진_v2.md 3-1): 어디서 들어오고 나가고, 어디에 없는지
SUITES = ["felt", "analog", "brush", "air"]
CUE_ROLES = ["theme", "bed", "air", "reprise"]
CUE_ENTRIES = ["downbeat", "fade_in"]
CUE_EXITS = ["ending", "fade_bar", "into_next"]
MUSIC = _obj({
    "suite": {"type": "string", "enum": SUITES},
    "suite_reason": STR,        # 이 영상의 말투·논지와 왜 맞는지 한 줄
    "fit_score": INT,           # 0~10. 7 미만이면 air 만 쓰거나 음악 없이 간다(게이트 D6)
    "describe": STR,            # 주제곡을 묘사하는 영어 한 줄
    "tempo_bpm": INT,           # 원하는 템포. 0 = 박 없음
    "cues": {"type": "array", "items": _obj({
        "id": STR, "start_seg": INT, "end_seg": INT,       # −1 = 영상 맨 앞 / 맨 끝
        "role": {"type": "string", "enum": CUE_ROLES},
        "energy": INT,
        "entry": {"type": "string", "enum": CUE_ENTRIES},
        "exit": {"type": "string", "enum": CUE_EXITS},
        "why_in": STR, "why_out": STR,
    })},
    "silences": {"type": "array", "items": _obj({"start_seg": INT, "end_seg": INT, "why": STR})},
    "hero": {"type": "array", "items": _obj({
        "seg": INT, "kind": {"type": "string", "enum": ["ident", "tonal"]}, "why": STR})},
    "shorts": _obj({"role": {"type": "string", "enum": ["bed", "air", "none"]}, "energy": INT, "note": STR}),
    # 내 음악 폴더의 곡 목록이 주어지면 이 영상에 쓸 곡의 파일 이름(목록에 있는 것만, 맞는 곡이 없으면 "")
    "track": STR,
    "track_reason": STR,
    "notes": STR,
})

# 🔤 자막 디자이너
CAPTIONS = _obj({
    "emphasis": {"type": "array", "items": _obj({
        "seg": INT, "word": STR, "type": {"type": "string", "enum": ["keyword", "term", "number", "contrast"]}})},
    "notes": STR,
})

# ✍️ 카피라이터
COPY = _obj({
    "titles": STR_LIST,
    "description": STR,
    "hashtags": STR_LIST,
    "tags": STR_LIST,
    "thumbnail_texts": STR_LIST,
    "pinned_comment": STR,
})

# 🧐 아트 디렉터 — 렌더된 스틸을 보고 수정 지시
QA = _obj({
    "verdict": {"type": "string", "enum": ["pass", "revise"]},
    "issues": {"type": "array", "items": _obj({
        "target": STR,  # 그래픽 id 또는 "captions" · "sheet"
        "check": STR,      # 루브릭 항목 번호("R3") — art_director.md
        "measured": STR,   # 잰 값("헤드라인 44px / 본문 38px = 1.16")
        "severity": {"type": "string", "enum": ["high", "medium", "low"]},
        "problem": STR,
        "scope": {"type": "string", "enum": ["graphic", "captions", "edit", "audio", "source"]},
        "blocking": BOOL,  # 렌더 전에 반드시 풀어야 하면 true
        # escalate_edit = 그래픽으로 풀 수 없는 편집·컷·음향·원본 문제(docs/upgrade/08 7절 — 게이트 A 를 다시 돌린다)
        "action": {"type": "string", "enum": ["none", "shorten_text", "change_layout", "drop", "revise_scene", "revise_card",
                                              "escalate_edit"]},
        "new_title": STR, "new_body": STR, "new_items": STR_LIST,
        "new_layout": {"type": "string", "enum": ["", *LAYOUTS]},
        "direction": STR,
    })},
    "summary": STR,
})

# 🔎 주제 조사(Claude + 웹 검색·가져오기) — 대본과 주제 설명만 보고 영상 제작 전에(docs/upgrade/14)
SOURCED = {"source_url": STR}
RESEARCH = _obj({
    "topic_summary": STR,                  # 이 주제의 사실 요약(3~6문장)
    "angle": STR,                          # 대본이 세우려는 관점 한 줄
    "entities": {"type": "array", "items": _obj({
        "name_ko": STR, "name_en": STR,
        "kind": {"type": "string", "enum": EV_KINDS},
        "role_in_script": STR,             # 대본에서 이 대상이 하는 일
        "script_quote": STR,               # 처음 나오는 대본 문장의 일부(그대로)
        "summary": STR,                    # 2~3문장(사실)
        "facts": {"type": "array", "items": _obj({"fact": STR, **SOURCED})},
        "years": STR,                      # 생몰·출시·완공 등("1935–", "2007")
        "visual_identity": STR,            # 어떻게 생겼나·무엇으로 알아보나(재현·자료 고르기에 쓴다)
        "commons_files": STR_LIST,         # 직접 확인한 위키미디어 공용 파일 이름('File:' 없이) — 라이선스는 앱이 다시 확인
        "official_url": STR, "wikipedia_url": STR,
    })},
    "concepts": {"type": "array", "items": _obj({
        "term": STR, "term_en": STR, "plain": STR, "canonical_example": STR, "visual_metaphor": STR, **SOURCED})},
    "timeline": {"type": "array", "items": _obj({"year": STR, "event": STR, **SOURCED})},
    "quotes": {"type": "array", "items": _obj({"text": STR, "speaker": STR, "work": STR, "verified": BOOL, **SOURCED})},
    "numbers": {"type": "array", "items": _obj({"value": STR, "meaning": STR, **SOURCED})},
    # 화면으로 다시 그릴 수 있는 것(UI·제품·도식·문서) — 재현에 필요한 사실(치수·색 HEX·배치·글자·순서)
    "recreations": {"type": "array", "items": _obj({"name": STR, "what": STR, "spec": STR, **SOURCED})},
    # 대본 주장 확인(대본은 바꾸지 않는다 — 화자에게 알려 줄 뿐)
    "script_checks": {"type": "array", "items": _obj({
        "sentence": STR, "verdict": {"type": "string", "enum": ["ok", "caution", "wrong", "unverifiable"]},
        "note": STR, **SOURCED})},
    "visual_directions": STR_LIST,         # 이 주제를 보여 주는 방법에 대한 조사자의 제안 3~6개
    "sources": {"type": "array", "items": _obj({"title": STR, "url": STR})},
})

# 🛠 시그니처 장면 빌더 — 트리트먼트의 시그니처 장면 하나를 자유 HTML 카드로(카드 DSL, check.mjs 로 검사)
SETPIECE = _obj({
    "layout": {"type": "string", "enum": ["fullscreen", "split", "overlay"]},
    "style": {"type": "string", "enum": CARD_STYLES},
    "title": STR,
    "html": STR,
    "timeline": STR,              # 직접 쓴 GSAP 타임라인 본문(card_dsl.md 7절) — 시그니처 장면은 거의 늘 쓴다
    "start_word": STR,
    "notes": STR,
})

# 🎨 모션 디자이너(수정 라운드)
MOTION_REVISE = _obj({"spec_json": STR, "changes": STR})
# 🃏 카드 디자이너(수정 라운드) — html 은 고친 카드 조각 전체
CARD_REVISE = _obj({"html": STR, "timeline": STR, "changes": STR})

SHORTS = SHORTS_PLAN

__all__ = ["RESEARCH", "SETPIECE", "TREATMENT", "SFX_KINDS", "PLAN_LAYOUTS", "MUSIC", "EVIDENCE", "EVIDENCE_PICK", "NEEDS", "TREATMENTS", "BRIEF", "EDITOR", "GRADE", "MOMENT_KINDS", "BGM_MOODS", "LOOKS", "MOTION", "STOCK", "STOCK_PICK", "CAPTIONS", "COPY", "QA", "MOTION_REVISE",
           "CARD_REVISE", "CARD_STYLES", "PHOTO_KINDS", "SHORTS", "TEMPLATE_NAMES", "HOOK_TYPES", "INTENTS", "VISUALS"]


# ✂️ 컷 편집 총괄(Opus) — 규칙이 만든 컷 초안(발화 남김/뺌 · 단어 정리)을 대본과 함께 보고 최종 판단. 바꿀 것만 낸다
CUT_REVIEW = _obj({
    "utterances": {"type": "array", "items": _obj({"id": INT, "keep": BOOL, "reason": STR})},
    "removals": {"type": "array", "items": _obj({"id": INT, "keep_removed": BOOL, "reason": STR})},
    "audio_events": {"type": "array", "items": _obj({"id": INT, "cut": BOOL, "reason": STR})},   # 비언어 소리(기침 등)
    # 대본 자체의 문제(전사 흔적): duplicate(of = 같은 앞 문장 번호) · mangled · fragment → 그 문장은 복원하지 않는다
    "script_issues": {"type": "array", "items": _obj({"sentence": INT, "kind": STR, "of": INT, "note": STR})},
    "notes": STR,
})


# 🧐 타임라인 검수(게이트 E) — 정지 화면이 아니라 타임라인을 본다(docs/upgrade/05b_편집_검수_루브릭.md)
RUBRIC = ["follow", "argument", "rhythm", "evidence", "hierarchy", "distinct"]
TL_KINDS = ["duplicate_take", "dead_air", "slide_chain", "hold_broken", "late_step", "no_tails", "no_evidence",
            "wrong_image", "label_leak", "template_repeat", "surface_mix", "flat_hierarchy", "other"]
TL_ACTIONS = ["none", "escalate_edit", "drop", "move", "merge_into_sequence", "extend_hold", "swap_to_image",
              "request_owner"]
TIMELINE_QA = _obj({
    "thesis_read": STR,                                   # 화면 글자만 읽고 쓴 논지 한 문장(소리 끄고 읽기)
    "scores": {"type": "array", "items": _obj({
        "criterion": {"type": "string", "enum": RUBRIC},
        "evidence": STR_LIST,                             # 근거 2~3개("09:00 검은 화면에 '효율' 한 단어 — 2.5초")
        "score": INT,                                     # 0~5
    })},
    "findings": {"type": "array", "items": _obj({
        "start": STR, "end": STR,                         # "mm:ss"
        "kind": {"type": "string", "enum": TL_KINDS},
        "severity": {"type": "string", "enum": ["high", "medium", "low"]},
        "target": STR,
        "action": {"type": "string", "enum": TL_ACTIONS},
        "blocking": BOOL,
        "direction": STR,
    })},
    "summary": STR,
})
