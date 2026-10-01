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
