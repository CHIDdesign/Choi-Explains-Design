"""여러 무료 스톡 제공처를 한 번에 검색하는 허브.

기본 순서: Pixabay(영상·사진, 한국어 검색) → Pexels(키가 있으면) → Coverr(영상) → Unsplash(사진)
→ Openverse(사진, 키 없이 항상 동작).
요청마다 제공처별 후보를 번갈아 섞어 최대 N개를 만들고, 🎞 자료 리서처가 썸네일 시트를 보고 고른다.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Optional

from ..util import LogFn, noop_log
from .base import StockCandidate, StockError, StockProvider


STOP = {"a", "an", "the", "of", "on", "in", "with", "and", "for", "to", "at", "by", "from", "into", "over",
        "under", "while", "is", "are", "its", "their", "his", "her", "very", "some"}
MIN_HITS = 3


def query_variants(q: str) -> list[str]:
    """스톡 검색은 단어를 모두 포함해야 걸린다(AND). 긴 묘사형 검색어는 결과가 0~1개라서 점점 줄여 본다.
    예: 'designer sketching wireframes on paper notebook'(1건) → 'designer sketching wireframes'(123건)."""
    q = re.sub(r"\s+", " ", (q or "").strip())
    if not q:
        return []
    core = [w for w in re.split(r"[\s,/]+", q) if w and w.lower() not in STOP]
    out = [q, " ".join(core), " ".join(core[:3]), " ".join(core[:2]), " ".join(core[-2:]), core[0] if core else ""]
    seen: list[str] = []
    for v in out:
        v = v.strip()
        if v and v.lower() not in [x.lower() for x in seen]:
            seen.append(v)
    return seen


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
        self.strikes: dict[str, int] = {}
        self.last_trace: list[str] = []

    @property
    def names(self) -> list[str]:
        return [p.name for p in self.providers]

    @classmethod
    def from_settings(cls, settings: Any, *, log: LogFn = noop_log, cache_dir: Optional[Path] = None) -> "StockHub":
        from .coverr import Coverr
        from .openverse import Openverse
        from .pexels import Pexels
        from .pixabay import Pixabay
        from .unsplash import Unsplash
        spec = [(Pixabay, getattr(settings, "pixabay_api_key", "")), (Pexels, getattr(settings, "pexels_api_key", "")),
                (Coverr, getattr(settings, "coverr_api_key", "")), (Unsplash, getattr(settings, "unsplash_access_key", ""))]
        provs = [cls_(key, log=log, cache_dir=cache_dir) for cls_, key in spec if key]
        if getattr(settings, "keyless_stock", True):
            provs.append(Openverse(log=log, cache_dir=cache_dir))
        return cls(provs, log=log)

    def check(self) -> str:
        """키가 있는 제공처를 한 번씩 불러 본다(키 오류·차단을 작업 초반에 드러냄). 결과 요약 문자열."""
        out = []
        for p in self.providers:
            if p.name == "Openverse":
                continue
            try:
                hits = p.search_photos("office", per_page=3)
                out.append(f"{p.name} 정상({len(hits)}건" + (f", 남은 호출 {p.remaining}" if p.remaining is not None else "")
                           + ")")
            except StockError as e:
                self.disabled[p.name] = str(e)
                out.append(f"⚠ {p.name}: {e}")
            except Exception as e:  # noqa: BLE001
                out.append(f"⚠ {p.name}: {type(e).__name__}: {str(e)[:120]}")
        return " · ".join(out) or "키가 있는 제공처 없음(Openverse 만)"

    def _call(self, p: StockProvider, method: str, query: str, **kw: Any) -> list[StockCandidate]:
        if p.name in self.disabled or not query:
            return []
        try:
            out = getattr(p, method)(query, **kw)
            self.strikes[p.name] = 0
            return out
        except StockError as e:
            # 예전엔 한 번 막히면(한도·일시 차단) 작업 끝까지 그 제공처를 껐다 → 뒤 요청이 전부 '후보 없음'.
            # 키 오류만 끄고, 일시 오류는 잠깐 쉬었다가 계속(3번 연속이면 끔).
            n = self.strikes.get(p.name, 0) + 1
            self.strikes[p.name] = n
            if e.fatal or n >= 3:
                self.disabled[p.name] = str(e)
                self.log(f"🎞 {p.name}: {e} → 이번 작업에서 제외")
            else:
                self.log(f"🎞 {p.name}: {e} → {4 * n}초 쉬고 계속")
                time.sleep(4 * n)
        except Exception as e:  # noqa: BLE001 - 네트워크 오류는 그 검색만 건너뜀
            self.log(f"🎞 {p.name} 검색 실패 '{query}': {e}")
        return []

    def search(self, st: dict[str, Any], n: int = 6) -> list[StockCandidate]:
        """영상 요청은 영상 제공처 → 부족하면 사진으로 넓힌다. 영어 검색어를 점점 줄여 가며, 그래도 없으면 한국어.
        self.last_trace 에 무엇을 몇 건 찾았는지 남긴다(진단용)."""
        qe, qk = st.get("query_en", ""), st.get("query_ko", "")
        out: list[StockCandidate] = []
        trace: list[str] = []
        kinds = ["video", "photo"] if st.get("kind", "video") == "video" else ["photo"]
        for kind in kinds:
            method = "search_videos" if kind == "video" else "search_photos"
            provs = [p for p in self.providers if (p.videos if kind == "video" else p.photos)]
            for q in query_variants(qe):
                groups = [self._call(p, method, q, per_page=n) for p in provs]
                trace.append(f"{kind} '{q}': " + ", ".join(f"{p.name} {len(g)}" for p, g in zip(provs, groups)))
                out = interleave([out] + groups, n)
                if len(out) >= MIN_HITS:
                    break
            if len(out) < MIN_HITS and qk:
                ko = [p for p in provs if p.korean]
                groups = [self._call(p, method, qk, per_page=n, locale="ko-KR") for p in ko]
                if ko:
                    trace.append(f"{kind} '{qk}'(ko): " + ", ".join(f"{p.name} {len(g)}" for p, g in zip(ko, groups)))
                out = interleave([out] + groups, n)
            if len(out) >= MIN_HITS:
                break
        self.last_trace = trace
        return out[:n]

    def download(self, c: StockCandidate, dst: Path) -> Path:
        p = next((p for p in self.providers if p.name == c.provider), None)
        if p is None:
            raise StockError(f"{c.provider} 제공처가 설정되어 있지 않습니다.")
        return p.download(c, dst)

    def remaining(self) -> dict[str, int]:
        return {p.name: p.remaining for p in self.providers if p.remaining is not None}
