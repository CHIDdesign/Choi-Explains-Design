"""GPU·네트워크 없이 전체 파이프라인을 검증하는 스모크 테스트.

합성 영상(테스트 패턴 + 단어 길이만큼의 톤) + 가짜 음성인식 결과로
대본 정렬 → NG 제거 → 규칙 기반 디렉터 → 프록시 → Remotion 렌더 → 내보내기까지 실행한다.

    python tests/e2e_synthetic.py [--browser /path/to/chrome] [--keep] [--face 얼굴클립.mp4] [--multi multicam|split]

--multi multicam: 같은 순간을 두 각도로 찍은 원본 2개(B 는 1.2초 먼저 녹화 시작 · 소리 작고 잡음 많음 · 좌우 반전·
                  가까운 앵글 · 17~23초 초점 나감) → 소리 싱크 · 목소리 카메라 · 앵글 고르기(흐린 구간 피하기) 확인
--multi split:    나눠 찍은 원본 2개(두 번째 파일이 앞 파일 마지막 문장을 다시 말하며 시작) → 가상 타임라인 이어 붙이기 ·
                  파일을 넘나드는 테이크 고르기 확인
--multi retake:   같은 대본을 처음부터 끝까지 두 번 찍은 원본 2개(다른 구도·다른 빠르기, 10/1 테스트의 P0 버그) →
                  읽기 회차 2개를 가려 한 편으로(길이가 두 배가 되지 않고 같은 대본 문장이 한 번만)
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


def make_words(spoken=SPOKEN) -> tuple[list[dict], float]:
    words, t = [], 0.8
    for sent, pause in spoken:
        for w in sent.split():
            d = 0.26 + 0.09 * len(w)
            words.append({"text": w, "start": round(t, 3), "end": round(t + d, 3), "prob": 0.95})
            t += d + 0.07
        t += pause
    return words, t + 1.0


def make_media(dst: Path, words: list[dict], duration: float, face: str = "", *, lead: float = 0.0,
               gain: float = 0.25, noise: float = 0.002, angle: str = "a",
               blur: tuple[float, float] | None = None) -> None:
    """lead: 이 카메라가 몇 초 먼저 녹화를 시작했나(그만큼 소리가 늦게 나옴). angle='b': 다른 각도(좌우 반전 · 가까이).
    blur: (시작, 끝) 이 카메라 시각으로 초점이 나간 구간."""
    sr = 48000
    duration = duration + lead
    n = int(sr * duration)
    audio = np.random.default_rng(1 if angle == "a" else 2).normal(0, noise, n)
    for i, w in enumerate(words):
        a, b = int((w["start"] + lead) * sr), int((w["end"] + lead) * sr)
        tt = np.arange(b - a) / sr
        f = 180 + (i % 7) * 25
        env = np.sin(np.pi * np.linspace(0, 1, b - a)) ** 0.5
        audio[a:b] += gain * env * (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * 2 * f * tt))
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    wav = dst.with_suffix(".wav")
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    extra = ""
    if angle == "b":   # 다른 각도: 좌우 반전 + 가까이(1.35배) + 살짝 따뜻하게
        extra += ",hflip,crop=iw/1.35:ih/1.35:(iw-iw/1.35)/2:(ih-ih/1.35)/3,scale=1920:1080,eq=gamma_r=1.05"
    if blur:
        extra += f",gblur=sigma=18:enable='between(t,{blur[0]},{blur[1]})'"
    if face:
        # 실제 얼굴 영상(짧은 클립을 반복)으로 — 색보정·얼굴 추적·카메라 연출을 눈으로 확인할 때
        src = ["-stream_loop", "-1", "-i", face]
        vf = ["-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30" + extra]
    else:
        src = ["-f", "lavfi", "-i", f"testsrc2=size=1920x1080:rate=30:duration={duration:.2f}"]
        vf = ["-vf", extra[1:]] if extra else []
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error"] + src + ["-i", str(wav), "-t", f"{duration:.2f}",
                    "-map", "0:v:0", "-map", "1:a:0"] + vf +
                   ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(dst)], check=True)
    wav.unlink()


def check_multi(mode: str, job: Path) -> None:
    src = json.loads((job / "work" / "sources.json").read_text(encoding="utf-8"))
    props = json.loads((job / "render" / "props_long.json").read_text(encoding="utf-8"))
    angles = json.loads((job / "work" / "angles.json").read_text(encoding="utf-8"))
    used = sorted({c["src"] for c in props["clips"]})
    print("묶음:", [[(Path(c["path"]).name, c["offset"]) for c in g["cams"]] for g in src["groups"]])
    print("롱폼 클립 소스:", used, "· 앵글 조각:", [(p["start"], p["end"], p["cam"], p["why"]) for p in angles["long"]])
    xml = (job / "output" / "부가자료" / "롱폼_premiere.xml").read_text(encoding="utf-8")
    if mode != "retake":
        assert used == ["media/proxy.mp4", "media/proxy_2.mp4"], used
        assert "source.mp4" in xml and "source_b.mp4" in xml
    if mode == "multicam":
        assert len(src["groups"]) == 1 and len(src["groups"][0]["cams"]) == 2
        a, b = src["groups"][0]["cams"]
        assert Path(a["path"]).name == "source.mp4", "목소리는 깨끗한 카메라에서"
        assert abs(b["offset"] - 1.2) < 0.04, b     # B 시각 = A 시각 + 1.2
        # B 가 초점이 나간 구간(B 시각 17~23초 = 가상 15.8~21.8초, 남기는 말 한가운데)에서는 B 를 쓰지 않는다
        bad = sum(max(0.0, min(p["end"], 21.3) - max(p["start"], 16.3)) for p in angles["long"] if p["cam"] == 1)
        assert bad < 0.6, bad
    elif mode == "retake":
        assert len(src["groups"]) == 2, src["groups"]
        align = json.loads((job / "work" / "align.json").read_text(encoding="utf-8"))
        rep = align["report"]
        print("읽기 회차:", rep.get("pass_mode"), rep.get("main_pass"), rep.get("passes"), "· 역할:", src.get("roles"))
        assert rep["pass_mode"] == "best_pass" and len(rep["passes"]) == 2 and rep["main_pass"] in (0, 1)
        assert sorted((src.get("roles") or {}).values()) == ["alt_take", "main"], src.get("roles")
        # 본편은 주 테이크(그 회차의 파일)로 — 다른 회차 파일은 빠진 문장 보강에만
        main_proxy = "media/proxy.mp4" if rep["main_pass"] == 0 else "media/proxy_2.mp4"
        assert main_proxy in used, used
        kept = [u["text"] for u in align["utterances"] if u["status"] == "keep"]
        for line in ("먼저 넓게 펼치고", "어포던스라는", "좋은 질문에는 세 가지", "결국 좋은 디자인은"):
            assert sum(line in t for t in kept) == 1, (line, kept)       # 같은 대본 문장이 한 번만
        keeps = json.loads((job / "work" / "keeps_long.json").read_text(encoding="utf-8"))
        body = sum(k["end"] - k["start"] for k in keeps)
        one = max(g["duration"] for g in src["groups"])
        print(f"본편 {body:.1f}초 · 회차 하나(긴 쪽) {one:.1f}초")
        assert body <= 1.0 * one, (body, one)                             # 두 배가 아니다
        report = (job / "output" / "부가자료" / "편집리포트.md").read_text(encoding="utf-8")
        assert "읽기 회차" in report
        return
    else:
        assert len(src["groups"]) == 2
        align = json.loads((job / "work" / "align.json").read_text(encoding="utf-8"))
        kept = [u["text"] for u in align["utterances"] if u["status"] == "keep"]
        assert sum("먼저 넓게 펼치고" in t for t in kept) == 1, kept     # 두 파일에서 말한 문장은 한 번만
        joined = " ".join(kept)
        for must in ("안녕하세요", "건너뜁니다", "시작합니다"):
            assert must in joined, joined


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", default="")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--work", default=str(ROOT / "projects" / "_e2e"))
    ap.add_argument("--face", default="", help="실제 얼굴 영상 클립(반복해서 원본으로 씀)")
    ap.add_argument("--multi", default="", choices=["", "multicam", "split", "retake"], help="원본 여러 개 시험")
    args = ap.parse_args()
    work = Path(args.work)
    if work.exists() and not args.keep:
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    video = work / "source.mp4"
    videos: list[Path] = []
    job = work / "job"
    if args.multi == "retake":
        # 같은 대본 전체를 두 번(두 번째는 다른 구도 · 쉼이 1.6배 · NG 없이 깔끔하게)
        words, duration = make_words()
        clean = [(t, p) for t, p in SPOKEN if t not in ("디자인 과정에는 더블 다이어몬드라는", "아 다시 할게요")]
        words_b, duration_b = make_words([(t, p * 1.6 + 0.3) for t, p in clean])
        by_file = {str(video): words, str(work / "source_b.mp4"): words_b}
        if not video.exists():
            make_media(video, words, duration, args.face)
            make_media(work / "source_b.mp4", words_b, duration_b, args.face, angle="b")
        videos = [work / "source_b.mp4"]
    elif args.multi == "split":
        # 나눠 찍기: 두 번째 파일은 앞 파일의 마지막 문장을 다시 말하며 시작(파일을 넘나드는 테이크)
        words, duration = make_words(SPOKEN[:6])
        words_b, duration_b = make_words([SPOKEN[5]] + SPOKEN[6:])
        by_file = {str(video): words, str(work / "source_b.mp4"): words_b}
        if not video.exists():
            make_media(video, words, duration, args.face)
            make_media(work / "source_b.mp4", words_b, duration_b, args.face, angle="b")
        videos = [work / "source_b.mp4"]
    else:
        words, duration = make_words()
        by_file = {str(video): words}
        if not video.exists():
            make_media(video, words, duration, args.face)
        if args.multi == "multicam":
            if not (work / "source_b.mp4").exists():
                make_media(work / "source_b.mp4", words, duration, args.face, lead=1.2, gain=0.12, noise=0.012,
                           angle="b", blur=(17.0, 23.0))
            videos = [work / "source_b.mp4"]

    # 음성 인식 대신 합성 결과 사용 — 원본이 여러 개면 파일 시각 → 가상 타임라인(work/sources.json)으로 옮긴다
    def fake_transcribe(*_a, **_k):
        src = json.loads((job / "work" / "sources.json").read_text(encoding="utf-8")) if videos else None
        if not src:
            return {"words": words, "segments": [], "info": {"model": "synthetic", "duration": duration}}
        out = []
        for g in src["groups"]:
            cam = next((c for c in g["cams"] if c["path"] in by_file), None)
            for w in by_file[cam["path"]] if cam else []:
                sh = g["start"] - cam["offset"]
                out.append({**w, "start": round(w["start"] + sh, 3), "end": round(w["end"] + sh, 3)})
        return {"words": out, "segments": [], "info": {"model": "synthetic", "duration": duration}}
    pl.transcribe = fake_transcribe

    settings = Settings()
    settings.anthropic_api_key = ""
    settings.projects_dir = str(work)
    settings.render.browser_executable = args.browser
    settings.render.gl = "swangle" if sys.platform != "win32" else "angle"
    settings.render.concurrency = 3
    settings.keyless_stock = False
    settings.download_sounds = False
    spec = pl.JobSpec(video=str(video), videos=[str(v) for v in videos], topic="좋은 디자인은 질문에서 시작한다", episode="01", script=SCRIPT,
                      shorts_count=1, use_claude=False, fetch_broll=False, thumbnails=True, short_max_sec=40, verify_edit=False)

    def log(m: str) -> None:
        print(m, flush=True)

    previews: list[tuple[str, str]] = []
    etas: list[float] = []

    def progress(key: str, _f: float, _o: float) -> None:
        left = eta.remaining()
        if left is not None:
            etas.append(left)

    eta = pl.Eta(work / "eta_history.json")
    res = pl.Pipeline(spec, settings, job, log=log, progress=progress, eta=eta,
                      preview=lambda path, cap: previews.append((path, cap))).run()
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
    assert any(f.startswith("검토시트_롱폼") for f in extras) and any(f.startswith("검토시트_숏폼1") for f in extras)
    # 리테이크·NG 는 단어 단위 정리(takes.py)가 발화를 만들기 전에 지운다
    align = json.loads((job / "work" / "align.json").read_text(encoding="utf-8"))
    removed = " ".join(r["text"] for r in align["report"]["words_removed"])
    assert "다이어몬드라는" in removed and "다시 할게요" in removed, removed
    kept_text = " ".join(u["text"] for u in align["utterances"] if u["status"] == "keep")
    assert "좋은 질문에는 세 가지 조건이 있습니다" in kept_text, kept_text   # 완성된 문장은 남긴다
    # 실시간 미리보기: 색보정 전후 → 렌더 중 프레임(롱폼·숏폼) → 썸네일
    caps = [c for _, c in previews]
    print(f"미리보기 {len(previews)}장:", caps[:3], "…", caps[-4:])
    assert caps and caps[0].startswith("자동 색보정")
    assert any(c.startswith("롱폼 렌더링") for c in caps) and any(c.startswith("숏폼 1 렌더링") for c in caps)
    assert any(c.startswith("썸네일") for c in caps)
    long_peeks = [c for c in caps if c.startswith("롱폼 렌더링")]
    assert long_peeks == sorted(long_peeks), "렌더 미리보기가 뒤로 가면 안 됨"
    # 남은 시간: 계획이 잡힌 뒤로 기록됐고, 이 PC 기록 파일이 생김
    hist = json.loads((work / "eta_history.json").read_text(encoding="utf-8"))
    print("남은 시간 예측(분):", [round(x / 60, 1) for x in etas[::max(1, len(etas) // 12)]])
    print("학습 기록:", {k: v[-1] for k, v in hist["factors"].items()})
    assert etas and "render" in hist["factors"]
    if args.multi:
        check_multi(args.multi, job)
    print("E2E OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
