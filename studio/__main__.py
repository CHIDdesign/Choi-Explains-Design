"""실행:
    python -m studio                                             → 창(GUI)
    python -m studio run --video 원본.mp4 --topic 주제.txt --script 대본.txt   → 롱폼 1 + 숏폼 2 (창 없이)
    python -m studio rerender <작업폴더>                          → 끝난 단계는 건너뛰고 이어서/다시
    python -m studio rerender <작업폴더> --until design --replan  → 🧪 디자인 벤치: 기획을 새로 짓고 검수(장면 심사·장면 시트)까지만(렌더 없이)
    python -m studio reference                                   → 🎯 레퍼런스 분석 창(사진·영상 끌어다 놓기 — run_reference.bat 과 같음)
    python -m studio reference 사진.png 릴스.mp4 [--note 메모]    → 창 없이 분석해 user/taste/refs 에 저장
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _read(p: str | None) -> str:
    if not p:
        return ""
    from .text.docfile import read_text_file
    return read_text_file(p)


def _text_or_file(v: str) -> str:
    return _read(v) if v and Path(v).exists() else (v or "")


def _run(pipe, until: str) -> int:
    from .gate import GateBlocked
    try:
        pipe.run(until=until)
    except GateBlocked as e:
        print(f"\n{e}\n\n이대로 만들려면: python -m studio rerender \"{pipe.dir}\" --force-render", flush=True)
        return 3
    return 0


def cli(argv: list[str]) -> int:
    from .pipeline import JobSpec, Pipeline, new_job_dir
    from .settings import Settings
    from .util import read_json

    ap = argparse.ArgumentParser(prog="studio")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="새 작업 실행")
    r.add_argument("--video", required=True, nargs="+",
                   help="원본 영상(여러 개 가능: 다른 각도로 동시에 찍은 것 · 나눠 찍은 것)")
    r.add_argument("--topic", default="", help="주제 설명(텍스트 파일 경로 또는 문장)")
    r.add_argument("--script", help="대본 파일(.txt/.md/.docx/.hwpx)")
    r.add_argument("--title", default="", help="(선택) 제목 — 비우면 AI 감독이 정한다")
    r.add_argument("--audio", default="")
    r.add_argument("--notes", help="(이전 버전) 메모 텍스트 파일")
    r.add_argument("--episode", default="")
    r.add_argument("--images", default="")
    r.add_argument("--bgm", default="")
    r.add_argument("--lut", default="")
    r.add_argument("--shorts", type=int, default=2)
    r.add_argument("--height", type=int, default=1080)
    r.add_argument("--pace", default="calm", choices=["calm", "normal", "fast"])
    r.add_argument("--no-claude", action="store_true")
    r.add_argument("--no-long", action="store_true")
    r.add_argument("--until", default="all", choices=["all", "plan", "design"])
    r.add_argument("--replan", action="store_true", help="저장된 기획을 쓰지 않고 새로 짓는다(🧪 디자인 벤치)")
    r.add_argument("--job-dir", default="")
    force_help = "품질 게이트가 멈춰도 렌더(원본·대본을 확인한 뒤에만 — 이유는 output/품질게이트_중단.md)"
    r.add_argument("--force-render", action="store_true", help=force_help)
    rr = sub.add_parser("rerender", help="작업 폴더를 다시 렌더")
    rr.add_argument("job_dir")
    rr.add_argument("--until", default="all", choices=["all", "plan", "design"])
    rr.add_argument("--replan", action="store_true", help="저장된 기획을 쓰지 않고 새로 짓는다(🧪 디자인 벤치)")
    rr.add_argument("--force-render", action="store_true", help=force_help)
    ref = sub.add_parser("reference", help="🎯 레퍼런스 분석(사진·영상 → 디자인 규칙). 파일이 없으면 창을 연다")
    ref.add_argument("files", nargs="*", help="사진·영상·폴더")
    ref.add_argument("--note", default="", help="(선택) 무엇이 좋은지 한 줄")
    ref.add_argument("--no-ai", action="store_true", help="측정값만(Claude 를 부르지 않음)")
    args = ap.parse_args(argv)

    settings = Settings.load()

    def log(msg: str) -> None:
        print(msg, flush=True)

    last = [-1]

    def progress(stage: str, frac: float, overall: float) -> None:
        pct = int(overall * 100)
        if pct != last[0]:
            last[0] = pct
            print(f"  [{pct:3d}%] {stage} {frac * 100:.0f}%", flush=True)

    if args.cmd == "run":
        spec = JobSpec(video=args.video[0], videos=args.video[1:], topic=_text_or_file(args.topic), title=args.title, audio=args.audio,
                       script=_read(args.script), notes=_read(args.notes), episode=args.episode,
                       images_dir=args.images, bgm=args.bgm, lut=args.lut, shorts_count=args.shorts,
                       out_height=args.height, pace=args.pace, use_claude=not args.no_claude,
                       make_long=not args.no_long)
        spec.reuse_plan = not args.replan
        job_dir = Path(args.job_dir) if args.job_dir else new_job_dir(settings, spec.working_title())
        return _run(Pipeline(spec, settings, job_dir, log=log, progress=progress, force_render=args.force_render),
                    args.until)
    if args.cmd == "rerender":
        job_dir = Path(args.job_dir)
        spec = JobSpec.from_dict(read_json(job_dir / "job.json", {}))
        if args.replan:
            spec.reuse_plan = False
        return _run(Pipeline(spec, settings, job_dir, log=log, progress=progress, force_render=args.force_render),
                    args.until)
    if args.cmd == "reference":
        from .agents import reference
        if not args.files:
            from .gui.reference_dialog import run_reference_tool
            return run_reference_tool()
        paths = reference.expand_paths(args.files)
        if not paths:
            print("사진·영상 파일이 없습니다.")
            return 1
        client, why = (None, "--no-ai") if args.no_ai else reference.make_client(settings, log=log)
        log(f"AI 연결: {why}" if client is not None else f"AI 없음({why}) — 측정값만 저장")
        bad = 0
        for p in paths:
            try:
                reference.analyze_file(p, client=client, note=args.note, log=log)
            except Exception as e:  # noqa: BLE001
                bad += 1
                log(f"⚠ {Path(p).name}: {e}")
        for row in reference.summary_rows()[: len(paths)]:
            log(f"- {row['name']}: {row['summary'] or row['measured']}")
        log(f"저장: {reference.ref_dir()}")
        return 1 if bad else 0
    ap.print_help()
    return 1


def main() -> int:
    from .net import use_os_certificates
    use_os_certificates()   # 백신·회사망 HTTPS 검사 환경에서도 Windows 인증서 저장소로 접속
    if len(sys.argv) > 1:
        return cli(sys.argv[1:])
    from .gui.app import run_gui
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
