"""④ 자료 폴더 색인 — 화자 자신의 자료(과제물·스케치·화면 캡처)가 어떤 스톡보다 강한 증거다(03 문서 2절 원칙 3).

자료 리서처에게 파일 목록(M번호 · 이름 · 크기)과 썸네일 시트 한 장을 함께 준다 — 이름만으로는 무엇인지 모르는 파일
('IMG_2034.jpg')도 눈으로 보고 `local_file` 을 고르게. 영상·PDF 는 아직 색인하지 않는다(이미지만).
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..broll.images import list_local_images, match_local

SHEET_MAX = 24


@dataclass
class LocalItem:
    key: str            # "M1"
    path: Path
    w: int = 0
    h: int = 0

    @property
    def name(self) -> str:
        return self.path.name


def index(folder: Optional[str | Path]) -> list[LocalItem]:
    from PIL import Image
    out = []
    for i, p in enumerate(list_local_images(folder), start=1):
        w = h = 0
        try:
            with Image.open(p) as im:
                w, h = im.size
        except Exception:  # noqa: BLE001 - 열리지 않는 파일은 크기 없이
            pass
        out.append(LocalItem(f"M{i}", p, w, h))
    return out


def listing(items: list[LocalItem]) -> str:
    if not items:
        return "(자료 폴더가 비어 있다 — 화자 자신의 작업을 말하는 문장은 own_material + fallback: code_drawn, notes 에 필요한 파일)"
    return "\n".join(f"- {it.key} `{it.name}`" + (f" ({it.w}×{it.h})" if it.w else "") for it in items[:80])


def sheet(items: list[LocalItem]) -> Optional[bytes]:
    """M번호 라벨을 단 썸네일 격자(최대 24장) — 없으면 None."""
    if not items:
        return None
    from ..stock.research import contact_sheet
    thumbs = []
    for it in items[:SHEET_MAX]:
        data = None
        try:
            from PIL import Image
            with Image.open(it.path) as im:
                im = im.convert("RGB")
                im.thumbnail((400, 400))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=80)
                data = buf.getvalue()
        except Exception:  # noqa: BLE001
            data = None
        thumbs.append((it.key, data))
    return contact_sheet(thumbs, contain=True)


def find(items: list[LocalItem], local_file: str, *names: str) -> Optional[LocalItem]:
    """리서처가 적은 파일 이름(정확히 → 확장자 없이 → M번호) → 이름·대상 이름으로 비슷한 파일."""
    lf = (local_file or "").strip()
    if lf:
        for it in items:
            if lf in (it.name, it.path.stem, it.key):
                return it
        low = lf.lower()
        for it in items:
            if it.name.lower() == low or it.path.stem.lower() == low:
                return it
    paths = [it.path for it in items]
    for n in (lf, *names):
        if n:
            hit = match_local(n, paths)
            if hit is not None:
                return next(it for it in items if it.path == hit)
    return None
