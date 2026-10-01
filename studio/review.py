"""검토 시트: 완성 영상을 2.5초마다 한 장씩 뽑아 시간·그 순간 자막과 함께 격자로 붙인다(부가자료/검토시트_*.jpg).

영상을 끝까지 돌려 보지 않아도 '어디에 그래픽이 비었는지, 자막이 말과 맞는지, 얼굴을 가리는지'를 한눈에 본다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .media.ffmpeg import FFmpeg


def _font(size: int):
    from PIL import ImageFont
    from .paths import RENDERER_FONTS
    for f in [Path(RENDERER_FONTS) / "ui" / "Pretendard-SemiBold.otf", Path("C:/Windows/Fonts/malgunbd.ttf"),
              Path("C:/Windows/Fonts/malgun.ttf")]:
        if f.exists():
            try:
                return ImageFont.truetype(str(f), size)
            except OSError:
                pass
    return ImageFont.load_default(size=size)


def caption_at(cues: list[dict[str, Any]], t: float) -> str:
    for c in cues:
        if c["start"] <= t < c["end"]:
            return " ".join(w["text"] for line in c["lines"] for w in line)
    return ""


def review_sheets(ff: FFmpeg, video: Path, cues: list[dict[str, Any]], dst_prefix: Path, *, every: float = 2.5,
                  title: str = "") -> list[Path]:
    """video → dst_prefix_01.jpg, _02.jpg … (세로 영상은 한 줄에 6장, 가로는 4장)"""
    from PIL import Image, ImageDraw
    info = ff.probe(video)
    w, h = info.display_size
    vertical = h > w
    cell_w = 230 if vertical else 440
    cols, rows = (6, 3) if vertical else (4, 5)
    frames = list(ff.iter_frames(video, fps=1.0 / every, width=cell_w, info=info))
    if not frames:
        return []
    cell_h = frames[0][1].shape[0]
    cap_h = 46
    pad = 10
    head = 46
    font, small = _font(17), _font(15)
    out: list[Path] = []
    per = cols * rows
    for page in range((len(frames) + per - 1) // per):
        chunk = frames[page * per:(page + 1) * per]
        n_rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new("RGB", (pad + cols * (cell_w + pad), head + n_rows * (cell_h + cap_h + pad) + pad),
                          (18, 18, 20))
        d = ImageDraw.Draw(sheet)
        d.text((pad, 12), f"{title}  ·  {page + 1}/{(len(frames) + per - 1) // per}  ·  {every:g}초 간격", font=font,
               fill=(235, 235, 235))
        for k, (t, bgr) in enumerate(chunk):
            x = pad + (k % cols) * (cell_w + pad)
            y = head + (k // cols) * (cell_h + cap_h + pad)
            sheet.paste(Image.fromarray(np.ascontiguousarray(bgr[..., ::-1])), (x, y))
            tc = f"{int(t // 60):02d}:{t % 60:04.1f}"
            d.rectangle([x, y, x + 62, y + 20], fill=(0, 0, 0))
            d.text((x + 4, y + 2), tc, font=small, fill=(255, 196, 0))
            cap = caption_at(cues, t)
            if cap:
                while cap and d.textlength(cap, font=small) > cell_w * 2 - 8:
                    cap = cap[:-1]
                lines = [cap]
                if d.textlength(cap, font=small) > cell_w - 6:
                    cut = len(cap)
                    while cut > 1 and d.textlength(cap[:cut], font=small) > cell_w - 6:
                        cut -= 1
                    lines = [cap[:cut], cap[cut:]]
                for j, ln in enumerate(lines[:2]):
                    d.text((x + 3, y + cell_h + 3 + j * 20), ln, font=small, fill=(210, 210, 210))
        p = dst_prefix.with_name(f"{dst_prefix.name}_{page + 1:02d}.jpg")
        p.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(p, quality=82)
        out.append(p)
    return out
