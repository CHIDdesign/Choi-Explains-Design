"""편집 문법 엔진 — AI 가 정한 '무엇을(그래픽·강조 순간)'을, 잘 만든 채널들의 '어떻게(편집 기술)'로 옮긴다.

입력: 편집 타임라인(컷), 시간이 정해진 그래픽, 챕터, AI 가 표시한 강조 순간(moments), 자막 큐.
출력(렌더 props 에 그대로 들어감):
  - camera      : 점프컷 프레이밍 — 와이드 1.00 ↔ 미디엄 1.12 를 NG 를 잘라낸 큰 점프·챕터 시작·전체화면 그래픽 복귀에서
                  바꾸는 하드 크롭 컷(디자인 v5). 샷 안에서 카메라는 움직이지 않는다. 종이 스킨은 액자 샷(framed)도.
  - callouts    : 핵심어 콜아웃(편집 감독이 문구를 쓴 강도 2 이상 순간)
  - sfx         : 그래픽이 말에 닿는 순간의 효과음
  - bgm_swells  : 배경음악을 올릴 구간 · bgm_dips(정점·챕터 끝 비우기) · bgm_anchors(곡이 끝났을 때 다시 시작할 자리)

수치는 PARAMS 한 곳에서 조정한다(근거는 docs/디자인_v5_토크쇼.md · docs/research/레퍼런스_영상_분석.md).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Optional

from ..director.plan import ENTER_EXIT, word_edit_time
from ..models import TimeMap
from ..util import text_hash

FPS_BASE = 30.0

PARAMS: dict[str, Any] = {
    # 카메라(점프컷 프레이밍): 크롭을 12% 바꾼 하드 컷으로 점프를 가린다. 슬로우 줌·글라이드 없음(디자인 v5)
    "wide": 1.0,
    "medium": 1.12,
    "medium_x": 0.03,
    "min_shot": 6.0,            # 긴 얼굴 구간을 문장 시작에서 나눌 때 앞뒤로 남길 최소 길이(초)
    # 같은 프레이밍이 이보다 길게 이어지면 문장 시작에서 크롭을 한 번 바꾼다
    "max_shot": 20.0,
    # 리듬 수준별 콜아웃 최소 간격(편집 감독의 rhythm 이 있는 곳만 — 없으면 callout_min_gap)
    "rhythm_gap": {"slow": 40.0, "steady": 20.0, "fast": 15.0},
    "hold_pad": 1.5,          # 🙂 얼굴 홀드 뒤에 더 비우는 시간(감정이 닿는 데 시간이 걸린다 — docs/upgrade/05 4-3)
    "hold_max": 25.0,         # 홀드 한 곳의 최대 길이(게이트 A7 과 같은 값)
    "hold_gap": 20.0,         # 홀드 사이 최소 간격 — 앞 홀드 끝에서 이 안에 시작하는 홀드는 뺀다(2026-10-03: 홀드 셋이 9~12초
                              # 간격으로 이어져 얼굴만 71초 → A7 block, 보충 카드는 홀드를 피하므로 메울 수 없었다)
    "big_jump": 1.2,            # 원본에서 이만큼 이상 건너뛴 컷(NG 제거)은 프레이밍 전환으로 가린다
    # 종이 스킨의 세 번째 '앵글': 화자를 찢어진 액자에 담아 종이 위에(사용자 레퍼런스 2). 와이드↔미디엄 사이사이,
    # 8초 이상인 샷만, 0.6초에 걸쳐 천천히 들어가고 나온다. classic 스킨은 파이프라인이 framed_every=0 으로 끈다.
    # 액자 샷은 끈다(10/1: 화자 화면 전체에 찢어진 흰 테두리가 생겼다 사라짐 — docs/upgrade/06 F-5). 렌더러 코드는 남겨 둔다
    "framed_every": 0,
    "framed_min": 8.0,
    "framed_glide": 0.6,
    # 전환 — 프리미엄 채널은 하드컷·펀치컷이 95% 이상. 눈에 띄는 전환은 롱폼 45~90초에 하나, 챕터 경계는 항상.
    "tx_min_gap": 45.0,         # 챕터 외 전환 사이 최소 간격(초) — 부드러운 전환만(블러·푸시·와이프)
    "tx_per_min": 1,            # ±30초 창 안의 최대 전환 수(챕터 포함)
    "tx_frames": {"whip": 8, "zoom": 10, "blur": 12, "push": 12, "flash": 9, "dip": 15, "wipe": 15, "leak": 24},
    # 효과음(피크 -1dBFS 정규화 뒤 게인, dB). 귀로 조정할 곳은 여기 한 곳이다 — 측정값은 어림이고 아무도 믹스를 듣지 않았다.
    # 피크로 맞추면 짧고 뾰족한 소리일수록 에너지가 작아 종이·클릭이 팝·휙(목소리 대비 최대 100ms −15 dB)보다 6~9 dB 더 묻혔다
    # (docs/research/효과음 출처와 감각적 사용법.md: 종이 −21.3 → +6, 클릭 −23.9 → +9)
    "sfx_gain": {"paper_slide": -13, "paper_place": -12, "page_turn": -11, "tape": -13, "pencil_stroke": -14, "paper_tear": -16,
                 "pencil_tick": -11, "stamp": -16, "print_place": -12, "air_soft": -20, "tonal": -19, "ident": -16,
                 "whoosh_soft": -18, "swoosh_short": -18, "swipe": -18, "pop": -17, "click": -10, "typing": -20,
                 "camera_shutter": -18, "paper": -11, "ding": -19, "bell_soft": -19, "notification": -18,
                 "whoosh_fast": -17, "whoosh_deep": -17, "gag": -12},
    "sfx_min_gap": 4.0,
    "sfx_per_min": 4,           # 60초 창 어디서도 4개 이하(게이트 D5)
    "sfx_speech_gap": 0.15,     # 말 시작 0.15초 안에는 놓지 않는다(앞으로 당긴다)
    # 콜아웃: 강도 2 이상·콜아웃 문구가 있는 순간
    "callout_min_gap": 20.0,
    "callout_sec": 3.0,
    # 배경음악
    "swell_intro": 1.4,
}

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
# 그래픽이 놓일 때(04c 4절 매핑) — 표에 없는 템플릿은 소리 없음("모르면 종이"를 없앤다)
SFX_FOR_TEMPLATE = {"keyword": "paper_place", "definition": "pencil_stroke", "quote": "", "photo": "",
                    "broll": "", "motion": "paper_slide", "stat": "stamp", "compare": "paper_place",
                    "list": "paper_slide", "process": "paper_slide", "cycle": "paper_slide", "timeline": "pencil_stroke",
                    "pyramid": "paper_place", "concept": "paper_place", "image_note": "tape", "lower_third": "",
                    "evidence": "", "card": "paper_slide"}
# 자동 효과음: 템플릿이 들어올 때만(사진·문서는 무음, 요소·전환은 소리 없음 — 디자인 v5)
AUTO_SFX_FOR_TEMPLATE = {"collage": "paper_place", "motion": "paper_slide", "card": "paper_slide", "keyword": "pop", "stat": "paper_place", "title": "paper_tear",
                         "chapter": "page_turn", "stamp": "stamp", "lower_third": "paper_place",
                         "list": "paper_slide", "process": "paper_slide", "cycle": "paper_slide", "timeline": "paper_slide",
                         "compare": "paper_slide", "definition": "paper_place", "quote": "bell_soft",
                         "pyramid": "paper_slide", "matrix": "paper_slide", "venn": "paper_slide", "double_diamond": "paper_slide"}
TEAR_AT = 0.2     # 타이틀 PaperRip(첫 12프레임)의 찢어지는 한가운데 — landing() 은 이미 끝난 뒤다
CUT_LAND = 0.25   # 오림이 내려앉는 데 걸리는 시간(렌더러 paperSettle 11프레임)
THUD_GAP = 0.25   # 오림 착지끼리의 최소 간격
HIGH_PITCH = ("ding", "bell_soft", "notification")   # 음 높은 소리는 영상당 2개까지(플레이북 07_sound) — 분당 상한만으로는 8번 울린다
HIGH_PITCH_MAX = 2
GAG_MAX, GAG_GAP = 4, 60.0    # 위트 소리는 영상당 4개, 60초에 1개
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
    callouts: list[dict] = field(default_factory=list)      # 화자 반대편 키워드 콜아웃(레퍼런스 채널식)
    bgm_swells: list[tuple[float, float]] = field(default_factory=list)
    bgm_switch: list[float] = field(default_factory=list)  # 배경음악을 다음 곡으로 바꿀 시각(챕터 카드)
    bgm_dips: list[tuple[float, float]] = field(default_factory=list)  # 음악을 비울 구간(핵심 문장 직전)
    bgm_anchors: list[float] = field(default_factory=list)  # 곡이 끝났으면 다시 시작할 자리(챕터 카드)
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


def landing(g: dict) -> float:
    """그래픽이 말에 닿는 시각 — start 는 말보다 앞당긴 첫 프레임이라 아직 보이는 것이 없다."""
    return g["start"] + ENTER_EXIT.get(g.get("layout", ""), (0.4, 0.8))[0]


def graphic_landings(graphics: list[dict]) -> list[float]:
    """효과음이 맞출 수 있는 착지(게이트 D11) — 도장은 소리를 고른 뒤 호스트 자료의 표시로 옮겨 가므로 그 at 으로."""
    stamps = [landing({"start": g["start"] + float(o.get("at", 0)), "layout": "fullscreen"})
              for g in graphics for o in (g.get("data") or {}).get("overlays") or [] if o.get("kind") == "stamp"]
    return [landing(g) for g in graphics] + stamps


def cutout_landings(g: dict) -> list[float]:
    """오림 그림이 내려앉는 시각들 — 오림 스택(at 이 없으면 렌더러처럼 고르게)과 사진 위 오림 오버레이.
    콜라주·타이틀·챕터의 조각은 8fps 로 한꺼번에 놓이는 한 덩어리, 몽타주는 하드 컷이라 등장음 하나로 끝난다."""
    d = g.get("data") or {}
    cuts = (d.get("cutouts") or []) if g.get("template") == "cutout_stack" else []
    span = max(14 / FPS_BASE, (g["end"] - g["start"]) * 0.72)
    ats = [float(c["at"]) if c.get("at") is not None else i * span / len(cuts) for i, c in enumerate(cuts)]
    ats += [float(o["at"]) for o in d.get("overlays") or [] if o.get("kind") == "cutout" and o.get("at") is not None]
    return [g["start"] + a + CUT_LAND for a in ats]


def auto_motion_sfx(graphics: list[dict]) -> list[dict]:
    """자동 효과음 후보(prio 1): 템플릿 등장만 + 타이틀 찢기 + 오림 스택의 한 장마다 종이 한 번(thud — 간격·분당 상한의 예외).
    감독이 지정한 그래픽은 감독 소리만."""
    ev: list[dict] = []
    for g in graphics:
        tpl = str(g.get("template", ""))
        cat = AUTO_SFX_FOR_TEMPLATE.get(tpl, "")
        if str((g.get("data") or {}).get("sfx") or "") not in ("", "none"):
            continue
        if tpl == "title":
            ev.append({"t": g["start"] + TEAR_AT, "category": cat, "prio": 1, "why": "타이틀 찢기(자동)"})
        elif cat:
            ev.append({"t": landing(g), "category": cat, "prio": 1, "why": f"{tpl} 등장(자동)"})
        ev += [{"t": t, "category": "paper_place", "prio": 1, "thud": True, "why": "오림 착지(자동)"} for t in cutout_landings(g)]
    return ev


def gag_category(idea: str) -> str:
    """위트 소리 하나의 효과음 카테고리 — 같은 문장(콜백)은 같은 카테고리·같은 파일."""
    return "gag_" + text_hash(idea.strip().lower())[:10]


def gag_events(gags: list[dict], seg_t: dict[int, tuple[float, float]], graphics: list[dict], utts: list, timemap: TimeMap,
               have: set[str]) -> list[dict]:
    """🎬 감독의 위트 소리 → 편집 시각 이벤트. 영상당 GAG_MAX 개·GAG_GAP 초 간격, 파일을 못 구한 것은 뺀다.
    silence_beat 는 category 가 빈 이벤트(pre 만큼 음악을 비우는 침묵만)."""
    by_id = {u.id: u for u in utts}
    landings = sorted(graphic_landings(graphics))
    out: list[dict] = []
    for g in gags:
        span = seg_t.get(g.get("seg"))
        idea = str(g.get("sound_idea") or "")
        cat = gag_category(idea) if idea else ""
        if not span or (cat and cat not in have):
            continue
        anchor = g.get("anchor")
        if anchor == "graphic_landing":
            t = next((x for x in landings if span[0] - 0.3 <= x <= span[1]), None)
            if t is None:               # 화면 사건이 없으면 그 소리는 뜻이 없다
                continue
        elif anchor == "word" and g.get("seg") in by_id:
            t = word_edit_time(by_id[g["seg"]], str(g.get("anchor_word") or ""), timemap)
            t = span[0] if t is None else t
        else:
            t = span[1] if anchor == "after_seg" else span[0]
        out.append({"t": t, "category": cat, "prio": 4, "pre": float(g.get("pre_silence_s") or 0.0), "gain_db": PARAMS["sfx_gain"]["gag"],
                    "why": f"위트 소리({g.get('type', '')})"})
    return _thin_by_gap(out, GAG_GAP)[:GAG_MAX]


def gag_dips(sfx: list[dict], gags: list[dict]) -> list[tuple[float, float]]:
    """위트 소리 앞 음악 비우기(pre_silence_s): directed_sfx 가 실제로 남긴 소리와 소리 없는 silence_beat 만 — 홀드·첫 3초에서
    빠진 소리의 자리에 음악 구멍만 남지 않게."""
    return [(e["t"] - e["pre"], e["t"]) for e in [*sfx, *(g for g in gags if not g["category"])] if e.get("pre", 0) > 0]


def directed_sfx(graphics: list[dict], segments: list[tuple[float, str]], *, holds: list[tuple[float, float]] = (),
                 speech_starts: list[float] = (), total: float = 0.0, P: dict = PARAMS, auto: bool = False,
                 gags: list[dict] = ()) -> list[dict]:
    """총괄 감독이 고른 곳에만 효과음(설정 sfx_mode='directed', 기본) — 규칙이 템플릿마다 뿌리지 않는다.
    graphics: 렌더 그래픽(data.sfx 가 있으면 그 그래픽이 들어올 때), segments: [(단락 시작 편집 시각, 효과음)] — 단락
    시작 뒤 1.5초 안에 그래픽이 들어오면 그 순간에 맞춘다. 홀드 안·첫 3초·말 시작 0.15초 안은 피하고(앞으로 당김),
    sfx_min_gap 간격·60초 창 sfx_per_min 개(게이트 D5). gags: gag_events 의 위트 소리 — 우선순위가 가장 높아 앞뒤 소리를 밀어낸다."""
    starts = sorted(landing(g) for g in graphics)
    ev: list[dict] = list(gags)
    for g in graphics:
        cat = str((g.get("data") or {}).get("sfx") or "")
        if cat and cat != "none":
            ev.append({"t": landing(g), "category": cat, "prio": 3, "why": f"{g.get('template', '')} 등장(감독 지정)"})
    for t, cat in segments:
        if not cat or cat == "none":
            continue
        near = next((x for x in starts if t - 0.2 <= x <= t + 1.5), None)
        ev.append({"t": near if near is not None else t, "category": cat, "prio": 2, "why": "단락 시작(감독 지정)"})
    if auto:
        ev += auto_motion_sfx(graphics)
    out = []
    for e in ev:
        t = e["t"]
        for s0 in speech_starts:
            if 0.0 <= s0 - t < P["sfx_speech_gap"]:
                t = max(0.0, s0 - P["sfx_speech_gap"])
        if t < 3.0 or (total and t > total - 1.0) or any(a <= t < b for a, b in holds):
            continue
        out.append({**e, "t": round(t, 3), "gain_db": e.get("gain_db", P["sfx_gain"].get(e["category"], -25))})
    picked = _cap_per_minute(_thin_by_gap([e for e in out if not e.get("thud")], P["sfx_min_gap"]), P["sfx_per_min"])
    picked = sorted(picked + _thin_by_gap([e for e in out if e.get("thud")], THUD_GAP), key=lambda e: e["t"])
    high = {id(e) for e in sorted((e for e in picked if e["category"] in HIGH_PITCH), key=lambda e: (-e["prio"], e["t"]))[HIGH_PITCH_MAX:]}
    return [e for e in picked if id(e) not in high]


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


# ---------------------------------------------------------------------------
# 카메라
# ---------------------------------------------------------------------------

def camera_plan(timemap: TimeMap, total: float, *, chapter_starts: list[float], covers: list[tuple],
                sentence_starts: list[float], P: dict = PARAMS, seed: int = 1,
                framed_ranges: Optional[list[tuple[float, float]]] = None,
                angle_cuts: Optional[list[float]] = None,
                holds: Optional[list[tuple[float, float]]] = None) -> list[dict]:
    """점프컷 프레이밍. 컷 지점에서만 와이드(1.00)/미디엄(1.12)을 번갈아 바꾼다 — 챕터 시작·전체화면 그래픽 복귀·NG 를 잘라낸
    큰 점프(≥big_jump). 얼굴만 max_shot 넘게 이어지면 문장 시작에서 한 번 더. 샷 안에서는 움직이지 않는다.
    framed_every > 0(종이 스킨)이면 전환 몇 번에 한 번은 액자 샷. angle_cuts(다시점 앵글이 바뀌는 편집 시각)는 새 샷 — 앵글
    자체가 컷을 가리므로 그 샷은 와이드에서 시작하고, 그 가까이(2초)에서는 프레이밍을 따로 바꾸지 않는다."""
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
        if must:
            bounds.append(c)
    # 얼굴만 너무 오래 이어지면 문장 경계에서 한 번 더
    filled = [bounds[0]]
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
        shot = {"start": round(a, 3), "end": round(b, 3), "zoom": round(zoom, 4), "zoomEnd": round(zoom, 4), "x": round(x, 4)}
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
                    holds: Optional[list[tuple[float, float]]] = None,
                    rhythm: Optional[list[tuple[float, float, str]]] = None, peak: Optional[float] = None) -> EditDecisions:
    """holds: 🙂 얼굴 홀드(편집 시각, 뒤 여유 포함) — 그 안에는 콜아웃·효과음이 없고 프레이밍도 움직이지 않는다.
    peak: 편집 감독의 정점 발화 시각 — 음악은 여기와 챕터 끝에서만 비운다."""
    ed = EditDecisions()
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
    covers = _covers(graphics, speech_total)
    chapter_starts = [c["start"] for c in chapters if c["start"] > 0.5]
    ed.camera = camera_plan(timemap, speech_total, chapter_starts=chapter_starts, covers=covers,
                            sentence_starts=sentence_starts, P=P, seed=seed, framed_ranges=framed_ranges,
                            angle_cuts=angle_cuts, holds=holds)

    # ---- 전환 -------------------------------------------------------------
    tx: list[dict] = []
    fps = FPS_BASE
    for k, (a, b, g) in enumerate(covers):
        tpl = g.get("template", "")
        kind = TX_FOR_TEMPLATE.get(tpl, TX_DEFAULT_IN)
        kind_dir = "up" if kind == "push" else None
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
    tx = sorted(major + _cap_per_minute(_thin_by_gap(minor, P["tx_min_gap"]), P["tx_per_min"]), key=lambda e: e["t"])
    for e in tx:
        e["dur"] = round(P["tx_frames"].get(e["type"], 14) / fps, 3)
    # 전면 그래픽의 들고 남은 렌더러의 하드 컷이다 — tx 는 콜아웃이 그 자리를 피하는 데만 쓴다(stage_tx=True 면 예전처럼 보낸다)
    ed.transitions = [{k: v for k, v in e.items() if k in ("t", "type", "dur", "dir") and v is not None}
                      for e in tx] if P.get("stage_tx", False) else []

    # 화자가 옆 패널에 밀려 있는 분할 구간에는 콜아웃을 두지 않는다(전체화면 그래픽과 같은 취급)
    side = [(g["start"], g["end"], None) for g in graphics if g.get("layout") == "split" and g["end"] > g["start"]]
    text_spans = [(a, b, None) for a, b in (text_graphic_spans or [])]
    # 화면 한쪽을 그래픽이 차지하는(패널·얼굴 옆 사진 액자·오버레이) 구간에는 콜아웃을 두지 않는다
    busy = text_spans + [(g["start"], g["end"], None) for g in graphics
                         if g.get("layout") in ("split", "pip", "overlay") or g.get("template") == "lower_third"]
    last_callout = -1e9
    for m in sorted(moments, key=lambda m: m.t):
        text = m.callout.strip()
        if not text or m.intensity < 2 or m.t - last_callout < gap_at(m.t, P["callout_min_gap"]) or _inside(m.t, busy, pad=0.3) \
                or _inside(m.t, covers, pad=0.4) or _inside(m.t, side, pad=0.4) \
                or _inside(m.t, [(e["t"] - 0.5, e["t"] + 0.5) for e in tx]):
            continue
        nxt = min([a for a, _, _ in covers if a > m.t] + [a for a, _, _ in busy if a > m.t] + [speech_total])
        end = min(m.t + P["callout_sec"], nxt - 0.15)
        if end - m.t < 1.8:
            continue
        fx = _face_x(face or [], m.t)
        lines = [x.strip() for x in text.replace("\\n", "\n").split("\n") if x.strip()][:2]
        hl = (m.word or "").strip()
        ed.callouts.append({"start": round(max(0.0, m.t - 0.08), 3), "end": round(end, 3), "text": "\n".join(lines),
                            "highlight": hl if hl and hl in "".join(lines) else "", "label": m.label,
                            "side": "right" if fx < 0.5 else "left"})
        last_callout = m.t

    # ---- 효과음 -------------------------------------------------------------
    sfx: list[dict] = []

    def add(t: float, cat: str, prio: int, why: str) -> None:
        if cat and 0 <= t <= total:
            sfx.append({"t": round(t, 3), "category": cat, "gain_db": P["sfx_gain"].get(cat, -18), "prio": prio,
                        "why": why})

    for g in graphics:
        tpl, a = g.get("template", ""), landing(g)
        if tpl == "chapter":
            add(a, "page_turn", 6, "챕터 진입")
        elif tpl == "title":
            add(g["start"] + TEAR_AT, "paper_tear", 6, "타이틀 찢기")
        else:
            add(a, SFX_FOR_TEMPLATE.get(tpl, ""), 2, f"{tpl} 등장")
    # 결론·감정 문장 밑에는 효과음을 깔지 않는다. 엔드카드는 스코어의 reprise 가 맡는다(효과음 없음)
    # 말 시작 0.15초 안에는 놓지 않는다 — 앞으로 당긴다(자음 대역을 비운다, 04c 2절 5번)
    onsets = [c["start"] for c in cues]
    for x in sfx:
        near = next((o for o in onsets if -P["sfx_speech_gap"] < x["t"] - o < P["sfx_speech_gap"]), None)
        if near is not None:
            x["t"] = round(max(0.0, near - P["sfx_speech_gap"]), 3)
    ed.sfx = _cap_per_minute(_thin_by_gap(sfx, P["sfx_min_gap"]), P["sfx_per_min"])

    # ---- 배경음악 부풀리기 --------------------------------------------------
    first_speech = cues[0]["start"] if cues else 0.0
    ed.bgm_swells = [(0.0, max(P["swell_intro"], first_speech))]
    # 비우기는 정점과 챕터 끝에서만(챕터 카드 스웰 바로 앞) — 자주 비우면 비움이 힘을 잃는다
    ed.bgm_dips = sorted(([(round(max(0.0, peak - 0.8), 3), round(peak + 0.2, 3))] if peak is not None else [])
                         + [(round(max(0.0, c - 1.8), 3), round(max(0.0, c - 0.6), 3)) for c in chapter_starts])
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
    face_time = speech_total - sum(b - a for a, b, _ in covers)
    runs = face_only_runs(graphics, ed.callouts, speech_total)
    ed.stats = {"shots": len(ed.camera), "transitions": len(ed.transitions), "sfx": len(ed.sfx), "callouts": len(ed.callouts),
                "face_ratio": round(face_time / max(1e-6, speech_total), 3),
                "max_face_run": round(max(runs, default=0.0), 1),
                "face_runs_over_25s": sum(1 for r in runs if r > 25.0),
                "holds": len(holds), "hold_sec": round(sum(b - a for a, b in holds), 1)}
    return ed


# ---------------------------------------------------------------------------
# 숏폼
# ---------------------------------------------------------------------------

def build_short_edit(*, timemap: TimeMap, total: float, graphics: list[dict], cues: list[dict],
                     moments: list[Moment], P: dict = PARAMS, seed: int = 2,
                     angle_cuts: Optional[list[float]] = None) -> EditDecisions:
    """숏폼: 프레이밍은 컷 지점에서만 크롭을 바꾼 하드 컷(1.00↔1.12), 화자에게 슬로우 줌·글라이드 없음(디자인 v5).
    다시점 앵글이 바뀌는 곳은 새 샷(1.00부터)."""
    ed = EditDecisions()
    rnd = random.Random(seed)
    # 1) 카메라: 컷 지점에서만 1.00 ↔ 1.12 교차(샷 최소 3.5초). 샷 안에서는 움직이지 않는다.
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
        z = 1.12 if level else 1.0
        level ^= 1
        ed.camera.append({"start": round(a, 3), "end": round(b, 3), "zoom": z, "zoomEnd": z})
    # 2) 전환: 콜드 오픈 → 본론으로 되감는 이음새 하나만(블러 디졸브 9프레임 = '되감기' 신호). 나머지는 컷
    keeps = timemap.keeps
    for i in range(1, len(keeps)):
        if keeps[i].start < keeps[i - 1].start:
            t = timemap.edit_span_of(i).start
            ed.transitions.append({"t": round(t, 3), "type": "zoom", "dur": 0.33})   # 디졸브 대신 줌스루(겹침 없음)
            break
    # 3) 효과음 — 참고 채널(Nick Saraev 숏폼) 실측: 컷에는 whoosh 가 없고(컷 지점 고음 에너지가 평소와 같음),
    #    카드·아이콘이 떨어질 때 작은 pop, 그 밖은 잔잔한 음악만. 그래픽 성격에 맞춰 종류는 다양하게, 5초에 하나 이하.
    sfx: list[dict] = []
    for g in graphics:
        cat = SFX_FOR_TEMPLATE.get(g.get("template", ""), "")
        if cat and g["start"] >= 3.0:          # 훅(첫 3초) 위에는 얹지 않는다(04c 6절)
            sfx.append({"t": landing(g), "category": cat, "gain_db": P["sfx_gain"].get(cat, -18), "prio": 3,
                        "why": f"{g.get('template', '')} 등장"})
    # 마지막은 스코어의 tag 가 맡는다 — 효과음 없음
    ed.sfx = _cap_per_minute(_thin_by_gap(sfx, 5.0), P["sfx_per_min"])
    ed.bgm_swells = [(0.0, 0.8)]
    ed.stats = {"shots": len(ed.camera), "transitions": len(ed.transitions), "punches": len(ed.punches),
                "sfx": len(ed.sfx)}
    return ed
