"""음성 인식(faster-whisper, 한국어, 단어 타임스탬프) + Silero VAD 발화 구간."""
from __future__ import annotations

import importlib.util
import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np

from ..models import Word
from ..util import CancelToken, LogFn, ProgressFn, noop_log, noop_progress
from ..paths import MODELS_DIR

# Whisper 모델(약 3GB)은 C 드라이브 사용자 캐시 대신 프로그램 폴더(models\hf)에 — setup/run 배치 파일과 같은 위치
os.environ.setdefault("HF_HOME", str(MODELS_DIR / "hf"))

_DLL_READY = False


def _prepare_windows_cuda(log: LogFn) -> None:
    """pip 로 설치한 nvidia-cublas-cu12 / nvidia-cudnn-cu12 DLL 을 찾을 수 있게 PATH 에 추가.

    CTranslate2 는 LoadLibrary 로 cublas64_12.dll / cudnn*.dll 을 찾기 때문에
    os.add_dll_directory 만으로는 부족한 경우가 있어 PATH 도 함께 수정한다.
    """
    global _DLL_READY
    if _DLL_READY or sys.platform != "win32":
        return
    _DLL_READY = True
    for pkg in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc", "nvidia.cuda_runtime"):
        try:
            spec = importlib.util.find_spec(pkg)
        except (ImportError, ValueError):
            spec = None
        if not spec or not spec.submodule_search_locations:
            continue
        for loc in spec.submodule_search_locations:
            for sub in ("bin", "lib"):
                d = os.path.join(loc, sub)
                if os.path.isdir(d):
                    try:
                        os.add_dll_directory(d)
                    except (OSError, AttributeError):
                        pass
                    os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
                    log(f"CUDA DLL 경로 추가: {d}")


def cuda_available() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:  # noqa: BLE001 - 드라이버 문제 등 어떤 예외든 CPU 로 폴백
        return False


def load_audio_16k(wav_path: str | Path) -> np.ndarray:
    import wave
    with wave.open(str(wav_path), "rb") as w:
        assert w.getframerate() == 16000 and w.getsampwidth() == 2, "16kHz/16bit WAV 가 필요합니다"
        ch = w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data


def speech_regions(audio16k: np.ndarray, *, threshold: float = 0.45, min_silence_ms: int = 250,
                   pad_ms: int = 60) -> list[tuple[float, float]]:
    """Silero VAD(faster-whisper 내장 모델)로 발화 구간 검출. 실패 시 에너지 기반."""
    try:
        from faster_whisper.vad import VadOptions, get_speech_timestamps
        opts = VadOptions(threshold=threshold, min_silence_duration_ms=min_silence_ms,
                          speech_pad_ms=pad_ms, min_speech_duration_ms=120)
        ts = get_speech_timestamps(audio16k, opts, sampling_rate=16000)
        return [(t["start"] / 16000.0, t["end"] / 16000.0) for t in ts]
    except Exception:  # noqa: BLE001
        return energy_regions(audio16k)


def energy_regions(audio: np.ndarray, rate: int = 16000, hop_s: float = 0.02,
                   min_silence_s: float = 0.25) -> list[tuple[float, float]]:
    hop = int(rate * hop_s)
    n = len(audio) // hop
    if n == 0:
        return []
    rms = np.sqrt((audio[: n * hop].reshape(n, hop) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    floor = np.percentile(db, 10)
    thr = max(floor + 12, -50)
    active = db > thr
    regions: list[tuple[float, float]] = []
    start = None
    silent_run = 0
    need = int(min_silence_s / hop_s)
    for i, a in enumerate(active):
        if a:
            if start is None:
                start = i
            silent_run = 0
        elif start is not None:
            silent_run += 1
            if silent_run >= need:
                regions.append((start * hop_s, (i - silent_run + 1) * hop_s))
                start, silent_run = None, 0
    if start is not None:
        regions.append((start * hop_s, n * hop_s))
    return regions


def transcribe(
    wav16k: str | Path,
    *,
    model_name: str = "large-v3",
    device: str = "auto",
    compute_type: str = "auto",
    language: str = "ko",
    hint_terms: Optional[list[str]] = None,
    initial_prompt: str = "",
    duration: float = 0.0,
    log: LogFn = noop_log,
    progress: ProgressFn = noop_progress,
    cancel: Optional[CancelToken] = None,
) -> dict:
    """faster-whisper 로 단어 단위 전사. 반환: {words:[...], segments:[...], info:{...}}"""
    _prepare_windows_cuda(log)
    from faster_whisper import WhisperModel  # 무거운 import 는 지연

    if device == "auto":
        device = "cuda" if cuda_available() else "cpu"
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"
    log(f"Whisper 모델 로드: {model_name} ({device}/{compute_type}) — 첫 실행은 모델 다운로드로 오래 걸립니다")
    t0 = time.time()
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception as e:  # noqa: BLE001
        if device == "cuda":
            log(f"GPU 로드 실패 → CPU 로 전환합니다: {e}")
            device, compute_type = "cpu", "int8"
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
        else:
            raise
    log(f"모델 로드 {time.time() - t0:.1f}s")

    hot = ", ".join(hint_terms or [])[:400]
    prompt = initial_prompt or ("다음은 디자인 이론을 설명하는 한국어 강의입니다. " + (hot[:200] if hot else ""))
    kwargs = dict(
        language=language,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=200),
        condition_on_previous_text=False,   # 반복 환각 방지
        initial_prompt=prompt,
        hallucination_silence_threshold=2.0,
    )
    if hot:
        kwargs["hotwords"] = hot
    try:
        segments, info = model.transcribe(str(wav16k), **kwargs)
    except TypeError:
        kwargs.pop("hotwords", None)
        kwargs.pop("hallucination_silence_threshold", None)
        segments, info = model.transcribe(str(wav16k), **kwargs)

    total = duration or float(getattr(info, "duration", 0.0) or 0.0)
    words: list[dict] = []
    segs: list[dict] = []
    try:
        for seg in segments:
            if cancel:
                cancel.check()
            seg_words = []
            for w in seg.words or []:
                txt = (w.word or "").strip()
                if not txt:
                    continue
                wd = Word(txt, float(w.start), float(w.end), float(getattr(w, "probability", 1.0)))
                seg_words.append(wd.to_dict())
            words.extend(seg_words)
            segs.append({"start": float(seg.start), "end": float(seg.end), "text": seg.text.strip(),
                         "avg_logprob": float(getattr(seg, "avg_logprob", 0.0)),
                         "no_speech_prob": float(getattr(seg, "no_speech_prob", 0.0))})
            if total > 0:
                progress(min(0.999, seg.end / total))
            log(f"  [{seg.start:7.1f}s] {seg.text.strip()[:60]}")
    except RuntimeError as e:
        if device == "cuda" and ("cublas" in str(e).lower() or "cudnn" in str(e).lower()):
            raise RuntimeError(
                "CUDA 라이브러리(cuBLAS/cuDNN)를 찾지 못했습니다. setup_windows.bat 을 다시 실행하거나 "
                "설정에서 Whisper 장치를 'cpu' 로 바꿔주세요.\n원본 오류: " + str(e)) from e
        raise
    progress(1.0)
    return {
        "words": words,
        "segments": segs,
        "info": {"language": getattr(info, "language", language), "duration": total,
                 "model": model_name, "device": device, "compute_type": compute_type},
    }
