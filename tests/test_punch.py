"""⚡ 펀치 구간 — 편집 감독의 energy_spans 안에서만 하드 펀치인·휩·임팩트를 허용하고, 그 밖은 젠틀 규칙 그대로."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studio.agents import schemas as S  # noqa: E402
from studio.agents.studio import merge_plan  # noqa: E402
from studio.edit.grammar import PARAMS, PUNCH, Moment, build_long_edit, build_short_edit, in_spans  # noqa: E402
from studio.models import Span, TimeMap  # noqa: E402
from studio.pipeline import Pipeline  # noqa: E402


def _cues(total: float, step: float = 2.0) -> list[dict]:
    out = []
    t = 0.0
    while t < total:
        out.append({"start": t, "end": min(total, t + step - 0.1), "lines": [[{"text": "핵심", "start": t, "end": t + 0.5}]]})
        t += step
    return out


def test_in_spans():
    assert in_spans(5, [(0, 10)]) and not in_spans(11, [(0, 10)]) and not in_spans(5, None) and not in_spans(5, [])


def test_long_edit_punch_only_inside_spans():
    tm = TimeMap([Span(0, 120)])
    moments = [Moment(t=10.0, end=11.0, kind="punchline", intensity=2),          # 밖: 글라이드
               Moment(t=30.0, end=31.0, kind="reveal", intensity=3),             # 안: 하드 펀치인
               Moment(t=33.0, end=34.0, kind="number", intensity=2),             # 안이지만 6초 안 → 탈락
               Moment(t=37.0, end=38.5, kind="punchline", intensity=1),          # 안: 강도 1 도 허용
               Moment(t=80.0, end=81.0, kind="punchline", intensity=2)]          # 밖: 40초 규칙으로 글라이드 하나 더
    graphics = [{"id": "g0", "template": "photo", "layout": "fullscreen", "start": 44.0, "end": 48.0}]
    ed = build_long_edit(timemap=tm, total=125.0, speech_total=120.0, graphics=graphics, chapters=[], moments=moments,
                         cues=_cues(120), sentence_starts=[0.0, 30.0, 60.0, 90.0], punch_spans=[(25.0, 50.0)])
    by_t = {p["t"]: p for p in ed.punches}
    assert by_t[10.0]["style"] == "glide" and by_t[10.0]["amount"] == PARAMS["punch"][2]
    assert by_t[30.0]["style"] == "cut" and by_t[30.0]["amount"] == PUNCH["punch"][3]
    assert by_t[30.0]["end"] - 30.0 <= PUNCH["punch_max"] + 1e-6                 # 당긴 채 오래 두지 않는다
    assert 33.0 not in by_t and by_t[37.0]["style"] == "cut" and by_t[37.0]["amount"] == PUNCH["punch"][1]
    assert by_t[80.0]["style"] == "glide"
    assert ed.stats["punch_spans"] == 1 and ed.stats["hot_punches"] == 2
    # 효과음(문구 팔레트 04c 6절): 펀치 구간 안은 도장(강도 3)·종이 놓기(강도 1), 밖의 강조 글라이드는 소리 없음.
    # 말 시작 0.15초 안이면 앞으로 당긴다
    def near(t):
        return next((s["category"] for s in ed.sfx if abs(s["t"] - t) <= 0.16), None)
    assert near(30.0) == "stamp" and near(37.0) == "paper_place" and near(10.0) is None
    # 전환: 펀치 구간 안의 사진 진입은 휩
    tx = {t["t"]: t for t in ed.transitions}
    assert tx[44.0]["type"] == "whip" and tx[44.0]["dir"] in ("left", "right")


def test_no_punch_over_split_panel_even_when_hot():
    tm = TimeMap([Span(0, 60)])
    moments = [Moment(t=20.0, end=21.0, kind="number", intensity=3), Moment(t=40.0, end=41.0, kind="reveal", intensity=3)]
    graphics = [{"id": "g0", "template": "definition", "layout": "split", "start": 18.0, "end": 24.0}]
    ed = build_long_edit(timemap=tm, total=60.0, speech_total=60.0, graphics=graphics, chapters=[], moments=moments,
                         cues=_cues(60), sentence_starts=[0.0, 30.0], punch_spans=[(15.0, 45.0)])
    assert [p["t"] for p in ed.punches] == [40.0] and ed.punches[0]["style"] == "cut"


def test_long_edit_without_spans_is_unchanged():
    tm = TimeMap([Span(0, 60)])
    moments = [Moment(t=10.0, end=11.0, kind="punchline", intensity=3), Moment(t=40.0, end=41.0, kind="reveal", intensity=1)]
    ed = build_long_edit(timemap=tm, total=60.0, speech_total=60.0, graphics=[], chapters=[], moments=moments,
                         cues=_cues(60), sentence_starts=[0.0, 30.0])
    assert [p["style"] for p in ed.punches] == ["glide"] and ed.stats["hot_punches"] == 0


def test_short_edit_hook_is_hot():
    tm = TimeMap([Span(0, 30)])
    moments = [Moment(t=1.5, end=2.2, kind="punchline", intensity=3), Moment(t=12.0, end=13.0, kind="number", intensity=2)]
    ed = build_short_edit(timemap=tm, total=30.0, graphics=[], cues=_cues(30), moments=moments)
    by_t = {p["t"]: p for p in ed.punches}
    assert by_t[1.5]["style"] == "cut" and by_t[1.5]["amount"] == PUNCH["punch"][3]     # 훅(첫 3초)
    assert by_t[12.0]["style"] == "glide"
    assert not any(s["t"] < 3.0 for s in ed.sfx)                                         # 훅 문장 위에는 효과음 없음
    ed2 = build_short_edit(timemap=tm, total=30.0, graphics=[], cues=_cues(30), moments=moments, hook=0.0)
    assert all(p["style"] == "glide" for p in ed2.punches)


def test_pipeline_punch_spans_budget_and_segment_filter():
    class P:
        plan_long = {"energy_spans": [{"start_seg": 0, "end_seg": 1, "reason": "훅"},
                                      {"start_seg": 5, "end_seg": 9, "reason": "절정"},
                                      {"start_seg": 3, "end_seg": 3, "reason": "짧음"}]}

    seg_t = {i: (i * 10.0, i * 10.0 + 9.0) for i in range(10)}      # 총 99초 → 예산 24.75초
    spans = Pipeline._punch_spans(P(), seg_t)
    assert spans[0] == (0.0, 19.0)                                  # 첫 구간 그대로
    assert spans[1][0] == 50.0 and abs((spans[1][1] - 50.0) - (24.75 - 19.0)) < 1e-6   # 예산만큼 잘림
    assert len(spans) == 2                                          # 예산 소진 뒤는 버림
    only = Pipeline._punch_spans(P(), seg_t, segs={5, 6})            # 숏폼: 그 숏폼의 발화만
    assert only == [(50.0, 69.0)]


def test_merge_plan_keeps_energy_spans_and_schema():
    raw, _ = merge_plan({"editor": {"drop": [], "moments": [], "pacing_notes": "",
                                    "energy_spans": [{"start_seg": 2, "end_seg": 4, "reason": "훅"}, "bad"]}})
    assert raw["energy_spans"] == [{"start_seg": 2, "end_seg": 4, "reason": "훅"}]
    assert "energy_spans" in S.EDITOR["properties"]
