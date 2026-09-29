"""파이프라인 전 단계가 공유하는 데이터 구조."""
from __future__ import annotations

import bisect
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class Word:
    text: str
    start: float
    end: float
    prob: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Word":
        return cls(d["text"], float(d["start"]), float(d["end"]), float(d.get("prob", 1.0)))


@dataclass
class Tag:
    """대본 속 [도식: 더블다이아몬드] 같은 연출 지시."""
    kind: str               # 정규화된 종류(chapter, diagram, keyword ...)
    args: list[str]
    raw: str
    pos: int                # 태그가 놓인 위치(정제된 대본 문자 인덱스)
    utt_id: Optional[int] = None
    end_pos: Optional[int] = None   # [숏폼 시작]~[숏폼 끝] 같은 범위 태그

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Tag":
        return cls(d["kind"], list(d.get("args", [])), d.get("raw", ""), int(d.get("pos", 0)),
                   d.get("utt_id"), d.get("end_pos"))


@dataclass
class Utterance:
    """발화 단위(대략 한 문장). 시간은 원본(source) 기준 초."""
    id: int
    start: float
    end: float
    text: str                      # 자막용(대본 교정 반영)
    asr_text: str                  # 음성인식 원문
    words: list[Word] = field(default_factory=list)
    script_span: Optional[tuple[int, int]] = None
    score: float = 0.0             # 대본 일치도 0~100
    status: str = "keep"           # keep | retake | meta | noise | director_drop
    note: str = ""
    take_score: float = 0.0        # 리테이크 묶음에서 매긴 테이크 품질(0~1, 묶음이 없으면 0)

    @property
    def kept(self) -> bool:
        return self.status == "keep"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["words"] = [w.to_dict() for w in self.words]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Utterance":
        span = d.get("script_span")
        return cls(
            id=int(d["id"]), start=float(d["start"]), end=float(d["end"]),
            text=d.get("text", ""), asr_text=d.get("asr_text", ""),
            words=[Word.from_dict(w) for w in d.get("words", [])],
            script_span=tuple(span) if span else None,
            score=float(d.get("score", 0.0)), status=d.get("status", "keep"), note=d.get("note", ""),
            take_score=float(d.get("take_score", 0.0)),
        )


@dataclass
class Span:
    start: float
    end: float

    @property
    def dur(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict[str, float]:
        return {"start": round(self.start, 4), "end": round(self.end, 4)}


class TimeMap:
    """원본 시간 ↔ 편집(컷 이후) 시간 변환.

    keep 구간들이 순서대로 이어 붙여진 타임라인을 표현한다.
    """

    def __init__(self, keeps: list[Span], preserve_order: bool = False):
        # preserve_order=True: 숏폼처럼 순서를 재배치한 편집(콜드 오픈 등)
        self.keeps = list(keeps) if preserve_order else sorted(keeps, key=lambda s: s.start)
        self.monotonic = all(self.keeps[i].start >= self.keeps[i - 1].end - 1e-6 for i in range(1, len(self.keeps)))
        self._src_starts = [k.start for k in self.keeps]
        self._edit_starts: list[float] = []
        acc = 0.0
        for k in self.keeps:
            self._edit_starts.append(acc)
            acc += k.dur
        self.duration = acc

    def src_to_edit(self, t: float, snap: bool = True) -> Optional[float]:
        """원본 시각 t 의 편집 시각. 잘린 구간이면 snap=True 일 때 다음 keep 시작으로."""
        if not self.keeps:
            return None
        if not self.monotonic:
            for i, k in enumerate(self.keeps):
                if k.start <= t <= k.end:
                    return self._edit_starts[i] + (t - k.start)
            if not snap:
                return None
            later = [i for i, k in enumerate(self.keeps) if k.start > t]
            return self._edit_starts[min(later, key=lambda i: self.keeps[i].start)] if later else self.duration
        i = bisect.bisect_right(self._src_starts, t) - 1
        if i >= 0:
            k = self.keeps[i]
            if k.start <= t <= k.end:
                return self._edit_starts[i] + (t - k.start)
        if not snap:
            return None
        nxt = i + 1
        if nxt < len(self.keeps):
            return self._edit_starts[nxt]
        return self.duration

    def edit_to_src(self, t: float) -> float:
        i = bisect.bisect_right(self._edit_starts, t) - 1
        i = max(0, min(i, len(self.keeps) - 1))
        return self.keeps[i].start + (t - self._edit_starts[i])

    def cut_points(self) -> list[float]:
        """편집 타임라인 상의 컷(점프컷) 위치들."""
        return self._edit_starts[1:]

    def edit_span_of(self, i: int) -> Span:
        return Span(self._edit_starts[i], self._edit_starts[i] + self.keeps[i].dur)

    def map_span(self, start: float, end: float) -> Optional[Span]:
        a = self.src_to_edit(start, snap=True)
        b = self.src_to_edit(end, snap=True)
        if a is None or b is None or b - a <= 0.01:
            return None
        return Span(a, b)

    def map_words(self, words: list["Word"]) -> list["Word"]:
        """단어들을 편집 시간으로 옮긴다. 재배치/중복된 keep 도 순서대로 처리."""
        out: list[Word] = []
        for i, k in enumerate(self.keeps):
            base = self._edit_starts[i]
            for w in words:
                mid = (w.start + w.end) / 2
                if k.start <= mid <= k.end:
                    s = base + max(0.0, w.start - k.start)
                    e = base + min(k.dur, w.end - k.start)
                    out.append(Word(w.text, s, max(e, s + 0.02), w.prob))
        return out

    def to_list(self) -> list[dict[str, float]]:
        return [k.to_dict() for k in self.keeps]

    @classmethod
    def from_list(cls, items: list[dict[str, float]], preserve_order: bool = False) -> "TimeMap":
        return cls([Span(float(d["start"]), float(d["end"])) for d in items], preserve_order=preserve_order)
