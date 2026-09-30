"""남은 시간 예측 — 단계별 소요 시간 모델(보수적) + 진행 중 실측 보정 + 이 PC 기록 학습.

예전 방식(고정 가중치 × 경과 시간 외삽)은 앞 단계가 빨리 끝나면 짧게 잡았다가 AI 기획·렌더링에서
계속 늘어났다. 여기서는
  1) 원본 길이·출력 fps·GPU·AI 사용 여부·출력 프레임 수로 단계마다 시간을 넉넉히 잡고
  2) 지금 단계는 계획 시간과 실측 속도 중 큰 쪽에서 시작해, 진행될수록 실측 쪽을 믿고
  3) 먼저 끝난 같은 종류 단계의 실제/예상 비율로 남은 단계를 조정하고(늘리기는 2배까지, 줄이기는 25%까지만)
  4) 끝난 단계의 실제/기본 비율을 user/eta_history.json 에 남겨 다음 작업부터 이 PC 속도로 잡는다.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .util import read_json, write_json

# 기본 소요 시간(초) — 첫 작업용이라 넉넉하게. f: 특징값(아래 features 참고)
DEFAULTS: dict[str, Callable[[dict], float]] = {
    "probe": lambda f: 5,
    "audio": lambda f: 15 + 10 * f["m"],
    "asr@gpu": lambda f: 40 + 10 * f["m"],
    "asr@cpu": lambda f: 40 + 80 * f["m"],
    "align": lambda f: 5 + 2 * f["m"],
    "face": lambda f: 10 + 8 * f.get("mv", f["m"]) * f["k"],        # mv: 원본 영상 길이 합(다시점이면 카메라 수만큼)
    "grade": lambda f: 25 + 3 * f.get("mv", f["m"]),
    "director@ai": lambda f: 150 + 20 * f["m"],
    "director@rule": lambda f: 15,
    "proxy": lambda f: 15 + 25 * f.get("mv", f["m"]) * f["k"],
    "verify@gpu": lambda f: 30 + 12 * f["out_s"] / 60,     # 편집된 목소리 다시 인식(최대 2차)
    "verify@cpu": lambda f: 30 + 100 * f["out_s"] / 60,
    "broll": lambda f: 40,
    "stock@ai": lambda f: 90,
    "stock@rule": lambda f: 45,
    "stock@off": lambda f: 3,
    "sound": lambda f: 60,
    "qa@ai": lambda f: 180,
    "qa@rule": lambda f: 20,
    "render": lambda f: 60 + 67 * f["frames_k"] + (15 if f["thumbs"] else 0),   # 약 15fps(첫 작업은 넉넉히)
    "master": lambda f: 20 + 8 * f["out_s"] / 60,
    "export": lambda f: 30,
}
# 같은 종류(느리면 같이 느린) 단계 묶음
GROUPS = {"audio": "sound", "master": "sound", "face": "video", "grade": "video", "proxy": "video",
          "render": "video", "director": "ai", "qa": "ai", "stock": "ai", "broll": "net", "sound": "net"}
GROUP_MIN, GROUP_MAX = 0.75, 2.0   # 같은 묶음 조정 범위(줄일 때는 조금만 — 보수적으로)
GROUP_EVIDENCE = 60.0  # 같은 묶음에서 이만큼(예상 초) 끝나야 조정
LEARN_KEEP = 5         # 단계마다 남길 기록 수
LEARN_MARGIN = 1.1     # 학습값에 더하는 여유
CACHED_S = 2.0         # 이보다 빨리 끝나면 캐시로 건너뛴 것으로 보고 학습하지 않음
TRUST_AT = 0.33        # 단계 진행률이 이만큼 되면 실측 속도를 온전히 믿음


def features(*, src_s: float, out_fps: float, long_s: float, shorts_s: float, thumbs: bool,
             video_s: Optional[float] = None) -> dict:
    """src_s: 목소리 타임라인 길이(원본이 여러 개면 이어 붙인 길이), video_s: 원본 영상 길이 합(얼굴·색·프록시는
    카메라마다 한 번씩 돈다)."""
    out_s = long_s + shorts_s
    return {"m": src_s / 60.0, "mv": (video_s if video_s is not None else src_s) / 60.0,
            "k": max(0.5, out_fps / 30.0), "out_s": out_s, "frames_k": out_s * out_fps / 1000.0, "thumbs": thumbs}


class Eta:
    """파이프라인이 start/update/finish 로 알려주고, 창은 remaining()/fraction() 을 1초마다 읽는다(스레드 안전)."""

    def __init__(self, history: Optional[Path] = None, clock: Callable[[], float] = time.monotonic):
        self._lock = threading.Lock()
        self._clock = clock
        self._history_path = history
        self._hist: dict[str, list[float]] = (read_json(history, {}).get("factors", {}) if history else {}) or {}
        self._t0: Optional[float] = None
        self._order: list[str] = []            # 남은 단계 순서
        self._cost: dict[str, float] = {}      # 단계 → 예상 초(학습·보정 반영)
        self._base: dict[str, float] = {}      # 단계 → 기본 초(학습 기록용)
        self._variant: dict[str, str] = {}     # 단계 → 기록 키(asr@gpu 등)
        self._group: dict[str, list[float]] = {}   # 묶음 → [실제 초 합, 예상 초 합]
        self._done: set[str] = set()
        self._cur: Optional[str] = None
        self._cur_t = 0.0
        self._frac = 0.0

    # ---- 계획 ----
    def begin(self) -> None:
        with self._lock:
            self._t0 = self._clock()

    def learned(self, variant: str) -> float:
        xs = [x for x in self._hist.get(variant, []) if x > 0][-3:]
        return min(6.0, max(0.25, max(xs) * LEARN_MARGIN)) if xs else 1.0

    def plan(self, stages: list[str], variants: dict[str, str], feats: dict) -> None:
        """stages: 앞으로 돌 단계(순서대로). variants: 단계 → DEFAULTS 키. 이미 끝난 단계는 건너뜀."""
        with self._lock:
            self._order = list(stages)
            for key in stages:
                if key in self._done:
                    continue
                self._set_cost(key, variants.get(key, key), feats)

    def refine(self, key: str, feats: dict) -> None:
        """출력 길이가 확정되면 아직 시작 안 한 단계(렌더·믹스)를 다시 잡는다."""
        with self._lock:
            if key in self._cost and key not in self._done and key != self._cur:
                self._set_cost(key, self._variant.get(key, key), feats)

    def _set_cost(self, key: str, variant: str, feats: dict) -> None:
        fn = DEFAULTS.get(variant) or DEFAULTS.get(key)
        base = float(fn(feats)) if fn else 10.0
        self._variant[key] = variant
        self._base[key] = base
        self._cost[key] = base * self.learned(variant)

    # ---- 진행 ----
    def start(self, key: str) -> None:
        with self._lock:
            self._cur, self._cur_t, self._frac = key, self._clock(), 0.0

    def update(self, key: str, frac: float) -> None:
        with self._lock:
            if key == self._cur:
                self._frac = max(self._frac, min(1.0, max(0.0, frac)))

    def finish(self, key: str) -> None:
        with self._lock:
            if key != self._cur:
                return
            took = self._clock() - self._cur_t
            self._done.add(key)
            self._cur = None
            if took < CACHED_S or key not in self._cost:
                return
            group = GROUPS.get(key)
            if group:
                g = self._group.setdefault(group, [0.0, 0.0])
                g[0] += took
                g[1] += self._cost[key]
            variant = self._variant.get(key, key)
            self._hist[variant] = (self._hist.get(variant, []) + [round(took / max(1.0, self._base[key]), 3)])[-LEARN_KEEP:]
            if self._history_path:
                try:
                    write_json(self._history_path, {"v": 1, "factors": self._hist})
                except OSError:
                    pass

    # ---- 읽기 ----
    def _factor(self, key: str) -> float:
        g = self._group.get(GROUPS.get(key, ""))
        if not g or g[1] < GROUP_EVIDENCE:
            return 1.0
        return min(GROUP_MAX, max(GROUP_MIN, g[0] / g[1]))

    def _expected(self, key: str) -> float:
        return self._cost.get(key, 0.0) * self._factor(key)

    def remaining(self) -> Optional[float]:
        """남은 초. 계획 전이면 None."""
        with self._lock:
            if not self._cost:
                return None
            now = self._clock()
            rest = sum(self._expected(k) for k in self._order if k not in self._done and k != self._cur)
            if self._cur is None or self._cur not in self._cost:
                return rest
            exp = self._expected(self._cur)
            t_in = now - self._cur_t
            f = self._frac
            plan_left = max(0.0, exp - t_in)
            if f >= 0.03 and t_in >= 5.0:
                measured = t_in * (1 - f) / f * LEARN_MARGIN
                w = min(1.0, (f - 0.03) / (TRUST_AT - 0.03))
                cur = (1 - w) * max(plan_left, measured) + w * measured
            else:
                cur = max(plan_left, min(30.0, 0.1 * exp))
            return rest + cur

    def fraction(self) -> Optional[float]:
        """시간 기준 진행률(경과 / (경과 + 남은 시간))."""
        left = self.remaining()
        if left is None or self._t0 is None:
            return None
        el = self._clock() - self._t0
        return el / max(1e-6, el + left)


class EtaDisplay:
    """화면 표시용: 한 번 보여 준 값은 1초씩 줄고, 좋아지면 바로 내리고, 확실히 늦어질 때만 올린다."""

    def __init__(self):
        self.shown: Optional[float] = None

    def step(self, target: Optional[float], dt: float) -> Optional[float]:
        if target is None:
            return self.shown
        if self.shown is None:
            self.shown = target
            return self.shown
        self.shown = max(0.0, self.shown - dt)
        if target < self.shown or target > self.shown + max(45.0, 0.15 * self.shown):
            self.shown = target
        return self.shown


def fmt_left(sec: Optional[float]) -> str:
    if sec is None:
        return "남은 시간 계산 중"
    if sec < 60:
        return "1분 이내"
    m = int(-(-sec // 60))  # 올림
    if m < 60:
        return f"남은 시간 약 {m}분"
    return f"남은 시간 약 {m // 60}시간" + (f" {m % 60}분" if m % 60 else "")
