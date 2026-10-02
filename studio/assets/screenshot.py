"""웹·앱 화면 캡처(03 문서 3절 screenshot) — C 등급(인용)이라 설정 allow_quote 가 켜졌을 때만 쓴다(기본 끔).

렌더와 같은 Chrome(renderer/scripts/screenshot.mjs)으로 폭 1440 · 문서 높이(최대 6000px)까지 한 장. 과거 시점 화면(as_of)은
인터넷 아카이브(Wayback) 의 가장 가까운 스냅샷 주소로 연다. 로그인 벽·차단이면 None — 사다리가 로고 → 자료 카드로 넘어간다.
로그인 뒤 화면·개인 정보·유료 본문은 찍지 않는다(주소는 리서처가 공개 페이지로 준다).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from .. import net
from ..paths import RENDERER_DIR
from ..util import LogFn, noop_log, run_process, write_json

WAYBACK = "https://archive.org/wayback/available"


def wayback_url(url: str, as_of: str) -> str:
    """as_of('2012-03', '2012') → 그 시점에 가장 가까운 스냅샷 주소. 없으면 ''."""
    ts = re.sub(r"[^0-9]", "", as_of or "")[:8]
    if not ts:
        return ""
    try:
        data = net.get_json(WAYBACK, params={"url": url, "timestamp": ts}, timeout=20, rounds=1)
    except Exception:  # noqa: BLE001
        return ""
    snap = ((data or {}).get("archived_snapshots") or {}).get("closest") or {}
    return str(snap.get("url") or "") if snap.get("available") else ""


def capture(shots: list[dict[str, Any]], *, node: str, work: Path, browser_executable: str = "", gl: str = "",
            log: LogFn = noop_log) -> dict[str, dict[str, Any]]:
    """shots: [{id, url, out(Path)}] → id → {ok, w, h, error}."""
    if not shots:
        return {}
    job = {"browserExecutable": browser_executable, "gl": gl,
           "shots": [{"id": s["id"], "url": s["url"], "out": str(s["out"]), "width": 1440, "height": 900,
                      "maxHeight": 6000} for s in shots]}
    job_file = work / "screenshot_job.json"
    write_json(job_file, job)
    res: dict[str, dict[str, Any]] = {}

    def on_line(line: str) -> None:
        line = line.strip()
        if line.startswith("{"):
            try:
                ev = json.loads(line)
            except ValueError:
                return
            if ev.get("type") == "shot":
                res[ev["id"]] = ev
    try:
        run_process([node, str(RENDERER_DIR / "scripts" / "screenshot.mjs"), str(job_file)], cwd=str(RENDERER_DIR),
                    on_line=on_line)
    except Exception as e:  # noqa: BLE001 - 캡처 실패는 사다리 다음 칸으로
        log(f"🖥 화면 캡처 실패: {e}")
    return res


def domain(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0]


def credit(url: str, as_of: str = "") -> tuple[str, str]:
    d = domain(url)
    when = f" ({as_of})" if as_of else ""
    return f"화면: {d}{when}", f"{d} 화면 캡처{when}. 비평·교육 목적의 인용 — {url}"

