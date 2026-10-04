"""자료 출처 넓히기(채널 주인 2026-10-04: "Unsplash 는 신청이 오래 걸린다 · 엄격하게 줄이지 말고 더 폭넓고 이해되게 ·
가능하면 구글 이미지를 쓰고 출처를 정확히").

- 미술관 오픈 액세스(시카고·메트 v1.1·클리블랜드): CC0 만, 검색어 낱말이 맞지 않는 결과는 버림, 출처 = 기관.
- Google 이미지(SerpApi): 재사용 가능 결과는 원문 페이지에서 라이선스를 다시 확인한 것만(NC·ND·위키·스톡 판매처는 버림),
  한 요청에 한 번만 부른다. 인용(C)은 tier_max C · 인용 켜짐일 때만, 출처 = 사이트·원문 주소·인용 사유.
- 사다리: 위키미디어 후보가 모자라면 넓혀서 한 시트로 고른다. 비전이 고르지 않은 후보는 받을 때 대신 쓰지 않는다.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from PIL import Image

from studio import net
from studio.assets import museums as M
from studio.assets.ladder import Deps, Ladder
from studio.stock import google as G
from studio.stock.base import StockCandidate, StockError
from studio.stock.providers import StockHub


class _R:
    def __init__(self, status: int = 200, body: Any = b"", url: str = ""):
        self.status = status
        self.content = body if isinstance(body, bytes) else (json.dumps(body) if not isinstance(body, str) else body).encode()
        self.headers: dict[str, str] = {}
        self.url = url

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")

    def json(self) -> Any:
        return json.loads(self.text)


def _jpg(w: int = 64, h: int = 48) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (180, 150, 120)).save(buf, "JPEG")
    return buf.getvalue()


AIC_JSON = {"data": [
    {"id": 154050, "title": "Side Chair", "image_id": "abc", "is_public_domain": True,
     "artist_display": "Designed by Michael Thonet\nAustrian, 1796-1871", "date_display": "c. 1851",
     "artwork_type_title": "Furniture", "medium_display": "Beech, cane", "thumbnail": {"width": 1383, "height": 2250}},
    {"id": 27992, "title": "A Sunday on La Grande Jatte", "image_id": "def", "is_public_domain": True,
     "artist_display": "Georges Seurat", "date_display": "1884", "thumbnail": {"width": 3000, "height": 2000}},
    {"id": 1, "title": "Thonet Armchair", "image_id": "", "is_public_domain": True, "artist_display": "", "thumbnail": {}}]}
MET_SEARCH = {"total": 2, "objectIDs": [504, 481775]}
MET_OBJ = {504: {"isPublicDomain": True, "primaryImage": "https://images.metmuseum.org/a.jpg",
                 "primaryImageSmall": "https://images.metmuseum.org/s.jpg", "title": "Bentwood Side Chair (Thonet type)",
                 "artistDisplayName": "Gebrüder Thonet", "objectDate": "1870", "objectName": "Side chair",
                 "objectURL": "https://www.metmuseum.org/art/collection/search/504"},
           481775: {"isPublicDomain": False, "primaryImage": "", "title": "Side Chair: Model #398"}}
CMA_JSON = {"data": [{"id": 9, "accession_number": "1966.1", "title": "Chair", "share_license_status": "CC0",
                      "creation_date": "1900", "url": "https://clevelandart.org/art/1966.1", "type": "Furniture",
                      "creators": [{"description": "Michael Thonet (Austrian)"}],
                      "images": {"web": {"url": "https://cdn/x_web.jpg", "width": "900", "height": "700"},
                                 "print": {"url": "https://cdn/x_print.jpg", "width": "3000", "height": "2333"}}}]}


def _museum_get(url, params=None, headers=None, **kw):
    assert "AIC-User-Agent" in (headers or {}) and "Mozilla" in headers["User-Agent"]
    if "artic.edu" in url:
        assert params["query[term][is_public_domain]"] == "true"
        return _R(body=AIC_JSON)
    if "v1.1/search" in url:
        return _R(body=MET_SEARCH)
    if "/objects/" in url:
        return _R(body=MET_OBJ[int(url.rsplit("/", 1)[-1])])
    return _R(body=CMA_JSON)


def test_museums_keep_cc0_matches_and_credit_the_institution(tmp_path):
    mus = M.Museums(cache_dir=tmp_path, get=_museum_get)
    got = mus.search("Thonet chair", limit=6)
    titles = [m["title"] for m in got]
    assert "A Sunday on La Grande Jatte" not in titles            # 검색어 낱말이 하나도 없는 결과(느슨한 검색) 버림
    assert "Side Chair: Model #398" not in titles                  # 메트: 퍼블릭 도메인이 아닌 객체는 그림 없음
    assert {m["src"] for m in got} == {"museum:aic", "museum:met", "museum:cma"}
    aic = next(m for m in got if m["src"] == "museum:aic")
    assert aic["url"].endswith("/full/1383,/0/default.jpg") and aic["thumb_url"].endswith("/full/400,/0/default.jpg")
    assert aic["artist"] == "Designed by Michael Thonet" and aic["tier"] == "A" and aic["lic"]["name"] == "CC0"
    assert aic["institution"] == "Art Institute of Chicago" and aic["origin"] == "museum"
    cma = next(m for m in got if m["src"] == "museum:cma")
    assert cma["url"].endswith("_print.jpg") and cma["width"] == 3000
    # 캐시: 두 번째 검색은 네트워크를 쓰지 않는다
    again = M.Museums(cache_dir=tmp_path, get=lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    assert [m["url"] for m in again.search("Thonet chair", limit=6)] == [m["url"] for m in got]
    assert M.relevant("Michael Thonet", {"title": "Just Dessert", "artist": "William Michael Harnett"}) is False


def test_license_is_confirmed_on_the_source_page():
    flickr = ('<a href="https://creativecommons.org/licenses/by/2.0/">Some rights reserved</a>'
              '"author": {"@type": "Person", "name": "Creative Tools", "url": "x"}'
              '<meta property="og:site_name" content="Flickr" />')
    lic = G.license_from_html("https://www.flickr.com/photos/a/1", flickr)
    assert lic is not None and lic.name == "CC BY 2.0" and lic.tier == "A" and G.page_author(flickr) == "Creative Tools"
    mixed = flickr + '<a href="https://creativecommons.org/licenses/by-nc-sa/2.0/">'
    assert G.license_from_html("https://blog.example/x", mixed) is None            # NC 가 섞이면 버림
    assert G.license_from_html("https://blog.example/x", "<p>© 2024 all rights</p>") is None
    sa = G.license_from_html("https://pxhere.example/p", 'href="//creativecommons.org/publicdomain/zero/1.0/"'
                             'href="https://creativecommons.org/licenses/by-sa/4.0/"')
    assert sa.tier == "A-sa"                                                         # 둘이면 조건이 많은 쪽
    px = G.license_from_html("https://pixabay.com/photos/x-123/", "")
    assert px.tier == "stock" and px.id == "pixabay"
    assert G.skip_host("https://en.wikipedia.org/wiki/Chair") and G.skip_host("https://www.shutterstock.com/x")
    assert G.verify_page("https://en.wikipedia.org/wiki/Chair", fetch=lambda *a, **k: _R(body=flickr)) is None


SERP = {"images_results": [
    {"position": 1, "title": "3D printer", "link": "https://www.flickr.com/photos/a/1", "source": "Flickr",
     "original": "https://live.staticflickr.com/1.jpg", "thumbnail": "https://encrypted-tbn0.gstatic.com/1",
     "original_width": 1600, "original_height": 1066},
    {"position": 2, "title": "Printer — Wikipedia", "link": "https://en.wikipedia.org/wiki/3D_printing",
     "original": "https://upload.wikimedia.org/2.jpg", "thumbnail": "t2", "original_width": 2000, "original_height": 1300},
    {"position": 3, "title": "printer blog", "link": "https://blog.example/post", "source": "blog",
     "original": "https://blog.example/3.jpg", "thumbnail": "t3", "original_width": 1600, "original_height": 1000},
    {"position": 4, "title": "tiny", "link": "https://www.flickr.com/photos/a/4", "original": "https://x/4.jpg",
     "thumbnail": "t4", "original_width": 400, "original_height": 300}]}
PAGES = {"https://www.flickr.com/photos/a/1": '<a href="https://creativecommons.org/licenses/by/2.0/">'
                                            '"author": {"@type":"Person","name":"Creative Tools"}'
                                            '<meta property="og:site_name" content="Flickr" />',
         "https://blog.example/post": "<p>All rights reserved</p>",
         "https://www.flickr.com/photos/a/4": '<a href="https://creativecommons.org/licenses/by/2.0/">'}


def _google(tmp_path, monkeypatch, calls):
    def fake_request(url, params=None, headers=None, **kw):
        if "serpapi.com/search" in url:
            calls.append(dict(params))
            return _R(body=SERP)
        return _R(body=PAGES.get(url, ""))
    monkeypatch.setattr(net, "request", fake_request)
    return G.GoogleImages("k", cache_dir=tmp_path, fetch=fake_request)


def test_google_reusable_results_need_a_confirmed_license(tmp_path, monkeypatch):
    calls: list[dict] = []
    g = _google(tmp_path, monkeypatch, calls)
    got = g.search_photos("3d printer", per_page=6)
    assert [c.url for c in got] == ["https://www.flickr.com/photos/a/1"]     # 위키·확인 못 한 블로그·작은 그림은 버림
    c = got[0]
    assert calls[0]["licenses"] == "fmc" and calls[0]["engine"] == "google_images"
    assert c.credit == "Creative Tools · CC BY 2.0 · Flickr"
    assert "creativecommons.org/licenses/by/2.0" in c.attribution and c.url in c.attribution
    assert not any("k" == p for p in (tmp_path / "x").parts)
    assert all("k" not in f.name.split("_") for f in tmp_path.glob("*.json"))   # 키는 캐시 파일 이름에 넣지 않는다
    quotes = g.quote_candidates("Braun SK 4", n=6)
    assert [q["page"] for q in quotes] == ["https://www.flickr.com/photos/a/1", "https://blog.example/post",
                                           "https://www.flickr.com/photos/a/4"]
    assert "licenses" not in calls[-1]
    q = quotes[1]
    assert q["tier"] == "C" and q["credit"][0] == "이미지: blog" and "저작권법 제28조" in q["credit"][1] \
        and "https://blog.example/post" in q["credit"][1]


def test_hub_calls_google_once_per_request(tmp_path, monkeypatch):
    calls: list[dict] = []
    g = _google(tmp_path, monkeypatch, calls)

    class _Few:
        name, videos, photos, korean = "Pixabay", True, True, True
        remaining = None

        def __init__(self):
            self.calls: list[str] = []

        def search_photos(self, q, **k):
            self.calls.append(q)
            return []
        search_videos = search_photos
    pix = _Few()
    hub = StockHub([pix, g])
    hub.search({"kind": "photo", "query_en": "foam model sanding workshop", "query_ko": "",
                "alt_queries": ["model making workshop", "clay modeling hands"]}, 6)
    # Google(월 250회 무료): 한 요청에 첫 검색어 그대로 한 번만 — 줄인 변형·다른 각도는 다른 제공처가 맡는다
    assert len(pix.calls) > 3 and [c["q"] for c in calls] == ["foam model sanding workshop"]


def test_out_of_searches_turns_google_off_for_the_job(tmp_path, monkeypatch):
    def fake_request(url, params=None, headers=None, **kw):
        return _R(429, {"error": "Your account has run out of searches."})
    monkeypatch.setattr(net, "request", fake_request)
    g = G.GoogleImages("k", cache_dir=tmp_path, fetch=fake_request)
    hub = StockHub([g])
    assert hub.search({"kind": "photo", "query_en": "desk lamp"}, 6) == []
    assert "Google" in hub.disabled
    try:
        g.search_photos("desk lamp")
        raise AssertionError("no error")
    except StockError as e:
        assert e.fatal


def test_page_image_reads_og_image():
    html = ('<meta property="og:site_name" content="Braun"><meta property="og:title" content="SK 4">'
            '<meta content="/img/sk4.jpg" property="og:image"><meta property="og:image:width" content="1600">')
    pi = G.page_image("https://www.braun.example/sk4", fetch=lambda *a, **k: _R(body=html))
    assert pi["url"] == "https://www.braun.example/img/sk4.jpg" and pi["site"] == "Braun" and pi["width"] == 1600


class _Media:
    def candidates(self, info, **kw):
        return []


class _WP:
    ua = "ChoiStudio/test"

    def entity(self, name, names):
        return {"qid": "Q1", "title": name}


class _Resolver:
    wp = _WP()

    def _lead_or_search(self, *a):
        return None


def _ladder(tmp_path, monkeypatch, *, allow_quote: bool, picks: list[dict]):
    pub = tmp_path / "public"
    seen: dict[str, Any] = {}

    def fake_download(url, dst, **kw):
        seen.setdefault("downloads", []).append((url, kw.get("headers") or {}))
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_bytes(_jpg(1800, 1200) if "full" in url or url.endswith(".jpg") else _jpg())
        return Path(dst)
    monkeypatch.setattr(net, "download", fake_download)

    class _Mus:
        def search(self, q, limit=6):
            seen["museum_q"] = q
            return M.Museums(get=_museum_get).search(q, limit=limit)

    class _Web:
        name = "Google"

        def reusable_candidates(self, q, n=6):
            seen["web_q"] = q
            return []

        def quote_candidates(self, q, n=6):
            seen["quote_q"] = q
            return [G.cand_meta({"link": "https://brand.example/p", "original": "https://brand.example/p.jpg",
                                 "thumbnail": "https://t/p", "title": "SK 4", "source": "brand.example"}, lic=G.QUOTE)]

    def pick(text, sheets):
        seen["text"] = text
        return picks
    d = Deps(resolver=_Resolver(), media=_Media(), museums=_Mus(), web=_Web(), allow_quote=allow_quote,
             page_image=lambda u: None, pick=pick, context=lambda seg: "토넷의 의자는 증기로 나무를 휘었다")
    return Ladder(d, public=pub, work=tmp_path / "work"), seen


ITEM = {"need": "entity", "treatment": "hero", "count": 1, "tier_max": "A", "role": "example",
        "subject": {"name_ko": "토넷 14번 의자", "name_en": "Thonet chair", "kind": "product", "shot": "subject",
                    "creator_en": "Michael Thonet"}, "claim": "증기로 휜 나무", "start_seg": 3}


def test_ladder_widens_to_museums_and_credits_them(tmp_path, monkeypatch):
    lad, seen = _ladder(tmp_path, monkeypatch, allow_quote=False,
                        picks=[{"request": 1, "choices": [{"candidate": 1, "score": 3, "shows": "의자 전체"}],
                                "reason": ""}])
    out = lad.run([ITEM])[0]
    assert seen["museum_q"] == "Michael Thonet Thonet chair" and "quote_q" not in seen    # 인용은 tier_max C 일 때만
    assert "그 장면의 말: 「토넷의 의자는" in seen["text"] and "museum:aic" in seen["text"]
    a = out["assets"][0]
    assert out["rung"] == "museum" and a["origin"] == "museum" and a["tier"] == "A"
    assert "Art Institute of Chicago" in a["credit"] and "CC0" in a["credit"]
    first = seen["downloads"][0]
    assert "Mozilla" in first[1]["User-Agent"]                     # 시카고 IIIF 는 브라우저형 UA 가 없으면 403


def test_ladder_quote_only_when_item_and_setting_allow(tmp_path, monkeypatch):
    it = dict(ITEM, tier_max="C", subject={"name_ko": "브라운 SK 4", "name_en": "Braun SK 4", "kind": "product",
                                           "shot": "subject"})
    lad, seen = _ladder(tmp_path, monkeypatch, allow_quote=True,
                        picks=[{"request": 1, "choices": [{"candidate": 1, "score": 3, "shows": "라디오"}]}])
    out = lad.run([it])[0]
    a = out["assets"][0]
    assert seen["quote_q"] == "Braun SK 4" and a["tier"] == "C" and out["rung"] == "web"
    assert a["credit"] == "이미지: brand.example" and "https://brand.example/p" in a["credit_full"] \
        and "인용" in a["credit_full"]
    assert "인용 — 그 대상 자체를 설명하는 문장에서만" in seen["text"]
    lad2, seen2 = _ladder(tmp_path / "b", monkeypatch, allow_quote=False, picks=[])
    lad2.run([it])
    assert "quote_q" not in seen2                                  # 설정에서 인용이 꺼져 있으면 찾지도 않는다


def test_unpicked_candidates_are_not_downloaded_in_place_of_the_pick(tmp_path):
    from studio.stock.research import tag_hits
    st = {"query_en": "foam model sanding", "alt_queries": ["model making workshop"]}
    beach = StockCandidate("photo", "1", "u", "", "d", 1920, 1080, alt="ocean, foam, beach, sand")
    shop = StockCandidate("photo", "2", "u", "", "d", 1920, 1080, alt="model, making, workshop, tools")
    assert tag_hits(st, beach) == 0 and tag_hits(st, shop) >= 2
