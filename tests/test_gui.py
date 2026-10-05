"""오토파일럿 창 스모크 테스트(오프스크린): 세 입력 → JobSpec, 진행·결과 화면 전환, 파일 끌어다 놓기 분류."""
from __future__ import annotations

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


def test_three_inputs_make_a_spec(app, tmp_path):
    from studio.gui.app import MainWindow
    w = MainWindow()
    assert w.pages.count() == 3 and w.pages.currentIndex() == 0
    assert not w.go.isEnabled()                      # 아직 아무것도 없음
    video = tmp_path / "원본.mp4"
    video.write_bytes(b"\0")
    script = tmp_path / "대본.txt"
    script.write_text("안녕하세요. 오늘은 게슈탈트 이야기입니다.", encoding="utf-8")
    w.topic.setPlainText("게슈탈트 원리 — 입문자용")
    w._on_files([str(video), str(script)])           # 탐색기에서 두 파일을 한꺼번에 끌어다 놓은 경우
    assert w.video.path == str(video)
    assert "게슈탈트" in w.script.toPlainText()
    assert w.go.isEnabled()
    spec = w._spec()
    assert (spec.video, spec.topic) == (str(video), "게슈탈트 원리 — 입문자용")
    assert spec.shorts_count == 2 and spec.make_long            # 롱폼 1 + 숏폼 2 고정
    assert spec.working_title() == "게슈탈트 원리 — 입문자용"
    # 원본 여러 개(다른 각도·나눠 찍은 것): 끌어다 놓으면 더해지고, 같은 파일은 한 번만
    cam_b = tmp_path / "원본_B.mp4"
    cam_b.write_bytes(b"\0")
    w._on_files([str(cam_b), str(video)])
    assert w.video.paths == [str(video), str(cam_b)] and "외 1개" in w.video.name.text()
    spec = w._spec()
    assert spec.video == str(video) and spec.videos == [str(cam_b)] and spec.sources() == [str(video), str(cam_b)]
    w.video.set_paths([])
    assert not w.go.isEnabled()


def test_result_page_lists_outputs(app, tmp_path):
    from studio.gui.app import MainWindow
    out = tmp_path / "output"
    (out / "부가자료").mkdir(parents=True)
    long_ = out / "1_롱폼_x.mp4"
    long_.write_bytes(b"\0")
    w = MainWindow()
    w._show_results({"title": "게슈탈트", "output": str(out), "long": str(long_), "shorts": [],
                     "upload_info": ""}, elapsed=65)
    assert w.pages.currentIndex() == 2 and "게슈탈트" in w.r_title.text()
    w._on_progress("asr", 0.5, 0.3)
    assert w.bar.value() == 300
    w.close()


def test_docx_and_hwpx_script_reading(tmp_path):
    import zipfile
    from studio.text.docfile import read_text_file
    d = tmp_path / "a.docx"
    with zipfile.ZipFile(d, "w") as z:
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   "<w:body><w:p><w:r><w:t>첫 문장.</w:t></w:r></w:p><w:p><w:r><w:t>둘째</w:t></w:r>"
                   "<w:r><w:t> 문장.</w:t></w:r></w:p></w:body></w:document>")
    assert read_text_file(d) == "첫 문장.\n둘째 문장."
    c = tmp_path / "b.txt"
    c.write_bytes("한글 대본".encode("cp949"))
    assert read_text_file(c) == "한글 대본"


def test_progress_page_live_preview_and_eta(app, tmp_path):
    import time as _time

    from PIL import Image
    from studio.eta import Eta
    from studio.gui.app import MainWindow
    img = tmp_path / "0_120.jpg"
    Image.new("RGB", (320, 180), (200, 40, 20)).save(img)
    w = MainWindow()
    w.pages.setCurrentIndex(1)
    assert w.peek_box.isHidden()
    w._on_preview(str(tmp_path / "없음.jpg"), "무시")           # 없는 파일은 건너뜀
    assert w.peek_box.isHidden()
    w._on_preview(str(img), "롱폼 렌더링 · 00:04 / 06:00")
    assert not w.peek_box.isHidden() and w.peek_cap.text() == "롱폼 렌더링 · 00:04 / 06:00"

    # 남은 시간: 작업자의 Eta 를 1초마다 읽어 보수적으로 표시하고, 막대는 뒤로 가지 않음
    class FakeWorker:
        eta = Eta(None)
    w.worker = FakeWorker()
    FakeWorker.eta.begin()
    FakeWorker.eta.plan(["render"], {}, {"m": 1, "k": 1, "out_s": 60, "frames_k": 1.8, "thumbs": False})
    from studio.eta import EtaDisplay
    w.eta_view = EtaDisplay()
    w.t_start = w._t_tick = _time.time()
    w._tick()
    assert "남은 시간 약" in w.p_sub.text()
    w._on_progress("render", 0.5, 0.3)
    w._on_progress("render", 0.5, 0.2)
    assert w.bar.value() == 300
    w.worker = None
    w.close()


def test_materials_folder_sets_images_dir(app, tmp_path):
    """P0-9: ④ 자료 폴더(선택) → JobSpec.images_dir. 폴더 안 이미지 수를 보여 주고, 비어 있으면 예전과 똑같다."""
    from PIL import Image

    from studio.gui.app import MainWindow
    w = MainWindow()
    assert w._spec().images_dir == "" and not w.materials_clear.isEnabled()
    folder = tmp_path / "자료"
    folder.mkdir()
    for name in ("디터 람스.jpg", "과제 스케치.png"):
        Image.new("RGB", (40, 30), (200, 200, 200)).save(folder / name)
    w._on_files([str(folder)])                       # 폴더를 끌어다 놓으면 ④
    assert w._spec().images_dir == str(folder)
    assert "이미지 2장" in w.materials_label.text()
    w._set_materials("")
    assert w._spec().images_dir == ""


def test_result_page_flags_needs_review(app, tmp_path):
    """게이트 E 가 검토 필요를 붙이면 결과 화면 제목·안내에 그대로 보인다."""
    from studio.gui.app import MainWindow
    w = MainWindow()
    w._show_results({"title": "질문이 먼저다", "output": str(tmp_path), "needs_review": True})
    assert w.r_title.text().startswith("⚠ 검토 필요") and "⚠검토필요.md" in w.r_sub.text()
    w._show_results({"title": "질문이 먼저다", "output": str(tmp_path)})
    assert w.r_title.text().startswith("완성!")


def test_scene_rating_dialog_records_taste(app, tmp_path, monkeypatch):
    """🎯 결과 화면 '장면 평가': rate.json(완성 영상의 장면 정지 화면) → 👍/👎 + 한 줄 → user/taste 기억."""
    from PIL import Image

    from studio.agents import taste
    from studio.gui.app import MainWindow
    from studio.gui.rate_dialog import RateDialog
    from studio.util import write_json
    monkeypatch.setattr(taste, "TASTE_DIR", tmp_path / "taste")
    job = tmp_path / "job1"
    (job / "work" / "rate").mkdir(parents=True)
    (job / "output").mkdir()
    rows = []
    for gid, tpl in (("g1", "card"), ("g2", "keyword"), ("g3", "motion")):
        f = job / "work" / "rate" / f"{gid}.jpg"
        Image.new("RGB", (480, 270), (200, 90, 40)).save(f)
        rows.append({"gid": gid, "template": tpl, "kind": tpl, "title": f"장면 {gid}", "t": 12.5, "still": str(f)})
    write_json(job / "work" / "rate.json", rows)
    w = MainWindow()
    w._show_results({"title": "t", "long": "", "shorts": [], "output": str(job / "output")})
    assert w.r_rate.isEnabled()                                  # 결과에 rate 가 없어도 작업 폴더에서 찾는다
    d = RateDialog(str(job / "work" / "rate.json"), "job1")
    assert len(d.rows) == 3
    d.rows[0].up.setChecked(True)
    d.rows[0].note.setText("큰 숫자 하나가 시원하다")
    d.rows[1].up.setChecked(True)
    d.rows[1].down.setChecked(True)                              # 둘 중 하나만
    d.rows[1].note.setText("제목+목록이라 PPT 같다")
    es = d.entries()
    assert [(e["gid"], e["verdict"]) for e in es] == [("g1", "up"), ("g2", "down")]
    monkeypatch.setattr("studio.gui.rate_dialog.QMessageBox.information", lambda *a, **k: None)
    d._save()
    assert (tmp_path / "taste" / "liked" / "job1_g1.jpg").exists()
    assert "PPT 같다" in taste.notes_block()


def test_reference_dialog_lists_refs_and_queues_drops(app, tmp_path, monkeypatch):
    """🎯 레퍼런스 분석 창: 저장된 분석이 카드로, 끌어다 놓은 폴더·파일은 사진·영상만 대기열에(AI 호출 없음)."""
    from PIL import Image

    from studio.agents import reference, taste
    from studio.gui.reference_dialog import ReferenceDialog
    from studio.util import write_json
    monkeypatch.setattr(taste, "TASTE_DIR", tmp_path / "taste")
    d = reference.ref_dir()
    Image.new("RGB", (640, 360), (30, 30, 30)).save(d / "a_sheet.jpg")
    write_json(d / "a.json", {"slug": "a", "name": "릴스A", "kind": "video", "analyzed_at": "2026-10-05 01:00", "sheet": "a_sheet.jpg",
                              "measure": {"duration": 30, "shots": 12, "shot_median_s": 2.1, "cuts_per_min": 22, "motion": 0.03,
                                          "dark": True, "edge_ratio": 0.05, "palette": [{"hex": "#111111", "share": 0.5}]},
                              "analysis": {"summary": "컷이 말에 맞는다", "rules": {"motion": "마스크 상승"}, "techniques": [{"name": "어절 마스크"}]}})
    write_json(d / "b.json", {"slug": "b", "name": "사진B", "kind": "image", "analyzed_at": "2026-10-05 00:00", "sheet": "",
                              "measure": {"width": 1200, "height": 675, "dark": False, "contrast": 0.4, "saturation": 0.2, "edge_ratio": 0.01,
                                          "palette": []}, "analysis": None, "error": "limit"})
    w = ReferenceDialog()
    assert [r["name"] for r in w.rows] == ["릴스A", "사진B"] and w.rows[0]["analyzed"] and not w.rows[1]["analyzed"]
    assert not w.go.isEnabled()
    (tmp_path / "x.png").write_bytes(b"\0")
    (tmp_path / "y.mov").write_bytes(b"\0")
    (tmp_path / "z.txt").write_bytes(b"\0")
    w.add_paths([str(tmp_path)])                      # 폴더를 놓으면 안의 사진·영상만
    assert [Path(p).name for p in w.queue] == ["x.png", "y.mov"] and w.list.count() == 2 and w.go.isEnabled()
    w.add_paths([str(tmp_path / "x.png")])            # 같은 파일은 한 번
    assert len(w.queue) == 2
    w._clear_queue()
    assert not w.queue and not w.go.isEnabled()
    from studio.gui.app import wait_bg
    wait_bg()                                          # AI 연결 확인 스레드가 끝난 뒤 창을 지운다


def test_main_window_has_reference_button_and_bench_mode(app, tmp_path):
    """메인 창: '🎯 레퍼런스' 버튼 · 🧪 디자인 벤치는 until='design' 으로 Worker 를 띄우고 끝나면 장면 시트 안내."""
    from studio.gui.app import MainWindow, Worker
    import inspect
    w = MainWindow()
    assert any(b.text() == "🎯 레퍼런스" for b in w.findChildren(type(w.ai_chip)))
    assert "until" in inspect.signature(Worker.__init__).parameters and "until" in inspect.signature(w._start).parameters
    w._until = "design"
    shown = []
    w._show_bench = lambda res: shown.append(res)     # 메시지 상자 대신
    w._on_done({"output": str(tmp_path / "out"), "job_dir": str(tmp_path), "critic": {"scenes": 3, "rejected": 1, "fixed": 1, "replaced": 0}})
    assert shown and shown[0]["critic"]["scenes"] == 3
