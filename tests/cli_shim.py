"""가짜 Claude Code CLI 를 실행 파일로 감싼다 — 테스트·E2E 가 진짜 claude 대신 부른다.

리눅스·맥은 sh 한 줄. Windows 는 sh 를 못 돌리고(.cmd 는 cmd.exe 가 --json-schema 의 따옴표를 깨뜨린다), 그래서 pip 이 콘솔 스크립트에
쓰는 distlib 런처(.exe — 명령줄을 그대로 파이썬에 넘긴다)로 만든다.
"""
from __future__ import annotations

import sys
from pathlib import Path


def make_shim(script: Path, dst_dir: Path, name: str = "claude") -> Path:
    """script(파이썬 파일)를 인자·표준 입출력 그대로 실행하는 실행 파일 경로."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        shim = dst_dir / name
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        shim.chmod(0o755)
        return shim
    from pip._vendor.distlib.scripts import ScriptMaker   # venv 에 늘 있는 pip 의 런처 생성기
    src = dst_dir / "_shim_src"
    src.mkdir(exist_ok=True)
    # 진짜 CLI(node)처럼 표준 입출력은 UTF-8 — 파이프의 파이썬 기본값은 cp949 라 한글 전사본이 깨진다
    (src / f"{name}.py").write_text(
        "#!python\nimport runpy, sys\n"
        "for s in (sys.stdin, sys.stdout, sys.stderr):\n    s.reconfigure(encoding='utf-8')\n"
        f"sys.argv[0] = {str(script)!r}\nrunpy.run_path({str(script)!r}, run_name='__main__')\n", encoding="utf-8")
    maker = ScriptMaker(str(src), str(dst_dir), add_launchers=True)
    maker.executable = sys.executable
    maker.clobber = True        # 같은 폴더에 다시 만들 때도 새 스크립트로
    out = [Path(p) for p in maker.make(f"{name}.py") if p.lower().endswith(".exe")]
    assert out, "distlib 런처를 만들지 못함"
    return out[0]


def utf8_console() -> None:
    """Windows 콘솔(cp949)에 이모지·상자 문자를 찍다 죽지 않게 — 앱의 .bat 은 chcp 65001 로 같은 일을 한다."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
