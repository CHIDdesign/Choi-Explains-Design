"""Pixabay(무료 스톡 사진·영상, 상업적 이용 가능) API — 기본 스톡 제공처. 모션 장면용 벡터·일러스트도(search_images).

- 키: https://pixabay.com/api/docs/ 에 로그인하면 문서 안에 내 키가 바로 보인다(무료).
- 한도: 60초당 100회(X-RateLimit-*). "요청은 24시간 캐시" → 작업 폴더에 캐시.
- 이미지는 핫링크 금지 → 반드시 내려받아 쓴다(렌더러는 로컬 파일만 쓰므로 해당 없음).
- 한국어 검색(lang=ko)을 직접 지원한다.
- 출처: 필수는 아니지만 "어디서 왔는지 보여 달라" → 화면 ▣ 와 설명란에 "작가 / Pixabay" 자동 표기.
"""
from __future__ import annotations

from typing import Any, Optional

from .base import StockCandidate, StockError, StockProvider

API = "https://pixabay.com/api"


class Pixabay(StockProvider):
    name = "Pixabay"
    videos = True
    photos = True
    korean = True

    def __init__(self, api_key: str, **kw: Any):
        if not api_key:
            raise StockError("Pixabay API 키가 없습니다(설정 → 스톡).")
        super().__init__(**kw)
        self.key = api_key

    def _params(self, query: str, per_page: int, locale: str) -> dict[str, Any]:
        return {"key": self.key, "q": query[:100], "lang": "ko" if locale.lower().startswith("ko") else "en",
                "safesearch": "true", "per_page": max(3, min(200, per_page)), "order": "popular"}

    def search_videos(self, query: str, *, per_page: int = 6, locale: str = "", min_duration: int = 3
                      ) -> list[StockCandidate]:
        params = self._params(query, per_page, locale)
        params["video_type"] = "film"
        data = self._get_json(API + "/videos/", params)
        out = []
        for h in data.get("hits", []) or []:
            if float(h.get("duration") or 0) < min_duration:
                continue
            best = pick_rendition(h.get("videos") or {})
            if not best:
                continue
            thumb = next((v.get("thumbnail") for v in (h.get("videos") or {}).values()
                          if isinstance(v, dict) and v.get("thumbnail")), "")
            out.append(StockCandidate(
                kind="video", id=h["id"], url=h.get("pageURL", ""), thumb=thumb, download=best["url"],
                width=int(best.get("width") or 0), height=int(best.get("height") or 0),
                duration=float(h.get("duration") or 0), author=h.get("user", ""),
                author_url=f"https://pixabay.com/users/{h.get('user', '')}-{h.get('user_id', '')}/",
                alt=h.get("tags", ""), provider=self.name))
        return out

    def search_photos(self, query: str, *, per_page: int = 6, locale: str = "") -> list[StockCandidate]:
        params = self._params(query, per_page, locale)
        params.update(image_type="photo", orientation="horizontal", min_width=1280)
        data = self._get_json(API + "/", params)
        out = []
        for h in data.get("hits", []) or []:
            # fullHDURL/imageURL 은 '전체 API 접근' 승인 계정만 — 없으면 largeImageURL(최대 1280px)
            dl = h.get("imageURL") or h.get("fullHDURL") or h.get("largeImageURL") or ""
            if not dl:
                continue
            w, hgt = int(h.get("imageWidth") or 0), int(h.get("imageHeight") or 0)
            if not (h.get("imageURL") or h.get("fullHDURL")) and w and hgt:
                s = 1280 / max(w, hgt)
                w, hgt = int(w * min(1, s)), int(hgt * min(1, s))
            out.append(StockCandidate(
                kind="photo", id=h["id"], url=h.get("pageURL", ""), thumb=h.get("webformatURL") or h.get("previewURL", ""),
                download=dl, width=w, height=hgt, author=h.get("user", ""),
                author_url=f"https://pixabay.com/users/{h.get('user', '')}-{h.get('user_id', '')}/",
                alt=h.get("tags", ""), provider=self.name))
        return out


    def search_images(self, query: str, *, image_type: str = "vector", per_page: int = 6) -> list[StockCandidate]:
        """그래픽 소재: vector(대개 투명 PNG 오브젝트) · illustration · photo. 모션 장면 안 이미지 요소용."""
        params = self._params(query, per_page, "")
        params.update(image_type=image_type if image_type in ("vector", "illustration", "photo") else "vector")
        data = self._get_json(API + "/", params)
        out = []
        for h in data.get("hits", []) or []:
            dl = h.get("largeImageURL") or h.get("webformatURL") or ""
            if not dl:
                continue
            out.append(StockCandidate(
                kind="photo", id=h["id"], url=h.get("pageURL", ""),
                thumb=h.get("webformatURL") or h.get("previewURL", ""), download=dl,     # 비전 선택용(미리보기 150px 는 작다)
                width=int(h.get("webformatWidth") or 0), height=int(h.get("webformatHeight") or 0),
                author=h.get("user", ""), author_url=f"https://pixabay.com/users/{h.get('user', '')}-{h.get('user_id', '')}/",
                alt=h.get("tags", ""), provider=self.name))
        return out


def pick_rendition(videos: dict[str, Any]) -> Optional[dict[str, Any]]:
    """large(보통 1920×1080) → medium(1280×720) 순. 짧은 변 720 미만은 쓰지 않는다."""
    for tier in ("large", "medium"):
        v = videos.get(tier) or {}
        if v.get("url") and min(int(v.get("width") or 0), int(v.get("height") or 0)) >= 720:
            return v
    return None
