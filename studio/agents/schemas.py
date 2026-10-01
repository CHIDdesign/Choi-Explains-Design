"""스튜디오 에이전트별 구조화 출력 스키마(모든 object 는 additionalProperties=false + 전체 required)."""
from __future__ import annotations

from ..director.catalog import LAYOUTS, TEMPLATE_NAMES
from ..director.schema import BOOL, GRAPHIC, HOOK_TYPES, INT, INT_LIST, NUM, SHORTS_PLAN, STR, STR_LIST, _obj

INTENTS = ["hook", "context", "explain", "example", "name_concept", "story", "data", "compare", "transition",
           "return_to_life", "payoff"]
VISUALS = ["none", "template", "motion", "stock_video", "stock_photo", "photo", "keyword"]
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
        "reason": STR,
    })},
    "cards": {"type": "array", "items": _obj({
        "start_seg": INT, "end_seg": INT, "start_word": STR,
        "layout": {"type": "string", "enum": ["fullscreen", "split", "overlay"]},
        "style": {"type": "string", "enum": CARD_STYLES},
        "title": STR,
        "html": STR,
        "sequence_id": STR,
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
        "target": STR,  # 그래픽 id 또는 "captions"
        "severity": {"type": "string", "enum": ["high", "medium", "low"]},
        "problem": STR,
        "action": {"type": "string", "enum": ["none", "shorten_text", "change_layout", "drop", "revise_scene", "revise_card"]},
        "new_title": STR, "new_body": STR, "new_items": STR_LIST,
        "new_layout": {"type": "string", "enum": ["", *LAYOUTS]},
        "direction": STR,
    })},
    "summary": STR,
})

# 🎨 모션 디자이너(수정 라운드)
MOTION_REVISE = _obj({"spec_json": STR, "changes": STR})
# 🃏 카드 디자이너(수정 라운드) — html 은 고친 카드 조각 전체
CARD_REVISE = _obj({"html": STR, "changes": STR})

SHORTS = SHORTS_PLAN

__all__ = ["BRIEF", "EDITOR", "GRADE", "MOMENT_KINDS", "BGM_MOODS", "LOOKS", "MOTION", "STOCK", "STOCK_PICK", "CAPTIONS", "COPY", "QA", "MOTION_REVISE",
           "CARD_REVISE", "CARD_STYLES", "PHOTO_KINDS", "SHORTS", "TEMPLATE_NAMES", "HOOK_TYPES", "INTENTS", "VISUALS"]


# ✂️ 컷 편집 총괄(Opus) — 규칙이 만든 컷 초안(발화 남김/뺌 · 단어 정리)을 대본과 함께 보고 최종 판단. 바꿀 것만 낸다
CUT_REVIEW = _obj({
    "utterances": {"type": "array", "items": _obj({"id": INT, "keep": BOOL, "reason": STR})},
    "removals": {"type": "array", "items": _obj({"id": INT, "keep_removed": BOOL, "reason": STR})},
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
