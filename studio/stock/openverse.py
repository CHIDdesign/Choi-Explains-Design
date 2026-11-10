"""Openverse(워드프레스 재단의 CC 이미지 검색 — Flickr·위키미디어 등 수억 장) — **키 없이** 동작하는 사진 제공처.

키를 하나도 넣지 않아도 B-roll 사진을 가져올 수 있게 항상 마지막 순서로 켜 둔다.
익명 호출은 분당·일일 한도가 있어 작업 폴더에 결과를 캐시한다. 출처는 "작가 / Openverse(원본 사이트)".
"""
from __future__ import annotations

from typing import Any

from .base import StockCandidate, StockProvider

API = "https://api.openverse.org/v1/images/"
AUDIO_API = "https://api.openverse.org/v1/audio/"


class Openverse(StockProvider):
    name = "Openverse"
    photos = True

    def __init__(self, key: str = "", **kw: Any):
        super().__init__(**kw)

    def search_photos(self, query: str, *, per_page: int = 6, locale: str = "") -> list[StockCandidate]:
        if locale.lower().startswith("ko"):
            return []
        # 상업적 이용·변형이 허용된 것만(유튜브 채널 = 상업, 자르고 색을 입힘 = 변형) — 10/1 테스트에 CC BY-NC 가 들어갔다
        data = self._get_json(API, {"q": query, "page_size": max(1, min(20, per_page * 2)), "aspect_ratio": "wide",
                                    "mature": "false", "license_type": "commercial,modification"})
        out: list[StockCandidate] = []
        for r in data.get("results", []) or []:
            w, h = int(r.get("width") or 0), int(r.get("height") or 0)
            if not r.get("url") or (w and w < 900) or not license_ok(r.get("license", "")):
                continue
            src = r.get("source") or r.get("provider") or ""
            out.append(StockCandidate(
                kind="photo", id=r.get("id", ""), url=r.get("foreign_landing_url") or r.get("url", ""),
                thumb=r.get("thumbnail") or r.get("url", ""), download=r["url"], width=w, height=h,
                author=r.get("creator") or "", alt=r.get("title") or "", provider=self.name,
                extra={"license": r.get("license", ""), "license_version": str(r.get("license_version") or ""),
                       "source": src, "attribution": r.get("attribution") or ""}))
            if len(out) >= per_page:
                break
        return out

    def search_audio(self, query: str, *, per_page: int = 20, max_sec: float = 3.0) -> list[dict[str, Any]]:
        """효과음 입고 후보: CC0 이고 짧은 소리만 → 매니페스트 항목의 재료. Openverse 의 라이선스는 원문보다 늦을 수 있다
        (2026-11-10: cc0 로 나온 Freesound 한 곡이 원문에서는 CC BY-NC) — 켜기 전에 page 를 확인한다."""
        data = self._get_json(AUDIO_API, {"q": query, "page_size": max(1, min(20, per_page)), "license": "cc0", "mature": "false"})
        out: list[dict[str, Any]] = []
        for r in data.get("results", []) or []:
            sec = float(r.get("duration") or 0) / 1000.0
            if r.get("url") and r.get("license") == "cc0" and 0 < sec <= max_sec:
                out.append({"title": r.get("title") or "", "url": r["url"], "page": r.get("foreign_landing_url") or "", "duration": sec,
                            "source": r.get("source") or "", "license": license_label(r["license"], str(r.get("license_version") or ""))})
        return out


def license_ok(code: str) -> bool:
    """Openverse 라이선스 코드(by · by-sa · cc0 · pdm · by-nc · by-nd · by-nc-sa · by-nc-nd · sampling+ …) — 비상업(nc)·
    변경 금지(nd)·샘플링은 버린다. 서버 필터(license_type)를 믿지 않고 응답마다 한 번 더 본다."""
    c = (code or "").strip().lower()
    if not c:
        return False
    parts = set(c.replace("+", "-").split("-"))
    return not ({"nc", "nd", "sampling"} & parts) and c in {"by", "by-sa", "cc0", "pdm"}


def license_label(code: str, version: str = "") -> str:
    c = (code or "").lower()
    if c == "cc0":
        return "CC0"
    if c == "pdm":
        return "Public Domain"
    return f"CC {c.upper()}" + (f" {version}" if version else "")
