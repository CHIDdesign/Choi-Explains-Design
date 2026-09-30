"""스튜디오 에이전트별 구조화 출력 스키마(모든 object 는 additionalProperties=false + 전체 required)."""
from __future__ import annotations

from ..director.catalog import LAYOUTS, TEMPLATE_NAMES
from ..director.schema import GRAPHIC, HOOK_TYPES, INT, INT_LIST, NUM, SHORTS_PLAN, STR, STR_LIST, _obj

INTENTS = ["hook", "context", "explain", "example", "name_concept", "story", "data", "compare", "transition",
           "return_to_life", "payoff"]
VISUALS = ["none", "template", "motion", "stock_video", "stock_photo", "photo", "keyword"]
# ✂️ 편집 감독이 표시하는 '강조 순간' — 편집 문법 엔진(studio/edit/grammar.py)이 강조 글라이드·콜아웃·강조 자막·효과음으로 옮긴다
MOMENT_KINDS = ["punchline", "reveal", "shift", "conclusion", "question", "number", "joke"]
BGM_MOODS = ["minimal", "calm", "ambient", "lofi", "piano", "inspiring", "upbeat"]
LOOKS = ["warm_rich", "natural", "warm_film", "clean_bright", "cinematic"]

# 🎬 총괄 감독 — 크리에이티브 브리프
BRIEF = _obj({
    "title": STR,          # 화면 타이틀 카드·파일 이름에 쓰는 영상 제목(18자 이내)
    "logline": STR,
    "audience": STR,
    "tone": STR,
    "structure": {"type": "array", "items": _obj({"title": STR, "start_seg": INT, "end_seg": INT, "purpose": STR})},
    "beats": {"type": "array", "items": _obj({
        "start_seg": INT, "end_seg": INT,
        "intent": {"type": "string", "enum": INTENTS},
        "visual": {"type": "string", "enum": VISUALS},
        "idea": STR,
        "priority": INT,
    })},
    "hook_segs": INT_LIST,
    "title_card_seg": INT,
    "shorts_ideas": {"type": "array", "items": _obj({"segments": INT_LIST, "angle": STR})},
    "caption_direction": STR,
    "music": _obj({"mood": STR, "notes": STR}),
    "bgm_mood": {"type": "string", "enum": BGM_MOODS},
    "shorts_bgm_mood": {"type": "string", "enum": BGM_MOODS},
    "notes_for_team": STR,
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

# 🎨 모션 디자이너 — 템플릿 그래픽 + 직접 설계한 모션 장면(spec_json 은 MotionSpec JSON 문자열)
MOTION = _obj({
    "graphics": {"type": "array", "items": GRAPHIC},
    "scenes": {"type": "array", "items": _obj({
        "start_seg": INT, "end_seg": INT, "start_word": STR,
        "layout": {"type": "string", "enum": ["fullscreen", "split"]},
        "title": STR,
        "spec_json": STR,
        "reason": STR,
    })},
})

# 🎞 자료 리서처 — 무료 스톡 요청(Pixabay·Unsplash·Coverr·Pexels)
STOCK = _obj({
    "requests": {"type": "array", "items": _obj({
        "start_seg": INT, "end_seg": INT, "start_word": STR,
        "kind": {"type": "string", "enum": ["video", "photo"]},
        "query_en": STR, "query_ko": STR,
        "layout": {"type": "string", "enum": list(LAYOUTS)},
        "purpose": STR,
        "must_show": STR,
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
    "preset_long": {"type": "string", "enum": ["editorial", "documentary", "glass", "boxed"]},
    "preset_short": {"type": "string", "enum": ["kinetic", "clean", "boxed"]},
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
        "action": {"type": "string", "enum": ["none", "shorten_text", "change_layout", "drop", "revise_scene"]},
        "new_title": STR, "new_body": STR, "new_items": STR_LIST,
        "new_layout": {"type": "string", "enum": ["", *LAYOUTS]},
        "direction": STR,
    })},
    "summary": STR,
})

# 🎨 모션 디자이너(수정 라운드)
MOTION_REVISE = _obj({"spec_json": STR, "changes": STR})

SHORTS = SHORTS_PLAN

__all__ = ["BRIEF", "EDITOR", "GRADE", "MOMENT_KINDS", "BGM_MOODS", "LOOKS", "MOTION", "STOCK", "STOCK_PICK", "CAPTIONS", "COPY", "QA", "MOTION_REVISE", "SHORTS",
           "TEMPLATE_NAMES", "HOOK_TYPES", "INTENTS", "VISUALS"]
