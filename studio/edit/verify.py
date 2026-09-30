"""편집 검사(머신러닝 2차 확인): 잘라 붙인 목소리를 Whisper 로 다시 받아 적고 VAD 로 다시 재서
아직 남은 되풀이·추임새·긴 무음을 찾아 원본 시간 구간으로 돌려준다 → 그만큼 더 잘라서 다시 붙인다.

첫 판단(원본 전사)이 놓친 것 — 단어 시간이 어긋났거나, 발화를 잘못 나눴거나, 앞뒤 문맥이 잘린 뒤에야
드러나는 되풀이 — 을 '결과물 기준'으로 한 번 더 잡는다. 결과는 work/verify.json·편집 리포트에 남는다.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models import Span, TimeMap, Word
from ..text.takes import clean_words, vad_pause

EDGE = 0.4          # 영상 맨 앞·끝의 무음은 건드리지 않음(초)


@dataclass
class Issue:
    start: float      # 편집 타임라인 기준
    end: float
    reason: str
    text: str = ""

    def to_dict(self) -> dict:
        return {"start": round(self.start, 3), "end": round(self.end, 3), "reason": self.reason, "text": self.text}


def find_issues(words: list[Word], vad: list[tuple[float, float]], *, max_silence: float,
                duration: float) -> list[Issue]:
    """편집된 목소리의 단어·VAD → 남은 문제들(편집 시간)."""
    _, removed = clean_words(words, pause=vad_pause(vad))
    issues = [Issue(r.start - 0.03, r.end + 0.05, r.reason, r.text) for r in removed]
    vad = sorted(vad)
    for (a, b), (c, d) in zip(vad, vad[1:]):
        if c - b > max_silence + 0.25 and b > EDGE and c < duration - EDGE:
            issues.append(Issue(b + 0.14, c - 0.10, "긴 무음", f"{c - b:.1f}초"))
    return sorted(issues, key=lambda i: i.start)


def to_source(issues: list[Issue], timemap: TimeMap) -> list[Span]:
    """편집 시간 구간 → 원본 시간 구간들(keep 경계를 넘으면 나눈다)."""
    out: list[Span] = []
    for it in issues:
        for i, k in enumerate(timemap.keeps):
            es = timemap.edit_span_of(i)
            a, b = max(es.start, it.start), min(es.end, it.end)
            if b - a > 0.02:
                out.append(Span(k.start + (a - es.start), k.start + (b - es.start)))
    return merge(out)


def merge(spans: list[Span]) -> list[Span]:
    out: list[Span] = []
    for s in sorted(spans, key=lambda s: s.start):
        if out and s.start <= out[-1].end + 0.01:
            out[-1] = Span(out[-1].start, max(out[-1].end, s.end))
        else:
            out.append(s)
    return out


def subtract(keeps: list[Span], drops: list[Span], *, min_keep: float = 0.15) -> list[Span]:
    """keep 구간들에서 drop 구간들을 뺀다(순서 유지)."""
    if not drops:
        return list(keeps)
    drops = merge(drops)
    out: list[Span] = []
    for k in keeps:
        pieces = [k]
        for d in drops:
            nxt = []
            for p in pieces:
                if d.end <= p.start or d.start >= p.end:
                    nxt.append(p)
                    continue
                if d.start > p.start:
                    nxt.append(Span(p.start, d.start))
                if d.end < p.end:
                    nxt.append(Span(d.end, p.end))
            pieces = nxt
        out.extend(p for p in pieces if p.dur >= min_keep)
    return out
