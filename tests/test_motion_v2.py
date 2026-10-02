"""WP9 모션 그래픽 v2(docs/upgrade/06 · 06b · 06c): DSL 추가 · 타이밍 린트 · 예제 · 변주 게이트 · 무대 간격 · 글자 층 · QA 스트립."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import gate  # noqa: E402
from studio.director.plan import TimedGraphic  # noqa: E402
from studio.motion import lint  # noqa: E402
from studio.motion.spec import clean_spec  # noqa: E402
from studio.render.props import bridge_split_gaps, stack_avoid_spans  # noqa: E402

EXAMPLES = json.loads((ROOT / "prompts" / "examples" / "motion_examples.json").read_text(encoding="utf-8"))
DURS = {"sketch_first_marks": 6.5, "fixation_two_groups": 12.45, "double_diamond_front": 9.0,
        "gap_under_deadline": 10.17, "no_example_fixates_more": 10.08}


def test_examples_pass_lint_in_both_boxes():
    """06c P0-2: 프롬프트에 붙는 예제는 린트 error 0건(보드 판·전면 무대) — 모션 디자이너가 베끼는 것이니까."""
    assert set(EXAMPLES) == set(DURS)
    for name, spec in EXAMPLES.items():
        c = clean_spec(json.loads(json.dumps(spec)), DURS[name])
        assert c is not None, name
        assert c.get("bg") == "paper", name                     # 한 재질: 크림 종이
        for box in ("split", "fullscreen"):
            errs = lint.errors(lint.lint(c, DURS[name], box=lint.BOXES[box]))
            assert not errs, (name, box, lint.describe(errs))


def test_old_style_scene_fails_lint():
    """10/1 의 모양: 2초 넘어서야 첫 요소, 작은 글자, 상자 구석의 작은 도형 → L01 · L02 · L17 · L18 error."""
    spec = clean_spec({"elements": [
        {"type": "text", "text": "리서치", "x": 30, "y": 50, "size": 3.2, "at": 2.4},
        {"type": "rect", "x": 30, "y": 60, "w": 8, "h": 8, "at": 2.6},
        {"type": "circle", "x": 70, "y": 60, "r": 2, "fill": "accent", "at": 3.0}]}, 8.0)
    spec["elements"][0]["at"] = 2.4                              # stage_first 가 옮긴 것을 되돌려 원래 모양으로
    spec["elements"][1]["at"] = 2.6
    rules = {i.rule for i in lint.errors(lint.lint(spec, 8.0, box=lint.BOXES["split"]))}
    assert {"L01_first_visible", "L02_open_empty", "L17_text_small", "L18_fill"} <= rules, rules
    n = lint.bump_small_text(spec, lint.BOXES["split"][1])
    assert n == 1 and spec["elements"][0]["size"] * lint.BOXES["split"][1] / 100 >= 28


def test_ghost_counts_as_stage_and_late_words():
    """ghost 는 0초부터 자리 표시로 보이니 L01 을 피한다. 말보다 0.5초 넘게 늦게 안착한 글은 L11 late."""
    base = [{"type": "rect", "x": 50, "y": 55, "w": 80, "h": 70, "fill": "faint", "at": 0.1},
            {"type": "text", "text": "예시를 닮는다", "x": 50, "y": 20, "size": 9, "at": 3.0}]
    late = clean_spec({"elements": [dict(e) for e in base]}, 8.0)
    words = [(1.0, 1.4, "예시를"), (1.4, 1.9, "닮는다")]
    rules = {i.rule for i in lint.lint(late, 8.0, words, box=lint.BOXES["split"])}
    assert "L11_late_vs_speech" in rules
    ghost = clean_spec({"elements": [dict(base[1], ghost=True, at=3.0)]}, 8.0)
    assert ghost["elements"][0]["ghost"] and ghost["elements"][0]["at"] == 3.0   # stage_first 가 옮기지 않는다
    assert "L01_first_visible" not in {i.rule for i in lint.lint(ghost, 8.0, box=lint.BOXES["split"])}


def test_clean_spec_v2_fields():
    s = clean_spec({"hero": 1, "layout_intent": "asym", "elements": [
        {"type": "text", "text": "가", "x": 50, "y": 50, "enter": "write", "ease": "settle", "ghost": True},
        {"type": "image", "src": "pixabay:vector:cup", "x": 50, "y": 50, "frame": "print"},
        {"type": "image", "src": "images/a.jpg", "x": 50, "y": 50, "tint": "duotone"},
        {"type": "mark", "kind": "circle", "x": 50, "y": 50, "w": 20, "h": 10},
        {"type": "mark", "kind": "sparkle", "x": 50, "y": 50}]}, 6.0)
    els = s["elements"]
    assert s["hero"] == 1 and s["layout_intent"] == "asym" and len(els) == 4
    assert els[0]["enter"] == "write" and els[0]["ease"] == "settle" and els[0]["ghost"]
    assert els[1]["frame"] == "print" and els[1]["tint"] == "ink"        # 벡터는 기본 잉크 단색(B8)
    assert els[2]["tint"] == "duotone" and els[3]["kind"] == "circle" and els[3]["dur"] == 0.5


def test_b7_variety_flags_repeated_structure():
    gs = [{"template": t, "layout": "split", "start": i * 12.0, "end": i * 12.0 + 6, "data": {}}
          for i, t in enumerate(["double_diamond"] * 3 + ["compare", "keyword", "list", "quote", "process", "stat"])]
    r = gate.b7_variety(gs)
    assert not r.ok and r.measured["max_run"] == 3 and "double_diamond" in r.message
    ok = [{"template": t, "layout": lay, "start": i * 12.0, "end": i * 12.0 + 6, "data": {}} for i, (t, lay) in enumerate(
        [("keyword", "pip"), ("compare", "split"), ("process", "fullscreen"), ("quote", "split"), ("list", "split"),
         ("stat", "pip"), ("definition", "split"), ("timeline", "fullscreen"), ("keyword", "split"), ("matrix", "split")])]
    assert gate.b7_variety(ok).ok
    assert gate.b7_variety(ok[:4]).skipped


def test_bridge_split_gaps_keeps_board_filled():
    """F-7: 판 사이 1초 미만 틈은 앞 그래픽을 늘려 메운다(같은 구성끼리만, 1초 이상이면 화자가 돌아온다)."""
    gs = [{"template": "list", "layout": "split", "start": 10.0, "end": 15.0, "skin": "classic"},
          {"template": "process", "layout": "split", "start": 15.6, "end": 20.0, "skin": "classic"},
          {"template": "compare", "layout": "split", "start": 21.5, "end": 25.0, "skin": "classic"},
          {"template": "keyword", "layout": "split", "start": 25.5, "end": 28.0, "skin": "paper"}]
    assert bridge_split_gaps(gs) == 1
    assert gs[0]["end"] == 15.6 and gs[1]["end"] == 20.0 and gs[2]["end"] == 25.0


def test_stack_avoid_includes_callouts_and_side_media():
    """F-9: 콜아웃·얼굴 옆 사진이 떠 있는 동안 두 층 강조 자막을 쓰지 않는다(같은 순간 글자 층은 둘까지)."""
    props = {"graphics": [{"template": "photo", "layout": "pip", "start": 30.0, "end": 34.0},
                          {"template": "photo", "layout": "fullscreen", "start": 50.0, "end": 54.0}],
             "callouts": [{"start": 40.0, "end": 42.5, "text": "질문"}]}
    spans = stack_avoid_spans(props)
    assert (30.0, 34.0) in spans and (40.0, 42.5) in spans and (50.0, 54.0) not in spans


def test_qa_strip_times_follow_06c():
    from studio.pipeline import qa_strip_times
    g = TimedGraphic(id="g3", template="motion", layout="fullscreen", start=10.0, end=22.45, data={
        "spec": {"elements": [{"type": "dots", "x": 50, "y": 50, "keys": [{"t": 10.3}, {"t": 11.1}]}]}})
    ts = qa_strip_times(g, settle=21.2)
    assert [round(t, 2) for t in ts] == [10.5, round(10 + 0.15 * 12.45, 2), round(10 + 0.4 * 12.45, 2), 21.27, 20.7, 22.05]


def test_qa_actionable_keeps_escalations_out():
    from studio.pipeline import qa_actionable
    issues = [{"action": "escalate_edit", "severity": "high", "scope": "edit", "blocking": True},
              {"action": "shorten_text", "severity": "low"}, {"action": "none", "severity": "high"}]
    assert [i["action"] for i in qa_actionable(issues)] == ["shorten_text"]
