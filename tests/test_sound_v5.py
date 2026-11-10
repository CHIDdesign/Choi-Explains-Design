"""디자인 v5 소리·전환: 곡 옆 크레딧 · 큐의 곡 위치 · 끊는 큐 · 대사 앞 침묵 · 오림 착지 · 찢기 · 드문 세로 밀기(reports/몰입 배경음악과 전환 효과음.md)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.edit.grammar import PARAMS, auto_motion_sfx, cutout_landings, directed_sfx  # noqa: E402
from studio.media import mix as M  # noqa: E402
from studio.render.remotion import find_node  # noqa: E402
from studio.sound import cues as C  # noqa: E402
from studio.sound.tracks import sidecar  # noqa: E402
from studio.stock.openverse import Openverse  # noqa: E402


def _seg_t(n=40, dur=5.0):
    return {i: (i * dur, i * dur + dur - 0.6) for i in range(n)}


# ---- 곡 옆 크레딧 ----
def test_sidecar_reads_class_and_credit(tmp_path):
    t = tmp_path / "wildflowers.mp3"
    assert sidecar(t) is None                                                       # 없으면 None — 곡을 빼지 않고 리포트가 경고한다
    (tmp_path / "wildflowers.txt").write_text("A\n'Wildflowers' by Scott Buckley - released under CC-BY 4.0.\nwww.scottbuckley.com.au\n", encoding="utf-8-sig")
    assert sidecar(t) == ("A", "'Wildflowers' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au")
    (tmp_path / "wildflowers.txt").write_bytes("크레딧만 붙여 넣음".encode("cp949"))
    assert sidecar(t) == ("own", "크레딧만 붙여 넣음")


def test_mix_all_carries_credit_for_long_and_shorts(tmp_path, monkeypatch):
    """곡 옆 크레딧이 롱폼·숏폼 양쪽의 bgm_title·등급으로 간다. 없으면 곡을 빼지 않고 경고 표시."""
    from types import SimpleNamespace

    from studio import pipeline as P
    from studio.edit.grammar import EditDecisions
    from studio.util import CancelToken
    monkeypatch.setattr(P, "mix", lambda *a, **k: {})
    monkeypatch.setattr(P, "track_features", lambda *a, **k: {})
    track = tmp_path / "곡.mp3"
    track.write_bytes(b"x")

    def run():
        pl = P.Pipeline.__new__(P.Pipeline)
        pl.spec, pl.work, pl.cancel, pl.log = SimpleNamespace(sfx=False, music=True, bgm=str(track)), tmp_path, CancelToken(), lambda s: None
        pl.ff = SimpleNamespace(ffmpeg="ffmpeg")
        pl.masters = [{"short": s, "total": 10.0, "edit": EditDecisions(), "voice": "v.wav"} for s in (False, True)]
        pl._mix_all()
        return pl.masters
    no = run()
    assert [(m["bgm_title"], m["music_license"], m["music_no_credit"]) for m in no] == [("곡.mp3", "own", True)] * 2
    (tmp_path / "곡.txt").write_text("A\n'곡' by 작가 - CC-BY 4.0", encoding="utf-8")
    assert [(m["bgm_title"], m["music_license"], m["music_no_credit"]) for m in run()] == [("'곡' by 작가 - CC-BY 4.0", "A", False)] * 2


# ---- 큐 시트 ----
def test_clean_music_keeps_stop_track_from_and_lead():
    raw = {"cues": [{"id": "m1", "start_seg": 1, "end_seg": 9, "exit": "stop", "track_from": 42.5, "why_in": "a", "why_out": "b"},
                    {"id": "m2", "start_seg": 12, "end_seg": 20, "exit": "bad", "track_from": "x"}],
           "silences": [{"start_seg": 21, "end_seg": 22, "lead_s": 9}, {"start_seg": 25, "end_seg": 26}]}
    m = C.clean_music(raw, list(range(40)))
    assert (m["cues"][0]["exit"], m["cues"][0]["track_from"]) == ("stop", 42.5)
    assert (m["cues"][1]["exit"], m["cues"][1]["track_from"]) == ("fade_bar", -1.0)
    assert [x["lead_s"] for x in m["silences"]] == [2.5, 0.0]
    assert C.clean_music(m, list(range(40))) == m


def test_silence_opens_before_the_line_and_stop_is_not_joined():
    m = C.clean_music({"cues": [{"id": "m1", "start_seg": 0, "end_seg": 10, "exit": "stop", "why_in": "a", "why_out": "b"},
                                {"id": "m2", "start_seg": 12, "end_seg": 18, "why_in": "a", "why_out": "b"}],
                       "silences": [{"start_seg": 10, "end_seg": 10, "lead_s": 1.2}]}, list(range(40)))
    cues, sil = C.resolve(m, _seg_t(), 200.0)
    assert cues[0].end == round(50.0 - 1.2, 2) and sil[0][0] == round(50.0 - 1.2, 2)     # 대사 첫 낱말 1.2초 앞에서 음악이 없다
    assert cues[0].exit == "stop"
    # 4초 미만 틈 잇기가 끊는 큐를 이어 붙이지 않는다
    close = C.clean_music({"cues": [{"id": "m1", "start_seg": 0, "end_seg": 4, "exit": "stop", "why_in": "a", "why_out": "b"},
                                    {"id": "m2", "start_seg": 5, "end_seg": 9, "why_in": "a", "why_out": "b"}]}, list(range(40)))
    q, _ = C.resolve(close, {i: (i * 5.0, i * 5.0 + 3.0) for i in range(40)}, 200.0)
    assert q[0].exit == "stop" and q[0].end < q[1].start


def test_only_last_piece_of_a_cut_stop_cue_stops():
    m = C.clean_music({"cues": [{"id": "m1", "start_seg": 0, "end_seg": 12, "exit": "stop", "track_from": 30, "why_in": "a", "why_out": "b"}]}, list(range(40)))
    q, _ = C.resolve(m, _seg_t(), 200.0, holds=[(25.0, 32.0)])
    assert [x.exit for x in q] == ["fade_bar", "stop"] and [x.track_from for x in q] == [30.0, -1.0]


def test_stop_window_is_a_short_tail():
    w = C.cue_windows([C.MusicCue("m", 0.0, 20.0, "bed", 1, "fade_in", "stop")], 25.0)
    assert w[1960] == 1.0 and 0.0 < w[1990] < 1.0 and w[2010] == 0.0


def test_align_stop_puts_peak_on_the_stop():
    q = {"start": 10.0, "end": 40.0}
    C.align_stop(q, 90.0)
    assert q == {"start": 10.0, "end": 40.0, "track_from": 60.0}
    short = {"start": 10.0, "end": 40.0}
    C.align_stop(short, 20.0)
    assert short == {"start": 20.0, "end": 40.0, "track_from": 0.0}                 # 곡이 모자라면 큐를 늦게 시작(반복 없음)
    flat = {"start": 10.0, "end": 40.0}
    C.align_stop(flat, 5.0)
    assert flat == {"start": 10.0, "end": 40.0}                                     # 쌓임이 없는 곡은 건드리지 않는다


def test_loudness_curve_and_quietest_before():
    sr = 1000
    x = np.ones(sr * 22, np.float32) * 0.1
    x[sr * 10:sr * 15] = 0.8
    curve = C.loudness_curve(x, sr)
    assert len(curve) == 4 and curve.index(max(curve)) == 2 and C.peak_time(curve) == 15.0
    y = np.ones(sr * 5, np.float32)
    y[int(4.9 * sr):int(4.92 * sr)] = 0.0
    assert -0.1 < C.quietest_before(y, sr, 5.0) < -0.07
    assert C.quietest_before(y, sr, 0.0) == 0.0


def _source(monkeypatch, secs: float, plan: M.BgmPlan, n_total: int):
    """곡 = 샘플 값이 곧 그 시각(초)인 램프 — 조각을 보면 곡의 어디인지 바로 안다."""
    ramp = np.linspace(0, secs, int(secs * M.SR), endpoint=False, dtype=np.float32)
    monkeypatch.setattr(M, "decode", lambda ff, path, start=0.0, duration=None: np.stack([ramp, ramp], axis=1)[int(start * M.SR):])
    return M._BgmSource(None, plan, n_total)


def test_track_from_places_each_cue_in_the_track(monkeypatch):
    plan = M.BgmPlan(path="x", lufs=-14.0, cues=[
        {"id": "m1", "start": 2.0, "end": 12.0, "track_from": 30.0, "exit": "fade_bar"},
        {"id": "m2", "start": 20.0, "end": 25.0, "track_from": -1.0, "exit": "fade_bar"}])
    src = _source(monkeypatch, 60.0, plan, 40 * M.SR)
    assert [a for a, _, _ in src.pieces] == [2 * M.SR, 20 * M.SR]
    assert abs(src.get(2 * M.SR, 10)[0, 0] - 30.0) < 0.01
    assert abs(src.get(20 * M.SR, 10)[0, 0] - 40.0) < 0.01                          # track_from 없는 큐는 앞 큐에 이어서


def test_track_never_repeats_when_too_short(monkeypatch):
    plan = M.BgmPlan(path="x", lufs=-14.0, cues=[{"id": "m1", "start": 0.0, "end": 30.0, "track_from": 50.0, "exit": "fade_bar"},
                                                 {"id": "m2", "start": 40.0, "end": 50.0, "track_from": -1.0, "exit": "fade_bar"}])
    src = _source(monkeypatch, 60.0, plan, 60 * M.SR)
    assert len(src.pieces) == 1 and src.pieces[0][1] == 10 * M.SR                   # 곡 끝까지 10초만, 다음 큐는 곡이 없어 소리 없음


def test_stop_cue_gets_peak_and_snaps_earlier(monkeypatch):
    secs, sr = 60, M.SR
    x = np.ones(secs * sr, np.float32) * 0.05
    x[40 * sr:45 * sr] = 0.5                                                        # 정점 = 45초에 끝나는 칸
    x[int(44.92 * sr):int(44.94 * sr)] = 0.0                                        # 멈춤 80ms 앞이 가장 조용하다
    monkeypatch.setattr(M, "decode", lambda ff, path, start=0.0, duration=None: np.stack([x, x], axis=1)[int(start * sr):])
    plan = M.BgmPlan(path="x", lufs=-14.0, cues=[{"id": "m1", "start": 5.0, "end": 25.0, "exit": "stop", "track_from": -1.0}])
    src = M._BgmSource(None, plan, 70 * sr)
    q = plan.cues[0]
    assert q["track_from"] == 25.0 and q["start"] == 5.0
    assert 24.9 <= q["end"] <= 24.94                                                # 큐를 고친 값이 그대로 믹스 곡선·리포트로 간다
    assert src.offsets[0] == 25 * sr


def test_dip_fade_does_not_eat_the_build_of_a_stop():
    total = 30.0
    act = np.ones(int(total * 100) + 1, np.float32)
    plan = M.BgmPlan(path="x", under_db=-20.0, gap_db=-12.0, swell_db=-8.0, dips=[(19.5, 20.5)],
                     cues=[{"id": "m", "start": 0.0, "end": 20.0, "exit": "stop", "role": "bed", "entry": "fade_in"}])
    g = M.bgm_gain_curve(act, plan, total)
    assert abs(g[1900] + 20.0) < 1.0                                                # 멈춤 1초 앞에도 제 레벨(비우기 페이드 없음)
    assert g[2100] < -50.0


def test_sfx_without_peak_lands_on_the_real_peak(tmp_path):
    from studio.media.ffmpeg import FFmpeg
    import shutil
    import wave
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg 없음")
    sr = M.SR

    def wav(path, x):
        with wave.open(str(path), "wb") as w:
            w.setnchannels(2), w.setsampwidth(2), w.setframerate(sr)
            w.writeframes((np.repeat(x[:, None], 2, axis=1) * 32767).astype("<i2").tobytes())
    x = np.zeros(sr, np.float32)
    x[int(0.3 * sr)] = 0.9
    wav(tmp_path / "s.wav", x)
    wav(tmp_path / "v.wav", np.zeros(sr * 3, np.float32))
    M.mix(FFmpeg(), tmp_path / "v.wav", tmp_path / "o.wav", total=3.0, sfx=[M.SfxCue(t=2.0, path=str(tmp_path / "s.wav"), gain_db=0.0)], bgm=None)
    with wave.open(str(tmp_path / "o.wav"), "rb") as r:
        out = np.frombuffer(r.readframes(r.getnframes()), "<i2")[::2]
    assert abs(int(np.abs(out).argmax()) - 2 * sr) < sr // 100


# ---- 효과음 ----
def test_each_cutout_lands_with_one_thud_past_the_caps():
    g = [{"template": "cutout_stack", "layout": "overlay", "start": 10.0, "end": 16.0,
          "data": {"cutouts": [{"at": 0.0}, {"at": 0.8}, {"at": 1.6}, {"at": 2.4}, {"at": 3.2}, {"at": 4.0}]}}]
    assert cutout_landings(g[0])[0] == 10.0 + 0.25
    keys = [{"template": "keyword", "layout": "overlay", "start": 3.5 + i * 4.5, "end": 5.0 + i * 4.5} for i in range(10)]
    out = directed_sfx(g + keys, [], total=120.0, auto=True)
    thuds = [e for e in out if e.get("thud")]
    assert len(thuds) == 6 and {e["category"] for e in thuds} == {"paper_place"}    # 4초 간격·분당 4개의 예외
    rest = [e["t"] for e in out if not e.get("thud")]
    assert all(b - a >= PARAMS["sfx_min_gap"] for a, b in zip(rest, rest[1:]))
    assert all(e["gain_db"] == PARAMS["sfx_gain"]["paper_place"] for e in thuds)


def test_cutout_overlay_on_a_photo_and_even_spacing():
    g = {"template": "evidence", "layout": "fullscreen", "start": 20.0, "end": 26.0, "data": {"overlays": [{"kind": "cutout", "at": 1.5}, {"kind": "circle", "at": 1.0}]}}
    assert [e["t"] for e in auto_motion_sfx([g])] == [21.75]
    even = {"template": "cutout_stack", "start": 0.0, "end": 10.0, "data": {"cutouts": [{}, {}]}}
    assert cutout_landings(even) == pytest.approx([0.25, 3.85])                                    # 렌더러와 같은 고른 간격(0.72 × 길이 ÷ 장 수)


def test_title_rip_sounds_while_it_tears():
    out = directed_sfx([{"template": "title", "layout": "fullscreen", "start": 20.0, "end": 23.0}], [], total=120.0, auto=True)
    assert [(e["category"], e["t"]) for e in out] == [("paper_tear", 20.2)]
    assert PARAMS["sfx_gain"]["paper_tear"] > -25


def test_paper_and_click_gains_are_raised_from_the_report():
    g = PARAMS["sfx_gain"]
    assert g["paper"] - g["pop"] >= 6 and g["click"] - g["pop"] >= 7


def test_manifest_licences():
    m = json.loads((ROOT / "assets" / "sound_manifest.json").read_text(encoding="utf-8"))
    by = {e["id"]: e for e in m["sfx"]}
    for i in ("sub_drop_1", "sub_drop_2", "reverse_cymbal_1", "reverse_cymbal_3"):
        assert by[i]["enabled"] is False and by[i]["commercial_ok"] is False        # 등급 ? 는 켜지 않는다
    assert not [e["id"] for e in m["sfx"] if e.get("enabled") is not False and (e.get("license") or {}).get("class") in ("?", "", None, "D", "X")]
    fresh = [e for e in m["sfx"] if (e.get("license") or {}).get("type") == "CC0 1.0"]
    assert {e["category"] for e in fresh} >= {"paper_tear", "stamp", "tape", "paper_place", "paper_slide", "page_turn", "paper"}
    assert all(e["page"].startswith("https://freesound.org/") and e["url"].startswith("https://") and e["enabled"] and e["license"]["class"] == "A" for e in fresh)
    assert "people/Geoff-Bremner-Audio/sounds/795801" not in json.dumps(m)           # Openverse 는 cc0 라 했지만 원문은 CC BY-NC


def test_openverse_audio_keeps_short_cc0_only():
    results = [{"title": "tear", "url": "https://a/1.mp3", "foreign_landing_url": "https://p/1", "duration": 800, "license": "cc0", "license_version": "1.0", "source": "freesound"},
               {"title": "long", "url": "https://a/2.mp3", "foreign_landing_url": "https://p/2", "duration": 90000, "license": "cc0"},
               {"title": "nc", "url": "https://a/3.mp3", "foreign_landing_url": "https://p/3", "duration": 500, "license": "by-nc", "license_version": "4.0"},
               {"title": "nd", "url": "https://a/4.mp3", "foreign_landing_url": "https://p/4", "duration": 500, "license": "by-nd"}]
    ov = Openverse()
    seen = {}
    ov._get_json = lambda url, params, headers=None: (seen.update(params), {"results": results})[1]
    out = ov.search_audio("paper tear")
    assert seen["license"] == "cc0" and [r["title"] for r in out] == ["tear"]
    assert out[0]["duration"] == 0.8 and out[0]["license"] == "CC0" and out[0]["page"] == "https://p/1"


# ---- 전환 ----
def _pairs(expr: str):
    try:
        node = find_node()
    except Exception:
        pytest.skip("node 없음")
    url = (ROOT / "renderer" / "src" / "lib" / "fullPairs.ts").as_uri()
    r = subprocess.run([node, "--experimental-strip-types", "--input-type=module", "-e", f"import * as c from '{url}'; console.log(JSON.stringify({expr}))"],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        pytest.skip(f"node 가 TS 를 못 읽음: {r.stderr[:80]}")
    return json.loads(r.stdout)


def _g(i, s, e, cover=True, still=False, held=""):
    return {"id": i, "start": s, "end": e, "cover": cover, "still": still, "held": held}


def test_push_only_between_abutting_stills_and_rare():
    gs = [_g("a", 0, 4, still=True), _g("b", 4, 8, still=True), _g("c", 8.2, 12, still=True), _g("gap", 20, 24, still=True),
          _g("d", 60, 64, still=True), _g("e", 64.3, 68, still=True), _g("f", 110, 114, still=True), _g("g", 114, 118, still=True),
          _g("h", 160, 164, still=True), _g("i", 164, 168, still=True)]
    out = _pairs(f"c.pushPairs({json.dumps(gs)}, 0.5)")
    assert out == {"b": "a", "e": "d", "g": "f"}                                    # 40초 간격, 영상당 3번까지
    film = [_g("a", 0, 4, still=True), _g("b", 4, 8)]
    assert _pairs(f"c.pushPairs({json.dumps(film)}, 0.5)") == {}                     # 영상·도식이 끼면 하드 컷
    over = [_g("a", 0, 4, still=True), _g("lt", 3, 5, cover=False), _g("b", 4, 8, still=True)]
    assert _pairs(f"c.pushPairs({json.dumps(over)}, 0.5)") == {"b": "a"}
    host = [_g("a", 0, 4, still=True), _g("b", 9, 12, still=True)]
    assert _pairs(f"c.pushPairs({json.dumps(host)}, 0.5)") == {}                    # 사이에 화자가 있으면 하드 컷


def test_paper_swap_needs_the_same_object_and_abutting():
    gs = [_g("a", 0, 4, held="process:공정"), _g("b", 4, 8, held="process:공정"), _g("c", 8, 12, held="process:공정"),
          _g("d", 12, 16, held="process:다른 것"), _g("e", 30, 34, held="process:다른 것"), _g("f", 34, 38, held="")]
    assert _pairs(f"c.paperSwaps({json.dumps(gs)}, 0.5)") == {"b": {"paper": "newsprint", "first": "a"}, "c": {"paper": "memo", "first": "a"}}
