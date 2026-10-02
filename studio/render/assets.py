"""렌더에 쓰는 작은 에셋을 절차적으로 생성(저작권 걱정 없음): 필름 그레인 타일, 종이 스킨의 구겨진 종이 텍스처,
은은한 효과음, 폰트 복사."""
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


PAPER_VERSION = 2


def _box_blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """가우시안 근사(상자 흐림 3회, numpy 만)."""
    r = max(1, int(round(sigma * 0.87)))
    out = a.astype(np.float32)
    for _ in range(3):
        for ax in (0, 1):
            pad = [(0, 0), (0, 0)]
            pad[ax] = (r + 1, r)
            c = np.cumsum(np.pad(out, pad, mode="edge"), axis=ax, dtype=np.float64)
            hi = np.take(c, np.arange(2 * r + 1, c.shape[ax]), axis=ax)
            lo = np.take(c, np.arange(0, c.shape[ax] - 2 * r - 1), axis=ax)
            out = ((hi - lo) / (2 * r + 1)).astype(np.float32)
    return out


def _smooth_noise(w: int, h: int, cells_x: int, rng: np.random.Generator) -> np.ndarray:
    from PIL import Image
    cells_y = max(2, round(cells_x * h / w))
    r = rng.normal(0, 1, (cells_y + 3, cells_x + 3)).astype(np.float32)
    img = Image.fromarray(r, "F").resize((w + w // cells_x * 3, h + h // cells_y * 3), Image.BICUBIC)
    ox, oy = w // cells_x, h // cells_y
    return np.asarray(img, np.float32)[oy:oy + h, ox:ox + w]


def crumpled_paper(w: int = 1920, h: int = 1080, *, base: tuple[int, int, int] = (43, 43, 48), seed: int = 11,
                   creases: int = 90, contrast: float = 1.0) -> np.ndarray:
    """구겨진 종이 질감(사용자 레퍼런스의 짙은 차콜 종이: 평균 RGB 40·40·45, 밝기 편차 ±3~12).
    ① 부드럽게 굽은 면(저주파 높이맵의 음영) ② 가늘고 날카로운 접힘선(무작위 보행 선: 어두운 골 + 1px 밝은 능선
    + 한쪽으로 번지는 그늘) ③ 종이 섬유 입자. 절차적 생성이라 저작권 걱정이 없다."""
    from PIL import Image, ImageDraw, ImageFilter
    rng = np.random.default_rng(seed)
    height = _smooth_noise(w, h, 7, rng) * 1.0 + _smooth_noise(w, h, 18, rng) * 0.45
    gy, gx = np.gradient(height)
    lobes = gx * -0.6 + gy * -0.8
    lobes /= np.percentile(np.abs(lobes), 98) + 1e-6
    dark = Image.new("L", (w, h), 0)
    light = Image.new("L", (w, h), 0)
    wedge = Image.new("L", (w, h), 0)
    dd, ld, wd = ImageDraw.Draw(dark), ImageDraw.Draw(light), ImageDraw.Draw(wedge)
    starts: list[tuple[float, float]] = []
    for k in range(creases):
        if starts and rng.random() < 0.35:                       # 기존 접힘선에서 갈라져 나감
            x, y = starts[rng.integers(len(starts))]
        else:
            x, y = rng.uniform(-50, w + 50), rng.uniform(-50, h + 50)
        ang = rng.uniform(0, 2 * np.pi)
        length = rng.uniform(90, 520)
        strength = rng.uniform(0.35, 1.0)
        pts = [(x, y)]
        walked = 0.0
        while walked < length:
            step = rng.uniform(10, 26)
            ang += rng.normal(0, 0.22)
            x, y = x + np.cos(ang) * step, y + np.sin(ang) * step
            pts.append((x, y))
            walked += step
        starts.extend(pts[::3])
        nx, ny = -np.sin(ang), np.cos(ang)
        dd.line(pts, fill=int(255 * strength), width=2 if strength > 0.75 else 1)
        ld.line([(px + nx * 1.5, py + ny * 1.5) for px, py in pts], fill=int(150 * strength), width=1)
        side = 1 if rng.random() < 0.5 else -1
        wd.line([(px + nx * side * 16, py + ny * side * 16) for px, py in pts], fill=int(200 * strength), width=30)
    dark_a = np.asarray(dark.filter(ImageFilter.GaussianBlur(0.6)), np.float32) / 255
    light_a = np.asarray(light.filter(ImageFilter.GaussianBlur(0.5)), np.float32) / 255
    wedge_a = np.asarray(wedge.filter(ImageFilter.GaussianBlur(14)), np.float32) / 255
    grain = rng.normal(0, 1, (h, w)).astype(np.float32)
    grain = grain * 0.7 + _box_blur(grain, 1.2) * 1.6
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    vign = 1 - 0.16 * (((xx / w - 0.5) ** 2 + (yy / h - 0.5) ** 2) * 2)
    lum = (lobes * 6.0 - dark_a * 10.0 + light_a * 6.0 - np.minimum(wedge_a, 1.2) * 6.5) * contrast + grain * 1.3
    out = (np.array(base, np.float32)[None, None, :] + lum[..., None]) * vign[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def make_paper(dst: Path) -> str:
    """public/fx/paper_dark.jpg — 종이 콜라주 스킨의 배경(한 번 만들고 재사용)."""
    from PIL import Image
    dst.mkdir(parents=True, exist_ok=True)
    p = dst / f"paper_dark_v{PAPER_VERSION}.jpg"
    if not p.exists():
        Image.fromarray(crumpled_paper(), "RGB").save(p, quality=90)
    return p.name


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

