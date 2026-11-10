"""이미지 위 그래픽 층(디자인 v5.1): 크롭 좌표 계산 · 좌표 없는 표시의 규칙 · 낱말 착지 · preflight."""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from studio import gate
from studio.agents.studio import Studio
from studio.assets import graphics as evg
from studio.assets.ladder import choose
from studio.director.plan import clean_overlays, normalize_long, time_graphics
from studio.models import Span, TimeMap, Utterance, Word
from studio.pipeline import short_retype
from studio.render import preflight
from studio.render.remotion import RenderError, find_node
from studio.stock.base import StockCandidate
from studio.stock.research import StockResearcher
from studio.vision import compose

ROOT = Path(__file__).resolve().parent.parent


def crop(expr: str):
    try:
        node = find_node()
    except RenderError:
        pytest.skip("node 없음")
    url = (ROOT / "renderer" / "src" / "lib" / "crop.ts").as_uri()
    code = f"import * as c from '{url}'; console.log(JSON.stringify({expr}))"
    r = subprocess.run([node, "--experimental-strip-types", "--input-type=module", "-e", code], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        pytest.skip(f"node 가 TS 를 못 읽음: {r.stderr[:80]}")
    return json.loads(r.stdout)


def test_normalized_points_follow_the_real_cover_crop():
    # 3:2 그림 → 16:9: 위아래가 잘린다. 가운데 맞춤이면 100px 씩, objectPosition 위쪽이면 아래만 잘린다
    center = crop("[0, 0.5, 1].map((v) => c.coverMap(2400, 1600, 1920, 1080)(v, v))")
    assert center == [[0, -100], [960, 540], [1920, 1180]]
    assert crop("c.coverMap(2400, 1600, 1920, 1080, 0.5, 0)(0.5, 0.25)") == [960, 320]
    # 세로 그림을 위쪽 42% 초점으로(레퍼런스의 돌출창 사례): 그려지는 높이 1920×3400/2917
    y = crop("c.coverMap(2917, 3400, 1920, 1080, 0.5, 0.42)(0.5, 0.36)[1]")
    h = 3400 * 1920 / 2917
    assert y == pytest.approx((1080 - h) * 0.42 + 0.36 * h)
    # contain 은 좌우에 여백 — 좌표도 여백 안쪽에서 시작한다
    assert crop("[0, 1].map((v) => c.coverMap(1000, 2000, 1920, 1080, 0.5, 0.5, 'contain')(v, v))") == [[690, 0], [1230, 1080]]


def test_unknown_size_or_cropped_target_draws_nothing():
    assert crop("c.coverMap(0, 0, 1920, 1080)") is None
    assert crop("c.targetRect({box: [0.1, 0.1, 0.2, 0.2]}, null, 1920, 1080)") is None
    # 세로 그림 가운데 맞춤이면 위쪽 대상은 화면 밖이다 — 엉뚱한 자리에 그리지 않는다
    assert crop("c.targetRect({box: [0.2, 0.05, 0.2, 0.1]}, c.coverMap(1000, 2000, 1920, 1080), 1920, 1080)") is None
    r = crop("c.targetRect({box: [0.25, 0.45, 0.5, 0.1]}, c.coverMap(1000, 2000, 1920, 1080), 1920, 1080)")
    assert r["x"] == pytest.approx(480) and r["w"] == pytest.approx(960) and r["y"] + r["h"] / 2 == pytest.approx(540)


def test_paper_tag_stays_on_screen_and_off_the_target():
    t = {"x": 1500, "y": 300, "w": 300, "h": 200}
    r = crop(f"c.placeNear({json.dumps(t)}, 320, 80, [{json.dumps(t)}], 1920, 1080)")
    assert r["x"] + r["w"] <= t["x"]                                        # 오른쪽 끝 대상이면 안쪽(왼쪽)에
    assert 56 <= r["x"] and r["y"] + r["h"] <= 1080 - 190
    big = {"x": 100, "y": 56, "w": 1700, "h": 700}
    over = crop(f"c.placeNear({json.dumps(big)}, 320, 80, [], 1920, 1080)")
    assert over["y"] >= big["y"] + big["h"]                                   # 자리가 없어도 표찰이 대상을 덮지 않는다
    left = crop("c.safeSlot('left', 300, 100, [], 1920, 1080)")
    right = crop("c.safeSlot('right', 300, 100, [{x: 1500, y: 96, w: 400, h: 100}], 1920, 1080)")
    assert left["x"] < 200 and right["x"] > 1400 and right["y"] > 196       # 먼저 놓인 것 아래로


def test_outline_curve_passes_through_every_vertex():
    pts = [[0, 0], [100, 0], [100, 80], [0, 80]]
    d = crop(f"c.catmullRom({json.dumps(pts)})")
    assert d.startswith("M0.0 0.0") and d.endswith("Z") and d.count("C") == 4
    assert all(f"{x:.1f} {y:.1f}C" in d or f"{x:.1f} {y:.1f}Z" in d for x, y in pts)
    assert crop("c.firstHit([0, 50], [200, 50], [[100, 0], [150, 0], [150, 100], [100, 100]])") == [100, 50]   # 지시선이 윤곽과 처음 만나는 곳
    assert crop("c.firstHit([0, 50], [50, 50], [[100, 0], [150, 0], [150, 100], [100, 100]])") is None


def test_paper_tag_prefers_the_empty_side():
    t = {"x": 800, "y": 300, "w": 200, "h": 200}
    assert crop(f"c.placeNear({json.dumps(t)}, 300, 80, [], 1920, 1080, 60, false, 'left')")["x"] + 300 <= t["x"]
    assert crop(f"c.placeNear({json.dumps(t)}, 300, 80, [], 1920, 1080, 60, false, 'right')")["x"] >= t["x"] + t["w"]


def test_without_coordinates_only_memo_and_label():
    out = clean_overlays([{"kind": "memo", "text": "메모"}, {"kind": "label", "text": "라벨"}])
    assert [o["kind"] for o in out] == ["memo", "label"]
    assert clean_overlays([{"kind": "circle"}, {"kind": "arrow", "text": ""}, {"kind": "focus"}, {"kind": "impact"}]) == []
    # 글이 있으면 어디를 가리키는지 몰라도 말은 남는다 — 좌표를 지어내지 않고 라벨로
    assert clean_overlays([{"kind": "stamp", "text": "철거"}]) == [{"kind": "label", "text": "철거"}]
    assert clean_overlays([{"kind": "outline", "point": [0.5, 0.5], "text": "경계"}]) == [{"kind": "label", "text": "경계"}]  # 윤곽은 상자가 있어야
    assert clean_overlays([{"kind": "cutout", "point": [0.5, 0.5]}]) == []  # 얹을 그림이 없다
    assert clean_overlays([{"kind": "label"}, {"kind": "nope", "text": "x"}]) == []


def test_coordinates_are_validated_and_capped():
    many = [{"kind": "circle", "box": [0.1, 0.1, 0.2, 0.2]}] * 5
    assert len(clean_overlays(many)) == 3
    [o] = clean_overlays([{"kind": "circle", "box": [-0.5, 0.2, 2, 0.3], "at_word": "지붕을"}])
    assert o["box"] == [0.0, 0.2, 1.0, 0.3] and o["at_word"] == "지붕을"
    assert clean_overlays([{"kind": "circle", "box": [0.1, 0.1, 0.2]}]) == []
    assert clean_overlays([{"kind": "circle", "box": [0.1, 0.1, 0.0, 0.2]}]) == []
    [o] = clean_overlays([{"kind": "outline", "poly": [[0.1, 0.2], [0.5, 0.2], [0.3, 0.6]]}])
    assert o["box"] == [0.1, 0.2, 0.4, 0.4]                                  # 윤곽만 줘도 상자를 잰다
    assert o["kind"] == "circle" and "poly" not in o                         # 꼭짓점이 적으면 대상을 못 따라간다 — 원으로
    ring = [[0.5 + 0.2 * math.cos(i / 4), 0.5 + 0.2 * math.sin(i / 4)] for i in range(25)]
    assert clean_overlays([{"kind": "outline", "poly": ring}])[0]["kind"] == "outline"


def test_budget_counts_a_labelled_mark_as_two_and_keeps_spoken_marks_first():
    circle = {"kind": "circle", "box": [0.1, 0.1, 0.2, 0.2], "text": "돌출창"}
    label = {"kind": "label", "box": [0.5, 0.5, 0.1, 0.1], "text": "사무소"}
    arrow = {"kind": "arrow", "point": [0.7, 0.7]}
    assert [o["kind"] for o in clean_overlays([circle, label, arrow])] == ["circle", "label"]     # 원 + 표찰 + 라벨 = 셋, 화살표는 넷째
    spoken = {**arrow, "at_word": "문으로"}
    assert [o["kind"] for o in clean_overlays([circle, label, spoken])] == ["circle", "arrow"]    # 말에 착지하는 표시가 먼저, 순서는 그대로


def test_bright_spot_finds_light_paper_or_gives_up():
    dark_left = "Array.from({length: 24}, () => Array.from({length: 24}, (_, c) => (c >= 12 ? 0.8 : 0.1)))"
    m = "(x, y) => [x * 1920, y * 1080]"
    x, y = crop(f"c.brightSpot({dark_left}, {m}, [0.2, 0.3], 340, 170, 1920, 1080)")
    assert x - 170 >= 960 - 80 and 56 <= y - 85 and y + 85 <= 1080 - 190                # 어두운 왼쪽을 피해 가장 가까운 밝은 자리, 자막 위
    all_dark = "Array.from({length: 24}, () => Array(24).fill(0.2))"
    assert crop(f"c.brightSpot({all_dark}, {m}, [0.5, 0.3], 340, 170, 1920, 1080)") is None


def test_expand_credit_swaps_when_the_new_picture_passes_half_the_frame():
    assert crop("[0.1, 0.3, 0.49, 0.5, 1].map((s) => c.expandCredit(s, '시카고 미술관', '클리블랜드 미술관'))") == [
        "시카고 미술관", "시카고 미술관 · 클리블랜드 미술관", "시카고 미술관 · 클리블랜드 미술관", "클리블랜드 미술관", "클리블랜드 미술관"]
    assert crop("c.expandCredit(0.3, '시카고 미술관', '시카고 미술관')") == "시카고 미술관"


def test_dimension_needs_a_real_number_and_two_ends():
    line = [[0.1, 0.5], [0.9, 0.5]]
    [o] = clean_overlays([{"kind": "dimension", "poly": line, "text": "54 m", "at_word": "폭은"}])
    assert o["poly"] == line and o["text"] == "54 m" and o["at_word"] == "폭은"
    assert clean_overlays([o]) == [o]                                          # plan.json 을 다시 정규화해도 남는다
    assert clean_overlays([{"kind": "dimension", "poly": line, "text": "아주 넓다"}]) == []
    assert clean_overlays([{"kind": "dimension", "box": [0.2, 0.3, 0.4, 0.1], "text": "120m"}])[0]["poly"] == [[0.2, 0.4], [0.6, 0.4]]   # 상자만 줬으면 긴 변을 따라
    assert clean_overlays([{"kind": "dimension", "box": [0.2, 0.3, 0.1, 0.4], "text": "120m"}])[0]["poly"] == [[0.3, 0.3], [0.3, 0.7]]
    assert clean_overlays([{"kind": "dimension", "text": "30 km"}]) == [{"kind": "label", "text": "30 km"}]    # 자리를 모르면 선을 지어내지 않는다


def test_dimension_figure_counts_up_and_stays_on_screen():
    assert crop("['1,208 m', '3.5배', '없음'].map((t) => c.countUp(t, 0.5))") == ["604 m", "1.8배", "없음"]
    assert crop("c.countUp('1,208 m', 1)") == "1,208 m"
    assert crop("c.figureAt([100, 500], [900, 500], 200, 70, 1920, 1080)")[1] < 500            # 가로선은 위로
    assert crop("c.figureAt([100, 60], [900, 60], 200, 70, 1920, 1080)")[1] > 60               # 위가 화면 밖이면 아래로
    assert crop("c.figureAt([800, 200], [800, 700], 200, 70, 1920, 1080)")[0] > 800            # 세로선은 오른쪽으로


def test_dimension_stays_clear_of_caption_and_prints():
    view = "{x: 0, y: 0, w: 1920, h: 1080}"
    low = "[[100, 960], [900, 960]]"
    assert crop(f"Math.max(...c.dimensionLine(...{low}, {view}, 1080, 11).map((p) => p[1]))") == 925 - 11    # 자막 위까지만 내려온다
    [a, b] = crop(f"c.dimensionLine(...{low}, {view}, 1080, 11, {{top: 500}})")
    assert a[1] == b[1] == 472                                                  # 대상 위쪽을 알면 그 위로
    [a, _] = crop(f"c.dimensionLine([100, 500], [900, 500], {view}, 1080, 9, {{doc: true, bottom: 515}})")
    assert a[1] == 527                                                          # 문서: 줄 아래 변 + 12px
    assert crop("c.dimensionLine([100, 500], [900, 500], {x: 0, y: 0, w: 960, h: 540}, 1080, 9, {doc: true, bottom: 515})")[0][1] == 521      # 밀려 들어간 문서: 화면 12px 은 층 6px


def test_full_frame_is_refused_when_the_picture_would_blur():
    assert crop("[c.tooSoft(1280, 720, 1920, 1080), c.tooSoft(1279, 720, 1920, 1080), c.tooSoft(1000, 2000, 1920, 1080), c.tooSoft(2400, 1600, 1920, 1080, true), c.tooSoft(undefined, undefined, 1920, 1080)]") == [False, True, True, True, False]


def test_cutout_label_lands_inside_the_opaque_shape():
    grid = "Array.from({length: 40}, (_, i) => Array.from({length: 40}, (_v, j) => (i >= 10 && i < 30 && j >= 20 ? 1 : 0)))"
    x, y = crop(f"c.snapOpaque({grid}, {{x: 0, y: 0, w: 400, h: 400}}, [0, 200])")
    assert 200 + 8 <= x <= 200 + 24 and 100 + 8 <= y <= 300 - 8                 # 왼쪽에서 와도 불투명한 곳 안쪽 8px 에 찍힌다
    assert crop(f"c.snapOpaque({'[[1, 0], [0, 0]]'}, {{x: 0, y: 0, w: 400, h: 400}}, [0, 0])") is None     # 안쪽이 없으면 null(상자 기준으로 돌아간다)


def test_expand_is_a_marker_without_a_place():
    out = clean_overlays([{"kind": "circle", "box": [0.1, 0.1, 0.2, 0.2]}] * 4 + [{"kind": "expand", "text": "글", "at_word": "낱말"}, {"kind": "expand"}])
    assert [o["kind"] for o in out] == ["circle"] * 3 + ["expand"] and out[-1] == {"kind": "expand"}   # 화면 표시 3개 상한을 먹지 않고, 한 번만


def test_expand_only_between_abutting_full_frames_at_most_twice():
    g = lambda i, s, e, cover=True, expand=True: {"id": i, "start": s, "end": e, "cover": cover, "expand": expand}
    gs = [g("a", 0, 4, expand=False), g("b", 4, 8), g("over", 7, 9, cover=False), g("c", 8.3, 12), g("host", 15, 18), g("e", 18, 20)]
    assert crop(f"c.expandPairs({json.dumps(gs)}, 0.5)") == {"b": "a", "c": "b"}                 # host 는 앞이 화자(3초 틈)라 하드 컷, e 는 세 번째라 없음
    assert crop(f"c.expandPairs({json.dumps(gs[3:])}, 0.5)") == {"e": "host"}
    assert crop("c.expandRect(1, 1920, 1080, [500, 400])") == {"x": 0, "y": 0, "w": 1920, "h": 1080, "a": 0}   # 끝은 화면 전체
    r = crop("c.expandRect(0, 1920, 1080, [1900, 1000])")
    assert r["x"] + r["w"] <= 1920 - 96 and r["y"] + r["h"] <= 1080 - 240 and r["a"] < 0          # 시작은 화면·자막 안쪽의 기울어진 조각


def _item(**kw):
    return {"need": "entity", "treatment": "hero", "start_seg": 1, "end_seg": 1, "start_word": "", "count": 2, "claim": "c",
            "subject": {"name_ko": "건물", "kind": "work"}, **kw}


def _asset(src="images/a.jpg", **kw):
    return {"src": src, "kind": "photo", "w": 2400, "h": 1600, "credit": "c", "tier": "A", **kw}


def test_vision_marks_reach_the_graphic_by_annotation_number():
    anns = [{"kind": "circle", "target": "지붕", "text": "", "at_word": "지붕을"}, {"kind": "arrow", "target": "문", "text": "", "at_word": ""},
            {"kind": "memo", "target": "", "text": "여기만 뚫렸다", "at_word": ""}]
    marks = [{"annotation": 1, "box": [0.4, 0.1, 0.2, 0.1], "point": [], "outline": []}]         # A2 는 비전이 못 찾았다
    gs, _ = evg.to_graphics([_item(annotations=anns, tone="desaturate")], [{"i": 0, "assets": [_asset(marks=marks), _asset("images/b.jpg")]}])
    g = gs[0]
    assert [o["kind"] for o in g["overlays"]] == ["circle", "memo"] and g["overlays"][0]["box"] == [0.4, 0.1, 0.2, 0.1]
    assert g["tone"] == "desaturate"
    assert len(g["assets"]) == 1 and g["assets"][0]["focus"] == pytest.approx([0.4, 0.1, 0.2, 0.1])   # 좌표는 그 한 장의 것, 크롭은 대상 쪽으로


def test_cutout_uses_the_second_asset_and_stays_in_the_ledger():
    anns = [{"kind": "cutout", "target": "오른쪽 빈터", "text": "이 의자", "at_word": ""}]
    marks = [{"annotation": 1, "box": [], "point": [0.7, 0.5], "outline": []}]
    gs, _ = evg.to_graphics([_item(annotations=anns)], [{"i": 0, "assets": [_asset(marks=marks), _asset("images/b.jpg", cut="images/b.cut2.png", w=800, h=900)]}])
    o = gs[0]["overlays"][0]
    assert o["image"] == "images/b.cut2.png" and o["cut"] is True and (o["w"], o["h"]) == (800, 900)
    assert [a["src"] for a in gs[0]["assets"]] == ["images/a.jpg", "images/b.jpg"]    # 자료 대장·출처에 남는다


def test_video_stock_never_uses_poster_coordinates():
    anns = [{"kind": "circle", "target": "손", "text": "손", "at_word": ""}, {"kind": "memo", "target": "", "text": "메모", "at_word": ""}]
    marks = [{"annotation": 1, "box": [0.1, 0.1, 0.2, 0.2], "point": [], "outline": []}]
    item = _item(need="stock", stock={"kind": "video", "query_en": "hand"}, annotations=anns, tone="darken")
    video, _ = evg.to_graphics([item], [{"i": 0, "stock": {"src": "broll/a.mp4", "kind": "video", "marks": marks}}])
    assert [(o["kind"], "box" in o) for o in video[0]["overlays"]] == [("label", False), ("memo", False)] and video[0]["tone"] == "darken"
    photo, _ = evg.to_graphics([{**item, "stock": {"kind": "photo", "query_en": "hand"}}], [{"i": 0, "stock": {"src": "broll/a.jpg", "kind": "photo", "marks": marks}}])
    assert photo[0]["overlays"][0]["box"] == [0.1, 0.1, 0.2, 0.2] and photo[0]["focus"] == pytest.approx([0.2, 0.2])


def test_grid_keeps_only_paper_notes():
    marks = [{"annotation": 1, "box": [0.1, 0.1, 0.2, 0.2], "point": [], "outline": []}]
    anns = [{"kind": "circle", "target": "x", "text": "", "at_word": ""}, {"kind": "memo", "target": "", "text": "메모", "at_word": ""}]
    gs, _ = evg.to_graphics([_item(annotations=anns, treatment="grid", count=4)], [{"i": 0, "assets": [_asset(f"images/{c}.jpg", marks=marks) for c in "abcd"]}])
    assert [o["kind"] for o in gs[0]["overlays"]] == ["memo"] and len(gs[0]["assets"]) == 4


def test_vision_marks_survive_both_pick_paths(tmp_path):
    marks = [{"annotation": 1, "box": [0.1, 0.1, 0.2, 0.2], "point": [], "outline": []}]
    pk = {"request": 1, "reason": "", "choices": [{"candidate": 2, "score": 3, "main_subject": True, "cliche": False, "shows": "s", "focus_box": [], "marks": marks}]}
    assert choose(pk, 3, 1, "")[0][1]["marks"] == marks                       # 사다리(위키미디어·미술관)
    studio = SimpleNamespace(pick_evidence=lambda *a: [pk])
    [flat] = Studio.pick_stock(studio, "", "", [])                            # 스톡
    assert flat["candidate"] == 2 and flat["marks"] == marks
    seen = {}

    def pick(text, sheets):
        seen["text"] = text
        return [flat]
    res = StockResearcher(hub=None, ff=None, work=tmp_path, public=tmp_path, pick=pick)
    cand = [StockCandidate("photo", str(i), "u", "", "d", 100, 100) for i in range(2)]
    st = {"kind": "photo", "query_en": "q", "annotations": [{"kind": "circle", "target": "지붕"}]}
    choice, _ = res._pick_round(["k"], {"k": st}, {"k": cand})
    assert choice == {"k": 1} and res._marks["k"] == marks and "A1 circle 「지붕」" in seen["text"]


def test_label_gate_reads_overlay_text():
    g = {"template": "evidence", "data": {"overlays": [{"kind": "memo", "text": "이 장면을 보여준다"}, {"kind": "label", "text": "1853년"}]}}
    assert not gate.b4_direction_notes([g]).ok
    gate.scrub_labels([g])
    assert [o["text"] for o in g["data"]["overlays"]] == ["", "1853년"]


def _utt(uid: int, t: float, text: str, per: float = 0.45) -> Utterance:
    words = [Word(w, t + k * per, t + k * per + per * 0.9, 0.95) for k, w in enumerate(text.split())]
    return Utterance(id=uid, start=t, end=words[-1].end, text=text, asr_text=text, words=words, status="keep")


def test_overlays_land_on_their_words_and_survive_replanning():
    utts = [_utt(0, 0.0, "첫 문장입니다"), _utt(1, 3.0, "이 건물의 지붕을 보시면 처음부터 문이 없었다는 걸 아실 겁니다 정말로"), _utt(2, 12.0, "다음 이야기입니다")]
    ov = [{"kind": "circle", "box": [0.4, 0.1, 0.2, 0.1], "at_word": "지붕을"}, {"kind": "memo", "text": "메모", "at_word": "문이"},
          {"kind": "label", "text": "못 찾는 낱말", "at_word": "없는말"}, {"kind": "expand"}]
    g = {**evg._g("evidence", "fullscreen", 1, 1, "", assets=[_asset()], treatment="hero", tier="A"), "overlays": ov, "tone": "darken"}
    plan = normalize_long({"graphics": [g], "chapters": [{"seg": 0, "title": "c"}]}, utts, [])
    [ev] = [x for x in plan["graphics"] if x["template"] == "evidence"]
    assert ev["overlays"][0]["at_word"] == "지붕을" and ev["tone"] == "darken"      # plan.json 을 다시 정규화해도 남는다
    [tg] = [x for x in time_graphics([ev], utts, TimeMap([Span(0.0, 20.0)]), total=20.0) if x.template == "evidence"]
    assert tg.data["tone"] == "darken"
    by = tg.data["overlays"]
    roof = next(w.start for w in utts[1].words if w.text == "지붕을")
    door = next(w.start for w in utts[1].words if w.text == "문이")
    assert tg.start + by[0]["at"] + 0.33 == pytest.approx(roof - 0.2, abs=0.01)
    assert tg.start + by[1]["at"] + 0.33 == pytest.approx(door - 0.2, abs=0.01)
    assert by[2]["at"] == pytest.approx(by[1]["at"] + 1.0)                     # 못 찾은 표시는 앞 표시 뒤로
    assert all("at_word" not in o for o in by) and len(tg.data["wordMarks"]) == 2
    assert by[3] == {"kind": "expand"}                                          # 전환 표시는 말에 착지하지 않는다(앞 표시의 시각도 밀지 않는다)
    assert ev["overlays"][0].get("at_word") == "지붕을"                         # 계획의 원본은 그대로(다시 잴 수 있게)


def test_preflight_drops_a_missing_cutout_only(tmp_path):
    (tmp_path / "images").mkdir()
    Image.new("RGB", (8, 8)).save(tmp_path / "images" / "a.jpg")
    g = {"template": "evidence", "start": 1.0, "data": {"assets": [{"src": "images/a.jpg"}],
         "overlays": [{"kind": "cutout", "image": "images/none.png"}, {"kind": "cutout", "image": "images/a.jpg"}, {"kind": "memo", "text": "m"}]}}
    notes: list[str] = []
    assert preflight.fix_graphic(g, preflight.MediaCheck(tmp_path), notes)
    assert [o.get("image") for o in g["data"]["overlays"]] == ["images/a.jpg", None] and notes


def test_compose_reads_a_korean_file_name(tmp_path):
    p = tmp_path / "해결책_스케치.jpg"          # 자료 폴더의 파일명 — cv2.imread 는 Windows 에서 못 읽어 빈 쪽을 못 쟀다
    Image.new("RGB", (64, 48), "white").save(p)
    assert compose.analyze_image(p)["w"] == 64
    assert compose.analyze_image(tmp_path / "없는파일.jpg") == {}


def test_shorts_do_not_inherit_full_frame_overlays():
    ov = [{"kind": "memo", "text": "m", "at": 0.5}]
    ev = short_retype({"template": "evidence", "assets": [_asset()], "overlays": ov, "tone": "darken", "title": "t"})
    broll = short_retype({"template": "broll", "src": "broll/a.jpg", "overlays": ov, "tone": "darken"})
    assert "overlays" not in ev and "tone" not in ev and "overlays" not in broll and "tone" not in broll


def test_tall_dimension_stays_in_frame_and_cropped_ends_become_a_memo():
    view = "{x: 0, y: 0, w: 1920, h: 1080}"
    [a, b] = crop(f"c.dimensionLine([1344, 108], [1344, 1026], {view}, 1080, 11, {{top: 108}})")
    assert min(a[1], b[1]) >= 11 and b[1] - a[1] == 918                       # 세로선은 대상 위로 넘기지 않고 길이 그대로 올린다
    cut = "c.coverMap(1600, 1200, 1920, 1080)"
    assert crop(f"c.endsVisible([[0.5, 0.05], [0.5, 0.95]], {cut}, {view})") is False
    assert crop(f"c.endsVisible([[0.5, 0.2], [0.5, 0.8]], {cut}, {view})") is True


def _late_graphic():
    u = Utterance(id=1, start=2.0, end=4.0, text="지붕을 본다", asr_text="지붕을 본다",
                  words=[Word("지붕을", 2.0, 2.6), Word("본다", 2.7, 4.0)])
    g = {"template": "keyword", "layout": "overlay", "start_seg": 1, "end_seg": 1, "overlays": [{"kind": "memo", "text": "지붕", "at_word": "지붕을"}]}
    return g, [u], TimeMap([Span(0.0, 30.0)])


def test_a18_catches_marks_of_a_graphic_pushed_behind_its_word():
    from studio.director.plan import land_marks
    g, utts, tm = _late_graphic()
    tg = SimpleNamespace(start=8.0, end=14.0, data={}, id="g0")
    land_marks(tg, g, utts, tm)
    assert tg.data["overlays"][0]["at"] == 0.0 and tg.data["wordMarks"][0]["spoken"] == pytest.approx(2.0, abs=0.01)
    assert not gate.a18_word_sync([{"start": tg.start, "data": tg.data}]).ok      # 말보다 6초 늦다


def test_marks_are_landed_again_when_the_start_moves():
    from studio.director.plan import land_marks
    g, utts, tm = _late_graphic()
    tg = SimpleNamespace(start=1.0, end=14.0, data={}, id="g0")
    land_marks(tg, g, utts, tm)
    first = tg.data["overlays"][0]["at"]
    tg.start = 0.5
    land_marks(tg, g, utts, tm)
    assert tg.data["overlays"][0]["at"] == pytest.approx(first + 0.5, abs=0.01)
