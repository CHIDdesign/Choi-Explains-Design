"""Claude 구조화 출력(JSON Schema). 구조화 출력 제약에 맞춰 단순한 타입만 사용한다
(모든 객체 additionalProperties=false, 숫자 범위 제약 없음 — 범위 검증은 plan.py 에서)."""
from __future__ import annotations

from .catalog import LAYOUTS, TEMPLATE_NAMES

HOOK_TYPES = (
    # docs/research/숏폼_후킹_리서치.md 7-2 의 우선순위 순서
    "everyday_why",        # 일상 사물의 '왜' (셜록현준형)
    "reframe_definition",  # 재정의·레이블링
    "payoff_first",        # 결과 먼저(콜드 오픈)
    "hidden_mechanism",    # 숨은 원리
    "compare_contrast",    # 비교·대조
    "contrarian",          # 통념 반박
    "story_in_medias_res", # 이야기 한가운데서 시작
    "visual_demo",         # 시각 시연
    "number_list",         # 숫자·리스트
    "pain_point",          # 공감·문제 제기
    "open_loop",           # 호기심 갭
    "authority_insider",   # 권위·경험·내부자
    "bold_prediction",     # 예측·선언
    "warning",             # 경고·손실 회피
)


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props.keys()),
            "additionalProperties": False}


STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}
NUM = {"type": "number"}
STR_LIST = {"type": "array", "items": STR}
INT_LIST = {"type": "array", "items": INT}

GRAPHIC = _obj({
    "template": {"type": "string", "enum": list(TEMPLATE_NAMES)},
    "layout": {"type": "string", "enum": list(LAYOUTS)},
    "start_seg": INT,
    "end_seg": INT,
    "start_word": STR,
    "title": STR,
    "subtitle": STR,
    "body": STR,
    "items": STR_LIST,
    "title_b": STR,
    "items_b": STR_LIST,
    "highlight": INT,
    # 단계 그래픽: 같은 도식을 단계마다 새로 띄우지 말고 하나에 — 그 낱말을 말할 때 강조가 그 단계로([] = 없음)
    "steps": {"type": "array", "items": _obj({"word": STR, "highlight": INT})},
    "author": STR,
    "source": STR,
    "image": STR,
    "reason": STR,
})

EMPHASIS = _obj({
    "seg": INT,
    "word": STR,
    "kind": {"type": "string", "enum": ["punch", "highlight"]},
})

LONG_PLAN = _obj({
    "summary": STR,
    "hook_segs": INT_LIST,
    "title_card_seg": INT,
    "chapters": {"type": "array", "items": _obj({"seg": INT, "title": STR})},
    "graphics": {"type": "array", "items": GRAPHIC},
    "emphasis": {"type": "array", "items": EMPHASIS},
    "drop": {"type": "array", "items": _obj({"seg": INT, "reason": STR})},
    # 🎬 오프닝 하이라이트: 본편 앞에 붙일 임팩트 있는 문장 2~4개(각 7초 이내, 합쳐 20초 이내) — 그 뒤 처음부터 시작
    "highlights": {"type": "array", "items": _obj({"seg": INT, "reason": STR})},
    "youtube": _obj({
        "titles": STR_LIST,
        "description": STR,
        "hashtags": STR_LIST,
        "tags": STR_LIST,
        "thumbnail_texts": STR_LIST,
        "pinned_comment": STR,
    }),
    "music": _obj({"mood": STR, "notes": STR}),
})

SHORT = _obj({
    "title": STR,
    "hook_type": {"type": "string", "enum": list(HOOK_TYPES)},
    "hook_title": STR,
    "hook_highlight": STR,
    "cold_open_seg": INT,
    "segments": INT_LIST,
    "graphics": {"type": "array", "items": GRAPHIC},
    "emphasis": {"type": "array", "items": _obj({"seg": INT, "word": STR})},
    # 개념 텍스트(3~5초마다 바뀜): 그 발화가 나올 때 릴스식은 위 카드(흰 개념 카드 + 형광펜), 종이 스킨 숏폼은
    # 화면 아래 '검정 라벨 + 큰 글씨'로. 모자라면 props.short_beats 가 강조 순간·강조어 자막으로 채운다
    "beats": {"type": "array", "items": _obj({"seg": INT, "label": STR, "text": STR, "accent": STR})},
    "cta": STR,
    "loop_line": STR,
    "caption": STR,
    "hashtags": STR_LIST,
    "viewer_takeaway": STR,   # 롱폼을 안 본 시청자가 이 한 편에서 얻는 한 문장(이해 가능성 자기 점검)
    "why": STR,
    "score": INT,
})

SHORTS_PLAN = _obj({"shorts": {"type": "array", "items": SHORT}})
