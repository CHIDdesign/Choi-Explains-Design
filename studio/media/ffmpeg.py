"""FFmpeg/FFprobe 래퍼: 탐색, 프로브, 진행률, NVENC 감지, 프레임 파이프."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Optional

import numpy as np

from ..util import CancelToken, LogFn, ProgressFn, noop_log, noop_progress, run_process, _popen_kwargs


class FFmpegError(RuntimeError):
    pass


@dataclass
class MediaInfo:
    path: str
    duration: float
    width: int = 0
    height: int = 0
    fps: float = 30.0
    fps_str: str = "30/1"
    vfr: bool = False
    rotation: int = 0
    has_video: bool = False
    has_audio: bool = False
    audio_rate: int = 48000
    audio_channels: int = 2
    vcodec: str = ""
    pix_fmt: str = ""
    color_transfer: str = ""
    bit_depth: int = 8

    @property
    def is_hdr(self) -> bool:
        return self.color_transfer in ("arib-std-b67", "smpte2084")

    @property
    def display_size(self) -> tuple[int, int]:
        if self.rotation in (90, 270, -90, -270):
            return self.height, self.width
        return self.width, self.height


class FFmpeg:
    def __init__(self, ffmpeg: str = "", ffprobe: str = ""):
        self.ffmpeg = ffmpeg or self._find("ffmpeg")
        self.ffprobe = ffprobe or self._find("ffprobe")
        if not self.ffmpeg:
            raise FFmpegError(
                "ffmpeg 를 찾을 수 없습니다. setup_windows.bat 을 실행하거나 "
                "'winget install Gyan.FFmpeg' 로 설치한 뒤 다시 시도하세요.")
        if not self.ffprobe:
            cand = Path(self.ffmpeg).with_name("ffprobe" + (".exe" if sys.platform == "win32" else ""))
            self.ffprobe = str(cand) if cand.exists() else ""
        if not self.ffprobe:
            raise FFmpegError("ffprobe 를 찾을 수 없습니다 (ffmpeg 와 같은 폴더에 있어야 합니다).")

    @staticmethod
    def _find(name: str) -> str:
        p = shutil.which(name)
        if p:
            return p
        if sys.platform == "win32":
            # winget(Gyan.FFmpeg) 기본 설치 위치 탐색
            local = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
            if local.exists():
                for exe in local.glob(f"Gyan.FFmpeg*/**/bin/{name}.exe"):
                    return str(exe)
            for base in (Path("C:/ffmpeg/bin"), Path("C:/Program Files/ffmpeg/bin")):
                exe = base / f"{name}.exe"
                if exe.exists():
                    return str(exe)
        return ""

    # ------------------------------------------------------------------
    @property
    @lru_cache(maxsize=1)
    def version(self) -> tuple[int, int]:
        try:
            out = subprocess.run([self.ffmpeg, "-hide_banner", "-version"], capture_output=True, text=True,
                                 **_popen_kwargs()).stdout
        except OSError:
            return (0, 0)
        m = re.search(r"ffmpeg version n?(\d+)\.(\d+)", out)
        if m:
            return int(m.group(1)), int(m.group(2))
        # git 빌드(N-12345-...)는 최신으로 간주
        return (99, 0)

    def filter_script_args(self, script_path: str | Path) -> list[str]:
        """긴 filter_complex 를 파일로 전달 (Windows 명령줄 길이 제한 회피)."""
        if self.version >= (7, 0):
            return ["-/filter_complex", str(script_path)]
        return ["-filter_complex_script", str(script_path)]

    def _nvenc_variant(self) -> list[str] | None:
        """동작하는 NVENC 옵션 조합을 찾는다(FFmpeg 9 는 레거시 프리셋/튜닝 일부 제거)."""
        if hasattr(self, "_nvenc_cache"):
            return self._nvenc_cache
        variants = [
            ["-preset", "p6", "-tune", "hq", "-rc", "vbr", "-cq", "{cq}", "-b:v", "0"],
            ["-preset", "p6", "-rc", "vbr", "-cq", "{cq}", "-b:v", "0"],
            ["-preset", "p5", "-cq", "{cq}"],
        ]
        found: list[str] | None = None
        for v in variants:
            opts = [x.replace("{cq}", "19") for x in v]
            try:
                r = subprocess.run(
                    [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                     "color=black:s=256x256:d=0.2", "-c:v", "h264_nvenc"] + opts + ["-f", "null", "-"],
                    capture_output=True, text=True, timeout=30, **_popen_kwargs())
            except (OSError, subprocess.TimeoutExpired):
                break
            if r.returncode == 0:
                found = v
                break
        self._nvenc_cache = found
        return found

    @property
    def nvenc_ok(self) -> bool:
        return self._nvenc_variant() is not None

    def video_codec_args(self, quality: str = "intermediate", gop: int = 15) -> list[str]:
        """중간 파일용 H.264 설정. NVENC 가 있으면 GPU, 없으면 x264."""
        variant = self._nvenc_variant()
        if variant is not None:
            cq = "16" if quality == "intermediate" else "19"
            return ["-c:v", "h264_nvenc"] + [x.replace("{cq}", cq) for x in variant] + \
                ["-g", str(gop), "-bf", "0", "-pix_fmt", "yuv420p"]
        crf = "14" if quality == "intermediate" else "18"
        return ["-c:v", "libx264", "-preset", "fast", "-crf", crf, "-g", str(gop), "-bf", "0",
                "-pix_fmt", "yuv420p"]

    # ------------------------------------------------------------------
    def probe(self, path: str | Path) -> MediaInfo:
        args = [self.ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           **_popen_kwargs())
        if r.returncode != 0:
            raise FFmpegError(f"ffprobe 실패: {path}\n{r.stderr[-800:]}")
        data = json.loads(r.stdout or "{}")
        fmt = data.get("format", {})
        info = MediaInfo(path=str(path), duration=float(fmt.get("duration") or 0.0))
        for st in data.get("streams", []):
            if st.get("codec_type") == "video" and not info.has_video:
                if st.get("disposition", {}).get("attached_pic"):
                    continue
                info.has_video = True
                info.width = int(st.get("width") or 0)
                info.height = int(st.get("height") or 0)
                info.vcodec = st.get("codec_name", "")
                info.pix_fmt = st.get("pix_fmt", "")
                info.color_transfer = st.get("color_transfer", "") or ""
                info.bit_depth = 10 if "10" in info.pix_fmt else 8
                rfr = st.get("r_frame_rate") or "30/1"
                afr = st.get("avg_frame_rate") or rfr
                info.fps = _ratio(afr) or _ratio(rfr) or 30.0
                info.fps_str = afr if _ratio(afr) else rfr
                r_val, a_val = _ratio(rfr), _ratio(afr)
                info.vfr = bool(r_val and a_val and abs(r_val - a_val) > 0.05)
                rot = 0
                tags = st.get("tags", {}) or {}
                if "rotate" in tags:
                    rot = int(float(tags["rotate"]))
                for sd in st.get("side_data_list", []) or []:
                    if "rotation" in sd:
                        rot = int(float(sd["rotation"]))
                info.rotation = rot % 360
                if not info.duration:
                    info.duration = float(st.get("duration") or 0.0)
            elif st.get("codec_type") == "audio" and not info.has_audio:
                info.has_audio = True
                info.audio_rate = int(st.get("sample_rate") or 48000)
                info.audio_channels = int(st.get("channels") or 2)
                if not info.duration:
                    info.duration = float(st.get("duration") or 0.0)
        return info

    # ------------------------------------------------------------------
    def run(
        self,
        args: list[str],
        *,
        duration: float = 0.0,
        progress: ProgressFn = noop_progress,
        log: LogFn = noop_log,
        cancel: Optional[CancelToken] = None,
        what: str = "ffmpeg",
    ) -> None:
        full = [self.ffmpeg, "-hide_banner", "-y", "-nostdin", "-progress", "pipe:1", "-nostats",
                "-loglevel", "error"] + args
        last = [-1.0]

        def on_line(line: str) -> None:
            if line.startswith("out_time_ms=") or line.startswith("out_time_us="):
                try:
                    t = int(line.split("=", 1)[1]) / 1_000_000
                except ValueError:
                    return
                if duration > 0:
                    frac = max(0.0, min(1.0, t / duration))
                    if frac - last[0] >= 0.005:
                        last[0] = frac
                        progress(frac)
            elif line and "=" not in line:
                log(f"[{what}] {line}")

        code, tail = run_process(full, on_line=on_line, cancel=cancel)
        if code != 0:
            raise FFmpegError(f"{what} 실패 (코드 {code})\n{tail}")
        progress(1.0)

    # ------------------------------------------------------------------
    def extract_audio(self, src: str | Path, dst: str | Path, *, rate: int = 16000, mono: bool = True,
                      stream: str = "a:0", cancel: Optional[CancelToken] = None, duration: float = 0.0,
                      progress: ProgressFn = noop_progress) -> None:
        args = ["-i", str(src), "-map", f"0:{stream}", "-vn", "-ac", "1" if mono else "2",
                "-ar", str(rate), "-c:a", "pcm_s16le", str(dst)]
        self.run(args, duration=duration, cancel=cancel, progress=progress, what="오디오 추출")

    def read_pcm(self, src: str | Path, rate: int = 16000) -> np.ndarray:
        """모노 float32 PCM 으로 읽기(짧은 파일/분석용)."""
        r = subprocess.run([self.ffmpeg, "-v", "error", "-nostdin", "-i", str(src), "-ac", "1", "-ar", str(rate),
                            "-f", "f32le", "-"], capture_output=True, **_popen_kwargs())
        if r.returncode != 0:
            raise FFmpegError(r.stderr.decode("utf-8", "replace")[-800:])
        return np.frombuffer(r.stdout, dtype=np.float32).copy()

    def iter_frames(self, src: str | Path, *, fps: float, width: int, info: Optional[MediaInfo] = None,
                    cancel: Optional[CancelToken] = None) -> Iterator[tuple[float, np.ndarray]]:
        """저해상도 BGR 프레임을 (시각, 배열) 로 순회. 얼굴 추적 등 분석용."""
        info = info or self.probe(src)
        dw, dh = info.display_size
        height = int(round(width * dh / max(1, dw) / 2) * 2)
        vf = f"fps={fps},scale={width}:{height}"
        args = [self.ffmpeg, "-v", "error", "-nostdin", "-i", str(src), "-an", "-vf", vf,
                "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **_popen_kwargs())
        if cancel:
            cancel.register(proc)
        frame_bytes = width * height * 3
        i = 0
        try:
            assert proc.stdout is not None
            while True:
                buf = proc.stdout.read(frame_bytes)
                if len(buf) < frame_bytes:
                    break
                yield i / fps, np.frombuffer(buf, np.uint8).reshape(height, width, 3)
                i += 1
        finally:
            proc.kill()
            proc.wait()
            if cancel:
                cancel.unregister(proc)

    def grab_frame(self, src: str | Path, t: float, dst: str | Path, width: int = 1920,
                   extra_vf: str = "") -> None:
        vf = f"scale={width}:-2:flags=lanczos"
        if extra_vf:
            vf = extra_vf + "," + vf
        args = ["-ss", f"{max(0.0, t):.3f}", "-i", str(src), "-frames:v", "1", "-vf", vf, "-q:v", "2", str(dst)]
        self.run(args, what="프레임 추출")


def _ratio(s: str) -> float:
    try:
        if "/" in s:
            a, b = s.split("/", 1)
            b_f = float(b)
            return float(a) / b_f if b_f else 0.0
        return float(s)
    except (ValueError, ZeroDivisionError):
        return 0.0


def hdr_to_sdr_filter() -> str:
    """HLG/PQ(아이폰 HDR 등) → SDR BT.709 톤매핑. zscale(libzimg) 필요."""
    return ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
            "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def pick_output_fps(info: MediaInfo) -> int:
    """출력 프레임레이트: 원본에 가까운 표준값(24/25/30/50/60)."""
    f = info.fps or 30.0
    for std in (23.976, 24, 25, 29.97, 30, 50, 59.94, 60):
        if abs(f - std) < 0.6:
            return int(round(std))
    return 30 if f < 45 else 60
