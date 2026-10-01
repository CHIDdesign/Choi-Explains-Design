"""세로 사진 → 크림 종이 여백 액자(16:10).

예전엔 세로로 긴 이미지(인물 전신·책 표지·포스터)를 버렸고(가로/세로 < 0.5~0.55), 남긴 세로 초상은 가로 액자에 가운데만
잘려 들어가 머리가 잘리기도 했다. 여기서는 세로(가로/세로 < 1.0) 이미지를 로고 카드와 같은 크림 종이(1600×1000) 위
가운데에 통째로 놓는다 — 모든 사진 자리(cover)에 그대로 들어가고, 렌더러는 로고 카드처럼(사진용 어둠·필름 룩 없이) 그린다.
(docs/upgrade/03_자료_조달_엔진_v2.md P0-11)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

CARD_W, CARD_H = 1600, 1000
PAPER = (0xF5, 0xF2, 0xEA)          # renderer tokens.ts NOTE.paper
PHOTO_H = 0.74                      # 사진 높이(카드 높이 대비) — 아래에 이름 자리(로고 카드와 같은 자리)
CENTER_Y = 0.44


def is_tall(path: Path, limit: float = 1.0) -> bool:
    from PIL import Image
    try:
        with Image.open(path) as im:
            w, h = im.size
    except Exception:  # noqa: BLE001 - 열 수 없으면 손대지 않는다
        return False
    return h > 0 and w / h < limit


def mat_tall(path: Path, limit: float = 1.0) -> Optional[Path]:
    """세로 이미지면 여백 액자 JPEG(`<이름>_mat.jpg`)을 만들어 그 경로를, 아니면 None."""
    from PIL import Image, ImageFilter, ImageOps
    if not is_tall(path, limit):
        return None
    dst = path.with_name(f"{path.stem}_mat.jpg")
    if dst.exists():
        return dst
    with Image.open(path) as src:
        im = ImageOps.exif_transpose(src).convert("RGB")
    h = int(CARD_H * PHOTO_H)
    w = max(1, round(im.width * h / im.height))
    if w > CARD_W * 0.9:                       # 아주 넓은 경우는 없지만(세로만 온다) 안전하게
        w = int(CARD_W * 0.9)
        h = max(1, round(im.height * w / im.width))
    im = im.resize((w, h), Image.LANCZOS)
    border = max(6, round(h * 0.012))         # 인화지 흰 테두리
    framed = ImageOps.expand(im, border=border, fill=(252, 251, 247))
    card = Image.new("RGB", (CARD_W, CARD_H), PAPER)
    x = (CARD_W - framed.width) // 2
    y = int(CARD_H * CENTER_Y - framed.height / 2)
    shadow = Image.new("L", (CARD_W, CARD_H), 0)
    shadow.paste(60, (x + 6, y + 10, x + framed.width + 6, y + framed.height + 10))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    card.paste(Image.new("RGB", (CARD_W, CARD_H), (60, 50, 40)), (0, 0), shadow)
    card.paste(framed, (x, y))
    dst.parent.mkdir(parents=True, exist_ok=True)
    card.save(dst, "JPEG", quality=92)
    return dst
