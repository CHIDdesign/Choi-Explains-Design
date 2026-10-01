"""이벤트 목록 — 완성본에서 화면에 일어나는 모든 일을 한 줄씩(타임라인 검수 입력, docs/upgrade/05b 3절).

줄 종류: CH(챕터) · SEQ(시퀀스) · G(단발 그래픽) · HOLD · TX(전환) · SFX · CALL(콜아웃) · PEAK. 화면 글자는 따옴표 안에 그대로.
"""
from __future__ import annotations

from typing import Any, Optional

from ..util import fmt_ts


def _text(g: dict[str, Any]) -> str:
    d = g.get("data") or {}
    parts = [str(d.get(k) or "") for k in ("title", "subtitle", "body", "keyword") if d.get(k)]
    items = [str(x if not isinstance(x, dict) else x.get("title") or x.get("text") or "") for x in d.get("items") or []]
    if items:
        parts.append(" ; ".join(x for x in items if x))
    if isinstance(d.get("card"), dict):
        import re
        parts.append(" ".join(re.sub(r"<[^>]+>", " ", d["card"].get("html") or "").split())[:60])
    if isinstance(d.get("spec"), dict):
        parts.append(" ".join(str(e.get("text")) for e in d["spec"].get("elements", []) if isinstance(e, dict)
                              and e.get("text"))[:60])
    return " | ".join(p for p in parts if p)[:120]


def event_list(props: dict[str, Any], *, holds: Optional[list[tuple[float, float]]] = None,
               sequences: Optional[dict[str, str]] = None, sfx: Optional[list[dict]] = None,
               peak_t: Optional[float] = None) -> str:
    gs = sorted(props.get("graphics", []) or [], key=lambda g: g["start"])
    callouts = props.get("callouts", []) or []
    tx = props.get("transitions", []) or []
    chapters = props.get("chapters", []) or []
    seq_ids = {str((g.get("data") or {}).get("seq_id") or "") for g in gs} - {""}
    rows: list[tuple[float, str]] = []
    for c in chapters:
        rows.append((c["start"], f"CH   {c.get('number', '')} {c.get('title', '')}"))
    seen_seq: set[str] = set()
    for g in gs:
        if g.get("template") in ("chapter",):
            continue
        sid = str((g.get("data") or {}).get("seq_id") or "")
        dur = g["end"] - g["start"]
        steps = (g.get("data") or {}).get("stepAt")
        extra = f" 단계 {len(steps)}(낱말에서)" if steps else ""
        if sid:
            if sid in seen_seq:
                rows.append((g["start"], f"     └ {g.get('template')} {dur:4.1f}s \"{_text(g)}\""))
                continue
            seen_seq.add(sid)
            n = sum(1 for x in gs if str((x.get("data") or {}).get("seq_id") or "") == sid)
            rows.append((g["start"], f"SEQ  {sid} {(sequences or {}).get(sid, '')} 샷 {n} · {g.get('template')} "
                                     f"{g.get('layout')} {dur:4.1f}s \"{_text(g)}\""))
        else:
            rows.append((g["start"], f"G    {g.get('id')} {g.get('template')} {g.get('layout')} {dur:4.1f}s{extra} "
                                     f"\"{_text(g)}\""))
    for a, b in holds or []:
        rows.append((a, f"HOLD {b - a:4.1f}s 얼굴(그래픽·효과음 없음)"))
    for t in tx:
        rows.append((t["t"], f"TX   {t.get('type')}"))
    for c in callouts:
        rows.append((c["start"], f"CALL \"{c.get('text', '').replace(chr(10), ' ')}\""))
    for x in sfx or []:
        rows.append((x["t"], f"SFX  {x.get('category')}"))
    if peak_t is not None:
        rows.append((peak_t, "PEAK 정점"))
    head = (f"# 길이 {fmt_ts(float(props.get('duration', 0)))} · 챕터 {len(chapters)} · 그래픽 {len(gs)} · 시퀀스 {len(seq_ids)} · "
            f"홀드 {len(holds or [])} · 전환 {len(tx)} · 효과음 {len(sfx or [])} · 콜아웃 {len(callouts)}")
    return "\n".join([head] + [f"{fmt_ts(t)}  {line}" for t, line in sorted(rows, key=lambda r: r[0])])
