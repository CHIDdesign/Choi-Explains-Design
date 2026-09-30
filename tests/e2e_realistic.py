"""실제 음성 인식으로 편집 정리를 검증(네트워크·모델 필요 — 일반 테스트에는 안 들어감).

gTTS 로 '실수 섞인 녹화'(되풀이·잠깐만요·추임새·긴 무음·같은 문장 두 번)를 만들고, 진짜 faster-whisper 로
인식 → 정렬·단어 정리 → 컷 → 편집 검사까지 돌린 뒤, 결과 목소리를 다시 인식해 정답과 비교한다.

  python tests/e2e_realistic.py --face 얼굴클립.mp4 [--model small] [--work 폴더]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCRIPT = """# 들어가며
안녕하세요. 오늘은 좋은 디자인이 어디에서 시작하는지 이야기해 볼게요.
많은 학생들이 디자인을 시작하면 바로 화면부터 그립니다.
하지만 좋은 디자인은 좋은 질문에서 시작합니다.
# 더블 다이아몬드
디자인 과정에는 더블 다이아몬드라는 유명한 모델이 있습니다.
첫 번째 다이아몬드는 문제를 발견하고 정의하는 단계입니다.
먼저 넓게 펼쳐서 관찰하고, 그 다음에 좁혀서 진짜 문제를 고릅니다.
두 번째 다이아몬드는 해결책을 만들고 전달하는 단계입니다.
# 마무리
결국 문제를 잘 정의하면 해결책은 따라옵니다.
다음 영상에서는 문제를 정의하는 방법을 더 자세히 알아볼게요.
"""
# keep: 남아야 함 / ng: 잘려야 함 / pause: 쉼(초)
TAKES = [
    ("keep", "안녕하세요."), ("pause", 1.0),
    ("ng", "오늘은 좋은 디자인이 어디서 시작하는지"), ("pause", 0.4),
    ("ng", "아 잠깐만요, 다시 할게요."), ("pause", 1.5),
    ("keep", "오늘은 좋은 디자인이 어디에서 시작하는지 이야기해 볼게요."), ("pause", 0.7),
    ("keep", "많은 학생들이 디자인을 시작하면 바로 화면부터 그립니다."), ("pause", 2.5),
    ("ng", "하지만 좋은 디자인은 좋은 질문에서"), ("pause", 0.5), ("ng", "음"), ("pause", 1.2),
    ("keep", "하지만 좋은 디자인은 좋은 질문에서 시작합니다."), ("pause", 0.8),
    ("keep", "디자인 과정에는 더블 다이아몬드라는 유명한 모델이 있습니다."), ("pause", 0.5),
    ("keep", "첫 번째 다이아몬드는 문제를 발견하고 정의하는 단계입니다."), ("pause", 0.6),
    ("ng", "먼저 넓게 펼쳐서 관찰하고, 그 다음에"), ("pause", 0.9),
    ("keep", "먼저 넓게 펼쳐서 관찰하고, 그 다음에 좁혀서 진짜 문제를 고릅니다."), ("pause", 0.6),
    ("ng", "어"), ("pause", 2.0),
    ("keep", "두 번째 다이아몬드는 해결책을 만들고 전달하는 단계입니다."), ("pause", 0.7),
    ("keep", "결국 문제를 잘 정의하면 해결책은 따라옵니다."), ("pause", 1.0),
    ("keep", "다음 영상에서는 문제를 정의하는 방법을 더 자세히 알아볼게요."), ("pause", 1.2),
]


def run(*a):
    subprocess.run([str(x) for x in a], check=True, capture_output=True)


def make(out: Path, face: str) -> tuple[Path, list[dict]]:
    from gtts import gTTS
    out.mkdir(parents=True, exist_ok=True)
    parts, segs, t = [], [], 0.6
    head = out / "p_head.wav"
    run("ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "0.6", head)
    parts.append(head)
    for i, (kind, val) in enumerate(TAKES):
        if kind == "pause":
            f = out / f"p{i}.wav"
            run("ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", str(val), f)
            parts.append(f)
            t += float(val)
            continue
        mp3, wav = out / f"s{i}.mp3", out / f"s{i}.wav"
        if not mp3.exists():
            gTTS(val, lang="ko").save(str(mp3))
        run("ffmpeg", "-y", "-i", mp3, "-af",
            "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
            "silenceremove=start_periods=1:start_threshold=-45dB,areverse,atempo=1.15", "-ar", "48000", "-ac", "1", wav)
        d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                  str(wav)], capture_output=True, text=True).stdout)
        segs.append({"kind": kind, "text": val, "start": round(t, 3), "end": round(t + d, 3)})
        parts.append(wav)
        t += d
    (out / "list.txt").write_text("".join(f"file '{p.name}'\n" for p in parts))
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", out / "list.txt", "-ar", "48000", "-ac", "1", out / "voice_src.wav")
    src = out / "source.mp4"
    run("ffmpeg", "-y", "-stream_loop", "-1", "-i", face, "-i", out / "voice_src.wav", "-map", "0:v", "-map", "1:a",
        "-t", f"{t:.2f}", "-vf", "scale=1280:720,fps=30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "160k", src)
    (out / "truth.json").write_text(json.dumps(segs, ensure_ascii=False, indent=1), encoding="utf-8")
    return src, segs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--face", required=True)
    ap.add_argument("--model", default="small")
    ap.add_argument("--work", default=str(ROOT / "projects" / "_e2e_realistic"))
    args = ap.parse_args()
    work = Path(args.work)
    src, segs = make(work / "media_src", args.face)
    from studio import pipeline as pl
    from studio.asr.transcribe import load_audio_16k, transcribe
    from studio.settings import Settings
    from studio.text.takes import ntok
    settings = Settings()
    settings.anthropic_api_key = ""
    settings.projects_dir = str(work)
    settings.whisper_model, settings.whisper_device, settings.whisper_compute = args.model, "cpu", "int8"
    settings.download_sounds = False
    spec = pl.JobSpec(video=str(src), topic="좋은 디자인은 질문에서 시작한다", script=SCRIPT, shorts_count=1,
                      use_claude=False, fetch_broll=False, fetch_stock=False, thumbnails=False, short_max_sec=40)
    job = work / "job"
    p = pl.Pipeline(spec, settings, job, log=lambda m: print(m, flush=True))
    for fn in (p.stage_probe, p.stage_audio, p.stage_asr, p.stage_align, p.stage_face, p.stage_grade,
               p.stage_director, p.stage_proxy, p.stage_verify):
        print(f"━━ {fn.__name__}", flush=True)
        fn()
    # 결과 목소리를 다시 받아 적어 정답과 비교
    out16 = job / "work" / "final16k.wav"
    p.ff.extract_audio(job / "media" / "long_voice.wav", out16, rate=16000, mono=True)
    res = transcribe(out16, model_name=args.model, device="cpu", compute_type="int8")
    final = ntok(" ".join(w["text"] for w in res["words"]))
    print("\n결과 전사:", " ".join(w["text"] for w in res["words"]))
    from rapidfuzz import fuzz
    ok = True
    for s in segs:
        present = fuzz.partial_ratio(ntok(s["text"]), final) >= 85
        if s["kind"] == "keep" and not present:
            print("  ✗ 빠짐:", s["text"])
            ok = False
    for phrase in ("잠깐만요", "다시할게요"):
        if phrase in final:
            print("  ✗ 남음:", phrase)
            ok = False
    n_intro = final.count("하지만좋은디자인은좋은질문에서")
    n_wide = final.count("먼저넓게펼쳐서관찰하고")
    print(f"  '하지만 좋은 디자인은…' {n_intro}번 · '먼저 넓게 펼쳐서…' {n_wide}번 (각 1번이어야 함)")
    ok &= n_intro == 1 and n_wide == 1
    audio = load_audio_16k(out16)
    from studio.asr.transcribe import speech_regions
    vad = speech_regions(audio)
    gaps = [round(b[0] - a[1], 2) for a, b in zip(vad, vad[1:]) if b[0] - a[1] > 0.8]
    print(f"  0.8초 넘는 무음: {gaps}")
    ok &= not gaps
    src_len = segs[-1]["end"] + 1.2
    print(f"  길이 {src_len:.1f}s → {p.timemap.duration:.1f}s")
    print("E2E REALISTIC", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
