"""다운로드한 스톡 소재를 렌더용으로 정리: 영상은 CFR/1080p/무음으로 필요한 길이만, 사진은 적당한 크기 JPG."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..media.ffmpeg import FFmpeg
from ..util import CancelToken, LogFn, noop_log


def prepare_video(ff: FFmpeg, src: Path, dst: Path, *, need: float, fps: int = 30, width: int = 1920,
                  height: int = 1080, src_duration: float = 0.0, log: LogFn = noop_log,
                  cancel: Optional[CancelToken] = None) -> Path:
    """필요 길이(need)+여유 만큼. 원본이 짧으면 반복, 길면 앞쪽 1/3 지점부터(도입부 흔들림 회피)."""
    need = max(1.0, need + 0.6)
    start = 0.0
    loop: list[str] = []
    if src_duration and src_duration > need + 1.0:
        start = min(src_duration - need - 0.2, max(0.0, (src_duration - need) / 3))
    elif src_duration and src_duration < need:
        loop = ["-stream_loop", "-1"]
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
          f"crop={width}:{height},fps={fps},format=yuv420p")
    args = loop + ["-ss", f"{start:.3f}", "-i", str(src), "-t", f"{need:.3f}", "-an", "-vf", vf] + \
        ff.video_codec_args("final", gop=15) + ["-movflags", "+faststart", str(dst)]
    ff.run(args, duration=need, log=log, cancel=cancel, what="스톡 영상 정리")
    return dst


def prepare_photo(src: Path, dst: Path, max_w: int = 2400) -> Path:
    from PIL import Image
    im = Image.open(src).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)), Image.LANCZOS)
    im.save(dst, quality=90)
    return dst
