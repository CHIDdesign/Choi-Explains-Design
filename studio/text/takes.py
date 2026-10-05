"""단어 단위 편집 정리: 되풀이한 앞부분(말 다시 시작)·추임새를 지운다.

예전 판단 단위는 '발화'(0.55초 쉼으로 나눈 덩어리)라서, Whisper 단어 시간이 쉼을 덮어 버리면
'그것의 평가가 거의 / 그것의 평가가 거의 전부처럼' 같은 되풀이가 한 덩어리로 통째로 살아남았다
(실제 업로드 영상의 음성 인식에서 확인: 3번 되풀이한 문장이 전부 남음).

여기서는 단어 열을 직접 본다.
  1) 되풀이: 문장 시작(쉼·문장 끝·추임새 뒤)에서 가까운 앞의 시도와 같은 말(2어절·4글자 이상)로 다시 시작하면,
     앞의 시도(갈라진 꼬리까지)를 지운다 — 마지막 시도가 남는다. 여러 번이면 차례로.
     단, 앞의 시도 안에서 문장이 끝났고 NG 말('다시 할게' 등)이 없으면 완성된 다른 문장이라 남긴다.
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


# 어절 끝에 붙는 조사·어미(같은 낱말인지 볼 때 무시) — '평가가/평가는', '어디서/어디인지', '여러분과/여러분들이랑'
PARTICLE_RE = re.compile(
    r"^(들)?(은|는|이|가|을|를|의|에|에서|에게|께|께서|한테|로|으로|로서|로써|으로서|으로써|와|과|랑|이랑|도|만|밖에|조차|마저|뿐"
    r"|부터|까지|처럼|보다|서|고|며|면|지만|는데|니까|다|요|죠|란|이란|나|이나|든지|이든지|라도|이라도|라면|이라면"
    r"|인지|이다|이라|라고|라는|이라는|이며|라서|이라서|인|인데|이고|이면|이지|예요|이에요|에요|네|야|니다|습니다|입니다)?$")
# 문장 첫머리 담화 표지 — '그래서 이제 …'처럼 같은 말로 시작해도 되풀이의 증거로 치지 않는다
DISCOURSE = {"그래서", "그런데", "근데", "그리고", "이제", "그니까", "그러니까", "사실", "또", "그럼", "자", "뭐",
             "이게", "그게", "일단", "그냥", "약간", "이렇게", "그렇게", "다음", "먼저"}


def same_word(a: str, b: str) -> bool:
    """어절이 같은가 — 조사·어미가 다른 정도는 같게(어디서/어디/어디인지). 어간 자체가 다르면(디자인은/디자이너는) 다르다.
    (예전엔 앞 2글자·60% 만 같으면 같다고 봐서 '디자인은…' 문장을 '디자이너는…' 의 되풀이로 지웠다)"""
    if not a or not b:
        return False
    if a == b:
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    if n < 2 or n < 0.6 * min(len(a), len(b)):
        return False
    # 공통 어간 뒤에 남는 것이 둘 다 조사·어미(또는 없음)여야 같은 낱말
    return bool(PARTICLE_RE.match(a[n:])) and bool(PARTICLE_RE.match(b[n:]))


def _cho(ch: str) -> int:
    """한글 음절의 초성 번호(한글이 아니면 -1)."""
    o = ord(ch)
    return (o - 0xAC00) // 588 if 0xAC00 <= o <= 0xD7A3 else -1


def fragment_of(frag: str, nxt: str) -> bool:
    """`frag` 가 `nxt` 를 말하려다 끊긴 토막인가 — '쵀'/'최은준입니다', '디자'/'디자인은'. 1~3글자, 앞글자가 같거나
    (받침·모음이 잘못 들린 한 글자는) 초성이 같으면 토막으로 본다."""
    frag, nxt = ntok(frag), ntok(nxt)
    if not frag or not nxt or len(frag) > 3 or frag == nxt:
        return False
    if nxt.startswith(frag):
        return True
    if len(frag) == 1:
        return _cho(frag) == _cho(nxt[0]) and _cho(frag) >= 0
    return frag[0] == nxt[0] and (frag[1] == nxt[1] or _cho(frag[1]) == _cho(nxt[1]) >= 0)


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
                fillers: bool = True, strict: bool = False) -> tuple[list[Word], list[Removal]]:
    """되풀이한 앞부분과 추임새를 지운 단어 목록과 지운 구간들.
    strict: 편집 검사(2차) 용 — 확실한 되풀이(3어절·8글자 이상, 또는 NG 말이 낀 것)만 지운다. 잘라 붙인 결과물에서 다시
    받아 적은 전사는 문맥이 끊겨 있어 약한 증거로 지우면 대본 문장을 잃는다."""
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
        for ki in range(kj - 1, max(0, kj - MAX_BACK_WORDS) - 1, -1):   # 0 에서 멈춤(−1 이면 마지막 단어로 넘어감)
            i = live[ki]
            if drop[i] or words[j].start - words[i].start > MAX_BACK_SEC:
                break
            # 같은 말이 몇 어절 이어지나
            k = 0
            chars = 0
            while ki + k < kj and kj + k < len(live) and same_word(toks[live[ki + k]], toks[live[kj + k]]):
                chars += len(toks[live[kj + k]])
                k += 1
            # 첫 어절이 담화 표지('그래서', '이제' …)면 증거에서 뺀다 — 문장마다 같은 말로 시작하는 화자가 많다
            k_eff, chars_eff = k, chars
            if k and toks[live[kj]] in DISCOURSE:
                k_eff, chars_eff = k - 1, chars - len(toks[live[kj]])
            tail = [live[x] for x in range(ki + k, kj) if not drop[live[x]]]
            # 절어서 다시 시작(2026-10-04 채널 주인: '안녕하세요 쵀 / 안녕하세요 최은준입니다' 가 둘 다 나갔다):
            # 같은 말 한 어절(3글자 이상)이라도 그 뒤에 끊긴 토막(1~2어절·4글자 이하, 맺지 않은 말)만 남기고 쉼 뒤에 처음부터
            # 다시 말했으면 — 토막이 다음 시도의 그 자리 낱말의 앞부분이면 — 앞 시도를 지운다
            # 토막은 다시 말한 그 낱말들('디자인은 디자 / 디자인은 …')이나 바로 이어지는 낱말('쵀' / '최은준입니다')의 앞부분이어야
            # 한다 — '배울 때 / 디자인을 …'처럼 쉼표 뒤 이어 가는 말을 지우지 않게
            upcoming = [toks[live[x]] for x in range(kj, min(len(live), kj + k + 3))]
            stutter = (k_eff >= 1 and chars_eff >= 3 and (j_start or chars_eff >= 4) and 1 <= len(tail) <= 2
                       and sum(len(toks[x]) for x in tail) <= 4 and not any(is_final(words[x]) for x in tail)
                       and any(fragment_of(toks[tail[-1]], w) for w in upcoming))
            if not stutter and (k_eff < 2 or chars_eff < 4):
                continue
            strong = k_eff >= 3 and chars_eff >= 8
            i_start = attempt_start(i) or any(attempt_start(live[x]) for x in range(max(0, ki - 2), ki))
            # 새 시도는 보통 쉼·문장 끝 뒤에서 시작 — 쉼 없이 곧바로 고쳐 말한 경우는 같은 말이 길 때만(3어절·8글자)
            if not (stutter or (j_start and (i_start or strong)) or (strong and i_start)):
                continue
            # 꼬리 안에서 문장이 끝났는데(다시 나오지 않는 끝말) NG 말도 없으면 버려진 시도가 아니라 완성된 다른 문장이다
            # 예) '좋은 질문에는 … 있습니다. 결국 좋은 디자인은 / 좋은 질문에서' — 짧은 꼬리여도 지우지 않는다
            ng_tail = any(k_ in "".join(toks[x] for x in tail) for k_ in NG_WORDS)
            open_final = any(is_final(words[x]) and not _covered(toks, live, x, ki, kj) for x in tail[:-1])
            # 꼬리의 마지막 어절도 본다 — 다만 문장을 맺는 어미(…다·요·죠·까)로 끝날 때만(위스퍼는 끊긴 시도에도 마침표를
            # 찍는다). 예전엔 빠뜨려서 '좋은 디자인은 단순합니다. / 좋은 디자인은 정직합니다.'의 앞 문장이 통째로 지워졌다
            if tail and not open_final and FINAL_RE.search(toks[tail[-1]]) and not _covered(toks, live, tail[-1], ki, kj):
                open_final = True
            if (open_final and not ng_tail) or len(tail) > MAX_TAIL_OPEN:
                continue
            if strict and not (strong or ng_tail or stutter):
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
    """문장 끝 어절 x 가 다음 시도의 **그 문장 안에서** 다시 나오는가(같은 문장을 반복한 경우). 다음 시도의 문장이 끝나면
    더 보지 않는다 — 몇 문장 뒤의 같은 끝말('…시작합니다')을 반복으로 보면 완성된 앞 문장을 지운다."""
    t = toks[x]
    for y in range(kj, min(len(live), kj + 40)):
        if same_word(t, toks[live[y]]):
            return True
        if FINAL_RE.search(toks[live[y]]) and y > kj:
            return False
    return False


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
