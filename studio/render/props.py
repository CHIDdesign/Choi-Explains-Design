"""편집 계획 → Remotion props(JSON). renderer/src/lib/types.ts 와 짝을 이룬다."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Optional

from ..director.plan import TimedGraphic, word_edit_time
from ..models import TimeMap, Utterance
from ..settings import Brand
from ..text.align import norm
from ..text.captions import build_cues, build_short_chunks
from ..vision.face import remap_track


LONG_PRESETS = ("editorial", "documentary", "glass", "boxed")
SHORT_PRESETS = ("kinetic", "clean", "boxed", "bar")


def brand_props(b: Brand) -> dict[str, Any]:
    return {"name": b.name, "shortName": b.short_name, "handle": b.handle, "presenter": b.presenter,
            "presenterTitle": b.presenter_title, "accent": b.accent, "ink": b.ink, "paper": b.paper, "year": b.year}


@dataclass
class Episode:
    title: str
    number: str = ""
    subtitle: str = ""
    series: str = "디자인 이론"

    def to_props(self) -> dict[str, str]:
        return {"title": self.title, "number": self.number, "subtitle": self.subtitle, "series": self.series}


# ---------------------------------------------------------------------------
# 카메라
# ---------------------------------------------------------------------------

def camera_shots(timemap: TimeMap, total: float, chapter_starts: list[float], seed: int = 1) -> list[dict]:
    """와이드(1.0)/미디엄(1.1) 2단 프레이밍 — 2캠 교차처럼.

    - 크게 잘라낸 곳(NG·리테이크 제거, 원본에서 1.5초 이상 건너뜀)은 점프컷이 티 나므로 항상 프레이밍 전환
    - 짧은 쉼 컷은 마지막 전환 후 12초 이상 지났을 때만 전환(셜록현준 리서치: 20~40초 간격, 논점 전환 시)
    - 챕터 시작은 와이드로 리셋, 샷 안에서는 아주 느린 푸시인(최대 3.5%)
    """
    rnd = random.Random(seed)
    big_jumps: set[float] = set()
    for i in range(1, len(timemap.keeps)):
        if timemap.keeps[i].start - timemap.keeps[i - 1].end >= 1.5:
            big_jumps.add(round(timemap.edit_span_of(i).start, 3))
    cuts = sorted(set([round(c, 3) for c in timemap.cut_points()] + [round(c, 3) for c in chapter_starts]))
    boundaries = [0.0]
    for c in cuts:
        if c <= 0.05:
            continue
        since = c - boundaries[-1]
        if c in chapter_starts or (c in big_jumps and since >= 2.0) or since >= 12.0:
            boundaries.append(c)
    boundaries.append(total)
    shots: list[dict] = []
    zoom = 1.0
    for i in range(len(boundaries) - 1):
        a, b = boundaries[i], boundaries[i + 1]
        if b - a < 0.05:
            continue
        if a in chapter_starts:
            zoom = 1.0
        elif i > 0:
            zoom = 1.1 if zoom == 1.0 else 1.0
        push = min(0.035, 0.0025 * (b - a)) * (1 if rnd.random() > 0.25 else 0)
        shots.append({"start": round(a, 3), "end": round(b, 3), "zoom": zoom, "zoomEnd": round(zoom * (1 + push), 4)})
    return shots


def punches(emphasis: list[dict], utts: list[Utterance], timemap: TimeMap, *, amount: float = 0.12,
            min_gap: float = 8.0) -> list[dict]:
    by_id = {u.id: u for u in utts}
    out: list[dict] = []
    for e in sorted(emphasis, key=lambda e: e.get("seg", 0)):
        if e.get("kind", "punch") != "punch":
            continue
        u = by_id.get(e.get("seg"))
        if not u or not u.words:
            continue
        t = word_edit_time(u, e.get("word", ""), timemap)
        if t is None:
            t = timemap.src_to_edit(u.words[0].start)
        end = timemap.src_to_edit(u.words[-1].end)
        if t is None or end is None or end - t < 0.6:
            continue
        if out and t - out[-1]["t"] < min_gap:
            continue
        out.append({"t": round(t, 3), "end": round(min(end + 0.2, t + 6.0), 3), "amount": amount})
    return out


def emphasis_keys(emphasis: list[dict], utts: list[Utterance], timemap: TimeMap) -> dict[tuple[float, str], Any]:
    """자막 강조어: {(편집 시각, 정규화 텍스트): 유형(keyword|term|number|contrast) 또는 True}"""
    by_id = {u.id: u for u in utts}
    keys: dict[tuple[float, str], Any] = {}
    for e in emphasis:
        if e.get("kind", "highlight") == "punch" and not e.get("word"):
            continue
        u = by_id.get(e.get("seg"))
        w = norm(e.get("word", ""))
        if not u or not w:
            continue
        for word in u.words:
            wn = norm(word.text)
            if wn and (w in wn or wn in w):
                t = timemap.src_to_edit(word.start, snap=False)
                if t is not None:
                    key = (round(t, 3), word.text.strip().rstrip(".,").replace(" ", ""))
                    typ = e.get("type") or True
                    if keys.get(key) in (None, True):
                        keys[key] = typ
                break
    return keys


# ---------------------------------------------------------------------------
# 오디오
# ---------------------------------------------------------------------------

def speech_regions(cues: list[dict], merge_gap: float = 1.2) -> list[tuple[float, float]]:
    regions: list[tuple[float, float]] = []
    for c in cues:
        for line in c["lines"]:
            for w in line:
                s, e = w["start"], w["end"]
                if regions and s - regions[-1][1] < merge_gap:
                    regions[-1] = (regions[-1][0], max(regions[-1][1], e))
                else:
                    regions.append((s, e))
    return regions


def bgm_envelope(regions: list[tuple[float, float]], total: float, swells: list[tuple[float, float]],
                 under: float = 0.055, gap: float = 0.14, swell: float = 0.26, ramp: float = 0.35) -> list[dict]:
    """목소리 아래로 덕킹(-25dB 안팎), 쉼에서 살짝 올리고, 인트로/챕터/엔드카드에서 부풀린다."""
    pts: list[tuple[float, float]] = [(0.0, swell * 0.8)]
    for s, e in regions:
        pts.append((max(0.0, s - ramp), None))  # type: ignore[arg-type]
        pts.append((s, under))
        pts.append((e, under))
        pts.append((e + ramp, None))  # type: ignore[arg-type]
    pts.append((total, 0.0))

    def level(t: float) -> float:
        for a, b in swells:
            if a <= t <= b:
                return swell
        inside = any(s <= t <= e for s, e in regions)
        return under if inside else gap

    kf: list[dict] = []
    for t, v in sorted(pts, key=lambda p: p[0]):
        val = level(t) if v is None else v
        if any(a <= t <= b for a, b in swells):
            val = swell
        kf.append({"t": round(t, 3), "v": round(val, 4)})
    # 끝 페이드아웃
    kf.append({"t": round(max(0.0, total - 2.0), 3), "v": kf[-1]["v"] if kf else gap})
    kf.append({"t": round(total, 3), "v": 0.0})
    kf.sort(key=lambda k: k["t"])
    dedup: list[dict] = []
    for k in kf:
        if dedup and abs(dedup[-1]["t"] - k["t"]) < 1e-3:
            dedup[-1] = k
        else:
            dedup.append(k)
    return dedup


def sfx_events(graphics: list[dict], sfx: dict[str, str], *, min_gap: float = 6.0) -> list[dict]:
    out: list[dict] = []
    last = -99.0
    for g in sorted(graphics, key=lambda g: g["start"]):
        if g["template"] in ("lower_third",) or g["layout"] == "overlay" and g["template"] != "stat":
            continue
        if g["start"] - last < min_gap:
            continue
        name = "thud" if g["template"] == "chapter" else "whoosh"
        if name in sfx:
            out.append({"src": f"sfx/{sfx[name]}", "t": round(max(0.0, g["start"] - 0.05), 3),
                        "volume": 0.28 if name == "whoosh" else 0.4})
            last = g["start"]
    return out


# ---------------------------------------------------------------------------
# 롱폼
# ---------------------------------------------------------------------------

def panel_side_from_face(samples: list[dict]) -> str:
    if not samples:
        return "right"
    xs = sorted(s["x"] for s in samples)
    med = xs[len(xs) // 2]
    return "left" if med > 0.55 else "right"


def utterance_word_groups(utts: list[Utterance], timemap: TimeMap) -> list[list]:
    groups = []
    for u in utts:
        if not u.kept or not u.words:
            continue
        mapped = timemap.map_words(u.words)
        if mapped:
            groups.append(mapped)
    return groups


def long_props(
    *,
    fps: int,
    brand: Brand,
    episode: Episode,
    utts: list[Utterance],
    timemap: TimeMap,
    graphics: list[TimedGraphic],
    chapters: list[dict],
    emphasis: list[dict],
    face_src: list[dict],
    voice_src: str,
    bgm_src: Optional[str],
    sfx: dict[str, str],
    grain_frames: list[str],
    grain: float,
    caption_preset: str = "editorial",
    endcard: bool = True,
    use_sfx: bool = True,
) -> dict[str, Any]:
    speech_total = timemap.duration
    end_dur = 6.0 if endcard else 0.0
    total = speech_total + end_dur
    em_keys = emphasis_keys(emphasis, utts, timemap)
    cues = build_cues(utterance_word_groups(utts, timemap), emphasis=em_keys)
    face = remap_track(face_src, timemap)
    chapter_starts = [c["start"] for c in chapters]
    gdicts = [g.to_dict() for g in graphics]
    clips = []
    for i, k in enumerate(timemap.keeps):
        span = timemap.edit_span_of(i)
        clips.append({"src": "media/proxy.mp4", "srcStart": round(k.start, 4), "start": round(span.start, 4),
                      "dur": round(k.dur, 4)})
    swells = [(0.0, 1.2)] + [(c, c + 2.5) for c in chapter_starts if c > 1] + ([(speech_total, total)] if endcard else [])
    regions = speech_regions(cues)
    return {
        "fps": fps,
        "width": 1920,
        "height": 1080,
        "duration": round(total, 3),
        "brand": brand_props(brand),
        "episode": episode.to_props(),
        "clips": clips,
        "voice": {"src": voice_src, "volume": 1.0},
        "bgm": {"src": bgm_src, "envelope": bgm_envelope(regions, total, swells), "loop": True} if bgm_src else None,
        "sfx": sfx_events(gdicts, sfx) if use_sfx else [],
        "captions": cues,
        "captionPreset": caption_preset if caption_preset in LONG_PRESETS else "editorial",
        "face": face,
        "camera": camera_shots(timemap, speech_total, chapter_starts),
        "punches": punches(emphasis, utts, timemap),
        "graphics": gdicts,
        "transitions": [],
        "callouts": [],
        "chapters": chapters,
        "panelSide": panel_side_from_face(face_src),
        "endcard": {"start": round(speech_total + 0.2, 3), "dur": end_dur - 0.2} if endcard else None,
        "grain": grain,
        "grainFrames": [f"fx/{f}" for f in grain_frames],
        "showChapterLabel": True,
    }


# ---------------------------------------------------------------------------
# 숏폼
# ---------------------------------------------------------------------------

def short_props(
    *,
    fps: int,
    brand: Brand,
    episode: Episode,
    spec: dict,
    utts: list[Utterance],
    timemap: TimeMap,
    graphics: list[TimedGraphic],
    face_src: list[dict],
    voice_src: str,
    bgm_src: Optional[str],
    sfx: dict[str, str],
    grain_frames: list[str],
    grain: float,
    layout: str = "full",
    progress_bar: bool = False,
    series_label: str = "",
    caption_preset: str = "kinetic",
    extra_emphasis: Optional[list[dict]] = None,
) -> dict[str, Any]:
    by_id = {u.id: u for u in utts}
    groups = []
    for sid in spec["segments"]:
        u = by_id.get(sid)
        if u and u.words:
            mapped = timemap.map_words(u.words)
            if mapped:
                groups.append(mapped)
    em = [{"seg": e["seg"], "word": e.get("word", ""), "kind": "highlight"} for e in spec.get("emphasis", [])]
    # 🔤 자막 디자이너가 롱폼에서 정한 강조(유형 포함) 중 이 숏폼에 들어간 것
    segs = set(spec["segments"])
    em = [e for e in extra_emphasis or [] if e.get("seg") in segs and e.get("kind") == "highlight"] + em
    em_keys = emphasis_keys(em, utts, timemap)
    cues = build_short_chunks(groups, emphasis=em_keys)
    total = timemap.duration
    clips = []
    for i, k in enumerate(timemap.keeps):
        span = timemap.edit_span_of(i)
        clips.append({"src": "media/proxy.mp4", "srcStart": round(k.start, 4), "start": round(span.start, 4),
                      "dur": round(k.dur, 4)})
    # 페이오프 펀치인: 강조어가 있는 청크 중 전체의 60~90% 지점
    pun = []
    for c in cues:
        if any(w.get("em") for line in c["lines"] for w in line) and 0.55 * total <= c["start"] <= 0.9 * total:
            pun.append({"t": c["start"], "end": min(total, c["end"] + 1.2), "amount": 0.1})
            break
    if cues and cues[0]["start"] < 1.5:
        # 시각 훅: 살짝 당긴 프레이밍으로 시작해 첫 자막 청크가 끝나는 자연스러운 쉼에서 풀어준다
        release = min(cues[0]["end"], 3.0, total)
        pun.insert(0, {"t": 0.0, "end": round(max(0.8, release), 3), "amount": 0.08})
    gdicts = [g.to_dict() for g in graphics]
    regions = speech_regions([{"lines": c["lines"]} for c in cues], merge_gap=0.8)
    return {
        "fps": fps,
        "width": 1080,
        "height": 1920,
        "duration": round(total, 3),
        "brand": brand_props(brand),
        "episode": episode.to_props(),
        "clips": clips,
        "voice": {"src": voice_src, "volume": 1.0},
        "bgm": {"src": bgm_src, "envelope": bgm_envelope(regions, total, [], under=0.045, gap=0.08), "loop": True}
        if bgm_src else None,
        "sfx": sfx_events(gdicts, sfx, min_gap=10) if sfx else [],
        "captions": cues,
        "face": remap_track(face_src, timemap),
        "camera": [],
        "punches": pun,
        "graphics": gdicts,
        "transitions": [],
        "hookTitle": spec.get("hook_title") or episode.title,
        "hookHighlight": spec.get("hook_highlight", ""),
        "seriesLabel": series_label,
        "layout": layout,
        "captionPreset": caption_preset if caption_preset in SHORT_PRESETS else "kinetic",
        "progressBar": progress_bar,
        "grain": grain,
        "grainFrames": [f"fx/{f}" for f in grain_frames],
    }


# ---------------------------------------------------------------------------
# 편집 문법 엔진 결과 반영
# ---------------------------------------------------------------------------

def apply_edit(props: dict[str, Any], ed: Any) -> dict[str, Any]:
    """studio/edit/grammar.py 의 EditDecisions → props(카메라·펀치인·전환·강조 자막)."""
    props["camera"] = ed.camera
    props["punches"] = ed.punches
    props["transitions"] = ed.transitions
    if "callouts" in props or getattr(ed, "callouts", None):
        props["callouts"] = list(getattr(ed, "callouts", []) or [])
    for i in ed.impact_cues:
        if 0 <= i < len(props["captions"]):
            props["captions"][i]["style"] = "impact"
    return props


def strip_audio(props: dict[str, Any]) -> dict[str, Any]:
    """음향은 FFmpeg 에서 따로 믹스·마스터링하므로 렌더 props 에서는 뺀다(무음 렌더)."""
    props["voice"] = None
    props["bgm"] = None
    props["sfx"] = []
    return props


def text_graphic_spans(graphics: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """화면에 글자 그래픽이 떠 있는 구간(LongForm.tsx textGraphicActive 와 같은 기준)."""
    return [(g["start"], g["end"]) for g in graphics
            if g["template"] not in ("lower_third", "broll", "photo", "title")]
