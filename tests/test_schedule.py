"""동시 실행 일정(pipeline.SCHEDULE): 서로 기다리지 않는 단계는 같이 돌고, 한 줄이 실패하면 나머지를 멈추고 원인 오류를 올린다."""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import pipeline as pl  # noqa: E402
from studio.eta import Eta  # noqa: E402
from studio.util import CancelToken, Cancelled  # noqa: E402


def _bare(tmp_path) -> pl.Pipeline:
    """FFmpeg 없이 _run_step 만 쓰는 최소 파이프라인."""
    p = object.__new__(pl.Pipeline)
    p.cancel = CancelToken()
    p.eta = Eta(None)
    p._progress = lambda *a: None
    p._user_log = lambda m: None
    p.log_file = tmp_path / "log.txt"
    p.log = p._log
    p._preview_cb = None
    p.extras = tmp_path
    return p


def test_schedule_keeps_dependencies():
    order = [k for st in pl.SCHEDULE for lane in st for k in lane if k in pl.STAGE_LABEL]
    assert sorted(order) == sorted(pl.STAGE_LABEL)            # 모든 단계가 한 번씩
    pos = {k: i for i, st in enumerate(pl.SCHEDULE) for lane in st for k in lane}
    # 음성 인식은 목소리 뒤, 정렬은 인식·얼굴 뒤, 색보정·기획은 정렬 뒤, 컷 검사·자료는 기획 뒤, 렌더는 그 모두 뒤
    assert pos["asr"] == pos["audio"] and pos["face"] == pos["asr"] < pos["align"]
    assert pos["align"] < pos["grade"] == pos["proxy"] == pos["director"]
    lane = next(lane for st in pl.SCHEDULE for lane in st if "grade" in lane)
    assert lane.index("grade") < lane.index("proxy")          # 프록시는 색보정 LUT 가 필요
    assert pos["director"] < pos["verify"] == pos["broll"] == pos["stock"] < pos["qa"] < pos["render"] < pos["master"]
    plan = [k for st in pl.schedule_for("plan") for lane in st for k in lane]
    assert set(plan) == set(pl.PLAN_ONLY) and "proxy" not in plan


def test_lanes_run_concurrently(tmp_path):
    p = _bare(tmp_path)
    seen: list[str] = []
    lock = threading.Lock()

    def work(name):
        def fn():
            time.sleep(0.4)
            with lock:
                seen.append(name)
        return fn
    t0 = time.time()
    p._run_step([["audio", "asr"], ["face"]], {"audio": work("audio"), "asr": work("asr"), "face": work("face")})
    took = time.time() - t0
    assert 0.75 < took < 1.15, took                         # 0.4 + 0.4 (얼굴 추적은 그 사이 같이)
    assert seen.index("audio") < seen.index("asr") and set(seen) == {"audio", "asr", "face"}
    assert {"audio", "asr", "face"} <= p.eta._done


def test_failing_lane_stops_others_and_raises_cause(tmp_path):
    p = _bare(tmp_path)

    def slow():
        for _ in range(100):           # 멈춤 신호가 오면 Cancelled
            time.sleep(0.05)
            p.cancel.check()

    def boom():
        time.sleep(0.1)
        raise ValueError("원인")
    t0 = time.time()
    with pytest.raises(ValueError, match="원인"):
        p._run_step([["director"], ["grade"]], {"director": slow, "grade": boom})
    assert time.time() - t0 < 2.0 and p.cancel.cancelled


def test_hidden_prep_failure_does_not_fail_the_step(tmp_path):
    p = _bare(tmp_path)

    def bad():
        raise RuntimeError("번들 실패")
    p._run_step([["sound"], ["bundle"]], {"sound": lambda: None, "bundle": bad})
    assert "번들 실패" in (tmp_path / "log.txt").read_text(encoding="utf-8")


def test_user_cancel_propagates_as_cancelled(tmp_path):
    p = _bare(tmp_path)

    def wait_cancel():
        for _ in range(100):
            time.sleep(0.02)
            p.cancel.check()
    threading.Timer(0.1, p.cancel.cancel).start()
    with pytest.raises(Cancelled):
        p._run_step([["verify"], ["broll"]], {"verify": wait_cancel, "broll": wait_cancel})
