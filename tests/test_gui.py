"""편집 툴 화면 스모크 테스트(오프스크린): 창 구성, 작업 → JobSpec 왕복, 타임라인 데이터."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    os.environ["CHOI_STUDIO_USER_DIR"] = str(tmp_path_factory.mktemp("user"))
    from PySide6.QtWidgets import QApplication
    a = QApplication.instance() or QApplication(sys.argv)
    from studio.gui import theme
    theme.apply(a, "#F93107")
    return a


def test_timeline_data_from_props():
    from studio.gui.timeline import TimelineData, tc
    d = TimelineData.from_dict({
        "duration": 30, "fps": 30,
        "clips": [{"start": 0, "dur": 10, "srcStart": 2}, {"start": 10, "dur": 12, "srcStart": 20}],
        "graphics": [{"template": "motion", "layout": "fullscreen", "start": 3, "end": 9, "data": {"title": "근접성"}},
                     {"template": "broll", "layout": "split", "start": 12, "end": 15,
                      "data": {"title": "스케치", "credit": "A / Pixabay"}},
                     {"template": "list", "layout": "split", "start": 16, "end": 22, "data": {"title": "조건"}}],
        "chapters": [{"start": 0, "title": "들어가며", "number": "01"}],
        "captions": [{"start": 1, "end": 2, "lines": [[{"text": "안녕"}, {"text": "하세요"}]]},
                     {"start": 3, "end": 4, "text": "두 번째"}]}, source="render")
    tracks = [c.track for c in d.clips]
    assert tracks.count("v1") == 2 and tracks.count("a1") == 2 and tracks.count("cc") == 2
    assert [c.track for c in d.clips if c.label.startswith(("모션", "스톡"))] == ["v3", "v3"]
    assert any("▣ A / Pixabay" in c.tip for c in d.clips)
    assert d.chapters == [(0.0, "01 들어가며")] and tc(61.5) == "00:01:01:15"


def test_main_window_builds_and_roundtrips_spec(app, tmp_path):
    from studio.gui.app import MainWindow
    from studio.pipeline import JobSpec
    w = MainWindow()
    names = {d.objectName() for d in w.findChildren(type(w.d_script))}
    assert {"dock_script", "dock_project", "dock_inspector", "dock_timeline", "dock_team", "dock_console",
            "dock_exports"} <= names
    spec = JobSpec(video=str(tmp_path / "a.mp4"), title="제목", episode="03", script="대본", notes="메모",
                   direction="모션 많이", caption_preset="glass", short_caption_preset="clean", qa_rounds=2,
                   studio_mode=False, fetch_stock=False, shorts_count=3, pace="fast", out_height=1440)
    w._apply_spec(spec)
    back = w._spec()
    for k in ("title", "episode", "script", "notes", "direction", "caption_preset", "short_caption_preset",
              "qa_rounds", "studio_mode", "fetch_stock", "shorts_count", "pace", "out_height"):
        assert getattr(back, k) == getattr(spec, k), k
    # 작업 폴더의 타임라인 불러오기
    job = tmp_path / "job"
    (job / "work").mkdir(parents=True)
    (job / "work" / "timeline.json").write_text(json.dumps({"duration": 12, "fps": 30, "clips": [
        {"start": 0, "dur": 12, "srcStart": 0}], "graphics": [], "chapters": [], "captions": []}), encoding="utf-8")
    w._set_job(job)
    assert w.timeline.data.duration == 12 and w.timeline.data.source == "plan"
    w.team.on_log("동시 작업: ✂️ 편집 감독 · 🎨 모션 디자이너")
    w.team.on_log("🎨 모션 디자이너: 완료 3s")
    assert "완료" in w.team.rows["🎨"][0].text() and "작업 중" in w.team.rows["✂️"][0].text()
    for i in range(3):
        w._workspace(i)
    w.close()
