"""사진·판화의 배경 오려 내기(디자인 v3 콜라주 — 운영자 레퍼런스의 '오린 사진 + 바닥 타원').

모델을 새로 받지 않고 두 길로만 오린다. 둘 다 아니면 오리지 않는다(억지로 오리면 들쭉날쭉한 덩어리가 된다 — 그런 사진은
렌더러가 종이 테두리 프린트로 붙인다).
1. 고른 바탕(흰 종이 판화·스캔·제품 사진·단색 배경): 테두리에 닿은 바탕색 덩어리 + 안쪽의 큰 바탕색 구멍을 지운다.
2. 인물 사진: 얼굴(YuNet·Haar, `vision/face.py`)로 사람 자리를 잡고 GrabCut — 오린 경계가 실제 윤곽(밝기 변화)을 따라가지
   않으면 버린다.
이미 투명 부분이 있는 PNG 는 그 알파를 그대로 쓴다. 가장자리는 1px 안으로 줄이고 1.5px 번지게 한다(바탕색 띠 방지).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

CUT_VERSION = 2
WORK = 640           # 마스크를 계산하는 크기(긴 변)
TOL = 30             # 바탕 판정 허용 차(채널마다)
HOLE_TOL = 14        # 안쪽 구멍은 더 엄격하게(판화의 흰 셔츠·하이라이트를 지우지 않게)
HOLE_MIN = 0.025     # 안쪽 바탕색 구멍은 화면의 2.5% 이상일 때만 지운다
BORDER_SHARE = 0.85  # 테두리 화소 중 바탕색에 가까운 몫이 이 이상이면 '고른 바탕'
SEPARATED = 0.85     # 인물 오리기: 경계의 이만큼이 안팎 색 차(Lab ΔE 14 이상)로 갈려야 받아들인다 — 머리가 배경에 녹은 곳이
                     # 있으면 들쭉날쭉한 덩어리가 된다(품위 있게 못 오리면 프린트로 붙인다)
SEP_DE = 14.0


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
    return (~bgm).astype(np.uint8) * 255


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
    fg = cv2.erode(fg, ker)                                                          # 바탕색 띠 1px 안으로
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
