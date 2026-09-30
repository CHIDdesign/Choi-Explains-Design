"""음성 트랙 처리: 외부 마이크 싱크, 보이스 정리(EQ/노이즈/컴프/디에서), 2-pass 라우드니스."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import numpy as np

from ..util import CancelToken, LogFn, ProgressFn, noop_log, noop_progress, run_process
from .ffmpeg import FFmpeg, FFmpegError

VOICE_CHAIN = (
    "highpass=f=75,"
    "afftdn=nr=10:nf=-40:tn=1,"            # 약한 광대역 노이즈 제거(과하면 목소리가 뭉개짐)
    "equalizer=f=250:t=q:w=1.2:g=-2,"       # 먹먹함 정리
    "equalizer=f=3500:t=q:w=1.5:g=1.5,"     # 명료도
    "deesser=i=0.35,"
    "acompressor=threshold=-20dB:ratio=3:attack=8:release=120:makeup=2"
)


def voice_chain(denoise_model: Optional[str | Path] = None) -> str:
    """방송용 보이스 체인. RNNoise 모델이 있으면 신경망 잡음 제거(에어컨·컴퓨터 팬·방 울림에 강함).

    하이패스 80Hz → 잡음 제거 → 박스감(200~250Hz) 정리 → 존재감(3~4kHz) → 공기감(10kHz 셸프)
    → 디에서 → 컴프레서 3:1 → (라우드니스는 build_voice_track 에서 2-pass)
    """
    if denoise_model:
        from ..edit.assemble import _escape_filter_path
        dn = f"aresample=48000,arnndn=m={_escape_filter_path(denoise_model)}:mix=0.85,afftdn=nr=4:nf=-45:tn=1,"
    else:
        dn = "afftdn=nr=10:nf=-40:tn=1,"
    return ("highpass=f=80:p=2," + dn +
            "equalizer=f=230:t=q:w=1.1:g=-2.5,"
            "equalizer=f=3400:t=q:w=1.3:g=2,"
            "highshelf=f=9500:g=1.5,"
            "deesser=i=0.4:m=0.5:f=0.5,"
            "acompressor=threshold=-21dB:ratio=3:attack=6:release=90:makeup=2:knee=4")


def estimate_offset(ref: np.ndarray, other: np.ndarray, rate: int, max_shift_s: float = 20.0) -> float:
    """카메라 오디오(ref) 대비 외부 녹음(other)의 시간 오프셋(초).

    반환값 d: other 의 시각 t 는 ref 의 시각 t + d 에 해당한다.
    (d>0 → 외부 녹음이 늦게 시작됨)
    """
    def envelope(x: np.ndarray) -> np.ndarray:
        hop = rate // 100  # 10ms
        n = len(x) // hop
        x = np.abs(x[: n * hop]).reshape(n, hop).mean(axis=1)
        x = np.log1p(x * 1000)
        x = x - x.mean()
        return x / (x.std() + 1e-9)

    a = envelope(ref[: rate * 240])
    b = envelope(other[: rate * 240])
    n = 1
    while n < len(a) + len(b):
        n *= 2
    corr = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
    max_lag = int(max_shift_s * 100)
    lags = np.concatenate([np.arange(0, max_lag + 1), np.arange(-max_lag, 0)])
    vals = np.concatenate([corr[: max_lag + 1], corr[-max_lag:]])
    best = lags[int(np.argmax(vals))]
    return float(best) / 100.0


def build_voice_track(
    ff: FFmpeg,
    video: str | Path,
    dst: str | Path,
    *,
    external_audio: Optional[str | Path] = None,
    duration: float,
    enhance: bool = True,
    denoise_model: Optional[str | Path] = None,
    target_lufs: float = -16.0,
    av_offset: float = 0.0,
    log: LogFn = noop_log,
    progress: ProgressFn = noop_progress,
    cancel: Optional[CancelToken] = None,
) -> dict:
    """영상 길이에 정확히 맞춘 48kHz 스테레오 보이스 WAV 를 만든다.
    av_offset: 원본 안에서 오디오가 첫 영상 프레임보다 늦게 시작한 초(MediaInfo.av_offset) — 이만큼 옮겨 입을 맞춘다.

    외부 녹음이 있으면 카메라 오디오와 교차상관으로 싱크를 맞춰 대체한다.
    """
    dst = Path(dst)
    info: dict = {"external": bool(external_audio), "offset": 0.0}
    src_input = ["-i", str(video)]
    map_audio = "0:a:0"
    pre = ""
    if external_audio:
        log("외부 녹음 싱크 분석 중…")
        ref = ff.read_pcm(video, 8000)
        other = ff.read_pcm(external_audio, 8000)
        off = estimate_offset(ref, other, 8000)
        info["offset"] = off
        log(f"외부 녹음 오프셋: {off:+.2f}s")
        src_input = ["-i", str(external_audio)]
        map_audio = "0:a:0"
        # other(t) == ref(t + off) → ref 타임라인으로 옮기려면 off 만큼 지연/선행
        if off >= 0:
            pre = f"adelay={int(off * 1000)}:all=1,"
        else:
            pre = f"atrim=start={-off:.3f},asetpts=PTS-STARTPTS,"
    elif abs(av_offset) >= 0.005:
        # 원본 안에서 오디오 스트림이 첫 영상 프레임보다 늦게/먼저 시작 → 목소리를 영상 타임라인(프록시 0초)에 맞춘다
        info["av_offset"] = round(av_offset, 4)
        log(f"오디오·영상 시작 차이 {av_offset * 1000:+.0f}ms → 목소리 위치를 맞춥니다")
        if av_offset > 0:
            pre = f"adelay={av_offset * 1000:.1f}:all=1,"
        else:
            pre = f"atrim=start={-av_offset:.4f},asetpts=PTS-STARTPTS,"
    chain = pre + (voice_chain(denoise_model) + "," if enhance else "")
    info["denoise"] = "rnnoise" if (enhance and denoise_model) else ("afftdn" if enhance else "off")
    fit = f"apad,atrim=0:{duration:.3f}"

    # 1-pass: 측정
    measure_filter = f"{chain}{fit},loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json"
    measured: dict = {}
    lines: list[str] = []

    def grab(line: str) -> None:
        lines.append(line)

    args = [ff.ffmpeg, "-hide_banner", "-nostdin", "-v", "info"] + src_input + [
        "-map", map_audio, "-af", measure_filter, "-f", "null", "-"]
    log("라우드니스 측정(1/2)…")
    code, tail = run_process(args, on_line=grab, cancel=cancel)
    if code != 0:
        raise FFmpegError(f"라우드니스 측정 실패\n{tail}")
    blob = "\n".join(lines)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", blob, re.S)
    if m:
        try:
            measured = json.loads(m.group(0))
        except json.JSONDecodeError:
            measured = {}
    progress(0.4)

    if measured:
        ln = (f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:measured_I={measured['input_i']}:"
              f"measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:"
              f"measured_thresh={measured['input_thresh']}:offset={measured.get('target_offset', 0)}:linear=true")
    else:
        ln = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
    final_filter = f"{chain}{fit},{ln},aresample=48000,alimiter=limit=0.93"
    log("보이스 트랙 생성(2/2)…")
    ff.run(src_input + ["-map", map_audio, "-af", final_filter, "-ac", "2", "-ar", "48000",
                        "-c:a", "pcm_s16le", str(dst)],
           duration=duration, cancel=cancel, progress=lambda f: progress(0.4 + 0.6 * f), what="보이스 처리")
    info["measured"] = measured
    return info
