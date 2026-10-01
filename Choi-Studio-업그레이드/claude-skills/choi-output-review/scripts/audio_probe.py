"""완성 믹스에서 목소리를 빼 음악+효과음만 남기고, 말하는 동안/쉬는 동안의 레벨과 출렁임을 잰다(읽기 전용).

    python audio_probe.py "projects/<job>"          # 결과는 stdout JSON

근거: studio/media/mix.py 는 보이스를 그대로 더하고 전체에 -6dB 여유를 곱해 work/mix_N.wav 로 쓴다.
따라서 mix / 0.5012 - voice = 음악 + 효과음(샘플 단위로 정확).
"""
from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np

HEAD = 10 ** (-6 / 20)   # mix.py headroom
HOP = 480                # 10ms @ 48kHz
SPEECH_DB = -42.0        # mix.voice_activity 와 같은 문턱


def probe(mix_path: Path, voice_path: Path, label: str) -> dict:
    with wave.open(str(mix_path), "rb") as m, wave.open(str(voice_path), "rb") as v:
        sr = m.getframerate()
        n = min(m.getnframes(), v.getnframes())
        vch = v.getnchannels()
        v_db: list[np.ndarray] = []
        r_db: list[np.ndarray] = []
        pos = 0
        while pos < n:
            k = min(sr * 30, n - pos)
            a = np.frombuffer(m.readframes(k), np.int16).astype(np.float32).reshape(-1, 2) / 32768 / HEAD
            b = np.frombuffer(v.readframes(k), np.int16).astype(np.float32).reshape(-1, vch) / 32768
            b = np.repeat(b, 2, axis=1) if vch == 1 else b[:, :2]
            res = (a - b).mean(axis=1)
            vo = b.mean(axis=1)
            q = len(vo) // HOP
            if q:
                v_db.append(10 * np.log10((vo[: q * HOP].reshape(q, HOP) ** 2).mean(axis=1) + 1e-12))
                r_db.append(10 * np.log10((res[: q * HOP].reshape(q, HOP) ** 2).mean(axis=1) + 1e-12))
            pos += k
    vd, rd = np.concatenate(v_db), np.concatenate(r_db)
    speech = vd > SPEECH_DB
    sec = rd[: len(rd) // 100 * 100].reshape(-1, 100)
    lv = 10 * np.log10((10 ** (sec / 10)).mean(axis=1) + 1e-12)      # 1초 창 음악 레벨
    d = np.abs(np.diff(lv))
    blk = lv[: len(lv) // 30 * 30].reshape(-1, 30)
    under = float(np.median(rd[speech]))
    pause = float(np.median(rd[~speech])) if (~speech).any() else under
    voice = float(np.median(vd[speech]))
    return {
        "label": label,
        "minutes": round(len(vd) / 6000, 2),
        "speech_ratio": round(float(speech.mean()), 3),
        "voice_minus_music_under_speech_db": round(voice - under, 1),
        "pause_swell_db": round(pause - under, 1),
        "music_jumps_over_3db_per_min": round(float((d > 3).sum() / (len(lv) / 60)), 1),
        "music_jumps_over_6db_per_min": round(float((d > 6).sum() / (len(lv) / 60)), 1),
        "music_level_p10_p50_p90_db": [round(float(np.percentile(lv, p)), 1) for p in (10, 50, 90)],
        "music_db_per_30s": [round(float(np.median(x)), 1) for x in blk],
    }


def main(job: str) -> None:
    root = Path(job)
    out = []
    pairs = [("long", root / "work" / "mix_0.wav",
              next((p for p in (root / "media" / "long_voice_full.wav", root / "media" / "long_voice.wav") if p.exists()),
                   root / "media" / "long_voice.wav"))]
    for i in range(1, 4):
        pairs.append((f"short_{i}", root / "work" / f"mix_{i}.wav", root / "media" / f"short_{i}_voice.wav"))
    for label, mix_path, voice_path in pairs:
        if mix_path.exists() and voice_path.exists():
            out.append(probe(mix_path, voice_path, label))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
