"""템플릿 collage · keyword_montage: 망점 오림, 항목 묶기, preflight, 계획 보존."""
from __future__ import annotations

import numpy as np
from PIL import Image

from studio.assets import graphics as evg
from studio.assets.cutout import _skyline_mask, montage_still, press_back, press_cutout
from studio.director.catalog import TEMPLATES
from studio.director.plan import normalize_long
from studio.render import preflight


def _photo(src, **kw):
    return {"src": src, "kind": "photo", "w": 800, "h": 600, "credit": "사진: A", "tier": "A", **kw}


def _item(seg, treatment, name, **kw):
    return {"start_seg": seg, "end_seg": seg, "start_word": name, "need": "entity", "treatment": treatment, "label": name, "claim": "c", "subject": {"name_ko": name, "name_en": name.upper(), "year": "1860", "kind": "person"}, **kw}


def _out(i, *srcs):
    return {"i": i, "assets": [_photo(s) for s in srcs], "archive": None, "stock": None}


def _building(path, sky=240, ink=40):
    a = np.full((640, 640, 3), sky, np.uint8)
    a[300:] = 120                      # 땅
    a[120:560, 220:420] = ink           # 탑
    a[60:120, 300:340] = ink            # 첨탑
    Image.fromarray(a).save(path, quality=92)


def test_press_cutout_cuts_a_skyline_and_falls_back_to_a_print(tmp_path):
    b = tmp_path / "tower.jpg"
    _building(b)
    path, cut, kind = press_cutout(b, kind="place")
    assert (cut, kind) == (True, "place") and path.suffix == ".png"
    with Image.open(path) as im:
        a = np.asarray(im.convert("RGBA"))[..., 3]
        rgb = np.asarray(im.convert("RGB"))
    assert (a > 200).mean() > 0.1 and (a < 30).any()                 # 오려졌다
    assert np.abs(rgb[..., 0].astype(int) - rgb[..., 2]).mean() < 30   # 흑백(잉크·종이 사이)
    noise = tmp_path / "noise.jpg"
    Image.fromarray(np.random.default_rng(1).integers(0, 255, (640, 640, 3), np.uint8)).save(noise, quality=92)
    p2, cut2, _ = press_cutout(noise, kind="person")
    assert not cut2 and p2.suffix == ".jpg" and p2.exists()           # 못 오리면 망점 인화지
    assert press_cutout(noise, kind="person") == (p2, False, "person")      # 같은 파일은 다시 만들지 않는다


def test_skyline_cut_leaves_no_band_of_sky_around_the_building(tmp_path):
    b = tmp_path / "tower.jpg"
    _building(b)
    arr = np.asarray(Image.open(b).convert("RGB"))
    m = _skyline_mask(arr)
    assert m is not None and (m > 127).mean() > 0.05
    assert ((m > 127) & (arr[..., 0] > 200)).mean() < 0.0015          # 예전에는 하늘색 띠가 흰 스티커 윤곽으로 남았다


def test_back_piece_is_out_of_focus_without_colour_bleed(tmp_path):
    a = np.zeros((600, 600, 4), np.uint8)
    a[..., 0] = 255                                                  # 오린 바깥은 빨강
    a[100:500, 100:500, :3] = np.random.default_rng(1).integers(90, 160, (400, 400, 3), np.uint8)
    a[100:500, 100:500, 3] = 255
    src = tmp_path / "x.press2.png"
    Image.fromarray(a, "RGBA").save(src)
    out = press_back(src)
    assert out.name == "x.press2.back.png" and press_back(src) == out
    b = np.asarray(Image.open(out))
    assert b[200:400, 200:400, :3].std() < 0.4 * a[200:400, 200:400, :3].std()
    assert b[300, 300, 3] > 240 and b[20, 20, 3] < 8 and 60 < b[300, 100, 3] < 200     # 안팎은 그대로, 경계만 부드럽게
    edge = b[300, 96:112, :3].astype(int)
    assert (edge[..., 0] - edge[..., 1]).max() < 40                  # 바깥의 빨강이 번져 들어오지 않는다


def _flat(path, v):
    Image.new("RGB", (2400, 1350), (v, v, v)).save(path, quality=95)


def test_montage_photos_land_on_one_brightness_and_black_ones_are_dropped(tmp_path):
    (tmp_path / "images").mkdir()
    for n, v in (("a", 210), ("b", 128), ("c", 72), ("d", 12)):
        _flat(tmp_path / "images" / f"{n}.jpg", v)
    g = {"template": "keyword_montage", "data": {"cutouts": [{"image": f"images/{n}.jpg", "credit": n} for n in "abcd"]}}
    evg._finish_press([g], tmp_path)
    got = g["data"]["cutouts"]
    assert [c["orig"] for c in got] == ["images/a.jpg", "images/b.jpg", "images/c.jpg"]
    for c in got:
        assert c["image"].endswith(".mont1.jpg") and 60 <= np.median(np.asarray(Image.open(tmp_path / c["image"]).convert("L"))) <= 80
    assert montage_still(tmp_path / "images" / "d.jpg")[1] is False
    only_dark = {"template": "keyword_montage", "data": {"cutouts": [{"image": "images/d.jpg"}, {"image": "images/d.jpg"}]}}
    evg._finish_press([only_dark], tmp_path)
    assert len(only_dark["data"]["cutouts"]) == 2                     # 전부 어두우면 몽타주를 없애지 않고 그대로 — 올리지는 않는다
    assert np.median(np.asarray(Image.open(tmp_path / only_dark["data"]["cutouts"][0]["image"]).convert("L"))) < 20


def test_only_the_hero_stays_in_focus_and_material_is_credited(tmp_path):
    (tmp_path / "images").mkdir()
    for n in ("place.png", "hero.png", "side.png", "rect.jpg", "orig.jpg"):
        Image.new("RGB", (120, 120), (90, 90, 90)).save(tmp_path / "images" / n)
    pieces = [{"image": "images/place.png", "orig": "images/orig.jpg", "cut": True, "kind": "place", "credit": "A"},
              {"image": "images/rect.jpg", "orig": "images/orig.jpg", "cut": False, "kind": "person", "credit": "B"},
              {"image": "images/hero.png", "orig": "images/orig.jpg", "cut": True, "kind": "person", "credit": "A"},
              {"image": "images/side.png", "orig": "images/orig.jpg", "cut": True, "kind": "person"},
              {"image": "images/orig.jpg", "orig": "images/orig.jpg", "cut": False, "kind": "person"}]
    g = {"template": "title", "data": {"title": "t", "cutouts": pieces}}
    evg._finish_press([g], tmp_path)
    got = g["data"]["cutouts"]
    assert [".back." in c["image"] for c in got] == [True, True, False, True, False]      # 망점을 못 찍은 원본은 그대로
    assert g["data"]["credit"] == "A · B"


def test_named_people_in_a_row_become_one_collage_landing_on_each_name():
    items = [_item(1, "collage", "링컨"), _item(2, "collage", "브람스"), _item(3, "collage", "보들레르")]
    outs = [_out(i, f"images/{i}.jpg") for i in range(3)]
    gs, _ = evg.to_graphics(items, outs)
    assert [g["template"] for g in gs] == ["collage"]
    g = gs[0]
    assert len(g["cutouts"]) == 3 and g["name"] == "링컨" and g["name_sub"] == "링컨".upper() + " · 1860" and g["disc"] == "orange"
    assert [c["word"] for c in g["cutouts"]] == ["링컨", "브람스", "보들레르"] and all(c["kind"] == "person" for c in g["cutouts"])
    assert g["credit"] == "사진: A"
    rows = evg.ledger_rows([{"template": "collage", "start": 0, "end": 1, "data": {"cutouts": g["cutouts"]}}], "롱폼")
    assert len(rows) == 3


def test_collage_needs_two_images_and_stays_scarce():
    # 한 장뿐이면 전면 자료 그대로
    gs, _ = evg.to_graphics([_item(1, "collage", "링컨")], [_out(0, "images/a.jpg")])
    assert gs[0]["template"] == "evidence"
    # 멀리 떨어진 콜라주가 많아도 COLLAGE_BEATS 곳까지만, 나머지는 전면 자료
    many = [_item(10 * i, "collage", f"인물{i}", count=2) for i in range(7)]
    outs = [_out(i, f"images/{i}a.jpg", f"images/{i}b.jpg") for i in range(7)]
    gs, _ = evg.to_graphics(many, outs)
    assert sum(g["template"] == "collage" for g in gs) == evg.COLLAGE_BEATS
    assert sum(g["template"] == "evidence" for g in gs) == 7 - evg.COLLAGE_BEATS
    assert [g["disc"] for g in gs if g["template"] == "collage"] == ["orange", "mint", "mint", "orange"]        # 오렌지는 세 곳에 한 곳까지


def test_sequence_with_a_word_becomes_a_montage():
    items = [_item(i, "sequence", f"사례{i}", display="쌓이는 도시") for i in (1, 2, 3)]
    gs, _ = evg.to_graphics(items, [_out(i, f"images/{i}.jpg") for i in range(3)])
    assert [g["template"] for g in gs] == ["keyword_montage"]
    assert gs[0]["title"] == "쌓이는 도시" and len(gs[0]["cutouts"]) == 3
    # 두 장은 몽타주가 아니다
    gs2, _ = evg.to_graphics(items[:2], [_out(i, f"images/{i}.jpg") for i in range(2)])
    assert all(g["template"] == "evidence" for g in gs2)


def test_plan_keeps_collage_fields():
    from studio.models import Utterance, Word

    def utt(i, t0, text):
        ws = [Word(w, t0 + k * 0.4, t0 + k * 0.4 + 0.3, 0.95) for k, w in enumerate(text.split())]
        return Utterance(id=i, start=t0, end=ws[-1].end, text=text, asr_text=text, words=ws, status="keep")
    g ={"template": "collage", "layout": "fullscreen", "start_seg": 1, "end_seg": 1, "cutouts": [{"image": "a.jpg", "orig": "a.jpg", "kind": "person"}, {"image": "b.jpg"}], "name": "링컨", "name_sub": "1860", "disc": "mint", "credit": "c"}
    plan = normalize_long({"graphics": [g, {"template": "collage", "layout": "fullscreen", "start_seg": 1, "cutouts": [{"image": "a.jpg"}]}]}, [utt(1, 0.0, "링컨은 그렇게 말했습니다")], [])
    assert len(plan["graphics"]) == 1
    out = plan["graphics"][0]
    assert out["name"] == "링컨" and out["disc"] == "mint" and out["cutouts"][0]["orig"] == "a.jpg"


def test_preflight_falls_back_to_original_and_drops_empty_collages(tmp_path):
    (tmp_path / "images").mkdir()
    Image.new("RGB", (8, 8)).save(tmp_path / "images" / "a.jpg")
    Image.new("RGB", (8, 8)).save(tmp_path / "images" / "b.jpg")
    chk = preflight.MediaCheck(tmp_path)
    notes: list[str] = []
    g = {"template": "collage", "start": 1.0, "data": {"cutouts": [{"image": "images/none.png", "orig": "images/a.jpg", "cut": True}, {"image": "images/b.jpg"}]}}
    assert preflight.fix_graphic(g, chk, notes)
    assert g["data"]["cutouts"][0]["image"] == "images/a.jpg" and g["data"]["cutouts"][0]["cut"] is False
    bad = {"template": "keyword_montage", "start": 1.0, "data": {"cutouts": [{"image": "images/none.png"}, {"image": "images/b.jpg"}, {"image": "images/none2.png"}]}}
    assert not preflight.fix_graphic({"template": "collage", "start": 1.0, "data": {"cutouts": [{"image": "images/none.png"}]}}, chk, notes)
    assert preflight.fix_graphic(bad, chk, notes) is False


def test_press_collages_fills_title_and_chapter_from_real_photos(tmp_path):
    (tmp_path / "images").mkdir()
    for n in ("a", "b", "c"):
        _building(tmp_path / "images" / f"{n}.jpg", sky=235 + ord(n) % 7)
    photo = lambda src, t: {"template": "photo", "layout": "fullscreen", "start": t, "end": t + 3, "data": {"image": src}}  # noqa: E731
    gs = [{"template": "title", "layout": "fullscreen", "start": 0.0, "end": 3.0, "data": {"title": "t"}},
          {"template": "chapter", "layout": "fullscreen", "start": 5.0, "end": 8.0, "data": {"title": "c1"}},
          photo("images/a.jpg", 9.0), photo("images/b.jpg", 13.0), photo("images/c.jpg", 17.0)]
    evg.press_collages(gs, tmp_path)
    assert len(gs[0]["data"]["cutouts"]) >= 2 and all(c["image"].startswith("images/") for c in gs[0]["data"]["cutouts"])
    assert len(gs[1]["data"]["cutouts"]) >= 2
    short = [photo("images/a.jpg", 4.0), photo("images/b.jpg", 8.0)]
    evg.press_short_hook(short, tmp_path)
    assert short[-1]["template"] == "collage" and short[-1]["start"] == 0.0 and len(short[-1]["data"]["cutouts"]) == 2
    # 앞 2.6초에 전면 그래픽이 이미 있으면 넣지 않는다
    taken = [photo("images/a.jpg", 1.0), photo("images/b.jpg", 8.0)]
    evg.press_short_hook(taken, tmp_path)
    assert all(g["template"] == "photo" for g in taken)


def test_catalog_has_researcher_templates():
    assert TEMPLATES["collage"].layouts == ("fullscreen",) and TEMPLATES["keyword_montage"].layouts == ("fullscreen",)
