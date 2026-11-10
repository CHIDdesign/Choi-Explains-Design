"""단계 그래픽(steps → stepAt)과 얼굴 홀드(docs/upgrade/05_편집_문법_v2.md 8절 1·2번).

10/1 테스트: S122 "먼저 문제를 넓게 탐색하고, 그걸 좁혀서 정의하고, 그다음에 아이디어를 내라고요" — 더블 다이아몬드 그래픽 3개를
이어 붙여 '정의' 강조가 말보다 +3.9초, '아이디어'가 +5.7초 늦었다. S158–S160(고백)은 챕터 정리 보드가 덮었다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studio import gate  # noqa: E402
from studio.director.plan import (TimedGraphic, argument_badges, merge_step_runs, normalize_long, step_times,  # noqa: E402
                                  time_graphics)
from studio.edit.grammar import Moment, build_long_edit  # noqa: E402
from studio.models import Span, TimeMap, Utterance, Word  # noqa: E402


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


def test_card_marks_land_on_spoken_words():
    from studio.motion.card import clean_card
    utts = _utts()
    tm = TimeMap([Span(0.0, 30.0)])
    card = clean_card({"html": '<div class="card"><div class="root">'
                               '<span data-anim="fade-in" data-at-word="좁혀서">가</span>'
                               '<span data-anim="fade-in" data-anim-at="9" data-at-word="그다음에">나</span>'
                               '<span data-anim="fade-in" data-anim-at="1" data-at-word="없는말">다</span>'
                               '</div></div>'}, layout="fullscreen", card_id="c1")
    gr = {"template": "card", "layout": "fullscreen", "start_seg": 1, "end_seg": 1, "start_word": "먼저", "title": "t", "card": card}
    plan = normalize_long({"graphics": [gr]}, utts, [])
    assert "data-at-word" in plan["graphics"][0]["card"]["html"]        # 계획에는 남아 편집이 바뀌면 다시 계산된다
    [g] = time_graphics(plan["graphics"], utts, tm, total=30.0)
    html = g.data["card"]["html"]
    assert "data-at-word" not in html
    ats = [float(x) for x in re.findall(r'data-anim-at="([^"]+)"', html)]
    assert len(ats) == 3 and ats[2] == 1.0, ats                         # 못 찾은 낱말은 디자이너 값 그대로
    for t, w in zip(ats, ("좁혀서", "그다음에")):
        assert abs(g.start + t + 0.5 + 0.2 - _word_t(utts[1], w)) <= 0.05, (t, w)     # data-anim-at 은 시작, 0.5초 뒤 도착
    assert "wordMarks" not in g.data["card"] and len(g.data["wordMarks"]) == 2
    moved = {"start": g.start + 3.0, "data": g.data}                    # 겹침 풀기로 그래픽이 3초 밀리면 게이트 A18 이 잡는다
    assert gate.a18_word_sync([{"start": g.start, "data": g.data}]).ok and not gate.a18_word_sync([moved]).ok


def test_motion_at_word_lands_on_spoken_word():
    utts = _utts()
    tm = TimeMap([Span(0.0, 30.0)])
    spec = {"elements": [
        {"type": "text", "text": "제목", "x": 50, "y": 10, "size": 9, "at": 0.1},
        {"type": "text", "text": "좁힌다", "x": 50, "y": 50, "size": 6, "enter": "fade", "dur": 0.4, "at": 0.5, "out": 2.0,
         "at_word": "좁혀서"},
        {"type": "mark", "kind": "underline", "x": 50, "y": 50, "w": 20, "h": 6, "dur": 0.5, "at": 0.6, "at_word": "좁혀서"},
        {"type": "text", "text": "없음", "x": 50, "y": 70, "size": 6, "at": 3.0, "at_word": "없는말"}]}
    gr = {"template": "motion", "layout": "fullscreen", "start_seg": 1, "end_seg": 1, "start_word": "먼저", "title": "t", "spec": spec}
    plan = normalize_long({"graphics": [gr]}, utts, [])
    logs: list[str] = []
    [g] = time_graphics(plan["graphics"], utts, tm, total=30.0, log=logs.append)
    assert plan["graphics"][0]["spec"]["elements"][1]["at_word"] == "좁혀서"    # 계획에는 남아 편집이 바뀌면 다시 계산된다
    els = g.data["spec"]["elements"]
    assert not any("at_word" in e for e in els)
    word = _word_t(utts[1], "좁혀서")
    assert abs(g.start + els[1]["at"] + 0.4 + 0.2 - word) <= 0.01
    assert abs(g.start + els[2]["at"] + 0.5 + 0.2 - word) <= 0.01               # 같은 낱말에 둘이 착지해도 뒤의 것을 버리지 않는다
    assert abs(els[1]["out"] - els[1]["at"] - 1.5) <= 0.01                      # 퇴장도 같이 밀린다
    assert "wordMarks" not in g.data["spec"]
    assert [m["spoken"] for m in g.data["wordMarks"]] == [pytest.approx(word, abs=0.01)] * 2    # 못 찾은 낱말은 잴 수 없어 빠진다
    synced = gate.a18_word_sync([{"start": g.start, "data": g.data}])
    assert synced.ok and synced.measured["n"] == 2 and synced.measured["max"] == pytest.approx(0.2, abs=0.01)
    assert els[3]["at"] == 3.0 and len(logs) == 1 and "없는말" in logs[0]       # 못 찾으면 디자이너 값 + 로그


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


def test_hold_span_blocks_callout():
    """홀드(13~29.5초) 안에는 콜아웃·효과음이 없다 — 밖의 같은 것은 그대로."""
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
    assert not any(inside(x["t"]) for x in ed.sfx)
    assert ed.bgm_dips == []                                                    # 비우기는 정점·챕터 끝에서만
    assert ed.stats["holds"] == 1


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


def test_hold_trims_graphic_whose_speech_ended_before_it():
    """홀드로 넘어간 것이 퇴장 꼬리·정착 여유뿐인 그래픽(말은 홀드 전에 끝남)은 홀드 앞에서 끊어 남긴다 — 2026-10-05 E2E: 발화 8~9 모션
    장면 6.6초가 홀드로 3초 넘어가 '남는 3.7초 < 60%' 로 통째로 빠지고 아트 디렉터가 고칠 장면이 없었다. end_seg 를 모르면 예전 비율 규칙."""
    import studio.pipeline as pl
    p = object.__new__(pl.Pipeline)
    p.utts = _utts()                       # 발화 2 는 9.0–10.8초, 홀드(발화 3~5)는 13.0초부터
    p.timemap = TimeMap([Span(0.0, 30.0)])
    p.plan_long = {"holds": [{"start_seg": 3, "end_seg": 5, "reason": "고백"}]}
    p.log = (logs := []).append
    gs = [TimedGraphic("g1", "motion", "fullscreen", 9.5, 16.5, {"end_seg": 2}, 5),     # 말은 10.8초에 끝, 꼬리·정착이 홀드로
          TimedGraphic("g2", "motion", "fullscreen", 9.5, 16.5, {}, 5)]                 # 같은 시각이지만 말이 어디까지인지 모름
    out = {g.id: g for g in p._respect_holds(gs)}
    assert "g1" in out and abs(out["g1"].end - 12.8) < 1e-6 and out["g1"].start == 9.5
    assert "g2" not in out                                                              # 남는 3.3초 < 60%·min_dur·0.8 → 예전대로 뺌
    assert any("그래픽 1개를 뺌" in m for m in logs)


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


def test_rhythm_levels_tighten_callout_gap_only_in_fast_spans():
    """콜아웃은 fast 구간에서만 촘촘해진다(15초) — 선언이 없는 곳은 기본 간격(20초) 그대로."""
    tm = TimeMap([Span(0.0, 200.0)])
    moments = [Moment(t=t, end=t + 1.0, kind="punchline", intensity=2, callout="핵심") for t in (20.0, 36.0, 120.0, 136.0)]
    cues = [{"start": t, "end": t + 1.9, "lines": [[{"text": "말", "start": t, "end": t + 0.5}]]}
            for t in range(0, 200, 2)]
    kw = dict(timemap=tm, total=200.0, speech_total=200.0, graphics=[], chapters=[], moments=moments, cues=cues,
              sentence_starts=[0.0, 60.0, 120.0])
    plain = build_long_edit(**kw)
    fast = build_long_edit(**kw, rhythm=[(15.0, 40.0, "fast")])
    t_plain = [round(c["start"] + 0.08, 2) for c in plain.callouts]
    t_fast = [round(c["start"] + 0.08, 2) for c in fast.callouts]
    assert t_plain == [20.0, 120.0]                                      # 20초 간격
    assert t_fast == [20.0, 36.0, 120.0]                                 # fast 구간 안에서만 15초 간격


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


def test_argument_tags_survive_renormalize_and_become_badges():
    utts = _utts()
    raw = {"studio": {"beats": [{"start_seg": 2, "argument_tag": "이유 1"}, {"start_seg": 3, "argument_tag": ""},
                                {"start_seg": 5, "argument_tag": "이유 2 아주아주아주아주아주아주아주아주 긴 태그"}, "bad"]}}
    plan = normalize_long(raw, utts, [])
    assert plan["argument_tags"][0] == {"seg": 2, "tag": "이유 1"} and len(plan["argument_tags"]) == 2
    assert len(plan["argument_tags"][1]["tag"]) == 18
    assert normalize_long(plan, utts, [])["argument_tags"] == plan["argument_tags"]      # 저장된 계획을 다시 정규화해도
    seg_t = {1: (10.0, 14.0), 2: (50.0, 54.0), 3: (120.0, 124.0), 4: (216.0, 220.0), 5: (400.0, 404.0)}
    tags = [{"seg": s, "tag": f"이유 {s}"} for s in (1, 2, 3, 4, 5)]
    out = argument_badges(tags, seg_t, [(118.0, 125.0), (398.0, 430.0)], 500.0)
    assert [(g.template, g.layout, g.data) for g in out[:1]] == [("lower_third", "overlay", {"slot": "badge", "title": "이유 1"})]
    # 2 는 앞 배지에서 90초 안 · 3 은 전면 그래픽 뒤로 밀림 · 4 는 밀린 3 에서 90초 뒤 · 5 는 12초 넘게 밀려야 해서 뺌
    assert [g.start for g in out] == [10.0, 125.3, 216.0] and all(abs(g.end - g.start - 3.0) < 1e-6 for g in out)
