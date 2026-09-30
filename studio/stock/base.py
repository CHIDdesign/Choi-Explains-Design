"""무료 스톡 API 공통 부분: 후보 데이터, 오류, 캐시·한도 처리가 들어간 GET, 다운로드."""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .. import net
from ..util import LogFn, noop_log


@dataclass
class StockCandidate:
    kind: str                # video | photo
    id: str
    url: str                 # 소재 페이지(출처 링크)
    thumb: str               # 미리보기 이미지(선택용)
    download: str            # 실제 파일 URL
    width: int
    height: int
    duration: float = 0.0
    author: str = ""
    author_url: str = ""
    alt: str = ""
    provider: str = "Pexels"  # Pixabay | Unsplash | Coverr | Pexels
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id)

    @property
    def credit(self) -> str:
        if self.provider == "Unsplash" and self.author:
            return f"Photo by {self.author} on Unsplash"  # Unsplash 가이드라인 표기
        return f"{self.author} / {self.provider}" if self.author else self.provider

    @property
    def key(self) -> str:
        """파일 이름용(제공처가 달라도 겹치지 않게)."""
        return f"{self.provider.lower()[:2]}{self.kind[0]}{re.sub(r'[^0-9A-Za-z_-]', '', self.id)[:40]}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StockCandidate":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


class StockError(RuntimeError):
    """키가 없거나 틀림, 한도 초과 등 — 그 제공처를 이번 작업에서 끈다."""


class StockProvider:
    """제공처 공통: 작업 폴더 캐시, 429 재시도, 남은 호출 수. 통신은 studio.net(여러 방식 + 실패 이유 기록)."""

    name = "stock"
    videos = False
    photos = False
    korean = False           # 한국어 검색어를 직접 받는가
    remaining_header = "X-Ratelimit-Remaining"

    def __init__(self, *, log: LogFn = noop_log, cache_dir: Optional[Path] = None, session=None):
        import requests
        self.session = session or requests.Session()   # 다운로드 집계(Unsplash·Coverr)용
        self.log = log
        self.cache_dir = cache_dir
        self.remaining: Optional[int] = None

    # ------------------------------------------------------------------
    def _cache_path(self, url: str, params: dict[str, Any]) -> Optional[Path]:
        if not self.cache_dir:
            return None
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        safe = {k: v for k, v in params.items() if k not in ("key", "api_key", "client_id")}  # 키는 파일명에 넣지 않는다
        slug = re.sub(r"[^0-9A-Za-z가-힣]+", "_", json.dumps(safe, ensure_ascii=False, sort_keys=True))[:120]
        path = re.sub(r"[^0-9A-Za-z]+", "_", url.split("//", 1)[-1])[:60]
        return self.cache_dir / f"{self.name.lower()}_{path}_{slug}.json"

    def _get_json(self, url: str, params: dict[str, Any], headers: Optional[dict[str, str]] = None) -> Any:
        cache = self._cache_path(url, params)
        if cache and cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        for attempt in range(3):
            try:
                r = net.request(url, params=params, headers=headers or {}, timeout=25)
            except net.NetError as e:
                raise StockError(f"{self.name} 에 연결하지 못했습니다 — {e}") from e
            rem = r.headers.get(self.remaining_header) or r.headers.get("X-RateLimit-Remaining")
            if rem is not None and str(rem).isdigit():
                self.remaining = int(rem)
            if r.status == 429:
                reset = r.headers.get("X-RateLimit-Reset")
                wait = min(60, int(reset) + 1) if reset and reset.isdigit() else min(30, 5 * (attempt + 1))
                self.log(f"{self.name} 한도 초과 → {wait}s 대기")
                time.sleep(wait)
                continue
            if r.status in (400, 401) and ("key" in r.text.lower() or r.status == 401):
                raise StockError(f"{self.name} API 키가 올바르지 않습니다({r.status}: {r.text[:80]}).")
            if r.status == 403:
                raise StockError(f"{self.name} 가 요청을 막았습니다(HTTP 403, 모든 접속 방식 실패).")
            if not r.ok:
                raise RuntimeError(f"{self.name} HTTP {r.status}: {r.text[:120]}")
            data = r.json()
            if cache:
                cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        raise StockError(f"{self.name} 요청이 계속 한도에 걸렸습니다.")

    # ------------------------------------------------------------------
    def search_videos(self, query: str, *, per_page: int = 6, locale: str = "") -> list[StockCandidate]:
        return []

    def search_photos(self, query: str, *, per_page: int = 6, locale: str = "") -> list[StockCandidate]:
        return []

    def register_download(self, c: StockCandidate) -> None:
        """다운로드 집계가 필요한 제공처(Unsplash·Coverr)만 구현."""

    def download(self, c: StockCandidate, dst: Path) -> Path:
        if dst.exists() and dst.stat().st_size > 0:
            return dst
        net.download(c.download, dst, timeout=180)
        try:
            self.register_download(c)
        except Exception as e:  # noqa: BLE001 - 집계 실패는 작업을 막지 않는다
            self.log(f"{self.name} 다운로드 집계 실패: {e}")
        return dst
