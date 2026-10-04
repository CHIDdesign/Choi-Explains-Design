"""미술관 오픈 액세스(키 없음) — 이름 있는 작품·제품·사물의 **소장 기관 사진**(CC0·퍼블릭 도메인만).

채널 주인 2026-10-04: "내용에 들어갈 자료를 더 폭넓고 이해가 되게 찾아" — 위키미디어에 없는 디자인사 실물(토넷 의자, 아르누보 포스터,
빈 공방의 은그릇…)은 소장 기관이 직접 찍은 깨끗한 사진이 있다. 2026-10-04 이 환경에서 직접 불러 본 결과:
- 시카고 미술관(Art Institute of Chicago) `api.artic.edu` — 키 없음, `is_public_domain` 필터, IIIF 1686px. 'Thonet chair' → Rocking
  Chair(Kohn), Side Chair(Michael Thonet). 이미지 서버는 브라우저형 User-Agent 가 없으면 403.
- 메트로폴리탄 미술관(The Met) — 검색 `/public/collection/v1/search` 는 2026-10-01 폐지, `/v1.1/search`(offset·limit)로 바뀌었다.
  검색 결과에 퍼블릭 도메인이 아닌 것도 섞여 있어 객체마다 `isPublicDomain`·`primaryImage` 를 다시 본다.
- 클리블랜드 미술관 `openaccess-api.clevelandart.org` — `cc0=1&has_image=1`.
- 1930년대 이후 디자인(바우하우스·브로이어·브라운)은 대부분 저작권이 남아 이미지가 없다 — 그 자리는 위키미디어·인용·모션 몫.
검색은 느슨해서(시카고 'Bauhaus' → 쇠라의 그림) 제목·작가·종류에 검색어의 낱말이 하나도 없는 결과는 버린다. 고르기는 비전이 한다.
후보 모양은 커먼즈 후보(assets/commons.py)와 같다 — 사다리의 비전 선택·받기·출처 표기를 그대로 탄다.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

from .. import net
from ..util import LogFn, noop_log
from .license import classify

AIC = "https://api.artic.edu/api/v1/artworks/search"
AIC_IIIF = "https://www.artic.edu/iiif/2/{id}/full/{w},/0/default.jpg"
CMA = "https://openaccess-api.clevelandart.org/api/artworks/"
MET_SEARCH = "https://collectionapi.metmuseum.org/public/collection/v1.1/search"
MET_OBJECT = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{id}"
CONTACT = "https://github.com/chiddesign/choi-explains-design"
UA = f"Mozilla/5.0 (compatible; ChoiStudio/1.0; +{CONTACT})"
INSTITUTIONS = {"aic": "Art Institute of Chicago", "cma": "The Cleveland Museum of Art",
                "met": "The Metropolitan Museum of Art"}
STOP = {"the", "and", "with", "for", "from", "of", "a", "an", "in", "on", "by", "de", "la", "le", "no", "nr"}


def fold(s: Any) -> str:
    """악센트·대소문자를 접은 소문자(Gebrüder → gebruder)."""
    t = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(ch for ch in t if not unicodedata.combining(ch)).lower()


def terms(q: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", fold(q)) if len(w) >= 3 and w not in STOP]


def relevant(query: str, m: dict[str, Any]) -> bool:
    """제목·작가·종류·설명에 검색어 낱말이 들어 있어야 — 낱말이 둘 이상이면 둘 이상(느슨한 검색이 엉뚱한 그림을 1위로 준다:
    시카고 'Bauhaus' → 쇠라, 'Michael Thonet' → 화가 William Michael Harnett)."""
    ts = terms(query)
    if not ts:
        return False
    hay = fold(" ".join(str(m.get(k) or "") for k in ("title", "artist", "kind", "description")))
    # 다섯 글자 이상은 낱말 안에서도(Armchair ⊃ chair), 짧은 것은 낱말 머리에서만(party ⊅ art)
    hit = sum(1 for t in ts if (t in hay if len(t) >= 5 else re.search(rf"\b{re.escape(t)}", hay)))
    return hit >= min(2, len(ts))


class Museums:
    """search(query) → 후보 메타(커먼즈 후보와 같은 키 + origin='museum'·institution·thumb_url)."""

    def __init__(self, *, cache_dir: Optional[Path] = None, log: LogFn = noop_log,
                 get: Optional[Callable[..., Any]] = None, sources: tuple[str, ...] = ("aic", "met", "cma")):
        self.cache_dir = cache_dir
        self.log = log
        self._get_raw = get or net.request
        self.sources = sources
        self.headers = {"User-Agent": UA, "AIC-User-Agent": f"ChoiStudio ({CONTACT})", "Accept": "application/json"}

    # ------------------------------------------------------------------
    def _get(self, url: str, params: Optional[dict[str, Any]] = None) -> Any:
        key = hashlib.sha1(json.dumps([url, params or {}], sort_keys=True).encode()).hexdigest()[:20]
        cache = self.cache_dir / f"museum_{key}.json" if self.cache_dir else None
        if cache and cache.exists():
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except ValueError:
                pass
        r = self._get_raw(url, params=params, headers=self.headers, timeout=20, rounds=1)
        if not r.ok:
            raise RuntimeError(f"HTTP {r.status}")
        data = r.json()
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    @staticmethod
    def _cand(src: str, *, oid: Any, title: str, artist: str, date: str, kind: str, page: str, url: str, thumb: str,
              w: int, h: int, medium: str = "") -> dict[str, Any]:
        inst = INSTITUTIONS[src]
        lic = classify("CC0")             # 세 기관 모두 퍼블릭 도메인 작품 이미지를 CC0 로 공개한다
        desc = " · ".join(x for x in (title, date, medium, inst) if x)
        name = re.sub(r"[\\/:*?\"<>|]+", " ", f"{title} ({inst} {oid}).jpg")[:120]
        return {"name": name, "url": url, "thumb_url": thumb, "orig_url": url, "width": int(w or 0),
                "height": int(h or 0), "mime": "image/jpeg", "page": page, "artist": artist[:80], "title": title,
                "kind": kind, "year": date, "description": desc[:300], "license": lic.name, "lic": lic.to_dict(),
                "tier": lic.tier, "src": f"museum:{src}", "origin": "museum", "institution": inst}

    # ------------------------------------------------------------------
    def aic(self, query: str, limit: int) -> list[dict[str, Any]]:
        data = self._get(AIC, {"q": query, "limit": str(limit * 2), "query[term][is_public_domain]": "true",
                               "fields": "id,title,artist_display,date_display,image_id,is_public_domain,thumbnail,"
                                         "medium_display,artwork_type_title"}) or {}
        out = []
        for d in data.get("data") or []:
            th = d.get("thumbnail") or {}
            if not (d.get("is_public_domain") and d.get("image_id")):
                continue
            w0, h0 = int(th.get("width") or 0), int(th.get("height") or 0)
            w = min(1686, w0) if w0 else 1686
            h = round(h0 * w / w0) if w0 and h0 else 0
            out.append(self._cand("aic", oid=d["id"], title=str(d.get("title") or ""),
                                  artist=str(d.get("artist_display") or "").split("\n")[0].strip(),   # 첫 줄 = 이름
                                  date=str(d.get("date_display") or ""), kind=str(d.get("artwork_type_title") or ""),
                                  medium=str(d.get("medium_display") or ""),
                                  page=f"https://www.artic.edu/artworks/{d['id']}",
                                  url=AIC_IIIF.format(id=d["image_id"], w=w), thumb=AIC_IIIF.format(id=d["image_id"], w=400),
                                  w=w, h=h))
        return out

    def cma(self, query: str, limit: int) -> list[dict[str, Any]]:
        data = self._get(CMA, {"q": query, "cc0": "1", "has_image": "1", "limit": str(limit * 2)}) or {}
        out = []
        for d in data.get("data") or []:
            im = d.get("images") or {}
            big = im.get("print") or im.get("web") or {}
            web = im.get("web") or big
            if str(d.get("share_license_status") or "").upper() != "CC0" or not big.get("url"):
                continue
            who = "; ".join(str(c.get("description") or "") for c in d.get("creators") or [] if c.get("description"))
            out.append(self._cand("cma", oid=d.get("accession_number") or d.get("id"), title=str(d.get("title") or ""),
                                  artist=who, date=str(d.get("creation_date") or ""), kind=str(d.get("type") or ""),
                                  medium=str(d.get("technique") or ""), page=str(d.get("url") or ""),
                                  url=big["url"], thumb=web.get("url") or big["url"],
                                  w=int(big.get("width") or 0), h=int(big.get("height") or 0)))
        return out

    def met(self, query: str, limit: int) -> list[dict[str, Any]]:
        data = self._get(MET_SEARCH, {"q": query, "hasImages": "true", "limit": str(limit * 2), "offset": "0"}) or {}
        ids = [i for i in (data.get("objectIDs") or [])][: limit * 2]

        def one(oid: Any) -> Optional[dict[str, Any]]:
            try:
                d = self._get(MET_OBJECT.format(id=oid)) or {}
            except Exception:  # noqa: BLE001 - 객체 하나의 실패로 나머지를 버리지 않는다
                return None
            if not (d.get("isPublicDomain") and d.get("primaryImage")):
                return None
            return self._cand("met", oid=oid, title=str(d.get("title") or ""), artist=str(d.get("artistDisplayName") or ""),
                              date=str(d.get("objectDate") or ""), kind=str(d.get("objectName") or ""),
                              medium=str(d.get("medium") or ""), page=str(d.get("objectURL") or ""),
                              url=d["primaryImage"], thumb=d.get("primaryImageSmall") or d["primaryImage"], w=0, h=0)
        with ThreadPoolExecutor(max_workers=4) as ex:
            return [m for m in ex.map(one, ids) if m]

    # ------------------------------------------------------------------
    def search(self, query: str, *, limit: int = 6) -> list[dict[str, Any]]:
        """기관마다 찾아 섞는다(기관 하나의 실패는 건너뜀). 검색어 낱말이 하나도 맞지 않는 결과는 버린다."""
        query = re.sub(r"\s+", " ", str(query or "")).strip()
        if not terms(query):
            return []
        groups: list[list[dict[str, Any]]] = []
        for src in self.sources:
            try:
                got = [m for m in getattr(self, src)(query, limit) if relevant(query, m)]
            except Exception as e:  # noqa: BLE001 - 기관 하나가 막혀도 다른 기관은 쓴다
                self.log(f"🏛 {INSTITUTIONS[src]} 검색 실패('{query}'): {e}")
                got = []
            groups.append(got)
        out: list[dict[str, Any]] = []
        for i in range(max((len(g) for g in groups), default=0)):
            for g in groups:
                if i < len(g) and len(out) < limit:
                    out.append(g[i])
        return out
