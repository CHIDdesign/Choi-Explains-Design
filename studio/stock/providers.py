"""여러 무료 스톡 제공처를 한 번에 검색하는 허브.

기본 순서: Pixabay(영상·사진, 한국어 검색) → Pexels(키가 있으면) → Coverr(영상) → Unsplash(사진).
요청마다 제공처별 후보를 번갈아 섞어 최대 N개를 만들고, 🎞 자료 리서처가 썸네일 시트를 보고 고른다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..util import LogFn, noop_log
from .base import StockCandidate, StockError, StockProvider


def interleave(groups: list[list[StockCandidate]], n: int) -> list[StockCandidate]:
    out: list[StockCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    i = 0
    while len(out) < n and any(i < len(g) for g in groups):
        for g in groups:
            if i < len(g) and len(out) < n:
                c = g[i]
                k = (c.provider, c.kind, c.id)
                if k not in seen:
                    seen.add(k)
                    out.append(c)
        i += 1
    return out


class StockHub:
    def __init__(self, providers: list[StockProvider], *, log: LogFn = noop_log):
        self.providers = providers
        self.log = log
        self.disabled: dict[str, str] = {}

    @property
    def names(self) -> list[str]:
        return [p.name for p in self.providers]

    @classmethod
    def from_settings(cls, settings: Any, *, log: LogFn = noop_log, cache_dir: Optional[Path] = None) -> "StockHub":
        from .coverr import Coverr
        from .pexels import Pexels
        from .pixabay import Pixabay
        from .unsplash import Unsplash
        spec = [(Pixabay, getattr(settings, "pixabay_api_key", "")), (Pexels, getattr(settings, "pexels_api_key", "")),
                (Coverr, getattr(settings, "coverr_api_key", "")), (Unsplash, getattr(settings, "unsplash_access_key", ""))]
        provs = [cls_(key, log=log, cache_dir=cache_dir) for cls_, key in spec if key]
        return cls(provs, log=log)

    def _call(self, p: StockProvider, method: str, query: str, **kw: Any) -> list[StockCandidate]:
        if p.name in self.disabled or not query:
            return []
        try:
            return getattr(p, method)(query, **kw)
        except StockError as e:
            self.disabled[p.name] = str(e)
            self.log(f"🎞 {p.name}: {e} → 이번 작업에서 제외")
        except Exception as e:  # noqa: BLE001 - 네트워크 오류는 그 검색만 건너뜀
            self.log(f"🎞 {p.name} 검색 실패 '{query}': {e}")
        return []

    def search(self, st: dict[str, Any], n: int = 6) -> list[StockCandidate]:
        """영상 요청은 영상 제공처 → 부족하면 사진으로 넓힌다. 영어 검색어 우선, 부족하면 한국어."""
        qe, qk = st.get("query_en", ""), st.get("query_ko", "")
        out: list[StockCandidate] = []
        kinds = ["video", "photo"] if st.get("kind", "video") == "video" else ["photo"]
        for kind in kinds:
            method = "search_videos" if kind == "video" else "search_photos"
            provs = [p for p in self.providers if (p.videos if kind == "video" else p.photos)]
            groups = [self._call(p, method, qe, per_page=n) for p in provs]
            if sum(len(g) for g in groups) < 2 and qk:
                groups += [self._call(p, method, qk, per_page=n, locale="ko-KR") for p in provs if p.korean]
            out = interleave([out] + groups, n)
            if len(out) >= 2:
                break
        return out[:n]

    def download(self, c: StockCandidate, dst: Path) -> Path:
        p = next((p for p in self.providers if p.name == c.provider), None)
        if p is None:
            raise StockError(f"{c.provider} 제공처가 설정되어 있지 않습니다.")
        return p.download(c, dst)

    def remaining(self) -> dict[str, int]:
        return {p.name: p.remaining for p in self.providers if p.remaining is not None}
