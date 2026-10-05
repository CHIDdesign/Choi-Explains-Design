"""🎯 취향 — 레퍼런스 보드와 장면 평가 기억(채널 주인 2026-10-04: "디자인 taste 를 대폭 업그레이드할 방안").

말로 된 디자인 규칙보다 **그림 몇 장**이 취향을 더 정확히 전한다. 디자이너(모션·카드·시그니처·스타일 프레임)와 심사(아트 디렉터·
시안 심사)는 매번 이 보드를 그림으로 본다.

- 레퍼런스 보드: `user/taste/` 에 운영자가 넣은 그림(좋아하는 영상의 정지 화면 등). 저장소에는 넣지 않는다(CLAUDE.md 규칙).
- 장면 평가 기억: 결과 화면 '장면 평가'에서 장면마다 👍/👎 + 한 줄 → `user/taste/memory.json`, 그 장면의 정지 화면은
  `liked/`·`disliked/` 로 복사 → 다음 작업부터 보드(좋아한 장면 · 싫어한 장면)와 메모 블록으로 들어간다. 쓸수록 운영자 취향으로 모인다.
- 운영자 그림이 하나도 없으면 파이프라인이 렌더로 확인한 하우스 예시 카드(prompts/examples/card_examples.json)를 보드로 쓴다.
- 🎯 레퍼런스 분석기(`reference.py`, 창의 '레퍼런스 분석' · run_reference.bat): 끌어다 놓은 사진·영상을 재고 Claude 가 규칙으로 옮긴 것
  (`refs/<slug>.json` + 컷 시트)이 보드 그림(`ref_sheets`)과 지시 끝 블록(`rules_block`)으로 디자인 역할마다 들어간다.
"""
from __future__ import annotations

import io
import json
import shutil
import time
from pathlib import Path
from typing import Any, Optional

from ..paths import USER_DIR

TASTE_DIR = USER_DIR / "taste"
EXTS = (".jpg", ".jpeg", ".png", ".webp")
Image3 = tuple[str, bytes, str]


def taste_dir() -> Path:
    TASTE_DIR.mkdir(parents=True, exist_ok=True)
    readme = TASTE_DIR / "여기에_레퍼런스_그림을_넣으세요.txt"
    if not readme.exists():
        readme.write_text("좋아하는 영상·모션 디자인의 정지 화면(jpg·png)을 이 폴더에 넣으면, 모든 디자이너와 심사가 매번 그림으로 봅니다.\n"
                          "liked/·disliked/ 는 결과 화면의 '장면 평가'가 채웁니다.\n", encoding="utf-8")
    return TASTE_DIR


def _images_in(d: Path, limit: int) -> list[Path]:
    if not d.exists():
        return []
    fs = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in EXTS]
    return sorted(fs, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def sheet(paths: list[Path], *, cols: int = 3, cell_w: int = 640) -> Optional[bytes]:
    """그림 여러 장 → 한 장(번호 없이, 비율 유지, 칸 높이는 16:9). 읽지 못한 그림은 건너뛴다."""
    from PIL import Image
    ims = []
    for p in paths:
        try:
            with Image.open(p) as im:
                ims.append(im.convert("RGB").copy())
        except Exception:  # noqa: BLE001
            continue
    if not ims:
        return None
    cols = min(cols, len(ims))
    ch = int(cell_w * 9 / 16)
    rows = (len(ims) + cols - 1) // cols
    out = Image.new("RGB", (cols * cell_w + (cols + 1) * 10, rows * ch + (rows + 1) * 10), (30, 30, 30))
    for i, im in enumerate(ims):
        im.thumbnail((cell_w, ch))
        x = 10 + (i % cols) * (cell_w + 10) + (cell_w - im.width) // 2
        y = 10 + (i // cols) * (ch + 10) + (ch - im.height) // 2
        out.paste(im, (x, y))
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=86)
    return buf.getvalue()


def board_images(*, refs: int = 8, liked: int = 6, disliked: int = 4) -> list[Image3]:
    """디자인 역할에게 보낼 보드(최대 세 장): 운영자 레퍼런스 · 좋아한 장면 · 싫어한 장면(피할 것)."""
    d = TASTE_DIR
    out: list[Image3] = []
    for paths, label in ((_images_in(d, refs), "운영자 레퍼런스 보드"),
                         (_images_in(d / "liked", liked), "운영자가 좋아한 장면(👍)"),
                         (_images_in(d / "disliked", disliked), "운영자가 싫어한 장면(👎 — 피할 것)")):
        data = sheet(paths) if paths else None
        if data:
            out.append((label, data, "image/jpeg"))
    # 🎯 레퍼런스 분석기가 만든 컷 시트(영상 레퍼런스는 샷마다 한 칸) — 규칙 블록(reference.rules_block)과 짝
    try:
        from . import reference
        out += reference.ref_sheets()
    except Exception:  # noqa: BLE001 - 시트 없이도 짓는다
        pass
    return out


def load_memory() -> list[dict[str, Any]]:
    try:
        data = json.loads((TASTE_DIR / "memory.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [m for m in data if isinstance(m, dict)] if isinstance(data, list) else []


def notes_block(limit: int = 24) -> str:
    """최근 장면 평가 메모 → 디자인 역할의 지시 끝 블록. 메모가 없으면 ''."""
    mem = [m for m in load_memory() if m.get("verdict") in ("up", "down") and (m.get("note") or m.get("title"))]
    if not mem:
        return ""
    lines = ["## 🎯 운영자 취향 메모(장면 평가 — 최근 순, 이 취향으로 맞춘다)"]
    for m in mem[-limit:][::-1]:
        mark = "👍" if m["verdict"] == "up" else "👎"
        what = " · ".join(x for x in (str(m.get("kind") or ""), str(m.get("title") or "")[:40]) if x)
        lines.append(f"- {mark} {what}" + (f" — {str(m['note'])[:160]}" if m.get("note") else ""))
    return "\n".join(lines) + "\n"


def record(entries: list[dict[str, Any]], *, job: str) -> int:
    """장면 평가 저장: entries = [{gid, verdict(up|down), note, title, kind, still(경로)}] → memory.json 에 붙이고, 정지 화면은
    liked/·disliked/ 로 복사. 같은 작업·같은 장면을 다시 평가하면 앞의 것을 바꾼다. 저장한 개수."""
    d = taste_dir()
    mem = load_memory()
    keep = [m for m in mem if not (m.get("job") == job and any(m.get("gid") == e.get("gid") for e in entries))]
    n = 0
    for e in entries:
        v = e.get("verdict")
        if v not in ("up", "down"):
            continue
        item = {"ts": int(time.time()), "job": job, "gid": str(e.get("gid") or ""), "verdict": v,
                "note": str(e.get("note") or "").strip()[:300], "title": str(e.get("title") or "")[:80],
                "kind": str(e.get("kind") or "")[:24]}
        src = Path(str(e.get("still") or ""))
        if src.is_file():
            sub = d / ("liked" if v == "up" else "disliked")
            sub.mkdir(parents=True, exist_ok=True)
            other = d / ("disliked" if v == "up" else "liked")
            name = f"{job[:40]}_{item['gid']}{src.suffix.lower() or '.jpg'}"
            (other / name).unlink(missing_ok=True)
            shutil.copyfile(src, sub / name)
            item["still"] = str(sub / name)
        keep.append(item)
        n += 1
    (d / "memory.json").write_text(json.dumps(keep[-400:], ensure_ascii=False, indent=1), encoding="utf-8")
    return n
