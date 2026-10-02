"""절차적 효과음(인터넷 없이도 항상 동작하는 기본 세트).

내려받은 효과음(Pixabay 등)이 없거나 실패했을 때 쓰는 대체품이다. 모두 48kHz 스테레오 WAV 이고,
파일마다 '피크 시각'을 함께 돌려준다(whoosh 의 피크를 컷 지점에 맞추기 위해).
"""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Callable

import numpy as np

SR = 48000


def _write(path: Path, x: np.ndarray, stereo_width: float = 0.0) -> None:
    x = np.asarray(x, np.float32)
    pk = float(np.abs(x).max()) or 1.0
    x = x / pk * 0.89
    left = x
    right = x
    if stereo_width > 0:
        d = int(SR * 0.0007 * stereo_width)
        right = np.concatenate([np.zeros(d, np.float32), x[:-d]]) if d else x
    pcm = (np.stack([left, right], axis=1) * 32767).astype(np.int16)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def _onepole(x: np.ndarray, cutoff: np.ndarray | float, high: bool = False) -> np.ndarray:
    """시간에 따라 변하는 1차 필터(블록 단위로 계수 갱신 → 파이썬 루프를 짧게)."""
    n = len(x)
    cut = np.broadcast_to(np.asarray(cutoff, np.float64), (n,))
    y = np.empty(n, np.float64)
    acc = 0.0
    blk = 64
    for i0 in range(0, n, blk):
        a = 1 - np.exp(-2 * np.pi * float(cut[i0]) / SR)
        seg = x[i0:i0 + blk]
        out = np.empty(len(seg))
        for k, v in enumerate(seg):
            acc += a * (v - acc)
            out[k] = acc
        y[i0:i0 + blk] = out
    return (x - y) if high else y


def _band(noise: np.ndarray, lo: np.ndarray | float, hi: np.ndarray | float) -> np.ndarray:
    return _onepole(_onepole(noise, hi), lo, high=True)


def _env(n: int, attack: float, peak_at: float, decay_pow: float = 2.0) -> np.ndarray:
    t = np.linspace(0, 1, n)
    rise = np.clip(t / max(1e-3, peak_at), 0, 1) ** attack
    fall = np.clip((1 - t) / max(1e-3, 1 - peak_at), 0, 1) ** decay_pow
    return np.where(t <= peak_at, rise, fall)


def whoosh(dur: float = 0.5, peak: float = 0.55, lo: float = 250, hi: float = 5200, seed: int = 1) -> tuple[np.ndarray, float]:
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    t = np.linspace(0, 1, n)
    sweep = np.exp(-((t - peak) ** 2) / 0.05)
    cut_hi = lo + (hi - lo) * sweep
    x = _band(rng.normal(0, 1, n), lo * 0.6, cut_hi) * _env(n, 2.2, peak, 1.8)
    return x, dur * peak


def swoosh(seed: int = 2) -> tuple[np.ndarray, float]:
    rng = np.random.default_rng(seed)
    n = int(SR * 0.2)
    t = np.linspace(0, 1, n)
    x = _band(rng.normal(0, 1, n), 1500, 3000 + 7000 * t) * _env(n, 1.5, 0.35, 2.5)
    return x, 0.2 * 0.35


def pop(seed: int = 3) -> tuple[np.ndarray, float]:
    n = int(SR * 0.14)
    t = np.arange(n) / SR
    f = 320 + 700 * np.exp(-t * 45)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 38)
    rng = np.random.default_rng(seed)
    x[:240] += rng.normal(0, 0.25, 240) * np.linspace(1, 0, 240)
    return x, 0.004


def click(seed: int = 4) -> tuple[np.ndarray, float]:
    n = int(SR * 0.05)
    t = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    x = 0.6 * np.sin(2 * np.pi * 2600 * t) * np.exp(-t * 160) + _onepole(rng.normal(0, 1, n), 6000) * np.exp(-t * 260)
    return x, 0.001


def riser(dur: float = 1.6, seed: int = 5) -> tuple[np.ndarray, float]:
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    t = np.linspace(0, 1, n)
    noise = _band(rng.normal(0, 1, n), 300 + 1500 * t, 1500 + 9000 * t ** 2)
    f = 180 * (2 ** (3 * t))
    tone = 0.35 * np.sin(2 * np.pi * np.cumsum(f) / SR)
    x = (noise + tone) * (t ** 2.2)
    x[-int(SR * 0.02):] *= np.linspace(1, 0, int(SR * 0.02))
    return x, dur * 0.99


def impact(seed: int = 6) -> tuple[np.ndarray, float]:
    rng = np.random.default_rng(seed)
    n = int(SR * 1.1)
    t = np.arange(n) / SR
    f = 38 + 60 * np.exp(-t * 9)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
    hit = _onepole(rng.normal(0, 1, n), 2200) * np.exp(-t * 22)
    tail = _onepole(rng.normal(0, 1, n), 900) * np.exp(-t * 4.5) * 0.25
    return sub * 0.9 + hit * 0.6 + tail, 0.01


def sub_drop(seed: int = 7) -> tuple[np.ndarray, float]:
    n = int(SR * 1.3)
    t = np.arange(n) / SR
    f = 30 + 70 * np.exp(-t * 2.8)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.4)
    x[:200] *= np.linspace(0, 1, 200)
    return x, 0.02


def ding(seed: int = 8) -> tuple[np.ndarray, float]:
    n = int(SR * 1.4)
    t = np.arange(n) / SR
    x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, a, d in
            [(1318.5, 1.0, 3.2), (1975.5, 0.45, 4.5), (2637.0, 0.2, 7.0), (3950.0, 0.08, 9.0)])
    x[:96] *= np.linspace(0, 1, 96)
    return x, 0.003


def typing(seed: int = 9) -> tuple[np.ndarray, float]:
    rng = np.random.default_rng(seed)
    n = int(SR * 1.2)
    x = np.zeros(n)
    t = 0.02
    while t < 1.1:
        c, _ = click(seed=int(t * 1000))
        c = c * rng.uniform(0.5, 1.0)
        i = int(t * SR)
        x[i:i + len(c)] += c[: n - i]
        t += rng.uniform(0.06, 0.14)
    return x, 0.02


def shutter(seed: int = 10) -> tuple[np.ndarray, float]:
    c1, _ = click(seed)
    c2, _ = click(seed + 1)
    n = int(SR * 0.22)
    x = np.zeros(n)
    x[: len(c1)] += c1
    j = int(SR * 0.09)
    x[j:j + len(c2)] += c2 * 0.8
    return x, 0.001


def reverse(seed: int = 11) -> tuple[np.ndarray, float]:
    x, _ = ding(seed)
    rng = np.random.default_rng(seed)
    n = len(x)
    t = np.arange(n) / SR
    wash = _onepole(rng.normal(0, 1, n), 5000) * np.exp(-t * 3.0) * 0.5
    y = (x + wash)[::-1]
    return y, (n - 1) / SR


def glitch(seed: int = 12) -> tuple[np.ndarray, float]:
    rng = np.random.default_rng(seed)
    n = int(SR * 0.28)
    x = np.zeros(n)
    i = 0
    while i < n:
        L = int(rng.uniform(0.01, 0.04) * SR)
        f = rng.uniform(200, 2400)
        seg = np.sign(np.sin(2 * np.pi * f * np.arange(L) / SR)) * rng.uniform(0.2, 1.0)
        x[i:i + L] = seg[: n - i]
        i += L + int(rng.uniform(0, 0.02) * SR)
    return _onepole(x, 7000), 0.01


def paper(seed: int = 13) -> tuple[np.ndarray, float]:
    rng = np.random.default_rng(seed)
    n = int(SR * 0.45)
    t = np.linspace(0, 1, n)
    x = _band(rng.normal(0, 1, n), 800, 6000) * (_env(n, 1.2, 0.3, 2.0) * (0.6 + 0.4 * np.abs(np.sin(40 * t))))
    return x, 0.45 * 0.3


# --- 문구 팔레트 v2(docs/upgrade/04c 8절) — 화면이 크림 종이·잉크·테이프이므로 소리도 종이·연필·도장 ----------------

def paper_slide(seed: int = 21, dur: float = 0.36) -> tuple[np.ndarray, float]:
    """종이가 책상 위를 미끄러진다: 대역 잡음 800~6000 Hz + 불규칙 엔벨로프, 0.25~0.45초."""
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    t = np.linspace(0, 1, n)
    grain = 0.55 + 0.45 * np.abs(np.sin(2 * np.pi * rng.uniform(18, 30) * t + rng.uniform(0, 3)))
    x = _band(rng.normal(0, 1, n), 800, 6000) * _env(n, 1.1, 0.35, 2.2) * grain
    return x, dur * 0.35


def paper_place(seed: int = 22) -> tuple[np.ndarray, float]:
    """종이를 내려놓는 낮은 '톡': 90~140 Hz 감쇠 사인 40 ms + 2~5 kHz 잡음 15 ms."""
    rng = np.random.default_rng(seed)
    n = int(SR * 0.3)
    t = np.arange(n) / SR
    f = rng.uniform(90, 140)
    body = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.04)
    tick = _band(rng.normal(0, 1, n), 2000, 5000) * np.exp(-t / 0.015) * 0.5
    return body + tick, 0.004


def page_turn(seed: int = 23) -> tuple[np.ndarray, float]:
    """페이지를 한 번 넘긴다: 미끄러짐 두 번을 0.25초 간격으로, 둘째를 더 낮게."""
    a, _ = paper_slide(seed, 0.4)
    b, _ = paper_slide(seed + 7, 0.45)
    j = int(SR * 0.25)
    x = np.zeros(j + len(b))
    x[: len(a)] += a
    x[j:] += _onepole(b, 2500) * 0.8
    return x, 0.25 + 0.45 * 0.35


def pencil_stroke(seed: int = 24, dur: float = 0.45) -> tuple[np.ndarray, float]:
    """연필이 선을 긋는다: 3~7 kHz 대역 잡음에 20~40 Hz 불규칙 진폭 변조."""
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    t = np.arange(n) / SR
    am = 0.55 + 0.45 * np.sin(2 * np.pi * rng.uniform(20, 40) * t + rng.normal(0, 0.6, n).cumsum() * 0.01)
    x = _band(rng.normal(0, 1, n), 3000, 7000) * am * _env(n, 0.6, 0.15, 1.4)
    return x, dur * 0.15


def pencil_tick(seed: int = 25) -> tuple[np.ndarray, float]:
    """짧은 체크: 대역 잡음 12 ms."""
    rng = np.random.default_rng(seed)
    n = int(SR * 0.06)
    t = np.arange(n) / SR
    return _band(rng.normal(0, 1, n), 2500, 6500) * np.exp(-t / 0.012), 0.002


def stamp(seed: int = 26) -> tuple[np.ndarray, float]:
    """고무 도장(부드럽게): 110 Hz 감쇠 사인 80 ms + 저역 잡음."""
    rng = np.random.default_rng(seed)
    n = int(SR * 0.35)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 110 * t) * np.exp(-t / 0.08)
    thud = _onepole(rng.normal(0, 1, n), 600) * np.exp(-t / 0.05) * 0.6
    return body + thud, 0.006


# (카테고리, 파일명, 생성기) — 문구 팔레트만 합성한다. tape·print_place·air_soft·tonal·ident 는 합성하지 않는다(없으면 무음)
SYNTHS: list[tuple[str, str, Callable[[], tuple[np.ndarray, float]]]] = [
    ("paper_slide", "paper_slide_1", lambda: paper_slide(21)),
    ("paper_slide", "paper_slide_2", lambda: paper_slide(31, 0.3)),
    ("paper_slide", "paper_slide_3", lambda: paper_slide(41, 0.42)),
    ("paper_place", "paper_place_1", lambda: paper_place(22)),
    ("paper_place", "paper_place_2", lambda: paper_place(32)),
    ("page_turn", "page_turn_1", lambda: page_turn(23)),
    ("pencil_stroke", "pencil_stroke_1", lambda: pencil_stroke(24)),
    ("pencil_stroke", "pencil_stroke_2", lambda: pencil_stroke(34, 0.35)),
    ("pencil_tick", "pencil_tick_1", lambda: pencil_tick(25)),
    ("pencil_tick", "pencil_tick_2", lambda: pencil_tick(35)),
    ("stamp", "stamp_1", lambda: stamp(26)),
]
# 예전 합성음(UI·예고편 소리 — 쓰지 않는다. 호환을 위해 함수만 남긴다)
LEGACY_SYNTHS: list[tuple[str, str, Callable[[], tuple[np.ndarray, float]]]] = [
    ("whoosh_soft", "whoosh_soft", lambda: whoosh(0.55, 0.55, 200, 4200, 1)),
    ("whoosh_fast", "whoosh_fast", lambda: whoosh(0.32, 0.6, 400, 7000, 21)),
    ("whoosh_deep", "whoosh_deep", lambda: whoosh(0.8, 0.5, 90, 2400, 31)),
    ("swoosh_short", "swoosh_short", swoosh),
    ("pop", "pop", pop),
    ("click", "click", click),
    ("riser", "riser", riser),
    ("impact", "impact", impact),
    ("sub_drop", "sub_drop", sub_drop),
    ("ding", "ding", ding),
    ("typing", "typing", typing),
    ("camera_shutter", "shutter", shutter),
    ("reverse", "reverse", reverse),
    ("glitch", "glitch", glitch),
    ("paper", "paper", paper),
]


def build(dst: Path) -> list[dict]:
    """모든 절차적 효과음을 dst 에 만든다(이미 있으면 건너뜀). 반환: 라이브러리 항목."""
    out = []
    for cat, name, fn in SYNTHS:
        p = dst / f"{name}.wav"
        x, peak = fn()
        if not p.exists():
            _write(p, x, stereo_width=1.0 if cat.startswith("whoosh") else 0.0)
        out.append({"id": f"synth_{name}", "category": cat, "path": str(p), "peak_s": round(float(peak), 4),
                    "duration": round(len(x) / SR, 3), "source": "synth"})
    return out
