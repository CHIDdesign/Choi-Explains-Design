"""✂️ 컷 편집 총괄(Opus) v2 — 규칙 엔진의 컷 초안을 대본·비언어 소리와 함께 보여 주고, 최종 EDL(무엇을 남기고 자를지)을 쓰게 한다.

v2(채널 주인 2026-10-02: "내용을 마음대로 잘라 없애거나, 헛기침 NG 가 들어가거나, 통으로 잘린다"): 초안의 모든 판단은 **후보**다 —
같은 대본 구간 겹침(리테이크), 읽기 회차, 짧은 NG 패턴, 단어 되풀이는 전부 흐릿한 판단이므로, 발화마다 점수·회차·이유를 보여 주고
Claude 가 발화 하나하나를 남길지 정한다(답에 없는 발화는 초안대로). 기침·헛기침·숨 같은 비언어 소리(vocal_events)는 인식 단어가
없어 남길 구간에 딸려 들어가므로 따로 목록으로 주고 자를지 정하게 한다.

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
    script_issues: list[dict] = field(default_factory=list)   # 대본 자체의 문제(duplicate·mangled·fragment) → fidelity.apply_script_issues

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
               raw: list[Word], events: Optional[list[dict]] = None, pass_of: Optional[dict[int, int]] = None) -> str:
    """Opus 에게 줄 입력: 대본(문장 번호) + 발화별 초안 판단(대본 일치 점수·회차·이유) + 단어 정리로 지운 말(앞뒤 문맥)
    + 비언어 소리 목록(기침·헛기침·숨 — 인식 단어 없음)."""
    lines = ["# 대본"]
    lines += [f"[{i + 1}] {t.strip()}" for i, (_, _, t) in enumerate(sentences)] or ["(대본 없음)"]
    lines.append("\n# 전사와 컷 초안(초안 판단은 전부 후보 — 당신이 발화마다 최종 결정)")
    for u in sorted(utts, key=lambda u: u.start):
        verdict = "[남김]" if u.kept else f"[뺌: {STATUS_LABEL.get(u.status, u.status)}{' — ' + u.note[:40] if u.note else ''}]"
        info = f"대본 {u.score:.0f}" if u.script_span else "대본 밖"
        if pass_of and len(set(pass_of.values())) > 1:
            info += f" · 회차 {pass_of.get(u.id, 0) + 1}"
        lines.append(f"U{u.id} {fmt_ts(u.start, True)}–{fmt_ts(u.end, True)} {verdict} ({info}) {u.asr_text}")
    if removals:
        lines.append("\n# 단어 정리로 지운 부분")
        for i, r in enumerate(removals):
            b, a = _context(raw, r["start"], r["end"])
            lines.append(f"R{i} {fmt_ts(r['start'], True)} [{r.get('reason', '')}] 「{r.get('text', '')}」 (앞: {b} / 뒤: {a})")
    if events:
        lines.append("\n# 비언어 소리(말소리는 있는데 인식 단어가 없는 토막 — 기침·헛기침·숨·입소리일 수 있다. 자를지 정한다. "
                     "'의심 단어'는 인식기가 단어로 적었지만 홀로 떨어진 추임새·헛기침일 수 있는 토막)")
        for e in events:
            kind = ("파열음" if e["kind"] == "burst" else f"의심 단어 「{e.get('text', '')}」(확신 {e.get('prob', 0):.2f})"
                    if e["kind"] == "word" else "약한 소리")
            lines.append(f"A{e['id']} {fmt_ts(e['start'], True)} {e['dur']:.2f}초 {e['dbfs']:.0f}dBFS "
                         f"{kind} (앞 말: {e.get('prev', '')} {e.get('gap_prev', 0):.2f}초 전 / "
                         f"뒤 말: {e.get('next', '')} {e.get('gap_next', 0):.2f}초 뒤)")
    return "\n".join(lines)


def event_cuts(result: dict[str, Any], events: list[dict]) -> tuple[list[int], dict[int, str]]:
    """Claude 가 자르기로 한 비언어 소리 id 와 이유."""
    ids: list[int] = []
    reasons: dict[int, str] = {}
    known = {e["id"] for e in events}
    for d in result.get("audio_events", []) or []:
        try:
            i = int(d.get("id", -1))
        except (TypeError, ValueError):
            continue
        if i in known and d.get("cut"):
            ids.append(i)
            reasons[i] = str(d.get("reason", ""))[:40]
    return ids, reasons


def apply(result: dict[str, Any], utts: list[Utterance], removals: list[dict], raw: list[Word]
          ) -> tuple[CutReview, list[dict]]:
    """Opus 의 판단을 적용한다. 반환: (요약, 남은 단어 정리 목록). 되살린 말의 단어는 그 시각의 발화에 끼워 넣는다.
    v2: 답에 모든 발화가 올 수 있다(초안과 같은 판단은 그대로, 다른 것만 바뀐다)."""
    rv = CutReview(notes=str(result.get("notes", ""))[:300])
    rv.script_issues = [i for i in (result.get("script_issues") or []) if isinstance(i, dict)][:40]
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
