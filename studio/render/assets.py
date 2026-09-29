"""렌더에 쓰는 작은 에셋을 절차적으로 생성(저작권 걱정 없음): 필름 그레인 타일, 은은한 효과음, 폰트 복사."""
from __future__ import annotations

import shutil
import wave
from pathlib import Path

import numpy as np

from ..paths import RENDERER_FONTS

SR = 48000


def copy_fonts(dst: Path) -> list[str]:
    dst.mkdir(parents=True, exist_ok=True)
    names = []
    for f in RENDERER_FONTS.glob("*.woff2"):
        target = dst / f.name
        if not target.exists() or target.stat().st_size != f.stat().st_size:
            shutil.copyfile(f, target)
        names.append(f.name)
    if not names:
        raise FileNotFoundError(
            f"폰트가 없습니다: {RENDERER_FONTS}. renderer 폴더에서 'npm install' 을 먼저 실행하세요.")
    return names


def make_grain(dst: Path, n: int = 4, w: int = 960, h: int = 540, seed: int = 7) -> list[str]:
    from PIL import Image
    dst.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        p = dst / f"grain_{i}.png"
        if not p.exists():
            noise = rng.normal(128, 38, (h, w))
            # 필름 입자처럼 아주 약하게 뭉치게
            noise = (noise + np.roll(noise, 1, axis=0) * 0.35 + np.roll(noise, 1, axis=1) * 0.35) / 1.7
            img = np.clip(noise, 0, 255).astype(np.uint8)
            Image.fromarray(img, "L").save(p, optimize=True)
        out.append(p.name)
    return out


def _write_wav(path: Path, mono: np.ndarray) -> None:
    mono = np.clip(mono, -1, 1)
    pcm = (mono * 32767 * 0.9).astype(np.int16)
    stereo = np.stack([pcm, pcm], axis=1)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(stereo.tobytes())


def _lowpass(x: np.ndarray, cutoff: np.ndarray) -> np.ndarray:
    """시간에 따라 변하는 1차 저역통과(바람 소리 스윕용)."""
    y = np.zeros_like(x)
    acc = 0.0
    for i in range(len(x)):
        a = 1 - np.exp(-2 * np.pi * cutoff[i] / SR)
        acc += a * (x[i] - acc)
        y[i] = acc
    return y


def make_sfx(dst: Path) -> dict[str, str]:
    """whoosh: 그래픽 전환 / tick: 목록 항목 / thud: 챕터 카드"""
    dst.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(3)
    files = {}
    p = dst / "whoosh.wav"
    if not p.exists():
        n = int(SR * 0.42)
        t = np.linspace(0, 1, n)
        noise = rng.normal(0, 1, n)
        cutoff = 400 + 5200 * np.sin(np.pi * t) ** 2
        x = _lowpass(noise, cutoff)
        env = np.sin(np.pi * t) ** 1.6
        x = x * env
        _write_wav(p, x / (np.abs(x).max() + 1e-9) * 0.55)
    files["whoosh"] = p.name
    p = dst / "tick.wav"
    if not p.exists():
        n = int(SR * 0.08)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * 1850 * t) * np.exp(-t * 90) + 0.3 * rng.normal(0, 1, n) * np.exp(-t * 300)
        _write_wav(p, x / (np.abs(x).max() + 1e-9) * 0.35)
    files["tick"] = p.name
    p = dst / "thud.wav"
    if not p.exists():
        n = int(SR * 0.6)
        t = np.arange(n) / SR
        f = 62 * np.exp(-t * 2.2) + 38
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 6.5)
        _write_wav(p, x / (np.abs(x).max() + 1e-9) * 0.7)
    files["thud"] = p.name
    return files
