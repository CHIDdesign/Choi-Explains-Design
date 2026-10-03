"""웹·앱 화면 캡처(03 문서 3절 screenshot) — C 등급(인용)이라 설정 allow_quote 가 켜졌을 때만 쓴다(기본 끔).

렌더와 같은 Chrome(renderer/scripts/screenshot.mjs)으로 폭 1440 · 문서 높이(최대 6000px)까지 한 장. 과거 시점 화면(as_of)은
인터넷 아카이브(Wayback) 의 가장 가까운 스냅샷 주소로 연다. 봇 확인(Cloudflare)·오류·로그인 벽·거의 빈 화면이면 버린다
(blocked_reason · ink_ratio) — 사다리가 로고 → 자료 카드, 논문은 출처 카드로 넘어간다.
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

# 찍으면 안 되는 화면 — 봇 확인·오류·로그인·쿠키 벽(2026-10-04: doi.org → ASME 의 Cloudflare 보안 확인 화면을 논문 자료로 냈다).
# (제목·본문에서 찾을 패턴, 화면에 남길 이유)
BLOCK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"just a moment|performing security verification|verify (that )?you are (a )?human|checking (your|if the site "
     r"connection is secure)|attention required|cf-browser-verification|ray id[: ]|ddos protection by|enable javascript "
     r"and cookies to continue|please (complete|wait while we verify)", "봇 확인(Cloudflare 등) 화면"),
    (r"captcha|are you a robot|not a robot|unusual traffic|automated (queries|requests)|bot detection",
     "로봇 확인(CAPTCHA) 화면"),
    (r"\baccess (denied|forbidden)\b|403 forbidden|error 1020|you don't have permission to access|request blocked|"
     r"has been blocked", "접근 거부 화면"),
    (r"404 not found|page not found|페이지를 찾을 수 없|this page (isn't|is not) available|server error|"
     r"502 bad gateway|503 service|service unavailable|err_[a-z_]+|this site can.t be reached", "오류 화면"),
    (r"(sign|log) in to (continue|view|read)|to continue, (sign|log) in|please (sign|log) in|로그인이 필요|"
     r"로그인해 주세요|로그인 후 이용", "로그인 벽"),
)
# 제목이 로그인이면 로그인 벽 — 본문의 'Log in' 링크는 정상 페이지(핀터레스트 첫 화면 등)에도 있어 본문으로는 보지 않는다
LOGIN_TITLE = r"^\s*(sign in|log in|login|로그인)\b"
MIN_TEXT = 40          # 본문 글자가 이보다 적으면(빈 화면·스크립트만) 쓰지 않는다
MIN_INK = 0.025        # 찍힌 그림에서 바탕이 아닌 픽셀 비율 — 이보다 적으면 거의 빈 화면


def blocked_reason(title: str = "", text: str = "", url: str = "") -> str:
    """캡처한 페이지가 자료로 쓸 수 없는 화면이면 그 이유, 아니면 "". 제목·최종 주소·본문 앞부분으로 판단한다."""
    head = f"{title or ''}\n{(text or '')[:1500]}"
    for pat, why in BLOCK_PATTERNS:
        if re.search(pat, head, re.I):
            return why
    if re.search(LOGIN_TITLE, title or "", re.I):
        return "로그인 벽"
    u = (url or "").lower()
    if re.search(r"/(login|signin|sign-in|auth|captcha|challenge)\b|__cf_chl|/cdn-cgi/", u):
        return "로그인·확인 주소로 넘어감"
    if text is not None and len(re.sub(r"\s+", "", text or "")) < MIN_TEXT and not title:
        return "본문이 거의 없는 화면"
    return ""


def ink_ratio(path: Path) -> float:
    """찍힌 화면에서 바탕(가장 흔한 밝기)과 다른 픽셀의 비율 — 거의 빈 화면(보안 확인·로딩)을 잡는다."""
    from PIL import Image
    import numpy as np
    with Image.open(path) as im:
        g = np.asarray(im.convert("L").resize((360, max(1, int(360 * im.height / max(1, im.width))))), dtype=np.int16)
    g = g[: min(len(g), 225)]                     # 첫 화면(16:10)만 — 화면에 나가는 곳
    hist = np.bincount(g.ravel(), minlength=256)
    bg = int(hist.argmax())
    return float((np.abs(g - bg) > 24).mean())


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
    for s in shots:
        ev = res.get(s["id"])
        if not ev or not ev.get("ok"):
            continue
        why = blocked_reason(ev.get("title", ""), ev.get("text", ""), ev.get("url", "")) if "text" in ev else ""
        if not why:
            try:
                ink = ink_ratio(Path(s["out"]))
                why = f"거의 빈 화면(잉크 {ink:.1%})" if ink < MIN_INK else ""
            except Exception:  # noqa: BLE001 - 그림을 못 읽으면 쓰지 않는다
                why = "찍은 그림을 읽지 못함"
        if why:
            ev.update(ok=False, error=f"blocked: {why}")
            log(f"🖥 화면 캡처 버림 — {why}: {ev.get('url') or s['url']}")
            try:
                Path(s["out"]).unlink()
            except OSError:
                pass
    return res


def domain(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0]


def credit(url: str, as_of: str = "") -> tuple[str, str]:
    d = domain(url)
    when = f" ({as_of})" if as_of else ""
    return f"화면: {d}{when}", f"{d} 화면 캡처{when}. 비평·교육 목적의 인용 — {url}"

