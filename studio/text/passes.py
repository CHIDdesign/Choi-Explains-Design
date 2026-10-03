"""대본 읽기 회차(pass) — 같은 대본을 처음부터 끝까지 두 번 이상 읽은 녹음을 가려낸다.

2026-10-01 테스트: 같은 대본을 다른 자리에서 한 번씩 찍은 원본 2개가 '나눠 찍음'으로 이어 붙어, 대본 전체가 두 번 들어갔다
(앞 6분 37초가 그래픽 없는 맨얼굴). 리테이크 묶기는 '120초 안'만 봤고, 감독의 삭제 요청은 '대본 문장'이라 거절됐다.
여기서는 전사본을 대본 위치로 그렸을 때 생기는 톱니(끝까지 갔다가 처음으로 돌아감)를 회차 경계로 본다.
설계: docs/upgrade/02_전체테이크_중복_처리_설계.md 3-1·3-2.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..models import Utterance


@dataclass
class ReadPass:
    idx: int
    utts: list[int] = field(default_factory=list)      # 발화 id(시간순)
    lo: int = 0
    hi: int = 0                                         # 덮은 대본 구간(clean 글자 인덱스)
    coverage: float = 0.0                               # 덮은 글자 수 / 대본 길이
    source: int = -1                                    # 한 회차가 한 묶음(파일)이면 그 번호, 섞였으면 -1
    score: float = 0.0                                  # choose_main_pass 가 매긴 점수

    def to_dict(self) -> dict:
        return {"idx": self.idx, "utts": [self.utts[0], self.utts[-1]] if self.utts else [], "n": len(self.utts),
                "coverage": round(self.coverage, 3), "source": self.source, "score": round(self.score, 3)}


def _covered(utts: list[Utterance], n: int, weight: Optional[bytes] = None) -> float:
    """덮은 대본 비율. weight: 글자마다 셀지(문장부호·띄어쓰기는 어느 발화도 덮지 않으니 빼야 온전한 회차가 100% 가 된다)."""
    marks = bytearray(max(1, n))
    for u in utts:
        if u.script_span:
            a, b = u.script_span
            marks[max(0, a):min(n, b)] = b"\x01" * max(0, min(n, b) - max(0, a))
    if weight is None:
        return sum(marks) / max(1, n)
    total = sum(weight) or 1
    return sum(m & w for m, w in zip(marks, weight)) / total


def detect_passes(utts: list[Utterance], n: int, *, back_jump: float = 0.35, min_cov: float = 0.25,
                  source_of: Optional[Callable[[Utterance], int]] = None, text: str = "") -> list[ReadPass]:
    """대본 위치가 크게 뒤로 돌아가는 지점에서 회차를 끊는다.
    back_jump: 지금까지의 최대 위치에서 대본 길이의 35% 이상 뒤로 가면 '다시 읽기 시작'(파일이 바뀌는 곳 ±1 발화면 20%).
    단 뒤로 간 뒤 3개 이상 발화가 그 근처에서 이어 전진해야 한다(한 문장만 다시 말한 건 리테이크).
    min_cov: 대본의 25% 미만만 덮는 조각은 회차가 아니라 부분 다시 찍기 — 앞 회차에 붙인다."""
    weight = bytes(1 if ch.isalnum() else 0 for ch in text[:n]) + bytes(max(0, n - len(text))) if text else None
    cov = lambda us: _covered(us, n, weight)    # noqa: E731
    order = sorted((u for u in utts if u.script_span and u.score >= 70), key=lambda u: u.start)
    if not order or n <= 0:
        return [ReadPass(0, [u.id for u in sorted(utts, key=lambda u: u.start)], 0, n, cov(utts))]
    cuts: list[int] = []
    peak = order[0].script_span[0]      # type: ignore[index]
    for k in range(1, len(order)):
        a = order[k].script_span[0]      # type: ignore[index]
        file_change = source_of is not None and source_of(order[k]) != source_of(order[k - 1])
        need = (0.2 if file_change else back_jump) * n
        if peak - a >= need:
            # 그 근처에서 3개 이상 이어 전진하는가
            nxt = [o.script_span[0] for o in order[k:k + 4]]   # type: ignore[index]
            if len(nxt) >= 3 and all(nxt[i] <= nxt[i + 1] + 0.05 * n for i in range(len(nxt) - 1)) and \
                    max(nxt) < peak - 0.1 * n:
                cuts.append(k)
                peak = a
                continue
        peak = max(peak, order[k].script_span[1])    # type: ignore[index]
    bounds = [0] + cuts + [len(order)]
    raw = [order[bounds[i]:bounds[i + 1]] for i in range(len(bounds) - 1)]
    # 너무 작은 조각(부분 다시 찍기)은 앞 회차에 붙인다
    merged: list[list[Utterance]] = []
    for seg in raw:
        if merged and cov(seg) < min_cov:
            merged[-1] = merged[-1] + seg
        else:
            merged.append(seg)
    if len(merged) > 1 and cov(merged[0]) < min_cov:
        merged[1] = merged[0] + merged[1]
        merged = merged[1:]
    # 대본 없는 발화(애드리브·NG)는 시간상 속한 회차에
    starts = [seg[0].start for seg in merged]
    passes: list[ReadPass] = []
    for i, seg in enumerate(merged):
        ids_set = {u.id for u in seg}
        t0 = starts[i] if i else -1e9
        t1 = starts[i + 1] if i + 1 < len(starts) else 1e18
        extra = [u.id for u in utts if u.id not in ids_set and not u.script_span and t0 <= u.start < t1]
        ids = sorted(ids_set | set(extra), key=lambda x: next(u.start for u in utts if u.id == x))
        spans = [u.script_span for u in seg if u.script_span]
        src = -1
        if source_of is not None:
            ss = {source_of(u) for u in seg}
            src = ss.pop() if len(ss) == 1 else -1
        passes.append(ReadPass(i, ids, min(a for a, _ in spans), max(b for _, b in spans), cov(seg), src))
    return passes


def choose_main_pass(passes: list[ReadPass], utts: list[Utterance], *,
                     quality: Optional[Callable[[Utterance], float]] = None, prefer: Optional[int] = None) -> int:
    """회차가 여럿일 때 주 테이크: 대본 일치·완결(커버리지)·유창성(짧은 끊김 적음)·화면 품질. 동점이면 나중 회차.
    prefer: 총괄 감독이 고른 회차(있으면 그것)."""
    if prefer is not None and 0 <= prefer < len(passes):
        return prefer
    by_id = {u.id: u for u in utts}
    best, best_key = 0, None
    for p in passes:
        us = [by_id[i] for i in p.utts if i in by_id and by_id[i].script_span]
        if not us:
            continue
        match = sum(u.score for u in us) / len(us) / 100.0
        fluent = 1.0 - sum(1 for u in us if len(u.words) <= 3) / len(us)     # 짧게 끊긴 발화가 많으면 덜 유창
        vis = (sum(quality(u) for u in us) / len(us)) if quality else 0.5
        p.score = 0.35 * match + 0.35 * min(1.0, p.coverage) + 0.15 * fluent + 0.15 * vis
        key = (round(p.score, 2), p.idx)          # 동점(소수 둘째 자리)이면 나중 회차
        if best_key is None or key > best_key:
            best, best_key = p.idx, key
    return best


# ---------------------------------------------------------------------------
# 대목(unit)마다 더 잘 나온 회차 고르기 — best_take(설계 02 3-2 '문장 단위 교체' + 3-3 'B캠')
# 채널 주인 2026-10-03: "다른 각도로 찍은 영상 중 각 장면마다 더 잘 나온 장면을 선택해서 편집해야 하는데 1번 영상만 쓴다"
# ---------------------------------------------------------------------------

@dataclass
class TakeUnit:
    idx: int
    lo: int
    hi: int                                             # 대본 clean 글자 구간
    text: str = ""                                      # 첫 문장 앞부분(리포트용)
    chosen: int = -1                                    # 고른 회차
    scores: dict[int, float] = field(default_factory=dict)
    cov: dict[int, float] = field(default_factory=dict)
    why: str = ""
    dur: float = 0.0                                    # 고른 회차로 이 대목이 차지하는 시간(초)

    def to_dict(self) -> dict:
        return {"idx": self.idx, "lo": self.lo, "hi": self.hi, "text": self.text[:24], "pass": self.chosen,
                "scores": {str(k): round(v, 3) for k, v in self.scores.items()},
                "cov": {str(k): round(v, 3) for k, v in self.cov.items()}, "why": self.why, "dur": round(self.dur, 1)}


def script_units(sentences: list[tuple[int, int, str]], clean: str, *, min_chars: int = 45,
                 max_chars: int = 220) -> list[tuple[int, int]]:
    """교차 편집의 단위(대목): 대본의 문단(줄바꿈)마다 하나 — 45자 미만(두 문장 안 됨)의 짧은 문단은 다음 문단과 합치고, 문단 구분이 없는
    긴 글은 220자쯤(서너 문장, 20~30초)마다 끊는다. 반환은 clean 글자 구간 [lo, hi)."""
    units: list[tuple[int, int]] = []
    a: Optional[int] = None
    chars = 0
    for i, (s0, e0, t) in enumerate(sentences):
        if a is None:
            a, chars = s0, 0
        chars += sum(1 for ch in t if ch.isalnum())
        last = i + 1 == len(sentences)
        para_end = (not last) and ("\n" in clean[e0:sentences[i + 1][0]] or "\n" in t.rstrip()[-1:])
        if last or (para_end and chars >= min_chars) or chars >= max_chars:
            units.append((a, e0))
            a = None
    if a is not None and sentences:
        units.append((a, sentences[-1][1]))
    return units


def unit_index(units: list[tuple[int, int]], pos: int) -> int:
    """대본 위치 → 대목 번호(경계는 다음 대목의 시작)."""
    k = 0
    for i, (lo, _) in enumerate(units):
        if pos >= lo:
            k = i
    return k


def choose_takes(passes: list[ReadPass], utts: list[Utterance], units: list[tuple[int, int]], *,
                 take_quality: Callable[[Utterance], float], start: int, text: str = "", alternate: Optional[bool] = None,
                 margin: float = 0.06, alt_margin: float = 0.03, min_hold_s: float = 20.0, min_cov: float = 0.6
                 ) -> list[TakeUnit]:
    """대목마다 회차를 고른다. 회차별 대목 점수 = 0.55·커버리지(그 대목의 글자를 얼마나 담았나, 0.95 면 만점)
    + 0.45·테이크 품질(take_score: 대본 일치·확신도·유창성·속도·음량·화면) − 0.10·끊긴 토막 비율(3어절 이하 발화).
    히스테리시스: 지금 회차가 그 대목을 60% 미만으로 담으면 바꾸고, 다른 회차가 0.06 넘게 나으면 바꾸고, 그 밖에는 유지 —
    단 회차가 다른 파일(다른 구도)에서 왔으면(alternate) 20초 넘게 한 회차가 이어진 뒤 비슷하게 좋은(−0.03 안) 다른
    회차로 교차한다(다시점 교차 편집처럼 구도가 바뀌어 보인다). 같은 파일을 두 번 읽은 것이면 품질로만 고른다."""
    if alternate is None:
        srcs = {p.source for p in passes}
        alternate = all(p.source >= 0 for p in passes) and len(srcs) > 1
    by_id = {u.id: u for u in utts}
    pass_of = {i: p.idx for p in passes for i in p.utts}
    n = len(text) or (max(hi for _, hi in units) if units else 1)
    weight = bytes(1 if ch.isalnum() else 0 for ch in text[:n]) + bytes(max(0, n - len(text))) if text else bytes([1]) * n
    # 회차별 대본 덮음 표시
    marks: dict[int, bytearray] = {p.idx: bytearray(n) for p in passes}
    for p in passes:
        for i in p.utts:
            u = by_id.get(i)
            if u and u.script_span:
                a, b = max(0, u.script_span[0]), min(n, u.script_span[1])
                if b > a:
                    marks[p.idx][a:b] = b"\x01" * (b - a)
    # 발화 → 대목(대본 구간 가운데)
    assigned: dict[tuple[int, int], list[Utterance]] = {}
    for p in passes:
        for i in p.utts:
            u = by_id.get(i)
            if u and u.script_span:
                k = unit_index(units, (u.script_span[0] + u.script_span[1]) // 2)
                assigned.setdefault((p.idx, k), []).append(u)
    out: list[TakeUnit] = []
    for k, (lo, hi) in enumerate(units):
        tu = TakeUnit(k, lo, hi, " ".join(text[lo:hi].split()) if text else "")      # 로그·리포트용(줄바꿈 없이)
        tot = sum(weight[lo:hi]) or 1
        for p in passes:
            cov = sum(m & w for m, w in zip(marks[p.idx][lo:hi], weight[lo:hi])) / tot
            us = assigned.get((p.idx, k), [])
            qual = sum(take_quality(u) for u in us) / len(us) if us else 0.0
            frag = sum(1 for u in us if len(u.words) <= 3) / len(us) if us else 0.0
            tu.cov[p.idx] = cov
            tu.scores[p.idx] = 0.55 * min(1.0, cov / 0.95) + 0.45 * qual - 0.10 * frag
        out.append(tu)
    cur: Optional[int] = start if any(p.idx == start for p in passes) else passes[0].idx
    hold = 0.0
    for tu in out:
        sc = tu.scores
        elig = [p for p in sc if tu.cov[p] >= min_cov] or sorted(sc, key=lambda p: (tu.cov[p], p))[-1:]
        best = max(elig, key=lambda p: (round(sc[p], 3), p))          # 동점이면 나중 회차
        pick, why = cur, "유지"
        if cur not in elig:
            pick, why = best, "지금 회차가 이 대목을 덜 담음"
        elif best != cur and sc[best] - sc[cur] > margin:
            pick, why = best, "더 잘 말한 테이크"
        elif alternate and hold >= min_hold_s and len(elig) > 1:
            alt = max((p for p in elig if p != cur), key=lambda p: (round(sc[p], 3), p))
            if sc[alt] >= sc[cur] - alt_margin:
                pick, why = alt, "교차(구도 바꾸기)"
        if pick != cur:
            hold = 0.0
        cur = pick
        tu.chosen, tu.why = int(pick), why
        us = assigned.get((pick, tu.idx), [])
        tu.dur = sum(u.end - u.start for u in us) if us else (tu.hi - tu.lo) / 5.0
        hold += tu.dur
    return out


def take_summary(units: list[TakeUnit]) -> str:
    """'1차 7대목 · 2차 5대목 · 회차 바뀜 6번'."""
    c = Counter(t.chosen for t in units)
    sw = sum(1 for a, b in zip(units, units[1:]) if a.chosen != b.chosen)
    return " · ".join(f"{k + 1}차 {v}대목" for k, v in sorted(c.items())) + f" · 회차 바뀜 {sw}번"
