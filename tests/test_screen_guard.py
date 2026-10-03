"""화면 캡처가 봇 확인·오류·로그인 화면이면 자료로 쓰지 않는다(studio/assets/screenshot.py) — 2026-10-04: doi.org → ASME 의
Cloudflare 'Performing security verification' 화면이 2020년 논문 자료로 영상에 두 번(콜드 오픈·03:38) 나갔다."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402

from studio.assets import screenshot as shot  # noqa: E402
from studio.assets.ladder import clip_words  # noqa: E402


def test_cloudflare_and_error_pages_are_blocked():
    assert shot.blocked_reason("Just a moment...", "asmedigitalcollection.asme.org\nPerforming security verification\n"
                               "This website uses a security service to protect against malicious bots.")
    assert shot.blocked_reason("", "Verify you are human\nRay ID: a44aa0e82a2bd1f5\nPerformance and Security by Cloudflare")
    assert shot.blocked_reason("Access Denied", "You don't have permission to access this resource.")
    assert shot.blocked_reason("404 Not Found", "The requested URL was not found on this server.")
    assert shot.blocked_reason("Sign in - Google Accounts", "Email or phone")
    assert shot.blocked_reason("Article", "x" * 100, "https://example.org/cdn-cgi/challenge-platform/h/g")


def test_normal_pages_pass_even_with_login_links():
    body = "Log in\nSign up\nGet your next idea — search for easy dinners, fashion, home decor and more ideas to try"
    assert shot.blocked_reason("Pinterest", body, "https://www.pinterest.com/") == ""
    assert shot.blocked_reason("Design fixation - ScienceDirect",
                               "Design Studies Volume 12, Issue 1, January 1991, Pages 3-11. Abstract. Design fixation "
                               "is a blind adherence ... Sign in Register", "https://www.sciencedirect.com/x") == ""


def test_nearly_blank_capture_is_rejected_by_ink(tmp_path):
    blank = Image.new("RGB", (1440, 900), "white")
    d = ImageDraw.Draw(blank)
    d.text((380, 130), "asmedigitalcollection.asme.org", fill=(40, 40, 40))
    d.text((380, 180), "Performing security verification", fill=(40, 40, 40))
    p = tmp_path / "cf.png"
    blank.save(p)
    assert shot.ink_ratio(p) < shot.MIN_INK
    page = Image.new("RGB", (1440, 900), "white")
    d = ImageDraw.Draw(page)
    for y in range(60, 860, 22):
        d.rectangle((120, y, 1300, y + 9), fill=(50, 50, 50))
    q = tmp_path / "article.png"
    page.save(q)
    assert shot.ink_ratio(q) > shot.MIN_INK


def test_capture_drops_blocked_shot(tmp_path, monkeypatch):
    out = tmp_path / "cap.jpg"
    Image.new("RGB", (1440, 900), "white").save(out)

    def fake_run(cmd, cwd=None, on_line=None, **kw):
        on_line(json.dumps({"type": "shot", "id": "s1", "ok": True, "w": 1440, "h": 900, "title": "Just a moment...",
                            "url": "https://asmedigitalcollection.asme.org/x",
                            "text": "Performing security verification"}))
    monkeypatch.setattr(shot, "run_process", fake_run)
    logs = []
    res = shot.capture([{"id": "s1", "url": "https://doi.org/10.1115/1.4046446", "out": out}], node="node", work=tmp_path,
                       log=logs.append)
    assert res["s1"]["ok"] is False and "blocked" in res["s1"]["error"]
    assert not out.exists()
    assert any("버림" in m for m in logs)


def test_clip_words_does_not_cut_mid_word():
    assert clip_words("Leahy 외 · J. Mech. Design 142(10), 2020", 24) == "Leahy 외 · J. Mech."
    assert clip_words("짧은 캡션", 24) == "짧은 캡션"
    assert len(clip_words("가" * 40, 24)) == 24
