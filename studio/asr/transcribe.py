"""음성 인식(faster-whisper, 한국어, 단어 타임스탬프) + Silero VAD 발화 구간."""
from __future__ import annotations

import importlib.util
import inspect
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
_MODELS: dict[tuple[str, str, str], object] = {}   # 같은 작업 안에서 모델 재사용(첫 인식 → 편집 검사)


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


def gpu_expected(device: str = "auto", log: LogFn = noop_log) -> bool:
    """남은 시간 예측용: 이 설정으로 음성 인식이 GPU 를 쓸지(모델은 올리지 않음). DLL 경로 준비가 먼저."""
    if device != "auto":
        return device == "cuda"
    _prepare_windows_cuda(log)
    return cuda_available()


def load_audio_16k(wav_path: str | Path) -> np.ndarray:
    """PCM WAV → 16kHz 모노 float32(-1~1). Whisper·VAD 입력.

    faster-whisper 에 파일 경로를 넘기면 PyAV 로 디코딩하는데, PyAV 19 에서 faster-whisper 가 쓰는
    인자(metadata_errors)가 없어져 실패한다. 그래서 FFmpeg 가 만든 WAV 를 여기서 직접 읽어 배열로 넘긴다.
    """
    import wave
    try:
        with wave.open(str(wav_path), "rb") as w:
            rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
            raw = w.readframes(w.getnframes())
    except (wave.Error, EOFError) as e:
        raise ValueError(f"음성 인식용 WAV 를 읽지 못했습니다({wav_path}): {e}") from e
    if width not in (2, 4):
        raise ValueError(f"16/32비트 PCM WAV 가 필요합니다({wav_path}: {width * 8}비트)")
    data = np.frombuffer(raw, dtype=np.int16 if width == 2 else np.int32).astype(np.float32)
    data /= 32768.0 if width == 2 else 2147483648.0
    if ch > 1:
        data = data[: len(data) // ch * ch].reshape(-1, ch).mean(axis=1)
    if rate != 16000 and len(data):
        n = int(round(len(data) * 16000 / rate))
        data = np.interp(np.arange(n) * (rate / 16000), np.arange(len(data)), data).astype(np.float32)
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
    batch_size: int = 8,
    log: LogFn = noop_log,
    progress: ProgressFn = noop_progress,
    cancel: Optional[CancelToken] = None,
) -> dict:
    """faster-whisper 로 단어 단위 전사. 반환: {words:[...], segments:[...], info:{...}}

    batch_size > 1 이면 배치 추론(BatchedInferencePipeline): VAD 로 나눈 30초 조각들을 한 번에 여러 개 디코딩한다 —
    GPU 에서 약 3~4배, CPU 에서도 약 2배 빠르다. 조각마다 같은 프롬프트(추임새 말투)가 들어가므로 추임새·되풀이를 받아
    적는 성질은 오히려 영상 끝까지 고르게 유지된다(순차 모드는 이전 문맥을 끄면 첫 창에만 프롬프트가 들어감).
    GPU 메모리가 모자라면 배치를 반씩 줄이고, 그래도 안 되면 순차로 다시 한다."""
    _prepare_windows_cuda(log)
    from faster_whisper import WhisperModel  # 무거운 import 는 지연

    if device == "auto":
        device = "cuda" if cuda_available() else "cpu"
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"
    model = _MODELS.get((model_name, device, compute_type))
    if model is None:
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
        _MODELS.clear()   # GPU 메모리: 한 번에 하나만
        _MODELS[(model_name, device, compute_type)] = model
        log(f"모델 로드 {time.time() - t0:.1f}s")

    hot = ", ".join(hint_terms or [])[:400]
    # 추임새·되풀이까지 받아 적게 하는 말투의 프롬프트(Whisper 는 프롬프트 문체를 따라 한다) — 그래야 잘라낼 수 있다
    prompt = initial_prompt or ("음, 어… 오늘은, 어, 디자인 이론을 설명하는 한국어 강의입니다. 그러니까, 음, 다시 말하면… "
                                + (hot[:200] if hot else ""))
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
    # 설치된 faster-whisper 가 모르는 옵션은 미리 뺀다(TypeError 를 잡아 재시도하면 다른 원인의 오류까지 가려진다)
    try:
        accepted = set(inspect.signature(model.transcribe).parameters)
    except (TypeError, ValueError):
        accepted = set(kwargs)
    dropped = [k for k in kwargs if k not in accepted]
    for k in dropped:
        kwargs.pop(k)
    if dropped:
        log(f"(이 faster-whisper 버전이 지원하지 않는 옵션 생략: {', '.join(dropped)})")
    audio = load_audio_16k(wav16k)   # 경로 대신 배열 — PyAV 디코딩을 거치지 않는다
    batch = max(1, int(batch_size or 1))
    gpu = gpu_memory() if device == "cuda" else None
    if gpu is not None:
        fitted = batch_for_gpu(batch, model_name, gpu, _tuned_cap(gpu[0]))
        log(f"GPU: {gpu[0]} · 메모리 {gpu[1]:.1f}GB(여유 {gpu[2]:.1f}GB) → 배치 {fitted}"
            + (f"(설정 {batch}에서 줄임 — 넘치면 시스템 메모리로 넘어가 몇 배 느려진다)" if fitted < batch else ""))
        batch = fitted
    t_run = time.time()
    while True:
        try:
            words, segs, info = _run(model, audio, kwargs, batch=batch, duration=duration, log=log,
                                     progress=progress, cancel=cancel)
            break
        except RuntimeError as e:
            low = str(e).lower()
            if device == "cuda" and ("cublas" in low or "cudnn" in low):
                raise RuntimeError(
                    "CUDA 라이브러리(cuBLAS/cuDNN)를 찾지 못했습니다. setup_windows.bat 을 다시 실행하거나 "
                    "설정에서 Whisper 장치를 'cpu' 로 바꿔주세요.\n원본 오류: " + str(e)) from e
            if batch > 1 and "out of memory" in low:
                batch = batch // 2 if batch > 2 else 1
                log(f"(음성 인식 메모리 부족 → 배치 {batch}{'(순차)' if batch == 1 else ''}로 다시)")
                continue
            raise
    total = duration or float(getattr(info, "duration", 0.0) or 0.0)
    took = max(0.1, time.time() - t_run)
    rtf = total / took if total else 0.0
    if total:
        log(f"음성 인식 속도: 실시간의 {rtf:.1f}배({total / 60:.1f}분 음성 → {took / 60:.1f}분, {device} · 배치 {batch})")
    if gpu is not None and total > 120:
        slow = rtf < SLOW_RTF
        cap = max(1, batch // 2) if slow and batch > 1 else (batch if not slow else 1)
        if slow:
            log(f"⚠️ GPU 인데 음성 인식이 실시간의 {rtf:.1f}배로 느립니다 — GPU 메모리가 넘친 것으로 보여 다음 실행부터 배치를 "
                f"{cap}(으)로 줄입니다. 다른 프로그램(게임·브라우저 영상)이 GPU 를 쓰고 있었다면 닫아 주세요")
        _save_tuning(gpu[0], batch, rtf, cap if slow else max(batch, _tuned_cap(gpu[0]) or batch))
    progress(1.0)
    return {
        "words": words,
        "segments": segs,
        "info": {"language": getattr(info, "language", language), "duration": total,
                 "model": model_name, "device": device, "compute_type": compute_type, "batch": batch},
    }


# 🕒 GPU 메모리에 맞는 배치(2026-10-04 실제 작업: 19.6분 음성이 GPU float16 배치 8 로 12.2분 — 실시간보다 느렸다).
# Windows NVIDIA 드라이버(536.40+)는 GPU 메모리가 모자라면 오류 대신 시스템 메모리로 넘겨(Sysmem Fallback) 몇 배 느려진다 —
# 'out of memory' 를 기다려 배치를 줄이던 방식으로는 못 잡는다. 그래서 ① 여유 VRAM 으로 배치를 고르고 ② 실제 속도를 재서
# 느렸으면 그 GPU 의 다음 실행부터 배치를 반으로(user/asr_tuning.json).
VRAM_BATCH = ((10.0, 8), (7.0, 4), (5.5, 2))     # 여유 GB → 배치(large-v3 · float16 · beam 5 기준), 그 아래는 순차
SLOW_RTF = 2.0                                   # 실시간의 2배보다 느리면 GPU 에서 비정상(정상은 10배 이상)


def gpu_memory() -> Optional[tuple[str, float, float]]:
    """(GPU 이름, 전체 GB, 여유 GB) — nvidia-smi 로(없거나 실패하면 None)."""
    import shutil
    exe = shutil.which("nvidia-smi")
    if not exe and sys.platform == "win32":
        cand = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
        exe = str(cand) if cand.exists() else None
    if not exe:
        return None
    try:
        from ..util import run_process
        code, out = run_process([exe, "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"])
    except Exception:  # noqa: BLE001
        return None
    if code != 0:
        return None
    for line in out.strip().splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) >= 3:
            try:
                total, used = float(parts[1]) / 1024, float(parts[2]) / 1024
            except ValueError:
                continue
            return parts[0], round(total, 1), round(max(0.0, total - used), 1)
    return None


def _tuning_file() -> Path:
    from ..paths import USER_DIR
    return USER_DIR / "asr_tuning.json"


def _tuned_cap(gpu: str) -> Optional[int]:
    import json
    try:
        data = json.loads(_tuning_file().read_text(encoding="utf-8"))
        cap = (data.get(gpu) or {}).get("batch_cap")
        return int(cap) if cap else None
    except (OSError, ValueError, TypeError):
        return None


def _save_tuning(gpu: str, batch: int, rtf: float, cap: int) -> None:
    import json
    f = _tuning_file()
    try:
        data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except (OSError, ValueError):
        data = {}
    data[gpu] = {"batch": batch, "rtf": round(rtf, 2), "batch_cap": cap, "at": time.strftime("%Y-%m-%d %H:%M")}
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def batch_for_gpu(want: int, model_name: str, info: Optional[tuple[str, float, float]],
                  cap: Optional[int] = None) -> int:
    """원하는 배치를 이 GPU 의 여유 VRAM·지난 실측(cap)에 맞춘다. large 가 아닌 모델은 메모리를 적게 써 그대로."""
    b = max(1, int(want or 1))
    if info is not None and "large" in model_name:
        free = info[2]
        b = min(b, next((n for gb, n in VRAM_BATCH if free >= gb), 1))
    if cap:
        b = min(b, max(1, cap))
    return b


def _run(model, audio: np.ndarray, kwargs: dict, *, batch: int, duration: float, log: LogFn, progress: ProgressFn,
         cancel: Optional[CancelToken]) -> tuple[list[dict], list[dict], object]:
    """한 번 전사(batch > 1 이면 배치 추론). 결과 단어·구간·info."""
    kw = dict(kwargs)
    pipe_cls = None
    if batch > 1:
        try:
            from faster_whisper import BatchedInferencePipeline as pipe_cls
        except ImportError:   # faster-whisper 1.1 미만: 순차로
            pipe_cls = None
    if pipe_cls is not None:
        runner = pipe_cls(model=model)
        try:
            accepted = set(inspect.signature(runner.transcribe).parameters)
        except (TypeError, ValueError):
            accepted = set(kw)
        kw = {k: v for k, v in kw.items() if k in accepted}
        kw["batch_size"] = batch
        segments, info = runner.transcribe(audio, **kw)
    else:
        segments, info = model.transcribe(audio, **kw)
    total = duration or float(getattr(info, "duration", 0.0) or 0.0)
    rows: list[tuple[dict, list[dict]]] = []
    for seg in segments:
        if cancel:
            cancel.check()
        seg_words = []
        for w in seg.words or []:
            txt = (w.word or "").strip()
            if not txt:
                continue
            seg_words.append(Word(txt, float(w.start), float(w.end), float(getattr(w, "probability", 1.0))).to_dict())
        rows.append(({"start": float(seg.start), "end": float(seg.end), "text": seg.text.strip(),
                      "avg_logprob": float(getattr(seg, "avg_logprob", 0.0)),
                      "no_speech_prob": float(getattr(seg, "no_speech_prob", 0.0))}, seg_words))
        if total > 0:
            progress(min(0.999, seg.end / total))
        log(f"  [{seg.start:7.1f}s] {seg.text.strip()[:60]}")
    # 배치 추론도 조각 순서대로 돌려주지만, 뒤 단계(정렬·되풀이 찾기)는 시간순을 전제로 하므로 구간 단위로 한 번 더 맞춘다
    rows.sort(key=lambda r: r[0]["start"])
    segs = [g for g, _ in rows]
    words = [w for _, ws in rows for w in ws]
    return words, segs, info
