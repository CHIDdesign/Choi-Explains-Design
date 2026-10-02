"""편집 문법 엔진 — AI 가 정한 '무엇을(그래픽·강조 순간)'을, 잘 만든 채널들의 '어떻게(편집 기술)'로 옮긴다.

입력: 편집 타임라인(컷), 시간이 정해진 그래픽, 챕터, AI 가 표시한 강조 순간(moments), 자막 큐.
출력(렌더 props 에 그대로 들어감):
  - camera      : 점프컷 프레이밍 — 와이드 1.00 ↔ 미디엄 1.06 을 NG 를 잘라낸 큰 점프·챕터 시작·전체화면 그래픽
                  복귀에서만 바꾼다(평범한 컷은 그대로 — 참고 채널처럼 얼굴 줌 교차 없음). 샷 안은 느린 드리프트,
                  얼굴만 max_shot 넘게 이어지면 문장 시작에서 글라이드로 한 번 바꾼다. 종이 스킨은 액자 샷(framed)도.
  - soft_cut    : 같은 프레이밍으로 이어지는 점프컷을 0.1초 섞는 소프트 컷(props.mark_soft_cuts)
  - punches     : 강조 순간 글라이드(0.7초에 걸쳐 +4/6/9% 당기고 0.9초에 걸쳐 풀림) — 영상당 최대 8회·40초 간격
  - transitions : 얼굴 ↔ 모션그래픽/B-roll/챕터 카드 사이 부드러운 전환(블러·푸시·와이프·빛샘만) — 밀도 제한
  - sfx         : 전환(whoosh_soft·swipe·paper·reverse), 템플릿별 그래픽 등장음(SFX_FOR_TEMPLATE), 목록 click,
                  챕터 riser, 타이틀 bell_soft, 강조 pop, 엔드카드 whoosh — 작고 부드럽게(impact·sub_drop·glitch 없음)
  - callouts    : 화자 반대편 키워드 콜아웃(가운데 화자는 그동안 천천히 옆으로 옮겨 자리를 만든다)
  - impact_cues : 크게 가운데로 바뀌는 강조 자막 큐 번호
  - bgm_swells  : 배경음악을 올릴 구간(인트로·챕터 카드·엔드카드) · bgm_dips(핵심 문장 직전 비우기) · bgm_switch(곡 교체)

수치는 prompts/playbook/ 의 리서치(레퍼런스 채널·지식 채널·리텐션 편집 가이드)에서 가져와, 교육 영상에 맞게
젠틀하게 낮췄다(2026-09-30 사용자 피드백). PARAMS 한 곳에서 조정한다.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Optional

from ..models import TimeMap

FPS_BASE = 30.0

PARAMS: dict[str, Any] = {
    # 카메라(점프컷 프레이밍)
    # 레퍼런스 채널 스토리보드 실측: 2~3 앵글을 5~8초마다 교차, 1080p 소스는 100/112/120%, 점프컷마다 12% 이상 차이
    # 2026-09-30 사용자 피드백: "너무 훅훅 튀어 정신없다, 교육 영상이니 젠틀하게" → 프레이밍 차이를 줄이고(112→106%),
    # 5~8초마다 바꾸던 앵글 교차를 없앴다. 프레이밍은 NG 를 잘라낸 큰 점프·챕터·그래픽 복귀에서만 바꾸고
    # (참고 채널 Nick Saraev 롱폼도 고정 카메라·얼굴 줌 0회), 그 사이는 아주 느린 드리프트(가감속).
    # 같은 프레이밍의 점프컷은 0.1초 부드러운 섞기(soft_cut)로 가린다.
    "wide": 1.0,
    "medium": 1.06,             # 두 번째 '카메라'(차이는 작게)
    "medium_x": 0.016,
    "min_shot": 6.0,            # 긴 얼굴 구간을 문장 시작에서 나눌 때 앞뒤로 남길 최소 길이(초)
    # 같은 프레이밍이 이보다 길게 이어지면 문장 시작에서 글라이드로 한 번 바꾼다 — 레퍼런스 채널 리서치(20~40초마다 카메라
    # 변화, 얼굴만 25초가 절대 상한)의 가운데 값. 컷이 아니라 1.2초 글라이드(1.00↔1.06)라 젠틀함은 그대로(예전 60초)
    "max_shot": 30.0,
    # 리듬 수준별 강조·콜아웃 최소 간격(편집 감독의 rhythm 이 있는 곳만 — 없으면 punch_min_gap·callout_min_gap 그대로).
    # 고르게 뿌리지 않고 fast 구간에 몰아 쓴다(총량 punch_cap 은 그대로, docs/upgrade/05 4-1·6-3)
    "rhythm_gap": {"slow": 40.0, "steady": 20.0, "fast": 6.0},
    "hold_pad": 1.5,          # 🙂 얼굴 홀드 뒤에 더 비우는 시간(감정이 닿는 데 시간이 걸린다 — docs/upgrade/05 4-3)
    "hold_max": 25.0,         # 홀드 한 곳의 최대 길이(게이트 A7 과 같은 값)
    "big_jump": 1.2,            # 원본에서 이만큼 이상 건너뛴 컷(NG 제거)은 프레이밍 전환으로 가린다
    "push_per_sec": 0.004,      # 느린 드리프트 0.4%/초 — 최대 5%
    "push_max": 0.05,
    "soft_cut": 0.1,            # 같은 프레이밍으로 이어지는 점프컷: 앞 장면 마지막 프레임을 0.1초 동안 섞어 튐을 줄임
    # 종이 스킨의 세 번째 '앵글': 화자를 찢어진 액자에 담아 종이 위에(사용자 레퍼런스 2). 와이드↔미디엄 사이사이,
    # 8초 이상인 샷만, 0.6초에 걸쳐 천천히 들어가고 나온다. classic 스킨은 파이프라인이 framed_every=0 으로 끈다.
    # 액자 샷은 끈다(10/1: 화자 화면 전체에 찢어진 흰 테두리가 생겼다 사라짐 — docs/upgrade/06 F-5). 렌더러 코드는 남겨 둔다
    "framed_every": 0,
    "framed_min": 8.0,
    "framed_glide": 0.6,
    # 강조: 하드컷 펀치인(+15~20%) 대신 0.7초에 걸쳐 천천히 당기는 글라이드(+4~9%), 영상당 8회·40초 간격
    "punch": {1: 0.04, 2: 0.06, 3: 0.09},
    "punch_min_gap": 40.0,
    "punch_max": 4.5,           # 강조 유지 최대(초)
    "punch_cap": 8,
    # 전환 — 프리미엄 채널은 하드컷·펀치컷이 95% 이상. 눈에 띄는 전환은 롱폼 45~90초에 하나, 챕터 경계는 항상.
    "tx_min_gap": 45.0,         # 챕터 외 전환 사이 최소 간격(초) — 부드러운 전환만(블러·푸시·와이프)
    "tx_per_min": 1,            # ±30초 창 안의 최대 전환 수(챕터 포함)
    "tx_frames": {"whip": 8, "zoom": 10, "blur": 12, "push": 12, "flash": 9, "dip": 15, "wipe": 15, "leak": 24},
    # 효과음(피크 -1dBFS 정규화 후 게인, dB). 최종 마스터(-14 LUFS)에서 피크가 대략 게인+1dB:
    # whoosh ≈ -24dBFS · pop ≈ -26 (리서치: whoosh -24 · pop -26 · impact -18, 숏폼은 목소리보다 10~18dB 아래)
    # 교육 영상이라 한 단계 낮고 부드럽게, 종류는 다양하게(종이·스와이프·팝·클릭·타자·작은 종·셔터)
    # 문구 팔레트 v2(docs/upgrade/04c 3절): 소리는 화면의 재질(종이·연필·테이프·도장)을 따른다. 게인은 표의 상대 레벨
    # (목소리 V − 18~26 LU)을 피크 정규화 기준 dB 로 옮긴 출발값 — 자주 나는 소리일수록 작고 짧게
    "sfx_gain": {"paper_slide": -26, "paper_place": -25, "page_turn": -23, "tape": -26, "pencil_stroke": -28,
                 "pencil_tick": -30, "stamp": -23, "print_place": -25, "air_soft": -30, "tonal": -19, "ident": -16,
                 # 🎬 총괄 감독이 고르는 모션 그래픽 효과음(Pixabay·Mixkit 실제 파일) — 목소리 아래 은은하게
                 "whoosh_soft": -25, "swoosh_short": -25, "swipe": -25, "pop": -24, "click": -26, "typing": -27,
                 "camera_shutter": -24, "paper": -23, "ding": -27, "bell_soft": -27, "notification": -25,
                 "whoosh_fast": -24, "whoosh_deep": -24},
    # 자동 모션 효과음(채널 주인 2026-10-02: 장면 전환·모션 등장에 유명한 효과음을 기본으로): 감독 지정보다 낮은 우선순위, 더 촘촘히
    "sfx_min_gap_auto": 1.0,
    "sfx_per_min_auto": 8,
    "sfx_min_gap": 2.0,         # 효과음 사이 최소 2초
    "sfx_per_min": 3,           # 60초 창 어디서도 3개 이하 — 목록 틱까지 모두 센다(게이트 D5)
    "list_click_max": 2,        # 목록 틱은 목록당 최대 2개(상한에 포함)
    "sfx_speech_gap": 0.15,     # 말 시작 0.15초 안에는 놓지 않는다(앞으로 당긴다)
    # 강조 자막·콜아웃
    "impact_min_gap": 22.0,
    # 콜아웃(화자 반대편 키워드)은 강조 글라이드(40초 간격·8회)와 따로 고른다 — 레퍼런스 실측 얼굴+오버레이 화면이
    # 롱폼의 약 21%인데, 글라이드에 묶여 있을 때는 영상당 8개(약 4%)가 상한이었다. 강도 2 이상·콜아웃 문구가 있는 순간
    "callout_min_gap": 20.0,
    "callout_center": 0.14,     # 얼굴이 가운데에서 이 비율 안이면 콜아웃 동안 반대쪽으로 리프레이밍
    "callout_zoom": 1.10,
    "callout_shift": 0.06,      # 화면 폭 비율(확대 여유 안에서만 실제로 움직인다)
    "callout_glide": 0.7,       # 콜아웃 자리 만들기: 컷 대신 0.7초에 걸쳐 천천히 옮기고(돌아올 때 0.9초)
    # 배경음악
    "swell_intro": 1.4,
}

# ⚡ 펀치 구간(✂️ 편집 감독의 energy_spans) 안에서만 쓰는 값 — 크리에이터식 펀치 편집(참고: Claude+HyperFrames 계열 편집
# 데모의 하드 펀치인·단어 슬램·휩·임팩트). 훅·클라이맥스·빠른 열거 같은 특정 부분에만, 전체의 20% 이하. 그 밖은 PARAMS 그대로.
PUNCH: dict[str, Any] = {
    "punch": {1: 0.06, 2: 0.10, 3: 0.14},   # 하드 펀치인(cut) 배율
    "punch_min_gap": 6.0,
    "punch_max": 2.2,                        # 당긴 채 오래 두지 않는다 — 다음 말에서 되돌아옴
    "punch_style": "cut",
    "impact_min_gap": 8.0,                   # 큰 단어 슬램 자막·콜아웃 간격
    "tx_min_gap": 8.0,                       # 휩·푸시 전환 간격
    "tx_kind": "whip",                       # 사진·스톡·키워드가 들어올 때의 전환
    "sfx_min_gap": 1.2,
    "sfx_per_min": 6,
    # 펀치 구간에서도 riser·impact·whoosh 는 없다 — 힘은 도장 한 번과 컷의 리듬에서(04c 6절)
    "sfx_for_punch": {3: "stamp", 2: "paper_slide", 1: "paper_place"},
}


def in_spans(t: float, spans: Optional[list[tuple[float, float]]]) -> bool:
    return bool(spans) and any(a <= t <= b for a, b in spans)


TX_FOR_TEMPLATE = {
    # 얼굴 → 전체화면 그래픽으로 들어갈 때 — 부드러운 것만(휩·플래시·줌 없음)
    "chapter": "wipe",
    "title": "leak",
    "keyword": "blur",
    "definition": "push",
    "quote": "blur",
    "broll": "blur",
    "photo": "blur",
    "motion": "push",
    "stat": "blur",
}
TX_DEFAULT_IN = "push"
# 전환 소리(04c 4절) — 컷·박자가 아니라 화면에서 무언가 넘어갈 때만. 블러·줌·빛샘·플래시는 소리 없음
SFX_FOR_TX = {"whip": "paper_slide", "zoom": "", "blur": "", "push": "paper_slide",
              "wipe": "page_turn", "leak": "", "flash": "", "dip": ""}
# 그래픽이 놓일 때(04c 4절 매핑) — 표에 없는 템플릿은 소리 없음("모르면 종이"를 없앤다)
SFX_FOR_TEMPLATE = {"keyword": "paper_place", "definition": "pencil_stroke", "quote": "", "photo": "print_place",
                    "broll": "", "motion": "paper_slide", "stat": "stamp", "compare": "paper_place",
                    "list": "paper_slide", "process": "paper_slide", "cycle": "paper_slide", "timeline": "pencil_stroke",
                    "pyramid": "paper_place", "concept": "paper_place", "image_note": "tape", "lower_third": "",
                    "recap": "paper_place", "evidence": "print_place", "card": "paper_slide"}
LIST_TEMPLATES = ("list", "process", "cycle", "timeline", "pyramid")
# 자동 모션 효과음(디자인 v4): 그래픽이 들어올 때 — 모션 그래픽에서 흔한 소리(Pixabay·Mixkit 실제 파일)
AUTO_SFX_FOR_TEMPLATE = {"motion": "whoosh_soft", "card": "whoosh_soft", "keyword": "pop", "stat": "ding", "photo": "camera_shutter",
                         "broll": "whoosh_soft", "evidence": "whoosh_soft", "title": "whoosh_deep", "chapter": "whoosh_deep",
                         "list": "swoosh_short", "process": "swoosh_short", "cycle": "swoosh_short", "timeline": "swoosh_short",
                         "compare": "swoosh_short", "definition": "click", "quote": "bell_soft", "recap": "click",
                         "pyramid": "swoosh_short", "matrix": "swoosh_short", "venn": "swoosh_short", "double_diamond": "swoosh_short",
                         "lower_third": ""}
# 장면 전환(components/fx/Transitions.tsx 종류)
AUTO_SFX_FOR_TX = {"whip": "whoosh_fast", "push": "whoosh_soft", "wipe": "swipe", "blur": "whoosh_soft", "leak": "whoosh_soft",
                   "zoom": "whoosh_soft", "flash": "", "dip": ""}
# 모션 장면 안의 부품이 등장할 때
AUTO_SFX_FOR_EL = {"chip": "pop", "bubble": "pop", "panel": "click", "device": "swoosh_short", "counter": "ding", "bar": "swoosh_short"}

MOMENT_KINDS = ("punchline", "reveal", "shift", "conclusion", "question", "number", "joke")


@dataclass
class Moment:
    """AI(✂️ 편집 감독)가 표시한 강조 순간 — 편집 시각으로 변환된 것."""
    t: float
    end: float
    kind: str = "punchline"
    intensity: int = 2
    seg: int = -1
    word: str = ""
    callout: str = ""      # 화자 옆 2줄 콜아웃 문구(AI 가 씀)
    label: str = ""


@dataclass
class EditDecisions:
    camera: list[dict] = field(default_factory=list)
    punches: list[dict] = field(default_factory=list)
    transitions: list[dict] = field(default_factory=list)
    sfx: list[dict] = field(default_factory=list)          # {t, category, gain_db, why}
    impact_cues: list[int] = field(default_factory=list)
    callouts: list[dict] = field(default_factory=list)      # 화자 반대편 키워드 콜아웃(레퍼런스 채널식)
    bgm_swells: list[tuple[float, float]] = field(default_factory=list)
    bgm_switch: list[float] = field(default_factory=list)  # 배경음악을 다음 곡으로 바꿀 시각(챕터 카드)
    bgm_dips: list[tuple[float, float]] = field(default_factory=list)  # 음악을 비울 구간(핵심 문장 직전)
    bgm_anchors: list[float] = field(default_factory=list)  # 곡이 끝났으면 다시 시작할 자리(챕터 카드)
    soft_cut: float = 0.0          # 같은 프레이밍 점프컷을 섞는 시간(초) — props.mark_soft_cuts
    stats: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 공통 도우미
# ---------------------------------------------------------------------------

def _covers(graphics: list[dict], total: float) -> list[tuple[float, float, dict]]:
    """얼굴이 가려지는 구간(전체화면 그래픽·타이틀·챕터 카드)."""
    out = []
    for g in graphics:
        full = g.get("layout") == "fullscreen" or g.get("template") in ("chapter",)
        if full and g["end"] > g["start"]:
            out.append((max(0.0, g["start"]), min(total, g["end"]), g))
    return sorted(out, key=lambda c: c[0])


def _inside(t: float, spans: list[tuple[float, float, Any]], pad: float = 0.0) -> bool:
    return any(a - pad <= t <= b + pad for a, b, *_ in spans)


def auto_motion_sfx(graphics: list[dict], transitions: list[dict] = ()) -> list[dict]:
    """자동 모션 효과음 후보(prio 1): 그래픽 등장(템플릿별) · 모션 장면 안 부품(칩·말풍선·패널·숫자) · 장면 전환."""
    ev: list[dict] = []
    for g in graphics:
        tpl = str(g.get("template", ""))
        cat = AUTO_SFX_FOR_TEMPLATE.get(tpl, "")
        data = g.get("data") or {}
        if str(data.get("sfx") or "") not in ("", "none"):
            continue                                        # 감독이 지정한 그래픽은 감독 소리만
        if cat:
            ev.append({"t": g["start"], "category": cat, "prio": 1, "why": f"{tpl} 등장(자동)"})
        spec = data.get("spec") if tpl == "motion" else None
        for el in (spec or {}).get("elements", []) or []:
            c2 = AUTO_SFX_FOR_EL.get(str(el.get("type", "")), "")
            if c2 and float(el.get("at", 0) or 0) >= 0.4:
                ev.append({"t": g["start"] + float(el.get("at", 0) or 0), "category": c2, "prio": 1,
                           "why": f"{el.get('type')} 등장(자동)"})
            elif el.get("type") == "text" and el.get("reveal") == "chars" and float(el.get("at", 0) or 0) >= 0.4:
                ev.append({"t": g["start"] + float(el.get("at", 0) or 0), "category": "typing", "prio": 1, "why": "타자 글(자동)"})
    for tx in transitions or ():
        cat = AUTO_SFX_FOR_TX.get(str(tx.get("type", "")), "")
        if cat:
            ev.append({"t": float(tx.get("t", 0) or 0), "category": cat, "prio": 1, "why": f"전환 {tx.get('type')}(자동)"})
    return ev


def directed_sfx(graphics: list[dict], segments: list[tuple[float, str]], *, holds: list[tuple[float, float]] = (),
                 speech_starts: list[float] = (), total: float = 0.0, P: dict = PARAMS, auto: bool = False,
                 transitions: list[dict] = ()) -> list[dict]:
    """총괄 감독이 고른 곳에만 효과음(설정 sfx_mode='directed', 기본) — 규칙이 템플릿마다 뿌리지 않는다.
    graphics: 렌더 그래픽(data.sfx 가 있으면 그 그래픽이 들어올 때), segments: [(단락 시작 편집 시각, 효과음)] — 단락
    시작 뒤 1.5초 안에 그래픽이 들어오면 그 순간에 맞춘다. 홀드 안·첫 3초·말 시작 0.15초 안은 피하고(앞으로 당김),
    2초 간격·60초 창 3개(게이트 D5)."""
    starts = sorted(g["start"] for g in graphics)
    ev: list[dict] = []
    for g in graphics:
        cat = str((g.get("data") or {}).get("sfx") or "")
        if cat and cat != "none":
            ev.append({"t": g["start"], "category": cat, "prio": 3, "why": f"{g.get('template', '')} 등장(감독 지정)"})
    for t, cat in segments:
        if not cat or cat == "none":
            continue
        near = next((x for x in starts if t - 0.2 <= x <= t + 1.5), None)
        ev.append({"t": near if near is not None else t, "category": cat, "prio": 2, "why": "단락 시작(감독 지정)"})
    if auto:
        ev += auto_motion_sfx(graphics, transitions)
    out = []
    for e in ev:
        t = e["t"]
        for s0 in speech_starts:
            if 0.0 <= s0 - t < P["sfx_speech_gap"]:
                t = max(0.0, s0 - P["sfx_speech_gap"])
        if t < 3.0 or (total and t > total - 1.0) or any(a <= t < b for a, b in holds):
            continue
        out.append({**e, "t": round(t, 3), "gain_db": P["sfx_gain"].get(e["category"], -25)})
    gap = P["sfx_min_gap_auto"] if auto else P["sfx_min_gap"]
    per_min = P["sfx_per_min_auto"] if auto else P["sfx_per_min"]
    return _cap_per_minute(_thin_by_gap(out, gap), per_min)


def _thin_by_gap(events: list[dict], gap: float, key: str = "t") -> list[dict]:
    """우선순위(prio 높을수록 먼저) 순으로 고르되 서로 gap 초 이상 떨어지게."""
    chosen: list[dict] = []
    for e in sorted(events, key=lambda e: (-e.get("prio", 0), e[key])):
        if all(abs(e[key] - c[key]) >= gap for c in chosen):
            chosen.append(e)
    return sorted(chosen, key=lambda e: e[key])


def _cap_per_minute(events: list[dict], per_min: int, key: str = "t") -> list[dict]:
    """우선순위 높은 것부터, **60초 창 어디서도** per_min 개 이하가 되게 고른다(게이트 D5 — 예전 ±30초 중심 창은
    창을 옮기면 4개가 잡혔다)."""
    out: list[dict] = []
    for e in sorted(events, key=lambda e: (-e.get("prio", 0), e[key])):
        ts = sorted([c[key] for c in out] + [e[key]])
        if all(sum(1 for t in ts if x <= t < x + 60.0) <= per_min for x in ts if e[key] - 60.0 < x <= e[key]):
            out.append(e)
    return sorted(out, key=lambda e: e[key])


def _carve_shot(shots: list[dict], a: float, b: float, new: dict, min_len: float = 1.0,
                glide_back: float = 0.0) -> list[dict]:
    """[a, b] 구간을 new 샷으로 바꾼다. 남는 조각이 min_len 보다 짧으면 이웃에 붙인다.
    glide_back > 0 이면 b 뒤 조각은 그 시간 동안 원래 프레이밍으로 천천히 돌아온다."""
    out: list[dict] = []
    for sh in shots:
        if sh["end"] <= a or sh["start"] >= b:
            out.append(dict(sh))
            continue
        if sh["start"] < a:
            out.append({**sh, "end": round(a, 3), "zoomEnd": sh["zoom"]})
        if sh["end"] > b:
            back = {**sh, "start": round(b, 3), "zoom": sh["zoomEnd"]}
            if glide_back > 0:
                back["glide"] = glide_back
            out.append(back)
    out.append(dict(new))
    out.sort(key=lambda s: s["start"])
    merged: list[dict] = []
    for sh in out:
        short = sh["end"] - sh["start"] < min_len and sh is not out[-1] and sh.get("x") != new.get("x")
        if merged and short and sh["start"] >= b - 1e-6:
            prev = merged[-1]
            merged[-1] = {**prev, "end": sh["end"]}
            continue
        if merged and short and sh["end"] <= a + 1e-6 and len(merged) >= 1:
            merged[-1] = {**merged[-1], "end": sh["end"]}
            continue
        merged.append(sh)
    return merged


def _merge_shots_near(shots: list[dict], times: list[float], win: float) -> list[dict]:
    """times 앞뒤 win 초 안에서 시작하는 샷은 앞 샷에 합친다(강조 글라이드와 프레이밍 전환이 연달아 겹치지 않게)."""
    out: list[dict] = []
    for sh in shots:
        if out and any(abs(sh["start"] - t) < win for t in times):
            out[-1] = {**out[-1], "end": sh["end"]}
            continue
        out.append(dict(sh))
    return out


def _face_x(face: list[dict], t: float) -> float:
    if not face:
        return 0.5
    near = min(face, key=lambda f: abs(f.get("t", 0) - t))
    return float(near.get("x", 0.5))


def face_only_runs(graphics: list[dict], callouts: list[dict], total: float) -> list[float]:
    """화면에 얼굴만 있는(그래픽·콜아웃이 하나도 없는) 구간 길이들 — 레퍼런스 실측: 보통 10초 이하, 25초가 절대 상한."""
    spans = sorted((max(0.0, x["start"]), min(total, x["end"])) for x in list(graphics) + list(callouts)
                   if x["end"] > x["start"])
    runs, t = [], 0.0
    for a, b in spans:
        if a > t:
            runs.append(a - t)
        t = max(t, b)
    if total > t:
        runs.append(total - t)
    return runs


def list_reveal_times(g: dict, fps: float = FPS_BASE) -> list[float]:
    """renderer/src/lib/anim.ts revealAt 과 같은 계산 — 목록 항목이 드러나는 시각(편집 초)."""
    items = (g.get("data") or {}).get("items") or []
    n = len(items)
    if not n:
        return []
    total_frames = (g["end"] - g["start"]) * fps
    lead = 10
    usable = max(1.0, total_frames * 0.72 - lead)
    return [g["start"] + (lead + usable / n * i) / fps for i in range(n)]


# ---------------------------------------------------------------------------
# 카메라
# ---------------------------------------------------------------------------

def camera_plan(timemap: TimeMap, total: float, *, chapter_starts: list[float], covers: list[tuple],
                sentence_starts: list[float], P: dict = PARAMS, seed: int = 1,
                framed_ranges: Optional[list[tuple[float, float]]] = None,
                angle_cuts: Optional[list[float]] = None,
                holds: Optional[list[tuple[float, float]]] = None) -> list[dict]:
    """점프컷 프레이밍(교육 영상용 젠틀 편집). 컷 지점에서만 와이드(1.00)/미디엄(1.06)을 번갈아 바꾼다 —
    챕터 시작·전체화면 그래픽 복귀·NG 를 잘라낸 큰 점프(≥big_jump)에서만(평범한 컷은 그대로).
    그 사이 같은 프레이밍의 점프컷은 소프트 컷(props.mark_soft_cuts)이 가린다. 얼굴만 max_shot 넘게 이어지면
    문장 시작에서 한 번 더 — 컷이 아니면 glide 로 천천히. framed_every > 0(종이 스킨)이면 전환 몇 번에 한 번은 액자 샷.
    angle_cuts(다시점 앵글이 바뀌는 편집 시각)는 새 샷 — 앵글 자체가 컷을 가리므로 그 샷은 와이드(1.00)에서 시작하고,
    앵글이 바뀌는 곳 가까이(2초)에서는 줌 프레이밍을 따로 바꾸지 않는다(앵글 교차와 줌 교차가 겹치면 어지럽다)."""
    rnd = random.Random(seed)
    cuts = timemap.cut_points()
    big: set[float] = set()
    for i in range(1, len(timemap.keeps)):
        if timemap.keeps[i].start - timemap.keeps[i - 1].end >= P["big_jump"]:
            big.add(round(timemap.edit_span_of(i).start, 3))
    chapter_set = {round(c, 3) for c in chapter_starts}
    cover_ends = [round(b, 3) for _, b, _ in covers]
    angle_set = {round(c, 3) for c in angle_cuts or []}
    cands = sorted({round(c, 3) for c in cuts} | chapter_set | set(cover_ends) | angle_set)
    bounds = [0.0]
    for c in cands:
        if c <= 0.05 or c >= total - 0.3:
            continue
        since = c - bounds[-1]
        near_angle = any(abs(c - x) < 2.0 for x in angle_set) and c not in angle_set
        must = c in chapter_set or c in cover_ends or c in angle_set or (c in big and since >= 1.2 and not near_angle)
        if must:                                    # 평범한 컷에서는 프레이밍을 바꾸지 않는다(교육 영상 — 얼굴 줌 교차 없음)
            bounds.append(c)
    # 얼굴만 너무 오래 이어지면 문장 경계에서 한 번 더 — 컷이 아닌 곳이면 컷 대신 천천히 옮겨 간다(glide)
    filled = [bounds[0]]
    cut_set = {round(c, 3) for c in cuts}
    fillers: set[float] = set()
    extra = sorted(s for s in sentence_starts if 0.5 < s < total - 1.0)
    for b in bounds[1:] + [total]:
        while b - filled[-1] > P["max_shot"]:
            mid = [s for s in extra if filled[-1] + P["min_shot"] <= s <= b - P["min_shot"]
                   and not _inside(s, covers) and not any(a0 <= s <= b0 for a0, b0 in holds or [])]
            if not mid:
                break
            target = filled[-1] + P["max_shot"] * 0.6
            pick = min(mid, key=lambda s: abs(s - target))
            filled.append(pick)
            fillers.add(round(pick, 3))
        if b < total:
            filled.append(b)
    # 너무 가까운 경계(1초 미만)는 하나로 — 0.1초짜리 샷은 튀어 보인다(앞 경계를 남김, 챕터 경계 우선)
    merged: list[float] = []
    for b in sorted(set(round(b, 3) for b in filled)):
        if merged and b - merged[-1] < 1.0:
            if b in chapter_set or b in angle_set:
                merged[-1] = b
            continue
        merged.append(b)
    bounds = merged + [total]
    shots: list[dict] = []
    level = "wide"
    side = 1 if rnd.random() > 0.5 else -1
    switches = 0
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        if b - a < 0.05:
            continue
        if i == 0 or round(a, 3) in chapter_set or round(a, 3) in angle_set:
            level = "wide"
        elif level != "wide":
            level = "wide"
        else:
            switches += 1
            every = int(P.get("framed_every", 0) or 0)
            framed_ok = framed_ranges is None or any(x <= a < y for x, y in framed_ranges)   # 하이브리드: 종이 챕터만
            level = "framed" if every and framed_ok and switches % every == 0 and b - a >= P.get("framed_min", 8.0) \
                else "medium"
        zoom = P["wide"] if level == "framed" else P[level]
        x = 0.0
        if level == "medium":
            side = -side
            x = side * P["medium_x"]
        push = min(P["push_max"], P["push_per_sec"] * (b - a)) if b - a > 5.0 else 0.0
        shot = {"start": round(a, 3), "end": round(b, 3), "zoom": round(zoom, 4),
                "zoomEnd": round(zoom * (1 + push), 4), "x": round(x, 4)}
        if round(a, 3) in fillers and not any(abs(a - c) < 0.05 for c in cut_set):
            shot["glide"] = 1.2
        if level == "framed":
            shot["framed"] = True
            shot["glide"] = P["framed_glide"]
        elif shots and shots[-1].get("framed"):
            shot["glide"] = P["framed_glide"]          # 액자에서 나올 때도 천천히
        shots.append(shot)
    return shots


# ---------------------------------------------------------------------------
# 롱폼
# ---------------------------------------------------------------------------

def build_long_edit(*, timemap: TimeMap, total: float, speech_total: float, graphics: list[dict],
                    chapters: list[dict], moments: list[Moment], cues: list[dict], sentence_starts: list[float],
                    text_graphic_spans: Optional[list[tuple[float, float]]] = None, endcard: bool = True,
                    face: Optional[list[dict]] = None, P: dict = PARAMS, seed: int = 1,
                    framed_ranges: Optional[list[tuple[float, float]]] = None,
                    angle_cuts: Optional[list[float]] = None,
                    punch_spans: Optional[list[tuple[float, float]]] = None, PU: dict = PUNCH,
                    holds: Optional[list[tuple[float, float]]] = None,
                    rhythm: Optional[list[tuple[float, float, str]]] = None) -> EditDecisions:
    """punch_spans: ⚡ 펀치 구간(편집 시각). 그 안에서는 PU 의 값으로 하드 펀치인·단어 슬램·휩·임팩트를 허용한다.
    holds: 🙂 얼굴 홀드(편집 시각, 뒤 여유 포함) — 그 안에는 강조·콜아웃·전환·효과음이 없고 프레이밍도 움직이지 않는다
    (편집 감독이 '얼굴로' 지킨 고백·결론 — 10/1: 정리 보드가 S158–S160 을 덮었다). 홀드 앞에서 음악을 비운다."""
    ed = EditDecisions(soft_cut=P["soft_cut"])
    holds = [(a, b) for a, b in (holds or []) if b > a]
    levels = [(a, b, lv) for a, b, lv in (rhythm or []) if b > a and lv in P["rhythm_gap"]]

    def gap_at(t: float, default: float) -> float:
        """그 시각의 리듬 수준이 정한 최소 간격(선언이 없으면 기존 값)."""
        lv = next((x for a, b, x in levels if a <= t < b), None)
        return P["rhythm_gap"][lv] if lv else default

    def in_hold(t: float, end: Optional[float] = None) -> bool:
        e = t if end is None else end
        return any(t < b and e >= a for a, b in holds)
    if holds:
        moments = [m for m in moments if not in_hold(m.t, m.end)]
    spans = [(a, b) for a, b in (punch_spans or []) if b > a]
    covers = _covers(graphics, speech_total)
    chapter_starts = [c["start"] for c in chapters if c["start"] > 0.5]
    ed.camera = camera_plan(timemap, speech_total, chapter_starts=chapter_starts, covers=covers,
                            sentence_starts=sentence_starts, P=P, seed=seed, framed_ranges=framed_ranges,
                            angle_cuts=angle_cuts, holds=holds)

    # ---- 전환 -------------------------------------------------------------
    tx: list[dict] = []
    fps = FPS_BASE
    whip_dir = ["left", "right"]
    for k, (a, b, g) in enumerate(covers):
        tpl = g.get("template", "")
        kind = TX_FOR_TEMPLATE.get(tpl, TX_DEFAULT_IN)
        if in_spans(a, spans) and tpl in ("photo", "broll", "keyword", "stat", "card"):
            kind = PU["tx_kind"]
        if kind == "whip":
            kind_dir = whip_dir[k % 2]
        elif kind == "push":
            kind_dir = "up"
        else:
            kind_dir = None
        prio = 3 if tpl in ("chapter", "title") else 2
        if a > 0.3:
            tx.append({"t": a, "type": kind, "dir": kind_dir, "prio": prio, "why": f"→ {tpl}"})
        # 그래픽 → 얼굴 복귀: 다음 커버가 바로 붙어 있으면 그 전환이 대신한다
        nxt = covers[k + 1][0] if k + 1 < len(covers) else None
        if b < speech_total - 0.5 and (nxt is None or nxt - b > 0.6):
            back = "blur" if tpl in ("chapter", "title", "quote", "photo", "broll") else "push"
            tx.append({"t": b, "type": back, "dir": "down" if back == "push" else None, "prio": 1,
                       "why": f"{tpl} → 얼굴"})
    major = _thin_by_gap([e for e in tx if e["prio"] >= 3], 8.0)          # 챕터·타이틀: 항상
    minor = [e for e in tx if e["prio"] < 3 and all(abs(e["t"] - m["t"]) >= 20.0 for m in major)]
    hot = [e for e in minor if in_spans(e["t"], spans)]                    # 펀치 구간: 간격만 짧게, 분당 상한 없음
    calm = _thin_by_gap([e for e in minor if not in_spans(e["t"], spans)], P["tx_min_gap"])
    tx = sorted(major + _cap_per_minute(calm, P["tx_per_min"]) + _thin_by_gap(hot, PU["tx_min_gap"]), key=lambda e: e["t"])
    for e in tx:
        e["dur"] = round(P["tx_frames"].get(e["type"], 14) / fps, 3)
    ed.transitions = [{k: v for k, v in e.items() if k in ("t", "type", "dur", "dir") and v is not None} for e in tx]

    # ---- 강조 글라이드 + 강조 자막 ------------------------------------------
    punches: list[dict] = []
    # 화자가 옆 패널에 밀려 있는 분할 구간에도 강조 줌은 두지 않는다(전체화면 그래픽과 같은 취급)
    side = [(g["start"], g["end"], None) for g in graphics if g.get("layout") == "split" and g["end"] > g["start"]]
    for m in sorted(moments, key=lambda m: (-m.intensity, m.t)):
        hot = in_spans(m.t, spans)
        if m.intensity < 2 and m.kind not in ("joke",) and not hot:
            continue
        if _inside(m.t, covers, pad=0.4) or _inside(m.t, side, pad=0.4) \
                or _inside(m.t, [(e["t"] - 0.5, e["t"] + 0.5) for e in tx]):
            continue
        # 간격: 같은 온도끼리는 각자의 규칙(젠틀 40초 · 펀치 6초), 펀치 구간과 젠틀 구간 사이는 6초만 띄우면 된다
        gap = PU["punch_min_gap"] if hot else gap_at(m.t, P["punch_min_gap"])

        def need(p: dict) -> float:
            if p["hot"] != hot:
                return PU["punch_min_gap"]
            return gap if hot else min(gap, gap_at(p["t"], P["punch_min_gap"]))
        if any(abs(m.t - p["t"]) < need(p) for p in punches):
            continue
        end = min(max(m.end + 0.15, m.t + 1.0), m.t + (PU["punch_max"] if hot else P["punch_max"]))
        nxt_cover = min([a for a, _, _ in covers if a > m.t] + [speech_total])
        end = min(end, nxt_cover - 0.05)
        if end - m.t < 0.6:
            continue
        # ⚡ 펀치 구간: 하드 펀치인(한 프레임에 당김) — 그 밖은 교육 영상용 글라이드
        style = PU["punch_style"] if hot else "glide"
        amt = (PU if hot else P)["punch"].get(max(1, min(3, m.intensity)), 0.16)
        punches.append({"t": round(m.t, 3), "end": round(end, 3), "amount": amt, "style": style,
                        "kind": m.kind, "intensity": m.intensity, "hot": hot})
    calm_p = sorted([p for p in punches if not p["hot"]], key=lambda p: (-p["intensity"], p["t"]))[: P["punch_cap"]]
    punches = sorted(calm_p + [p for p in punches if p["hot"]], key=lambda p: p["t"])
    ed.camera = _merge_shots_near(ed.camera, [p["t"] for p in punches], 1.0)
    ed.punches = [{k: p[k] for k in ("t", "end", "amount", "style")} for p in punches]

    text_spans = [(a, b, None) for a, b in (text_graphic_spans or [])]
    # 화면 한쪽을 그래픽이 차지하는(패널·얼굴 옆 사진 액자·오버레이) 구간에는 콜아웃을 두지 않는다
    busy = text_spans + [(g["start"], g["end"], None) for g in graphics
                         if g.get("layout") in ("split", "pip", "overlay") or g.get("template") == "lower_third"]
    by_t = {round(m.t, 3): m for m in moments}
    # 콜아웃 후보: 강조 글라이드가 된 순간 + 글라이드 간격(40초)·상한(8회)에 밀렸지만 콜아웃 문구가 있는 강도 2 이상 순간
    cands = [dict(p, punch=True) for p in punches]
    taken = {p["t"] for p in punches}
    for m in moments:
        t = round(m.t, 3)
        hot = in_spans(m.t, spans)
        if t in taken or not m.callout.strip() or (m.intensity < 2 and not hot):
            continue
        if _inside(m.t, covers, pad=0.4) or _inside(m.t, side, pad=0.4) \
                or _inside(m.t, [(e["t"] - 0.5, e["t"] + 0.5) for e in tx]):
            continue
        cands.append({"t": t, "end": round(max(m.end + 0.15, m.t + 1.0), 3), "intensity": m.intensity, "hot": hot,
                      "kind": m.kind, "punch": False})
        taken.add(t)
    cands.sort(key=lambda c: c["t"])
    last_callout = -1e9
    called: set[float] = set()
    for p in cands:
        m = by_t.get(p["t"])
        text = (m.callout if m else "").strip()
        gap = PU["impact_min_gap"] if p.get("hot") else gap_at(p["t"], P["callout_min_gap"])
        if not text or p["t"] - last_callout < gap or _inside(p["t"], busy, pad=0.3):
            continue
        nxt = min([a for a, _, _ in covers if a > p["t"]] + [a for a, _, _ in busy if a > p["t"]] + [speech_total])
        end = min(p["t"] + 4.2, max(p["end"] + 0.8, p["t"] + 2.8), nxt - 0.15)
        if end - p["t"] < 1.8:
            continue
        fx = _face_x(face or [], p["t"])
        lines = [x.strip() for x in text.replace("\\n", "\n").split("\n") if x.strip()][:2]
        hl = (m.word or "").strip() if m else ""
        ed.callouts.append({"start": round(max(0.0, p["t"] - 0.08), 3), "end": round(end, 3), "text": "\n".join(lines),
                            "highlight": hl if hl and hl in "".join(lines) else "", "label": (m.label if m else ""),
                            "side": "right" if fx < 0.5 else "left"})
        last_callout = p["t"]
        called.add(p["t"])
        if not p["punch"]:
            ed.callouts[-1]["pop"] = True    # 글라이드 없는 콜아웃: 등장에 작은 pop(효과음 간격 규칙은 그대로)
    # 화자가 화면 가운데에 있으면 콜아웃 동안 카메라를 반대쪽으로 천천히(glide) 옮겨 자리를 만든다(레퍼런스 채널식 리프레이밍).
    # 이때는 리프레이밍 자체가 강조 역할을 하므로 같은 순간의 강조 글라이드는 뺀다(효과음은 유지).
    reframed: set[float] = set()
    for c in ed.callouts:
        fx = _face_x(face or [], c["start"])
        if abs(fx - 0.5) > P["callout_center"]:
            continue
        x = -P["callout_shift"] if c["side"] == "right" else P["callout_shift"]
        ed.camera = _carve_shot(ed.camera, c["start"], c["end"], {
            "start": c["start"], "end": c["end"], "zoom": P["callout_zoom"], "zoomEnd": P["callout_zoom"], "x": x,
            "glide": P["callout_glide"]}, glide_back=P["callout_glide"] + 0.2)
        reframed.add(round(c["start"] + 0.08, 3))
        c["pop"] = True        # 리프레이밍이 강조를 대신하니 콜아웃이 놓일 때의 종이 소리는 남긴다
    if reframed:
        # ⚡ 펀치 구간의 하드 펀치인(cut)은 리프레이밍과 겹쳐도 남긴다(펀치 편집의 핵심). 젠틀 글라이드만 리프레이밍이 대신한다
        ed.punches = [p for p in ed.punches if round(p["t"], 3) not in reframed or p["style"] == "cut"]
    last_impact = -1e9
    for p in punches:
        if p["t"] in called:
            continue
        if (p["intensity"] < 2 and not p.get("hot")) or p["t"] - last_impact < (PU if p.get("hot") else P)["impact_min_gap"] \
                or _inside(p["t"], text_spans):
            continue
        for i, c in enumerate(cues):
            if c["start"] - 0.05 <= p["t"] < c["end"]:
                n_chars = sum(len(w["text"]) for line in c["lines"] for w in line)
                if n_chars <= 22:  # 두 줄 이내 짧은 문장만 크게
                    ed.impact_cues.append(i)
                    last_impact = p["t"]
                break

    # ---- 효과음 -------------------------------------------------------------
    sfx: list[dict] = []

    def add(t: float, cat: str, prio: int, why: str) -> None:
        if cat and 0 <= t <= total:
            sfx.append({"t": round(t, 3), "category": cat, "gain_db": P["sfx_gain"].get(cat, -18), "prio": prio,
                        "why": why})

    for e in tx:
        add(e["t"], SFX_FOR_TX.get(e["type"], ""), 5 if e["prio"] >= 2 else 3, f"전환 {e['type']}")
    tx_times = [e["t"] for e in tx]
    for g in graphics:
        tpl, a = g.get("template", ""), g["start"]
        near_tx = any(abs(a - t) < 0.4 for t in tx_times)
        if tpl == "chapter":
            if not near_tx:              # 와이프 전환의 page_turn 과 하나로(챕터 진입 소리는 한 번)
                add(a, "page_turn", 6, "챕터 진입")
        elif tpl == "title":
            add(a + 0.15, "ident", 6, "타이틀 카드")      # 채널 인장(없으면 무음 — tonal 은 스코어가 맡는다)
        elif not near_tx:
            add(a, SFX_FOR_TEMPLATE.get(tpl, ""), 2, f"{tpl} 등장")
        if tpl in LIST_TEMPLATES:
            for i, rt in enumerate(list_reveal_times(g)[1: 1 + P["list_click_max"]]):
                add(rt, "pencil_tick", 1, "목록 항목")       # 첫 항목은 등장 소리와 겹치므로 생략
    for p in punches:
        if p.get("hot"):
            add(p["t"], PU["sfx_for_punch"].get(p["intensity"], ""), 5, f"펀치 강조({p['kind']})")
        # 펀치 밖 강조 글라이드는 소리 없음 — 화면에 놓이는 것이 없다
    for c in ed.callouts:
        if c.pop("pop", False):
            add(c["start"] + 0.08, "paper_place", 2, "콜아웃")
    # 결론·감정 문장 밑에는 효과음을 깔지 않는다. 엔드카드는 스코어의 reprise 가 맡는다(효과음 없음)
    # 말 시작 0.15초 안에는 놓지 않는다 — 앞으로 당긴다(자음 대역을 비운다, 04c 2절 5번)
    onsets = [c["start"] for c in cues]
    for x in sfx:
        near = next((o for o in onsets if -P["sfx_speech_gap"] < x["t"] - o < P["sfx_speech_gap"]), None)
        if near is not None:
            x["t"] = round(max(0.0, near - P["sfx_speech_gap"]), 3)
    # 목록 틱·챕터도 간격·분당 상한에 모두 센다(예전엔 click·riser 가 상한 밖이라 '틱틱' 튀었다 — 게이트 D5)
    hot_sfx = _thin_by_gap([s for s in sfx if in_spans(s["t"], spans)], PU["sfx_min_gap"])   # 펀치 구간: 촘촘히
    hot_sfx = _cap_per_minute(hot_sfx, PU["sfx_per_min"])
    others = _thin_by_gap([s for s in sfx if not in_spans(s["t"], spans)], P["sfx_min_gap"])
    others = _cap_per_minute(others, P["sfx_per_min"])
    ed.sfx = sorted(others + hot_sfx, key=lambda s: s["t"])

    # ---- 배경음악 부풀리기 --------------------------------------------------
    first_speech = cues[0]["start"] if cues else 0.0
    ed.bgm_swells = [(0.0, max(P["swell_intro"], first_speech))]
    # 가장 큰 순간(강도 3) 0.8초 전에 음악을 비운다 — 영상당 3~6번
    for m in sorted([m for m in moments if m.intensity >= 3], key=lambda m: m.t)[:6]:
        if not ed.bgm_dips or m.t - ed.bgm_dips[-1][1] > 30:
            ed.bgm_dips.append((round(max(0.0, m.t - 0.8), 3), round(m.t + 0.2, 3)))
    ed.bgm_swells += [(max(0.0, c - 0.6), c + 2.4) for c in chapter_starts]
    # 한 영상 한 곡 — 챕터마다 곡을 바꾸지 않는다(10/1: 조성·템포가 다른 세 곡을 이었다, docs/upgrade/04 11절 2번).
    # 챕터 시작은 곡이 다 끝났을 때 다시 시작할 구조 앵커로만 쓴다(mix.BgmPlan.restart_at)
    ed.bgm_anchors = [round(c, 3) for c in chapter_starts]
    if endcard and total > speech_total:
        ed.bgm_swells.append((speech_total, total))
    if holds:
        ed.transitions = [x for x in ed.transitions if not in_hold(x["t"])]
        ed.sfx = [x for x in ed.sfx if not in_hold(x["t"])]
        ed.callouts = [x for x in ed.callouts if not in_hold(x["start"], x["end"])]
        ed.punches = [x for x in ed.punches if not in_hold(x["t"])]
        # 홀드 앞 숨: 음악을 0.8초 전부터 비운다(시작 0.2초 뒤까지)
        ed.bgm_dips = sorted(ed.bgm_dips + [(round(max(0.0, a - 0.8), 3), round(a + 0.2, 3)) for a, _ in holds])
    face_time = speech_total - sum(b - a for a, b, _ in covers)
    runs = face_only_runs(graphics, ed.callouts, speech_total)
    ed.stats = {"shots": len(ed.camera), "transitions": len(ed.transitions), "punches": len(ed.punches),
                "sfx": len(ed.sfx), "impact_captions": len(ed.impact_cues), "callouts": len(ed.callouts),
                "face_ratio": round(face_time / max(1e-6, speech_total), 3),
                "max_face_run": round(max(runs, default=0.0), 1),
                "face_runs_over_25s": sum(1 for r in runs if r > 25.0),
                "punch_spans": len(spans), "hot_punches": sum(1 for p in punches if p.get("hot")),
                "holds": len(holds), "hold_sec": round(sum(b - a for a, b in holds), 1)}
    return ed


# ---------------------------------------------------------------------------
# 숏폼
# ---------------------------------------------------------------------------

def build_short_edit(*, timemap: TimeMap, total: float, graphics: list[dict], cues: list[dict],
                     moments: list[Moment], P: dict = PARAMS, seed: int = 2,
                     angle_cuts: Optional[list[float]] = None,
                     punch_spans: Optional[list[tuple[float, float]]] = None, hook: float = 3.0,
                     PU: dict = PUNCH) -> EditDecisions:
    """숏폼: 롱폼보다 빠른 호흡이지만 교육 채널답게 부드럽게 — 프레이밍은 컷 지점에서만 작게(1.00↔1.06) 바꾸고,
    같은 프레이밍 점프컷은 소프트 컷, 강조는 글라이드. 다시점 앵글이 바뀌는 곳은 새 샷(1.00부터)."""
    ed = EditDecisions(soft_cut=P["soft_cut"])
    rnd = random.Random(seed)
    # ⚡ 숏폼의 훅(첫 hook 초)과 편집 감독의 펀치 구간에서는 하드 펀치인 허용
    spans = [(0.0, hook)] + [(a, b) for a, b in (punch_spans or []) if b > a] if hook > 0 else list(punch_spans or [])
    # 1) 카메라: 컷 지점에서만 1.00 ↔ 1.06 교차(샷 최소 3.5초). 샷 안에서는 느린 드리프트(최대 4%).
    angle_set = {round(c, 3) for c in angle_cuts or []}
    marks = sorted({round(c, 3) for c in timemap.cut_points()} | angle_set)
    bounds = [0.0]
    for m in marks:
        if m >= total - 1.0:
            continue
        if m in angle_set:
            if m - bounds[-1] < 1.0 and len(bounds) > 1:
                bounds[-1] = m
            elif m - bounds[-1] >= 0.05:
                bounds.append(m)
        elif m - bounds[-1] >= 3.5 and not any(abs(m - x) < 2.0 for x in angle_set):
            bounds.append(m)
    bounds.append(total)
    level = rnd.choice([0, 1])
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        if round(a, 3) in angle_set:
            level = 0
        z = 1.06 if level else 1.0
        level ^= 1
        push = min(0.04, 0.008 * (b - a)) if b - a > 3.5 else 0.0
        ed.camera.append({"start": round(a, 3), "end": round(b, 3), "zoom": z, "zoomEnd": round(z * (1 + push), 4)})
    # 2) 전환: 콜드 오픈 → 본론으로 되감는 이음새 하나만(블러 디졸브 9프레임 = '되감기' 신호). 나머지는 컷
    #    (프레이밍이 그대로 이어지는 컷은 소프트 컷).
    keeps = timemap.keeps
    for i in range(1, len(keeps)):
        if keeps[i].start < keeps[i - 1].start:
            t = timemap.edit_span_of(i).start
            ed.transitions.append({"t": round(t, 3), "type": "blur", "dur": 0.3})
            break
    # 3) 강조 글라이드: 강조 순간(최대 3개, 5초 간격)
    for m in sorted(moments, key=lambda m: -m.intensity):
        if len(ed.punches) >= 3:
            break
        hot = in_spans(m.t, spans)
        if any(abs(m.t - p["t"]) < (3 if hot else 5) for p in ed.punches) or m.t < (0.4 if hot else 1.0) or m.t > total - 1.0:
            continue
        if hot:
            ed.punches.append({"t": round(m.t, 3), "end": round(min(max(m.end + 0.2, m.t + 1.2), m.t + PU["punch_max"], total), 3),
                               "amount": PU["punch"][3 if m.intensity >= 3 else 2], "style": PU["punch_style"]})
        else:
            ed.punches.append({"t": round(m.t, 3), "end": round(min(max(m.end + 0.3, m.t + 1.8), m.t + 3.0, total), 3),
                               "amount": 0.07 if m.intensity >= 3 else 0.05, "style": "glide"})
    ed.punches.sort(key=lambda p: p["t"])
    # 4) 효과음 — 참고 채널(Nick Saraev 숏폼) 실측: 컷에는 whoosh 가 없고(컷 지점 고음 에너지가 평소와 같음),
    #    카드·아이콘이 떨어질 때 작은 pop, 그 밖은 잔잔한 음악만. 그래픽 성격에 맞춰 종류는 다양하게, 5초에 하나 이하.
    sfx: list[dict] = []
    for g in graphics:
        media = g.get("template") in ("photo", "broll", "evidence")
        cat = "print_place" if media else SFX_FOR_TEMPLATE.get(g.get("template", ""), "")
        if cat and g["start"] >= 3.0:          # 훅(첫 3초) 위에는 얹지 않는다(04c 6절)
            sfx.append({"t": g["start"], "category": cat, "gain_db": P["sfx_gain"].get(cat, -26), "prio": 3,
                        "why": f"{g.get('template', '')} 등장"})
    for p in ed.punches:
        if p["style"] == "cut" and p["t"] >= 3.0:
            sfx.append({"t": p["t"], "category": "paper_slide", "gain_db": P["sfx_gain"]["paper_slide"] - 2, "prio": 2,
                        "why": "강조"})
    # 마지막은 스코어의 tag 가 맡는다 — 효과음 없음
    ed.sfx = _thin_by_gap(sfx, 5.0)[:6]
    ed.bgm_swells = [(0.0, 0.8)]
    ed.stats = {"shots": len(ed.camera), "transitions": len(ed.transitions), "punches": len(ed.punches),
                "sfx": len(ed.sfx)}
    return ed
