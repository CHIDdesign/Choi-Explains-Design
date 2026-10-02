"""🎼 음악 큐 시트 → 편집 시각(docs/upgrade/04_음악_사운드_엔진_v2.md 3절).

음악 감독(`prompts/agents/music_supervisor.md`, 스키마 MUSIC)은 발화 번호로 "어디서 들어오고 나가고, 어디에 없는지"를 낸다.
여기서 그것을 초로 옮긴다:
  · start_seg −1 = 0초, 챕터의 첫 발화면 챕터 카드 등장 −0.3초 · end_seg −1 = 영상 끝, 아니면 그 발화 끝 +0.4초
  · 지워진 발화는 가장 가까운 남은 발화로 · silences(와 얼굴 홀드·강도 3 순간)는 큐보다 우선 — 겹치는 큐를 자른다
  · 12초 미만으로 쓴 큐는 버린다 — 침묵이 큐 안을 자르면 그건 쉼이다: 남은 조각은 4초 이상이면 산다
  · 큐 사이 틈이 4초 미만이면 앞 큐를 이어 붙인다(into_next)
한 영상 한 곡이라 큐는 곡을 고르지 않는다 — 같은 곡이 큐 안에서만 들린다(나머지는 침묵이 곧 큐다).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

SUITES = ("felt", "analog", "brush", "air")
ROLES = ("theme", "bed", "air", "reprise")
ENTRIES = ("downbeat", "fade_in")
EXITS = ("ending", "fade_bar", "into_next")
MIN_CUE = 12.0
MIN_PIECE = 4.0       # 침묵이 자른 큐의 남은 조각(이보다 짧으면 버린다)
JOIN_GAP = 4.0


@dataclass
class MusicCue:
    id: str
    start: float
    end: float
    role: str = "bed"
    energy: int = 1
    entry: str = "fade_in"
    exit: str = "fade_bar"
    why_in: str = ""
    why_out: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _int(v: Any, default: int = -1) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def clean_music(raw: Any, valid: list[int]) -> dict[str, Any]:
    """계획 정규화(normalize_long) — enum 밖 값은 기본값, 발화 번호는 남은 발화로(−1 은 그대로). 비면 {}."""
    if not isinstance(raw, dict) or not raw:
        return {}

    def seg(v: Any) -> int:
        s = _int(v)
        if s == -1 or not valid:
            return -1
        return s if s in valid else min(valid, key=lambda x: (abs(x - s), x))
    cues = []
    for i, c in enumerate(raw.get("cues") or []):
        if not isinstance(c, dict):
            continue
        cues.append({"id": str(c.get("id") or f"m{i + 1}")[:8], "start_seg": seg(c.get("start_seg")),
                     "end_seg": seg(c.get("end_seg")), "role": c.get("role") if c.get("role") in ROLES else "bed",
                     "energy": max(0, min(5, _int(c.get("energy"), 1))),
                     "entry": c.get("entry") if c.get("entry") in ENTRIES else "fade_in",
                     "exit": c.get("exit") if c.get("exit") in EXITS else "fade_bar",
                     "why_in": str(c.get("why_in") or "")[:120], "why_out": str(c.get("why_out") or "")[:120]})
    silences = [{"start_seg": seg(x.get("start_seg")), "end_seg": seg(x.get("end_seg")), "why": str(x.get("why") or "")[:120]}
                for x in raw.get("silences") or [] if isinstance(x, dict)]
    sh = raw.get("shorts") if isinstance(raw.get("shorts"), dict) else {}
    return {"suite": raw.get("suite") if raw.get("suite") in SUITES else "felt",
            "suite_reason": str(raw.get("suite_reason") or "")[:160],
            "fit_score": max(0, min(10, _int(raw.get("fit_score"), 7))),
            "describe": str(raw.get("describe") or "")[:200], "tempo_bpm": max(0, min(200, _int(raw.get("tempo_bpm"), 0))),
            "cues": cues, "silences": silences,
            "hero": [{"seg": seg(h.get("seg")), "kind": h.get("kind") if h.get("kind") in ("ident", "tonal") else "tonal",
                      "why": str(h.get("why") or "")[:120]} for h in raw.get("hero") or [] if isinstance(h, dict)][:3],
            "shorts": {"role": sh.get("role") if sh.get("role") in ("bed", "air", "none") else "air",
                       "energy": max(0, min(3, _int(sh.get("energy"), 1))), "note": str(sh.get("note") or "")[:160]},
            "notes": str(raw.get("notes") or "")[:200], "by": str(raw.get("by") or "ai")[:8]}


def _cut(spans: list[tuple[float, float]], holes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = list(spans)
    for a, b in holes:
        nxt = []
        for s, e in out:
            if b <= s or a >= e:
                nxt.append((s, e))
                continue
            if a > s:
                nxt.append((s, a))
            if b < e:
                nxt.append((b, e))
        out = nxt
    return out


def resolve(music: dict[str, Any], seg_t: dict[int, tuple[float, float]], total: float, *,
            chapter_starts: list[float] = (), holds: list[tuple[float, float]] = (),
            strong: list[tuple[float, float]] = (), min_len: float = MIN_CUE, min_piece: float = MIN_PIECE,
            join_gap: float = JOIN_GAP) -> tuple[list[MusicCue], list[tuple[float, float]]]:
    """큐 시트 → (큐 목록(초), 침묵 구간(초)). strong: 강도 3 순간의 그 문장(시작, 끝) — 시작 2.5초 전부터 비운다."""
    if not music or not seg_t:
        return [], []
    ids = sorted(seg_t)

    def t_of(seg: int, end: bool) -> float:
        if seg == -1:
            return total if end else 0.0
        s = seg if seg in seg_t else min(ids, key=lambda x: (abs(x - seg), x))
        a, b = seg_t[s]
        if end:
            return min(total, b + 0.4)
        for c in chapter_starts:          # 챕터의 첫 발화면 챕터 카드에 맞춰 들어온다
            if 0.0 <= a - c <= 3.5:
                return max(0.0, c - 0.3)
        return a
    silences = [(t_of(x["start_seg"], False), t_of(x["end_seg"], True)) for x in music.get("silences") or []]
    silences += [(a, b) for a, b in holds]
    silences += [(max(0.0, a - 2.5), b + 0.6) for a, b in strong]
    silences = [(a, b) for a, b in silences if b > a]
    cues: list[MusicCue] = []
    for c in music.get("cues") or []:
        a, b = t_of(c["start_seg"], False), t_of(c["end_seg"], True)
        if b - a < min_len:            # 쓴 그대로 12초가 안 되는 큐는 버린다(짧은 큐가 잦으면 산만하다)
            continue
        for s, e in _cut([(a, b)], silences):
            if e - s < min_piece:
                continue
            cues.append(MusicCue(c["id"], round(s, 2), round(e, 2), c["role"], c["energy"], c["entry"], c["exit"],
                                 c.get("why_in", ""), c.get("why_out", "")))
    cues.sort(key=lambda q: q.start)
    merged: list[MusicCue] = []
    for q in cues:                         # 겹치면 앞 큐가 이긴다
        if merged and q.start < merged[-1].end:
            q.start = merged[-1].end
            if q.end <= q.start:
                continue
        merged.append(q)
    keep = [q for q in merged if q.end - q.start >= min_piece]
    for p, q in zip(keep, keep[1:]):      # 짧은 틈은 잇는다(편성만 바뀌는 것처럼)
        if 0 < q.start - p.end < join_gap and not any(a < q.start and b > p.end for a, b in silences):
            p.end = q.start
            p.exit = "into_next"
    return keep, silences


def occupancy(cues: list[MusicCue], total: float) -> float:
    return sum(q.end - q.start for q in cues) / total if total else 0.0


def fallback_music(chapter_segs: list[int], title_seg: int, last_seg: int, *, bed_len_segs: int = 3,
                   reprise_seg: Optional[int] = None) -> dict[str, Any]:
    """음악 감독이 없을 때의 규칙 큐 시트(04 문서 8절): 오프닝~타이틀 theme, 챕터 첫 발화부터 짧게 bed, 마지막 reprise,
    나머지 침묵. reprise_seg: 엔딩 큐가 들어올 발화(끝에서 20초쯤 앞 — 마지막 발화 하나로는 12초 최소 길이에 못 미쳐
    버려진다). 없으면 last_seg."""
    cues = [{"id": "m1", "start_seg": -1, "end_seg": title_seg if title_seg >= 0 else (chapter_segs[0] if chapter_segs else -1),
             "role": "theme", "energy": 2, "entry": "downbeat", "exit": "fade_bar",
             "why_in": "훅과 타이틀", "why_out": "본론 첫 설명 앞"}]
    for i, s in enumerate(chapter_segs[1:], start=2):
        cues.append({"id": f"m{i}", "start_seg": s, "end_seg": s + bed_len_segs, "role": "bed", "energy": 1,
                     "entry": "fade_in", "exit": "fade_bar", "why_in": "챕터 전환", "why_out": "설명이 시작된다"})
    cues.append({"id": f"m{len(cues) + 1}", "start_seg": last_seg if reprise_seg is None else reprise_seg, "end_seg": -1,
                 "role": "reprise", "energy": 2,
                 "entry": "fade_in", "exit": "ending", "why_in": "엔딩", "why_out": "종지"})
    return {"suite": "felt", "suite_reason": "규칙 기본", "fit_score": 7, "describe": "", "tempo_bpm": 0, "cues": cues,
            "silences": [], "hero": [], "shorts": {"role": "air", "energy": 1, "note": ""}, "notes": "규칙 큐 시트",
            "by": "rule"}


def cue_windows(cues: list[MusicCue], total: float, step: float = 0.01) -> "Any":
    """10ms 해상도의 큐 진폭 창(0~1): 큐 밖 0, 시작은 entry(downbeat 0.3초 · fade_in 2초), 끝은 exit(fade_bar 2초 ·
    ending 3초 · into_next 0.8초) 코사인."""
    import numpy as np
    n = int(np.ceil(total / step)) + 1
    w = np.zeros(n, np.float32)
    for q in cues:
        i0, i1 = max(0, int(q.start / step)), min(n, int(q.end / step))
        if i1 <= i0:
            continue
        seg = np.ones(i1 - i0, np.float32)
        fi = min(len(seg) // 2, int((0.3 if q.entry == "downbeat" else 2.0) / step))
        fo = min(len(seg) // 2, int({"ending": 3.0, "into_next": 0.8}.get(q.exit, 2.0) / step))
        if fi > 0:
            seg[:fi] *= 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fi, dtype=np.float32))
        if fo > 0:
            seg[-fo:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, fo, dtype=np.float32))
        w[i0:i1] = np.maximum(w[i0:i1], seg)
    return w


def plan_cues(cues: list[MusicCue]) -> list[dict[str, Any]]:
    return [q.to_dict() for q in cues]


def from_dicts(items: Optional[list[dict[str, Any]]]) -> list[MusicCue]:
    out = []
    for d in items or []:
        try:
            out.append(MusicCue(**{k: d[k] for k in MusicCue.__dataclass_fields__ if k in d}))
        except TypeError:
            continue
    return out
