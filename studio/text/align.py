"""음성인식 결과 ↔ 대본 정렬.

1) 단어 스트림을 발화(문장) 단위로 나눈다.
2) 각 발화를 대본의 어느 부분인지 퍼지 매칭한다(rapidfuzz).
3) 같은 대본 구간을 여러 번 말했으면 가장 또렷한 테이크만 남긴다(NG/리테이크 제거):
   대본 일치도·완결성·인식 확신도·말더듬/추임새·말 속도·음량·최신성을 합산해 고른다.
4) "다시 할게요" 같은 메타 발화를 제거한다.
5) 매칭된 발화는 대본 문장으로 자막을 교정하고, 글자 단위 정렬로 단어 시간을 옮긴다.
6) 대본 태그를 실제 발화(시간)에 고정한다.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Optional

from rapidfuzz import fuzz

from ..models import Tag, Utterance, Word
from .script import ParsedScript

NORM_RE = re.compile(r"[0-9A-Za-z가-힣ㄱ-ㆎ]")
META_PATTERNS = [
    "다시할게", "다시하겠", "다시갈게", "다시갈께", "다시할께", "다시찍", "처음부터", "잠깐만", "잠시만",
    "엔지", "ng", "컷컷", "틀렸", "아다시", "다시다시", "한번더할게", "죄송합니다다시", "어디까지했",
]
FILLER_ONLY = {"음", "어", "아", "그", "음음", "어어", "에", "으음", "흠", "네", "자"}


def norm(text: str) -> str:
    return "".join(NORM_RE.findall(text)).lower()


def norm_with_map(text: str) -> tuple[str, list[int]]:
    out: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(text):
        if NORM_RE.match(ch):
            out.append(ch.lower())
            idx.append(i)
    return "".join(out), idx


def apply_glossary(text: str, glossary: dict[str, str]) -> str:
    for wrong, right in (glossary or {}).items():
        if wrong and wrong in text:
            text = text.replace(wrong, right)
    return text


# ----------------------------------------------------------------------------
# 1) 발화 분할
# ----------------------------------------------------------------------------

def build_utterances(words: list[Word], *, split_gap: float = 0.55, max_words: int = 28) -> list[Utterance]:
    utts: list[Utterance] = []
    cur: list[Word] = []

    def flush() -> None:
        if not cur:
            return
        text = " ".join(w.text for w in cur)
        utts.append(Utterance(id=len(utts), start=cur[0].start, end=cur[-1].end, text=text, asr_text=text,
                              words=list(cur)))
        cur.clear()

    for i, w in enumerate(words):
        if cur:
            gap = w.start - cur[-1].end
            ends_sentence = bool(re.search(r"[.?!。？！]$", cur[-1].text))
            if gap >= split_gap or (ends_sentence and gap >= 0.12) or len(cur) >= max_words:
                flush()
        cur.append(w)
    flush()
    return utts


# ----------------------------------------------------------------------------
# 2~6) 정렬
# ----------------------------------------------------------------------------

@dataclass
class AlignReport:
    matched: int = 0
    retakes: int = 0
    meta: int = 0
    unmatched: int = 0
    script_coverage: float = 0.0
    missing_sentences: list[str] | None = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class ScriptAligner:
    def __init__(self, script: ParsedScript, glossary: Optional[dict[str, str]] = None,
                 match_threshold: float = 66.0, script_text_threshold: float = 86.0, audio=None):
        self.script = script
        self.audio = audio  # 16kHz 모노(float) — 테이크 음량 비교용, 없어도 된다
        self.glossary = glossary or {}
        self.snorm, self.smap = norm_with_map(script.clean)
        self.match_threshold = match_threshold
        self.script_text_threshold = script_text_threshold

    # --------------------------------------------------------------
    def run(self, utts: list[Utterance]) -> tuple[list[Utterance], list[Tag], AlignReport]:
        rep = AlignReport()
        has_script = len(self.snorm) > 20
        if has_script:
            self._match_all(utts)
        self._mark_meta(utts)
        if has_script:
            self._mark_retakes_by_script(utts)
        self._mark_retakes_by_similarity(utts)
        for u in utts:
            if not u.kept:
                continue
            if has_script and u.script_span and u.score >= self.script_text_threshold:
                self._apply_script_text(u)
            else:
                self._apply_glossary_words(u)
        tags = self._anchor_tags(utts) if has_script else []
        rep.matched = sum(1 for u in utts if u.kept and u.script_span)
        rep.retakes = sum(1 for u in utts if u.status == "retake")
        rep.meta = sum(1 for u in utts if u.status == "meta")
        rep.unmatched = sum(1 for u in utts if u.kept and not u.script_span)
        if has_script:
            rep.script_coverage, rep.missing_sentences = self._coverage(utts)
        return utts, tags, rep

    # --------------------------------------------------------------
    def _match_all(self, utts: list[Utterance]) -> None:
        cursor = 0
        n = len(self.snorm)
        for u in utts:
            un = norm(u.asr_text)
            if len(un) < 4:
                continue
            best = None
            for back, fwd in ((700, 1600), (n, n)):
                lo = max(0, cursor - back)
                hi = min(n, cursor + fwd + len(un))
                window = self.snorm[lo:hi]
                if not window:
                    continue
                al = fuzz.partial_ratio_alignment(un, window) if len(un) <= len(window) else None
                if al is None:
                    continue
                cand = (al.score, lo + al.dest_start, lo + al.dest_end)
                if best is None or cand[0] > best[0]:
                    best = cand
                if best[0] >= self.match_threshold + 10:
                    break
            if best and best[0] >= self.match_threshold:
                score, a, b = best
                a, b = self._refine_span(un, a, b)
                u.score = float(score)
                # 정규화 인덱스 → clean 문자 인덱스
                u.script_span = (self.smap[a], self.smap[max(a, b - 1)] + 1)
                cursor = max(cursor, b) if score >= 80 else cursor

    def _refine_span(self, un: str, a: int, b: int) -> tuple[int, int]:
        """partial_ratio 가 준 구간(길이 = 발화 길이)을 앞뒤로 조금 넓혀 실제 일치 경계에 맞춘다."""
        pad = max(4, len(un) // 3)
        lo = max(0, a - pad)
        hi = min(len(self.snorm), b + pad)
        sub = self.snorm[lo:hi]
        sm = difflib.SequenceMatcher(None, un, sub, autojunk=False)
        blocks = [bl for bl in sm.get_matching_blocks() if bl.size >= 2]
        if not blocks:
            return a, b
        return lo + blocks[0].b, lo + blocks[-1].b + blocks[-1].size

    # --------------------------------------------------------------
    def _mark_meta(self, utts: list[Utterance]) -> None:
        for u in utts:
            un = norm(u.asr_text)
            if not un:
                u.status = "noise"
                continue
            if u.script_span and u.score >= 80:
                continue
            if un in FILLER_ONLY:
                u.status = "meta"
                u.note = "추임새"
                continue
            if len(un) <= 18 and any(p in un for p in META_PATTERNS):
                u.status = "meta"
                u.note = "NG/메타 발화"

    def _mark_retakes_by_script(self, utts: list[Utterance]) -> None:
        """같은 대본 구간을 여러 번 말한 테이크들을 묶고, 가장 또렷한 테이크만 남긴다."""
        kept = [u for u in utts if u.kept and u.script_span]
        groups = _UnionFind(len(kept))
        for j, uj in enumerate(kept):
            aj, bj = uj.script_span  # type: ignore[misc]
            for i in range(max(0, j - 10), j):
                ui = kept[i]
                if uj.start - ui.end > 120:  # 2분 이상 떨어진 반복은 의도적 반복으로 본다
                    continue
                ai, bi = ui.script_span  # type: ignore[misc]
                overlap = min(bi, bj) - max(ai, aj)
                if overlap >= 0.5 * max(1, min(bi - ai, bj - aj)):
                    groups.union(i, j)
        for members in groups.clusters():
            if len(members) > 1:
                self._resolve_takes([kept[k] for k in members], span=lambda u: u.script_span)

    def _mark_retakes_by_similarity(self, utts: list[Utterance]) -> None:
        """대본에 없는 발화끼리의 반복(대본이 없거나 애드리브) — 비슷한 발화 묶음에서 가장 또렷한 것만."""
        kept = [u for u in utts if u.kept]
        groups = _UnionFind(len(kept))
        for j, uj in enumerate(kept):
            nj = norm(uj.asr_text)
            if len(nj) < 6:
                continue
            for i in range(max(0, j - 3), j):
                ui = kept[i]
                ni = norm(ui.asr_text)
                if len(ni) < 6 or uj.start - ui.end > 25:
                    continue
                if ui.script_span and uj.script_span:
                    continue  # 대본 기준 판정이 이미 처리
                short, long_ = (ni, nj) if len(ni) <= len(nj) else (nj, ni)
                if fuzz.partial_ratio(short, long_) >= 82 and len(short) >= 0.3 * len(long_):
                    groups.union(i, j)
        for members in groups.clusters():
            if len(members) > 1:
                self._resolve_takes([kept[k] for k in members], span=None)

    def _resolve_takes(self, takes: list[Utterance], span) -> None:
        """테이크 묶음 → 점수순으로 고르되, 이미 고른 테이크와 20% 넘게 겹치면 버린다(같은 말 두 번 방지)."""
        def length(u: Utterance) -> int:
            if span is not None and span(u):
                a, b = span(u)
                return max(1, b - a)
            return max(1, len(norm(u.asr_text)))

        def overlap(u: Utterance, v: Utterance) -> float:
            if span is not None and span(u) and span(v):
                (a1, b1), (a2, b2) = span(u), span(v)
                return max(0, min(b1, b2) - max(a1, a2)) / length(u)
            return 1.0  # 대본 없는 반복은 통째로 같은 말

        longest = max(length(u) for u in takes)
        order = sorted(takes, key=lambda u: u.start)
        rates = sorted(len(norm(u.text)) / max(0.3, u.end - u.start) for u in takes)
        med_rate = rates[len(rates) // 2]
        scored = []
        for rank, u in enumerate(order):
            s = take_score(u, coverage=length(u) / longest, med_rate=med_rate, energy=self._energy(u),
                           recency=rank / max(1, len(order) - 1))
            scored.append((s, u))
        scored.sort(key=lambda p: -p[0])
        chosen: list[tuple[float, Utterance]] = []
        for s, u in scored:
            if all(overlap(u, c) < 0.2 for _, c in chosen):
                chosen.append((s, u))
                continue
            best_s, best = chosen[0]
            u.status = "retake"
            u.note = f"#{best.id} 가 더 또렷함 ({s * 100:.0f} < {best_s * 100:.0f}점)"
            u.take_score = round(s, 3)
        for s, u in chosen:
            u.take_score = round(s, 3)

    def _energy(self, u: Utterance) -> Optional[float]:
        """발화 구간의 평균 음량(dBFS) — 16kHz 오디오가 있을 때만."""
        a = self.audio
        if a is None or not len(a):
            return None
        i0, i1 = int(u.start * 16000), int(u.end * 16000)
        seg = a[max(0, i0):max(i0 + 1, min(len(a), i1))]
        if not len(seg):
            return None
        import numpy as np
        rms = float(np.sqrt(np.mean(np.square(seg.astype(np.float32)))) + 1e-9)
        return 20 * float(np.log10(rms))

    # --------------------------------------------------------------
    def _apply_glossary_words(self, u: Utterance) -> None:
        if not self.glossary:
            return
        u.text = apply_glossary(u.text, self.glossary)
        # 단어 단위는 간단 치환(붙어 있는 두 단어 용어는 텍스트에만 반영)
        for w in u.words:
            w.text = apply_glossary(w.text, self.glossary)

    def _apply_script_text(self, u: Utterance) -> None:
        a, b = u.script_span  # type: ignore[misc]
        clean = self.script.clean
        # 어절 경계까지 확장
        while a > 0 and not clean[a - 1].isspace():
            a -= 1
        while b < len(clean) and not clean[b].isspace():
            b += 1
        sub = clean[a:b].strip()
        if not sub:
            return
        # 발화 글자별 시간
        asr_chars: list[str] = []
        asr_times: list[tuple[float, float]] = []
        for w in u.words:
            wn = norm(w.text)
            if not wn:
                continue
            step = (w.end - w.start) / len(wn)
            for k, ch in enumerate(wn):
                asr_chars.append(ch)
                asr_times.append((w.start + k * step, w.start + (k + 1) * step))
        sub_norm, sub_map = norm_with_map(sub)
        if not sub_norm or not asr_chars:
            return
        sm = difflib.SequenceMatcher(None, "".join(asr_chars), sub_norm, autojunk=False)
        times: list[Optional[tuple[float, float]]] = [None] * len(sub_norm)
        for bl in sm.get_matching_blocks():
            for k in range(bl.size):
                times[bl.b + k] = asr_times[bl.a + k]
        _interpolate(times, u.start, u.end)
        # 어절(토큰) 단위로 묶기
        tokens: list[Word] = []
        for m in re.finditer(r"\S+", sub):
            idxs = [k for k, ci in enumerate(sub_map) if m.start() <= ci < m.end()]
            if not idxs:
                if tokens:  # 문장부호만 있는 토큰은 앞 토큰에 붙인다
                    tokens[-1].text += m.group(0)
                continue
            st = times[idxs[0]][0]  # type: ignore[index]
            en = times[idxs[-1]][1]  # type: ignore[index]
            tokens.append(Word(m.group(0), st, max(en, st + 0.04)))
        if tokens:
            _monotonic(tokens)
            u.words = tokens
            u.text = sub


    # --------------------------------------------------------------
    def _anchor_tags(self, utts: list[Utterance]) -> list[Tag]:
        kept = [u for u in utts if u.kept and u.script_span]
        kept_sorted = sorted(kept, key=lambda u: u.script_span[0])  # type: ignore[index]
        anchored: list[Tag] = []
        for t in self.script.tags:
            target = None
            for u in kept_sorted:
                a, b = u.script_span  # type: ignore[misc]
                if b > t.pos:  # 태그 위치를 포함하거나 그 이후 첫 발화
                    target = u
                    break
            if target is None and kept_sorted:
                # 대본 맨 끝(뒤에 문장이 없는) 태그 → 바로 앞 발화에 붙인다
                target = kept_sorted[-1]
            if target is None:
                continue
            t.utt_id = target.id
            anchored.append(t)
        return anchored

    def _coverage(self, utts: list[Utterance]) -> tuple[float, list[str]]:
        covered = [False] * (len(self.script.clean) + 1)
        for u in utts:
            if u.kept and u.script_span:
                a, b = u.script_span
                for k in range(a, min(b, len(covered))):
                    covered[k] = True
        missing: list[str] = []
        total = 0
        hit = 0
        for s, e, text in self.script.sentences:
            n = max(1, e - s)
            c = sum(covered[s:e])
            total += n
            hit += c
            if c / n < 0.3 and len(text) > 6:
                missing.append(text)
        return (hit / total if total else 0.0), missing[:30]


FILLER_WORDS = {"음", "어", "아", "그", "저", "에", "뭐", "좀", "이제", "막", "으음", "어어", "음음", "그니까", "그러니까"}


def take_score(u: Utterance, *, coverage: float, med_rate: float, energy: Optional[float] = None,
               recency: float = 0.0) -> float:
    """테이크 품질(0~1, 높을수록 또렷). 같은 대본 구간을 여러 번 말했을 때 어느 것을 쓸지 정한다.

    - 대본 일치도(말실수 없이 대본대로)          35%
    - 완결성(중간에 끊기지 않고 끝까지 말함)      30%
    - 음성인식 확신도(발음이 또렷함)              15%
    - 유창성: 추임새·단어 반복·긴 머뭇거림 감점
    - 말 속도: 묶음 중앙값보다 크게 느리면(더듬음) 감점
    - 음량: 더 힘 있게 말한 테이크 가산(±5%)
    - 최신성: 보통 마지막 테이크가 고쳐 말한 것(+4%)
    """
    words = u.words or []
    sim = (u.score or 70.0) / 100.0
    cov = min(1.0, coverage)
    cov_term = cov if cov >= 0.8 else cov * 0.6  # 중간에 끊긴 테이크는 크게 감점
    conf = sum(w.prob for w in words) / len(words) if words else 0.8
    toks = [norm(w.text) for w in words]
    fillers = sum(1 for t in toks if t in FILLER_WORDS)
    repeats = sum(1 for a, b in zip(toks, toks[1:]) if a and a == b)
    pauses = sum(1 for a, b in zip(words, words[1:]) if b.start - a.end > 0.7)
    flu = min(0.25, 0.05 * fillers + 0.06 * repeats + 0.04 * pauses)
    rate = len(norm(u.text)) / max(0.3, u.end - u.start)
    slow = max(0.0, (med_rate - rate) / max(1e-6, med_rate)) if med_rate else 0.0
    score = 0.35 * sim + 0.30 * cov_term + 0.15 * conf - flu - 0.12 * min(1.0, slow)
    if energy is not None:
        score += 0.05 * max(-1.0, min(1.0, (energy + 30.0) / 12.0))
    score += 0.04 * recency
    return max(0.0, score)


class _UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)

    def clusters(self) -> list[list[int]]:
        out: dict[int, list[int]] = {}
        for i in range(len(self.p)):
            out.setdefault(self.find(i), []).append(i)
        return list(out.values())


def _interpolate(times: list[Optional[tuple[float, float]]], t0: float, t1: float) -> None:
    n = len(times)
    known = [i for i, t in enumerate(times) if t is not None]
    if not known:
        step = (t1 - t0) / max(1, n)
        for i in range(n):
            times[i] = (t0 + i * step, t0 + (i + 1) * step)
        return
    for i in range(n):
        if times[i] is not None:
            continue
        prev = max((k for k in known if k < i), default=None)
        nxt = min((k for k in known if k > i), default=None)
        if prev is not None and nxt is not None:
            a = times[prev][1]  # type: ignore[index]
            b = max(a, times[nxt][0])  # type: ignore[index]
            count = nxt - prev - 1
            seg = (b - a) / count
            k = i - prev - 1
            times[i] = (a + k * seg, a + (k + 1) * seg)
        elif prev is not None:
            a = times[prev][1]  # type: ignore[index]
            times[i] = (a, min(t1, a + 0.08))
        else:
            b = times[nxt][0]  # type: ignore[index]
            times[i] = (max(t0, b - 0.08), b)


def _monotonic(tokens: list[Word]) -> None:
    for i in range(1, len(tokens)):
        if tokens[i].start < tokens[i - 1].start:
            tokens[i].start = tokens[i - 1].start
        if tokens[i].end < tokens[i].start:
            tokens[i].end = tokens[i].start + 0.04
    for i in range(len(tokens) - 1):
        if tokens[i].end > tokens[i + 1].start:
            tokens[i].end = max(tokens[i].start + 0.02, tokens[i + 1].start)
