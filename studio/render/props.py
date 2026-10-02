"""편집 계획 → Remotion props(JSON). renderer/src/lib/types.ts 와 짝을 이룬다.

long_props/short_props 가 기본 props 를 만들고, 파이프라인이 그 위에 편집 문법 엔진 결과(apply_edit·mark_soft_cuts),
숏폼 개념 텍스트(short_beats), 화면 글자와 같은 말인 자막 숨김(dedupe_captions)을 더한다.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Optional

from ..director.plan import TimedGraphic, word_edit_time
from ..models import TimeMap, Utterance
from ..settings import Brand
from ..text.align import find_word, norm
from ..text.captions import build_phrase_cues, snap_cues_to_speech
from ..vision.face import remap_track


LONG_PRESETS = ("paper", "editorial", "documentary", "glass", "boxed")
SHORT_PRESETS = ("paper", "kinetic", "clean", "boxed", "bar")


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
    """기본 카메라(편집 문법 엔진 없이 props 만 만들 때). 파이프라인은 apply_edit 가 grammar.camera_plan 결과로 덮어쓴다.

    와이드(1.0)/미디엄(1.1) 2단 프레이밍 — 2캠 교차처럼.

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
        word = find_word(u.words, w)
        if word is not None:
            t = timemap.src_to_edit(word.start, snap=False)
            if t is not None:
                key = (round(t, 3), word.text.strip().rstrip(".,").replace(" ", ""))
                typ = e.get("type") or True
                if keys.get(key) in (None, True):
                    keys[key] = typ
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

def two_lines(title: str, min_len: int = 10) -> str:
    """숏폼 첫 장면 큰 제목: 한 줄로 길면 가운데에 가까운 띄어쓰기에서 두 줄로(AI 가 hook_title 을 비웠을 때)."""
    title = (title or "").strip()
    spaces = [i for i, ch in enumerate(title) if ch == " "]
    if "\n" in title or len(title) <= min_len or not spaces:
        return title
    sp = min(spaces, key=lambda i: abs(i - len(title) / 2))
    return title[:sp] + "\n" + title[sp + 1:]


def keep_clips(timemap: TimeMap, src: str = "media/proxy.mp4") -> list[dict[str, Any]]:
    """원본이 하나일 때: keep 마다 클립 하나(프록시 시각 = 원본 시각)."""
    clips = []
    for i, k in enumerate(timemap.keeps):
        span = timemap.edit_span_of(i)
        clips.append({"src": src, "srcStart": round(k.start, 4), "start": round(span.start, 4), "dur": round(k.dur, 4)})
    return clips


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
    skin: str = "classic",
    paper_texture: str = "",
    grain: float,
    caption_preset: str = "paper",
    endcard: bool = True,
    use_sfx: bool = True,
    speech_onsets: Optional[list[float]] = None,
    clips: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """clips: 원본이 여러 개일 때 앵글 조각대로 만든 클립(studio/media/sources.clips_for). 없으면 keep 마다 proxy.mp4.
    face_src 는 그때 앵글을 따라 이은 가상 시각 트랙."""
    speech_total = timemap.duration
    end_dur = 6.0 if endcard else 0.0
    total = speech_total + end_dur
    em_keys = emphasis_keys(emphasis, utts, timemap)
    cues = build_phrase_cues(utterance_word_groups(utts, timemap), emphasis=em_keys)
    snap_cues_to_speech(cues, speech_onsets or [])
    face = remap_track(face_src, timemap)
    chapter_starts = [c["start"] for c in chapters]
    gdicts = paper_layouts([g.to_dict() for g in graphics], skin)
    clips = clips if clips is not None else keep_clips(timemap)
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
        "captionPreset": caption_preset if caption_preset in LONG_PRESETS else "paper",
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
        "peekEvery": 0,   # 렌더 중 진행 화면 미리보기 간격(프레임). 최종 렌더에서만 켠다
        # classic(기본) = 에디토리얼 + 레퍼런스 일부(얼굴 위 사진 액자·개념 카드 글 위계·타이틀 구도·출처·오늘의 정리),
        # paper = 레퍼런스 종이 콜라주 전체(구겨진 종이·거친 테두리·화자 액자 샷)
        "skin": skin,
        "paperTexture": f"fx/{paper_texture}" if paper_texture else "",
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
    skin: str = "classic",
    paper_texture: str = "",
    grain: float,
    layout: str = "full",
    progress_bar: bool = False,
    series_label: str = "",
    caption_preset: str = "paper",
    extra_emphasis: Optional[list[dict]] = None,
    speech_onsets: Optional[list[float]] = None,
    clips: Optional[list[dict[str, Any]]] = None,
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
    # 릴스식은 한두 마디씩 아주 크게(참고 릴스: 5~8자), 그 밖은 12자
    cues = build_phrase_cues(groups, emphasis=em_keys, max_chars=6 if layout == "reel" else 12,
                             max_dur=1.1 if layout == "reel" else 2.0)
    snap_cues_to_speech(cues, speech_onsets or [])
    total = timemap.duration
    clips = clips if clips is not None else keep_clips(timemap)
    # 페이오프 강조(글라이드): 강조어가 있는 청크 중 전체의 55~90% 지점
    pun = []
    for c in cues:
        if any(w.get("em") for line in c["lines"] for w in line) and 0.55 * total <= c["start"] <= 0.9 * total:
            pun.append({"t": c["start"], "end": min(total, c["end"] + 1.2), "amount": 0.06, "style": "glide"})
            break
    if cues and cues[0]["start"] < 1.5:
        # 시각 훅: 살짝 당긴 프레이밍으로 시작해 첫 자막 청크가 끝나는 자연스러운 쉼에서 풀어준다
        release = min(cues[0]["end"], 3.0, total)
        pun.insert(0, {"t": 0.0, "end": round(max(0.8, release), 3), "amount": 0.06, "style": "glide"})
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
        "hookTitle": spec.get("hook_title") or two_lines(episode.title),
        "hookHighlight": spec.get("hook_highlight", ""),
        "seriesLabel": series_label,
        "layout": layout,
        "captionPreset": caption_preset if caption_preset in SHORT_PRESETS else "paper",
        "progressBar": progress_bar,
        "grain": grain,
        "grainFrames": [f"fx/{f}" for f in grain_frames],
        "peekEvery": 0,
        "skin": skin,
        "paperTexture": f"fx/{paper_texture}" if paper_texture else "",
    }


# ---------------------------------------------------------------------------
# 편집 문법 엔진 결과 반영
# ---------------------------------------------------------------------------

PAPER_SPLIT = ("keyword", "definition", "quote", "stat")


def paper_layouts(gdicts: list[dict[str, Any]], skin: str) -> list[dict[str, Any]]:
    """종이 스킨: 전면 개념 카드(키워드·정의·인용·숫자)는 '글 왼쪽 + 화자 액자 오른쪽'(사용자 레퍼런스 1)으로.
    전면 종이에 글만 있으면 오른쪽 절반이 비고 화자도 사라진다."""
    if skin != "paper":
        return gdicts
    for g in gdicts:
        if g.get("template") in PAPER_SPLIT and g.get("layout") == "fullscreen":
            g["layout"] = "split"
    return gdicts


# ---------------------------------------------------------------------------
# 🎬 오프닝 하이라이트: 본편 props 를 뒤로 밀고 앞에 하이라이트 props 를 붙인다
# ---------------------------------------------------------------------------
def shift_props(props: dict[str, Any], dt: float) -> None:
    """props 의 모든 시각 필드를 dt 만큼 뒤로(제자리)."""
    def sh(d: dict[str, Any], *keys: str) -> None:
        for k in keys:
            if k in d and d[k] is not None:
                d[k] = round(float(d[k]) + dt, 3)
    for c in props.get("clips") or []:
        c["start"] = round(c["start"] + dt, 4)
    for c in props.get("captions") or []:
        sh(c, "start", "end")
        for line in c.get("lines") or []:
            for w in line:
                sh(w, "start", "end")
    for f in props.get("face") or []:
        sh(f, "t")
    for x in props.get("camera") or []:
        sh(x, "start", "end")
    for x in props.get("punches") or []:
        sh(x, "t", "end")
    for x in props.get("graphics") or []:
        sh(x, "start", "end")
    for x in props.get("transitions") or []:
        sh(x, "t")
    for x in props.get("callouts") or []:
        sh(x, "start", "end")
    for x in props.get("chapters") or []:
        sh(x, "start")
    for x in props.get("sfx") or []:
        sh(x, "t")
    if props.get("endcard"):
        sh(props["endcard"], "start")
    if props.get("bgm"):
        for k in props["bgm"].get("envelope") or []:
            sh(k, "t")
    props["duration"] = round(props["duration"] + dt, 3)


def prepend_props(main: dict[str, Any], head: dict[str, Any]) -> None:
    """head(하이라이트, 0초부터) 의 시간 목록을 main(이미 shift_props 로 밀어 둔 본편) 앞에 붙인다."""
    for k in ("clips", "captions", "face", "camera", "punches", "graphics", "transitions", "callouts", "sfx"):
        main[k] = list(head.get(k) or []) + list(main.get(k) or [])


def shift_decisions(ed: Any, dt: float) -> None:
    """편집 문법 결정(음향 믹스가 쓰는 효과음·음악 큐)을 dt 만큼 뒤로."""
    for s_ in ed.sfx:
        s_["t"] = round(s_["t"] + dt, 3)
    ed.bgm_swells = [(round(a + dt, 3), round(b + dt, 3)) for a, b in ed.bgm_swells]
    ed.bgm_dips = [(round(a + dt, 3), round(b + dt, 3)) for a, b in ed.bgm_dips]
    ed.bgm_switch = [round(t + dt, 3) for t in ed.bgm_switch]


# ---------------------------------------------------------------------------
# 얼굴을 가리지 않는 배치(채널 피드백: 얼굴 옆 사진 액자·개념 텍스트가 자주 얼굴을 덮었다)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 🎓 롱폼 무대(docs/롱폼_무대_디자인.md) 편집법: 챕터 카드 목차 + 챕터 끝 정리 보드
# ---------------------------------------------------------------------------
RECAP_SOURCES = ("keyword", "definition", "stat", "list", "compare", "quote", "process", "cycle", "double_diamond",
                 "matrix", "timeline", "venn", "pyramid", "motion", "card")
RECAP_MIN_CHAPTER = 45.0      # 이보다 짧은 챕터는 정리하지 않는다
RECAP_DUR = (7.0, 5.0)        # 먼저 7초, 안 되면 5초
RECAP_SEARCH = 20.0           # 챕터 끝에서 이만큼 앞까지 빈 창을 찾는다(챕터 끝에 그래픽이 몰리면 12초로는 자주 못 찾았다)


def _shorten(text: str, n: int = 26) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def recap_point(g: dict[str, Any]) -> str:
    """그래픽 하나 → 정리 보드 한 줄(핵심 개념)."""
    d = g.get("data") or {}
    tpl = g.get("template", "")
    title = str(d.get("title") or "").strip()
    body = str(d.get("body") or "").strip()
    if tpl == "definition":
        return _shorten(f"{title}: {body}" if title and body else title or body, 30)
    if tpl == "stat":
        return _shorten(f"{title} — {body}" if title and body else title or body, 30)
    if tpl == "compare":
        b = str(d.get("title_b") or "").strip()
        return _shorten(f"{title} vs {b}" if title and b else d.get("subtitle") or title or b)
    if tpl == "quote":
        who = str(d.get("author") or "").strip()
        return _shorten(f"{who}: “{body}”" if who and body else body or title, 30)
    if tpl == "card":
        card = d.get("card")
        if isinstance(card, dict) and not title:
            from ..motion.card import card_text
            return _shorten(card_text(card).split("\n")[0] if card_text(card) else "")
    if tpl == "motion" and not title:
        spec = d.get("spec")
        if isinstance(spec, dict):
            title = str(spec.get("label") or "")
    return _shorten(title)


def chapter_recaps(gdicts: list[dict[str, Any]], chapters: list[dict[str, Any]], speech_total: float,
                   avoid: Optional[list[tuple[float, float]]] = None) -> list[dict]:
    """챕터 끝 **정리 보드**(템플릿 recap, split): 그 챕터에서 나온 키워드·정의·숫자·목록·비교·도식 제목을 시간순으로 2~4개
    모아, 챕터 끝 7초(안 되면 5초)에 다른 그래픽과 겹치지 않는 가장 늦은 창에 둔다. 45초 넘는 챕터만.
    avoid: 편집 감독의 강조 순간·⚡ 펀치 구간(편집 시각) — 얼굴로 힘을 주는 자리라 보드로 덮지 않는다(자리가 없으면 정리를
    건너뛴다). gdicts 에 바로 추가하고(시간순 유지) 추가한 것을 돌려준다. AI 가 만드는 목록과 다른, 앱의 롱폼 편집법."""
    if not chapters:
        return []
    starts = sorted(float(c["start"]) for c in chapters)
    bounds = starts + [float(speech_total)]
    busy = [(g["start"] - 0.5, g["end"] + 0.3) for g in gdicts if g.get("template") != "lower_third"]
    busy += [(float(a), float(b)) for a, b in (avoid or []) if b > a]
    added: list[dict] = []
    for ci, c in enumerate(sorted(chapters, key=lambda c: float(c["start"]))):
        a, b = bounds[ci], bounds[ci + 1]
        if b - a < RECAP_MIN_CHAPTER:
            continue
        points: list[str] = []
        for g in sorted(gdicts, key=lambda g: g["start"]):
            if not (a <= g["start"] < b) or g.get("template") not in RECAP_SOURCES:
                continue
            p = recap_point(g)
            key = p.replace(" ", "").lower()
            if p and key not in {q.replace(" ", "").lower() for q in points}:
                points.append(p)
        if len(points) < 2:
            continue
        points = points[:4]
        placed = None
        end = b - 0.4
        while placed is None and end >= b - RECAP_SEARCH:
            for dur in RECAP_DUR:
                st = end - dur
                if st < a + 20.0:
                    continue
                if not any(st < y and end > x for x, y in busy):
                    placed = (st, end)
                    break
            end -= 0.5
        if placed is None:
            continue
        st, end = placed
        g = {"id": f"recap{c.get('number', ci + 1)}", "template": "recap", "layout": "split", "start": round(st, 3),
             "end": round(end, 3), "priority": 6, "source": "auto",
             "data": {"title": str(c.get("claim") or c.get("title") or ""), "subtitle": "이번 챕터 정리",
                      "number": str(c.get("number", "")), "items": points}}
        gdicts.append(g)
        busy.append((st - 0.5, end + 0.3))
        added.append(g)
    if added:
        gdicts.sort(key=lambda g: g["start"])
    return added


def chapter_maps(gdicts: list[dict[str, Any]], chapters: list[dict[str, Any]]) -> int:
    """챕터 카드에 **목차**(전체 챕터 제목 + 지금 챕터)를 넣는다 → 렌더러 ChapterCard 가 그린다."""
    titles = [str(c.get("title") or "") for c in sorted(chapters, key=lambda c: float(c["start"]))]
    numbers = [str(c.get("number") or "") for c in sorted(chapters, key=lambda c: float(c["start"]))]
    n = 0
    for g in gdicts:
        if g.get("template") != "chapter":
            continue
        d = g.setdefault("data", {})
        d["items"] = titles
        num = str(d.get("number") or "")
        d["highlight"] = numbers.index(num) if num in numbers else -1
        n += 1
    return n


# ---------------------------------------------------------------------------
# 📸 자료 사진 위 키워드 슬램(레퍼런스: 같은 사진이 이어진 채 어두워지며 큰 키워드 + 'A → B')
# ---------------------------------------------------------------------------
def fold_keywords_into_media(gdicts: list[dict[str, Any]], *, gap: float = 0.6) -> int:
    """전면 사진·스톡 **안에서 시작하거나 바로 뒤에 붙는** 키워드 그래픽을 그 사진에 접는다: 사진은 이어지고
    `keyword_at` 초부터 어두워지며 큰 키워드(`keyword`)와 아랫줄(`keyword_sub`: subtitle/body)이 뜬다.
    따로 뜨던 키워드 그래픽은 지운다. 돌려주는 값: 접은 개수."""
    media = [g for g in gdicts if g.get("layout") == "fullscreen" and g.get("template") in ("photo", "broll")]
    folded = 0
    for k in [g for g in gdicts if g.get("template") == "keyword"]:
        title = str((k.get("data") or {}).get("title") or "").strip()
        if not title:
            continue
        for m in media:
            if m.get("data", {}).get("keyword"):
                continue
            inside = m["start"] <= k["start"] < m["end"] - 1.2
            after = 0 <= k["start"] - m["end"] <= gap
            if not (inside or after):
                continue
            d = m.setdefault("data", {})
            d["keyword"] = title
            d["keyword_sub"] = str(k["data"].get("subtitle") or k["data"].get("body") or "")
            d["keyword_at"] = round((k["start"] if inside else m["end"]) - m["start"], 3)
            if after or k["end"] > m["end"]:
                m["end"] = round(max(m["end"], k["end"]), 3)
            gdicts.remove(k)
            folded += 1
            break
    return folded


PIP_W, PIP_H = 700, 520       # renderer Collage.pipBoxes 기본 액자 크기
PIP_MIN_W = 420               # 이보다 작아지면 액자 대신 화자 패널(split)로
PIP_MARGIN = 60
PIP_TEMPLATES = ("photo", "broll", "keyword", "definition", "quote", "stat")
TOPBAR_MAX_CHARS = 16          # 이보다 짧은 키워드(보조문 없음)는 화면 위 소제목 바
TOPBAR_CLEAR = 230             # 머리 위가 이만큼(px) 비어 있어야 소제목 바
TOPBAR_W, TOPBAR_H = 1240, 120
TOPBAR_MIN_HOLD = 4.5          # 소제목 바는 적어도 이만큼(레퍼런스 실측: 섹션 태그 4~6초) — 다음 그래픽 앞까지만


def _head_half_width(s: float, H: int) -> float:
    """얼굴 상자 높이 비율(s) → 화면에서 머리(머리카락·귀 포함)가 차지하는 반폭(px) + 여유."""
    return s * H * 0.64 + 40.0


def face_safe_layouts(gdicts: list[dict[str, Any]], face: list[dict[str, Any]], *, W: int = 1920, H: int = 1080
                      ) -> dict[str, int]:
    """pip/overlay 그래픽(사진 액자·개념 텍스트)마다 그 구간의 얼굴 트랙(편집 시각)으로 **빈 쪽**과 액자 크기를 정한다.
    · 얼굴 왼쪽·오른쪽 여유 중 넓은 쪽, 액자는 여유에 맞춰 700→420px 까지 줄인다
    · 어느 쪽도 420px 이 안 되면(클로즈업·화면 가운데) 액자 대신 화자 패널(split)로 바꾼다 — 얼굴 위에 얹지 않는다
    결과는 g["pip"] = {side, w, h}(렌더러 pipBoxes 가 그대로 쓴다). 얼굴 트랙이 없으면 예전대로(렌더러가 faceX 로)."""
    import bisect
    stats = {"placed": 0, "shrunk": 0, "to_split": 0, "top": 0}
    if not face:
        return stats
    ts = [f["t"] for f in face]
    for g in gdicts:
        if g.get("layout") not in ("pip", "overlay") or g.get("template") not in PIP_TEMPLATES:
            continue
        i0 = max(0, bisect.bisect_left(ts, g["start"] - 0.3) - 1)
        i1 = min(len(face), bisect.bisect_right(ts, g["end"] + 0.3) + 1)
        sub = face[i0:i1] or [min(face, key=lambda f: abs(f["t"] - g["start"]))]
        left_edge = min(f["x"] * W - _head_half_width(f["s"], H) for f in sub)
        right_edge = max(f["x"] * W + _head_half_width(f["s"], H) for f in sub)
        # 짧은 키워드(보조문 없음)는 화면 위 **소제목 바**(레퍼런스: 종이 띠 + '!' 배지) — 머리 위가 비어 있을 때만
        d = g.get("data") or {}
        if g.get("template") == "keyword" and len(str(d.get("title") or "")) <= TOPBAR_MAX_CHARS \
                and not d.get("subtitle") and not d.get("body"):
            head_top = min(f["y"] * H - f["s"] * H * 0.95 for f in sub)
            if head_top >= TOPBAR_CLEAR:
                g["pip"] = {"side": "top", "w": TOPBAR_W, "h": TOPBAR_H}
                nxt = min([o["start"] for o in gdicts if o is not g and o["start"] > g["start"]], default=face[-1]["t"])
                g["end"] = round(max(g["end"], min(g["start"] + TOPBAR_MIN_HOLD, nxt - 0.3, face[-1]["t"])), 3)
                stats["placed"] += 1
                stats["top"] = stats.get("top", 0) + 1
                continue
        free_left = left_edge - PIP_MARGIN
        free_right = W - right_edge - PIP_MARGIN
        side = "left" if free_left >= free_right else "right"
        free = max(free_left, free_right)
        w = min(PIP_W, free - 24)
        if w < PIP_MIN_W:
            g["layout"] = "split"
            g.pop("pip", None)
            stats["to_split"] += 1
            continue
        w = int(round(w))
        g["pip"] = {"side": side, "w": w, "h": int(round(w * PIP_H / PIP_W))}
        stats["placed"] += 1
        if w < PIP_W:
            stats["shrunk"] += 1
    return stats


def mark_soft_cuts(clips: list[dict[str, Any]], camera: list[dict[str, Any]], transitions: list[dict[str, Any]],
                   soft: float) -> int:
    """프레이밍이 그대로 이어지는 점프컷에 소프트 컷(앞 장면 마지막 프레임을 soft 초 동안 섞기)을 표시.
    프레이밍이 바뀌는 컷(카메라 경계)·전환이 있는 컷·앵글이 바뀌는 컷은 그대로 둔다. 길이·싱크는 바뀌지 않는다.
    같은 keep 안에서 앵글만 바뀌는 자리(원본 시각이 이어짐)는 점프컷이 아니므로 애초에 소프트 컷 대상이 아니다."""
    bounds = [float(s["start"]) for s in camera if not s.get("glide")]
    tx = [float(e["t"]) for e in transitions]
    n = 0
    for prev, c in zip(clips, clips[1:]):
        c.pop("soft", None)
        t = float(c["start"])
        if soft <= 0 or any(abs(b - t) < 0.05 for b in bounds) or any(abs(x - t) < 0.4 for x in tx):
            continue
        if prev.get("src") != c.get("src"):      # 앵글이 바뀌는 컷(다시점)은 하드 컷
            continue
        c["soft"] = round(soft, 3)
        n += 1
    return n


def apply_edit(props: dict[str, Any], ed: Any) -> dict[str, Any]:
    """studio/edit/grammar.py 의 EditDecisions → props(카메라·강조 글라이드·전환·콜아웃·강조 자막·소프트 컷)."""
    props["camera"] = ed.camera
    props["punches"] = ed.punches
    props["transitions"] = ed.transitions
    mark_soft_cuts(props["clips"], ed.camera, ed.transitions, float(getattr(ed, "soft_cut", 0.0) or 0.0))
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


def bridge_split_gaps(graphics: list[dict[str, Any]], *, gap: float = 1.0) -> int:
    """F-7(docs/upgrade/06 4-4): 화자가 판으로 줄어든 동안에는 종이 판이 늘 있다 — 이어지는 split 그래픽 사이가 1.0초
    미만이면(렌더러 buildRegionSpans 가 화자를 줄인 채 두는 간격) 앞 그래픽을 다음 시작까지 늘린다. 같은 구성(skin)끼리만.
    10/1: 08:45·10:45 에 화자가 줄어든 채 옆이 비었다. 반환: 늘린 수."""
    splits = sorted((g for g in graphics if g.get("layout") == "split" and g.get("template") != "title"),
                    key=lambda g: g["start"])
    n = 0
    for a, b in zip(splits, splits[1:]):
        d = b["start"] - a["end"]
        if 0 < d < gap and a.get("skin") == b.get("skin"):
            a["end"] = round(b["start"], 3)
            n += 1
    return n


def stack_avoid_spans(props: dict[str, Any]) -> list[tuple[float, float]]:
    """F-9: 두 층 강조 자막을 피할 구간 — 글자 그래픽 + 콜아웃 + 얼굴 옆 메모·사진(pip/overlay). 같은 순간 글자 층은 둘까지."""
    out = text_graphic_spans(props.get("graphics") or [])
    out += [(float(c["start"]), float(c["end"])) for c in props.get("callouts") or [] if "start" in c and "end" in c]
    out += [(g["start"], g["end"]) for g in props.get("graphics") or []
            if g.get("layout") in ("pip", "overlay") and g["template"] in ("broll", "photo")]
    return sorted(out)


def text_graphic_spans(graphics: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """화면에 글자 그래픽이 떠 있는 구간(LongForm.tsx textGraphicActive 와 같은 기준)."""
    return [(g["start"], g["end"]) for g in graphics
            if g["template"] not in ("lower_third", "broll", "photo", "title")]


# ---------------------------------------------------------------------------
# 숏폼 개념 텍스트(beats: 릴스식 위 카드 · 종이 스킨 하단)
# ---------------------------------------------------------------------------

def _cue_text(c: dict[str, Any]) -> str:
    return " ".join(w["text"] for line in c["lines"] for w in line).strip(" .,!?…")


def short_beats(spec: dict[str, Any], utts: list[Utterance], timemap: TimeMap, cues: list[dict[str, Any]],
                moments: list[Any], total: float, *, min_len: float = 2.2, max_len: float = 5.0,
                every: float = 4.5) -> list[dict[str, Any]]:
    """3~5초마다 바뀌는 개념 텍스트(릴스식은 위 카드, 종이 스킨 숏폼은 하단). AI 가 쓴 beats(발화 기준)를
    편집 시간으로 옮기고, 모자라면 강조 순간(콜아웃)·강조어가 든 자막으로 채워 화면이 비지 않게 한다."""
    by_id = {u.id: u for u in utts}
    raw: list[dict[str, Any]] = []
    for b in spec.get("beats", []) or []:
        u = by_id.get(b.get("seg"))
        if not u or not u.words:
            continue
        t = timemap.src_to_edit(u.words[0].start, snap=True)
        if t is not None and t < total - 1.0:
            raw.append({"start": t, "text": b["text"], "label": b.get("label", ""), "accent": b.get("accent", ""),
                        "prio": 3})
    for m in moments:
        text = (getattr(m, "callout", "") or "").replace("\\n", "\n").split("\n")[0].strip()
        if text:
            raw.append({"start": m.t, "text": text[:16], "label": getattr(m, "label", "") or "핵심",
                        "accent": getattr(m, "word", "") or "", "prio": 2})
    for c in cues:
        ems = [w for line in c["lines"] for w in line if w.get("em")]
        if ems:
            text = _cue_text(c)
            if 3 <= len(text) <= 16:
                raw.append({"start": c["start"], "text": text, "label": "포인트",
                            "accent": ems[0]["text"].strip(" .,!?…"), "prio": 1})
    raw.sort(key=lambda b: (b["start"], -b["prio"]))
    out: list[dict[str, Any]] = []
    for b in raw:
        if b["start"] < 0.25:
            b["start"] = 0.25
        if out and b["start"] - out[-1]["start"] < every * (0.55 if b["prio"] >= 3 else 1.0):
            if b["prio"] > out[-1]["prio"] and b["start"] - out[-1]["start"] < 1.0:
                out[-1] = b                                  # 거의 같은 자리면 더 중요한 쪽
            continue
        out.append(b)
    for i, b in enumerate(out):
        nxt = out[i + 1]["start"] - 0.2 if i + 1 < len(out) else total - 0.3
        b["end"] = round(min(b["start"] + max_len, nxt), 3)
        b["start"] = round(b["start"], 3)
        if b["accent"] and b["accent"] not in b["text"]:
            b["accent"] = ""
    return [{k: b[k] for k in ("start", "end", "text", "label", "accent")} for b in out if b["end"] - b["start"] >= min_len]


# ---------------------------------------------------------------------------
# 화면 그래픽과 겹치는 자막 숨기기
# ---------------------------------------------------------------------------

def _graphic_text(g: dict[str, Any]) -> str:
    d = g.get("data", g)
    parts = [str(d.get(k) or "") for k in ("title", "subtitle", "body", "title_b", "author", "number", "keyword",
                                           "keyword_sub")]
    parts += [str(x) for k in ("items", "items_b") for x in (d.get(k) or [])]
    spec = d.get("spec")
    if isinstance(spec, dict):
        parts += [str(e.get("text", "")) for e in spec.get("elements", []) or [] if isinstance(e, dict)]
        parts.append(str(spec.get("label", "")))
    card = d.get("card")
    if isinstance(card, dict):
        from ..motion.card import card_text
        parts.append(card_text(card))
    return " ".join(p for p in parts if p)


def mark_sequences(props: dict[str, Any], seq_types: Optional[dict[str, str]] = None) -> int:
    """같은 시퀀스(data.seq_id)의 그래픽에 g.seq = {id, type, index, count} — 렌더러는 둘째 샷부터 등장 애니메이션 없이 컷한다.
    반환: 시퀀스 수."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for g in props.get("graphics", []) or []:
        sid = str((g.get("data") or {}).get("seq_id") or "")
        if sid:
            groups.setdefault(sid, []).append(g)
    for sid, gs in groups.items():
        gs.sort(key=lambda g: g["start"])
        for i, g in enumerate(gs):
            g["seq"] = {"id": sid, "type": (seq_types or {}).get(sid, ""), "index": i, "count": len(gs)}
    return len(groups)


HIGH_LOAD_SEQ = ("document_read", "detail_zoom")


def high_load_spans(props: dict[str, Any], seq_types: Optional[dict[str, str]] = None) -> list[tuple[float, float]]:
    """뜯어봐야 하는 화면(load: high — 단계 도식 walkthrough·문서 읽기·뜯어보기) 구간. 그 위에서는 자막을 숨긴다(눈이 화면에
    있어야 한다 — docs/upgrade/05 6-4, 메이어의 중복 원칙). seq_types: 시퀀스 id → 유형."""
    out = []
    for g in props.get("graphics", []) or []:
        d = g.get("data") or {}
        st = (seq_types or {}).get(str(d.get("seq_id") or ""), "")
        if d.get("stepAt") or st in HIGH_LOAD_SEQ:
            if g.get("layout") in ("fullscreen", "split"):
                out.append((float(g["start"]), float(g["end"])))
    return out


def hide_over(cues: list[dict[str, Any]], spans: list[tuple[float, float]], *, overlap: float = 0.5) -> int:
    """구간과 절반 넘게 겹치는 자막을 화면에서만 숨긴다(SRT 에는 남는다)."""
    n = 0
    for c in cues:
        dur = max(1e-3, c["end"] - c["start"])
        if not c.get("hidden") and any(min(b, c["end"]) - max(a, c["start"]) >= overlap * dur for a, b in spans):
            c["hidden"] = True
            n += 1
    return n


def dedupe_captions(cues: list[dict[str, Any]], overlays: list[tuple[float, float, str]], *, share: float = 0.6,
                    overlap: float = 0.5) -> int:
    """화면 그래픽이 이미 같은 말을 보여 주는 동안의 자막에 hidden 표시(화면에서만 끔 — SRT 에는 남는다).
    같은 말 = 자막 어절의 share 이상이 그 그래픽 글자에 있다(조사·어미가 달라도 같은 어간이면 같은 말)."""
    from ..text.takes import ntok, same_word
    ov = [(a, b, [ntok(w) for w in text.split() if ntok(w)]) for a, b, text in overlays if text.strip()]
    n = 0
    for c in cues:
        c.pop("hidden", None)
        words = [ntok(w["text"]) for line in c["lines"] for w in line]
        words = [w for w in words if w]
        if not words:
            continue
        dur = max(1e-3, c["end"] - c["start"])
        for a, b, toks in ov:
            if min(b, c["end"]) - max(a, c["start"]) < overlap * dur:
                continue
            hit = sum(1 for w in words if any(same_word(w, t) or (len(w) >= 2 and w in t) for t in toks))
            if hit / len(words) >= share and (hit >= 2 or (len(words) == 1 and len(words[0]) >= 2)):
                c["hidden"] = True
                n += 1
                break
    return n


def caption_overlays(props: dict[str, Any]) -> list[tuple[float, float, str]]:
    """props 의 그래픽·콜아웃·(숏폼) 개념 텍스트 → (시작, 끝, 화면 글자)."""
    out = [(g["start"], g["end"], _graphic_text(g)) for g in props.get("graphics", [])
           if g.get("template") not in ("lower_third",)]
    out += [(c["start"], c["end"], c.get("text", "")) for c in props.get("callouts", []) or []]
    out += [(b["start"], b["end"], b.get("text", "")) for b in props.get("beats", []) or []]
    return out


def mark_stack_cues(cues: list[dict[str, Any]], *, min_gap: float, avoid: Optional[list[tuple[float, float]]] = None,
                    max_chars: int = 16) -> int:
    """두 층 강조 자막(기울인 명조 앞말 + 굵은 그라데이션 핵심어)을 쓸 큐에 style='stack'.
    참고 채널 실측: 몇 초에 한 번, 핵심어가 든 한 마디에만(롱폼은 18초 안팎, 숏폼은 3~5초에 하나).
    grammar 가 이미 'impact' 로 고른 큐도 같은 모양으로 그리므로 간격 계산에 넣는다."""
    avoid = avoid or []
    last = -1e9
    n = 0
    for c in cues:
        if c.get("style") == "impact":
            last = c["start"]
            continue
        if c.get("hidden") or c.get("style"):
            continue
        words = [w for line in c["lines"] for w in line]
        text = "".join(w["text"] for w in words)
        if not any(w.get("em") for w in words) or len(text) > max_chars:
            continue
        if c["start"] - last < min_gap or any(a - 0.2 <= c["start"] < b + 0.2 for a, b in avoid):
            continue
        c["style"] = "stack"
        last = c["start"]
        n += 1
    return n
