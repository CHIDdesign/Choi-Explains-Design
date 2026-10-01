"""목소리 분석 → 최소 맞춤 보정(studio/media/voice.py): 깨끗한 목소리는 손대지 않고, 문제가 있는 만큼만 조금 고친다."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.media.voice import (BANDS, REF_DELTA, VoiceRecipe, analyze_voice,  # noqa: E402
                                loudness_gain, plan_voice_recipe)

RATE = 24000


def _speech(seconds: float = 12.0, *, seed: int = 1, tilt: dict[str, float] | None = None,
            dyn_db: float = 6.0, noise_db: float | None = None) -> np.ndarray:
    """LTASS 모양의 가짜 목소리: 대역별 잡음을 기준 상대 레벨로 섞고 음절(4Hz)·문장(쉼) 변조.
    tilt: 대역별 추가 dB(예: {"presence": -8} 이면 흐린 마이크). dyn_db: 문장마다 음량이 이만큼 오르내림."""
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    out = np.zeros(n, np.float32)
    ref = {"body": 0.0, **REF_DELTA}
    freqs = np.fft.rfftfreq(n, 1.0 / RATE)
    spec = np.zeros(len(freqs), np.complex64)
    for name, (lo, hi) in BANDS.items():
        m = (freqs >= lo) & (freqs < hi)
        lvl = ref[name] + (tilt or {}).get(name, 0.0)
        # 대역 파워 = 10^(lvl/10) → 빈당 진폭은 빈 수로 나눈다
        amp = np.sqrt(10 ** (lvl / 10) / max(1, m.sum()))
        spec[m] = amp * (rng.standard_normal(m.sum()) + 1j * rng.standard_normal(m.sum()))
    out = np.fft.irfft(spec, n).astype(np.float32)
    out /= np.abs(out).max() + 1e-9
    # 음절 변조(4Hz) + 문장(2.5초 말, 0.7초 쉼) + 문장마다 음량 변화
    syl = 0.55 + 0.45 * np.maximum(0, np.sin(2 * np.pi * 4.0 * t))
    env = np.zeros(n, np.float32)
    k = 0
    pos = 0.0
    while pos < seconds:
        a, b = int(pos * RATE), int(min(seconds, pos + 2.5) * RATE)
        g = 10 ** ((dyn_db / 2) * (1 if k % 2 == 0 else -1) / 20)
        env[a:b] = g
        pos += 3.2
        k += 1
    out = out * syl * env * 0.25
    if noise_db is not None:
        out = out + rng.standard_normal(n).astype(np.float32) * 10 ** (noise_db / 20)
    return out.astype(np.float32)


def test_clean_voice_is_left_alone():
    st = analyze_voice(_speech(), RATE)
    assert st.ok and st.snr >= 38, st.to_dict()
    assert all(abs(v) < 2.5 for v in st.deviation.values()), st.deviation
    r = plan_voice_recipe(st)
    assert r.denoise == "none" and not r.eq and not r.air_shelf and not r.deess and not r.comp_ratio
    assert r.highpass == 50 and r.is_flat()
    f = r.filter()
    assert f == "highpass=f=50:p=1"


def test_dull_mic_gets_small_presence_boost_only():
    st = analyze_voice(_speech(tilt={"presence": -7, "air": -9}), RATE)
    r = plan_voice_recipe(st)
    boosts = [(f, g) for f, _, g in r.eq if g > 0]
    assert boosts and boosts[0][0] == 3500 and 0 < boosts[0][1] <= 2.0, r.summary()
    assert 0 < r.air_shelf <= 1.5
    assert all(g >= -2.5 for _, _, g in r.eq)


def test_boxy_room_gets_gentle_lowmid_cut_never_bass_boost():
    st = analyze_voice(_speech(tilt={"lowmid": 8}), RATE)
    r = plan_voice_recipe(st)
    cuts = [(f, g) for f, _, g in r.eq if g < 0]
    assert cuts and cuts[0][0] == 230 and -2.5 <= cuts[0][1] < 0, r.summary()
    assert not any(f < 300 and g > 0 for f, _, g in r.eq)


def test_noise_level_decides_denoise_strength():
    quiet = plan_voice_recipe(analyze_voice(_speech(noise_db=-70), RATE))
    assert quiet.denoise == "none"
    some = plan_voice_recipe(analyze_voice(_speech(noise_db=-48), RATE))
    assert some.denoise in ("light", "rnnoise"), some.summary()
    loud = plan_voice_recipe(analyze_voice(_speech(noise_db=-30), RATE))
    assert loud.denoise.startswith("rnnoise") and loud.denoise_mix <= 0.7, loud.summary()
    # 모델이 없으면 afftdn 으로, 있으면 arnndn 으로
    assert "afftdn" in loud.filter() and "arnndn" not in loud.filter()
    assert "arnndn=m=/m/x.rnnn:mix=0.70" in loud.filter("/m/x.rnnn")


def test_wide_dynamics_gets_gentle_compressor_only():
    calm = plan_voice_recipe(analyze_voice(_speech(dyn_db=4), RATE))
    assert calm.comp_ratio == 0
    wide = plan_voice_recipe(analyze_voice(_speech(dyn_db=18), RATE))
    assert 1.5 <= wide.comp_ratio <= 2.0, wide.summary()
    assert "makeup=1" in wide.filter() and ("ratio=2.00" in wide.filter() or "ratio=1.50" in wide.filter())


def test_loudness_gain_is_linear_and_caps_limiting():
    g, lim = loudness_gain({"input_i": "-24.0", "input_tp": "-10.0"}, -16.0)
    assert g == 8.0 and lim == 0.0
    g, lim = loudness_gain({"input_i": "-30.0", "input_tp": "-3.0"}, -16.0)   # 피크가 +9.5dB 넘침 → 게인 줄임
    assert lim == 6.0 and g < 14.0
    assert loudness_gain({}, -16.0) == (0.0, 0.0)


def test_recipe_filter_is_accepted_by_ffmpeg():
    if not shutil.which("ffmpeg"):
        import pytest
        pytest.skip("ffmpeg 없음")
    r = VoiceRecipe(highpass=80, highpass_poles=2, declip=True, denoise="light", denoise_nr=5, noise_floor=-58,
                    eq=[(230.0, 1.0, -1.2), (3500.0, 1.2, 1.1)], air_shelf=0.8, deess=0.15, comp_ratio=1.5,
                    comp_threshold=-22)
    chain = r.filter() + ",volume=+3.00dB,alimiter=limit=0.84:attack=5:release=80:level=false"
    res = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anoisesrc=d=1:c=pink:r=48000",
                          "-af", chain, "-f", "null", "-"], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
