"""오토파일럿 엔진 단위 테스트: 편집 문법·색보정 LUT·믹스·사운드 라이브러리(네트워크 없이)."""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.edit.grammar import PARAMS, Moment, build_long_edit, build_short_edit, camera_plan  # noqa: E402
from studio.models import Span, TimeMap  # noqa: E402


def _cue(a: float, b: float, text: str) -> dict:
    return {"start": a, "end": b, "lines": [[{"text": w, "start": a, "end": b} for w in text.split()]]}


def _long_case():
    tm = TimeMap([Span(0, 20), Span(22, 60), Span(61, 120), Span(125, 200)])
    total = tm.duration
    graphics = [
        {"template": "title", "layout": "fullscreen", "start": 14.0, "end": 17.4, "data": {}},
        {"template": "motion", "layout": "fullscreen", "start": 40.0, "end": 48.0, "data": {}},
        {"template": "broll", "layout": "fullscreen", "start": 70.0, "end": 75.0, "data": {}},
        {"template": "chapter", "layout": "fullscreen", "start": 100.0, "end": 102.6, "data": {}},
        {"template": "list", "layout": "split", "start": 130.0, "end": 140.0, "data": {"items": ["가", "나", "다"]}},
    ]
    chapters = [{"start": 0.0, "title": "들어가며", "number": "01"}, {"start": 100.1, "title": "원리", "number": "02"}]
    moments = [Moment(t=30.0, end=33.0, kind="punchline", intensity=3, word="질문", callout="좋은 디자인은\n질문에서",
                      label="핵심"),
               Moment(t=31.0, end=32.0, kind="reveal", intensity=2),            # 너무 가까움 → 버림
               Moment(t=150.0, end=153.0, kind="conclusion", intensity=2, callout=""),
               Moment(t=44.0, end=46.0, kind="punchline", intensity=3, callout="그래픽 위")]  # 풀스크린 그래픽 위 → 버림
    cues = [_cue(t, t + 2.5, "좋은 디자인은 질문에서 시작합니다") for t in range(1, int(total) - 3, 3)]
    face = [{"t": float(t), "x": 0.35, "y": 0.4, "s": 0.3} for t in range(0, int(total))]
    ed = build_long_edit(timemap=tm, total=total + 10, speech_total=total, graphics=graphics, chapters=chapters,
                         moments=moments, cues=cues, sentence_starts=[float(t) for t in range(0, int(total), 7)],
                         text_graphic_spans=[(130.0, 140.0)], face=face)
    return tm, total, ed


def test_camera_alternates_and_never_flickers():
    tm, total, ed = _long_case()
    zooms = [c["zoom"] for c in ed.camera]
    assert set(zooms) == {PARAMS["wide"], PARAMS["medium"]}
    assert all(c["end"] - c["start"] >= 0.99 for c in ed.camera[:-1])
    # 같은 프레이밍이 20초 넘게 이어지지 않는다(셜록현준: 5~8초마다 앵글 교차)
    assert max(c["end"] - c["start"] for c in ed.camera) <= 20.0
    # 긴 샷은 느린 푸시인(최대 6%)
    assert all(c["zoomEnd"] / c["zoom"] - 1 <= PARAMS["push_max"] + 1e-6 for c in ed.camera)


def test_transitions_are_restrained():
    _, _, ed = _long_case()
    types = [t["type"] for t in ed.transitions]
    assert "wipe" in types and "leak" in types          # 챕터·타이틀은 항상
    minor = [t for t in ed.transitions if t["type"] not in ("wipe", "leak")]
    for a, b in zip(minor, minor[1:]):
        assert b["t"] - a["t"] >= PARAMS["tx_min_gap"]  # 하드컷 ≥ 90%
    assert all(0.2 <= t["dur"] <= 1.0 for t in ed.transitions)


def test_punch_callout_and_sfx_rules():
    _, _, ed = _long_case()
    ts = [p["t"] for p in ed.punches]
    assert 30.0 in ts and 31.0 not in ts and 44.0 not in ts     # 간격·풀스크린 그래픽 규칙
    assert ed.punches[0]["amount"] == PARAMS["punch"][3]
    c = ed.callouts[0]
    assert c["text"] == "좋은 디자인은\n질문에서" and c["highlight"] == "질문" and c["label"] == "핵심"
    assert c["side"] == "right"                                  # 얼굴이 왼쪽(x=0.35) → 오른쪽 빈 공간
    assert 2.0 <= c["end"] - c["start"] <= 4.5
    non_click = [s for s in ed.sfx if s["category"] not in ("click", "riser")]  # riser 는 챕터 whoosh 와 짝
    for a, b in zip(non_click, non_click[1:]):
        assert b["t"] - a["t"] >= PARAMS["sfx_min_gap"] - 1e-6
    assert not any(s["category"] == "ding" for s in ed.sfx)      # 결론 문장 밑에는 효과음 없음
    assert any(s["category"] == "riser" for s in ed.sfx)         # 챕터 진입
    assert ed.bgm_dips and ed.bgm_dips[0][1] - ed.bgm_dips[0][0] == pytest.approx(1.0)  # 강도 3 직전 음악 비우기


def test_camera_plan_merges_micro_shots():
    tm = TimeMap([Span(0, 4.6), Span(6.0, 15.4), Span(17.0, 17.2), Span(17.3, 30), Span(31, 40)])
    shots = camera_plan(tm, tm.duration, chapter_starts=[15.6], covers=[], sentence_starts=[2, 8, 12, 20, 25, 33])
    assert all(s["end"] - s["start"] >= 0.99 for s in shots[:-1])


def test_short_edit_is_fast_but_sparse():
    tm = TimeMap([Span(50, 52.5), Span(10, 30), Span(31, 40)], preserve_order=True)   # 콜드 오픈 재배치
    total = tm.duration
    cues = [_cue(t * 1.2, t * 1.2 + 1.1, "짧은 자막") for t in range(int(total / 1.2))]
    cues[5]["lines"][0][0]["em"] = "keyword"
    ed = build_short_edit(timemap=tm, total=total, graphics=[{"start": 8.0, "end": 12.0}], cues=cues,
                          moments=[Moment(t=20.0, end=22.0, intensity=3)])
    assert len(ed.transitions) == 1 and ed.transitions[0]["type"] == "blur"       # 되감기 이음새 하나
    assert {c["zoom"] for c in ed.camera} == {1.0, 1.1}
    assert all(c["end"] - c["start"] >= 1.0 for c in ed.camera[:-1])
    assert 2 <= len(ed.sfx) <= 4


# ---------------------------------------------------------------------------
# 색보정
# ---------------------------------------------------------------------------

def test_grade_correction_fixes_blue_cast_and_underexposure(tmp_path):
    from studio.grade import auto as G
    rng = np.random.default_rng(0)
    img = np.clip(rng.normal(0.25, 0.08, (90, 160, 3)), 0, 1).astype(np.float32)
    img[..., 2] *= 1.35                                   # 파란 캐스트 + 어두움
    img[30:60, 60:100] = [0.42, 0.30, 0.30]               # 얼굴 영역(피부)
    face = {"t": 0, "x": 0.5, "y": 0.5, "s": 0.35}
    st = G.analyze([(0.0, img)], [face])
    c = G.correction_from_stats(st)
    assert c.gains[2] < 1.0 and c.gamma < 1.0             # 파랑 줄이고 밝게
    out = G.grade(img, c, G.GradeChoice(look="natural"))
    assert out[..., 2].mean() / out[..., 0].mean() < img[..., 2].mean() / img[..., 0].mean()
    # LUT 로 구운 결과가 numpy 계산과 같은 모양(.cube 33³)
    cube = G.write_cube(tmp_path / "g.cube", c, G.GradeChoice(look="warm_film", strength=0.7))
    lines = cube.read_text(encoding="ascii").splitlines()
    assert "LUT_3D_SIZE 33" in lines and len([ln for ln in lines if ln[:1].isdigit()]) == 33 ** 3
    sheet = G.comparison_sheet([img, img], c, cell_w=160)
    assert sheet[:2] == b"\xff\xd8"


def test_grade_choice_is_clamped():
    from studio.grade.auto import GradeChoice
    c = GradeChoice(look="rainbow", strength=3, exposure=1, warmth=-9, saturation=5).clamp()
    assert (c.look, c.strength, c.exposure, c.warmth, c.saturation) == ("natural", 1.0, 0.15, -0.4, 1.15)


# ---------------------------------------------------------------------------
# 음향
# ---------------------------------------------------------------------------

def _wav(path: Path, x: np.ndarray, sr: int = 48000) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.stack([x, x], 1) * 32767).astype(np.int16).tobytes())


def test_bgm_curve_ducks_under_voice_and_dips():
    from studio.media.mix import BgmPlan, bgm_gain_curve
    act = np.zeros(1000, np.float32)
    act[200:600] = 1
    plan = BgmPlan(path="x", swells=[(0.0, 1.0)], dips=[(8.0, 9.0)], fade_in=0, fade_out=0)
    g = bgm_gain_curve(act, plan, 10.0)
    assert g[400] == pytest.approx(plan.under_db, abs=0.5)           # 말하는 동안 덕킹
    assert g[50] == pytest.approx(plan.swell_db, abs=0.5)            # 인트로 스웰
    assert g[890] < -40                                               # 핵심 문장 직전 비우기
    assert g[700] > plan.under_db + 5                                 # 쉼에서는 다시 올라옴


def test_mix_and_master_hit_minus_14_lufs(tmp_path):
    from studio.media.ffmpeg import FFmpeg
    from studio.media.mix import BgmPlan, SfxCue, measure_lufs, mix, mux_final
    from studio.sound import synth
    ff = FFmpeg()
    sr = 48000
    t = np.arange(12 * sr) / sr
    voice = np.where((t % 4) < 3, 0.3 * np.sin(2 * np.pi * 190 * t), 0.0)
    _wav(tmp_path / "voice.wav", voice)
    _wav(tmp_path / "bgm.wav", 0.2 * np.sin(2 * np.pi * 220 * np.arange(5 * sr) / sr))
    sfx = synth.build(tmp_path / "sfx")
    whoosh = next(s for s in sfx if s["category"] == "whoosh_soft")
    rep = mix(ff, tmp_path / "voice.wav", tmp_path / "mix.wav", total=12.0,
              sfx=[SfxCue(t=3.5, path=whoosh["path"], gain_db=-20, peak=whoosh["peak_s"])],
              bgm=BgmPlan(path=str(tmp_path / "bgm.wav"), switch_at=[6.0],
                          playlist=[(str(tmp_path / "bgm.wav"), None), (str(tmp_path / "bgm.wav"), None)]))
    assert rep["sfx"] == 1 and rep["bgm_tracks"] == 1
    import subprocess
    subprocess.run([ff.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=160x90:d=12:r=30", "-c:v",
                    "libx264", "-pix_fmt", "yuv420p", str(tmp_path / "v.mp4")], check=True)
    mux_final(ff, tmp_path / "v.mp4", tmp_path / "mix.wav", tmp_path / "final.mp4")
    lufs = measure_lufs(ff, tmp_path / "final.mp4")
    assert lufs is not None and abs(lufs + 14) < 1.0


def test_sound_library_prefers_real_then_falls_back(tmp_path):
    import json
    from studio.sound.library import SoundLibrary
    (tmp_path / "m.json").write_text(json.dumps({"sfx": [], "bgm": [], "models": []}), encoding="utf-8")
    lib = SoundLibrary(root=tmp_path / "sound", manifest=tmp_path / "m.json").ensure(download=False)
    # 내려받은 게 없으면 절차적 효과음, 없는 카테고리는 비슷한 것으로
    assert lib.pick("whoosh_fast").source == "synth"
    assert lib.pick("reverse_cymbal").category == "reverse"
    assert lib.pick("chime").category == "ding"
    assert lib.pick_bgm(("minimal",)) is None and lib.rnnoise_model() is None
