"""사진 위 구도(studio/vision/compose.py): 빈 쪽 고르기 · cover 로 자를 때 얼굴이 잘리면 초점·액자."""
from __future__ import annotations

import numpy as np

from studio.vision import compose


def test_free_side_is_opposite_of_busy_subject():
    busy = np.array([[0.02, 0.03, 0.30], [0.02, 0.04, 0.35], [0.02, 0.03, 0.28]])      # 피사체가 오른쪽
    lum = np.full((3, 3), 0.6)
    p = compose._place(None, busy, lum)
    assert p["side"] == "left" and p["dark"] is False
    p2 = compose._place([0.05, 0.2, 0.3, 0.4], busy, lum)                              # 얼굴이 왼쪽 → 오른쪽에 글자
    assert p2["side"] == "right"
    p3 = compose._place(None, np.array([[0.3, 0.02, 0.3]] * 3), np.full((3, 3), 0.2))   # 양쪽 복잡·가운데 고요·어두움
    assert p3["side"] == "center" and p3["dark"] is True


def test_cover_crop_keeps_face_or_falls_back_to_contain():
    # 세로 사진(1000×1500)을 16:9 로 꽉 채우면 위아래가 잘린다 — 얼굴이 위쪽이면 초점을 얼굴로
    info = {"w": 1000, "h": 1500, "face": [0.3, 0.05, 0.4, 0.25], "side": "left", "dark": False}
    plan = compose.plan_media(info, 1920, 1080)
    assert plan["focus"] and plan["focus"][1] < 0.3 and "fit" not in plan
    assert compose.box_inside(info["face"], compose.visible_region(1000, 1500, 1920, 1080, tuple(plan["focus"])))
    # 얼굴이 세로의 70% 를 차지하면 어떻게 잘라도 잘린다 → 통째로
    info2 = {"w": 1000, "h": 1500, "face": [0.1, 0.1, 0.8, 0.7], "side": "left", "dark": False}
    assert compose.plan_media(info2, 1920, 1080).get("fit") == "contain"
    # 가로 사진의 얼굴이 가운데면 그대로
    info3 = {"w": 1600, "h": 900, "face": [0.4, 0.3, 0.2, 0.3], "side": "left", "dark": False}
    assert "focus" not in compose.plan_media(info3, 1920, 1080)


def test_analyze_image_measures_grid_and_side(tmp_path):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (640, 360), (235, 235, 230))
    d = ImageDraw.Draw(im)
    rng = np.random.default_rng(3)
    for _ in range(600):                                                  # 오른쪽에 복잡한 무늬
        x, y = int(rng.integers(430, 640)), int(rng.integers(0, 360))
        d.rectangle([x, y, x + 6, y + 6], fill=(int(rng.integers(0, 255)),) * 3)
    p = tmp_path / "a.jpg"
    im.save(p)
    info = compose.analyze_image(p)
    assert info["w"] == 640 and info["side"] == "left" and info["busy"][1][2] > info["busy"][1][0]
    assert "🖼 사진 1장" in compose.media_report([compose.plan_media(info)])
