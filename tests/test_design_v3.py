"""디자인 v3 '종이 콜라주'(docs/디자인_v3_종이콜라주.md) 단위 테스트 — 운영자 레퍼런스(센트럴 파크 에디토리얼 콜라주):
오려 내기(고른 바탕만 · 인물은 경계가 갈릴 때만) · 콜라주 트리트먼트(오린 사진·큰 글자·연도·인용) 보존 · 자료 비율 방침
(얼굴 15~55% · 실물 자료 ≥ 30%) · 모션 DSL 새 명조 · 디자인 색(숲 초록 기본)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import gate  # noqa: E402
from studio.agents import schemas as S  # noqa: E402
from studio.assets import graphics as evg  # noqa: E402
from studio.assets import ladder as lad  # noqa: E402
from studio.assets.cutout import boundary_contrast, cutout, plain_background  # noqa: E402
from studio.director.plan import EXTRA_DATA_KEYS, _clean_graphic  # noqa: E402
from studio.motion.spec import clean_spec  # noqa: E402
from studio.render.props import brand_props  # noqa: E402
from studio.settings import Brand  # noqa: E402


def _object_on_paper(path: Path, *, hole: bool = True) -> Path:
    """흰 종이 위 의자 같은 물건(다리 사이가 바탕으로 둘러싸인 큰 구멍) — 압축 잡음 포함."""
    im = Image.new("RGB", (900, 700), (243, 240, 232))
    d = ImageDraw.Draw(im)
    d.rectangle([250, 120, 650, 200], fill=(30, 28, 26))          # 등받이
    d.rectangle([250, 380, 650, 440], fill=(30, 28, 26))          # 앉는 판
    d.rectangle([250, 120, 280, 640], fill=(120, 120, 125))       # 다리
    d.rectangle([620, 120, 650, 640], fill=(120, 120, 125))
    if hole:
        d.rectangle([250, 610, 650, 640], fill=(120, 120, 125))   # 아래 가로대 → 다리 사이가 닫힌 구멍
    a = np.asarray(im).astype(np.int16) + np.random.default_rng(3).integers(-5, 6, (700, 900, 3))
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(path, quality=90)
    return path


def test_cutout_removes_plain_background_and_enclosed_holes(tmp_path):
    src = _object_on_paper(tmp_path / "chair.jpg")
    out = cutout(src)
    assert out is not None and out.suffix == ".png" and out.exists()
    a = np.asarray(Image.open(out))[..., 3]
    h, w = a.shape
    assert a[0, 0] < 10 and a[-1, -1] < 10                     # 테두리 바탕은 투명
    # 내용 상자로 잘린 좌표: 등받이 0.10 · 앉는 판 0.55 · 그 사이 0.34 · 앉는 판과 가로대 사이 0.75
    assert a[int(h * 0.10), w // 2] > 240 and a[int(h * 0.55), w // 2] > 240
    # 다리 사이(등받이·앉는 판·가로대로 둘러싸인 바탕)도 지운다
    assert a[int(h * 0.34), w // 2] < 10 and a[int(h * 0.75), w // 2] < 10
    assert cutout(src) == out                                  # 같은 결과는 다시 만들지 않는다


def test_cutout_skips_busy_backgrounds_and_keeps_existing_alpha(tmp_path):
    rng = np.random.default_rng(1)
    busy = tmp_path / "street.jpg"
    Image.fromarray(rng.integers(0, 255, (500, 700, 3)).astype(np.uint8)).save(busy)
    assert plain_background(np.asarray(Image.open(busy))) is None
    assert cutout(busy) is None                                # 고른 바탕도 얼굴도 없으면 오리지 않는다(프린트로)
    rgba = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
    ImageDraw.Draw(rgba).ellipse([100, 50, 300, 250], fill=(200, 30, 30, 255))
    p = tmp_path / "logo.png"
    rgba.save(p)
    out = cutout(p)
    assert out is not None and np.asarray(Image.open(out))[..., 3].max() == 255


def test_boundary_contrast_rejects_cuts_through_flat_regions():
    arr = np.full((200, 200, 3), 128, np.uint8)
    arr[50:150, 50:150] = (20, 20, 20)
    good = np.zeros((200, 200), np.uint8)
    good[50:150, 50:150] = 255
    assert boundary_contrast(arr, good) > 0.9                  # 실제 윤곽을 따라 자른 경계
    bad = np.zeros((200, 200), np.uint8)
    bad[30:170, 30:170] = 255                                  # 회색 바탕 한가운데를 자른 경계
    assert boundary_contrast(arr, bad) < 0.2


def test_collage_treatment_from_research_items():
    assert lad.drawn_treatment("cutout", 1, "A") == "collage"
    assert lad.drawn_treatment("collage", 1, "A", "logo") == "hero"
    assert "collage" in S.TREATMENTS and {"display", "quote"} <= set(S.EVIDENCE["properties"]["items"]["items"]["properties"])
    base = {"start_seg": 1, "end_seg": 1, "start_word": "", "claim": "c", "need": "entity", "count": 1,
            "subject": {"name_ko": "옴스테드", "year": "1857"}, "label": "", "caption": "", "fallback": "type_card"}
    items = [dict(base, treatment="hero", display="센트럴 파크"),
             dict(base, treatment="hero"),
             dict(base, start_seg=2, end_seg=2, need="stock", treatment="full", quote="모두를 위한 정원",
                  stock={"kind": "video", "query_en": "aerial park city", "query_ko": "공원"}),
             dict(base, start_seg=3, end_seg=3, need="stock", treatment="collage", display="여백",
                  stock={"kind": "photo", "query_en": "empty bench park", "query_ko": "빈 벤치"})]
    asset = {"src": "images/a.jpg", "kind": "photo", "w": 1200, "h": 1500, "tier": "A", "credit": "c"}
    outs = [{"i": 0, "assets": [asset]}, {"i": 1, "assets": [dict(asset, cut="images/a.cut2.png")]},
            {"i": 2, "stock": {"src": "broll/v.mp4", "kind": "video", "credit": "k"}},
            {"i": 3, "stock": {"src": "broll/p.jpg", "kind": "photo", "credit": "k"}}]
    gs, _ = evg.to_graphics(items, outs)
    assert gs[0]["treatment"] == "collage" and gs[0]["display"] == "센트럴 파크" and gs[0]["year"] == "1857"
    assert gs[1]["treatment"] == "collage"                     # 오린 사진이 있으면 큰 글자 없이도 콜라주
    assert gs[2]["template"] == "broll" and gs[2]["quote"] == "모두를 위한 정원" and "treatment" not in gs[2]
    assert gs[3]["template"] == "broll" and gs[3]["treatment"] == "collage" and gs[3]["display"] == "여백"


def test_collage_fields_survive_plan_normalisation():
    assert {"year", "display", "quote", "cut", "w", "h"} <= set(EXTRA_DATA_KEYS)
    ev = {"template": "evidence", "layout": "fullscreen", "start_seg": 1, "end_seg": 1, "treatment": "collage",
          "assets": [{"src": "images/a.jpg", "kind": "photo", "w": 10, "h": 10, "cut": "images/a.cut2.png"}],
          "year": "c. 1857년", "display": "센트럴 파크 이야기", "quote": "q" * 50}
    out = _clean_graphic(ev, [1])
    assert out["treatment"] == "collage" and out["assets"][0]["cut"] == "images/a.cut2.png"
    assert out["year"] == "1857" and out["display"] == "센트럴 파크 이" and len(out["quote"]) == 36
    br = {"template": "broll", "layout": "fullscreen", "start_seg": 1, "end_seg": 1, "src": "broll/p.jpg", "kind": "photo",
          "stock": {"kind": "photo", "query_en": "bench", "query_ko": "벤치"}, "cut": "broll/p.cut2.png", "w": 1600,
          "h": 1067, "treatment": "collage", "display": "여백"}
    out = _clean_graphic(br, [1])
    assert out["cut"] == "broll/p.cut2.png" and out["treatment"] == "collage" and out["display"] == "여백"
    out = _clean_graphic(dict(br, treatment="hero"), [1])
    assert "treatment" not in out                              # 스톡의 트리트먼트는 콜라주만 뜻이 있다


def test_media_first_policy_thresholds():
    assert gate.a8_face_ratio(0.25).ok and gate.a8_face_ratio(0.5).ok
    assert not gate.a8_face_ratio(0.62).ok and gate.a8_face_ratio(0.62).repair == "fill_gaps"
    assert not gate.a8_face_ratio(0.1).ok
    gs = [{"id": "g", "template": "broll", "layout": "fullscreen", "start": 0, "end": 50, "data": {"src": "b.mp4"}}]
    assert not gate.b1_media_ratio(gs, 200.0).ok                # 25% < 30%
    gs[0]["end"] = 70
    assert gate.b1_media_ratio(gs, 200.0).ok


def test_motion_dsl_accepts_new_serif_fonts():
    spec = clean_spec({"bg": "paper", "elements": [
        {"type": "text", "text": "1857", "x": 50, "y": 30, "size": 12, "font": "italic", "at": 0},
        {"type": "text", "text": "센트럴 파크", "x": 50, "y": 55, "size": 12, "font": "poster", "at": 0},
        {"type": "text", "text": "x", "x": 50, "y": 75, "size": 6, "font": "comic", "at": 0}]}, 6.0)
    fonts = [e.get("font") for e in spec["elements"]]
    assert fonts[:2] == ["italic", "poster"] and fonts[2] is None


def test_design_palette_defaults_to_forest_and_brand_keeps_accent():
    b = Brand()
    p = brand_props(b)
    assert b.palette == "forest" and p["accent"] == "#2B8A64" and p["deep"] and p["tint"]
    b.palette = "brand"
    p = brand_props(b)
    assert p["accent"] == b.accent and "deep" not in p
