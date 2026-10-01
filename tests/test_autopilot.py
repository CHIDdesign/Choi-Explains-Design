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


def test_callouts_are_not_capped_by_punch_glides():
    """콜아웃은 강조 글라이드(40초 간격)와 따로 20초 간격으로 — 레퍼런스의 얼굴+오버레이 비율(약 21%)에 가깝게.
    글라이드가 없는 콜아웃은 등장에 작은 pop. 얼굴만 이어지는 가장 긴 구간을 통계로 남긴다."""
    tm = TimeMap([Span(0, 120)])
    moments = [Moment(t=float(t), end=t + 2.5, kind="punchline", intensity=2, word="핵심", callout=f"핵심 {t}")
               for t in (10, 32, 54, 76, 98)]
    face = [{"t": float(t), "x": 0.3, "y": 0.4, "s": 0.3} for t in range(120)]
    ed = build_long_edit(timemap=tm, total=120.0, speech_total=120.0, graphics=[], chapters=[], moments=moments,
                         cues=[], sentence_starts=list(range(0, 120, 8)), face=face)
    assert len(ed.punches) == 3                                   # 글라이드는 40초 간격 그대로
    starts = [round(c["start"] + 0.08) for c in ed.callouts]
    assert starts == [10, 32, 54, 76, 98]                         # 콜아웃은 모두(20초 간격 이상)
    no_glide = [t for t in starts if not any(abs(p["t"] - t) < 0.01 for p in ed.punches)]
    assert no_glide and all(any(s["category"] == "pop" and abs(s["t"] - t) < 0.2 for s in ed.sfx) for t in no_glide)
    assert ed.stats["callouts"] == 5 and 0 < ed.stats["max_face_run"] < 30


def test_long_face_only_stretch_gets_a_gentle_framing_change():
    """얼굴만 max_shot(30초) 넘게 이어지면 문장 시작에서 글라이드로 프레이밍을 한 번 바꾼다(컷 없음)."""
    tm = TimeMap([Span(0, 70)])
    shots = camera_plan(tm, 70.0, chapter_starts=[], covers=[], sentence_starts=list(range(0, 70, 5)))
    assert len(shots) >= 2 and all(s["end"] - s["start"] <= PARAMS["max_shot"] + 1e-6 for s in shots)
    assert all(s.get("glide", 0) > 0 for s in shots[1:])


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


def _patch(rgb, rng, n=40, noise=0.02):
    return np.clip(np.array(rgb, np.float32) + rng.normal(0, noise, (n, n, 3)), 0, 1).astype(np.float32)


def _lab(x):
    from studio.grade.auto import srgb_to_lab
    L, a, b = srgb_to_lab(x.reshape(-1, 3))
    return float(L.mean()), float(a.mean()), float(b.mean()), float(np.hypot(a, b).mean(), ), \
        float(np.degrees(np.arctan2(b.mean(), a.mean())) % 360)


def _auto_grade(parts, face_rgb, face_luma):
    """분석 → 교정 → 풍부함 → 룩 → 피부 보호(파이프라인과 같은 순서)."""
    from studio.grade import auto as G
    img = np.concatenate(parts, axis=1)
    st = G.analyze([(0.0, img)], [None])
    st["face_rgb"], st["face_luma"] = list(face_rgb), face_luma
    c = G.correction_from_stats(st)
    out = G.grade(img, c, G.plan_choice([img], c, "warm_rich", skin_rgb=st["face_rgb"]))
    return [out[:, i * 40:(i + 1) * 40] for i in range(len(parts))], c


def test_gray_warm_room_gets_richer_but_bounded():
    """교정이 방의 온기를 지워 회색이 된 화면(배경 채도 8 아래 = 정상 범위 밖): 진해지되 색상은 원본 그대로(레퍼런스 쪽으로
    '옮기지' 않는다), 피부는 피부색 범위에 채도 30 이하."""
    rng = np.random.default_rng(1)
    (wall, skin, dark), _ = _auto_grade([_patch([0.55, 0.53, 0.50], rng), _patch([0.70, 0.55, 0.47], rng),
                                         _patch([0.12, 0.11, 0.10], rng)], [0.70, 0.55, 0.47], 0.58)
    Lw, aw, bw, Cw, hw = _lab(wall)
    assert 9 <= Cw <= 20 and 7 <= bw <= 16 and aw > 0 and abs(hw - 84.3) <= 6   # 진해지되 원래 크림색 그대로, 과하지 않게
    _, _, _, Cs, hs = _lab(skin)
    assert 40 <= hs <= 60 and Cs <= 31
    assert abs(_lab(dark)[2]) < 4                                   # 암부는 그대로


def test_blue_monitor_room_keeps_its_light_but_skin_and_whites_are_fixed():
    """모니터 불빛의 파란 방(피부 색상 335° · 흰 벽 b −14): 예전엔 평균을 레퍼런스에 맞추느라 통째로 주황이 됐다.
    이제 피부는 피부색 선, 흰 것은 흰색, 배경은 차가운 채로."""
    rng = np.random.default_rng(2)
    blue = np.array([0.80, 0.90, 1.15], np.float32)
    sk = np.clip(_patch([0.62, 0.50, 0.42], rng) * blue, 0, 1)
    from studio.grade.auto import _luma
    (skin, white, wall), c = _auto_grade([sk, np.clip(_patch([0.80, 0.85, 0.95], rng), 0, 1),
                                          np.clip(_patch([0.30, 0.34, 0.48], rng), 0, 1)],
                                         sk.reshape(-1, 3).mean(0), float(np.median(_luma(sk))))
    _, _, _, Cs, hs = _lab(skin)
    assert 32 <= hs <= 62 and 8 <= Cs <= 32, (hs, Cs)
    Lw, aw, bw, Cw, _ = _lab(white)
    # 흰 벽·모니터는 거의 흰색(원본 C 14 → 9 이하). 최소 개입이라 얼굴을 범위 안쪽 경계까지만 옮기므로 완전한 중립은 아니다
    assert abs(bw) <= 6 and Cw <= 9 and Lw > 85
    assert _lab(wall)[2] <= -10                                       # 파란 배경은 파란 채로(노랗게 되지 않음)
    assert any("피부" in n for n in c.notes)


def test_correct_studio_footage_is_left_almost_alone():
    rng = np.random.default_rng(3)
    (skin, white, gray), _ = _auto_grade([_patch([0.76, 0.58, 0.48], rng), _patch([0.92, 0.92, 0.92], rng),
                                          _patch([0.45, 0.45, 0.45], rng)], [0.76, 0.58, 0.48], 0.62)
    Lw, aw, bw, _, _ = _lab(white)
    assert abs(aw) <= 4 and abs(bw) <= 5 and Lw > 90                 # 흰 것은 흰색(살짝 크림까지만)
    _, ag, bg, _, _ = _lab(gray)
    assert abs(ag) <= 6 and abs(bg) <= 6                             # 회색은 은은한 온기까지만
    _, _, _, Cs, hs = _lab(skin)
    assert 40 <= hs <= 60 and Cs <= 31


def test_yellow_and_green_faces_are_brought_to_the_skin_line():
    """백열등의 노란 얼굴(80°) · 형광등의 초록 얼굴(100°) → 피부색 선 가까이(62° 이하), 채도 30 이하."""
    rng = np.random.default_rng(4)
    (skin, _), c = _auto_grade([np.clip(_patch([0.85, 0.66, 0.36], rng), 0, 1), _patch([0.62, 0.50, 0.30], rng)],
                               [0.85, 0.66, 0.36], 0.62)
    _, _, _, Cs, hs = _lab(skin)
    assert hs <= 62 and Cs <= 32, (hs, Cs)
    (skin, _), _ = _auto_grade([np.clip(_patch([0.62, 0.60, 0.44], rng), 0, 1), _patch([0.70, 0.72, 0.66], rng)],
                               [0.62, 0.60, 0.44], 0.58)
    _, _, _, Cs, hs = _lab(skin)
    assert hs <= 64 and Cs <= 32, (hs, Cs)


def _warm_room(rng, h=90, w=160):
    """채널 주인이 '적당히 좋은 색감'이라고 한 장면을 흉내 낸 프레임: 스탠드 조명의 크림·베이지 벽, 자연스러운 피부,
    깊은 암부, 밝은 램프."""
    img = np.empty((h, w, 3), np.float32)
    img[:] = [0.72, 0.62, 0.50]                       # 크림·베이지 벽
    img[:, :30] = [0.05, 0.04, 0.035]                 # 어두운 구석
    img[:20, 120:] = [0.97, 0.93, 0.84]               # 램프 빛
    img[25:75, 60:100] = [0.80, 0.60, 0.50]           # 얼굴
    return np.clip(img + rng.normal(0, 0.012, img.shape), 0, 1).astype(np.float32)


def test_good_footage_is_left_untouched():
    """첫 원칙: 원래 톤이 괜찮은 영상은 건드리지 않는다 — 스코프 모두 정상, 교정·레시피 없음, LUT 도 만들지 않는다."""
    from studio.grade import auto as G
    from studio.grade import scopes
    rng = np.random.default_rng(7)
    frames = [_warm_room(rng) for _ in range(3)]
    face = {"t": 0, "x": 0.5, "y": 0.55, "s": 0.3}
    checks = scopes.assess(scopes.metrics(frames, [face] * 3))
    assert scopes.all_ok(checks), scopes.summary(checks)
    st = G.analyze([(0.0, f) for f in frames], [face] * 3)
    c = G.correction_from_stats(st)
    assert G.is_identity_correction(c), c.notes
    ch = G.plan_choice(frames, c, "natural", skin_rgb=st.get("face_rgb"))
    assert ch.recipe["why"] == ["레시피 없음(정상 범위)"]
    assert G.is_identity(c, G.untouched_choice())
    assert G.cleanup_filters({"noise": 0.004}) == []                 # 깨끗하면 디노이즈·샤픈도 없음
    sheet = scopes.draw([("원본", frames)])
    assert sheet[:2] == b"\xff\xd8"


def test_scopes_flag_only_what_is_out_of_range():
    from studio.grade import scopes
    rng = np.random.default_rng(8)
    flat = np.clip(0.45 + rng.normal(0, 0.02, (90, 160, 3)), 0, 1).astype(np.float32)   # 회색·평평한 로그 소스
    bad = {c.key for c in scopes.assess(scopes.metrics([flat])) if not c.ok}
    assert {"spread", "chroma_mid", "black_ire", "white_ire"} <= bad
    assert "clip_pct" not in bad


def test_qc_backs_off_when_grade_amplifies_color_noise():
    """보정 뒤 검사: 압축 색 잡음을 1.5배 넘게 키우는 선택(채도 이득 큼)은 세기·채도를 줄인다."""
    from studio.grade import auto as G
    rng = np.random.default_rng(9)
    wall = np.clip(np.array([0.60, 0.57, 0.52], np.float32) + rng.normal(0, 0.02, (90, 160, 3)), 0, 1).astype(np.float32)
    loud = G.GradeChoice(look="warm_rich", strength=1.0, saturation=1.15,
                         recipe={"contrast": 0.0, "black": 0.0, "chroma_gain": 1.8, "skin_gain": 1.3, "warmth": 0.0})
    ch, qc = G.qc_backoff([wall], G.Correction(), loud, max_noise=1.3)
    assert qc["backoff"] and ch.strength < 1.0 and ch.recipe["chroma_gain"] < 1.8
    assert qc["noise_gain"] < 1.6


def test_enrich_never_shifts_the_whole_frame_and_can_be_switched_off():
    from studio.grade.auto import REFERENCE_LAB, Correction, GradeChoice, grade, lab_stats
    rng = np.random.default_rng(5)
    img = np.concatenate([_patch([0.62, 0.62, 0.64], rng), _patch([0.78, 0.60, 0.50], rng)], axis=1)
    src = lab_stats(img)
    out = grade(img, Correction(), GradeChoice(look="warm_rich", src_lab=src))
    assert 0 <= lab_stats(out)[2] - src[2] <= 8                     # 온기는 +8 이하(예전엔 +12 넘게)
    assert lab_stats(out)[2] < REFERENCE_LAB["b"]                    # 레퍼런스 평균으로 '옮기지' 않는다
    plain = grade(img, Correction(), GradeChoice(look="natural", match=0.0, strength=0.0))
    assert abs(lab_stats(plain)[2] - src[2]) < 1.5


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


def test_hybrid_looks_follow_content_and_always_mix():
    from studio.edit.style import apply_looks, choose_looks
    g = lambda i, tpl, a, layout="split": {"id": i, "template": tpl, "layout": layout, "start": a, "end": a + 4,
                                           "data": {}}
    graphics = [g("t", "title", 0.2, "fullscreen"), g("k", "keyword", 10), g("q", "quote", 20, "fullscreen"),
                g("p", "photo", 30, "pip"), g("pr", "process", 70, "fullscreen"), g("m", "matrix", 85, "fullscreen"),
                g("d", "definition", 95, "fullscreen")]
    chapters = [{"start": 0.0, "title": "들어가며", "number": "01"}, {"start": 60.0, "title": "구조", "number": "02"}]
    texts = {0.0: "제가 처음 디자인을 배울 때 경험을 예를 들어 이야기해 볼게요", 60.0: "세 단계 구조를 비교해 보면"}
    plan = choose_looks(graphics, chapters, 120.0, lambda a, b: " ".join(v for k, v in texts.items() if a <= k < b))
    assert [c["look"] for c in plan.chapters] == ["paper", "classic"]
    assert plan.graphic_skins["pr"] == "classic" and plan.graphic_skins["m"] == "classic"
    # 개념 카드는 그 챕터의 구성을 따른다(기본 챕터 → 롱폼 무대 플레이트·보드, 종이 챕터 → 사용자 템플릿), 타이틀은 늘 종이
    assert plan.graphic_skins["d"] == "classic" and plan.graphic_skins["k"] == "paper" and plan.graphic_skins["t"] == "paper"
    assert plan.paper_ranges() == [(0.0, 60.0)]
    props = {"graphics": [dict(x) for x in graphics], "chapters": [dict(c) for c in chapters]}
    apply_looks(props, plan)
    assert props["skin"] == "hybrid" and [c["look"] for c in props["chapters"]] == ["paper", "classic"]
    assert next(x for x in props["graphics"] if x["id"] == "q")["layout"] == "split"          # 종이 개념 카드 → 화자 액자
    assert next(x for x in props["graphics"] if x["id"] == "d")["layout"] == "fullscreen"     # 기본 챕터는 그대로
    # 모두 한쪽이면 하나는 반대로(섞기)
    same = choose_looks([g("a", "process", 5), g("b", "cycle", 65)], chapters, 120.0, lambda a, b: "")
    assert {c["look"] for c in same.chapters} == {"paper", "classic"}


def test_face_safe_pip_placement_picks_free_side_or_falls_back_to_split():
    """얼굴 옆 사진 액자·개념 텍스트가 얼굴을 덮지 않게: 빈 쪽으로, 좁으면 줄이고, 자리가 없으면 화자 패널로."""
    from studio.render.props import face_safe_layouts

    def g(i, tpl, a, layout="pip"):
        return {"id": i, "template": tpl, "layout": layout, "start": a, "end": a + 4, "data": {}}

    def track(x, s, t0=0.0, t1=200.0):
        return [{"t": t, "x": x, "y": 0.4, "s": s} for t in range(int(t0), int(t1))]
    # 화자가 오른쪽(x 0.62) → 액자는 왼쪽, 원래 크기
    gs = [g("p", "photo", 10), g("k", "keyword", 20, "overlay"), g("l", "list", 30, "overlay")]
    st = face_safe_layouts(gs, track(0.62, 0.3))
    assert gs[0]["pip"] == {"side": "left", "w": 700, "h": 520} and gs[1]["pip"]["side"] == "left"
    assert "pip" not in gs[2] and st["placed"] == 2 and st["to_split"] == 0
    # 가운데 큰 얼굴(x 0.5, s 0.42) → 여유에 맞춰 줄인 액자
    gs = [g("p", "photo", 10)]
    st = face_safe_layouts(gs, track(0.5, 0.42))
    assert 420 <= gs[0]["pip"]["w"] < 700 and st["shrunk"] == 1
    # 클로즈업(s 0.65) → 액자 대신 화자 패널(split)
    gs = [g("p", "photo", 10), g("b", "broll", 20)]
    st = face_safe_layouts(gs, track(0.5, 0.65))
    assert all(x["layout"] == "split" and "pip" not in x for x in gs) and st["to_split"] == 2
    # 구간 안에서 얼굴이 움직이면(0.3 → 0.62) 두 위치를 다 피한다
    tr = track(0.3, 0.3, 0, 12) + track(0.62, 0.3, 12, 40)
    gs = [g("p", "photo", 8)]
    face_safe_layouts(gs, tr)
    assert gs[0]["layout"] == "split" and "pip" not in gs[0]      # 양쪽 다 좁아져 패널로
    # 얼굴 트랙이 없으면 손대지 않는다(렌더러가 faceX 로)
    gs = [g("p", "photo", 8)]
    assert face_safe_layouts(gs, []) == {"placed": 0, "shrunk": 0, "to_split": 0, "top": 0} and "pip" not in gs[0]


# ---------------------------------------------------------------------------
# 🎓 롱폼 무대 편집법: 챕터 끝 정리 보드 · 챕터 카드 목차 (studio/render/props.py)
# ---------------------------------------------------------------------------

def _g(i, tpl, a, b, layout="split", **data):
    return {"id": i, "template": tpl, "layout": layout, "start": a, "end": b, "data": data}


def test_chapter_recaps_collects_points_and_sits_in_free_window_at_chapter_end():
    from studio.render.props import chapter_recaps
    chapters = [{"start": 0.0, "title": "들어가며", "number": "01", "claim": ""},
                {"start": 60.0, "title": "문제 정의", "number": "02", "claim": "좋은 답은 질문을 바꿀 때 나온다"}]
    gs = [_g("k1", "keyword", 5, 9, "overlay", title="발산 먼저"),
          _g("d1", "definition", 70, 76, title="어포던스", body="형태가 사용법을 알려주는 성질"),
          _g("s1", "stat", 90, 94, "overlay", title="85%", body="다섯 명이면 충분"),
          _g("l1", "list", 100, 108, title="좋은 질문의 조건", items=["가", "나"]),
          _g("k2", "keyword", 100, 103, "overlay", title="좋은 질문의 조건"),      # 같은 말은 한 번만
          _g("p1", "broll", 122, 126, "pip", src="x.mp4")]
    added = chapter_recaps(gs, chapters, 130.0)
    assert len(added) == 1, added
    r = added[0]
    assert r["template"] == "recap" and r["layout"] == "split" and r["id"] == "recap02"
    assert r["data"]["title"] == "좋은 답은 질문을 바꿀 때 나온다"
    assert r["data"]["items"] == ["어포던스: 형태가 사용법을 알려주는 성질", "85% — 다섯 명이면 충분", "좋은 질문의 조건"]
    # 챕터 끝(129.6) 창은 122~126 스톡과 겹치므로 그 앞의 빈 창으로
    assert r["end"] <= 129.6 and r["end"] - r["start"] in (7.0, 5.0)
    assert not any(r["start"] < g["end"] + 0.3 and r["end"] > g["start"] - 0.5 for g in gs if g is not r)
    assert gs == sorted(gs, key=lambda g: g["start"])          # 시간순 유지
    # 첫 챕터(60초)는 개념이 하나뿐이라 정리하지 않는다


def test_chapter_recaps_never_covers_emphasis_moments_or_punch_spans():
    """편집 감독의 강조 순간·펀치 구간은 얼굴로 힘을 주는 자리 — 정리 보드가 덮지 않고, 그 앞의 빈 창으로 가거나 건너뛴다."""
    from studio.render.props import chapter_recaps
    chapters = [{"start": 0.0, "title": "A", "number": "01"}, {"start": 10.0, "title": "B", "number": "02"}]
    mk = lambda: [_g("k1", "keyword", 20, 24, "overlay", title="하나"), _g("k2", "keyword", 40, 44, "overlay", title="둘")]
    gs = mk()
    added = chapter_recaps(gs, chapters, 80.0, avoid=[(72.0, 79.0)])          # 끝 7초가 펀치 구간 → 그 앞 창으로
    assert added and added[0]["end"] <= 72.0 and added[0]["start"] >= 44.3
    gs = mk()
    assert chapter_recaps(gs, chapters, 80.0, avoid=[(60.0, 79.6)]) == []    # 끝 20초가 통째로 강조 → 건너뛴다


def test_chapter_recaps_skips_short_chapters_and_busy_endings():
    from studio.render.props import chapter_recaps
    chapters = [{"start": 0.0, "title": "A", "number": "01"}, {"start": 30.0, "title": "B", "number": "02"}]
    gs = [_g("k1", "keyword", 2, 5, "overlay", title="하나"), _g("k2", "keyword", 8, 11, "overlay", title="둘"),
          _g("k3", "keyword", 40, 43, "overlay", title="셋"), _g("k4", "keyword", 50, 53, "overlay", title="넷"),
          _g("m1", "motion", 58, 79.8, "fullscreen", title="장면")]
    assert chapter_recaps(gs, chapters, 80.0) == []           # 30초 챕터 + 끝 20초가 전체화면으로 꽉 찬 챕터


def test_chapter_maps_fill_chapter_cards_with_table_of_contents():
    from studio.render.props import chapter_maps
    chapters = [{"start": 0.0, "title": "들어가며", "number": "01"}, {"start": 60.0, "title": "문제 정의", "number": "02"},
                {"start": 120.0, "title": "정리", "number": "03"}]
    gs = [_g("ch02", "chapter", 59.9, 63.1, "fullscreen", title="문제 정의", number="02"),
          _g("ch03", "chapter", 119.9, 123.1, "fullscreen", title="정리", number="03"),
          _g("k", "keyword", 5, 8, "overlay", title="x")]
    assert chapter_maps(gs, chapters) == 2
    assert gs[0]["data"]["items"] == ["들어가며", "문제 정의", "정리"] and gs[0]["data"]["highlight"] == 1
    assert gs[1]["data"]["highlight"] == 2 and "items" not in gs[2]["data"]


def test_recap_point_texts():
    from studio.render.props import recap_point
    assert recap_point(_g("a", "compare", 0, 1, title="발산", title_b="수렴")) == "발산 vs 수렴"
    assert recap_point(_g("a", "quote", 0, 1, body="적게, 그러나 더 좋게", author="디터 람스")) == "디터 람스: “적게, 그러나 더 좋게”"
    assert recap_point(_g("a", "motion", 0, 1, spec={"label": "게슈탈트 · 근접성", "elements": []})) == "게슈탈트 · 근접성"
    long = recap_point(_g("a", "keyword", 0, 1, title="아주 아주 아주 아주 아주 아주 아주 긴 제목입니다 정말로"))
    assert long.endswith("…") and len(long) <= 26


def test_fold_keywords_into_media_makes_keyword_slam_on_the_photo():
    from studio.render.props import fold_keywords_into_media
    gs = [_g("p", "photo", 10, 16, "fullscreen", image="a.jpg", title="바우하우스"),
          _g("k", "keyword", 16.3, 19.5, "overlay", title="형태는 기능을 따른다", subtitle="장식 → 기능"),
          _g("b", "broll", 30, 35, "fullscreen", src="x.mp4"),
          _g("k2", "keyword", 32, 34.5, "overlay", title="대량 생산"),
          _g("k3", "keyword", 50, 53, "overlay", title="따로 뜨는 키워드")]
    assert fold_keywords_into_media(gs) == 2
    ids = [g["id"] for g in gs]
    assert ids == ["p", "b", "k3"]
    p = gs[0]
    assert p["data"]["keyword"] == "형태는 기능을 따른다" and p["data"]["keyword_sub"] == "장식 → 기능"
    assert p["data"]["keyword_at"] == 6.0 and p["end"] == 19.5          # 사진이 키워드 끝까지 이어진다
    b = gs[1]
    assert b["data"]["keyword"] == "대량 생산" and b["data"]["keyword_at"] == 2.0 and b["end"] == 35


def test_face_safe_puts_short_keywords_in_top_section_bar_when_head_is_low():
    from studio.render.props import face_safe_layouts

    def tr(y, s):
        return [{"t": t, "x": 0.5, "y": y, "s": s} for t in range(0, 40)]
    gs = [_g("k", "keyword", 5, 9, "overlay", title="공원 속에 도로를 숨긴 방법"),
          _g("k2", "keyword", 12, 16, "overlay", title="발산", subtitle="넓게 펼친다"),       # 보조문 있음 → 옆 메모
          _g("k3", "keyword", 20, 24, "overlay", title="이 제목은 열여섯 자를 훌쩍 넘는 긴 키워드입니다")]
    st = face_safe_layouts(gs, tr(0.48, 0.26))                 # 머리 위 ≈ 252px 비어 있음
    assert gs[0]["pip"] == {"side": "top", "w": 1240, "h": 120} and st["top"] == 1
    assert gs[1]["pip"]["side"] in ("left", "right") and gs[2]["pip"]["side"] in ("left", "right")
    gs = [_g("k", "keyword", 5, 9, "overlay", title="공원 속에 도로를 숨긴 방법")]
    st = face_safe_layouts(gs, tr(0.36, 0.3))                  # 머리가 위에 붙어 있음 → 옆 메모
    assert gs[0]["pip"]["side"] in ("left", "right") and st["top"] == 0


def test_topic_tag_goes_to_first_face_only_window():
    """'오늘의 주제'(논지 한 줄)는 타이틀 뒤 얼굴만 보이는 첫 빈 자리에 — 말에 맞춘 그래픽을 밀어내지 않는다."""
    from studio import pipeline as pl
    from studio.director.plan import TimedGraphic
    p = object.__new__(pl.Pipeline)
    p.plan_long = {"summary": "좋은 디자인은 해결책이 아니라 질문에서 시작한다. 그래서 오늘은"}
    gs = [TimedGraphic("title", "title", "fullscreen", 1.3, 4.7, {}, 12, "auto"),
          TimedGraphic("g0", "double_diamond", "fullscreen", 6.0, 11.1, {}, 6, "director"),
          TimedGraphic("g1", "keyword", "split", 11.6, 15.9, {}, 5, "director")]
    lt = p._lower_third(gs, after=4.7, total=60.0)
    assert lt is not None and lt.start >= 15.9 and lt.end - lt.start >= 4.0
    assert lt.data == {"subtitle": "오늘의 주제", "title": "좋은 디자인은 해결책이 아니라 질문에서 시작한다"}
    assert p._lower_third(gs[:1], after=4.7, total=60.0).start == pytest.approx(5.5)   # 비어 있으면 타이틀 바로 뒤
    assert pl.topic_line("디자인 과정에서 가장 많이 건너뛰는 단계가 사실은 가장 중요하다") == "디자인 과정에서 가장 많이 건너뛰는 단계가 사실은…"
    assert pl.topic_line("짧다") == ""


def test_beige_wall_does_not_blotch_or_turn_pink():
    """실제 사례: 노란 베이지 벽(색상 88°)이 피부 보호에 잡혀 픽셀마다 다르게 32~60° 로 옮겨지며 분홍·연두 얼룩이 됐다.
    얼굴이 이미 피부 범위면 벽은 옮기지 않고, 압축된 색 잡음(2×2 덩어리)을 얼룩으로 키우지 않는다."""
    from studio.grade import auto as G
    rng = np.random.default_rng(7)
    n = 64
    L = np.full((n, n), 70.0) + rng.normal(0, 0.8, (n, n))
    a = 0.5 + np.kron(rng.normal(0, 1.6, (n // 2, n // 2)), np.ones((2, 2)))
    b = 21.0 + np.kron(rng.normal(0, 1.6, (n // 2, n // 2)), np.ones((2, 2)))
    wall = np.clip(G.lab_to_srgb(L, a, b), 0, 1).astype(np.float32)
    face_rgb = [0.72, 0.55, 0.45]                                   # 색상 약 50° — 이미 피부 범위
    face = np.clip(_patch(face_rgb, rng, n=n, noise=0.01), 0, 1)
    img = np.concatenate([wall, face], axis=1)
    st = G.analyze([(0.0, img)], [None])
    st["face_rgb"], st["face_luma"] = face_rgb, 0.6
    c = G.correction_from_stats(st)
    out = G.grade(img, c, G.plan_choice([img], c, "warm_rich", skin_rgb=face_rgb))[:, :n]

    def noise(x):
        _, aa, bb = G.srgb_to_lab(x.reshape(-1, 3))
        return float(np.hypot(aa - aa.mean(), bb - bb.mean()).mean())
    assert noise(out) <= 1.6 * noise(wall), (noise(wall), noise(out))   # 예전 3.4배
    _, _, _, _, hw = _lab(out)
    assert hw >= 75, hw                                               # 분홍(60° 쪽)으로 끌려가지 않는다
