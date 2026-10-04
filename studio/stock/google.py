"""Google 이미지(SerpApi) — 채널 주인 2026-10-04: "가능하면 그냥 구글 이미지를 활용해. 출처만 정확히 남기면 되잖아."

출처 표기만으로는 남의 사진을 쓸 권리가 생기지 않는다(저작권법 제28조 인용은 '내 영상이 주, 그림은 종'이고 그 그림 자체를 다룰 때만).
그래서 Google 이미지를 **두 길로만** 쓴다.
1. 재사용 가능 라이선스(`licenses=fmc`: 상업적 이용·수정 가능) 결과 → **원문 페이지에서 라이선스를 다시 확인**한 것만:
   그림마다 라이선스를 붙이는 사진 사이트(`PHOTO_SITES` — Flickr·PxHere·rawpixel…)의 CC BY·BY-SA·CC0·PDM 링크(NC·ND 가 섞이면 버림),
   Pixabay·Unsplash·Pexels 자체 약관, 커먼즈 파일 페이지는 커먼즈 API 의 그 파일 라이선스, 미국 연방 기관 사진(PD). 일반 사이트의
   CC 링크는 글의 라이선스라 믿지 않는다. 확인 못 하면 버린다.
   위키백과·위키미디어 페이지는 쓰지 않는다(페이지 아래 글 라이선스 링크가 그림의 라이선스가 아니고, 그 그림은 위키미디어 칸이 API 로
   정확히 다룬다). → StockHub 의 제공처 'Google' · 사다리의 고유명사 칸.
2. 인용(C 등급) — 그 작품·제품·화면 **자체를 설명하는 문장**에서만(자료 리서처의 tier_max C), 설정 '인용 자료 쓰기'가 켜져 있을 때만.
   라이선스 필터 없이 찾고, 화면에는 `이미지: 사이트`, 설명란·자료 대장에는 제목·사이트·원문 주소와 인용 사유. 6초 이내·전면 금지·
   긴 변 1600px 이하는 사다리·렌더 정책이 지킨다.
SerpApi 무료 요금제는 월 250회(카드 없음) — 한 요청에 첫 검색어로 한 번만 부른다(StockHub `once`). 남은 횟수는 account.json(무료 호출).
공식 페이지의 대표 이미지(og:image)는 키 없이 `page_image` 로(인용 칸).
"""
from __future__ import annotations

import html as htmllib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urljoin, urlparse

from .. import net
from ..assets.license import License, classify
from .base import StockCandidate, StockError, StockProvider

SERP = "https://serpapi.com/search.json"
ACCOUNT = "https://serpapi.com/account.json"
CC_RE = re.compile(r"creativecommons\.org/(?:licenses|publicdomain)/([a-z\-+]+)/?(\d\.\d)?", re.I)
STOCK_SITES = {"pixabay.com": ("pixabay", "Pixabay Content License", "https://pixabay.com/service/license-summary/"),
               "unsplash.com": ("unsplash", "Unsplash License", "https://unsplash.com/license"),
               "pexels.com": ("pexels", "Pexels License", "https://www.pexels.com/license/")}
# 그림의 라이선스를 페이지로 확인할 수 없는 곳: 위키(아래 글 라이선스 링크가 그림 것이 아님) · 위키 농장 · 스톡 판매처(워터마크 미리보기)
# 미국 연방정부 저작물(17 U.S.C. §105) — 기관이 직접 찍은 사진은 퍼블릭 도메인. 단 외부 제공('courtesy')·저작권 표시가 있으면 아니다.
# 주(州)·지방 정부(.gov 일부)는 해당 없음 → 연방 기관 도메인만
FEDERAL = ("af.mil", "army.mil", "navy.mil", "marines.mil", "defense.gov", "dvidshub.net", "nasa.gov", "nps.gov",
           "noaa.gov", "usda.gov", "fws.gov", "usgs.gov", "nih.gov", "cdc.gov")
FEDERAL_CREDIT = re.compile(r"U\.S\. (Air Force|Army|Navy|Marine Corps|Space Force|Coast Guard|National Guard) (photo|graphic|"
                            r"illustration)|\b(NASA|NPS|NOAA|USDA|USGS) (photo|image)|public domain", re.I)
# 그림마다 라이선스를 따로 붙이는 사진 사이트 — CC 링크는 여기서만 믿는다. 일반 사이트의 CC 링크는 대개 글(사이트 전체)의
# 라이선스라 그 안의 책 표지·보도 사진에는 해당하지 않는다(2026-10-04 실제 키 확인: 법률 블로그의 CC BY-SA 바닥글로 책 표지가 통과)
PHOTO_SITES = ("flickr.com", "pxhere.com", "rawpixel.com", "stocksnap.io", "publicdomainpictures.net", "picryl.com",
               "nappy.co", "burst.shopify.com", "freerangestock.com", "openverse.org")
COMMONS_FILE = re.compile(r"commons\.wikimedia\.org/wiki/File:([^?#]+)", re.I)
SKIP_HOSTS = ("wikipedia.org", "wikimedia.org", "wikidata.org", "fandom.com", "wikia.com", "wikiwand.com", "namu.wiki",
              "shutterstock.com", "gettyimages.", "istockphoto.com", "alamy.com", "dreamstime.com", "123rf.com",
              "depositphotos.com", "adobe.com", "freepik.com", "vecteezy.com", "pinterest.", "instagram.com",
              "facebook.com", "tiktok.com", "youtube.com", "x.com", "twitter.com")
QUOTE = License("quote", "인용", "", "C", True, False, False, True)
FetchFn = Callable[..., Any]


def host(url: str) -> str:
    return re.sub(r"^www\.", "", urlparse(url or "").netloc.lower())


def skip_host(url: str) -> bool:
    h = host(url)
    return not h or any(s in h for s in SKIP_HOSTS)


def _meta(html: str, *names: str) -> str:
    for n in names:
        for pat in (rf'<meta[^>]+(?:property|name)=["\']{re.escape(n)}["\'][^>]*content=["\']([^"\']*)["\']',
                    rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']{re.escape(n)}["\']'):
            m = re.search(pat, html, re.I)
            if m and m.group(1).strip():
                return htmllib.unescape(m.group(1).strip())
    return ""


def page_author(html: str) -> str:
    """JSON-LD author/creator 이름 → <meta name=author> → rel=author 링크 글자."""
    m = re.search(r'"(?:author|creator)"\s*:\s*\{[^{}]*?"name"\s*:\s*"([^"]{1,80})"', html)
    if m:
        return htmllib.unescape(m.group(1)).strip()
    a = _meta(html, "author", "article:author")
    if a and not a.startswith("http"):
        return a[:80]
    m = re.search(r'<a[^>]+rel=["\']author["\'][^>]*>([^<]{1,80})</a>', html, re.I)
    return htmllib.unescape(m.group(1)).strip() if m else ""


def license_from_html(url: str, html: str) -> Optional[License]:
    """원문 페이지의 라이선스. 자체 라이선스 사이트(Pixabay·Unsplash·Pexels)는 그 약관, 그 밖은 CC 링크 —
    NC·ND 링크가 하나라도 있으면(페이지에 여러 그림이 섞여 있을 수 있다) 버린다. 여럿이면 가장 조건이 많은 쪽(BY-SA > BY > CC0·PDM)."""
    h = host(url)
    for dom, (lid, name, lurl) in STOCK_SITES.items():
        if h == dom or h.endswith("." + dom):
            return License(lid, name, lurl, "stock", True, True, False, False)
    found = [(m.group(1).lower(), m.group(2) or "") for m in CC_RE.finditer(html or "")]
    if not found:
        return None
    kinds = {k for k, _ in found}
    if any(set(k.replace("+", "-").split("-")) & {"nc", "nd", "sampling"} for k in kinds):
        return None
    ver = next((v for k, v in found if v and k in ("by-sa", "by")), "")
    if "by-sa" in kinds:
        return classify(f"CC BY-SA {ver}".strip())
    if "by" in kinds:
        return classify(f"CC BY {ver}".strip())
    if "zero" in kinds:
        return classify("CC0")
    if "mark" in kinds:
        return classify("Public domain")
    return None


def _federal(h: str) -> bool:
    return any(h == d or h.endswith("." + d) for d in FEDERAL)


def commons_license(url: str, *, fetch: FetchFn = net.request) -> Optional[dict[str, Any]]:
    """위키미디어 커먼즈 파일 페이지 — 페이지 아래 글 라이선스 링크가 아니라 커먼즈 API 의 그 파일 라이선스로(정확하다)."""
    from urllib.parse import unquote
    m = COMMONS_FILE.search(url or "")
    if not m:
        return None
    name = unquote(m.group(1)).replace("_", " ")
    try:
        r = fetch("https://commons.wikimedia.org/w/api.php",
                  params={"action": "query", "titles": f"File:{name}", "prop": "imageinfo", "iiprop": "extmetadata",
                          "iiextmetadatafilter": "LicenseShortName|Artist|Restrictions|NonFree", "format": "json",
                          "formatversion": "2"},
                  headers={"User-Agent": "ChoiStudio/1.0 (https://github.com/chiddesign/choi-explains-design)"},
                  timeout=10, rounds=1)
        page = ((r.json().get("query") or {}).get("pages") or [{}])[0] if r.ok else {}
    except Exception:  # noqa: BLE001
        return None
    meta = ((page.get("imageinfo") or [{}])[0].get("extmetadata")) or {}
    val = lambda k: re.sub(r"<[^>]+>", "", str((meta.get(k) or {}).get("value") or "")).strip()  # noqa: E731
    lic = classify(val("LicenseShortName"), nonfree=bool(val("NonFree")), restrictions=val("Restrictions"))
    if lic.tier not in ("A", "A-sa"):
        return None
    return {"license": lic, "author": val("Artist")[:80], "site": "Wikimedia Commons", "title": name.rsplit(".", 1)[0]}


def verify_page(url: str, *, fetch: FetchFn = net.request) -> Optional[dict[str, Any]]:
    """원문 페이지를 열어 라이선스·작가·사이트 이름을 확인한다. 확인 못 하면 None(그 그림은 쓰지 않는다).
    2026-10-04 실제 키로 확인: 결과의 상당수가 미국 연방 기관(af.mil·nps.gov — CC 링크 없이 퍼블릭 도메인)과 커먼즈 파일 페이지였다."""
    if COMMONS_FILE.search(url or ""):
        return commons_license(url, fetch=fetch)
    if skip_host(url):
        return None
    h = host(url)
    if any(h == d or h.endswith("." + d) for d in STOCK_SITES):
        return {"license": license_from_html(url, ""), "author": "", "site": h.split(".")[-2].capitalize(), "title": ""}
    try:
        r = fetch(url, timeout=8, rounds=1)
    except Exception:  # noqa: BLE001 - 열 수 없으면 확인 못 함
        return None
    if not r.ok:
        return None
    html = (r.text or "")[:1_500_000]
    photo_site = any(h == d or h.endswith("." + d) for d in PHOTO_SITES)
    lic = license_from_html(url, html) if photo_site else None
    if lic is None and _federal(h) and FEDERAL_CREDIT.search(html) and not re.search(r"courtesy|©|copyright \d{4}", html,
                                                                                       re.I):
        lic = License("PD-USGov", "퍼블릭 도메인(미국 연방정부 저작물)", "https://www.usa.gov/government-copyright", "A",
                      True, True, False, False)
    if lic is None:
        return None
    return {"license": lic, "author": page_author(html), "site": _meta(html, "og:site_name") or h,
            "title": _meta(html, "og:title", "twitter:title")}


def page_image(url: str, *, fetch: FetchFn = net.request) -> Optional[dict[str, Any]]:
    """공식 페이지(제품·작품·기관)의 대표 이미지(og:image · twitter:image) — 키 없이. 인용(C) 칸 전용."""
    if not url or not url.startswith("http"):
        return None
    try:
        r = fetch(url, timeout=15, rounds=1)
    except Exception:  # noqa: BLE001
        return None
    if not r.ok:
        return None
    html = (r.text or "")[:1_500_000]
    img = _meta(html, "og:image:secure_url", "og:image", "twitter:image", "twitter:image:src")
    if not img:
        return None
    return {"url": urljoin(url, img), "page": url, "title": _meta(html, "og:title", "twitter:title"),
            "site": _meta(html, "og:site_name") or host(url),
            "width": int(_meta(html, "og:image:width") or 0) if _meta(html, "og:image:width").isdigit() else 0,
            "height": int(_meta(html, "og:image:height") or 0) if _meta(html, "og:image:height").isdigit() else 0}


def quote_credit(title: str, site: str, page: str) -> tuple[str, str]:
    """인용 그림의 (화면, 설명란) 출처."""
    site = site or host(page)
    return (f"이미지: {site}"[:40],
            f"{(title or '').strip() or '이미지'} — {site}. 비평·교육 목적의 인용(저작권법 제28조) — {page}".strip())


def cand_meta(r: dict[str, Any], *, lic: License, author: str = "", site: str = "", origin: str = "web") -> dict[str, Any]:
    """SerpApi 결과 하나 → 사다리 후보(커먼즈 후보와 같은 키)."""
    page = str(r.get("link") or "")
    site = site or str(r.get("source") or "") or host(page)
    title = re.sub(r"\s+", " ", str(r.get("title") or "")).strip()
    url = str(r.get("original") or "")
    ext = (Path(urlparse(url).path).suffix.lower() or ".jpg")[:5]
    m = {"name": f"{title[:60] or host(page)} ({site}){ext if ext in ('.jpg', '.jpeg', '.png', '.webp') else '.jpg'}",
         "url": url, "thumb_url": str(r.get("thumbnail") or url), "orig_url": url,
         "width": int(r.get("original_width") or 0), "height": int(r.get("original_height") or 0),
         "mime": "image/png" if ext == ".png" else "image/jpeg", "page": page, "artist": author[:80], "title": title,
         "description": f"{title} — {site}"[:300], "license": lic.name, "lic": lic.to_dict(), "tier": lic.tier,
         "src": "google", "origin": origin, "institution": site}
    if lic.tier == "C":
        m["credit"] = list(quote_credit(title, site, page))
    return m


class SerpGoogle:
    """SerpApi 의 google_images 엔진. 결과 캐시는 StockProvider 캐시(키는 파일 이름에 넣지 않는다)를 빌려 쓴다."""

    def __init__(self, provider: "GoogleImages"):
        self.p = provider

    def images(self, query: str, *, reusable: bool, n: int = 10, locale: str = "") -> list[dict[str, Any]]:
        ko = locale.lower().startswith("ko") or bool(re.search(r"[가-힣]", query))
        params = {"engine": "google_images", "q": query[:120], "api_key": self.p.key, "safe": "active",
                  "hl": "ko" if ko else "en", "gl": "kr" if ko else "us", "ijn": "0"}
        if reusable:
            params["licenses"] = "fmc"          # 상업적 이용·공유·수정 가능(원문에서 다시 확인한다)
        data = self.p._get_json(SERP, params) or {}
        err = str(data.get("error") or "")
        if err:
            low = err.lower()
            if "hasn't returned any results" in low or "no results" in low:
                return []
            if "invalid api key" in low or "run out of searches" in low or "account" in low:
                raise StockError(f"Google(SerpApi): {err}")
            raise StockError(f"Google(SerpApi): {err}", fatal=False)
        out = []
        for r in data.get("images_results") or []:
            if not r.get("original") or not r.get("link") or r.get("is_product"):
                continue
            out.append(r)
            if len(out) >= n:
                break
        return out


class GoogleImages(StockProvider):
    """StockHub 제공처 'Google' — 재사용 가능 라이선스로 찾고 원문에서 라이선스를 확인한 사진만 후보로."""

    name = "Google"
    photos = True
    korean = True
    once = True                       # 한 요청에 첫 검색어로 한 번만(월 무료 250회)
    remaining_header = "X-SerpApi-Remaining"

    def __init__(self, api_key: str, *, fetch: FetchFn = net.request, **kw: Any):
        if not api_key:
            raise StockError("SerpApi 키가 없습니다(설정 → 스톡).")
        super().__init__(**kw)
        self.key = api_key
        self.fetch = fetch
        self.serp = SerpGoogle(self)
        self._verified: dict[str, Optional[dict[str, Any]]] = {}

    def _get_json(self, url: str, params: dict[str, Any], headers: Optional[dict[str, str]] = None) -> Any:
        """SerpApi 는 횟수가 떨어지면 429 + "run out of searches" — 한도 대기(기본 처리)를 하지 않고 이번 작업에서 끈다."""
        cache = self._cache_path(url, params)
        if cache and cache.exists():
            return json.loads(cache.read_text(encoding="utf-8"))
        try:
            r = net.request(url, params=params, headers=headers or {}, timeout=40, rounds=1)
        except net.NetError as e:
            raise StockError(f"Google(SerpApi) 에 연결하지 못했습니다 — {e}", fatal=False) from e
        try:
            data = r.json()
        except ValueError:
            data = {}
        if not r.ok:
            err = str((data or {}).get("error") or r.text[:120])
            low = err.lower()
            raise StockError(f"Google(SerpApi): {err}",
                             fatal=r.status in (401, 403) or "run out" in low or "invalid api key" in low)
        if cache and isinstance(data, dict) and not data.get("error"):
            cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def status(self) -> str:
        """남은 검색 횟수(account.json 은 횟수를 쓰지 않는다)."""
        try:
            r = net.request(ACCOUNT, params={"api_key": self.key}, timeout=15, rounds=1)
            d = r.json() if r.ok else {}
        except Exception as e:  # noqa: BLE001
            return f"⚠ Google(SerpApi): 계정 확인 실패 {e}"
        if not r.ok or d.get("error"):
            return f"⚠ Google(SerpApi): {d.get('error') or f'HTTP {r.status}'}"
        left = d.get("total_searches_left", d.get("plan_searches_left"))
        if isinstance(left, int):
            self.remaining = left
        return f"Google(SerpApi) 정상(이번 달 남은 검색 {left})"

    def verified(self, page: str) -> Optional[dict[str, Any]]:
        if page not in self._verified:
            self._verified[page] = verify_page(page, fetch=self.fetch)
        return self._verified[page]

    def search_photos(self, query: str, *, per_page: int = 6, locale: str = "") -> list[StockCandidate]:
        raw = [r for r in self.serp.images(query, reusable=True, n=per_page * 3, locale=locale)
               if COMMONS_FILE.search(str(r.get("link") or "")) or not skip_host(str(r.get("link") or ""))]
        # 같은 페이지가 여러 번 나온다(실측: 한 기사 페이지 7번) — 페이지마다 한 번만 열고, 같은 페이지의 그림은 하나만 후보로
        seen: set[str] = set()
        raw = [r for r in raw if not (str(r["link"]) in seen or seen.add(str(r["link"])))]
        with ThreadPoolExecutor(max_workers=8) as ex:
            checks = list(ex.map(lambda r: self.verified(str(r["link"])), raw))
        out: list[StockCandidate] = []
        for r, v in zip(raw, checks):
            if not v or not v.get("license"):
                continue
            w, h = int(r.get("original_width") or 0), int(r.get("original_height") or 0)
            if (w and w < 900) or (w and h and not 0.5 <= w / h <= 2.6):
                continue
            lic: License = v["license"]
            site = v.get("site") or str(r.get("source") or "") or host(r["link"])
            title = re.sub(r"\s+", " ", str(r.get("title") or v.get("title") or "")).strip()
            author = v.get("author") or ""
            full = (f"\"{title or '사진'}\"" + (f" by {author}" if author else "") + f" — {lic.name}"
                    + (f" ({lic.url})" if lic.url else "") + f" — {site} — {r['link']}")
            out.append(StockCandidate(
                kind="photo", id=str(r.get("position") or len(out)) + "_" + re.sub(r"[^0-9A-Za-z]", "", host(r["link"]))[:12]
                + re.sub(r"[^0-9A-Za-z]", "", str(r["original"]))[-16:],
                url=str(r["link"]), thumb=str(r.get("thumbnail") or r["original"]), download=str(r["original"]),
                width=w, height=h, author=author, alt=f"{title} — {site} · {lic.name}", provider=self.name,
                extra={"license": lic.name, "tier": lic.tier, "lic": lic.to_dict(), "site": site, "title": title,
                       "attribution": full}))
            if len(out) >= per_page:
                break
        return out

    def quote_candidates(self, query: str, *, n: int = 6) -> list[dict[str, Any]]:
        """인용(C) 후보 — 라이선스 필터 없이. 사다리가 tier_max C·인용 켜짐일 때만 부른다."""
        out = []
        for r in self.serp.images(query, reusable=False, n=n * 2):
            if skip_host(str(r.get("link") or "")):
                continue
            out.append(cand_meta(r, lic=QUOTE, origin="web"))
            if len(out) >= n:
                break
        return out

    def reusable_candidates(self, query: str, *, n: int = 6) -> list[dict[str, Any]]:
        """재사용 가능(원문에서 확인한) 후보 — 사다리의 고유명사 칸용(A·A-sa·stock)."""
        out = []
        for c in self.search_photos(query, per_page=n):
            m = cand_meta({"link": c.url, "original": c.download, "thumbnail": c.thumb, "title": c.extra.get("title", ""),
                           "original_width": c.width, "original_height": c.height},
                          lic=License(**c.extra["lic"]), author=c.author, site=c.extra.get("site", ""))
            m["credit_full"] = c.extra.get("attribution", "")
            out.append(m)
        return out

    def download(self, c: StockCandidate, dst: Path) -> Path:
        if dst.exists() and dst.stat().st_size > 0:
            return dst
        net.download(c.download, dst, timeout=90, headers={"User-Agent": net.BROWSER_UA, "Referer": c.url,
                                                            "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"})
        return dst
