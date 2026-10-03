"""컷 리스트: 남길 발화 + 호흡(템포 프리셋) → keep 구간(원본 시간)."""
from __future__ import annotations

import bisect
from dataclasses import dataclass

from ..models import Span, Utterance


@dataclass(frozen=True)
class Pace:
    name: str
    pre_pad: float        # 말 시작 전 여유
    post_pad: float       # 말 끝난 뒤 여유
    keep_gap: float       # 이보다 짧은 쉼은 그대로 둔다
    inner_gap: float      # 발화 내부 머뭇거림이 이보다 길면 잘라낸다
    min_keep: float = 0.22
    max_silence: float = 0.6   # 남긴 구간 안의 무음(VAD)이 이보다 길면 줄인다(Whisper 단어가 쉼을 덮어도)
    pause_after: float = 0.16  # 긴 무음을 줄일 때 앞말 뒤에 남기는 쉼
    pause_before: float = 0.12 # 뒷말 앞에 남기는 쉼


PACES: dict[str, Pace] = {
    # 레퍼런스 채널처럼 생각하는 '호흡'이 살아있는 설명형. 문장 사이 0.8초·문장 안 1.0초까지의 쉼은 그대로 둔다 — 예전(0.55·0.6)엔
    # 생각하는 쉼마다 점프컷이 생겨 말이 이상하게 이어졌다(채널 피드백). 줄일 때도 0.55초는 남긴다.
    "calm": Pace("calm", pre_pad=0.12, post_pad=0.22, keep_gap=0.8, inner_gap=1.3, max_silence=1.0,
                 pause_after=0.3, pause_before=0.25),
    "normal": Pace("normal", pre_pad=0.08, post_pad=0.16, keep_gap=0.5, inner_gap=0.9, max_silence=0.6,
                   pause_after=0.22, pause_before=0.16),
    "fast": Pace("fast", pre_pad=0.05, post_pad=0.10, keep_gap=0.22, inner_gap=0.4, max_silence=0.32),
    # 숏폼: 데드에어 제거
    "shorts": Pace("shorts", pre_pad=0.04, post_pad=0.08, keep_gap=0.14, inner_gap=0.28, min_keep=0.15,
                   max_silence=0.24, pause_after=0.1, pause_before=0.1),
    # 오프닝 하이라이트: 문장 조각 사이에 숨 한 번(앞 0.12 + 뒤 0.38초)이 남게
    "highlight": Pace("highlight", pre_pad=0.12, post_pad=0.38, keep_gap=0.3, inner_gap=0.6, min_keep=0.2,
                      max_silence=0.45, pause_after=0.16, pause_before=0.12),
}


def _snap_to_vad(t: float, regions: list[tuple[float, float]], starts: list[float], *, is_start: bool,
                 tol: float = 0.25) -> float:
    """Whisper 단어 경계(±0.2s 오차)를 VAD 경계로 보정.
    t 가 말소리 구간 안이면 그 구간의 경계로만 맞춘다 — 끝을 앞 구간의 끝으로 되돌리면 마지막 단어가 잘리고
    (Whisper 는 쉼 앞 단어 끝을 일찍 찍는다), 시작을 다음 구간 시작으로 밀면 첫 단어가 잘린다."""
    if not regions:
        return t
    i = bisect.bisect_right(starts, t) - 1
    if 0 <= i < len(regions) and regions[i][0] <= t < regions[i][1]:
        c = regions[i][0] if is_start else regions[i][1]
        return c if abs(c - t) <= tol else t
    cands = []
    for k in (i - 1, i, i + 1):
        if 0 <= k < len(regions):
            cands.append(regions[k][0] if is_start else regions[k][1])
    best = min(cands, key=lambda c: abs(c - t))
    return best if abs(best - t) <= tol else t


def _extend_end(t: float, regions: list[tuple[float, float]], starts: list[float], bounds: list[float],
                limit: float = 0.8) -> float:
    """t 가 말소리(VAD) 안이면 그 말소리 끝까지(최대 limit초, 다음 단어·지운 구간 시작 전까지) 늘린다."""
    i = bisect.bisect_right(starts, t) - 1
    if i < 0 or regions[i][1] <= t:
        return t
    nxt = bisect.bisect_right(bounds, t + 0.02)
    cap = bounds[nxt] - 0.03 if nxt < len(bounds) else float("inf")
    return max(t, min(regions[i][1], t + limit, cap))


def _extend_start(t: float, regions: list[tuple[float, float]], starts: list[float], bounds: list[float],
                  limit: float = 0.5) -> float:
    i = bisect.bisect_right(starts, t) - 1
    if i < 0 or not (regions[i][0] < t < regions[i][1]):
        return t
    prv = bisect.bisect_left(bounds, t - 0.02) - 1
    floor = bounds[prv] + 0.03 if prv >= 0 else float("-inf")
    return min(t, max(regions[i][0], t - limit, floor))


def _dropped_spans(ctx: list[Utterance], chosen_ids: set[int], chosen: list[Utterance]) -> list[Span]:
    """남기지 않는 발화의 구간 — 남기는 단어와 겹치는 부분은 뺀다(Whisper 단어 시각이 이웃과 살짝 겹쳐도 남길 말을
    깎지 않게)."""
    kept = sorted((w.start, w.end) for u in chosen for w in u.words)
    ks = [a for a, _ in kept]
    out: list[Span] = []
    for u in ctx:
        if id(u) in chosen_ids or not u.words:
            continue
        a, b = u.words[0].start, u.words[-1].end
        pieces = [Span(a, b)]
        j = max(0, bisect.bisect_left(ks, a) - 1)
        while j < len(kept) and kept[j][0] < b:
            ws, we = kept[j]
            nxt = []
            for p in pieces:
                if we <= p.start or ws >= p.end:
                    nxt.append(p)
                    continue
                if ws > p.start:
                    nxt.append(Span(p.start, ws))
                if we < p.end:
                    nxt.append(Span(we, p.end))
            pieces = nxt
            j += 1
        out.extend(p for p in pieces if p.dur > 0.05)
    return out


def build_keeps(
    utts: list[Utterance],
    *,
    pace: Pace,
    vad: list[tuple[float, float]] | None = None,
    media_duration: float,
    fps: float = 30.0,
    only_ids: set[int] | None = None,
    include_all: bool = False,
    exclude: list[Span] | None = None,
    context: list[Utterance] | None = None,
) -> list[Span]:
    """남길 발화들의 단어 시간으로 keep 구간을 만든다.
    exclude: 지운 되풀이·추임새 구간 — 늘릴 때 넘어가지 않고, 마지막에 한 번 더 빼서 소리가 새지 않게.
    context: 전체 발화(없으면 utts). 남기지 않는 발화(다시 말한 테이크·NG·숏폼에 넣지 않은 이웃 문장)는 경계로도 쓰고
    exclude 에도 넣는다 — 패딩·짧은 틈 합치기로 되살아나거나(“다시.”가 남음), 숏폼이 옆 문장 첫 단어까지 늘어나지 않게."""
    vad = sorted(vad or [])
    starts = [r[0] for r in vad]
    ctx = context if context is not None else utts
    chosen = [u for u in utts if (u.kept or include_all) and (only_ids is None or u.id in only_ids) and u.words]
    chosen_ids = {id(u) for u in chosen}
    dropped = _dropped_spans(ctx, chosen_ids, chosen)
    removed = list(exclude or [])
    exclude = sorted(removed + dropped, key=lambda x: x.start)
    # 다른 단어(남기든 지우든)·지운 구간의 경계 — 말소리 끝까지 늘릴 때 넘지 않는 선
    bounds_start = sorted([w.start for u in ctx for w in u.words] + [x.start for x in exclude])
    bounds_end = sorted([w.end for u in ctx for w in u.words] + [x.end for x in exclude])
    raw: list[Span] = []
    for u in utts:
        if (not u.kept and not include_all) or (only_ids is not None and u.id not in only_ids) or not u.words:
            continue
        # 발화 내부의 긴 머뭇거림 분리
        cur_s = u.words[0].start
        cur_e = u.words[0].end
        for w in u.words[1:]:
            if w.start - cur_e > pace.inner_gap:
                raw.append(Span(cur_s, cur_e))
                cur_s = w.start
            cur_e = max(cur_e, w.end)
        raw.append(Span(cur_s, cur_e))

    spans: list[Span] = []
    for s in raw:
        a = _snap_to_vad(s.start, vad, starts, is_start=True)
        b = _snap_to_vad(s.end, vad, starts, is_start=False)
        # Whisper 는 쉼 앞 마지막 단어의 끝을 0.5초 넘게 일찍 찍기도 한다('안녕하세요' → '안녕하세') → 말소리 끝까지
        b = _extend_end(b, vad, starts, bounds_start)
        a = _extend_start(a, vad, starts, bounds_end)
        if b <= a:
            a, b = s.start, s.end
        spans.append(Span(max(0.0, a - pace.pre_pad), min(media_duration, b + pace.post_pad)))
    spans.sort(key=lambda s: s.start)

    merged: list[Span] = []
    for s in spans:
        if merged and s.start - merged[-1].end <= pace.keep_gap:
            merged[-1] = Span(merged[-1].start, max(merged[-1].end, s.end))
        else:
            merged.append(s)
    if exclude:
        from .verify import subtract
        # 지운 되풀이·추임새: Whisper 단어 시각(±0.2초) 대신 실제 쉼 속에서 자른다 — 지운 말의 꼬리가 새지 않고,
        # 남기는 다음 말은 숨 한 번(0.06초) 뒤에 시작한다. 남기지 않는 발화는 이미 남길 단어를 뺀 구간이라 그대로
        kept_starts = sorted(w.start for u in chosen for w in u.words)
        kept_ends = sorted(w.end for u in chosen for w in u.words)
        widened = [_widen_removed(x, vad, starts, kept_starts, kept_ends) for x in removed if x.dur > 0.06]
        merged = subtract(merged, widened + dropped, min_keep=pace.min_keep)
    word_starts = sorted(w.start for u in utts if (u.kept or include_all) for w in u.words)
    merged = trim_dead_air(merged, vad, word_starts, max_silence=pace.max_silence,
                           pad_after=pace.pause_after, pad_before=pace.pause_before)
    merged = [s for s in merged if s.dur >= pace.min_keep]
    return quantize(merged, fps, media_duration)


def _widen_removed(x: Span, vad: list[tuple[float, float]], starts: list[float], kept_starts: list[float],
                   kept_ends: list[float]) -> Span:
    """지운 구간(Whisper 단어 시각)을 앞뒤 실제 쉼까지 넓힌다.
    끝: 지운 마지막 단어의 말소리(VAD)가 실제로 끝나는 곳까지(최대 +0.4초), 다음 남길 단어 0.06초 전까지.
    시작: 지운 첫 단어의 말소리 시작까지(그 말소리 구간이 앞 남길 단어 뒤에서 시작했을 때만, 최대 −0.3초)."""
    j = bisect.bisect_right(kept_starts, x.end - 0.02)
    nxt = kept_starts[j] if j < len(kept_starts) else float("inf")
    e = x.end
    i = bisect.bisect_right(starts, x.end) - 1
    if 0 <= i < len(vad) and vad[i][0] <= x.end < vad[i][1]:
        e = min(vad[i][1], x.end + 0.4)
    cap = nxt - 0.06
    e = max(x.end - 0.02, min(e, cap)) if cap > x.start + 0.05 else x.end - 0.02
    j = bisect.bisect_left(kept_ends, x.start + 0.02) - 1
    prv = kept_ends[j] if j >= 0 else float("-inf")
    floor = prv + 0.06
    s = x.start + 0.02
    i = bisect.bisect_right(starts, x.start) - 1
    if 0 <= i < len(vad) and vad[i][0] < x.start < vad[i][1] and vad[i][0] > floor:
        s = max(vad[i][0], x.start - 0.3)
    if floor < e:
        s = max(floor, s)
    return Span(min(s, e), e)


def trim_dead_air(spans: list[Span], vad: list[tuple[float, float]], word_starts: list[float], *,
                  max_silence: float, pad_after: float = 0.14, pad_before: float = 0.1) -> list[Span]:
    """남긴 구간 안에서 VAD 가 조용하다고 본 곳이 max_silence 보다 길면 가운데를 잘라 자연스러운 쉼만 남긴다.
    그 조용한 곳에서 시작하는 단어가 있으면(VAD 가 작은 소리를 놓친 것) 자르지 않는다."""
    if not vad:
        return spans
    out: list[Span] = []
    for sp in spans:
        cuts: list[tuple[float, float]] = []
        prev_end = None
        for a, b in vad:
            if b <= sp.start or a >= sp.end:
                continue
            if prev_end is not None:
                s0, s1 = max(prev_end, sp.start), min(a, sp.end)
                if s1 - s0 > max_silence:
                    lo, hi = s0 + pad_after, s1 - pad_before
                    i = bisect.bisect_left(word_starts, s0 + 0.05)
                    if hi > lo and not (i < len(word_starts) and word_starts[i] < s1 - 0.05):
                        cuts.append((lo, hi))
            prev_end = b if prev_end is None else max(prev_end, b)
        cur = sp.start
        for lo, hi in cuts:
            out.append(Span(cur, lo))
            cur = hi
        out.append(Span(cur, sp.end))
    return out


def quantize(spans: list[Span], fps: float, media_duration: float) -> list[Span]:
    """프레임 격자에 맞춰 영상/음성 길이가 정확히 일치하도록. 앞 구간과 1초 안에서 겹치는 시작은 앞 구간 끝으로 밀되,
    **뒤로 돌아가는 구간(콜드 오픈·대본 순서 재배치)은 그대로 둔다** — 2026-10-03 숏폼: 콜드 오픈 S57 뒤의 S47–S56 이
    모두 앞 구간 끝 뒤로 밀려 2프레임 미만이 되어 사라졌다(계획 45초 → 결과 11.8초, 편집 검사 drop 이 있을 때만)."""
    out: list[Span] = []
    last_frame = int(media_duration * fps)
    for s in spans:
        a = int(round(s.start * fps))
        b = min(int(round(s.end * fps)), last_frame)
        if out:
            prev_b = int(round(out[-1].end * fps))
            if prev_b - int(round(fps)) <= a < prev_b:
                a = prev_b
        if b - a >= 2:
            out.append(Span(a / fps, b / fps))
    return out


def keeps_for_segments(utts: list[Utterance], ids: list[int], *, pace: Pace, vad, media_duration: float,
                       fps: float, exclude: list[Span] | None = None) -> list[Span]:
    """숏폼: 지정한 발화 순서대로(재배치 허용) keep 구간 생성. 연속 발화는 합친다."""
    by_id = {u.id: u for u in utts}
    groups: list[list[int]] = []
    for i in ids:
        if i not in by_id:
            continue
        if groups and i == groups[-1][-1] + 1:
            groups[-1].append(i)
        else:
            groups.append([i])
    out: list[Span] = []
    for g in groups:
        sub = [by_id[i] for i in g]
        # 이웃 문장(숏폼에 넣지 않은 발화)까지 알려 줘야 말소리 끝까지 늘릴 때 그 문장으로 넘어가지 않는다
        spans = build_keeps(sub, pace=pace, vad=vad, media_duration=media_duration, fps=fps,
                            include_all=True, exclude=exclude, context=utts)
        out.extend(spans)
    return out
