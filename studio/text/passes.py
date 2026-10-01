"""대본 읽기 회차(pass) — 같은 대본을 처음부터 끝까지 두 번 이상 읽은 녹음을 가려낸다.

2026-10-01 테스트: 같은 대본을 다른 자리에서 한 번씩 찍은 원본 2개가 '나눠 찍음'으로 이어 붙어, 대본 전체가 두 번 들어갔다
(앞 6분 37초가 그래픽 없는 맨얼굴). 리테이크 묶기는 '120초 안'만 봤고, 감독의 삭제 요청은 '대본 문장'이라 거절됐다.
여기서는 전사본을 대본 위치로 그렸을 때 생기는 톱니(끝까지 갔다가 처음으로 돌아감)를 회차 경계로 본다.
설계: docs/upgrade/02_전체테이크_중복_처리_설계.md 3-1·3-2.
"""
from __future__ import annotations

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
