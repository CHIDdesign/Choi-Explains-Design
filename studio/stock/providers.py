"""여러 무료 스톡 제공처를 한 번에 검색하는 허브.

기본 순서: Pixabay(영상·사진, 한국어 검색) → Pexels(키가 있으면) → Coverr(영상) → Unsplash(사진)
→ Openverse(사진, 키 없이 항상 동작).
요청마다 제공처별 후보를 번갈아 섞어 최대 N개를 만들고, 🎞 자료 리서처가 썸네일 시트를 보고 고른다.
검색 중 오류: 키 오류(StockError.fatal)만 그 제공처를 이번 작업에서 끄고, 연결 실패·일시 차단·한도는 잠시 쉬었다가
계속 쓴다(3번 연속이면 끈다).
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
# 줄일 때 먼저 버리는 뜻 없는 동사 — 'designer working on laptop' 을 줄이면 'designer working' 이 아니라
# 'designer laptop' 이어야 한다(무엇이 보여야 하는지는 명사가 말한다)
VAGUE = {"working", "using", "doing", "making", "having", "getting", "looking", "showing", "being", "taking"}
MIN_HITS = 3
# 한국어 검색(제공처의 자체 번역)에서 다른 뜻으로 번역되는 낱말 — 문맥상 흔한 뜻으로 풀어 쓴다
KO_AMBIGUOUS = {"노트북": "노트북 컴퓨터", "마우스": "컴퓨터 마우스", "모니터": "컴퓨터 모니터", "패드": "태블릿",
                "태블릿": "태블릿 컴퓨터", "폰": "스마트폰", "앱": "스마트폰 앱", "키보드": "컴퓨터 키보드",
                "프린터": "사무용 프린터", "펜": "필기용 펜"}


def ko_query(q: str) -> str:
    """한국어 대체 검색어의 동음이의어를 풀어 쓴다('노트북' → '노트북 컴퓨터'). 이미 풀어 쓴 것은 그대로."""
    q = re.sub(r"\s+", " ", (q or "").strip())
    return KO_AMBIGUOUS.get(q, q)


def query_variants(q: str, *, min_words: int = 1) -> list[str]:
    """스톡 검색은 단어를 모두 포함해야 걸린다(AND). 긴 묘사형 검색어는 결과가 0~1개라서 점점 줄여 본다.
    예: 'designer sketching wireframes on paper notebook'(1건) → 'designer sketching wireframes'(123건).
    줄일 때 뜻 없는 동사(working·using …)를 먼저 버려 보여야 할 명사가 남게 한다.
    min_words: 이보다 짧게 줄이지 않는다 — 한 낱말까지 줄이면 동음이의어가 걸린다(2026-10-04 'foam mockup' → 'foam' → 파도 거품)."""
    q = re.sub(r"\s+", " ", (q or "").strip())
    if not q:
        return []
    core = [w for w in re.split(r"[\s,/]+", q) if w and w.lower() not in STOP]
    if len([w for w in core if w.lower() not in VAGUE]) >= 2:
        core = [w for w in core if w.lower() not in VAGUE]
    out = [q, " ".join(core), " ".join(core[:3]), " ".join(core[:2]), " ".join(core[-2:]), core[0] if core else ""]
    floor = min(min_words, len(core)) if core else 1
    out = [v for v in out if len(v.split()) >= floor]
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
                if e.fatal:              # 키 오류만 끈다 — 연결 끊김·일시 차단 한 번으로 작업 내내 빼지 않게(_call 과 같은 기준)
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
        """영상 요청은 영상 제공처 → 부족하면 사진으로 넓힌다. 영어 검색어를 점점 줄여 가며(두 낱말까지), 그래도 없으면 한국어.
        리서처가 준 다른 각도 검색어(alt_queries — 역추상화: 손·과정·장소·질감)가 있으면 첫 검색어와 함께 찾아 후보를 섞는다 —
        비전 선택이 한 가지 해석만 보지 않게. self.last_trace 에 무엇을 몇 건 찾았는지 남긴다(진단용)."""
        qe, qk = st.get("query_en", ""), st.get("query_ko", "")
        alts = [str(q).strip() for q in st.get("alt_queries") or [] if str(q or "").strip()][:2]
        out: list[StockCandidate] = []
        trace: list[str] = []
        kinds = ["video", "photo"] if st.get("kind", "video") == "video" else ["photo"]
        for kind in kinds:
            method = "search_videos" if kind == "video" else "search_photos"
            provs = [p for p in self.providers if (p.videos if kind == "video" else p.photos)]
            per_q: list[list[StockCandidate]] = []
            for q0 in [qe] + alts:
                got: list[StockCandidate] = []
                for q in query_variants(q0, min_words=2):
                    groups = [self._call(p, method, q, per_page=n) for p in provs]
                    trace.append(f"{kind} '{q}': " + ", ".join(f"{p.name} {len(g)}" for p, g in zip(provs, groups)))
                    got = interleave([got] + groups, n)
                    if len(got) >= MIN_HITS:
                        break
                per_q.append(got)
            out = interleave([out] + per_q, n)
            if len(out) < MIN_HITS and qk:
                ko = [p for p in provs if p.korean]
                qk = ko_query(qk)
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
