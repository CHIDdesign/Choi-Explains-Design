"""위키백과 대표 이미지 — 인물·종교·사물·브랜드·작품 같은 고유명사는 스톡보다 그 문서의 대표 사진이 낫다.

순서: ko.wikipedia 문서(REST summary, 리다이렉트를 따라감) → 못 찾으면 검색 1위(동음이의 문서 제외) → en.wikipedia.
대표 이미지 파일의 라이선스는 커먼즈(없으면 그 위키) imageinfo 로 확인해 자유 라이선스(CC0·PD·CC BY·CC BY-SA)만 쓰고,
화면 크레딧("작가 · 라이선스 · Wikipedia (문서명)")을 남긴다. 비자유(fair-use) 이미지는 건너뛴다.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, unquote

from .. import __version__, net
from ..util import LogFn, noop_log
from .images import OK_LICENSES, ImageResult, _strip_html

REST = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
API = "https://{lang}.wikipedia.org/w/api.php"
COMMONS = "https://commons.wikimedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"
HUMAN = "Q5"                 # 위키데이터 '사람'(P31 instance of)
II_FILTER = "LicenseShortName|UsageTerms|Artist|Credit|Restrictions|NonFree|ImageDescription"
DISAMBIG_HINT = ("동음이의", "disambiguation", "may refer to")
NONFREE_HINT = ("non-free", "fair use", "비자유", "공정 이용")


def title_matches(term: str, title: str) -> bool:
    """검색 결과 제목이 찾는 말과 같은 대상인가 — 띄어쓰기·괄호 설명을 빼고 거의 같거나 한쪽이 다른 쪽을 포함할 때만."""
    from rapidfuzz import fuzz

    def n(s: str) -> str:
        s = re.sub(r"\s*\([^)]*\)\s*$", "", s)      # '브라운 (기업)' → '브라운'
        return re.sub(r"[\s_\-·.]+", "", s).lower()

    a, b = n(term), n(title)
    if not a or not b:
        return False
    if a == b:
        return True
    # 포함은 길이가 비슷할 때만('braun' ⊂ 'braunsk4' 는 회사 문서 ≠ 라디오 문서)
    if len(a) >= 3 and (a in b or b in a) and min(len(a), len(b)) / max(len(a), len(b)) >= 0.75:
        return True
    return fuzz.ratio(a, b) >= 85


def _safe(name: str, n: int = 50) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "_", name).strip("_")[:n] or "image"


def _file_name_from_url(url: str) -> str:
    """https://upload.wikimedia.org/wikipedia/commons/a/ab/Name.jpg 또는 /thumb/…/Name.jpg/800px-Name.jpg → Name.jpg
    (REST summary 의 이미지 URL 에는 ?utm_source=… 가 붙어 온다 — 떼어 낸다)"""
    url = url.split("?", 1)[0].split("#", 1)[0]
    parts = [unquote(p) for p in url.split("/") if p]
    if "thumb" in parts:
        i = parts.index("thumb")
        rest = parts[i + 1:]
        return rest[-2] if len(rest) >= 2 else rest[-1]
    return parts[-1]


class WikipediaImages:
    def __init__(self, contact: str = "", log: LogFn = noop_log, cache_dir: Optional[Path] = None,
                 langs: tuple[str, ...] = ("ko", "en")):
        contact = contact or "https://github.com/chiddesign/choi-explains-design"
        self.ua = f"ChoiStudio/{__version__} ({contact}) python-requests"
        self.log = log
        self.cache_dir = cache_dir
        self.langs = langs
        self._last = 0.0

    # --- HTTP -------------------------------------------------------------
    def _get(self, url: str, params: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        # 위키미디어 API 예절: 호출 사이 1초, 429 면 Retry-After 만큼 쉬고 한 번 더
        wait = 1.0 - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        hdr = {"User-Agent": self.ua, "Accept": "application/json"}
        r = net.request(url, params=params, headers=hdr, timeout=20, rounds=1)
        for attempt in range(3):
            if r.status != 429:
                break
            try:
                delay = min(20.0, float(r.headers.get("Retry-After") or r.headers.get("retry-after") or 0) or 4.0 * (attempt + 1))
            except ValueError:
                delay = 4.0 * (attempt + 1)
            time.sleep(delay)
            self._last = time.time()
            r = net.request(url, params=params, headers=hdr, timeout=20, rounds=1)
        if r.status == 404:
            return None
        if not r.ok:
            raise RuntimeError(f"Wikipedia HTTP {r.status}")
        try:
            data = r.json()
        except ValueError as e:
            raise RuntimeError(f"Wikipedia 응답이 JSON 이 아님: {e}") from e
        return data if isinstance(data, dict) else None

    # --- 문서 -------------------------------------------------------------
    def summary(self, term: str, lang: str) -> Optional[dict[str, Any]]:
        """문서 요약(REST). 없으면 검색 1위(동음이의 제외)로. 이미지 없는 문서도 돌려준다(호출자가 판단)."""
        title = term.strip().replace(" ", "_")
        if not title:
            return None
        s = self._get(REST.format(lang=lang, title=quote(title, safe="")))
        if s and s.get("type") == "disambiguation":
            s = None
        if s and s.get("type") in ("standard", "no-extract"):
            return s
        data = self._get(API.format(lang=lang), {"action": "query", "list": "search", "srsearch": term, "srlimit": "5",
                                                 "format": "json", "formatversion": "2"})
        hits = ((data or {}).get("query") or {}).get("search") or []
        for h in hits:
            t = h.get("title", "")
            snippet = _strip_html(h.get("snippet", "")).lower()
            if not t or any(k in snippet for k in DISAMBIG_HINT) or any(k in t.lower() for k in DISAMBIG_HINT):
                continue
            # 검색 1위가 그 말을 '언급만' 하는 다른 문서일 수 있다(Massimo Vignelli → 블루밍데일스). 제목이 거의 같을 때만.
            if not title_matches(term, t):
                continue
            s = self._get(REST.format(lang=lang, title=quote(t.replace(" ", "_"), safe="")))
            if s and s.get("type") in ("standard", "no-extract"):
                return s
        return None

    def file_meta(self, image_url: str, lang: str) -> dict[str, Any]:
        """대표 이미지 파일의 라이선스·작가·1920px 썸네일. 커먼즈에 없으면 그 위키(비자유 이미지가 여기 있다)."""
        name = _file_name_from_url(image_url)
        params = {"action": "query", "titles": f"File:{name}", "prop": "imageinfo",
                  "iiprop": "url|size|mime|extmetadata", "iiurlwidth": "1920",
                  "iiextmetadatafilter": "LicenseShortName|UsageTerms|Artist|Credit|Restrictions|NonFree",
                  "format": "json", "formatversion": "2"}
        for api in (COMMONS, API.format(lang=lang)):
            data = self._get(api, params) or {}
            pages = ((data.get("query") or {}).get("pages")) or []
            for p in pages:
                if p.get("missing"):
                    continue
                ii = (p.get("imageinfo") or [{}])[0]
                meta = ii.get("extmetadata") or {}
                val = lambda k: _strip_html((meta.get(k) or {}).get("value", ""))  # noqa: E731
                return {"name": name, "license": val("LicenseShortName"), "usage": val("UsageTerms"),
                        "artist": val("Artist")[:80], "restrictions": val("Restrictions"), "nonfree": val("NonFree"),
                        "url": ii.get("thumburl") or ii.get("url") or image_url, "mime": ii.get("mime", ""),
                        "width": ii.get("width", 0), "height": ii.get("height", 0),
                        "page": ii.get("descriptionurl", ""), "repo": "commons" if api == COMMONS else lang}
        return {"name": name, "license": "", "url": image_url, "mime": "", "width": 0, "height": 0, "page": "",
                "artist": "", "restrictions": "", "usage": "", "nonfree": "", "repo": ""}

    @staticmethod
    def license_ok(meta: dict[str, Any]) -> bool:
        lic = (meta.get("license") or "").lower()
        usage = (meta.get("usage") or "").lower()
        if not lic:
            return False
        if re.search(r"(^|[\s-])n[cd]($|[\s-])", lic) or meta.get("restrictions") or meta.get("nonfree"):
            return False
        if any(k in lic or k in usage for k in NONFREE_HINT):
            return False
        return any(k in lic for k in OK_LICENSES)

    # --- 가져오기 ---------------------------------------------------------
    def lookup(self, term: str) -> Optional[dict[str, Any]]:
        """문서와 쓸 수 있는 대표 이미지(없으면 None). 캐시는 검색어 단위."""
        cache = None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache = self.cache_dir / f"wp_{_safe(term, 60)}.json"
            if cache.exists():
                data = json.loads(cache.read_text(encoding="utf-8"))
                return data or None
        found: Optional[dict[str, Any]] = None
        for lang in self.langs:
            try:
                s = self.summary(term, lang)
            except Exception as e:  # noqa: BLE001 - 네트워크 오류는 다음 언어로
                self.log(f"위키백과({lang}) 조회 실패({term}): {e}")
                continue
            if not s:
                continue
            img = (s.get("originalimage") or s.get("thumbnail") or {}).get("source", "")
            if not img:
                continue
            try:
                meta = self.file_meta(img, lang)
            except Exception as e:  # noqa: BLE001
                self.log(f"위키백과 이미지 정보 실패({term}): {e}")
                continue
            if not self.license_ok(meta):
                self.log(f"위키백과 '{s.get('title')}' 대표 이미지는 자유 라이선스가 아님({meta.get('license') or '?'}) — 건너뜀")
                continue
            w, h = meta.get("width") or 0, meta.get("height") or 0
            if w and h and w / max(1, h) < 0.5:
                continue   # 너무 세로로 긴 이미지(인물 전신 사진 등)는 액자에 안 맞는다
            found = {"lang": lang, "title": s.get("title", term), "description": s.get("description", ""),
                     "page": ((s.get("content_urls") or {}).get("desktop") or {}).get("page", ""),
                     "image": meta}
            break
        if cache:
            cache.write_text(json.dumps(found or {}, ensure_ascii=False), encoding="utf-8")
        return found

    # --- 위키데이터: 무엇인가(사람·브랜드) · 로고 · 초상 후보 -------------------------------------------
    def entity(self, term: str, names: tuple[str, ...] = ()) -> Optional[dict[str, Any]]:
        """문서 → 위키데이터 항목: {qid, title, lang, page, lead(대표 이미지 URL), human, p18[], logos[], commons_cat,
        label_en}. 문서·항목이 없으면 None. 캐시는 검색어 단위(wd_*.json)."""
        cache = None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache = self.cache_dir / f"wd_{_safe(term, 60)}.json"
            if cache.exists():
                data = json.loads(cache.read_text(encoding="utf-8"))
                return data or None
        tries = [(term, lang) for lang in self.langs] + [(n, "en") for n in names if n and n != term]
        s, lang = None, ""
        for t, lg in tries:
            try:
                s = self.summary(t, lg)
            except Exception as e:  # noqa: BLE001 - 네트워크 오류는 다음 후보로
                self.log(f"위키백과({lg}) 조회 실패({t}): {e}")
                s = None
            if s and s.get("wikibase_item"):
                lang = lg
                break
        if not s or not s.get("wikibase_item"):
            if cache:
                cache.write_text("{}", encoding="utf-8")
            return None
        qid = s["wikibase_item"]
        data = self._get(WIKIDATA, {"action": "wbgetentities", "ids": qid, "props": "claims|labels",
                                    "languages": "en|ko", "format": "json"}) or {}
        ent = (data.get("entities") or {}).get(qid) or {}
        claims = ent.get("claims") or {}

        def vals(prop: str) -> list[str]:
            out = []
            for c in claims.get(prop) or []:
                if c.get("rank") == "deprecated":
                    continue
                v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
                if isinstance(v, dict) and v.get("id"):
                    out.append(v["id"])
                elif isinstance(v, str):
                    out.append(v)
            # 선호(preferred) 순위를 앞으로
            pref = [((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") for c in claims.get(prop) or []
                    if c.get("rank") == "preferred"]
            return sorted(out, key=lambda v: 0 if v in pref else 1)
        info = {"qid": qid, "title": s.get("title", term), "lang": lang, "description": s.get("description", ""),
                "page": ((s.get("content_urls") or {}).get("desktop") or {}).get("page", ""),
                "lead": (s.get("originalimage") or s.get("thumbnail") or {}).get("source", ""),
                "human": HUMAN in vals("P31"), "p18": vals("P18")[:3], "logos": vals("P154")[:3],
                "commons_cat": (vals("P373") or [""])[0],
                "label_en": (((ent.get("labels") or {}).get("en") or {}).get("value") or "")}
        if cache:
            cache.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        return info

    def files_meta(self, names: list[str], width: int = 1920) -> list[dict[str, Any]]:
        """커먼즈 파일 여러 개의 라이선스·크기·썸네일(한 번에 50개까지)."""
        out: list[dict[str, Any]] = []
        names = [n for n in dict.fromkeys(names) if n][:50]
        if not names:
            return out
        data = self._get(COMMONS, {"action": "query", "titles": "|".join(f"File:{n}" for n in names),
                                   "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
                                   "iiurlwidth": str(width), "iiextmetadatafilter": II_FILTER,
                                   "format": "json", "formatversion": "2"}) or {}
        return [m for m in (_meta_of(p) for p in ((data.get("query") or {}).get("pages")) or []) if m]

    def category_files(self, cat: str, limit: int = 30, width: int = 1920) -> list[dict[str, Any]]:
        """커먼즈 분류(위키데이터 P373)의 사진들 — 인물 사진 후보."""
        data = self._get(COMMONS, {"action": "query", "generator": "categorymembers",
                                   "gcmtitle": f"Category:{cat}", "gcmtype": "file", "gcmlimit": str(limit),
                                   "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata",
                                   "iiurlwidth": str(width), "iiextmetadatafilter": II_FILTER,
                                   "format": "json", "formatversion": "2"}) or {}
        return [m for m in (_meta_of(p) for p in ((data.get("query") or {}).get("pages")) or []) if m]

    def logo_meta(self, info: dict[str, Any]) -> Optional[dict[str, Any]]:
        """위키데이터 P154 로고 파일 중 쓸 수 있는 것(저작권 자유 — 상표 제한만 있는 것 허용)."""
        for m in self.files_meta(info.get("logos") or [], width=1200):
            if logo_license_ok(m):
                return m
        return None

    def portrait_candidates(self, info: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
        """인물 사진 후보: 위키데이터 대표 사진(P18) → 문서 대표 이미지 → 커먼즈 분류의 사진. 자유 라이선스·사진 파일·
        600px 이상만. 각 후보에 src(wikidata|lead|category) 를 붙인다."""
        first = [(n, "wikidata") for n in info.get("p18") or []]
        if info.get("lead"):
            first.append((_file_name_from_url(info["lead"]), "lead"))
        metas = {m["name"]: m for m in self.files_meta([n for n, _ in first])}
        out: list[dict[str, Any]] = []
        for n, src in first:
            if n in metas and n not in {m["name"] for m in out}:
                out.append({**metas[n], "src": src})
        if info.get("commons_cat"):
            try:
                more = self.category_files(info["commons_cat"])
            except Exception as e:  # noqa: BLE001
                self.log(f"커먼즈 분류 조회 실패({info['commons_cat']}): {e}")
                more = []
            more.sort(key=lambda m: -(m.get("width", 0) * m.get("height", 0)))
            out += [{**m, "src": "category"} for m in more if m["name"] not in {o["name"] for o in out}]

        def usable(m: dict[str, Any]) -> bool:
            w, h = m.get("width") or 0, m.get("height") or 0
            return (portrait_license_ok(m) and (m.get("mime") or "") in ("image/jpeg", "image/png", "image/webp")
                    and min(w, h) >= 600 and 0.5 <= w / max(1, h) <= 2.0)
        return [m for m in out if usable(m)][:limit]

    def fetch(self, term: str, dst_dir: Path) -> Optional[ImageResult]:
        found = self.lookup(term)
        if not found:
            return None
        meta = found["image"]
        ext = ".png" if "png" in (meta.get("mime") or "") else ".jpg"
        dst = dst_dir / f"wp_{_safe(term)}{ext}"
        try:
            if not dst.exists():
                net.download(meta["url"], dst, timeout=60, headers={"User-Agent": self.ua})
        except Exception as e:  # noqa: BLE001
            self.log(f"위키백과 이미지 다운로드 실패({term}): {e}")
            return None
        artist = meta.get("artist") or "Unknown"
        credit = f"{artist} · {meta.get('license')} · Wikipedia ({found['title']})"
        return ImageResult(dst, credit, meta.get("license", ""), meta.get("page") or found.get("page", ""), "wikipedia")


def _meta_of(p: dict[str, Any]) -> Optional[dict[str, Any]]:
    if p.get("missing") or not p.get("imageinfo"):
        return None
    ii = p["imageinfo"][0]
    meta = ii.get("extmetadata") or {}
    val = lambda k: _strip_html((meta.get(k) or {}).get("value", ""))  # noqa: E731
    name = str(p.get("title", "")).split(":", 1)[-1]
    return {"name": name, "license": val("LicenseShortName"), "usage": val("UsageTerms"), "artist": val("Artist")[:80],
            "restrictions": val("Restrictions"), "nonfree": val("NonFree"), "description": val("ImageDescription")[:300],
            "url": ii.get("thumburl") or ii.get("url", ""), "orig_url": ii.get("url", ""), "mime": ii.get("mime", ""),
            "width": ii.get("width", 0), "height": ii.get("height", 0), "page": ii.get("descriptionurl", ""),
            "repo": "commons"}


def logo_license_ok(meta: dict[str, Any]) -> bool:
    """로고용: 저작권은 자유(PD·CC0·CC BY(-SA))여야 하고, 제한은 상표('trademarked')만 허용(지명 사용)."""
    restr = {r.strip().lower() for r in re.split(r"[|,;]", meta.get("restrictions") or "") if r.strip()}
    if restr - {"trademarked"}:
        return False
    return WikipediaImages.license_ok({**meta, "restrictions": ""})


def portrait_license_ok(meta: dict[str, Any]) -> bool:
    """인물 사진용: 자유 라이선스 + 제한은 초상권 경고('personality')만 허용 — 공인을 설명하는 교육 영상에서 그 사람의
    사진을 보여 주는 것은 광고·보증이 아니다(커먼즈 인물 사진 대부분에 붙어 있다)."""
    restr = {r.strip().lower() for r in re.split(r"[|,;]", meta.get("restrictions") or "") if r.strip()}
    if restr - {"personality"}:
        return False
    return WikipediaImages.license_ok({**meta, "restrictions": ""})
