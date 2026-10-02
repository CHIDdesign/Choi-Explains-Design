"""증거 항목 + 조달 결과 → 계획 그래픽(03 문서 6-2 merge_plan).

- 지나가는 언급(pip) → 얼굴 옆 자료 사진(`photo` — 기존 경로: 종이 메모 위 사진·로고 카드)
- 그 밖 → `evidence` 템플릿(전면: hero · full · archive_card · doc_highlight · browser_frame · grid · compare_pair)
- 스톡 → `broll`(src 가 이미 채워진 채)
- 못 구함 → 사다리 끝: 자료 카드(keyword 타이포 카드) · code_drawn(모션 디자이너에게) · 얼굴(아무것도 안 넣음)
화면 글자는 리서처의 label(주장)·caption(사실)뿐 — 검색어·연출 메모·종류(kind)는 화면에 가지 않는다(게이트 B3~B5).
"""
from __future__ import annotations

from typing import Any

from ..director.plan import type_card
from ..util import LogFn, noop_log
from .ladder import FULLSCREEN, clean_item, drawn_treatment

TIER_WORST = {"own": 0, "made": 0, "A": 1, "A-sa": 2, "stock": 2, "B": 3, "C": 4}
EVIDENCE_KEYS = ("need", "role", "subject", "claim", "must_show", "avoid", "count", "treatment", "tier_max", "fallback",
                 "priority", "focus", "sequence_id", "local_file")


def _g(template: str, layout: str, start: int, end: int, word: str = "", **kw: Any) -> dict[str, Any]:
    g = {"template": template, "layout": layout, "start_seg": start, "end_seg": end, "start_word": word,
         "title": "", "subtitle": "", "body": "", "items": [], "title_b": "", "items_b": [], "highlight": -1,
         "author": "", "source": "", "image": "", "reason": ""}
    g.update(kw)
    return g


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
                   stock={"kind": st.get("kind") or it["stock"].get("kind") or "photo",
                          "query_en": it["stock"].get("query_en", ""), "query_ko": it["stock"].get("query_ko", ""),
                          "purpose": str(it.get("claim", ""))[:60], "must_show": it.get("must_show", "")},
                   src=st.get("src", ""), kind=st.get("kind", "photo"), credit=st.get("credit", ""),
                   stock_url=st.get("url", ""), **common)
            if st.get("kind") == "photo":
                g["kenburns"] = "in"
            graphics.append(g)
            continue
        assets = [a for a in o.get("assets") or [] if isinstance(a, dict) and a.get("src")][: it["count"]]
        if assets or o.get("archive"):
            tier = worst_tier(assets) if assets else "made"
            kind0 = str(assets[0].get("kind") or "photo") if assets else ""
            t = drawn_treatment(it["treatment"], len(assets), tier, kind0) if assets else "archive_card"
            if t == "pip" and kind0 in ("photo", "logo"):
                a = assets[0]
                g = _g("photo", "pip", s, s, word, title=it.get("label") or name, image=a.get("mat_src") or a["src"],
                       body=it.get("caption", ""), credit=a.get("credit", ""), resolved=True, **common)
                if kind0 == "logo":
                    g["logo"] = True
                if a.get("mat_src"):
                    g["mat"] = True
                graphics.append(g)
                continue
            archive = o.get("archive")
            if t == "archive_card" and archive is None:
                archive = _photo_archive(it, o)
            credit = " · ".join(dict.fromkeys(a.get("credit", "") for a in assets if a.get("credit"))) \
                or str(o.get("credit") or "")
            graphics.append(_g("evidence", "fullscreen", s, e, word, title=it.get("label", ""),
                               body=it.get("caption", ""), assets=assets, treatment=t, archive=archive, tier=tier,
                               credit=credit[:120], caption=it.get("caption", ""), **common))
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
    return graphics, drawn


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
    if drawn:
        out.append("\n## 재현 요청(code_drawn) — 실물이 없어 선으로 재현해야 하는 것. 모션 장면으로 만든다")
        out += [f"- S{d['start_seg']}–S{d['end_seg']} 「{d.get('name') or ''}」 {d.get('claim', '')} · 그릴 것: "
                f"{d.get('must_show', '')}" + (f" · 시퀀스 {d['sequence_id']}" if d.get("sequence_id") else "")
                for d in drawn]
    return "\n".join(out)


def props_credits(graphics: list[dict[str, Any]]) -> list[str]:
    """완성 props 의 증거 자료 출처(설명란용 credit_full — 없으면 화면용) + 출처 카드의 DOI 링크."""
    out: list[str] = []
    for g in graphics:
        d = g.get("data") or {}
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
        elif t == "photo" and d.get("image"):
            rows.append({**base, "자산": d["image"], "등급": "", "라이선스": d.get("credit", ""), "크기": "",
                         "출처": d.get("credit", ""), "출처 URL": "", "대체": "로고" if d.get("logo") else "", "인용 사유": ""})
        elif t == "broll" and d.get("src"):
            rows.append({**base, "자산": d["src"], "등급": "stock", "라이선스": d.get("credit", ""), "크기": "",
                         "출처": d.get("credit", ""), "출처 URL": d.get("stock_url", ""), "대체": "", "인용 사유": ""})
    return rows
