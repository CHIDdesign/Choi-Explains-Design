"""스코프 — 컬러리스트가 눈 대신 보는 계기판(파형 · RGB 퍼레이드 · 벡터스코프).

프리미어 Lumetri 스코프와 같은 것을 재서
  · metrics(): 수치 — 블랙/화이트 IRE, 클리핑, 얼굴(피부) IRE · 색상, 색 틀어짐, 채도, 대비
  · assess(): 판정 — 항목마다 '정상 범위인가'. **모두 정상이면 색을 건드리지 않는다**(원본 유지)
  · draw(): 그림 — 보정 전/후 스코프 시트(부가자료 · 🎨 컬러리스트가 비교 시트와 함께 본다)
  · chroma_noise_gain(): 보정이 압축 색 잡음을 얼마나 키웠나(얼룩 검사)
모든 입력은 감마 인코딩된 RGB(0~1), 프레임은 분석용 축소본이면 충분하다.
"""
from __future__ import annotations

import io
import math
from dataclasses import asdict, dataclass
from typing import Any, Optional

import numpy as np

# BT.709 Y'CbCr
KR, KB = 0.2126, 0.0722
SKIN_LINE_DEG = 123.0          # 벡터스코프의 피부색 선(I 선) — +Cb 축에서 반시계 방향
# 정상 범위(유튜브·방송 기준을 교육용 토킹헤드에 맞춤) — 벗어난 항목만 고친다
OK = {
    "skin_ire": (45.0, 75.0),      # 얼굴 밝기(밝은 피부 60~70, 어두운 피부 45~)
    "mid_ire": (28.0, 62.0),       # 얼굴이 없을 때 화면 중간 밝기
    "black_ire": (0.0, 7.0),       # 0.5% 지점 — 7 IRE 넘으면 떠 있는(뿌연) 블랙
    "white_ire": (75.0, 100.0),    # 99.5% 지점 — 75 아래면 탁한 화면
    "clip_pct": (0.0, 1.5),        # 99 IRE 이상 픽셀 비율(%)
    "skin_hue": (34.0, 60.0),      # 피부 CIELAB 색상(도) — 피부색 선 50° 근처
    "skin_chroma": (8.0, 30.0),    # 피부 채도 — 30 넘으면 주황, 8 아래면 창백·회색
    "cast": (0.0, 8.0),            # 무채색(흰 벽·회색) 픽셀의 색 틀어짐(CIELAB 채도) — 얼굴이 없을 때만 본다
    "chroma_mid": (8.0, 40.0),     # 피부 아닌 중간톤 채도 — 8 아래면 회색·로그 프로파일
    "spread": (0.40, 1.0),         # 밝기 p90 − p10 — 0.40 아래면 평평한(로그) 소스
}


def luma(x: np.ndarray) -> np.ndarray:
    return x[..., 0] * KR + x[..., 1] * (1 - KR - KB) + x[..., 2] * KB


def cbcr(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    y = luma(x)
    return (x[..., 2] - y) / 1.8556, (x[..., 0] - y) / 1.5748


def _lab(x: np.ndarray):
    from .auto import srgb_to_lab
    return srgb_to_lab(x)


def _face_pixels(f: np.ndarray, face: Optional[dict]) -> Optional[np.ndarray]:
    from .auto import face_box, skin_mask
    if not face:
        return None
    box = face_box(face, f.shape[1], f.shape[0])
    if not box:
        return None
    x0, y0, x1, y1 = box
    px = f[y0:y1, x0:x1].reshape(-1, 3)
    if len(px) < 30:
        return None
    sk = skin_mask(px)
    if float((sk > 0.3).mean()) > 0.4:
        return px[sk > 0.3]
    lum = luma(px)          # 색이 크게 틀어진 얼굴: 얼굴 상자의 중간 밝기
    core = px[(lum > np.percentile(lum, 30)) & (lum < np.percentile(lum, 92))]
    return core if len(core) > 20 else px


def metrics(frames: list[np.ndarray], faces: Optional[list[Optional[dict]]] = None) -> dict[str, Any]:
    """스코프 수치. faces: 프레임마다 얼굴 표본({x,y,s}) 또는 None."""
    from .auto import _lab_hue, skin_mask
    pix = np.concatenate([f.reshape(-1, 3) for f in frames]).astype(np.float32)
    if len(pix) > 600_000:
        pix = pix[np.random.default_rng(0).choice(len(pix), 600_000, replace=False)]
    y = luma(pix)
    L, a, b = _lab(pix)
    C = np.hypot(a, b)
    m: dict[str, Any] = {
        "black_ire": float(np.percentile(y, 0.5) * 100),
        "white_ire": float(np.percentile(y, 99.5) * 100),
        "mid_ire": float(np.median(y) * 100),
        "clip_pct": float(np.mean(y >= 0.99) * 100),
        "crush_pct": float(np.mean(y <= 0.01) * 100),
        "spread": float(np.percentile(y, 90) - np.percentile(y, 10)),
        "parade": [float(np.median(pix[:, i]) * 100) for i in range(3)],
    }
    skin = skin_mask(pix)
    mid = (L > 25) & (L < 80) & (skin < 0.3)
    m["chroma_mid"] = float(np.median(C[mid])) if mid.sum() > 200 else float(np.median(C))
    neutral = (C < 12) & (L > 35) & (L < 92)
    if neutral.sum() > 300:
        m["cast"] = float(math.hypot(float(a[neutral].mean()), float(b[neutral].mean())))
        m["cast_ab"] = [float(a[neutral].mean()), float(b[neutral].mean())]
    face_px = []
    for f, fc in zip(frames, faces or [None] * len(frames)):
        px = _face_pixels(f, fc)
        if px is not None:
            face_px.append(px)
    if face_px:
        fp = np.concatenate(face_px)
        Lf, af, bf = _lab(fp)
        m["skin_ire"] = float(np.median(luma(fp)) * 100)
        # −180~180° 로(354° 같은 붉은·자주 얼굴이 '높음'이 아니라 '낮음'으로 읽히게)
        m["skin_hue"] = float((_lab_hue(np.array(af.mean()), np.array(bf.mean())) + 180.0) % 360.0 - 180.0)
        m["skin_chroma"] = float(math.hypot(float(af.mean()), float(bf.mean())))
        cb, cr = cbcr(fp)
        m["skin_vec_deg"] = float(math.degrees(math.atan2(float(cr.mean()), float(cb.mean()))) % 360)
    return m


@dataclass
class Check:
    key: str
    label: str
    value: float
    lo: float
    hi: float

    @property
    def ok(self) -> bool:
        return self.lo <= self.value <= self.hi

    def text(self) -> str:
        unit = "°" if "hue" in self.key else ("%" if "pct" in self.key else "")
        mark = "정상" if self.ok else ("낮음" if self.value < self.lo else "높음")
        return f"{self.label} {self.value:.1f}{unit} ({self.lo:g}~{self.hi:g}{unit}, {mark})"

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "ok": self.ok}


LABELS = {"skin_ire": "얼굴 밝기 IRE", "mid_ire": "중간 밝기 IRE", "black_ire": "블랙 IRE", "white_ire": "화이트 IRE",
          "clip_pct": "하이라이트 클리핑", "skin_hue": "피부 색상", "skin_chroma": "피부 채도", "cast": "색 틀어짐",
          "chroma_mid": "배경 채도", "spread": "대비(p90−p10)"}


def assess(m: dict[str, Any]) -> list[Check]:
    """정상 범위 판정. 얼굴이 있으면 밝기·색은 얼굴로(배경의 조명은 장면의 것), 없으면 화면 중간·무채색으로."""
    keys = ["black_ire", "white_ire", "clip_pct", "chroma_mid", "spread"]
    if "skin_ire" in m:
        keys = ["skin_ire", "skin_hue", "skin_chroma"] + keys
    else:
        keys = ["mid_ire"] + (["cast"] if "cast" in m else []) + keys
    return [Check(k, LABELS[k], float(m[k]), *OK[k]) for k in keys if k in m]


def all_ok(checks: list[Check]) -> bool:
    return all(c.ok for c in checks)


def summary(checks: list[Check]) -> str:
    bad = [c for c in checks if not c.ok]
    if not bad:
        return "모든 항목 정상 범위"
    return " · ".join(c.text() for c in bad)


def chroma_noise_gain(before: list[np.ndarray], after: list[np.ndarray]) -> float:
    """보정이 국소 색 잡음(압축 4:2:0 덩어리)을 몇 배로 키웠나 — 1.5 넘으면 얼룩이 보이기 시작한다."""
    def hp(x: np.ndarray) -> float:
        _, a, b = _lab(x)
        k = 4
        h, w = a.shape[:2]
        if h < 2 * k + 2 or w < 2 * k + 2:
            return float(np.hypot(a - a.mean(), b - b.mean()).mean())
        # 상자 평균과의 차(국소 잡음) — 적분 영상으로 빠르게
        def box(c: np.ndarray) -> np.ndarray:
            p = np.pad(c, k + 1, mode="edge").cumsum(0).cumsum(1)
            n = 2 * k + 1
            s = p[n:, n:] - p[:-n, n:] - p[n:, :-n] + p[:-n, :-n]
            return s[: h, : w] / (n * n)
        return float(np.hypot(a - box(a), b - box(b)).mean())
    vb = np.mean([hp(f) for f in before]) if before else 0.0
    va = np.mean([hp(f) for f in after]) if after else 0.0
    return float(va / max(1e-6, vb))


# ---------------------------------------------------------------------------
# 그림
# ---------------------------------------------------------------------------

def _waveform(y: np.ndarray, w: int = 256, h: int = 160, color=(160, 255, 170)) -> np.ndarray:
    """열마다 밝기 분포(위가 100 IRE). y: (H, W) 0~1."""
    H, W = y.shape
    cols = np.minimum((np.arange(W) * w // W), w - 1)
    xs = np.broadcast_to(cols, (H, W)).ravel()
    ys = np.clip(((1 - y.ravel()) * (h - 1)).round().astype(int), 0, h - 1)
    acc = np.zeros((h, w), np.float32)
    np.add.at(acc, (ys, xs), 1.0)
    acc = np.log1p(acc) / max(1e-6, np.log1p(acc).max())
    img = (acc[..., None] * np.array(color, np.float32)[None, None, :]).astype(np.uint8)
    for ire in (0, 25, 50, 75, 100):
        r = int(round((1 - ire / 100) * (h - 1)))
        img[r, :] = np.maximum(img[r, :], 60)
    return img


def _vectorscope(x: np.ndarray, size: int = 160) -> np.ndarray:
    cb, cr = cbcr(x.reshape(-1, 3))
    scale = (size / 2 - 4) / 0.5
    px = np.clip((size / 2 + cb * scale).round().astype(int), 0, size - 1)
    py = np.clip((size / 2 - cr * scale).round().astype(int), 0, size - 1)
    acc = np.zeros((size, size), np.float32)
    np.add.at(acc, (py, px), 1.0)
    acc = np.log1p(acc) / max(1e-6, np.log1p(acc).max())
    img = (acc[..., None] * np.array([200, 255, 200], np.float32)).astype(np.uint8)
    c = size / 2
    yy, xx = np.mgrid[0:size, 0:size]
    rr = np.hypot(xx - c, yy - c)
    for rad in (0.25 * scale, (size / 2 - 4)):          # 채도 0.25 · 0.5(가장자리) 원
        ring = np.abs(rr - rad) < 0.6
        img[ring] = np.maximum(img[ring], 55)
    # 피부색 선(I 선)
    t = np.linspace(0, size / 2 - 4, 200)
    lx = (c + t * math.cos(math.radians(SKIN_LINE_DEG))).astype(int)
    ly = (c - t * math.sin(math.radians(SKIN_LINE_DEG))).astype(int)
    img[ly, lx] = [255, 170, 120]
    return img


def draw(rows: list[tuple[str, list[np.ndarray]]], *, title: str = "") -> bytes:
    """행마다(예: 원본 / 보정) 파형 · RGB 퍼레이드 · 벡터스코프. 반환: JPEG."""
    from PIL import Image, ImageDraw
    from .auto import _font
    cell_w, cell_h, pad, head = 256, 160, 8, 30
    W = pad + cell_w + pad + 3 * 96 + pad + cell_h + pad
    H = head + len(rows) * (cell_h + pad + 22) + pad
    sheet = Image.new("RGB", (W, H), (14, 14, 16))
    d = ImageDraw.Draw(sheet)
    font = _font(18)
    small = _font(15)
    d.text((pad, 6), title or "스코프 — 파형 · RGB 퍼레이드 · 벡터스코프(주황 선 = 피부색 선)", fill=(235, 235, 235), font=small)
    for i, (label, frames) in enumerate(rows):
        x = np.concatenate([f for f in frames], axis=1) if len(frames) > 1 else frames[0]
        top = head + i * (cell_h + pad + 22)
        d.text((pad, top), label, fill=(255, 255, 255), font=font)
        top += 22
        wf = _waveform(luma(x))
        sheet.paste(Image.fromarray(wf), (pad, top))
        px = pad + cell_w + pad
        for ch, col in enumerate([(255, 90, 90), (90, 255, 110), (100, 150, 255)]):
            p = _waveform(x[..., ch], w=96, color=col)
            sheet.paste(Image.fromarray(p), (px + ch * 96, top))
        vx = px + 3 * 96 + pad
        sheet.paste(Image.fromarray(_vectorscope(x)), (vx, top))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=90)
    return buf.getvalue()
