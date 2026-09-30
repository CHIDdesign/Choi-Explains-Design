"""자막 큐 만들기.

- 지금 쓰는 것(롱폼·숏폼 모두): build_phrase_cues — 한 줄에 한두 마디씩(롱폼 ≤13자·≤2.4초, 숏폼 12자·2.0초,
  릴스식 8자·1.6초), 쉼표·문장 끝·이음 어미에서 끊고 snap_cues_to_speech 로 말소리 시작(VAD)에 맞춘다
- 예전 방식(테스트·호환용): build_cues 롱폼 줄당 16자 × 최대 2줄(넷플릭스 한국어 가이드 · 셜록현준 리서치 규칙 16),
  build_short_chunks 숏폼 1~3어절·6~14자(숏폼 리서치 4-4)
- 강조: 🔤 자막 디자이너가 고른 단어에 유형(keyword/term/number/contrast)을 붙이고, 한 큐에 하나만 남긴다
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


Emphasis = "dict[tuple[float, str], str | bool] | set[tuple[float, str]] | None"


def _em_lookup(emphasis, start: float, txt: str):
    """(단어 시작시각, 정규화 텍스트) 가 강조 목록에 있으면 유형(또는 True)."""
    if not emphasis:
        return None
    flat = re.sub(r"\s", "", txt)
    items = emphasis.items() if isinstance(emphasis, dict) else ((k, True) for k in emphasis)
    for (t, key), typ in items:
        if abs(start - t) < 0.05 and key and key in flat:
            return typ or True
    return None


def one_em_per_cue(cues: list[dict]) -> None:
    """한 큐(청크)에 강조는 하나만 — 여러 개면 전문용어/숫자 > 대비 > 키워드 순으로 남긴다."""
    rank = {"term": 0, "number": 1, "contrast": 2, "keyword": 3, True: 4}
    for c in cues:
        ems = [w for line in c["lines"] for w in line if w.get("em")]
        if len(ems) <= 1:
            continue
        keep = min(ems, key=lambda w: rank.get(w["em"], 5))
        for w in ems:
            if w is not keep:
                w.pop("em", None)


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
    max_chars: int = 16,
    max_lines: int = 2,
    max_dur: float = 5.5,
    gap_break: float = 0.6,
    tail: float = 0.25,
    emphasis=None,
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
            em = _em_lookup(emphasis, w.start, txt)
            if em:
                item["em"] = em
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
    one_em_per_cue(cues)
    return cues


def build_short_chunks(
    groups: Iterable[list[Word]],
    *,
    max_chars: int = 14,
    max_words: int = 3,
    min_dur: float = 0.6,
    emphasis=None,
) -> list[dict]:
    cues: list[dict] = []
    for words in groups:
        cur: list[dict] = []
        for w in words:
            txt = display_text(w.text)
            if not txt:
                continue
            item = {"text": txt, "start": round(w.start, 3), "end": round(w.end, 3)}
            em = _em_lookup(emphasis, w.start, txt)
            if em:
                item["em"] = em
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
    one_em_per_cue(merged)
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


# 한국어 이음 어미·쉼표 뒤는 자연스러운 끊는 자리
CONNECT_RE = re.compile(r"(고|며|면|서|데|지만|는데|니까|으니|어서|아서|도록|려고|다가|해도|든지|거나|는지)$")
FINAL_RE = re.compile(r"(니다|어요|아요|예요|에요|해요|죠|다)$")


def build_phrase_cues(
    groups: Iterable[list[Word]],
    *,
    max_chars: int = 13,
    max_dur: float = 2.4,
    min_dur: float = 0.45,
    tail: float = 0.12,
    emphasis=None,
) -> list[dict]:
    """요즘 자막 호흡: 한 줄에 한두 마디(≈13자·2.4초 이하)씩 빠르게. 쉼표·문장 끝·이음 어미에서 끊는다.
    (예전 롱폼 자막은 16자×2줄·5.5초까지 이어져 '너무 길다'는 평)"""
    cues: list[dict] = []
    for words in groups:
        cur: list[dict] = []

        def flush() -> None:
            if cur:
                cues.append({"start": cur[0]["start"], "end": cur[-1]["end"], "lines": [cur[:]]})
                cur.clear()

        for w in words:
            txt = display_text(w.text)
            if not txt:
                continue
            item = {"text": txt, "start": round(w.start, 3), "end": round(w.end, 3)}
            em = _em_lookup(emphasis, w.start, txt)
            if em:
                item["em"] = em
            raw = w.text.strip()
            ends_phrase = bool(re.search(r"[.?!,]$", raw) or CONNECT_RE.search(re.sub(r"[^가-힣]", "", raw))
                               or FINAL_RE.search(re.sub(r"[^가-힣]", "", raw)))
            if cur:
                length = sum(_clen(x["text"]) for x in cur) + len(cur) + _clen(txt)
                # 이 단어로 구가 끝나면 4자까지는 넘겨도 한 덩어리로('설득력이 | 있는지' 처럼 끝말만 떨어지지 않게)
                limit = max_chars + (4 if ends_phrase else 0)
                if length > limit or w.end - cur[0]["start"] > max_dur:
                    flush()
            cur.append(item)
            now = sum(_clen(x["text"]) for x in cur) + len(cur) - 1
            if re.search(r"[.?!,]$", raw) or (now >= 7 and ends_phrase):
                flush()
        flush()
    # 한 글자·두 글자만 남은 조각은 앞 청크에 붙인다(너무 길어지지 않으면)
    merged: list[dict] = []
    for c in cues:
        words_c = c["lines"][0]
        short = sum(_clen(x["text"]) for x in words_c) <= 2
        if merged and short and c["start"] - merged[-1]["end"] < 0.3:
            prev = merged[-1]["lines"][0]
            if sum(_clen(x["text"]) for x in prev + words_c) + len(prev) <= max_chars + 3:
                merged[-1]["lines"] = [prev + words_c]
                merged[-1]["end"] = c["end"]
                continue
        merged.append(c)
    for i, c in enumerate(merged):
        nxt = merged[i + 1]["start"] if i + 1 < len(merged) else c["end"] + 0.5
        c["end"] = round(min(max(c["end"] + tail, c["start"] + min_dur), nxt), 3)
    one_em_per_cue(merged)
    return merged


def snap_cues_to_speech(cues: list[dict], onsets: list[float], *, before: float = 0.25, after: float = 0.3) -> None:
    """자막 시작을 실제 말소리 시작(VAD, 편집 시간)에 맞춘다 — Whisper 단어 시작이 앞뒤로 흔들리는 것 보정."""
    import bisect
    if not onsets:
        return
    for i, c in enumerate(cues):
        k = bisect.bisect_left(onsets, c["start"] - before)
        if k < len(onsets) and onsets[k] <= c["start"] + after:
            lo = cues[i - 1]["start"] + 0.2 if i > 0 else 0.0
            new = max(lo, onsets[k] - 0.04)
            if new < c["end"] - 0.25:
                if i > 0 and cues[i - 1]["end"] > new:
                    cues[i - 1]["end"] = round(new, 3)
                c["start"] = round(new, 3)

