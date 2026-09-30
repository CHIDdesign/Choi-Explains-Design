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
    # 교육 영상용 젠틀 편집: 앵글 차이는 작고(≤6%), 프레이밍은 NG 점프·챕터·그래픽 복귀에서만 바뀐다
    assert PARAMS["medium"] <= 1.07
    cuts = {round(c, 3) for c in tm.cut_points()} | {100.1}
    covers_end = {17.4, 48.0, 75.0, 102.6, 140.0}
    for c in ed.camera[1:]:
        if c.get("glide"):
            continue
        assert any(abs(c["start"] - x) < 0.01 for x in cuts | covers_end), c
    # 긴 샷은 느린 드리프트(최대 5%)
    assert all(c["zoomEnd"] / c["zoom"] - 1 <= PARAMS["push_max"] + 1e-6 for c in ed.camera)


def test_transitions_are_restrained():
    _, _, ed = _long_case()
    types = [t["type"] for t in ed.transitions]
    assert "wipe" in types and "leak" in types          # 챕터·타이틀은 항상
    minor = [t for t in ed.transitions if t["type"] not in ("wipe", "leak")]
    for a, b in zip(minor, minor[1:]):
        assert b["t"] - a["t"] >= PARAMS["tx_min_gap"]  # 하드컷 ≥ 90%
    assert all(0.2 <= t["dur"] <= 1.0 for t in ed.transitions)
    assert not {"whip", "flash", "zoom"} & set(types)      # 튀는 전환은 쓰지 않는다


def test_punch_callout_and_sfx_rules():
    _, _, ed = _long_case()
    ts = [p["t"] for p in ed.punches]
    assert 30.0 in ts and 31.0 not in ts and 44.0 not in ts     # 간격·풀스크린 그래픽 규칙
    assert ed.punches[0]["amount"] == PARAMS["punch"][3] <= 0.1
    assert all(p["style"] == "glide" for p in ed.punches)      # 하드컷 줌 없이 천천히 당긴다
    assert not {"impact", "sub_drop", "glitch"} & {s["category"] for s in ed.sfx}   # 거친 효과음 없음
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


def test_centered_speaker_is_reframed_for_callout():
    """화자가 가운데면 콜아웃 동안 반대쪽으로 천천히 옮겨 자리를 만들고, 같은 순간의 강조 글라이드는 뺀다."""
    tm = TimeMap([Span(0, 60)])
    moments = [Moment(t=20.0, end=23.0, kind="punchline", intensity=3, word="질문", callout="연필보다\n질문 먼저")]
    face = [{"t": float(t), "x": 0.5, "y": 0.4, "s": 0.3} for t in range(60)]
    ed = build_long_edit(timemap=tm, total=60.0, speech_total=60.0, graphics=[], chapters=[], moments=moments,
                         cues=[_cue(19.9, 22.5, "연필보다 질문")], sentence_starts=[0, 10, 20, 30, 40, 50], face=face)
    c = ed.callouts[0]
    shot = next(s for s in ed.camera if s["start"] <= c["start"] + 0.01 < s["end"])
    assert shot["start"] == pytest.approx(c["start"]) and shot["end"] == pytest.approx(c["end"])
    assert shot["zoom"] == PARAMS["callout_zoom"]
    assert (shot["x"] < 0) == (c["side"] == "right")          # 콜아웃 반대쪽으로 화자를 민다
    assert shot["glide"] > 0.3                                 # 컷이 아니라 천천히 옮겨 간다
    back = next(s for s in ed.camera if abs(s["start"] - c["end"]) < 0.01)
    assert back["glide"] > 0.3                                 # 돌아올 때도
    assert not any(abs(p["t"] - 20.0) < 0.01 for p in ed.punches)
    assert any(s["category"] == "pop" and abs(s["t"] - 20.0) < 0.01 for s in ed.sfx)
    assert all(s["end"] - s["start"] >= 0.99 for s in ed.camera[:-1])


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
    assert {c["zoom"] for c in ed.camera} <= {1.0, 1.06}
    assert all(c["end"] - c["start"] >= 3.4 for c in ed.camera[:-1])
    assert all(p["style"] == "glide" for p in ed.punches)
    assert 2 <= len(ed.sfx) <= 6 and not {"impact", "sub_drop", "whoosh_fast", "reverse", "swipe"} & {
        s["category"] for s in ed.sfx}                                   # 컷·이음새에 whoosh 없음(참고 채널)
    assert ed.soft_cut > 0


def test_soft_cuts_only_where_framing_continues():
    from studio.render.props import mark_soft_cuts
    clips = [{"start": 0.0}, {"start": 5.0}, {"start": 9.0}, {"start": 14.0}, {"start": 20.0}]
    camera = [{"start": 0.0, "end": 9.0}, {"start": 9.0, "end": 20.0},
              {"start": 20.0, "end": 30.0, "glide": 0.7}]
    n = mark_soft_cuts(clips, camera, [{"t": 14.1}], 0.1)
    assert n == 2
    assert clips[1]["soft"] == 0.1 and clips[4]["soft"] == 0.1    # 같은 프레이밍·글라이드 샷
    assert "soft" not in clips[2] and "soft" not in clips[3]       # 앵글 전환·전환 효과가 있는 컷
    assert "soft" not in clips[0]


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
    assert (c.look, c.strength, c.exposure, c.warmth, c.saturation) == ("warm_rich", 1.0, 0.15, -0.4, 1.15)


def test_reference_match_makes_gray_footage_warm_and_rich_but_keeps_skin():
    """업로드된 결과물은 회색(얼굴 화면 b +2.5, C 5.9) — 레퍼런스(b +14.5, C 16.9) 쪽으로 눈에 띄게, 피부는 덜."""
    from studio.grade.auto import REFERENCE_LAB, Correction, GradeChoice, grade, lab_stats, skin_mask
    rng = np.random.default_rng(1)
    wall = np.clip(0.62 + rng.normal(0, 0.03, (40, 40, 3)), 0, 1) * np.array([1.0, 1.0, 1.02])
    skin = np.tile(np.array([0.78, 0.60, 0.50]), (40, 40, 1))
    img = np.concatenate([wall, skin], axis=1).astype(np.float32)
    src = lab_stats(img)
    out = grade(img, Correction(), GradeChoice(look="warm_rich", src_lab=src))
    L0, a0, b0, C0 = src
    L1, a1, b1, C1 = lab_stats(out)
    assert b1 - b0 > 4 and C1 > C0 + 3                           # 확실히 따뜻하고 진하게
    assert b1 < REFERENCE_LAB["b"] + 4
    w0, w1 = lab_stats(img[:, :40]), lab_stats(out[:, :40])       # 회색 벽: 노랗게, 초록으로 가지 않게
    assert w1[2] - w0[2] > 5 and w1[1] >= w0[1] - 0.6
    sk0, sk1 = lab_stats(img[:, 40:]), lab_stats(out[:, 40:])
    assert sk1[3] < sk0[3] * 1.45 and skin_mask(out[:, 40:]).mean() > 0.5   # 피부는 피부색 그대로
    # 레퍼런스 매칭을 끄면 거의 그대로
    plain = grade(img, Correction(), GradeChoice(look="natural", match=0.0, strength=0.0))
    assert abs(lab_stats(plain)[2] - b0) < 1.0


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


def test_voice_is_aligned_when_audio_stream_starts_late(tmp_path):
    """폰·카메라·OBS 녹화처럼 오디오 스트림이 영상보다 늦게 시작하면(start_time) 예전엔 그만큼 소리가 앞당겨졌다."""
    import shutil
    import subprocess
    import wave

    import numpy as np
    import pytest
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg 없음")
    from studio.edit.assemble import build_proxy
    from studio.media.audio import build_voice_track
    from studio.media.ffmpeg import FFmpeg
    base, src = tmp_path / "v.mp4", tmp_path / "off.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=black:s=160x120:r=30:d=4,drawbox=c=white:t=fill:enable='between(t,2,2.1)'",
                    "-f", "lavfi", "-i", "sine=f=1000:d=4:sample_rate=48000,volume=enable='not(between(t,2,2.1))':volume=0",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(base)], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(base), "-itsoffset", "0.3", "-i", str(base),
                    "-map", "0:v", "-map", "1:a", "-c", "copy", str(src)], check=True)
    ff = FFmpeg()
    info = ff.probe(src)
    assert info.av_offset > 0.2
    build_voice_track(ff, src, tmp_path / "voice.wav", duration=info.duration, enhance=False, av_offset=info.av_offset)
    build_proxy(ff, src, info, tmp_path / "proxy.mp4", fps=30, height=120)
    with wave.open(str(tmp_path / "voice.wav")) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, 2)[:, 0]
    beep = int(np.argmax(np.abs(a) > 2000)) / 48000
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(tmp_path / "proxy.mp4"), "-vf", "scale=8:8,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    flash = int(np.argmax(np.frombuffer(raw, np.uint8).reshape(-1, 64).mean(1) > 128)) / 30
    assert abs((beep - flash) - 0.3) < 0.05, (beep, flash)   # 원본처럼 소리가 화면보다 0.3초 늦게


# ---------------------------------------------------------------------------
# 종이 콜라주 스킨(사용자 레퍼런스)
# ---------------------------------------------------------------------------

def test_paper_texture_matches_reference_paper():
    """레퍼런스 종이 측정값: 평균 RGB ≈ (40, 40, 45), 밝기 편차 ≈ 3."""
    from studio.render.assets import crumpled_paper
    a = crumpled_paper(480, 270).astype(float)
    mean = a.mean((0, 1))
    assert abs(mean[0] - 40) < 5 and mean[2] - mean[0] > 3        # 짙은 차콜, 살짝 푸른 기
    assert 1.5 < a.mean(-1).std() < 7


def test_paper_skin_moves_fullscreen_concepts_next_to_speaker():
    from studio.render.props import paper_layouts
    gs = [{"template": "definition", "layout": "fullscreen"}, {"template": "process", "layout": "fullscreen"},
          {"template": "keyword", "layout": "overlay"}]
    out = paper_layouts([dict(g) for g in gs], "paper")
    assert [g["layout"] for g in out] == ["split", "fullscreen", "overlay"]
    assert [g["layout"] for g in paper_layouts([dict(g) for g in gs], "classic")] == ["fullscreen", "fullscreen",
                                                                                      "overlay"]


def test_camera_plan_uses_framed_shots_gently():
    tm = TimeMap([Span(0, 12), Span(14, 30), Span(32, 50), Span(52, 70), Span(72, 90)])
    shots = camera_plan(tm, tm.duration, chapter_starts=[], covers=[], sentence_starts=[])
    framed = [s for s in shots if s.get("framed")]
    assert framed and all(s["end"] - s["start"] >= PARAMS["framed_min"] for s in framed)
    for i, s in enumerate(shots):
        if s.get("framed") or (i and shots[i - 1].get("framed")):
            assert s["glide"] == PARAMS["framed_glide"]          # 액자 들어가고 나올 때 천천히


def test_short_beats_fill_the_bottom_every_few_seconds():
    from studio.edit.grammar import Moment
    from studio.models import Utterance, Word
    from studio.render.props import short_beats
    words = [Word(f"w{i}", i * 1.0, i * 1.0 + 0.8, 0.9) for i in range(30)]
    utts = [Utterance(id=k, start=k * 6.0, end=k * 6.0 + 5.8, text="", asr_text="", words=words[k * 6:(k + 1) * 6])
            for k in range(5)]
    tm = TimeMap([Span(0, 30)])
    spec = {"beats": [{"seg": 0, "label": "오늘의 질문", "text": "좋은 디자인의 시작", "accent": "시작"},
                      {"seg": 3, "label": "핵심", "text": "질문이 먼저다", "accent": "없는말"}]}
    cues = [{"start": 12.0, "end": 13.5, "lines": [[{"text": "해결책부터", "start": 12, "end": 13, "em": True},
                                                  {"text": "그리지", "start": 13, "end": 13.5}]]}]
    beats = short_beats(spec, utts, tm, cues, [Moment(t=6.2, end=8.0, callout="넓게\n펼치기", label="방법")], 30.0)
    assert [b["text"] for b in beats] == ["좋은 디자인의 시작", "넓게", "해결책부터 그리지", "질문이 먼저다"]
    assert beats[0]["start"] == 0.25 and beats[-1]["accent"] == ""          # 텍스트에 없는 강조어는 버림
    for a, b in zip(beats, beats[1:]):
        assert a["end"] <= b["start"] and 2.2 <= a["end"] - a["start"] <= 5.0


def test_shorts_inherit_long_graphics_in_their_segments():
    from types import SimpleNamespace
    from studio.pipeline import Pipeline
    long_g = [{"template": "chapter", "start_seg": 3}, {"template": "list", "start_seg": 3},
              {"template": "broll", "start_seg": 4, "src": "broll/a.mp4"}, {"template": "broll", "start_seg": 4},
              {"template": "motion", "start_seg": 9}, {"template": "keyword", "start_seg": 5}]
    fake = SimpleNamespace(plan_long={"graphics": long_g})
    s = {"segments": [3, 4, 5], "graphics": [{"template": "keyword", "start_seg": 5}]}
    got = Pipeline._short_graphics(fake, s)
    assert [(g["template"], g["start_seg"]) for g in got] == [("keyword", 5), ("list", 3), ("broll", 4)]


def test_captions_hidden_when_graphic_already_shows_the_words():
    from studio.render.props import caption_overlays, dedupe_captions
    cue = lambda a, b, txt: {"start": a, "end": b, "lines": [[{"text": w} for w in txt.split()]]}
    cues = [cue(10.0, 11.5, "좋은 질문의 조건은"), cue(11.5, 13.0, "세 가지입니다"), cue(20.0, 21.0, "어포던스란"),
            cue(30.0, 31.2, "전혀 다른 이야기")]
    props = {"graphics": [{"template": "list", "start": 9.8, "end": 16.0,
                           "data": {"title": "좋은 질문의 조건", "items": ["구체적이다", "열려 있다"]}},
                          {"template": "definition", "start": 19.5, "end": 24.0,
                           "data": {"title": "어포던스", "body": "형태가 사용법을 알려주는 성질"}}],
             "callouts": [{"start": 29.0, "end": 33.0, "text": "질문이\n먼저"}]}
    n = dedupe_captions(cues, caption_overlays(props))
    assert n == 2
    assert [bool(c.get("hidden")) for c in cues] == [True, False, True, False]


def test_stack_captions_are_rare_and_skip_busy_or_hidden():
    from studio.render.props import mark_stack_cues
    cue = lambda a, txt, em=None, **kw: {"start": a, "end": a + 1.0, "lines": [[
        {"text": w, "start": a, "end": a + 1.0, **({"em": "keyword"} if w == em else {})} for w in txt.split()]], **kw}
    cues = [cue(1, "좋은 질문이", "질문이"), cue(5, "먼저 입니다", "먼저"), cue(20, "디자인의 시작", "시작"),
            cue(30, "숨긴 자막", "자막", hidden=True), cue(45, "아주 아주 긴 문장이라 두 층으로는 안 된다", "문장이라"),
            cue(60, "그래픽 위", "위"), cue(80, "결론은 질문", "질문", style="impact"), cue(85, "바로 다음", "다음")]
    n = mark_stack_cues(cues, min_gap=18.0, avoid=[(59.5, 62.0)])
    assert [c.get("style") for c in cues] == ["stack", None, "stack", None, None, None, "impact", None] and n == 2
