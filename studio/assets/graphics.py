"""증거 항목 + 조달 결과 → 계획 그래픽(03 문서 6-2 merge_plan).

- 지나가는 언급(pip) → 얼굴 옆 자료 사진(`photo` — 기존 경로: 종이 메모 위 사진·로고 카드)
- 그 밖 → `evidence` 템플릿(전면: hero · full · archive_card · doc_highlight · browser_frame · grid · compare_pair)
- 스톡 → `broll`(src 가 이미 채워진 채)
- 못 구함 → 사다리 끝: 자료 카드(keyword 타이포 카드) · code_drawn(모션 디자이너에게) · 얼굴(아무것도 안 넣음)
화면 글자는 리서처의 label(주장)·caption(사실)뿐 — 검색어·연출 메모·종류(kind)는 화면에 가지 않는다(게이트 B3~B5).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..director.plan import clean_overlays, credit_line, type_card
from ..director.schema import TONES
from ..util import LogFn, noop_log
from .ladder import FULLSCREEN, clean_item, drawn_treatment

COLLAGE_BEATS = 4       # 영상당 콜라주 비트(타이틀 제외) — 토크쇼를 콜라주로 채우지 않는다. 챕터 카드와 합쳐 5 안쪽
COLLAGE_GAP = 2         # 발화 2개 안쪽의 잇단 호명은 한 덩어리로
PIECES = 5
MONTAGE_MIN = 3
TIER_WORST = {"own": 0, "made": 0, "A": 1, "A-sa": 2, "stock": 2, "B": 3, "C": 4}
EVIDENCE_KEYS = ("need", "role", "subject", "claim", "must_show", "avoid", "count", "treatment", "tier_max", "fallback",
                 "priority", "focus", "sequence_id", "local_file")


def _g(template: str, layout: str, start: int, end: int, word: str = "", **kw: Any) -> dict[str, Any]:
    g = {"template": template, "layout": layout, "start_seg": start, "end_seg": end, "start_word": word,
         "title": "", "subtitle": "", "body": "", "items": [], "title_b": "", "items_b": [], "highlight": -1,
         "author": "", "source": "", "image": "", "reason": ""}
    g.update(kw)
    return g


def _collage_text(it: dict[str, Any]) -> dict[str, str]:
    """리서처 항목 → 콜라주 화면 글(연도는 대상의 연도, 큰 글자·인용은 리서처가 준 것만)."""
    out = {k: str(it.get(k) or "").strip() for k in ("display", "quote") if it.get(k)}
    year = str((it.get("subject") or {}).get("year") or "").strip()
    if year:
        out["year"] = year
    return out


def _overlays(it: dict[str, Any], marks: Any, *, second: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """리서처의 표시 + 그림을 본 비전이 준 좌표(요청의 A번호로 맞춘다) → data.overlays. second = cutout 으로 얹을 그림."""
    located = {}
    for m in marks if isinstance(marks, list) else []:
        if isinstance(m, dict) and isinstance(m.get("annotation"), int):
            located[m["annotation"]] = m
    raw = []
    for n, a in enumerate(it.get("annotations") or [], start=1):
        m = located.get(n, {})
        flat = m.get("outline") if isinstance(m.get("outline"), list) else []
        o = {**a, "box": m.get("box"), "point": m.get("point"), "poly": [flat[i:i + 2] for i in range(0, len(flat) - 1, 2)]}
        if a.get("kind") == "cutout" and second:
            o.update(image=second.get("cut") or second.get("tight") or second["src"], cut=bool(second.get("cut")), w=second.get("w"), h=second.get("h"))
        raw.append(o)
    return clean_overlays(raw)


def _marks_box(overlays: list[dict[str, Any]]) -> list[float]:
    """표시 대상 전부를 담는 상자(cover 로 잘려도 대상이 남게 초점을 맞춘다). 좌표가 없으면 []."""
    pts = []
    for o in overlays:
        if o.get("box"):
            x, y, w, h = o["box"]
            pts += [(x, y), (x + w, y + h)]
        elif o.get("point"):
            pts.append(tuple(o["point"]))
    if not pts:
        return []
    x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
    return [x0, y0, max(p[0] for p in pts) - x0, max(p[1] for p in pts) - y0]


def _merge_stacks(graphics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """잇달아 호명되는 사례(발화 2개 안)는 오림 스택 하나로 — 4장까지, 그림마다 자기 이름을 말할 때 내려앉는다."""
    drop: set[int] = set()
    last: dict[str, Any] | None = None
    for g in sorted((g for g in graphics if g["template"] == "cutout_stack"), key=lambda g: g["start_seg"]):
        if last is not None and g["start_seg"] - last["end_seg"] <= 2 and len(last["cutouts"]) + len(g["cutouts"]) <= 4:
            last["cutouts"] += g["cutouts"]
            last["end_seg"] = max(last["end_seg"], g["end_seg"])
            last["credit"] = credit_line(last["cutouts"])
            drop.add(id(g))
        else:
            last = g
    return [g for g in graphics if id(g) not in drop]


def _piece_kind(subject: dict[str, Any]) -> str:
    k = str(subject.get("kind") or "")
    return "person" if k == "person" else "place" if k in ("place", "building") else ""


def _press_mark(kind: str, it: dict[str, Any], name: str, word: str, seg: int, images: list[dict[str, Any]]) -> dict[str, Any]:
    """콜라주·몽타주 후보 표시(to_graphics 끝에서 잇단 항목을 묶는다). 낱말은 첫 그림에만 — 나머지는 렌더러가 고르게 놓는다."""
    subj = it.get("subject") or {}
    pieces = [{"image": a["src"], "orig": a["src"], "w": a.get("w"), "h": a.get("h"), "kind": _piece_kind(subj), "credit": a.get("credit", ""),
               "credit_full": a.get("credit_full", ""), "seg": seg, "word": word if i == 0 else ""} for i, a in enumerate(images)]
    sub = " · ".join(x for x in (str(subj.get("name_en") or ""), str(subj.get("year") or "")) if x)
    return {"kind": kind, "pieces": pieces, "name": it.get("label") or name, "sub": sub[:40], "display": it.get("display", "")}


def _collect_press(graphics: list[dict[str, Any]], log: LogFn) -> list[dict[str, Any]]:
    """표시된 항목을 묶어 콜라주·몽타주 하나로. 그림이 모자라면(콜라주 2장 · 몽타주 3장 미만) 또는 콜라주가 이미 많으면 원래의 전면 자료 그대로 둔다."""
    groups: list[list[dict[str, Any]]] = []
    for g in sorted((g for g in graphics if g.get("_press")), key=lambda g: g["start_seg"]):
        prev = groups[-1] if groups else None
        p, q = g["_press"], prev[-1]["_press"] if prev else None
        if prev and q["kind"] == p["kind"] and g["start_seg"] - prev[-1]["end_seg"] <= COLLAGE_GAP and sum(len(x["_press"]["pieces"]) for x in prev) + len(p["pieces"]) <= PIECES \
                and (p["kind"] == "collage" or p["display"] == q["display"]):
            prev.append(g)
        else:
            groups.append([g])
    drop: set[int] = set()
    made: list[dict[str, Any]] = []
    beats = 0
    for grp in groups:
        first = grp[0]["_press"]
        pieces = [c for x in grp for c in x["_press"]["pieces"]][:PIECES]
        montage = first["kind"] == "montage"
        if len(pieces) < (MONTAGE_MIN if montage else 2) or (not montage and beats >= COLLAGE_BEATS):
            if not montage and len(pieces) >= 2:
                log(f"🎞 콜라주 {COLLAGE_BEATS}곳을 채워 '{first['name']}' 는 전면 자료로")
            continue
        s, e = grp[0]["start_seg"], max(x["end_seg"] for x in grp)
        credit = credit_line(pieces)
        extra = {"title": first["display"]} if montage else {"name": first["name"], "name_sub": first["sub"], "disc": "mint" if beats % 3 else "orange"}
        made.append(_g("keyword_montage" if montage else "collage", "fullscreen", s, e, grp[0].get("start_word", ""), cutouts=pieces, credit=credit, reason=grp[0].get("reason", ""),
                       evidence=grp[0].get("evidence"), **extra))
        beats += 0 if montage else 1
        drop.update(id(x) for x in grp)
    out = [g for g in graphics if id(g) not in drop] + made
    for g in out:
        g.pop("_press", None)
    return sorted(out, key=lambda g: g["start_seg"])


def _real_photos(g: dict[str, Any]) -> list[dict[str, Any]]:
    """완성 props 의 그래픽 하나에서 콜라주 조각 재료(실제 사진). 인용(C 등급)은 변형·전면 금지라 재료가 되지 못한다(정책 4절)."""
    d = g.get("data") or {}
    if g.get("template") == "evidence":
        return [{"image": a["src"], "kind": "", "credit": a.get("credit", "")} for a in d.get("assets") or [] if a.get("kind") == "photo" and a.get("src") and a.get("tier") != "C"]
    if g.get("template") == "photo" and d.get("image") and not (d.get("logo") or d.get("mat") or d.get("tier") == "C"):
        return [{"image": d["image"], "kind": "", "credit": d.get("credit", "")}]
    return []


def _pressed(c: dict[str, Any], public: Path) -> dict[str, Any]:
    """조각 하나 → 망점 파일(캐시됨). 못 읽으면 원본 사진 그대로 인화지로 — 빈자리는 없다."""
    from PIL import Image
    from .cutout import press_cutout
    orig = c.get("orig") or c["image"]
    r = press_cutout(public / orig, kind=c.get("kind") or "")
    if r is None:
        return {**c, "image": orig, "orig": orig, "cut": False}
    path, cut, kind = r
    with Image.open(path) as im:
        w, h = im.size
    return {**c, "image": path.relative_to(public).as_posix(), "orig": orig, "cut": cut, "w": w, "h": h, "kind": kind}


def _press_many(pieces: list[dict[str, Any]], public: Path) -> list[dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=3) as ex:         # 한 장에 수 초(GrabCut) — 같은 원본을 두 스레드가 동시에 쓰지 않게 파일마다 한 번만
        list(ex.map(lambda c: _pressed(c, public), {c.get("orig") or c["image"]: c for c in pieces}.values()))
    return [_pressed(c, public) for c in pieces]            # 이제 캐시에서 읽는다


def _pick(pieces: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """오려진 조각을 먼저, 같은 사진은 한 번만 — 2장 안 되면 빈 목록(콜라주가 아니다). 비트의 at 은 그 비트의 시간이라 떼고 렌더러가 고르게 놓게 한다."""
    uniq = list({c["orig"]: c for c in pieces}.values())
    picked = sorted(uniq, key=lambda c: not c.get("cut"))[:n]
    return [{k: v for k, v in c.items() if k != "at"} for c in picked] if len(picked) >= 2 else []


def _press_beat(g: dict[str, Any], public: Path, log: LogFn) -> None:
    """콜라주 비트의 조각을 망점으로. 인화지는 한 화면 한 장까지라(렌더러 arrange) 둘 이상이면 호명한 인물이 사라진다 — 원본 사진을 차례로 보이는 전면 자료로 되돌린다."""
    d = g["data"]
    d["cutouts"] = _press_many(d.get("cutouts") or [], public)
    prints = sum(1 for c in d["cutouts"] if not c.get("cut"))
    log(f"🎞 콜라주 {len(d['cutouts'])}조각(오림 {len(d['cutouts']) - prints} · 인화지 {prints})")
    if prints < 2:
        return
    log("🎞 오림이 모자라 콜라주 대신 전면 자료로")
    g["template"] = "evidence"
    d["assets"] = [{"src": c["orig"], "kind": "photo", "w": c.get("w"), "h": c.get("h"), "credit": c.get("credit", ""), "credit_full": c.get("credit_full", "")} for c in d.pop("cutouts")]
    d["treatment"] = "hero"
    for k in ("name", "name_sub", "disc", "wordMarks"):
        d.pop(k, None)


def _finish_press(graphics: list[dict[str, Any]], public: Path) -> None:
    """조각을 다 고른 뒤: 주인공(렌더러 arrange 와 같은 규칙 — 첫 오린 사람, 없으면 첫 오림)만 선명하게 두고 나머지는 초점을 흐린 파일로, 몽타주 사진은 글자 뒤 밝기를 맞춘 파일로."""
    from .cutout import montage_still, press_back
    for g in graphics:
        d = g.get("data") or {}
        pieces = d.get("cutouts") or []
        if g.get("template") == "keyword_montage":
            done = [(c, montage_still(public / (c.get("orig") or c["image"]))) for c in pieces]
            good = [x for x in done if x[1] and x[1][1]]
            d["cutouts"] = [{**c, "image": r[0].relative_to(public).as_posix(), "orig": c.get("orig") or c["image"]} if r else c for c, r in (good if len(good) >= 2 else done)]
        elif pieces and g.get("template") in ("collage", "title", "chapter"):
            d["credit"] = d.get("credit") or credit_line(pieces)
            cut = [c for c in pieces if c.get("cut")]
            hero = next((c for c in cut if c.get("kind") != "place"), cut[0] if cut else pieces[0])
            d["cutouts"] = [c if c is hero or c["image"] == c.get("orig") else {**c, "image": press_back(public / c["image"], fade=c.get("kind") == "place").relative_to(public).as_posix()} for c in pieces]


def press_collages(graphics: list[dict[str, Any]], public: Path, *, log: LogFn = noop_log) -> None:
    """완성 props 를 렌더 직전에: 콜라주의 조각을 흑백 망점 오림으로 만들고, 실제 사진이 있으면 타이틀·챕터 카드도 콜라주로(챕터는 비트와 합쳐 영상당 5곳 안쪽, 타이틀은 별도)."""
    for g in [g for g in graphics if g.get("template") == "collage"]:
        _press_beat(g, public, log)
    beats = [g for g in graphics if g.get("template") == "collage"]
    pool = [c for g in beats for c in g["data"].get("cutouts") or []]
    order = sorted(graphics, key=lambda g: float(g.get("start", 0) or 0))
    title = next((g for g in order if g.get("template") == "title"), None)
    photos = [p for g in order for p in _real_photos(g)]
    if title is not None and (pool or photos):
        got = _pick(pool + _press_many(photos[:6], public) if len(pool) < 4 else pool, 4)
        if got:
            title.setdefault("data", {})["cutouts"] = got
    cards = [g for g in order if g.get("template") == "chapter" and g.get("layout") == "fullscreen"]
    for g in cards[:max(0, 5 - len(beats))]:
        i = order.index(g)
        near = []
        for x in order[i + 1:]:
            if x.get("template") == "chapter" and x.get("layout") == "fullscreen":
                break
            near += _real_photos(x)
        got = _pick(_press_many(near[:5], public), 3) if len(near) >= 2 else []
        if got:
            g.setdefault("data", {})["cutouts"] = got
    _finish_press(graphics, public)


def press_short_hook(graphics: list[dict[str, Any]], public: Path, hook: float = 2.6, *, log: LogFn = noop_log) -> None:
    """숏폼 첫머리: 이 숏폼의 실제 사진이 2장 이상이고 앞 2.6초가 비어 있으면 콜라주로 연다(제목은 ReelShort 가 위에 얹는다 — 이름표 없음)."""
    if any(g.get("layout") == "fullscreen" and float(g.get("start", 99) or 99) < hook for g in graphics):
        return
    photos = [p for g in sorted(graphics, key=lambda g: float(g.get("start", 0) or 0)) for p in _real_photos(g)]
    for g in graphics:
        if g.get("template") == "collage":
            _press_beat(g, public, log)
            photos += g["data"].get("cutouts") or []
    got = _pick(_press_many(photos[:5], public), 4) if len(photos) >= 2 else []
    if got:
        graphics.append({"id": "hook_collage", "template": "collage", "layout": "fullscreen", "start": 0.0, "end": hook, "priority": 9, "source": "auto", "skin": "classic",
                         "data": {"cutouts": got, "credit": credit_line(got)}})
        log(f"📱 숏폼 첫머리 콜라주 {len(got)}조각")
    _finish_press(graphics, public)


def worst_tier(assets: list[dict[str, Any]]) -> str:
    tiers = [str(a.get("tier") or "") for a in assets]
    return max(tiers, key=lambda t: TIER_WORST.get(t, 1)) if tiers else "made"


def _photo_archive(it: dict[str, Any], o: dict[str, Any]) -> dict[str, Any]:
    s = it.get("subject") or {}
    rows = []
    if s.get("creator_en"):
        rows.append({"k": "작가" if s.get("kind") == "work" else "만든 이", "v": s["creator_en"]})
    if s.get("year"):
        rows.append({"k": "연도", "v": s["year"]})
    desc = ((o.get("info") or {}).get("description") or "").strip()
    if desc and len(rows) < 3:
        rows.append({"k": "무엇", "v": desc[:28]})
    return {"variant": "photo", "title": (s.get("name_ko") or s.get("name_en") or it.get("label") or "")[:24],
            "rows": rows[:3], "label": it.get("label", "")}


def to_graphics(items: list[dict[str, Any]], outcomes: list[dict[str, Any]], *,
                log: LogFn = noop_log) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """→ (그래픽, 모션 디자이너에게 넘길 code_drawn 요청)."""
    graphics: list[dict[str, Any]] = []
    drawn: list[dict[str, Any]] = []
    seen_logos: set[str] = set()      # 같은 로고는 한 영상에 한 번(2026-10-03 채널 주인: 로고가 여러 번 나오면 안 된다)
    by_i = {o.get("i", n): o for n, o in enumerate(outcomes)}
    for n, raw in enumerate(items):
        it = clean_item(raw)
        o = by_i.get(n) or {}
        try:
            s, e = int(it.get("start_seg", -1)), int(it.get("end_seg", it.get("start_seg", -1)))
        except (TypeError, ValueError):
            continue
        e = max(s, e)
        word = str(it.get("start_word") or "")
        subj = it.get("subject") or {}
        name = str(subj.get("name_ko") or subj.get("name_en") or "").strip()
        ev = {k: it.get(k) for k in EVIDENCE_KEYS if k in it}
        common = {"reason": "자료 리서처: " + str(it.get("claim", ""))[:80], "evidence": ev,
                  "sequence_id": str(it.get("sequence_id") or "")[:16]}
        if o.get("stock"):
            st = o["stock"]
            layout = "fullscreen" if it["treatment"] in FULLSCREEN else "pip"
            g = _g("broll", layout, s, e, word, title=it.get("label", ""), image=it["stock"].get("query_en", ""),
                   **_collage_text(it),
                   stock={"kind": st.get("kind") or it["stock"].get("kind") or "photo",
                          "query_en": it["stock"].get("query_en", ""), "query_ko": it["stock"].get("query_ko", ""),
                          "purpose": str(it.get("claim", ""))[:60], "must_show": it.get("must_show", "")},
                   src=st.get("src", ""), kind=st.get("kind", "photo"), credit=st.get("credit", ""),
                   stock_url=st.get("url", ""), **common)
            if layout == "fullscreen":
                # 영상의 좌표는 쓰지 않는다 — 비전은 포스터 한 장을 봤을 뿐, 표시가 닿을 때 그 자리에 대상이 있다는 보장이 없다
                g["overlays"] = _overlays(it, st.get("marks") if st.get("kind") == "photo" else None)
                if it.get("tone") in TONES:
                    g["tone"] = it["tone"]
                mb = _marks_box(g["overlays"])
                if mb:
                    g["focus"] = [mb[0] + mb[2] / 2, mb[1] + mb[3] / 2]
            if st.get("kind") == "photo":
                g["kenburns"] = "in"
                if it["treatment"] in ("collage", "cutout") or it.get("display"):
                    g["treatment"] = "collage"      # 디자인 v3: 스톡 사진도 종이 무대 위 콜라주로
                if it["treatment"] == "sequence" and it.get("display"):
                    g["_press"] = _press_mark("montage", it, name, word, s, [{"src": st.get("src"), "credit": st.get("credit", ""), "w": st.get("width"), "h": st.get("height")}])
            graphics.append(g)
            continue
        assets = [a for a in o.get("assets") or [] if isinstance(a, dict) and a.get("src")][: it["count"]]
        if assets or o.get("archive"):
            tier = worst_tier(assets) if assets else "made"
            kind0 = str(assets[0].get("kind") or "photo") if assets else ""
            if it["treatment"] == "stack" and kind0 == "photo":
                cuts = [{"image": a.get("cut") or a.get("tight") or a["src"], "cut": bool(a.get("cut")), "label": it.get("label") or name,
                         "w": a.get("w"), "h": a.get("h"), "credit": a.get("credit", ""), "credit_full": a.get("credit_full", ""),
                         "seg": s, "word": word} for a in assets[:1]]
                graphics.append(_g("cutout_stack", "overlay", s, e, word, cutouts=cuts, credit=cuts[0]["credit"], **common))
                continue
            t = drawn_treatment(it["treatment"], len(assets), tier, kind0) if assets else "archive_card"
            if t == "hero" and kind0 == "photo" and (assets[0].get("cut") or it.get("display")):
                t = "collage"      # 디자인 v3: 오린 사진·큰 글자가 있으면 바닥 타원 위 콜라주(운영자 레퍼런스)
            if kind0 == "logo":
                # 로고는 이름표다 — 전면·콜라주로 키우지 않고(큰 흰 판 가운데 작은 휘장이 12초), 같은 로고는 한 번만.
                # 그 문장 구간의 전면은 그 대상이 '하는 일'의 현장(스톡 영상)이 맡는다(자료 리서처 프롬프트 1절).
                key = str(assets[0].get("src") or name)
                if key in seen_logos:
                    log(f"🎞 '{name or it.get('label') or ''}' 로고는 이미 한 번 보였다 → 이 자리는 비움(말로 충분)")
                    continue
                seen_logos.add(key)
                if t != "pip":
                    log(f"🎞 '{name or it.get('label') or ''}' 로고는 전면({t})이 아니라 이름표(pip)로")
                    t = "pip"
            if t == "pip" and kind0 in ("photo", "logo"):
                a = assets[0]
                g = _g("photo", "pip", s, s, word, title=it.get("label") or name, image=a.get("mat_src") or a["src"],
                       body=it.get("caption", ""), credit=a.get("credit", ""), resolved=True, tier=a.get("tier", ""), **common)
                if kind0 == "logo":
                    g["logo"] = True
                if a.get("mat_src"):
                    g["mat"] = True
                graphics.append(g)
                continue
            archive = o.get("archive")
            if t == "archive_card" and archive is None:
                archive = _photo_archive(it, o)
            on_one = t in ("hero", "full", "collage", "doc_highlight") and bool(assets)      # 격자·스크롤 화면에는 좌표를 쓰지 않는다
            overlays = _overlays(it, assets[0].get("marks") if on_one else None,
                                 second=assets[1] if on_one and len(assets) > 1 else None)
            mb = _marks_box(overlays)
            if mb:                   # 좌표는 그 한 장의 것 — 다른 장으로 넘어가지 않는다(오림으로 얹는 둘째 그림만 남긴다)
                assets = assets[:2 if any(ov["kind"] == "cutout" for ov in overlays) else 1]
                assets[0] = {**assets[0], "focus": mb}
            credit = " · ".join(dict.fromkeys(a.get("credit", "") for a in assets if a.get("credit"))) \
                or str(o.get("credit") or "")
            g = _g("evidence", "fullscreen", s, e, word, title=it.get("label", ""),
                   body=it.get("caption", ""), assets=assets, treatment=t, archive=archive, tier=tier,
                   credit=credit[:120], caption=it.get("caption", ""), overlays=overlays,
                   tone=it.get("tone"), **_collage_text(it), **common)
            if kind0 == "photo" and assets and tier != "C":
                if it["treatment"] in ("collage", "cutout"):
                    g["_press"] = _press_mark("collage", it, name, word, s, assets)
                elif it["treatment"] == "sequence" and it.get("display"):
                    g["_press"] = _press_mark("montage", it, name, word, s, assets)
            graphics.append(g)
            continue
        rung = o.get("rung") or "type_card"
        if rung == "code_drawn":
            drawn.append({"start_seg": s, "end_seg": e, "start_word": word, "claim": it.get("claim", ""),
                          "must_show": it.get("must_show", ""), "name": name, "sequence_id": common["sequence_id"],
                          "why": o.get("why", "")})
            continue
        if rung == "type_card":
            card = type_card(_g("photo", "pip" if it["treatment"] == "pip" else "overlay", s, s, word,
                                title=it.get("label") or name, body=it.get("caption", "")),
                             ((o.get("info") or {}).get("description") or ""))
            if card is not None:
                card.update(common)
                card["fallback"] = "type_card"
                graphics.append(card)
                log(f"🎞 '{name or it.get('label') or it.get('claim', '')[:20]}' 자료 없음({o.get('why', '')}) → 자료 카드")
                continue
        log(f"🎞 '{name or it.get('claim', '')[:24]}' 자료 없음({o.get('why', '')}) — 얼굴로 둡니다")
    return _collect_press(_merge_stacks(graphics), log), drawn


def brief_for_motion(items: list[dict[str, Any]], outcomes: list[dict[str, Any]],
                     drawn: list[dict[str, Any]]) -> str:
    """모션 디자이너에게: 확보한 자료 목록(E번호 · 발화 · 대상 · 종류 · 해상도 · 등급) + 재현 요청(code_drawn)."""
    lines = []
    for n, (raw, o) in enumerate(zip(items, outcomes), start=1):
        it = clean_item(raw)
        got = o.get("assets") or []
        if not (got or o.get("archive") or o.get("stock")):
            continue
        what = ", ".join(f"{a.get('kind')} {a.get('w')}×{a.get('h')} {a.get('tier')}" for a in got[:3]) \
            or ("출처 카드" if o.get("archive") else f"스톡 {(o.get('stock') or {}).get('kind', '')}")
        s = it.get("subject") or {}
        lines.append(f"- E{n} S{it.get('start_seg')}–S{it.get('end_seg')} 「{s.get('name_ko') or it.get('label') or ''}」 "
                     f"{it['need']} · {it['treatment']} · {what} · {str(it.get('claim', ''))[:40]}")
    out = ["## 확보된 자료(자료 리서처 → 조달 결과) — 이 문장들에는 글자 카드를 먼저 놓지 않는다. 자료가 주인공이다."]
    out += lines or ["- (확보된 실물 자료 없음)"]
    # 조달 실패 — 예전엔 목록에서 조용히 빠져 그 자리가 얼굴로 남았다(2026-10-04 채널 주인: '없으면 비워 두겠다'는 무책임하다)
    lost = []
    for raw, o in zip(items, outcomes):
        it = clean_item(raw)
        if it["need"] == "code_drawn" or o.get("assets") or o.get("archive") or o.get("stock"):
            continue
        st = it.get("stock") or {}
        idea = st.get("query_en") or (it.get("subject") or {}).get("name_en") or ""
        lost.append(f"- S{it.get('start_seg')}–S{it.get('end_seg')} 「{str(it.get('claim', ''))[:40]}」 · 보여야 할 것: "
                    f"{str(it.get('must_show', ''))[:60]}" + (f" · 찾던 그림: {idea}" if idea else "")
                    + (f" · 못 구한 이유: {o['why']}" if o.get("why") else ""))
    if lost:
        out.append("\n## 조달 실패 — 억지로 채우지 않는다")
        out.append("실물·스톡을 못 구한 자리다. 기본은 화자가 맡는다. 그 말이 구조·흐름·변화를 설명할 때만 카드 상한 안에서 도식으로 짓는다. "
                   "없는 실물의 모양·사이트 화면을 지어 그리거나 한 문장 은유를 전면 타이포로 짓지 않는다. "
                   "같은 검색어의 그림 부품(pixabay:)을 다시 넣지 않는다 — 이미 못 찾았다.")
        out += lost[:20]
    if drawn:
        out.append("\n## 재현 요청(code_drawn) — 실물이 보여 줄 수 없는 구조를 선으로. 카드 상한 안에서만, 사이트·앱 화면이면 짓지 않는다")
        out += [f"- S{d['start_seg']}–S{d['end_seg']} 「{d.get('name') or ''}」 {d.get('claim', '')} · 그릴 것: "
                f"{d.get('must_show', '')}" + (f" · 시퀀스 {d['sequence_id']}" if d.get("sequence_id") else "")
                for d in drawn]
    return "\n".join(out)


def props_credits(graphics: list[dict[str, Any]]) -> list[str]:
    """완성 props 의 증거 자료 출처(설명란용 credit_full — 없으면 화면용) + 출처 카드의 DOI 링크."""
    out: list[str] = []
    for g in graphics:
        d = g.get("data") or {}
        if g.get("template") in ("cutout_stack", "collage", "keyword_montage"):
            out += [c.get("credit_full") or c.get("credit") for c in d.get("cutouts") or [] if c.get("credit_full") or c.get("credit")]
        if g.get("template") != "evidence":
            continue
        for a in d.get("assets") or []:
            c = a.get("credit_full") or a.get("credit") or ""
            if c:
                out.append(c)
        arc = d.get("archive") or {}
        if arc.get("variant") == "source" and d.get("credit"):
            out.append(f"{d['credit']} — {arc.get('title', '')}" + (f" ({arc['ref']})" if arc.get("ref") else ""))
    return list(dict.fromkeys(out))


def ledger_rows(graphics: list[dict[str, Any]], where: str) -> list[dict[str, Any]]:
    """자료 대장(부가자료/자료_대장.csv) 줄 — 화면에 실제로 나간 자료만(완성 props 기준)."""
    rows = []
    for g in graphics:
        d = g.get("data") or {}
        t = g.get("template")
        start, dur = float(g.get("start", 0)), float(g.get("end", 0)) - float(g.get("start", 0))
        base = {"시작": f"{where} {int(start // 60):02d}:{start % 60:05.2f}", "초": f"{dur:.1f}"}
        if t == "evidence":
            for a in d.get("assets") or []:
                rows.append({**base, "자산": a.get("src", ""), "등급": a.get("tier", ""), "라이선스": a.get("credit", ""),
                             "크기": f"{a.get('w', 0)}×{a.get('h', 0)}", "출처": a.get("credit_full") or a.get("credit", ""),
                             "출처 URL": (a.get("meta") or {}).get("ref", ""), "대체": "",
                             "인용 사유": (d.get("title") or d.get("caption") or "") if a.get("tier") == "C" else ""})
            arc = d.get("archive") or {}
            if arc and not d.get("assets"):
                rows.append({**base, "자산": f"출처 카드: {arc.get('title', '')}"[:80], "등급": "made", "라이선스": "자체 제작",
                             "크기": "", "출처": d.get("credit", ""), "출처 URL": arc.get("ref", ""), "대체": "", "인용 사유": ""})
        elif t in ("cutout_stack", "collage", "keyword_montage"):
            for c in d.get("cutouts") or []:
                rows.append({**base, "자산": c.get("image", ""), "등급": "", "라이선스": c.get("credit", ""), "크기": f"{c.get('w', 0)}×{c.get('h', 0)}",
                             "출처": c.get("credit_full") or c.get("credit", ""), "출처 URL": "", "대체": "", "인용 사유": ""})
        elif t == "photo" and d.get("image"):
            rows.append({**base, "자산": d["image"], "등급": "", "라이선스": d.get("credit", ""), "크기": "",
                         "출처": d.get("credit", ""), "출처 URL": "", "대체": "로고" if d.get("logo") else "", "인용 사유": ""})
        elif t == "broll" and d.get("src"):
            rows.append({**base, "자산": d["src"], "등급": "stock", "라이선스": d.get("credit", ""), "크기": "",
                         "출처": d.get("credit", ""), "출처 URL": d.get("stock_url", ""), "대체": "", "인용 사유": ""})
    return rows
