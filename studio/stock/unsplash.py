"""Unsplash(고해상도 사진, 상업적 이용 가능) API — 사진 전용.

- 키: https://unsplash.com/developers → New Application → Access Key. 데모 등급은 시간당 50회.
- 인증 헤더 `Authorization: Client-ID <키>`.
- API 가이드라인: 사진을 내려받을 때마다 `links.download_location` 에 GET(다운로드 집계) → 자동으로 호출.
- 출처 필수: "Photo by 작가 on Unsplash" — 화면 ▣ 와 설명란(사진 페이지 링크 포함)에 자동 표기.
- 한국어 검색(lang)은 승인된 앱만 → 영어 검색어만 쓴다. Unsplash+(유료) 사진은 제외.
"""
from __future__ import annotations

from typing import Any

from .base import StockCandidate, StockError, StockProvider

API = "https://api.unsplash.com"


class Unsplash(StockProvider):
    name = "Unsplash"
    photos = True

    def __init__(self, access_key: str, **kw: Any):
        if not access_key:
            raise StockError("Unsplash Access Key 가 없습니다(설정 → 스톡).")
        super().__init__(**kw)
        self.auth = {"Authorization": f"Client-ID {access_key}", "Accept-Version": "v1"}

    def search_photos(self, query: str, *, per_page: int = 6, locale: str = "") -> list[StockCandidate]:
        if locale.lower().startswith("ko"):
            return []
        data = self._get_json(API + "/search/photos", {"query": query, "per_page": max(1, min(30, per_page)),
                                                         "orientation": "landscape", "content_filter": "high"},
                              headers=self.auth)
        out = []
        for p in data.get("results", []) or []:
            if p.get("premium") or p.get("plus"):
                continue
            urls = p.get("urls") or {}
            raw = urls.get("raw") or ""
            if not raw:
                continue
            sep = "&" if "?" in raw else "?"
            user = p.get("user") or {}
            links = p.get("links") or {}
            out.append(StockCandidate(
                kind="photo", id=p["id"], url=links.get("html", ""), thumb=urls.get("small") or urls.get("thumb", ""),
                download=f"{raw}{sep}w=2400&q=85&fm=jpg", width=int(p.get("width") or 0),
                height=int(p.get("height") or 0), author=user.get("name", ""),
                author_url=(user.get("links") or {}).get("html", ""), alt=p.get("alt_description") or "",
                provider=self.name, extra={"download_location": links.get("download_location", "")}))
        return out

    def register_download(self, c: StockCandidate) -> None:
        loc = (c.extra or {}).get("download_location")
        if loc:
            self.session.get(loc, headers=self.auth, timeout=20)
