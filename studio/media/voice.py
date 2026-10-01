"""목소리 분석 → 최소 맞춤 보정 레시피.

예전(v5까지)은 모든 영상에 같은 '방송용 체인'(RNNoise 0.85 + afftdn + 230Hz −2.5dB + 3.4kHz +2dB + 셸프 + 디에서
+ 컴프레서 3:1)을 때려 넣었다 → 원본보다 먹먹하고 눌린 소리(채널 피드백: "이퀄라이저 음성 보정이 너무 먹먹해져").
이제는 색보정처럼 **원본을 먼저 재고, 기준에서 벗어난 만큼의 절반만, 상한 안에서** 고친다. 정상 범위면 아무것도 안 한다.

잰다(analyze_voice): 24kHz 모노 PCM 을 85ms 프레임으로 STFT
  - 잡음 바닥·말소리 레벨·SNR(조용한 프레임 vs 말소리 프레임)
  - 대역별 스펙트럼: 럼블(<80Hz)·저중역(150–300)·몸통(300–1k)·중고역(1–2.5k)·존재감(2.5–5k)·공기(5–10k),
    몸통 대비 상대 레벨을 장시간 평균 음성 스펙트럼(LTASS, Byrne 1994)과 비교 → 대역별 편차(dB)
  - 치찰음: 프레임별 (공기 − 존재감) 의 95퍼센타일
  - 다이내믹: 0.4초 RMS 의 P90 − P10(말소리 프레임)
  - 클리핑 비율
고친다(plan_voice_recipe, 각 항목은 근거가 있을 때만):
  - 하이패스: 럼블이 기준보다 크면 80Hz(2차), 아니면 50Hz(1차, 들리지 않는 초저역만)
  - 잡음 제거: SNR ≥ 38dB 없음 · 28–38 afftdn 약하게 · 18–28 RNNoise 0.45 · <18 RNNoise 0.7 + afftdn
  - EQ: 편차가 ±2.5dB 를 넘는 대역만, 편차의 절반, 상한 ±2dB(저중역 컷 −2.5) — 저역 부스트는 안 한다
  - 디에서: 치찰음이 기준보다 8dB 이상 튈 때만 0.15–0.3
  - 컴프레서: 다이내믹이 11dB 를 넘을 때만 1.5–2:1, 무릎 6dB, 메이크업 0
  - 라우드니스: 측정 후 **선형 게인**(volume) + 룩어헤드 리미터 — loudnorm 의 동적 모드(펌핑·눌림) 를 쓰지 않는다
결과·수치는 work/audio.json 과 편집 리포트에 남는다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

import numpy as np

# 대역(Hz)
BANDS: dict[str, tuple[float, float]] = {
    "rumble": (20, 80), "lowmid": (150, 300), "body": (300, 1000), "lowpres": (1000, 2500),
    "presence": (2500, 5000), "air": (5000, 10000),
}
# LTASS(Byrne et al. 1994, 남녀 합산 1/3 옥타브) 를 대역별 파워 합으로 묶어 '몸통(300–1k)' 대비 상대 레벨(dB)
REF_DELTA: dict[str, float] = {"rumble": -23.2, "lowmid": -3.8, "lowpres": -6.8, "presence": -11.2, "air": -13.4}
REF_SIB = REF_DELTA["air"] - REF_DELTA["presence"]      # 공기 − 존재감 기준(−2.2dB)

DEAD_ZONE = 2.5        # 이 안의 편차는 건드리지 않는다(dB)
HALF = 0.5             # 편차의 절반만 고친다
CAP_BOOST = 2.0        # 부스트 상한(dB)
CAP_CUT = 2.5          # 컷 상한(dB)


@dataclass
class VoiceStats:
    duration: float = 0.0
    speech_ratio: float = 0.0     # 말소리 프레임 비율
    speech_db: float = -30.0      # 말소리 RMS(dBFS, 중앙값)
    noise_db: float = -70.0       # 잡음 바닥(dBFS)
    snr: float = 40.0
    levels: dict[str, float] = field(default_factory=dict)     # 대역 레벨(몸통 대비 dB)
    deviation: dict[str, float] = field(default_factory=dict)  # 기준(LTASS) 대비 편차(dB)
    sibilance: float = 0.0        # 치찰음 초과(dB, 기준 대비)
    dynamics: float = 8.0         # 0.4초 RMS 의 P90 − P10(dB)
    clip_ratio: float = 0.0
    ok: bool = True               # 잴 만큼 소리가 있었나

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("speech_db", "noise_db", "snr", "sibilance", "dynamics"):
            d[k] = round(d[k], 1)
        d["levels"] = {k: round(v, 1) for k, v in self.levels.items()}
        d["deviation"] = {k: round(v, 1) for k, v in self.deviation.items()}
        d["clip_ratio"] = round(self.clip_ratio, 6)
        return d


@dataclass
class VoiceRecipe:
    highpass: float = 50.0        # Hz(0 = 없음)
    highpass_poles: int = 1
    declip: bool = False
    denoise: str = "none"         # none | light | rnnoise | rnnoise+light
    denoise_mix: float = 0.0      # RNNoise 섞는 비율
    denoise_nr: float = 0.0       # afftdn 감쇠(dB)
    noise_floor: float = -60.0    # afftdn nf
    eq: list[tuple[float, float, float]] = field(default_factory=list)   # (Hz, Q, dB)
    air_shelf: float = 0.0        # 9kHz 하이셸프(dB)
    deess: float = 0.0            # deesser i(0 = 없음)
    comp_ratio: float = 0.0       # 0 = 없음
    comp_threshold: float = -20.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["eq"] = [[f, q, round(g, 2)] for f, q, g in self.eq]
        return d

    def is_flat(self) -> bool:
        return (self.denoise == "none" and not self.eq and not self.air_shelf and not self.deess
                and not self.comp_ratio and not self.declip and self.highpass <= 50)

    def summary(self) -> str:
        """사람이 읽는 한 줄: '하이패스 50Hz(초저역만) · 잡음 제거 없음(SNR 41dB) · EQ 250Hz −1.2dB · 컴프레서 없음'."""
        parts = []
        parts.append(f"하이패스 {self.highpass:.0f}Hz" + ("(초저역만)" if self.highpass <= 50 else "(럼블)") if self.highpass
                     else "하이패스 없음")
        if self.declip:
            parts.append("클리핑 복원")
        dn = {"none": "잡음 제거 없음", "light": f"잡음 제거 약하게({self.denoise_nr:.0f}dB)",
              "rnnoise": f"RNNoise {self.denoise_mix:.0%}", "rnnoise+light": f"RNNoise {self.denoise_mix:.0%} + 약한 제거"}
        parts.append(dn.get(self.denoise, self.denoise))
        if self.eq or self.air_shelf:
            eqs = [f"{f / 1000:.1f}kHz {g:+.1f}dB" if f >= 1000 else f"{f:.0f}Hz {g:+.1f}dB" for f, _, g in self.eq]
            if self.air_shelf:
                eqs.append(f"9kHz 셸프 {self.air_shelf:+.1f}dB")
            parts.append("EQ " + " · ".join(eqs))
        else:
            parts.append("EQ 없음")
        parts.append(f"디에서 {self.deess:.2f}" if self.deess else "디에서 없음")
        parts.append(f"컴프레서 {self.comp_ratio:.1f}:1" if self.comp_ratio else "컴프레서 없음")
        return " · ".join(parts)

    def filter(self, denoise_model: Optional[str] = None) -> str:
        """FFmpeg -af 체인(라우드니스 제외). denoise_model: RNNoise 모델 경로(필터용으로 이스케이프된 것)."""
        parts: list[str] = []
        if self.declip:
            parts.append("adeclip")
        if self.highpass:
            parts.append(f"highpass=f={self.highpass:.0f}:p={self.highpass_poles}")
        nf = max(-80.0, min(-20.0, self.noise_floor))
        if self.denoise in ("rnnoise", "rnnoise+light") and denoise_model:
            parts.append(f"aresample=48000,arnndn=m={denoise_model}:mix={self.denoise_mix:.2f}")
            if self.denoise == "rnnoise+light":
                parts.append(f"afftdn=nr={max(2.0, self.denoise_nr):.0f}:nf={nf:.0f}:tn=1")
        elif self.denoise in ("light", "rnnoise", "rnnoise+light"):
            # 모델이 없으면 afftdn 으로(RNNoise 가 없을 때도 과하게 밀지 않는다)
            nr = self.denoise_nr if self.denoise == "light" else max(self.denoise_nr, 6.0 + 6.0 * self.denoise_mix)
            parts.append(f"afftdn=nr={nr:.0f}:nf={nf:.0f}:tn=1")
        for f, q, g in self.eq:
            parts.append(f"equalizer=f={f:.0f}:t=q:w={q:.2f}:g={g:+.2f}")
        if self.air_shelf:
            parts.append(f"highshelf=f=9000:g={self.air_shelf:+.2f}")
        if self.deess:
            parts.append(f"deesser=i={self.deess:.2f}:m=0.5:f=0.5")
        if self.comp_ratio:
            parts.append(f"acompressor=threshold={self.comp_threshold:.0f}dB:ratio={self.comp_ratio:.2f}:attack=10:"
                         f"release=150:knee=6:makeup=1")
        return ",".join(parts)


# ---------------------------------------------------------------------------
# 측정
# ---------------------------------------------------------------------------

def analyze_voice(pcm: np.ndarray, rate: int = 24000, *, frame: int = 2048, hop: int = 1024) -> VoiceStats:
    """모노 float PCM(−1~1) → VoiceStats. 24kHz 권장(공기 대역 10kHz 까지 본다)."""
    x = np.asarray(pcm, dtype=np.float32)
    dur = len(x) / float(rate)
    n = (len(x) - frame) // hop + 1
    st = VoiceStats(duration=round(dur, 2))
    if n < 20:
        st.ok = False
        return st
    st.clip_ratio = float(np.mean(np.abs(x) > 0.985))
    win = np.hanning(frame).astype(np.float32)
    freqs = np.fft.rfftfreq(frame, 1.0 / rate)
    names = list(BANDS)
    M = np.stack([((freqs >= lo) & (freqs < hi)).astype(np.float32) for lo, hi in BANDS.values()], axis=1)
    band_p = np.empty((n, len(names)), np.float32)
    rms_db = np.empty(n, np.float32)
    offs = np.arange(frame)
    CH = 512
    for i0 in range(0, n, CH):
        idx = np.arange(i0, min(n, i0 + CH))
        seg = x[idx[:, None] * hop + offs[None, :]]
        rms_db[idx] = 20 * np.log10(np.sqrt((seg * seg).mean(axis=1)) + 1e-9)
        P = np.abs(np.fft.rfft(seg * win, axis=1)) ** 2
        band_p[idx] = P @ M
    floor = float(np.percentile(rms_db, 5))
    spread = float(np.percentile(rms_db, 95) - floor)      # 조용한 곳과 말소리의 차이(잡음이 많으면 작다)
    if spread < 5.0:
        # 레벨이 거의 일정 — 말소리가 없거나 잡음뿐. 잡음 판정만 남기고 나머지는 기준값
        st.ok = False
        st.noise_db = round(floor, 1)
        return st
    speech = rms_db >= floor + max(6.0, 0.55 * spread)
    noise = rms_db <= floor + max(2.0, 0.25 * spread)
    if speech.sum() < 10:
        st.ok = False
        st.noise_db = round(floor, 1)
        return st
    if noise.sum() < max(5, int(0.02 * n)):
        noise = rms_db <= np.percentile(rms_db, 5)
    st.speech_ratio = float(speech.mean())
    st.speech_db = float(np.median(rms_db[speech]))
    st.noise_db = float(10 * np.log10(np.mean(10 ** (rms_db[noise] / 10)) + 1e-12))
    st.snr = st.speech_db - st.noise_db
    # 대역 레벨(말소리 프레임 평균 파워) — 몸통 대비
    mean_p = band_p[speech].mean(axis=0) + 1e-12
    lvl = 10 * np.log10(mean_p)
    body = lvl[names.index("body")]
    st.levels = {k: float(lvl[i] - body) for i, k in enumerate(names) if k != "body"}
    st.deviation = {k: float(st.levels[k] - REF_DELTA[k]) for k in REF_DELTA}
    # 치찰음: 프레임별 (공기 − 존재감) 의 95퍼센타일
    ai, pi = names.index("air"), names.index("presence")
    per = 10 * np.log10(band_p[speech, ai] + 1e-12) - 10 * np.log10(band_p[speech, pi] + 1e-12)
    st.sibilance = float(np.percentile(per, 95) - REF_SIB)
    # 다이내믹: 0.4초 창 RMS(말소리 프레임만) 의 P90 − P10
    k = max(1, int(round(0.4 * rate / hop)))
    p_lin = 10 ** (rms_db / 10)
    kern = np.ones(k, np.float32) / k
    smooth = 10 * np.log10(np.convolve(p_lin, kern, mode="same") + 1e-12)
    sp = smooth[speech]
    st.dynamics = float(np.percentile(sp, 90) - np.percentile(sp, 10)) if len(sp) > 10 else 8.0
    return st


# ---------------------------------------------------------------------------
# 레시피
# ---------------------------------------------------------------------------

def _half(dev: float, cap: float) -> float:
    return float(np.sign(dev) * min(cap, HALF * abs(dev)))


def plan_voice_recipe(st: VoiceStats) -> VoiceRecipe:
    r = VoiceRecipe()
    if not st.ok:
        r.notes.append("소리가 거의 없어 기본(초저역 하이패스)만")
        return r
    dev = st.deviation
    # 럼블(에어컨·책상 진동·근접 효과)
    if dev.get("rumble", 0) > 6:
        r.highpass, r.highpass_poles = 80.0, 2
        r.notes.append(f"저역 럼블 +{dev['rumble']:.0f}dB → 하이패스 80Hz")
    # 클리핑
    if st.clip_ratio > 1e-4:
        r.declip = True
        r.notes.append(f"클리핑 {st.clip_ratio * 100:.2f}% → 복원")
    # 잡음
    if st.snr >= 38:
        r.notes.append(f"SNR {st.snr:.0f}dB → 잡음 제거 안 함")
    elif st.snr >= 28:
        r.denoise, r.denoise_nr = "light", 5.0
        r.notes.append(f"SNR {st.snr:.0f}dB → 약한 잡음 제거")
    elif st.snr >= 18:
        r.denoise, r.denoise_mix, r.denoise_nr = "rnnoise", 0.45, 6.0
        r.notes.append(f"SNR {st.snr:.0f}dB → RNNoise 45%")
    else:
        r.denoise, r.denoise_mix, r.denoise_nr = "rnnoise+light", 0.7, 5.0
        r.notes.append(f"SNR {st.snr:.0f}dB → RNNoise 70% + 약한 제거")
    r.noise_floor = st.noise_db + 2.0
    # EQ — 편차의 절반, 데드존 밖만, 상한 안에서. 저역은 부스트하지 않는다(먹먹함의 원인)
    lm = dev.get("lowmid", 0)
    if lm > DEAD_ZONE:
        r.eq.append((230.0, 1.0, -min(CAP_CUT, HALF * lm)))
        r.notes.append(f"저중역 +{lm:.0f}dB(먹먹) → 230Hz {r.eq[-1][2]:+.1f}dB")
    lp = dev.get("lowpres", 0)
    if lp > DEAD_ZONE + 1:
        r.eq.append((1500.0, 1.2, -min(1.5, 0.4 * lp)))
        r.notes.append(f"중고역 +{lp:.0f}dB(콧소리) → 1.5kHz {r.eq[-1][2]:+.1f}dB")
    pr = dev.get("presence", 0)
    if pr < -DEAD_ZONE:
        r.eq.append((3500.0, 1.2, min(CAP_BOOST, HALF * -pr)))
        r.notes.append(f"존재감 {pr:.0f}dB(흐림) → 3.5kHz {r.eq[-1][2]:+.1f}dB")
    elif pr > DEAD_ZONE + 1:
        r.eq.append((3500.0, 1.2, -min(1.5, 0.4 * pr)))
        r.notes.append(f"존재감 +{pr:.0f}dB(날카로움) → 3.5kHz {r.eq[-1][2]:+.1f}dB")
    air = dev.get("air", 0)
    if air < -(DEAD_ZONE + 1):
        r.air_shelf = min(1.5, 0.35 * -air)
        r.notes.append(f"공기 {air:.0f}dB → 9kHz 셸프 {r.air_shelf:+.1f}dB")
    # 치찰음
    if st.sibilance > 12:
        r.deess = 0.3
    elif st.sibilance > 8:
        r.deess = 0.15
    if r.deess:
        r.notes.append(f"치찰음 +{st.sibilance:.0f}dB → 디에서 {r.deess:.2f}")
    # 다이내믹(0.4초 RMS 분포) — 넓을 때만 살짝 모은다
    if st.dynamics > 14:
        r.comp_ratio = 2.0
    elif st.dynamics > 11:
        r.comp_ratio = 1.5
    if r.comp_ratio:
        r.comp_threshold = float(max(-40.0, min(-8.0, st.speech_db + 3.0)))
        r.notes.append(f"다이내믹 {st.dynamics:.0f}dB → 컴프레서 {r.comp_ratio:.1f}:1(문턱 {r.comp_threshold:.0f}dB)")
    else:
        r.notes.append(f"다이내믹 {st.dynamics:.0f}dB → 컴프레서 안 함")
    return r


def loudness_gain(measured: dict, target: float, tp: float = -1.5, max_limit: float = 6.0) -> tuple[float, float]:
    """1-pass loudnorm 측정값 → (선형 게인 dB, 리미터가 깎을 최대 dB).
    피크가 tp 를 max_limit 넘게 넘으면 게인을 줄인다(리미터가 과하게 일하지 않게)."""
    try:
        i = float(measured["input_i"])
        peak = float(measured["input_tp"])
    except (KeyError, TypeError, ValueError):
        return 0.0, 0.0
    if not np.isfinite(i) or i < -70:
        return 0.0, 0.0
    gain = target - i
    over = peak + gain - tp
    if over > max_limit:
        gain -= over - max_limit
        over = max_limit
    return round(gain, 2), round(max(0.0, over), 2)
