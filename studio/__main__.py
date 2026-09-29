"""실행:
    python -m studio                      → 창(GUI)
    python -m studio run --video a.mp4 --title "제목" --script 대본.txt --notes 메모.txt
    python -m studio rerender <작업폴더>   → 저장된 분석/계획으로 다시 렌더
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _read(p: str | None) -> str:
    if not p:
        return ""
    return Path(p).read_text(encoding="utf-8")


def cli(argv: list[str]) -> int:
    from .pipeline import JobSpec, Pipeline, new_job_dir
    from .settings import Settings
    from .util import read_json

    ap = argparse.ArgumentParser(prog="studio")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="새 작업 실행")
    r.add_argument("--video", required=True)
    r.add_argument("--title", required=True)
    r.add_argument("--audio", default="")
    r.add_argument("--script", help="대본 텍스트 파일")
    r.add_argument("--notes", help="메모 텍스트 파일")
    r.add_argument("--episode", default="")
    r.add_argument("--images", default="")
    r.add_argument("--bgm", default="")
    r.add_argument("--lut", default="")
    r.add_argument("--shorts", type=int, default=2)
    r.add_argument("--height", type=int, default=1080)
    r.add_argument("--pace", default="calm", choices=["calm", "normal", "fast"])
    r.add_argument("--no-claude", action="store_true")
    r.add_argument("--no-long", action="store_true")
    r.add_argument("--until", default="all", choices=["all", "plan"])
    r.add_argument("--job-dir", default="")
    rr = sub.add_parser("rerender", help="작업 폴더를 다시 렌더")
    rr.add_argument("job_dir")
    rr.add_argument("--until", default="all", choices=["all", "plan"])
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
        spec = JobSpec(video=args.video, title=args.title, audio=args.audio, script=_read(args.script),
                       notes=_read(args.notes), episode=args.episode, images_dir=args.images, bgm=args.bgm,
                       lut=args.lut, shorts_count=args.shorts, out_height=args.height, pace=args.pace,
                       use_claude=not args.no_claude, make_long=not args.no_long)
        job_dir = Path(args.job_dir) if args.job_dir else new_job_dir(settings, args.title)
        Pipeline(spec, settings, job_dir, log=log, progress=progress).run(until=args.until)
        return 0
    if args.cmd == "rerender":
        job_dir = Path(args.job_dir)
        spec = JobSpec.from_dict(read_json(job_dir / "job.json", {}))
        Pipeline(spec, settings, job_dir, log=log, progress=progress).run(until=args.until)
        return 0
    ap.print_help()
    return 1


def main() -> int:
    if len(sys.argv) > 1:
        return cli(sys.argv[1:])
    from .gui.app import run_gui
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
