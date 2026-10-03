"""💾 저장 공간 — 디스크가 가득 차서 40분 작업 끝에 렌더가 멈추지 않게.

2026-10-04 실제 작업: 10분짜리 원본 둘의 편집본(프록시, NVENC cq16 · 카메라마다 수 GB)이 작업 폴더에 있고, Remotion 이
렌더할 때마다(검수 스틸은 장마다) 그 프록시를 임시 폴더로 통째로 복사했다. 예전 작업 폴더 여럿의 프록시와 실패·취소한 렌더가
남긴 임시 복사본까지 쌓여 C 드라이브가 가득 찼고, 검수 렌더와 본 렌더가 `ENOSPC: no space left on device` 로 멈췄다.

여기서 하는 일:
- `free_bytes` · `is_disk_full` — 남은 공간, 디스크 가득 오류인지(Node ENOSPC · errno 28 · Windows 112 · 한국어 메시지).
- `sweep_temp` — 실패·취소한 렌더가 남긴 Remotion·Chrome 임시 폴더(이름이 `remotion-`·`puppeteer_dev_chrome_profile-`·
  `choi_render`)를 지운다. 앱 전용 임시 폴더에서는 10분, 시스템 임시 폴더에서는 2시간 넘게 손대지 않은 것만.
- `reclaim` — 지금 작업이 아닌 예전 작업 폴더에서 **다시 만들 수 있는 큰 파일만**(편집본 프록시 · 렌더 번들 · 무음 렌더 ·
  검수 스틸 · 스톡 원본) 오래된 것부터 지운다. 결과 영상(output/)·기획·전사·로그는 건드리지 않는다.
- `need_bytes` — 이 작업이 아직 쓸 공간 어림(프록시 + 렌더 + 여유).
- `DiskSpaceError` — 정리해도 모자라면 무엇이 얼마나 모자란지, 어디를 비우면 되는지 한국어로.
"""
from __future__ import annotations

import errno
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

GB = 1024 ** 3
MB = 1024 ** 2

# 다시 만들 수 있는 큰 파일(작업 폴더 기준) — 지워도 같은 입력으로 다시 누르면 그 단계만 다시 한다
RECLAIMABLE = ("media/proxy*.mp4", "render/bundle", "render/raw", "render/peek", "render/tmp", "work/qa",
               "work/stock_raw", "work/thumb_cands", "work/verify16k.wav")
TEMP_PREFIXES = ("remotion-", "puppeteer_dev_chrome_profile-", "choi_render")
SYSTEM_TEMP_PREFIXES = ("remotion-",)       # 시스템 임시 폴더에서는 Remotion 이 만든 것만(다른 프로그램 것은 두지 않는다)
DISK_FULL_MARKERS = ("enospc", "no space left on device", "not enough space on the disk", "disk full",
                     "디스크 공간이 부족", "디스크에 공간이 부족", "winerror 112", "errno 28")

# 편집본(프록시) 크기 어림: NVENC cq16 · GOP 15 · B 프레임 없음 1080p30 ≈ 30 Mbps ≈ 0.23 GB/분(x264 crf14 도 비슷)
PROXY_GB_PER_MIN_1080 = 0.23
# 렌더 결과(무음 렌더 + 소리 합친 완성본, GPU 16 Mbps ≈ 0.12 GB/분)
RENDER_GB_PER_MIN = 0.12
MARGIN = 2 * GB


class DiskSpaceError(RuntimeError):
    """정리해도 공간이 모자랄 때 — 메시지는 사용자에게 그대로 보인다."""


def free_bytes(path: str | Path) -> int:
    """path 가 있는 드라이브의 남은 바이트(없는 경로면 있는 부모까지 올라간다). 못 재면 아주 큰 값."""
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        return int(shutil.disk_usage(p).free)
    except OSError:
        return 1 << 62


def drive_label(path: str | Path) -> str:
    p = Path(path).resolve()
    return p.drive or (p.anchor or "/")


def fmt_gb(n: float) -> str:
    return f"{n / GB:.1f}GB"


def is_disk_full(err: BaseException | str) -> bool:
    if isinstance(err, OSError) and getattr(err, "errno", None) == errno.ENOSPC:
        return True
    if isinstance(err, OSError) and getattr(err, "winerror", None) in (39, 112):
        return True
    text = str(err).lower()
    return any(m in text for m in DISK_FULL_MARKERS)


def dir_size(p: Path) -> int:
    if p.is_file():
        try:
            return p.stat().st_size
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(p, onerror=lambda e: None):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def _remove(p: Path) -> int:
    """지우고, 실제로 사라진 바이트(쓰는 중이라 못 지운 파일은 빼고)."""
    before = dir_size(p)
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    else:
        try:
            p.unlink()
        except OSError:
            pass
    after = dir_size(p) if p.exists() else 0
    return max(0, before - after)


def _mtime(p: Path) -> float:
    """폴더는 안쪽까지 가장 최근 수정 시각(렌더 중인 폴더는 방금 쓴 파일이 있다)."""
    try:
        latest = p.stat().st_mtime
    except OSError:
        return time.time()
    if p.is_dir():
        for root, _dirs, files in os.walk(p, onerror=lambda e: None):
            for f in files[:200]:
                try:
                    latest = max(latest, os.lstat(os.path.join(root, f)).st_mtime)
                except OSError:
                    pass
    return latest


def temp_roots() -> list[tuple[Path, tuple[str, ...], float]]:
    """(임시 폴더, 지울 이름 앞부분, 최소 방치 시간 초). 앱 전용 임시 폴더(실행 .bat 이 TEMP 를 돌려 둔 곳)는 10분,
    시스템 임시 폴더는 2시간 — 다른 Remotion 작업이 쓰는 중일 수 있으니."""
    from .paths import ROOT
    out: list[tuple[Path, tuple[str, ...], float]] = []
    seen: set[str] = set()

    def add(p: Optional[Path], prefixes: tuple[str, ...], age: float) -> None:
        if p is None:
            return
        try:
            key = str(p.resolve()).lower()
        except OSError:
            return
        if key in seen or not p.is_dir():
            return
        seen.add(key)
        out.append((p, prefixes, age))
    app_tmp = [ROOT / "tools" / "tmp"]
    la = os.environ.get("LOCALAPPDATA")
    if la:
        app_tmp.append(Path(la) / "Temp" / "ChoiStudio")
    cur = Path(tempfile.gettempdir())
    for p in app_tmp:
        add(p, TEMP_PREFIXES, 600.0)
    if any(str(cur).lower() == str(p).lower() for p in app_tmp):
        add(cur, TEMP_PREFIXES, 600.0)
    else:
        add(cur, SYSTEM_TEMP_PREFIXES + ("choi_render",), 7200.0)
    if la:
        add(Path(la) / "Temp", SYSTEM_TEMP_PREFIXES + ("choi_render",), 7200.0)
    return out


def sweep_temp(roots: Optional[Iterable[tuple[Path, tuple[str, ...], float]]] = None, *,
               now: Optional[float] = None, log: Callable[[str], None] = lambda m: None) -> int:
    """실패·취소한 렌더가 남긴 임시 폴더를 지운다 → 지운 바이트."""
    now = time.time() if now is None else now
    freed = 0
    for root, prefixes, age in (temp_roots() if roots is None else roots):
        try:
            entries = list(Path(root).iterdir())
        except OSError:
            continue
        for p in entries:
            if not p.name.startswith(prefixes):
                continue
            if now - _mtime(p) < age:
                continue
            freed += _remove(p)
    if freed >= 50 * MB:
        log(f"🧹 지난 렌더가 남긴 임시 파일 {fmt_gb(freed)} 를 지웠습니다")
    return freed


@dataclass
class JobCache:
    path: Path
    items: list[Path] = field(default_factory=list)
    size: int = 0
    finished: bool = False
    mtime: float = 0.0


def job_caches(projects_dir: Path, keep: Iterable[Path] = ()) -> list[JobCache]:
    """지울 수 있는 예전 작업의 큰 파일 목록 — 끝난 작업 먼저, 그 안에서 오래된 것부터. 작업 폴더처럼 생긴 것(work/ 와
    job.json 또는 media/·render/)만 본다."""
    keep_s = {str(Path(k).resolve()).lower() for k in keep}
    out: list[JobCache] = []
    try:
        dirs = [d for d in Path(projects_dir).iterdir() if d.is_dir()]
    except OSError:
        return []
    for d in dirs:
        try:
            if str(d.resolve()).lower() in keep_s:
                continue
        except OSError:
            continue
        if not (d / "work").is_dir() or not ((d / "job.json").exists() or (d / "media").is_dir()
                                             or (d / "render").is_dir()):
            continue
        items: list[Path] = []
        for pat in RECLAIMABLE:
            items += [p for p in d.glob(pat) if p.exists()]
        size = sum(dir_size(p) for p in items)
        if size < 20 * MB:
            continue
        out_dir = d / "output"
        finished = out_dir.is_dir() and any(out_dir.glob("*.mp4"))
        try:
            mtime = (d / "job.json").stat().st_mtime if (d / "job.json").exists() else d.stat().st_mtime
        except OSError:
            mtime = 0.0
        out.append(JobCache(d, items, size, finished, mtime))
    out.sort(key=lambda j: (not j.finished, j.mtime))
    return out


def reclaim(projects_dir: Path, keep: Iterable[Path], need: int, *, at: Optional[Path] = None,
            log: Callable[[str], None] = lambda m: None) -> int:
    """남은 공간이 need 바이트가 될 때까지: 임시 폴더 청소 → 예전 작업의 다시 만들 수 있는 큰 파일(끝난 작업·오래된 것부터).
    → 지운 바이트. 결과 영상(output/)·기획·전사는 그대로 둔다."""
    where = at or projects_dir
    freed = sweep_temp(log=log)
    if free_bytes(where) >= need:
        return freed
    for job in job_caches(projects_dir, keep):
        got = 0
        for p in job.items:
            got += _remove(p)
        if got:
            freed += got
            log(f"🧹 예전 작업 「{job.path.name[:40]}」의 편집본·렌더 임시 파일 {fmt_gb(got)} 정리"
                f"(결과 영상·기획은 그대로 — 그 작업을 다시 누르면 편집본만 새로 만듭니다)")
        if free_bytes(where) >= need:
            break
    return freed


def need_bytes(source_minutes: float, *, height: int = 1080, cameras: int = 1, have_proxies: int = 0,
               render: bool = True) -> int:
    """이 작업이 앞으로 쓸 공간 어림: 아직 없는 편집본(카메라마다 원본 길이) + 렌더 결과(무음 렌더 + 완성본, 원본 길이의
    절반을 넘지 않는다고 본다) + 여유 2GB."""
    scale = (max(360, height) / 1080) ** 2
    proxies = PROXY_GB_PER_MIN_1080 * scale * source_minutes * GB
    proxies = max(0.0, proxies - have_proxies)
    out = RENDER_GB_PER_MIN * scale * max(1.0, source_minutes / max(1, cameras) * 0.6) * 2 * GB if render else 0
    return int(proxies + out + MARGIN)


def shortage_message(where: Path, free: int, need: int, projects_dir: Path, keep: Iterable[Path] = ()) -> str:
    """정리해도 모자랄 때 사용자에게 보일 글."""
    left = job_caches(projects_dir, keep)
    others = sum(j.size for j in left)
    drive = drive_label(where)
    lines = [f"저장 공간이 부족합니다 — {drive} 드라이브 여유 {fmt_gb(free)}, 이 작업에 약 {fmt_gb(need)} 가 필요합니다.",
             "지난 렌더의 임시 파일과 예전 작업의 편집본(다시 만들 수 있는 파일)은 이미 정리했습니다."]
    if others:
        lines.append(f"아직 남은 예전 작업 파일: {fmt_gb(others)}")
    lines += ["다음 중 하나를 한 뒤 같은 입력으로 다시 누르면 끝난 단계는 건너뛰고 이어서 합니다:",
              f"  · {projects_dir} 에서 필요 없는 예전 작업 폴더를 지운다(output 안의 완성 영상은 먼저 옮겨 두세요)",
              "  · 고급 설정 › 경로 에서 작업 폴더를 여유 있는 다른 드라이브로 바꾼다",
              "  · 윈도우 설정 › 시스템 › 저장소 에서 임시 파일·휴지통을 비운다"]
    if "onedrive" in str(projects_dir).lower():
        lines.append("  · 프로그램 폴더가 OneDrive 안에 있어 작업 파일(수 GB)이 OneDrive 로도 올라갑니다 — "
                     "C:\\ChoiStudio 처럼 OneDrive 밖으로 옮기길 권합니다")
    return "\n".join(lines)
