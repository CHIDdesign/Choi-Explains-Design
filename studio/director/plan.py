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
EXTRA_DATA_KEYS = ("credit", "src", "kind", "kenburns", "stock_url", "logo")

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
        if not isinstance(spec, dict) or not clean_spec(spec, 16.0):
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
    if tn == "photo" and g.get("wiki"):
        out["wiki"] = True   # 위키백과 전용(고유명사): 못 찾으면 스톡으로 넘기지 않고 뺀다
    if tn == "photo":
        # 고유명사의 종류(자료 리서처가 문맥으로 정함: person → 품위 있는 초상, brand → 로고)와 영어 이름(로고 찾기)
        for k in ("entity", "name_en"):
            if g.get(k):
                out[k] = str(g[k])[:80]
        if g.get("logo"):
            out["logo"] = True
    if tn == "photo" and g.get("subtitle") and "image" in out and not out.get("image_en"):
        pass
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
        "energy_spans": [],                      # ⚡ 펀치 구간(젠틀 규칙을 잠시 푸는 특정 부분)
        "highlights": [],                        # 🎬 오프닝 하이라이트(본편 앞 콜드 오픈) 발화들
        "title": str(raw.get("title", "") or "").strip(),       # 🎬 화면 타이틀
        "bgm_mood": str(raw.get("bgm_mood", "") or ""),
        "shorts_bgm_mood": str(raw.get("shorts_bgm_mood", "") or ""),
    }
    for c in raw.get("chapters", []) or []:
        if isinstance(c, dict) and str(c.get("title", "")).strip():
            item = {"seg": _nearest(kept, c.get("seg")), "title": str(c["title"]).strip()}
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
    for e in (raw.get("energy_spans", []) or [])[:3]:
        if not isinstance(e, dict):
            continue
        a, b = _nearest(kept, e.get("start_seg")), _nearest(kept, e.get("end_seg", e.get("start_seg")))
        if a is None or b is None:
            continue
        if b < a:
            a, b = b, a
        plan["energy_spans"].append({"start_seg": a, "end_seg": b, "reason": str(e.get("reason", "") or "")[:60]})

    for h in raw.get("highlights", []) or []:
        seg = h.get("seg") if isinstance(h, dict) else h
        if seg in kept and seg not in kept[:2] and not any(x["seg"] == seg for x in plan["highlights"]):
            plan["highlights"].append({"seg": seg, "reason": str((h.get("reason", "") if isinstance(h, dict) else "") or "")[:60]})
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
                     log: Any = None) -> list[dict[str, Any]]:
    """숏폼 기획 정리. **제대로 된 한 편**이 우선: 이해 가능성(short_coherence)이 낮으면 연속 구간으로 고치고,
    둘째 편은 첫 편과 다른 구간이면서 점수 8 이상일 때만 남긴다(채널 피드백: 둘을 억지로 채우지 말 것)."""
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
