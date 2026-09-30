"""원본 영상 여러 개 — 다시점(동시 촬영) 묶기 · 가상 타임라인 · 앵글 고르기.

원본을 여러 개 넣으면:
1) **동시 촬영인지 가린다.** 소리 에너지 곡선(10ms)을 서로 교차상관해 한 시점에서 뚜렷하게 겹치면 같은 순간을 다른
   각도에서 찍은 것(다시점)으로 묶고, 시간 차이(오프셋)를 잰다. 겹치지 않으면 따로 찍은 것(이어 찍기·다시 찍기)이다.
2) **가상 타임라인.** 묶음(동시 촬영 1개 이상)을 입력 순서대로 2초 무음을 사이에 두고 잇는다. 묶음 안에서는 목소리가
   가장 깨끗한 카메라(말소리 대 잡음 비)의 소리를 쓰고, 그 카메라의 영상 시각이 묶음 시각이다. 이후 단계(음성 인식·
   대본 맞추기·테이크 고르기·컷)는 원본이 하나일 때와 똑같이 이 타임라인에서 돈다 — 따로 찍은 파일에서 같은 문장을
   다시 말했다면 테이크 고르기가 더 또렷하고 잘 나온 쪽을 고른다(화면 품질도 반영).
3) **앵글 고르기.** 남길 구간마다 그 순간을 담은 카메라들의 화면 품질(얼굴이 보이는가 · 초점 · 노출 · 정면을 보는가 ·
   얼굴 크기)을 비교해 가장 잘 나온 앵글을 쓴다. 점프컷 자리에서 앵글을 바꿔 컷을 가리고, 한 앵글이 너무 오래
   이어지면 비슷하게 좋은 다른 앵글로 교차한다. 바꾼 뒤 최소 유지 시간이 있어 앵글이 깜빡이지 않는다.
원본이 하나면 이 모듈은 '카메라 1개 · 묶음 1개'로 동작한다(앵글 고르기 없음 · 테이크 고르기에는 화면 품질이
조금(±6%) 반영된다 — 고개를 돌렸거나 초점이 나간 테이크보다 잘 나온 테이크).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from ..models import Span
from ..util import CancelToken, LogFn, noop_log

GAP = 2.0          # 따로 찍은 묶음 사이 무음(초) — 발화·keep 이 묶음을 넘지 않게
RATE = 8000        # 싱크 분석 샘플레이트
HOP = 0.01         # 에너지 곡선 간격(초)
# 동시 촬영 판정 — 전체 상관만 보면 같은 대본을 비슷한 속도로 따로 찍은 두 테이크도 상관 0.4 · 두드러짐 8 까지
# 나온다(tests/test_sources.py). 그래서 '어디서나 같은 시간 차이인가'를 본다: 겹친 구간을 15초 창으로 나눠
# 창마다 ±1초 안에서 다시 맞춰 보면, 동시 촬영은 거의 모든 창이 같은 차이(±50ms)에서 맞고, 따로 찍은 테이크는
# 말 속도가 조금씩 달라 차이가 흘러간다.
WIN = 15.0               # 일관성 창(초)
MIN_CONSIST = 0.7        # 같은 차이에서 맞아야 하는 창 비율


# ---------------------------------------------------------------------------
# 자료 구조
# ---------------------------------------------------------------------------

@dataclass
class Cam:
    idx: int                  # 입력 순서(0 = 첫 영상)
    path: str
    duration: float           # 영상 길이(영상 시각 = 프록시 시각)
    offset: float = 0.0       # 묶음 시각 t → 이 카메라 영상 시각 t + offset
    snr: float = 0.0          # 말소리 대 잡음(dB) — 묶음의 목소리를 고를 때
    corr: float = 1.0         # 기준 카메라와의 소리 상관(동시 촬영 확신도)

    @property
    def proxy(self) -> str:
        return "media/proxy.mp4" if self.idx == 0 else f"media/proxy_{self.idx + 1}.mp4"

    def lo(self) -> float:
        """묶음 시각으로 이 카메라가 담은 구간의 시작."""
        return max(0.0, -self.offset)

    def hi(self, group_dur: float) -> float:
        return min(group_dur, self.duration - self.offset)


@dataclass
class Group:
    cams: list[Cam]           # cams[0] = 목소리를 쓰는 카메라(묶음 시각의 기준, offset 0)
    start: float = 0.0        # 가상 타임라인에서 시작
    duration: float = 0.0

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass
class SourceMap:
    groups: list[Group] = field(default_factory=list)

    @property
    def cams(self) -> list[Cam]:
        return [c for g in self.groups for c in g.cams]

    @property
    def single(self) -> bool:
        return len(self.cams) <= 1

    @property
    def multicam(self) -> bool:
        return any(len(g.cams) > 1 for g in self.groups)

    @property
    def total(self) -> float:
        return self.groups[-1].end if self.groups else 0.0

    def cam(self, idx: int) -> Cam:
        return next(c for c in self.cams if c.idx == idx)

    def group_of(self, idx: int) -> Group:
        return next(g for g in self.groups if any(c.idx == idx for c in g.cams))

    def group_at(self, t: float) -> Group:
        for g in self.groups:
            if t < g.end + GAP / 2:
                return g
        return self.groups[-1]

    def to_cam(self, t: float, cam: Cam) -> float:
        """가상 시각 → 카메라 영상 시각(프록시 시각)."""
        g = self.group_of(cam.idx)
        return t - g.start + cam.offset

    def from_cam(self, t: float, cam: Cam) -> float:
        g = self.group_of(cam.idx)
        return t - cam.offset + g.start

    def candidates(self, a: float, b: float, tol: float = 1e-3) -> list[Cam]:
        """[a, b](가상 시각)를 끝까지 담은 카메라들. 없으면 그 묶음의 기준 카메라.
        여유는 반올림 오차만큼 — 카메라 첫 프레임보다 앞에서 시작하는 조각을 주면 클립이 0초로 당겨져 그 조각 내내
        몇 프레임 어긋난다."""
        g = self.group_at((a + b) / 2)
        out = [c for c in g.cams if c.lo() - tol <= a - g.start and b - g.start <= c.hi(g.duration) + tol]
        return out or [g.cams[0]]

    def clamp_keeps(self, keeps: list[Span], fps: float, min_dur: float = 0.1) -> list[Span]:
        """keep 이 묶음 밖(사이 무음)으로 넘치면 잘라 묶음 안에만 남긴다."""
        if self.single:
            return keeps
        out: list[Span] = []
        for k in keeps:
            for g in self.groups:
                a, b = max(k.start, g.start), min(k.end, g.end)
                a = math.ceil(a * fps - 1e-6) / fps
                b = math.floor(b * fps + 1e-6) / fps
                if b - a >= min_dur:
                    out.append(Span(round(a, 6), round(b, 6)))
        return out

    def summary(self) -> str:
        parts = []
        for i, g in enumerate(self.groups, 1):
            names = [Path(c.path).name for c in g.cams]
            if len(g.cams) == 1:
                parts.append(f"묶음 {i}: {names[0]} ({g.duration / 60:.1f}분)")
            else:
                offs = ", ".join(f"{Path(c.path).name} {c.offset:+.2f}s" for c in g.cams[1:])
                parts.append(f"묶음 {i}: 다시점 {len(g.cams)}대 — 목소리 {names[0]} · 싱크 {offs}")
        return " / ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {"groups": [{"start": g.start, "duration": g.duration,
                            "cams": [vars(c).copy() for c in g.cams]} for g in self.groups]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SourceMap":
        return cls([Group([Cam(**c) for c in g["cams"]], g["start"], g["duration"]) for g in d.get("groups", [])])

    @classmethod
    def one(cls, path: str, duration: float) -> "SourceMap":
        return cls([Group([Cam(0, path, duration)], 0.0, duration)])


# ---------------------------------------------------------------------------
# 싱크 분석
# ---------------------------------------------------------------------------

def envelope(x: np.ndarray, rate: int = RATE, hop: float = HOP) -> np.ndarray:
    """로그 에너지 곡선(평균 0 · 분산 1). 마이크·거리가 달라도 말의 리듬은 같다."""
    n = int(rate * hop)
    m = len(x) // n
    if m < 2:
        return np.zeros(2, np.float32)
    e = np.sqrt(np.mean(np.square(x[: m * n].reshape(m, n).astype(np.float32)), axis=1))
    e = np.log1p(e * 1000.0)
    e = e - e.mean()
    return (e / (e.std() + 1e-9)).astype(np.float32)


@dataclass
class Match:
    offset: float     # b 영상 시각 = a 영상 시각 + offset
    corr: float       # 겹친 구간 피어슨 상관
    z: float          # 봉우리 두드러짐
    overlap: float    # 겹친 길이(초)
    consistent: float = 0.0   # 15초 창 중 같은 시간 차이(±50ms)에서 맞은 비율
    windows: int = 0

    @property
    def same(self) -> bool:
        if self.overlap < 8.0 or self.corr < 0.3:
            return False
        if self.windows >= 2:
            return self.consistent >= MIN_CONSIST
        return self.corr >= 0.6 and self.z >= 6.0      # 겹침이 30초 미만: 창이 모자라 엄격하게


def match(a: np.ndarray, b: np.ndarray, hop: float = HOP) -> Match:
    """두 에너지 곡선의 시간 차이. 반환 offset: b 의 시각 = a 의 시각 + offset."""
    if len(a) < 10 or len(b) < 10:
        return Match(0.0, 0.0, 0.0, 0.0)
    n = 1
    while n < len(a) + len(b):
        n *= 2
    c = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
    # c[k] = Σ a[i+k]·b[i] → k>0: a 가 k 만큼 뒤(=b 가 늦게 시작) / 원형 인덱스의 뒤쪽은 음수 k
    lags = np.concatenate([np.arange(0, len(a)), np.arange(-(len(b) - 1), 0)])
    vals = np.concatenate([c[: len(a)], c[n - (len(b) - 1):]])
    # 겹친 길이로 나눠 짧게 겹친 가짜 봉우리를 누르되, 최소 겹침(8초)보다 짧은 쪽은 제외
    ov = np.minimum(len(a), lags + len(b)) - np.maximum(0, lags)
    ok = ov >= int(8.0 / hop)
    if not ok.any():
        ok = ov >= max(10, int(min(len(a), len(b)) * 0.5))
    score = np.where(ok, vals / np.maximum(ov, 1), -np.inf)
    i = int(np.argmax(score))
    k = int(lags[i])
    finite = score[np.isfinite(score)]
    z = float((score[i] - np.median(finite)) / (finite.std() + 1e-9)) if len(finite) > 2 else 0.0
    # 겹친 구간 피어슨
    a0, a1 = max(0, k), min(len(a), k + len(b))
    xa, xb = a[a0:a1], b[a0 - k:a1 - k]
    corr = float(np.corrcoef(xa, xb)[0, 1]) if len(xa) > 10 and xa.std() > 0 and xb.std() > 0 else 0.0
    # 봉우리 포물선 보간(10ms 보다 촘촘하게)
    frac = 0.0
    if 0 < i < len(score) - 1 and np.isfinite(score[i - 1]) and np.isfinite(score[i + 1]) \
            and lags[i - 1] == k - 1 and lags[i + 1] == k + 1:
        y0, y1, y2 = score[i - 1], score[i], score[i + 1]
        den = y0 - 2 * y1 + y2
        if abs(den) > 1e-12:
            frac = float(np.clip(0.5 * (y0 - y2) / den, -0.5, 0.5))
    cons, nwin = _consistency(a, b, k, hop)
    # a[i+k] ≈ b[i] → b 시각 i·hop = a 시각 (i+k)·hop − k·hop → offset = −k·hop
    return Match(offset=round(-(k + frac) * hop, 4), corr=round(corr, 3), z=round(z, 1),
                 overlap=round(float(a1 - a0) * hop, 2), consistent=round(cons, 2), windows=nwin)


def _consistency(a: np.ndarray, b: np.ndarray, k: int, hop: float) -> tuple[float, int]:
    """겹친 구간을 WIN 초 창으로 나눠, 창마다 ±1초 안에서 다시 찾은 시간 차이가 전체 차이 k 와 같은(±50ms) 비율."""
    w = int(WIN / hop)
    r = int(1.0 / hop)
    tol = max(1, int(0.05 / hop))
    a0, a1 = max(0, k), min(len(a), k + len(b))
    ok = n = 0
    for i in range(a0, a1 - w + 1, w):
        xa = a[i:i + w]
        j0, j1 = i - k - r, i - k + w + r
        if j0 < 0 or j1 > len(b) or xa.std() < 1e-6:
            continue
        seg = b[j0:j1]
        c = np.correlate(seg, xa - xa.mean(), mode="valid")          # 2r+1 개(창을 b 위에서 −r..+r 로 밀기)
        csum = np.concatenate([[0.0], np.cumsum(seg)])
        csq = np.concatenate([[0.0], np.cumsum(seg.astype(np.float64) ** 2)])
        m = np.arange(len(c))
        s1, s2 = csum[m + w] - csum[m], csq[m + w] - csq[m]
        sd = np.sqrt(np.maximum(s2 - s1 * s1 / w, 1e-9))
        cc = c / (sd * xa.std() * np.sqrt(w) + 1e-9)
        j = int(np.argmax(cc))
        n += 1
        if abs(j - r) <= tol and cc[j] >= 0.3:
            ok += 1
    return (ok / n if n else 0.0), n


def voice_snr(x: np.ndarray, rate: int = RATE) -> float:
    """말소리 대 잡음(dB): 20ms 음량의 상위 5% − 하위 10%. 클리핑은 크게 감점."""
    n = int(rate * 0.02)
    m = len(x) // n
    if m < 20:
        return 0.0
    rms = np.sqrt(np.mean(np.square(x[: m * n].reshape(m, n).astype(np.float32)), axis=1)) + 1e-7
    db = 20 * np.log10(rms)
    clip = float(np.mean(np.abs(x) > 0.985))
    return round(float(np.percentile(db, 95) - np.percentile(db, 10)) - 400.0 * clip, 2)


def to_video_time(pcm: np.ndarray, av_offset: float, rate: int = RATE) -> np.ndarray:
    """오디오 스트림 → 영상 시각(0 = 첫 영상 프레임)으로 옮긴다(MediaInfo.av_offset)."""
    s = int(round(abs(av_offset) * rate))
    if av_offset > 0:
        return np.concatenate([np.zeros(s, pcm.dtype), pcm])
    return pcm[s:] if s else pcm


def group_sources(pcms: list[np.ndarray], paths: list[str], durations: list[float], *, fps: float,
                  log: LogFn = noop_log, rate: int = RATE) -> SourceMap:
    """영상 시각 PCM(8kHz 모노) 목록 → 묶음·오프셋·목소리 카메라·가상 타임라인."""
    return group_envelopes([envelope(p, rate) for p in pcms], [voice_snr(p, rate) for p in pcms], paths, durations,
                           fps=fps, log=log)


def group_envelopes(envs: list[np.ndarray], snrs: list[float], paths: list[str], durations: list[float], *,
                    fps: float, log: LogFn = noop_log) -> SourceMap:
    """에너지 곡선 · 말소리 대 잡음 → 묶음·오프셋·목소리 카메라·가상 타임라인."""
    n = len(envs)
    pair: dict[tuple[int, int], Match] = {}
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            m = match(envs[i], envs[j])
            pair[(i, j)] = m
            log(f"   싱크 {Path(paths[i]).name} ↔ {Path(paths[j]).name}: 상관 {m.corr:.2f} · 두드러짐 {m.z:.0f}"
                f" · 겹침 {m.overlap:.0f}s · 같은 차이 {m.consistent * 100:.0f}%({m.windows}창)"
                + (f" → 동시 촬영(차이 {m.offset:+.2f}s)" if m.same else " → 따로 찍음"))
            if m.same:
                parent[find(j)] = find(i)
    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(find(i), []).append(i)
    groups: list[Group] = []
    t = 0.0
    for members in sorted(clusters.values(), key=min):
        ref = max(members, key=lambda i: (snrs[i], durations[i]))
        # 기준에서 강한 연결을 따라 오프셋을 누적(BFS)
        offs = {ref: 0.0}
        corr = {ref: 1.0}
        todo = [ref]
        while todo:
            a = todo.pop()
            for b in members:
                if b in offs:
                    continue
                m = pair.get((min(a, b), max(a, b)))
                if m is None or not m.same:
                    continue
                d = m.offset if a < b else -m.offset     # b 시각 = a 시각 + d
                offs[b] = offs[a] + d
                corr[b] = m.corr
                todo.append(b)
        cams = [Cam(i, paths[i], durations[i], round(offs.get(i, 0.0), 4), snrs[i], corr.get(i, 0.0))
                for i in sorted(members, key=lambda i: (i != ref, i))]
        start = math.ceil(t * fps - 1e-6) / fps
        dur = math.floor(durations[ref] * fps + 1e-6) / fps
        groups.append(Group(cams, round(start, 6), round(dur, 6)))
        t = start + dur + GAP
    return SourceMap(groups)


def analyze_sources(ff, paths: list[str], infos: list, *, fps: float, log: LogFn = noop_log,
                    cancel: Optional[CancelToken] = None) -> SourceMap:
    if len(paths) == 1:
        return SourceMap.one(paths[0], infos[0].duration)
    log(f"원본 {len(paths)}개 — 소리로 동시 촬영(다시점)인지, 따로 찍었는지 가립니다")
    envs, snrs = [], []
    for p, info in zip(paths, infos):   # 파일 하나씩 읽어 곡선만 남긴다(1시간 PCM ≈ 115MB 를 모두 들고 있지 않게)
        if cancel:
            cancel.check()
        pcm = ff.read_pcm(p, RATE) if info.has_audio else np.zeros(int(info.duration * RATE), np.float32)
        pcm = to_video_time(pcm, info.av_offset)
        envs.append(envelope(pcm))
        snrs.append(voice_snr(pcm))
        del pcm
    return group_envelopes(envs, snrs, paths, [i.duration for i in infos], fps=fps, log=log)


def master_audio_args(smap: SourceMap, infos: dict[int, Any], dst: str | Path) -> list[str]:
    """가상 타임라인 목소리 원본(무보정 48kHz 스테레오 WAV)을 만드는 ffmpeg 인자.
    묶음마다 목소리 카메라의 소리를 영상 시각으로 옮기고(av_offset) 묶음 길이에 맞춘 뒤, 사이에 무음을 두고 잇는다."""
    args: list[str] = []
    chains: list[str] = []
    labels: list[str] = []
    cursor = 0.0
    for k, g in enumerate(smap.groups):
        cam = g.cams[0]
        args += ["-i", cam.path]
        lead = g.start - cursor
        if lead > 0.001:
            chains.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{lead:.6f}[z{k}]")
            labels.append(f"[z{k}]")
        d = infos[cam.idx].av_offset if infos[cam.idx].has_audio else 0.0
        shift = f"adelay={d * 1000:.1f}:all=1," if d > 0.0005 else (
            f"atrim=start={-d:.4f},asetpts=PTS-STARTPTS," if d < -0.0005 else "")
        # asetpts 먼저: 오디오 스트림이 영상보다 늦게 시작하면 타임스탬프가 av_offset 부터라 atrim(시각 기준)이
        # 그만큼 짧게 잘라, 뒤 묶음 목소리가 영상보다 앞서게 된다
        chains.append(f"[{k}:a:0]asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,{shift}apad,"
                      f"atrim=0:{g.duration:.6f},asetpts=PTS-STARTPTS[g{k}]")
        labels.append(f"[g{k}]")
        cursor = g.end
    graph = ";".join(chains) + ";" + "".join(labels) + f"concat=n={len(labels)}:v=0:a=1[out]"
    return args + ["-filter_complex", graph, "-map", "[out]", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le",
                   str(dst)]


# ---------------------------------------------------------------------------
# 화면 품질 · 앵글 고르기
# ---------------------------------------------------------------------------

class Quality:
    """카메라별 화면 품질 표본(face.py track_faces 의 quality: 카메라 영상 시각 4fps)."""

    def __init__(self, samples: list[dict]):
        s = sorted(samples, key=lambda d: d["t"])
        self.samples = s
        self.t = np.array([d["t"] for d in s], float)
        self.f = np.array([d.get("f", 0.0) for d in s], float)       # 얼굴 확신도(0 = 없음)
        self.sz = np.array([d.get("s", 0.0) for d in s], float)      # 얼굴 높이 / 화면 높이
        self.sh = np.array([d.get("sh", 0.0) for d in s], float)     # 초점(라플라시안 분산의 로그)
        self.lu = np.array([d.get("l", 0.5) for d in s], float)      # 얼굴(없으면 화면) 밝기 0~1
        self.cl = np.array([d.get("c", 0.0) for d in s], float)      # 날아가거나 뭉개진 화소 비율
        self.fr = np.array([d.get("fr", 0.6) for d in s], float)     # 정면 정도 0~1

    def window(self, a: float, b: float) -> Optional[dict[str, float]]:
        if not len(self.t):
            return None
        i0, i1 = np.searchsorted(self.t, a), np.searchsorted(self.t, b, side="right")
        if i1 <= i0:
            j = int(np.clip(np.searchsorted(self.t, (a + b) / 2), 0, len(self.t) - 1))
            i0, i1 = j, j + 1
        f = self.f[i0:i1]
        face = f > 0
        return {"face": float(face.mean()),
                "sharp": float(np.median(self.sh[i0:i1])),
                "expo": float(np.mean(1.0 - np.minimum(1.0, np.abs(self.lu[i0:i1] - 0.52) / 0.36))
                              - 2.0 * np.mean(self.cl[i0:i1])),
                "front": float(self.fr[i0:i1][face].mean()) if face.any() else 0.3,
                "size": float(self.sz[i0:i1][face].mean()) if face.any() else 0.0}


def angle_scores(stats: dict[int, Optional[dict[str, float]]], *, prefer_close: bool = False,
                 top: Optional[float] = None) -> dict[int, float]:
    """같은 순간의 카메라들 → 점수(0~1). 초점은 기준(top: 없으면 이 순간 가장 또렷한 카메라)과 비교한 상대값."""
    ok = {k: v for k, v in stats.items() if v}
    if not ok:
        return {k: 0.5 for k in stats}
    top = max([v["sharp"] for v in ok.values()] + ([top] if top is not None else []))
    out: dict[int, float] = {}
    for k in stats:
        v = stats[k]
        if not v:
            out[k] = 0.2
            continue
        sharp = float(np.clip(1.0 + (v["sharp"] - top) / 1.2, 0.0, 1.0))
        size = min(1.0, v["size"] / 0.38) if prefer_close else 1.0 - min(1.0, abs(v["size"] - 0.3) / 0.3)
        s = 0.32 * v["face"] + 0.24 * sharp + 0.16 * max(0.0, v["expo"]) + 0.14 * v["front"] + 0.14 * size
        out[k] = round(float(s), 4)
    return out


@dataclass
class Piece:
    keep: int         # timemap.keeps 인덱스
    start: float      # 가상 시각
    end: float
    cam: int          # Cam.idx
    score: float = 0.0
    why: str = ""


def choose_angles(keeps: list[Span], smap: SourceMap, quality: dict[int, Quality], *,
                  sentence_starts: Optional[list[float]] = None, prefer_close: bool = False,
                  min_hold: float = 2.5, max_hold: float = 9.0, jump: float = 0.25) -> list[Piece]:
    """남길 구간(가상 시각) → 앵글 조각. 원본이 하나면 keep 마다 카메라 0 한 조각.

    - 구간을 담은 카메라들 중 품질 점수가 가장 높은 앵글.
    - 바꾸는 기준(히스테리시스): 점프컷 자리(원본에서 jump 초 넘게 건너뜀)는 차이가 조금만 나도, 그 밖(문장 경계)은
      분명히 나을 때만. 바꾼 뒤 min_hold 초는 유지 — 단, 얼굴이 사라지는 등 나빠지면 바로 바꾼다.
    - 한 앵글이 max_hold 초 넘게 이어지면 비슷하게 좋은 다른 앵글로 교차(다시점 교차 편집).
    """
    if smap.single or not smap.multicam:
        return [Piece(i, k.start, k.end, smap.group_at((k.start + k.end) / 2).cams[0].idx) for i, k in enumerate(keeps)]
    starts = sorted(sentence_starts or [])
    # 1) 조각: keep, 긴 keep 은 문장 시작에서 나눔(교차할 기회)
    segs: list[tuple[int, float, float, bool]] = []   # (keep, a, b, 점프컷 뒤인가)
    for i, k in enumerate(keeps):
        cut = i > 0 and (abs(k.start - keeps[i - 1].end) > jump      # 숏폼은 순서를 바꾸기도 한다(콜드 오픈)
                         or smap.group_at(k.start) is not smap.group_at(keeps[i - 1].end))
        a = k.start
        inner = [s for s in starts if k.start + min_hold <= s <= k.end - min_hold]
        for s in inner:
            if s - a >= min_hold * 1.4:
                segs.append((i, a, s, cut if a == k.start else False))
                a = s
        segs.append((i, a, k.end, cut if a == k.start else False))
    pieces: list[Piece] = []
    cur: Optional[int] = None
    hold = 0.0
    for keep_i, a, b, cut in segs:
        cands = smap.candidates(a, b)
        stats = {}
        for c in cands:
            q = quality.get(c.idx)
            stats[c.idx] = q.window(smap.to_cam(a, c), smap.to_cam(b, c)) if q else None
        sc = angle_scores(stats, prefer_close=prefer_close)
        best = max(sc, key=lambda k: sc[k])
        pick, why = cur, "유지"
        if cur not in sc:
            pick, why = best, "시작" if cur is None else "다른 묶음"
        elif best != cur:
            gain = sc[best] - sc[cur]
            if sc[cur] < 0.3 and gain > 0.1:
                pick, why = best, "앵글 품질 저하"
            elif hold >= min_hold and gain > (0.02 if cut else 0.12):
                pick, why = best, "점프컷 · 더 잘 나온 앵글" if cut else "더 잘 나온 앵글"
        if pick == cur and len(sc) > 1 and hold >= min_hold and (hold >= max_hold or (cut and hold >= min_hold * 2)):
            alt = max((k for k in sc if k != cur), key=lambda k: sc[k])
            if sc[alt] >= sc[cur] - 0.1 and sc[alt] >= 0.35:
                pick, why = alt, "교차(점프컷 가리기)" if cut else "교차(한 앵글이 길어짐)"
        if pick != cur:
            hold = 0.0
        cur = pick
        hold += b - a
        prev = pieces[-1] if pieces else None
        if prev and prev.keep == keep_i and prev.cam == pick and abs(prev.end - a) < 1e-6:
            prev.end = b
        else:
            pieces.append(Piece(keep_i, a, b, int(pick), round(sc[pick], 3), why))
    return pieces


def angle_summary(pieces: list[Piece], smap: SourceMap) -> str:
    """'A.mp4 62% · B.mp4 38% · 앵글 전환 14번'."""
    tot = sum(p.end - p.start for p in pieces) or 1.0
    by: dict[int, float] = {}
    for p in pieces:
        by[p.cam] = by.get(p.cam, 0.0) + p.end - p.start
    sw = sum(1 for p, q in zip(pieces, pieces[1:]) if p.cam != q.cam)
    return " · ".join(f"{Path(smap.cam(k).path).name} {v / tot * 100:.0f}%" for k, v in sorted(by.items())) \
        + f" · 앵글 전환 {sw}번"


def angle_cut_times(pieces: list[Piece], timemap) -> list[float]:
    """앵글이 바뀌는 편집 시각 — 편집 문법이 이 자리를 새 샷으로 본다(프레이밍 초기화 · 소프트 컷 없음)."""
    out = []
    for p, q in zip(pieces, pieces[1:]):
        if p.cam != q.cam:
            span = timemap.edit_span_of(q.keep)
            out.append(round(span.start + (q.start - timemap.keeps[q.keep].start), 3))
    return out


def clips_for(pieces: list[Piece], timemap, smap: SourceMap) -> list[dict[str, Any]]:
    """앵글 조각 → 렌더 클립(카메라별 프록시 · 프록시 시각)."""
    clips = []
    for p in pieces:
        k = timemap.keeps[p.keep]
        span = timemap.edit_span_of(p.keep)
        cam = smap.cam(p.cam)
        clips.append({"src": cam.proxy, "srcStart": round(max(0.0, smap.to_cam(p.start, cam)), 4),
                      "start": round(span.start + (p.start - k.start), 4), "dur": round(p.end - p.start, 4)})
    return clips


def face_track(pieces: list[Piece], smap: SourceMap, faces: dict[int, list[dict]], step: float = 0.25) -> list[dict]:
    """앵글 조각을 따라 카메라별 얼굴 트랙을 이어 붙인 가상 시각 트랙(remap_track 입력)."""
    out: list[dict] = []
    arrays: dict[int, tuple[np.ndarray, dict[str, np.ndarray]]] = {}   # 카메라마다 한 번만(조각마다 만들면 긴 영상에서 느림)
    for p in pieces:
        cam = smap.cam(p.cam)
        if p.cam not in arrays:
            s = faces.get(p.cam) or []
            arrays[p.cam] = (np.array([d["t"] for d in s]), {k: np.array([d[k] for d in s]) for k in ("x", "y", "s")})
        ts, cols = arrays[p.cam]
        if not len(ts):
            continue
        # 조각 끝 바로 앞까지 — 다음 앵글의 첫 표본과 섞여 얼굴 위치가 미리 움직이지 않게
        for t in list(np.arange(p.start, p.end - 0.002, step)) + [p.end - 0.002]:
            ct = smap.to_cam(float(t), cam)
            out.append({"t": round(float(t), 3), **{k: round(float(np.interp(ct, ts, v)), 4) for k, v in cols.items()}})
    out.sort(key=lambda d: d["t"])
    return out


def visual_scorer(smap: SourceMap, quality: dict[int, Quality]) -> Optional[Callable[[float, float], Optional[float]]]:
    """테이크 고르기용: [a, b](가상 시각)에서 가장 잘 나온 앵글의 점수. 품질 표본이 없으면 None.
    초점은 작업 전체 기준(얼굴이 보이는 표본의 카메라별 중앙값 중 최고)과 비교 — 따로 찍은 파일의 테이크끼리도
    흐린 쪽이 감점된다(같은 순간 카메라끼리만 비교하면 각 테이크가 자기 자신과만 비교된다)."""
    if not quality:
        return None
    meds = [float(np.median(q.sh[q.f > 0])) for q in quality.values() if len(q.t) and (q.f > 0).any()]
    top = max(meds) if meds else None

    def score(a: float, b: float) -> Optional[float]:
        cands = smap.candidates(a, b)
        stats = {c.idx: (quality[c.idx].window(smap.to_cam(a, c), smap.to_cam(b, c)) if c.idx in quality else None)
                 for c in cands}
        if not any(stats.values()):
            return None
        return max(angle_scores(stats, top=top).values())
    return score
