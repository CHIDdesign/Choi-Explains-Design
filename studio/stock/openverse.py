"""Openverse(워드프레스 재단의 CC 이미지 검색 — Flickr·위키미디어 등 수억 장) — **키 없이** 동작하는 사진 제공처.

키를 하나도 넣지 않아도 B-roll 사진을 가져올 수 있게 항상 마지막 순서로 켜 둔다.
익명 호출은 분당·일일 한도가 있어 작업 폴더에 결과를 캐시한다. 출처는 "작가 / Openverse(원본 사이트)".
"""
from __future__ import annotations

from typing import Any

from .base import StockCandidate, StockProvider

API = "https://api.openverse.org/v1/images/"


class Openverse(StockProvider):
    name = "Openverse"
    photos = True

    def __init__(self, key: str = "", **kw: Any):
        super().__init__(**kw)

    def search_photos(self, query: str, *, per_page: int = 6, locale: str = "") -> list[StockCandidate]:
        if locale.lower().startswith("ko"):
            return []
        data = self._get_json(API, {"q": query, "page_size": max(1, min(20, per_page * 2)), "aspect_ratio": "wide",
                                    "mature": "false"})
        out: list[StockCandidate] = []
        for r in data.get("results", []) or []:
            w, h = int(r.get("width") or 0), int(r.get("height") or 0)
            if not r.get("url") or (w and w < 900):
                continue
            src = r.get("source") or r.get("provider") or ""
            out.append(StockCandidate(
                kind="photo", id=r.get("id", ""), url=r.get("foreign_landing_url") or r.get("url", ""),
                thumb=r.get("thumbnail") or r.get("url", ""), download=r["url"], width=w, height=h,
                author=r.get("creator") or "", alt=r.get("title") or "", provider=self.name,
                extra={"license": r.get("license", ""), "source": src}))
            if len(out) >= per_page:
                break
        return out
