"""대본 충실 보증 — 대본을 받았으면 대본의 모든 문장이 완성 영상에 들어가야 한다.

편집 단계는 여럿이 말을 지운다: 대본 맞추기(같은 대목을 여러 번 말한 테이크 중 하나만), 단어 정리(다시 말한 앞부분·추임새),
✂️ 편집 감독의 drop, 편집 검사(다시 받아 적어 남은 되풀이를 한 번 더). 각각은 '같은 말이 다른 곳에 남아 있다'고 믿고
지우지만, 그 믿음이 틀리면(비슷한 문장을 같은 대목으로 오인, 나열하는 병렬 문장을 되풀이로 오인, 인식이 틀려 대본 일치
점수가 낮은 문장을 애드리브로 오인) 대본 문장이 통째로 사라진다 — 채널 주인: "잘려서 없어진 내용이 한둘이 아니다".

여기서는 단계마다의 판단을 믿지 않고 **결과**를 본다: 대본 문장마다 편집본(남긴 단어를 시간순으로 이은 글)에서 그
문장의 글자가 얼마나 들리는지 재고(coverage), 모자라면 원본 녹음에서 그 문장을 말한 곳(가장 잘 맞고, 앞뒤 문장 사이에
있고, 같으면 나중 테이크)을 찾아 되살린다(find_restore). 녹음 어디에도 없는 문장(말하지 않았거나 인식 실패)은 리포트에 남긴다.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from rapidfuzz import fuzz

from ..models import Word
from .align import norm

COVERED = 0.7          # 이만큼 들리면 그 문장은 편집본에 있다(인식 오차 감안 — 온전한 문장은 보통 0.85 이상)
MIN_GAIN = 0.25        # 되살린 뒤 이만큼은 더 들려야 되살린다(엉뚱한 곳을 붙이지 않게)
MIN_CHARS = 5          # 이보다 짧은 문장(“네.”)은 따지지 않는다


@dataclass
class Sentence:
    idx: int
    text: str
    n: str                              # norm(text)


@dataclass
class Restore:
    sentence: int
    text: str
    start: float
    end: float
    words: list[Word] = field(default_factory=list)
    ratio: float = 0.0                  # 그 테이크가 문장 글자를 얼마나 담는가


def sentences_of(sentences: Iterable[tuple[int, int, str]]) -> list[Sentence]:
    out = []
    for i, (_, _, text) in enumerate(sentences):
        n = norm(text)
        if len(n) >= MIN_CHARS:
            out.append(Sentence(i, text.strip(), n))
    return out


def _stream(words: Sequence[Word]) -> tuple[str, list[int]]:
    chars: list[str] = []
    owner: list[int] = []
    for i, w in enumerate(words):
        for ch in norm(w.text):
            chars.append(ch)
            owner.append(i)
    return "".join(chars), owner


def _matched(sn: str, text: str) -> tuple[int, list[int]]:
    """문장(sn)의 글자 중 text 에 순서대로 맞는 글자 수와, 맞은 text 쪽 글자 위치들."""
    sm = difflib.SequenceMatcher(None, sn, text, autojunk=False)
    pos: list[int] = []
    for bl in sm.get_matching_blocks():
        if bl.size >= 2 or (bl.size == 1 and len(sn) <= 8):
            pos.extend(range(bl.b, bl.b + bl.size))
    return len(pos), pos


GLOBAL = 0.8           # 순서를 벗어난 곳(편집본 전체)에서 찾을 때는 더 엄격하게 — 비슷한 다른 문장('디자인은 … 시작합니다')을
                       # 그 문장으로 착각해 빠진 문장을 '있다'고 보지 않게


def coverage(sents: list[Sentence], words: Sequence[Word]) -> list[float]:
    """대본 문장마다 편집본(words, 재생 순서)에서 들리는 비율 0~1. 커서(앞 문장이 끝난 곳)를 따라가며 가까운 곳에서 찾고,
    없으면 전체에서(그때는 GLOBAL 이상만 인정)."""
    text, _ = _stream(words)
    out: list[float] = []
    cursor = 0
    for s in sents:
        best, best_end = 0.0, cursor
        windows = [(max(0, cursor - 60), min(len(text), cursor + 4 * len(s.n) + 400), COVERED),
                   (0, len(text), GLOBAL)]
        for lo, hi, need in windows:
            win = text[lo:hi]
            if len(win) < len(s.n) // 2 or not win:
                continue
            if len(win) >= len(s.n):
                al = fuzz.partial_ratio_alignment(s.n, win)
                a, b = (al.dest_start, al.dest_end) if al else (0, len(win))
            else:
                a, b = 0, len(win)
            pad = max(6, len(s.n) // 3)
            sub_lo = max(0, a - pad)
            sub = win[sub_lo:min(len(win), b + pad)]
            m, pos = _matched(s.n, sub)
            r = m / len(s.n)
            if r < need:
                r = min(r, COVERED - 0.01) if need > COVERED else r     # 전체 검색의 어중간한 일치는 '빠짐'으로
            if r > best:
                best, best_end = r, lo + sub_lo + (max(pos) + 1 if pos else 0)
            if best >= COVERED:
                break
        if best >= COVERED:
            cursor = max(cursor, best_end)
        out.append(round(best, 3))
    return out


def find_restore(s: Sentence, runs: list[list[Word]], *, in_edit, after: float = -1.0, before: float = 1e18
                 ) -> Optional[Restore]:
    """문장 s 를 말한 곳을 runs(원본 발화·이웃 발화 묶음, 단어 시간순)에서 찾는다. 맞는 단어 구간(첫 맞은 단어 ~ 마지막)이
    문장 글자의 60% 이상을 담고, 그 구간 글자의 절반 이상이 문장과 맞을 때만. 고르는 순서: 많이 담은 것(5% 단위) → 일부가
    이미 편집본에 있는 테이크(지워진 단어만 채움) → 앞뒤 문장 사이(after~before)에 있는 것 → 나중 테이크.
    in_edit(word) 가 참인 단어는 이미 편집본에 있다. 편집본에 통째로 있는 테이크가 거의 같은 만큼 담으면 None(이미 있음)."""
    best: Optional[tuple[tuple, Restore]] = None
    present = 0.0          # 이미 편집본에 통째로 있는 테이크가 이 문장을 담는 정도(인식이 틀려 coverage 가 낮았을 뿐인 경우)
    for run in runs:
        if not run:
            continue
        text, owner = _stream(run)
        if len(text) < len(s.n) // 2:
            continue
        m, pos = _matched(s.n, text)
        ratio = m / len(s.n)
        if ratio < 0.6 or not pos:
            continue
        i0, i1 = owner[min(pos)], owner[max(pos)]
        span_chars = sum(len(norm(w.text)) for w in run[i0:i1 + 1])
        if m / max(1, span_chars) < 0.5:
            continue
        ws = run[i0:i1 + 1]
        if all(in_edit(w) for w in ws):
            present = max(present, ratio)
            continue
        ordered = after - 0.5 <= ws[0].start and ws[-1].end <= before + 0.5
        touches = any(in_edit(w) for w in ws)      # 일부가 이미 편집본에 있는 테이크(지워진 단어만 채우면 된다)
        key = (round(ratio * 20), touches, ordered, ws[0].start)
        if best is None or key > best[0]:
            best = (key, Restore(s.idx, s.text, ws[0].start, ws[-1].end, list(ws), round(ratio, 3)))
    if best is None or present >= min(COVERED, best[1].ratio - 0.1):
        return None            # 그 문장은 이미 편집본에 있다(같은 말을 두 번 넣지 않는다)
    return best[1]


def runs_of(groups: list[list[Word]], *, join_gap: float = 2.5) -> list[list[Word]]:
    """발화 묶음 + 이웃 두 발화를 이은 묶음(한 문장을 쉬었다 이어 말해 발화가 둘로 나뉜 경우)."""
    groups = [sorted(g, key=lambda w: w.start) for g in groups if g]
    groups.sort(key=lambda g: g[0].start)
    out = list(groups)
    for a, b in zip(groups, groups[1:]):
        if b[0].start - a[-1].end <= join_gap:
            out.append(a + b)
    return out


def neighbors(i: int, cov: list[float], times: list[Optional[tuple[float, float]]]) -> tuple[float, float]:
    """문장 i 앞뒤로 편집본에 있는 문장의 원본 시각 — 되살릴 테이크가 그 사이에 있으면 순서가 맞다."""
    after = max((times[k][1] for k in range(i) if cov[k] >= COVERED and times[k]), default=-1.0)
    before = min((times[k][0] for k in range(i + 1, len(cov)) if cov[k] >= COVERED and times[k]), default=1e18)
    return after, before


def sentence_times(sents: list[Sentence], words: Sequence[Word]) -> list[Optional[tuple[float, float]]]:
    """편집본 단어(원본 시각)에서 문장마다 가장 잘 맞는 곳의 원본 시각 — 순서 판단용(대략이면 된다)."""
    text, owner = _stream(words)
    out: list[Optional[tuple[float, float]]] = []
    for s in sents:
        if len(text) < len(s.n):
            out.append(None)
            continue
        al = fuzz.partial_ratio_alignment(s.n, text)
        if not al or al.score < 60 or al.dest_end <= al.dest_start:
            out.append(None)
            continue
        w0, w1 = words[owner[al.dest_start]], words[owner[min(len(owner) - 1, al.dest_end - 1)]]
        out.append((w0.start, w1.end))
    return out


def present_ratio(s: Sentence, runs: list[list[Word]], *, in_edit, after: float = -1.0, before: float = 1e18) -> float:
    """편집본에 통째로 들어 있고 그 문장 자리(앞뒤 문장 사이)에 있는 발화 묶음이 문장 s 를 담는 정도 — 인식이 달라
    coverage 가 낮았을 뿐인지 가린다(다른 자리의 비슷한 문장은 세지 않는다)."""
    best = 0.0
    for run in runs:
        if not run or not all(in_edit(w) for w in run):
            continue
        if run[0].start < after - 0.5 or run[-1].end > before + 0.5:
            continue
        text, _ = _stream(run)
        if text:
            best = max(best, _matched(s.n, text)[0] / len(s.n))
    return best
