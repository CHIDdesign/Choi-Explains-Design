"""고유명사 자료 사진: 위키백과 대표 이미지 조회(가짜 HTTP), 라이선스 필터, 해석 순서, 규칙 기반 고유명사 찾기, 계획 반영."""
from __future__ import annotations

import json
from pathlib import Path

from studio import net
from studio.agents import schemas as S
from studio.agents.studio import merge_plan
from studio.broll.entities import find_entities
from studio.broll.images import ImageResult, resolve_image
from studio.broll.wikipedia import WikipediaImages, _file_name_from_url
from studio.director.plan import _clean_graphic


def _resp(status: int, data=None, headers=None) -> net.Response:
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else b""
    return net.Response(status, body, headers or {})


def _fake_wiki(monkeypatch, routes: dict[str, object], downloads: list[str]):
    """routes: URL 조각 → 응답 dict(또는 404 를 뜻하는 None). 순서대로 첫 일치."""
    def request(url, *, params=None, headers=None, timeout=30.0, dst=None, rounds=3):
        full = url + ("?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else "")
        for key, data in routes.items():
            if key in full:
                return _resp(404) if data is None else _resp(200, data)
        return _resp(500)

    def download(url, dst: Path, *, timeout=180.0, headers=None, rounds=3):
        downloads.append(url)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"\xff\xd8jpg")
        return dst

    monkeypatch.setattr(net, "request", request)
    monkeypatch.setattr(net, "download", download)


SUMMARY_KO = {"type": "standard", "title": "디터 람스", "description": "독일의 산업 디자이너",
              "originalimage": {"source": "https://upload.wikimedia.org/wikipedia/commons/2/23/Dieter_Rams_2010.jpg",
                                "width": 1600, "height": 1200},
              "content_urls": {"desktop": {"page": "https://ko.wikipedia.org/wiki/디터_람스"}}}
FILE_OK = {"query": {"pages": [{"title": "File:Dieter_Rams_2010.jpg", "imageinfo": [{
    "url": "https://upload.wikimedia.org/wikipedia/commons/2/23/Dieter_Rams_2010.jpg",
    "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/23/Dieter_Rams_2010.jpg/1920px-Dieter_Rams_2010.jpg",
    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Dieter_Rams_2010.jpg", "mime": "image/jpeg",
    "width": 1600, "height": 1200,
    "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 3.0"}, "Artist": {"value": "<a href='x'>Vitsœ</a>"}}}]}]}}
FILE_NONFREE = {"query": {"pages": [{"title": "File:Poster.jpg", "imageinfo": [{
    "url": "https://upload.wikimedia.org/wikipedia/ko/1/11/Poster.jpg", "mime": "image/jpeg", "width": 800, "height": 1200,
    "extmetadata": {"LicenseShortName": {"value": "Fair use"}, "NonFree": {"value": "true"}}}]}]}}


def test_file_name_from_url():
    assert _file_name_from_url("https://upload.wikimedia.org/wikipedia/commons/2/23/Dieter_Rams_2010.jpg") == "Dieter_Rams_2010.jpg"
    assert _file_name_from_url("https://upload.wikimedia.org/wikipedia/commons/thumb/2/23/A%20b.jpg/800px-A_b.jpg") == "A b.jpg"


def test_lookup_uses_page_image_with_free_license(monkeypatch, tmp_path):
    downloads: list[str] = []
    _fake_wiki(monkeypatch, {"ko.wikipedia.org/api/rest_v1/page/summary/": SUMMARY_KO,
                             "commons.wikimedia.org": FILE_OK}, downloads)
    wp = WikipediaImages(log=lambda *_: None, cache_dir=tmp_path / "cache")
    res = wp.fetch("디터 람스", tmp_path / "img")
    assert res is not None and res.origin == "wikipedia"
    assert res.path.name == "wp_디터_람스.jpg" and res.path.exists()
    assert "Vitsœ" in res.credit and "CC BY-SA 3.0" in res.credit and "Wikipedia (디터 람스)" in res.credit
    assert downloads and "1920px" in downloads[0]                 # 1920px 썸네일을 받는다
    # 캐시: 두 번째는 HTTP 없이
    monkeypatch.setattr(net, "request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no http")))
    assert wp.lookup("디터 람스")["title"] == "디터 람스"


def test_lookup_falls_back_to_search_and_english_and_skips_nonfree(monkeypatch, tmp_path):
    downloads: list[str] = []
    routes = {
        # ko: 직접 제목 없음 → 검색 → 동음이의 제외 → 요약(비자유 이미지) → en 으로
        "ko.wikipedia.org/api/rest_v1/page/summary/%EB%B8%8C%EB%9D%BC%EC%9A%B4_SK4": None,
        "ko.wikipedia.org/w/api.php?action=query&list=search": {"query": {"search": [
            {"title": "브라운 (동음이의)", "snippet": "동음이의 문서"}, {"title": "브라운 SK 4", "snippet": "라디오"}]}},
        "ko.wikipedia.org/api/rest_v1/page/summary/%EB%B8%8C%EB%9D%BC%EC%9A%B4_SK_4": {
            "type": "standard", "title": "브라운 SK 4",
            "originalimage": {"source": "https://upload.wikimedia.org/wikipedia/ko/1/11/Poster.jpg"}},
        "commons.wikimedia.org": {"query": {"pages": [{"title": "File:Poster.jpg", "missing": True}]}},
        "ko.wikipedia.org/w/api.php?action=query&titles=File": FILE_NONFREE,
        "en.wikipedia.org/api/rest_v1/page/summary/": {
            "type": "standard", "title": "Braun SK 4",
            "originalimage": {"source": "https://upload.wikimedia.org/wikipedia/commons/2/23/Dieter_Rams_2010.jpg"}},
    }
    # en 의 파일은 커먼즈에 있고 자유 라이선스 — commons 라우트는 첫 일치가 missing 이므로 en 용은 별도 키로
    class Router:
        def __init__(self):
            self.n_commons = 0

    r = Router()
    orig_routes = dict(routes)

    def request(url, *, params=None, headers=None, timeout=30.0, dst=None, rounds=3):
        full = url + ("?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else "")
        if "commons.wikimedia.org" in full:
            r.n_commons += 1
            return _resp(200, orig_routes["commons.wikimedia.org"] if r.n_commons == 1 else FILE_OK)
        for key, data in orig_routes.items():
            if key in full:
                return _resp(404) if data is None else _resp(200, data)
        return _resp(500)

    monkeypatch.setattr(net, "request", request)
    monkeypatch.setattr(net, "download", lambda url, dst, **k: (downloads.append(url), dst.write_bytes(b"x"), dst)[2])
    logs: list[str] = []
    wp = WikipediaImages(log=logs.append)
    res = wp.fetch("브라운 SK4", tmp_path)
    assert res is not None and "Wikipedia (Braun SK 4)" in res.credit
    assert any("자유 라이선스가 아님" in x for x in logs)


def test_license_filter():
    ok = WikipediaImages.license_ok
    assert ok({"license": "CC BY-SA 4.0"}) and ok({"license": "Public domain"}) and ok({"license": "CC0"})
    assert not ok({"license": "CC BY-NC 2.0"}) and not ok({"license": "CC BY-ND 4.0"})
    assert not ok({"license": "CC BY 4.0", "restrictions": "trademarked"})
    assert not ok({"license": "Fair use"}) and not ok({"license": ""}) and not ok({"license": "CC BY 4.0", "nonfree": "true"})


def test_resolve_prefers_wikipedia_over_commons(tmp_path):
    calls: list[str] = []

    class WP:
        def fetch(self, q, d):
            calls.append("wp:" + q)
            return ImageResult(d / "wp.jpg", "A · CC0 · Wikipedia (X)", "CC0", "", "wikipedia")

    class WM:
        def fetch(self, q, d):
            calls.append("wm:" + q)
            return None

    res = resolve_image("Dieter Rams", local=[], dst_dir=tmp_path, wikimedia=WM(), wikipedia=WP())
    assert res and res.origin == "wikipedia" and calls == ["wp:Dieter Rams"]

    class WP2(WP):
        def fetch(self, q, d):
            calls.append("wp:" + q)
            return None

    calls.clear()
    assert resolve_image("x", local=[], dst_dir=tmp_path, wikimedia=WM(), wikipedia=WP2()) is None
    assert calls == ["wp:x", "wm:x"]


def test_find_entities_is_conservative():
    text = ("오늘은 Dieter Rams 이야기입니다. The Design is good. 브라운의 Braun SK 4 라디오, 그리고 『디자인의 디자인』이라는 책. "
            "불교와 기독교의 건축도 봅니다. Dieter Rams 는 두 번 나옵니다. Less but Better 라는 말도 있죠. Design Council 도.")
    ents = find_entities(text)
    terms = [e.term for e in ents]
    assert terms[:1] == ["Dieter Rams"]                       # 등장 순서
    assert "Braun SK 4" in terms and "디자인의 디자인" in terms and "불교" in terms and "기독교" in terms
    assert "Design Council" in terms and "Less but Better" not in terms   # 소문자 낱말이 섞인 구는 이름이 아니다
    assert "The Design" not in terms and terms.count("Dieter Rams") == 1
    kinds = {e.term: e.kind for e in ents}
    assert kinds["디자인의 디자인"] == "work" and kinds["불교"] == "religion" and kinds["Dieter Rams"] == "name"


def test_merge_plan_and_clean_keep_wiki_flag():
    raw, _ = merge_plan({"stock": {"requests": [], "photos": [
        {"start_seg": 4, "start_word": "디터", "name_ko": "디터 람스", "name_en": "Dieter Rams", "kind": "person",
         "layout": "pip", "reason": "인물"},
        {"start_seg": 5, "start_word": "", "name_ko": "", "name_en": "", "kind": "other", "layout": "pip", "reason": ""}]}})
    photos = [g for g in raw["graphics"] if g["template"] == "photo"]
    assert len(photos) == 1 and photos[0]["wiki"] is True and photos[0]["image"] == "디터 람스"
    assert photos[0]["subtitle"] == "Dieter Rams" and raw["studio"]["wiki_photos"] == 2
    cleaned = _clean_graphic(photos[0], [4, 5])
    assert cleaned and cleaned.get("wiki") is True and cleaned["layout"] == "pip"
    assert "photos" in S.STOCK["properties"] and "person" in S.PHOTO_KINDS


# ---------------------------------------------------------------------------
# 브랜드 → 로고, 사람 → 가장 품위 있는 초상
# ---------------------------------------------------------------------------

SI_DATA = [{"title": "Pinterest", "slug": "pinterest", "hex": "BD081C", "source": "https://business.pinterest.com"},
           {"title": "Kakao", "slug": "kakao", "hex": "FFCD00", "source": "https://www.kakaocorp.com",
            "aliases": {"loc": {"ko-KR": "카카오"}}},
           {"title": "Apple Music", "slug": "applemusic", "hex": "FA243C", "source": "x"}]
SI_SVG = '<svg role="img" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><title>P</title><path d="M12 0C5 0 0 5 0 12z"/></svg>'


def _fake_si(monkeypatch, calls: list[str]):
    def request(url, *, params=None, headers=None, timeout=30.0, dst=None, rounds=3):
        calls.append(url)
        if url.endswith("simple-icons.json"):
            return _resp(200, SI_DATA)
        if url.endswith("/icons/pinterest.svg") or url.endswith("/icons/kakao.svg"):
            return net.Response(200, SI_SVG.encode())
        return _resp(404)
    monkeypatch.setattr(net, "request", request)


def test_simple_icons_logo_card(monkeypatch, tmp_path):
    from studio.broll.logos import PAPER, SimpleIcons, contrast
    calls: list[str] = []
    _fake_si(monkeypatch, calls)
    si = SimpleIcons(tmp_path / "cache")
    assert si.find(["핀터레스트", "Pinterest Inc."])["slug"] == "pinterest"     # 법인 꼬리 무시
    assert si.find(["Apple"]) is None                                           # 비슷한 이름(Apple Music) 금지
    assert si.find(["카카오"])["slug"] == "kakao"                                # 한국어 별칭
    res = si.fetch(["Pinterest"], tmp_path / "images")
    svg = res.path.read_text(encoding="utf-8")
    assert res.origin == "logo" and res.path.suffix == ".svg" and "CC0" in res.credit
    assert f'fill="{PAPER}"' in svg and 'fill="#BD081C"' in svg and "M12 0C5" in svg
    kakao = si.fetch(["Kakao"], tmp_path / "images").path.read_text(encoding="utf-8")
    assert contrast("#FFCD00", PAPER) < 2.2 and 'rx=' in kakao and 'fill="#26211E"' in kakao   # 노랑은 타일 위 잉크 마크
    n = len(calls)
    SimpleIcons(tmp_path / "cache").find(["Pinterest"])                          # 목록은 디스크 캐시
    assert len(calls) == n


class _FakeWP:
    ua = "test"

    def __init__(self, info, cands=(), lead=None):
        self.info, self.cands, self.lead = info, list(cands), lead
        self.fetched: list[str] = []

    def entity(self, term, names=()):
        return self.info

    def portrait_candidates(self, info, limit=8):
        return self.cands

    def logo_meta(self, info):
        return None

    def fetch(self, term, dst_dir):
        self.fetched.append(term)
        return self.lead


def test_brand_never_falls_back_to_executive_photo(tmp_path):
    """'핀터레스트를 참고해서 디자인한다' — 위키백과 대표 이미지(창업자의 SXSW 사진)로 넘어가지 않는다."""
    from studio.broll.resolve import MediaResolver
    lead = ImageResult(tmp_path / "Silbermann_at_SXSW.jpg", "Anya · CC BY 2.0")
    wp = _FakeWP({"human": False, "logos": [], "lead": "Silbermann_at_SXSW.jpg", "title": "핀터레스트"}, lead=lead)
    r = MediaResolver(local=[], dst_dir=tmp_path / "img", work_dir=tmp_path, wikimedia=None, wikipedia=wp, logos=None)
    p = r.plan("핀터레스트", "brand", ("Pinterest",))
    assert p.kind == "brand" and p.result is None and wp.fetched == []
    # 규칙 경로(종류 모름)라도 위키데이터에 로고가 있는 사람 아닌 항목이면 브랜드
    wp2 = _FakeWP({"human": False, "logos": ["Pinterest Logo.svg"], "lead": "x.jpg", "title": "Pinterest"}, lead=lead)
    p2 = MediaResolver(local=[], dst_dir=tmp_path / "img", work_dir=tmp_path, wikimedia=None, wikipedia=wp2,
                       logos=None).plan("Pinterest", "", ())
    assert p2.kind == "brand" and wp2.fetched == []
    # AI 가 brand 라고 해도 위키데이터가 사람이면 사람
    wp3 = _FakeWP({"human": True, "logos": [], "title": "Ben Silbermann"}, cands=[{"name": "a.jpg"}])
    p3 = MediaResolver(local=[], dst_dir=tmp_path / "img", work_dir=tmp_path, wikimedia=None, wikipedia=wp3,
                       logos=None).plan("Ben Silbermann", "brand", ())
    assert p3.kind == "person" and p3.candidates


def test_portrait_rules_prefer_composed_portraits_over_event_shots():
    from studio.broll.resolve import meta_score
    event = {"name": "Silbermann at SXSW 2012.jpg", "src": "lead", "width": 5184, "height": 3456}
    panel = {"name": "Dieter Rams speaking with students.jpg", "src": "category", "width": 2000, "height": 1300}
    portrait = {"name": "Dieter Rams portrait (cropped).jpg", "src": "category", "width": 1200, "height": 1500}
    curated = {"name": "Dieter Rams 2010.jpg", "src": "wikidata", "width": 1600, "height": 1900}
    s = {k: meta_score(m)[0] for k, m in {"event": event, "panel": panel, "portrait": portrait, "curated": curated}.items()}
    assert s["portrait"] > s["event"] and s["portrait"] > s["panel"] and s["curated"] > s["panel"]
    assert "행사·인터뷰·단체 사진" in meta_score(event)[1]


def test_portrait_and_logo_license_rules():
    from studio.broll.wikipedia import logo_license_ok, portrait_license_ok
    assert logo_license_ok({"license": "Public domain", "restrictions": "trademarked"})
    assert not logo_license_ok({"license": "Fair use", "restrictions": "trademarked"})
    assert not logo_license_ok({"license": "CC BY-SA 4.0", "restrictions": "trademarked|personality"})
    assert portrait_license_ok({"license": "CC BY 2.0", "restrictions": "personality"})
    assert not portrait_license_ok({"license": "CC BY 2.0", "restrictions": "trademarked"})
    assert not WikipediaImages.license_ok({"license": "CC BY 2.0", "restrictions": "personality"})   # 일반 경로는 그대로


def test_merge_plan_keeps_entity_kind_for_logo_and_portrait():
    raw_long, _ = merge_plan({"stock": {"photos": [
        {"start_seg": 2, "start_word": "핀터레스트", "name_ko": "핀터레스트", "name_en": "Pinterest", "kind": "brand",
         "layout": "pip", "reason": "참고 서비스"}]}})
    g = raw_long["graphics"][0]
    assert g["entity"] == "brand" and g["name_en"] == "Pinterest" and g["body"] == "브랜드"   # 화면에 'brand' 영어 금지
    clean = _clean_graphic({**g, "logo": True}, {2})
    assert clean["entity"] == "brand" and clean["name_en"] == "Pinterest" and clean["logo"] is True


def _jpeg(path: Path, color=(180, 150, 130)) -> None:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (400, 500), color).save(path, "JPEG")


def test_pick_portraits_uses_vision_then_rules(monkeypatch, tmp_path):
    """후보 썸네일 → 규칙 점수 → AI 비전 선택(있으면) → 1920px 받기. AI 가 없으면 규칙 점수 1위(행사 사진이 아닌 것)."""
    from types import SimpleNamespace

    from studio.broll.resolve import MediaPlan, MediaResolver
    from studio.pipeline import Pipeline

    def download(url, dst: Path, *, timeout=180.0, headers=None, rounds=3):
        _jpeg(dst)
        return dst
    monkeypatch.setattr(net, "download", download)
    cands = [{"name": "Rams at Design Conference 2015.jpg", "src": "lead", "width": 3000, "height": 2000,
              "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/x.jpg/1920px-x.jpg",
              "license": "CC BY 2.0", "artist": "A", "mime": "image/jpeg"},
             {"name": "Dieter Rams portrait.jpg", "src": "category", "width": 1200, "height": 1500,
              "url": "https://upload.wikimedia.org/wikipedia/commons/c/cd/y.jpg", "license": "CC BY-SA 4.0",
              "artist": "B", "mime": "image/jpeg"}]
    wp = _FakeWP({"human": True, "title": "디터 람스"})
    r = MediaResolver(local=[], dst_dir=tmp_path / "img", work_dir=tmp_path / "work", wikimedia=None, wikipedia=wp,
                      logos=None)
    logs: list[str] = []
    asked: list[str] = []

    class Studio:
        def pick_portrait(self, ctx, text, sheets):
            asked.append(text)
            assert sheets and sheets[0][0] == "R1" and sheets[0][1][:2] == b"\xff\xd8"
            return [{"request": 1, "candidate": 1, "reason": "단정한 표정"}]

    # AI 있음: 비전이 C1 을 고르면 규칙 점수와 달라도 C1
    p = MediaPlan("디터 람스", "person", candidates=[dict(c) for c in cands], info=wp.info)
    me = SimpleNamespace(_ensure_studio=lambda: Studio(), ctx="", log=logs.append)
    Pipeline._pick_portraits(me, r, [p])
    assert asked and "R1 디터 람스" in asked[0] and "규칙 점수" in asked[0]
    assert p.result is not None and p.result.path.exists() and "Rams_at_Design" in p.result.path.name
    assert "A · CC BY 2.0 · Wikimedia Commons (디터 람스)" == p.result.credit
    # AI 없음: 규칙 점수 1위 = 행사 사진이 아닌 초상
    p2 = MediaPlan("디터 람스", "person", candidates=[dict(c) for c in cands], info=wp.info)
    Pipeline._pick_portraits(SimpleNamespace(_ensure_studio=lambda: None, ctx="", log=logs.append), r, [p2])
    assert p2.result is not None and "portrait" in p2.result.path.name
