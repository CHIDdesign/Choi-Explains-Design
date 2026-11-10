"""사진·판화의 배경 오려 내기(디자인 v3 콜라주 — 운영자 레퍼런스의 '오린 사진 + 바닥 타원').

모델을 새로 받지 않고 두 길로만 오린다. 둘 다 아니면 오리지 않는다(억지로 오리면 들쭉날쭉한 덩어리가 된다 — 그런 사진은
렌더러가 종이 테두리 프린트로 붙인다).
1. 고른 바탕(흰 종이 판화·스캔·제품 사진·단색 배경): 테두리에 닿은 바탕색 덩어리 + 안쪽의 큰 바탕색 구멍을 지운다.
2. 인물 사진: 얼굴(YuNet·Haar, `vision/face.py`)로 사람 자리를 잡고 GrabCut — 오린 경계가 실제 윤곽(밝기 변화)을 따라가지
   않으면 버린다.
이미 투명 부분이 있는 PNG 는 그 알파를 그대로 쓴다. 가장자리는 2px 안으로 줄이고 1.5px 번지게 한다(바탕색 띠 방지).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

CUT_VERSION = 4
WORK = 640           # 마스크를 계산하는 크기(긴 변)
TOL = 30             # 바탕 판정 허용 차(채널마다)
HOLE_TOL = 14        # 안쪽 구멍은 더 엄격하게(판화의 흰 셔츠·하이라이트를 지우지 않게)
HOLE_MIN = 0.025     # 안쪽 바탕색 구멍은 화면의 2.5% 이상일 때만 지운다
BORDER_SHARE = 0.85  # 테두리 화소 중 바탕색에 가까운 몫이 이 이상이면 '고른 바탕'
SEPARATED = 0.85     # 인물 오리기: 경계의 이만큼이 안팎 색 차(Lab ΔE 14 이상)로 갈려야 받아들인다 — 머리가 배경에 녹은 곳이
                     # 있으면 들쭉날쭉한 덩어리가 된다(품위 있게 못 오리면 프린트로 붙인다)
SEP_DE = 14.0
SHADOW_MIN = 0.002   # 물건에 둘러싸인 바닥 그림자는 화면의 0.2% 이상일 때만 지운다
RIM_SHARP = 24       # 바탕과의 경계가 이보다 또렷하면(9×9 안의 L* 차, 중앙값) 그림자가 아니라 회색 물건이다


def _border(a: np.ndarray, band: int) -> np.ndarray:
    return np.concatenate([a[:band].reshape(-1, 3), a[-band:].reshape(-1, 3), a[:, :band].reshape(-1, 3),
                           a[:, -band:].reshape(-1, 3)])


def plain_background(rgb: np.ndarray, tol: int = TOL) -> Optional[np.ndarray]:
    """테두리가 고른 바탕이면 그 색(중앙값), 아니면 None."""
    band = max(2, int(min(rgb.shape[:2]) * 0.02))
    b = _border(rgb, band).astype(np.int16)
    med = np.median(b, axis=0)
    close = np.abs(b - med).max(axis=1) <= tol
    return med.astype(np.uint8) if close.mean() >= BORDER_SHARE else None


def _plain_mask(arr: np.ndarray, bg: np.ndarray) -> np.ndarray:
    import cv2
    diff = np.abs(arr.astype(np.int16) - bg.astype(np.int16)).max(axis=2)
    near = (diff <= TOL).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(near, connectivity=4)
    h, w = near.shape
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])).tolist())
    strict = diff <= HOLE_TOL
    bgm = np.zeros_like(near, dtype=bool)
    for i in range(1, n):
        comp = lab == i
        if i in edge:
            bgm |= comp
        elif stats[i, cv2.CC_STAT_AREA] >= HOLE_MIN * h * w and strict[comp].mean() > 0.9:
            bgm |= comp                       # 의자 다리 사이처럼 둘러싸인 큰 바탕
    return _drop_floor_shadow(arr, (~bgm).astype(np.uint8) * 255)


def _drop_floor_shadow(arr: np.ndarray, fg: np.ndarray) -> np.ndarray:
    """물건 아래쪽의 무채색·저대비 덩어리(바탕에 이어진 것)는 바닥 그림자다 — 흰 테두리가 그것까지 따라가면 회색 덩어리가 붙는다.
    위쪽은 건드리지 않는다(흰 셔츠·석고)."""
    import cv2
    ys = np.where((fg > 0).any(axis=1))[0]
    if not len(ys):
        return fg
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB).astype(np.float32)
    soft = (lab[..., 0] * 100 / 255 > 38) & (np.hypot(lab[..., 1] - 128, lab[..., 2] - 128) < 9) & (fg > 0)     # 다리 밑동의 짙은 그림자까지. 짙은 나무·가죽(L 35 아래)은 남는다
    soft[:ys[0] + int(0.45 * (ys[-1] - ys[0]))] = False
    mean = cv2.blur(lab[..., 0], (5, 5))
    soft &= np.sqrt(np.maximum(cv2.blur(lab[..., 0] * lab[..., 0], (5, 5)) - mean * mean, 0)) < 5     # 천·나뭇결이 아니라 매끈한 면만
    near = np.ones((9, 9), np.uint8)                     # 매끈함 검사가 경계 2~3px 를 빼므로 넉넉히 본다
    rim = cv2.dilate((fg == 0).astype(np.uint8), near) > 0
    light = lab[..., 0] * 100 / 255
    step = cv2.morphologyEx(light, cv2.MORPH_GRADIENT, near)
    n, parts = cv2.connectedComponents(soft.astype(np.uint8), connectivity=4)
    for i in range(1, n):
        part = parts == i
        edge = part & rim
        if np.median(step[edge]) > RIM_SHARP if edge.any() else light[part].mean() <= 60:     # 바탕에 안 닿은 면은 밝을 때만 그림자로 본다
            soft[part] = False
    _n, comp, stats, _c = cv2.connectedComponentsWithStats((soft | (fg == 0)).astype(np.uint8), connectivity=4)
    big = np.flatnonzero(stats[:, cv2.CC_STAT_AREA] >= SHADOW_MIN * arr.shape[0] * arr.shape[1])     # 다리 사이처럼 물건에 둘러싸인 큰 면도
    out = fg.copy()
    out[soft & np.isin(comp, np.concatenate([np.unique(comp[fg == 0]), big[big > 0]]))] = 0
    return out


def _portrait_mask(arr: np.ndarray) -> Optional[np.ndarray]:
    import cv2
    from ..util import noop_log
    from ..vision.face import _Detector
    h, w = arr.shape[:2]
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    try:
        f = _Detector(w, h, noop_log).detect_full(bgr)
    except Exception:  # noqa: BLE001 - 검출기가 없으면 오리지 않는다
        return None
    if not f:
        return None
    fx, fy, fw, fh = f[:4]
    if fh < 0.08 * h or fh > 0.7 * h:
        return None
    x0, x1 = int(max(2, fx - 1.5 * fw)), int(min(w - 3, fx + 2.5 * fw))
    y0 = int(max(2, fy - 0.75 * fh))
    mask = np.full((h, w), cv2.GC_BGD, np.uint8)
    mask[y0:, x0:x1 + 1] = cv2.GC_PR_FGD
    cx0, cx1 = int(fx + 0.2 * fw), int(fx + 0.8 * fw)
    mask[int(fy + 0.2 * fh):int(min(h, fy + 0.9 * fh)), cx0:cx1] = cv2.GC_FGD            # 얼굴 가운데
    mask[int(min(h - 1, fy + 1.3 * fh)):, int(fx + 0.1 * fw):int(fx + 0.9 * fw)] = cv2.GC_FGD   # 목 아래 몸통
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(bgr, mask, None, bgd, fgd, 6, cv2.GC_INIT_WITH_MASK)
    except Exception:  # noqa: BLE001
        return None
    fg = np.isin(mask, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    if n < 2:
        return None
    face_lab = lab[int(fy + fh / 2), int(fx + fw / 2)]
    if face_lab == 0:
        return None
    fg = (lab == face_lab).astype(np.uint8)
    cnts, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    fg = np.zeros_like(fg)
    cv2.drawContours(fg, cnts, -1, 1, thickness=-1)                                      # 구멍 메우기
    if boundary_contrast(arr, fg) < SEPARATED:
        return None
    return fg * 255


def boundary_contrast(arr: np.ndarray, fg: np.ndarray, band: int = 6) -> float:
    """오린 경계(아래 가장자리 제외) 가운데, 안쪽 띠와 바깥쪽 띠의 평균 색이 Lab 에서 SEP_DE 이상 다른 몫(0~1)."""
    import cv2
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB).astype(np.float32)
    lab[..., 0] *= 100 / 255
    lab[..., 1:] -= 128
    m = (fg > 127).astype(np.uint8)
    din = cv2.distanceTransform(m, cv2.DIST_L2, 3)
    dout = cv2.distanceTransform(1 - m, cv2.DIST_L2, 3)
    inner = ((din >= 2) & (din <= band)).astype(np.float32)
    outer = ((dout >= 2) & (dout <= band)).astype(np.float32)
    k = (2 * band + 3, 2 * band + 3)

    def local_mean(w):
        den = cv2.blur(w, k) + 1e-6
        return np.stack([cv2.blur(lab[..., c] * w, k) / den for c in range(3)], -1), den
    mi, di = local_mean(inner)
    mo, do = local_mean(outer)
    edge = (cv2.morphologyEx(m, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0)
    edge[-band:] = False
    edge[:2] = edge[:, :2] = edge[:, -2:] = False
    edge &= (di > 0.02) & (do > 0.02)
    if edge.sum() < 40:
        return 0.0
    de = np.linalg.norm(mi[edge] - mo[edge], axis=1)
    return float((de >= SEP_DE).mean())


def cutout_mask(im) -> Optional[np.ndarray]:
    """PIL 이미지 → 전경 마스크(0~255, 원본 크기) 또는 None(오릴 수 없음)."""
    import cv2
    from PIL import Image
    rgba = im.convert("RGBA")
    alpha = np.asarray(rgba)[..., 3]
    if (alpha < 250).mean() > 0.05:                      # 이미 투명한 PNG
        return alpha
    rgb = rgba.convert("RGB")
    k = min(1.0, WORK / max(rgb.size))
    small = rgb.resize((max(1, int(rgb.width * k)), max(1, int(rgb.height * k))), Image.BILINEAR) if k < 1 else rgb
    arr = np.ascontiguousarray(np.asarray(small))
    bg = plain_background(arr)
    fg = _plain_mask(arr, bg) if bg is not None else _portrait_mask(arr)
    if fg is None:
        return None
    share = float((fg > 127).mean())
    if not 0.06 <= share <= 0.88:
        return None
    ker = np.ones((3, 3), np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, ker)                                  # 티끌 지우기
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))            # 작은 틈 메우기
    fg = cv2.erode(fg, ker, iterations=2)                                            # 바탕색 띠 2px 안으로
    big = cv2.resize(fg, rgb.size, interpolation=cv2.INTER_LINEAR)
    sigma = max(1.0, 1.5 / max(k, 1e-6) * 0.5)
    return cv2.GaussianBlur(big, (0, 0), sigma)


def cutout(src: Path, dst: Optional[Path] = None, *, max_side: int = 1600) -> Optional[Path]:
    """src → 배경을 지운 PNG(내용 상자로 자름, 여백 2%) 또는 None. 결과가 이미 있으면 그대로."""
    from PIL import Image
    dst = dst or src.with_name(f"{src.stem}.cut{CUT_VERSION}.png")
    if dst.exists():
        return dst
    try:
        with Image.open(src) as im:
            im.load()
            if max(im.size) > max_side:
                im.thumbnail((max_side, max_side))
            mask = cutout_mask(im)
            if mask is None:
                return None
            rgba = im.convert("RGBA")
    except Exception:  # noqa: BLE001 - 읽지 못하는 그림은 오리지 않는다
        return None
    out = np.asarray(rgba).copy()
    out[..., 3] = np.minimum(out[..., 3], mask)
    ys, xs = np.where(out[..., 3] > 24)
    if not len(xs):
        return None
    pad = int(max(out.shape[:2]) * 0.02)
    y0, y1 = max(0, ys.min() - pad), min(out.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(out.shape[1], xs.max() + pad + 1)
    Image.fromarray(out[y0:y1, x0:x1], "RGBA").save(dst)
    return dst


# ─────────────────────────────────────────────────────────────────────────────
# 콜라주 조각(템플릿 collage): 사람은 흉상으로, 건물은 하늘을 따라 오려 흑백 망점 인쇄로. 못 오리면 망점 인화지 — 빈자리는 없다.
PRESS_VERSION = 2
PRESS_SIDE = 1200        # 결과의 긴 변 — 망점 칸은 이 크기 기준이다
PRESS_CELL = 5.5         # 화면에서 대략 4~5px 망점(더 작으면 압축에 뭉개진다)
PRESS_TONE = 0.65        # 망점에 섞는 연속 톤 — 망점이 세면 얼굴이 점으로 흩어지고 필터를 씌운 것처럼 보인다
PRESS_HI = (232 - 38) / (245 - 38)     # 가장 밝은 곳을 종이 흰색(245)이 아니라 232 로 — 이마의 결이 남는다
BACK_BLUR = 4.0          # 뒤 조각의 초점 흐림(화면 px) — 조각은 화면 높이 750px 안팎으로 놓인다
BUST_W = 3.3             # 흉상 자르기: 얼굴 폭의 배수(가운데에서 좌우로)
BUST_UP, BUST_DOWN = 1.1, 3.9      # 얼굴 높이의 배수(위로 · 아래로)
SKY_MIN, SKY_MAX = 0.12, 0.7       # 하늘이 차지하는 몫
RISE_MIN = 0.22          # 건물로 보는 높이(가장 높은 곳 대비) — 그 밖의 낮은 땅·나무는 잘라 낸다


def _unmount(arr: np.ndarray) -> tuple[int, int, int, int]:
    """대지(mount) 위에 붙은 사각·타원 사진이면 사진 자리, 아니면 그림 전체 — 대지까지 '바탕이 고른 그림'으로 오리면 사진 사각형만 남는다."""
    import cv2
    from ..vision.compose import _blank_mask, _inner_rect
    h, w = arr.shape[:2]
    bg = plain_background(arr)
    if bg is None:
        r = _inner_rect(_blank_mask(arr))         # 네 변에 고르지 않게 남은 스캔 여백
        return (int(r[0] * w), int(r[1] * h), int(r[2] * w), int(r[3] * h)) if r else (0, 0, w, h)
    fg = (np.abs(arr.astype(np.int16) - bg.astype(np.int16)).max(axis=2) > TOL).astype(np.uint8)
    ker = np.ones((9, 9), np.uint8)
    fg = cv2.morphologyEx(cv2.morphologyEx(fg, cv2.MORPH_CLOSE, ker), cv2.MORPH_OPEN, ker)
    n, lab, st, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    if n < 2:
        return 0, 0, w, h
    i = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    x, y, bw, bh, area = st[i]
    cnts, _ = cv2.findContours((lab == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    solid = area / max(1.0, cv2.contourArea(cv2.convexHull(max(cnts, key=cv2.contourArea))))
    return (int(x), int(y), int(x + bw), int(y + bh)) if area >= 0.2 * w * h and area / (bw * bh) >= 0.72 and solid >= 0.95 else (0, 0, w, h)


def _main_part(fg: np.ndarray, x: int, y: int) -> Optional[np.ndarray]:
    """(x, y) 를 품은 덩어리만, 구멍은 메워서."""
    import cv2
    _n, lab = cv2.connectedComponents(fg, connectivity=8)
    if lab[y, x] == 0:
        return None
    one = (lab == lab[y, x]).astype(np.uint8)
    cnts, _ = cv2.findContours(one, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    out = np.zeros_like(one)
    cv2.drawContours(out, cnts, -1, 1, thickness=-1)
    return out


def _bust_mask(arr: np.ndarray, face: tuple[float, float, float, float], turned: bool = False) -> Optional[np.ndarray]:
    """얼굴 둘레에 사람 모양(머리 타원 + 어깨 사다리꼴)을 먼저 깔고 GrabCut. 머리가 배경으로 번졌거나 얼굴이 잘렸으면 None."""
    import cv2
    h, w = arr.shape[:2]
    fx, fy, fw, fh = face
    cx, cy = int(fx + fw / 2), int(fy + fh * 0.45)
    # 사람 모양의 틀: 어깨선 위쪽의 머리 타원 밖은 언제나 배경 — 틀이 없으면 인물과 톤이 비슷한 벽이 네모난 덩어리로 딸려 온다
    mask = np.full((h, w), cv2.GC_BGD, np.uint8)
    shoulders = np.array([[cx - 0.62 * fw, fy + 1.05 * fh], [cx + 0.62 * fw, fy + 1.05 * fh], [cx + 2.9 * fw, fy + 2.5 * fh], [cx + 3.2 * fw, h],
                          [cx - 3.2 * fw, h], [cx - 2.9 * fw, fy + 2.5 * fh]], np.int32)
    cv2.fillPoly(mask, [shoulders], cv2.GC_PR_BGD)
    cv2.ellipse(mask, (cx, cy), (int(1.42 * fw), int(1.5 * fh)), 0, 180, 360, cv2.GC_PR_BGD, -1)                      # 머리칼은 넓게, 귀 아래로는 좁아진다
    cv2.fillPoly(mask, [np.array([[cx - 1.42 * fw, cy], [cx + 1.42 * fw, cy], [cx + 0.95 * fw, fy + 1.2 * fh], [cx - 0.95 * fw, fy + 1.2 * fh]], np.int32)], cv2.GC_PR_BGD)
    body = np.array([[cx - 0.5 * fw, fy + fh], [cx + 0.5 * fw, fy + fh], [cx + 1.9 * fw, fy + 2.2 * fh], [cx + 2.2 * fw, h],
                     [cx - 2.2 * fw, h], [cx - 1.9 * fw, fy + 2.2 * fh]], np.int32)
    cv2.fillPoly(mask, [body], cv2.GC_PR_FGD)
    cv2.ellipse(mask, (cx, cy), (int(0.8 * fw), int(1.05 * fh)), 0, 0, 360, cv2.GC_PR_FGD, -1)
    cv2.ellipse(mask, (cx, cy), (int(0.36 * fw), int(0.5 * fh)), 0, 0, 360, cv2.GC_FGD, -1)
    mask[int(fy + 1.5 * fh):max(int(fy + 1.5 * fh) + 1, min(int(0.8 * h), int(fy + 3 * fh))), max(0, int(cx - 0.45 * fw)):int(cx + 0.45 * fw)] = cv2.GC_FGD     # 아래 끝까지 찍으면 액자·대지가 줄기처럼 딸려 온다
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), mask, None, bgd, fgd, 4, cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return None
    fg = np.isin(mask, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
    r = max(3, int(0.09 * fw)) | 1
    fg = cv2.morphologyEx(cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((r, r), np.uint8)), cv2.MORPH_CLOSE, np.ones((r, r), np.uint8))
    one = _main_part(fg, cx, cy)
    if one is None:
        return None
    eye = min(h - 1, int(fy + 0.35 * fh))
    oval = np.zeros((h, w), np.uint8)
    cv2.ellipse(oval, (cx, cy), (int(0.36 * fw), int(0.5 * fh)), 0, 0, 360, 1, -1)
    if not one[eye].any() or one[oval > 0].mean() < 0.97 or one[min(h - 1, int(fy + 2 * fh)):].mean() < 0.15:     # 얼굴이 뚫렸거나 몸이 없다
        return None
    if turned and max(fx - np.argmax(one[eye]), np.flatnonzero(one[eye])[-1] - (fx + fw)) < 0.12 * fw:
        return None                                        # 옆얼굴인데 뒤통수가 없다(어두운 머리 + 어두운 배경)
    return one * 255                                       # 아래 끝은 언제나 화면 밖이다(렌더러 pieceBox)


def _skyline_mask(arr: np.ndarray) -> Optional[np.ndarray]:
    """건물: 위쪽에 닿은 크고 매끈한 밝은 면을 하늘로 보고 그 아래를 남긴다(옛 인화지의 어두운 테두리는 하늘 위에 있어도 넘어간다). 스카이라인이 납작하면 오릴 것이 없다 — None."""
    import cv2
    h, w = arr.shape[:2]
    lum = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)[..., 0].astype(np.float32) * 100 / 255
    soft = cv2.GaussianBlur(lum, (0, 0), 1.6)
    grad = cv2.morphologyEx(soft, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats((grad < 2.2).astype(np.uint8), connectivity=4)
    near = set(np.unique(lab[:max(2, int(0.12 * h))]).tolist()) - {0}
    big = [i for i in near if st[i, cv2.CC_STAT_AREA] >= 0.05 * w * h and soft[lab == i].mean() >= 45]
    if not big:
        return None
    main = max(big, key=lambda i: st[i, cv2.CC_STAT_AREA])
    level = soft[lab == main].mean()
    sky = np.isin(lab, [i for i in big if abs(soft[lab == i].mean() - level) < 14])
    if not SKY_MIN <= float(sky.mean()) <= SKY_MAX:
        return None
    sky = cv2.morphologyEx(sky.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    has = sky.any(axis=0)
    if has.mean() < 0.75:                                                     # 건물이 사진 위 끝을 뚫고 나갔다 — 수평으로 잘린 지붕이 된다
        return None
    below = np.maximum.accumulate(sky, axis=0) & (sky == 0)                    # 처음 하늘이 나온 뒤 끝나는 곳(그 위 테두리는 무시 · 잔디 같은 낮은 평면은 안 본다)
    line = np.where(below.any(axis=0), np.argmax(below, axis=0), h).astype(np.float32)
    line[~has] = h
    near_sky = lambda x, a, b: abs(float(soft[int(a):int(b), x].mean()) - level) < 12     # noqa: E731
    med = np.median(np.lib.stride_tricks.sliding_window_view(np.pad(line, 7, mode="edge"), 15), axis=1)
    for x in np.flatnonzero(line < med - 3):                                  # 구름·얼룩이 만든 가는 기둥은 하늘과 톤이 같다(첨탑은 어둡다)
        if near_sky(x, line[x], med[x]):
            line[x] = med[x]
    line = cv2.medianBlur(line.reshape(1, -1), 5).ravel()
    ground = float(np.percentile(line, 92))
    rise = ground - line
    if rise.max() < 0.22 * h or np.mean(rise >= 0.92 * rise.max()) > 0.5:     # 납작한 윗변이면 사각 인화지와 다를 것이 없다
        return None
    peak = int(np.argmax(rise))
    _n, parts = cv2.connectedComponents((rise >= RISE_MIN * rise.max()).astype(np.uint8).reshape(1, -1), connectivity=4)
    xs = np.flatnonzero(parts.ravel() == parts[0, peak])
    if len(xs) < 0.15 * w:
        return None
    yy = np.arange(h)[:, None]
    fg = (yy >= line[None, :]).astype(np.uint8)
    fg[:, :xs[0]] = 0
    fg[:, xs[-1] + 1:] = 0
    bottom = min(h, int(ground + 0.1 * h))
    while bottom > line[peak] + 0.2 * h and near_sky(int((xs[0] + xs[-1]) / 2), bottom - 3, bottom):      # 사진 아래의 빈 대지
        bottom -= 2
    fg[bottom:] = 0
    k = max(3, int(0.03 * w))
    thin = (fg & (1 - cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((1, k), np.uint8)))).astype(np.uint8)       # 가는 수직 조각: 어두우면 첨탑, 밝으면 구름·얼룩이다
    n, tl = cv2.connectedComponents(thin, connectivity=8)
    for i in range(1, n):
        if soft[tl == i].mean() > level - 20:
            fg[tl == i] = 0
    seed = min(h - 1, int(line[peak]) + 6)
    one = _main_part(fg, peak, seed) if fg[seed, peak] else None
    if one is None:
        return None
    rim = one & (1 - cv2.erode(one, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))))
    one[(rim > 0) & (np.abs(lum - level) < 15)] = 0                           # 하늘 판정은 경계 몇 px 앞에서 멈춘다 — 그대로 오리면 하늘색 띠가 흰 스티커 윤곽이 된다
    return one * 255


def _scissor(fg: np.ndarray, sigma: float) -> np.ndarray:
    """그래프 컷의 톱니를 가위로 자른 매끈한 곡선으로(문턱 전에 흐린다)."""
    import cv2
    return (cv2.GaussianBlur(fg.astype(np.float32) / 255, (0, 0), sigma) >= 0.5).astype(np.uint8) * 255


def _press(rgb: np.ndarray, fg: Optional[np.ndarray]) -> np.ndarray:
    """흑백 망점 + 연속 톤. 레벨은 오린 부분에서만 잰다 — 밝은 하늘이 있어도 인물 톤이 뜨지 않게."""
    from ..grade.auto import _luma
    from ..grade.house import INK, PAPER, halftone
    x = rgb.astype(np.float32) / 255
    lum = _luma(x)
    solid = fg is not None and (fg > 127).any()
    inside = lum[fg > 127] if solid else lum
    lo, hi = np.percentile(inside, [2, 98])
    t = np.clip((lum - lo) / max(1e-3, hi - lo), 0, 1) ** 0.92
    if solid:
        t = np.where(fg > 127, t, float(np.median(t[fg > 127])))
    tone = (INK + (PAPER - INK) * t[..., None]).astype(np.float32)
    out = halftone(np.repeat(t[..., None], 3, axis=2), cell=PRESS_CELL) * (1 - PRESS_TONE) + tone * PRESS_TONE
    return np.clip((INK + (out - INK) * PRESS_HI) * 255 + 0.5, 0, 255).astype(np.uint8)


def _find_face(arr: np.ndarray) -> Optional[tuple[float, float, float, float, bool]]:
    """한 사람의 얼굴 (x, y, w, h, 옆얼굴인가). 옛 사진에서 검출기는 크기마다 답이 갈려 몇 크기로 보고 확신이 가장 높은 것을 쓴다. 비슷한 크기의 얼굴이 또 있으면(단체 사진) None — 한 명만 도려내면 어색하다."""
    import cv2
    from ..util import noop_log
    from ..vision.face import _Detector
    best = None
    for side in (640, 480, 320, 880):
        k = side / max(arr.shape[:2])
        small = cv2.cvtColor(cv2.resize(arr, None, fx=k, fy=k, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2BGR)
        try:
            d = _Detector(small.shape[1], small.shape[0], noop_log)
            f = d.detect_full(small)
            others = d.yunet.detect(small)[1] if d.yunet is not None else None
        except Exception:  # noqa: BLE001 - 검출기가 없으면 얼굴 없이
            return None
        if f is None or f[3] < 0.05 * small.shape[0]:
            continue
        if others is not None and sum(float(x[2]) * float(x[3]) >= 0.45 * f[2] * f[3] for x in others) > 1:
            return None
        if best is None or f[4] > best[4]:
            best = (*(v / k for v in f[:4]), f[4], f[5])
    return (best[0], best[1], best[2], best[3], best[5] < 0.5) if best and best[4] >= 0.6 else None


def press_cutout(src: Path, *, kind: str = "") -> Optional[tuple[Path, bool, str]]:
    """사진 → 콜라주 조각 (경로, 오렸는가, person|place). 오리면 `<이름>.press1.png`(사람)·`.press1b.png`(건물, 알파), 못 오리면 `<이름>.print1.jpg`(망점 인화지). 그림을 못 읽으면 None."""
    import cv2
    from PIL import Image
    cut_dst, place_dst, print_dst = src.with_name(f"{src.stem}.press{PRESS_VERSION}.png"), src.with_name(f"{src.stem}.press{PRESS_VERSION}b.png"), src.with_name(f"{src.stem}.print{PRESS_VERSION}.jpg")
    for p, cut, k in ((cut_dst, True, "person"), (place_dst, True, "place"), (print_dst, False, kind or "person")):
        if p.exists():
            return p, cut, k
    try:
        with Image.open(src) as im:
            full = np.ascontiguousarray(np.asarray(im.convert("RGB")))
    except Exception:  # noqa: BLE001 - 읽지 못하는 그림은 조각이 되지 못한다
        return None
    k = min(1.0, WORK / max(full.shape[:2]))
    small = cv2.resize(full, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else full
    x0, y0, x1, y1 = [int(v / k) for v in _unmount(small)]
    photo = full[y0:y1, x0:x1]
    k = min(1.0, WORK / max(photo.shape[:2]))
    work = cv2.resize(photo, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else photo
    crop, fg, found = photo, None, kind or "person"
    face = _find_face(work) if kind != "place" else None
    if face is not None:
        fx, fy, fw, fh = [v / k for v in face[:4]]
        cx = fx + fw / 2
        bx0, bx1 = max(0, int(cx - BUST_W * fw)), min(photo.shape[1], int(cx + BUST_W * fw))
        by0, by1 = max(0, int(fy - BUST_UP * fh)), min(int(photo.shape[0] * 0.97), int(fy + BUST_DOWN * fh))     # 0.97: 사진 아래의 인화지 끝·캡션 띠
        bust = photo[by0:by1, bx0:bx1]
        q = min(1.0, 520 / max(bust.shape[:2]))
        m = _bust_mask(cv2.resize(bust, None, fx=q, fy=q, interpolation=cv2.INTER_AREA) if q < 1 else bust, ((fx - bx0) * q, (fy - by0) * q, fw * q, fh * q), face[4])
        if m is not None:
            crop, fg, found = bust, cv2.resize(_scissor(m, max(1.5, 0.045 * fw * q)), (bust.shape[1], bust.shape[0]), interpolation=cv2.INTER_LINEAR), "person"
            edge = max(3, int(0.012 * bust.shape[1]))              # 몸이 사진 끝까지 닿으면 인화지 끝의 흰 띠가 세로줄로 남는다
            if bx0 == 0:
                fg[:, :edge] = 0
            if bx1 == photo.shape[1]:
                fg[:, -edge:] = 0
    elif kind != "person":
        m = _skyline_mask(work)
        if m is not None:
            crop, fg, found = photo, cv2.resize(_scissor(m, 2.4), (photo.shape[1], photo.shape[0]), interpolation=cv2.INTER_LINEAR), "place"
    if fg is not None:
        ys, xs = np.where(fg > 127)
        if not 0.1 <= len(xs) / fg.size <= 0.9:
            fg = None
        else:
            pad = int(max(fg.shape) * 0.012)
            cy0, cy1, cx0, cx1 = max(0, ys.min() - pad), min(fg.shape[0], ys.max() + pad + 1), max(0, xs.min() - pad), min(fg.shape[1], xs.max() + pad + 1)
            crop, fg = crop[cy0:cy1, cx0:cx1], fg[cy0:cy1, cx0:cx1]
    s = PRESS_SIDE / max(crop.shape[:2])
    crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    if fg is None:
        Image.fromarray(_press(crop, None)).save(print_dst, quality=90)
        return print_dst, False, found
    fg = cv2.GaussianBlur(cv2.resize(fg, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_LINEAR), (0, 0), 1.0)
    dst = place_dst if found == "place" else cut_dst
    Image.fromarray(np.dstack([_press(crop, fg), fg]), "RGBA").save(dst)
    return dst, True, found


def press_back(src: Path, *, fade: bool = False) -> Path:
    """뒤에 놓이는 조각의 초점 흐림을 파일로 굽는다(프레임마다 도는 필터 금지) — 콜라주의 깊이는 대부분 초점 차이다. `<이름>.back.png|jpg`. fade = 아래 18% 를 종이로 녹인다(사람 몸통이 다 못 가린 건물 밑동이 수평으로 잘려 보이지 않게)."""
    import cv2
    from PIL import Image
    dst = src.with_name(f"{src.stem}.back{src.suffix}")
    if dst.exists():
        return dst
    with Image.open(src) as im:
        a = np.asarray(im.convert("RGBA"), np.float32) / 255
    sigma = BACK_BLUR * a.shape[0] / 750
    alpha = a[..., 3:]
    edge = cv2.GaussianBlur(alpha, (0, 0), sigma)[..., None]
    rgb = cv2.GaussianBlur(a[..., :3] * alpha, (0, 0), sigma) / np.maximum(edge, 1e-3)     # 알파를 곱한 채 흐려야 오린 바깥의 색이 번져 들어오지 않는다
    if fade:
        edge = edge * np.clip((a.shape[0] - np.arange(a.shape[0], dtype=np.float32)) / (0.18 * a.shape[0]), 0, 1)[:, None, None]
    if src.suffix.lower() == ".png":
        Image.fromarray((np.dstack([rgb, edge]).clip(0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").save(dst)
    else:
        Image.fromarray((rgb.clip(0, 1) * 255 + 0.5).astype(np.uint8)).save(dst, quality=90)
    return dst


# 핵심어 몽타주: 컷마다 글자 뒤 어두움이 달라 하드 컷에서 번쩍이지 않게
MONTAGE_LUM = 70.0       # 글자 뒤 밝기 중앙값(0~255)
MONTAGE_DARK = 60.0      # 이보다 어두운 사진은 맞출 수 없다 — 올리면 검정이 뜬다


def montage_still(src: Path) -> Optional[tuple[Path, bool]]:
    """몽타주 사진 → (`<이름>.mont1.jpg`, 쓸 만한가). 곱하기로만 어둡게 해 글자 뒤 띠(렌더러와 같은 cover 자르기)를 MONTAGE_LUM 에 맞추고, 글자와 간섭하는 건축 선을 σ2 로 굽는다. 거의 검은 사진은 False. 못 읽으면 None."""
    import cv2
    from PIL import Image
    from ..grade.auto import _luma
    dst = src.with_name(f"{src.stem}.mont1.jpg")
    try:
        with Image.open(src) as im:
            rgb = np.asarray(im.convert("RGB"), np.float32) / 255
    except Exception:  # noqa: BLE001 - 못 읽는 그림은 원본 그대로 두어 preflight 가 가린다
        return None
    k = max(1920 / rgb.shape[1], 1080 / rgb.shape[0])
    rgb = cv2.resize(rgb, None, fx=k, fy=k, interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)
    y0, x0 = int((rgb.shape[0] - 1080) * 0.38), (rgb.shape[1] - 1920) // 2
    lum = float(np.median(_luma(rgb[y0 + 400:y0 + 620, x0 + 260:x0 + 1660]))) * 255
    if not dst.exists():
        grey = _luma(rgb)[..., None]
        out = (grey + (rgb - grey) * 0.65) * min(1.0, MONTAGE_LUM / max(lum, 1.0))
        Image.fromarray((cv2.GaussianBlur(out, (0, 0), 2.0).clip(0, 1) * 255 + 0.5).astype(np.uint8)).save(dst, quality=90)
    return dst, lum >= MONTAGE_DARK
