"""영상 정지 화면(포스터) — 입력 영상 미리보기와 결과 카드에 쓴다. 한 번 만들면 캐시."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional


def poster_path(video: str) -> Path:
    from ..paths import USER_DIR
    st = Path(video).stat()
    key = hashlib.sha1(f"{video}|{st.st_size}|{st.st_mtime}".encode()).hexdigest()[:16]
    return USER_DIR / "cache" / "posters" / f"{key}.jpg"


def make_poster(video: str) -> Optional[Path]:
    """영상 3초 지점(짧으면 첫 프레임)의 정지 화면."""
    out = poster_path(video)
    if out.exists():
        return out
    try:
        from ..media.ffmpeg import FFmpeg, hdr_to_sdr_filter
        ff = FFmpeg()
        info = ff.probe(video)
        out.parent.mkdir(parents=True, exist_ok=True)
        t = 3.0 if info.duration > 6 else 0.0
        ff.grab_frame(video, t, out, width=1280, extra_vf=hdr_to_sdr_filter() if info.is_hdr else "")
        return out if out.exists() else None
    except Exception:  # noqa: BLE001 - 정지 화면은 없어도 된다
        return None
