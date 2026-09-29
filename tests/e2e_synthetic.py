"""GPU·네트워크 없이 전체 파이프라인을 검증하는 스모크 테스트.

합성 영상(테스트 패턴 + 단어 길이만큼의 톤) + 가짜 음성인식 결과로
대본 정렬 → NG 제거 → 규칙 기반 디렉터 → 프록시 → Remotion 렌더 → 내보내기까지 실행한다.

    python tests/e2e_synthetic.py [--browser /path/to/chrome] [--keep]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import pipeline as pl  # noqa: E402
from studio.settings import Settings  # noqa: E402

SCRIPT = """# 들어가며
안녕하세요. 오늘은 좋은 디자인이 어디에서 시작하는지 이야기해 보겠습니다.
[도식: 더블다이아몬드 | 발견] 디자인 과정에는 더블 다이아몬드라는 유명한 모델이 있습니다.
[강조: 발산] 먼저 넓게 펼치고 그 다음에 좁혀야 합니다.
# 문제를 다시 정의하기
[숏폼 시작]사실 대부분의 학생들은 이 단계를 건너뜁니다. 바로 해결책부터 그리기 시작하죠.
[정의: 어포던스 | Affordance | 형태가 사용법을 알려주는 성질] 어포던스라는 말을 들어보셨나요?
[목록: 좋은 질문의 조건 | 구체적이다 ; 열려 있다 ; 사용자를 향한다] 좋은 질문에는 세 가지 조건이 있습니다.
결국 좋은 디자인은 좋은 질문에서 시작합니다.[숏폼 끝]
"""

# (말한 문장, 문장 뒤 쉼) — 리테이크와 NG 포함
SPOKEN = [
    ("안녕하세요.", 0.9),
    ("오늘은 좋은 디자인이 어디에서 시작하는지 이야기해 보겠습니다.", 1.0),
    ("디자인 과정에는 더블 다이어몬드라는", 1.2),           # 중간에 끊김(리테이크 대상)
    ("아 다시 할게요", 1.4),                              # NG
    ("디자인 과정에는 더블 다이아몬드라는 유명한 모델이 있습니다.", 0.9),
    ("먼저 넓게 펼치고 그 다음에 좁혀야 합니다.", 1.6),
    ("사실 대부분의 학생들은 이 단계를 건너뜁니다.", 0.7),
    ("바로 해결책부터 그리기 시작하죠.", 0.9),
    ("어포던스라는 말을 들어보셨나요?", 0.8),
    ("좋은 질문에는 세 가지 조건이 있습니다.", 0.9),
    ("결국 좋은 디자인은 좋은 질문에서 시작합니다.", 1.5),
]


def make_words() -> tuple[list[dict], float]:
    words, t = [], 0.8
    for sent, pause in SPOKEN:
        for w in sent.split():
            d = 0.26 + 0.09 * len(w)
            words.append({"text": w, "start": round(t, 3), "end": round(t + d, 3), "prob": 0.95})
            t += d + 0.07
        t += pause
    return words, t + 1.0


def make_media(dst: Path, words: list[dict], duration: float, face: str = "") -> None:
    sr = 48000
    n = int(sr * duration)
    audio = np.random.default_rng(1).normal(0, 0.002, n)
    for i, w in enumerate(words):
        a, b = int(w["start"] * sr), int(w["end"] * sr)
        tt = np.arange(b - a) / sr
        f = 180 + (i % 7) * 25
        env = np.sin(np.pi * np.linspace(0, 1, b - a)) ** 0.5
        audio[a:b] += 0.25 * env * (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * 2 * f * tt))
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    wav = dst.with_suffix(".wav")
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    if face:
        # 실제 얼굴 영상(짧은 클립을 반복)으로 — 색보정·얼굴 추적·카메라 연출을 눈으로 확인할 때
        src = ["-stream_loop", "-1", "-i", face]
        vf = ["-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30"]
    else:
        src = ["-f", "lavfi", "-i", f"testsrc2=size=1920x1080:rate=30:duration={duration:.2f}"]
        vf = []
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + src + ["-i", str(wav), "-t", f"{duration:.2f}",
                    "-map", "0:v:0", "-map", "1:a:0"] + vf +
                   ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(dst)], check=True)
    wav.unlink()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", default="")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--work", default=str(ROOT / "projects" / "_e2e"))
    ap.add_argument("--face", default="", help="실제 얼굴 영상 클립(반복해서 원본으로 씀)")
    args = ap.parse_args()
    work = Path(args.work)
    if work.exists() and not args.keep:
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    words, duration = make_words()
    video = work / "source.mp4"
    if not video.exists():
        make_media(video, words, duration, args.face)

    # 음성 인식 대신 합성 결과 사용
    def fake_transcribe(*_a, **_k):
        return {"words": words, "segments": [], "info": {"model": "synthetic", "duration": duration}}
    pl.transcribe = fake_transcribe

    settings = Settings()
    settings.anthropic_api_key = ""
    settings.projects_dir = str(work)
    settings.render.browser_executable = args.browser
    settings.render.gl = "swangle" if sys.platform != "win32" else "angle"
    settings.render.concurrency = 3
    settings.keyless_stock = False
    settings.download_sounds = False
    spec = pl.JobSpec(video=str(video), topic="좋은 디자인은 질문에서 시작한다", episode="01", script=SCRIPT,
                      shorts_count=1, use_claude=False, fetch_broll=False, thumbnails=True, short_max_sec=40)
    job = work / "job"

    def log(m: str) -> None:
        print(m, flush=True)

    res = pl.Pipeline(spec, settings, job, log=log).run()
    out = Path(res["output"])
    files = sorted(p.name for p in out.iterdir())
    print("\n출력:", json.dumps(files, ensure_ascii=False, indent=1))
    extras = sorted(p.name for p in (out / "부가자료").iterdir())
    print("부가자료:", json.dumps(extras, ensure_ascii=False, indent=1))
    assert any(f.startswith("1_롱폼") and f.endswith(".mp4") for f in files), "롱폼 없음"
    assert any("숏폼1" in f and f.endswith(".mp4") for f in files), "숏폼 없음"
    assert "업로드정보.txt" in files
    assert any(f.endswith(".srt") for f in extras) and any(f.endswith("_premiere.xml") for f in extras)
    assert any(f.startswith("썸네일") for f in extras) and "색보정_전후.jpg" in extras
    align = json.loads((job / "work" / "align.json").read_text(encoding="utf-8"))
    statuses = [u["status"] for u in align["utterances"]]
    assert "retake" in statuses and "meta" in statuses, statuses
    print("E2E OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
