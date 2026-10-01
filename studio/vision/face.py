"""얼굴 추적: 줌 인 중심점과 9:16 세로 리프레이밍에 사용 + 화면 품질 표본(원본 여러 개일 때 앵글·테이크 고르기).

YuNet(OpenCV DNN, MIT) → 없으면 Haar Cascade → 그래도 없으면 화면 중앙.
결과는 정규화 좌표(0~1)이며, 토킹헤드 특성상 강하게 스무딩한다.
품질 표본(quality)은 스무딩하지 않은 그 프레임의 값: 얼굴 확신도 · 크기 · 초점(얼굴 영역 라플라시안 분산) · 밝기 ·
날아가거나 뭉개진 화소 비율 · 정면 정도(YuNet 눈·코 위치) — studio/media/sources.py 가 쓴다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..media.ffmpeg import FFmpeg, MediaInfo
from ..paths import MODELS_DIR
from ..util import CancelToken, LogFn, ProgressFn, noop_log, noop_progress


@dataclass
class FaceSample:
    t: float
    x: float      # 얼굴 중심 x (0~1)
    y: float      # 얼굴 중심 y (0~1)
    s: float      # 얼굴 높이 / 화면 높이
    conf: float

    def to_dict(self) -> dict:
        return {"t": round(self.t, 3), "x": round(self.x, 4), "y": round(self.y, 4), "s": round(self.s, 4)}


class _Detector:
    def __init__(self, width: int, height: int, log: LogFn):
        import cv2
        try:  # OpenCV 5 의 무해한 백엔드 경고 숨김
            cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
        except AttributeError:
            pass
        self.cv2 = cv2
        self.kind = "center"
        self.yunet = None
        self.haar = None
        for name in ("face_detection_yunet_2026may.onnx", "face_detection_yunet_2023mar.onnx"):
            path = MODELS_DIR / name
            if not path.exists():
                continue
            try:
                det = cv2.FaceDetectorYN.create(str(path), "", (width, height), 0.6, 0.3, 20)
                det.detect(np.zeros((height, width, 3), np.uint8))
                self.yunet = det
                self.kind = f"yunet:{name}"
                break
            except Exception as e:  # noqa: BLE001
                log(f"YuNet 로드 실패({name}): {e}")
        if self.yunet is None:
            try:
                cascade = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                self.haar = cv2.CascadeClassifier(cascade)
                if not self.haar.empty():
                    self.kind = "haar"
                else:
                    self.haar = None
            except Exception:  # noqa: BLE001
                self.haar = None

    def detect(self, frame: np.ndarray) -> Optional[tuple[float, float, float, float, float]]:
        r = self.detect_full(frame)
        return r[:5] if r else None

    def detect_full(self, frame: np.ndarray) -> Optional[tuple[float, float, float, float, float, float]]:
        """(x, y, w, h, 확신도, 정면 정도 0~1). 정면 정도는 YuNet 랜드마크가 있을 때만(없으면 0.6)."""
        h, w = frame.shape[:2]
        if self.yunet is not None:
            _, faces = self.yunet.detect(frame)
            if faces is None or len(faces) == 0:
                return None
            # 가장 큰 얼굴
            f = max(faces, key=lambda r: r[2] * r[3])
            x, y, fw, fh, conf = float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])
            # 코가 두 눈 가운데에서 얼마나 벗어났나(눈 사이 거리 대비) → 고개를 돌린 정도
            eye_d = abs(float(f[6]) - float(f[4])) + 1e-6
            off = abs(float(f[8]) - (float(f[4]) + float(f[6])) / 2) / eye_d
            return x, y, fw, fh, conf, float(max(0.0, 1.0 - off / 0.6))
        if self.haar is not None:
            gray = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2GRAY)
            faces = self.haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5,
                                               minSize=(max(24, w // 20), max(24, w // 20)))
            if len(faces) == 0:
                return None
            x, y, fw, fh = max(faces, key=lambda r: r[2] * r[3])
            return float(x), float(y), float(fw), float(fh), 0.8, 0.6
        return None


def eye_contrast(gray: np.ndarray, eyes: list[tuple[float, float]]) -> Optional[float]:
    """두 눈 주변 작은 조각의 밝기 대비(p95 − p5, 0~1) 평균 — 뜬 눈은 흰자·홍채·동공이 있어 대비가 크고, 감은 눈은 눈꺼풀
    살갗이라 평평하다. 절대 기준이 아니라 같은 영상의 후보끼리 비교하는 값(썸네일 프레임 고르기, docs/upgrade/10 3-1)."""
    if len(eyes) < 2:
        return None
    (x1, y1), (x2, y2) = eyes[:2]
    d = float(np.hypot(x2 - x1, y2 - y1))
    if d < 8:
        return None
    r = max(3, int(round(d * 0.2)))
    vals = []
    for x, y in eyes[:2]:
        xi, yi = int(round(x)), int(round(y))
        patch = gray[max(0, yi - r // 2):yi + r // 2 + 1, max(0, xi - r):xi + r + 1]
        if patch.size < 9:
            return None
        lo, hi = np.percentile(patch, [5, 95])
        vals.append((hi - lo) / 255.0)
    return float(np.mean(vals))


def eye_openness(frame: np.ndarray, detector: Optional["_Detector"] = None) -> Optional[float]:
    """프레임 → eye_contrast(YuNet 눈 랜드마크). YuNet 이 없거나 얼굴이 없으면 None."""
    h, w = frame.shape[:2]
    det = detector or _Detector(w, h, noop_log)
    if det.yunet is None:
        return None
    try:
        det.yunet.setInputSize((w, h))
    except Exception:  # noqa: BLE001
        pass
    _, faces = det.yunet.detect(frame)
    if faces is None or len(faces) == 0:
        return None
    f = max(faces, key=lambda r: r[2] * r[3])
    gray = det.cv2.cvtColor(frame, det.cv2.COLOR_BGR2GRAY)
    return eye_contrast(gray, [(float(f[4]), float(f[5])), (float(f[6]), float(f[7]))])


def frame_quality(frame: np.ndarray, box: Optional[tuple[float, float, float, float]]) -> tuple[float, float, float]:
    """(초점 = log1p(라플라시안 분산), 밝기 0~1, 날아가거나 뭉개진 화소 비율). 얼굴이 있으면 얼굴 영역,
    없으면 화면 가운데. 영역을 높이 96px 로 맞춰 재므로 카메라 해상도·얼굴 크기가 달라도 비교할 수 있다."""
    import cv2
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    if box:
        x, y, fw, fh = box
        cx, cy, half = x + fw / 2, y + fh / 2, max(fw, fh) * 0.6
        x0, x1 = int(max(0, cx - half)), int(min(w, cx + half))
        y0, y1 = int(max(0, cy - half)), int(min(h, cy + half))
    else:
        x0, x1, y0, y1 = w // 4, w * 3 // 4, h // 4, h * 3 // 4
    roi = gray[y0:y1, x0:x1] if (x1 - x0 >= 8 and y1 - y0 >= 8) else gray
    roi = cv2.resize(roi, (max(8, int(96 * roi.shape[1] / max(1, roi.shape[0]))), 96), interpolation=cv2.INTER_AREA)
    sharp = float(np.log1p(cv2.Laplacian(roi, cv2.CV_32F).var()))
    clip = float(np.mean((gray > 250) | (gray < 4)))
    return sharp, float(roi.mean() / 255.0), clip


def track_faces(
    ff: FFmpeg,
    video: str,
    info: MediaInfo,
    *,
    sample_fps: float = 4.0,
    width: int = 640,
    log: LogFn = noop_log,
    progress: ProgressFn = noop_progress,
    cancel: Optional[CancelToken] = None,
) -> dict:
    dw, dh = info.display_size
    height = int(round(width * dh / max(1, dw) / 2) * 2)
    det = _Detector(width, height, log)
    log(f"얼굴 검출기: {det.kind}")
    raw: list[FaceSample] = []
    quality: list[dict] = []
    total = max(1.0, info.duration)
    for t, frame in ff.iter_frames(video, fps=sample_fps, width=width, info=info, cancel=cancel):
        r = det.detect_full(frame) if det.kind != "center" else None
        if r:
            x, y, fw, fh, conf, front = r
            raw.append(FaceSample(t, (x + fw / 2) / width, (y + fh / 2) / height, fh / height, conf))
        sharp, luma, clip = frame_quality(frame, r[:4] if r else None)
        quality.append({"t": round(t, 3), "f": round(r[4], 3) if r else 0.0, "s": round(r[3] / height, 4) if r else 0.0,
                        "sh": round(sharp, 3), "l": round(luma, 3), "c": round(clip, 4),
                        "fr": round(r[5], 3) if r else 0.0})
        if int(t * sample_fps) % 20 == 0:
            progress(min(0.999, t / total))
    progress(1.0)
    if not quality:   # 디코딩이 안 된 영상: 얼굴 트랙이 조용히 화면 가운데로 채워지지 않게 알린다
        log(f"⚠ 영상 프레임을 읽지 못했습니다({video}) — 얼굴 위치를 화면 가운데로 둡니다")
    smooth = smooth_track(raw, total, sample_fps)
    found = len(raw)
    log(f"얼굴 검출 {found}프레임 / 약 {int(total * sample_fps)}프레임")
    return {"detector": det.kind, "samples": [s.to_dict() for s in smooth], "quality": quality,
            "found_ratio": found / max(1, int(total * sample_fps))}


def smooth_track(raw: list[FaceSample], duration: float, fps: float, tau: float = 0.9) -> list[FaceSample]:
    """결측 보간 → 이상치 제거(중앙값) → 양방향 지수 스무딩. 0.25초 간격으로 반환."""
    if not raw:
        return [FaceSample(0.0, 0.5, 0.42, 0.28, 0.0), FaceSample(duration, 0.5, 0.42, 0.28, 0.0)]
    step = 0.25
    grid = np.arange(0.0, max(duration, step) + step, step)
    ts = np.array([r.t for r in raw])
    xs = np.array([r.x for r in raw])
    ys = np.array([r.y for r in raw])
    ss = np.array([r.s for r in raw])

    def med(a: np.ndarray, k: int = 5) -> np.ndarray:
        if len(a) < k:
            return a
        pad = k // 2
        ap = np.pad(a, pad, mode="edge")
        return np.array([np.median(ap[i:i + k]) for i in range(len(a))])

    xs, ys, ss = med(xs), med(ys), med(ss)
    gx = np.interp(grid, ts, xs)
    gy = np.interp(grid, ts, ys)
    gs = np.interp(grid, ts, ss)
    alpha = 1 - np.exp(-step / tau)

    def ema2(a: np.ndarray) -> np.ndarray:
        f = a.copy()
        for i in range(1, len(f)):
            f[i] = f[i - 1] + alpha * (f[i] - f[i - 1])
        b = f.copy()
        for i in range(len(b) - 2, -1, -1):
            b[i] = b[i + 1] + alpha * (b[i] - b[i + 1])
        return b

    gx, gy, gs = ema2(gx), ema2(gy), ema2(gs)
    return [FaceSample(float(t), float(x), float(y), float(s), 1.0) for t, x, y, s in zip(grid, gx, gy, gs)]


def remap_track(samples: list[dict], timemap, step: float = 0.25) -> list[dict]:
    """원본 시간 얼굴 트랙 → 편집 시간 트랙(각 keep 구간 내부만)."""
    if not samples:
        return []
    ts = np.array([s["t"] for s in samples])
    xs = np.array([s["x"] for s in samples])
    ys = np.array([s["y"] for s in samples])
    ss = np.array([s["s"] for s in samples])
    out: list[dict] = []
    for i, k in enumerate(timemap.keeps):
        span = timemap.edit_span_of(i)
        t = k.start
        while t < k.end - 0.002:      # keep 끝 시각은 다음 keep 의 첫 표본과 같은 편집 시각이라 넣지 않는다
            et = span.start + (t - k.start)
            out.append({"t": round(et, 3), "x": round(float(np.interp(t, ts, xs)), 4),
                        "y": round(float(np.interp(t, ts, ys)), 4), "s": round(float(np.interp(t, ts, ss)), 4)})
            t += step
        # keep 끝 바로 앞 표본: 없으면 컷 직전 0.25초 동안 다음 keep 의 얼굴 위치로 미리 미끄러진다
        end = k.end - 0.002
        if end > k.start:
            et = span.start + (end - k.start)
            out.append({"t": round(et, 3), "x": round(float(np.interp(end, ts, xs)), 4),
                        "y": round(float(np.interp(end, ts, ys)), 4), "s": round(float(np.interp(end, ts, ss)), 4)})
    out.sort(key=lambda d: d["t"])
    return out
