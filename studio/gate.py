"""품질 게이트 — "이상하면 렌더하지 않는다"(docs/upgrade/08_품질_게이트.md).

2026-10-01 테스트는 로그에 '얼굴 화면 비율 95% · 얼굴만 이어진 최장 397초'가 찍혔고 아트 디렉터가 '대본 전체가 두 번
들어갔다'고 적었는데도 20분을 들여 렌더했다. 오토파일럿은 '사람이 안 봐도 된다'가 아니라 '사람이 볼 필요가 있을 때
멈춰서 알려 준다'여야 한다.

검사는 모두 순수 함수(입력 = 발화·그래픽·통계, 출력 = GateResult)이고 파이프라인이 단계 사이에서 부른다:
- 게이트 A(구조) — 컷 확정 뒤 A1·A2·A3·A5, 렌더 props 확정 뒤 A6·A7·A8·A9
- 게이트 B(화면 글자) — 렌더 props 확정 뒤 B3·B4·B5
level: block(수리 뒤에도 실패하면 렌더하지 않음) · repair(수리 한 번, 그래도 실패하면 warn 으로) · warn(리포트 맨 위).
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from .models import Utterance
from .util import fmt_ts, write_json

LEVELS = ("block", "repair", "warn")


@dataclass
class GateResult:
    id: str                         # "A1_length"
    ok: bool
    level: str                      # block | repair | warn
    measured: dict = field(default_factory=dict)
    message: str = ""               # 사람에게 보여 줄 한 줄
    repair: str = ""                # 수리 루틴 이름
    repaired: bool = False          # 수리 뒤 통과
    skipped: bool = False           # 검사할 거리가 없음(대본 없음 등)

    @property
    def blocking(self) -> bool:
        return not self.ok and self.level == "block"

    def to_dict(self) -> dict:
        return asdict(self)


class GateBlocked(RuntimeError):
    """block 게이트가 수리 뒤에도 실패 — 렌더하지 않는다(CLI --force-render 로만 무시)."""

    def __init__(self, results: list[GateResult], where: str = ""):
        self.results = results
        bad = [r for r in results if r.blocking]
        lines = [f"- {r.id}: {r.message}" for r in bad]
        super().__init__("품질 게이트에서 멈췄습니다 — 이대로 렌더하면 이상한 영상이 나옵니다"
                         + (f"({where})" if where else "") + ":\n" + "\n".join(lines))


def _ok(id_: str, level: str, measured: dict, msg: str, repair: str = "") -> GateResult:
    return GateResult(id_, True, level, measured, msg, repair)


def _bad(id_: str, level: str, measured: dict, msg: str, repair: str = "") -> GateResult:
    return GateResult(id_, False, level, measured, msg, repair)


def _skip(id_: str, level: str, msg: str) -> GateResult:
    return GateResult(id_, True, level, {}, msg, skipped=True)


_ALNUM = re.compile(r"[0-9A-Za-z가-힣]")


def _chars(text: str) -> int:
    return len(_ALNUM.findall(text or ""))


def _kept(utts: Iterable[Utterance]) -> list[Utterance]:
    return sorted((u for u in utts if u.kept), key=lambda u: u.start)


# ---------------------------------------------------------------------------
# 게이트 A — 구조(컷 확정 직후)
# ---------------------------------------------------------------------------

def a1_length(utts: list[Utterance], script: str, edit_sec: float, *, slack: float = 1.25,
              adlib_slack: float = 1.8, coverage: float = 1.0) -> GateResult:
    """편집 길이 vs 대본 분량. 발화 속도는 이 편집본의 실측(글자/초) — 대본 글자 수 ÷ 속도 = 대본을 한 번 읽는 길이.
    대본에 맞은 발화의 글자가 대본의 1.25배를 넘으면(같은 문장이 두 번) 실패. 대본을 거의 다 읽은 녹음(coverage ≥ 0.8)이면
    대본 밖 발화까지 합쳐 1.8배를 넘어도 실패(인식이 대본에 못 맞춘 두 번째 회차) — 대본이 개요뿐이라 말이 훨씬 많은
    녹음은 이 둘째 기준을 보지 않는다."""
    n = _chars(script)
    if n < 20:
        return _skip("A1_length", "block", "대본이 없어 길이 검사를 건너뜀")
    kept = _kept(utts)
    all_c = sum(_chars(u.text) for u in kept)
    script_c = sum(_chars(u.text) for u in kept if u.script_span)
    rate = all_c / max(1e-6, edit_sec)
    expected = n / max(1e-6, rate) if rate > 0 else 0.0
    m = {"long_sec": round(edit_sec, 1), "expected_sec": round(expected, 1), "rate_cps": round(rate, 2),
         "script_ratio": round(script_c / n, 3), "all_ratio": round(all_c / n, 3)}
    if script_c / n > slack or (coverage >= 0.8 and all_c / n > adlib_slack):
        return _bad("A1_length", "block", m,
                    f"편집 길이 {fmt_ts(edit_sec)} — 대본을 한 번 읽는 분량(약 {fmt_ts(expected)})의 "
                    f"{edit_sec / max(1e-6, expected):.1f}배(같은 대본이 두 번 들어간 것으로 보임)", "passes")
    return _ok("A1_length", "block", m, f"편집 길이 {fmt_ts(edit_sec)} · 대본 분량 약 {fmt_ts(expected)}")


def a2_planned(edit_sec: float, expected_sec: float, *, lo: float = 0.8, hi: float = 1.25) -> GateResult:
    """총괄 감독이 브리프에 적은 예상 길이(integrity.expected_sec)와의 차이. AI 추정이라 경고만."""
    if expected_sec <= 0:
        return _skip("A2_planned", "warn", "감독 예상 길이 없음")
    r = edit_sec / expected_sec
    m = {"long_sec": round(edit_sec, 1), "planned_sec": round(expected_sec, 1), "ratio": round(r, 2)}
    if lo <= r <= hi:
        return _ok("A2_planned", "warn", m, f"감독 예상 {fmt_ts(expected_sec)} 의 {r:.2f}배")
    return _bad("A2_planned", "warn", m, f"편집 길이 {fmt_ts(edit_sec)} 가 감독 예상 {fmt_ts(expected_sec)} 의 {r:.2f}배")


def duplicate_pairs(utts: list[Utterance], *, overlap: float = 0.6, min_chars: int = 6) -> list[tuple[Utterance, Utterance]]:
    """같은 대본 구간(짧은 쪽의 60% 이상 겹침)을 덮는 남긴 발화 쌍. 6글자 미만 구간('네' 같은 것)은 보지 않는다."""
    kept = sorted((u for u in utts if u.kept and u.script_span and u.script_span[1] - u.script_span[0] >= min_chars),
                  key=lambda u: u.script_span[0])   # type: ignore[index]
    out: list[tuple[Utterance, Utterance]] = []
    for i, a in enumerate(kept):
        a0, a1 = a.script_span     # type: ignore[misc]
        for b in kept[i + 1:]:
            b0, b1 = b.script_span  # type: ignore[misc]
            if b0 >= a1:
                break
            inter = min(a1, b1) - max(a0, b0)
            if inter > 0 and inter >= overlap * min(a1 - a0, b1 - b0):
                out.append((a, b))
    return out


def a3_duplicates(utts: list[Utterance], script: str) -> GateResult:
    if _chars(script) < 20:
        return _skip("A3_duplicates", "block", "대본이 없어 중복 검사를 건너뜀")
    pairs = duplicate_pairs(utts)
    m = {"pairs": len(pairs),
         "examples": [{"a": a.id, "b": b.id, "at": [round(a.start, 1), round(b.start, 1)], "text": a.text[:30]}
                      for a, b in pairs[:6]]}
    if pairs:
        ex = pairs[0][0]
        return _bad("A3_duplicates", "block", m,
                    f"같은 대본 문장이 두 번 들어감 {len(pairs)}곳(예: 「{ex.text[:24]}」 원본 {fmt_ts(pairs[0][0].start)}·"
                    f"{fmt_ts(pairs[0][1].start)})", "drop_duplicates")
    return _ok("A3_duplicates", "block", m, "같은 대본 문장이 두 번 들어간 곳 없음")


GREETING_OPEN = re.compile(r"안녕하세요|반갑습니다")
GREETING_CLOSE = re.compile(r"시청해\s*주셔서|구독(과|이나|\s*버튼|\s*부탁)|좋아요(와|\s*눌러)|다음\s*(영상|시간)에서\s*(뵙|만나)|"
                            r"영상은\s*여기까지|오늘은\s*여기까지")


def a5_greetings(utts: list[Utterance], edit_start: dict[int, float], edit_sec: float, script_len: int) -> GateResult:
    """인사('안녕하세요')는 첫 10%, 끝인사('시청해 주셔서', '구독')는 마지막 10% 안에. 대본에서도 가운데 있는 인사(인용 등)는
    그 자리가 맞으므로 보지 않는다. edit_start: 발화 id → 편집 시각."""
    if edit_sec <= 0:
        return _skip("A5_greetings", "repair", "편집본 없음")
    bad = []
    for u in _kept(utts):
        t = edit_start.get(u.id)
        if t is None:
            continue
        pos = t / edit_sec
        spos = (u.script_span[0] / max(1, script_len)) if (u.script_span and script_len) else None
        if GREETING_OPEN.search(u.text) and pos > 0.10 and (spos is None or spos < 0.10):
            bad.append({"id": u.id, "at": round(t, 1), "kind": "open", "text": u.text[:30]})
        elif GREETING_CLOSE.search(u.text) and pos < 0.90 and (spos is None or spos > 0.90):
            bad.append({"id": u.id, "at": round(t, 1), "kind": "close", "text": u.text[:30]})
    m = {"misplaced": bad}
    if bad:
        b = bad[0]
        return _bad("A5_greetings", "repair", m,
                    f"{'인사' if b['kind'] == 'open' else '끝인사'}가 영상 {fmt_ts(b['at'])}"
                    f"({b['at'] / edit_sec * 100:.0f}% 지점)에 있음 — 「{b['text'][:20]}」", "drop_duplicates")
    return _ok("A5_greetings", "repair", m, "인사·끝인사 위치 정상")


# ---------------------------------------------------------------------------
# 게이트 A — 화면 구조(렌더 props 확정 뒤, 본편 시각)
# ---------------------------------------------------------------------------

AUTO_ONLY = ("title", "lower_third", "chapter")


def _spans(graphics: list[dict], callouts: Optional[list[dict]] = None, *, skip: tuple = ()) -> list[tuple[float, float]]:
    return sorted((float(g["start"]), float(g["end"])) for g in list(graphics) + list(callouts or [])
                  if g.get("end", 0) > g.get("start", 0) and g.get("template") not in skip)


def a6_distribution(graphics: list[dict], total: float, callouts: Optional[list[dict]] = None, *,
                    bin_min: float = 30.0, max_bins: int = 10) -> GateResult:
    """영상을 (최대) 10등분했을 때 그래픽이 0개인 칸이 없어야 한다. 짧은 영상은 칸을 30초 이상으로(1분 영상 = 2칸).
    타이틀·챕터 카드·이름 자막은 내용 그래픽이 아니라 세지 않는다."""
    if total <= 0:
        return _skip("A6_distribution", "block", "편집본 없음")
    n = max(1, min(max_bins, int(total // bin_min)))
    w = total / n
    spans = _spans(graphics, callouts, skip=AUTO_ONLY)
    empty = [i for i in range(n) if not any(a < (i + 1) * w and b > i * w for a, b in spans)]
    m = {"bins": n, "bin_sec": round(w, 1), "empty": empty,
         "empty_at": [[round(i * w, 1), round((i + 1) * w, 1)] for i in empty]}
    if empty:
        return _bad("A6_distribution", "block", m,
                    f"{n}등분 중 그래픽이 하나도 없는 칸 {len(empty)}개("
                    + ", ".join(f"{fmt_ts(i * w)}–{fmt_ts((i + 1) * w)}" for i in empty[:4]) + ")", "fill_gaps")
    return _ok("A6_distribution", "block", m, f"{n}등분 모든 칸에 그래픽 있음")


def face_only_spans(graphics: list[dict], callouts: Optional[list[dict]], total: float) -> list[tuple[float, float]]:
    """화면에 얼굴만 있는(그래픽·콜아웃이 하나도 없는) 구간 — grammar.face_only_runs 의 위치판."""
    out, t = [], 0.0
    for a, b in _spans(graphics, callouts):
        a, b = max(0.0, a), min(total, b)
        if a > t:
            out.append((t, a))
        t = max(t, b)
    if total > t:
        out.append((t, total))
    return out


def a7_face_run(graphics: list[dict], total: float, callouts: Optional[list[dict]] = None, *,
                soft: float = 25.0, hard: float = 40.0) -> GateResult:
    """맨얼굴 최장 구간 — 25초 이하(플레이북 절대 상한). 25~40초는 repair, 40초 초과는 block."""
    runs = face_only_spans(graphics, callouts, total)
    longest = max((b - a for a, b in runs), default=0.0)
    over = [(round(a, 1), round(b, 1)) for a, b in runs if b - a > soft]
    m = {"max_face_run": round(longest, 1), "over_25": len(over), "runs": over[:8]}
    if longest <= soft:
        return _ok("A7_face_run", "block", m, f"얼굴만 이어진 최장 {longest:.0f}초")
    a, b = max(runs, key=lambda r: r[1] - r[0])
    level = "block" if longest > hard else "repair"
    return _bad("A7_face_run", level, m, f"얼굴만 {longest:.0f}초 이어짐({fmt_ts(a)}–{fmt_ts(b)}, 25초 넘는 곳 {len(over)}곳)",
                "fill_gaps")


def face_ratio(graphics: list[dict], total: float) -> float:
    """얼굴이 보이는 시간 비율 — 전체화면 그래픽·챕터 카드가 덮지 않은 시간(grammar._covers 와 같은 기준)."""
    covered, t = 0.0, 0.0
    for a, b in sorted((max(0.0, float(g["start"])), min(total, float(g["end"]))) for g in graphics
                       if (g.get("layout") == "fullscreen" or g.get("template") == "chapter") and g["end"] > g["start"]):
        a = max(a, t)
        if b > a:
            covered += b - a
        t = max(t, b)
    return max(0.0, 1.0 - covered / max(1e-6, total))


def a8_face_ratio(ratio: float, *, lo: float = 0.35, hi: float = 0.70) -> GateResult:
    m = {"face_ratio": round(ratio, 3)}
    if lo <= ratio <= hi:
        return _ok("A8_face_ratio", "repair", m, f"얼굴 화면 비율 {ratio * 100:.0f}%")
    return _bad("A8_face_ratio", "repair", m,
                f"얼굴 화면 비율 {ratio * 100:.0f}%(권장 {lo * 100:.0f}~{hi * 100:.0f}%) — "
                + ("전체화면 그래픽이 너무 적음" if ratio > hi else "얼굴이 너무 적게 보임"), "fill_gaps" if ratio > hi else "")


def a9_title(graphics: list[dict], *, limit: float = 40.0) -> GateResult:
    """타이틀 카드는 본편 시작 후 40초 안(10/1 테스트: 06:48)."""
    ts = [float(g["start"]) for g in graphics if g.get("template") == "title"]
    if not ts:
        return _skip("A9_title", "block", "타이틀 카드 없음")
    t = min(ts)
    m = {"title_at": round(t, 1)}
    if t <= limit:
        return _ok("A9_title", "block", m, f"타이틀 {fmt_ts(t)}")
    return _bad("A9_title", "block", m, f"타이틀 카드가 본편 {fmt_ts(t)} 에 나옴(40초 안이어야 함)", "retime_title")


# ---------------------------------------------------------------------------
# 게이트 A11~A17 — 리듬(docs/upgrade/05_편집_문법_v2.md 4-2). 시계가 아니라 내용이 박자를 정한다:
# '모든 것이 중간'(빠른 묶음도 긴 홀드도 없음)을 잡는다
# ---------------------------------------------------------------------------

CONTENT_SKIP = ("title", "lower_third", "chapter", "recap")


def _content(graphics: list[dict]) -> list[dict]:
    return sorted((g for g in graphics if g.get("template") not in CONTENT_SKIP and g.get("end", 0) > g.get("start", 0)),
                  key=lambda g: g["start"])


def _seq_of(g: dict) -> str:
    return str((g.get("data") or {}).get("seq_id") or g.get("sequence_id") or "")


def a11_fast_runs(graphics: list[dict], total: float, *, fast_gap: float = 2.5, min_total: float = 180.0) -> GateResult:
    """빠른 묶음: 3장 이상 시퀀스 안에서 2.5초 이하 간격이 2번 이상 이어지는 곳이 하나는 있어야 한다(3분 넘는 영상)."""
    if total < min_total:
        return _skip("A11_fast_runs", "repair", "3분 미만 — 건너뜀")
    seqs: dict[str, list[dict]] = {}
    for g in _content(graphics):
        if _seq_of(g):
            seqs.setdefault(_seq_of(g), []).append(g)
    fast = []
    for sid, gs in seqs.items():
        starts = [g["start"] for g in gs]
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        if len(gs) >= 3 and sum(1 for x in gaps if x <= fast_gap) >= 2:
            fast.append(sid)
    m = {"sequences": len(seqs), "fast": fast}
    if fast:
        return _ok("A11_fast_runs", "repair", m, f"빠른 묶음 {len(fast)}곳")
    return _bad("A11_fast_runs", "repair", m, f"빠른 묶음(시퀀스 안 2.5초 이하 컷)이 하나도 없음 — 시퀀스 {len(seqs)}개", "")


def graphic_chains(graphics: list[dict], *, gap: float = 1.0) -> list[list[dict]]:
    """시퀀스가 아닌 그래픽이 1초 미만 간격으로 이어진 사슬들."""
    chains: list[list[dict]] = []
    cur: list[dict] = []
    for g in _content(graphics):
        if _seq_of(g):
            if len(cur) > 1:
                chains.append(cur)
            cur = []
            continue
        if cur and g["start"] - cur[-1]["end"] < gap:
            cur.append(g)
        else:
            if len(cur) > 1:
                chains.append(cur)
            cur = [g]
    if len(cur) > 1:
        chains.append(cur)
    return chains


def a12_chain(graphics: list[dict], *, chain_max: int = 3) -> GateResult:
    chains = [c for c in graphic_chains(graphics) if len(c) > chain_max]
    longest = max((len(c) for c in graphic_chains(graphics)), default=1)
    m = {"longest": longest, "chains": [[g.get("id") for g in c] for c in chains[:4]]}
    if not chains:
        return _ok("A12_chain", "repair", m, f"그래픽 사슬 최장 {longest}개")
    c = chains[0]
    return _bad("A12_chain", "repair", m, f"시퀀스가 아닌 그래픽 {len(c)}개가 1초 안 간격으로 이어짐({fmt_ts(c[0]['start'])}–"
                f"{fmt_ts(c[-1]['end'])}) — 3개까지", "trim_chain")


def a13_duration_spread(graphics: list[dict], *, spread_min: float = 4.0) -> GateResult:
    durs = sorted(g["end"] - g["start"] for g in _content(graphics))
    if len(durs) < 6:
        return _skip("A13_spread", "warn", "그래픽이 적어 건너뜀")
    p10 = durs[int(0.1 * (len(durs) - 1))]
    p90 = durs[int(round(0.9 * (len(durs) - 1)))]
    r = p90 / max(0.1, p10)
    m = {"p10": round(p10, 2), "p90": round(p90, 2), "ratio": round(r, 2)}
    if r >= spread_min:
        return _ok("A13_spread", "warn", m, f"길이 분포 p90/p10 = {r:.1f}")
    return _bad("A13_spread", "warn", m, f"그래픽 길이가 다 비슷함(p90/p10 = {r:.1f}, {spread_min:.0f} 이상 권장) — 빠른 묶음·긴 자료가 없다")


def a14_hold_guard(graphics: list[dict], holds: list[tuple[float, float]], callouts: Optional[list[dict]] = None,
                   sfx: Optional[list[dict]] = None) -> GateResult:
    """홀드(뒤 여유 포함) 안에 그래픽·보드·콜아웃·효과음 0 — 대본 태그 그래픽은 명령이라 예외(홀드가 그 앞까지 줄어든다)."""
    if not holds:
        return _skip("A14_hold_guard", "block", "홀드 없음")
    hits = []
    for g in graphics:
        if g.get("template") in ("title", "chapter") or g.get("source") == "tag":
            continue
        if any(g["start"] < b and g["end"] > a for a, b in holds):
            hits.append({"what": g.get("template"), "id": g.get("id"), "at": round(g["start"], 1)})
    for c in callouts or []:
        if any(c["start"] < b and c["end"] > a for a, b in holds):
            hits.append({"what": "callout", "at": round(c["start"], 1)})
    for x in sfx or []:
        if any(a <= x["t"] <= b for a, b in holds):
            hits.append({"what": "sfx", "at": round(x["t"], 1)})
    m = {"holds": len(holds), "hits": hits[:8]}
    if not hits:
        return _ok("A14_hold_guard", "block", m, f"얼굴 홀드 {len(holds)}곳 보호됨")
    return _bad("A14_hold_guard", "block", m, f"얼굴 홀드 안에 {hits[0]['what']} 등 {len(hits)}개", "respect_holds")


def step_runs(graphics: list[dict], *, gap: float = 2.0) -> list[list[dict]]:
    """합쳐지지 않은 단계 강조 — 같은 도식(템플릿·항목)이 강조만 바꿔 2초 안 간격으로 이어진 묶음."""
    runs: list[list[dict]] = []
    cur: list[dict] = []
    for g in _content(graphics):
        d = g.get("data") or {}
        key = (g.get("template"), tuple(d.get("items") or []))
        if cur:
            pd = cur[-1].get("data") or {}
            pkey = (cur[-1].get("template"), tuple(pd.get("items") or []))
            if key == pkey and key[1] and g["start"] - cur[-1]["end"] < gap and d.get("highlight") != pd.get("highlight"):
                cur.append(g)
                continue
            if len(cur) > 1:
                runs.append(cur)
        cur = [g]
    if len(cur) > 1:
        runs.append(cur)
    return runs


def a15_step_sync(graphics: list[dict]) -> GateResult:
    """단계 강조는 그 낱말에서(그래픽 하나 + stepAt) — 단계마다 그래픽을 새로 띄우면 강조가 말보다 4~6초 늦다."""
    runs = step_runs(graphics)
    stepped = sum(1 for g in graphics if (g.get("data") or {}).get("stepAt"))
    m = {"stepped": stepped, "unmerged": [[g.get("id") for g in r] for r in runs[:4]]}
    if not runs:
        return _ok("A15_step_sync", "repair", m, f"단계 그래픽 {stepped}개(낱말에서 강조)")
    return _bad("A15_step_sync", "repair", m, f"같은 도식을 단계마다 새로 띄운 곳 {len(runs)}곳 — 강조가 말보다 늦다", "merge_steps")


def a16_hold_presence(graphics: list[dict], chapters: list[dict], total: float, callouts: Optional[list[dict]] = None,
                      *, chapter_min: float = 60.0, hold_min: float = 12.0) -> GateResult:
    """60초 넘는 챕터마다 12초 이상 얼굴만 이어지는 구간이 하나(고백·결론이 숨 쉴 자리)."""
    bounds = [c["start"] for c in sorted(chapters, key=lambda c: c["start"])] + [total]
    runs = face_only_spans(graphics, callouts, total)
    short = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        if b - a <= chapter_min:
            continue
        longest = max((min(y, b) - max(x, a) for x, y in runs if x < b and y > a), default=0.0)
        if longest < hold_min:
            short.append({"chapter": i + 1, "longest": round(longest, 1)})
    m = {"chapters_without_hold": short}
    if not short:
        return _ok("A16_hold_presence", "warn", m, "긴 챕터마다 얼굴로 머무는 자리 있음")
    return _bad("A16_hold_presence", "warn", m, f"챕터 {short[0]['chapter']} 에 12초 넘게 얼굴로 머무는 자리가 없음"
                f"(최장 {short[0]['longest']:.0f}초)")


def a17_monotony(graphics: list[dict], *, cv_warn: float = 0.45) -> GateResult:
    starts = [g["start"] for g in _content(graphics)]
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    if len(gaps) < 6:
        return _skip("A17_monotony", "warn", "그래픽이 적어 건너뜀")
    mean = sum(gaps) / len(gaps)
    cv = (sum((x - mean) ** 2 for x in gaps) / len(gaps)) ** 0.5 / max(1e-6, mean)
    m = {"gap_cv": round(cv, 2), "mean_gap": round(mean, 1)}
    if cv >= cv_warn:
        return _ok("A17_monotony", "warn", m, f"간격 변화 CV {cv:.2f}")
    return _bad("A17_monotony", "warn", m, f"그래픽 간격이 시계처럼 고름(CV {cv:.2f}) — 내용이 박자를 정하게")


# ---------------------------------------------------------------------------
# 게이트 B — 화면 글자 위생(렌더 props 확정 뒤)
# ---------------------------------------------------------------------------

TEXT_FIELDS = ("title", "subtitle", "body", "title_b", "highlight", "author", "label", "keyword", "keyword_sub", "caption")
LIST_FIELDS = ("items", "items_b")
TEXT_TEMPLATES = ("keyword", "definition", "quote", "stat")

INTERNAL_NAMES = {"motion", "card", "keyword", "broll", "b-roll", "photo", "recap", "stat", "chapter", "brand", "footage",
                  "episode", "lower_third", "lowerthird", "fullscreen", "overlay", "pip", "split", "video", "person",
                  "work", "object", "place", "religion", "other", "screenshot"}
INTERNAL_TOKEN = re.compile(r"\b(start_seg|end_seg|start_word|query_(?:ko|en)|must_show|template|layout)\b"
                            r"|\(S\d{1,4}\)|\bS\d{1,4}\s*[–~-]\s*S?\d{1,4}\b|\bseg\s*\d+\b|\bg\d{1,3}\b")
DIRECTION = re.compile(r"보여\s?준다|보여\s?줌|보여\s?주기|보여\s?주는\s?(장면|컷|샷)|B-?roll|b-?roll|비롤|인서트\s?컷|"
                       r"화면\s?전환|장면\s?전환|컷\s?전환|(장면|컷|전환점)\s*$")


def _fields(g: dict) -> list[tuple[str, Any, str]]:
    """그래픽의 화면 글자 (경로, 담은 dict/list, 키). 계획 모양(키가 바로)과 props 모양(data 안) 모두."""
    d = g.get("data") if isinstance(g.get("data"), dict) else g
    out: list[tuple[str, Any, str]] = []
    for k in TEXT_FIELDS:
        if isinstance(d.get(k), str) and d[k].strip():
            out.append((k, d, k))
    for k in LIST_FIELDS:
        items = d.get(k)
        if isinstance(items, list):
            for i, it in enumerate(items):
                if isinstance(it, str) and it.strip():
                    out.append((f"{k}[{i}]", items, i))     # type: ignore[arg-type]
                elif isinstance(it, dict):
                    for kk in ("title", "body", "label", "text"):
                        if isinstance(it.get(kk), str) and it[kk].strip():
                            out.append((f"{k}[{i}].{kk}", it, kk))
    arc = d.get("archive") if isinstance(d.get("archive"), dict) else None      # 증거 자료의 자료·출처 카드
    if arc:
        for kk in ("title", "label", "quote"):
            if isinstance(arc.get(kk), str) and arc[kk].strip():
                out.append((f"archive.{kk}", arc, kk))
        for i, r in enumerate(arc.get("rows") or []):
            if isinstance(r, dict) and isinstance(r.get("v"), str) and r["v"].strip():
                out.append((f"archive.rows[{i}]", r, "v"))
    return out


def _get(holder: Any, key: Any) -> str:
    return holder[key]


def _plain(text: str) -> str:
    return re.sub(r"[\s()\[\]{}「」『』<>·:;,.!?'\"/_-]+", "", text).lower()


def _internal(text: str) -> bool:
    p = _plain(text)
    return p in {re.sub(r"[_-]", "", x) for x in INTERNAL_NAMES} or bool(re.fullmatch(r"[sg]\d{1,4}", p)) \
        or bool(INTERNAL_TOKEN.search(text))


def _card_texts(g: dict) -> list[str]:
    """자유 카드 HTML·모션 장면의 글자(내부 이름 검사용)."""
    d = g.get("data") if isinstance(g.get("data"), dict) else g
    out: list[str] = []
    card = d.get("card") if isinstance(d.get("card"), dict) else None
    if card and isinstance(card.get("html"), str):
        out += [t.strip() for t in re.split(r"<[^>]+>", _html.unescape(card["html"])) if t.strip()]
    spec = d.get("spec") if isinstance(d.get("spec"), dict) else None
    if spec:
        for el in spec.get("elements", []) or []:
            if isinstance(el, dict) and isinstance(el.get("text"), str) and el["text"].strip():
                out.append(el["text"].strip())
    return out


def _gid(g: dict) -> str:
    return str(g.get("id") or f"{g.get('template', '?')}@{g.get('start_seg', g.get('start', '?'))}")


def _queries(g: dict) -> list[str]:
    st = g.get("stock") if isinstance(g.get("stock"), dict) else {}
    return [q for q in (st.get("query_ko"), st.get("query_en"), st.get("purpose")) if isinstance(q, str) and q.strip()]


def _is_query_label(title: str, queries: list[str]) -> bool:
    t = _plain(title)
    if not t:
        return False
    words = {w for q in queries for w in re.findall(r"[0-9A-Za-z가-힣]+", q.lower())}
    tw = re.findall(r"[0-9A-Za-z가-힣]+", title.lower())
    return any(t == _plain(q) for q in queries) or (bool(tw) and all(w in words for w in tw))


# --- 자료(03 문서 9절 되메우기 루프의 B1·B2·B6) --------------------------------------------------------------

def _d(g: dict) -> dict:
    return g.get("data") if isinstance(g.get("data"), dict) else g


def is_real_media(g: dict) -> bool:
    """실물 이미지인가 — 사진·스톡·화면 캡처·문서(B1). 코드로 그린 것·로고 카드·출처 카드·자료(타이포) 카드는 아니다."""
    d = _d(g)
    t = g.get("template")
    if t == "photo":
        return bool(d.get("image")) and not d.get("logo")
    if t == "broll":
        return bool(d.get("src"))
    if t == "evidence":
        return any(a.get("kind") in ("photo", "video", "screen", "document") for a in d.get("assets") or [])
    return False


def is_hero_media(g: dict) -> bool:
    """전면 실물(풀블리드 또는 화면의 55% 이상 — 증거 hero 는 1728×724 ≈ 60%)."""
    return is_real_media(g) and (g.get("layout") == "fullscreen" or g.get("template") == "evidence")


def b1_media_ratio(graphics: list[dict], total: float, *, min_ratio: float = 0.15) -> GateResult:
    """실물 자료가 보이는 시간 / 본편 ≥ 15%(목표 25~30%). 짧은 영상(90초 미만)은 건너뛴다."""
    secs = sum(max(0.0, float(g["end"]) - float(g["start"])) for g in graphics if is_real_media(g) and "end" in g)
    ratio = secs / total if total else 0.0
    m = {"seconds": round(secs, 1), "ratio": round(ratio, 3), "target": [0.25, 0.30], "min": min_ratio}
    if total < 90:
        r = _ok("B1_media_ratio", "warn", m, f"실물 자료 {ratio:.0%}(짧은 영상 — 건너뜀)")
        r.skipped = True
        return r
    if ratio < min_ratio:
        return _bad("B1_media_ratio", "warn", m, f"실물 자료가 보이는 시간 {ratio:.0%}(최소 {min_ratio:.0%}, 목표 25~30%) — "
                    "과제물·스케치·화면 캡처를 ④ 자료 폴더에 넣으면 채워진다")
    return _ok("B1_media_ratio", "warn", m, f"실물 자료 {ratio:.0%}")


def b2_hero_per_chapter(graphics: list[dict], chapters: list[dict], total: float, *, min_len: float = 45.0) -> GateResult:
    """실물 자료가 있는 챕터(45초 이상)마다 전면 실물이 한 번 이상 — 얼굴 옆 작은 액자(pip)만으로 끝나는 챕터가 없다.
    chapters: [{start, end?}] (끝이 없으면 다음 챕터 시작·전체 끝). 수리 promote_hero."""
    cs = sorted(chapters, key=lambda c: float(c.get("start", 0)))
    spans = [(float(c.get("start", 0)), float(c.get("end") or (cs[i + 1]["start"] if i + 1 < len(cs) else total)))
             for i, c in enumerate(cs)] or [(0.0, total)]
    lacking = []
    for a, b in spans:
        if b - a < min_len:
            continue
        inside = [g for g in graphics if is_real_media(g) and a <= float(g.get("start", -1)) < b]
        if inside and not any(is_hero_media(g) for g in inside):
            lacking.append([round(a, 1), round(b, 1)])
    m = {"lacking": lacking}
    if lacking:
        return _bad("B2_hero", "repair", m, f"전면 실물 자료가 없는 챕터 {len(lacking)}개(얼굴 옆 작은 액자뿐)", "promote_hero")
    return _ok("B2_hero", "repair", m, "자료가 있는 챕터마다 전면 자료가 있다")


def promote_hero(plan_graphics: list[dict], timed: list[dict], lacking: list[list[float]]) -> int:
    """B2 수리: 그 챕터의 실물 사진 중 가장 큰(해상도) 것을 전면으로. timed(props 그래픽)로 챕터 안에 있는 것을 찾고,
    plan_graphics(계획) 의 같은 그래픽 layout 을 fullscreen 으로 바꾼다. 반환: 올린 수."""
    n = 0
    by_id = {f"g{i}": g for i, g in enumerate(plan_graphics)}
    for a, b in lacking:
        cands = [g for g in timed if is_real_media(g) and a <= float(g.get("start", -1)) < b and g.get("id") in by_id
                 and g.get("template") in ("photo", "broll")]
        if not cands:
            continue

        def size(g: dict) -> float:
            pg = by_id[g["id"]]
            ev = [x for x in (pg.get("assets") or []) if isinstance(x, dict)]
            return max([float(x.get("w", 0) or 0) * float(x.get("h", 0) or 0) for x in ev] + [float(g["end"]) - float(g["start"])])
        best = max(cands, key=size)
        pg = by_id[best["id"]]
        if pg.get("layout") != "fullscreen":
            pg["layout"] = "fullscreen"
            pg["promoted"] = "B2"
            n += 1
    return n


def b6_pick_scores(graphics: list[dict]) -> GateResult:
    """비전 선택 점수(0~3)가 2 미만인 자료가 화면에 없다(사다리가 2점 이상만 쓴다 — 안전망)."""
    low = []
    for g in graphics:
        for a in _d(g).get("assets") or []:
            sc = a.get("score", -1) if isinstance(a, dict) else -1
            if isinstance(sc, (int, float)) and 0 <= sc < 2:
                low.append({"graphic": _gid(g), "src": a.get("src", ""), "score": sc})
    m = {"low": low}
    if low:
        return _bad("B6_relevance", "warn", m, f"관련도 2점 미만 자료 {len(low)}장이 화면에 있다")
    return _ok("B6_relevance", "warn", m, "화면의 자료는 모두 관련도 2점 이상(또는 화자 자료·규칙 선택)")


# --- 색(07 문서 7절 게이트 F) ----------------------------------------------------------------------------

def f1_blotch(bi: dict[str, float], *, max_ratio: float = 2.0, max_off: float = 0.01) -> GateResult:
    """평평한 면의 얼룩: 색 잡음 비 ≤ 2.0 이고 색상이 그 면에서 12° 넘게 벗어난 화소 증가 ≤ 1%.
    (10/1 설치본 ×4.36 · 2.1~14.7% 실패, 지금 ×1.34 · 0% 통과)"""
    m = dict(bi)
    if bi.get("frames", 1) == 0:
        r = _ok("F1_blotch", "repair", m, "평평한 면이 없어 얼룩 검사 건너뜀")
        r.skipped = True
        return r
    if bi.get("ratio", 1.0) > max_ratio or bi.get("off", 0.0) > max_off:
        return _bad("F1_blotch", "repair", m, f"보정이 평평한 면에 얼룩(색 잡음 ×{bi.get('ratio', 0):.2f}, "
                    f"색상 튐 {bi.get('off', 0):.1%})", "soften_grade")
    return _ok("F1_blotch", "repair", m, f"얼룩 없음(색 잡음 ×{bi.get('ratio', 1):.2f})")


def f3_sources(before: float, after: float, *, max_de: float = 3.0) -> GateResult:
    """원본 사이 얼굴 ΔE ≤ 3 — 컷으로 이어 붙여도 같은 사람 같은 날로 읽힌다."""
    m = {"face_de_before": round(before, 2), "face_de_after": round(after, 2)}
    if after > max_de:
        return _bad("F3_sources", "warn", m, f"원본 사이 얼굴색 차이 ΔE {after:.1f}(매칭 전 {before:.1f}) — 조명이 크게 다름")
    msg = f"원본 사이 얼굴 ΔE {after:.1f}" + (f"(매칭 전 {before:.1f})" if before > after + 0.05 else "")
    r = _ok("F3_sources", "repair", m, msg)
    r.repaired = before > max_de >= after
    return r


def f4_clipping(before: float, after: float, *, max_total: float = 0.02, max_rise: float = 0.01) -> GateResult:
    """날아간 하이라이트: 화면 ≤ 2% 이고 원본 대비 증가 ≤ 1%p(전등·침구가 날아가지 않게)."""
    m = {"clip_before": round(before, 4), "clip_after": round(after, 4)}
    if after > max(max_total, before) or after - before > max_rise:
        return _bad("F4_clipping", "repair", m, f"하이라이트가 날아감 {before:.1%} → {after:.1%}", "white_1")
    return _ok("F4_clipping", "repair", m, f"하이라이트 {before:.1%} → {after:.1%}")


def f6_tags(problems: dict[str, list[str]]) -> GateResult:
    """완성본 색 태그: BT.709 · 제한 범위(tv) · yuv420p — 어긋나면 플레이어마다 색이 다르게 보인다."""
    bad = {k: v for k, v in problems.items() if v}
    m = {"files": bad}
    if bad:
        k, v = next(iter(bad.items()))
        return _bad("F6_tags", "warn", m, f"색 태그가 BT.709 가 아님: {k} ({', '.join(v)})")
    return _ok("F6_tags", "warn", m, "색 태그 BT.709 · tv · yuv420p")


# --- 소리(04 문서 9절 게이트 D) ---------------------------------------------------------------------
def d1_voice_over_music(voice_lufs: Optional[float], under_db: Optional[float], *, ref_lufs: float = -14.0,
                        lo: float = 18.0, hi: float = 26.0) -> GateResult:
    """말 구간 목소리 − 음악 18~26 LU(목표 20). 음악은 곡마다 ref_lufs 로 맞춘 뒤 under_db 를 곱하므로
    말 아래 음악 ≈ ref_lufs + under_db — 게인 계획에서 잰다(곡 원래 다이내믹은 들어가지 않는다)."""
    if voice_lufs is None or under_db is None:
        return _skip("D1_voice_music", "repair", "음악 없음")
    d = voice_lufs - (ref_lufs + under_db)
    m = {"voice_lufs": round(voice_lufs, 1), "music_under_lufs": round(ref_lufs + under_db, 1), "diff_lu": round(d, 1)}
    if not lo <= d <= hi:
        return _bad("D1_voice_music", "repair", m, f"목소리가 음악보다 {d:.1f} LU 위({lo:.0f}~{hi:.0f})", "bed_level")
    return _ok("D1_voice_music", "repair", m, f"목소리 − 음악 {d:.1f} LU")


def d3_one_track(tracks: int) -> GateResult:
    """한 영상 한 곡(아이덴트 제외)."""
    m = {"tracks": tracks}
    if tracks > 1:
        return _bad("D3_one_track", "repair", m, f"곡이 {tracks}개 — 한 영상 한 곡", "one_track")
    return _ok("D3_one_track", "repair", m, "곡 하나" if tracks else "음악 없음")


def d5_sfx_density(cues: list[tuple[float, str]], *, punch: list[tuple[float, float]] = (), window: float = 60.0,
                   cap: int = 3) -> GateResult:
    """효과음: 펀치 구간 밖 60초 창 어디서도 3개 이하(목록 틱 포함), 같은 파일 연속 2회 금지.
    cues: (시각, 파일 경로) 시간순."""
    cues = sorted(cues)
    outside = [t for t, _ in cues if not any(a <= t < b for a, b in punch)]
    worst, at = 0, 0.0
    for i, t in enumerate(outside):
        n = sum(1 for u in outside[i:] if u < t + window)
        if n > worst:
            worst, at = n, t
    repeats = [round(cues[i][0], 1) for i in range(1, len(cues)) if cues[i][1] == cues[i - 1][1]]
    m = {"sfx": len(cues), "max_per_window": worst, "window_at": round(at, 1), "repeats": repeats[:6]}
    if worst > cap:
        return _bad("D5_sfx_density", "warn", m, f"효과음이 {at:.0f}초부터 60초 안에 {worst}개(상한 {cap})")
    if repeats:
        return _bad("D5_sfx_density", "warn", m, f"같은 효과음 파일이 연달아 {len(repeats)}번")
    return _ok("D5_sfx_density", "warn", m, f"효과음 {len(cues)}개 · 60초 창 최대 {worst}개")


def d6_fit(fit_score: Optional[int], *, min_fit: int = 7) -> GateResult:
    """음악 감독의 fit_score ≥ 7 — 아니면 air 판만(수리), 그것도 안 되면 음악 없음."""
    if fit_score is None:
        return _skip("D6_fit", "repair", "큐 시트 없음")
    m = {"fit_score": fit_score}
    if fit_score < min_fit:
        return _bad("D6_fit", "repair", m, f"맞는 음악 점수 {fit_score}/10 — air 만 쓴다", "air_only")
    return _ok("D6_fit", "repair", m, f"맞는 음악 점수 {fit_score}/10")


def d8_occupancy(share: Optional[float], cues: list[dict], *, lo: float = 0.30, hi: float = 0.65) -> GateResult:
    """롱폼 음악 점유율 30~65%(처음부터 끝까지 깐 계획은 틀린 계획), 모든 큐에 why_in·why_out."""
    if share is None:
        return _skip("D8_occupancy", "warn", "음악 없음")
    no_why = [c.get("id", "") for c in cues if not (str(c.get("why_in", "")).strip() and str(c.get("why_out", "")).strip())]
    m = {"share": round(share, 3), "cues": len(cues), "no_why": no_why}
    if not lo <= share <= hi:
        return _bad("D8_occupancy", "warn", m, f"음악 점유율 {share:.0%}({lo:.0%}~{hi:.0%})")
    if no_why:
        return _bad("D8_occupancy", "warn", m, f"들어오고 나가는 이유가 없는 큐 {', '.join(no_why)}")
    return _ok("D8_occupancy", "warn", m, f"음악 점유율 {share:.0%} · 큐 {len(cues)}개")


def d9_license(used: list[tuple[str, str]]) -> GateResult:
    """쓰인 모든 음원(곡·효과음)의 저작권 위험 등급이 own·A~C. used: (이름, 등급). 등급 없음 = 확인 안 됨."""
    bad = [f"{n}({c or '등급 없음'})" for n, c in used if c not in ("own", "A", "A-sa", "B", "C", "synth")]
    m = {"used": len(used), "bad": bad}
    if bad:
        return _bad("D9_license", "block", m, f"라이선스가 확인되지 않은 음원: {', '.join(bad[:4])}")
    return _ok("D9_license", "block", m, f"음원 {len(used)}개 라이선스 확인")


def d10_voice_level(voice_lufs: Optional[float], *, target: float = -16.0, tol: float = 1.0) -> GateResult:
    """목소리 스템 −16 ±1 LUFS(마스터 −14 의 바탕)."""
    if voice_lufs is None:
        return _skip("D10_voice", "warn", "목소리 측정 못 함")
    m = {"voice_lufs": round(voice_lufs, 1)}
    if abs(voice_lufs - target) > tol:
        return _bad("D10_voice", "warn", m, f"목소리 {voice_lufs:.1f} LUFS(목표 {target:.0f} ±{tol:.0f})")
    return _ok("D10_voice", "warn", m, f"목소리 {voice_lufs:.1f} LUFS")


def b3_query_labels(graphics: list[dict]) -> GateResult:
    """자료 라벨 = 검색어(10/1: 스톡 위 큰 글씨 '스케치북 넘기기'). 계획 모양의 broll·photo(stock 이 있는 것)."""
    bad = []
    for g in graphics:
        qs = _queries(g)
        d = g.get("data") if isinstance(g.get("data"), dict) else g
        if qs and isinstance(d.get("title"), str) and _is_query_label(d["title"], qs):
            bad.append({"graphic": _gid(g), "field": "title", "text": d["title"][:30]})
        if g.get("template") == "broll" and d.get("subtitle") in ("video", "photo"):
            bad.append({"graphic": _gid(g), "field": "subtitle", "text": d["subtitle"]})
    m = {"labels": bad}
    if bad:
        return _bad("B3_query_label", "repair", m, f"자료 라벨이 검색어 그대로 {len(bad)}곳(예: 「{bad[0]['text']}」)",
                    "scrub_labels")
    return _ok("B3_query_label", "repair", m, "자료 라벨에 검색어 없음")


def b4_direction_notes(graphics: list[dict]) -> GateResult:
    """화면 글자에 연출 메모('…보여준다', '…하는 장면', '전환점', 'B-roll')."""
    bad = []
    for g in graphics:
        for path, holder, key in _fields(g):
            text = _get(holder, key)
            if DIRECTION.search(text):
                bad.append({"graphic": _gid(g), "field": path, "text": text[:40]})
    m = {"notes": bad}
    if bad:
        return _bad("B4_direction", "repair", m, f"화면에 연출 메모 {len(bad)}곳(예: 「{bad[0]['text'][:24]}」)",
                    "scrub_labels")
    return _ok("B4_direction", "repair", m, "화면 글자에 연출 메모 없음")


def b5_internal_names(graphics: list[dict]) -> GateResult:
    """화면 글자에 내부 이름(템플릿·종류 enum·S12 같은 발화 번호·키 이름)."""
    bad = []
    for g in graphics:
        for path, holder, key in _fields(g):
            text = _get(holder, key)
            if _internal(text):
                bad.append({"graphic": _gid(g), "field": path, "text": text[:30]})
        for t in _card_texts(g):
            if _internal(t):
                bad.append({"graphic": _gid(g), "field": "card/spec", "text": t[:30]})
    m = {"names": bad}
    if bad:
        return _bad("B5_internal", "block", m, f"화면에 내부 이름 {len(bad)}곳(예: 「{bad[0]['text']}」)", "scrub_labels")
    return _ok("B5_internal", "block", m, "화면 글자에 내부 이름 없음")


def scrub_labels(graphics: list[dict]) -> tuple[int, list[dict]]:
    """B3·B4·B5 수리: 그 필드를 비운다. 글자가 주인공인 그래픽(키워드·정의·인용·숫자)의 제목이 비면 그래픽째 뺀다.
    반환 (고친 필드 수, 남길 그래픽). 카드·모션 안의 내부 이름은 그 글자 덩어리만 지운다."""
    fixed = 0
    keep: list[dict] = []
    for g in graphics:
        qs = _queries(g)
        d = g.get("data") if isinstance(g.get("data"), dict) else g
        drop = False
        for path, holder, key in _fields(g):
            text = _get(holder, key)
            bad = _internal(text) or DIRECTION.search(text) is not None \
                or (key == "title" and holder is d and bool(qs) and _is_query_label(text, qs))
            if not bad:
                continue
            fixed += 1
            holder[key] = ""
            if holder is d and key == "title" and g.get("template") in TEXT_TEMPLATES:
                drop = True
        if g.get("template") == "broll" and d.get("subtitle") in ("video", "photo"):
            d["subtitle"] = ""
            fixed += 1
        for k in LIST_FIELDS:      # 비운 항목은 목록에서 뺀다
            if isinstance(d.get(k), list):
                d[k] = [it for it in d[k] if not (isinstance(it, str) and not it.strip())]
        card = d.get("card") if isinstance(d.get("card"), dict) else None
        if card and isinstance(card.get("html"), str):
            def _clean_text(mt: re.Match) -> str:
                t = mt.group(0)
                return "" if t.strip() and _internal(_html.unescape(t.strip())) else t
            new = re.sub(r"(?<=>)[^<]+(?=<)", _clean_text, card["html"])
            if new != card["html"]:
                card["html"] = new
                fixed += 1
        spec = d.get("spec") if isinstance(d.get("spec"), dict) else None
        if spec and isinstance(spec.get("elements"), list):
            n0 = len(spec["elements"])
            spec["elements"] = [el for el in spec["elements"]
                                if not (isinstance(el, dict) and isinstance(el.get("text"), str) and _internal(el["text"]))]
            fixed += n0 - len(spec["elements"])
        if not drop:
            keep.append(g)
    return fixed, keep


# ---------------------------------------------------------------------------
# 게이트 E — 완성본(타임라인 검수, docs/upgrade/05b). 가중 평균·판정은 코드가 한다
# ---------------------------------------------------------------------------

RUBRIC_WEIGHT = {"follow": 30, "argument": 20, "rhythm": 15, "evidence": 15, "hierarchy": 10, "distinct": 10}
PASS_SCORE = 3.8
TL_KIND_TO_GATE = {"duplicate_take": ["A1_length", "A3_duplicates", "A5_greetings"],
                   "dead_air": ["A6_distribution", "A7_face_run"], "slide_chain": ["A12_chain"],
                   "hold_broken": ["A14_hold_guard"], "late_step": ["A15_step_sync"],
                   "no_tails": ["A11_fast_runs", "A16_hold_presence"], "no_evidence": [], "wrong_image": [],
                   "label_leak": ["B3_query_label", "B4_direction", "B5_internal"], "template_repeat": [],
                   "surface_mix": [], "flat_hierarchy": [], "other": []}


def gate_e(tl: dict) -> GateResult:
    """타임라인 검수 결과 → 게이트 E. 기준별 점수(0~5)의 가중 평균 ≥ 3.8 이고 2점 이하 기준이 없으면 pass.
    high·blocking 발견이 하나라도 있으면 needs_review(결과 폴더·창에 '검토 필요'). 빠진 기준은 '채점 실패'로 두고 평균에서 뺀다."""
    scores = {}
    for sc in tl.get("scores", []) or []:
        c = sc.get("criterion")
        if c in RUBRIC_WEIGHT:
            try:
                scores[c] = max(0, min(5, int(sc.get("score", 0))))
            except (TypeError, ValueError):
                continue
    total_w = sum(RUBRIC_WEIGHT[c] for c in scores)
    avg = sum(RUBRIC_WEIGHT[c] * v for c, v in scores.items()) / total_w if total_w else 0.0
    findings = [f for f in tl.get("findings", []) or [] if isinstance(f, dict)]
    blocking_f = [f for f in findings if f.get("severity") == "high" and f.get("blocking")]
    low = [c for c, v in scores.items() if v <= 2]
    verdict = "needs_review" if blocking_f else ("pass" if scores and avg >= PASS_SCORE and not low else "revise")
    m = {"weighted": round(avg, 2), "scores": scores, "missing": [c for c in RUBRIC_WEIGHT if c not in scores],
         "verdict": verdict, "thesis_read": str(tl.get("thesis_read", ""))[:120],
         "findings": [{k: f.get(k) for k in ("start", "end", "kind", "severity", "action", "blocking", "direction")}
                      for f in findings[:12]]}
    if verdict == "pass":
        return _ok("E_timeline", "warn", m, f"타임라인 검수 통과(가중 {avg:.2f})")
    if verdict == "needs_review":
        f = blocking_f[0]
        return _bad("E_timeline", "warn", m, f"검토 필요 — {f.get('start', '')}~{f.get('end', '')} {f.get('kind')}: "
                    f"{str(f.get('direction', ''))[:60]}")
    worst = sorted(scores.items(), key=lambda kv: kv[1])[:2]
    return _bad("E_timeline", "warn", m, f"타임라인 검수 {avg:.2f}점(통과 {PASS_SCORE}) — 약한 기준: "
                + ", ".join(f"{c} {v}" for c, v in worst))


def gate_feedback(results: list[GateResult], tl: dict) -> list[dict]:
    """게이트는 통과했는데 검수가 잡은 것 — 임계값을 고칠 신호(work/gate_feedback.json 에 쌓는다)."""
    by = {r.id: r for r in results}
    out = []
    for f in tl.get("findings", []) or []:
        for gid in TL_KIND_TO_GATE.get(f.get("kind", ""), []):
            r = by.get(gid)
            if r is not None and r.ok and not r.skipped:
                out.append({"gate": gid, "measured": r.measured, "finding": {k: f.get(k) for k in
                                                                              ("start", "end", "kind", "severity",
                                                                               "direction")}})
    return out


# ---------------------------------------------------------------------------
# 결과 정리
# ---------------------------------------------------------------------------

def blocking(results: list[GateResult]) -> list[GateResult]:
    return [r for r in results if r.blocking]


def demote(results: list[GateResult]) -> None:
    """repair 수준이 수리 뒤에도 실패하면 warn 으로(진행하되 리포트 맨 위에)."""
    for r in results:
        if not r.ok and r.level == "repair":
            r.level = "warn"


def merge(old: list[GateResult], new: list[GateResult]) -> list[GateResult]:
    """같은 id 는 새 결과로(첫 결과가 실패였고 새 결과가 통과면 '수리됨')."""
    by = {r.id: r for r in old}
    for r in new:
        prev = by.get(r.id)
        if prev is not None and r.ok and (not prev.ok or prev.repaired):
            r.repaired = True
        by[r.id] = r
    order = [r.id for r in old] + [r.id for r in new if r.id not in {x.id for x in old}]
    return [by[i] for i in order]


def combine(results: list[GateResult]) -> list[GateResult]:
    """여러 화면(롱폼·숏폼)에서 잰 같은 검사를 하나로: 하나라도 실패면 그 실패, 아니면 통과(어디서든 수리했으면 수리됨)."""
    out: dict[str, GateResult] = {}
    for r in results:
        prev = out.get(r.id)
        if prev is None:
            out[r.id] = r
        elif prev.ok and not r.ok:
            out[r.id] = r
        elif prev.ok and r.ok and r.repaired:
            prev.repaired = True
    return list(out.values())


def summary(results: list[GateResult]) -> str:
    bad = [r for r in results if not r.ok]
    fixed = [r for r in results if r.repaired]
    if not bad:
        return f"🚦 품질 게이트 통과 {len(results)}개" + (f"(수리 {len(fixed)}개)" if fixed else "")
    return (f"🚦 품질 게이트: 통과 {len(results) - len(bad)} · "
            + " · ".join(f"{'⛔' if r.level == 'block' else '⚠'} {r.id} {r.message}" for r in bad))


def report_section(results: list[GateResult]) -> str:
    """편집리포트 첫 절 — 통과/수리/경고/멈춤 표. 경고가 있으면 맨 위에 '검토 필요'."""
    if not results:
        return ""
    bad = [r for r in results if not r.ok]
    lines = ["## 🚦 품질 게이트", ""]
    if bad:
        lines += ["**검토 필요** — " + " · ".join(f"{r.id}: {r.message}" for r in bad), ""]
    lines += ["| 검사 | 결과 | 내용 |", "|---|---|---|"]
    for r in results:
        state = ("건너뜀" if r.skipped else "통과(수리함)" if r.repaired else "통과") if r.ok else \
            ("멈춤" if r.level == "block" else "경고")
        lines.append(f"| {r.id} | {state} | {r.message.replace('|', '/')} |")
    e = next((r for r in results if r.id == "E_timeline"), None)
    if e is not None and e.measured.get("scores"):
        m = e.measured
        lines += ["", f"### 🧐 타임라인 검수 — 가중 {m.get('weighted')} · {m.get('verdict')}", ""]
        if m.get("thesis_read"):
            lines.append(f"처음 보는 눈이 읽은 논지: {m['thesis_read']}")
            lines.append("")
        lines.append(" · ".join(f"{c} {v}" for c, v in m["scores"].items()))
        for f in m.get("findings", []):
            lines.append(f"- {f.get('start', '')}~{f.get('end', '')} [{f.get('severity')}] {f.get('kind')} → "
                         f"{f.get('action')}: {str(f.get('direction', '')).replace('|', '/')}")
    return "\n".join(lines) + "\n\n"


def write(path: Path, results: list[GateResult], *, forced: bool = False) -> None:
    write_json(path, {"forced": forced, "ok": not blocking(results), "results": [r.to_dict() for r in results]})
