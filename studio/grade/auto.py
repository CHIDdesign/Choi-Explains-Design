"""자동 색보정 — 샘플 프레임 분석 → 교정 + 룩 → 33³ 3D LUT(.cube) → 프록시에 굽는다.

1) 남길 구간에서 프레임을 고르게 뽑아(얼굴 위치 포함) 통계를 낸다.
순서는 컬러리스트의 3단계(참고: Zac Watson "3 Step Premiere Pro Color Grading", "Color Grading Full Walkthrough")를 따른다.
2) 교정(Correction) — 먼저 맞게 만든다: 화이트밸런스는 **피부를 피부색(CIELAB 색상 약 50°)에 놓는 것**이 기준(무채색 픽셀은
   출발점), 블랙/화이트 포인트 · 노출(얼굴 55~70 IRE) · 채도. 장면의 조명(따뜻한 방, 창가의 푸른빛)은 지우지 않는다.
3) 풍부함(enrich) — 'LUT 을 낮은 세기로': 채도를 레퍼런스 쪽으로 조금(최대 1.6배, 피부는 40%), 온기는 밝은 곳에만
   조금(b* 최대 +5, 피부 50%, 흰 것은 흰 채로), 중간톤 대비 살짝. **화면 전체의 평균색을 어디로 옮기지 않는다** —
   예전엔 평균을 레퍼런스(b +14.5)에 맞추느라 파란 조명의 방을 통째로 주황·노랑으로 만들었다(얼굴이 오렌지).
4) 룩(Look) 5가지 — 웜 리치(기본) · 내추럴 · 웜 필름 · 클린 브라이트 · 시네마틱 — 를 같은 프레임에 입혀 비교 시트를
   만들고 🎨 컬러리스트(Claude 비전)가 고른다. Claude 가 없으면 '웜 리치'.
5) 피부 보호(skin_guard) — 마지막에 피부만 점검: 색상 32~60°, 채도 30 이하(넘으면 되돌림). 주황·노랑·초록 피부 금지.
6) 전부를 LUT 하나로 구워 FFmpeg lut3d 로 프록시에 적용 → 롱폼·숏폼·썸네일이 같은 색.

모든 연산은 감마 인코딩된 RGB(0~1) 기준이며, 화이트밸런스만 선형광에서 한다.
"""
from __future__ import annotations

import io
import math
import subprocess
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Optional

import numpy as np

from ..media.ffmpeg import FFmpeg, FFmpegError, MediaInfo, hdr_to_sdr_filter
from ..util import _popen_kwargs

LUT_SIZE = 33


# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------

@dataclass
class Correction:
    gains: tuple[float, float, float] = (1.0, 1.0, 1.0)   # 선형광 채널 게인(화이트밸런스)
    black: float = 0.0                                     # 입력 블랙 포인트
    white: float = 1.0                                     # 입력 화이트 포인트
    gamma: float = 1.0                                     # 중간톤(out = in ** gamma, <1 이면 밝아짐)
    sat: float = 1.0
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Look:
    """룩 = **목표값**. 얼마나 더할지는 영상마다 measure() → plan_recipe() 가 정한다(같은 룩이라도 영상마다 양이 다르다)."""
    name: str
    label: str
    target_contrast: float = 0.60   # 밝기 스프레드(p90 − p10, 0~1). 평평한 로그 소스 0.3~0.4, 또렷한 영상 0.6~0.7
    target_chroma: float = 18.0     # 피부 아닌 중간톤의 채도 중앙값(CIELAB C)
    target_skin_chroma: float = 23.0
    target_warmth: float = 6.0      # 중간톤·하이라이트 무채색이 가질 b*(온기). 흰 것은 보호
    fade: float = 0.0               # 블랙 들어올림(필름 느낌)
    exposure: float = 0.0           # 감마로 환산(+ 밝게)
    vibrance: float = 0.06          # 채도 낮은 곳을 더 올림(피부 보호)
    shadows: tuple[float, float, float] = (0.0, 0.0, 0.0)     # 스플릿 토닝 — 어두운 영역 RGB 오프셋
    highlights: tuple[float, float, float] = (0.0, 0.0, 0.0)  # 밝은 영역 RGB 오프셋
    rolloff: float = 0.3            # 하이라이트 부드럽게 눌러주기


LOOKS: dict[str, Look] = {l.name: l for l in [
    # 기본: 따뜻하고 풍부하게 + 살짝 대비 — 사용자 취향(스탠드 조명의 따뜻한 방 · 건강한 피부 · 깊은 암부)
    Look("warm_rich", "웜 리치", target_contrast=0.63, target_chroma=21.0, target_skin_chroma=25.0, target_warmth=9.0,
         vibrance=0.08, shadows=(-0.003, 0.0, 0.005), highlights=(0.014, 0.007, -0.012), rolloff=0.45),
    Look("natural", "내추럴", target_contrast=0.58, target_chroma=16.0, target_skin_chroma=21.0, target_warmth=3.0,
         vibrance=0.06, rolloff=0.3),
    Look("warm_film", "웜 필름", target_contrast=0.60, target_chroma=17.0, target_skin_chroma=22.0, target_warmth=11.0,
         fade=0.025, vibrance=0.06, shadows=(-0.004, 0.004, 0.012), highlights=(0.014, 0.006, -0.010), rolloff=0.5),
    Look("clean_bright", "클린 브라이트", target_contrast=0.55, target_chroma=19.0, target_skin_chroma=23.0,
         target_warmth=5.0, exposure=0.06, vibrance=0.10, rolloff=0.45),
    Look("cinematic", "시네마틱", target_contrast=0.69, target_chroma=15.0, target_skin_chroma=20.0, target_warmth=4.0,
         fade=0.02, vibrance=0.04, shadows=(-0.012, 0.004, 0.016), highlights=(0.018, 0.006, -0.012), rolloff=0.6),
]}


# 레퍼런스 색(CIELAB 평균): 사용자가 직접 편집한 장면(2026-09-30 제공, 따뜻한 스탠드 조명의 방)을 잰 값.
# 룩의 목표값(채도·온기)이 여기서 나왔다. 화면 평균을 이 값으로 옮기지 않는다(그렇게 했더니 파란 방이 통째로 주황).
# user/reference_frames/ 에 좋아하는 장면(jpg/png)을 넣으면 그 평균으로 목표를 조금 옮긴다(reference_targets).
REFERENCE_LAB = {"L": 41.8, "a": 4.7, "b": 14.5, "C": 16.9}
SKIN_HUE = (32.0, 60.0)        # 피부가 자연스러운 CIELAB 색상 범위(도). 낮으면 붉거나 자주, 높으면 노랗거나 초록
SKIN_HUE_TARGET = 50.0
SKIN_CHROMA_MAX = 30.0         # 이보다 진한 피부는 주황
WARMTH_MAX_B = 9.0             # 한 영상에 더할 수 있는 온기(b*) 상한
CHROMA_GAIN_MAX = 1.8          # 채도 이득 상한(피부는 따로, 1.3)
CONTRAST_MAX = 0.32            # S-커브 상한


@dataclass
class GradeChoice:
    look: str = "warm_rich"
    strength: float = 1.0          # 룩 적용 정도(0~1) — 레시피 양 전체에 곱한다
    match: float = 1.0             # (호환) 0 이면 레시피(풍부함·대비·온기)를 끈다
    src_lab: tuple = ()            # 교정 후 원본 평균 (L, a, b, C) — 분석 때 채움
    ref_lab: tuple = ()            # 레퍼런스 평균 (L, a, b, C) — 비면 REFERENCE_LAB
    recipe: dict = field(default_factory=dict)   # plan_recipe() 결과(이 영상에 맞춘 양). 비면 src/ref 로 보수적 기본
    exposure: float = 0.0          # 추가 미세 조정(-0.15~0.15)
    warmth: float = 0.0            # (-0.4~0.4)
    saturation: float = 1.0        # (0.85~1.15)
    reason: str = ""
    by: str = "rule"

    def clamp(self) -> "GradeChoice":
        c = replace(self)
        c.look = c.look if c.look in LOOKS else "warm_rich"
        c.strength = float(min(1.0, max(0.0, c.strength)))
        c.match = float(min(1.2, max(0.0, c.match)))
        c.exposure = float(min(0.15, max(-0.15, c.exposure)))
        c.warmth = float(min(0.4, max(-0.4, c.warmth)))
        c.saturation = float(min(1.15, max(0.85, c.saturation)))
        return c


# ---------------------------------------------------------------------------
# 색 연산(numpy, 0~1)
# ---------------------------------------------------------------------------

def _to_linear(x: np.ndarray) -> np.ndarray:
    return np.power(np.clip(x, 0, 1), 2.2)


def _to_gamma(x: np.ndarray) -> np.ndarray:
    return np.power(np.clip(x, 0, 1), 1 / 2.2)


def _luma(x: np.ndarray) -> np.ndarray:
    return x[..., 0] * 0.2126 + x[..., 1] * 0.7152 + x[..., 2] * 0.0722


def _hue_sat(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mx = x.max(axis=-1)
    mn = x.min(axis=-1)
    d = mx - mn + 1e-9
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60.0
    s = np.where(mx > 1e-6, (mx - mn) / (mx + 1e-9), 0.0)
    return h, s


def skin_mask(x: np.ndarray) -> np.ndarray:
    """피부톤(색상 5~45°, 채도 0.12~0.7, 너무 어둡지 않음) 가중치 0~1."""
    h, s = _hue_sat(x)
    lum = _luma(x)
    hue_w = np.clip(1 - np.abs(h - 22.0) / 26.0, 0, 1)
    sat_w = np.clip((s - 0.1) / 0.1, 0, 1) * np.clip((0.75 - s) / 0.1, 0, 1)
    return hue_w * sat_w * np.clip((lum - 0.12) / 0.1, 0, 1)


def _scurve(x: np.ndarray, amount: float) -> np.ndarray:
    s = x * x * (3 - 2 * x)
    return x + amount * (s - x)


def _rolloff(x: np.ndarray, amount: float, knee: float = 0.82) -> np.ndarray:
    if amount <= 0:
        return x
    over = np.clip(x - knee, 0, None)
    span = 1 - knee
    soft = knee + span * (1 - np.exp(-over / span * 1.6)) / (1 - math.exp(-1.6))
    return np.where(x > knee, x + amount * (soft - x), x)


def apply_correction(x: np.ndarray, c: Correction) -> np.ndarray:
    lin = _to_linear(x) * np.array(c.gains, dtype=np.float32)
    y = _to_gamma(lin)
    y = np.clip((y - c.black) / max(1e-3, c.white - c.black), 0, 1)
    y = np.power(y, c.gamma)
    if abs(c.sat - 1) > 1e-3:
        lum = _luma(y)[..., None]
        y = lum + (y - lum) * c.sat
    return np.clip(y, 0, 1)


def apply_look(x: np.ndarray, look: Look, strength: float = 1.0, *, exposure: float = 0.0, warmth: float = 0.0,
               saturation: float = 1.0) -> np.ndarray:
    """룩의 캐릭터(노출·하이라이트 롤오프·페이드·스플릿 토닝·바이브런스)와 컬러리스트의 미세 조정.
    대비·채도·온기의 '양'은 여기가 아니라 레시피(enrich)가 영상마다 정한다."""
    if strength <= 0 and not exposure and not warmth and saturation == 1.0:
        return x
    k = strength
    skin = skin_mask(x)[..., None]
    y = x
    if abs(warmth) > 1e-4:          # 컬러리스트 미세 조정(선형광 색온도)
        lin = _to_linear(y) * np.array([1 + 0.06 * warmth, 1.0, 1 - 0.06 * warmth], dtype=np.float32)
        y = _to_gamma(lin)
    ex = look.exposure * k + exposure
    if abs(ex) > 1e-4:
        y = np.power(np.clip(y, 0, 1), 1 / (1 + 1.6 * ex))
    y = _rolloff(np.clip(y, 0, 1), look.rolloff * k)
    if look.fade:
        y = look.fade * k + y * (1 - look.fade * k)
    # 스플릿 토닝(피부는 70% 보호)
    lum = _luma(y)[..., None]
    protect = 1 - 0.7 * skin
    sh = np.array(look.shadows, dtype=np.float32) * k
    hi = np.array(look.highlights, dtype=np.float32) * k
    y = y + protect * (sh * (1 - lum) ** 2 + hi * lum ** 2)
    # 바이브런스(채도 낮은 곳을 더, 피부는 덜) + 사용자 채도
    lum = _luma(y)[..., None]
    _, sat_px = _hue_sat(np.clip(y, 0, 1))
    vib = 1 + look.vibrance * k * (1 - sat_px[..., None]) * (1 - 0.6 * skin)
    y = lum + (y - lum) * saturation * vib
    return np.clip(y, 0, 1)


_WP = np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
_M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]], dtype=np.float32)
_MI = np.linalg.inv(_M).astype(np.float32)


def srgb_to_lab(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lin = np.where(x <= 0.04045, x / 12.92, ((np.clip(x, 0, 1) + 0.055) / 1.055) ** 2.4)
    xyz = lin @ _M.T / _WP
    f = np.where(xyz > 0.008856, np.cbrt(np.clip(xyz, 0, None)), 7.787 * xyz + 16 / 116)
    return 116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])


def lab_to_srgb(L: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    fy = (L + 16) / 116
    f = np.stack([fy + a / 500, fy, fy - b / 200], -1)
    xyz = np.where(f > 0.206893, f ** 3, (f - 16 / 116) / 7.787) * _WP
    lin = np.clip(xyz @ _MI.T, 0, None)
    return np.clip(np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.power(lin, 1 / 2.4) - 0.055), 0, 1)


def lab_stats(x: np.ndarray) -> tuple[float, float, float, float]:
    L, a, b = srgb_to_lab(x.reshape(-1, 3))
    return float(L.mean()), float(a.mean()), float(b.mean()), float(np.hypot(a, b).mean())


def reference_lab(folder: Optional[Path] = None) -> tuple[float, float, float, float]:
    """user/reference_frames/ 의 이미지 평균(없으면 기본 레퍼런스)."""
    if folder and folder.is_dir():
        from PIL import Image
        arrs = []
        for f in sorted(folder.iterdir())[:24]:
            if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                try:
                    im = Image.open(f).convert("RGB")
                    im.thumbnail((480, 480))
                    arrs.append(np.asarray(im, dtype=np.float32).reshape(-1, 3) / 255.0)
                except OSError:
                    continue
        if arrs:
            return lab_stats(np.concatenate(arrs))
    r = REFERENCE_LAB
    return r["L"], r["a"], r["b"], r["C"]


def _lab_hue(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.degrees(np.arctan2(b, a)) % 360.0


def measure(frames: list[np.ndarray]) -> dict[str, float]:
    """교정된 프레임들의 '지금 상태' — 레시피는 여기서 목표까지의 거리로 정해진다.
    spread: 밝기 p90 − p10 (대비) · p005: 암부 바닥 · chroma_mid: 피부 아닌 중간톤 채도 중앙값 · skin_chroma: 피부 채도 중앙값
    · neutral_b: 무채색에 가까운 중간톤·하이라이트의 b*(장면의 온기) · skin_hue."""
    pix = np.concatenate([f.reshape(-1, 3) for f in frames]).astype(np.float32)
    if len(pix) > 400_000:
        pix = pix[np.random.default_rng(0).choice(len(pix), 400_000, replace=False)]
    lum = _luma(pix)
    L, a, b = srgb_to_lab(pix)
    C = np.hypot(a, b)
    skin = skin_mask(pix)
    mid = (L > 25) & (L < 80)
    non_skin_mid = mid & (skin < 0.3)
    sk = skin > 0.3
    neutral = (C < 12) & (L > 35) & (L < 88)
    m = {
        "spread": float(np.percentile(lum, 90) - np.percentile(lum, 10)),
        "p005": float(np.percentile(lum, 0.5)),
        "p50": float(np.percentile(lum, 50)),
        "chroma_mid": float(np.median(C[non_skin_mid])) if non_skin_mid.sum() > 200 else float(np.median(C)),
        "skin_chroma": float(np.median(C[sk])) if sk.sum() > 200 else 0.0,
        "skin_hue": float(_lab_hue(np.array(a[sk].mean()), np.array(b[sk].mean()))) if sk.sum() > 200 else -1.0,
        "neutral_b": float(np.median(b[neutral])) if neutral.sum() > 200 else float(np.median(b[mid])) if mid.sum() else 0.0,
        "mean_b": float(b.mean()),
    }
    # 레시피의 대비 계산용: 밝기 표본(2000개)
    m["_lum"] = np.sort(lum)[:: max(1, len(lum) // 2000)].astype(np.float32)
    return m


def reference_targets(look: Look, ref: tuple) -> tuple[float, float]:
    """(채도 목표, 온기 목표) — user/reference_frames 가 있으면 그 평균으로 룩 목표를 조금 옮긴다(±30%)."""
    if not ref:
        return look.target_chroma, look.target_warmth
    rL, ra, rb, rC = ref
    base_c, base_b = REFERENCE_LAB["C"], REFERENCE_LAB["b"]
    chroma = look.target_chroma * float(np.clip(rC / max(1.0, base_c), 0.7, 1.3))
    warmth = look.target_warmth + float(np.clip(rb - base_b, -4.0, 4.0)) * 0.5
    return chroma, max(0.0, warmth)


def plan_recipe(m: dict, look: Look, ref: tuple = ()) -> dict[str, Any]:
    """이 영상에 맞춘 양: 목표(룩) − 지금(measure). 같은 룩이라도 평평한 로그 소스엔 대비를 많이, 이미 또렷한 영상엔 거의
    안 주고, 채도 낮은 영상엔 채도를 많이, 파란 방엔 온기를 조금만(상한) 준다."""
    target_c, target_b = reference_targets(look, ref)
    why: list[str] = []
    # 1) 대비: S-커브 세기를 이분 탐색으로 — 밝기 스프레드가 목표에 닿을 만큼만(최소 0.04: '살짝'은 늘)
    lum = m.get("_lum")
    contrast = 0.04
    if lum is not None and len(lum) > 50 and m["spread"] < look.target_contrast:
        lo, hi = 0.0, CONTRAST_MAX
        for _ in range(14):
            mid_a = (lo + hi) / 2
            y = _scurve(lum, mid_a)
            if float(np.percentile(y, 90) - np.percentile(y, 10)) < look.target_contrast:
                lo = mid_a
            else:
                hi = mid_a
        contrast = max(0.04, min(CONTRAST_MAX, (lo + hi) / 2))
    why.append(f"명암 {m['spread']:.2f}→S커브 {contrast:.2f}")
    # 2) 암부 깊이: 교정 뒤에도 떠 있는 블랙(0.5% 지점)을 목표 0.012 로
    black = float(np.clip(m["p005"] - 0.012, 0.0, 0.035))
    if black > 0.004:
        why.append(f"암부 −{black:.3f}")
    # 3) 채도: 피부 아닌 중간톤 채도 → 목표(이득 1~1.8배), 피부는 따로(0.9~1.3배, 위에서 30 이하로 막힘)
    chroma_gain = float(np.clip(target_c / max(4.0, m["chroma_mid"]), 1.0, CHROMA_GAIN_MAX))
    skin_gain = float(np.clip(look.target_skin_chroma / max(6.0, m["skin_chroma"]), 0.9, 1.3)) if m.get("skin_chroma") else 1.05
    why.append(f"채도 {m['chroma_mid']:.0f}→×{chroma_gain:.2f}(피부 ×{skin_gain:.2f})")
    # 4) 온기: 무채색 중간톤의 b* → 목표(더할 뿐, 빼지 않는다; 상한)
    warmth = float(np.clip(target_b - m["neutral_b"], 0.0, WARMTH_MAX_B))
    why.append(f"온기 b {m['neutral_b']:+.0f}→+{warmth:.1f}")
    return {"contrast": round(contrast, 4), "black": round(black, 4), "chroma_gain": round(chroma_gain, 3),
            "skin_gain": round(skin_gain, 3), "warmth": round(warmth, 2), "why": why,
            "measured": {k: round(v, 3) for k, v in m.items() if not k.startswith("_")}}


def recipe_summary(recipe: dict) -> str:
    return " · ".join(recipe.get("why", [])) or "기본"


def default_recipe(src: tuple, ref: tuple) -> dict[str, Any]:
    """measure 없이(그리드만 있을 때·예전 호출) 쓰는 보수적 레시피: 채도는 레퍼런스 대비로, 온기는 작게."""
    sC = src[3] if src else REFERENCE_LAB["C"]
    sb = src[2] if src else REFERENCE_LAB["b"]
    rC = ref[3] if ref else REFERENCE_LAB["C"]
    rb = ref[2] if ref else REFERENCE_LAB["b"]
    return {"contrast": 0.08, "black": 0.0, "chroma_gain": float(np.clip(rC / max(2.0, sC), 1.0, 1.4)),
            "skin_gain": 1.05, "warmth": float(np.clip(0.35 * (rb - sb), 0.0, 5.0)), "why": ["기본"]}


def enrich(x: np.ndarray, recipe: dict, k: float = 1.0) -> np.ndarray:
    """레시피대로 — 채도(중간톤에 가장 많이, 피부는 따로, 파랑·청록은 절반), 온기(밝은 곳에만, 흰 것 보호, 크림빛),
    대비(S-커브 + 암부 깊이). 화면 평균색을 옮기지 않는다: 온기는 더할 뿐이고 암부는 건드리지 않는다."""
    if k <= 0 or not recipe:
        return x
    L, a, b = srgb_to_lab(x)
    C = np.hypot(a, b)
    h = _lab_hue(a, b)
    skin = skin_mask(x)
    w = np.clip(L / 100, 0, 1)
    mid = 4 * w * (1 - w)
    # 채도
    g = 1 + (float(recipe.get("chroma_gain", 1.0)) - 1) * k
    gain = 1 + (g - 1) * (0.55 + 0.45 * mid)
    cool = np.clip(1 - np.abs(((h - 240 + 180) % 360) - 180) / 70, 0, 1)   # 170°~310°(청록·파랑·보라) 1
    gain = 1 + (gain - 1) * (1 - 0.5 * cool)
    sg = 1 + (float(recipe.get("skin_gain", 1.0)) - 1) * k
    gain = gain * (1 - skin) + sg * skin
    a2, b2 = a * gain, b * gain
    # 온기(밝은 곳에만) — b* 와 그 40% 의 a*(노랑이 아니라 크림·앰버)
    db = float(recipe.get("warmth", 0.0)) * k
    if db > 0.05:
        bright = np.clip((L - 25) / 35, 0, 1)
        white = np.clip((L - 72) / 10, 0, 1) * np.clip((9 - C) / 5, 0, 1)
        wgt = bright * (1 - 0.5 * skin) * (1 - 0.75 * white)
        a2 = a2 + 0.4 * db * wgt
        b2 = b2 + db * wgt
    # 대비: S-커브 + 암부 깊이(밝기만)
    t = np.clip(L / 100, 0, 1)
    t = _scurve(t, float(recipe.get("contrast", 0.0)) * k)
    blk = float(recipe.get("black", 0.0)) * k
    if blk > 0:
        t = np.clip((t - blk) / (1 - blk), 0, 1)
    return lab_to_srgb(100 * t, a2, b2)


def _skin_qualifier(L: np.ndarray, C: np.ndarray, h: np.ndarray) -> np.ndarray:
    """피부 보호용 넓은 판정(CIELAB): 색상 12~100°, 채도 8~78, 밝기 22~95. 컬러리스트의 HSL 보조 키어와 같은 역할 —
    이미 노랗거나 붉어진 얼굴도 잡아야 하므로 skin_mask 보다 넓다. 벽·나무처럼 비슷한 색도 조금 잡히지만
    되돌리는 방향(피부색 선·채도 30)이 그런 것에도 해롭지 않다."""
    hue_w = np.clip((h - 12) / 12, 0, 1) * np.clip((100 - h) / 12, 0, 1)
    c_w = np.clip((C - 8) / 6, 0, 1) * np.clip((78 - C) / 14, 0, 1)
    l_w = np.clip((L - 22) / 8, 0, 1) * np.clip((95 - L) / 7, 0, 1)      # 밝은 피부·하이라이트(L 85~90)도 잡는다
    return hue_w * c_w * l_w


def skin_guard(x: np.ndarray) -> np.ndarray:
    """마지막 점검 — 피부 픽셀만: 색상을 32~60° 안으로(넘친 만큼 되돌림), 채도 30 이상은 눌러서 주황이 되지 않게.
    피부가 아닌 곳은 그대로(배경은 장면의 조명을 지킨다)."""
    L, a, b = srgb_to_lab(x)
    C = np.hypot(a, b)
    h = _lab_hue(a, b)
    skin = _skin_qualifier(L, C, h)
    if float(skin.max()) < 0.05:
        return x
    lo, hi = SKIN_HUE
    target = np.where(h < lo, lo, np.where(h > hi, hi, h))
    # 범위 밖이면 경계로 — 6° 넘게 벗어난 픽셀은 완전히, 경계 가까이(0~6°)는 70~100%(피부의 자연스러운 편차는 남긴다).
    # 범위 안은 그대로
    off = np.minimum(np.abs(h - target), 60.0) / 6.0
    rot = skin * np.clip(0.7 + 0.3 * off, 0, 1) * (h != target)
    h2 = h + (target - h) * rot
    C2 = np.where(C > SKIN_CHROMA_MAX, SKIN_CHROMA_MAX + (C - SKIN_CHROMA_MAX) * 0.1, C)
    C2 = C + (C2 - C) * skin
    rad = np.radians(h2)
    return lab_to_srgb(L, C2 * np.cos(rad), C2 * np.sin(rad))


def grade(x: np.ndarray, c: Correction, choice: GradeChoice) -> np.ndarray:
    """교정 → 레시피(이 영상에 맞춘 대비·채도·온기) → 룩의 캐릭터 → 피부 보호. 픽셀마다 독립이라 LUT 으로 구울 수 있다."""
    ch = choice.clamp()
    y = apply_correction(x, c)
    if ch.match > 0:
        recipe = ch.recipe or default_recipe(tuple(ch.src_lab), tuple(ch.ref_lab) if ch.ref_lab else reference_lab())
        y = enrich(y, recipe, ch.strength if ch.recipe else min(1.0, ch.match))
    y = apply_look(y, LOOKS[ch.look], ch.strength, exposure=ch.exposure, warmth=ch.warmth,
                   saturation=ch.saturation)
    return skin_guard(y)


def plan_choice(frames: list[np.ndarray], c: Correction, look: str = "warm_rich", ref: tuple = (),
                **kw: Any) -> GradeChoice:
    """교정된 프레임을 재서 그 영상에 맞춘 GradeChoice(레시피 포함)를 만든다."""
    corrected = [apply_correction(f, c) for f in frames]
    m = measure(corrected)
    src = lab_stats(np.concatenate([f.reshape(-1, 3) for f in corrected]))
    lk = LOOKS.get(look, LOOKS["warm_rich"])
    return GradeChoice(look=lk.name, src_lab=src, ref_lab=ref, recipe=plan_recipe(m, lk, ref), **kw)


# ---------------------------------------------------------------------------
# 분석
# ---------------------------------------------------------------------------

def sample_frames(ff: FFmpeg, video: str | Path, times: list[float], info: MediaInfo, width: int = 480
                  ) -> list[tuple[float, np.ndarray]]:
    """지정 시각의 프레임을 RGB float(0~1) 로. HDR 은 SDR 로 톤매핑한 모습 기준."""
    dw, dh = info.display_size
    height = int(round(width * dh / max(1, dw) / 2) * 2)
    vf = (hdr_to_sdr_filter() + "," if info.is_hdr else "") + f"scale={width}:{height}:flags=area"
    def grab(t: float) -> Optional[tuple[float, np.ndarray]]:
        args = [ff.ffmpeg, "-v", "error", "-nostdin", "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1",
                "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        try:
            r = subprocess.run(args, capture_output=True, timeout=120, **_popen_kwargs())
        except subprocess.TimeoutExpired:
            return None
        if r.returncode != 0 or len(r.stdout) < width * height * 3:
            return None
        arr = np.frombuffer(r.stdout[: width * height * 3], np.uint8).reshape(height, width, 3)
        return t, arr.astype(np.float32) / 255.0

    # 시각마다 ffmpeg 하나 — 4K HEVC·HDR 은 한 장에 몇 초씩 걸려 4개씩 동시에(순서는 그대로)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        out = [r for r in ex.map(grab, times) if r is not None]
    if not out:
        raise FFmpegError("색 분석용 프레임을 읽지 못했습니다.")
    return out


def face_box(face: Optional[dict], w: int, h: int) -> Optional[tuple[int, int, int, int]]:
    if not face or face.get("s", 0) <= 0.02:
        return None
    fh = face["s"] * h
    cx, cy = face["x"] * w, face["y"] * h
    x0, x1 = int(cx - fh * 0.32), int(cx + fh * 0.32)
    y0, y1 = int(cy - fh * 0.30), int(cy + fh * 0.35)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    return (x0, y0, x1, y1) if x1 - x0 > 4 and y1 - y0 > 4 else None


def analyze(frames: list[tuple[float, np.ndarray]], faces: list[Optional[dict]]) -> dict[str, Any]:
    pix = np.concatenate([f.reshape(-1, 3) for _, f in frames])
    lum = _luma(pix)
    h, s = _hue_sat(pix)
    face_pix = []
    for (_, f), fc in zip(frames, faces):
        box = face_box(fc, f.shape[1], f.shape[0])
        if box:
            x0, y0, x1, y1 = box
            face_pix.append(f[y0:y1, x0:x1].reshape(-1, 3))
    face = np.concatenate(face_pix) if face_pix else None
    # 무채색 후보: 중간 밝기 + 저채도(피부 제외)
    neutral = (lum > 0.12) & (lum < 0.9) & (s < 0.22)
    lap = []
    for _, f in frames[:6]:
        g = _luma(f)
        l = np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:])
        lap.append(float(np.median(l)))
    stats: dict[str, Any] = {
        "p005": float(np.percentile(lum, 0.5)), "p50": float(np.percentile(lum, 50)),
        "p997": float(np.percentile(lum, 99.7)), "sat_mean": float(np.mean(s)),
        "neutral_frac": float(np.mean(neutral)), "noise": float(np.median(lap)) if lap else 0.0,
        "mean_rgb": [float(v) for v in pix.mean(axis=0)],
    }
    if neutral.sum() > 500:
        stats["neutral_rgb_lin"] = [float(v) for v in _to_linear(pix[neutral]).mean(axis=0)]
    stats["gray_world_lin"] = [float(v) for v in _to_linear(pix).mean(axis=0)]
    if face is not None and len(face) > 50:
        fs = skin_mask(face)
        frac = float((fs > 0.3).mean())
        if frac > 0.6:
            sk = face[fs > 0.3]
        else:   # 색이 크게 틀어졌거나(파란 모니터 불빛) 조명이 섞인 얼굴(한쪽 램프·한쪽 모니터): 피부 마스크는 따뜻한 쪽만
                # 잡으므로 얼굴 상자의 중간 밝기 픽셀 전체(머리카락·배경 제외)로 — 컬러리스트는 얼굴 전체를 본다
            lum_f = _luma(face)
            core = face[(lum_f > np.percentile(lum_f, 30)) & (lum_f < np.percentile(lum_f, 92))]
            sk = core if len(core) > 30 else face
        stats["face_luma"] = float(np.median(_luma(sk)))
        stats["face_rgb"] = [float(v) for v in sk.mean(axis=0)]
        stats["face_frac"] = float((fs > 0.3).mean())
        L_f, a_f, b_f = srgb_to_lab(sk)
        stats["face_lab"] = [float(L_f.mean()), float(a_f.mean()), float(b_f.mean())]
        stats["face_hue"] = float(_lab_hue(a_f.mean(), b_f.mean()))
    return stats


def _skin_line_gains(face_rgb: np.ndarray, gains: np.ndarray, target: float = SKIN_HUE_TARGET,
                     steps: int = 12) -> np.ndarray:
    """얼굴 평균색이 CIELAB 색상 target(도)에 오도록 R·B 게인을 조금씩 조정(피부색 선 위에 놓기).
    채도는 건드리지 않고 색상만 — 색상 오차의 부호로 B(파랑↔노랑)와 R(빨강↔초록)을 나눠 움직인다."""
    g = np.array(gains, dtype=np.float64).copy()
    lin = _to_linear(face_rgb.astype(np.float64))
    for _ in range(steps):
        rgb = _to_gamma(lin * g)[None, :]
        _, a, b = srgb_to_lab(rgb.astype(np.float32))
        a, b = float(a[0]), float(b[0])
        C = math.hypot(a, b)
        if C < 3.0:                          # 거의 무채색 얼굴: 살짝 따뜻하게 밀어 시작
            g = g * np.array([1.02, 1.0, 0.98])
            continue
        err = ((_lab_hue(np.array(a), np.array(b)) - target + 180) % 360) - 180   # -180~180, + 는 노랑·초록·파랑 쪽
        if abs(err) < 2.0:
            break
        # 목표점(같은 채도, 목표 색상)과의 a·b 차이 → R 은 a 차이, B 는 -b 차이로
        ta, tb = C * math.cos(math.radians(target)), C * math.sin(math.radians(target))
        g[0] *= math.exp(0.010 * (ta - a))
        g[2] *= math.exp(-0.010 * (tb - b))
        g = np.clip(g, 0.6, 1.6)
        g = g / (g @ np.array([0.2126, 0.7152, 0.0722]))
    return g


def correction_from_stats(st: dict[str, Any]) -> Correction:
    c = Correction()
    notes = c.notes
    # 1) 화이트밸런스 — 무채색 픽셀(없으면 전체 평균의 절반 세기), 75% 만 적용
    ref = st.get("neutral_rgb_lin")
    weight = 0.75
    if ref is None:
        ref = st["gray_world_lin"]
        weight = 0.4
    ref = np.array(ref) + 1e-6
    gains = ref.mean() / ref
    if gains[0] < gains[2]:      # 장면이 따뜻함(주황 조명) → 식히는 교정은 조금만(따뜻한 룩을 지우지 않게)
        weight *= 0.35
    gains = 1 + (gains - 1) * weight
    gains = np.clip(gains, 0.8, 1.25)
    # 피부 기준: 교정 후 피부의 CIELAB 색상이 피부색 선(약 50°) 근처여야 한다. 벗어나 있으면(모니터 불빛의 파란 얼굴,
    # 형광등의 초록 얼굴, 백열등의 노란 얼굴) 게인을 풀어서 피부를 그 선에 놓는다 — 컬러리스트가 '교정'에서 하는 일.
    # 따뜻한 장면은 절반만(방의 온기를 남긴다). 게인 0.7~1.4 (R/B 2:1 까지).
    if "face_rgb" in st:
        face0 = np.array(st["face_rgb"], dtype=np.float32)
        before = _lab_hue(*srgb_to_lab(_to_gamma(_to_linear(face0) * gains)[None, :])[1:])[0]
        solved = _skin_line_gains(face0, gains)
        wgt = 0.6 if gains[0] < gains[2] else 0.85
        gains = np.clip(1 + (solved - 1) * wgt, 0.7, 1.4)
        after = _lab_hue(*srgb_to_lab(_to_gamma(_to_linear(face0) * gains)[None, :])[1:])[0]
        if abs(after - before) > 3:
            cold = ((before - SKIN_HUE_TARGET + 180) % 360 - 180) > 0   # 피부색 선보다 노랑·초록·파랑 쪽
            notes.append(f"피부톤을 피부색 선에 맞춤({'차가운' if cold else '붉은'} 얼굴 {before:.0f}° → {after:.0f}°)")
    gains = gains / (gains @ np.array([0.2126, 0.7152, 0.0722]))  # 밝기 보존
    c.gains = tuple(float(round(g, 4)) for g in gains)  # type: ignore[assignment]
    dev = float(np.max(np.abs(np.array(c.gains) - 1)))
    if dev > 0.03:
        notes.append(f"화이트밸런스 {'따뜻하게' if c.gains[2] < c.gains[0] else '차갑게'} 보정({dev * 100:.0f}%)")
    # 2) 블랙/화이트 포인트 — 떠 있는 블랙은 60%만 내리고(밝은 하이키 화면 보호), 늘림은 최대 1.3배
    black = min(0.08, max(0.0, (st["p005"] - 0.02) * 0.6))
    white = max(0.8, min(1.0, st["p997"] + 0.015))
    if white - black < 1 / 1.3:
        mid = (white + black) / 2
        black, white = max(0.0, mid - 0.5 / 1.3), min(1.0, mid + 0.5 / 1.3)
    c.black, c.white = round(black, 4), round(white, 4)
    if black > 0.02 or white < 0.97:
        notes.append(f"명암 범위 정리({black:.2f}~{white:.2f})")
    # 3) 노출 — 얼굴 밝기가 0.50~0.70(없으면 중간값 0.34~0.55) 밖일 때만 가까운 경계로, 감마 0.72~1.3
    if "face_luma" in st:
        cur, lo, hi = st["face_luma"], 0.50, 0.70   # 피부 60~70 IRE(어두운 피부톤도 있어 하한은 50)
    else:
        cur, lo, hi = st["p50"], 0.34, 0.55
    cur = min(0.95, max(0.02, (cur - black) / max(1e-3, white - black)))
    target = min(hi, max(lo, cur))
    g = math.log(target) / math.log(cur) if 0 < cur < 1 else 1.0
    c.gamma = round(float(min(1.3, max(0.72, g))), 3)
    if abs(c.gamma - 1) > 0.05:
        notes.append(f"노출 {'올림' if c.gamma < 1 else '내림'}(감마 {c.gamma:.2f})")
    # 4) 채도 — 밋밋한 로그/플랫 소스는 올리고, 과한 것은 살짝 내림.
    #    단, 교정 후 피부 채도가 원본의 1.1배(최대 0.5)를 넘지 않게 한다(얼굴이 주황색이 되지 않도록).
    sm = st["sat_mean"]
    c.sat = round(float(min(1.25, max(0.9, 1 + (0.26 - sm) * 1.2))), 3)
    if "face_rgb" in st:
        face0 = np.array(st["face_rgb"], dtype=np.float32)[None, :]
        _, s0 = _hue_sat(face0)
        for _ in range(8):
            _, s1 = _hue_sat(apply_correction(face0, c))
            if s1[0] <= min(0.5, s0[0] * 1.1) + 1e-3 or c.sat <= 0.85:
                break
            c.sat = round(c.sat - 0.03, 3)
    if abs(c.sat - 1) > 0.05:
        notes.append(f"채도 {'올림' if c.sat > 1 else '내림'}({c.sat:.2f})")
    return c


def cleanup_filters(st: dict[str, Any]) -> list[str]:
    """노이즈(암부 촬영) 정도에 맞춘 디노이즈 + 은은한 샤픈."""
    noise = st.get("noise", 0.0)
    out = []
    if noise > 0.02:
        out.append("hqdn3d=3:2.5:6:5")
    elif noise > 0.01:
        out.append("hqdn3d=2:1.5:4:3")
    else:
        out.append("hqdn3d=1:1:3:3")
    out.append("unsharp=5:5:0.35:5:5:0")
    return out


# ---------------------------------------------------------------------------
# LUT · 비교 시트
# ---------------------------------------------------------------------------

def write_cube(path: Path, c: Correction, choice: GradeChoice, size: int = LUT_SIZE) -> Path:
    r = np.linspace(0, 1, size, dtype=np.float32)
    # .cube: 빨강이 가장 빨리 변한다(R 안쪽, B 바깥쪽)
    b, g, rr = np.meshgrid(r, r, r, indexing="ij")
    grid = np.stack([rr, g, b], axis=-1).reshape(-1, 3)
    out = grade(grid, c, choice)
    lines = [f"TITLE \"Choi Studio auto grade ({choice.look})\"", f"LUT_3D_SIZE {size}", "DOMAIN_MIN 0 0 0",
             "DOMAIN_MAX 1 1 1"]
    lines += [f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}" for v in out]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


def _font(size: int):
    from PIL import ImageFont
    from ..paths import RENDERER_FONTS
    for f in [Path(RENDERER_FONTS) / "ui" / "Pretendard-SemiBold.otf", Path("C:/Windows/Fonts/malgunbd.ttf")]:
        if f.exists():
            try:
                return ImageFont.truetype(str(f), size)
            except OSError:
                pass
    return ImageFont.load_default(size=size)


def _to_img(x: np.ndarray):
    from PIL import Image
    return Image.fromarray((np.clip(x, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB")


def comparison_sheet(frames: list[np.ndarray], c: Correction, *, cell_w: int = 360, src_lab: tuple = (),
                     ref_lab: tuple = ()) -> bytes:
    """행 = 프레임, 열 = 원본 + 룩들(각 룩의 목표에 맞춰 이 영상용 레시피를 따로 계산). 🎨 컬러리스트가 고를 비교 시트."""
    from PIL import Image, ImageDraw
    cols = [("0 원본", None)] + [(f"{i + 1} {l.label}", l.name) for i, l in enumerate(LOOKS.values())]
    ch = int(round(cell_w * frames[0].shape[0] / frames[0].shape[1]))
    pad, head = 6, 34
    sheet = Image.new("RGB", (len(cols) * (cell_w + pad) + pad, head + len(frames) * (ch + pad) + pad), (18, 18, 18))
    d = ImageDraw.Draw(sheet)
    font = _font(20)
    choices = {name: plan_choice(frames, c, name, ref_lab) for _, name in cols if name}
    for j, (label, name) in enumerate(cols):
        d.text((pad + j * (cell_w + pad) + 4, 6), label, fill=(240, 240, 240), font=font)
        for i, f in enumerate(frames):
            img = f if name is None else grade(f, c, choices[name])
            tile = _to_img(img).resize((cell_w, ch))
            sheet.paste(tile, (pad + j * (cell_w + pad), head + i * (ch + pad)))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def before_after(frame: np.ndarray, c: Correction, choice: GradeChoice, path: Path, width: int = 1280) -> Path:
    """사용자 확인용: 왼쪽 원본 | 오른쪽 보정."""
    from PIL import Image, ImageDraw
    h = int(round(width * frame.shape[0] / frame.shape[1]))
    a = _to_img(frame).resize((width, h))
    b = _to_img(grade(frame, c, choice)).resize((width, h))
    out = Image.new("RGB", (width, h))
    out.paste(a.crop((0, 0, width // 2, h)), (0, 0))
    out.paste(b.crop((width // 2, 0, width, h)), (width // 2, 0))
    d = ImageDraw.Draw(out)
    d.line([(width // 2, 0), (width // 2, h)], fill=(255, 255, 255), width=2)
    font = _font(26)
    d.text((20, 16), "원본", fill=(255, 255, 255), font=font)
    d.text((width // 2 + 20, 16), f"자동 색보정 · {LOOKS[choice.look].label}", fill=(255, 255, 255), font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path, "JPEG", quality=90)
    return path


def plan_to_dict(stats: dict, c: Correction, choice: GradeChoice, filters: list[str]) -> dict[str, Any]:
    return {"stats": stats, "correction": asdict(c), "choice": asdict(choice), "filters": filters}
