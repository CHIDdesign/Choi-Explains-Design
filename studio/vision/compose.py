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


def analyze_image(path: Path, log: LogFn = noop_log) -> dict[str, Any]:
    """{w, h, face: NBox|None, busy: 3×3, lum: 3×3, subject: [cx, cy], side: left|right|center, dark: bool}. 못 읽으면 {}."""
    try:
        import cv2
        from .face import _Detector
    except Exception:  # noqa: BLE001
        return {}
    im = cv2.imread(str(path), cv2.IMREAD_COLOR)
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
    return {"w": w0, "h": h0, "face": face, "busy": [[round(v, 3) for v in row] for row in busy.tolist()],
            "lum": [[round(v, 3) for v in row] for row in lum.tolist()], **_place(face, busy, lum)}


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
    out: dict[str, Any] = {"safe": {"side": info.get("side", "left"), "dark": bool(info.get("dark"))}}
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
