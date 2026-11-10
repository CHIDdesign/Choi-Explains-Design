"""렌더에 쓰는 작은 에셋을 절차적으로 생성(저작권 걱정 없음): 필름 그레인 타일, 재질 키트(종이·책상 텍스처),
은은한 효과음, 폰트 복사."""
from __future__ import annotations

import shutil
import wave
from pathlib import Path

import numpy as np

from ..paths import RENDERER_DIR, RENDERER_FONTS, ROOT, USER_DIR

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


# ---------------------------------------------------------------------------
# 재질 키트(docs/디자인_v5_토크쇼.md): 조명을 받은 높이맵으로 만든 종이 — CSS 그라디언트로는 '찍은 종이'처럼 보이지 않는다.
# 높이 = 저주파 굴곡 + 섬유 + 구김 선(능선·골) + 구김 면 → 위 왼쪽 빛 하나로 음영 → 톤 얼룩 · 고운 입자.
TEX_VERSION = 8
KRAFT = dict(base=(182, 153, 112), relief=0.72, fibre=1.32, scale=2.0, creases=12, crease=0.45, facets=18, facet=0.006, mottle=0.028, grain=3.2, seed=57)     # 결이 크고 세면 엠보스처럼 보인다
TEX_LIGHT = np.array((-0.52, -0.70, 0.49), np.float32)     # 위 왼쪽(이미지 좌표: y 아래로)
TEXTURES: dict[str, dict] = {
    # relief 굴곡 · fibre 섬유 · creases 구김 선 수 · crease 세기 · facets 구김 면 수 · facet 세기 · mottle 톤 얼룩 · grain 입자
    "eggshell": dict(base=(243, 242, 236), curl=0.1, relief=1.3, fibre=0.75, creases=7, crease=0.35, facets=0, facet=0.0, mottle=0.012, grain=1.5, seed=21),
    "parchment": dict(base=(238, 231, 216), relief=1.6, fibre=1.2, hf=0.6, creases=6, crease=0.55, folds=4, fold=0.35, facets=26, facet=0.010, mottle=0.024, grain=1.8, seed=33),     # 온 화면에 같은 크기의 잔주름이면 엠보스 필터다: 잔결은 낮추고 긴 접힘선을 넣는다
    "memo": dict(base=(252, 250, 244), relief=0.9, fibre=0.7, creases=4, crease=0.35, facets=0, facet=0.0, mottle=0.007, grain=1.1, seed=45),
    "kraft": KRAFT,
    "gray": dict(base=(205, 201, 195), relief=1.1, fibre=1.3, creases=8, crease=0.5, facets=0, facet=0.0, mottle=0.022, grain=2.6, seed=129),     # 회색지(콜라주 바탕·이름표)
    "newsblur": dict(base=(222, 214, 194), relief=1.6, fibre=1.8, creases=16, crease=0.9, facets=34, facet=0.014, mottle=0.030, grain=3.0, seed=141),     # 콜라주 뒤의 신문 조각: 활자 줄까지 초점이 나간 채로 굽는다
    "graph": dict(base=(241, 241, 233), relief=1.0, fibre=0.7, creases=5, crease=0.4, facets=0, facet=0.0, mottle=0.010, grain=1.3, seed=69),
    "newsprint": dict(base=(222, 214, 194), relief=1.6, fibre=1.8, creases=16, crease=0.9, facets=34, facet=0.014, mottle=0.030, grain=3.0, seed=81),
    "print": dict(base=(240, 237, 229), relief=2.0, fibre=1.0, creases=46, crease=1.5, facets=120, facet=0.018, mottle=0.011, grain=1.6, seed=93),
    "forest": dict(base=(33, 80, 64), relief=1.8, fibre=1.5, creases=8, crease=0.8, facets=0, facet=0.0, mottle=0.040, grain=2.2, seed=105),
    "blueprint": dict(base=(31, 58, 90), relief=1.5, fibre=1.2, creases=12, crease=0.8, facets=14, facet=0.020, mottle=0.050, grain=2.4, seed=117),
}


def _fbm(w: int, h: int, cells: int, octaves: int, rng: np.random.Generator, gain: float = 0.5) -> np.ndarray:
    import cv2
    out = np.zeros((h, w), np.float32)
    amp = 1.0
    for i in range(octaves):
        cx = cells * 2 ** i
        cy = max(2, round(cx * h / w))
        out += amp * cv2.resize(rng.normal(0, 1, (cy + 2, cx + 2)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
        amp *= gain
    return out / (out.std() + 1e-6)


def _fibres(w: int, h: int, n: int, rng: np.random.Generator, lo: float = 12, hi: float = 70, ang: float | None = None, curl: float = 0.4) -> np.ndarray:
    """짧게 굽은 섬유 다발(1px, 세기 제각각) — 종이의 결. ang 을 주면 그 방향으로 누운 결, curl 이 작으면 곧은 결."""
    import cv2
    layer = np.zeros((h, w), np.uint8)
    for _ in range(n):
        x, y, a, step = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(0, 2 * np.pi) if ang is None else ang + rng.normal(0, 0.05), rng.uniform(lo, hi) / 3
        pts = []
        for _k in range(4):
            pts.append((x, y))
            a += rng.normal(0, curl)
            x, y = x + np.cos(a) * step, y + np.sin(a) * step
        cv2.polylines(layer, [np.int32(pts)], False, int(rng.uniform(70, 255)), 1, cv2.LINE_AA)
    return layer.astype(np.float32) / 255


def _crease_map(w: int, h: int, n: int, rng: np.random.Generator) -> np.ndarray:
    """구김 선(무작위 보행 + 갈라짐)의 높이: 능선은 +, 골은 −. 날카로운 선 + 넓은 어깨."""
    import cv2
    up = np.zeros((h, w), np.uint8)
    down = np.zeros((h, w), np.uint8)
    starts: list[tuple[float, float]] = []
    for _ in range(n):
        if starts and rng.random() < 0.4:
            x, y = starts[rng.integers(len(starts))]
        else:
            x, y = rng.uniform(-40, w + 40), rng.uniform(-40, h + 40)
        ang, length, val = rng.uniform(0, 2 * np.pi), rng.uniform(120, 760), int(rng.uniform(90, 255))
        pts = [(x, y)]
        walked = 0.0
        while walked < length:
            step = rng.uniform(14, 40)
            ang += rng.normal(0, 0.16)
            x, y = x + np.cos(ang) * step, y + np.sin(ang) * step
            pts.append((x, y))
            walked += step
        starts.extend(pts[::3])
        cv2.polylines(up if rng.random() < 0.5 else down, [np.int32(pts)], False, val, 1, cv2.LINE_AA)
    sharp = cv2.GaussianBlur(up, (0, 0), 0.8).astype(np.float32) - cv2.GaussianBlur(down, (0, 0), 0.8).astype(np.float32)
    wide = cv2.GaussianBlur(up, (0, 0), 7).astype(np.float32) - cv2.GaussianBlur(down, (0, 0), 7).astype(np.float32)
    return (sharp * 1.4 + wide * 9.0) / 255


def _fold_map(w: int, h: int, n: int, rng: np.random.Generator) -> np.ndarray:
    """화면을 가로지르는 긴 접힘선 n 개: 거의 곧고 구간마다 세기가 달라 군데군데 끊겨 보인다."""
    import cv2
    layer = np.zeros((h, w), np.uint8)
    seg = 28.0
    for _ in range(n):
        ang = float(rng.uniform(-0.45, 0.45)) + (np.pi / 2 if rng.random() < 0.5 else 0.0)
        half = float(rng.uniform(0.35, 0.7)) * max(w, h)
        x, y = rng.uniform(0.15, 0.85) * w - np.cos(ang) * half, rng.uniform(0.15, 0.85) * h - np.sin(ang) * half
        bend, v = float(rng.normal(0, 0.012)), float(rng.uniform(0.3, 1.0))
        for _s in range(int(2 * half / seg)):
            ang += bend + float(rng.normal(0, 0.006))
            nx, ny = x + np.cos(ang) * seg, y + np.sin(ang) * seg
            v = float(np.clip(v + rng.normal(0, 0.16), 0.0, 1.0))
            cv2.line(layer, (int(x), int(y)), (int(nx), int(ny)), int(v * 255), 1, cv2.LINE_AA)
            x, y = nx, ny
    f = layer.astype(np.float32) / 255
    return cv2.GaussianBlur(f, (0, 0), 0.9) * 1.8 + cv2.GaussianBlur(f, (0, 0), 6) * 11


def _facet_shade(w: int, h: int, n: int, rng: np.random.Generator) -> np.ndarray:
    """구겨진 면: 면마다 기운 방향이 달라 밝기가 다르다(보로노이 + 살짝 휜 경계). 값 ±1 안팎."""
    import cv2
    mask = np.ones((h, w), np.uint8)
    mask[rng.integers(0, h, n), rng.integers(0, w, n)] = 0
    _d, labels = cv2.distanceTransformWithLabels(mask, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_CCOMP)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    labels = cv2.remap(labels.astype(np.float32), xx + _fbm(w, h, 8, 3, rng) * 16, yy + _fbm(w, h, 8, 3, rng) * 16,
                       cv2.INTER_NEAREST, borderMode=cv2.BORDER_REPLICATE).astype(np.int32)
    tilt = rng.normal(0, 1, labels.max() + 1).astype(np.float32)
    keep = _fbm(w, h, 3, 2, rng) * 0.5 + 0.6             # 구김은 고르지 않다 — 평평하게 남는 데가 있다
    return cv2.GaussianBlur(np.clip(tilt, -1.4, 1.4)[labels], (0, 0), 7.0) * np.clip(keep, 0.05, 1.2)     # 경계가 선명하면 종이에 네모 얼룩이 생긴다


def paper_texture(w: int = 1920, h: int = 1080, *, base=(244, 243, 238), relief: float = 1.0, fibre: float = 1.0, creases: int = 8,
                  crease: float = 0.6, facets: int = 0, facet: float = 0.0, mottle: float = 0.015, grain: float = 1.5,
                  curl: float = 0.4, scale: float = 1.0, hf: float = 1.0, folds: int = 0, fold: float = 1.0, seed: int = 1) -> np.ndarray:
    import cv2
    rng = np.random.default_rng(seed)
    height = _fbm(w, h, round(5 * scale), 3, rng) * relief * 2.6 + _fbm(w, h, round(90 * scale), 2, rng) * relief * 0.11 * hf
    fine = _fibres(w, h, 16000, rng, 10 / scale, 46 / scale, curl=curl)
    long_f = _fibres(w, h, 1400, rng, 50 / scale, 150 / scale, curl=curl)
    height = height + (cv2.GaussianBlur(fine, (0, 0), 0.7) * 0.34 + cv2.GaussianBlur(long_f, (0, 0), 0.8) * 0.2) * fibre * hf
    if creases:
        height = height + _crease_map(w, h, creases, rng) * crease
    if folds:
        height = height + _fold_map(w, h, folds, rng) * fold
    gx = cv2.Sobel(height, cv2.CV_32F, 1, 0, ksize=3) / 8
    gy = cv2.Sobel(height, cv2.CV_32F, 0, 1, ksize=3) / 8
    k = 0.24
    n = np.stack((-gx * k, -gy * k, np.ones_like(gx)), 2)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    lum = (n @ TEX_LIGHT) / TEX_LIGHT[2]
    if facets:
        lum = lum + _facet_shade(w, h, facets, rng) * facet
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    lum = lum * (1.012 - 0.035 * (xx / w * 0.45 + yy / h * 0.55)) * (1 + _fbm(w, h, 3, 3, rng) * mottle)
    rgb = np.array(base, np.float32)[None, None, :] * lum[..., None]     # 얼룩은 밝기만 — 색이 움직이면 복숭아빛 번짐이 된다
    noise = rng.normal(0, 1, (h, w)).astype(np.float32)
    rgb += (noise * 0.6 + cv2.GaussianBlur(noise, (0, 0), 0.9) * 1.3)[..., None] * grain
    return np.clip(rgb, 0, 255)


def _graph_lines(rgb: np.ndarray, rng: np.random.Generator, ink=(92, 150, 138)) -> np.ndarray:
    """모눈 인쇄(얇은 선 + 다섯 칸마다 진한 선) — 인쇄가 고르지 않게 세기를 흔든다."""
    h, w = rgb.shape[:2]
    a = np.zeros((h, w), np.float32)
    step = 36
    for k in range(0, max(w, h) + step, step):
        v = 0.5 if k % (step * 5) == 0 else 0.22
        a[:, k: k + 1] = np.maximum(a[:, k: k + 1], v)
        a[k: k + 1, :] = np.maximum(a[k: k + 1, :], v)
    a *= np.clip(0.85 + _fbm(w, h, 40, 2, rng) * 0.15, 0.4, 1.1)
    return rgb * (1 - a[..., None]) + np.array(ink, np.float32)[None, None, :] * a[..., None]


def _fleck(rgb: np.ndarray, rng: np.random.Generator, n: int, amount: float, lo: float = 4, hi: float = 18) -> np.ndarray:
    """재생지의 어두운 섬유 조각(크라프트·신문지)."""
    h, w = rgb.shape[:2]
    return rgb * (1 - _fibres(w, h, n, rng, lo, hi)[..., None] * amount)


def _kraft() -> np.ndarray:
    import cv2
    rng = np.random.default_rng(KRAFT["seed"] + 1000)
    rgb = _fleck(paper_texture(**KRAFT), rng, 3000, 0.2, 3, 9)
    lay = cv2.GaussianBlur(_fibres(*rgb.shape[1::-1], 2600, rng, 60, 300, ang=0.0, curl=0.1), (0, 0), 0.9)   # 가로로 누운 긴 섬유 — 구김이 세면 가죽처럼 보인다
    return rgb * (1 - lay[..., None] * 0.1)


def _news_columns(rgb: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """초점이 나간 신문 조각: 세 단의 활자를 글자 칸으로 찍고 종이째 σ2 로 흐린다 — 읽히지 않으니 같은 문장이 되풀이될 일도, 제호도 없다."""
    import cv2
    h, w = rgb.shape[:2]
    a = np.zeros((h, w), np.float32)
    for col in range(30, w - 200, 238):
        for y in range(20, h - 14, 21):
            x = col
            while x < col + 198:
                for _ in range(int(rng.integers(2, 7))):                 # 어절의 글자 수
                    for _s in range(int(rng.integers(2, 5))):            # 글자 하나 = 획 몇 개(네모를 찍으면 벽돌처럼 보인다)
                        i, j = int(rng.integers(0, 11)), int(rng.integers(0, 11))
                        if x < col + 198:
                            a[y + i:y + i + 2, x:x + 13] = 0.9
                            a[y:y + 13, x + j:x + j + 2] = 0.9
                    x += 15
                x += 7
    a = cv2.GaussianBlur(a, (0, 0), 2.0)[..., None]
    return cv2.GaussianBlur(rgb, (0, 0), 2.0) * (1 - a) + np.array((42, 38, 32), np.float32)[None, None, :] * a


def blueprint_texture(w: int = 1920, h: int = 1080) -> np.ndarray:
    """청사진 조각: 실제 입면도 스캔(Rookery Building, Art Institute of Chicago, CC0)을 시아노타입으로 — 벡터로 그린 창틀은 옆 종이 조각과 재질이 맞지 않는다."""
    import cv2
    from PIL import Image
    paper = paper_texture(w, h, **TEXTURES["blueprint"])
    with Image.open(ROOT / "assets" / "material" / "rookery_elevation.jpg") as im:
        g = np.asarray(im.convert("L"), np.float32) / 255
    k = max(w / g.shape[1], h / g.shape[0])
    g = cv2.resize(g, (round(g.shape[1] * k), round(g.shape[0] * k)), interpolation=cv2.INTER_CUBIC)
    y0, x0 = (g.shape[0] - h) // 2, (g.shape[1] - w) // 2
    g = g[y0:y0 + h, x0:x0 + w]
    bg = cv2.GaussianBlur(g, (0, 0), 30)                  # 누런 얼룩을 지우고 선만 남긴다
    ink = np.clip((bg - g) / (bg * 0.42 + 1e-3), 0, 1) ** 0.75
    light = np.array((232, 238, 240), np.float32)[None, None, :]
    return np.clip(paper * (1 - ink[..., None]) + light * ink[..., None] * paper.mean(2, keepdims=True) / paper.mean(), 0, 255)


def make_texture(name: str) -> np.ndarray:
    if name == "desk":
        rgb = _kraft() * np.array((0.36, 0.36, 0.38), np.float32)            # 어두운 면 = 크라프트를 곱해 어둡게(절차적 나뭇결은 CG 로 읽혔다)
    elif name == "blueprint":
        rgb = blueprint_texture()
    elif name == "kraft":
        rgb = _kraft()
    else:
        cfg = TEXTURES[name]
        rgb = paper_texture(**cfg)
        rng = np.random.default_rng(cfg["seed"] + 1000)
        if name == "graph":
            rgb = _graph_lines(rgb, rng)
        elif name == "newsprint":
            rgb = _fleck(rgb, rng, 1400, 0.2, 3, 9)
        elif name == "newsblur":
            rgb = _news_columns(_fleck(rgb, rng, 1400, 0.2, 3, 9), rng)
    return rgb.astype(np.uint8)


def make_textures(dst: Path) -> list[str]:
    """public/fx/tex/<이름>.jpg — 한 번 만들어 user/cache 에 두고 작업 폴더(와 Remotion Studio 미리보기 폴더)로 복사한다."""
    from PIL import Image
    cache = USER_DIR / "cache" / f"textures_v{TEX_VERSION}"
    cache.mkdir(parents=True, exist_ok=True)
    out = []
    for name in (*TEXTURES, "desk"):
        src = cache / f"{name}.jpg"
        if not src.exists():
            tmp = src.with_suffix(f".{np.random.randint(1 << 30)}.tmp")   # 동시에 도는 작업이 반쯤 쓴 파일을 읽지 않게
            Image.fromarray(make_texture(name), "RGB").save(tmp, "JPEG", quality=88, optimize=True)
            tmp.replace(src)
        for folder in (dst, RENDERER_DIR / "public" / "fx" / "tex"):
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / src.name
            if not target.exists() or target.stat().st_size != src.stat().st_size:
                shutil.copyfile(src, target)
        out.append(src.name)
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

