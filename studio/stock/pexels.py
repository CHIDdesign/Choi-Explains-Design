"""Pexels(무료 스톡 영상·사진) API — 선택 제공처(신규 키 발급이 막힌 경우가 있어 기본은 Pixabay).

- 키: https://www.pexels.com/ko-kr/api/ (이미 가진 키가 있으면 설정 → 스톡에 넣으면 함께 검색한다).
- 헤더 `Authorization: <키>`. 기본 한도 시간당 200회·월 2만 회.
- 가이드라인: Pexels 링크와 작가 크레딧 → 화면 ▣ 크레딧 + 설명란 출처 목록에 자동 기록.
"""
from __future__ import annotations

from typing import Any, Optional

from .base import StockCandidate, StockError, StockProvider

API = "https://api.pexels.com"

PexelsError = StockError  # 이전 이름 호환


class Pexels(StockProvider):
    name = "Pexels"
    videos = True
    photos = True
    korean = True  # locale=ko-KR

    def __init__(self, api_key: str, **kw: Any):
        if not api_key:
            raise StockError("Pexels API 키가 없습니다(설정 → 스톡).")
        super().__init__(**kw)
        self.auth = {"Authorization": api_key}

    def search_videos(self, query: str, *, per_page: int = 6, locale: str = "", min_duration: int = 4,
                      orientation: str = "landscape") -> list[StockCandidate]:
        params: dict[str, Any] = {"query": query, "orientation": orientation, "size": "medium",
                                  "per_page": per_page, "min_duration": min_duration}
        if locale:
            params["locale"] = locale
        data = self._get_json(API + "/videos/search", params, headers=self.auth)
        out = []
        for v in data.get("videos", []) or []:
            f = pick_video_file(v.get("video_files") or [])
            if not f:
                continue
            user = v.get("user") or {}
            out.append(StockCandidate(
                kind="video", id=v["id"], url=v.get("url", ""), thumb=v.get("image", ""),
                download=f["link"], width=int(f.get("width") or v.get("width") or 0),
                height=int(f.get("height") or v.get("height") or 0), duration=float(v.get("duration") or 0),
                author=user.get("name", ""), author_url=user.get("url", ""), provider=self.name,
                extra={"fps": f.get("fps"), "quality": f.get("quality")}))
        return out

    def search_photos(self, query: str, *, per_page: int = 6, locale: str = "",
                      orientation: str = "landscape") -> list[StockCandidate]:
        params: dict[str, Any] = {"query": query, "orientation": orientation, "size": "large", "per_page": per_page}
        if locale:
            params["locale"] = locale
        data = self._get_json(API + "/v1/search", params, headers=self.auth)
        out = []
        for p in data.get("photos", []) or []:
            src = p.get("src") or {}
            original = src.get("original") or src.get("large2x") or ""
            if not original:
                continue
            sep = "&" if "?" in original else "?"
            out.append(StockCandidate(
                kind="photo", id=p["id"], url=p.get("url", ""), thumb=src.get("medium") or src.get("small", ""),
                download=f"{original}{sep}auto=compress&cs=tinysrgb&w=2400", width=int(p.get("width") or 0),
                height=int(p.get("height") or 0), author=p.get("photographer", ""),
                author_url=p.get("photographer_url", ""), alt=p.get("alt", ""), provider=self.name))
        return out


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
