"""자동 색보정 — 샘플 프레임 분석 → 교정 + 룩 → 33³ 3D LUT(.cube) → 프록시에 굽는다.

1) 남길 구간에서 프레임을 고르게 뽑아(얼굴 위치 포함) 통계를 낸다.
2) 교정(Correction): 화이트밸런스(무채색 픽셀 + 피부톤 점검) · 블랙/화이트 포인트 · 노출(얼굴 밝기 목표) · 채도.
   과보정을 막으려고 모든 값에 한계를 둔다(분위기 조명을 '형광등'으로 만들지 않도록 WB 는 75%만).
3) 룩(Look) 4가지 — 내추럴 · 웜 필름 · 클린 브라이트 · 시네마틱 — 를 같은 프레임에 입혀 비교 시트를 만들고
   🧐 아트 디렉터(Claude 비전)가 고른다. Claude 가 없으면 '내추럴'.
4) 교정 + 룩을 LUT 하나로 구워 FFmpeg lut3d 로 프록시에 적용 → 롱폼·숏폼·썸네일이 같은 색.

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
    name: str
    label: str
    contrast: float = 0.1          # S-커브 세기
    fade: float = 0.0              # 블랙 들어올림(필름 느낌)
    warmth: float = 0.0            # +따뜻 / -차갑게
    tint: float = 0.0              # +마젠타 / -그린
    exposure: float = 0.0          # 감마로 환산(+ 밝게)
    sat: float = 1.0
    vibrance: float = 0.0          # 채도 낮은 곳을 더 올림(피부 보호)
    shadows: tuple[float, float, float] = (0.0, 0.0, 0.0)     # 스플릿 토닝 — 어두운 영역 RGB 오프셋
    highlights: tuple[float, float, float] = (0.0, 0.0, 0.0)  # 밝은 영역 RGB 오프셋
    rolloff: float = 0.3           # 하이라이트 부드럽게 눌러주기


LOOKS: dict[str, Look] = {l.name: l for l in [
    # 기본: 따뜻하고 풍부하게 — 사용자가 직접 편집한 장면(스탠드 조명의 따뜻한 방)에 맞춘 룩 + 레퍼런스 매칭
    Look("warm_rich", "웜 리치", contrast=0.14, warmth=0.12, sat=1.0, vibrance=0.10,
         shadows=(0.004, 0.0, -0.008), highlights=(0.012, 0.006, -0.010), rolloff=0.45),
    Look("natural", "내추럴", contrast=0.10, sat=1.04, vibrance=0.10, rolloff=0.3),
    Look("warm_film", "웜 필름", contrast=0.17, fade=0.025, warmth=0.35, sat=0.96, vibrance=0.08,
         shadows=(-0.004, 0.004, 0.012), highlights=(0.014, 0.006, -0.010), rolloff=0.5),
    Look("clean_bright", "클린 브라이트", contrast=0.06, exposure=0.06, warmth=0.10, sat=1.08, vibrance=0.15,
         rolloff=0.45),
    Look("cinematic", "시네마틱", contrast=0.22, fade=0.02, warmth=0.08, sat=0.93, vibrance=0.05,
         shadows=(-0.012, 0.004, 0.016), highlights=(0.018, 0.006, -0.012), rolloff=0.6),
]}


# 레퍼런스 색(CIELAB 평균): 사용자가 직접 편집한 장면(2026-09-30 제공, 따뜻한 스탠드 조명의 방)을 잰 값.
# 업로드된 결과물의 얼굴 화면은 L 30.8 · a +2.0 · b +2.5 · C 5.9(회색) — 교정이 방의 따뜻함을 지우고 룩은 2%만 더했다.
# user/reference_frames/ 에 좋아하는 장면(jpg/png)을 넣으면 그 평균을 대신 쓴다.
REFERENCE_LAB = {"L": 41.8, "a": 4.7, "b": 14.5, "C": 16.9}


@dataclass
class GradeChoice:
    look: str = "warm_rich"
    strength: float = 1.0          # 룩 적용 정도(0~1)
    match: float = 1.0             # 레퍼런스 색으로 옮기는 정도(0~1.2)
    src_lab: tuple = ()            # 교정 후 원본 평균 (L, a, b, C) — 분석 때 채움
    ref_lab: tuple = ()            # 레퍼런스 평균 (L, a, b, C) — 비면 REFERENCE_LAB
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
    if strength <= 0 and not exposure and not warmth and saturation == 1.0:
        return x
    k = strength
    skin = skin_mask(x)[..., None]
    y = x
    # 색온도·틴트(선형광에서)
    w = look.warmth * k + warmth
    t = look.tint * k
    if abs(w) > 1e-4 or abs(t) > 1e-4:
        lin = _to_linear(y) * np.array([1 + 0.06 * w, 1 - 0.04 * t, 1 - 0.06 * w], dtype=np.float32)
        y = _to_gamma(lin)
    # 노출(감마)
    ex = look.exposure * k + exposure
    if abs(ex) > 1e-4:
        y = np.power(np.clip(y, 0, 1), 1 / (1 + 1.6 * ex))
    # 콘트라스트 S-커브 + 하이라이트 롤오프 + 페이드
    y = _scurve(np.clip(y, 0, 1), look.contrast * k)
    y = _rolloff(y, look.rolloff * k)
    if look.fade:
        y = look.fade * k + y * (1 - look.fade * k)
    # 스플릿 토닝(피부는 70% 보호)
    lum = _luma(y)[..., None]
    protect = 1 - 0.7 * skin
    sh = np.array(look.shadows, dtype=np.float32) * k
    hi = np.array(look.highlights, dtype=np.float32) * k
    y = y + protect * (sh * (1 - lum) ** 2 + hi * lum ** 2)
    # 채도 + 바이브런스(채도 낮은 곳을 더, 피부는 덜)
    lum = _luma(y)[..., None]
    _, s = _hue_sat(np.clip(y, 0, 1))
    vib = 1 + look.vibrance * k * (1 - s[..., None]) * (1 - 0.6 * skin)
    sat = (1 + (look.sat - 1) * k) * saturation
    y = lum + (y - lum) * sat * vib
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


def ref_match(x: np.ndarray, src: tuple, ref: tuple, k: float) -> np.ndarray:
    """원본 평균색(src) → 레퍼런스 평균색(ref) 쪽으로(CIELAB): 채도 이득 + 색 이동 + 중간톤 밝기.
    피부는 채도 이득을 35%만, 색 이동을 55%만(얼굴이 주황색이 되지 않게). 중간톤에 가장 많이, 암부·하이라이트는 덜."""
    if k <= 0 or not src:
        return x
    sL, sa, sb, sC = src
    rL, ra, rb, rC = ref
    L, a, b = srgb_to_lab(x)
    skin = skin_mask(x)
    g = 1 + k * 0.75 * (float(np.clip(rC / max(2.0, sC), 1.0, 2.6)) - 1)
    gg = g * (1 - skin) + (1 + (g - 1) * 0.35) * skin
    # 따뜻한 쪽으로만 옮긴다(평균이 피부에 끌려 벽이 초록·파랑으로 가지 않게)
    da, db = max(-0.5, k * (ra - sa * g)), max(-0.5, k * (rb - sb * g))
    w = np.clip(L / 100, 0, 1)
    tone = 0.45 + 0.55 * (4 * w * (1 - w))
    sh = 1 - 0.45 * skin
    L2 = L + k * 0.6 * float(np.clip(rL - sL, -6, 10)) * tone
    t = np.clip(L2 / 100, 0, 1)
    L2 = 100 * (t + 0.18 * min(1.0, k) * (t * t * (3 - 2 * t) - t))    # 풍부함: 중간톤 대비 살짝
    return lab_to_srgb(L2, a * gg + da * tone * sh, b * gg + db * tone * sh)


def grade(x: np.ndarray, c: Correction, choice: GradeChoice) -> np.ndarray:
    ch = choice.clamp()
    y = apply_correction(x, c)
    if ch.match > 0 and ch.src_lab:
        y = ref_match(y, tuple(ch.src_lab), tuple(ch.ref_lab) if ch.ref_lab else reference_lab(), ch.match)
    return apply_look(y, LOOKS[ch.look], ch.strength, exposure=ch.exposure, warmth=ch.warmth,
                      saturation=ch.saturation)


# ---------------------------------------------------------------------------
# 분석
# ---------------------------------------------------------------------------

def sample_frames(ff: FFmpeg, video: str | Path, times: list[float], info: MediaInfo, width: int = 480
                  ) -> list[tuple[float, np.ndarray]]:
    """지정 시각의 프레임을 RGB float(0~1) 로. HDR 은 SDR 로 톤매핑한 모습 기준."""
    dw, dh = info.display_size
    height = int(round(width * dh / max(1, dw) / 2) * 2)
    vf = (hdr_to_sdr_filter() + "," if info.is_hdr else "") + f"scale={width}:{height}:flags=area"
    out = []
    for t in times:
        args = [ff.ffmpeg, "-v", "error", "-nostdin", "-ss", f"{max(0.0, t):.3f}", "-i", str(video), "-frames:v", "1",
                "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        r = subprocess.run(args, capture_output=True, **_popen_kwargs())
        if r.returncode != 0 or len(r.stdout) < width * height * 3:
            continue
        arr = np.frombuffer(r.stdout[: width * height * 3], np.uint8).reshape(height, width, 3)
        out.append((t, arr.astype(np.float32) / 255.0))
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
        sk = face[fs > 0.3] if (fs > 0.3).sum() > 30 else face
        stats["face_luma"] = float(np.median(_luma(sk)))
        stats["face_rgb"] = [float(v) for v in sk.mean(axis=0)]
        stats["face_frac"] = float((fs > 0.3).mean())
    return stats


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
    # 피부 점검: 교정 후 피부가 초록/파랑 쪽(R/G < 1.05)이면 살짝 따뜻하게, 너무 붉으면(R/G > 1.55) 식힌다
    if "face_rgb" in st:
        f = _to_linear(np.array(st["face_rgb"])) * gains
        fr = _to_gamma(f)
        rg = fr[0] / max(1e-3, fr[1])
        if rg < 1.05:
            gains = gains * np.array([1.05, 1.0, 0.95])
            notes.append("피부톤이 차가워 따뜻하게 보정")
        elif rg > 1.45:
            gains = gains * np.array([0.965, 1.0, 1.03])
            notes.append("피부톤이 너무 붉어 식힘")
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


def comparison_sheet(frames: list[np.ndarray], c: Correction, *, cell_w: int = 360, src_lab: tuple = ()) -> bytes:
    """행 = 프레임, 열 = 원본 + 룩들(모두 레퍼런스 매칭 포함). 🎨 컬러리스트가 고를 비교 시트(JPEG)."""
    from PIL import Image, ImageDraw
    cols = [("0 원본", None)] + [(f"{i + 1} {l.label}", l.name) for i, l in enumerate(LOOKS.values())]
    ch = int(round(cell_w * frames[0].shape[0] / frames[0].shape[1]))
    pad, head = 6, 34
    sheet = Image.new("RGB", (len(cols) * (cell_w + pad) + pad, head + len(frames) * (ch + pad) + pad), (18, 18, 18))
    d = ImageDraw.Draw(sheet)
    font = _font(20)
    for j, (label, name) in enumerate(cols):
        d.text((pad + j * (cell_w + pad) + 4, 6), label, fill=(240, 240, 240), font=font)
        for i, f in enumerate(frames):
            img = f if name is None else grade(f, c, GradeChoice(look=name, src_lab=src_lab))
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
