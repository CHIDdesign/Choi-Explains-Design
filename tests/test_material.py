"""재질 키트(디자인 v5.1): 텍스처 생성·캐시, 오림 스택 preflight, 인용 줄바꿈."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from studio.assets.cutout import cutout_mask
from studio.render import assets, preflight
from studio.render.props import board_scraps, chapter_scraps, stamps_onto_media
from studio.render.remotion import RenderError, find_node
from studio.vision import compose

ROOT = Path(__file__).resolve().parent.parent


def test_textures_generate_once_and_reach_public(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, "USER_DIR", tmp_path / "user")
    monkeypatch.setattr(assets, "RENDERER_DIR", tmp_path / "renderer")
    monkeypatch.setattr(assets, "TEXTURES", {"memo": assets.TEXTURES["memo"]})
    dst = tmp_path / "public" / "fx" / "tex"
    assert assets.make_textures(dst) == ["memo.jpg", "desk.jpg"]
    memo = np.asarray(Image.open(dst / "memo.jpg").convert("RGB"), np.float32)
    assert memo.shape == (1080, 1920, 3)
    assert np.abs(memo.mean((0, 1)) - (252, 250, 244)).max() < 8          # 재질을 입혀도 그 종이색이다
    assert memo.std((0, 1)).max() > 1.0                                    # 평면색이 아니다
    assert (tmp_path / "renderer" / "public" / "fx" / "tex" / "memo.jpg").exists()
    cached = tmp_path / "user" / "cache" / f"textures_v{assets.TEX_VERSION}" / "memo.jpg"
    stamp = cached.stat().st_mtime_ns
    assets.make_textures(dst)
    assert cached.stat().st_mtime_ns == stamp                              # 두 번째부터는 만들지 않는다


def test_cutout_stack_without_files_is_dropped(tmp_path):
    (tmp_path / "images").mkdir()
    Image.new("RGB", (8, 8)).save(tmp_path / "images" / "a.jpg")
    chk = preflight.MediaCheck(tmp_path)
    notes: list[str] = []
    g = {"template": "cutout_stack", "start": 1.0, "data": {"cutouts": [{"image": "images/a.jpg"}, {"image": "images/none.jpg"}]}}
    assert preflight.fix_graphic(g, chk, notes) and [c["image"] for c in g["data"]["cutouts"]] == ["images/a.jpg"]
    assert not preflight.fix_graphic({"template": "cutout_stack", "start": 1.0, "data": {"cutouts": [{"image": "images/none.jpg"}]}}, chk, notes)


def test_quote_breaks_at_the_clause_not_after_a_determiner():
    try:
        node = find_node()
    except RenderError:
        pytest.skip("node 없음")
    fit = (ROOT / "renderer" / "src" / "lib" / "fit.ts").as_uri()
    code = f"import {{balanceLines as b}} from '{fit}'; console.log(JSON.stringify([b('우리가 건물을 만들지만, 그 다음에는 건물이 우리를 만든다.', 65, 1305, 4, -0.01), b('광화문 광장 면적 중 그늘 없는 비율', 36, 480, 3, -0.015)]))"
    r = subprocess.run([node, "--experimental-strip-types", "--input-type=module", "-e", code], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        pytest.skip(f"node 가 TS 를 못 읽음: {r.stderr[:80]}")
    quote, stat = json.loads(r.stdout)
    assert quote == ["우리가 건물을 만들지만,", "그 다음에는 건물이 우리를 만든다."]
    assert not any(line.endswith("면적") for line in stat)                # '면적 / 중' 으로 끊지 않는다


def _photo(w=900, h=600):
    return np.random.default_rng(1).integers(30, 150, (h, w, 3), np.uint8)


def test_scan_margins_are_trimmed_and_marks_follow(tmp_path):
    a = _photo()
    cream = (236, 229, 212)
    a[:40], a[-40:] = cream, cream
    a[:, :60], a[:, -60:] = cream, cream
    p = tmp_path / "scan.jpg"
    Image.fromarray(a).save(p, quality=95)
    out, rect = compose.trim_scan(p)
    assert abs(Image.open(out).width - 780) < 16 and abs(Image.open(out).height - 520) < 16
    m = compose.reframe_marks([{"point": [0.5, 0.5], "box": [0.5, 0.5, 0.1, 0.1], "outline": [0.5, 0.5]}], rect)[0]
    assert m["point"] == pytest.approx([0.5, 0.5], abs=0.01) and m["outline"] == pytest.approx([0.5, 0.5], abs=0.01)
    assert m["box"][2] > 0.1                                                  # 잘린 만큼 상자는 커진다


def test_mark_outside_the_inner_rect_keeps_the_margin(tmp_path):
    a = _photo()
    a[:, :60], a[:, -60:], a[:40], a[-40:] = (236, 229, 212), (236, 229, 212), (236, 229, 212), (236, 229, 212)
    p = tmp_path / "scan.jpg"
    Image.fromarray(a).save(p, quality=95)
    assert compose.trim_scan(p, [0.0, 0.3, 0.05, 0.4])[1][0] == 0.0          # 표시 대상이 여백에 있으면 그쪽은 자르지 않는다


def test_photo_on_a_plain_backdrop_is_not_a_scan(tmp_path):
    a = np.full((600, 900, 3), 230, np.uint8)
    a[150:450, 300:600] = _photo(300, 300)
    p = tmp_path / "product.jpg"
    Image.fromarray(a).save(p, quality=95)
    assert compose.trim_scan(p) is None                                       # 흰 배경 제품 사진의 배경은 여백이 아니다


def test_sky_along_one_edge_is_not_a_margin(tmp_path):
    a = _photo()
    a[:150] = (225, 228, 232)
    p = tmp_path / "sky.jpg"
    Image.fromarray(a).save(p, quality=95)
    assert compose.trim_scan(p) is None


def test_tight_crop_cuts_the_backdrop_round_the_object(tmp_path):
    a = np.tile(np.linspace(232, 160, 800, dtype=np.float32)[:, None, None], (1, 600, 3)).astype(np.uint8)
    a[250:600, 200:400] = (60, 40, 30)
    p = tmp_path / "chair.jpg"
    Image.fromarray(a).save(p, quality=95)
    w, h = Image.open(compose.tight_crop(p)).size
    assert 200 <= w < 360 and 350 <= h < 520


def test_floor_shadow_is_not_part_of_the_cutout():
    a = np.full((800, 640, 3), 216, np.uint8)
    a[200:560, 200:440] = (70, 42, 24)                                        # 물건
    a[560:640, 170:480] = np.linspace(112, 172, 80, dtype=np.uint8)[:, None, None]   # 바닥 그림자: 바탕보다 어둡고 무채색, 물건 밑동일수록 짙다
    m = cutout_mask(Image.fromarray(a))
    assert m is not None and m[350, 320] > 200 and m[610, 320] < 40 and m[580, 320] < 40


def test_chapter_card_shows_the_chapters_own_material():
    big = lambda t: {"template": "chapter", "layout": "fullscreen", "start": t, "data": {"title": "x"}}
    photo = lambda t, n: {"template": "photo", "layout": "fullscreen", "start": t, "data": {"image": f"images/{n}.jpg", "w": 300, "h": 200}}
    ev = {"template": "evidence", "layout": "fullscreen", "start": 3.0, "data": {"assets": [{"src": "images/a.jpg", "kind": "photo", "w": 400, "h": 300}]}}
    gs = [big(0), ev, photo(5, "b"), photo(7, "c"), big(20), photo(25, "d")]
    chapter_scraps(gs)
    assert [x["image"] for x in gs[0]["data"]["scraps"]] == ["images/a.jpg", "images/b.jpg"] and [x["image"] for x in gs[4]["data"]["scraps"]] == ["images/d.jpg"]


def test_board_gets_the_nearest_real_picture_once():
    ev = lambda t, src, **kw: {"template": "evidence", "start": t, "data": {"assets": [{"src": src, "kind": "photo", "w": 800, "h": 600, **kw}]}}  # noqa: E731
    board = lambda t: {"template": "process", "layout": "fullscreen", "start": t, "data": {}}  # noqa: E731
    gs = [ev(10, "images/a.jpg"), ev(30, "images/b.jpg", cut="images/b.cut.png"), board(12), board(14), board(500)]
    board_scraps(gs)
    assert gs[2]["data"]["scraps"][0]["image"] == "images/a.jpg"
    assert gs[3]["data"]["scraps"][0] == {"image": "images/b.cut.png", "w": 800, "h": 600, "cut": True}     # 같은 사진을 두 보드에 쓰지 않는다
    assert "scraps" not in gs[4]["data"]                                                                     # 멀리 있는 자료는 붙이지 않는다


def test_stamp_over_a_picture_becomes_a_mark_on_it():
    photo = {"template": "photo", "layout": "fullscreen", "start": 5.0, "end": 9.0, "data": {"overlays": []}}
    stamp = {"template": "stamp", "layout": "overlay", "start": 6.0, "end": 8.0, "data": {"title": "철거 예정", "subtitle": "1966"}}
    alone = {"template": "stamp", "layout": "overlay", "start": 20.0, "end": 21.0, "data": {"title": "x"}}
    gs = [photo, stamp, alone]
    stamps_onto_media(gs)
    assert gs == [photo, alone]
    assert photo["data"]["overlays"] == [{"kind": "stamp", "point": [0.54, 0.3], "text": "철거 예정", "at": 1.0, "sub": "1966"}]


def test_parchment_blotches_move_lightness_only():
    import cv2
    lab = cv2.cvtColor(assets.make_texture("parchment").astype(np.float32) / 255, cv2.COLOR_RGB2LAB)
    low = cv2.GaussianBlur(lab[..., 1:], (0, 0), 40)
    assert np.sqrt(((low - low.mean((0, 1))) ** 2).sum(2)).max() <= 1.5                                      # 복숭아빛 번짐이 없다(ΔE)


def test_chapter_scrap_files_are_checked(tmp_path):
    (tmp_path / "images").mkdir()
    Image.new("RGB", (8, 8)).save(tmp_path / "images" / "a.jpg")
    g = {"template": "chapter", "start": 1.0, "data": {"title": "x", "scraps": [{"image": "images/a.jpg"}, {"image": "images/none.jpg"}]}}
    assert preflight.fix_graphic(g, preflight.MediaCheck(tmp_path), []) and [s["image"] for s in g["data"]["scraps"]] == ["images/a.jpg"]


def test_credit_strip_only_where_the_corner_is_bright():
    info = {"side": "left", "dark": False, "lum": [[0.2] * 3, [0.2] * 3, [0.2, 0.2, 0.9]]}
    assert compose.plan_media(info)["safe"]["light"] is True
    info["lum"][2][2] = 0.3
    assert compose.plan_media(info)["safe"]["light"] is False
