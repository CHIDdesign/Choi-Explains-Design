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
    # 음성 인식은 목소리 뒤, 정렬은 인식 바로 뒤(같은 줄 — 얼굴은 stage_align 이 기다리고, 🔎 조사는 기다리지 않는다),
    # 색보정·기획은 정렬·조사 뒤, 컷 검사·자료는 기획 뒤, 렌더는 그 모두 뒤
    lane = next(lane for st in pl.SCHEDULE for lane in st if "asr" in lane)
    assert lane.index("audio") < lane.index("asr") < lane.index("align")
    assert pos["face"] == pos["research"] == pos["align"]
    assert pos["align"] < pos["grade"] == pos["proxy"] == pos["director"]
    lane = next(lane for st in pl.SCHEDULE for lane in st if "grade" in lane)
    assert lane.index("grade") < lane.index("proxy")          # 프록시는 색보정 LUT 가 필요
    assert pos["director"] < pos["verify"] == pos["broll"] == pos["stock"] < pos["qa"] < pos["render"] < pos["master"]
    assert pos["verify"] < pos["music"] == pos["qa"]           # 🎼 큐 시트는 편집 검사가 컷을 확정한 뒤
    plan = [k for st in pl.schedule_for("plan") for lane in st for k in lane]
    assert set(plan) == set(pl.PLAN_ONLY) and "proxy" not in plan


def test_lanes_run_concurrently(tmp_path):
    p = _bare(tmp_path)
    seen: list[str] = []
    span: dict[str, tuple[float, float]] = {}
    lock = threading.Lock()

    def work(name):
        def fn():
            a = time.monotonic()
            time.sleep(0.4)
            with lock:
                seen.append(name)
                span[name] = (a, time.monotonic())
        return fn
    p._run_step([["audio", "asr"], ["face"]], {"audio": work("audio"), "asr": work("asr"), "face": work("face")})
    # 시계 길이 대신 겹침으로 확인(기계가 바쁠 때 sleep 이 늘어나도 흔들리지 않게): 얼굴 추적은 목소리 → 인식과 동시에,
    # 목소리 다듬기와 인식은 차례로
    assert span["face"][0] < span["audio"][1] and span["audio"][0] < span["face"][1]
    assert span["audio"][1] <= span["asr"][0] + 1e-3
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
    with pytest.raises(ValueError, match="원인"):       # 꼭 필요한 단계(대본 맞추기)의 실패는 작업을 멈춘다
        p._run_step([["director"], ["align"]], {"director": slow, "align": boom})
    assert time.time() - t0 < 2.0 and p.cancel.cancelled


def test_leaf_stage_failure_is_skipped_with_a_safe_fallback(tmp_path):
    """말단 작업(효과음·검수·편집 검사 …)이 실패하면 그 단계만 건너뛰고(대체 상태) 나머지는 끝까지 돈다."""
    from types import SimpleNamespace
    p = _bare(tmp_path)
    p.soft_failures = []
    p.spec = SimpleNamespace(sfx=True, music=True)
    ran = []

    def bad():
        raise RuntimeError("효과음 서버 다운")
    p._run_step([["verify"], ["sound", "bundle"]],
                {"verify": lambda: ran.append("verify"), "sound": bad, "bundle": lambda: ran.append("bundle")})
    assert ran == ["verify", "bundle"] or sorted(ran) == ["bundle", "verify"]
    assert not p.cancel.cancelled and p.spec.sfx is False and p.spec.music is False
    assert p.soft_failures[0]["stage"] == "sound" and "효과음 서버 다운" in p.soft_failures[0]["error"]
    assert "건너뛰고 계속" in (tmp_path / "log.txt").read_text(encoding="utf-8")


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


def test_sound_defaults_no_sfx_and_only_my_music(tmp_path):
    """채널 주인: 효과음·음원이 다 별로 → 효과음은 🎬 총괄 감독(Claude)이 고른 곳에만(sfx_mode='directed', 기본 —
    docs/upgrade/14), 배경음악은 내 음악 폴더의 곡만(비어 있으면 없음, 둘 이상이면 음악 감독이 고른다)."""
    from types import SimpleNamespace

    from studio.settings import Settings
    st = Settings()
    assert st.sfx_enabled is False and st.sfx_mode == "directed" and st.music_mode == "mine"
    p = _bare(tmp_path)
    music = tmp_path / "music"
    music.mkdir()
    p.settings = SimpleNamespace(sfx_enabled=False, sfx_mode="off", music_mode="mine", music_dir=str(music))
    p.spec = SimpleNamespace(sfx=True, music=True, bgm="", topic="디자인", video="a.mp4")
    pl.Pipeline._resolve_sound(p)
    assert p.spec.sfx is False and p.spec.music is False and p.spec.bgm == ""      # 효과음 끔 · 폴더가 비면 음악 없음
    p.settings = SimpleNamespace(sfx_enabled=False, sfx_mode="directed", music_mode="mine", music_dir=str(music))
    p.spec = SimpleNamespace(sfx=True, music=True, bgm="", topic="디자인", video="a.mp4")
    pl.Pipeline._resolve_sound(p)
    assert p.spec.sfx is True                                                        # 감독이 고른 곳에만
    (music / "calm.mp3").write_bytes(b"x")
    p.spec = SimpleNamespace(sfx=True, music=True, bgm="", topic="디자인", video="a.mp4")
    pl.Pipeline._resolve_sound(p)
    assert p.spec.music is True and p.spec.bgm.endswith("calm.mp3")
    p.settings = SimpleNamespace(sfx_enabled=True, music_mode="off", music_dir="")
    p.spec = SimpleNamespace(sfx=True, music=True, bgm="", topic="디자인", video="a.mp4")
    pl.Pipeline._resolve_sound(p)
    assert p.spec.sfx is True and p.spec.music is False
