"""🎼 음악 v2(WP10 — docs/upgrade/04_음악_사운드_엔진_v2.md): 큐 시트 정리 · 시각 변환(침묵 우선) · 큐 창 · 상태별 레벨."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.media.mix import BgmPlan, bgm_gain_curve, bgm_levels  # noqa: E402
from studio.sound import cues as C  # noqa: E402


def _seg_t(n=40, dur=5.0):
    return {i: (i * dur, i * dur + dur - 0.6) for i in range(n)}


RAW = {"suite": "felt", "suite_reason": "느린 고백", "fit_score": 8, "describe": "sparse felt piano", "tempo_bpm": 70,
       "cues": [{"id": "m1", "start_seg": -1, "end_seg": 4, "role": "theme", "energy": 2, "entry": "downbeat",
                 "exit": "into_next", "why_in": "훅", "why_out": "본론"},
                {"id": "m2", "start_seg": 5, "end_seg": 12, "role": "bed", "energy": 1, "entry": "downbeat",
                 "exit": "fade_bar", "why_in": "문제 제기", "why_out": "고백 전"},
                {"id": "m3", "start_seg": 20, "end_seg": 21, "role": "bed", "energy": 2, "entry": "fade_in",
                 "exit": "fade_bar", "why_in": "짧다", "why_out": "짧다"},
                {"id": "m4", "start_seg": 33, "end_seg": -1, "role": "reprise", "energy": 9, "entry": "nope",
                 "exit": "ending", "why_in": "엔딩", "why_out": "종지"}],
       "silences": [{"start_seg": 8, "end_seg": 9, "why": "결론 문장"}],
       "hero": [], "shorts": {"role": "upbeat", "energy": 2, "note": ""}, "notes": ""}


def test_clean_music_validates_enums_and_segments():
    m = C.clean_music(RAW, list(range(40)))
    assert m["cues"][3]["energy"] == 5 and m["cues"][3]["entry"] == "fade_in"     # 범위·enum 밖 → 기본값
    assert m["shorts"]["role"] == "air"                                             # 업비트 같은 값은 없다
    assert C.clean_music({}, [1]) == {}
    gone = C.clean_music({**RAW, "cues": [{**RAW["cues"][1], "start_seg": 99}]}, list(range(40)))
    assert gone["cues"][0]["start_seg"] == 39                                       # 없는 발화 → 가장 가까운 발화


def test_cues_resolve_and_silences_win():
    m = C.clean_music(RAW, list(range(40)))
    seg_t = _seg_t()
    cues, silences = C.resolve(m, seg_t, 200.0, chapter_starts=[24.7], holds=[(140.0, 150.0)])
    ids = [q.id for q in cues]
    assert ids[0] == "m1" and cues[0].start == 0.0
    # 침묵(S8–S9 = 40~49.4+0.4초)이 m2 를 자르고, 잘린 뒷조각(49.8~64.8 → 15초)은 남는다
    m2 = [q for q in cues if q.id == "m2"]
    assert all(not (q.start < 49.0 and q.end > 41.0) for q in m2) and m2
    assert m2[0].start == cues[0].end == 24.8                                       # 겹치면 앞 큐가 이긴다
    assert "m3" not in ids                                                          # 12초 미만은 버린다
    assert cues[-1].id == "m4" and cues[-1].end == 200.0
    # 챕터의 첫 발화면 챕터 카드 −0.3초에 맞춰 들어온다 · 4초 미만 틈은 앞 큐를 이어 붙인다
    only = {**m, "cues": [m["cues"][0], m["cues"][1]], "silences": []}
    only["cues"][0] = {**only["cues"][0], "end_seg": 3, "exit": "fade_bar"}
    c2, _ = C.resolve(only, seg_t, 200.0, chapter_starts=[22.0])
    assert c2[1].start == 21.7 and c2[0].end == 21.7 and c2[0].exit == "into_next"
    share = C.occupancy(cues, 200.0)
    assert 0.2 < share < 0.65, share


def test_cue_window_ramps_and_silence_between():
    cues = [C.MusicCue("m1", 0.0, 20.0, "theme", 2, "downbeat", "fade_bar"),
            C.MusicCue("m2", 40.0, 60.0, "bed", 1, "fade_in", "ending")]
    w = C.cue_windows(cues, 70.0)
    assert w[1000] == 1.0 and w[3000] == 0.0 and w[6500] == 0.0
    assert 0.0 < w[4050] < 0.5                                                      # fade_in 2초
    assert w[25] > 0.5                                                              # downbeat 0.3초


def test_gain_curve_follows_cues_and_roles():
    total = 60.0
    act = np.zeros(int(total * 100) + 1, np.float32)
    act[:2000] = 1.0                                                                # 0~20초 말, 그 뒤 말 없음
    under, gap, swell = bgm_levels(-20.0, -20.0)
    plan = BgmPlan(path="x", under_db=under, gap_db=gap, swell_db=swell,
                   cues=[{"id": "m1", "start": 0.0, "end": 30.0, "role": "theme", "entry": "downbeat", "exit": "fade_bar"},
                         {"id": "m2", "start": 40.0, "end": 58.0, "role": "air", "entry": "fade_in", "exit": "ending"}])
    g = bgm_gain_curve(act, plan, total)
    assert g[3500] < -50                                                            # 큐 사이 = 침묵
    assert abs(g[1000] - under) < 1.5                                               # 말 아래 bed 레벨
    assert g[2600] > g[1000] + 6                                                    # theme 의 말 없는 곳 = feature
    assert g[4800] < under - 6                                                      # air 는 말 아래보다 낮다


def test_ingest_gate_rejects_dense_or_registered(tmp_path):
    """입고 게이트(04b 5절): 빽빽한 곡·Content ID 등록곡·증빙 없는 곡은 탈락, 성긴 곡은 통과."""
    import shutil
    import wave
    import pytest
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg 없음")
    sys.path.insert(0, str(ROOT / "scripts"))
    import sound_ingest as SI

    def write(path, bpm, notes_per_beat=1, dur=40, amp=0.3):
        sr = 48000
        x = np.zeros(sr * dur)
        step = 60 / bpm / notes_per_beat
        k = 0
        while k * step < dur - 3:
            i = int(k * step * sr)
            n = min(len(x) - i, int(sr * 1.5))
            env = np.exp(-np.arange(n) / sr / 0.5) * (0.4 + 0.6 * (k % 8 == 0))     # 마디 첫 음만 크게(LRA)
            x[i:i + n] += amp * env * np.sin(2 * np.pi * (196 + 22 * (k % 5)) * np.arange(n) / sr)
            k += 1
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
        return path
    proof = tmp_path / "proof.txt"
    proof.write_text("own work")
    sparse = SI.measure(write(tmp_path / "sparse.wav", 70, 1))
    dense = SI.measure(write(tmp_path / "dense.wav", 128, 4))
    assert 60 <= sparse["bpm"] <= 80 and sparse["onsets_per_s"] < dense["onsets_per_s"]
    ok = dict((n, o) for n, o, _ in SI.gate(sparse, role="theme", suite="felt", license_class="A", proof=str(proof),
                                            content_id="none", approved_by="운영자"))
    assert ok["밀도"] and ok["템포"] and ok["권리 등급"] and ok["Content ID"]
    bad = dict((n, o) for n, o, _ in SI.gate(dense, role="bed", suite="felt", license_class="C", proof="",
                                             content_id="registered", approved_by=""))
    assert not bad["밀도"] and not bad["권리 등급"] and not bad["Content ID"] and not bad["청취 승인"]


def test_music_cues_survive_normalize():
    """계획의 새 키 music_cues 는 normalize_long 을 다시 거쳐도 남는다(CLAUDE.md 규칙) — 지워진 발화는 가까운 남은 발화로."""
    from studio.director.plan import normalize_long
    from studio.models import Utterance
    utts = [Utterance(id=i, start=i * 4.0, end=i * 4.0 + 3.0, text=f"문장 {i}", asr_text=f"문장 {i}",
                      status="retake" if i == 3 else "keep") for i in range(8)]
    raw = {"title": "t", "chapters": [], "graphics": [], "music_cues": dict(RAW, cues=[dict(RAW["cues"][1], start_seg=3)])}
    plan = normalize_long(raw, utts, [])
    assert plan["music_cues"]["cues"][0]["start_seg"] in (2, 4) and plan["music_cues"]["suite"] == "felt"
    again = normalize_long(dict(raw, music_cues=plan["music_cues"]), utts, [])
    assert again["music_cues"] == plan["music_cues"]
    assert normalize_long({"title": "t"}, utts, [])["music_cues"] == {}


def test_fallback_cue_sheet_resolves():
    """음악 감독이 없을 때의 규칙 큐 시트: 오프닝~타이틀 theme · 챕터 bed · 마지막 reprise, 나머지 침묵(점유율 100% 아님)."""
    m = C.clean_music(C.fallback_music([0, 12, 24], 3, 39, reprise_seg=36), list(range(40)))
    cues, _ = C.resolve(m, _seg_t(), 200.0)
    roles = [q.role for q in cues]
    assert roles[0] == "theme" and roles[-1] == "reprise" and "bed" in roles
    assert 0.2 < C.occupancy(cues, 200.0) < 0.65


def test_gate_d_fails_on_20261001_run():
    """10/1 실행의 수치: 목소리−음악 15.5 LU · 곡 3개 · 점유율 100% · Content ID 등록 곡(D) · 목소리 −21.8 LUFS."""
    from studio import gate
    under = -21.0                        # 말 아래 음악 = −14 + under_db
    r = gate.d1_voice_over_music(-21.8, -21.8 - 15.5 + 14.0)
    assert not r.ok and abs(r.measured["diff_lu"] - 15.5) < 0.05 and r.level == "repair"
    assert gate.d1_voice_over_music(-16.0, -16.0 - 20.0 + 14.0).ok
    assert gate.d1_voice_over_music(None, under).skipped
    assert not gate.d3_one_track(3).ok and gate.d3_one_track(1).ok
    assert not gate.d8_occupancy(1.0, []).ok
    assert gate.d8_occupancy(0.5, [{"id": "m1", "why_in": "훅", "why_out": "본론"}]).ok
    assert not gate.d8_occupancy(0.5, [{"id": "m1", "why_in": "훅", "why_out": ""}]).ok
    r = gate.d9_license([("bgm_calm_piano", "D"), ("tick", "A")])
    assert not r.ok and r.level == "block" and "bgm_calm_piano" in r.message
    assert gate.d9_license([("내 곡.mp3", "own"), ("tick", "A"), ("paper", "C")]).ok
    assert not gate.d9_license([("unknown", "?")]).ok
    assert not gate.d10_voice_level(-21.8).ok and gate.d10_voice_level(-16.4).ok
    assert not gate.d6_fit(5).ok and gate.d6_fit(8).ok and gate.d6_fit(None).skipped


def test_gate_d5_counts_ticks_in_any_60s_window():
    """목록 틱을 포함해 60초 창 어디서도 3개 이하(펀치 구간 밖), 같은 파일 연속 금지."""
    from studio import gate
    cues = [(10.0, "a.wav"), (30.0, "b.wav"), (50.0, "c.wav"), (75.0, "d.wav")]
    assert gate.d5_sfx_density(cues).ok
    r = gate.d5_sfx_density(cues + [(55.0, "e.wav")])
    assert not r.ok and r.measured["max_per_window"] == 4
    assert gate.d5_sfx_density(cues + [(55.0, "e.wav")], punch=[(54.0, 56.0)]).ok
    assert not gate.d5_sfx_density([(10.0, "a.wav"), (40.0, "a.wav")]).ok


def test_short_music_role_from_sheet():
    """숏폼은 롱폼과 같은 곡 — 큐 시트의 shorts.role: none 이면 음악 없음, air 면 전체가 air 큐. fit 7 미만도 air."""
    from studio.pipeline import Pipeline
    pl = Pipeline.__new__(Pipeline)
    m = {"short": True, "total": 40.0}
    assert pl._apply_music_sheet(BgmPlan(path="x.wav"), {"shorts": {"role": "none"}}, m) is None
    b = pl._apply_music_sheet(BgmPlan(path="x.wav"), {"shorts": {"role": "air"}, "fit_score": 8}, m)
    assert b is not None and b.cues == [{"id": "s1", "start": 0.0, "end": 40.0, "role": "air", "energy": 1,
                                         "entry": "fade_in", "exit": "ending"}]
    b = pl._apply_music_sheet(BgmPlan(path="x.wav"), {"shorts": {"role": "bed"}, "fit_score": 8}, m)
    assert b is not None and b.cues == []
    b = pl._apply_music_sheet(BgmPlan(path="x.wav"), {"shorts": {"role": "bed"}, "fit_score": 5}, m)
    assert b.cues and b.cues[0]["role"] == "air"


def test_silence_inside_cue_is_a_pause_not_a_drop():
    """짧은 영상 E2E 에서 홀드·강도 3 침묵이 큐를 12초 미만 조각으로 잘라 음악이 통째로 사라졌다 — 12초는 쓴 큐의 길이에만,
    침묵이 자른 조각은 4초 이상이면 남는다."""
    seg_t = _seg_t(20)
    m = C.clean_music({"cues": [{"id": "m1", "start_seg": -1, "end_seg": 3, "role": "theme", "why_in": "훅", "why_out": "본론"}]},
                      list(range(20)))
    cues, sil = C.resolve(m, seg_t, 100.0, strong=[(9.0, 10.5)])
    assert [q.id for q in cues] == ["m1", "m1"] and cues[0].end <= 6.5 + 1e-6 and cues[1].start >= 11.1 - 1e-6
    tiny, _ = C.resolve(m, seg_t, 100.0, strong=[(3.5, 15.5)])
    assert all(q.end - q.start >= C.MIN_PIECE for q in tiny)
