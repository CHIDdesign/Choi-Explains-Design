"""디렉터 출력(발화 ID 기준) 검증 → 대본 태그 강제 반영 → 편집 시간 기준 이벤트로 변환."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Optional

from ..models import Tag, TimeMap, Utterance
from ..motion.card import card_settle_time, card_text, clean_card
from ..motion.spec import clean_spec
from ..text.align import find_word, norm
from .catalog import DIAGRAM_ALIASES, PRESET_DIAGRAMS, TAG_TO_TEMPLATE, TEMPLATES
from .schema import HOOK_TYPES

EM_TYPES = ("keyword", "term", "number", "contrast")  # 자막 강조 유형(renderer EmType)
MOMENT_KINDS = ("punchline", "reveal", "shift", "conclusion", "question", "number", "joke")  # 강조 순간

# 렌더러로 넘기는 그래픽 데이터 키(템플릿별로 없는 키는 생략)
DATA_KEYS = ("title", "subtitle", "body", "items", "title_b", "items_b", "highlight", "author", "source", "image")
EXTRA_DATA_KEYS = ("credit", "src", "kind", "kenburns", "stock_url")

GRAPHIC_KEYS = ("template", "layout", "start_seg", "end_seg", "start_word", "title", "subtitle", "body",
                "items", "title_b", "items_b", "highlight", "author", "source", "image", "reason")


def blank_graphic(template: str, seg: int) -> dict[str, Any]:
    t = TEMPLATES.get(template)
    return {"template": template, "layout": t.layouts[0] if t else "fullscreen", "start_seg": seg,
            "end_seg": seg, "start_word": "", "title": "", "subtitle": "", "body": "", "items": [],
            "title_b": "", "items_b": [], "highlight": -1, "author": "", "source": "", "image": "",
            "reason": ""}


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
    out["items"] = [str(x).strip() for x in out.get("items") or [] if str(x).strip()][:8]
    out["items_b"] = [str(x).strip() for x in out.get("items_b") or [] if str(x).strip()][:8]
    try:
        out["highlight"] = int(out.get("highlight", -1))
    except (TypeError, ValueError):
        out["highlight"] = -1
    # 템플릿별 최소 요건
    tn = out["template"]
    if tn in ("keyword", "chapter", "stat") and not out["title"].strip():
        return None
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
        if not isinstance(spec, dict) or not clean_spec(spec, 12.0):
            return None
        out["spec"] = spec
    if tn == "card":
        # 🃏 자유 HTML 카드 — 재정규화 때도 다시 정리한다(스코프·금지 항목은 멱등)
        card = clean_card(g.get("card"), layout=out["layout"])
        if not card:
            return None
        out["card"] = card
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
        for k in ("src", "kind", "credit", "kenburns", "stock_url"):
            if g.get(k):
                out[k] = g[k]
    if tn == "photo" and g.get("credit"):
        out["credit"] = g["credit"]
    return out


def _nearest(valid: list[int], seg: Any) -> int:
    try:
        seg = int(seg)
    except (TypeError, ValueError):
        return valid[0]
    if seg in valid:
        return seg
    return min(valid, key=lambda v: (abs(v - seg), v))


def normalize_long(raw: dict[str, Any], utts: list[Utterance], tags: list[Tag]) -> dict[str, Any]:
    kept = [u.id for u in utts if u.kept]
    if not kept:
        raise ValueError("남은 발화가 없습니다")
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
        "captions": raw.get("captions") or {},   # 🔤 자막 디자이너의 프리셋 선택
        "studio": raw.get("studio") or {},       # 🎬 스튜디오 메모(리포트용)
        "moments": [],                           # ✂️ 강조 순간(편집 문법 엔진 입력)
        "title": str(raw.get("title", "") or "").strip(),       # 🎬 화면 타이틀
        "bgm_mood": str(raw.get("bgm_mood", "") or ""),
        "shorts_bgm_mood": str(raw.get("shorts_bgm_mood", "") or ""),
    }
    for c in raw.get("chapters", []) or []:
        if isinstance(c, dict) and str(c.get("title", "")).strip():
            plan["chapters"].append({"seg": _nearest(kept, c.get("seg")), "title": str(c["title"]).strip()})
    for g in raw.get("graphics", []) or []:
        cg = _clean_graphic(g, kept)
        if cg:
            if cg["template"] == "chapter":
                plan["chapters"].append({"seg": cg["start_seg"], "title": cg["title"]})
            else:
                plan["graphics"].append(cg)
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
    # 너무 많이 버리지 않도록(디렉터 삭제는 전체의 15% 까지만)
    max_drop = max(1, int(len(kept) * 0.15))
    plan["drop"] = plan["drop"][:max_drop]
    return plan


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


def normalize_shorts(raw: dict[str, Any], utts: list[Utterance], *, count: int) -> list[dict[str, Any]]:
    kept = [u.id for u in utts if u.kept]
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
            "why": str(s.get("why", "")).strip(),
            "score": int(s.get("score", 5) or 5),
        })
    out.sort(key=lambda s: -s["score"])
    return out[:count]


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
) -> list[TimedGraphic]:
    by_id = {u.id: u for u in utts}
    seg_t = seg_edit_times(utts, timemap)
    order = sorted(seg_t.keys(), key=lambda i: seg_t[i][0])
    timed: list[TimedGraphic] = []
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
        # 읽기 시간(한국어 12자/초 + 도착 여유 1.2초) — 넷플릭스 한국어 자막 기준
        want = max(want, 1.2 + reading_chars(g) / 12.0)
        if g["template"] == "motion" and isinstance(g.get("spec"), dict):
            want = max(want, spec_settle_time(g["spec"]) + 1.2)
        if g["template"] == "card" and isinstance(g.get("card"), dict):
            want = max(want, card_settle_time(g["card"]) + 1.2)
        end = max(end, start + want)
        # 목표 길이에 맞게 다음 발화들까지 자연스럽게 연장
        if end - start < want and s_seg in order:
            k = order.index(s_seg)
            while k + 1 < len(order) and seg_t[order[k]][1] < start + want:
                k += 1
            end = max(end, seg_t[order[k]][1])
        end = min(end, start + t.max_dur, total - 0.3)
        # 참고 채널 실측: 화면이 말보다 0.3~1.0초 먼저 도착한다(시청자가 들을 때 이미 보고 있음)
        if g["template"] == "broll":
            start = max(start - 0.3, min_start)
        else:
            start = max(start - 0.45, min_start)
        if end - start < t.min_dur * 0.7:
            continue
        data = {k: g.get(k) for k in DATA_KEYS}
        for k in EXTRA_DATA_KEYS:
            if g.get(k):
                data[k] = g[k]
        if g["template"] == "broll" and not g.get("src"):
            continue  # 소재를 못 구한 B-roll 은 버린다(틀린 B-roll 보다 없는 게 낫다)
        if g["template"] == "motion":
            spec = clean_spec(g.get("spec"), end - start)
            if not spec:
                continue
            data["spec"] = spec
        if g["template"] == "card":
            if not isinstance(g.get("card"), dict):
                continue
            data["card"] = g["card"]
        timed.append(TimedGraphic(f"{id_prefix}{i}", g["template"], g["layout"], start, end, data,
                                  t.priority + (3 if "태그" in (g.get("reason") or "") else 0),
                                  "tag" if "태그" in (g.get("reason") or "") else "director"))
    return resolve_overlaps(timed + list(reserved or []), total=total)


def resolve_overlaps(items: list[TimedGraphic], gap: float = 0.2, total: Optional[float] = None) -> list[TimedGraphic]:
    items = sorted(items, key=lambda g: (g.start, -g.priority))
    out: list[TimedGraphic] = []
    for g in items:
        if not out or g.start >= out[-1].end + gap:
            out.append(g)
            continue
        last = out[-1]
        min_last = TEMPLATES[last.template].min_dur if last.template in TEMPLATES else 1.5
        min_g = TEMPLATES[g.template].min_dur if g.template in TEMPLATES else 1.5
        if g.priority > last.priority and g.start - last.start >= min_last * 0.8:
            last.end = g.start - gap
            out.append(g)
        elif g.priority > last.priority:
            # 새 그래픽이 더 중요하고 이전 것이 너무 짧아지면 이전 것을 버린다
            out[-1] = g
        else:
            g.start = last.end + gap
            if g.end - g.start < min_g * 0.8 and (g.priority >= 8 or g.source == "tag"):
                # 대본 태그 등 중요한 그래픽은 뒤로 밀어서라도 최소 길이를 확보 — 말이 끝난 뒤(엔드카드)로는 넘기지 않는다
                g.end = g.start + min_g
                if total is not None:
                    g.end = min(g.end, total - 0.3)
            if g.end - g.start >= min_g * 0.8:
                out.append(g)
    return out
