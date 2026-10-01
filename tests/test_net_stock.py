"""스톡·효과음이 '하나도' 안 되던 원인들의 회귀 테스트(네트워크 없이).

- Pixabay CDN 은 몰아서 받으면 403 → 방식 바꿔 다시 시도·간격(studio.net)
- 긴 묘사형 검색어는 0~1건 → 검색어를 줄여 가며 재검색
- 검색 0건·다운로드 실패를 '없음'으로 영구 캐시하던 문제
- 진단 자료에 키 값이 들어가지 않음
"""
from __future__ import annotations

import json
import ssl
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import net  # noqa: E402
from studio.stock.base import StockCandidate  # noqa: E402
from studio.stock.providers import StockHub, query_variants  # noqa: E402
from studio.stock.research import StockResearcher  # noqa: E402


def _fake_impl(monkeypatch, script):
    """script: 방식 → 응답 목록(차례로). 예외 인스턴스면 raise."""
    calls = []

    def mk(name):
        def f(url, headers, timeout, dst):
            calls.append(name)
            r = script[name].pop(0) if script.get(name) else net.Response(599)
            if isinstance(r, Exception):
                raise r
            if dst is not None and r.ok:
                dst.write_bytes(r.content or b"data")
            return r
        return f
    monkeypatch.setattr(net, "_IMPL", {k: mk(k) for k in net.STRATEGIES})
    monkeypatch.setattr(net, "ROUND_WAIT", (0.0, 0.0, 0.0))
    monkeypatch.setattr(net, "HOST_GAPS", {})
    monkeypatch.setattr(net, "HOST_GAP", 0.0)
    net._best.clear()
    net.ERRORS.clear()
    net.STATS.clear()
    return calls


def test_net_falls_back_on_certificate_error_and_cloudflare_block(monkeypatch, tmp_path):
    calls = _fake_impl(monkeypatch, {
        "requests": [ssl.SSLCertVerificationError("self-signed certificate in certificate chain")],
        "urllib": [net.Response(403, b"blocked")],
        "curl": [net.Response(200, b"mp3")],
    })
    dst = tmp_path / "a.mp3"
    net.download("https://cdn.pixabay.com/audio/x.mp3", dst)
    assert dst.read_bytes() == b"mp3" and calls == ["requests", "urllib", "curl"]
    assert net._best["cdn.pixabay.com"] == "curl"
    text = "\n".join(net.summary())
    assert "self-signed" in text and "HTTP 403" in text   # 진단에 이유가 남는다


def test_net_retries_rounds_when_everything_is_blocked(monkeypatch):
    calls = _fake_impl(monkeypatch, {
        "requests": [net.Response(403), net.Response(200, b"{}")],
        "urllib": [net.Response(403)], "curl": [net.Response(403)],
    })
    r = net.request("https://cdn.pixabay.com/photo/x.jpg")
    assert r.ok and calls == ["requests", "urllib", "curl", "requests"]


def test_query_variants_shorten_descriptive_queries():
    v = query_variants("designer sketching wireframes on paper notebook")
    assert v[0] == "designer sketching wireframes on paper notebook"
    assert "designer sketching wireframes" in v and "designer sketching" in v and len(v) == len(set(v))


class _Prov:
    name, videos, photos, korean = "Pixabay", True, True, True

    def __init__(self, hit_words=2):
        self.hit_words, self.calls, self.remaining = hit_words, [], None

    def search_videos(self, q, **k):
        self.calls.append(q)
        if len(q.split()) > self.hit_words:        # 단어가 많으면 0건(AND 검색)
            return []
        return [StockCandidate("video", f"{q}{i}", "u", "", "d", 1920, 1080, 8.0, "a", provider="Pixabay")
                for i in range(4)]

    search_photos = search_videos


def test_hub_relaxes_query_until_enough_hits():
    p = _Prov()
    hub = StockHub([p])
    got = hub.search({"kind": "video", "query_en": "designer sketching wireframes on paper"}, 6)
    assert len(got) == 4 and p.calls[-1] == "designer sketching"
    assert "designer sketching" in hub.last_trace[-1]


def test_failures_are_not_cached_forever_but_rejections_are(tmp_path, monkeypatch):
    public = tmp_path / "public"
    monkeypatch.setattr(StockResearcher, "_thumb", lambda self, c: None)

    def g(q):
        return {"template": "broll", "stock": {"kind": "video", "query_en": q, "query_ko": "", "purpose": "",
                                                "must_show": ""}}
    boom = {"n": 0}

    def bad_fetch(self, c):
        boom["n"] += 1
        raise RuntimeError("HTTP 403")
    monkeypatch.setattr(StockResearcher, "_fetch", bad_fetch)
    lists = [[g("desk"), g("hands")]]
    r = StockResearcher(StockHub([_Prov()]), ff=None, work=tmp_path, public=public,
                        pick=lambda t, s: [{"request": 1, "candidate": 1}, {"request": 2, "candidate": -1}])
    r.run(lists)
    assert r.stats["download_failed"] == 1 and r.stats["rejected"] == 1 and boom["n"] == 3   # 다른 후보까지 시도
    cache = json.loads((tmp_path / "stock.json").read_text(encoding="utf-8"))
    assert sorted(v["why"] for v in cache.values()) == ["download_failed", "rejected"]

    # 다음 실행: 다운로드 실패한 요청만 다시 시도해서 성공
    def good_fetch(self, c):
        dst = public / "broll" / "ok.mp4"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"x")
        return {"src": "broll/ok.mp4", "kind": "video", "credit": c.credit, "url": c.url, "author_url": ""}
    monkeypatch.setattr(StockResearcher, "_fetch", good_fetch)
    lists2 = [[g("desk"), g("hands")]]
    r2 = StockResearcher(StockHub([_Prov()]), ff=None, work=tmp_path, public=public,
                         pick=lambda t, s: [{"request": 1, "candidate": 1}])
    r2.run(lists2)
    assert [x.get("src") for x in lists2[0]] == ["broll/ok.mp4"] and r2.stats["used"] == 1


def test_diagnostics_zip_hides_keys(tmp_path):
    from studio import diag
    from studio.settings import Settings

    class P:
        pass
    p = P()
    p.title, p.dir = "테스트", tmp_path
    p.work, p.extras, p.render_dir = tmp_path / "work", tmp_path / "output" / "부가자료", tmp_path / "render"
    p.work.mkdir(parents=True)
    (p.work / "plan.json").write_text("{}", encoding="utf-8")
    (p.work / "big.wav").write_bytes(b"0" * 10)
    p.settings = Settings()
    p.settings.pixabay_api_key = "SECRET-KEY-123"
    z = diag.write(p, error="boom")
    names = zipfile.ZipFile(z).namelist()
    assert "work/plan.json" in names and "work/진단.md" in names and "work/big.wav" not in names
    md = (p.work / "진단.md").read_text(encoding="utf-8")
    assert "pixabay_api_key: 있음" in md and "SECRET-KEY-123" not in md
    assert all(b"SECRET-KEY-123" not in zipfile.ZipFile(z).read(n) for n in names)


class _FlakyProvider:
    """처음엔 일시 차단(403), 그다음엔 정상 — 예전엔 한 번 막히면 작업 끝까지 제외됐다."""
    name = "Pixabay"
    videos = photos = True
    korean = False

    def __init__(self, fatal=False):
        self.n = 0
        self.fatal = fatal

    def search_photos(self, q, per_page=6, locale=""):
        from studio.stock.base import StockError
        self.n += 1
        if self.n == 1:
            raise StockError("막힘", fatal=self.fatal)
        return [StockCandidate(kind="photo", id=self.n, url="u", thumb="", download="d", width=1, height=1,
                               provider=self.name)]

    def search_images(self, q, image_type="vector", per_page=6):
        return [StockCandidate(kind="photo", id=99, url="https://pixabay.com/x", thumb="", download="d", width=64,
                               height=32, author="kim", provider=self.name)]

    def download(self, c, dst):
        from PIL import Image
        dst.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (64, 32), (255, 0, 0, 0)).save(dst, "PNG")
        return dst


def test_transient_block_does_not_disable_provider_for_the_whole_job(monkeypatch):
    import studio.stock.providers as P
    monkeypatch.setattr(P.time, "sleep", lambda s: None)
    prov = _FlakyProvider()
    hub = StockHub([prov])
    assert hub._call(prov, "search_photos", "chair") == []          # 일시 차단 → 이 검색만 건너뜀
    assert "Pixabay" not in hub.disabled
    assert len(hub._call(prov, "search_photos", "chair")) == 1     # 다음 검색은 된다
    bad = _FlakyProvider(fatal=True)
    hub2 = StockHub([bad])
    hub2._call(bad, "search_photos", "chair")
    assert "Pixabay" in hub2.disabled                               # 키 오류만 끈다


def test_motion_scene_pixabay_images_are_downloaded_and_rewritten(tmp_path):
    prov = _FlakyProvider()
    hub = StockHub([prov])
    res = StockResearcher(hub, ff=None, work=tmp_path / "work", public=tmp_path / "public")
    spec = {"elements": [{"type": "image", "src": "pixabay:vector:light bulb", "w": 30, "h": 30, "frame": "cutout"},
                         {"type": "text", "text": "아이디어"}]}
    lists = [[{"template": "motion", "spec": spec}, {"template": "keyword", "title": "x"}]]
    assert res.resolve_images(lists) == 1
    el = spec["elements"][0]
    assert el["src"].startswith("broll/img_") and el["src"].endswith(".png")      # 투명 PNG 는 PNG 로
    assert (tmp_path / "public" / el["src"]).exists() and res.credits[0]["origin"] == "Pixabay"


def test_query_shortening_keeps_what_must_be_seen():
    """'노트북으로 작업하는 디자이너' — 줄여도 'designer working' 이 아니라 'designer laptop'(보여야 할 물건이 남는다),
    한국어 대체 검색은 동음이의어를 풀어 쓴다(제공처 번역이 '노트북' → notebook 으로 가지 않게)."""
    from studio.stock.providers import ko_query, query_variants
    v = query_variants("designer working on laptop")
    assert v[0] == "designer working on laptop" and "designer laptop" in v
    assert "designer working" not in v and all(x.lower() != "working" for x in v)
    assert ko_query("노트북") == "노트북 컴퓨터" and ko_query("노트북 컴퓨터") == "노트북 컴퓨터"
    assert ko_query("스케치하는 학생") == "스케치하는 학생"


def test_openverse_filters_nc_nd_and_uses_attribution(monkeypatch):
    """P0-3(10/1: 화면에 CC BY-NC 사진): 요청에 license_type=commercial,modification, 응답도 한 번 더 걸러 nc·nd·sampling 을
    버리고, 화면 출처는 짧게 · 업로드 정보는 attribution 전문."""
    from studio.stock.openverse import Openverse, license_ok
    resp = {"results": [
        {"id": "a", "title": "Sketchbook", "url": "https://x/a.jpg", "width": 2000, "height": 1300, "creator": "Kim",
         "license": "by-nc", "license_version": "2.0", "source": "flickr", "attribution": "A by Kim, CC BY-NC 2.0"},
        {"id": "b", "title": "Mood board", "url": "https://x/b.jpg", "width": 2000, "height": 1300, "creator": "Lee",
         "license": "by-nd", "license_version": "4.0", "source": "flickr", "attribution": "B"},
        {"id": "c", "title": "Design desk", "url": "https://x/c.jpg", "width": 2400, "height": 1600, "creator": "Park",
         "license": "by-sa", "license_version": "4.0", "source": "wikimedia",
         "foreign_landing_url": "https://commons.wikimedia.org/wiki/File:C.jpg",
         "attribution": '"Design desk" by Park is licensed under CC BY-SA 4.0. To view a copy of this license, visit '
                        'https://creativecommons.org/licenses/by-sa/4.0/.'},
        {"id": "d", "title": "Old print", "url": "https://x/d.jpg", "width": 1800, "height": 1200, "creator": "",
         "license": "pdm", "license_version": "", "source": "smithsonian", "attribution": "Old print, public domain"},
        {"id": "e", "title": "tiny", "url": "https://x/e.jpg", "width": 600, "height": 400, "creator": "Choi",
         "license": "cc0", "source": "x", "attribution": ""}]}
    seen = {}

    def fake(self, url, params, headers=None):
        seen.update(params)
        return resp
    monkeypatch.setattr(Openverse, "_get_json", fake)
    got = Openverse().search_photos("design desk", per_page=6)
    assert seen["license_type"] == "commercial,modification"
    assert [c.id for c in got] == ["c", "d"]                     # nc·nd·작은 것 제외
    assert got[0].credit == "Park · CC BY-SA 4.0 · wikimedia via Openverse"
    assert got[0].attribution.startswith('"Design desk" by Park is licensed under CC BY-SA 4.0')
    assert got[1].credit == "Public Domain · smithsonian via Openverse"
    assert not any(license_ok(c) for c in ("by-nc", "by-nd", "by-nc-sa", "by-nc-nd", "sampling+", "", "nc-sampling+"))
    assert all(license_ok(c) for c in ("by", "by-sa", "cc0", "pdm"))
