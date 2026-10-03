"""스톡·그림 고르기 — 이 영상의 세계 안에서, 첫 후보를 그냥 쓰지 않고(2026-10-04 채널 주인: "픽사베이 api 를 활용하라고 한 거지
아무거나 갖다 쓰라는 게 아니다"). 실제로 화면에 나간 것: 'product prototype foam mockup' → 해변 파도 거품, 'product 3d render studio'
→ 거실 인테리어, '학교'(미대 산업디자인과) → 색연필·아이 공책."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.agents import schemas as S  # noqa: E402
from studio.agents.studio import treatment_block, world_block  # noqa: E402
from studio.assets import graphics as evg  # noqa: E402
from studio.stock.base import StockCandidate  # noqa: E402
from studio.stock.providers import StockHub, query_variants  # noqa: E402
from studio.stock.research import StockResearcher, junk, query_terms, rule_choice  # noqa: E402


def cand(i, alt, kind="photo"):
    return StockCandidate(kind=kind, id=i, url=f"https://pixabay.com/{i}", thumb="", download="d", width=1280,
                          height=720, author="a", alt=alt, provider="Pixabay")


def test_rule_choice_needs_core_nouns_in_tags_and_skips_ai_or_homonyms():
    beach = cand(1, "beach, sea, foam, waves, sunset")
    ai = cand(2, "ai generated, anime, foam, model, sanding")
    real = cand(3, "foam, model, sanding, workshop, hands")
    assert rule_choice({"query_en": "foam model sanding"}, [beach, ai, real]) == 2
    # 거실 인테리어는 'render' 하나만 맞는다 — 핵심 낱말 둘 이상이 필요
    interior = cand(4, "interior, living room, furniture, 3d render")
    assert rule_choice({"query_en": "product 3d render studio"}, [interior]) == -1
    # 다른 각도 검색어로는 맞는 후보
    screen = cand(5, "screen, 3d model, software, computer")
    assert rule_choice({"query_en": "product 3d render", "alt_queries": ["3d model screen"]}, [interior, screen]) == 1
    assert junk(ai) and not junk(real)
    assert "sanding" not in query_terms("hands sanding close up") or query_terms("hands sanding close up") == ["sand"]


def test_query_variants_do_not_shrink_to_a_homonym():
    v = query_variants("product prototype foam mockup", min_words=2)
    assert all(len(x.split()) >= 2 for x in v)
    assert "foam" not in v and "product" not in v
    assert query_variants("chair", min_words=2) == ["chair"]


class _Prov:
    name, videos, photos, korean = "Pixabay", True, True, False

    def __init__(self):
        self.calls = []

    def search_photos(self, q, per_page=6, locale=""):
        self.calls.append(q)
        return [cand(f"{q}-{i}", q.replace(" ", ", ")) for i in range(3)]

    search_videos = search_photos


def test_hub_mixes_alt_query_candidates():
    p = _Prov()
    hub = StockHub([p])
    got = hub.search({"kind": "photo", "query_en": "pin board photos", "alt_queries": ["cork board", "color swatches"]}, 6)
    qs = {c.id.rsplit("-", 1)[0] for c in got}
    assert qs == {"pin board photos", "cork board", "color swatches"}
    assert p.calls[:3] == ["pin board photos", "cork board", "color swatches"]


class _ImgProv:
    name, videos, photos, korean = "Pixabay", False, True, False

    def __init__(self, table):
        self.table, self.calls = table, []

    def search_images(self, q, image_type="vector", per_page=6):
        self.calls.append(q)
        return list(self.table.get(q, []))

    def search_photos(self, q, per_page=6, locale=""):
        return []

    def download(self, c, dst):
        from PIL import Image
        dst.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 32), (200, 180, 150)).save(dst, "JPEG")
        return dst


def _scene(src, title="다시 꺼낸 지난 작업"):
    spec = {"elements": [{"type": "image", "src": src, "w": 40, "h": 30, "frame": "print"},
                         {"type": "text", "text": "지난 작업"}]}
    return {"template": "motion", "title": title, "start_seg": 7, "spec": spec}, spec


def test_motion_scene_images_are_picked_by_vision_with_context(tmp_path, monkeypatch):
    monkeypatch.setattr(StockResearcher, "_thumb", lambda self, c: None)
    table = {"foam model sanding": [cand(1, "beach, sea, foam"), cand(2, "foam, model, workshop"),
                                    cand(3, "foam, model, sanding, hands")]}
    prov = _ImgProv(table)
    seen = []

    def pick(text, sheets):
        seen.append(text)
        return [{"request": 1, "candidate": 3, "reason": "손으로 폼 모형을 다듬는 컷"}]
    res = StockResearcher(StockHub([prov]), ff=None, work=tmp_path / "work", public=tmp_path / "public", pick=pick)
    g, spec = _scene("pixabay:photo:foam model sanding")
    assert res.resolve_images([[g]], context=lambda gg: "그때 만든 폼 목업을 다시 꺼내 봤어요") == 1
    assert "img_pip3" in spec["elements"][0]["src"]
    assert "그 장면의 말: 「그때 만든 폼 목업을 다시 꺼내 봤어요」" in seen[0] and "다시 꺼낸 지난 작업" in seen[0]


def test_motion_scene_image_rejected_then_retried_then_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(StockResearcher, "_thumb", lambda self, c: None)
    table = {"product 3d render": [cand(1, "interior, living room, 3d render")],
             "3d model screen": [cand(2, "orc, fantasy, 3d")]}
    prov = _ImgProv(table)
    rounds = []

    def pick(text, sheets):
        rounds.append(text)
        if len(rounds) == 1:
            return [{"request": 1, "candidate": -1, "reason": "거실 인테리어", "retry_query_en": "3d model screen"}]
        return [{"request": 1, "candidate": -1, "reason": "게임 캐릭터"}]
    res = StockResearcher(StockHub([prov]), ff=None, work=tmp_path / "work", public=tmp_path / "public", pick=pick)
    g, spec = _scene("pixabay:photo:product 3d render")
    assert res.resolve_images([[g]]) == 0
    assert [e["type"] for e in spec["elements"]] == ["text"]          # 그림 부품만 빠지고 장면은 남는다
    assert prov.calls[-1] == "3d model screen" and len(rounds) == 2
    assert any(v.get("why") == "rejected" for v in res.cache.values())


def test_without_vision_first_result_is_not_used_blindly(tmp_path):
    prov = _ImgProv({"product prototype foam mockup": [cand(1, "beach, sea, foam, waves")],
                     "product prototype foam": [cand(1, "beach, sea, foam, waves")],
                     "product prototype": [], "foam mockup": [cand(1, "beach, sea, foam, waves")]})
    res = StockResearcher(StockHub([prov]), ff=None, work=tmp_path / "work", public=tmp_path / "public")
    g, spec = _scene("pixabay:photo:product prototype foam mockup")
    assert res.resolve_images([[g]]) == 0 and len(spec["elements"]) == 1
    assert "foam" not in prov.calls                                    # 한 낱말까지 줄이지 않는다


def test_pick_round_out_of_range_candidate_is_a_reject(tmp_path, monkeypatch):
    monkeypatch.setattr(StockResearcher, "_thumb", lambda self, c: None)
    res = StockResearcher(StockHub([]), ff=None, work=tmp_path, public=tmp_path,
                          pick=lambda t, s: [{"request": 1, "candidate": 9}])
    res.stats = {"rejected": 0}
    choice, _ = res._pick_round(["k"], {"k": {"kind": "photo", "query_en": "pin board"}}, {"k": [cand(1, "pin, board")]})
    assert choice["k"] == -1


def test_world_block_and_treatment_carry_the_world():
    tr = {"concept": "c", "motifs": [], "world": {"who": "한국 미술대학 산업디자인과 2학년", "where": "실기실·모형실",
                                                    "era": "2020년대", "props": "폼 모형·마커", "look": "자연광",
                                                    "never": "초중고 교실·아이·색연필 세트"}}
    wb = world_block(tr)
    assert "미술대학 산업디자인과" in wb and "이 세계가 아닌 것" in wb and "색연필 세트" in wb
    assert "이 영상의 세계" in treatment_block({"treatment": tr}, "stock")
    assert "이 영상의 세계" in treatment_block({"treatment": tr}, "motion")
    assert "이 영상의 세계" not in treatment_block({"treatment": tr}, "editor")
    assert "주제 설명: 홍익대" in world_block({}, "홍익대 산업디자인 전공생의 고백")
    assert world_block({}, "") == ""
    # 스키마: 트리트먼트에 world, 증거 스톡에 angle·alt_queries
    assert "world" in S.TREATMENT["properties"] and "world" in S.TREATMENT["required"]
    st = S.EVIDENCE["properties"]["items"]["items"]["properties"]["stock"]
    assert set(st["required"]) >= {"angle", "alt_queries"}


def test_motion_brief_lists_failed_procurement_instead_of_dropping_it():
    items = [{"start_seg": 3, "end_seg": 4, "need": "stock", "claim": "학교에서 배운 프로세스",
              "must_show": "미대 실기실에서 폼 모형을 다듬는 손", "stock": {"kind": "video", "query_en": "foam model sanding"},
              "fallback": "code_drawn", "treatment": "full"},
             {"start_seg": 9, "end_seg": 9, "need": "code_drawn", "claim": "재현", "must_show": "도식", "treatment": "hero"}]
    outcomes = [{"i": 0, "need": "stock", "rung": "face", "assets": [], "archive": None, "stock": None, "why": "못 구함"},
                {"i": 1, "need": "code_drawn", "rung": "code_drawn", "assets": [], "archive": None, "stock": None, "why": ""}]
    brief = evg.brief_for_motion(items, outcomes, [])
    assert "조달 실패 — 비워 두지 않는다" in brief
    assert "S3–S4" in brief and "foam model sanding" in brief and "미대 실기실" in brief
