"""디자인 v5 카메라·효과음·음악 비우기 — 화자에게 슬로우 줌 없음, 점프컷은 하드 크롭, 효과음은 그래픽 착지에."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studio.director.plan import ENTER_EXIT  # noqa: E402
from studio.edit.grammar import PARAMS, Moment, auto_motion_sfx, build_long_edit, build_short_edit, directed_sfx  # noqa: E402
from studio.models import Span, TimeMap  # noqa: E402


def _cues(total: float, step: float = 2.0) -> list[dict]:
    out = []
    t = 0.0
    while t < total:
        out.append({"start": t, "end": min(total, t + step - 0.1), "lines": [[{"text": "핵심", "start": t, "end": t + 0.5}]]})
        t += step
    return out


def _long(moments=(), graphics=(), chapters=(), total=120.0, **kw):
    tm = kw.pop("tm", TimeMap([Span(0, total)]))
    return build_long_edit(timemap=tm, total=total, speech_total=total, graphics=list(graphics), chapters=list(chapters),
                           moments=list(moments), cues=_cues(total), sentence_starts=[float(t) for t in range(0, int(total), 10)], **kw)


def test_jump_cut_keeps_scale_and_zoom_is_gentle():
    """2026-11-11 채널 주인: 확대해 잘라 붙이지 말고 젠틀한 줌인. 점프컷에서는 크기 그대로."""
    tm = TimeMap([Span(0, 23), Span(28, 62), Span(72, 130)])        # NG 를 잘라낸 큰 점프 둘(편집 시각 23·57)
    ed = _long(tm=tm, total=115.0, moments=[Moment(t=30.0, end=31.0, kind="reveal", intensity=3)])
    assert ed.punches == []
    assert {s["zoom"] for s in ed.camera} == {1.0, PARAMS["medium"]}
    assert not any(abs(s["start"] - c) < 0.01 for s in ed.camera for c in (23.0, 57.0))   # 점프컷은 프레이밍 경계가 아니다
    assert all(s["zoom"] == s["zoomEnd"] and s["glide"] >= 2.5 for s in ed.camera[1:])   # 크기는 2.5초 넘게 걸쳐서만


def test_callout_lasts_three_seconds_and_keeps_gap():
    moments = [Moment(t=10.0, end=11.0, intensity=2, callout="핵심어"), Moment(t=15.0, end=16.0, intensity=3, callout="너무 가까움"),
               Moment(t=50.0, end=58.0, intensity=2, callout="둘째"), Moment(t=90.0, end=91.0, intensity=1, callout="약함")]
    ed = _long(moments)
    assert [c["text"] for c in ed.callouts] == ["핵심어", "둘째"]
    assert all(c["end"] - c["start"] <= PARAMS["callout_sec"] + 0.1 for c in ed.callouts)
    assert "impact_captions" not in ed.stats and not hasattr(ed, "impact_cues")


def test_auto_sfx_only_on_template_entry_and_lands_on_the_word():
    g = [{"template": "keyword", "layout": "overlay", "start": 10.0, "end": 13.0},
         {"template": "photo", "layout": "fullscreen", "start": 20.0, "end": 24.0},
         {"template": "evidence", "layout": "fullscreen", "start": 30.0, "end": 34.0},
         {"template": "broll", "layout": "fullscreen", "start": 40.0, "end": 44.0},
         {"template": "motion", "layout": "fullscreen", "start": 50.0, "end": 60.0,
          "data": {"spec": {"elements": [{"type": "chip", "at": 2.0}, {"type": "counter", "at": 4.0}]}}}]
    ev = auto_motion_sfx(g)
    assert [(e["category"], e["t"]) for e in ev] == [("pop", 10.0 + ENTER_EXIT["overlay"][0]),
                                                     ("paper_slide", 50.0 + ENTER_EXIT["fullscreen"][0])]


def test_directed_sfx_cap_gap_and_audible_gain():
    g = [{"template": "keyword", "layout": "overlay", "start": 10.0 + i * 2.0, "end": 12.0 + i * 2.0} for i in range(20)]
    out = directed_sfx(g, [], total=120.0, auto=True)
    ts = [x["t"] for x in out]
    assert all(b - a >= PARAMS["sfx_min_gap"] for a, b in zip(ts, ts[1:]))
    assert all(sum(1 for u in ts if t <= u < t + 60) <= 4 for t in ts)
    assert PARAMS["sfx_per_min"] == 4 and PARAMS["sfx_min_gap"] == 4.0
    assert -20 <= min(PARAMS["sfx_gain"].values()) and max(PARAMS["sfx_gain"].values()) <= -10


def test_music_dips_only_at_peak_and_chapter_ends():
    moments = [Moment(t=t, end=t + 1, kind="reveal", intensity=3) for t in (20.0, 60.0, 100.0)]
    ed = _long(moments, chapters=[{"start": 0.0}, {"start": 80.0}], peak=60.0, holds=[(30.0, 40.0)])
    assert ed.bgm_dips == [(59.2, 60.2), (78.2, 79.4)]


def test_highlight_style_call_has_no_punch():
    ed = _long(total=20.0)
    assert ed.punches == [] and ed.transitions == []


def test_short_edit_has_no_glide_on_the_speaker():
    tm = TimeMap([Span(0, 30)])
    moments = [Moment(t=1.5, end=2.2, kind="punchline", intensity=3), Moment(t=12.0, end=13.0, kind="number", intensity=2)]
    ed = build_short_edit(timemap=tm, total=30.0, graphics=[], cues=_cues(30), moments=moments)
    assert ed.punches == [] and all(c["zoom"] == c["zoomEnd"] for c in ed.camera)
    assert not any(s["t"] < 3.0 for s in ed.sfx)


def test_short_auto_sfx_stays_within_the_per_minute_cap():
    tm = TimeMap([Span(0.0, 55.0)])
    gs = [{"start": t, "end": t + 3.0, "template": "keyword", "layout": "overlay"} for t in range(5, 50, 7)]
    ed = build_short_edit(timemap=tm, total=55.0, graphics=gs, cues=_cues(55), moments=[])
    assert 0 < len(ed.sfx) <= PARAMS["sfx_per_min"]


def test_stamp_sound_has_a_landing_after_moving_onto_the_media():
    from studio.edit.grammar import graphic_landings
    from studio.render.props import stamps_onto_media
    host = {"template": "photo", "layout": "fullscreen", "start": 10.0, "end": 20.0, "data": {"image": "a.jpg"}}
    stamp = {"template": "stamp", "layout": "fullscreen", "start": 11.0, "end": 13.0, "data": {"title": "철거"}}
    gs = [host, stamp]
    before = graphic_landings(gs)[1]
    stamps_onto_media(gs)
    assert gs == [host] and any(abs(t - before) <= 0.25 for t in graphic_landings(gs))


def test_stamp_stays_a_graphic_when_the_media_will_not_draw_marks():
    from studio.render.props import stamps_onto_media
    for data in ({"display": "여백"}, {"quote": "인용"}, {"keyword": "핵심"},
                 {"overlays": [{"kind": "circle", "text": "지붕"}, {"kind": "arrow"}]}):
        host = {"template": "evidence", "layout": "fullscreen", "start": 10.0, "end": 20.0, "data": dict(data)}
        stamp = {"template": "stamp", "layout": "fullscreen", "start": 11.0, "end": 13.0, "data": {"title": "철거"}}
        gs = [host, stamp]
        stamps_onto_media(gs)
        assert stamp in gs and not any(o["kind"] == "stamp" for o in host["data"].get("overlays", []))
