"""자료 조달 엔진 v2(WP7 — docs/upgrade/03_자료_조달_엔진_v2.md · 03b · 저작권 정책) 단위 테스트. 네트워크 없이:
등급 · 서지 확인 · 비전 선택 규칙 · 사다리(화자 자료 → 고유명사 후보 여러 장 → 로고 → 출처 카드 → 스톡 → 대체) ·
그래픽 변환 · 계획 보존·시각 · 자료 리서처 → 조달 → 모션 순서 · 게이트 B1·B2·B6 · 숏폼 옮기기 · 출처·자료 대장."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import gate  # noqa: E402
from studio.agents import schemas as S  # noqa: E402
from studio.agents.studio import AGENTS, Studio, merge_plan  # noqa: E402
from studio.assets import graphics as evg  # noqa: E402
from studio.assets import ladder as lad  # noqa: E402
from studio.assets import scholar as sch  # noqa: E402
from studio.assets.library import AssetLibrary  # noqa: E402
from studio.assets.license import allowed, classify  # noqa: E402
from studio.assets.local import index as local_index, find as local_find  # noqa: E402
from studio.broll.images import ImageResult  # noqa: E402
from studio.broll.resolve import MediaPlan  # noqa: E402
from studio.director.catalog import TEMPLATES, catalog_markdown  # noqa: E402
from studio.director.context import JobBrief  # noqa: E402
from studio.director.plan import EVIDENCE_HOLD, normalize_long, time_graphics  # noqa: E402
from studio.models import Span, TimeMap, Utterance, Word  # noqa: E402

JANSSON = {"DOI": "10.1016/0142-694X(91)90003-F", "title": ["Design fixation"],
           "author": [{"family": "Jansson"}, {"family": "Smith"}], "container-title": ["Design Studies"],
           "issued": {"date-parts": [[1991, 3]]}, "volume": "12", "issue": "1", "page": "3-11", "publisher": "Elsevier BV"}


def _img(path: Path, w: int = 1800, h: int = 1200, color=(180, 120, 90)) -> Path:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), color).save(path, "JPEG")
    return path


def _item(need: str, seg: int = 1, **kw) -> dict:
    it = {"start_seg": seg, "end_seg": seg, "start_word": "", "claim": "주장", "need": need, "role": "example",
          "subject": {"name_ko": "", "name_en": "", "kind": "other", "shot": "subject", "creator_en": "", "year": "",
                      "qid": ""},
          "source": {"citation": "", "doi": "", "url": "", "as_of": "", "locator": ""},
          "stock": {"kind": "photo", "query_en": "", "query_ko": ""}, "local_file": "", "must_show": "", "avoid": "",
          "count": 1, "label": "", "caption": "", "treatment": "hero", "focus": "", "annotations": [],
          "pair": {"name_ko": "", "name_en": "", "label": ""}, "tier_max": "A", "fallback": "type_card", "priority": 1,
          "sequence_id": ""}
    for k, v in kw.items():
        if k in ("subject", "source", "stock") and isinstance(v, dict):
            it[k] = {**it[k], **v}
        else:
            it[k] = v
    return it


# ---------------------------------------------------------------------------
# 등급·서지
# ---------------------------------------------------------------------------

def test_license_tiers_and_quote_switch():
    assert classify("CC BY-NC-ND 2.0").tier == "D" and not allowed(classify("CC BY-NC-ND 2.0"))
    assert classify("CC BY-SA 4.0").tier == "A-sa" and classify("CC BY 2.0").tier == "A"
    assert classify("Public domain").tier == "A" and not classify("CC0").attribution_required
    assert classify("", origin="pixabay").tier == "stock" and classify("", origin="user").tier == "own"
    c = classify("", origin="screenshot")
    assert c.tier == "C"
    assert not allowed(c, "C") and not allowed(c, "A", allow_quote=True) and allowed(c, "C", allow_quote=True)
    assert classify("all rights reserved").tier == "D" and classify("").tier == "D"


def test_scholar_confirms_only_matching_literature(monkeypatch, tmp_path):
    """10/1 대본의 두 논문 — 인용과 서지가 맞을 때만 출처 카드. 연도가 다른 후보·지어낸 인용은 버린다."""
    assert sch.matches("Jansson & Smith (1991) Design fixation. Design Studies 12(1)", JANSSON)
    assert not sch.matches("Jansson & Smith (1995) Design fixation", JANSSON)
    other = {**JANSSON, "title": ["Something else entirely"], "author": [{"family": "Kim"}]}
    assert not sch.matches("Jansson & Smith (1991) Design fixation", other)
    calls = []

    def fake_get(self, url, params=None):
        calls.append((url, params))
        if params:
            return {"message": {"items": [other, JANSSON]}}
        return {"message": JANSSON}
    monkeypatch.setattr(sch.Scholar, "_get", fake_get)
    s = sch.Scholar(cache_dir=tmp_path)
    m = s.resolve("Jansson & Smith (1991) Design fixation. Design Studies 12(1)")
    assert m and m["authors"] == "Jansson & Smith" and m["year"] == "1991" and m["doi"].startswith("10.1016")
    card = sch.source_card(m, label="고착 실험", locator="초록의 결론")
    assert card["variant"] == "source" and {"k": "연도", "v": "1991"} in card["rows"]
    assert any(r["k"] == "저널" and r["v"] == "Design Studies 12(1)" for r in card["rows"])
    assert sch.short_credit(m) == "Jansson & Smith (1991), Design Studies"
    n = len(calls)
    assert s.resolve("Jansson & Smith (1991) Design fixation. Design Studies 12(1)") == m and len(calls) == n  # 캐시


def test_scholar_network_error_is_not_cached(monkeypatch, tmp_path):
    def boom(self, url, params=None):
        raise RuntimeError("down")
    monkeypatch.setattr(sch.Scholar, "_get", boom)
    s = sch.Scholar(cache_dir=tmp_path)
    assert s.resolve("Jansson & Smith (1991) Design fixation") is None
    assert not list(tmp_path.glob("cr_*.json"))


# ---------------------------------------------------------------------------
# 비전 선택 규칙(B6)
# ---------------------------------------------------------------------------

def test_choose_keeps_only_two_points_and_main_subject():
    pick = {"request": 1, "reason": "", "choices": [
        {"candidate": 1, "score": 3, "main_subject": False, "cliche": False, "shows": "무대 위 두 사람", "focus_box": []},
        {"candidate": 2, "score": 3, "main_subject": True, "cliche": True, "shows": "악수", "focus_box": []},
        {"candidate": 3, "score": 2, "main_subject": True, "cliche": False, "shows": "서비스 화면",
         "focus_box": [0.1, 0.2, 0.5, 0.5]},
        {"candidate": 9, "score": 3, "main_subject": True, "cliche": False, "shows": "없는 후보", "focus_box": []}]}
    got = lad.choose(pick, 4, 2, "site_app")
    assert [i for i, _ in got] == [2] and got[0][1]["focus_box"] == [0.1, 0.2, 0.5, 0.5]
    # 사람(person)이면 main_subject 규칙은 적용되지 않는다
    assert [i for i, _ in lad.choose(pick, 4, 3, "person")] == [0, 2]


def test_drawn_treatment_degrades_to_what_renderer_draws():
    assert lad.drawn_treatment("detail_zoom", 1, "A") == "hero"
    assert lad.drawn_treatment("grid", 3, "A") == "hero" and lad.drawn_treatment("grid", 4, "A") == "grid"
    assert lad.drawn_treatment("full", 1, "C") == "hero"                      # 인용은 풀블리드 금지
    assert lad.drawn_treatment("browser_frame", 1, "C", "screen") == "browser_frame"
    assert lad.drawn_treatment("browser_frame", 1, "A", "photo") == "hero"
    assert lad.drawn_treatment("full", 1, "A", "logo") == "hero"


# ---------------------------------------------------------------------------
# 사다리
# ---------------------------------------------------------------------------

class FakeWP:
    ua = "test"

    def entity(self, term, names=()):
        return {"qid": "Q1", "title": term, "lang": "ko", "description": "1959년 라디오", "human": False,
                "p18": [], "logos": [], "commons_cat": "", "lead": "", "label_en": term}


class FakeResolver:
    def __init__(self):
        self.wp = FakeWP()
        self.plans = []

    def plan(self, query, kind="", names=()):
        self.plans.append((query, kind))
        p = MediaPlan(query)
        p.kind = kind
        if kind == "brand" and query == "핀터레스트":
            p.result = ImageResult(Path(self.logo), "Pinterest 로고 · Simple Icons(CC0)", "CC0", "", "logo")
        return p

    def _lead_or_search(self, query, names=()):
        return None


class FakeMedia:
    def candidates(self, info, *, kind="", tier_max="A", min_long=900):
        lic = classify("CC BY-SA 4.0").to_dict()
        return [{"name": f"Braun_SK4_{i}.jpg", "url": f"https://x/{i}.jpg", "mime": "image/jpeg", "width": 2400,
                 "height": 1600, "artist": "Kim", "page": f"https://commons/{i}", "license": "CC BY-SA 4.0",
                 "src": "wikidata", "tier": "A-sa", "lic": lic, "description": ""} for i in range(3)]


class FakeScholar:
    def resolve(self, citation, doi=""):
        return sch._meta(JANSSON) if "Jansson" in citation else None


def test_ladder_climbs_by_need_and_never_drops_silently(tmp_path, monkeypatch):
    public = tmp_path / "public"
    mats = tmp_path / "mats"
    _img(mats / "거꾸로_채운_프로세스.jpg", 1600, 2000)
    logo = _img(public / "images" / "logo_pinterest.jpg", 1600, 1000)
    res = FakeResolver()
    res.logo = str(logo)

    def fake_download(url, dst, **kw):
        _img(Path(dst), 2400 if "x/" in url else 500, 1600 if "x/" in url else 333)
        return Path(dst)
    monkeypatch.setattr(lad.net, "download", fake_download)
    picks_seen = []

    def pick(text, sheets):
        picks_seen.append((text, len(sheets)))
        return [{"request": 1, "reason": "", "choices": [
            {"candidate": 2, "score": 3, "main_subject": True, "cliche": False, "shows": "SK4 정면",
             "focus_box": [0.2, 0.2, 0.5, 0.5]},
            {"candidate": 1, "score": 1, "main_subject": True, "cliche": False, "shows": "흐림", "focus_box": []}]}]
    stock_reqs = []

    def stock(reqs):
        stock_reqs.extend(reqs)
        return [{"src": "broll/x.mp4", "kind": "video", "credit": "Kim / Pixabay", "url": "https://pixabay.com/v"}]
    deps = lad.Deps(resolver=res, media=FakeMedia(), scholar=FakeScholar(), local=tuple(local_index(mats)),
                    library=AssetLibrary(tmp_path / "lib"), pick=pick, stock=stock)
    items = [
        _item("own_material", 1, local_file="거꾸로_채운_프로세스.jpg", label="다시 꺼낸 작업"),
        _item("entity", 2, subject={"name_ko": "브라운 SK4", "name_en": "Braun SK 4", "kind": "product"}, count=2),
        _item("entity", 3, subject={"name_ko": "핀터레스트", "name_en": "Pinterest", "kind": "site_app", "shot": "screen"}),
        _item("primary_source", 4, source={"citation": "Jansson & Smith (1991) Design fixation", "locator": "결론"},
              treatment="doc_highlight", tier_max="C"),
        _item("screenshot", 5, source={"url": "https://example.com"}, subject={"name_ko": "어떤 앱"}, tier_max="C"),
        _item("code_drawn", 6, must_show="고착 실험 설계"),
        _item("stock", 7, stock={"kind": "video", "query_en": "hands flipping sketchbook pages"}, fallback="face"),
        _item("entity", 8, subject={"name_ko": "없는 대상", "kind": "person"}, label="없는 대상"),
    ]
    outs = lad.Ladder(deps, public=public, work=tmp_path / "work").run(items)
    by = {o["i"]: o for o in outs}
    assert by[0]["rung"] == "local" and by[0]["assets"][0]["tier"] == "own"
    assert by[0]["assets"][0]["src"].startswith("images/own_") and by[0]["assets"][0]["mat_src"]   # 세로 → 여백 액자 사본
    assert (public / by[0]["assets"][0]["src"]).exists()
    # 고유명사: 후보 여러 장 → 비전 2점 이상만(C2 하나) → 커먼즈 A-sa, 초점 상자
    a = by[1]["assets"]
    assert by[1]["rung"] == "commons" and len(a) == 1 and a[0]["tier"] == "A-sa" and a[0]["focus"] == [0.2, 0.2, 0.5, 0.5]
    assert "CC BY-SA 4.0" in a[0]["credit"] and picks_seen and picks_seen[0][1] == 1
    # 서비스(사이트·앱): 로고 — 인물 사진으로 대신하지 않는다
    assert by[2]["rung"] == "logo" and by[2]["assets"][0]["kind"] == "logo"
    assert ("핀터레스트", "brand") in res.plans and ("핀터레스트", "person") not in res.plans
    # 1차 자료: 서지 확인 → 출처 카드(인용이 꺼져 있으니 첫 화면 캡처 없음)
    assert by[3]["rung"] == "scholar" and by[3]["archive"]["variant"] == "source" and not by[3]["assets"]
    # 화면 캡처는 C 등급(기본 끔) → 로고도 없으면 자료 카드로
    assert by[4]["rung"] == "type_card" and "꺼짐" in by[4]["why"]
    assert by[5]["rung"] == "code_drawn"
    assert by[6]["rung"] == "stock" and stock_reqs[0]["query_en"] == "hands flipping sketchbook pages"
    assert by[7]["rung"] == "type_card"
    st = lad.summary(items, outs)
    assert st["requests"] == 8 and st["acquired"] == 5 and st["rungs"]["type_card"] == 2
    # 라이브러리: 화자 자료·A 등급은 다음 영상을 위해 남는다(인용·스톡은 아니다)
    lib = AssetLibrary(tmp_path / "lib")
    assert lib.find("거꾸로_채운_프로세스.jpg") and lib.find("Braun SK 4")


def test_screenshot_used_only_when_quote_allowed(tmp_path):
    public = tmp_path / "public"
    calls = []

    def capture(shots):
        calls.append(shots)
        _img(Path(shots[0]["out"]), 1440, 3000)
        return {shots[0]["id"]: {"ok": True}}
    deps = lad.Deps(capture=capture, allow_quote=True)
    it = _item("screenshot", 1, source={"url": "https://www.pinterest.com/"}, treatment="browser_frame", tier_max="C")
    out = lad.Ladder(deps, public=public, work=tmp_path).run([it])[0]
    a = out["assets"][0]
    assert out["rung"] == "screenshot" and a["kind"] == "screen" and a["tier"] == "C" and calls
    assert a["credit"].startswith("화면: pinterest.com") and max(a["w"], a["h"]) <= 1600   # 인용은 긴 변 1600 이하
    g, _ = evg.to_graphics([it], [out])
    assert g[0]["template"] == "evidence" and g[0]["treatment"] == "browser_frame" and g[0]["tier"] == "C"


# ---------------------------------------------------------------------------
# 그래픽 변환 · 계획
# ---------------------------------------------------------------------------

def _outcome(i, **kw):
    return {"i": i, "need": "entity", "rung": "", "assets": [], "archive": None, "stock": None, "why": "", **kw}


def _asset(src="images/a.jpg", kind="photo", tier="A", **kw):
    return {"src": src, "kind": kind, "w": 2000, "h": 1300, "focus": None, "credit": "사진: Kim · CC BY 4.0 · Wikimedia Commons",
            "credit_full": "\"A\" by Kim — CC BY 4.0", "tier": tier, "origin": "commons", "shows": "", "score": 3,
            "meta": {"title": "A", "creator": "Kim", "ref": "https://c/a"}, "mat_src": "", **kw}


def test_to_graphics_keeps_labels_clean_and_falls_back():
    items = [_item("entity", 1, subject={"name_ko": "브라운 SK4"}, treatment="pip", label="", caption="1956 · 디터 람스"),
             _item("entity", 2, subject={"name_ko": "브라운 SK4"}, treatment="hero", label="질문이 만든 형태"),
             _item("primary_source", 3, label="고착", treatment="doc_highlight"),
             _item("stock", 4, stock={"kind": "video", "query_en": "hands sketching", "query_ko": "스케치하는 손"},
                   treatment="full"),
             _item("entity", 5, subject={"name_ko": "홍익대학교"}, treatment="hero"),
             _item("code_drawn", 6, must_show="격자 도식"),
             _item("stock", 7, stock={"query_en": "x"}, fallback="face")]
    outs = [_outcome(0, assets=[_asset()]), _outcome(1, assets=[_asset("images/b.jpg"), _asset("images/c.jpg")]),
            _outcome(2, archive=sch.source_card(sch._meta(JANSSON)), credit="Jansson & Smith (1991), Design Studies"),
            _outcome(3, stock={"src": "broll/s.mp4", "kind": "video", "credit": "Kim / Pixabay", "url": "u"}),
            _outcome(4, rung="type_card", why="없음", info={"description": "서울의 대학"}),
            _outcome(5, rung="code_drawn"), _outcome(6, rung="face")]
    gs, drawn = evg.to_graphics(items, outs)
    t = [g["template"] for g in gs]
    assert t == ["photo", "evidence", "evidence", "broll", "keyword"], t
    assert gs[0]["resolved"] and gs[0]["image"] == "images/a.jpg" and gs[0]["layout"] == "pip"
    assert gs[1]["treatment"] == "hero" and len(gs[1]["assets"]) == 1         # count=1 → 한 장
    assert gs[2]["treatment"] == "archive_card" and gs[2]["archive"]["variant"] == "source"
    assert gs[3]["src"] == "broll/s.mp4" and gs[3]["title"] == "" and gs[3]["layout"] == "fullscreen"
    assert gs[4]["title"] == "홍익대학교" and gs[4]["subtitle"] == "서울의 대학"
    assert drawn and drawn[0]["must_show"] == "격자 도식"
    for g in gs:   # 화면 글자에 검색어·종류(kind)가 없다(게이트 B3~B5)
        assert gate.b3_query_labels([g]).ok and gate.b5_internal_names([g]).ok
    brief = evg.brief_for_motion(items, outs, drawn)
    assert "E2" in brief and "재현 요청" in brief and "격자 도식" in brief


def test_merge_plan_uses_outcomes_or_legacy_paths():
    items = [_item("entity", 0, subject={"name_ko": "핀터레스트", "name_en": "Pinterest", "kind": "site_app"}),
             _item("stock", 1, stock={"kind": "photo", "query_en": "sketchbook"}),
             _item("primary_source", 2)]
    raw, _ = merge_plan({"director": {"title": "t"}, "stock": {"items": items, "notes": ""}})
    t = [(g["template"], g.get("entity", "")) for g in raw["graphics"]]
    assert t == [("photo", "brand"), ("broll", "")], t                     # 조달 결과 없음 → 예전 단계가 찾는다
    outs = [_outcome(0, assets=[_asset(kind="logo")], rung="logo"), _outcome(1, rung="face"), _outcome(2, rung="face")]
    raw2, _ = merge_plan({"director": {"title": "t"}, "stock": {"items": items, "notes": ""}, "evidence_outcomes": outs})
    assert [g["template"] for g in raw2["graphics"]] == ["evidence"]
    assert raw2["studio"]["evidence_items"] == 3


def _utts(n=8):
    out, t = [], 0.0
    for i in range(n):
        words = [Word("문장", t, t + 0.5), Word(f"번호{i}", t + 0.6, t + 1.2), Word("입니다", t + 1.3, t + 2.0)]
        out.append(Utterance(id=i, start=t, end=t + 2.0, text=f"문장 번호{i} 입니다", asr_text="", words=words))
        t += 2.5
    return out


def test_evidence_survives_normalize_and_is_timed():
    utts = _utts()
    gs = [{**evg._g("evidence", "fullscreen", 1, 1, "", title="질문의 형태", assets=[_asset()], treatment="hero",
                    caption="1956", tier="A", credit="c", evidence={"need": "entity", "role": "proof"})},
          {**evg._g("evidence", "fullscreen", 4, 4, "", treatment="archive_card", tier="made",
                    archive=sch.source_card(sch._meta(JANSSON)), evidence={"role": "context"})},
          {**evg._g("evidence", "fullscreen", 6, 6, "", assets=[_asset(kind="screen", tier="C")],
                    treatment="browser_frame", tier="C")},
          evg._g("evidence", "fullscreen", 7, 7, "", treatment="hero")]          # 조달 안 된 것 → 계획에서 빠진다
    plan = normalize_long({"graphics": gs, "chapters": [{"seg": 0, "title": "c"}]}, utts, [])
    ev = [g for g in plan["graphics"] if g["template"] == "evidence"]
    assert len(ev) == 3 and ev[0]["assets"][0]["src"] == "images/a.jpg" and ev[1]["archive"]["rows"]
    tm = TimeMap([Span(0.0, 20.0)])
    timed = time_graphics(ev, utts, tm, total=20.0)
    d = {g.data.get("treatment"): g for g in timed}
    assert d["hero"].end - d["hero"].start >= EVIDENCE_HOLD["hero"] - 0.1 and d["hero"].data["assets"]
    assert d["hero"].priority > d["archive_card"].priority                     # 맥락(context)은 근거(proof)보다 낮다
    assert d["browser_frame"].end - d["browser_frame"].start <= 6.0 + 0.3      # 인용(C)은 6초 이내
    assert "evidence" not in catalog_markdown() and TEMPLATES["evidence"].priority == 8


# ---------------------------------------------------------------------------
# 순서: 자료 → 조달 → 모션
# ---------------------------------------------------------------------------

class FakeClaude:
    def __init__(self):
        self.calls = []

    def structured(self, *, system, shared_context, instruction, schema, images=None, label="", **kw):
        key = next(k for k, a in AGENTS.items() if a.schema is schema and a.label == label)
        self.calls.append((key, instruction, len(images or [])))
        if key == "director":
            return {"title": "t", "logline": "l", "beats": [], "structure": []}
        if key == "stock":
            n = sum(1 for c in self.calls if c[0] == "stock")
            return {"items": [_item("entity", n, subject={"name_ko": f"대상{n}"})], "notes": ""}
        if key == "motion":
            return {"graphics": [], "scenes": [], "cards": []}
        return {}


def test_studio_runs_researcher_then_procurement_then_motion():
    fc = FakeClaude()
    st = Studio(fc, workers=4)
    seen = []

    def procure(res, rnd):
        seen.append((rnd, len(res["items"])))
        outs = [_outcome(0, assets=[_asset()], rung="commons")]
        return {"outcomes": outs, "brief": "## 확보된 자료\n- E1 대상", "sheet": b"jpeg",
                "backfill": "## 이번 호출은 보충이다\n- [B1] 부족" if rnd == 1 else ""}
    raw, _ = st.plan(JobBrief(title="t"), "ctx", shorts_count=0, procure=procure,
                     materials=("- M1 `a.jpg`", b"sheet"))
    order = [c[0] for c in fc.calls]
    assert order.index("stock") < order.index("motion"), order
    assert seen == [(1, 1), (2, 1)]                                            # 보충 호출은 한 번
    stock_calls = [c for c in fc.calls if c[0] == "stock"]
    assert len(stock_calls) == 2 and "M1 `a.jpg`" in stock_calls[0][1] and stock_calls[0][2] == 1
    assert "이번 호출은 보충이다" in stock_calls[1][1]
    motion = next(c for c in fc.calls if c[0] == "motion")
    assert "확보된 자료" in motion[1] and motion[2] == 1                       # 확보 목록 + 컨택트 시트
    assert len(st.results["evidence_outcomes"]) == 2 and [o["i"] for o in st.results["evidence_outcomes"]] == [0, 1]
    assert [g["template"] for g in raw["graphics"]] == ["evidence", "evidence"]


def test_pick_stock_adapts_v2_scores():
    st = Studio(FakeClaude())
    st.pick_evidence = lambda ctx, text, sheets: [
        {"request": 1, "reason": "", "choices": [{"candidate": 1, "score": 3, "main_subject": True, "cliche": True,
                                                  "shows": "악수", "focus_box": []},
                                                 {"candidate": 3, "score": 2, "main_subject": True, "cliche": False,
                                                  "shows": "손과 연필", "focus_box": []}]},
        {"request": 2, "reason": "없음", "choices": []}]
    got = st.pick_stock("ctx", "", [])
    assert got[0]["candidate"] == 3 and got[1]["candidate"] == -1
    assert AGENTS["stock"].prompt == "visual_researcher" and AGENTS["stock"].schema is S.EVIDENCE
    assert AGENTS["stock"].effort == "high" and AGENTS["stock_pick"].schema is S.EVIDENCE_PICK


# ---------------------------------------------------------------------------
# 게이트 B1·B2·B6 · 숏폼 · 출처
# ---------------------------------------------------------------------------

def _tg(i, tpl, layout, a, b, **data):
    return {"id": f"g{i}", "template": tpl, "layout": layout, "start": a, "end": b, "data": data}


def test_b_gates_measure_real_media_and_promote_hero():
    gs = [_tg(0, "photo", "pip", 10, 14, image="images/a.jpg"), _tg(1, "keyword", "overlay", 20, 24, title="x"),
          _tg(2, "photo", "pip", 100, 104, image="images/l.svg", logo=True)]
    b1 = gate.b1_media_ratio(gs, 200.0)
    assert not b1.ok and b1.measured["seconds"] == 4.0                       # 로고 카드는 실물이 아니다
    assert gate.b1_media_ratio(gs + [_tg(3, "broll", "fullscreen", 30, 60, src="b.mp4")], 200.0).ok
    chapters = [{"start": 0.0}, {"start": 90.0}]
    b2 = gate.b2_hero_per_chapter(gs, chapters, 200.0)
    assert not b2.ok and b2.measured["lacking"] == [[0.0, 90.0]]
    plan = [{"template": "photo", "layout": "pip"}, {"template": "keyword", "layout": "overlay"},
            {"template": "photo", "layout": "pip"}]
    assert gate.promote_hero(plan, gs, b2.measured["lacking"]) == 1 and plan[0]["layout"] == "fullscreen"
    ev = _tg(4, "evidence", "fullscreen", 40, 45, assets=[{"src": "x", "kind": "photo", "score": 1}])
    assert gate.b2_hero_per_chapter([ev], chapters, 200.0).ok
    assert not gate.b6_pick_scores([ev]).ok and gate.b6_pick_scores(gs).ok


def test_evidence_moves_to_shorts_as_photo_or_card():
    from studio.pipeline import short_retype
    g = evg._g("evidence", "fullscreen", 1, 1, "", title="질문의 형태", caption="1956", assets=[_asset()],
               treatment="hero")
    c = short_retype(g)
    assert c["template"] == "photo" and c["image"] == "images/a.jpg" and c["resolved"] and "assets" not in c
    s = evg._g("evidence", "fullscreen", 1, 1, "", treatment="archive_card",
               archive=sch.source_card(sch._meta(JANSSON)))
    k = short_retype(s)
    assert k["template"] == "keyword" and k["title"] == "Design fixation" and "Jansson & Smith" in k["subtitle"]


def test_credits_and_ledger_from_final_props(tmp_path):
    from studio.assets.license import write_ledger
    gs = [_tg(0, "evidence", "fullscreen", 5, 10, assets=[_asset(tier="C")], title="화면", treatment="hero"),
          _tg(1, "evidence", "fullscreen", 12, 16, archive={**sch.source_card(sch._meta(JANSSON))},
              credit="Jansson & Smith (1991), Design Studies"),
          _tg(2, "broll", "fullscreen", 20, 23, src="broll/s.mp4", credit="Kim / Pixabay", stock_url="u")]
    cr = evg.props_credits(gs)
    assert cr[0] == "\"A\" by Kim — CC BY 4.0" and "doi.org" in cr[1]
    rows = evg.ledger_rows(gs, "롱폼")
    assert [r["등급"] for r in rows] == ["C", "made", "stock"] and rows[0]["인용 사유"] == "화면"
    write_ledger(tmp_path / "l.csv", rows)
    text = (tmp_path / "l.csv").read_text(encoding="utf-8-sig")
    assert text.splitlines()[0].startswith("자산,등급") and "broll/s.mp4" in text


def test_local_materials_index_and_find(tmp_path):
    _img(tmp_path / "IMG_2034.jpg", 800, 600)
    _img(tmp_path / "최종_렌더링.png", 1200, 800)
    items = local_index(tmp_path)
    assert [i.key for i in items] == ["M1", "M2"] and items[0].w == 800
    assert local_find(items, "M2").name == "최종_렌더링.png"
    assert local_find(items, "", "최종 렌더링").name == "최종_렌더링.png"
    assert local_find(items, "없는파일.jpg") is None
