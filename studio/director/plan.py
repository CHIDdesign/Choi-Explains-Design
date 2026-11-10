"""디렉터 출력(발화 ID 기준) 검증 → 대본 태그 강제 반영 → 편집 시간 기준 이벤트로 변환."""
from __future__ import annotations

import copy
import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, Optional

from ..models import Tag, TimeMap, Utterance
from ..motion.card import card_settle_time, card_text, clean_card
from ..motion.lint import settle_of
from ..motion.spec import clean_spec, stage_first
from ..text.align import find_word, norm
from ..text.topic import strip_label
from .catalog import DIAGRAM_ALIASES, PRESET_DIAGRAMS, TAG_TO_TEMPLATE, TEMPLATES
from .schema import HOOK_TYPES, OVERLAY_KINDS, TONES

EM_TYPES = ("keyword", "term", "number", "contrast")  # 자막 강조 유형(renderer EmType)
MOMENT_KINDS = ("punchline", "reveal", "shift", "conclusion", "question", "number", "joke")  # 강조 순간
SOUND_GAG_TYPES = ("thud", "silence_beat", "mismatch", "literal", "mickey", "callback")

# 렌더러로 넘기는 그래픽 데이터 키(템플릿별로 없는 키는 생략)
DATA_KEYS = ("title", "subtitle", "body", "items", "title_b", "items_b", "highlight", "author", "source", "image")
EXTRA_DATA_KEYS = ("credit", "src", "kind", "kenburns", "stock_url", "logo", "mat", "motif",
                   "assets", "treatment", "archive", "caption", "tier",   # 뒤 다섯 = 증거 자료(evidence, 03b 1절)
                   "year", "display", "quote", "cut", "w", "h",          # 디자인 v3 콜라주(연도 · 큰 글자 · 인용 · 오린 사진)
                   "cutouts", "safe", "face", "focus", "fit", "tone", "name", "name_sub", "disc")               # 사진 위 구도(studio/vision/compose.py) · 바탕 처리
# 증거 자료(evidence)의 트리트먼트별 기본 유지 시간(03b 14절 — 읽을 것이 있으면 길게)
EVIDENCE_HOLD = {"hero": 4.5, "full": 3.5, "collage": 5.0, "archive_card": 4.2, "browser_frame": 5.0, "doc_highlight": 6.0,
                 "grid": 4.5, "compare_pair": 6.0, "pip": 3.0}
# 총괄 감독이 트리트먼트에서 고르는 효과음(그래픽이 들어올 때) — 모션 그래픽에서 흔히 쓰는 소리(Pixabay·Mixkit, 매니페스트)
SFX_DIRECTED = ("paper_slide", "paper_place", "page_turn", "pencil_stroke", "pencil_tick", "stamp", "tape",
                "whoosh_soft", "swoosh_short", "swipe", "pop", "click", "typing", "camera_shutter", "paper", "ding",
                "bell_soft", "notification")
EVIDENCE_ASSET_KEYS = ("src", "kind", "w", "h", "focus", "credit", "credit_full", "tier", "origin", "shows", "score",
                       "meta", "mat_src", "cut", "tight")

GRAPHIC_KEYS = ("template", "layout", "start_seg", "end_seg", "start_word", "title", "subtitle", "body",
                "items", "title_b", "items_b", "highlight", "author", "source", "image", "reason", "motif")
LOGO_MAX_SEC = 4.0      # 로고는 이름표 — 길어도 4초(2026-10-03: 큰 흰 판 가운데 작은 휘장 하나가 12.3초)


PIECE_TEMPLATES = ("cutout_stack", "collage", "keyword_montage")     # data.cutouts 를 말에 착지시키는 템플릿
OVERLAY_FREE = ("memo", "label")      # 좌표 없이 빈 쪽에 놓을 수 있는 것 — 나머지는 어디를 가리키는지 알아야 한다
OVERLAY_MAX = 3                       # 한 화면에
OUTLINE_MIN = 8                       # 꼭짓점이 이보다 적은 윤곽은 대상을 따라가지 못한다 — 손으로 그린 원으로
OVERLAY_TEXT = {"memo": 18, "stamp": 6, "dimension": 12}
OVERLAY_SETTLE = 0.33                 # 렌더러의 착지 10프레임
CREDIT_MAX = 120
CUTOUT_KEYS = ("image", "label", "cut", "w", "h", "credit", "credit_full", "seg", "word", "orig", "kind")


def _unit(v: Any, n: int) -> list[float]:
    """길이 n 의 0~1 숫자 목록. 모양이 틀리면 []."""
    if not isinstance(v, list) or len(v) != n or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
        return []
    return [round(max(0.0, min(1.0, float(x))), 4) for x in v]


def overlay_weight(o: dict[str, Any]) -> int:
    return 2 if o.get("text") and o["kind"] not in ("label", "memo", "stamp", "dimension") else 1


def _within_budget(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """한 화면 OVERLAY_MAX 개까지 — 글이 달린 표시는 표시 + 종이 표찰 둘로 센다. 말에 착지하는 것(at_word)부터 남기고 순서는 그대로(Overlays.tsx withinBudget 과 같은 규칙)."""
    keep: set[int] = set()
    used = 0
    for o in sorted(items, key=lambda o: not o.get("at_word")):
        w = overlay_weight(o)
        if used + w <= OVERLAY_MAX:
            keep.add(id(o))
            used += w
    return [o for o in items if id(o) in keep]


def clean_overlays(raw: Any) -> list[dict[str, Any]]:
    """이미지 위 그래픽의 규칙 한 곳: 한 화면 3개, 좌표는 그림을 본 비전이 준 0~1 만. 좌표가 없으면 memo·label 만 남는다
    (추측 금지 — 다른 종류는 글이 있으면 label 로 낮추고 없으면 뺀다)."""
    from ..assets.ladder import clip_words
    out: list[dict[str, Any]] = []
    for o in raw if isinstance(raw, list) else []:
        if not isinstance(o, dict) or o.get("kind") not in OVERLAY_KINDS:
            continue
        kind = o["kind"]
        if kind == "expand":                 # 자리가 없는 전환 표시 — 짝과 횟수는 렌더러(crop.ts expandPairs)가 최종 타임라인에서 가른다
            out.append({"kind": "expand"})
            continue
        text = clip_words(o.get("text"), OVERLAY_TEXT.get(kind, 14))
        if kind == "dimension" and not any(c.isdigit() for c in text):      # 치수선은 실제 숫자에만
            continue
        box = _unit(o.get("box"), 4)
        box = box if box and box[2] > 0.005 and box[3] > 0.005 else []
        point = _unit(o.get("point"), 2)
        poly = [p for p in (_unit(q, 2) for q in (o.get("poly") if isinstance(o.get("poly"), list) else [])) if p]
        if kind == "dimension":              # 두 끝점. 비전이 상자만 줬으면 긴 변을 따라
            poly = [poly[0], poly[-1]] if len(poly) >= 2 else []
            if not poly and box:
                x, y, w, h = box
                poly = [[x, round(y + h, 4)], [round(x + w, 4), round(y + h, 4)]] if w >= h else [[round(x + w, 4), y], [round(x + w, 4), round(y + h, 4)]]
        elif len(poly) < 3:
            poly = []
        if poly and not box:
            xs, ys = [p[0] for p in poly], [p[1] for p in poly]
            box = [min(xs), min(ys), round(max(xs) - min(xs), 4), round(max(ys) - min(ys), 4)]
        if kind == "outline" and box and len(poly) < OUTLINE_MIN:
            kind, poly = "circle", []
        located = poly if kind == "dimension" else box if kind in ("outline", "focus", "highlight") else (box or point)
        if kind == "cutout" and not o.get("image"):
            located = []
        if not located and kind not in OVERLAY_FREE:
            if not text:
                continue
            kind, box, point, poly = "label", [], [], []
        if kind in ("label", "memo", "stamp") and not text:
            continue
        item: dict[str, Any] = {"kind": kind}
        item.update({k: v for k, v in (("box", box), ("point", point), ("poly", poly), ("text", text)) if v})
        if kind == "cutout":
            item.update(image=str(o["image"]), cut=bool(o.get("cut")))
            item.update({k: o[k] for k in ("w", "h") if o.get(k)})
        word = str(o.get("at_word") or "").strip()[:24]
        if word:
            item["at_word"] = word
        out.append(item)
    return _within_budget([o for o in out if o["kind"] != "expand"]) + [o for o in out if o["kind"] == "expand"][:1]


def land_overlays(g: dict[str, Any], utts: list[Utterance], timemap: TimeMap, start: float, dur: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """표시의 at_word → 그 낱말 0.2초 전에 내려앉는 at(그래픽 시작 기준 초). 낱말을 못 찾은 표시는 앞 표시 뒤 1초, 그래픽 끝 0.6초 안에는
    놓지 않는다. 반환: (표시, 게이트 A18 의 wordMarks)."""
    items = [dict(o) for o in g["overlays"] if o["kind"] != "expand"]
    steps = [{"word": str(o.get("at_word") or ""), "highlight": i} for i, o in enumerate(items)]
    spoken = {s["index"]: s["t"] for s in step_times({**g, "steps": steps}, utts, timemap, start, min_steps=1)}
    out, marks = [], []
    prev = -0.4
    for i, o in enumerate(items):
        o.pop("at_word", None)
        at = max(0.0, spoken[i] - 0.2 - OVERLAY_SETTLE) if i in spoken else prev + 1.0
        if at > dur - 0.6:
            continue
        o["at"] = prev = round(at, 3)
        out.append(o)
        if i in spoken:
            marks.append({"land": round(at + OVERLAY_SETTLE, 3), "spoken": round(start + spoken[i], 3)})
    return out + [o for o in g["overlays"] if o["kind"] == "expand"], marks


def land_cutouts(g: dict[str, Any], utts: list[Utterance], timemap: TimeMap, start: float, dur: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """오림 스택: 그림마다 자기 사례를 말한 낱말에 내려앉는다(at = 그래픽 시작 기준 초). 못 찾은 그림은 at 없이 — 렌더러가 고르게 놓는다.
    그래픽 끝 0.6초 안이나 끝 뒤에 닿는 그림은 놓일 틈이 없어 뺀다."""
    steps = [{"word": c.get("word", ""), "highlight": i, "seg": c.get("seg")} for i, c in enumerate(g["cutouts"])]
    spoken = {s["index"]: s["t"] for s in step_times({**g, "steps": steps}, utts, timemap, start, min_steps=1)}
    items, marks = [], []
    for i, c in enumerate(g["cutouts"]):
        item = {k: v for k, v in c.items() if k not in ("seg", "word")}
        if i in spoken:
            item["at"] = round(max(0.0, spoken[i] - 0.2 - OVERLAY_SETTLE), 3)
            if item["at"] > max(0.0, dur - 0.6):
                continue
            marks.append({"land": round(item["at"] + OVERLAY_SETTLE, 3), "spoken": round(start + spoken[i], 3)})
        items.append(item)
    return items, marks


def credit_line(pieces: list[dict[str, Any]]) -> str:
    """조각들의 화면 출처 한 줄(CREDIT_MAX 자): 통째로 들어가는 출처만 — 이름 가운데서 자르지 않는다(전문은 설명란의 credit_full)."""
    from ..assets.ladder import clip_words
    line = ""
    for c in dict.fromkeys(p["credit"] for p in pieces if p.get("credit")):
        if line and len(line) + 3 + len(c) > CREDIT_MAX:
            break
        line = f"{line} · {c}" if line else c
    return clip_words(line, CREDIT_MAX)


def land_marks(tg: "TimedGraphic", g: dict[str, Any], utts: list[Utterance], timemap: TimeMap) -> None:
    """표시·오림의 at_word 를 tg 의 지금 시작·길이로 잰다 — 그래픽이 옮겨질 때마다 다시."""
    if not (g.get("overlays") or g["template"] in PIECE_TEMPLATES):
        return
    key = "cutouts" if g["template"] in PIECE_TEMPLATES else "overlays"
    tg.data[key], word_marks = (land_cutouts if key == "cutouts" else land_overlays)(g, utts, timemap, tg.start, tg.end - tg.start)
    if key == "cutouts":
        tg.data["credit"] = credit_line(tg.data[key]) or tg.data.get("credit", "")     # 뺀 그림의 출처를 남기지 않는다
    if word_marks:
        tg.data["wordMarks"] = word_marks
    else:
        tg.data.pop("wordMarks", None)


def blank_graphic(template: str, seg: int) -> dict[str, Any]:
    t = TEMPLATES.get(template)
    return {"template": template, "layout": t.layouts[0] if t else "fullscreen", "start_seg": seg,
            "end_seg": seg, "start_word": "", "title": "", "subtitle": "", "body": "", "items": [],
            "title_b": "", "items_b": [], "highlight": -1, "author": "", "source": "", "image": "",
            "reason": ""}


def type_card(g: dict, description: str = "") -> Optional[dict]:
    """자료를 못 구한 사진·스톡 → 타이포 자료 카드(이름 + 한 줄) — 사다리의 마지막 칸(docs/upgrade/03 P0-4). 화면 글자로 쓸
    이름(사진: 이름, 스톡: 리서처의 caption)이 없으면 None(그 자리는 비우고 로그만)."""
    title = strip_label(str(g.get("title") or ""))
    if not title:
        return None
    card = copy.deepcopy(g)
    card["template"] = "keyword"
    card["layout"] = {"pip": "overlay"}.get(g.get("layout", ""), g.get("layout") or "overlay")
    if card["layout"] not in TEMPLATES["keyword"].layouts:
        card["layout"] = "overlay"
    card["title"] = title[:14]
    card["subtitle"] = str(description or g.get("body") or "")[:28] if g.get("template") == "photo" else ""
    card["body"] = ""
    card["fallback"] = "type_card"
    for k in ("stock", "image", "wiki", "src", "credit", "logo", "mat", "kenburns", "stock_url", "kind"):
        card.pop(k, None)
    card["image"] = ""
    return card


SEQ_TYPES = ("evidence_stack", "detail_zoom", "document_read", "walkthrough", "comparison", "montage")
STEP_TEMPLATES = ("process", "cycle", "double_diamond", "timeline", "pyramid", "list", "matrix", "venn")


def _clean_steps(steps: Any, n_items: int, valid: list[int]) -> list[dict[str, Any]]:
    """단계 그래픽의 steps: [{word, highlight(, seg)}] — 낱말에서 강조 단계가 바뀐다(docs/upgrade/05 6-1). 단계가 2개 미만이면 [].
    seg 는 내부용(자동으로 합친 단계 — 그 단계가 시작하는 발화)."""
    out: list[dict[str, Any]] = []
    for st in steps if isinstance(steps, list) else []:
        if not isinstance(st, dict):
            continue
        try:
            h = int(st.get("highlight", -1))
        except (TypeError, ValueError):
            continue
        if not 0 <= h < max(1, n_items):
            continue
        item: dict[str, Any] = {"word": str(st.get("word") or "").strip()[:24], "highlight": h}
        if st.get("seg") is not None and st.get("seg") in valid:
            item["seg"] = st["seg"]
        if item["word"] or "seg" in item:
            out.append(item)
    return out[:8] if len(out) >= 2 else []


def merge_step_runs(graphics: list[dict[str, Any]]) -> int:
    """같은 도식(템플릿·제목·항목이 같음)을 강조만 바꿔 잇달아 낸 그래픽들을 하나로 합치고 steps 로 — 단계마다 그래픽이
    새로 들어오면 강조가 말보다 4~6초 늦다(10/1: 더블 다이아몬드 셋, '정의' 강조 +3.9초 · '아이디어' +5.7초).
    다음 그래픽이 앞 그래픽 끝에서 2발화 안에 시작할 때만. 반환: 합친 그래픽 수."""
    merged = 0
    order = sorted(range(len(graphics)), key=lambda i: graphics[i].get("start_seg", 0))
    drop: set[int] = set()
    k = 0
    while k < len(order):
        i = order[k]
        g = graphics[i]
        run = [i]
        if g.get("template") in STEP_TEMPLATES and not g.get("steps"):
            j = k + 1
            while j < len(order):
                h = graphics[order[j]]
                prev = graphics[run[-1]]
                same = (h.get("template") == g.get("template") and h.get("items") == g.get("items")
                        and (h.get("title") or "") == (g.get("title") or "") and not h.get("steps"))
                if not same or h.get("start_seg", 0) - prev.get("end_seg", prev.get("start_seg", 0)) > 2:
                    break
                run.append(order[j])
                j += 1
        if len(run) >= 2 and len({graphics[x].get("highlight", -1) for x in run}) >= 2:
            steps = [{"word": graphics[x].get("start_word") or "", "highlight": graphics[x].get("highlight", -1),
                      "seg": graphics[x].get("start_seg")} for x in run if graphics[x].get("highlight", -1) >= 0]
            if len(steps) >= 2:
                g["steps"] = steps
                g["highlight"] = steps[0]["highlight"]
                g["end_seg"] = max(graphics[x].get("end_seg", graphics[x].get("start_seg", 0)) for x in run)
                g["reason"] = (g.get("reason") or "") + f" · 단계 {len(steps)}개를 한 그래픽으로(낱말에서 강조)"
                drop.update(run[1:])
                merged += len(run) - 1
            k += len(run)
            continue
        k += 1
    if drop:
        graphics[:] = [g for n, g in enumerate(graphics) if n not in drop]
    return merged


def step_times(g: dict[str, Any], utts: list[Utterance], timemap: TimeMap, start: float,
               min_steps: int = 2) -> list[dict[str, Any]]:
    """steps → [{t(그래픽 시작 기준 초), index}] — 그 낱말을 말하는 순간(앞 단계 낱말보다 뒤, 그래픽 발화 범위 안).
    낱말을 못 찾으면 그 단계 발화(seg)의 시작. 2개 미만이면 []. 그래픽이 낱말 뒤로 밀렸으면 t 는 음수다(게이트 A18 이 그 차이를 잰다)."""
    by_id = {u.id: u for u in utts}
    lo, hi = g.get("start_seg", 0), g.get("end_seg", g.get("start_seg", 0))
    span = [u for u in sorted(utts, key=lambda u: u.start) if lo <= u.id <= hi and u.kept and u.words]
    out: list[dict[str, Any]] = []
    last_src = -1e9
    for st in g.get("steps") or []:
        hit: Optional[float] = None          # 원본 시각
        cands = [by_id[st["seg"]]] if st.get("seg") in by_id else span
        for u in cands:
            if st.get("word"):
                w = find_word([x for x in u.words if x.start >= last_src - 1e-6], st["word"])
                if w is not None:
                    hit = w.start
            if hit is None and st.get("seg") == u.id and u.words:
                hit = max(u.words[0].start, last_src)
            if hit is not None:
                break
        if hit is None:
            continue
        t = timemap.src_to_edit(hit, snap=True)
        if t is None:
            continue
        last_src = hit
        out.append({"t": round(t - start, 3), "index": int(st["highlight"])})
    # 시각이 거꾸로 가면(편집 순서가 바뀐 숏폼 등) 그 단계는 뺀다
    mono: list[dict[str, Any]] = []
    for x in out:
        if not mono or x["t"] >= mono[-1]["t"]:     # 같은 시각은 거꾸로가 아니다(글자와 밑줄이 같은 낱말에 착지)
            mono.append(x)
    return mono if len(mono) >= min_steps else []


AT_WORD_TAG_RE = re.compile(r'<[^>]*\sdata-at-word="[^"]*"[^>]*>')


def land_on_words(g: dict[str, Any], utts: list[Utterance], timemap: TimeMap, start: float) -> tuple[dict[str, Any], float]:
    """카드의 data-at-word="낱말"(문서 순서 = 말하는 순서) → 그 낱말 0.2초 전에 도착하는 data-anim-at. 낱말을 못 찾은 표시는
    디자이너가 쓴 data-anim-at 그대로. (시각을 넣은 카드 사본, 마지막 표시 시각)."""
    tags = AT_WORD_TAG_RE.findall(g["card"]["html"])
    if not tags:
        return g["card"], 0.0
    steps = [{"word": re.search(r'data-at-word="([^"]*)"', t).group(1), "highlight": i} for i, t in enumerate(tags)]
    spoken = {s["index"]: s["t"] for s in step_times({**g, "steps": steps}, utts, timemap, start, min_steps=1)}
    durs = [re.search(r'data-anim-duration="([\d.]+)"', t) for t in tags]
    dur_of = [float(m.group(1)) if m else 0.5 for m in durs]       # card-anim.mjs 기본 0.5초 — data-anim-at 은 시작 시각이다
    at = {i: max(0.0, t - 0.2 - dur_of[i]) for i, t in spoken.items()}
    seen = iter(range(len(tags)))

    def stamp(m: re.Match) -> str:
        i = next(seen)
        tag = re.sub(r'\sdata-at-word="[^"]*"', "", m.group(0))
        if i not in at:
            return tag
        tag = re.sub(r'\sdata-anim-at="[^"]*"', "", tag)
        return re.sub(r"\s*/?>$", lambda e: f' data-anim-at="{at[i]:.2f}"{e.group(0)}', tag)

    # 게이트 A18: 낱말을 찾은 표시의 착지(시작 + 애니메이션 길이)와 그 낱말의 편집 시각
    marks = [{"land": round(a + dur_of[i], 3), "spoken": round(start + spoken[i], 3)} for i, a in at.items()]
    return {**g["card"], "html": AT_WORD_TAG_RE.sub(stamp, g["card"]["html"]), "wordMarks": marks}, max(at.values(), default=0.0)


def land_scene_on_words(spec: dict[str, Any], g: dict[str, Any], utts: list[Utterance], timemap: TimeMap, start: float,
                        log: Callable[[str], None]) -> float:
    """모션 요소의 at_word(at 순서 = 말하는 순서) → 그 낱말 0.2초 전에 다 도착하도록 at 을 옮긴다. 퇴장·키프레임도 같이 민다.
    못 찾은 요소는 디자이너의 at 그대로. spec 은 clean_spec 사본이라 제자리에서 고친다. 반환: 마지막 낱말 시각."""
    marked = sorted((e for e in spec["elements"] if "at_word" in e), key=lambda e: e["at"])
    if not marked:
        return 0.0
    words = [e.pop("at_word") for e in marked]
    spoken = {s["index"]: s["t"] for s in step_times({**g, "steps": [{"word": w, "highlight": i} for i, w in enumerate(words)]},
                                                     utts, timemap, start, min_steps=1)}
    for i, e in enumerate(marked):
        if i not in spoken:
            log(f"🎯 모션 장면 S{g.get('start_seg')}: 낱말 '{words[i]}' 을 말에서 찾지 못해 at {e['at']:.1f}초 그대로")
            continue
        shift = max(-e["at"], spoken[i] - 0.2 - settle_of(e))
        e["at"] += shift
        if "out" in e:
            e["out"] += shift
        if "groupAt" in e:
            e["groupAt"] += shift
        for k in e.get("keys", []):
            k["t"] += shift
    spec["wordMarks"] = [{"land": round(settle_of(marked[i]), 3), "spoken": round(start + t, 3)}
                         for i, t in spoken.items()]    # 게이트 A18
    return max(spoken.values(), default=0.0)


def _split_items(s: str) -> list[str]:
    return [x.strip() for x in re.split(r"[;；\n]|,(?!\d)", s or "") if x.strip()]


def _find_index(items: list[str], name: str) -> int:
    if not name:
        return -1
    if name.strip().lstrip("-").isdigit():
        i = int(name.strip())
        return i if -1 <= i < len(items) else -1
    n = norm(name)
    for i, it in enumerate(items):
        if n and (n in norm(it) or norm(it) in n):
            return i
    return -1


def graphic_from_tag(tag: Tag, seg: int) -> Optional[dict[str, Any]]:
    """대본 태그 → 그래픽 명세(디렉터 JSON 과 같은 모양)."""
    a = tag.args + [""] * 4
    kind = tag.kind
    if kind == "diagram":
        name = a[0].strip()
        key = name.replace(" ", "").lower()
        preset = None
        for pk, pv in PRESET_DIAGRAMS.items():
            if pk.replace(" ", "").lower() in key or key in pk.replace(" ", "").lower():
                preset = pv
                break
        template = (preset or {}).get("template") or DIAGRAM_ALIASES.get(key) or DIAGRAM_ALIASES.get(name)
        if not template:
            template = "process"
        g = blank_graphic(template, seg)
        g["title"] = (preset or {}).get("title", name)
        items = list((preset or {}).get("items", []))
        if len(a[1].split(";")) > 1:  # [도식: 이름 | 항목;항목 | 강조]
            items = _split_items(a[1])
            g["highlight"] = _find_index(items, a[2])
        else:
            g["highlight"] = _find_index(items, a[1])
        g["items"] = items
        g["reason"] = "대본 태그"
        return g
    template = TAG_TO_TEMPLATE.get(kind)
    if not template:
        return None
    g = blank_graphic(template, seg)
    g["reason"] = "대본 태그"
    if template == "chapter":
        g["title"] = a[0]
        g["subtitle"] = a[1]
    elif template == "keyword":
        g["title"], g["subtitle"] = a[0], a[1]
    elif template == "definition":
        g["title"], g["subtitle"], g["body"] = a[0], a[1], a[2]
    elif template == "quote":
        g["body"], g["author"], g["source"] = a[0], a[1], a[2]
    elif template == "photo":
        g["image"], g["title"], g["body"] = a[0], a[0], a[1]
        if a[2] in TEMPLATES["photo"].layouts:
            g["layout"] = a[2]
    elif template == "list":
        g["title"], g["items"] = a[0], _split_items(a[1])
    elif template in ("process", "cycle", "pyramid"):
        g["title"], g["items"] = a[0], _split_items(a[1])
        g["highlight"] = _find_index(g["items"], a[2])
    elif template == "matrix":
        g["title"], g["items"], g["items_b"] = a[0], _split_items(a[1]), _split_items(a[2])
        g["highlight"] = _find_index(g["items"], a[3])
    elif template == "compare":
        def side(s: str) -> tuple[str, list[str]]:
            head, _, rest = s.partition(":")
            if not rest:
                head, _, rest = s.partition("：")
            return head.strip(), _split_items(rest)
        g["title"], g["items"] = side(a[0])
        g["title_b"], g["items_b"] = side(a[1])
        g["subtitle"] = a[2]
    elif template == "timeline":
        g["title"] = a[0]
        items = []
        for it in _split_items(a[1]):
            m = re.match(r"^\s*(\d{2,4}(?:년|s)?)\s*[:：\-–]?\s*(.+)$", it)
            items.append(f"{m.group(1)}|{m.group(2)}" if m else it)
        g["items"] = items
    elif template == "stat":
        g["title"], g["body"], g["subtitle"] = a[0], a[1], a[2]
    elif template == "venn":
        g["title"], g["items"], g["body"] = a[0], _split_items(a[1]), a[2]
    return g


# ----------------------------------------------------------------------------
# 1) 디렉터 JSON 정리 (발화 ID 기준)
# ----------------------------------------------------------------------------

def _clean_graphic(g: dict[str, Any], valid: list[int]) -> Optional[dict[str, Any]]:
    if not isinstance(g, dict) or g.get("template") not in TEMPLATES:
        return None
    out = blank_graphic(g["template"], 0)
    for k in GRAPHIC_KEYS:
        if k in g and g[k] is not None:
            out[k] = g[k]
    t = TEMPLATES[out["template"]]
    if out["layout"] not in t.layouts:
        out["layout"] = t.layouts[0]
    out["start_seg"] = _nearest(valid, out["start_seg"])
    out["end_seg"] = _nearest(valid, out.get("end_seg", out["start_seg"]))
    if out["end_seg"] < out["start_seg"]:
        out["end_seg"] = out["start_seg"]
    if str(out.get("source") or "").strip().lower() in ("gate", "auto", "director", "tag"):
        out["source"] = ""          # 출처 칸(화면에 '( … )'로 나감)에 들어간 내부 표시 — 2026-10-04 보충 카드에 '( gate )'
    out["items"] = [str(x).strip() for x in out.get("items") or [] if str(x).strip()][:8]
    out["items_b"] = [str(x).strip() for x in out.get("items_b") or [] if str(x).strip()][:8]
    try:
        out["highlight"] = int(out.get("highlight", -1))
    except (TypeError, ValueError):
        out["highlight"] = -1
    steps = _clean_steps(g.get("steps"), len(out["items"]) or 8, valid)
    if steps:
        out["steps"] = steps
    sid = str(g.get("sequence_id") or "").strip()[:16]
    if sid:
        out["sequence_id"] = sid
    # 템플릿별 최소 요건
    tn = out["template"]
    if tn in ("keyword", "chapter", "stat", "lower_third") and not out["title"].strip():
        return None
    if tn in PIECE_TEMPLATES:
        cuts = [{k: c[k] for k in CUTOUT_KEYS if k in c} for c in g.get("cutouts") or [] if isinstance(c, dict) and c.get("image")][:4 if tn == "cutout_stack" else 5]
        if not cuts or (tn != "cutout_stack" and len(cuts) < 2):
            return None      # 앱이 채우는 템플릿 — 그림 없이 고른 것은 빈 층만 남는다
        out["cutouts"] = cuts
        for k in ("name", "name_sub", "disc"):
            if g.get(k):
                out[k] = str(g[k])[:40]
        if g.get("credit"):
            out["credit"] = str(g["credit"])[:120]
    if tn == "quote" and not out["body"].strip():
        return None
    if tn == "photo" and not out["image"].strip():
        return None
    if tn in ("list", "process", "cycle", "pyramid", "timeline") and len(out["items"]) < 2:
        return None
    if tn == "compare" and (not out["title"] or not out["title_b"]):
        return None
    if tn == "matrix" and len(out["items"]) < 4:
        return None
    if tn == "double_diamond" and len(out["items"]) != 4:
        out["items"] = ["발견", "정의", "개발", "전달"]
    if tn == "venn" and len(out["items"]) < 2:
        return None
    if tn == "motion":
        # 🎨 모션 디자이너가 설계한 MotionSpec(장면 길이에 맞춘 최종 정리는 time_graphics 에서)
        spec = g.get("spec")
        if not isinstance(spec, dict) or not clean_spec(spec, 16.0):
            return None
        out["spec"] = spec
    if tn == "card":
        # 🃏 자유 HTML 카드 — 재정규화 때도 다시 정리한다(스코프·금지 항목은 멱등)
        card = clean_card(g.get("card"), layout=out["layout"])
        if not card:
            return None
        out["card"] = card
        if g.get("why_not_evidence"):
            out["why_not_evidence"] = str(g["why_not_evidence"])[:200]
        if g.get("signature"):
            out["signature"] = True     # 🛠 시그니처 장면(트리트먼트) — 겹치면 이긴다
    if g.get("sfx") in SFX_DIRECTED:
        out["sfx"] = g["sfx"]           # 총괄 감독이 고른 효과음(트리트먼트) — 그 그래픽이 들어올 때
    if tn == "broll":
        # 🎞 스톡 요청 — 단일 디렉터 모드에서는 image=영어 검색어, subtitle=video|photo, title=한국어 검색어
        st = g.get("stock") if isinstance(g.get("stock"), dict) else {}
        kind = st.get("kind") or (out["subtitle"] if out["subtitle"] in ("video", "photo") else "video")
        stock = {"kind": kind if kind in ("video", "photo") else "video",
                 "query_en": str(st.get("query_en") or out["image"]).strip(),
                 "query_ko": str(st.get("query_ko") or out["title"]).strip(),
                 "purpose": str(st.get("purpose") or out["body"]).strip(),
                 "must_show": str(st.get("must_show") or "").strip()}
        if not (stock["query_en"] or stock["query_ko"]):
            return None
        out["stock"] = stock
        # 단일 디렉터·숏폼 PD 의 broll 은 title=한국어 검색어, subtitle=video|photo, body=연출 메모 — 검색어로 옮겼으니
        # 화면에서는 지운다(게이트 B3·B4·B5). 자료 리서처의 caption(주장)은 남는다
        if out["title"] and (out["title"] == stock["query_ko"] or out["title"] == stock["query_en"]):
            out["title"] = ""
        if out["subtitle"] in ("video", "photo"):
            out["subtitle"] = ""
        if out["body"] and out["body"] == stock["purpose"]:
            out["body"] = ""
        for k in ("src", "kind", "credit", "kenburns", "stock_url", "cut", "w", "h", "treatment", "focus"):
            if g.get(k):
                out[k] = g[k]
        if out.get("treatment") not in (None, "collage"):
            out.pop("treatment")
    if tn in ("broll", "evidence"):
        _keep_collage_text(g, out)
    if tn in ("photo", "broll", "evidence"):
        overlays = clean_overlays(g.get("overlays"))
        if overlays:
            out["overlays"] = overlays
        if g.get("tone") in TONES:
            out["tone"] = g["tone"]
    if tn == "photo" and g.get("credit"):
        out["credit"] = g["credit"]
    if tn == "photo" and g.get("wiki"):
        out["wiki"] = True   # 위키백과 전용(고유명사): 못 찾으면 스톡으로 넘기지 않고 뺀다
    if tn == "photo":
        # 고유명사의 종류(자료 리서처가 문맥으로 정함: person → 품위 있는 초상, brand → 로고)와 영어 이름(로고 찾기)
        for k in ("entity", "name_en", "tier"):
            if g.get(k):
                out[k] = str(g[k])[:80]
        if g.get("logo"):
            out["logo"] = True
        if g.get("mat"):
            out["mat"] = True        # 세로 사진을 크림 종이 여백 액자에 넣은 것(로고 카드처럼 그린다)
    if tn in ("photo", "broll", "evidence", "keyword", *PIECE_TEMPLATES) and isinstance(g.get("evidence"), dict):
        out["evidence"] = {k: v for k, v in g["evidence"].items() if isinstance(k, str)}   # 리서처의 원 요청(화면에 안 나감)
    if tn == "photo" and g.get("resolved"):
        out["resolved"] = True       # 조달 사다리가 이미 파일로 바꾼 것(image = public 기준 경로)
    if tn == "keyword" and g.get("fallback"):
        out["fallback"] = str(g["fallback"])[:16]
    if tn == "evidence":
        assets = [{k: a[k] for k in EVIDENCE_ASSET_KEYS if k in a} for a in g.get("assets") or []
                  if isinstance(a, dict) and a.get("src")][:5]
        archive = g.get("archive") if isinstance(g.get("archive"), dict) else None
        if not assets and not archive:
            return None      # 조달 전·실패한 증거는 계획에 남기지 않는다(사다리가 이미 자료 카드·code_drawn 으로 바꿨다)
        out["assets"] = assets
        if archive:
            out["archive"] = {"variant": str(archive.get("variant") or "source"),
                              "title": str(archive.get("title") or "")[:90],
                              "rows": [{"k": str(r.get("k", ""))[:8], "v": str(r.get("v", ""))[:60]}
                                       for r in archive.get("rows") or [] if isinstance(r, dict)][:4],
                              "label": str(archive.get("label") or "")[:14], "quote": str(archive.get("quote") or "")[:60],
                              "ref": str(archive.get("ref") or "")[:200]}
        tr = str(g.get("treatment") or "hero")
        out["treatment"] = tr if tr in EVIDENCE_HOLD else "hero"
        for k in ("tier", "caption", "credit"):
            if g.get(k):
                out[k] = str(g[k])[:120]
    return out


def _keep_collage_text(g: dict[str, Any], out: dict[str, Any]) -> None:
    """디자인 v3 콜라주의 화면 글: 큰 연도(숫자 4자리), 사진 뒤 큰 글자(8자), 영상 위 인용 한 줄(36자)."""
    y = re.search(r"(1[0-9]{3}|20[0-9]{2})", str(g.get("year") or ""))
    if y:
        out["year"] = y.group(1)
    for k, n in (("display", 8), ("quote", 36)):
        v = str(g.get(k) or "").strip()
        if v:
            out[k] = v[:n]


def _nearest(valid: list[int], seg: Any) -> int:
    try:
        seg = int(seg)
    except (TypeError, ValueError):
        return valid[0]
    if seg in valid:
        return seg
    return min(valid, key=lambda v: (abs(v - seg), v))


def fit_highlight_runs(runs: list[list[int]], kept: list[Utterance], dur_of: Callable[[list[int]], float], *,
                       lo: float, hi: float, piece_max: float, max_gap: float = 2.5) -> tuple[list[list[int]], int]:
    """🎬 오프닝 하이라이트 조각(이어지는 발화 id 묶음, 시간순)을 합 [lo, hi] 초에 맞춘다. dur_of(run) = 그 조각을 실제로 자른
    길이(자를 수 없으면 음수). 상한을 넘기는 조각은 빼고, 합이 lo 보다 짧으면 가장 짧은 조각부터 바로 뒤 발화(같은 흐름 —
    max_gap 초 안, 다른 조각이 아님, 조각의 원본 구간 piece_max 이하)를 하나씩 붙인다 — 그 생각의 근거·끝맺음까지 듣게
    (2026-10-04 채널 주인: "10초대라 너무 압축돼 알맹이 없이 잘린다 — 20~30초"). 반환: (쓸 조각, 붙인 발화 수)."""
    pos = {u.id: i for i, u in enumerate(kept)}

    def assemble(rs: list[list[int]]) -> tuple[list[list[int]], float]:
        used, total = [], 0.0
        for run in rs:
            d = dur_of(run)
            if d <= 0 or total + d > hi:
                continue
            used.append(run)
            total += d
        return used, total

    used, total = assemble(runs)
    grown = 0
    while total < lo:
        taken = {sid for r in used for sid in r}
        best = None
        for i, run in sorted(enumerate(used), key=lambda x: dur_of(x[1])):
            j = pos[run[-1]] + 1
            if j >= len(kept) or kept[j].id in taken:
                continue
            nxt, first, last = kept[j], kept[pos[run[0]]], kept[pos[run[-1]]]
            if nxt.start - last.end > max_gap or nxt.end - first.start > piece_max:
                continue
            t_used, t_total = assemble([r + [nxt.id] if k == i else r for k, r in enumerate(used)])
            if len(t_used) == len(used) and total < t_total <= hi:
                best = (t_used, t_total)
                break
        if best is None:
            break
        used, total = best
        grown += 1
    return used, grown


def clean_sound_gags(raw: Any, kept: list[int]) -> list[dict[str, Any]]:
    """감독의 위트 소리 — 어긋남(why)이 없거나 영어 설명이 없으면 뺀다. silence_beat 만 소리 없이."""
    out: list[dict[str, Any]] = []
    for g in (raw if isinstance(raw, list) else [])[:8]:
        if not isinstance(g, dict) or g.get("seg") not in kept or g.get("type") not in SOUND_GAG_TYPES or not str(g.get("why") or "").strip():
            continue
        idea = "" if g["type"] == "silence_beat" else str(g.get("sound_idea") or "").strip()[:120]
        if (not idea and g["type"] != "silence_beat") or not idea.isascii():
            continue
        try:
            pre = round(min(max(float(g.get("pre_silence_s") or 0.0), 0.0), 1.0), 2)
        except (TypeError, ValueError):
            pre = 0.0
        out.append({"seg": g["seg"], "anchor": g.get("anchor") if g.get("anchor") in ("word", "after_seg", "graphic_landing") else "after_seg",
                    "anchor_word": str(g.get("anchor_word") or "")[:30], "type": g["type"], "sound_idea": idea, "pre_silence_s": pre,
                    "queries": [str(q).strip()[:40] for q in g.get("queries") or [] if str(q).strip().isascii() and str(q).strip()][:3],
                    "why": str(g["why"]).strip()[:80]})
    return out[:4]


def normalize_long(raw: dict[str, Any], utts: list[Utterance], tags: list[Tag]) -> dict[str, Any]:
    kept = [u.id for u in utts if u.kept]
    if not kept:
        raise ValueError("남은 발화가 없습니다")
    from ..sound.cues import clean_music
    plan: dict[str, Any] = {
        "summary": str(raw.get("summary", "")),
        "hook_segs": [s for s in raw.get("hook_segs", []) if s in kept],
        "title_card_seg": raw.get("title_card_seg", -1) if raw.get("title_card_seg", -1) in kept else -1,
        "chapters": [],
        "graphics": [],
        "emphasis": [],
        "drop": [],
        "youtube": raw.get("youtube") or {},
        "music": raw.get("music") or {},
        # 🎼 음악 감독의 큐 시트(손으로 고친 것이 있으면 그것이 이긴다 — 없으면 work/music.json)
        "music_cues": clean_music(raw.get("music_cues"), kept),
        "captions": raw.get("captions") or {},   # 🔤 자막 디자이너의 프리셋 선택
        "studio": raw.get("studio") or {},       # 🎬 스튜디오 메모(리포트용)
        "moments": [],                           # ✂️ 강조 순간(편집 문법 엔진 입력)
        "highlights": [],                        # 🎬 오프닝 하이라이트(본편 앞 콜드 오픈) 발화들
        "argument_tags": [],                     # 논증 배지(좌상단 띠, 90~150초마다)
        "holds": [],                             # 🙂 얼굴 홀드(그래픽·보드·콜아웃·효과음 없이 얼굴만 — 고백·결론·질문 뒤)
        "pauses": [],                            # 🫁 발화 뒤 쉼(초) — 호흡 설계(studio/edit/breath.py)가 원본 무음으로 채운다
        "silences": [],                          # 🤫 전환·정점 앞 진짜 침묵(총괄 감독) — 쉼 + 그 사이 음악·효과음 없음
        "sound_gags": [],                        # 🔊 위트 소리(총괄 감독) — 앱이 찾아 받아 화면 사건에 맞춘다(studio/sound/fetch.py)
        "sequences": [],                         # 시퀀스(한 주장을 받치는 연속 화면 묶음) — docs/upgrade/05 2·6장
        "rhythm": [],                            # 리듬 수준(slow · steady · fast) 발화 구간
        "peak_seg": raw.get("peak_seg", -1) if raw.get("peak_seg", -1) in kept else -1,
        "central_question": str(raw.get("central_question", "") or "")[:80],
        "payoff_seg": raw.get("payoff_seg", -1) if raw.get("payoff_seg", -1) in kept else -1,
        "title": strip_label(str(raw.get("title", "") or "")),       # 🎬 화면 타이틀('제목:' 라벨은 뗀다)
        "bgm_mood": str(raw.get("bgm_mood", "") or ""),
        "shorts_bgm_mood": str(raw.get("shorts_bgm_mood", "") or ""),
    }
    for c in raw.get("chapters", []) or []:
        if isinstance(c, dict) and str(c.get("title", "")).strip():
            item = {"seg": _nearest(kept, c.get("seg")), "title": strip_label(str(c["title"]))}
            if str(c.get("claim", "") or "").strip():
                item["claim"] = str(c["claim"]).strip()[:40]     # 챕터의 주장 한 문장(챕터 카드 부제)
            plan["chapters"].append(item)
    for g in raw.get("graphics", []) or []:
        cg = _clean_graphic(g, kept)
        if cg:
            if cg["template"] == "chapter":
                plan["chapters"].append({"seg": cg["start_seg"], "title": cg["title"]})
            else:
                plan["graphics"].append(cg)
    merge_step_runs(plan["graphics"])
    cap_cards(plan["graphics"], sum(u.end - u.start for u in utts if u.kept))
    for e in raw.get("emphasis", []) or []:
        if isinstance(e, dict) and e.get("seg") in kept and e.get("kind") in ("punch", "highlight"):
            item = {"seg": e["seg"], "word": str(e.get("word", "")), "kind": e["kind"]}
            if e.get("type") in EM_TYPES:
                item["type"] = e["type"]
            plan["emphasis"].append(item)
    for d in raw.get("drop", []) or []:
        if isinstance(d, dict) and d.get("seg") in kept:
            plan["drop"].append({"seg": d["seg"], "reason": str(d.get("reason", ""))})
    for m in raw.get("moments", []) or []:
        if isinstance(m, dict) and m.get("seg") in kept and m.get("kind") in MOMENT_KINDS:
            try:
                inten = max(1, min(3, int(m.get("intensity", 2))))
            except (TypeError, ValueError):
                inten = 2
            item = {"seg": m["seg"], "word": str(m.get("word", "")), "kind": m["kind"], "intensity": inten,
                    "callout": str(m.get("callout", "") or "").strip()[:40],
                    "label": str(m.get("label", "") or "").strip()[:16]}
            if not any(x["seg"] == item["seg"] and x["kind"] == item["kind"] for x in plan["moments"]):
                plan["moments"].append(item)
    # 논증 배지: 총괄 감독이 비트에 붙인 태그('이유 1'). studio 메모의 beats 에서 다시 뽑으므로 재정규화해도 그대로
    for b in (raw.get("studio") or {}).get("beats") or []:
        tag = str(b.get("argument_tag") or "").strip()[:18] if isinstance(b, dict) else ""
        if tag:
            plan["argument_tags"].append({"seg": _nearest(kept, b.get("start_seg")), "tag": tag})
    for h in (raw.get("holds", []) or [])[:10]:
        if not isinstance(h, dict):
            continue
        a, b = _nearest(kept, h.get("start_seg")), _nearest(kept, h.get("end_seg", h.get("start_seg")))
        if a is None or b is None:
            continue
        if b < a:
            a, b = b, a
        if not any(x["start_seg"] <= b and a <= x["end_seg"] for x in plan["holds"]):
            plan["holds"].append({"start_seg": a, "end_seg": b, "reason": str(h.get("reason", "") or "")[:60]})
    from ..edit.breath import EXPLICIT_RANGE
    for p in (raw.get("pauses", []) or [])[:16]:
        if not isinstance(p, dict) or p.get("after_seg") not in kept:
            continue
        try:
            sec = min(max(float(p.get("sec", 0.8)), EXPLICIT_RANGE[0]), EXPLICIT_RANGE[1])
        except (TypeError, ValueError):
            continue
        if not any(x["after_seg"] == p["after_seg"] for x in plan["pauses"]):
            plan["pauses"].append({"after_seg": p["after_seg"], "sec": round(sec, 2),
                                   "reason": str(p.get("reason", "") or "")[:60]})
    for s in (raw.get("silences", []) or [])[:8]:
        if not isinstance(s, dict) or s.get("after_seg") not in kept or any(x["after_seg"] == s["after_seg"] for x in plan["silences"]):
            continue
        try:
            sec = round(min(max(float(s.get("sec", 1.0)), EXPLICIT_RANGE[0]), EXPLICIT_RANGE[1]), 2)
        except (TypeError, ValueError):
            continue
        plan["silences"].append({"after_seg": s["after_seg"], "sec": sec, "before": "peak" if s.get("before") == "peak" else "turn",
                                 "why": str(s.get("why", "") or "")[:60]})
        same = next((x for x in plan["pauses"] if x["after_seg"] == s["after_seg"]), None)
        if same is not None:
            same["sec"] = max(same["sec"], sec)
        else:
            plan["pauses"].append({"after_seg": s["after_seg"], "sec": sec, "reason": "침묵"})
    plan["sound_gags"] = clean_sound_gags(((raw.get("studio") or {}).get("treatment") or {}).get("sound_gags") or raw.get("sound_gags"), kept)
    for q in (raw.get("sequences", []) or [])[:24]:
        if not isinstance(q, dict) or q.get("type") not in SEQ_TYPES or not str(q.get("id") or "").strip():
            continue
        a, b = _nearest(kept, q.get("start_seg")), _nearest(kept, q.get("end_seg", q.get("start_seg")))
        if a is None or b is None:
            continue
        if b < a:
            a, b = b, a
        shots = [{"seg": _nearest(kept, x.get("seg")), "word": str(x.get("word", "") or "")[:24],
                  "show": str(x.get("show", "") or "")[:24]} for x in (q.get("shots") or [])[:8] if isinstance(x, dict)]
        plan["sequences"].append({
            "id": str(q["id"]).strip()[:16], "type": q["type"], "start_seg": a, "end_seg": b,
            "claim": str(q.get("claim", "") or "")[:60], "shots": [x for x in shots if x["seg"] is not None],
            "layout": q.get("layout") if q.get("layout") in ("fullscreen", "split", "pip") else "fullscreen",
            "audio": q.get("audio") if q.get("audio") in ("bed", "rest", "swell") else "bed",
            "enter": q.get("enter") if q.get("enter") in ("on_word", "voice_first", "picture_first") else "on_word",
            "exit": q.get("exit") if q.get("exit") in ("on_sentence", "tail") else "on_sentence",
            "fallback": q.get("fallback") if q.get("fallback") in ("single", "template", "face") else "single",
            "reason": str(q.get("reason", "") or "")[:60]})
    for r in (raw.get("rhythm", []) or [])[:40]:
        if not isinstance(r, dict) or r.get("level") not in ("slow", "steady", "fast"):
            continue
        a, b = _nearest(kept, r.get("start_seg")), _nearest(kept, r.get("end_seg", r.get("start_seg")))
        if a is None or b is None:
            continue
        plan["rhythm"].append({"start_seg": min(a, b), "end_seg": max(a, b), "level": r["level"],
                               "reason": str(r.get("reason", "") or "")[:60]})
    # 🎬 하이라이트 조각 = 이어지는 발화 seg~end_seg(한 생각, 많아야 4발화). 예전 계획(end_seg 없음)은 한 발화 조각
    for h in raw.get("highlights", []) or []:
        seg = h.get("seg") if isinstance(h, dict) else h
        if seg not in kept or seg in kept[:2]:
            continue
        end = h.get("end_seg", seg) if isinstance(h, dict) else seg
        end = end if end in kept and end >= seg else seg
        i = kept.index(seg)
        end = kept[min(kept.index(end), i + 3)]
        if any(x["seg"] <= end and seg <= x["end_seg"] for x in plan["highlights"]):
            continue
        plan["highlights"].append({"seg": seg, "end_seg": end,
                                   "reason": str((h.get("reason", "") if isinstance(h, dict) else "") or "")[:60]})
    plan["highlights"] = plan["highlights"][:4]
    # 대본 태그는 반드시 반영(디렉터가 빠뜨렸으면 추가)
    enforce_tags(plan, tags, kept)
    # 챕터 중복 제거 + 정렬
    seen: set[int] = set()
    chapters = []
    for c in sorted(plan["chapters"], key=lambda c: c["seg"]):
        if c["seg"] not in seen:
            seen.add(c["seg"])
            chapters.append(c)
    plan["chapters"] = chapters
    # 너무 많이 버리지 않도록(디렉터 삭제는 전체의 5% 까지만 — 대본 문장은 파이프라인이 따로 거절한다)
    max_drop = max(1, int(len(kept) * 0.05))
    plan["drop"] = plan["drop"][:max_drop]
    return plan


def cap_cards(graphics: list[dict[str, Any]], sec: float) -> None:
    """자유 카드는 실물이 보여 줄 수 없는 메커니즘에만 — 15분에 6곳까지(시그니처 포함, 최소 3곳). 넘치면 시그니처를 남기고,
    실물 대신 쓴 이유가 없는 카드부터, 그다음 늦은 것부터 뺀다."""
    cards = sorted((g for g in graphics if g["template"] == "card"),
                   key=lambda g: (not g.get("signature"), not g.get("why_not_evidence"), g["start_seg"]))
    drop = {id(g) for g in cards[max(3, round(6 * sec / 900)):]}
    if drop:
        graphics[:] = [g for g in graphics if id(g) not in drop]


def enforce_tags(plan: dict[str, Any], tags: list[Tag], kept: list[int]) -> None:
    for t in tags:
        if t.utt_id is None or t.utt_id not in kept:
            continue
        seg = t.utt_id
        if t.kind == "chapter":
            if not any(abs(kept.index(c["seg"]) - kept.index(seg)) <= 1 for c in plan["chapters"]
                       if c["seg"] in kept):
                plan["chapters"].append({"seg": seg, "title": t.args[0] if t.args else ""})
            continue
        # 저장된 plan.json 을 다시 정규화해도 결과가 같아야 한다(중복 추가 금지)
        if t.kind == "zoom":
            if not any(e["seg"] == seg and e.get("kind") == "punch" for e in plan["emphasis"]):
                plan["emphasis"].append({"seg": seg, "word": "", "kind": "punch"})
            if not any(m["seg"] == seg for m in plan.setdefault("moments", [])):
                plan["moments"].append({"seg": seg, "word": t.args[0] if t.args else "", "kind": "punchline",
                                        "intensity": 2, "callout": "", "label": ""})
            continue
        if t.kind == "cut":
            if not any(d["seg"] == seg for d in plan["drop"]):
                plan["drop"].insert(0, {"seg": seg, "reason": "대본 [컷] 태그"})
            continue
        g = graphic_from_tag(t, seg)
        if not g:
            continue
        near = [x for x in plan["graphics"] if x["template"] == g["template"]
                and abs(kept.index(x["start_seg"]) - kept.index(seg)) <= 1]
        if near:
            if "태그" not in (near[0].get("reason") or ""):
                near[0]["reason"] = (near[0].get("reason") or "") + " (대본 태그)"
            continue
        plan["graphics"].append(g)


# 앞 문맥 없이는 뜻이 안 서는 첫말(숏폼 첫 문장·콜드 오픈에 오면 '뭔 내용인지 모르겠다')
DANGLING_START = ("그래서", "그런데", "그러니까", "그니까", "근데", "그리고", "이게", "그게", "이건", "그건", "이런", "그런",
                  "그럼", "그러면", "또", "여기서", "즉", "이렇게", "그렇게", "다음", "두 번째", "세 번째", "마지막으로",
                  "아까", "앞에서", "그때", "이때", "이 부분", "그 부분", "그 다음", "이제 그", "왜냐하면")
_STOP = set("이것 그것 우리 여러분 오늘 영상 정말 진짜 이유 방법 사실 하나 정도 부분 때문 그리고 그래서 하지만 디자인".split())


def _content_words(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[가-힣A-Za-z]{2,}", text):
        w = re.sub(r"(은|는|이|가|을|를|의|에|에서|으로|로|와|과|도|만|까지|부터|이라는|라는|입니다|이에요|예요|이란|란)$", "", w)
        if len(w) >= 2 and w not in _STOP:
            out.add(w)
    return out


def short_coherence(segs: list[int], by_id: dict[int, Utterance], kept: list[int], *, cold: int = -1,
                    hook_title: str = "") -> tuple[float, list[str]]:
    """숏폼이 롱폼을 안 본 사람에게도 한 덩어리로 이해되는지(0~1) + 문제 목록.
    - 떨어진 발화 이어붙이기: 본문(콜드 오픈 제외) 안의 건너뛴 발화 수마다 감점(1개까지는 허용)
    - 첫 문장이 '그래서·이게·아까' 처럼 앞 문맥에 매달리면 감점
    - 마지막 문장이 끝나지 않으면(문장부호·종결 어미 없음) 감점
    - 훅 타이틀의 명사가 말 속에 하나도 없으면(약속-해소 불일치) 감점"""
    problems: list[str] = []
    score = 1.0
    body = [x for x in segs if x != cold] if cold in segs else list(segs)
    pos = {u: i for i, u in enumerate(kept)}
    skipped = 0
    for a, b in zip(body, body[1:]):
        if a in pos and b in pos:
            d = pos[b] - pos[a]
            if d <= 0:
                skipped += 2          # 순서가 뒤바뀜
            else:
                skipped += d - 1
    if skipped > 1:
        score -= min(0.6, 0.15 * skipped)
        problems.append(f"발화 {skipped}개를 건너뛰며 이어 붙임")
    first = by_id.get(segs[0])
    if first is not None:
        t = first.text.strip()
        if any(t.startswith(d) for d in DANGLING_START):
            score -= 0.3
            problems.append(f"첫 문장이 앞 문맥에 매달림: 「{t[:20]}」")
    last = by_id.get(body[-1] if body else segs[-1])
    if last is not None:
        t = last.text.strip()
        if not re.search(r"([.?!。？！]|다|요|죠|까|네)$", t):
            score -= 0.2
            problems.append(f"끝 문장이 끝나지 않음: 「{t[-20:]}」")
    if hook_title:
        spoken = " ".join(by_id[i].text for i in segs if i in by_id)
        nouns = _content_words(hook_title.replace("\n", " "))
        if nouns and not (nouns & _content_words(spoken)):
            score -= 0.2
            problems.append("훅 타이틀의 명사가 말 속에 없음(약속-해소 불일치)")
    return max(0.0, round(score, 2)), problems


def repair_segments(segs: list[int], by_id: dict[int, Utterance], kept: list[int], *, cold: int, max_sec: float
                    ) -> list[int]:
    """떨어진 발화를 이어 붙인 숏폼 → 첫 발화부터 끝 발화까지 **연속 구간**으로 고친다(빠진 문장을 되살림). 너무 길면
    콜드 오픈(또는 마지막 발화)을 포함하는 뒤쪽 연속 구간을 max_sec 안에서 남긴다."""
    body = [x for x in segs if x != cold]
    if not body:
        return segs
    pos = {u: i for i, u in enumerate(kept)}

    def dur(ids: list[int]) -> float:
        return sum(by_id[i].end - by_id[i].start for i in ids if i in by_id)
    # 본문을 '가까운 발화 묶음'으로 나눈다(2개 이상 건너뛰면 다른 묶음) → 가장 긴 묶음만 쓴다(멀리서 끌어온 문장은 뺀다)
    ordered = sorted(body, key=lambda x: pos.get(x, 0))
    clusters: list[list[int]] = [[ordered[0]]]
    for a, b in zip(ordered, ordered[1:]):
        if pos.get(b, 0) - pos.get(a, 0) - 1 >= 2:
            clusters.append([b])
        else:
            clusters[-1].append(b)
    main = max(clusters, key=lambda c: dur(kept[pos[c[0]]:pos[c[-1]] + 1]))
    run = kept[pos[main[0]]:pos[main[-1]] + 1]
    while len(run) > 1 and dur(run) > max_sec:
        run = run[1:]           # 앞에서부터 줄인다 — 페이오프(뒤쪽)를 남긴다
    out = list(run)
    if cold in by_id:
        # 콜드 오픈은 앞 문맥 없이 서는 문장일 때만 맨 앞에(아니면 뺀다)
        if cold in out:
            out.remove(cold)
        if not any(by_id[cold].text.strip().startswith(d) for d in DANGLING_START):
            out.insert(0, cold)
    return out


def normalize_shorts(raw: dict[str, Any], utts: list[Utterance], *, count: int, max_sec: int = 60,
                     log: Any = None, order: Optional[list[int]] = None) -> list[dict[str, Any]]:
    """숏폼 기획 정리. **제대로 된 한 편**이 우선: 이해 가능성(short_coherence)이 낮으면 연속 구간으로 고치고,
    둘째 편은 첫 편과 다른 구간이면서 점수 8 이상일 때만 남긴다(채널 피드백: 둘을 억지로 채우지 말 것).
    order: 남긴 발화의 **편집 순서**(대본을 여러 번 읽은 녹음은 시간순이 아니라 대본 자리 순 — 2026-10-03 E2E: 회차를 교차한
    뒤 시간순으로 '건너뛴 발화'로 보여 숏폼을 통째로 잃었다). 없으면 시간순."""
    kept_set = {u.id for u in utts if u.kept}
    kept = [i for i in order if i in kept_set] if order else [u.id for u in utts if u.kept]
    by_id = {u.id: u for u in utts}
    out: list[dict[str, Any]] = []
    for s in (raw.get("shorts") or [])[: max(0, count) + 2]:
        if not isinstance(s, dict):
            continue
        segs: list[int] = []
        for x in s.get("segments", []) or []:
            if x in kept and x not in segs:
                segs.append(x)
        cold = s.get("cold_open_seg", -1)
        if cold in kept:
            if cold in segs:
                segs.remove(cold)
            segs.insert(0, cold)
        else:
            cold = -1
        if not segs:
            continue
        hook_title = str(s.get("hook_title", "")).strip()
        coherence, problems = short_coherence(segs, by_id, kept, cold=cold, hook_title=hook_title)
        repaired = False
        if coherence < 0.7 and any("건너뛰" in p or "뒤바뀜" in p for p in problems):
            new = repair_segments(segs, by_id, kept, cold=cold, max_sec=max_sec)
            if new != segs:
                segs, repaired = new, True
                coherence, problems = short_coherence(segs, by_id, kept, cold=cold, hook_title=hook_title)
                if log:
                    log(f"📱 숏폼 「{s.get('title', '')}」: 떨어진 발화를 이어 붙여 이해가 어려움 → 연속 구간으로 고침")
        dur = sum(by_id[i].end - by_id[i].start for i in segs)
        if dur < 12:
            continue
        graphics = [g for g in (_clean_graphic(g, segs) for g in s.get("graphics", []) or []) if g]
        hook_type = s.get("hook_type") if s.get("hook_type") in HOOK_TYPES else "open_loop"
        out.append({
            "title": str(s.get("title", "")).strip() or "short",
            "hook_type": hook_type,
            "hook_title": str(s.get("hook_title", "")).strip(),
            "hook_highlight": str(s.get("hook_highlight", "")).strip(),
            "cold_open_seg": cold,
            "segments": segs,
            "graphics": graphics,
            "emphasis": [e for e in s.get("emphasis", []) or [] if isinstance(e, dict) and e.get("seg") in segs],
            "beats": [{"seg": b["seg"], "label": str(b.get("label", "")).strip()[:14],
                       "text": str(b.get("text", "")).strip()[:24], "accent": str(b.get("accent", "")).strip()}
                      for b in s.get("beats", []) or []
                      if isinstance(b, dict) and b.get("seg") in segs and str(b.get("text", "")).strip()],
            "cta": str(s.get("cta", "")).strip(),
            "loop_line": str(s.get("loop_line", "")).strip(),
            "caption": str(s.get("caption", "")).strip(),
            "hashtags": [str(h).strip() for h in s.get("hashtags", []) or [] if str(h).strip()][:8],
            "viewer_takeaway": str(s.get("viewer_takeaway", "") or "").strip()[:80],
            "why": str(s.get("why", "")).strip() + (f" · 이해 가능성 {coherence:.1f}" + (f"({'; '.join(problems)})" if problems else "")
                                                    + (" → 연속 구간으로 고침" if repaired else "")),
            "coherence": coherence,
            "score": int(s.get("score", 5) or 5),
        })
    # 정렬: 이해 가능성이 낮은 편(0.5 미만)은 뒤로, 그 안에서 점수순
    out.sort(key=lambda s: (s["coherence"] < 0.5, -s["score"], -s["coherence"]))
    picked: list[dict[str, Any]] = []
    for s in out:
        if not picked:
            picked.append(s)
            continue
        if len(picked) >= count:
            break
        overlap = set(s["segments"]) & set(picked[0]["segments"])
        if s["score"] >= 8 and s["coherence"] >= 0.7 and len(overlap) <= 1:
            picked.append(s)
        elif log:
            log(f"📱 숏폼 「{s.get('title', '')}」 은 만들지 않음(점수 {s['score']} · 이해 가능성 {s['coherence']:.1f} · "
                f"첫 편과 겹침 {len(overlap)}) — 제대로 된 한 편이 우선")
    return picked


# ----------------------------------------------------------------------------
# 2) 편집 시간으로 변환
# ----------------------------------------------------------------------------

@dataclass
class TimedGraphic:
    id: str
    template: str
    layout: str
    start: float
    end: float
    data: dict[str, Any]
    priority: int = 5
    source: str = "director"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["start"] = round(self.start, 3)
        d["end"] = round(self.end, 3)
        return d


BADGE_SEC = 3.0
BADGE_GAP = 90.0        # 배지 사이 최소 간격 — 앞 배지에서 이 안이면 건너뛴다
BADGE_SLIP = 12.0       # 전면 그래픽·홀드에 걸리면 끝난 뒤로 밀되 이만큼까지만


def argument_badges(tags: list[dict], seg_t: dict[int, tuple[float, float]], covers: list[tuple[float, float]],
                    total: float) -> list[TimedGraphic]:
    """논증 배지 = 좌상단 슬롯의 lower_third(data.slot='badge'). covers(전면 그래픽·얼굴 홀드) 위에는 올리지 않는다."""
    out: list[TimedGraphic] = []
    last = -1e9
    for tag in sorted(tags, key=lambda x: x["seg"]):
        if tag["seg"] not in seg_t:
            continue
        said = t = seg_t[tag["seg"]][0]
        for a, b in sorted(covers):
            if a - 0.2 < t + BADGE_SEC and t < b:     # 배지가 떠 있는 3초 전체가 덮개 밖이어야 한다
                t = b + 0.3
        if t - said > BADGE_SLIP or t - last < BADGE_GAP or t + BADGE_SEC > total:
            continue
        out.append(TimedGraphic(f"badge{len(out)}", "lower_third", "overlay", round(t, 3), round(t + BADGE_SEC, 3),
                                {"slot": "badge", "title": tag["tag"]}, priority=4, source="auto"))
        last = t
    return out


def seg_edit_times(utts: list[Utterance], timemap: TimeMap) -> dict[int, tuple[float, float]]:
    out: dict[int, tuple[float, float]] = {}
    for u in utts:
        if not u.words:
            continue
        a = timemap.src_to_edit(u.words[0].start, snap=True)
        b = timemap.src_to_edit(u.words[-1].end, snap=True)
        if a is None or b is None:
            continue
        out[u.id] = (a, max(b, a + 0.2))
    return out


def word_edit_time(u: Utterance, word: str, timemap: TimeMap) -> Optional[float]:
    if not word:
        return None
    w = find_word(u.words, word)
    return timemap.src_to_edit(w.start, snap=True) if w else None


def reading_chars(g: dict[str, Any]) -> int:
    parts = [g.get("title") or "", g.get("subtitle") or "", g.get("body") or "", g.get("title_b") or ""]
    parts += [str(x) for x in (g.get("items") or []) + (g.get("items_b") or [])]
    if g.get("template") == "motion" and isinstance(g.get("spec"), dict):
        parts += [str(e.get("text", "")) for e in g["spec"].get("elements", []) if isinstance(e, dict)]
    if g.get("template") == "card" and isinstance(g.get("card"), dict):
        # 카드는 단계적으로 드러나고 라벨·메타 글자가 많다 — 읽기 시간은 카드 DSL 의 상한(60자)까지만 센다
        parts.append(card_text(g["card"]).replace(" ", "")[:60])
    if g.get("template") in ("broll", "photo"):
        return 0
    if g.get("template") == "evidence":
        arc = g.get("archive") or {}
        parts = [g.get("title") or "", g.get("caption") or g.get("body") or "", arc.get("title") or "",
                 arc.get("quote") or ""] + [str(r.get("v", "")) for r in arc.get("rows") or []][:2]
    return sum(len(p.replace(" ", "")) for p in parts)


def spec_settle_time(spec: dict[str, Any]) -> float:
    """모든 요소가 도착(진입 완료)하는 시각."""
    t = 0.0
    for e in spec.get("elements", []) or []:
        if not isinstance(e, dict):
            continue
        try:
            t = max(t, float(e.get("at", 0) or 0) + float(e.get("dur", 0.5) or 0.5))
            for k in e.get("keys", []) or []:
                t = max(t, float(k.get("t", 0) or 0))
        except (TypeError, ValueError):
            continue
    return t


def time_graphics(
    graphics: list[dict[str, Any]],
    utts: list[Utterance],
    timemap: TimeMap,
    *,
    total: float,
    reserved: list[TimedGraphic] | None = None,
    min_start: float = 1.2,
    id_prefix: str = "g",
    log: Optional[Callable[[str], None]] = None,
) -> list[TimedGraphic]:
    say = log or (lambda _m: None)
    by_id = {u.id: u for u in utts}
    seg_t = seg_edit_times(utts, timemap)
    order = sorted(seg_t.keys(), key=lambda i: seg_t[i][0])
    timed: list[TimedGraphic] = []

    def land(g: dict[str, Any], data: dict[str, Any], start: float, dur: float) -> Optional[float]:
        """모션·카드의 표시를 이 시작 시각 기준으로 낱말에 맞춘다. 반환: 마지막 낱말 시각(그릴 수 없는 장면이면 None)."""
        if g["template"] == "motion":
            spec = clean_spec(g.get("spec"), dur)
            if not spec:
                return None
            last = land_scene_on_words(spec, g, utts, timemap, start, say)
            if spec.get("wordMarks"):
                data["wordMarks"] = spec.pop("wordMarks")
            stage_first(spec["elements"])           # 낱말로 옮긴 뒤에도 0.5초 안에 무대가 서 있게
            data["spec"] = spec
            return last
        data["card"], last = land_on_words(g, utts, timemap, start)
        if data["card"].get("wordMarks"):
            data["wordMarks"] = data["card"].pop("wordMarks")
        return last

    def land_steps(g: dict[str, Any], data: dict[str, Any], start: float) -> list[dict[str, Any]]:
        at = step_times(g, utts, timemap, start)
        if at:
            data["stepAt"] = [{**s, "t": max(0.0, s["t"])} for s in at]
            data["wordMarks"] = [{"land": max(0.0, s["t"]), "spoken": round(start + s["t"], 3)} for s in at]
            data["highlight"] = at[0]["index"]
        return at

    for i, g in enumerate(graphics):
        t = TEMPLATES[g["template"]]
        s_seg = g["start_seg"]
        if s_seg not in seg_t:
            continue
        start = seg_t[s_seg][0]
        wt = word_edit_time(by_id[s_seg], g.get("start_word", ""), timemap) if s_seg in by_id else None
        if wt is not None:
            start = wt
        e_seg = g.get("end_seg", s_seg)
        end = seg_t.get(e_seg, seg_t[s_seg])[1]
        # 목록/단계형은 항목 수만큼 충분히
        want = t.min_dur
        n_items = len(g.get("items") or []) + len(g.get("items_b") or [])
        if g["template"] in ("list", "process", "cycle", "timeline", "pyramid", "compare"):
            want = max(want, 1.6 + 1.4 * n_items)
        # 읽기 시간(한국어 10자/초 + 도착·눈이 가는 여유 1.8초) — 2026-10-04 채널 주인: "그래픽이 말이 끝나면 끝나서 너무 짧고
        # 잘 보이지도 않는다"(글자를 줄인 뒤 읽기 시간도 같이 줄어 카드가 3초 안팎이 됐다)
        want = max(want, 1.8 + reading_chars(g) / 10.0)
        if g["template"] == "motion" and isinstance(g.get("spec"), dict):
            want = max(want, spec_settle_time(g["spec"]) + 2.0)
        if g["template"] == "card" and isinstance(g.get("card"), dict):
            want = max(want, card_settle_time(g["card"]) + 2.0)
        if g["template"] in ("collage", "keyword_montage"):
            want = max(want, 1.1 * len(g.get("cutouts") or []) + (1.2 if g["template"] == "collage" else 0.0))
        if g["template"] == "evidence":
            # 트리트먼트별 유지 + 여러 장이면 장마다 1.8초(03 문서 6-2)
            n_assets = len(g.get("assets") or [])
            want = max(want, EVIDENCE_HOLD.get(g.get("treatment", "hero"), 4.0)
                       + 1.8 * max(0, n_assets - 1) * (g.get("treatment") in ("hero", "full")))
        end = max(end, start + want)
        # 목표 길이에 맞게 다음 발화들까지 자연스럽게 연장
        if end - start < want and s_seg in order:
            k = order.index(s_seg)
            while k + 1 < len(order) and seg_t[order[k]][1] < start + want:
                k += 1
            end = max(end, seg_t[order[k]][1])
        end = min(end, start + t.max_dur, total - 0.3)
        if g["template"] == "evidence" and g.get("tier") == "C":
            end = min(end, start + 6.0)          # 인용(C 등급)은 한 번에 6초 이내(저작권 정책 4절 2)
        if g.get("logo"):
            end = min(end, start + LOGO_MAX_SEC)   # 로고는 이름표로 잠깐만
        # 진입·퇴장은 역할마다(ENTER_EXIT) — 2026-10-04 채널 주인: "그래픽은 그 말이 나오기 직전에 살짝 미리 등장해야 하는데
        # 말하고 나서 뜨고, 말이 끝나면 바로 사라진다". 등장은 그 낱말 0.35~0.5초 전(눈이 먼저 가 있게), 퇴장은 문장 끝 뒤
        # 0.6~1.0초 머문다(다음 그래픽이 오면 resolve_overlaps 가 그 앞에서 자른다)
        lead, tail = ENTER_EXIT.get(g.get("layout", ""), (0.4, 0.8))
        start = max(start - lead, min_start)
        end = min(end + tail, total - 0.3)
        if end - start < t.min_dur * 0.7:
            continue
        data = {k: g.get(k) for k in DATA_KEYS}
        # 말이 어디까지인지(마지막 발화) — 홀드 앞에서 끊을 때 '넘어간 것이 꼬리뿐인가' 를 판단한다(Pipeline._respect_holds)
        data["end_seg"] = int(g.get("end_seg", g.get("start_seg", 0)) or 0)
        for k in EXTRA_DATA_KEYS:
            if g.get(k):
                data[k] = g[k]
        if g.get("sequence_id"):
            data["seq_id"] = g["sequence_id"]
        if g["template"] == "lower_third":
            data["slot"] = "super"        # 총괄·모션이 고른 인물·기관 슈퍼(앱이 넣는 '오늘의 주제'·논증 배지와 구분)
        if g.get("steps"):
            # 단계 그래픽: 강조가 그 낱말에서 바뀐다(그래픽은 하나, 끝은 마지막 단계 문장의 끝)
            at = land_steps(g, data, start)
            if at:
                end = max(end, start + at[-1]["t"] + 1.6)
                if total:
                    end = min(end, total - 0.3)
        if g["template"] == "broll" and not g.get("src"):
            continue  # 소재를 못 구한 B-roll 은 버린다(틀린 B-roll 보다 없는 게 낫다)
        if g["template"] == "evidence" and not (g.get("assets") or g.get("archive")):
            continue
        if g["template"] in ("motion", "card"):
            if g["template"] == "card" and not isinstance(g.get("card"), dict):
                continue
            last = land(g, data, start, end - start)
            if last is None:
                say(f"🎨 모션 장면 S{s_seg} '{g.get('title', '')}': 그릴 수 있는 내용이 없어 뺍니다")
                continue
            end = min(max(end, start + last + 2.0), total - 0.3) if total else end
        # 증거의 역할: 근거·사례는 우선순위 그대로(8), 맥락·분위기는 6(03 문서 6-2)
        role_pen = 2 if (g.get("evidence") or {}).get("role") in ("context", "mood") else 0
        if g.get("sfx") in SFX_DIRECTED:
            data["sfx"] = g["sfx"]
        timed.append(TimedGraphic(f"{id_prefix}{i}", g["template"], g["layout"], start, end, data,
                                  t.priority - role_pen + (3 if "태그" in (g.get("reason") or "") else 0)
                                  + (3 if g.get("signature") else 0),
                                  "tag" if "태그" in (g.get("reason") or "") else "director"))
    planned = {tg.id: tg.start for tg in timed}
    out = resolve_overlaps(timed + list(reserved or []), total=total)
    source = {f"{id_prefix}{i}": g for i, g in enumerate(graphics)}
    for tg in out:                # 자리를 다투다 옮겨진 그래픽도 표시는 그 낱말에 — 시작이 정해진 뒤에 잰다
        g = source.get(tg.id)
        if g is None:
            continue
        land_marks(tg, g, utts, timemap)
        if tg.start != planned.get(tg.id):
            if g["template"] in ("motion", "card"):
                land(g, tg.data, tg.start, tg.end - tg.start)
            elif g.get("steps"):
                land_steps(g, tg.data, tg.start)
    return out


# (진입 선행, 퇴장 꼬리) 초 — 예전 pip −3f/+6f · split −9f/+8f · 전면 −2f/+8f 는 "말한 뒤에 뜨고 말 끝나면 사라진다"(2026-10-04)
ENTER_EXIT = {"pip": (0.35, 0.6), "overlay": (0.35, 0.6), "split": (0.5, 0.9), "fullscreen": (0.45, 1.0)}
EVIDENCE = ("photo", "broll", "evidence", "collage", "keyword_montage")      # 실물 자료(사진·스톡·증거) — 자리를 다투면 버리지 않고 다음 빈 자리로 옮긴다


def resolve_overlaps(items: list[TimedGraphic], gap: float = 0.2, total: Optional[float] = None,
                     max_shift: float = 8.0) -> list[TimedGraphic]:
    """시간순으로 겹침을 푼다. 더 중요한 그래픽이 오면 앞의 것을 줄이거나 버리고, 덜 중요하면 뒤로 민다.
    실물 자료(EVIDENCE)는 밀리거나 밀려나도 버리지 않고 최소 길이를 지켜 다음 빈 자리로 옮긴다 — 원래 자리에서 max_shift
    초 안에서만(10/1: 받아 둔 홍익대 사진이 타이틀 카드에 밀려 지워졌는데 바로 뒤 5초가 비어 있었다)."""
    stamps = [g for g in items if g.template == "stamp"]
    queue = sorted((g for g in items if g.template != "stamp"), key=lambda g: (g.start, -g.priority))
    orig = {id(g): g.start for g in queue}

    def min_dur(x: TimedGraphic) -> float:
        return TEMPLATES[x.template].min_dur if x.template in TEMPLATES else 1.5

    def defer(x: TimedGraphic, t: float) -> bool:
        """자료 x 를 t 부터 다시 놓는다(큐에 다시 넣음). 옮길 수 없으면 False."""
        if x.template not in EVIDENCE or t - orig.get(id(x), x.start) > max_shift:
            return False
        d = max(x.end - x.start, min_dur(x))
        x.start, x.end = t, t + d
        if total is not None:
            x.end = min(x.end, total - 0.3)
        if x.end - x.start < min_dur(x) * 0.8:
            return False
        k = 0
        while k < len(queue) and (queue[k].start, -queue[k].priority) <= (x.start, -x.priority):
            k += 1
        queue.insert(k, x)
        return True

    out: list[TimedGraphic] = []
    while queue:
        g = queue.pop(0)
        if not out or g.start >= out[-1].end + gap:
            out.append(g)
            continue
        last = out[-1]
        min_last, min_g = min_dur(last), min_dur(g)
        seq_g, seq_last = (g.data or {}).get("seq_id"), (last.data or {}).get("seq_id")
        if seq_g and seq_g == seq_last and g.start - last.start >= 0.8:
            # 같은 시퀀스: 다음 샷이 앞 샷을 자른다(간격 0, 같은 틀 안의 컷 — 밀거나 버리지 않는다)
            last.end = g.start
            out.append(g)
            continue
        if (g.template in EVIDENCE and last.template in EVIDENCE and orig.get(id(g), g.start) == g.start
                and orig.get(id(last), last.start) != last.start and g.priority >= last.priority - 1):
            # 밀려 온 자료가 제 문장의 자료를 밀어내지 않는다 — 제 시각의 자료가 이기고, 밀려 온 것은 그 뒤로(자리가 없으면 빠진다)
            if g.start - last.start >= min_last * 0.8:
                last.end = g.start
                out.append(g)
            else:
                out[-1] = g
                defer(last, g.end + gap)
        elif (g.template in EVIDENCE and last.template in EVIDENCE and g.priority >= last.priority
                and g.start - last.start >= min_last and orig.get(id(g), g.start) == g.start):
            # 실물 자료끼리: 자료는 자기 문장의 것 — 앞 자료가 최소 시간을 채웠으면 다음 문장의 자료가 들어올 때 끝난다
            # (읽을 시간으로 늘어난 앞 자료가 다음 문장의 자료를 밀어내 결국 버려지던 것)
            last.end = g.start
            out.append(g)
        elif g.priority > last.priority and g.start - last.start >= min_last * 0.8:
            last.end = g.start - gap
            out.append(g)
        elif g.priority > last.priority:
            # 새 그래픽이 더 중요하고 이전 것이 너무 짧아지면 이전 것을 버린다 — 실물 자료면 새 그래픽 뒤로 옮긴다
            out[-1] = g
            defer(last, g.end + gap)
        elif g.template in EVIDENCE:
            defer(g, last.end + gap)
        else:
            g.start = last.end + gap
            if g.end - g.start < min_g * 0.8 and (g.priority >= 8 or g.source == "tag"):
                # 대본 태그 등 중요한 그래픽은 뒤로 밀어서라도 최소 길이를 확보 — 말이 끝난 뒤(엔드카드)로는 넘기지 않는다
                g.end = g.start + min_g
                if total is not None:
                    g.end = min(g.end, total - 0.3)
            if g.end - g.start >= min_g * 0.8:
                out.append(g)
    return seat_stamps(out, stamps)


def seat_stamps(placed: list[TimedGraphic], stamps: list[TimedGraphic]) -> list[TimedGraphic]:
    """도장은 자리를 다투는 그래픽이 아니라 전면 자료 위에 찍는 층이다. 그 시각에 전면 자료가 없으면(얼굴 위) 찍지 않는다."""
    out = list(placed)
    for s in stamps:
        host = next((m for m in placed if m.template in EVIDENCE and m.layout == "fullscreen"
                     and m.start - 1.0 <= s.start and max(s.start, m.start + 0.3) + 1.5 <= m.end), None)
        if host is not None:
            s.start, s.end = max(s.start, host.start + 0.3), min(s.end, host.end)
            out.append(s)
    return sorted(out, key=lambda g: g.start)
