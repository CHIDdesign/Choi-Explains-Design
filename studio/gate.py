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
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from .models import Utterance
from .paths import RENDERER_DIR
from .util import fmt_ts, write_json

LEVELS = ("block", "repair", "warn")

# 숫자의 지위(docs/research/롱폼 숏폼 디렉팅 문법 조사.md): 차단·수리는 '구조'(프로그램이 결함을 있음/없음으로 판정 — 싱크·중복·자료 누락·대본 충실·
# 라이선스·길이)만. 나머지는 경고. 측정 = 연구로 방향이 받쳐짐(초·퍼센트는 공학값) · 실무 = 이름 있는 현업·채널 주인 · 취향 = 시청 추정·공학값.
# 시험값은 조사의 제안이라 A/B 로 정한다. tests/test_directing_rules.py 가 '구조'가 아닌 id 의 차단·수리를 막는다.
THRESHOLDS: dict[str, tuple[str, str]] = {
    "A1_length": ("구조", "대본 글자의 1.25배 · 대본 밖 포함 1.8배"),
    "A2_planned": ("취향", "감독 예상의 0.8~1.25배"),
    "A3_duplicates": ("구조", "같은 대본 구간 60% 겹침 0쌍"),
    "A5_greetings": ("구조", "인사 첫 10% · 끝인사 마지막 10%"),
    "A6_distribution": ("취향", "최대 10등분(칸 30초+)에 빈 칸 0"),
    "A7_face_run": ("취향", "맨얼굴 50초"),
    "A8_face_ratio": ("취향", "얼굴 40~85%"),
    "A9_title": ("취향", "타이틀 40초 안"),
    "A12_chain": ("취향", "이어진 그래픽 3개"),
    "A14_hold_guard": ("구조", "선언한 홀드 안 그래픽 0"),
    "A15_step_sync": ("구조", "단계마다 새 그래픽 0"),
    "A16_hold_presence": ("취향", "60초+ 챕터에 얼굴 12초"),
    "A18_word_sync": ("측정", "낱말 착지 중앙값 0.35초 · 최대 1초"),
    "A19_link_audit": ("실무", "'그리고' 3연속(시험값)"),
    "A20_reprise": ("측정", "질문 → 답 120초(시험값)"),
    "H1_first_speech": ("취향", "첫 말 0.5초"),
    "H2_first_change": ("취향", "첫 화면 변화 3초"),
    "H3_question": ("취향", "8초 안에 질문"),
    "H4_short_open": ("실무", "숏폼 2초 안에 말이나 훅 글자"),
    "S1_hedge": ("실무", "뺀 단서 문장 0"),
    "P1_phone_px": ("취향", "고정 자리 글자 28px"),
    "B1_media_ratio": ("취향", "실물 자료 20%"),
    "B2_hero": ("취향", "45초+ 챕터에 전면 자료"),
    "B3_query_label": ("구조", "자료 라벨 = 검색어 0"),
    "B4_direction": ("구조", "화면 글자 연출 메모 0"),
    "B5_internal": ("구조", "화면 글자 내부 이름 0"),
    "B6_relevance": ("구조", "비전 선택 2점 미만 0"),
    "B7_variety": ("취향", "같은 템플릿 2연속 · 25% · 조합 20%"),
    "B10_portraits": ("구조", "구도 분석 실패 0"),
    "B11_motif_repeat": ("구조", "같은 도식 2회 · 로고 1회(채널 주인)"),
    "B12_cutaway_role": ("실무", "임무 없는 컷어웨이 0 · mood 15%(시험값)"),
    "F1_blotch": ("구조", "색 잡음 ×2.0 · 색상 튐 1%"),
    "F3_sources": ("구조", "원본 사이 얼굴 ΔE 3"),
    "F4_clipping": ("구조", "날아간 면 2% · 증가 1%p"),
    "F6_tags": ("구조", "BT.709 · tv · yuv420p"),
    "D1_voice_music": ("측정", "목소리 − 음악 18~26 LU(논문 하한은 10 LU, A/B 전 수리 금지)"),
    "D3_one_track": ("구조", "한 영상 한 곡"),
    "D5_sfx_density": ("취향", "60초 창 효과음 상한"),
    "D6_fit": ("취향", "음악 감독 점수 7"),
    "D8_occupancy": ("취향", "음악 점유율 30~65%"),
    "D9_license": ("구조", "라이선스 미확인 0"),
    "D10_voice": ("측정", "목소리 −16 ±1 LUFS"),
    "D11_duration": ("구조", "믹스·렌더 길이 1프레임"),
    "D11_sfx_landing": ("구조", "효과음·착지 0.25초"),
    "D11_voice_caption": ("구조", "첫 자막·목소리 0.25초"),
    "D12_silences": ("실무", "전환·정점 앞 진짜 침묵 2곳"),
    "D13_ears": ("취향", "Gemini 가 믹스 발췌를 들은 소견 — 음악이 말을 덮음·효과음 튐·계획한 침묵(한 편 모델 소견이라 경고만)"),
    "E_timeline": ("취향", "가중 3.8 — 한 편 모델 점수라 참고만"),
}


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
    타이틀·챕터 카드·이름 자막은 내용 그래픽이 아니라 세지 않는다. 시계 기준이라 경고만 — 빈 칸은 토크 구간일 수 있다."""
    if total <= 0:
        return _skip("A6_distribution", "warn", "편집본 없음")
    n = max(1, min(max_bins, int(total // bin_min)))
    w = total / n
    spans = _spans(graphics, callouts, skip=AUTO_ONLY)
    empty = [i for i in range(n) if not any(a < (i + 1) * w and b > i * w for a, b in spans)]
    m = {"bins": n, "bin_sec": round(w, 1), "empty": empty,
         "empty_at": [[round(i * w, 1), round((i + 1) * w, 1)] for i in empty]}
    if empty:
        return _bad("A6_distribution", "warn", m,
                    f"{n}등분 중 그래픽이 하나도 없는 칸 {len(empty)}개("
                    + ", ".join(f"{fmt_ts(i * w)}–{fmt_ts((i + 1) * w)}" for i in empty[:4]) + ")")
    return _ok("A6_distribution", "warn", m, f"{n}등분 모든 칸에 그래픽 있음")


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
                soft: float = 50.0) -> GateResult:
    """맨얼굴 최장 구간 — 50초 넘으면 경고(30~50초 토크는 디자인 v5 의 곡선). 근거 없는 숫자라 카드를 끼워 고치지 않는다."""
    runs = face_only_spans(graphics, callouts, total)
    longest = max((b - a for a, b in runs), default=0.0)
    over = [(round(a, 1), round(b, 1)) for a, b in runs if b - a > soft]
    m = {"max_face_run": round(longest, 1), "over_soft": len(over), "runs": over[:8]}
    if longest <= soft:
        return _ok("A7_face_run", "warn", m, f"얼굴만 이어진 최장 {longest:.0f}초")
    a, b = max(runs, key=lambda r: r[1] - r[0])
    return _bad("A7_face_run", "warn", m, f"얼굴만 {longest:.0f}초 이어짐({fmt_ts(a)}–{fmt_ts(b)}, {soft:.0f}초 넘는 곳 {len(over)}곳)")


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


def a8_face_ratio(ratio: float, *, lo: float = 0.40, hi: float = 0.85) -> GateResult:
    """얼굴 화면 비율 40~85%(디자인 v5, 목표 50~60%). 수리 없음 — 카드를 더해도 비율은 바뀌지 않는다."""
    m = {"face_ratio": round(ratio, 3)}
    if lo <= ratio <= hi:
        return _ok("A8_face_ratio", "warn", m, f"얼굴 화면 비율 {ratio * 100:.0f}%")
    return _bad("A8_face_ratio", "warn", m,
                f"얼굴 화면 비율 {ratio * 100:.0f}%(권장 {lo * 100:.0f}~{hi * 100:.0f}%) — "
                + ("전체화면 자료가 너무 적음" if ratio > hi else "얼굴이 너무 적게 보임"))


def a9_title(graphics: list[dict], *, limit: float = 40.0) -> GateResult:
    """타이틀 카드는 본편 시작 후 40초 안(10/1 테스트: 06:48). 콜드 오픈 길이는 근거가 없는 숫자라 경고만."""
    ts = [float(g["start"]) for g in graphics if g.get("template") == "title"]
    if not ts:
        return _skip("A9_title", "warn", "타이틀 카드 없음")
    t = min(ts)
    m = {"title_at": round(t, 1)}
    if t <= limit:
        return _ok("A9_title", "warn", m, f"타이틀 {fmt_ts(t)}")
    return _bad("A9_title", "warn", m, f"타이틀 카드가 본편 {fmt_ts(t)} 에 나옴(권장 40초 안)")


# ---------------------------------------------------------------------------
# 게이트 A12~A16 — 리듬(docs/upgrade/05_편집_문법_v2.md 4-2). 시계가 아니라 내용이 박자를 정한다
# ---------------------------------------------------------------------------

CONTENT_SKIP = ("title", "lower_third", "chapter")


def _content(graphics: list[dict]) -> list[dict]:
    return sorted((g for g in graphics if g.get("template") not in CONTENT_SKIP and g.get("end", 0) > g.get("start", 0)),
                  key=lambda g: g["start"])


def _seq_of(g: dict) -> str:
    return str((g.get("data") or {}).get("seq_id") or g.get("sequence_id") or "")


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
        return _ok("A12_chain", "warn", m, f"그래픽 사슬 최장 {longest}개")
    c = chains[0]
    return _bad("A12_chain", "warn", m, f"시퀀스가 아닌 그래픽 {len(c)}개가 1초 안 간격으로 이어짐({fmt_ts(c[0]['start'])}–"
                f"{fmt_ts(c[-1]['end'])}) — 권장 3개까지")


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


def a18_word_sync(graphics: list[dict], *, median_max: float = 0.35, any_max: float = 1.0) -> GateResult:
    """표시가 말한 낱말에 착지했나. wordMarks = time_graphics 가 낱말을 찾은 표시마다 남긴 {land(그래픽 기준 초), spoken(편집 시각)}
    — 그 뒤 겹침 풀기·수리로 그래픽이 밀리면 여기서 잡힌다. 하이라이트로 밀기 전 본편 시각에서 부른다."""
    lags = [abs(float(g["start"]) + float(m["land"]) - float(m["spoken"])) for g in graphics for m in _d(g).get("wordMarks") or []]
    if not lags:
        return _ok("A18_word_sync", "warn", {"n": 0}, "낱말에 맞춘 표시 없음")
    med, worst = statistics.median(lags), max(lags)
    m = {"n": len(lags), "median": round(med, 3), "max": round(worst, 3)}
    if med > median_max or worst > any_max:
        return _bad("A18_word_sync", "warn", m, f"표시가 말과 어긋남: 중앙값 {med:.2f}초(≤{median_max}) · 최대 {worst:.2f}초(≤{any_max:.1f})")
    return _ok("A18_word_sync", "warn", m, f"낱말 착지 {len(lags)}곳 · 중앙값 {med:.2f}초 · 최대 {worst:.2f}초")


def and_runs(segments: list[dict], *, run: int = 3) -> list[list[dict]]:
    """단락 연결 감사: 앞 단락과 '그리고'(link = and)로만 이어진 단락이 run 개 이상 연달아 있는 묶음들."""
    out: list[list[dict]] = []
    cur: list[dict] = []
    for s in list(segments) + [{}]:
        if s.get("link") == "and":
            cur.append(s)
            continue
        if len(cur) >= run:
            out.append(cur)
        cur = []
    return out


def a19_link_audit(segments: list[dict]) -> GateResult:
    """단락 연결(treatment.segments[].link)이 '그래서·그런데' 없이 '그리고'만 이어지는 곳. 대본은 못 고치므로 알리기만 하고
    연출은 merge_plan(link_pauses)이 쉼으로 끊는다."""
    links = [str(s.get("link") or "") for s in segments]
    if not any(links):
        return _skip("A19_link_audit", "warn", "단락 연결 선언 없음")
    runs = and_runs(segments)
    m: dict[str, Any] = {k: links.count(k) for k in ("therefore", "but", "and", "none")}
    m["runs"] = [[r[0].get("start_seg"), r[-1].get("end_seg")] for r in runs]
    if runs:
        return _bad("A19_link_audit", "warn", m, f"단락이 '그리고'로만 이어진 곳 {len(runs)}곳"
                    f"(S{m['runs'][0][0]}–S{m['runs'][0][1]}) — 대본은 그대로 두고 쉼으로 끊음")
    return _ok("A19_link_audit", "warn", m, f"단락 연결 그래서 {m['therefore']} · 그런데 {m['but']} · 그리고 {m['and']}")


REPRISE_AFTER = 120.0     # 질문을 연 지 이보다 오래면 답 앞에 다시 띄운다(Golman: 최근에 열린 질문일수록 답을 찾는다 — 초는 시험값)


def reprise_slot(busy: list[tuple[float, float]], answer_at: float, *, need: float = 3.0, want: float = 4.0,
                 back: float = 25.0) -> Optional[tuple[float, float]]:
    """답 앞 back 초 안에서 답에 가장 가까운 빈 자리(need 초 이상, 길면 want 초). 없으면 None."""
    floor = max(0.0, answer_at - back)
    end = answer_at - 0.2
    for a, b in sorted(busy, key=lambda r: -r[1]) + [(floor - 1.0, floor - 0.3)]:
        start = max(floor, b + 0.3)
        if end - start >= need:
            return round(max(start, end - want), 3), round(end, 3)
        end = min(end, a - 0.3)
    return None


def a20_reprise(span: Optional[tuple[float, float]], graphics: list[dict], *, after: float = REPRISE_AFTER) -> GateResult:
    """중심 질문이 열린 시각 → 답(payoff_seg)이 2분 넘게 떨어져 있으면 답 앞에 질문이 다시 떠야 한다."""
    if span is None:
        return _skip("A20_reprise", "warn", "중심 질문이나 답 발화 없음")
    gap = span[1] - span[0]
    m = {"opened": round(span[0], 1), "answer": round(span[1], 1), "gap": round(gap, 1)}
    if gap <= after:
        return _ok("A20_reprise", "warn", m, f"질문에서 답까지 {gap:.0f}초 — 다시 띄울 필요 없음")
    if any(g.get("id") == "reprise" for g in graphics):
        return _ok("A20_reprise", "warn", m, f"질문에서 답까지 {gap:.0f}초 — 답 앞에 다시 띄움")
    return _bad("A20_reprise", "warn", m, f"질문을 연 지 {gap:.0f}초 뒤에 답이 나오는데 답 앞에 다시 띄울 빈 자리가 없음({fmt_ts(span[1])})")


# --- 훅(최종 타임라인: 하이라이트를 붙인 뒤의 롱폼 · 숏폼) --------------------------------------------------------------
_WORDS = re.compile(r"[0-9A-Za-z가-힣]+")


def h1_first_speech(captions: list[dict], *, limit: float = 0.5) -> GateResult:
    """첫 말은 0.5초 안에."""
    if not captions:
        return _skip("H1_first_speech", "warn", "자막 없음")
    t = min(float(c["start"]) for c in captions)
    m = {"first_speech": round(t, 3)}
    if t > limit:
        return _bad("H1_first_speech", "warn", m, f"첫 말이 {t:.2f}초에 시작(≤{limit})")
    return _ok("H1_first_speech", "warn", m, f"첫 말 {t:.2f}초")


def h2_first_change(props: dict, *, limit: float = 3.0) -> GateResult:
    """첫 화면 변화는 3초 안에: 그래픽 들고남 · 콜아웃 · 전환 · 펀치 · 프레이밍이 바뀌는 컷 · 다른 카메라."""
    ev = [float(g[k]) for g in props.get("graphics") or [] for k in ("start", "end")]
    ev += [float(c["start"]) for c in props.get("callouts") or []]
    ev += [float(x["t"]) for k in ("transitions", "punches") for x in props.get(k) or []]
    cam, clips = props.get("camera") or [], props.get("clips") or []
    ev += [float(b["start"]) for a, b in zip(cam, cam[1:]) if b.get("cut") or abs(b["zoom"] - a["zoomEnd"]) > 1e-3]
    ev += [float(b["start"]) for a, b in zip(clips, clips[1:]) if a["src"] != b["src"]]
    first = min((t for t in ev if t > 0.05), default=None)
    m = {"first_change": None if first is None else round(first, 3)}
    if first is None or first > limit:
        return _bad("H2_first_change", "warn", m, f"첫 {limit:.0f}초 동안 화면이 바뀌지 않음")
    return _ok("H2_first_change", "warn", m, f"첫 화면 변화 {first:.2f}초")


def h3_question(captions: list[dict], question: str, *, by: float = 8.0, share: float = 0.5) -> GateResult:
    """계획이 선언한 질문이 8초 안에 들리나. 총괄 감독이 줄여 쓴 문장이라 어절의 앞 두 글자로 맞춘다(어미·조사가 달라도 같은 말)."""
    q = _WORDS.findall(question or "")
    if not q:
        return _skip("H3_question", "warn", "계획에 질문 없음")
    heard = {x[:2] for c in captions if float(c["start"]) < by for line in c.get("lines") or [] for w in line
             for x in _WORDS.findall(w.get("text", ""))}
    r = sum(w[:2] in heard for w in q) / len(q)
    m = {"question": question[:40], "heard_share": round(r, 2)}
    if r < share:
        return _bad("H3_question", "warn", m, f"{by:.0f}초 안에 훅의 질문이 들리지 않음({r:.0%}): {question[:30]}")
    return _ok("H3_question", "warn", m, f"{by:.0f}초 안에 질문이 들림({r:.0%})")


def h4_short_open(props: dict, *, limit: float = 2.0) -> GateResult:
    """숏폼은 2초 안에 말이나 훅 글자가 나와야 한다(훅 타이틀은 0초부터 화면에 있다 — HookTitle·ReelShort)."""
    speech = min((float(c["start"]) for c in props.get("captions") or []), default=None)
    hook = bool(str(props.get("hookTitle") or "").strip())
    m = {"first_speech": None if speech is None else round(speech, 3), "hook_text": hook}
    if not hook and (speech is None or speech > limit):
        return _bad("H4_short_open", "warn", m, f"숏폼 첫 {limit:.0f}초에 말도 훅 글자도 없음")
    return _ok("H4_short_open", "warn", m, "숏폼 시작에 훅 글자" if hook else f"숏폼 첫 말 {speech:.2f}초")


# 숏폼 발췌에서 빠지면 주장이 단정으로 바뀌는 말(플레이북 8-3)
HEDGE = re.compile(r"다만|물론|반론|에\s*따르면|에\s*의하면|아직\s*확인|확인되지\s*않|제\s*생각에는")


def s1_hedge(segs: list[int], text_of: dict[int, str], kept: list[int], *, before: int = 1, after: int = 2) -> GateResult:
    """주장 + 근거로 자른 숏폼이 단서 문장을 뺐는가. 고른 발화의 앞 before · 뒤 after 발화 중 빠진 것을 본다
    (~에 따르면 은 주장 앞에, 다만 은 뒤에 온다). kept: 남긴 발화의 편집 순서."""
    pos = {u: i for i, u in enumerate(kept)}
    chosen = sorted(pos[s] for s in segs if s in pos)
    if not chosen:
        return _skip("S1_hedge", "warn", "숏폼 발화 없음")
    near = {p for q in chosen for p in range(q - before, q + after + 1)}
    lost = [kept[p] for p in sorted(near - set(chosen)) if 0 <= p < len(kept) and HEDGE.search(text_of.get(kept[p], ""))]
    m = {"lost": lost, "examples": [text_of.get(u, "")[:30] for u in lost[:3]]}
    if lost:
        return _bad("S1_hedge", "warn", m, f"숏폼이 단서 문장 {len(lost)}개를 뺐다(예: 「{m['examples'][0]}」) — 주장이 단정으로 바뀔 수 있다")
    return _ok("S1_hedge", "warn", m, "숏폼 곁의 단서 문장을 빼지 않음")


# --- 폰 가독성(고정 자리) ---------------------------------------------------------------------------------------
def slot_px() -> dict[str, float]:
    """렌더러가 고정 자리에 쓰는 값(tokens.ts SLOT_TYPE) → 자리마다 가장 작아질 때의 px(1080p). 자유 카드는 check.mjs 가 잰다."""
    src = (RENDERER_DIR / "src" / "design" / "tokens.ts").read_text(encoding="utf-8")
    body = src[src.index("export const SLOT_TYPE"):]
    t = {k: float(v) for k, v in re.findall(r"(\w+):\s*([\d.]+)", body[:body.index("}")])}
    return {"자막": t["caption"], "띠 제목": t["band"], "용어 정의 본문": t["definition"] * t["bandBody"],
            "슈퍼 이름": t["superName"], "슈퍼 소속": t["superSub"], "핵심어": t["keywordMin"],
            "핵심어 보조": max(t["keywordSubMin"], t["keywordMin"] * t["keywordSub"]), "인용": 1080 * t["quote"],
            "인용 원전": 1080 * t["quote"] * t["quoteWho"], "숫자 태그 보조": t["statSub"], "출처": t["credit"]}


def p1_phone_px(slots: dict[str, float], *, floor: float = 28.0) -> GateResult:
    """고정 자리 글자의 최소 px ≥ check.mjs 와 같은 28px."""
    low = {k: round(v, 1) for k, v in slots.items() if v < floor}
    m = {"floor": floor, "below": low, "slots": len(slots)}
    if list(low) == ["출처"]:   # 출처는 읽으라고 띄우는 글이 아니라 자료 내내 깔리는 표기다(v5 '우하단 작게')
        return _ok("P1_phone_px", "warn", m, f"고정 자리 글자 {floor:.0f}px 이상(출처 표기만 예외 {low['출처']}px)")
    if low:
        return _bad("P1_phone_px", "warn", m, "폰에서 작은 고정 자리: " + ", ".join(f"{k} {v}px" for k, v in low.items()))
    return _ok("P1_phone_px", "warn", m, f"고정 자리 글자 모두 {floor:.0f}px 이상")


def b7_variety(graphics: list[dict], *, run_max: int = 2, share_max: float = 0.25, combo_max: float = 0.20,
               min_n: int = 8) -> GateResult:
    """B7 변주(docs/upgrade/06 5장): 같은 템플릿 3회 연속 금지 · 한 템플릿 ≤ 25% · (구도, 템플릿) 쌍이 직전과 같지 않다 ·
    한 조합 ≤ 20%. 10/1: double_diamond 5 · compare 3 · keyword 8(41개). 길잡이·자동 템플릿과 시퀀스 안의 샷은 빼고 센다."""
    gs = [g for g in _content(graphics) if not _seq_of(g)]
    if len(gs) < min_n:
        return _skip("B7_variety", "warn", "그래픽이 적어 건너뜀")
    tpl = [g["template"] for g in gs]
    combo = [(g.get("layout", ""), g["template"]) for g in gs]
    run, worst, at = 1, 1, ""
    for a, b in zip(tpl, tpl[1:]):
        run = run + 1 if a == b else 1
        if run > worst:
            worst, at = run, b
    pairs = sum(1 for a, b in zip(combo, combo[1:]) if a == b)
    top_t = max(set(tpl), key=tpl.count)
    top_c = max(set(combo), key=combo.count)
    m = {"n": len(gs), "max_run": worst, "run_template": at, "top_template": top_t,
         "top_template_share": round(tpl.count(top_t) / len(gs), 2), "repeat_pairs": pairs,
         "top_combo": "/".join(top_c), "top_combo_share": round(combo.count(top_c) / len(gs), 2)}
    bad = []
    if worst > run_max:
        bad.append(f"{at} {worst}회 연속")
    if m["top_template_share"] > share_max:
        bad.append(f"{top_t} {m['top_template_share']:.0%}")
    if m["top_combo_share"] > combo_max:
        bad.append(f"{m['top_combo']} 조합 {m['top_combo_share']:.0%}")
    if bad:
        return _bad("B7_variety", "warn", m, "같은 구조 반복: " + " · ".join(bad) + " — 글자가 아니라 구조를 바꾼다")
    return _ok("B7_variety", "warn", m, f"변주 최다 {top_t} {m['top_template_share']:.0%} · 연속 최대 {worst}")


# ---------------------------------------------------------------------------
# 게이트 B11 — 같은 시각 장치의 되풀이(2026-10-03 채널 주인: "더블 다이아몬드 모션 그래픽이 너무 많이 나와", 로고도 한 번만)
# ---------------------------------------------------------------------------

MOTIF_TEMPLATES = ("motion", "card", "evidence", "photo", "broll", "double_diamond", "process", "cycle", "pyramid",
                   "venn", "timeline", "compare", "diagram")
_MOTIF_STOP = {"내가", "우리", "그리고", "그래서", "하지만", "이론", "디자인", "과정", "순서", "실제", "결국", "오늘", "장면",
               "이야기", "질문", "예고", "다시", "같은", "하나", "모든", "위에", "사이"}
_MOTIF_TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")


def _motif_phrases(title: str) -> set[str]:
    """제목의 이어진 두 낱말(바이그램) — '더블 다이아몬드' 처럼 이름이 두 낱말인 장치를 잡는다."""
    toks = [t for t in _MOTIF_TOKEN.findall(title or "") if t not in _MOTIF_STOP]
    return {toks[i] + " " + toks[i + 1] for i in range(len(toks) - 1)}


def motif_groups(graphics: list[dict]) -> dict[str, list[dict]]:
    """같은 장치를 그린 그래픽 묶음(시간순). 열쇠는 `data.motif`(에이전트가 적음) · 로고 파일 · 제목의 같은 두 낱말 구절."""
    gs = [g for g in _content(graphics) if g.get("template") in MOTIF_TEMPLATES]
    groups: dict[str, list[dict]] = {}
    seen: set[int] = set()
    for g in gs:
        d = g.get("data") or {}
        key = ""
        if d.get("logo"):
            key = "logo:" + str(d.get("image") or d.get("src") or d.get("title") or "").rsplit("/", 1)[-1]
        elif d.get("motif"):
            key = "motif:" + str(d["motif"]).strip().lower()
        if key:
            groups.setdefault(key, []).append(g)
            seen.add(id(g))
    rest = [g for g in gs if id(g) not in seen]
    phrases = [_motif_phrases(str((g.get("data") or {}).get("title") or "")) for g in rest]
    used: set[int] = set()
    for i, g in enumerate(rest):
        if i in used or not phrases[i]:
            continue
        members = [i] + [j for j in range(i + 1, len(rest)) if j not in used and phrases[i] & phrases[j]]
        if len(members) > 1:
            key = "title:" + sorted(phrases[i] & phrases[members[1]])[0]
            groups[key] = [rest[j] for j in members]
            used.update(members)
    return groups


def b11_motif_repeat(graphics: list[dict], *, cap: int = 2, logo_cap: int = 1) -> GateResult:
    """B11 같은 장치 되풀이: 같은 도식·사물(`motif` 또는 제목의 같은 두 낱말)은 영상당 2회(처음 + 결론)까지, 같은 로고는 1회.
    넘으면 수리 `trim_motifs`(시그니처 장면은 남기고, 요소가 적은 장면부터 뺌)."""
    groups = motif_groups(graphics)
    over = {k: v for k, v in groups.items() if len(v) > (logo_cap if k.startswith("logo:") else cap)}
    m = {"groups": {k: [str(g.get("id", "")) for g in v] for k, v in groups.items() if len(v) > 1},
         "over": {k: len(v) for k, v in over.items()}}
    if over:
        return _bad("B11_motif_repeat", "repair", m, "같은 장치 되풀이: " + " · ".join(
            f"{k.split(':', 1)[1]} {len(v)}회" for k, v in over.items()) + f" — 도식·사물은 {cap}회, 로고는 {logo_cap}회까지",
            "trim_motifs")
    return _ok("B11_motif_repeat", "repair", m, "되풀이 없음" if not m["groups"] else
               "되풀이 " + " · ".join(f"{k.split(':', 1)[1]} {len(v)}회" for k, v in groups.items() if len(v) > 1))


def motif_drops(graphics: list[dict], *, cap: int = 2, logo_cap: int = 1) -> list[dict]:
    """B11 수리: 묶음마다 상한을 넘는 그래픽 — 시그니처 장면은 늘 남기고, 나머지는 내용이 많은 것(요소·글자 수) → 먼저 나온 것 순으로
    남긴다. 반환은 뺄 그래픽(렌더 props 의 그래픽)."""
    def weight(g: dict) -> float:
        d = g.get("data") or {}
        if d.get("signature") or g.get("signature"):
            return 1e9
        spec = d.get("spec") if isinstance(d.get("spec"), dict) else None
        if spec:
            return len(spec.get("elements") or []) + len(spec.get("els") or [])
        if isinstance(d.get("card"), dict):
            return len(re.sub(r"<[^>]+>", "", str(d["card"].get("html", "")))) / 8.0
        return 1.0 + float(g.get("end", 0) - g.get("start", 0)) / 100.0
    drops: list[dict] = []
    for k, members in motif_groups(graphics).items():
        limit = logo_cap if k.startswith("logo:") else cap
        if len(members) <= limit:
            continue
        if k.startswith("logo:"):
            # 로고는 이름표(pip) · 먼저 나온 것을 남긴다 — 전면으로 키운 쪽이 빠진다
            keep = sorted(members, key=lambda g: (g.get("layout") != "pip", g.get("start", 0)))[:limit]
        else:
            keep = sorted(members, key=lambda g: (-weight(g), g.get("start", 0)))[:limit]
        drops += [g for g in members if g not in keep]
    return drops


# ---------------------------------------------------------------------------
# 게이트 B — 화면 글자 위생(렌더 props 확정 뒤)
# ---------------------------------------------------------------------------

TEXT_FIELDS = ("title", "subtitle", "body", "title_b", "highlight", "author", "label", "keyword", "keyword_sub", "caption")
LIST_FIELDS = ("items", "items_b", "overlays")
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
    if t in ("collage", "keyword_montage"):
        return bool(d.get("cutouts"))
    return False


def is_hero_media(g: dict) -> bool:
    """전면 실물(풀블리드 또는 화면의 55% 이상 — 증거 hero 는 1728×724 ≈ 60%)."""
    return is_real_media(g) and (g.get("layout") == "fullscreen" or g.get("template") == "evidence")


def b10_portraits(plans: list[dict]) -> GateResult:
    """B10 인물 사진 구도(채널 주인: "인물 사진은 얼굴이 잘 드러나고 잘리지 않는지 확인") — compose.plan_media 결과를 센다.
    얼굴이 잘려 초점을 옮겼거나(focus) 통째로 보이게 한(contain) 사진은 수리된 것, 분석 자체를 못 한 사진은 경고."""
    faces = [p for p in plans if p.get("face")]
    moved = sum(1 for p in faces if p.get("focus"))
    contain = sum(1 for p in faces if p.get("fit") == "contain")
    failed = sum(1 for p in plans if p.get("error"))
    m = {"photos": len(plans), "faces": len(faces), "refocused": moved, "contain": contain, "unanalyzed": failed}
    if failed:
        return _bad("B10_portraits", "warn", m, f"사진 {failed}장은 구도를 분석하지 못했다(얼굴이 잘릴 수 있음)")
    return _ok("B10_portraits", "warn", m, f"사진 {len(plans)}장 구도 분석 — 얼굴 {len(faces)}(초점 조정 {moved} · 통째 {contain})")


def b1_media_ratio(graphics: list[dict], total: float, *, min_ratio: float = 0.20) -> GateResult:
    """실물 자료가 보이는 시간 / 본편 ≥ 20%(목표 25~35% — 디자인 v5). 짧은 영상(90초 미만)은 건너뛴다."""
    secs = sum(max(0.0, float(g["end"]) - float(g["start"])) for g in graphics if is_real_media(g) and "end" in g)
    ratio = secs / total if total else 0.0
    m = {"seconds": round(secs, 1), "ratio": round(ratio, 3), "target": [0.25, 0.35], "min": min_ratio}
    if total < 90:
        r = _ok("B1_media_ratio", "warn", m, f"실물 자료 {ratio:.0%}(짧은 영상 — 건너뜀)")
        r.skipped = True
        return r
    if ratio < min_ratio:
        return _bad("B1_media_ratio", "warn", m, f"실물 자료가 보이는 시간 {ratio:.0%}(최소 {min_ratio:.0%}, 목표 25~35%) — "
                    "과제물·스케치·화면 캡처를 ④ 자료 폴더에 넣으면 채워진다")
    return _ok("B1_media_ratio", "warn", m, f"실물 자료 {ratio:.0%}")


def b2_hero_per_chapter(graphics: list[dict], chapters: list[dict], total: float, *, min_len: float = 45.0) -> GateResult:
    """실물 자료가 있는 챕터(45초 이상)마다 전면 실물이 한 번 이상 — 얼굴 옆 작은 액자(pip)만으로 끝나는 챕터가 없다.
    chapters: [{start, end?}] (끝이 없으면 다음 챕터 시작·전체 끝)."""
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
        return _bad("B2_hero", "warn", m, f"전면 실물 자료가 없는 챕터 {len(lacking)}개(얼굴 옆 작은 액자뿐)")
    return _ok("B2_hero", "warn", m, "자료가 있는 챕터마다 전면 자료가 있다")


# 자료 리서처의 role → 컷어웨이 임무(비트에 선언이 없을 때)
EV_ROLE_TO_CUTAWAY = {"proof": "prove", "example": "prove", "context": "context", "process": "explain", "mood": "reset"}


def cutaway_roles(graphics: list[dict], plan_graphics: list[dict], beats: list[dict]) -> dict[str, str]:
    """화면의 그래픽(id g{i} = 계획 순서) → 임무. 자료 리서처가 mood 로 낸 자료는 비트가 뭐라 했든 reset."""
    out: dict[str, str] = {}
    for g in graphics:
        m = re.fullmatch(r"g(\d+)", str(g.get("id", "")))
        if not m or int(m.group(1)) >= len(plan_graphics):
            continue
        pg = plan_graphics[int(m.group(1))]
        seg = pg.get("start_seg", -1)
        beat = next((b for b in beats if b.get("start_seg", 0) <= seg <= b.get("end_seg", -1)), {})
        ev = EV_ROLE_TO_CUTAWAY.get(str((pg.get("evidence") or {}).get("role") or ""), "")
        role = str(beat.get("cutaway") or "")
        out[str(g["id"])] = "reset" if ev == "reset" else (role if role not in ("", "none") else ev)
    return out


def b12_cutaway_role(graphics: list[dict], roles: dict[str, str], *, mood_cap: float = 0.15) -> GateResult:
    """컷어웨이(얼굴을 덮는 전면 그래픽)마다 임무가 있는가, 분위기뿐인 자료(reset)가 컷어웨이 시간의 15% 안인가. 시험값이라 경고만.
    얼굴 위 pip 사진은 비트의 cutaway 가 none 인 자리라 세지 않는다."""
    cuts = [g for g in _content(graphics) if g.get("layout") == "fullscreen"]
    if not cuts or not any(roles.values()):
        return _skip("B12_cutaway_role", "warn", "컷어웨이나 임무 선언 없음(규칙 폴백)")
    total = sum(float(g["end"]) - float(g["start"]) for g in cuts)
    mood = sum(float(g["end"]) - float(g["start"]) for g in cuts if roles.get(str(g.get("id"))) == "reset")
    missing = [str(g.get("id")) for g in cuts if not roles.get(str(g.get("id")))]
    share = mood / total if total else 0.0
    m = {"cutaways": len(cuts), "mood_sec": round(mood, 1), "mood_share": round(share, 3), "undeclared": missing[:12]}
    bad = ([f"임무를 선언하지 않은 컷어웨이 {len(missing)}개({', '.join(missing[:4])})"] if missing else []) \
        + ([f"분위기뿐인 자료 {share:.0%}(상한 {mood_cap:.0%})"] if share > mood_cap else [])
    if bad:
        return _bad("B12_cutaway_role", "warn", m, " · ".join(bad))
    return _ok("B12_cutaway_role", "warn", m, f"컷어웨이 {len(cuts)}개 모두 임무 있음 · 분위기뿐인 자료 {share:.0%}")


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
        return _skip("D1_voice_music", "warn", "음악 없음")
    d = voice_lufs - (ref_lufs + under_db)
    m = {"voice_lufs": round(voice_lufs, 1), "music_under_lufs": round(ref_lufs + under_db, 1), "diff_lu": round(d, 1)}
    if not lo <= d <= hi:
        return _bad("D1_voice_music", "warn", m, f"목소리가 음악보다 {d:.1f} LU 위({lo:.0f}~{hi:.0f})")
    return _ok("D1_voice_music", "warn", m, f"목소리 − 음악 {d:.1f} LU")


def d3_one_track(tracks: int) -> GateResult:
    """한 영상 한 곡(아이덴트 제외)."""
    m = {"tracks": tracks}
    if tracks > 1:
        return _bad("D3_one_track", "repair", m, f"곡이 {tracks}개 — 한 영상 한 곡", "one_track")
    return _ok("D3_one_track", "repair", m, "곡 하나" if tracks else "음악 없음")


def d5_sfx_density(cues: list[tuple[float, str]], *, window: float = 60.0, cap: int = 3) -> GateResult:
    """효과음: 60초 창 어디서도 cap 개 이하, 같은 파일 연속 2회 금지. cues: (시각, 파일 경로) 시간순."""
    cues = sorted(cues)
    outside = [t for t, _ in cues]
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
    """음악 감독의 fit_score ≥ 7 — 아니면 믹스가 air 판으로 간다(음악 감독 자신의 판단이라 게이트는 알리기만 한다)."""
    if fit_score is None:
        return _skip("D6_fit", "warn", "큐 시트 없음")
    m = {"fit_score": fit_score}
    if fit_score < min_fit:
        return _bad("D6_fit", "warn", m, f"맞는 음악 점수 {fit_score}/10 — air 만 쓴다")
    return _ok("D6_fit", "warn", m, f"맞는 음악 점수 {fit_score}/10")


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


def d11_duration(mix_sec: float, render_sec: float, fps: float, name: str = "") -> GateResult:
    """믹스와 무음 렌더의 길이가 1프레임 넘게 다르면 합칠 때(-shortest) 끝이 잘린다."""
    diff = abs(mix_sec - render_sec)
    m = {"name": name, "mix_sec": round(mix_sec, 3), "render_sec": round(render_sec, 3), "diff_sec": round(diff, 3)}
    if diff > 1.0 / fps + 1e-3:
        return _bad("D11_duration", "block", m, f"{name} 소리와 영상 길이가 {diff:.3f}초 다름(믹스 {mix_sec:.3f} · 렌더 {render_sec:.3f})")
    return _ok("D11_duration", "block", m, f"소리·영상 길이 차이 {diff:.3f}초")


def d11_sfx_landing(cues: list[dict], landings: list[float], *, tol: float = 0.25) -> GateResult:
    """그래픽 등장에서 나온 효과음(why 에 '등장')은 최종 타임라인에서 그 착지 tol 초 안에 있어야 한다."""
    from_g = [float(c["t"]) for c in cues if "등장" in str(c.get("why", ""))]
    off = [round(t, 2) for t in from_g if not any(abs(t - x) <= tol for x in landings)]
    m = {"cues": len(from_g), "off": off[:8]}
    if off:
        return _bad("D11_sfx_landing", "warn", m, f"효과음 {len(off)}개가 그래픽 착지에서 {tol}초 넘게 떨어짐({off[0]:.1f}초 등)")
    return _ok("D11_sfx_landing", "warn", m, f"그래픽 효과음 {len(from_g)}개 착지에 맞음")


def d11_voice_caption(voice_sec: Optional[float], caption_sec: Optional[float], *, tol: float = 0.25) -> GateResult:
    """실제 목소리 파일의 시작과 첫 자막이 tol 초 안에."""
    if voice_sec is None or caption_sec is None:
        return _skip("D11_voice_caption", "warn", "목소리 시작이나 자막이 없음")
    diff = abs(voice_sec - caption_sec)
    m = {"voice_sec": round(voice_sec, 3), "caption_sec": round(caption_sec, 3), "diff_sec": round(diff, 3)}
    if diff > tol:
        return _bad("D11_voice_caption", "warn", m, f"첫 자막이 목소리와 {diff:.2f}초 어긋남(≤{tol})")
    return _ok("D11_voice_caption", "warn", m, f"첫 자막·목소리 차이 {diff:.2f}초")


def d12_silences(spans: Optional[list[tuple[float, float]]], cues: list[dict], sfx: list[tuple[float, str]], *, need: int = 2,
                 min_sec: float = 0.5) -> GateResult:
    """총괄 감독이 전환·정점 앞에 선언한 침묵이 실제로 났는가: 말이 min_sec 이상 쉬고 그 사이 음악 큐·효과음이 없는 곳이 need 곳 이상.
    spans: 최종 타임라인의 쉼(앞 발화 끝, 다음 발화 시작). None = 기획에 트리트먼트가 없다(규칙 폴백)."""
    if spans is None:
        return _skip("D12_silences", "warn", "트리트먼트 없음")
    real = [(a, b) for a, b in spans if b - a >= min_sec
            and not any(float(q["start"]) < b - 0.02 and float(q["end"]) > a + 0.02 for q in cues)     # 큐 경계는 0.01초로 반올림돼 있다
            and not any(a <= float(t) <= b for t, _ in sfx)]
    m = {"declared": len(spans), "real": len(real), "spans": [[round(a, 1), round(b, 1)] for a, b in real[:8]]}
    if len(real) < need:
        return _bad("D12_silences", "warn", m, f"전환·정점 앞 진짜 침묵 {len(real)}곳(선언 {len(spans)}, 필요 {need})")
    return _ok("D12_silences", "warn", m, f"전환·정점 앞 침묵 {len(real)}곳")


def d13_ears(heard: Optional[dict], why: str = "") -> GateResult:
    """👂 Gemini 가 완성 믹스 발췌를 들은 소견(studio/sound/listen.py hear_mix). 경고만 — 믹스를 자동으로 바꾸지 않는다."""
    if not heard:
        return _skip("D13_ears", "warn", f"듣지 못함({why})" if why else "들을 발췌 없음")
    bad = [t for k, t in (("music_covers_voice", "음악이 말을 덮음"), ("sfx_jumps_out", "효과음이 튐")) if heard.get(k) is True]
    if heard.get("silence_clear") is False:
        bad.append("계획한 침묵이 안 들림")
    note = f" — {heard['note']}" if heard.get("note") else ""
    if bad:
        return _bad("D13_ears", "warn", dict(heard), "👂 " + " · ".join(bad) + note)
    return _ok("D13_ears", "warn", dict(heard), "👂 믹스 발췌 이상 없음" + note)


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
                   "no_tails": ["A16_hold_presence"], "no_evidence": [], "wrong_image": [],
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
