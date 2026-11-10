"""사진·스톡 위 구도(채널 주인 2026-10-02: "스톡 이미지 위 그래픽은 그 이미지의 모습을 분석한 뒤 알맞게 배치하라",
"인물 사진은 얼굴이 잘리지 않는지 확인하라").

사진 한 장을 재서 ① 얼굴 상자(YuNet, 없으면 Haar) ② 3×3 칸의 복잡도(에지 밀도)·밝기 ③ 피사체 자리 → 글자·칩·말풍선을
놓을 **빈 쪽**(side)과 어두운 사진인지(dark)를 정하고, 16:9 로 꽉 채워 자를 때 얼굴이 잘리면 초점(focus)을 얼굴로 옮기고,
그래도 안 들어가면 통째로 보이게(fit=contain) 한다. 결과는 그래픽 data 에 `safe`·`focus`·`fit`·`face` 로 들어가고 렌더러
(Photo·Broll·FootageText·Pill)가 그대로 쓴다. 순수 측정이라 캐시(work/compose.json)된다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import numpy as np

from ..util import LogFn, noop_log

NBox = list[float]  # [x, y, w, h] 0~1
LUM_GRID = 24           # 휘도 격자 한 변 — 렌더러가 치수선·도장을 놓을 때 그 자리 밝기를 본다
SOFT_EDGE = 25.0        # 긴 변 1600 에서 잰 윤곽 세기(라플라시안 절댓값 p99) — 이보다 낮으면 크기만 크고 실제로는 흐린 그림이다(전면으로 키우면 윤곽이 번진다)
SCAN_MAX_BLANK = 0.35   # 테두리에 이어진 평면이 이보다 넓으면 스캔 여백이 아니라 바탕(제품·판화)
SCAN_MIN_AREA = 0.5     # 안쪽 직사각형이 이보다 작으면 자르지 않는다
SCAN_MAX_SIDE = 0.2     # 한 변에서 이보다 많이 깎아야 하면 자르지 않는다(그림의 일부일 가능성)
SCAN_INSET = 0.004      # 종이 가장자리의 번짐까지 안쪽으로
SCAN_KEEP = 0.8         # 표시 대상이 이만큼 남으면 안쪽 직사각형 그대로(윤곽 끝이 잘리는 편이 흰 쐐기보다 낫다)


def analyze_image(path: Path, log: LogFn = noop_log) -> dict[str, Any]:
    """{w, h, face: NBox|None, busy: 3×3, lum: 3×3, subject: [cx, cy], side: left|right|center, dark: bool}. 못 읽으면 {}."""
    try:
        import cv2
        from .face import _Detector
    except Exception:  # noqa: BLE001
        return {}
    try:
        im = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)   # imread 는 Windows 의 한글 경로를 못 읽는다
    except (OSError, cv2.error):
        return {}
    if im is None:
        return {}
    h0, w0 = im.shape[:2]
    scale = 640.0 / max(1, w0)
    small = cv2.resize(im, (max(16, int(w0 * scale)), max(16, int(h0 * scale)))) if scale < 1 else im
    h, w = small.shape[:2]
    face: Optional[NBox] = None
    try:
        det = _Detector(w, h, log)
        r = det.detect_full(small)
        if r and r[4] >= 0.6:
            face = [round(r[0] / w, 4), round(r[1] / h, 4), round(r[2] / w, 4), round(r[3] / h, 4)]
    except Exception:  # noqa: BLE001
        face = None
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 160)
    busy = np.zeros((3, 3)); lum = np.zeros((3, 3))
    for r_ in range(3):
        for c_ in range(3):
            ys, ye = int(h * r_ / 3), int(h * (r_ + 1) / 3)
            xs, xe = int(w * c_ / 3), int(w * (c_ + 1) / 3)
            busy[r_, c_] = float(edges[ys:ye, xs:xe].mean() / 255.0)
            lum[r_, c_] = float(gray[ys:ye, xs:xe].mean() / 255.0)
    grid = cv2.resize(gray, (LUM_GRID, LUM_GRID), interpolation=cv2.INTER_AREA) / 255.0
    k = min(1.0, 1600.0 / max(h0, w0))
    full = cv2.cvtColor(cv2.resize(im, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else im, cv2.COLOR_BGR2GRAY)
    soft = float(np.percentile(np.abs(cv2.Laplacian(full, cv2.CV_32F)), 99)) < SOFT_EDGE
    return {"w": w0, "h": h0, "face": face, "soft": soft, "grid": [[round(v, 2) for v in row] for row in grid.tolist()], "busy": [[round(v, 3) for v in row] for row in busy.tolist()],
            "lum": [[round(v, 3) for v in row] for row in lum.tolist()], **_place(face, busy, lum)}


def _blank_mask(rgb: np.ndarray, lightest: float = 68) -> np.ndarray:
    """테두리에 이어진 밝고 무채색이거나 새까만 평면(스캔 여백·무자료 쐐기·촬영 배경). 긴 변 480px 로 잰다."""
    import cv2
    k = 480 / max(rgb.shape[:2])
    a = cv2.resize(rgb, (max(16, int(rgb.shape[1] * k)), max(16, int(rgb.shape[0] * k))), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32)
    lum, chroma = lab[..., 0] * 100 / 255, np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    mean = cv2.blur(lum, (5, 5))
    std = np.sqrt(np.maximum(cv2.blur(lum * lum, (5, 5)) - mean * mean, 0))
    flat = (((lum > lightest) & (chroma < 30)) | (lum < 5)) & (std < 4)
    _n, comp = cv2.connectedComponents(flat.astype(np.uint8), connectivity=4)
    edge = np.unique(np.concatenate([comp[0], comp[-1], comp[:, 0], comp[:, -1]]))
    return np.isin(comp, edge[edge > 0])


def _inner_rect(blank: np.ndarray) -> Optional[tuple[float, float, float, float]]:
    """스캔 여백·회전된 스캔의 무자료 쐐기를 뺀 가장 큰 안쪽 직사각형(정규화). 판단이 서지 않으면 None."""
    # 흰 배경 제품 사진(바탕이 넓다)과 위쪽만 하늘인 사진은 여백이 아니다
    if blank.mean() > SCAN_MAX_BLANK or sum(float(s.mean()) >= 0.55 for s in (blank[0], blank[-1], blank[:, 0], blank[:, -1])) < 2:
        return None
    h, w = blank.shape
    heights = np.zeros(w, np.int32)
    best = (0, 0, 0, 0, 0)
    for y in range(h):                    # 히스토그램으로 푸는 최대 직사각형
        heights = np.where(blank[y], 0, heights + 1)
        stack: list[tuple[int, int]] = []
        for x in range(w + 1):
            cur, start = (int(heights[x]) if x < w else 0), x
            while stack and stack[-1][1] >= cur:
                sx, sh = stack.pop()
                if sh * (x - sx) > best[0]:
                    best = (sh * (x - sx), sx, y - sh + 1, x, y + 1)
                start = sx
            stack.append((start, cur))
    area, x0, y0, x1, y1 = best
    r = (x0 / w, y0 / h, x1 / w, y1 / h)
    if area < SCAN_MIN_AREA * w * h or max(r[0], r[1], 1 - r[2], 1 - r[3]) > SCAN_MAX_SIDE:
        return None
    return r


def trim_scan(path: Path, keep: Optional[NBox] = None) -> Optional[tuple[Path, tuple[float, float, float, float]]]:
    """스캔 여백·무자료 영역을 잘라 낸 사본(`<이름>.trim.jpg`)과 그 영역(원본 기준 정규화 x0, y0, x1, y1). 자를 것이 없으면 None.
    keep = 비전이 표시를 건 대상 전부를 담는 상자 — 말이 가리키는 것을 크게 자르지 않는다."""
    from PIL import Image
    try:
        with Image.open(path) as src:
            im = src.convert("RGB")
    except Exception:  # noqa: BLE001 - SVG 로고 등은 손대지 않는다
        return None
    blank = _blank_mask(np.asarray(im))
    r = _inner_rect(blank)
    if r is None:
        return None
    x0, y0, x1, y1 = r[0] + SCAN_INSET, r[1] + SCAN_INSET, r[2] - SCAN_INSET, r[3] - SCAN_INSET
    if keep:
        seen = max(0.0, min(x1, keep[0] + keep[2]) - max(x0, keep[0])) * max(0.0, min(y1, keep[1] + keep[3]) - max(y0, keep[1]))
        if seen < SCAN_KEEP * keep[2] * keep[3]:      # 대상이 많이 잘리면 여백을 조금 남기더라도 대상을 살린다
            x0, y0, x1, y1 = min(x0, keep[0]), min(y0, keep[1]), max(x1, keep[0] + keep[2]), max(y1, keep[1] + keep[3])
    rect = (max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1))
    if (rect[2] - rect[0]) * (rect[3] - rect[1]) > 0.97:
        return None
    dst = path.with_name(f"{path.stem}.trim.jpg")
    im.crop((round(rect[0] * im.width), round(rect[1] * im.height), round(rect[2] * im.width), round(rect[3] * im.height))).save(dst, quality=92)
    return dst, rect


def tight_crop(path: Path) -> Optional[Path]:
    """오리지 못한 물건 사진: 촬영 배경을 물건 둘레로 잘라 사각 인화지로 쓸 사본(`<이름>.tight.jpg`). 배경이 넓지 않으면 None."""
    from PIL import Image
    try:
        with Image.open(path) as src:
            im = src.convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    blank = _blank_mask(np.asarray(im), lightest=55)
    if blank.mean() <= SCAN_MAX_BLANK:
        return None
    ys, xs = np.where(~blank)
    if not len(xs):
        return None
    h, w = blank.shape
    pad = 0.04 * max(h, w)
    box = (max(0, xs.min() - pad) / w, max(0, ys.min() - pad) / h, min(w, xs.max() + 1 + pad) / w, min(h, ys.max() + 1 + pad) / h)
    dst = path.with_name(f"{path.stem}.tight.jpg")
    im.crop((round(box[0] * im.width), round(box[1] * im.height), round(box[2] * im.width), round(box[3] * im.height))).save(dst, quality=92)
    return dst


def reframe_marks(marks: list, rect: tuple[float, float, float, float]) -> list:
    """비전이 원본에 준 표시 좌표(box·point·outline) → 잘라 낸 사본의 좌표."""
    x0, y0, x1, y1 = rect
    sx, sy = 1 / max(1e-6, x1 - x0), 1 / max(1e-6, y1 - y0)
    out = []
    for m in marks:
        n = dict(m)
        if isinstance(m.get("box"), list) and len(m["box"]) == 4:
            n["box"] = [(m["box"][0] - x0) * sx, (m["box"][1] - y0) * sy, m["box"][2] * sx, m["box"][3] * sy]
        if isinstance(m.get("point"), list) and len(m["point"]) == 2:
            n["point"] = [(m["point"][0] - x0) * sx, (m["point"][1] - y0) * sy]
        if isinstance(m.get("outline"), list):
            n["outline"] = [(v - x0) * sx if i % 2 == 0 else (v - y0) * sy for i, v in enumerate(m["outline"])]
        out.append(n)
    return out


def _place(face: Optional[NBox], busy: np.ndarray, lum: np.ndarray) -> dict[str, Any]:
    """피사체(얼굴 또는 에지 무게중심)와 칸별 복잡도로 글자를 놓을 빈 쪽을 정한다."""
    cols = busy.mean(axis=0)                        # 왼·가운데·오른쪽 복잡도
    if face:
        cx = face[0] + face[2] / 2
    else:
        total = busy.sum() or 1.0
        cx = float(sum(busy[:, c].sum() * (c + 0.5) / 3 for c in range(3)) / total)
    # 피사체 반대쪽 중 덜 복잡한 쪽
    cand = ["left", "right"] if cx >= 0.5 else ["right", "left"]
    side = cand[0]
    if face:
        fx0, fx1 = face[0], face[0] + face[2]
        if side == "left" and fx0 < 0.42:          # 얼굴이 왼쪽 반에도 걸치면 반대로
            side = "right"
        elif side == "right" and fx1 > 0.58:
            side = "left"
    # 양쪽 다 복잡하고 가운데가 고요하면 가운데(가운데 글자 + 어둠)
    if cols[0] > 0.12 and cols[2] > 0.12 and cols[1] < min(cols[0], cols[2]) * 0.6 and not face:
        side = "center"
    dark = bool(lum.mean() < 0.38)
    return {"subject": [round(cx, 3), 0.5], "side": side, "dark": dark, "busy_side": round(float(cols[0] if side == "left" else cols[2]), 3)}


def visible_region(w: int, h: int, box_w: float, box_h: float, focus: Optional[tuple[float, float]] = None) -> tuple[float, float, float, float]:
    """cover 로 꽉 채워 자를 때 보이는 영역(정규화 x0, y0, x1, y1). focus = objectPosition(0~1) — 기본 가운데."""
    if w <= 0 or h <= 0:
        return (0.0, 0.0, 1.0, 1.0)
    img_ar, box_ar = w / h, box_w / box_h
    fx, fy = focus if focus else (0.5, 0.5)
    if img_ar > box_ar:                              # 좌우가 잘린다
        vis_w = box_ar / img_ar
        x0 = min(max(0.0, fx - vis_w * fx), 1.0 - vis_w)   # objectPosition 의 뜻: 그 비율 지점이 상자의 같은 비율 지점에
        return (x0, 0.0, x0 + vis_w, 1.0)
    vis_h = img_ar / box_ar                         # 위아래가 잘린다
    y0 = min(max(0.0, fy - vis_h * fy), 1.0 - vis_h)
    return (0.0, y0, 1.0, y0 + vis_h)


def box_inside(b: NBox, region: tuple[float, float, float, float], margin: float = 0.04) -> bool:
    x0, y0, x1, y1 = region
    return b[0] >= x0 - margin and b[1] >= y0 - margin and b[0] + b[2] <= x1 + margin and b[1] + b[3] <= y1 + margin


def focus_for(w: int, h: int, box_w: float, box_h: float, face: NBox) -> tuple[float, float]:
    """얼굴 상자가 cover 영역의 가운데에 오도록 하는 objectPosition(0~1). 잘리는 축만 움직인다."""
    img_ar, box_ar = w / h, box_w / box_h
    cx, cy = face[0] + face[2] / 2, face[1] + face[3] / 2
    if img_ar > box_ar:
        vis_w = box_ar / img_ar
        x0 = min(max(0.0, cx - vis_w / 2), 1.0 - vis_w)
        return (round(x0 / (1.0 - vis_w), 4) if vis_w < 1 else 0.5, 0.5)
    vis_h = img_ar / box_ar
    y0 = min(max(0.0, cy - vis_h / 2), 1.0 - vis_h)
    return (0.5, round(y0 / (1.0 - vis_h), 4) if vis_h < 1 else 0.5)


def plan_media(info: dict[str, Any], box_w: float = 1920, box_h: float = 1080) -> dict[str, Any]:
    """분석 결과 → 그래픽 data 에 넣을 것: {safe: {side, dark}, face?, focus?, fit?}.
    얼굴이 cover 영역 밖이면 초점(objectPosition)을 얼굴이 가운데 오게 옮기고, 그래도 안 들어가면 fit=contain."""
    lum = info.get("lum") or [[0.0] * 3] * 3
    out: dict[str, Any] = {"safe": {"side": info.get("side", "left"), "dark": bool(info.get("dark")), "light": bool(lum[2][2] > 0.62),   # light: 우하단(출처 자리)이 밝다
                                     "dim": bool(np.mean(lum) < 0.15), "soft": bool(info.get("soft"))}}                            # dim: 종이의 넓은 그림자가 배경보다 밝아 안개가 된다 · soft: 전면으로 키우지 않는다
    if info.get("grid"):
        out["safe"]["lum"] = info["grid"]
    face = info.get("face")
    w, h = int(info.get("w", 0) or 0), int(info.get("h", 0) or 0)
    if not face or not w or not h:
        return out
    out["face"] = face
    if box_inside(face, visible_region(w, h, box_w, box_h)):
        return out
    focus = focus_for(w, h, box_w, box_h, face)
    out["focus"] = [focus[0], focus[1]]
    if not box_inside(face, visible_region(w, h, box_w, box_h, focus)):
        out["fit"] = "contain"                       # 얼굴이 너무 커서 어떻게 잘라도 잘린다 → 통째로(무대 위 액자)
    return out


def media_report(plans: list[dict[str, Any]]) -> str:
    n = len(plans)
    faces = sum(1 for p in plans if p.get("face"))
    focus = sum(1 for p in plans if p.get("focus"))
    contain = sum(1 for p in plans if p.get("fit") == "contain")
    return f"🖼 사진 {n}장 구도 분석: 얼굴 {faces} · 초점 조정 {focus} · 액자(통째) {contain}"
