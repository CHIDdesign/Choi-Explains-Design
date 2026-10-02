"""자막 큐 만들기.

- 지금 쓰는 것(롱폼·숏폼 모두): build_phrase_cues — 한 줄에 한두 마디씩(롱폼 ≤13자·≤2.4초, 숏폼 12자·2.0초,
  릴스식 8자·1.6초), 쉼표·문장 끝·이음 어미에서 끊고 snap_cues_to_speech 로 말소리 시작(VAD)에 맞춘다
- 예전 방식(테스트·호환용): build_cues 롱폼 줄당 16자 × 최대 2줄(넷플릭스 한국어 가이드 · 레퍼런스 채널 리서치 규칙 16),
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


# ---------------------------------------------------------------------------
# 호흡 단위 자막(build_phrase_cues)
#   글자 수로만 끊으면 '철수는 오늘 비행기를 / 타고 로스앤젤레스로 / 향하는 길이었다' 처럼 구가 갈라진다(채널 피드백).
#   원하는 것: '철수는 오늘 / 비행기를 타고 / 로스앤젤레스로 향하는 / 길이었다' — 2어절 안팎의 **구(句)** 단위.
#   어절 사이마다 '끊기 좋은 정도'를 매기고(문장부호·쉼·이음 어미는 좋고, 목적어·관형어·부사 뒤는 나쁘다),
#   큐마다 '모양 비용'(2~3어절·13자 안팎·2.4초 안)을 더해 DP 로 가장 자연스러운 분할을 고른다.
# ---------------------------------------------------------------------------
_HANGUL = re.compile(r"[^가-힣]")
# 관형형 어미(뒤의 명사와 떨어져도 호흡은 산다: '로스앤젤레스로 향하는 / 길이었다')
ADNOMINAL_RE = re.compile(r"(하는|되는|있는|없는|이는|오는|가는|보는|주는|만드는|이라는|라는|다는|하던|했던|되던|된|한|할|될|볼|인|던)$")
OBJECT_RE = re.compile(r"(을|를)$")
GENITIVE_RE = re.compile(r"의$")
ADVERBIAL_RE = re.compile(r"(에|에서|로|으로|에게|께|부터|까지|보다|처럼|와|과|랑|이랑|마다|대로)$")
SUBJECT_RE = re.compile(r"(이|가|은|는|께서)$")
# 뒤 어절이 의존 명사·보조 용언이면 앞 어절과 절대 떼지 않는다('할 수 있다', '하는 것이', '그런 게')
BOUND_NEXT = {"것", "것이", "것을", "것은", "것도", "거", "게", "건", "걸", "거야", "거죠", "거예요", "겁니다", "거고", "거든요",
              "수", "때", "때가", "때는", "데", "지", "줄", "뿐", "채", "듯", "만큼", "정도", "중", "후", "전", "때문에",
              "때문이죠", "경우", "대로", "편", "리", "법", "쪽", "탓", "김에", "나름", "따름", "바", "적", "척", "체",
              "않는", "않고", "않아요", "않습니다", "못", "못해요", "있어요", "있습니다", "없어요", "없습니다", "싶어요",
              "싶은", "싶습니다", "봐요", "보세요", "주세요", "됩니다", "돼요",
              "있는", "없는", "있다", "없다", "있고", "없고", "있어", "없어", "있으면", "없으면", "있을", "없을", "있던",
              "없던", "있죠", "없죠", "있어서", "없어서", "있지만", "없지만"}
# 뒤에 오는 말에 붙는 부사·관형사(뒤에서 끊지 않는다)
ATTACH_NEXT = {"매우", "아주", "정말", "너무", "더", "가장", "잘", "못", "안", "꼭", "좀", "약간", "되게", "굉장히", "훨씬",
               "거의", "바로", "계속", "이미", "아직", "막", "딱", "참", "진짜", "완전", "제일", "항상", "늘", "자주", "전혀",
               "절대", "결코", "또", "또한", "다시", "이", "그", "저", "이런", "그런", "저런", "어떤", "무슨", "모든", "각",
               "한", "두", "세", "네", "첫", "여러", "다른", "같은", "새로운", "어느", "몇", "온갖", "별", "약", "총", "단",
               "즉", "곧", "안", "잘못"}
# 형용사 관형형(뒤의 명사에 붙는다: '좋은 디자인은', '중요한 것은') — 동사 관형형(향하는·만든)은 길면 떼어도 호흡이 산다
ADJ_ADNOMINAL_RE = re.compile(
    r"(중요한|특별한|다양한|단순한|복잡한|강력한|간단한|새로운|유명한|필요한|가능한|충분한|완벽한|정확한|자연스러운|아름다운|편한|불편한"
    r"|좋은|나쁜|많은|적은|작은|높은|낮은|빠른|느린|쉬운|어려운|같은|다른|어떤|이런|그런|저런|모든|큰|새|옛|긴|먼|센|온|첫)$")
# 문장 부사·접속 부사(뒤에서 끊기 좋다: '철수는 오늘 /', '그래서 /')
SENT_ADV = {"오늘", "지금", "이제", "그래서", "그런데", "하지만", "결국", "사실", "먼저", "그리고", "또는", "즉", "물론",
            "특히", "다만", "그러나", "그래도", "그러면", "그럼", "예를", "보통", "대개", "원래", "실제로", "당연히", "아마",
            "물론이죠", "어쨌든", "근데", "그러니까", "그니까", "그러다", "다음으로", "마지막으로", "첫째", "둘째", "셋째"}


def _boundary_cost(cur: dict, nxt: dict) -> float:
    """cur 와 nxt 사이에서 끊는 비용(낮을수록 좋다)."""
    raw = cur["raw"]
    h = _HANGUL.sub("", raw)
    nh = _HANGUL.sub("", nxt["raw"])
    if re.search(r"[.?!。？！]$", raw):
        return -20.0
    cost = 0.0
    if re.search(r"[,，、]$", raw):
        cost -= 6.0
    gap = nxt["start"] - cur["end"]
    if gap >= 0.6:
        cost -= 8.0
    elif gap >= 0.35:
        cost -= 4.0
    elif gap >= 0.2:
        cost -= 1.5
    if nh in BOUND_NEXT:
        return cost + 8.0
    if h in ATTACH_NEXT or ADJ_ADNOMINAL_RE.search(h) \
            or (len(h) == 2 and h[-1] in "은는" and not ADNOMINAL_RE.search(h)):   # 2글자 '좋은·많은·손은' 은 뒷말에 붙는다
        return cost + 4.0
    if CONNECT_RE.search(h) or FINAL_RE.search(h):
        cost -= 3.0
    elif ADNOMINAL_RE.search(h):
        cost -= 0.5
    elif OBJECT_RE.search(h) or GENITIVE_RE.search(h):
        cost += 5.0
    elif ADVERBIAL_RE.search(h):
        cost += 2.5
    elif SUBJECT_RE.search(h):
        cost += 1.5
    if h in SENT_ADV:
        cost -= 1.5
    return cost


def _chunk_cost(words: list[dict], max_chars: int, max_dur: float) -> float:
    n = len(words)
    chars = sum(_clen(w["text"]) for w in words) + (n - 1)
    cost = 0.0
    if chars > max_chars:
        cost += 30.0 + 5.0 * (chars - max_chars)
    if words[-1]["end"] - words[0]["start"] > max_dur:
        cost += 25.0
    if n == 1:
        cost += 2.0 + (6.0 if _clen(words[0]["text"]) < 4 else 0.0)
    elif n >= 4:
        cost += 3.0 * (n - 3)
    if chars < 4:
        cost += 3.0
    return cost


def split_phrases(items: list[dict], *, max_chars: int = 13, max_dur: float = 2.4, max_words: int = 5) -> list[list[dict]]:
    """어절 목록(text·raw·start·end) → 호흡 단위 청크들(DP)."""
    n = len(items)
    if n == 0:
        return []
    INF = float("inf")
    best = [INF] * (n + 1)
    prev = [-1] * (n + 1)
    best[0] = 0.0
    for j in range(1, n + 1):
        for i in range(max(0, j - max_words), j):
            if best[i] == INF:
                continue
            c = best[i] + _chunk_cost(items[i:j], max_chars, max_dur)
            if i > 0:
                c += _boundary_cost(items[i - 1], items[i])
            if c < best[j]:
                best[j], prev[j] = c, i
    out: list[list[dict]] = []
    j = n
    while j > 0:
        i = prev[j]
        out.append(items[i:j])
        j = i
    out.reverse()
    return out


def build_phrase_cues(
    groups: Iterable[list[Word]],
    *,
    max_chars: int = 13,
    max_dur: float = 2.4,
    min_dur: float = 0.45,
    tail: float = 0.12,
    emphasis=None,
) -> list[dict]:
    """요즘 자막 호흡: 한 줄에 한두 마디(≈13자·2.4초 이하)씩 빠르게 — **구 단위**로 끊는다(split_phrases).
    '철수는 오늘 / 비행기를 타고 / 로스앤젤레스로 향하는 / 길이었다' 처럼 목적어와 서술어, 부사와 뒷말, 관형사와 명사는
    떼지 않고, 문장부호·쉼·이음 어미·문장 부사 뒤에서 끊는다."""
    cues: list[dict] = []
    for words in groups:
        items: list[dict] = []
        for w in words:
            txt = display_text(w.text)
            if not txt:
                continue
            item = {"text": txt, "start": round(w.start, 3), "end": round(w.end, 3), "raw": w.text.strip()}
            em = _em_lookup(emphasis, w.start, txt)
            if em:
                item["em"] = em
            items.append(item)
        for chunk in split_phrases(items, max_chars=max_chars, max_dur=max_dur):
            line = [{k: v for k, v in it.items() if k != "raw"} for it in chunk]
            cues.append({"start": line[0]["start"], "end": line[-1]["end"], "lines": [line]})
    # 편집 시각 순으로(숏폼 재배치·겹친 단어가 있어도 끝 시각 계산이 음수가 되지 않게)
    cues.sort(key=lambda c: c["start"])
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

