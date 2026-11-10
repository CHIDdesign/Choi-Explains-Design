"""자료 출처 v2: 라익스 권리 판정 · NASA 필터 · 제공처 안내표 · 작업당 키 점검 · 못구한자료.md · 설정 창(네트워크 없음, 응답은 인라인)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from studio.assets import museums as M  # noqa: E402
from studio.stock import nasa as N  # noqa: E402
from studio.stock.sources import key_hint, status  # noqa: E402


class _R:
    status = 200
    ok = True
    headers: dict[str, str] = {}

    def __init__(self, body: Any):
        self.text = json.dumps(body)

    def json(self) -> Any:
        return json.loads(self.text)


IIIF = "https://iiif.micr.io/abc/full/max/0/default.jpg"
ZERO = "https://creativecommons.org/publicdomain/zero/1.0/"
MARK = "https://creativecommons.org/publicdomain/mark/1.0/"
INC = "https://rightsstatements.org/vocab/InC/1.0/"


def _rijks_rec(rights: str, *, timespan: Any = None) -> dict[str, Any]:
    return {"subject_to": [{"classified_as": [{"id": ZERO}]}],     # 맨 위 CC0 는 메타데이터의 것 — 저작권 있는 그림에도 붙어 있다
            "subject_of": [{"digitally_carried_by": [
                {"access_point": [{"id": IIIF}], "referred_to_by": [{"content": rights}]},
                {"format": "text/html", "access_point": [{"id": "https://www.rijksmuseum.nl/en/collection/SK-1"}]}]}],
            "identified_by": [{"type": "Identifier", "content": "SK-1"},
                              {"type": "Name", "content": "De stoel", "language": [{"id": "http://x/300388256"}]},
                              {"type": "Name", "content": "Thonet chair", "language": [{"id": f"http://x/{M.RIJKS_EN}"}]}],
            "produced_by": {"timespan": timespan if timespan is not None else {"identified_by": [{"content": "1860"}]},
                            "carried_out_by": [{"notation": [{"@language": "en", "@value": "Michael Thonet"}]}]}}


def test_rijks_trusts_only_the_image_record_rights():
    assert M.rijks_open_image(_rijks_rec(INC)) is None                       # 맨 위 CC0 에 속지 않는다
    assert M.rijks_open_image(_rijks_rec(ZERO)) == (IIIF, "CC0")
    assert M.rijks_open_image(_rijks_rec(MARK)) == (IIIF, "Public Domain")
    rec = _rijks_rec(ZERO)
    rec["subject_of"][0]["digitally_carried_by"][0]["access_point"] = []     # 이미지 주소가 없으면 쓰지 않는다
    assert M.rijks_open_image(rec) is None


def test_rijks_search_builds_candidates_and_survives_a_bad_record():
    """timespan 은 객체이기도 목록이기도 하고(실호출에서 전체가 죽었다), 레코드 하나가 깨져도 나머지는 쓴다."""
    recs = {"https://id/1": _rijks_rec(ZERO), "https://id/2": _rijks_rec(INC),
            "https://id/3": _rijks_rec(MARK, timespan=[{"identified_by": [{"content": "1870"}]}]),
            "https://id/4": {"subject_of": "깨진 레코드"}}

    def get(url: str, params=None, **_: Any) -> _R:
        if url == M.RIJKS:
            return _R({"orderedItems": [{"id": k} for k in recs]})
        if url.endswith("info.json"):
            return _R({"width": 4000, "height": 3000})
        return _R(recs[url])
    got = M.Museums(get=get, sources=("rijks",)).search("Thonet chair", limit=6)
    assert len(got) == 2                                                     # InC·깨진 레코드는 빠진다
    assert {c["url"] for c in got} == {"https://iiif.micr.io/abc/full/1920,/0/default.jpg"}
    c = got[0]
    assert c["institution"] == "Rijksmuseum" and c["origin"] == "museum" and c["width"] == 1920 and c["height"] == 1440
    assert c["page"] == "https://www.rijksmuseum.nl/en/collection/SK-1" and "Thonet chair" in c["name"]


def _nasa_item(nid: str, title: str, *, who: str = "NASA", desc: str = "", links: Any = None) -> dict[str, Any]:
    return {"href": f"http://images-assets.nasa.gov/x/{nid}/collection.json",
            "data": [{"nasa_id": nid, "title": title, "description": desc, "photographer": who, "keywords": ["rocket"]}],
            "links": links if links is not None else [
                {"rel": "preview", "href": f"http://images-assets.nasa.gov/{nid}~thumb.jpg"},
                {"href": f"http://images-assets.nasa.gov/{nid}~small.jpg", "width": 640, "height": 360},
                {"href": f"http://images-assets.nasa.gov/{nid}~large.jpg", "width": 1920, "height": 1080},
                {"href": f"http://images-assets.nasa.gov/{nid}~orig.jpg", "width": 4000, "height": 2250}]}


def test_nasa_filters_rights_partners_and_people(monkeypatch):
    items = [_nasa_item("ok", "Rocket launch"), _nasa_item("rights", "Rocket launch", desc="Photo courtesy of ACME"),
             _nasa_item("partner", "Rocket launch", who="Rocket Lab"), _nasa_item("people", "Rocket launch crew portrait"),
             _nasa_item("other", "Saturn moon"),
             _nasa_item("tall", "Rocket launch", links=[{"href": "http://x/t~large.jpg", "width": 1000, "height": 2000}])]
    monkeypatch.setattr(N.net, "request", lambda *a, **k: _R({"collection": {"items": items}}))
    p = N.Nasa()
    got = p.search_photos("rocket launch", per_page=6)
    assert [c.id for c in got] == ["ok"]
    c = got[0]
    assert c.download == "https://images-assets.nasa.gov/ok~large.jpg" and c.width == 1920     # 1920 이상 중 가장 작은 것, https
    assert c.credit == "NASA" and c.provider == "NASA" and c.url.endswith("/details/ok")
    assert p.search_photos("rocket launch", locale="ko-KR") == []                              # 한국어 검색어는 NASA 에 없다


def test_nasa_video_resolves_files_only_when_downloaded(monkeypatch, tmp_path):
    called: list[str] = []
    manifest = ["http://x/v~orig.mp4", "http://x/v~large.mp4", "http://x/v~mobile.mp4", "http://x/metadata.json"]

    def get_json(url: str, **_: Any) -> Any:
        called.append(url)
        return {"Composite:Duration": "0:01:23"} if url.endswith("metadata.json") else manifest
    monkeypatch.setattr(N.net, "request", lambda *a, **k: _R({"collection": {"items": [_nasa_item("v", "Rocket launch")]}}))
    monkeypatch.setattr(N.net, "get_json", get_json)
    monkeypatch.setattr(N.net, "download", lambda url, dst, **_: Path(dst).write_bytes(b"x"))
    p = N.Nasa()
    c = p.search_videos("rocket launch", per_page=3)[0]
    assert c.download == "" and called == []                     # 검색 단계에서는 항목마다 더 부르지 않는다
    p.download(c, tmp_path / "v.mp4")
    assert c.download == "https://x/v~large.mp4" and c.duration == 83.0  # orig 는 5배쯤 크다


def test_nasa_seconds_formats():
    assert N.seconds({"Composite:Duration": "12.3 s"}) == 12.3
    assert N.seconds({"Video:Duration": "0:01:23"}) == 83.0 and N.seconds({}) == 0.0


def test_sources_table_never_holds_key_values():
    s = NS(pixabay_api_key="SECRET-VALUE", serpapi_key="")
    rows = status(s)
    assert "SECRET-VALUE" not in json.dumps(rows, ensure_ascii=False)
    by = {r["name"]: r["state"] for r in rows}
    assert by["Pixabay"] == "set" and by["Google 이미지(SerpApi)"] == "empty" and by["NASA"] == "keyless"
    assert key_hint("stock", "video", s) == [] and key_hint("stock", "photo", s) == ["Google 이미지(SerpApi)"]
    assert key_hint("own_material", "", s) == []


def _pipeline(tmp_path: Path, **settings: Any):
    from studio.pipeline import Pipeline
    pl = Pipeline.__new__(Pipeline)
    pl.extras, pl.work = tmp_path / "ex", tmp_path / "w"
    pl.settings = NS(**settings)
    pl.spec = NS(fetch_stock=True)
    pl.utts, pl.logged = [NS(id=3, text="토네트 의자는 증기로 구부렸습니다."), NS(id=5, text="다른 문장")], []
    pl.log = pl.logged.append
    return pl


def test_stock_enabled_counts_serpapi():
    from studio.pipeline import Pipeline
    base = dict(keyless_stock=False, pixabay_api_key="", unsplash_access_key="", coverr_api_key="", pexels_api_key="")
    assert Pipeline._stock_enabled(NS(spec=NS(fetch_stock=True), settings=NS(**base, serpapi_key="k")))
    assert not Pipeline._stock_enabled(NS(spec=NS(fetch_stock=True), settings=NS(**base, serpapi_key="")))


def test_stock_hub_checks_once_per_job(tmp_path, monkeypatch):
    from studio import pipeline as P
    calls: list[int] = []
    hub = NS(names=["Pixabay"], check=lambda: calls.append(1) or "정상")
    monkeypatch.setattr(P.StockHub, "from_settings", classmethod(lambda cls, *a, **k: hub))
    pl = _pipeline(tmp_path)
    assert pl._stock_hub() is hub and pl._stock_hub() is hub
    assert len(calls) == 1 and sum("검색처" in m for m in pl.logged) == 1


def test_missing_report_lists_only_real_gaps(tmp_path):
    pl = _pipeline(tmp_path, pixabay_api_key="", serpapi_key="k")
    (tmp_path / "ex").mkdir()
    items = [{"start_seg": 3, "subject": {"name_ko": "토네트 14번 의자"}},
             {"start_seg": 5, "stock": {"kind": "video", "query_ko": "공장 작업"}},
             {"start_seg": 7, "claim": "그릴 것"}, {"start_seg": 9, "subject": {"name_ko": "확보"}}]
    outs = [{"need": "entity", "rung": "type_card", "why": "쓸 수 있는 이미지 없음", "assets": [], "archive": None, "stock": None},
            {"need": "stock", "rung": "face", "why": "못 구함", "assets": [], "archive": None, "stock": None},
            {"need": "code_drawn", "rung": "code_drawn", "why": "", "assets": [], "archive": None, "stock": None},
            {"need": "entity", "rung": "wiki", "why": "", "assets": [{"src": "a.jpg"}], "archive": None, "stock": None}]
    round2 = {"items": [{"start_seg": 5, "subject": {"name_ko": "다른 자료"}}],     # 2회차가 5번 문장을 채웠다
              "outcomes": [{"need": "entity", "rung": "wiki", "assets": [{"src": "b.jpg"}], "archive": None, "stock": None}]}
    pl._write_missing([{"items": items, "outcomes": outs}, round2])
    text = (pl.extras / "못구한자료.md").read_text(encoding="utf8")
    assert "# 못 구한 자료 1건" in text and "「토네트 의자는 증기로 구부렸습니다.」" in text and "토네트 14번 의자" in text
    assert "글자 카드" in text and "④ 자료 폴더" in text and "공장 작업" not in text and "그릴 것" not in text
    pl._write_missing([{"items": items[3:], "outcomes": outs[3:]}])          # 다 채우면 지난 목록을 남기지 않는다
    assert not (pl.extras / "못구한자료.md").exists()


def test_settings_table_reflects_typed_keys_and_checks_them(monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from studio.gui import settings_dialog as D
    from studio.settings import Settings
    app = QApplication.instance() or QApplication(sys.argv)
    monkeypatch.setattr(D, "find_claude", lambda *_: "")       # 창이 열리면 도는 Claude 확인 — 진짜 CLI 를 부르지 않는다
    dlg = D.SettingsDialog(Settings())
    assert dlg.source_state["NASA"].text() == "키 필요 없음" and dlg.source_state["Pixabay"].text() == "키 없음"
    dlg.pixabay.setText("  k  ")
    assert dlg.source_state["Pixabay"].text() == "키 있음"
    seen: list[Any] = []
    monkeypatch.setattr(D.StockHub, "from_settings", classmethod(lambda cls, s: seen.append(s) or NS(check=lambda: "Pixabay 정상(3건)")))
    dlg._check_stock()
    # 끝나기 전에 창이 사라지면 Qt 가 프로세스를 죽인다(0xC0000409, Git Bash 에선 127). quit 는 메인 스레드로 오므로 wait 만으로는 안 끝난다
    deadline = time.monotonic() + 5.0
    while not (dlg._thread.isFinished() and dlg._sthread.isFinished()) and time.monotonic() < deadline:
        app.processEvents()
    assert dlg._thread.isFinished() and dlg._sthread.isFinished()
    assert seen[0].pixabay_api_key == "k" and "정상" in dlg.stock_msg.text() and dlg.check_stock.isEnabled()
