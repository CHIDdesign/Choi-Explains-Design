"""모션 레퍼런스(docs/upgrade/14) — Jitter 공개 템플릿 갤러리에서 Claude 가 기획에 맞는 움직임을 고르고, 앱이 그 템플릿 페이지의
미리보기를 렌더와 같은 Chrome 으로 여러 장 찍어(움직임의 단계) 🛠 시그니처 장면 빌더에게 보여 준다. 빌더는 그 움직임(등장 순서·
이징·쌓임·마스크)을 우리 HTML 카드(GSAP)·종이 콜라주 스타일로 **다시 짓는다** — 템플릿 파일을 내려받거나 그대로 쓰지 않는다.

- `assets/jitter_catalog.json` : 템플릿 목록(slug · 이름 · 분류 · 한 줄 설명) — 공개 갤러리 페이지에서 모은 것
- `catalog_block()`             : 총괄 감독이 읽는 목록(분류별)
- `capture_refs()`              : slug → 참고 프레임 시트(JPEG 바이트), user/cache/motion_refs 에 캐시
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from ..paths import ROOT, USER_DIR
from ..util import LogFn, noop_log

CATALOG = ROOT / "assets" / "jitter_catalog.json"
CACHE = USER_DIR / "cache" / "motion_refs"
BASE = "https://jitter.video/template/"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,80}$")


def load_catalog(path: Path = CATALOG) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [d for d in data if isinstance(d, dict) and SLUG_RE.match(str(d.get("slug") or ""))]


def catalog_block(cat: Optional[list[dict[str, Any]]] = None, *, desc_chars: int = 110) -> str:
    """분류별 '`slug` 이름 — 설명' 목록. 총괄 감독이 시그니처 장면마다 하나를 `motion_ref` 로 고른다."""
    cat = load_catalog() if cat is None else cat
    if not cat:
        return ""
    groups: dict[str, list[dict[str, Any]]] = {}
    for d in cat:
        for c in d.get("categories") or ["etc"]:
            groups.setdefault(c, []).append(d)
    seen: set[str] = set()
    lines = ["## 모션 레퍼런스 목록(Jitter 공개 템플릿 — 움직임만 참고해 우리 스타일로 다시 짓는다)"]
    for c in sorted(groups):
        rows = []
        for d in groups[c]:
            if d["slug"] in seen:
                continue
            seen.add(d["slug"])
            desc = str(d.get("description") or "").strip()
            rows.append(f"- `{d['slug']}` {d.get('name', '')}" + (f" — {desc[:desc_chars]}" if desc else ""))
        if rows:
            lines.append(f"### {c}")
            lines += rows
    return "\n".join(lines) + "\n"


def known(slug: str, cat: Optional[list[dict[str, Any]]] = None) -> bool:
    cat = load_catalog() if cat is None else cat
    return any(d["slug"] == slug for d in cat)


def contact_sheet(frames: list[Path], cols: int = 4, cell_w: int = 420) -> Optional[bytes]:
    """참고 프레임 → 한 장(번호 붙임, 시간 순서)."""
    import io

    from PIL import Image, ImageDraw
    ims = []
    for f in frames:
        try:
            im = Image.open(f).convert("RGB")
        except OSError:
            continue
        k = cell_w / im.width
        ims.append(im.resize((cell_w, max(1, int(im.height * k)))))
    if not ims:
        return None
    ch = max(im.height for im in ims)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w + (cols + 1) * 8, rows * (ch + 26) + 8), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(ims):
        x, y = 8 + (i % cols) * (cell_w + 8), 8 + (i // cols) * (ch + 26)
        sheet.paste(im, (x, y + 18))
        d.text((x, y + 2), f"{i + 1}", fill=(240, 240, 240))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=84)
    return buf.getvalue()


def capture_refs(slugs: list[str], *, node: str, browser_executable: str = "", gl: str = "", work: Path,
                 log: LogFn = noop_log, cache: Path = CACHE, frames: int = 8, every_ms: int = 450,
                 ignore_cert_errors: bool = False, cancel=None) -> dict[str, bytes]:
    """slug → 참고 프레임 시트. 이미 찍은 것은 캐시에서. 실패한 것은 빠진다(장면은 레퍼런스 없이 지어진다)."""
    from ..paths import RENDERER_DIR
    from ..util import run_process, write_json
    out: dict[str, bytes] = {}
    todo = []
    for s in dict.fromkeys(x for x in slugs if SLUG_RE.match(x or "")):
        sheet = cache / s / "sheet.jpg"
        if sheet.exists():
            out[s] = sheet.read_bytes()
        else:
            todo.append(s)
    if not todo:
        return out
    job = {"browserExecutable": browser_executable, "gl": gl, "ignoreCertErrors": ignore_cert_errors,
           "refs": [{"id": s, "url": f"{BASE}{s}/", "outDir": str(cache / s), "frames": frames, "every": every_ms}
                    for s in todo]}
    work.mkdir(parents=True, exist_ok=True)
    job_file = work / "motion_ref_job.json"
    write_json(job_file, job)
    ok: set[str] = set()

    def on_line(line: str) -> None:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            return
        if ev.get("type") == "ref":
            if ev.get("ok"):
                ok.add(str(ev.get("id")))
            else:
                log(f"🎞 모션 레퍼런스 「{ev.get('id')}」 캡처 실패: {ev.get('error', '')[:120]}")
    try:
        run_process([node, str(RENDERER_DIR / "scripts" / "motion_ref.mjs"), str(job_file)], cwd=str(RENDERER_DIR),
                    on_line=on_line, cancel=cancel)
    except Exception as e:  # noqa: BLE001 - 레퍼런스는 덤
        log(f"🎞 모션 레퍼런스 캡처 실패: {e}")
    for s in todo:
        if s not in ok:
            continue
        frames_ = sorted((cache / s).glob("f*.jpg"))
        data = contact_sheet(frames_)
        if data:
            (cache / s / "sheet.jpg").write_bytes(data)
            out[s] = data
    if ok:
        log(f"🎞 모션 레퍼런스 {len(ok)}개 캡처(움직임 단계 {frames}장씩) — 🛠 빌더가 보고 다시 짓는다")
    return out
