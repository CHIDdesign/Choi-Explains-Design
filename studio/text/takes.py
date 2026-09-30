"""단어 단위 편집 정리: 되풀이한 앞부분(말 다시 시작)·추임새를 지운다.

예전 판단 단위는 '발화'(0.55초 쉼으로 나눈 덩어리)라서, Whisper 단어 시간이 쉼을 덮어 버리면
'그것의 평가가 거의 / 그것의 평가가 거의 전부처럼' 같은 되풀이가 한 덩어리로 통째로 살아남았다
(실제 업로드 영상의 음성 인식에서 확인: 3번 되풀이한 문장이 전부 남음).

여기서는 단어 열을 직접 본다.
  1) 되풀이: 문장 시작(쉼·문장 끝·추임새 뒤)에서 가까운 앞의 시도와 같은 말(2어절·4글자 이상)로 다시 시작하면,
     앞의 시도(갈라진 꼬리까지)를 지운다 — 마지막 시도가 남는다. 여러 번이면 차례로.
     '첫 번째 다이아몬드는 … / 두 번째 다이아몬드는'처럼 문장 중간부터 같은 말은 의도적 반복이라 건드리지 않는다.
  2) 추임새: 따로 떨어진 '어·음·아' 등.
결과는 남길 단어와 지운 구간 목록(이유 포함) — 편집 리포트·진단에 그대로 남는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from ..models import Word

NORM_RE = re.compile(r"[0-9A-Za-z가-힣]+")
FILLERS = {"어", "음", "으", "으음", "음음", "어어", "아", "에", "엄", "흠", "허", "어음", "음어", "아아", "에에", "그어"}
NG_WORDS = ("다시할게", "다시하겠", "다시갈게", "잠깐만", "잠시만", "처음부터", "다시다시", "아니다시")
FINAL_RE = re.compile(r"(다|요|죠|까|네)$")
PAUSE = 0.25            # 이보다 길게 쉬면 새 시도가 시작될 수 있는 자리
MAX_BACK_WORDS = 40     # 되풀이를 찾는 범위(어절)
MAX_BACK_SEC = 30.0
MAX_TAIL = 8            # 갈라진 꼬리(같은 말 뒤 다른 말)가 이 어절 수 이하면 버려진 시도로 본다
MAX_TAIL_OPEN = 20      # 꼬리가 길어도 문장이 끝나지 않았으면 이만큼까지는 버려진 시도


def ntok(text: str) -> str:
    return "".join(NORM_RE.findall(text)).lower()


def same_word(a: str, b: str) -> bool:
    """어절이 같은가 — 조사·어미가 다른 정도는 같게(어디서/어디/어디인지)."""
    if not a or not b:
        return False
    if a == b:
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n >= 2 and n >= 0.6 * min(len(a), len(b))


def is_final(w: Word) -> bool:
    t = w.text.strip()
    return bool(re.search(r"[.?!。？！]$", t)) or bool(FINAL_RE.search(ntok(t)))


@dataclass
class Removal:
    start: float
    end: float
    text: str
    reason: str

    def to_dict(self) -> dict:
        return {"start": round(self.start, 3), "end": round(self.end, 3), "text": self.text, "reason": self.reason}


def default_pause(a: Word, b: Word) -> float:
    return max(0.0, b.start - a.end)


def clean_words(words: list[Word], *, pause: Optional[Callable[[Word, Word], float]] = None,
                fillers: bool = True) -> tuple[list[Word], list[Removal]]:
    """되풀이한 앞부분과 추임새를 지운 단어 목록과 지운 구간들."""
    pause = pause or default_pause
    toks = [ntok(w.text) for w in words]
    drop = [False] * len(words)
    reason: dict[int, str] = {}

    def gap_before(i: int) -> float:
        return 99.0 if i == 0 else pause(words[i - 1], words[i])

    def is_filler(i: int) -> bool:
        return toks[i] in FILLERS

    def attempt_start(i: int) -> bool:
        """새 시도가 시작될 수 있는 자리: 맨 앞 · 쉼 뒤 · 문장 끝 뒤 · 추임새/NG 뒤."""
        if i == 0 or gap_before(i) >= PAUSE:
            return True
        p = i - 1
        while p >= 0 and drop[p]:
            p -= 1
        if p < 0:
            return True
        return is_final(words[p]) or is_filler(p) or any(k in toks[p] for k in NG_WORDS)

    # 1) 추임새
    if fillers:
        for i, t in enumerate(toks):
            if t in FILLERS:
                alone = gap_before(i) >= 0.12 or (i + 1 < len(words) and pause(words[i], words[i + 1]) >= 0.12)
                if alone or attempt_start(i) or (i + 1 < len(words) and attempt_start(i + 1)):
                    drop[i] = True
                    reason[i] = "추임새"

    # 2) 되풀이 — 왼쪽부터, 새 시도 j 마다 가까운 앞의 시도 i 를 찾는다
    live = [i for i in range(len(words)) if not drop[i] and toks[i]]
    pos = {w: k for k, w in enumerate(live)}
    for j in live:
        if drop[j]:
            continue
        j_start = attempt_start(j)
        kj = pos[j]
        best = None
        for ki in range(kj - 1, max(-1, kj - MAX_BACK_WORDS) - 1, -1):
            i = live[ki]
            if drop[i] or words[j].start - words[i].start > MAX_BACK_SEC:
                break
            # 같은 말이 몇 어절 이어지나
            k = 0
            chars = 0
            while ki + k < kj and kj + k < len(live) and same_word(toks[live[ki + k]], toks[live[kj + k]]):
                chars += len(toks[live[kj + k]])
                k += 1
            if k < 2 or chars < 4:
                continue
            strong = k >= 3 and chars >= 8
            i_start = attempt_start(i) or any(attempt_start(live[x]) for x in range(max(0, ki - 2), ki))
            # 새 시도는 보통 쉼·문장 끝 뒤에서 시작 — 쉼 없이 곧바로 고쳐 말한 경우는 같은 말이 길 때만(3어절·8글자)
            if not ((j_start and (i_start or strong)) or (strong and i_start)):
                continue
            tail = [live[x] for x in range(ki + k, kj) if not drop[live[x]]]
            if len(tail) > MAX_TAIL:
                if len(tail) > MAX_TAIL_OPEN or any(is_final(words[x]) and not _covered(toks, live, x, ki, kj)
                                                     for x in tail[:-1]):
                    continue
            cand = (k, chars, -ki)
            if best is None or cand > best[0]:
                best = (cand, ki)
        if best is None:
            continue
        ki = best[1]
        for x in range(ki, kj):
            i = live[x]
            if not drop[i]:
                drop[i] = True
                reason[i] = "되풀이(다시 말한 앞부분)"

    kept = [w for w, d in zip(words, drop) if not d]
    return kept, _spans(words, drop, reason)


def _covered(toks: list[str], live: list[int], x: int, ki: int, kj: int) -> bool:
    """문장 끝 어절 x 가 다음 시도 안에서도 다시 나오는가(같은 문장을 반복한 경우)."""
    t = toks[x]
    return any(same_word(t, toks[live[y]]) for y in range(kj, min(len(live), kj + 40)))


def _spans(words: list[Word], drop: list[bool], reason: dict[int, str]) -> list[Removal]:
    out: list[Removal] = []
    i = 0
    while i < len(words):
        if not drop[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(words) and drop[j + 1] and reason.get(j + 1) == reason.get(i):
            j += 1
        out.append(Removal(words[i].start, words[j].end, " ".join(w.text for w in words[i:j + 1]),
                           reason.get(i, "")))
        i = j + 1
    return out


def vad_pause(regions: list[tuple[float, float]]) -> Callable[[Word, Word], float]:
    """VAD(말소리 구간)로 두 단어 사이 실제 쉼을 잰다 — Whisper 단어 시간이 쉼을 덮어도 잡힌다."""
    import bisect
    starts = [r[0] for r in regions]

    def f(a: Word, b: Word) -> float:
        gap = max(0.0, b.start - a.end)
        lo, hi = a.start + 0.05, b.start
        if hi <= lo or not regions:
            return gap
        k = max(0, bisect.bisect_right(starts, lo) - 1)
        silent, t = 0.0, lo
        best = 0.0
        while k < len(regions) and regions[k][0] < hi:
            s, e = regions[k]
            if s > t:
                best = max(best, min(s, hi) - t)
            t = max(t, e)
            k += 1
        if t < hi:
            best = max(best, hi - t)
        return max(gap, best, silent)
    return f
