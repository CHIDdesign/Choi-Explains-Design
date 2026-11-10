"""렌더용 중간 파일.

- proxy.mp4 : 원본 전체를 CFR/SDR/출력 해상도 근처로 변환(오디오 없음, 짧은 GOP → Remotion 탐색이 빠름)
- *_voice.wav : 보이스 트랙을 keep 구간대로 잘라 붙인 WAV (샘플 단위 정확)

영상 컷은 Remotion 이 proxy 에서 프레임 단위로 직접 가져오므로 재인코딩 손실/싱크 누적 오차가 없다.
"""
from __future__ import annotations

import numpy as np

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
        vf.append(f"scale=in_color_matrix={matrix if not info.is_hdr else 'bt709'},format=gbrpf32le")
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


class _NotPcm(Exception):
    pass


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if len(x) else 0.0


def _seam_ok(prev_end: int, next_start: int, handle: Optional[np.ndarray], edge_rms: float) -> bool:
    """앞 keep 끝 뒤의 원본(handle)을 다음 keep 머리에 섞어도 되는가. 다음 keep 과 겹치는 간격(같은 소리가 두 번 더해짐),
    원본 밖·사실상 무음(앞 keep 이 계단처럼 끝남), 가장자리보다 +6dB 넘게 큰 핸들(지운 말이 샘)이면 예전 선형 페이드로."""
    if handle is None or abs(next_start - prev_end) < len(handle):
        return False
    return max(1.0, edge_rms * 0.01) <= _rms(handle) <= edge_rms * 2.0


def _cut_wav(src: Path, keeps: list[Span], dst: Path, *, fade: float, progress: ProgressFn,
             cancel: Optional[CancelToken]) -> float:
    """16bit PCM WAV 를 keep 대로 표본 단위로 잘라 붙인다. 이음새는 원본 핸들로 equal-power 크로스페이드 — 앞 keep 은 끝까지
    그대로 두고 그 끝 뒤 원본 × cos 를 다음 keep 머리 × sin 에 더한다(출력 표본 수 불변, 룸톤이 파이지 않음). 원본에서 이어지는
    keep(간격 0)은 그냥 잇고, 첫 시작·마지막 끝·짧은 keep·`_seam_ok` 가 거절한 이음새는 선형 페이드(afade 기본 곡선과 같음).
    원본 끝을 넘는 keep 은 무음으로 채워 길이를 영상과 맞춘다."""
    import wave
    try:
        r = wave.open(str(src), "rb")
    except (wave.Error, EOFError) as e:
        raise _NotPcm(str(e)) from e
    with r:
        ch, width, sr, total_frames = r.getnchannels(), r.getsampwidth(), r.getframerate(), r.getnframes()
        if width != 2 or sr != 48000 or ch != 2:
            raise _NotPcm(f"{width * 8}bit {sr}Hz {ch}ch")
        tmp = dst.with_name(dst.stem + ".part.wav")
        total = 0.0
        spans = [(int(round(k.start * sr)), int(round(k.end * sr))) for k in keeps]
        xf = int(round(fade * sr))
        p = (np.arange(xf, dtype=np.float32) / max(1, xf))[:, None] * (np.pi / 2)
        fade_in, into = True, None     # 이번 keep 머리: 선형 페이드를 거는가 · 섞을 앞 keep 의 핸들
        with wave.open(str(tmp), "wb") as w:
            w.setnchannels(ch)
            w.setsampwidth(2)
            w.setframerate(sr)
            for i, (a, b) in enumerate(spans):
                if cancel and i % 50 == 0:
                    cancel.check()
                n = max(0, b - a)
                total += n / sr
                buf = np.zeros((n, ch), np.float32)
                if a < total_frames and n:
                    r.setpos(max(0, a))
                    got = np.frombuffer(r.readframes(min(n, total_frames - a)), np.int16).reshape(-1, ch)
                    buf[:len(got)] = got
                # 이음새 판정은 표본을 건드리기 전에(가장자리 RMS 는 원본 값으로)
                fade_out, out = True, None
                if i + 1 < len(spans):
                    na, nb = spans[i + 1]
                    if na == b:
                        fade_out = False
                    elif xf > 0 and min(n, nb - na) >= 4 * xf and b + xf <= total_frames:
                        r.setpos(b)
                        handle = np.frombuffer(r.readframes(xf), np.int16).reshape(-1, ch).astype(np.float32)
                        if _seam_ok(b, na, handle, _rms(buf[n - xf:])):
                            fade_out, out = False, handle
                nf = min(int(round(min(fade, (n / sr) / 4) * sr)), n // 2)
                if nf > 0:
                    ramp = np.linspace(0.0, 1.0, nf, dtype=np.float32)[:, None]
                    if fade_in:
                        buf[:nf] *= ramp
                    if fade_out:
                        buf[n - nf:] *= ramp[::-1]
                if into is not None:
                    buf[:xf] = buf[:xf] * np.sin(p) + into * np.cos(p)
                fade_in, into = fade_out, out
                w.writeframes(np.clip(np.round(buf), -32768, 32767).astype("<i2").tobytes())
                progress((i + 1) / len(keeps))
        tmp.replace(dst)
        return total


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
    """keep 구간대로 음성을 잘라 붙인다. 이음새는 12ms 크로스페이드(또는 선형 페이드)로 '틱' 잡음을 막는다.
    보이스 트랙(48kHz 16bit WAV)은 표본을 직접 잘라 붙인다 — ffmpeg asplit 는 컷 수 × 전체 길이만큼 돌아
    컷이 많은 긴 영상에서 몇 분씩 걸렸다(20분 · 400컷 54초 → 1초 미만). 다른 형식이면 ffmpeg 로."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    n = len(keeps)
    if n == 0:
        raise ValueError("남길 구간이 없습니다")
    try:
        return _cut_wav(Path(voice_wav), keeps, Path(dst), fade=fade, progress=progress, cancel=cancel)
    except _NotPcm:
        pass
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
