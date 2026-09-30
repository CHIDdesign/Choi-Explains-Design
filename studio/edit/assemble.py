"""렌더용 중간 파일.

- proxy.mp4 : 원본 전체를 CFR/SDR/출력 해상도 근처로 변환(오디오 없음, 짧은 GOP → Remotion 탐색이 빠름)
- *_voice.wav : 보이스 트랙을 keep 구간대로 잘라 붙인 WAV (샘플 단위 정확)

영상 컷은 Remotion 이 proxy 에서 프레임 단위로 직접 가져오므로 재인코딩 손실/싱크 누적 오차가 없다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..media.ffmpeg import FFmpeg, MediaInfo, hdr_to_sdr_filter
from ..models import Span
from ..util import CancelToken, LogFn, ProgressFn, noop_log, noop_progress


def proxy_height_for(info: MediaInfo, out_height: int) -> int:
    _, src_h = info.display_size
    want = {1080: 1440, 1440: 2160, 2160: 2160}.get(out_height, int(out_height * 1.334))
    h = min(src_h or out_height, want)
    return int(h // 2 * 2)


def _escape_filter_path(p: str | Path) -> str:
    # ffmpeg 필터 인자 안의 Windows 경로: C\:/path 형태, 작은따옴표로 감싼다
    s = str(Path(p).resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return f"'{s}'"


def build_proxy(
    ff: FFmpeg,
    src: str | Path,
    info: MediaInfo,
    dst: str | Path,
    *,
    fps: int,
    height: int,
    lut: Optional[str | Path] = None,
    pre_filters: Optional[list[str]] = None,
    post_filters: Optional[list[str]] = None,
    log: LogFn = noop_log,
    progress: ProgressFn = noop_progress,
    cancel: Optional[CancelToken] = None,
) -> None:
    """pre_filters: LUT 전(디노이즈 등, YUV) / post_filters: LUT 후(샤픈 등)."""
    vf: list[str] = []
    if info.is_hdr:
        log("HDR(HLG/PQ) 영상 감지 → SDR 톤매핑")
        vf.append(hdr_to_sdr_filter())
    vf.append("setpts=PTS-STARTPTS")   # 프록시 0초 = 첫 영상 프레임(목소리도 여기에 맞춤: MediaInfo.av_offset)
    vf.append(f"fps={fps}")
    # 태그 없는 HD 영상을 BT.601 로 잘못 읽지 않도록(색이 살짝 틀어짐) 색 행렬을 명시
    matrix = info.color_space if info.color_space in ("bt709", "bt470bg", "smpte170m", "bt2020nc") else (
        "bt709" if (info.height or 0) >= 700 else "bt601")
    matrix = {"bt470bg": "bt601", "smpte170m": "bt601", "bt2020nc": "bt2020"}.get(matrix, matrix)
    vf.append(f"scale=-2:{height}:flags=lanczos")
    vf += list(pre_filters or [])
    if lut:
        vf.append(f"scale=in_color_matrix={matrix if not info.is_hdr else 'bt709'},format=gbrp")
        vf.append(f"lut3d=file={_escape_filter_path(lut)}:interp=tetrahedral")
        vf.append("scale=out_color_matrix=bt709:out_range=tv")
    vf += list(post_filters or [])
    vf.append("format=yuv420p")
    hw: list[str] = []
    if ff.nvenc_ok and not info.is_hdr:
        hw = ["-hwaccel", "auto"]
    args = hw + ["-i", str(src), "-map", "0:v:0", "-an", "-vf", ",".join(vf)] + \
        ff.video_codec_args("intermediate", gop=15) + \
        ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
         "-movflags", "+faststart", str(dst)]
    ff.run(args, duration=info.duration, progress=progress, log=log, cancel=cancel, what="프록시 생성")


def cut_audio(
    ff: FFmpeg,
    voice_wav: str | Path,
    keeps: list[Span],
    dst: str | Path,
    work_dir: str | Path,
    *,
    fade: float = 0.012,
    log: LogFn = noop_log,
    progress: ProgressFn = noop_progress,
    cancel: Optional[CancelToken] = None,
) -> float:
    """keep 구간대로 음성을 잘라 붙인다. 이음새마다 12ms 페이드로 '틱' 잡음을 막는다."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    n = len(keeps)
    if n == 0:
        raise ValueError("남길 구간이 없습니다")
    lines = [f"[0:a]asplit={n}" + "".join(f"[s{i}]" for i in range(n)) + ";"] if n > 1 else []
    total = 0.0
    for i, k in enumerate(keeps):
        src_label = f"[s{i}]" if n > 1 else "[0:a]"
        d = k.dur
        total += d
        f = min(fade, d / 4)
        lines.append(
            f"{src_label}atrim=start={k.start:.6f}:end={k.end:.6f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={f:.4f},afade=t=out:st={max(0.0, d - f):.4f}:d={f:.4f}[a{i}];")
    lines.append("".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[aout]")
    script = work_dir / (Path(dst).stem + "_filter.txt")
    script.write_text("\n".join(lines), encoding="utf-8")
    args = ["-i", str(voice_wav)] + ff.filter_script_args(script) + \
        ["-map", "[aout]", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(dst)]
    ff.run(args, duration=total, progress=progress, log=log, cancel=cancel, what="오디오 컷")
    return total
