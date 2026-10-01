"""앱 아이콘(창 아이콘 + 바탕화면 바로가기 .ico) — 외부 파일 없이 그려서 만든다."""
from __future__ import annotations

import sys
from pathlib import Path

ACCENT = (249, 49, 7)
INK = (17, 17, 17)


def draw_icon(size: int = 256):
    """잉크색 둥근 사각형 + 시그널 레드 재생 삼각형 + 흰 C."""
    from PIL import Image, ImageDraw
    s = size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(s * 0.22)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=r, fill=INK + (255,))
    w = max(2, int(s * 0.11))
    box = [int(s * 0.2), int(s * 0.2), int(s * 0.8), int(s * 0.8)]
    d.arc(box, start=40, end=320, fill=(245, 245, 242, 255), width=w)
    cx, cy = s * 0.53, s * 0.5
    t = s * 0.14
    d.polygon([(cx - t * 0.55, cy - t), (cx - t * 0.55, cy + t), (cx + t * 1.0, cy)], fill=ACCENT + (255,))
    return img


def write_ico(dst: Path) -> Path:
    img = draw_icon(256)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return dst


def qicon():
    """PySide6 QIcon(창 아이콘)."""
    from PIL.ImageQt import ImageQt
    from PySide6.QtGui import QIcon, QPixmap
    return QIcon(QPixmap.fromImage(ImageQt(draw_icon(256))))


if __name__ == "__main__":  # setup_windows.bat: python -m studio.gui.icon <out.ico>
    print(write_ico(Path(sys.argv[1] if len(sys.argv) > 1 else "choi_studio.ico")))
