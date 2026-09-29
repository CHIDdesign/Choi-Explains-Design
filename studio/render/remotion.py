"""Remotion 렌더 실행(renderer/scripts/render.mjs) 및 Studio 미리보기."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..paths import RENDERER_DIR
from ..util import CancelToken, LogFn, ProgressFn, noop_log, noop_progress, run_process, write_json


class RenderError(RuntimeError):
    pass


def find_node(custom: str = "") -> str:
    if custom and Path(custom).exists():
        return custom
    p = shutil.which("node")
    if p:
        return p
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
            cand = Path(base) / "nodejs" / "node.exe"
            if cand.exists():
                return str(cand)
    raise RenderError("Node.js 를 찾을 수 없습니다. setup_windows.bat 을 실행하거나 https://nodejs.org 에서 LTS 를 설치하세요.")


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

    def to_job(self) -> dict:
        d = {"kind": self.kind, "composition": self.composition, "props": str(self.props_path),
             "output": str(self.output), "scale": self.scale, "crf": self.crf, "x264Preset": self.x264_preset,
             "encoder": self.encoder, "frame": int(self.frame)}
        if self.frames:
            d["frames"] = [{"frame": int(f), "output": str(o)} for f, o in self.frames]
        return d


@dataclass
class RenderJob:
    public_dir: Path
    bundle_dir: Path
    links: list[tuple[Path, str]] = field(default_factory=list)
    items: list[RenderItem] = field(default_factory=list)
    browser_executable: str = ""
    gl: str = ""
    concurrency: int = 0
    reuse_bundle: bool = False


def run_render(job: RenderJob, job_file: Path, *, node: str, log: LogFn = noop_log,
               progress: ProgressFn = noop_progress, cancel: Optional[CancelToken] = None) -> None:
    ensure_renderer_installed()
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

    code, tail = run_process([node, str(RENDERER_DIR / "scripts" / "render.mjs"), str(job_file)], cwd=RENDERER_DIR,
                             on_line=on_line, cancel=cancel)
    if code != 0:
        raise RenderError("Remotion 렌더 실패\n" + (state["err"] or tail)[-3000:])
    progress(1.0)


def open_studio(public_dir: Path, props_path: Path, node: str, composition: str = "LongForm") -> subprocess.Popen:
    """Remotion Studio(브라우저 미리보기)를 연다."""
    ensure_renderer_installed()
    cli = RENDERER_DIR / "node_modules" / "@remotion" / "cli" / "remotion-cli.js"
    args = [node, str(cli), "studio", "src/index.ts", f"--public-dir={public_dir}", f"--props={props_path}"]
    return subprocess.Popen(args, cwd=RENDERER_DIR)
