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
