"""렌더 전 자산 확인(studio/render/preflight.py)과 모션 장면 'pixabay:' 참조 해석.

2026-10-04 실제 작업: 모션 장면의 기기(device) 부품 src 가 'pixabay:photo:design portfolio layout' 인 채 렌더로 넘어가
Remotion 이 http://localhost:3000/public/pixabay%3Aphoto%3A… 404 로 검수 스틸과 본 렌더를 모두 멈췄다(스톡 단계는 image
부품만 파일로 바꿨다)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from studio.render import preflight
from studio.stock.providers import StockHub
from studio.stock.research import StockResearcher, stock_refs, strip_stock_images
from test_net_stock import _FlakyProvider

DEVICE = {"type": "device", "kind": "laptop", "w": 46, "x": 50, "y": 54,
          "src": "pixabay:photo:design portfolio layout", "rows": ["리서치", "스케치"], "title": "포트폴리오"}


def _public(tmp_path: Path) -> Path:
    pub = tmp_path / "public_src"
    (pub / "broll").mkdir(parents=True)
    (pub / "images").mkdir()
    (pub / "fx").mkdir()
    Image.new("RGB", (32, 18), (200, 180, 160)).save(pub / "broll" / "pip1.full.jpg")
    Image.new("RGB", (32, 18), (90, 90, 90)).save(pub / "images" / "own.jpg")
    (pub / "broll" / "piv10824.mp4").write_bytes(b"\x00" * 64)
    (pub / "fx" / "grain0.png").write_bytes(b"")                                  # 0바이트
    (pub / "images" / "html.jpg").write_text("<html>403 Forbidden</html>")       # 오류 페이지를 .jpg 로 받은 것
    return pub


def _props() -> dict:
    return {
        "clips": [{"src": "media/proxy.mp4", "srcStart": 0, "start": 0, "dur": 5}],
        "voice": None, "bgm": None, "sfx": [], "grainFrames": ["fx/grain0.png"], "paperTexture": "fx/paper.jpg",
        "graphics": [
            {"template": "motion", "start": 172.8, "data": {"image": "", "spec": {"elements": [
                {"type": "text", "text": "결과 · 마감"}, dict(DEVICE),
                {"type": "image", "src": "pixabay:photo:white coffee cup", "w": 30, "h": 30},
                {"type": "image", "src": "broll/pip1.full.jpg", "w": 30, "h": 30}]}}},
            # 스톡 그래픽의 image 칸에는 검색어가 남아 있다(사진 템플릿만 읽는 칸)
            {"template": "broll", "start": 13.7,
             "data": {"src": "broll/piv10824.mp4", "image": "product design students sketching foam model studio"}},
            {"template": "broll", "start": 20.0, "data": {"src": "broll/missing.jpg", "cut": "broll/missing.cut.png"}},
            {"template": "photo", "start": 34.8, "data": {"image": "images/html.jpg"}},
            {"template": "photo", "start": 40.0, "data": {"image": "images/own.jpg", "cut": "images/own.cut.png"}},
            {"template": "evidence", "start": 6.6, "data": {"title": "출처", "assets": [
                {"src": "images/cap_missing.jpg", "kind": "document", "w": 10, "h": 10}]}},
            {"template": "evidence", "start": 50.0, "data": {"assets": [{"src": "images/gone.jpg", "kind": "photo"}]}},
            {"template": "card", "start": 60.0, "data": {"card": {
                "html": '<div class="a"><img src="images/own.jpg"><img src="images/nope.png" width="20"></div>'}}},
        ],
    }


def test_fix_props_removes_only_what_points_at_missing_files(tmp_path):
    pub = _public(tmp_path)
    proxy = tmp_path / "media" / "proxy.mp4"
    proxy.parent.mkdir()
    proxy.write_bytes(b"\x00" * 64)
    props = _props()
    notes, fatal = preflight.fix_props(props, preflight.MediaCheck(pub, {"media/proxy.mp4": proxy}))
    assert fatal == []                                    # 화자 영상은 링크(프록시)로 있다
    g = {x["start"]: x for x in props["graphics"]}
    els = g[172.8]["data"]["spec"]["elements"]
    dev = next(e for e in els if e["type"] == "device")
    assert "src" not in dev and dev["rows"] == ["리서치", "스케치"]      # 기기는 그림 없이(행으로) 남는다
    assert [e.get("src") for e in els if e["type"] == "image"] == ["broll/pip1.full.jpg"]   # 못 구한 그림 부품만 빠짐
    assert g[13.7]["data"]["image"] == "" and g[13.7]["data"]["src"] == "broll/piv10824.mp4"
    assert 20.0 not in g and 34.8 not in g                # 스톡·사진은 그 그림 없이는 안 되므로 그래픽째
    assert "cut" not in g[40.0]["data"]                   # 오린 PNG 가 없으면 원본 사진으로
    assert g[6.6]["data"]["assets"] == []                 # 제목이 있으면 자료 카드로 남는다
    assert 50.0 not in g                                  # 그림도 글도 없는 자료 판은 뺀다
    assert g[60.0]["data"]["card"]["html"] == '<div class="a"><img src="images/own.jpg"></div>'
    assert props["grainFrames"] == [] and props["paperTexture"] == ""
    assert any("기기 화면" in n and "pixabay:photo:design portfolio layout" in n for n in notes)
    assert "외" in preflight.summary(notes, limit=2)


def test_missing_speaker_video_is_fatal(tmp_path):
    pub = _public(tmp_path)
    _, fatal = preflight.fix_props(_props(), preflight.MediaCheck(pub, {}))
    assert fatal and "화자 영상 media/proxy.mp4" in fatal[0]


def test_run_render_rewrites_props_before_remotion_sees_them(tmp_path, monkeypatch):
    from studio.render import remotion
    pub = _public(tmp_path)
    proxy = tmp_path / "proxy.mp4"
    proxy.write_bytes(b"\x00" * 64)
    props_p = tmp_path / "props_long.json"
    props_p.write_text(json.dumps(_props(), ensure_ascii=False), encoding="utf-8")
    thumb_p = tmp_path / "props_thumb_1.json"
    thumb_p.write_text(json.dumps({"image": "images/thumb_frame_1.jpg", "text": "x"}), encoding="utf-8")
    seen: dict = {}

    def fake_run(args, *, cwd=None, env=None, on_line=None, cancel=None, stdin_data=None):
        seen["job"] = json.loads(Path(args[-1]).read_text(encoding="utf-8"))
        seen["props"] = json.loads(props_p.read_text(encoding="utf-8"))
        return 0, ""
    monkeypatch.setattr(remotion, "run_process", fake_run)
    monkeypatch.setattr(remotion, "ensure_renderer_installed", lambda: None)
    logs: list[str] = []
    job = remotion.RenderJob(public_dir=pub, bundle_dir=tmp_path / "bundle", links=[(proxy, "media/proxy.mp4")],
                             items=[remotion.RenderItem("video", "LongForm", props_p, tmp_path / "long.mp4"),
                                    remotion.RenderItem("frames", "LongForm", props_p, tmp_path / "qa"),
                                    remotion.RenderItem("still", "Thumbnail", thumb_p, tmp_path / "썸네일1.jpg")])
    remotion.run_render(job, tmp_path / "job.json", node="node", log=logs.append)
    assert "pixabay:" not in json.dumps(seen["props"])          # 렌더러가 받는 props 에 해석 안 된 참조가 없다
    assert [r["composition"] for r in seen["job"]["renders"]] == ["LongForm", "LongForm"]   # 그림 없는 썸네일만 건너뜀
    assert sum("🛫 렌더 전 자산 확인" in m for m in logs) == 1        # 같은 props 는 한 번만 잰다
    assert job.fixed == [props_p]                                # 파이프라인이 고친 props 를 다시 읽는다
    assert any("썸네일" in m and "건너뜀" in m for m in logs)

    (tmp_path / "proxy.mp4").unlink()                            # 화자 영상이 없으면 Remotion 을 부르기 전에 멈춘다
    seen.clear()
    job.items = [remotion.RenderItem("video", "LongForm", props_p, tmp_path / "long.mp4")]
    with pytest.raises(remotion.RenderError, match="렌더할 수 없습니다 — 화자 영상"):
        remotion.run_render(job, tmp_path / "job.json", node="node")
    assert not seen


def test_device_screen_pixabay_image_is_downloaded(tmp_path, monkeypatch):
    """스톡 단계는 image 뿐 아니라 device 화면의 'pixabay:' 도 파일로 바꾼다(화면이라 색을 지키는 graded 톤).
    후보는 비전으로 고른다(2026-10-04 — 검색 1위를 그냥 쓰지 않는다)."""
    monkeypatch.setattr(StockResearcher, "_thumb", lambda self, c: None)
    res = StockResearcher(StockHub([_FlakyProvider()]), ff=None, work=tmp_path / "work", public=tmp_path / "public",
                          pick=lambda text, sheets: [{"request": 1, "candidate": 1, "reason": "포트폴리오 화면"}])
    spec = {"elements": [dict(DEVICE), {"type": "text", "text": "포트폴리오"}]}
    lists = [[{"template": "motion", "spec": spec}]]
    assert stock_refs(spec) and res.resolve_images(lists) == 1
    dev = spec["elements"][0]
    assert dev["src"].startswith("broll/img_") and (tmp_path / "public" / dev["src"]).exists()
    assert not stock_refs(spec)


def test_strip_keeps_device_but_drops_its_unresolved_picture():
    spec = {"elements": [dict(DEVICE), {"type": "image", "src": "pixabay:vector:cup"}, {"type": "text", "text": "a"}]}
    assert strip_stock_images([[{"template": "motion", "spec": spec}]]) == 2
    assert [e["type"] for e in spec["elements"]] == ["device", "text"] and "src" not in spec["elements"][0]


def test_scenes_revised_after_stock_get_their_pictures_resolved_or_dropped(tmp_path):
    """검수(revise_scene)가 스톡 단계 뒤에 새로 넣은 'pixabay:' 도 렌더 전에 정리된다 — 스톡이 꺼져 있으면 뺀다."""
    from studio.pipeline import Pipeline
    p = Pipeline.__new__(Pipeline)
    p._stock_enabled = lambda: False
    g = {"template": "motion", "spec": {"elements": [dict(DEVICE), {"type": "image", "src": "pixabay:photo:desk"}]}}
    Pipeline._resolve_scene_images(p, [g, {"template": "keyword"}])
    assert not stock_refs(g["spec"]) and [e["type"] for e in g["spec"]["elements"]] == ["device"]


def test_renderer_never_loads_unresolved_scene_pictures():
    tsx = (Path(__file__).resolve().parents[1] / "renderer" / "src" / "components" / "motion" / "MotionScene.tsx")
    src = tsx.read_text(encoding="utf-8")
    assert "localSrc(el.src) ?" in src and "!localSrc(el.src)" in src     # 기기 화면·그림 둘 다
