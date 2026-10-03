"""호흡 설계 — 이어 붙인 곳마다 문장의 경계에 맞는 쉼을 둔다.

2026-10-04 채널 주인: "컷편집 실력은 좋아졌는데 너무 빨리 전환된다. 마디마디에 자연스러운 공백이 있어야 하는데 훅훅 넘어간다.
차분하고 딥한 주제라 릴스 포함 호흡 빠른 편집은 아니다." 실측(6:25 롱폼): 말 사이 쉼 중앙값 0.15초, 0.4초 넘는 쉼은 8곳뿐,
49초 숏폼은 0.25초 넘는 쉼이 하나도 없었다. 원인은 이어 붙인 곳(다른 테이크·다른 회차·지운 리테이크 사이)의 쉼이 문장 안이든
문단이 바뀌든 똑같이 '앞 여유 0.12 + 뒤 여유 0.22초'였던 것 — 대본을 두 번 읽은 원본은 거의 모든 문장 경계가 이어 붙인 곳이다.

이 모듈은 재생 순서로 놓인 keep 구간에서 이웃 둘(A → B)마다
1. 경계의 종류를 본다: 문장 안(inner) · 문장 사이(sentence) · 문단·생각이 바뀌는 곳(paragraph) · 여운(beat, 정점·결론 뒤 또는
   ✂️ 편집 감독이 `pauses` 로 지정한 곳)
2. 지금 들리는 쉼(A 의 마지막 말소리 뒤 + B 의 첫 말소리 앞)을 재고
3. 목표보다 짧으면 원본의 실제 무음 속으로 A 의 끝을 늘리고(생각이 내려앉는 쪽 먼저) 모자라면 B 의 시작을 당긴다.
   말소리(VAD)·다른 단어·지운 구간·다른 keep·원본 파일 경계는 넘지 않는다 — 무음을 지어내지 않으므로 영상과 소리는 그대로 맞고,
   화면에는 말을 마친 화자의 얼굴이 잠깐 머문다(편집자들이 말하는 '숨 쉴 틈').
목표보다 긴 쉼은 건드리지 않는다(긴 무음은 cuts.trim_dead_air 가 줄인다).
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from ..models import Span, Utterance


@dataclass(frozen=True)
class Breath:
    inner: float        # 같은 문장의 조각 사이(말이 끊기지 않게 짧게)
    sentence: float     # 문장과 문장 사이
    paragraph: float    # 문단(대목)·생각이 바뀌는 곳
    beat: float         # 정점·결론·질문 뒤 여운
    tail_share: float = 0.6   # 늘릴 몫 중 앞말 뒤(A 의 끝)에 먼저 주는 비율
    margin: float = 0.06      # 다른 말소리·지운 구간·다른 keep 에서 띄울 거리

    def target(self, kind: str) -> float:
        return float(getattr(self, kind, self.sentence))


# 수치 근거: 낭독 녹음 48개의 실측(Kazlauskienė & Kalašinskaitė 2020) — 문장 사이 빠른 화자 0.20~0.98초 · 느린 화자 0.34~1.36초,
# 문단 사이 0.40~1.34초 · 0.75~1.80초(prompts/skills/agents/editor.md '호흡' 절). 측정된 중앙값 0.15초는 사람이 읽을 때 나올 수 없는
# 길이였다. calm(롱폼 기본)은 채널 톤(차분한 고백·에세이)에 맞춰 문장 0.6 · 문단 1.0 · 여운 1.3초, 숏폼도 '데드에어 제거'가 아니라
# 문장 끝 0.4초 안팎의 숨은 남긴다.
BREATHS: dict[str, Breath] = {
    "calm": Breath(inner=0.28, sentence=0.62, paragraph=1.0, beat=1.3),
    "normal": Breath(inner=0.2, sentence=0.45, paragraph=0.72, beat=0.95),
    "fast": Breath(inner=0.12, sentence=0.26, paragraph=0.36, beat=0.5),
    "shorts_calm": Breath(inner=0.15, sentence=0.42, paragraph=0.6, beat=0.9),
    "shorts": Breath(inner=0.08, sentence=0.16, paragraph=0.22, beat=0.3),
    "highlight": Breath(inner=0.2, sentence=0.45, paragraph=0.45, beat=0.45),
}
KINDS = ("inner", "sentence", "paragraph", "beat")
EXPLICIT_RANGE = (0.5, 1.6)      # 편집 감독이 지정한 쉼(초)의 범위 — 편집 검사의 '긴 무음'(max_silence + 0.25) 아래

# 문장이 끝나는 어절(맺는 어미·문장부호) — 대본 위치가 없는 발화(애드리브)의 경계를 고를 때
_END_RE = re.compile(r"(?:[.?!…]|다|요|죠|까|네|군|지|니다|세요|어요|아요|에요|예요|래요|대요|거든요|잖아요)[\"'”’)\]]*$")


def ends_sentence(text: str) -> bool:
    t = (text or "").strip()
    return bool(t) and bool(_END_RE.search(t))


@dataclass
class Join:
    """이어 붙인 곳 하나의 기록(리포트·편집 검사용)."""
    index: int          # B 의 위치(재생 순서)
    kind: str
    target: float
    before: float       # 늘리기 전에 들리던 쉼
    after: float        # 늘린 뒤
    explicit: bool = False


@dataclass
class BreathReport:
    joins: list[Join] = field(default_factory=list)

    @property
    def added(self) -> float:
        return sum(max(0.0, j.after - j.before) for j in self.joins)

    def summary(self) -> str:
        if not self.joins:
            return "이어 붙인 곳 없음"
        by = {k: [j for j in self.joins if j.kind == k] for k in KINDS}
        parts = []
        for k, label in (("paragraph", "문단"), ("sentence", "문장"), ("inner", "문장 안"), ("beat", "여운")):
            js = by[k]
            if js:
                avg = sum(j.after for j in js) / len(js)
                short = sum(1 for j in js if j.after < j.target - 0.08)
                parts.append(f"{label} {len(js)}곳 평균 {avg:.2f}초" + (f"(원본 무음이 모자란 곳 {short})" if short else ""))
        return " · ".join(parts) + f" — 늘린 시간 {self.added:.1f}초"

    def to_dict(self) -> dict:
        return {"added": round(self.added, 2),
                "joins": [{"i": j.index, "kind": j.kind, "target": round(j.target, 2), "before": round(j.before, 2),
                           "after": round(j.after, 2), "explicit": j.explicit} for j in self.joins]}


def merge_spans(spans: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for a, b in sorted((float(a), float(b)) for a, b in spans if b > a):
        if out and a <= out[-1][1] + 1e-6:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _speech_end(k: Span, speech: list[tuple[float, float]], starts: list[float]) -> float:
    """구간 k 안에서 마지막 말소리가 끝나는 시각(없으면 k.start)."""
    i = bisect.bisect_left(starts, k.end) - 1
    while i >= 0:
        a, b = speech[i]
        if b > k.start and a < k.end:
            return min(b, k.end)
        if b <= k.start:
            break
        i -= 1
    return k.start


def _speech_start(k: Span, speech: list[tuple[float, float]], starts: list[float]) -> float:
    """구간 k 안에서 첫 말소리가 시작하는 시각(없으면 k.end)."""
    i = max(0, bisect.bisect_right(starts, k.start) - 1)
    while i < len(speech):
        a, b = speech[i]
        if a >= k.end:
            break
        if b > k.start:
            return max(a, k.start)
        i += 1
    return k.end


def _room_after(t: float, walls: list[tuple[float, float]], limit: float) -> float:
    """t 뒤로 늘릴 수 있는 길이 — 가장 가까운 벽(말소리·지운 구간·다른 keep)의 시작까지. t 가 벽 안이면 0."""
    nxt = limit
    for a, b in walls:
        if a <= t < b - 1e-6:
            return 0.0
        if a >= t:
            nxt = min(nxt, a)
    return max(0.0, nxt - t)


def _room_before(t: float, walls: list[tuple[float, float]], floor: float) -> float:
    prv = floor
    for a, b in walls:
        if a + 1e-6 < t <= b:
            return 0.0
        if b <= t:
            prv = max(prv, b)
    return max(0.0, t - prv)


def breathe(keeps: list[Span], *, speech: Sequence[tuple[float, float]], blocked: Sequence[tuple[float, float]] = (),
            kind_of: Callable[[int], tuple[str, Optional[float]]], breath: Breath, media_duration: float,
            bounds: Sequence[tuple[float, float]] = (), budget: Optional[float] = None) -> tuple[list[Span], BreathReport]:
    """재생 순서의 keeps → 이어 붙인 곳마다 경계에 맞는 쉼을 둔 keeps(순서 그대로) + 기록.

    speech: 원본의 말소리 구간(VAD ∪ 모든 단어 — 남기지 않는 말도 벽이다). blocked: 지운 구간(되풀이·기침·편집 검사 drop).
    kind_of(i): keeps[i-1] → keeps[i] 경계의 (종류, 지정 초 또는 None). bounds: 원본 파일(묶음) 구간 — 넘지 않는다.
    budget: 늘릴 수 있는 총 시간(숏폼 길이 상한) — 넘으면 문단 > 여운 > 문장 > 문장 안 순서로 나눠 준다."""
    report = BreathReport()
    if len(keeps) < 2:
        return list(keeps), report
    sp = merge_spans(speech)
    sp_starts = [a for a, _ in sp]
    out = [Span(k.start, k.end) for k in keeps]
    group = [(float(a), float(b)) for a, b in bounds] or [(0.0, float(media_duration))]

    def grp(t: float) -> tuple[float, float]:
        for a, b in group:
            if a - 1e-6 <= t <= b + 1e-6:
                return a, b
        return 0.0, float(media_duration)

    # 1) 경계마다 지금 들리는 쉼과 목표
    plans: list[tuple[int, str, float, float, bool]] = []      # (i, kind, target, now, explicit)
    for i in range(1, len(out)):
        a, b = out[i - 1], out[i]
        kind, sec = kind_of(i)
        kind = kind if kind in KINDS else "sentence"
        explicit = sec is not None
        target = min(max(float(sec), EXPLICIT_RANGE[0]), EXPLICIT_RANGE[1]) if explicit else breath.target(kind)
        now = (a.end - _speech_end(a, sp, sp_starts)) + (_speech_start(b, sp, sp_starts) - b.start)
        plans.append((i, kind, target, max(0.0, now), explicit))
    need = {i: max(0.0, t - now) for i, _, t, now, _ in plans}
    if budget is not None:
        left = max(0.0, float(budget))
        order = {"paragraph": 0, "beat": 1, "sentence": 2, "inner": 3}
        grant: dict[int, float] = {}
        for i, kind, *_ in sorted(plans, key=lambda p: order.get(p[1], 4)):
            g = min(need[i], left)
            grant[i] = g
            left -= g
        need = grant

    # 2) 늘리기 — 벽: 말소리 · 지운 구간 · 다른 keep(앞에서 늘린 값으로)
    base_walls = merge_spans(list(sp) + [(float(a), float(b)) for a, b in blocked])
    for i, kind, target, now, explicit in plans:
        a, b = out[i - 1], out[i]
        want = need.get(i, 0.0)
        if want > 0.02:
            others = [(k.start, k.end) for j, k in enumerate(out) if j not in (i - 1, i)]
            walls = base_walls + others
            ga, gb = grp(a.end)
            room_a = _room_after(a.end, walls, gb) - breath.margin
            if b.start >= a.end - 1e-6 and grp(b.start) == (ga, gb):   # B 가 원본에서 바로 뒤 — 겹치지 않게 B 시작까지
                room_a = min(room_a, b.start - a.end)
            room_a = max(0.0, room_a)
            ha, _ = grp(b.start)
            room_b = _room_before(b.start, walls, ha) - breath.margin
            if b.start >= a.end - 1e-6:
                room_b = min(room_b, b.start - a.end)
            room_b = max(0.0, room_b)
            ext_a = min(want * breath.tail_share, room_a)
            ext_b = min(want - ext_a, room_b)
            ext_a = min(want - ext_b, room_a)              # B 앞에 자리가 없으면 A 뒤에 더
            if b.start >= a.end - 1e-6:                    # 둘 다 같은 무음을 쓰면 겹친다 — 합이 사이 길이를 넘지 않게
                over = (a.end + ext_a) - (b.start - ext_b)
                if over > 0:
                    ext_b = max(0.0, ext_b - over)
            out[i - 1] = Span(a.start, min(float(media_duration), a.end + ext_a))
            out[i] = Span(max(0.0, b.start - ext_b), b.end)
        after = now + (out[i - 1].end - a.end) + (b.start - out[i].start)
        report.joins.append(Join(i, kind, target, now, after, explicit))
    return out, report


def join_kinds(keeps: list[Span], utts: list[Utterance], *, clean: str = "",
               sentence_spans: Sequence[tuple[int, int]] = (), explicit_after: Optional[dict[int, float]] = None,
               beat_after: Sequence[int] = ()) -> Callable[[int], tuple[str, Optional[float]]]:
    """keeps(재생 순서)의 경계 종류를 정하는 함수. 대본 위치(script_span)가 있으면 대본의 문단(줄바꿈)·문장 경계로, 없으면
    앞 발화의 끝말(맺는 어미·문장부호)로. explicit_after: {발화 id: 쉼 초}(편집 감독 pauses) — 그 발화로 끝나는 경계에 그대로.
    beat_after: 여운을 둘 발화 id(정점·답) — 지정 쉼이 없을 때 beat."""
    kept = [u for u in utts if u.kept and u.words]
    explicit_after = explicit_after or {}
    beats = set(beat_after)
    sent_ends = sorted(e for _, e in sentence_spans)
    sent_starts = sorted(s for s, _ in sentence_spans)

    def para(pos: int) -> int:
        return clean.count("\n", 0, max(0, min(pos, len(clean))))

    def last_utt(k: Span) -> Optional[Utterance]:
        best = None
        for u in kept:
            ws = [w for w in u.words if k.start - 0.05 <= w.end <= k.end + 0.05 and w.start < k.end]
            if ws and (best is None or ws[-1].end > best[1]):
                best = (u, ws[-1].end)
        return best[0] if best else None

    def first_utt(k: Span) -> Optional[Utterance]:
        best = None
        for u in kept:
            ws = [w for w in u.words if k.start - 0.05 <= w.start <= k.end + 0.05 and w.end > k.start]
            if ws and (best is None or ws[0].start < best[1]):
                best = (u, ws[0].start)
        return best[0] if best else None

    def near(xs: list[int], pos: int, tol: int) -> bool:
        j = bisect.bisect_left(xs, pos - tol)
        return j < len(xs) and xs[j] <= pos + tol

    cache: dict[int, tuple[str, Optional[float]]] = {}

    def kind_of(i: int) -> tuple[str, Optional[float]]:
        if i in cache:
            return cache[i]
        u1, u2 = last_utt(keeps[i - 1]), first_utt(keeps[i])
        res: tuple[str, Optional[float]] = ("sentence", None)
        if u1 is not None and u1.id in explicit_after and (u2 is None or u2.id != u1.id):
            res = ("beat", float(explicit_after[u1.id]))
        elif u1 is not None and u1.id in beats and (u2 is None or u2.id != u1.id):
            res = ("beat", None)
        elif u1 is not None and u2 is not None:
            s1, s2 = u1.script_span, u2.script_span
            if s1 and s2 and clean:
                # 대본 위치는 정렬 오차로 몇 글자 어긋날 수 있다 — 대본에서 이어지는 경계면 그 사이(±3자)에 줄바꿈이 있는지,
                # 아니면(콜드 오픈·재배치) 두 발화의 문단 번호로
                forward = s1[1] - 3 <= s2[0] <= s1[1] + 40
                if (forward and "\n" in clean[max(0, s1[1] - 3): s2[0] + 3]) or \
                        (not forward and para((s1[0] + s1[1]) // 2) != para((s2[0] + s2[1]) // 2)):
                    res = ("paragraph", None)
                elif u1.id == u2.id:
                    res = ("inner", None)
                elif near(sent_ends, s1[1], 3) or near(sent_starts, s2[0], 3):
                    res = ("sentence", None)
                else:
                    res = ("inner", None)
            elif u1.id == u2.id:
                res = ("inner", None)
            else:
                last = u1.words[-1].text if u1.words else u1.text
                res = ("sentence", None) if ends_sentence(u1.text) or ends_sentence(last) else ("inner", None)
        cache[i] = res
        return res

    return kind_of
