"""💾 저장 공간(studio/storage.py) — 2026-10-04 실제 작업이 디스크 가득(ENOSPC)으로 검수·렌더에서 멈췄다.

Remotion 이 렌더마다(검수 스틸은 장마다) 수 GB 프록시를 임시 폴더로 복사했고, 예전 작업 폴더의 프록시와 실패한 렌더가 남긴
임시 복사본이 쌓여 C 드라이브가 가득 찼다."""
from __future__ import annotations

import errno
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studio import storage  # noqa: E402
from studio.util import CancelToken  # noqa: E402

MB = 1024 * 1024


def _file(p: Path, mb: float, age_h: float = 0.0) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\0" * int(mb * MB))
    if age_h:
        t = time.time() - age_h * 3600
        os.utime(p, (t, t))
    return p


def _age(p: Path, hours: float) -> None:
    t = time.time() - hours * 3600
    for root, _d, files in os.walk(p):
        for f in files:
            os.utime(os.path.join(root, f), (t, t))
    os.utime(p, (t, t))


def test_disk_full_is_recognized_in_every_form():
    assert storage.is_disk_full(OSError(errno.ENOSPC, "No space left on device"))
    assert storage.is_disk_full(RuntimeError("Remotion 렌더 실패\nError: ENOSPC: no space left on device, write"))
    assert storage.is_disk_full(OSError(28, "디스크 공간이 부족합니다"))
    assert storage.is_disk_full("[WinError 112] There is not enough space on the disk")
    assert not storage.is_disk_full(RuntimeError("KeyError: 'gap'"))
    assert not storage.is_disk_full(OSError(errno.ENOENT, "No such file"))


def test_sweep_temp_removes_only_stale_render_leftovers(tmp_path):
    app = tmp_path / "app_tmp"
    old_copy = app / "remotion-v4.0.530-assetsabc123" / "remotion-assets-dir" / "proxy_2.mp4"
    _file(old_copy, 5)
    _age(app / "remotion-v4.0.530-assetsabc123", 1.0)
    old_profile = app / "puppeteer_dev_chrome_profile-XYZ"
    _file(old_profile / "Default" / "Cookies", 1)
    _age(old_profile, 1.0)
    fresh = app / "remotion-v4.0.530-assetsnew"            # 지금 렌더 중일 수 있다(10분 안)
    _file(fresh / "remotion-assets-dir" / "proxy.mp4", 1)
    mine = app / "choi_render" / "123_456"
    _file(mine / "x.bin", 1)
    _age(app / "choi_render", 1.0)
    other = app / "someone-else"
    _file(other / "keep.bin", 1)
    _age(other, 5.0)
    system = tmp_path / "sys_tmp"
    sys_old = system / "remotion-v4.0.530-assetsold"
    _file(sys_old / "a.mp4", 2)
    _age(sys_old, 3.0)
    sys_young = system / "remotion-v4.0.530-assetsyoung"   # 시스템 임시 폴더는 2시간 넘은 것만
    _file(sys_young / "a.mp4", 2)
    _age(sys_young, 1.0)
    sys_puppeteer = system / "puppeteer_dev_chrome_profile-OTHER"   # 다른 프로그램 것일 수 있다 → 두기
    _file(sys_puppeteer / "x", 1)
    _age(sys_puppeteer, 5.0)
    logs: list[str] = []
    freed = storage.sweep_temp([(app, storage.TEMP_PREFIXES, 600.0),
                                (system, storage.SYSTEM_TEMP_PREFIXES + ("choi_render",), 7200.0)], log=logs.append)
    assert not old_copy.exists() and not old_profile.exists() and not (app / "choi_render").exists()
    assert not sys_old.exists()
    assert fresh.exists() and other.exists() and sys_young.exists() and sys_puppeteer.exists()
    assert freed >= 9 * MB and logs == []          # 50MB 아래면 로그로 떠들지 않는다


def _job(projects: Path, name: str, *, proxy_mb: float, finished: bool, age_h: float) -> Path:
    d = projects / name
    (d / "work").mkdir(parents=True)
    (d / "work" / "plan.json").write_text("{}", encoding="utf-8")
    (d / "job.json").write_text("{}", encoding="utf-8")
    _file(d / "media" / "proxy.mp4", proxy_mb)
    _file(d / "render" / "raw" / "long.mp4", 10)
    _file(d / "work" / "qa" / "r1" / "g1.jpg", 1)
    if finished:
        _file(d / "output" / "1_롱폼.mp4", 10)
    t = time.time() - age_h * 3600
    os.utime(d / "job.json", (t, t))
    return d


def test_reclaim_frees_old_jobs_regenerable_files_but_never_outputs_or_the_current_job(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    oldest_unfinished = _job(projects, "20261001_old_failed", proxy_mb=60, finished=False, age_h=72)
    old_done = _job(projects, "20261002_done", proxy_mb=60, finished=True, age_h=48)
    newer_done = _job(projects, "20261003_done", proxy_mb=60, finished=True, age_h=24)
    current = _job(projects, "20261004_current", proxy_mb=60, finished=False, age_h=0)
    (projects / "not_a_job").mkdir()
    _file(projects / "not_a_job" / "big.mp4", 50)
    monkeypatch.setattr(storage, "temp_roots", lambda: [])
    base = 10 * MB

    def fake_free(_p):
        gone = sum(71 * MB for d in (oldest_unfinished, old_done, newer_done)
                   if not (d / "media" / "proxy.mp4").exists())
        return base + gone
    monkeypatch.setattr(storage, "free_bytes", fake_free)
    logs: list[str] = []
    freed = storage.reclaim(projects, [current], 100 * MB, log=logs.append)
    # 끝난 작업 중 오래된 것부터 → 하나로 모자라 다음 끝난 작업 → 그래서 멈춤(끝나지 않은 작업은 건드리지 않음)
    assert not (old_done / "media" / "proxy.mp4").exists() and not (newer_done / "media" / "proxy.mp4").exists()
    assert (oldest_unfinished / "media" / "proxy.mp4").exists()
    assert freed >= 140 * MB and len(logs) == 2 and "결과 영상" in logs[0]
    for d in (old_done, newer_done):
        assert (d / "output" / "1_롱폼.mp4").exists() and (d / "work" / "plan.json").exists()
        assert not (d / "render" / "raw").exists() and not (d / "work" / "qa").exists()
    assert (current / "media" / "proxy.mp4").exists() and (current / "render" / "raw" / "long.mp4").exists()
    assert (projects / "not_a_job" / "big.mp4").exists()


def test_need_estimate_and_shortage_message(tmp_path):
    full = storage.need_bytes(19.5, height=1080, cameras=2)          # 2026-10-04: 10분 + 9.5분 원본 둘
    assert 6 * storage.GB < full < 10 * storage.GB
    resumed = storage.need_bytes(19.5, height=1080, cameras=2, have_proxies=int(4.5 * storage.GB))
    assert resumed < full - 4 * storage.GB
    msg = storage.shortage_message(tmp_path / "OneDrive" / "Desktop" / "projects" / "job", int(1.2 * storage.GB),
                                   full, tmp_path / "OneDrive" / "projects")
    assert msg.startswith("저장 공간이 부족합니다") and "1.2GB" in msg and "OneDrive" in msg and "다시 누르면" in msg


def _pipe(tmp_path, monkeypatch, free_seq):
    import studio.pipeline as pl
    p = object.__new__(pl.Pipeline)
    p.dir = tmp_path / "projects" / "job"
    p.media = p.dir / "media"
    p.media.mkdir(parents=True)
    p.infos = {0: SimpleNamespace(duration=600.0)}
    p.info = p.infos[0]
    p.smap = SimpleNamespace(groups=[0], cams=[0])
    p.spec = SimpleNamespace(out_height=1080)
    p.cancel = CancelToken()
    p.logs = []
    p.log = p.logs.append
    p._log_file_only = lambda m: None
    p.soft_failures = []
    p.eta = SimpleNamespace(start=lambda k: None, finish=lambda k: None)
    p._stage = lambda *a: None
    reclaimed: list[int] = []
    monkeypatch.setattr(storage, "reclaim", lambda *a, **k: reclaimed.append(1) or 0)
    monkeypatch.setattr(storage, "sweep_temp", lambda **k: 0)
    it = iter(free_seq)
    monkeypatch.setattr(storage, "free_bytes", lambda _p: next(it))
    return p, reclaimed


def test_stage_hitting_a_full_disk_is_cleaned_up_and_retried_once(tmp_path, monkeypatch):
    big = 100 * storage.GB
    p, reclaimed = _pipe(tmp_path, monkeypatch, [0, big, big])
    calls: list[int] = []

    def render():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("Remotion 렌더 실패\nError: ENOSPC: no space left on device, write")
    p._call_stage("render", render)
    assert len(calls) == 2 and reclaimed and any("한 번 다시" in m for m in p.logs)


def test_full_disk_that_cleanup_cannot_fix_stops_with_a_clear_message_even_in_a_soft_stage(tmp_path, monkeypatch):
    p, _ = _pipe(tmp_path, monkeypatch, [0] * 10)

    def qa():
        raise RuntimeError("Error: ENOSPC: no space left on device, write")
    with pytest.raises(storage.DiskSpaceError) as e:
        p._run_stage("qa", qa)                 # 검수는 말단 단계지만 디스크 가득은 삼키지 않는다(렌더도 같은 이유로 멈춘다)
    assert str(e.value).startswith("저장 공간이 부족합니다") and not p.soft_failures


def test_space_check_before_long_work_stops_early(tmp_path, monkeypatch):
    p, reclaimed = _pipe(tmp_path, monkeypatch, [int(1 * storage.GB), int(1.5 * storage.GB)])
    with pytest.raises(storage.DiskSpaceError):
        p._ensure_space("start")
    assert reclaimed and any("저장 공간" in m for m in p.logs)
    p2, reclaimed2 = _pipe(tmp_path / "b", monkeypatch, [50 * storage.GB])
    p2._ensure_space("render")                  # 넉넉하면 아무것도 지우지 않는다
    assert not reclaimed2


def test_render_runs_in_its_own_temp_folder_and_removes_it(tmp_path, monkeypatch):
    from studio.render import remotion
    seen: dict = {}

    def fake_run(args, *, cwd=None, env=None, on_line=None, cancel=None, stdin_data=None):
        t = Path(env["TEMP"])
        seen["tmp"] = t
        seen["same"] = env["TMP"] == env["TEMP"] == env["TMPDIR"]
        (t / "remotion-v4.0.530-assetsX").mkdir(parents=True)
        (t / "remotion-v4.0.530-assetsX" / "copy.mp4").write_bytes(b"x" * 1000)
        return 1, "Error: ENOSPC: no space left on device, write"
    monkeypatch.setattr(remotion, "run_process", fake_run)
    monkeypatch.setattr(remotion, "ensure_renderer_installed", lambda: None)
    job = remotion.RenderJob(public_dir=tmp_path / "pub", bundle_dir=tmp_path / "bundle")
    with pytest.raises(remotion.RenderError) as e:
        remotion.run_render(job, tmp_path / "job.json", node="node")
    assert "choi_render" in str(seen["tmp"]) and seen["same"]
    assert not seen["tmp"].exists()              # 실패해도 임시 폴더(프록시 복사본 포함)는 지운다
    assert storage.is_disk_full(e.value)


def test_render_script_reads_public_media_in_place():
    """render.mjs 가 번들 public 의 영상을 임시 폴더로 복사하지 않게 Remotion 의 downloadAsset 을 고친다 — 그 연결이
    지금 설치된 Remotion 에 맞는지(파일·함수 이름) 확인한다."""
    js = (ROOT / "renderer" / "scripts" / "render.mjs").read_text(encoding="utf-8")
    assert "require('@remotion/renderer')" in js and "localMedia(pub)" in js
    assert "from '@remotion/renderer'" not in js          # ESM 판은 고칠 수 없다 — CommonJS 판 하나만
    dl = ROOT / "renderer" / "node_modules" / "@remotion" / "renderer" / "dist" / "assets" / \
        "download-and-map-assets-to-file.js"
    srv = ROOT / "renderer" / "node_modules" / "@remotion" / "renderer" / "dist" / "offthread-video-server.js"
    if not dl.exists():
        pytest.skip("renderer/node_modules 없음")
    assert "exports.downloadAsset = downloadAsset" in dl.read_text(encoding="utf-8")
    assert "(0, download_and_map_assets_to_file_1.downloadAsset)(" in srv.read_text(encoding="utf-8")
