"""자료 하우스 트리트먼트(docs/upgrade/07b_자료_하우스_트리트먼트.md) — 스톡·아카이브·클립아트를 종이 위에 앉히기.

인쇄물에는 종이보다 밝은 색도, 잉크보다 어두운 색도 없다: 밖에서 온 그림의 톤을 [잉크 #26211E, 종이 #F5F2EA] 안으로.
  T1 graded   레벨 → 채도 중앙값 16 → 색 방향을 채널 쪽으로 절반 → [잉크, 종이] 리맵(색이 정보인 그림·따뜻한/중립 사진)
  T2 duotone  휘도 → 잉크 → 따뜻한 회색 → 종이(차가운·원색 스톡, 색이 정보가 아닌 사진)
  T3 halftone 45° 망점, 잉크 한 색(작거나 압축이 심한 그림)
  T4 lineart  색을 버리고 잉크 한 색 + 알파(벡터·일러스트·아이콘 — 모션 장면의 클립아트)
입자는 굽지 않는다(렌더러 최상단의 입자 한 장). 시그널(주황)은 그림에 물들이지 않는다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import numpy as np

from .auto import REFERENCE_LAB, _luma, _scurve, lab_to_srgb, srgb_to_lab

HOUSE_VERSION = 1
INK = np.array([38, 33, 30], np.float32) / 255          # #26211E
PAPER = np.array([245, 242, 234], np.float32) / 255     # #F5F2EA
TREATMENTS = ("graded", "duotone", "halftone", "lineart", "none")
# 그림이 놓이는 곳 → T1 의 리맵 세기 k(07b 3절 표)
SURFACE_K = {"full": 0.5, "paper": 0.85, "stage": 0.5}


def house_stats(x: np.ndarray) -> dict[str, float]:
    """x: sRGB 0~1. 레벨(0.5~99.5%) · 중간톤 채도·색 방향 중앙값."""
    pix = x.reshape(-1, 3)
    if len(pix) > 300_000:
        pix = pix[np.random.default_rng(0).choice(len(pix), 300_000, replace=False)]
    lum = _luma(pix)
    lo, hi = np.percentile(lum, [0.5, 99.5])
    L, a, b = srgb_to_lab(pix)
    C = np.hypot(a, b)
    mid = (L > 25) & (L < 80)
    if mid.sum() < 50:
        mid = np.ones_like(L, bool)
    return {"lo": float(lo), "hi": float(max(hi, lo + 1 / 1.4)),       # 늘림은 1.4배까지
            "c_med": float(np.median(C[mid])), "a_med": float(np.median(a[mid])), "b_med": float(np.median(b[mid]))}


def house_grade(x: np.ndarray, st: dict[str, float], k: float = 0.5, c_target: float = 16.0,
                pull: float = 0.5, keep_color: bool = False) -> np.ndarray:
    """T1. k: [잉크, 종이] 리맵 세기(전면 0.5 · 종이 위 0.85 · 색이 정보면 0.3). keep_color 면 색 방향·채도는 그대로(레벨만)."""
    if keep_color:
        k, pull = 0.3, 0.0
    x = np.clip((x - st["lo"]) / max(1e-3, st["hi"] - st["lo"]), 0, 1).astype(np.float32)
    L, a, b = srgb_to_lab(x)
    if not keep_color:
        w = 4 * (L / 100) * (1 - L / 100)                                 # 중간톤에서만 방향을 옮긴다
        a = a + pull * (REFERENCE_LAB["a"] - st["a_med"]) * w * 0.5
        b = b + pull * (REFERENCE_LAB["b"] - st["b_med"]) * w * 0.5
        C = np.hypot(a, b) + 1e-6
        g = float(np.clip(c_target / max(st["c_med"], 4.0), 0.6, 1.25))
        C2 = np.where(C * g > 40, 40 + (C * g - 40) * 0.3, C * g)         # 원색은 무릎
        a, b = a * C2 / C, b * C2 / C
    x = lab_to_srgb(L, a, b)
    lo, hi = k * INK, 1 - k * (1 - PAPER)
    return np.clip(lo + x * (hi - lo), 0, 1)


def duotone(x: np.ndarray, mid=(0.55, 0.50, 0.45)) -> np.ndarray:
    """T2. 잉크 → 따뜻한 회색 → 종이."""
    lum = _luma(x)
    lo, hi = np.percentile(lum, [0.5, 99.5])
    t = _scurve(np.clip((lum - lo) / max(1e-3, hi - lo), 0, 1), 0.15)[..., None]
    m = np.array(mid, np.float32)
    return np.where(t < 0.5, INK + (m - INK) * np.clip(t * 2, 0, 1),
                    m + (PAPER - m) * np.clip(t * 2 - 1, 0, 1)).astype(np.float32)


def halftone(x: np.ndarray, cell: float = 7.0, angle: float = 45.0) -> np.ndarray:
    """T3. 망점 면적 = 어두운 정도. cell 은 출력 화소 기준(1080p 에서 6~8)."""
    from PIL import Image, ImageFilter
    g = np.asarray(Image.fromarray((_luma(x) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(cell / 2)),
                   np.float32) / 255
    lo, hi = np.percentile(g, [1, 99])
    g = np.clip((g - lo) / max(1e-3, hi - lo), 0, 1)
    h, w = g.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    th = np.deg2rad(angle)
    u = (xx * np.cos(th) + yy * np.sin(th)) / cell
    v = (-xx * np.sin(th) + yy * np.cos(th)) / cell
    d = np.hypot(u - np.round(u), v - np.round(v))
    r = np.sqrt(np.clip(1 - g, 0, 1) / np.pi)
    alpha = np.clip((r - d) * cell + 0.5, 0, 1)[..., None]              # 1px 안티에일리어싱
    return (PAPER + (INK - PAPER) * alpha).astype(np.float32)


def lineart(rgba, ink=INK):
    """T4. 클립아트 → 잉크 한 색 + 알파(밝은 면은 투명). 어두운 무대 위에서는 ink 에 PAPER 를 준다."""
    from PIL import Image
    a = np.asarray(rgba.convert("RGBA"), np.float32) / 255
    lum = _luma(a[..., :3]) * a[..., 3] + (1 - a[..., 3])               # 투명한 곳 = 흰색
    cover = np.clip((0.82 - lum) / 0.45, 0, 1)                          # 어두울수록 잉크
    out = np.concatenate([np.broadcast_to(np.asarray(ink, np.float32), a[..., :3].shape), cover[..., None]], -1)
    return Image.fromarray((out * 255).astype(np.uint8), "RGBA")


def pick_treatment(kind: str, st: dict[str, float], w: int, h: int, keep_color: bool = False,
                   series_std: float = 0.0, surface: str = "paper") -> str:
    """kind: vector|illustration|photo. 문턱은 07b 의 실제 자료 10장에서 잡은 제안값. 전면(full)에는 망점을 쓰지 않는다."""
    if kind in ("vector", "illustration"):
        return "lineart"
    if keep_color:
        return "graded"
    if max(w, h) < 1200 and surface != "full":
        return "halftone"
    cool = st["b_med"] < 0 and st["c_med"] > 15        # 차가운 지배색
    loud = st["c_med"] > 30                            # 원색
    if cool or loud or series_std > 12:
        return "duotone"
    return "graded"


def treat_file(src: Path, dst: Path, *, kind: str = "photo", treatment: str = "auto", surface: str = "paper",
               keep_color: bool = False, max_w: int = 2400) -> tuple[Path, str]:
    """그림 파일 → 처리한 파일(lineart 는 PNG, 나머지 JPEG 92). 반환 (경로, 고른 처리)."""
    from PIL import Image
    im = Image.open(src)
    if kind in ("vector", "illustration") or treatment == "lineart":
        dst = dst.with_suffix(".png")
        out = lineart(im, ink=PAPER if surface == "stage" else INK)
        if out.width > max_w:
            out = out.resize((max_w, int(out.height * max_w / out.width)), Image.LANCZOS)
        out.save(dst)
        return dst, "lineart"
    rgb = im.convert("RGB")
    if rgb.width > max_w:
        rgb = rgb.resize((max_w, int(rgb.height * max_w / rgb.width)), Image.LANCZOS)
    x = np.asarray(rgb, np.float32) / 255
    st = house_stats(x)
    t = treatment if treatment in TREATMENTS else pick_treatment(kind, st, rgb.width, rgb.height, keep_color,
                                                                 surface=surface)
    if t == "none":
        y = x
    elif t == "duotone":
        y = duotone(x)
    elif t == "halftone":
        y = halftone(x)
    else:
        t = "graded"
        y = house_grade(x, st, k=SURFACE_K.get(surface, 0.85), keep_color=keep_color)
    dst = dst.with_suffix(".jpg")
    tmp = dst.with_name(dst.stem + ".part.jpg")
    Image.fromarray((np.clip(y, 0, 1) * 255 + 0.5).astype(np.uint8)).save(tmp, quality=92, format="JPEG")
    tmp.replace(dst)
    return dst, t


def colorful_clipart(path: Path) -> Optional[float]:
    """B8 — 컬러 클립아트인가: 불투명 화소의 채도 중앙값(Lab C). 선화(잉크 한 색)는 거의 0."""
    from PIL import Image
    try:
        a = np.asarray(Image.open(path).convert("RGBA"), np.float32) / 255
    except Exception:  # noqa: BLE001
        return None
    m = a[..., 3] > 0.5
    if m.sum() < 50:
        return 0.0
    _, aa, bb = srgb_to_lab(a[..., :3][m])
    return float(np.median(np.hypot(aa, bb)))
