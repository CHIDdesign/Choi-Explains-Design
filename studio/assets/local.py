"""④ 자료 폴더 색인 — 화자 자신의 자료(과제물·스케치·화면 캡처)가 어떤 스톡보다 강한 증거다(03 문서 2절 원칙 3).

자료 리서처에게 파일 목록(M번호 · 이름 · 크기)과 썸네일 시트 한 장을 함께 준다 — 이름만으로는 무엇인지 모르는 파일
('IMG_2034.jpg')도 눈으로 보고 `local_file` 을 고르게. 영상·PDF 는 아직 색인하지 않는다(이미지만) — 지원하지 않는 파일은
목록에 '이미지로 넣어 달라'고 적고(`other_files`), 조달 뒤 어느 파일이 화면에 배치됐는지 센다(`used_files` — 2026-10-04
채널 주인: "참고자료를 줘도 제대로 쓰지 않는다": 안 쓴 파일은 자료 리서처 보충 호출로 다시 배치하고 리포트에 남긴다).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ..broll.images import IMAGE_EXT, list_local_images, match_local

SHEET_MAX = 24
SKIP_EXT = {".txt", ".md", ".json", ".ini", ".db", ".ds_store"}


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


def other_files(folder: Optional[str | Path]) -> list[Path]:
    """자료 폴더의 이미지가 아닌 파일(PDF·PPTX·영상·문서) — 아직 색인하지 않으니 사용자에게 알린다."""
    if not folder or not Path(folder).is_dir():
        return []
    return sorted(f for f in Path(folder).rglob("*") if f.is_file() and not f.name.startswith(".")
                  and f.suffix.lower() not in IMAGE_EXT and f.suffix.lower() not in SKIP_EXT)


def listing(items: list[LocalItem], others: list[Path] = ()) -> str:
    lines = []
    if not items:
        lines.append("(자료 폴더에 이미지가 없다 — 화자 자신의 작업을 말하는 문장은 own_material + fallback: code_drawn, notes 에 필요한 파일)")
    lines += [f"- {it.key} `{it.name}`" + (f" ({it.w}×{it.h})" if it.w else "") for it in items[:80]]
    if others:
        lines.append("- (이미지가 아니라 아직 못 읽는 파일: " + ", ".join(f"`{p.name}`" for p in others[:12])
                     + (" …" if len(others) > 12 else "") + " — PNG·JPG 로 저장해 넣으면 쓴다)")
    return "\n".join(lines)


def own_name(path: Path) -> str:
    """조달 사다리가 자료 폴더 파일을 복사할 때 쓰는 이름의 줄기(`own_<이름>`, studio/assets/ladder.py _add_file)."""
    return Path("own_" + re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", path.name)[-60:]).stem


def used_files(items: list[LocalItem], outcomes: list[dict[str, Any]]) -> set[str]:
    """조달 결과에 실제로 들어간 자료 폴더 파일 이름들(화면에 배치된 것)."""
    stems = {own_name(it.path): it.name for it in items}
    used: set[str] = set()
    for o in outcomes or []:
        for a in (o.get("assets") or []) if isinstance(o, dict) else []:
            stem = Path(str((a or {}).get("path") or "")).stem
            stem = re.sub(r"\.full\.h\d+$", "", stem)
            if stem in stems:
                used.add(stems[stem])
    return used


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
