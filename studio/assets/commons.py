"""고유명사(entity) 자료 후보 여러 장 — 대표 이미지 1장이 아니라(03 문서 P0-5·P1):
위키데이터 대표 사진(P18) → 문서 대표 이미지 → 문서 안 모든 이미지(REST media-list) → 커먼즈 depicts(P180) → 커먼즈 분류(P373).
라이선스는 license.classify 로 등급을 매겨 요청의 tier_max·설정 안에서만 남기고, 래스터·긴 변 900px 이상·
극단적 비율이 아닌 것만. 사람 아닌 대상(제품·작품·서비스)에는 행사·인터뷰·무대 사진을 빼 둔다
(10/1: '핀터레스트' = 창업자의 SXSW 무대 사진).
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote

from ..broll.resolve import EVENT_WORDS
from ..broll.wikipedia import COMMONS, II_FILTER, WikipediaImages, _file_name_from_url, _meta_of
from ..util import LogFn, noop_log
from .license import allowed, classify

MEDIA_LIST = "https://{lang}.wikipedia.org/api/rest_v1/page/media-list/{title}"
RASTER = ("image/jpeg", "image/png", "image/webp", "image/tiff")
SRC_RANK = {"research": -1, "wikidata": 0, "lead": 1, "article": 2, "depicts": 3, "category": 4}   # research = 🔎 조사 노트가 확인한 파일
SKIP_NAMES = ("flag of", "coat of arms", "icon", "logo", "map", "signature", "locator", "commons-logo", "wiki")


class EntityMedia:
    def __init__(self, wp: WikipediaImages, *, log: LogFn = noop_log, allow_quote: bool = False):
        self.wp = wp
        self.log = log
        self.allow_quote = allow_quote

    def media_list(self, title: str, lang: str) -> list[str]:
        """문서 안 이미지 파일 이름들(문서 순서)."""
        if not title:
            return []
        data = self.wp._get(MEDIA_LIST.format(lang=lang, title=quote(title.replace(" ", "_"), safe=""))) or {}
        out = []
        for it in data.get("items") or []:
            if it.get("type") != "image":
                continue
            t = str(it.get("title") or "")
            if t:
                out.append(t.split(":", 1)[-1])
        return out

    def depicts(self, qid: str, limit: int = 20) -> list[dict[str, Any]]:
        """커먼즈 구조화 데이터 depicts(P180) = 그 대상이 찍힌 파일."""
        if not qid:
            return []
        data = self.wp._get(COMMONS, {"action": "query", "generator": "search", "gsrsearch": f"haswbstatement:P180={qid}",
                                      "gsrnamespace": "6", "gsrlimit": str(limit), "prop": "imageinfo",
                                      "iiprop": "url|size|mime|extmetadata", "iiurlwidth": "1920",
                                      "iiextmetadatafilter": II_FILTER, "format": "json", "formatversion": "2"}) or {}
        return [m for m in (_meta_of(p) for p in ((data.get("query") or {}).get("pages")) or []) if m]

    def candidates(self, info: dict[str, Any], *, kind: str = "", tier_max: str = "A", limit: int = 9,
                   min_long: int = 900) -> list[dict[str, Any]]:
        """후보 메타 목록(src·tier·lic 포함) — 좋은 출처 순. 네트워크 오류는 그 출처만 건너뛴다."""
        named: list[tuple[str, str]] = [(n, "wikidata") for n in info.get("p18") or []]
        if info.get("lead"):
            named.append((_file_name_from_url(info["lead"]), "lead"))
        try:
            named += [(n, "article") for n in self.media_list(info.get("title", ""), info.get("lang") or "ko")[:20]]
        except Exception as e:  # noqa: BLE001
            self.log(f"문서 이미지 목록 실패({info.get('title')}): {e}")
        seen: set[str] = set()
        order = []
        for n, src in named:
            if n and n not in seen:
                seen.add(n)
                order.append((n, src))
        metas: dict[str, dict[str, Any]] = {}
        try:
            for i in range(0, len(order), 50):
                for m in self.wp.files_meta([n for n, _ in order[i:i + 50]]):
                    metas[m["name"]] = m
        except Exception as e:  # noqa: BLE001
            self.log(f"커먼즈 파일 정보 실패({info.get('title')}): {e}")
        out = [{**metas[n], "src": src} for n, src in order if n in metas]
        extra: list[dict[str, Any]] = []
        try:
            extra += [{**m, "src": "depicts"} for m in self.depicts(info.get("qid", ""))]
        except Exception as e:  # noqa: BLE001
            self.log(f"커먼즈 depicts 조회 실패({info.get('qid')}): {e}")
        if info.get("commons_cat"):
            try:
                extra += [{**m, "src": "category"} for m in self.wp.category_files(info["commons_cat"])]
            except Exception as e:  # noqa: BLE001
                self.log(f"커먼즈 분류 조회 실패({info['commons_cat']}): {e}")
        for m in extra:
            if m["name"] not in seen:
                seen.add(m["name"])
                out.append(m)
        return self.usable(out, kind=kind, tier_max=tier_max, min_long=min_long)[:limit]

    def usable(self, metas: list[dict[str, Any]], *, kind: str = "", tier_max: str = "A",
               min_long: int = 900) -> list[dict[str, Any]]:
        out = []
        for m in metas:
            lic = classify(m.get("license", ""), nonfree=bool(m.get("nonfree")), restrictions=m.get("restrictions", ""))
            if not allowed(lic, tier_max, allow_quote=self.allow_quote):
                continue
            w, h = m.get("width") or 0, m.get("height") or 0
            if (m.get("mime") or "") not in RASTER or max(w, h) < min_long or not (0.4 <= w / max(1, h) <= 2.6):
                continue
            name = m.get("name", "").lower()
            if any(k in name for k in SKIP_NAMES):
                continue
            text = f"{m.get('name', '')} {m.get('description', '')}"
            if kind != "person" and EVENT_WORDS.search(text):
                continue          # 제품·작품·서비스 자리에 행사·인터뷰·무대 사진을 두지 않는다
            out.append({**m, "tier": lic.tier, "lic": lic.to_dict()})
        out.sort(key=lambda m: (SRC_RANK.get(m.get("src", ""), 9), -(m.get("width", 0) * m.get("height", 0)) // 10 ** 6))
        return out


def pick_by_rule(cands: list[dict[str, Any]], count: int) -> list[int]:
    """AI 가 없을 때: 좋은 출처 순으로 서로 다른 파일 count 장."""
    return list(range(min(max(1, count), len(cands))))


def first_or_none(xs: list[Any]) -> Optional[Any]:
    return xs[0] if xs else None
