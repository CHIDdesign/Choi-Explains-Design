"""🎼 음원 입고 게이트(docs/upgrade/04b_사운드_라이브러리_v2.md 5절) — 운영자가 고른 곡을 라이브러리에 넣기 전에 잰다.

곡을 고르는 것은 운영자다(04b 4절). 이 스크립트는 그 곡이 채널의 '말 아래 바닥'으로 쓸 수 있는지만 숫자로 본다:
권리 등급(A·B·C + 증빙) · Content ID · 과압축(LUFS ≤ −13, LRA ≥ 4) · 밀도(초당 온셋) · 템포(56~92 BPM) ·
말 대역(1~4 kHz 에너지 비율) · 엔딩(마지막 온셋 뒤 감쇠 ≥ 2초) · 앞 무음 · 청취 승인.

    python scripts/sound_ingest.py 곡.wav --id felt_kit1_bed --suite felt --role bed --license-class A \
        --proof 증빙.pdf --content-id none --approved-by 운영자 [--write assets/sound_manifest.json]

결과 표를 찍고, 통과하면 매니페스트 v2 항목(JSON)을 출력한다(--write 면 매니페스트의 scores 목록에 더한다).
제3자 음원 파일은 저장소에 넣지 않는다 — 매니페스트에는 받을 주소·권리·측정값만.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LIMITS = {"bed": {"onsets": 2.0, "band": 0.03}, "theme": {"onsets": 3.5, "band": 0.06},
          "reprise": {"onsets": 3.5, "band": 0.06}, "air": {"onsets": 0.5, "band": 0.03}, "tag": {"onsets": 3.5, "band": 0.06}}
TEMPO = {"default": (56.0, 92.0), "brush": (56.0, 96.0)}


def decode_mono(ffmpeg: str, path: Path, sr: int = 22050) -> np.ndarray:
    r = subprocess.run([ffmpeg, "-v", "error", "-nostdin", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                       capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.float32).copy()


def loudness(ffmpeg: str, path: Path) -> tuple[float, float]:
    r = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    tail = r.stderr[-3000:]
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", tail)
    lra = re.findall(r"LRA:\s+(-?[\d.]+) LU", tail)
    return (float(i[-1]) if i else float("nan")), (float(lra[-1]) if lra else float("nan"))


def onset_strength(x: np.ndarray, sr: int, n_fft: int = 2048, hop: int = 512) -> tuple[np.ndarray, float]:
    """기준 검출기: STFT 2048/512 Hann, log1p(100·|S|) 의 양의 차분 합."""
    win = np.hanning(n_fft).astype(np.float32)
    n = 1 + max(0, (len(x) - n_fft) // hop)
    frames = np.lib.stride_tricks.as_strided(x, (n, n_fft), (x.strides[0] * hop, x.strides[0])) * win
    S = np.log1p(100 * np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0, np.diff(S, axis=0)).sum(axis=1)
    return flux, sr / hop


def onsets(flux: np.ndarray, fps: float) -> np.ndarray:
    """국소 최대이면서 앞뒤 0.5초 중앙값의 1.5배 + 0.15σ 초과, 최소 간격 60 ms."""
    k = max(1, int(0.5 * fps))
    sd = float(flux.std())
    out, last = [], -1e9
    for i in range(1, len(flux) - 1):
        if flux[i] < flux[i - 1] or flux[i] < flux[i + 1]:
            continue
        med = float(np.median(flux[max(0, i - k): i + k + 1]))
        if flux[i] > 1.5 * med + 0.15 * sd and (i - last) / fps >= 0.06:
            out.append(i)
            last = i
    return np.array(out) / fps


def tempo(flux: np.ndarray, fps: float) -> float:
    """온셋 강도 자기상관 + 96 BPM 중심 로그 정규 가중, 45~200 BPM."""
    f = flux - flux.mean()
    ac = np.correlate(f, f, mode="full")[len(f) - 1:]
    lags = np.arange(len(ac))
    bpm = np.where(lags > 0, 60.0 * fps / np.maximum(lags, 1), 0)
    ok = (bpm >= 45) & (bpm <= 200)
    w = np.exp(-0.5 * (np.log2(np.maximum(bpm, 1) / 96.0) / 0.9) ** 2)
    score = np.where(ok, ac * w, -np.inf)
    return float(bpm[int(np.argmax(score))]) if ok.any() else 0.0


def band_ratio(x: np.ndarray, sr: int, lo: float = 1000, hi: float = 4000) -> float:
    spec = np.abs(np.fft.rfft(x[: sr * 120])) ** 2
    freqs = np.fft.rfftfreq(len(x[: sr * 120]), 1 / sr)
    tot = float(spec.sum()) or 1.0
    return float(spec[(freqs >= lo) & (freqs < hi)].sum() / tot)


def lead_silence(x: np.ndarray, sr: int, db: float = -50.0) -> float:
    a = np.abs(x)
    idx = np.nonzero(a > 10 ** (db / 20))[0]
    return round(float(idx[0]) / sr, 2) if len(idx) else 0.0


def measure(path: Path, ffmpeg: str = "ffmpeg") -> dict:
    sr = 22050
    x = decode_mono(ffmpeg, path, sr)
    flux, fps = onset_strength(x, sr)
    ons = onsets(flux, fps)
    dur = len(x) / sr
    li, lra = loudness(ffmpeg, path)
    last_on = float(ons[-1]) if len(ons) else 0.0
    return {"duration": round(dur, 2), "lufs_i": li, "lra": lra, "onsets_per_s": round(len(ons) / max(1.0, dur), 3),
            "bpm": round(tempo(flux, fps), 1), "band_1_4k": round(band_ratio(x, sr), 4),
            "lead_silence_s": lead_silence(x, sr), "tail_after_last_onset_s": round(dur - last_on, 2)}


def gate(m: dict, *, role: str, suite: str, license_class: str, proof: str, content_id: str, approved_by: str,
         pulse: bool = True) -> list[tuple[str, bool, str]]:
    lim = LIMITS.get(role, LIMITS["bed"])
    lo, hi = TEMPO.get(suite, TEMPO["default"])
    out = [("권리 등급", license_class in ("A", "B", "C") and bool(proof) and Path(proof).exists(),
            f"class {license_class or '?'} · 증빙 {'있음' if proof and Path(proof).exists() else '없음'}"),
           ("Content ID", content_id == "none" or (license_class == "B" and content_id == "safelisted"), content_id or "?"),
           ("과압축", m["lufs_i"] <= -13.0 and m["lra"] >= 4.0, f"{m['lufs_i']:.1f} LUFS · LRA {m['lra']:.1f}"),
           ("밀도", m["onsets_per_s"] <= lim["onsets"], f"초당 온셋 {m['onsets_per_s']:.2f} (≤ {lim['onsets']})"),
           ("템포", (not pulse) or lo <= m["bpm"] <= hi or lo <= m["bpm"] / 2 <= hi,
            f"{m['bpm']:.0f} BPM ({lo:.0f}~{hi:.0f}, 배수 혼동은 사람이 확인)"),
           ("말 대역", m["band_1_4k"] <= lim["band"], f"1~4 kHz {m['band_1_4k']:.1%} (≤ {lim['band']:.0%})"),
           ("엔딩", role != "theme" or m["tail_after_last_onset_s"] >= 2.0, f"마지막 온셋 뒤 {m['tail_after_last_onset_s']:.1f}초"),
           ("청취 승인", bool(approved_by), approved_by or "없음")]
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file")
    ap.add_argument("--id", required=True)
    ap.add_argument("--suite", choices=["felt", "analog", "brush", "air"], required=True)
    ap.add_argument("--role", choices=list(LIMITS), default="bed")
    ap.add_argument("--kit", default="", help="같은 곡의 판들을 묶는 키트 이름(예: felt_kit1)")
    ap.add_argument("--license-class", default="", choices=["", "A", "B", "C", "D", "X"])
    ap.add_argument("--license-type", default="")
    ap.add_argument("--attribution", default="")
    ap.add_argument("--proof", default="")
    ap.add_argument("--content-id", default="", choices=["", "none", "registered", "safelisted"])
    ap.add_argument("--url", default="", help="받을 주소(매니페스트에 남는다 — 파일은 저장소에 넣지 않는다)")
    ap.add_argument("--approved-by", default="")
    ap.add_argument("--no-pulse", action="store_true", help="박 없는 곡(air·드론)")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--write", default="", help="통과하면 이 매니페스트의 scores 에 더한다")
    a = ap.parse_args(argv)
    m = measure(Path(a.file), a.ffmpeg)
    rows = gate(m, role=a.role, suite=a.suite, license_class=a.license_class, proof=a.proof, content_id=a.content_id,
                approved_by=a.approved_by, pulse=not a.no_pulse)
    w = max(len(r[0]) for r in rows)
    for name, ok, why in rows:
        print(f"{'통과' if ok else '탈락'}  {name:<{w}}  {why}")
    passed = all(ok for _, ok, _ in rows)
    entry = {"id": a.id, "suite": a.suite, "kit": a.kit or a.id.rsplit("_", 1)[0], "role": a.role, "url": a.url,
             "license": {"class": a.license_class, "type": a.license_type, "attribution": a.attribution,
                         "proof": Path(a.proof).name if a.proof else "", "content_id": a.content_id},
             "measure": m, "pulse": not a.no_pulse, "approved_by": a.approved_by, "enabled": passed}
    print(json.dumps(entry, ensure_ascii=False, indent=1))
    if passed and a.write:
        p = Path(a.write)
        man = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        scores = [e for e in man.get("scores", []) if e.get("id") != a.id] + [entry]
        man["scores"] = scores
        p.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"→ {p} 의 scores 에 더함")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
