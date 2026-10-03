"""Remotion 렌더 실행(renderer/scripts/render.mjs) 및 Studio 미리보기."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..paths import RENDERER_DIR, TOOLS_DIR
from ..util import CancelToken, LogFn, ProgressFn, noop_log, noop_progress, run_process, write_json


class RenderError(RuntimeError):
    pass


def render_temp_dir() -> Path:
    """렌더 프로세스 하나만 쓰는 임시 폴더(TEMP 아래 choi_render/<pid>_<ms>) — Remotion·Chrome 이 os.tmpdir() 에 만드는
    것(브라우저 프로필·자산 내려받기)이 모두 여기로 오고, 렌더가 끝나면(실패·취소여도) 통째로 지운다. 예전엔 실패·취소한 렌더마다
    수 GB 프록시 복사본이 임시 폴더에 남아 쌓였다(2026-10-04 ENOSPC). ASCII 경로라 Chrome 프로필 경로에 한글이 안 들어간다."""
    d = Path(tempfile.gettempdir()) / "choi_render" / f"{os.getpid()}_{int(time.time() * 1000)}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def preflight_items(job: "RenderJob", log: LogFn = noop_log) -> list["RenderItem"]:
    """🛫 렌더 전 자산 확인(studio/render/preflight.py): props 마다 가리키는 파일이 publicDir 에 있는지 보고, 없는 것을 가리키는
    부품은 빼서 props 파일을 다시 쓴다 — 그림 하나가 없다고 Remotion 이 렌더 전체를 멈추지 않게(2026-10-04). 화자 영상이 없으면
    렌더할 수 없으니 그 이유로 멈추고, 그림이 없는 썸네일은 그 한 장만 건너뛴다."""
    from . import preflight
    chk = preflight.MediaCheck(job.public_dir, {dst: Path(src) for src, dst in job.links})
    done: dict[str, list[str]] = {}
    keep: list[RenderItem] = []
    for it in job.items:
        key = str(it.props_path)
        if key not in done:
            done[key] = []
            try:
                props = json.loads(Path(it.props_path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                props = None             # 읽을 수 없으면 렌더러가 그 이유로 실패하게 둔다
            if isinstance(props, dict):
                notes, fatal = preflight.fix_props(props, chk)
                if notes:
                    write_json(Path(it.props_path), props)
                    job.fixed.append(Path(it.props_path))
                    log(f"🛫 렌더 전 자산 확인({Path(it.props_path).name}): 없는 파일을 가리키는 {len(notes)}곳을 빼고 렌더합니다 — "
                        + preflight.summary(notes))
                done[key] = fatal
        fatal = done[key]
        if fatal and it.composition == "Thumbnail":
            log(f"🛫 썸네일 {Path(it.output).name} 건너뜀 — " + " · ".join(fatal))
            continue
        if fatal:
            raise RenderError("렌더할 수 없습니다 — " + " · ".join(fatal))
        keep.append(it)
    return keep


def find_node(custom: str = "") -> str:
    if custom and Path(custom).exists():
        return custom
    portable = TOOLS_DIR / "node" / ("node.exe" if sys.platform == "win32" else "bin/node")
    if portable.exists():  # setup_windows.bat 이 설치한 휴대용 Node.js 우선
        return str(portable)
    p = shutil.which("node")
    if p:
        return p
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
            cand = Path(base) / "nodejs" / "node.exe"
            if cand.exists():
                return str(cand)
    raise RenderError("Node.js 를 찾을 수 없습니다. setup_windows.bat 을 다시 실행하면 tools\\node 에 자동으로 설치됩니다.")


def ensure_renderer_installed() -> None:
    if not (RENDERER_DIR / "node_modules" / "remotion").exists():
        raise RenderError("renderer 의존성이 없습니다. renderer 폴더에서 'npm install' 을 실행하세요 (setup_windows.bat 이 자동으로 합니다).")


@dataclass
class RenderItem:
    kind: str            # video | still | frames(같은 props 로 스틸 여러 장 — 검수용)
    composition: str     # LongForm | Short | Thumbnail
    props_path: Path
    output: Path
    scale: float = 1.0
    crf: int = 18
    x264_preset: str = "medium"
    encoder: str = "auto"   # auto(Windows=GPU) | cpu | gpu
    weight: float = 1.0     # 진행률 가중치(길이)
    frame: int = 0          # still: 뽑을 프레임
    frames: list[tuple[int, Path]] = field(default_factory=list)  # frames: (프레임, 출력 경로)
    muted: bool = False     # 소리 없이 렌더(음향은 FFmpeg 에서 따로 믹스·마스터링)
    peek_dir: str = ""      # video: props.peekEvery 프레임마다 지금 프레임을 여기에 jpg 로(진행 화면 미리보기)

    def to_job(self) -> dict:
        d = {"kind": self.kind, "composition": self.composition, "props": str(self.props_path),
             "output": str(self.output), "scale": self.scale, "crf": self.crf, "x264Preset": self.x264_preset,
             "encoder": self.encoder, "frame": int(self.frame), "muted": bool(self.muted),
             "peekDir": str(self.peek_dir)}
        if self.frames:
            d["frames"] = [{"frame": int(f), "output": str(o)} for f, o in self.frames]
        return d


@dataclass
class RenderJob:
    public_dir: Path
    bundle_dir: Path
    links: list[tuple[Path, str]] = field(default_factory=list)
    items: list[RenderItem] = field(default_factory=list)
    fixed: list[Path] = field(default_factory=list)   # 렌더 전 자산 확인이 고쳐 다시 쓴 props 파일
    browser_executable: str = ""
    gl: str = ""
    concurrency: int = 0
    reuse_bundle: bool = False


def run_render(job: RenderJob, job_file: Path, *, node: str, log: LogFn = noop_log,
               progress: ProgressFn = noop_progress, cancel: Optional[CancelToken] = None,
               on_peek: Optional[Callable[[dict], None]] = None) -> None:
    """on_peek: 미리보기 이미지가 나올 때마다 {index, frame, file[, k, n]} (렌더 중 프레임·검수 스틸·썸네일)."""
    ensure_renderer_installed()
    had = bool(job.items)
    job.items = preflight_items(job, log)
    if had and not job.items:            # 건너뛴 썸네일뿐이면 부를 것이 없다
        return
    data = {
        "publicDir": str(job.public_dir),
        "bundleDir": str(job.bundle_dir),
        "links": [{"src": str(src), "dst": dst} for src, dst in job.links],
        "browserExecutable": job.browser_executable,
        "gl": job.gl,
        "concurrency": job.concurrency,
        "reuseBundle": job.reuse_bundle,
        "renders": [it.to_job() for it in job.items],
    }
    write_json(job_file, data)
    weights = [max(0.05, it.weight) for it in job.items]
    total_w = sum(weights) or 1.0
    done_w = [0.0]
    state = {"index": -1, "err": ""}
    bundle_share = 0.04

    def on_line(line: str) -> None:
        line = line.strip()
        if not line.startswith("{"):
            noisy = ("memory" in line.lower() or "docker" in line.lower() or "cgroup" in line.lower())
            if line and not noisy:
                log(f"[remotion] {line[:300]}")
            return
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            log(f"[remotion] {line[:300]}")
            return
        typ = ev.get("type")
        if typ == "bundle":
            progress(bundle_share * float(ev.get("progress", 0)))
        elif typ == "start":
            state["index"] = ev["index"]
            if job.items[ev["index"]].kind != "frames":
                log(f"렌더 시작: {ev.get('composition')} → {Path(ev.get('output', '')).name}")
        elif typ == "progress":
            i = ev["index"]
            frac = (done_w[0] + weights[i] * float(ev.get("progress", 0))) / total_w
            progress(bundle_share + (1 - bundle_share) * frac)
        elif typ == "done":
            done_w[0] += weights[ev["index"]]
            if job.items[ev["index"]].kind != "frames":
                log(f"완료: {Path(ev.get('output', '')).name}")
        elif typ == "error":
            state["err"] = ev.get("message", "")
            log("[remotion 오류] " + state["err"][:2000])
        elif typ == "log":
            log(f"[remotion] {ev.get('message', '')}")
        elif typ == "peek" and on_peek is not None:
            try:
                on_peek(ev)
            except Exception:  # noqa: BLE001 - 미리보기 실패가 렌더를 멈추면 안 됨
                pass

    tmp = render_temp_dir()
    env = {**os.environ, "TEMP": str(tmp), "TMP": str(tmp), "TMPDIR": str(tmp)}
    try:
        code, tail = run_process([node, str(RENDERER_DIR / "scripts" / "render.mjs"), str(job_file)], cwd=RENDERER_DIR,
                                 env=env, on_line=on_line, cancel=cancel)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if code != 0:
        raise RenderError("Remotion 렌더 실패\n" + (state["err"] or tail)[-3000:])
    progress(1.0)

