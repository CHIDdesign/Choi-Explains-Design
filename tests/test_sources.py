"""원본 여러 개: 소리 싱크 · 묶음 · 가상 타임라인 · 앵글 고르기 · 클립/얼굴 트랙 · 편집 문법 연동."""
import numpy as np

from studio.edit.grammar import build_short_edit, camera_plan
from studio.media.sources import (GAP, RATE, Cam, Group, Piece, Quality, SourceMap, angle_cut_times, choose_angles,
                                  clips_for, envelope, face_track, group_sources, master_audio_args, match,
                                  visual_scorer)
from studio.models import Span, TimeMap
from studio.render.props import mark_soft_cuts


def _speech(sec: float, seed: int) -> np.ndarray:
    r = np.random.default_rng(seed)
    x = np.zeros(int(sec * RATE), np.float32)
    t = 0.0
    while t < sec - 1:
        d = r.uniform(0.15, 0.6)
        a, b = int(t * RATE), int(min(sec, t + d) * RATE)
        x[a:b] = r.normal(0, r.uniform(0.05, 0.3), b - a)
        t += d + r.uniform(0.05, 0.5)
    return x


def test_match_finds_offset_direction():
    world = _speech(80, 1)
    a = world[5 * RATE:70 * RATE]              # A 는 세상 시각 5초에 녹화 시작
    b = 0.5 * world[2 * RATE:75 * RATE]        # B 는 2초에 시작(3초 먼저) → B 시각 = A 시각 + 3
    m = match(envelope(a), envelope(b))
    assert m.same and abs(m.offset - 3.0) < 0.02, m
    other = _speech(60, 9)
    assert not match(envelope(a), envelope(other)).same


def _take(seed: int, base: list[tuple[float, float, float]]) -> np.ndarray:
    r = np.random.default_rng(seed)
    x = []
    for d, p, amp in base:
        x.append(r.normal(0, amp, int(d * r.uniform(0.85, 1.15) * RATE)))
        x.append(r.normal(0, 0.003, int(p * r.uniform(0.6, 1.4) * RATE)))
    return np.concatenate(x).astype(np.float32)


def test_same_script_separate_takes_are_not_multicam():
    """같은 대본을 비슷한 속도로 따로 찍은 테이크(단어 길이 ±15%)는 전체 상관이 꽤 나와도 시간 차이가 흘러가서
    동시 촬영이 아니다. 진짜 다시점(울림·먼 마이크·잡음)은 모든 창이 같은 차이에서 맞는다."""
    r = np.random.default_rng(0)
    base = [(r.uniform(0.15, 0.6), r.uniform(0.05, 0.5), r.uniform(0.05, 0.3)) for _ in range(300)]
    for s in range(1, 6):
        assert not match(envelope(_take(s, base)), envelope(_take(s + 100, base))).same
    a = _take(1, base)
    ir = np.exp(-np.arange(int(0.4 * RATE)) / (0.08 * RATE)).astype(np.float32)
    far = np.convolve(a, ir / ir.sum())[:len(a)] * 0.3 + 0.1 * a
    b = np.concatenate([np.zeros(int(3.3 * RATE), np.float32), far])
    b = b + np.random.default_rng(6).normal(0, 0.02, len(b)).astype(np.float32)
    m = match(envelope(a), envelope(b))
    assert m.same and m.windows >= 5 and m.consistent >= 0.9 and abs(m.offset - 3.3) < 0.02, m


def test_group_sources_multicam_and_separate_takes():
    world = _speech(90, 2)
    noise = np.random.default_rng(3)
    a = world[4 * RATE:80 * RATE] + noise.normal(0, 0.003, 76 * RATE).astype(np.float32)
    b = 0.4 * world[10 * RATE:86 * RATE] + noise.normal(0, 0.03, 76 * RATE).astype(np.float32)   # 잡음 많은 카메라
    c = _speech(50, 5) + noise.normal(0, 0.003, 50 * RATE).astype(np.float32)                   # 따로 찍음
    sm = group_sources([b, a, c], ["b.mp4", "a.mp4", "c.mp4"], [76.0, 76.0, 50.0], fps=30)
    assert len(sm.groups) == 2 and sm.multicam and not sm.single
    g0, g1 = sm.groups
    assert [c.path for c in g0.cams] == ["a.mp4", "b.mp4"]          # 목소리는 깨끗한 a (묶음 시각 기준)
    assert abs(g0.cams[1].offset - (-6.0)) < 0.03                   # b 는 6초 늦게 시작 → b 시각 = a 시각 − 6
    assert g1.start == round(np.ceil((g0.end + GAP) * 30 - 1e-6) / 30, 6) and g1.cams[0].path == "c.mp4"
    # 가상 시각 ↔ 카메라 시각
    b_cam = g0.cams[1]
    assert abs(sm.to_cam(10.0, b_cam) - 4.0) < 0.03 and abs(sm.from_cam(4.0, b_cam) - 10.0) < 0.03
    assert [c.path for c in sm.candidates(2.0, 5.0)] == ["a.mp4"]   # b 는 6초부터 담았다
    assert {c.path for c in sm.candidates(20.0, 25.0)} == {"a.mp4", "b.mp4"}
    # 묶음 사이 무음으로 넘친 keep 은 잘린다
    keeps = sm.clamp_keeps([Span(70.0, g0.end + 0.8), Span(g1.start - 0.5, g1.start + 3.0)], 30)
    assert keeps[0].end <= g0.end + 1e-6 and keeps[1].start >= g1.start - 1e-6
    # 왕복 직렬화
    assert SourceMap.from_dict(sm.to_dict()).to_dict() == sm.to_dict()


def _two_cam_map() -> SourceMap:
    return SourceMap([Group([Cam(0, "a.mp4", 60.0), Cam(1, "b.mp4", 62.0, offset=1.0)], 0.0, 60.0)])


def _quality(bad: tuple[float, float] = (0, 0), face_s: float = 0.3, sharp: float = 5.0) -> Quality:
    out = []
    for i in range(0, 62 * 4):
        t = i / 4
        blur = bad[0] <= t < bad[1]
        out.append({"t": t, "f": 0.0 if blur else 0.9, "s": face_s, "sh": 2.0 if blur else sharp, "l": 0.5,
                    "c": 0.0, "fr": 0.9})
    return Quality(out)


def test_choose_angles_avoids_bad_angle_and_cross_cuts():
    sm = _two_cam_map()
    # 카메라 0 은 20~32초(카메라 시각) 초점이 나가고 얼굴이 사라짐 → 그 구간은 카메라 1
    q = {0: _quality(bad=(20, 32)), 1: _quality(face_s=0.34)}
    keeps = [Span(0, 6), Span(6.5, 14), Span(14.6, 19), Span(19.5, 31), Span(31.8, 40), Span(40.5, 58)]
    starts = [0, 3, 6.5, 10, 14.6, 19.5, 23, 27, 31.8, 35, 40.5, 45, 50, 54]
    pieces = choose_angles(keeps, sm, q, sentence_starts=starts)
    assert pieces[0].start == 0 and pieces[-1].end == 58
    assert all(p.end > p.start for p in pieces)
    in_bad = [p for p in pieces if p.start < 31 and p.end > 20.5]
    assert in_bad and all(p.cam == 1 for p in in_bad), [(p.start, p.end, p.cam) for p in pieces]
    assert len({p.cam for p in pieces}) == 2
    # 앵글을 바꾼 뒤 최소 유지(품질 저하로 바꾸는 경우 제외) — 샷이 너무 짧게 깜빡이지 않는다
    runs, cur, t0 = [], pieces[0].cam, pieces[0].start
    for p in pieces[1:]:
        if p.cam != cur:
            runs.append(p.start - t0)
            cur, t0 = p.cam, p.start
    assert min(runs) >= 2.5
    # 같은 품질이면 너무 오래 한 앵글에 머물지 않는다(교차 편집)
    even = choose_angles([Span(0, 58)], sm, {0: _quality(), 1: _quality()}, sentence_starts=list(range(0, 58, 4)))
    assert len({p.cam for p in even}) == 2


def test_single_source_is_unchanged():
    sm = SourceMap.one("a.mp4", 30.0)
    keeps = [Span(0.5, 4.0), Span(5.0, 9.0)]
    pieces = choose_angles(keeps, sm, {})
    assert [(p.keep, p.start, p.end, p.cam) for p in pieces] == [(0, 0.5, 4.0, 0), (1, 5.0, 9.0, 0)]
    tm = TimeMap(keeps)
    clips = clips_for(pieces, tm, sm)
    assert [c["src"] for c in clips] == ["media/proxy.mp4"] * 2 and clips[1]["srcStart"] == 5.0
    assert angle_cut_times(pieces, tm) == [] and sm.clamp_keeps(keeps, 30) == keeps


def test_clips_face_and_grammar_follow_angles():
    sm = _two_cam_map()
    keeps = [Span(0, 6), Span(8, 14)]
    tm = TimeMap(keeps)
    pieces = [Piece(0, 0, 3, 0), Piece(0, 3, 6, 1), Piece(1, 8, 14, 1)]
    clips = clips_for(pieces, tm, sm)
    assert [c["src"] for c in clips] == ["media/proxy.mp4", "media/proxy_2.mp4", "media/proxy_2.mp4"]
    assert clips[1]["srcStart"] == 4.0 and clips[1]["start"] == 3.0 and clips[2]["srcStart"] == 9.0
    cuts = angle_cut_times(pieces, tm)
    assert cuts == [3.0]
    faces = {0: [{"t": t, "x": 0.3, "y": 0.4, "s": 0.3} for t in np.arange(0, 60, 0.25)],
             1: [{"t": t, "x": 0.7, "y": 0.4, "s": 0.4} for t in np.arange(0, 62, 0.25)]}
    tr = face_track(pieces, sm, faces)
    xs = {round(d["t"], 2): d["x"] for d in tr}
    assert xs[1.0] == 0.3 and xs[4.0] == 0.7 and xs[10.0] == 0.7
    # 편집 문법: 앵글이 바뀌는 곳은 새 샷(와이드), 그 컷은 소프트 컷이 아니다
    shots = camera_plan(tm, tm.duration, chapter_starts=[], covers=[], sentence_starts=[], angle_cuts=cuts)
    assert any(abs(s["start"] - 3.0) < 1e-6 and s["zoom"] == 1.0 for s in shots)
    mark_soft_cuts(clips, [], [], 0.1)
    assert "soft" not in clips[1]
    ed = build_short_edit(timemap=tm, total=tm.duration, graphics=[], cues=[], moments=[], angle_cuts=cuts)
    assert any(abs(s["start"] - 3.0) < 1e-6 and s["zoom"] == 1.0 for s in ed.camera)


def test_visual_scorer_and_master_audio_args():
    sm = _two_cam_map()
    score = visual_scorer(sm, {0: _quality(bad=(0, 60)), 1: _quality(bad=(0, 62))})
    good = visual_scorer(sm, {0: _quality(), 1: _quality()})
    assert score(5, 8) < good(5, 8)
    assert visual_scorer(sm, {}) is None

    class Info:
        def __init__(self, off):
            self.av_offset, self.has_audio = off, True
    two = SourceMap([Group([Cam(0, "a.mp4", 10.0)], 0.0, 10.0), Group([Cam(1, "b.mp4", 5.0)], 12.0, 5.0)])
    args = master_audio_args(two, {0: Info(0.05), 1: Info(-0.02)}, "out.wav")
    graph = args[args.index("-filter_complex") + 1]
    assert args.count("-i") == 2 and "adelay=50.0" in graph and "atrim=start=0.0200" in graph
    assert "anullsrc" in graph and "atrim=0:2.000000" in graph and "concat=n=3" in graph


def test_blurry_take_in_separate_file_scores_lower_and_audio_timestamps_reset():
    sm = SourceMap([Group([Cam(0, "a.mp4", 62.0)], 0.0, 62.0), Group([Cam(1, "b.mp4", 62.0)], 64.0, 62.0)])
    v = visual_scorer(sm, {0: _quality(sharp=6.0), 1: _quality(sharp=1.0)})
    assert v(5, 8) > v(70, 73) + 0.15          # 따로 찍은 파일의 흐린 테이크는 감점(작업 전체 기준 초점)

    class Info:
        av_offset, has_audio = 0.3, True
    args = master_audio_args(SourceMap.one("a.mp4", 10.0), {0: Info()}, "o.wav")
    graph = args[args.index("-filter_complex") + 1]
    # 늦게 시작한 오디오: 타임스탬프를 먼저 0으로(안 그러면 atrim 이 av_offset 만큼 짧게 잘라 뒤 묶음이 앞당겨짐)
    assert graph.index("asetpts=PTS-STARTPTS") < graph.index("adelay=300.0")


def test_cut_audio_slices_samples_with_fades(tmp_path):
    import wave

    from studio.edit.assemble import cut_audio
    sr = 48000
    x = np.full((sr * 3, 2), 10000, np.int16)
    src = tmp_path / "v.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(x.tobytes())
    keeps = [Span(0.5, 1.0), Span(2.0, 2.5), Span(2.9, 3.4)]      # 마지막은 원본 끝(3초)을 넘음 → 무음으로 채움
    total = cut_audio(None, src, keeps, tmp_path / "o.wav", tmp_path)
    with wave.open(str(tmp_path / "o.wav")) as r:
        y = np.frombuffer(r.readframes(r.getnframes()), np.int16).reshape(-1, 2)
    assert abs(total - 1.5) < 1e-9 and len(y) == int(1.5 * sr)
    assert y[0, 0] == 0 and y[int(0.25 * sr), 0] == 10000        # 이음새마다 페이드 인, 가운데는 원래 값
    assert y[int(0.5 * sr) - 1, 0] == 0 and y[int(0.5 * sr) + 1000, 0] == 10000
    assert np.all(y[int(1.1 * sr):, 0] == 0)                      # 끝을 넘은 부분은 무음(길이는 영상과 같게)
