"""단계 그래픽(steps → stepAt)과 얼굴 홀드(docs/upgrade/05_편집_문법_v2.md 8절 1·2번).

10/1 테스트: S122 "먼저 문제를 넓게 탐색하고, 그걸 좁혀서 정의하고, 그다음에 아이디어를 내라고요" — 더블 다이아몬드 그래픽 3개를
이어 붙여 '정의' 강조가 말보다 +3.9초, '아이디어'가 +5.7초 늦었다. S158–S160(고백)은 챕터 정리 보드가 덮었다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studio.director.plan import (TimedGraphic, merge_step_runs, normalize_long, step_times,  # noqa: E402
                                  time_graphics)
from studio.edit.grammar import Moment, build_long_edit  # noqa: E402
from studio.models import Span, TimeMap, Utterance, Word  # noqa: E402
from studio.render.props import chapter_recaps  # noqa: E402


def _utt(uid: int, t: float, text: str, per: float = 0.45) -> Utterance:
    words = [Word(w, t + k * per, t + k * per + per * 0.9, 0.95) for k, w in enumerate(text.split())]
    return Utterance(id=uid, start=t, end=words[-1].end, text=text, asr_text=text, words=words, status="keep")


S122 = "먼저 문제를 넓게 탐색하고 그걸 좁혀서 정의하고 그다음에 아이디어를 내라고요"


def _utts() -> list[Utterance]:
    return [_utt(0, 0.0, "더블 다이아몬드라는 유명한 도식이 있습니다"),
            _utt(1, 4.0, S122),
            _utt(2, 9.0, "결국 순서가 중요하다는 말입니다"),
            _utt(3, 13.0, "저도 처음엔 그 순서를 거꾸로 했습니다"),
            _utt(4, 17.0, "그 순간이 지금도 기억납니다"),
            _utt(5, 21.0, "제가 건너뛴 건 단계가 아니었습니다"),
            _utt(6, 25.0, "내 첫 아이디어를 의심해볼 시간이었죠")]


def _word_t(u: Utterance, w: str) -> float:
    return next(x.start for x in u.words if x.text.startswith(w))


def test_steps_change_on_spoken_words():
    utts = _utts()
    tm = TimeMap([Span(0.0, 30.0)])
    dd = {"template": "double_diamond", "layout": "split", "start_seg": 1, "end_seg": 1, "start_word": "먼저",
          "title": "더블 다이아몬드", "items": ["발견", "정의", "개발", "전달"],
          "steps": [{"word": "먼저", "highlight": 0}, {"word": "좁혀서", "highlight": 1},
                    {"word": "그다음에", "highlight": 2}]}
    plan = normalize_long({"graphics": [dd]}, utts, [])
    assert len(plan["graphics"]) == 1 and len(plan["graphics"][0]["steps"]) == 3
    [g] = time_graphics(plan["graphics"], utts, tm, total=30.0)
    at = g.data["stepAt"]
    assert [s["index"] for s in at] == [0, 1, 2]
    for s, w in zip(at, ("먼저", "좁혀서", "그다음에")):
        assert abs(g.start + s["t"] - _word_t(utts[1], w)) <= 0.5, (s, w)       # 게이트 A15: 낱말 ±0.5초
    assert g.end >= g.start + at[-1]["t"] + 1.0


def test_consecutive_highlight_graphics_merge_into_one_stepped_graphic():
    """AI 가 예전처럼 같은 도식을 highlight 만 바꿔 셋 이어 내도 하나로 합쳐 낱말(각 그래픽의 start_word)에서 바꾼다."""
    utts = _utts()
    tm = TimeMap([Span(0.0, 30.0)])
    base = {"template": "double_diamond", "layout": "split", "title": "더블 다이아몬드",
            "items": ["발견", "정의", "개발", "전달"]}
    raw = [dict(base, start_seg=1, end_seg=1, start_word="먼저", highlight=0),
           dict(base, start_seg=1, end_seg=1, start_word="좁혀서", highlight=1),
           dict(base, start_seg=1, end_seg=2, start_word="그다음에", highlight=2),
           {"template": "keyword", "layout": "overlay", "start_seg": 3, "end_seg": 3, "title": "거꾸로"}]
    plan = normalize_long({"graphics": raw}, utts, [])
    dds = [g for g in plan["graphics"] if g["template"] == "double_diamond"]
    assert len(dds) == 1 and [s["highlight"] for s in dds[0]["steps"]] == [0, 1, 2] and dds[0]["end_seg"] == 2
    timed = {g.template: g for g in time_graphics(plan["graphics"], utts, tm, total=30.0)}
    g = timed["double_diamond"]
    assert abs(g.start + g.data["stepAt"][2]["t"] - _word_t(utts[1], "그다음에")) <= 0.5
    # 항목이 다르면(다른 도식) 합치지 않는다
    other = [dict(base, start_seg=1, end_seg=1, highlight=0), dict(base, start_seg=2, end_seg=2, highlight=1,
                                                                    items=["a", "b", "c", "d"])]
    assert merge_step_runs(other) == 0 and len(other) == 2


def test_step_words_must_move_forward():
    """같은 낱말이 두 번 나오면 앞 단계 뒤의 것 — 단계 시각은 거꾸로 가지 않는다."""
    u = _utt(9, 0.0, "먼저 넓게 그리고 먼저 좁게")
    tm = TimeMap([Span(0.0, 10.0)])
    g = {"start_seg": 9, "end_seg": 9, "steps": [{"word": "넓게", "highlight": 0}, {"word": "먼저", "highlight": 1}]}
    at = step_times(g, [u], tm, 0.0)
    assert [s["index"] for s in at] == [0, 1] and at[1]["t"] > at[0]["t"]
    assert abs(at[1]["t"] - u.words[3].start) < 1e-6


def test_hold_span_blocks_recap_and_callout():
    """홀드(13~29.5초) 안에는 콜아웃·강조·효과음·정리 보드가 없다 — 밖의 같은 것은 그대로."""
    tm = TimeMap([Span(0.0, 120.0)])
    holds = [(13.0, 29.5)]
    moments = [Moment(t=20.0, end=21.0, kind="reveal", intensity=3, callout="거꾸로\n했다", label="고백"),
               Moment(t=60.0, end=61.0, kind="reveal", intensity=3, callout="순서가\n답이다", label="핵심")]
    cues = [{"start": t, "end": t + 1.9, "lines": [[{"text": "말", "start": t, "end": t + 0.5}]]}
            for t in range(0, 120, 2)]
    ed = build_long_edit(timemap=tm, total=120.0, speech_total=120.0, graphics=[], chapters=[], moments=moments,
                         cues=cues, sentence_starts=[0.0, 13.0, 30.0, 60.0, 90.0], holds=holds)

    def inside(t: float) -> bool:
        return 13.0 <= t <= 29.5
    assert not any(inside(c["start"]) or inside(c["end"]) for c in ed.callouts)
    assert any(abs(c["start"] - 60.0) < 2.0 for c in ed.callouts)               # 밖의 콜아웃은 그대로
    assert not any(inside(p["t"]) for p in ed.punches) and not any(inside(x["t"]) for x in ed.sfx)
    assert any(a <= 12.3 and b >= 13.0 for a, b in ed.bgm_dips)                 # 홀드 앞 숨(음악 비움)
    assert ed.stats["holds"] == 1
    # 정리 보드는 홀드를 피한다(자리가 없으면 건너뜀)
    gd = [{"id": "g1", "template": "keyword", "layout": "overlay", "start": 5.0, "end": 9.0, "data": {"title": "순서"}},
          {"id": "g2", "template": "definition", "layout": "split", "start": 10.0, "end": 13.0,
           "data": {"title": "발견", "body": "넓게 보기"}}]
    chapters = [{"start": 0.0, "title": "순서", "number": "01"}, {"start": 30.0, "title": "다음", "number": "02"}]
    recaps = chapter_recaps(gd, chapters, 120.0, avoid=holds)
    assert not any(r["start"] < 29.5 and r["end"] > 13.0 for r in recaps)


def test_pipeline_drops_graphics_inside_holds_but_keeps_script_tags():
    import studio.pipeline as pl
    p = object.__new__(pl.Pipeline)
    p.utts = _utts()
    p.timemap = TimeMap([Span(0.0, 30.0)])
    p.plan_long = {"holds": [{"start_seg": 3, "end_seg": 5, "reason": "고백"}]}
    p.log = (logs := []).append
    gs = [TimedGraphic("g1", "keyword", "overlay", 1.0, 4.0, {}, 5),
          TimedGraphic("g2", "recap", "split", 15.0, 20.0, {}, 4, "auto"),
          TimedGraphic("g3", "keyword", "overlay", 10.0, 16.0, {}, 5),           # 홀드로 들어감 → 앞에서 끊음
          TimedGraphic("g4", "process", "split", 22.0, 27.0, {}, 9, "tag")]     # 대본 태그 → 남고 홀드가 줄어듦
    out = {g.id: g for g in p._respect_holds(gs)}
    assert set(out) == {"g1", "g3", "g4"} and out["g3"].end <= 13.0
    [(a, b)] = p._hold_spans()
    assert a == 13.0 and b <= 22.0 - 0.3 + 1e-6
    assert any("얼굴 홀드" in m for m in logs)


def test_normalize_long_keeps_sequences_rhythm_and_peak():
    utts = _utts()
    raw = {"graphics": [{"template": "photo", "layout": "fullscreen", "start_seg": 1, "end_seg": 1, "image": "a",
                         "title": "", "sequence_id": "q1"}],
           "sequences": [{"id": "q1", "type": "evidence_stack", "start_seg": 1, "end_seg": 2, "claim": "사례가 쌓인다",
                          "shots": [{"seg": 1, "word": "먼저", "show": "스케치"}, {"seg": 2, "word": "결국", "show": "장표"}],
                          "layout": "fullscreen", "audio": "bed", "enter": "on_word", "exit": "on_sentence",
                          "fallback": "single", "priority": 1, "reason": ""},
                         {"id": "", "type": "evidence_stack", "start_seg": 1, "end_seg": 1},      # id 없음 → 버림
                         {"id": "q9", "type": "bogus", "start_seg": 1, "end_seg": 1}],            # 모르는 유형 → 버림
           "rhythm": [{"start_seg": 3, "end_seg": 6, "level": "slow", "reason": "고백"},
                      {"start_seg": 1, "end_seg": 2, "level": "warp"}],
           "peak_seg": 5, "central_question": "왜 순서가 중요할까", "payoff_seg": 6,
           "holds": [{"start_seg": 3, "end_seg": 5, "reason": "고백"}]}
    plan = normalize_long(raw, utts, [])
    assert [q["id"] for q in plan["sequences"]] == ["q1"] and len(plan["sequences"][0]["shots"]) == 2
    assert plan["rhythm"] == [{"start_seg": 3, "end_seg": 6, "level": "slow", "reason": "고백"}]
    assert plan["peak_seg"] == 5 and plan["payoff_seg"] == 6 and plan["central_question"] == "왜 순서가 중요할까"
    assert plan["graphics"][0]["sequence_id"] == "q1" and plan["holds"][0]["end_seg"] == 5
    # 재정규화(plan.json 다시 읽기)에도 그대로
    again = normalize_long(plan, utts, [])
    assert again["sequences"] == plan["sequences"] and again["graphics"][0]["sequence_id"] == "q1"


def test_same_sequence_shots_cut_without_gap():
    from studio.director.plan import resolve_overlaps
    a = TimedGraphic("g1", "photo", "fullscreen", 10.0, 14.0, {"seq_id": "q1"}, 6)
    b = TimedGraphic("g2", "photo", "fullscreen", 11.8, 15.0, {"seq_id": "q1"}, 6)
    c = TimedGraphic("g3", "photo", "fullscreen", 13.6, 17.0, {"seq_id": "q1"}, 6)
    out = resolve_overlaps([a, b, c], total=100.0)
    assert [g.id for g in out] == ["g1", "g2", "g3"]
    assert out[0].end == 11.8 and out[1].end == 13.6                     # 다음 샷이 자른다(간격 0)


def test_sequence_marks_and_high_load_caption_hiding():
    from studio.render.props import hide_over, high_load_spans, mark_sequences
    props = {"graphics": [
        {"id": "g1", "template": "photo", "layout": "fullscreen", "start": 10.0, "end": 11.8, "data": {"seq_id": "q1"}},
        {"id": "g2", "template": "photo", "layout": "fullscreen", "start": 11.8, "end": 13.6, "data": {"seq_id": "q1"}},
        {"id": "g3", "template": "process", "layout": "split", "start": 20.0, "end": 30.0,
         "data": {"items": ["a", "b"], "stepAt": [{"t": 0.5, "index": 0}, {"t": 4.0, "index": 1}]}},
        {"id": "g4", "template": "photo", "layout": "fullscreen", "start": 40.0, "end": 46.0, "data": {"seq_id": "q2"}}]}
    assert mark_sequences(props, {"q1": "evidence_stack", "q2": "document_read"}) == 2
    assert props["graphics"][1]["seq"] == {"id": "q1", "type": "evidence_stack", "index": 1, "count": 2}
    spans = high_load_spans(props, {"q1": "evidence_stack", "q2": "document_read"})
    assert spans == [(20.0, 30.0), (40.0, 46.0)]                          # 단계 도식 + 문서 읽기(증거 쌓기는 아님)
    cues = [{"start": 21.0, "end": 23.0, "lines": []}, {"start": 12.0, "end": 13.0, "lines": []},
            {"start": 45.5, "end": 47.5, "lines": []}]
    assert hide_over(cues, spans) == 1 and cues[0]["hidden"] and not cues[1].get("hidden") and not cues[2].get("hidden")


def test_brief_sequence_schema_is_strict():
    from studio.agents import schemas as S

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node.get("required", [])) == set(node.get("properties", {}))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    for sch in (S.BRIEF, S.EDITOR, S.MOTION):
        walk(sch)
    beat = S.BRIEF["properties"]["beats"]["items"]["properties"]
    assert {"show", "function", "on_screen_text", "sequence_id"} <= set(beat)
    assert set(S.BRIEF["properties"]["sequences"]["items"]["properties"]["type"]["enum"]) == set(S.SEQ_TYPES)
    assert {"holds", "rhythm", "peak_seg"} <= set(S.EDITOR["properties"])


def test_rhythm_levels_cluster_emphasis_in_fast_spans():
    """강조는 고르게 뿌리지 않고 fast 구간에 몰린다(6초 간격) — 선언이 없는 곳은 예전 간격(40초) 그대로."""
    tm = TimeMap([Span(0.0, 200.0)])
    moments = [Moment(t=t, end=t + 1.0, kind="punchline", intensity=2) for t in (20.0, 27.0, 34.0, 120.0, 130.0)]
    cues = [{"start": t, "end": t + 1.9, "lines": [[{"text": "말", "start": t, "end": t + 0.5}]]}
            for t in range(0, 200, 2)]
    kw = dict(timemap=tm, total=200.0, speech_total=200.0, graphics=[], chapters=[], moments=moments, cues=cues,
              sentence_starts=[0.0, 60.0, 120.0])
    plain = build_long_edit(**kw)
    fast = build_long_edit(**kw, rhythm=[(15.0, 40.0, "fast")])
    t_plain = [p["t"] for p in plain.punches]
    t_fast = [p["t"] for p in fast.punches]
    assert 27.0 not in t_plain and 34.0 not in t_plain                    # 40초 간격
    assert {20.0, 27.0, 34.0} <= set(t_fast)                             # fast 구간 안에서는 6초 간격
    assert 130.0 not in t_fast                                           # 밖은 그대로


def test_hold_spans_drop_holds_chained_within_hold_gap():
    """2026-10-03 실제 작업: 홀드 셋이 9~12초 간격으로 이어져 얼굴만 71초(A7 block) — 앞 홀드 끝에서 hold_gap(20초) 안에
    시작하는 홀드는 뺀다. 떨어진 홀드는 그대로."""
    import studio.pipeline as pl
    from studio.edit.grammar import PARAMS
    p = object.__new__(pl.Pipeline)
    say = "그 순간이 지금도 또렷하게 기억이 납니다"                     # 6어절 ≈ 2.7초 + hold_pad → 홀드 최소 3초를 넘긴다
    p.utts = [_utt(0, 0.0, say), _utt(1, 40.0, say), _utt(2, 48.0, say), _utt(3, 100.0, say)]
    p.timemap = TimeMap([Span(0.0, 150.0)])
    p.plan_long = {"holds": [{"start_seg": s, "end_seg": s, "reason": "고백"} for s in (0, 1, 2, 3)]}
    p.log = (logs := []).append
    holds = p._hold_spans()
    assert [round(a) for a, _ in holds] == [0, 40, 100]                # 48초 홀드는 40초 홀드 끝(≈43초)에서 20초 안 → 뺌
    assert len(p._holds_dropped) == 1 and round(p._holds_dropped[0][0]) == 48
    assert all(b2 >= a1 + PARAMS["hold_gap"] for (_, a1), (b2, _) in zip(holds, holds[1:]))
    p._respect_holds([])
    assert any("뺀 홀드 1곳" in m for m in logs)
