"""Pexels(무료 스톡 영상·사진) API 클라이언트.

- 키는 https://www.pexels.com/ko-kr/api/ 에서 무료 발급(설정 → 스톡 탭).
- 요청 헤더 `Authorization: <키>`. 기본 한도 시간당 200회·월 2만 회 → 결과를 작업 폴더에 캐시.
- Pexels 가이드라인: Pexels 링크와 작가 크레딧 표기 → 화면 ▣ 크레딧 + 설명란 출처 목록에 자동 기록.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..util import LogFn, noop_log

API = "https://api.pexels.com"


@dataclass
class StockCandidate:
    kind: str                # video | photo
    id: int
    url: str                 # Pexels 페이지
    thumb: str               # 미리보기 이미지(선택용)
    download: str            # 실제 파일 URL
    width: int
    height: int
    duration: float = 0.0
    author: str = ""
    author_url: str = ""
    alt: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def credit(self) -> str:
        return f"{self.author or 'Pexels'} / Pexels"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StockCandidate":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


class PexelsError(RuntimeError):
    pass


class Pexels:
    def __init__(self, api_key: str, *, log: LogFn = noop_log, cache_dir: Optional[Path] = None, session=None):
        if not api_key:
            raise PexelsError("Pexels API 키가 없습니다(설정 → 스톡).")
        import requests
        self.session = session or requests.Session()
        self.session.headers["Authorization"] = api_key
        self.session.headers["User-Agent"] = "ChoiStudio (+https://www.pexels.com)"
        self.log = log
        self.cache_dir = cache_dir
        self.remaining: Optional[int] = None

    # ------------------------------------------------------------------
    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        key = None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^0-9A-Za-z가-힣]+", "_", json.dumps(params, ensure_ascii=False, sort_keys=True))[:120]
            key = self.cache_dir / f"px_{path.strip('/').replace('/', '_')}_{slug}.json"
            if key.exists():
                return json.loads(key.read_text(encoding="utf-8"))
        for attempt in range(3):
            r = self.session.get(API + path, params=params, timeout=25)
            rem = r.headers.get("X-Ratelimit-Remaining")
            if rem is not None and rem.isdigit():
                self.remaining = int(rem)
            if r.status_code == 429:
                wait = min(30, 5 * (attempt + 1))
                self.log(f"Pexels 한도 초과 → {wait}s 대기")
                time.sleep(wait)
                continue
            if r.status_code in (401, 403):
                raise PexelsError("Pexels API 키가 올바르지 않습니다(401/403).")
            r.raise_for_status()
            data = r.json()
            if key:
                key.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        raise PexelsError("Pexels 요청이 계속 한도에 걸렸습니다.")

    # ------------------------------------------------------------------
    def search_videos(self, query: str, *, orientation: str = "landscape", min_duration: int = 4,
                      per_page: int = 8, locale: str = "") -> list[StockCandidate]:
        params: dict[str, Any] = {"query": query, "orientation": orientation, "size": "medium",
                                  "per_page": per_page, "min_duration": min_duration}
        if locale:
            params["locale"] = locale
        data = self._get("/videos/search", params)
        out = []
        for v in data.get("videos", []) or []:
            f = pick_video_file(v.get("video_files") or [], orientation)
            if not f:
                continue
            user = v.get("user") or {}
            out.append(StockCandidate(
                kind="video", id=int(v["id"]), url=v.get("url", ""), thumb=v.get("image", ""),
                download=f["link"], width=int(f.get("width") or v.get("width") or 0),
                height=int(f.get("height") or v.get("height") or 0), duration=float(v.get("duration") or 0),
                author=user.get("name", ""), author_url=user.get("url", ""),
                extra={"fps": f.get("fps"), "quality": f.get("quality")}))
        return out

    def search_photos(self, query: str, *, orientation: str = "landscape", per_page: int = 8,
                      locale: str = "") -> list[StockCandidate]:
        params: dict[str, Any] = {"query": query, "orientation": orientation, "size": "large", "per_page": per_page}
        if locale:
            params["locale"] = locale
        data = self._get("/v1/search", params)
        out = []
        for p in data.get("photos", []) or []:
            src = p.get("src") or {}
            original = src.get("original") or src.get("large2x") or ""
            if not original:
                continue
            sep = "&" if "?" in original else "?"
            out.append(StockCandidate(
                kind="photo", id=int(p["id"]), url=p.get("url", ""), thumb=src.get("medium") or src.get("small", ""),
                download=f"{original}{sep}auto=compress&cs=tinysrgb&w=2400", width=int(p.get("width") or 0),
                height=int(p.get("height") or 0), author=p.get("photographer", ""),
                author_url=p.get("photographer_url", ""), alt=p.get("alt", "")))
        return out

    def download(self, url: str, dst: Path) -> Path:
        if dst.exists() and dst.stat().st_size > 0:
            return dst
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(dst.suffix + ".part")
        with self.session.get(url, timeout=120, stream=True) as r:
            r.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        tmp.replace(dst)
        return dst


def pick_video_file(files: list[dict[str, Any]], orientation: str = "landscape") -> Optional[dict[str, Any]]:
    """1080p 이상에서 가장 가벼운 mp4(4K 는 디코딩이 무거워 1080~1440 우선)."""
    mp4 = [f for f in files if (f.get("file_type") or "").endswith("mp4") and f.get("link")]
    if not mp4:
        return None

    def short_side(f: dict[str, Any]) -> int:
        w, h = int(f.get("width") or 0), int(f.get("height") or 0)
        return min(w, h) if w and h else 0

    good = [f for f in mp4 if 1080 <= short_side(f) <= 1440 and (f.get("fps") or 30) <= 60]
    if good:
        return min(good, key=short_side)
    bigger = [f for f in mp4 if short_side(f) > 1440]
    if bigger:
        return min(bigger, key=short_side)
    return max(mp4, key=short_side)
