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


PACES: dict[str, Pace] = {
    # 셜록현준처럼 생각하는 '호흡'이 살아있는 설명형
    "calm": Pace("calm", pre_pad=0.12, post_pad=0.22, keep_gap=0.55, inner_gap=0.9),
    "normal": Pace("normal", pre_pad=0.08, post_pad=0.16, keep_gap=0.38, inner_gap=0.65),
    "fast": Pace("fast", pre_pad=0.05, post_pad=0.10, keep_gap=0.22, inner_gap=0.4),
    # 숏폼: 데드에어 제거
    "shorts": Pace("shorts", pre_pad=0.04, post_pad=0.08, keep_gap=0.14, inner_gap=0.28, min_keep=0.15),
}


def _snap_to_vad(t: float, regions: list[tuple[float, float]], starts: list[float], *, is_start: bool,
                 tol: float = 0.25) -> float:
    """Whisper 단어 경계(±0.2s 오차)를 VAD 경계로 보정."""
    if not regions:
        return t
    i = bisect.bisect_right(starts, t) - 1
    cands = []
    for k in (i - 1, i, i + 1):
        if 0 <= k < len(regions):
            cands.append(regions[k][0] if is_start else regions[k][1])
    best = min(cands, key=lambda c: abs(c - t))
    return best if abs(best - t) <= tol else t


def build_keeps(
    utts: list[Utterance],
    *,
    pace: Pace,
    vad: list[tuple[float, float]] | None = None,
    media_duration: float,
    fps: float = 30.0,
    only_ids: set[int] | None = None,
    include_all: bool = False,
) -> list[Span]:
    """남길 발화들의 단어 시간으로 keep 구간을 만든다."""
    vad = sorted(vad or [])
    starts = [r[0] for r in vad]
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
    merged = [s for s in merged if s.dur >= pace.min_keep]
    return quantize(merged, fps, media_duration)


def quantize(spans: list[Span], fps: float, media_duration: float) -> list[Span]:
    """프레임 격자에 맞춰 영상/음성 길이가 정확히 일치하도록."""
    out: list[Span] = []
    last_frame = int(media_duration * fps)
    for s in spans:
        a = int(round(s.start * fps))
        b = min(int(round(s.end * fps)), last_frame)
        if out:
            prev_b = int(round(out[-1].end * fps))
            a = max(a, prev_b)
        if b - a >= 2:
            out.append(Span(a / fps, b / fps))
    return out


def keeps_for_segments(utts: list[Utterance], ids: list[int], *, pace: Pace, vad, media_duration: float,
                       fps: float) -> list[Span]:
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
        spans = build_keeps(sub, pace=pace, vad=vad, media_duration=media_duration, fps=fps,
                            include_all=True)
        out.extend(spans)
    return out
