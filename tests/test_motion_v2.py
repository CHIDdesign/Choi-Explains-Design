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
from studio.render.props import bridge_fullscreen_gaps, bridge_split_gaps  # noqa: E402

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


def test_removed_v4_parts_are_dropped_and_an_emptied_scene_goes():
    """v5 는 가짜 UI 를 그리지 않는다(렌더러에 panel·chip·bubble·device·iso 가 없다) — 정화에서 빼고, 제목·판만 남으면 장면째 뺀다."""
    title = {"type": "text", "text": "도구들", "x": 30, "y": 22, "size": 9, "at": 0.1}
    plate = {"type": "rect", "x": 50, "y": 60, "w": 60, "h": 40, "at": 0.2}
    chip = {"type": "chip", "x": 72, "y": 30, "at": 1.0, "text": "구역 확인"}
    dots = {"type": "dots", "x": 50, "y": 60, "at": 0.5, "count": 6, "cols": 3}
    assert [e["type"] for e in clean_spec({"elements": [title, chip, dots]}, 8.0)["elements"]] == ["text", "dots"]
    assert clean_spec({"elements": [title, plate, chip]}, 8.0) is None
    assert clean_spec({"elements": [title, plate]}, 8.0) is not None             # 잃은 것이 없으면 디자이너의 장면 그대로
    assert clean_spec({"elements": [title, plate], "lost_parts": True}, 8.0) is None   # 스톡 단계에서 그림을 잃은 장면


def test_l28_caption_zone_text_is_an_error_only_on_the_fullscreen_stage():
    """E2E 10/2: 전면 무대 y=95 글자가 자막 상자와 겹쳤다 — 아래 10% 는 자막 자리."""
    spec = {"bg": "paper", "elements": [
        {"type": "rect", "x": 50, "y": 50, "w": 90, "h": 80, "fill": "white", "at": 0},
        {"type": "text", "x": 50, "y": 30, "size": 6, "text": "제목이 먼저", "at": 0},
        {"type": "text", "x": 50, "y": 95, "size": 5, "text": "그래도 닮았다", "at": 0.6}]}
    c = clean_spec(json.loads(json.dumps(spec)), 4.0)
    full = [i.rule for i in lint.lint(c, 4.0, box=lint.BOXES["fullscreen"])]
    assert "L28_caption_zone" in full
    split = [i.rule for i in lint.lint(c, 4.0, box=lint.BOXES["split"])]
    assert "L28_caption_zone" not in split


def test_lint_scene_cleans_raw_designer_spec_first():
    """2026-10-03 실제 작업: 계획에 저장된 원본 spec 의 dots 요소에 gap·r 이 없어 `lint` 가 KeyError 로 멈췄다 —
    `lint_scene` 은 렌더러가 받을 모양(clean_spec)으로 만든 뒤 린트하고, 원본은 건드리지 않는다."""
    import copy

    import pytest
    from studio.motion import lint as mlint
    raw = {"elements": [
        {"type": "text", "text": "첫 아이디어", "x": 50, "y": 20, "size": 6, "at": 0.0},
        {"type": "dots", "x": 50, "y": 60, "count": 12, "cols": 6, "at": 0.8},        # gap·r 생략(선택 값)
        {"type": "rect", "x": 50, "y": 85, "at": 1.5},                                   # w·h 생략
    ]}
    before = copy.deepcopy(raw)
    with pytest.raises(KeyError):
        mlint.lint(raw, 8.0, [], box=mlint.box_for("fullscreen"))
    issues = mlint.lint_scene(raw, 8.0, [], box=mlint.box_for("fullscreen"))
    assert issues and all(isinstance(i, mlint.Issue) for i in issues)
    assert raw == before                                        # 원본 spec 은 그대로(렌더 직전 time_graphics 가 다시 정리)
    assert [i.rule for i in mlint.lint_scene({"elements": []}, 8.0, [])] == ["L00_empty"]
    assert [i.rule for i in mlint.lint_scene("not a spec", 8.0, [])] == ["L00_empty"]


def test_bridge_fullscreen_gaps_closes_short_gaps_only():
    """2026-10-03: 전면 그래픽 사이 0.2~0.5초 틈의 디졸브 동안 화자가 비쳤다 — 0.5초 이하 틈만 앞 그래픽을 늘려 메운다."""
    gs = [{"id": "g0", "template": "motion", "layout": "fullscreen", "start": 10.0, "end": 14.0},
          {"id": "g1", "template": "card", "layout": "fullscreen", "start": 14.3, "end": 18.0},       # 0.3초 → 메움
          {"id": "g2", "template": "broll", "layout": "fullscreen", "start": 18.9, "end": 22.0},      # 0.9초 → 얼굴로 돌아감
          {"id": "g3", "template": "title", "layout": "fullscreen", "start": 22.2, "end": 25.0},      # 타이틀은 제외
          {"id": "g4", "template": "keyword", "layout": "overlay", "start": 22.1, "end": 24.0}]
    assert bridge_fullscreen_gaps(gs) == 1
    assert gs[0]["end"] == 14.3 and gs[1]["end"] == 18.0 and gs[2]["end"] == 22.0
