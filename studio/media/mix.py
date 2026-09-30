"""최종 오디오 믹스: 보이스 + 배경음악(자동 덕킹) + 효과음 → 2-pass 라우드니스(-14 LUFS, -1 dBTP).

- 보이스: 컷 편집된 WAV(샘플 단위로 영상과 일치) — 기준 트랙, 손대지 않는다.
- 배경음악: 곡을 영상 길이만큼 이어 붙이고(2초 크로스페이드), 목소리가 나오는 동안은 낮추고(덕킹)
  쉬는 곳·인트로·챕터 전환·엔드카드에서는 올린다. 덕킹 곡선은 보이스의 실제 음량(10ms 단위)으로 계산.
- 효과음: 각 파일을 피크 기준으로 맞춘 뒤, '가장 큰 순간(피크)'이 지정 시각에 오도록 놓는다
  (예: whoosh 의 피크 = 컷 지점).
- 결과: 16bit WAV(여유 -6dB) → 최종 인코딩 때 loudnorm 2-pass 로 -14 LUFS 에 맞춘다.

메모리를 아끼려고 60초 단위로 나눠 섞는다(20분 영상도 수백 MB 안에서).
"""
from __future__ import annotations

import json
import re
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from ..util import CancelToken, LogFn, noop_log, run_process
from .ffmpeg import FFmpeg, FFmpegError

SR = 48000
HOP = 480  # 10ms


@dataclass
class SfxCue:
    t: float                  # 효과음의 '피크'가 올 편집 시각(초)
    path: str
    gain_db: float = -12.0    # 피크 정규화(-1 dBFS) 이후 추가 게인
    peak: float = 0.0         # 파일 안에서 피크 위치(초) — 라이브러리 메타
    name: str = ""
    fade_out: float = 0.0     # 너무 긴 효과음은 잘라낸다(초, 0 = 그대로)


@dataclass
class BgmPlan:
    path: str
    lufs: Optional[float] = None      # 곡의 통합 라우드니스(없으면 측정)
    under_db: float = -21.0           # 말하는 동안(최종 마스터에서 약 -33 LUFS = 목소리보다 약 20LU 아래)
    gap_db: float = -9.0              # 말이 쉬는 곳(최종 약 -21 LUFS)
    swell_db: float = -6.0            # 인트로·챕터 카드·엔드카드(최종 약 -18 LUFS)
    swells: list[tuple[float, float]] = field(default_factory=list)
    dips: list[tuple[float, float]] = field(default_factory=list)   # 음악을 비울 구간(핵심 문장 직전 0.8초)
    start_offset: float = 0.0         # 곡의 어디서부터 쓸지(초)
    fade_in: float = 1.5
    fade_out: float = 3.0
    tail: float = 0.0                 # 보이스가 끝난 뒤 이어질 길이(엔드카드 등)
    playlist: list[tuple[str, Optional[float]]] = field(default_factory=list)  # 챕터마다 바꿀 곡들(path, lufs)
    switch_at: list[float] = field(default_factory=list)                         # 곡을 바꿀 시각(챕터 시작)


# ---------------------------------------------------------------------------
# 입출력
# ---------------------------------------------------------------------------

def decode(ff: FFmpeg, path: str | Path, *, start: float = 0.0, duration: Optional[float] = None) -> np.ndarray:
    """오디오 파일 → (N, 2) float32, 48kHz."""
    import subprocess
    from ..util import _popen_kwargs
    args = [ff.ffmpeg, "-v", "error", "-nostdin"]
    if start > 0:
        args += ["-ss", f"{start:.3f}"]
    args += ["-i", str(path)]
    if duration:
        args += ["-t", f"{duration:.3f}"]
    args += ["-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"]
    r = subprocess.run(args, capture_output=True, **_popen_kwargs())
    if r.returncode != 0:
        raise FFmpegError(f"오디오 디코드 실패: {path}\n" + r.stderr.decode("utf-8", "replace")[-400:])
    x = np.frombuffer(r.stdout, np.float32)
    return x[: len(x) // 2 * 2].reshape(-1, 2).copy()


def measure_lufs(ff: FFmpeg, path: str | Path) -> Optional[float]:
    lines: list[str] = []
    code, _ = run_process([ff.ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-vn", "-af",
                           "ebur128=framelog=quiet", "-f", "null", "-"], on_line=lines.append)
    if code != 0:
        return None
    for line in reversed(lines):
        m = re.search(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", line)
        if m:
            v = float(m.group(1))
            return v if v > -70 else None
    return None


def _read_wav_frames(wf: wave.Wave_read, n: int) -> np.ndarray:
    raw = wf.readframes(n)
    ch, sw = wf.getnchannels(), wf.getsampwidth()
    if sw != 2:
        raise ValueError("16bit WAV 만 지원")
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    x = x.reshape(-1, ch)
    return np.repeat(x, 2, axis=1) if ch == 1 else x[:, :2]


# ---------------------------------------------------------------------------
# 덕킹 곡선
# ---------------------------------------------------------------------------

def voice_activity(voice_wav: str | Path, *, threshold_db: float = -42.0, hang: float = 0.5) -> np.ndarray:
    """10ms 단위 보이스 활성(0/1). 짧은 쉼(hang)은 활성으로 메운다."""
    with wave.open(str(voice_wav), "rb") as wf:
        if wf.getframerate() != SR:
            raise ValueError("보이스 WAV 는 48kHz 여야 합니다")
        levels: list[np.ndarray] = []
        while True:
            x = _read_wav_frames(wf, SR * 30)
            if not len(x):
                break
            m = x.mean(axis=1)
            n = len(m) // HOP
            if n:
                blk = m[: n * HOP].reshape(n, HOP)
                levels.append(10 * np.log10(np.mean(blk * blk, axis=1) + 1e-12))
    db = np.concatenate(levels) if levels else np.zeros(0)
    act = (db > threshold_db).astype(np.float32)
    k = int(hang * 100)
    if k > 0 and len(act):
        # 앞뒤로 hang 만큼 넓힘(팽창) → 문장 사이 짧은 쉼에서 음악이 출렁이지 않게
        pad = np.convolve(act, np.ones(2 * k + 1), mode="same")
        act = (pad > 0).astype(np.float32)
    return act


def bgm_gain_curve(act: np.ndarray, plan: BgmPlan, total: float) -> np.ndarray:
    """10ms 단위 배경음악 게인(dB). 내려갈 땐 빠르게(60ms), 올라올 땐 천천히(400ms)."""
    n = int(np.ceil(total * 100)) + 1
    a = np.zeros(n, np.float32)
    a[: min(n, len(act))] = act[:n]
    target = np.where(a > 0.5, plan.under_db, plan.gap_db).astype(np.float32)
    for s, e in plan.swells:
        i0, i1 = max(0, int(s * 100)), min(n, int(e * 100))
        target[i0:i1] = np.maximum(target[i0:i1], plan.swell_db)
    for s, e in plan.dips:
        i0, i1 = max(0, int(s * 100)), min(n, int(e * 100))
        target[i0:i1] = -60.0
    out = np.empty_like(target)
    cur = float(target[0])
    down = 1 - np.exp(-1 / 5.0)    # ≈50ms
    up = 1 - np.exp(-1 / 60.0)     # ≈600ms
    for i, tv in enumerate(target):
        cur += (tv - cur) * (down if tv < cur else up)
        out[i] = cur
    # 페이드 인/아웃
    fi = int(plan.fade_in * 100)
    if fi > 0:
        out[:fi] += 20 * np.log10(np.linspace(0.02, 1, min(fi, n)) + 1e-6)[: len(out[:fi])]
    fo = int(plan.fade_out * 100)
    if fo > 0:
        out[-fo:] += 20 * np.log10(np.linspace(1, 0.001, min(fo, n)) + 1e-6)[-len(out[-fo:]):]
    return out


# ---------------------------------------------------------------------------
# 믹스
# ---------------------------------------------------------------------------

class _BgmSource:
    """배경음악을 60초 조각 단위로 만들어 준다(20분 영상도 곡 몇 개 분량의 메모리만 쓴다).

    곡(들)을 '조각(piece)'으로 이어 붙인다: 조각 = 한 곡을 처음부터 L 샘플, 앞뒤 2초 등전력 크로스페이드.
    챕터가 바뀌는 곳(switch_at)에서는 다음 곡으로 넘어간다.
    """

    def __init__(self, ff: FFmpeg, plan: BgmPlan, n_total: int, xfade: float = 2.0):
        self.ff = ff
        self.xf = int(xfade * SR)
        tracks = plan.playlist or [(plan.path, plan.lufs)]
        cuts = [0] + sorted({int(t * SR) for t in plan.switch_at if 3 * SR < t * SR < n_total - 3 * SR}) + [n_total]
        self.decoded: dict[str, np.ndarray] = {}
        self.pieces: list[tuple[int, int, str]] = []   # (시작 샘플, 길이, 경로)
        for i in range(len(cuts) - 1):
            path, lufs = tracks[i % len(tracks)]
            raw = self._track(path, lufs, plan.start_offset if i == 0 else 0.0)
            if not len(raw):
                continue
            a, b = cuts[i], cuts[i + 1]
            last_seg = i == len(cuts) - 2
            pos = a
            while pos < b:
                want = b - pos + (0 if last_seg else self.xf)
                L = min(len(raw), want)
                self.pieces.append((pos, L, path))
                if pos + L >= b + (0 if last_seg else self.xf) or L < self.xf * 2:
                    break
                pos += L - self.xf
        self._cache: dict[int, np.ndarray] = {}

    def _track(self, path: str, lufs: Optional[float], offset: float) -> np.ndarray:
        key = f"{path}@{offset:.2f}"
        if key not in self.decoded:
            if lufs is None:
                lufs = measure_lufs(self.ff, path)
            raw = decode(self.ff, path, start=offset)
            norm = 10 ** ((-14.0 - (lufs if lufs is not None else -14.0)) / 20)
            self.decoded[key] = (raw * norm).astype(np.float32)
        return self.decoded[key]

    def _piece(self, k: int) -> np.ndarray:
        if k not in self._cache:
            start, L, path = self.pieces[k]
            src = next(v for kk, v in self.decoded.items() if kk.startswith(path + "@"))
            x = src[:L].copy()
            f = min(self.xf, L // 3)
            if k > 0 and f:
                x[:f] *= np.sqrt(np.linspace(0, 1, f, dtype=np.float32))[:, None]
            if k < len(self.pieces) - 1 and f:
                x[-f:] *= np.sqrt(np.linspace(1, 0, f, dtype=np.float32))[:, None]
            self._cache[k] = x
        return self._cache[k]

    def get(self, pos: int, n: int) -> np.ndarray:
        out = np.zeros((n, 2), np.float32)
        for k, (a, L, _) in enumerate(self.pieces):
            if a + L <= pos or a >= pos + n:
                continue
            x = self._piece(k)
            s0, s1 = max(a, pos), min(a + L, pos + n)
            out[s0 - pos:s1 - pos] += x[s0 - a:s1 - a]
        for k in [k for k in self._cache if self.pieces[k][0] + self.pieces[k][1] <= pos]:
            del self._cache[k]
        return out


def mix(ff: FFmpeg, voice_wav: str | Path, dst: str | Path, *, total: float, sfx: list[SfxCue],
        bgm: Optional[BgmPlan], log: LogFn = noop_log, cancel: Optional[CancelToken] = None) -> dict:
    """보이스(길이 기준) + 배경음악 + 효과음 → 16bit 48kHz 스테레오 WAV(여유 -6dB)."""
    dst = Path(dst)
    n_total = int(round(total * SR))
    report: dict = {"sfx": len(sfx), "bgm": Path(bgm.path).name if bgm else ""}
    # 효과음: 파일별 한 번만 디코드 + 피크 정규화(-1 dBFS)
    bank: dict[str, np.ndarray] = {}
    for c in sfx:
        if c.path in bank:
            continue
        try:
            x = decode(ff, c.path)
        except FFmpegError as e:
            log(f"효과음 읽기 실패(건너뜀): {Path(c.path).name} — {e}")
            bank[c.path] = np.zeros((0, 2), np.float32)
            continue
        pk = float(np.abs(x).max()) if len(x) else 0.0
        bank[c.path] = x * (0.89 / pk) if pk > 1e-6 else x
    # 배경음악: 곡마다 -14 LUFS 로 맞춘 뒤 덕킹 곡선(챕터마다 곡 교체 가능)
    track: Optional[_BgmSource] = None
    curve = None
    if bgm:
        try:
            track = _BgmSource(ff, bgm, n_total)
            act = voice_activity(voice_wav)
            curve = bgm_gain_curve(act, bgm, total)
            report["bgm_tracks"] = len({p for _, _, p in track.pieces})
        except (FFmpegError, ValueError) as e:
            log(f"배경음악 준비 실패(음악 없이 진행): {e}")
            track = None
    placed: list[tuple[int, np.ndarray]] = []
    for c in sfx:
        x = bank.get(c.path)
        if x is None or not len(x):
            continue
        pk = max(0, int(round(c.peak * SR)))
        if c.fade_out and len(x) > pk + int(c.fade_out * SR):
            # 긴 꼬리만 자른다: 정점(컷에 맞출 지점)까지는 그대로, 정점 뒤 fade_out 초에 걸쳐 사라지게.
            # (예전엔 앞 fade_out 초만 남기고 그것마저 0 으로 줄여, 라이저가 컷 1초 전에 끝나 버렸다)
            m = int(c.fade_out * SR)
            x = x[:pk + m].copy()
            x[pk:] *= np.linspace(1, 0, m, dtype=np.float32)[:, None] ** 2
        g = 10 ** (c.gain_db / 20)
        start = int(round((c.t - c.peak) * SR))
        if start < 0:
            x = x[-start:]
            start = 0
        placed.append((start, x * g))
    placed.sort(key=lambda p: p[0])

    headroom = 10 ** (-6 / 20)
    chunk = SR * 60
    peak_seen = 0.0
    with wave.open(str(voice_wav), "rb") as vf, wave.open(str(dst), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(SR)
        pos = 0
        while pos < n_total:
            if cancel:
                cancel.check()
            n = min(chunk, n_total - pos)
            v = _read_wav_frames(vf, n)
            buf = np.zeros((n, 2), np.float32)
            buf[: len(v)] += v[:n]
            if track is not None and curve is not None:
                t_idx = (pos + np.arange(n)) / HOP
                gdb = np.interp(t_idx, np.arange(len(curve)), curve)
                buf += track.get(pos, n) * (10 ** (gdb / 20))[:, None].astype(np.float32)
            for s, x in placed:
                if s >= pos + n:
                    break
                e = s + len(x)
                if e <= pos:
                    continue
                a, b = max(s, pos), min(e, pos + n)
                buf[a - pos:b - pos] += x[a - s:b - s]
            buf *= headroom
            peak_seen = max(peak_seen, float(np.abs(buf).max()) if n else 0.0)
            np.clip(buf, -1, 1, out=buf)
            out.writeframes((buf * 32767).astype(np.int16).tobytes())
            pos += n
    report["peak_dbfs"] = round(20 * np.log10(peak_seen + 1e-9), 2)
    return report


# ---------------------------------------------------------------------------
# 최종 인코딩(영상 + 믹스 → -14 LUFS)
# ---------------------------------------------------------------------------

def loudness_args(ff: FFmpeg, wav: str | Path, *, target: float = -14.0, tp: float = -1.0,
                  cancel: Optional[CancelToken] = None) -> str:
    """loudnorm 1-pass 측정 → 2-pass 필터 문자열. **항상 선형**: loudnorm 은 목표 LRA 가 측정 LRA 보다 작거나 게인이
    피크를 넘기면 동적 모드로 바뀌어(펌핑·눌림) 목소리가 먹먹해진다 — LRA 는 측정값 이상으로 두고, 피크가 넘치면
    volume + 룩어헤드 리미터로 간다."""
    lines: list[str] = []
    code, tail = run_process([ff.ffmpeg, "-hide_banner", "-nostdin", "-i", str(wav), "-af",
                              f"loudnorm=I={target}:TP={tp}:LRA=11:print_format=json", "-f", "null", "-"],
                             on_line=lines.append, cancel=cancel)
    if code != 0:
        raise FFmpegError(f"라우드니스 측정 실패\n{tail}")
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", "\n".join(lines), re.S)
    if not m:
        return f"loudnorm=I={target}:TP={tp}:LRA=18"
    d = json.loads(m.group(0))
    try:
        gain = target - float(d["input_i"])
        lra = max(11.0, float(d["input_lra"]) + 1.0)
        peak_after = float(d["input_tp"]) + gain
    except (KeyError, ValueError, TypeError):
        return f"loudnorm=I={target}:TP={tp}:LRA=18"
    if peak_after > tp - 0.2:
        # 선형 게인 + 리미터(넘치는 피크만 잡는다)
        lim = 10 ** (tp / 20)
        return f"volume={gain:+.2f}dB,alimiter=limit={lim:.3f}:attack=5:release=80:level=false,aresample=48000"
    return (f"loudnorm=I={target}:TP={tp}:LRA={lra:.0f}:measured_I={d['input_i']}:measured_TP={d['input_tp']}:"
            f"measured_LRA={d['input_lra']}:measured_thresh={d['input_thresh']}:offset={d.get('target_offset', 0)}:"
            f"linear=true,aresample=48000")


def mux_final(ff: FFmpeg, video: str | Path, mix_wav: str | Path, dst: str | Path, *, target: float = -14.0,
              log: LogFn = noop_log, cancel: Optional[CancelToken] = None) -> None:
    """무음으로 렌더한 영상 + 믹스 → 최종 MP4(영상 스트림은 복사, AAC 320k)."""
    af = loudness_args(ff, mix_wav, target=target, cancel=cancel)
    tmp = Path(dst).with_suffix(".tmp.mp4")
    ff.run(["-i", str(video), "-i", str(mix_wav), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
            "-af", af, "-c:a", "aac", "-b:a", "384k", "-ar", "48000", "-movflags", "+faststart", "-shortest",
            str(tmp)], log=log, cancel=cancel, what="최종 음향 합치기")
    Path(tmp).replace(dst)
