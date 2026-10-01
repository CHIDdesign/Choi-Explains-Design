"""음성 트랙 처리: 외부 마이크 싱크, 원본 A/V 시작 차이 보정, 목소리 분석 → 최소 맞춤 보정(studio/media/voice.py),
선형 라우드니스(측정 게인 + 리미터)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import numpy as np

from ..util import CancelToken, LogFn, ProgressFn, noop_log, noop_progress, run_process
from .ffmpeg import FFmpeg, FFmpegError
from .voice import VoiceRecipe, VoiceStats, analyze_voice, loudness_gain, plan_voice_recipe

def voice_chain(denoise_model: Optional[str | Path] = None, recipe: Optional[VoiceRecipe] = None) -> str:
    """보이스 체인. recipe 가 없으면 '아무것도 안 하는' 기본 레시피(초저역 하이패스만)."""
    esc = None
    if denoise_model:
        from ..edit.assemble import _escape_filter_path
        esc = _escape_filter_path(denoise_model)
    return (recipe or VoiceRecipe()).filter(esc)


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
    # 목소리 분석 → 이 목소리에 필요한 만큼만(레시피). 잴 때는 라우드니스와 무관하니 24kHz 모노로 읽는다
    recipe: Optional[VoiceRecipe] = None
    stats: Optional[VoiceStats] = None
    if enhance:
        log("목소리 분석 중(잡음·스펙트럼·치찰음·다이내믹)…")
        try:
            pcm = ff.read_pcm(external_audio or video, 24000)
            stats = analyze_voice(pcm, 24000)
            del pcm
        except Exception as e:  # noqa: BLE001 - 분석 실패면 아무것도 안 하는 레시피
            log(f"(목소리 분석 실패 → 보정 없이 진행: {e})")
            stats = VoiceStats(ok=False)
        recipe = plan_voice_recipe(stats)
        if recipe.denoise != "none" and not denoise_model:
            recipe.notes.append("RNNoise 모델 없음 → afftdn 으로 대신")
        log(f"🎙 잰 값: 말소리 {stats.speech_db:.0f}dBFS · 잡음 {stats.noise_db:.0f}dBFS · SNR {stats.snr:.0f}dB · "
            + " ".join(f"{k} {v:+.0f}" for k, v in stats.deviation.items()) + f" · 치찰음 {stats.sibilance:+.0f} · "
            f"다이내믹 {stats.dynamics:.0f}dB")
        log("🎙 이 목소리에 맞춘 양: " + recipe.summary())
        info["voice_stats"] = stats.to_dict()
        info["recipe"] = recipe.to_dict()
        info["recipe_summary"] = recipe.summary()
    # 타임스탬프를 0부터로: 오디오가 늦게 시작한 파일은 첫 타임스탬프가 av_offset 이라, 그대로 두면 끝의 atrim(시각
    # 기준)이 영상보다 av_offset 만큼 짧게 자른다
    body = voice_chain(denoise_model, recipe) if enhance else ""
    chain = "asetpts=PTS-STARTPTS," + pre + (body + "," if body else "")
    info["denoise"] = (recipe.denoise if recipe else "off") if enhance else "off"
    if info["denoise"] != "none" and info["denoise"] != "off" and not denoise_model:
        info["denoise"] += "(afftdn)"
    fit = f"apad,atrim=0:{duration:.3f}"

    # 1-pass: 측정(EBU R128 통합 라우드니스·트루 피크)
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

    # 2-pass: 선형 게인 + 룩어헤드 리미터. loudnorm 의 동적 모드(LRA·피크 조건이 안 맞으면 자동 전환)는 말소리를
    # 눌러 먹먹하게 만든다 — 측정한 만큼만 키우고 튀는 피크만 리미터가 잡는다
    gain, limited = loudness_gain(measured, target_lufs) if measured else (0.0, 0.0)
    info["gain_db"] = gain
    info["peak_limited_db"] = limited
    if measured:
        log(f"라우드니스: {float(measured['input_i']):.1f} → {target_lufs:.0f} LUFS(게인 {gain:+.1f}dB"
            + (f", 피크 리미팅 최대 {limited:.1f}dB" if limited > 0.3 else "") + ")")
        ln = f"volume={gain:+.2f}dB,alimiter=limit=0.84:attack=5:release=80:level=false"
    else:
        ln = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=18"
    final_filter = f"{chain}{fit},{ln}"
    log("보이스 트랙 생성(2/2)…")
    ff.run(src_input + ["-map", map_audio, "-af", final_filter, "-ac", "2", "-ar", "48000",
                        "-c:a", "pcm_s16le", str(dst)],
           duration=duration, cancel=cancel, progress=lambda f: progress(0.4 + 0.6 * f), what="보이스 처리")
    info["measured"] = measured
    return info
