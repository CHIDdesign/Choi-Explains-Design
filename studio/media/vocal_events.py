"""비언어 소리(기침·헛기침·숨·입소리) 찾기 — 컷 편집 v2(채널 주인 2026-10-02: "헛기침하는 장면이 그대로 들어갔다").

Whisper 는 기침을 단어로 적지 않는다. 그래서 '말소리(VAD)는 있는데 인식 단어가 없는 토막'이 생기고, 남길 구간은 단어 끝을
VAD 말소리 끝까지 늘리므로(cuts.py) 그 토막이 완성본에 딸려 들어갔다. 여기서는 그런 토막을 찾아 세기(dBFS)·길이로 분류만 한다
— 자를지는 ✂️ 컷 편집 총괄(Claude)이 앞뒤 말을 보고 정하고, AI 가 없을 때는 `default_cuts`(또렷하게 떨어진 짧은 파열음만).
"""
from __future__ import annotations

from typing import Any, Optional

import numpy as np

from ..models import Word

SR = 16000


def _dbfs(x: np.ndarray) -> float:
    if x.size == 0:
        return -120.0
    rms = float(np.sqrt(np.mean(np.square(x.astype(np.float32)))))
    return 20.0 * np.log10(max(rms, 1e-7))


def vocal_events(audio16k: np.ndarray, vad: list[tuple[float, float]], words: list[Word], *, min_dur: float = 0.16,
                 max_dur: float = 2.5, min_dbfs: float = -40.0, margin: float = 0.10) -> list[dict[str, Any]]:
    """VAD 말소리 안에서 인식 단어가 덮지 않는 토막 → [{id, start, end, dur, dbfs, kind, prev, next, gap_prev, gap_next}].
    kind: burst(짧고 큰 소리 — 기침·헛기침·입소리) · soft(숨·웅얼거림). margin: 단어 앞뒤로 더 덮어 주는 여유(초)."""
    ws = sorted(words, key=lambda w: w.start)
    starts = np.array([w.start for w in ws]) if ws else np.zeros(0)
    ends = np.array([w.end for w in ws]) if ws else np.zeros(0)
    out: list[dict[str, Any]] = []
    for a, b in vad:
        # 이 말소리 구간을 덮는 단어 구간(여유 포함)을 빼고 남는 토막
        covered: list[tuple[float, float]] = []
        for w in ws:
            if w.end + margin < a or w.start - margin > b:
                continue
            covered.append((max(a, w.start - margin), min(b, w.end + margin)))
        covered.sort()
        cur = a
        free: list[tuple[float, float]] = []
        for c0, c1 in covered:
            if c0 > cur:
                free.append((cur, c0))
            cur = max(cur, c1)
        if cur < b:
            free.append((cur, b))
        for s, e in free:
            dur = e - s
            if dur < min_dur or dur > max_dur:
                continue
            seg = audio16k[int(s * SR):int(e * SR)]
            db = _dbfs(seg)
            if db < min_dbfs:
                continue
            # 가장 가까운 앞·뒤 단어
            pi = int(np.searchsorted(ends, s, side="right")) - 1 if ws else -1
            ni = int(np.searchsorted(starts, e, side="left")) if ws else -1
            prev = ws[pi] if 0 <= pi < len(ws) else None
            nxt = ws[ni] if ws and 0 <= ni < len(ws) else None
            kind = "burst" if (db >= -30.0 and dur <= 0.9) else "soft"
            out.append({"id": len(out), "start": round(s, 3), "end": round(e, 3), "dur": round(dur, 3), "dbfs": round(db, 1),
                        "kind": kind, "prev": prev.text if prev else "", "next": nxt.text if nxt else "",
                        "gap_prev": round(s - prev.end, 2) if prev else 9.9, "gap_next": round(nxt.start - e, 2) if nxt else 9.9})
    return out


def default_cuts(events: list[dict[str, Any]]) -> list[int]:
    """AI 없이 자를 것: 말에서 또렷이 떨어진(앞뒤 0.25초 이상) 짧은 파열음만 — 애매한 것은 둔다(빠진 내용이 더 해롭다)."""
    return [e["id"] for e in events if e["kind"] == "burst" and e["gap_prev"] >= 0.25 and e["gap_next"] >= 0.25]


def as_removals(events: list[dict[str, Any]], ids: list[int], reasons: Optional[dict[int, str]] = None) -> list[dict[str, Any]]:
    """잘라 낼 소리 → 단어 정리(removed)와 같은 모양의 구간(cuts.py 가 keep 에서 빼고 쉼 안에서 넓힌다)."""
    want = set(ids)
    return [{"start": e["start"], "end": e["end"], "text": "(비언어 소리)", "reason": "비언어 소리" +
             (f": {(reasons or {}).get(e['id'], '')}" if (reasons or {}).get(e["id"]) else "")}
            for e in events if e["id"] in want]
