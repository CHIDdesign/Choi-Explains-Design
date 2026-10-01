"""Coverr(시네마틱 스톡 영상) API — 영상 전용, 선택 사항.

- 키: https://coverr.co/developers (Coverr 계정 → 앱 만들기). 데모 등급은 시간당 50회.
- 인증 헤더 `Authorization: Bearer <키>`. 검색 `GET /videos?query=…&urls=true`.
- 내려받으면 `PATCH /videos/{id}/stats/downloads` 로 다운로드를 알린다(자동).
- 출처 필수(Coverr 는 앱에 로고·링크 표기를 요구) → 화면 ▣ 와 설명란에 "Coverr" 자동 표기.
- 주의: Coverr 문서의 상업적 이용 문구가 페이지마다 다르다(developers 페이지는 허용, docs 소개 페이지는
  "상업적 이용 금지"). 수익 채널이면 https://coverr.co/license 를 직접 확인한 뒤 켜세요.
"""
from __future__ import annotations

from typing import Any

from .base import StockCandidate, StockError, StockProvider

API = "https://api.coverr.co"


class Coverr(StockProvider):
    name = "Coverr"
    videos = True

    def __init__(self, api_key: str, **kw: Any):
        if not api_key:
            raise StockError("Coverr API 키가 없습니다(설정 → 스톡).")
        super().__init__(**kw)
        self.auth = {"Authorization": f"Bearer {api_key}"}

    def search_videos(self, query: str, *, per_page: int = 6, locale: str = "", min_duration: int = 3
                      ) -> list[StockCandidate]:
        if locale.lower().startswith("ko"):
            return []
        data = self._get_json(API + "/videos", {"query": query, "page_size": max(1, min(50, per_page)),
                                                "urls": "true", "sort": "popular"}, headers=self.auth)
        out = []
        for v in data.get("hits", []) or []:
            urls = v.get("urls") or {}
            dl = urls.get("mp4_download") or urls.get("mp4") or ""
            if not dl or v.get("is_vertical") or float(v.get("duration") or 0) < min_duration:
                continue
            out.append(StockCandidate(
                kind="video", id=v["id"], url=f"https://coverr.co/videos/{v['id']}", thumb=v.get("thumbnail") or
                v.get("poster", ""), download=dl, width=int(v.get("max_width") or 0),
                height=int(v.get("max_height") or 0), duration=float(v.get("duration") or 0), author="",
                alt=v.get("title", ""), provider=self.name))
        return out

    def register_download(self, c: StockCandidate) -> None:
        self.session.patch(f"{API}/videos/{c.id}/stats/downloads", headers=self.auth, timeout=20)
