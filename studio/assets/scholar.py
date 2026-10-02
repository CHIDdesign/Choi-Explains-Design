"""1차 자료(논문·책·기사) — 서지 해석 → 출처 카드(03 문서 3절 primary_source).

자료 리서처는 확실한 것만 `citation`(저자·연도·제목·저널 중)과 아는 `doi` 를 적는다. 앱이 Crossref 로 확인하고,
**일치하는 문헌이 없으면 출처 카드를 만들지 않는다**(지어낸 서지를 사실처럼 화면에 내지 않는다).
일치 = 연도가 맞고(인용에 연도가 있으면) 저자 성이 인용에 있거나 제목이 거의 같다.
출처 카드는 서지 사실을 우리가 조판한 것(자체 제작) — 논문 첫 쪽 캡처(C 등급)는 설정 allow_quote 일 때만.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from .. import __version__, net
from ..util import LogFn, noop_log

CROSSREF = "https://api.crossref.org/works"
SELECT = "DOI,title,author,container-title,issued,volume,issue,page,publisher,type,score"


def _ua() -> str:
    # Crossref 예절: 앱 이름과 연락처(저장소 주소) — 사용자 정보는 넣지 않는다
    return f"ChoiStudio/{__version__} (https://github.com/chiddesign/choi-explains-design)"


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", " ", (s or "").lower()).strip()


def _year(item: dict[str, Any]) -> str:
    for k in ("issued", "published-print", "published-online", "created"):
        parts = ((item.get(k) or {}).get("date-parts") or [[None]])[0]
        if parts and parts[0]:
            return str(parts[0])
    return ""


def _authors(item: dict[str, Any]) -> list[str]:
    return [str(a.get("family") or a.get("name") or "").strip() for a in item.get("author") or []
            if (a.get("family") or a.get("name"))]


def author_line(names: list[str]) -> str:
    """Jansson & Smith · Leahy et al."""
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} & {names[1]}"
    return f"{names[0]} et al."


def matches(citation: str, item: dict[str, Any]) -> bool:
    """서지 데이터베이스의 후보가 리서처가 적은 인용과 같은 문헌인가 — 보수적으로."""
    from rapidfuzz import fuzz
    cit = _norm(citation)
    if not cit:
        return False
    y = _year(item)
    years = re.findall(r"(?<!\d)(1[5-9]\d\d|20\d\d)(?!\d)", citation)
    if years and y and y not in years:
        return False
    title = _norm(" ".join(item.get("title") or []))
    surnames = [_norm(a) for a in _authors(item)]
    by_author = any(s and re.search(rf"(^|\s){re.escape(s)}(\s|$)", cit) for s in surnames[:3])
    by_title = bool(title) and (fuzz.partial_ratio(title, cit) >= 88 if len(title) >= 12 else title in cit)
    if by_author and (by_title or years):
        return True
    return by_title and len(title) >= 12


def _meta(item: dict[str, Any]) -> dict[str, Any]:
    doi = str(item.get("DOI") or "")
    names = _authors(item)
    return {"title": " ".join(item.get("title") or []).strip(), "authors": author_line(names), "author_list": names[:8],
            "journal": " ".join(item.get("container-title") or []).strip(), "year": _year(item),
            "volume": str(item.get("volume") or ""), "issue": str(item.get("issue") or ""),
            "pages": str(item.get("page") or ""), "publisher": str(item.get("publisher") or ""),
            "doi": doi, "url": f"https://doi.org/{doi}" if doi else "", "type": str(item.get("type") or "")}


class Scholar:
    def __init__(self, *, cache_dir: Optional[Path] = None, log: LogFn = noop_log):
        self.cache_dir = cache_dir
        self.log = log

    def _get(self, url: str, params: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        r = net.request(url, params=params, headers={"User-Agent": _ua(), "Accept": "application/json"}, timeout=25,
                        rounds=2)
        if r.status == 404:
            return None
        if not r.ok:
            raise RuntimeError(f"Crossref HTTP {r.status}")
        data = r.json()
        return data if isinstance(data, dict) else None

    def resolve(self, citation: str, doi: str = "") -> Optional[dict[str, Any]]:
        """인용 → 확인된 서지 메타(제목·저자·저널·연도·권·호·쪽·DOI) 또는 None. 네트워크 오류는 '없음'으로 캐시하지 않는다."""
        citation, doi = (citation or "").strip(), (doi or "").strip().removeprefix("https://doi.org/")
        if not (citation or doi):
            return None
        cache = None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            from ..util import text_hash
            cache = self.cache_dir / f"cr_{text_hash(citation, doi)[:16]}.json"
            if cache.exists():
                data = json.loads(cache.read_text(encoding="utf-8"))
                return data or None
        found: Optional[dict[str, Any]] = None
        errored = False
        try:
            if doi:
                data = self._get(f"{CROSSREF}/{quote(doi, safe='/')}")
                item = (data or {}).get("message") or {}
                # DOI 가 있어도 인용과 어긋나면(리서처가 다른 DOI 를 적음) 쓰지 않는다
                if item and (not citation or matches(citation, item)):
                    found = _meta(item)
            if found is None and citation:
                data = self._get(CROSSREF, {"query.bibliographic": citation, "rows": "5", "select": SELECT})
                for item in ((data or {}).get("message") or {}).get("items") or []:
                    if matches(citation, item):
                        found = _meta(item)
                        break
        except Exception as e:  # noqa: BLE001 - 서지 확인 실패는 출처 카드 없이
            self.log(f"📚 서지 확인 실패({citation[:40] or doi}): {e}")
            errored = True
        if cache and (found or not errored):
            cache.write_text(json.dumps(found or {}, ensure_ascii=False), encoding="utf-8")
        return found


def source_card(meta: dict[str, Any], *, label: str = "", locator: str = "") -> dict[str, Any]:
    """출처 카드(ArchiveCard variant=source) 데이터 — 사실만: 제목 · 저자 · 저널(권·호) · 연도 · DOI."""
    vol = meta.get("volume", "")
    jr = meta.get("journal", "") + (f" {vol}" if vol else "") + (f"({meta['issue']})" if meta.get("issue") else "")
    rows = [{"k": "저자", "v": meta.get("authors", "")}, {"k": "저널" if meta.get("journal") else "출판",
                                                           "v": jr.strip() or meta.get("publisher", "")},
            {"k": "연도", "v": meta.get("year", "")}]
    if meta.get("doi"):
        rows.append({"k": "DOI", "v": meta["doi"]})
    return {"variant": "source", "title": meta.get("title", "")[:90], "rows": [r for r in rows if r["v"]],
            "label": label, "quote": locator[:60], "ref": meta.get("url", "")}


def short_credit(meta: dict[str, Any]) -> str:
    """화면 출처 줄: '{저자} ({연도}), {저널}'."""
    out = meta.get("authors", "")
    if meta.get("year"):
        out += f" ({meta['year']})"
    if meta.get("journal"):
        out += f", {meta['journal']}"
    return out.strip(", ")


def full_credit(meta: dict[str, Any]) -> str:
    parts = [f"{meta.get('authors', '')} ({meta.get('year', '')}). {meta.get('title', '')}."]
    if meta.get("journal"):
        parts.append(f"{meta['journal']}" + (f" {meta['volume']}" if meta.get("volume") else "")
                     + (f"({meta['issue']})" if meta.get("issue") else "")
                     + (f", {meta['pages']}" if meta.get("pages") else "") + ".")
    if meta.get("url"):
        parts.append(meta["url"])
    return " ".join(parts)
