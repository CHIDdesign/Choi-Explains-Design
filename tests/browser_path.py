"""테스트가 쓸 헤드리스 Chrome — 클라우드(리눅스) 경로가 없으면 Remotion 이 renderer/node_modules/.remotion 에 받아 둔 것."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINUX = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"


def headless_browser() -> str:
    """있는 첫 경로. 없으면 리눅스 경로(없는 파일 — 테스트가 그것을 보고 건너뛴다)."""
    base = ROOT / "renderer" / "node_modules" / ".remotion" / "chrome-headless-shell"
    for p in (os.environ.get("CHOI_TEST_BROWSER", ""), LINUX,
              base / "win64" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe",
              base / "linux64" / "chrome-headless-shell-linux64" / "chrome-headless-shell",
              base / "mac-arm64" / "chrome-headless-shell-mac-arm64" / "chrome-headless-shell",
              base / "mac-x64" / "chrome-headless-shell-mac-x64" / "chrome-headless-shell"):
        if p and Path(p).is_file():
            return str(p)
    return LINUX
