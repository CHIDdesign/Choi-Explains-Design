"""✂️ 컷 편집 총괄(Opus) — 규칙 엔진의 컷 초안을 대본과 함께 보여 주고, 틀린 판단만 고치게 한다.

규칙(takes.py · align.py)은 빠르고 기계적인 초안을 만든다: 같은 대목의 테이크 중 하나만 남기기, NG 빼기, 끊긴 시도·추임새
지우기. 문맥을 모르니 '같은 말로 시작하는 다른 문장'을 되풀이로, 인식이 틀린 대본 문장을 애드리브로 오인한다. 최종 판단은
대본과 전사 전체를 읽는 Opus 가 한다(채널 주인: 편집 전체의 총괄은 Opus, 외부 프로그램은 말단 작업만). 마지막 안전망은
여전히 대본 충실 보증(fidelity.py) — Opus 가 틀려도 대본 문장은 빠지지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..models import Utterance, Word
from ..util import fmt_ts

STATUS_LABEL = {"retake": "다시 말한 테이크", "meta": "NG·메타 발화", "noise": "잡음", "director_drop": "편집 감독이 뺌",
                "editor_cut": "컷 총괄이 뺌"}


@dataclass
class CutReview:
    restored_utts: list[int] = field(default_factory=list)
    cut_utts: list[int] = field(default_factory=list)
    restored_removals: list[int] = field(default_factory=list)
    notes: str = ""
    reasons: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        parts = []
        if self.restored_utts:
            parts.append(f"되살린 발화 {len(self.restored_utts)}")
        if self.cut_utts:
            parts.append(f"더 뺀 발화 {len(self.cut_utts)}")
        if self.restored_removals:
            parts.append(f"되살린 말 {len(self.restored_removals)}")
        return " · ".join(parts) or "초안 그대로"


def _context(raw: list[Word], start: float, end: float, n: int = 6) -> tuple[str, str]:
    before = [w.text for w in raw if w.end <= start + 0.01][-n:]
    after = [w.text for w in raw if w.start >= end - 0.01][:n]
    return " ".join(before), " ".join(after)


def draft_text(sentences: list[tuple[int, int, str]], utts: list[Utterance], removals: list[dict],
               raw: list[Word]) -> str:
    """Opus 에게 줄 입력: 대본(문장 번호) + 발화별 초안 판단 + 단어 정리로 지운 말(앞뒤 문맥)."""
    lines = ["# 대본"]
    lines += [f"[{i + 1}] {t.strip()}" for i, (_, _, t) in enumerate(sentences)] or ["(대본 없음)"]
    lines.append("\n# 전사와 컷 초안")
    for u in sorted(utts, key=lambda u: u.start):
        verdict = "[남김]" if u.kept else f"[뺌: {STATUS_LABEL.get(u.status, u.status)}{' — ' + u.note[:40] if u.note else ''}]"
        lines.append(f"U{u.id} {fmt_ts(u.start, True)}–{fmt_ts(u.end, True)} {verdict} {u.asr_text}")
    if removals:
        lines.append("\n# 단어 정리로 지운 부분")
        for i, r in enumerate(removals):
            b, a = _context(raw, r["start"], r["end"])
            lines.append(f"R{i} {fmt_ts(r['start'], True)} [{r.get('reason', '')}] 「{r.get('text', '')}」 (앞: {b} / 뒤: {a})")
    return "\n".join(lines)


def apply(result: dict[str, Any], utts: list[Utterance], removals: list[dict], raw: list[Word]
          ) -> tuple[CutReview, list[dict]]:
    """Opus 의 판단을 적용한다. 반환: (요약, 남은 단어 정리 목록). 되살린 말의 단어는 그 시각의 발화에 끼워 넣는다."""
    rv = CutReview(notes=str(result.get("notes", ""))[:300])
    by_id = {u.id: u for u in utts}
    for d in result.get("utterances", []) or []:
        u = by_id.get(int(d.get("id", -1)))
        if u is None or not u.words:
            continue
        reason = str(d.get("reason", ""))[:80]
        if d.get("keep") and not u.kept and u.status != "noise":
            u.note = f"✂️ 총괄이 살림: {reason} (초안: {STATUS_LABEL.get(u.status, u.status)})"
            u.status = "keep"
            rv.restored_utts.append(u.id)
        elif not d.get("keep") and u.kept:
            u.status, u.note = "editor_cut", f"✂️ 총괄이 뺌: {reason}"
            rv.cut_utts.append(u.id)
    restore_ids = {int(d.get("id", -1)) for d in result.get("removals", []) or [] if d.get("keep_removed")}
    remaining: list[dict] = []
    for i, r in enumerate(removals):
        if i not in restore_ids:
            remaining.append(r)
            continue
        ws = [w for w in raw if r["start"] - 0.02 <= w.start and w.end <= r["end"] + 0.02]
        host = _host(utts, r["start"], r["end"])
        if ws and host is not None:
            have = {(round(w.start, 2), w.text) for w in host.words}
            host.words = sorted(host.words + [w for w in ws if (round(w.start, 2), w.text) not in have],
                                key=lambda w: w.start)
            host.start, host.end = host.words[0].start, host.words[-1].end
            host.text = host.asr_text = " ".join(w.text for w in host.words)
            if not host.kept:
                host.status, host.note = "keep", "✂️ 총괄이 살림(지운 말 되살림)"
        rv.restored_removals.append(i)
    return rv, remaining


def _host(utts: list[Utterance], a: float, b: float) -> Optional[Utterance]:
    """되살릴 말이 들어갈 발화: 그 시각을 덮거나 가장 가까운(2초 안) 남긴 발화, 없으면 덮는 발화."""
    kept = [u for u in utts if u.kept and u.words]
    for u in kept:
        if u.start - 0.3 <= a <= u.end + 0.3 or u.start - 0.3 <= b <= u.end + 0.3:
            return u
    near = min(kept, key=lambda u: min(abs(a - u.end), abs(u.start - b)), default=None)
    if near is not None and min(abs(a - near.end), abs(near.start - b)) <= 2.0:
        return near
    return next((u for u in utts if u.start - 0.3 <= a <= u.end + 0.3), None)
