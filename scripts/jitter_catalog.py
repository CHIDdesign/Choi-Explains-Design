"""Jitter 공개 템플릿 갤러리 → assets/jitter_catalog.json(slug · 이름 · 분류 · 한 줄 설명) — 모션 레퍼런스 목록 다시 만들기.

    python scripts/jitter_catalog.py [--out assets/jitter_catalog.json]

갤러리의 분류 페이지와 템플릿 페이지의 공개 메타(제목·설명)만 읽는다(초당 1회 정도). 템플릿 파일은 받지 않는다 — 총괄 감독이
움직임을 고르고, 앱이 미리보기를 찍어 🛠 시그니처 장면 빌더가 우리 스타일로 다시 짓는다(docs/upgrade/14).
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASE = "https://jitter.video"
CATS = ("ads", "backgrounds", "brand", "buttons", "charts", "devices", "icons", "jitter-ai", "logos", "showreels",
        "social-media", "text", "ui-elements", "video-titles", "websites")


def get(url: str) -> str:
    from studio import net
    try:
        r = net.request(url, timeout=25, rounds=1)
        return r.text if r.ok else ""
    except Exception:  # noqa: BLE001
        return ""


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "assets" / "jitter_catalog.json"))
    args = ap.parse_args(argv)
    link = re.compile(r'href="(?:https://jitter.video)?/template/([^"/]+)/?"')
    cats: dict[str, set[str]] = {s: set() for s in link.findall(get(f"{BASE}/templates/all/"))}
    for c in CATS:
        for s in link.findall(get(f"{BASE}/templates/{c}/")):
            cats.setdefault(s, set()).add(c)
        time.sleep(1.0)
    out = []
    for slug in sorted(cats):
        page = get(f"{BASE}/template/{slug}/")
        time.sleep(0.8)
        t = re.search(r"<title>([^<]+)</title>", page)
        d = re.search(r'<meta name="description" content="([^"]*)"', page)
        name = html.unescape(t.group(1)).split("·")[0].split("|")[0].replace(" Template", "").strip() if t else slug
        out.append({"slug": slug, "name": name, "categories": sorted(cats[slug]) or ["etc"],
                    "description": html.unescape(d.group(1)).strip() if d else ""})
    Path(args.out).write_text("[\n" + ",\n".join(json.dumps(x, ensure_ascii=False) for x in out) + "\n]\n", encoding="utf-8")
    print(f"{len(out)}개 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
