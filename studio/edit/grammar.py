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

수치는 prompts/playbook/ 의 리서치(셜록현준·지식 채널·리텐션 편집 가이드)에서 가져와, 교육 영상에 맞게
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
    # 셜록현준 스토리보드 실측: 2~3 앵글을 5~8초마다 교차, 1080p 소스는 100/112/120%, 점프컷마다 12% 이상 차이
    # 2026-09-30 사용자 피드백: "너무 훅훅 튀어 정신없다, 교육 영상이니 젠틀하게" → 프레이밍 차이를 줄이고(112→106%),
    # 5~8초마다 바꾸던 앵글 교차를 없앴다. 프레이밍은 NG 를 잘라낸 큰 점프·챕터·그래픽 복귀에서만 바꾸고
    # (참고 채널 Nick Saraev 롱폼도 고정 카메라·얼굴 줌 0회), 그 사이는 아주 느린 드리프트(가감속).
    # 같은 프레이밍의 점프컷은 0.1초 부드러운 섞기(soft_cut)로 가린다.
    "wide": 1.0,
    "medium": 1.06,             # 두 번째 '카메라'(차이는 작게)
    "medium_x": 0.016,
    "min_shot": 6.0,            # 긴 얼굴 구간을 문장 시작에서 나눌 때 앞뒤로 남길 최소 길이(초)
    # 같은 프레이밍이 이보다 길게 이어지면 문장 시작에서 글라이드로 한 번 바꾼다 — 셜록현준 리서치(20~40초마다 카메라
    # 변화, 얼굴만 25초가 절대 상한)의 가운데 값. 컷이 아니라 1.2초 글라이드(1.00↔1.06)라 젠틀함은 그대로(예전 60초)
    "max_shot": 30.0,
    "big_jump": 1.2,            # 원본에서 이만큼 이상 건너뛴 컷(NG 제거)은 프레이밍 전환으로 가린다
    "push_per_sec": 0.004,      # 느린 드리프트 0.4%/초 — 최대 5%
    "push_max": 0.05,
    "soft_cut": 0.1,            # 같은 프레이밍으로 이어지는 점프컷: 앞 장면 마지막 프레임을 0.1초 동안 섞어 튐을 줄임
    # 종이 스킨의 세 번째 '앵글': 화자를 찢어진 액자에 담아 종이 위에(사용자 레퍼런스 2). 와이드↔미디엄 사이사이,
    # 8초 이상인 샷만, 0.6초에 걸쳐 천천히 들어가고 나온다. classic 스킨은 파이프라인이 framed_every=0 으로 끈다.
    "framed_every": 2,          # 앵글 전환 두 번에 한 번은 액자 샷
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
    "sfx_gain": {"whoosh_fast": -25, "whoosh_soft": -25, "whoosh_deep": -25, "swoosh_short": -26, "pop": -27,
                 "click": -29, "riser": -28, "impact": -24, "sub_drop": -26, "ding": -28, "camera_shutter": -26,
                 "reverse": -26, "typing": -31, "paper": -24, "glitch": -30, "swipe": -26, "bell_soft": -28,
                 "notification": -30},
    "sfx_min_gap": 2.0,         # 효과음 사이 최소 2초
    "sfx_per_min": 4,           # ±30초 창에 최대 4개(평균 분당 2개)
    "list_click_max": 6,
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
    "sfx_for_punch": {3: "impact", 2: "whoosh_fast", 1: "pop"},
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
SFX_FOR_TX = {"whip": "whoosh_soft", "zoom": "whoosh_soft", "blur": "whoosh_soft", "push": "swipe",
              "wipe": "paper", "leak": "reverse", "flash": "whoosh_soft", "dip": ""}
# 그래픽이 나올 때 효과음 — 종류를 다양하게(템플릿 성격에 맞춰)
SFX_FOR_TEMPLATE = {"keyword": "pop", "definition": "typing", "quote": "typing", "photo": "camera_shutter",
                    "broll": "whoosh_soft", "motion": "swipe", "stat": "ding", "compare": "paper", "list": "paper",
                    "process": "paper", "cycle": "swipe", "timeline": "paper", "pyramid": "paper",
                    "concept": "paper", "image_note": "paper", "lower_third": "swoosh_short", "recap": "paper"}
LIST_TEMPLATES = ("list", "process", "cycle", "timeline", "pyramid")

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
    callouts: list[dict] = field(default_factory=list)      # 화자 반대편 키워드 콜아웃(셜록현준식)
    bgm_swells: list[tuple[float, float]] = field(default_factory=list)
    bgm_switch: list[float] = field(default_factory=list)  # 배경음악을 다음 곡으로 바꿀 시각(챕터 카드)
    bgm_dips: list[tuple[float, float]] = field(default_factory=list)  # 음악을 비울 구간(핵심 문장 직전)
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


def _thin_by_gap(events: list[dict], gap: float, key: str = "t") -> list[dict]:
    """우선순위(prio 높을수록 먼저) 순으로 고르되 서로 gap 초 이상 떨어지게."""
    chosen: list[dict] = []
    for e in sorted(events, key=lambda e: (-e.get("prio", 0), e[key])):
        if all(abs(e[key] - c[key]) >= gap for c in chosen):
            chosen.append(e)
    return sorted(chosen, key=lambda e: e[key])


def _cap_per_minute(events: list[dict], per_min: int, key: str = "t") -> list[dict]:
    out: list[dict] = []
    for e in sorted(events, key=lambda e: (-e.get("prio", 0), e[key])):
        window = [c for c in out if abs(c[key] - e[key]) < 30.0]
        if len(window) < per_min:
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
                angle_cuts: Optional[list[float]] = None) -> list[dict]:
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
                   and not _inside(s, covers)]
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
                    punch_spans: Optional[list[tuple[float, float]]] = None, PU: dict = PUNCH) -> EditDecisions:
    """punch_spans: ⚡ 펀치 구간(편집 시각). 그 안에서는 PU 의 값으로 하드 펀치인·단어 슬램·휩·임팩트를 허용한다."""
    ed = EditDecisions(soft_cut=P["soft_cut"])
    spans = [(a, b) for a, b in (punch_spans or []) if b > a]
    covers = _covers(graphics, speech_total)
    chapter_starts = [c["start"] for c in chapters if c["start"] > 0.5]
    ed.camera = camera_plan(timemap, speech_total, chapter_starts=chapter_starts, covers=covers,
                            sentence_starts=sentence_starts, P=P, seed=seed, framed_ranges=framed_ranges,
                            angle_cuts=angle_cuts)

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
        gap = PU["punch_min_gap"] if hot else P["punch_min_gap"]
        if any(abs(m.t - p["t"]) < (gap if p["hot"] == hot else PU["punch_min_gap"]) for p in punches):
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
        gap = PU["impact_min_gap"] if p.get("hot") else P["callout_min_gap"]
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
    # 화자가 화면 가운데에 있으면 콜아웃 동안 카메라를 반대쪽으로 천천히(glide) 옮겨 자리를 만든다(셜록현준식 리프레이밍).
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
            add(a, "riser", 4, "챕터 진입 riser")
        elif tpl == "title":
            add(a + 0.15, "bell_soft", 6, "타이틀 카드")
        elif not near_tx:
            add(a, SFX_FOR_TEMPLATE.get(tpl, "paper"), 2, f"{tpl} 등장")
        if tpl in LIST_TEMPLATES:
            for i, rt in enumerate(list_reveal_times(g)[: P["list_click_max"]]):
                if i:  # 첫 항목은 등장 효과음과 겹치므로 생략
                    add(rt, "click", 1, "목록 항목")
    for p in punches:
        if p.get("hot"):
            add(p["t"], PU["sfx_for_punch"].get(p["intensity"], "pop"), 5, f"펀치 강조({p['kind']})")
        else:
            add(p["t"], "pop" if p["intensity"] >= 2 else "", 4 if p["intensity"] >= 3 else 2, f"강조({p['kind']})")
    for c in ed.callouts:
        if c.pop("pop", False):
            add(c["start"] + 0.08, "pop", 2, "콜아웃")
    # 결론·감정 문장 밑에는 효과음을 깔지 않는다(리서치) — 대신 배경음악을 0.8초 전에 비워 '숨'을 준다
    if endcard and total > speech_total + 0.5:
        add(speech_total + 0.2, "whoosh_soft", 3, "엔드카드")
    # 목록 click 은 간격 규칙에서 제외(항목마다 짧게 나오는 게 자연스럽다).
    # riser 는 소리가 '앞으로' 깔리고 피크가 챕터 진입(와이프 whoosh)과 겹치도록 설계된 짝이라 함께 둔다.
    lead = ("click", "riser")
    clicks = [s for s in sfx if s["category"] in lead]
    rest = [s for s in sfx if s["category"] not in lead]
    hot_sfx = _thin_by_gap([s for s in rest if in_spans(s["t"], spans)], PU["sfx_min_gap"])   # 펀치 구간: 촘촘히
    others = _thin_by_gap([s for s in rest if not in_spans(s["t"], spans)], P["sfx_min_gap"])
    others = _cap_per_minute(others, P["sfx_per_min"])
    ed.sfx = sorted(others + hot_sfx + clicks, key=lambda s: s["t"])

    # ---- 배경음악 부풀리기 --------------------------------------------------
    first_speech = cues[0]["start"] if cues else 0.0
    ed.bgm_swells = [(0.0, max(P["swell_intro"], first_speech))]
    # 가장 큰 순간(강도 3) 0.8초 전에 음악을 비운다 — 영상당 3~6번
    for m in sorted([m for m in moments if m.intensity >= 3], key=lambda m: m.t)[:6]:
        if not ed.bgm_dips or m.t - ed.bgm_dips[-1][1] > 30:
            ed.bgm_dips.append((round(max(0.0, m.t - 0.8), 3), round(m.t + 0.2, 3)))
    ed.bgm_swells += [(max(0.0, c - 0.6), c + 2.4) for c in chapter_starts]
    # 챕터가 바뀌면 곡도 바꾼다(최소 90초 간격 — 짧은 챕터마다 바꾸면 산만하다)
    for c in chapter_starts:
        if c - (ed.bgm_switch[-1] if ed.bgm_switch else 0.0) >= 90.0 and speech_total - c >= 45.0:
            ed.bgm_switch.append(round(c, 3))
    if endcard and total > speech_total:
        ed.bgm_swells.append((speech_total, total))
    face_time = speech_total - sum(b - a for a, b, _ in covers)
    runs = face_only_runs(graphics, ed.callouts, speech_total)
    ed.stats = {"shots": len(ed.camera), "transitions": len(ed.transitions), "punches": len(ed.punches),
                "sfx": len(ed.sfx), "impact_captions": len(ed.impact_cues), "callouts": len(ed.callouts),
                "face_ratio": round(face_time / max(1e-6, speech_total), 3),
                "max_face_run": round(max(runs, default=0.0), 1),
                "face_runs_over_25s": sum(1 for r in runs if r > 25.0),
                "punch_spans": len(spans), "hot_punches": sum(1 for p in punches if p.get("hot"))}
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
        media = g.get("template") in ("photo", "broll")
        cat = "pop" if media else SFX_FOR_TEMPLATE.get(g.get("template", ""), "paper")
        sfx.append({"t": g["start"], "category": cat, "gain_db": P["sfx_gain"].get(cat, -26), "prio": 3,
                    "why": f"{g.get('template', '')} 등장"})
    for p in ed.punches:
        cat = "whoosh_fast" if p["style"] == "cut" else "pop"
        sfx.append({"t": p["t"], "category": cat, "gain_db": P["sfx_gain"][cat] - 2, "prio": 2, "why": "강조"})
    if total > 8:
        sfx.append({"t": max(0.0, total - 1.6), "category": "ding", "gain_db": P["sfx_gain"]["ding"], "prio": 2,
                    "why": "페이오프"})
    ed.sfx = _thin_by_gap(sfx, 5.0)[:6]
    ed.bgm_swells = [(0.0, 0.8)]
    ed.stats = {"shots": len(ed.camera), "transitions": len(ed.transitions), "punches": len(ed.punches),
                "sfx": len(ed.sfx)}
    return ed
