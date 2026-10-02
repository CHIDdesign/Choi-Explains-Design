"""자료 하우스 트리트먼트(docs/upgrade/07b) — 스톡·아카이브·클립아트를 [잉크, 종이] 안으로."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.grade import house as H  # noqa: E402
from studio.grade.auto import srgb_to_lab  # noqa: E402


def _cool_stock(n=200):
    """파란 셔츠 · 짙은 책상(10/1 pip593333: 블랙 (0.09, 0.11, 0.15) · 화이트 1.0 · 중간톤 b* −4.9)."""
    rng = np.random.default_rng(0)
    x = np.zeros((n, n, 3), np.float32)
    x[:, : n // 2] = [0.20, 0.32, 0.62]
    x[:, n // 2:] = [0.09, 0.11, 0.15]
    x[: n // 4] = 1.0
    x[n // 4: n // 2, n // 4: n // 2] = [0.55, 0.60, 0.70]
    return np.clip(x + rng.normal(0, 0.01, x.shape), 0, 1).astype(np.float32)


def test_graded_range_inside_ink_and_paper():
    x = _cool_stock()
    y = H.house_grade(x, H.house_stats(x), k=0.85)
    assert (y.reshape(-1, 3).min(0) >= 0.85 * H.INK - 1e-3).all()
    assert (y.reshape(-1, 3).max(0) <= 1 - 0.85 * (1 - H.PAPER) + 1e-3).all()
    keep = H.house_grade(x, H.house_stats(x), keep_color=True)
    _, a0, b0 = srgb_to_lab(x.reshape(-1, 3))
    _, a1, b1 = srgb_to_lab(keep.reshape(-1, 3))
    assert abs(float(np.median(b1)) - float(np.median(b0))) < 6       # 색이 정보면 방향은 그대로


def test_duotone_endpoints_are_ink_and_paper():
    x = _cool_stock()
    y = H.duotone(x)
    lum = y.mean(-1)
    assert np.allclose(y.reshape(-1, 3)[np.argmin(lum.reshape(-1))], H.INK, atol=0.02)
    assert np.allclose(y.reshape(-1, 3)[np.argmax(lum.reshape(-1))], H.PAPER, atol=0.02)


def test_halftone_coverage_tracks_darkness():
    x = np.zeros((120, 240, 3), np.float32)
    x[:, :120] = 0.2
    x[:, 120:] = 0.85
    y = H.halftone(x)
    dark_ink = float((y[:, 20:100].mean(-1) < 0.5).mean())
    light_ink = float((y[:, 140:220].mean(-1) < 0.5).mean())
    assert dark_ink > light_ink + 0.2


def test_lineart_drops_color_keeps_alpha(tmp_path):
    from PIL import Image
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for x in range(10, 54):
        for y in range(10, 54):
            im.putpixel((x, y), (220, 40, 40, 255) if x < 32 else (30, 30, 30, 255))
    out = np.asarray(H.lineart(im), np.float32) / 255
    assert out[0, 0, 3] == 0.0                                      # 투명은 투명
    assert out[30, 45, 3] > 0.9 and np.allclose(out[30, 45, :3], H.INK, atol=0.02)
    assert H.colorful_clipart(_save(tmp_path / "c.png", H.lineart(im))) < 6.0          # 잉크 자체 채도 ≈ 3.4
    assert H.colorful_clipart(_save(tmp_path / "o.png", im)) > 20.0


def _save(p, im):
    im.save(p)
    return p


def test_cool_stock_picks_duotone_and_warm_picks_graded():
    x = _cool_stock(1400)
    assert H.pick_treatment("photo", H.house_stats(x), 1400, 1400) == "duotone"
    warm = np.clip(np.full((1400, 1400, 3), [0.72, 0.62, 0.48], np.float32)
                   + np.random.default_rng(1).normal(0, 0.05, (1400, 1400, 3)), 0, 1).astype(np.float32)
    assert H.pick_treatment("photo", H.house_stats(warm), 1400, 1400) == "graded"
    assert H.pick_treatment("vector", {}, 10, 10) == "lineart"
    assert H.pick_treatment("photo", H.house_stats(warm), 800, 600) == "halftone"
    assert H.pick_treatment("photo", H.house_stats(warm), 800, 600, surface="full") == "graded"
    assert H.pick_treatment("photo", H.house_stats(x), 1400, 1400, keep_color=True) == "graded"


def test_treat_file_writes_versioned_copy(tmp_path):
    from PIL import Image
    src = tmp_path / "a.jpg"
    Image.fromarray((_cool_stock(1300) * 255).astype(np.uint8)).save(src)
    out, t = H.treat_file(src, tmp_path / f"a.full.h{H.HOUSE_VERSION}", surface="full")
    assert out.exists() and out.suffix == ".jpg" and t == "duotone"
    v = Image.open(src).convert("RGBA")
    out2, t2 = H.treat_file(src, tmp_path / "v", kind="vector")
    assert out2.suffix == ".png" and t2 == "lineart" and Image.open(out2).mode == "RGBA" and v
