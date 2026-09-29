"""남은 시간 예측(studio/eta.py): 보수적으로 잡고, 늘어나지 않고, 캐시·학습·실측을 반영하는지."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.eta import DEFAULTS, Eta, EtaDisplay, features, fmt_left  # noqa: E402

KEYS = ["probe", "audio", "asr", "align", "face", "grade", "director", "proxy", "broll", "stock", "sound", "qa",
        "render", "master", "export"]
VARIANTS = {"asr": "asr@gpu", "director": "director@ai", "qa": "qa@ai", "stock": "stock@ai"}
# 7.5분 · 60fps 원본(사용자 실제 사례), 롱폼 + 숏폼 2편
FEATS = features(src_s=450, out_fps=60, long_s=450 * 0.85, shorts_s=2 * 60, thumbs=True)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def simulate(actual: dict[str, float], *, history=None, cached=(), bumpy=False):
    """단계별 실제 초로 1초씩 돌리며 (경과, 화면에 보인 남은 초, 실제 남은 초) 를 모은다."""
    clock = Clock()
    eta = Eta(history, clock=clock)
    view = EtaDisplay()
    total = sum(actual[k] for k in KEYS if k not in cached)
    seen: list[tuple[float, float, float]] = []
    t0 = clock.t
    eta.begin()
    for key in KEYS:
        eta.start(key)
        dur = 0.0 if key in cached else actual[key]
        steps = max(1, int(dur))
        for i in range(steps):
            clock.t += dur / steps
            frac = (i + 1) / steps
            if bumpy and key in ("director", "qa"):
                frac = min(1.0, round(frac * 4) / 4)   # 에이전트 단위로 뚝뚝 오르는 진행률
            eta.update(key, frac)
            left = view.step(eta.remaining(), dur / steps)
            if left is not None:
                seen.append((clock.t - t0, left, total - (clock.t - t0)))
        eta.finish(key)
        if key == "probe":
            eta.plan(KEYS, VARIANTS, FEATS)
    return eta, seen


def base(key: str) -> float:
    return DEFAULTS[VARIANTS.get(key, key)](FEATS)


def test_faster_machine_counts_down_without_growing():
    actual = {k: base(k) * 0.6 for k in KEYS}
    _, seen = simulate(actual, bumpy=True)
    shown = [s for _, s, _ in seen]
    assert all(b <= a + 1e-6 for a, b in zip(shown, shown[1:])), "보이는 남은 시간이 늘어나면 안 됨"
    assert shown[0] >= seen[0][2], "처음 예측은 실제보다 길게(보수적)"


def test_slower_machine_rarely_grows_and_ends_close():
    # 영상 처리가 기본값보다 40% 느린 PC: 얼굴 추적에서 느린 걸 보고 편집본·렌더를 미리 늘려 잡아야 함
    actual = {k: base(k) * (1.4 if k in ("face", "grade", "proxy", "render") else 0.9) for k in KEYS}
    _, seen = simulate(actual, bumpy=True)
    shown = [s for _, s, _ in seen]
    ups = sum(1 for a, b in zip(shown, shown[1:]) if b > a + 1e-6)
    assert ups <= 3, ups
    # 렌더가 1/3 이상 진행된 뒤로는 실제 남은 시간의 ±25% 안
    render_start = sum(actual[k] for k in KEYS[:KEYS.index("render")])
    late = [(s, r) for t, s, r in seen if t > render_start + actual["render"] / 3 and r > 60]
    assert late and all(abs(s - r) <= 0.25 * r + 30 for s, r in late)


def test_cached_stages_are_skipped_and_not_learned(tmp_path):
    hist = tmp_path / "eta_history.json"
    actual = {k: base(k) for k in KEYS}
    eta, seen = simulate(actual, history=hist, cached=("audio", "asr", "align", "face", "grade"))
    factors = eta._hist
    assert "asr@gpu" not in factors and "audio" not in factors
    assert "render" in factors and abs(factors["render"][-1] - 1.0) < 0.05


def test_history_makes_next_run_match_this_pc(tmp_path):
    hist = tmp_path / "eta_history.json"
    actual = {k: base(k) * (2.0 if k == "render" else 0.5) for k in KEYS}
    simulate(actual, history=hist)
    clock = Clock()
    eta = Eta(hist, clock=clock)
    eta.begin()
    eta.plan(KEYS, VARIANTS, FEATS)
    assert abs(eta._cost["render"] - base("render") * 2.0 * 1.1) < 1.0     # 느렸던 렌더는 길게
    assert abs(eta._cost["asr"] - base("asr") * 0.5 * 1.1) < 1.0            # 빨랐던 인식은 짧게
    total_pred = eta.remaining()
    total_true = sum(actual.values()) - actual["probe"]
    assert total_true <= total_pred <= total_true * 1.2


def test_current_stage_trusts_measured_speed_as_it_progresses():
    clock = Clock()
    eta = Eta(None, clock=clock)
    eta.begin()
    eta.plan(["render"], {}, FEATS)
    exp = eta._cost["render"]
    eta.start("render")
    clock.t += 100
    eta.update("render", 0.5)          # 절반을 100초에 → 남은 건 약 100초(+10%)
    assert abs(eta.remaining() - 110) < 1
    eta.update("render", 0.5)
    clock.t += exp                      # 진행 없이 계획 시간을 넘겨도 0 이 되지 않음
    assert eta.remaining() > 0


def test_display_and_format():
    v = EtaDisplay()
    assert v.step(None, 1) is None
    assert v.step(600, 1) == 600
    assert v.step(620, 1) == 599        # 조금 늘어난 건 무시하고 계속 줄어듦
    assert v.step(400, 1) == 400        # 좋아지면 바로 반영
    assert v.step(700, 1) == 700        # 확실히 늦어지면 올림
    assert fmt_left(None) == "남은 시간 계산 중"
    assert fmt_left(30) == "1분 이내"
    assert fmt_left(61) == "남은 시간 약 2분"
    assert fmt_left(3600) == "남은 시간 약 1시간"
    assert fmt_left(3700) == "남은 시간 약 1시간 2분"
