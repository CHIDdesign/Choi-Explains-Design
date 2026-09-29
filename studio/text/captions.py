"""자막 큐 만들기.

- 롱폼: 1줄 우선, 최대 2줄, 줄당 18자 이내(셜록현준 리서치 규칙 16), 발화 경계에서 끊음
- 숏폼: 1~3어절, 6~14자 청크(숏폼 리서치 4-4), 최소 0.6초 표시
"""
from __future__ import annotations

import re
from typing import Iterable

from ..models import Word

TRAIL_PUNCT = re.compile(r"[.,，、·…]+$")


def display_text(t: str) -> str:
    t = t.strip()
    t = TRAIL_PUNCT.sub("", t)
    return t


def _clen(s: str) -> int:
    return len(s.replace(" ", ""))


def _split_lines(words: list[dict], max_chars: int, max_lines: int) -> list[list[dict]]:
    total = sum(_clen(w["text"]) for w in words) + max(0, len(words) - 1)
    if total <= max_chars or max_lines == 1 or len(words) < 2:
        return [list(words)]
    # 두 줄로 나누는 지점: 균형 + 의미 단위(연결 어미·문장부호 뒤) 선호, 한 글자 관형어 뒤는 피함
    best_i, best_cost = 1, 10**9
    acc = 0
    for i in range(1, len(words)):
        prev = words[i - 1]["text"]
        acc += _clen(prev) + 1
        cost = abs(acc - (total - acc))
        if re.search(r"(고|서|며|면|데|지만|는데|니까|듯|[,.?!])$", prev):
            cost -= 5
        if _clen(prev) == 1:
            cost += 6
        if acc > max_chars + 1 or total - acc > max_chars + 1:
            cost += 20
        if cost < best_cost:
            best_i, best_cost = i, cost
    return [words[:best_i], words[best_i:]]


def build_cues(
    groups: Iterable[list[Word]],
    *,
    max_chars: int = 18,
    max_lines: int = 2,
    max_dur: float = 5.5,
    gap_break: float = 0.6,
    tail: float = 0.25,
    emphasis: set[tuple[float, str]] | None = None,
) -> list[dict]:
    """groups: 발화별 단어 목록(편집 시간). emphasis: (단어 시작시각, 정규화 텍스트) 집합."""
    cues: list[dict] = []
    cap = max_chars * max_lines
    for words in groups:
        cur: list[dict] = []

        def flush() -> None:
            if not cur:
                return
            lines = _split_lines(list(cur), max_chars, max_lines)
            cues.append({"start": cur[0]["start"], "end": cur[-1]["end"] + tail, "lines": lines})
            cur.clear()

        prev_raw = ""
        for w in words:
            txt = display_text(w.text)
            if not txt:
                continue
            item = {"text": txt, "start": round(w.start, 3), "end": round(w.end, 3)}
            if emphasis and any(abs(w.start - t) < 0.05 and key and key in re.sub(r"\s", "", txt) for t, key in emphasis):
                item["em"] = True
            if cur:
                length = sum(_clen(x["text"]) for x in cur) + len(cur) + _clen(txt)
                too_long = length > cap
                too_slow = w.end - cur[0]["start"] > max_dur
                gap = w.start - cur[-1]["end"] > gap_break
                sentence_end = bool(re.search(r"[.?!]$", prev_raw.strip()))
                if too_long or too_slow or gap or (sentence_end and length > max_chars * 0.6):
                    flush()
            cur.append(item)
            prev_raw = w.text
        flush()
    _fix_overlaps(cues)
    return cues


def build_short_chunks(
    groups: Iterable[list[Word]],
    *,
    max_chars: int = 14,
    max_words: int = 3,
    min_dur: float = 0.6,
    emphasis: set[tuple[float, str]] | None = None,
) -> list[dict]:
    cues: list[dict] = []
    for words in groups:
        cur: list[dict] = []
        for w in words:
            txt = display_text(w.text)
            if not txt:
                continue
            item = {"text": txt, "start": round(w.start, 3), "end": round(w.end, 3)}
            if emphasis and any(abs(w.start - t) < 0.05 and key and key in re.sub(r"\s", "", txt) for t, key in emphasis):
                item["em"] = True
            if cur:
                length = sum(_clen(x["text"]) for x in cur) + _clen(txt) + len(cur)
                if length > max_chars or len(cur) >= max_words:
                    cues.append({"start": cur[0]["start"], "end": cur[-1]["end"], "lines": [cur[:]]})
                    cur = []
            cur.append(item)
            if re.search(r"[.?!,]$", w.text.strip()):
                cues.append({"start": cur[0]["start"], "end": cur[-1]["end"], "lines": [cur[:]]})
                cur = []
        if cur:
            cues.append({"start": cur[0]["start"], "end": cur[-1]["end"], "lines": [cur[:]]})
    # 너무 짧은 청크는 다음 청크와 합치거나 늘린다
    merged: list[dict] = []
    for c in cues:
        if merged and (merged[-1]["end"] - merged[-1]["start"] < min_dur * 0.6):
            prev = merged[-1]
            words = prev["lines"][0] + c["lines"][0]
            if sum(_clen(x["text"]) for x in words) <= max_chars + 4:
                prev["lines"] = [words]
                prev["end"] = c["end"]
                continue
        merged.append(c)
    for i, c in enumerate(merged):
        nxt = merged[i + 1]["start"] if i + 1 < len(merged) else c["end"] + 0.4
        c["end"] = min(max(c["end"] + 0.12, c["start"] + min_dur), nxt)
    return merged


def _fix_overlaps(cues: list[dict]) -> None:
    for i in range(len(cues) - 1):
        if cues[i]["end"] > cues[i + 1]["start"]:
            cues[i]["end"] = max(cues[i]["start"] + 0.3, cues[i + 1]["start"])
        # 짧은 공백은 메워서 깜빡임 방지
        elif cues[i + 1]["start"] - cues[i]["end"] < 0.25:
            cues[i]["end"] = cues[i + 1]["start"]


def cues_to_srt(cues: list[dict]) -> str:
    def ts(t: float) -> str:
        t = max(0.0, t)
        h = int(t // 3600)
        m = int(t % 3600 // 60)
        s = int(t % 60)
        ms = int(round((t - int(t)) * 1000))
        if ms == 1000:
            s, ms = s + 1, 0
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    out = []
    for i, c in enumerate(cues, 1):
        text = "\n".join(" ".join(w["text"] for w in line) for line in c["lines"])
        out.append(f"{i}\n{ts(c['start'])} --> {ts(c['end'])}\n{text}\n")
    return "\n".join(out)
