"""🎯 레퍼런스 분석 창 — 사진·영상을 끌어다 놓으면 재고(측정) Claude 가 보고(비전) 디자인 규칙으로 옮겨 모든 디자이너·심사가 매번 읽는다.

채널 주인 2026-10-04: "깃 못 다룬다. 디자인 설정툴처럼 UI 대충 만들어서 자료 드래그드롭 해 넣으면 알아서 벤치마킹하고 디자인 분석하는 것".
메인 창의 '🎯 레퍼런스' 버튼, 또는 run_reference.bat(독립 실행)으로 연다. 분석은 백그라운드 스레드에서(창이 멈추지 않게), 결과는
user/taste/refs/ 에 쌓이고(저장소 밖) 다음 작업부터 자동으로 들어간다(studio/agents/reference.py).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..agents import reference
from ..settings import Settings
from ..util import CancelToken, Cancelled

FILTER = "사진·영상 (*.jpg *.jpeg *.png *.webp *.bmp *.mp4 *.mov *.m4v *.webm *.mkv *.avi)"


class _Worker(QObject):
    log = Signal(str)
    one = Signal(dict)
    done = Signal(int, int)       # 성공 수 · 실패 수
    failed = Signal(str)

    def __init__(self, paths: list[str], note: str, settings: Settings, cancel: CancelToken):
        super().__init__()
        self.paths, self.note, self.settings, self.cancel = paths, note, settings, cancel

    def run(self) -> None:
        ok = bad = 0
        try:
            client, why = reference.make_client(self.settings, log=self.log.emit)
            self.log.emit(f"AI 연결: {why}" if client is not None else f"AI 없음({why}) — 측정값만 저장합니다(규칙은 AI 가 있어야 나옵니다)")
            for p in self.paths:
                self.cancel.check()
                try:
                    rec = reference.analyze_file(p, client=client, note=self.note, log=self.log.emit, cancel=self.cancel)
                    ok += 1
                    self.one.emit(rec)
                except Cancelled:
                    raise
                except Exception as e:  # noqa: BLE001 - 한 파일의 실패가 나머지를 막지 않는다
                    bad += 1
                    self.log.emit(f"⚠ {Path(p).name}: {e}")
            self.done.emit(ok, bad)
        except Cancelled:
            self.failed.emit("취소했습니다.")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"{e}\n{traceback.format_exc()[-1500:]}")


class _DropZone(QFrame):
    dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setObjectName("panel")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(120)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 18, 18, 18)
        t = QLabel("여기에 레퍼런스 사진·영상(릴스·설명 영상 캡처·스크린샷)을 끌어다 놓으세요")
        t.setAlignment(Qt.AlignCenter)
        t.setWordWrap(True)
        s = QLabel("폴더를 놓으면 안의 사진·영상을 모두 넣습니다 · 눌러서 고르기도 됩니다")
        s.setObjectName("stepHint")
        s.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        v.addWidget(s)

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        ps = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if ps:
            self.dropped.emit(ps)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            ps, _ = QFileDialog.getOpenFileNames(self, "레퍼런스 사진·영상 선택", "", FILTER)
            if ps:
                self.dropped.emit(ps)


class _RefCard(QFrame):
    deleted = Signal(str)

    def __init__(self, row: dict):
        super().__init__()
        self.setObjectName("panel")
        self.row = row
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 10, 10, 10)
        pic = QLabel()
        pm = QPixmap(row.get("sheet") or "")
        if not pm.isNull():
            pic.setPixmap(pm.scaledToWidth(300, Qt.SmoothTransformation))
            pic.setCursor(Qt.PointingHandCursor)
            pic.mousePressEvent = lambda _e, p=row.get("sheet"): QDesktopServices.openUrl(QUrl.fromLocalFile(p))
        h.addWidget(pic)
        v = QVBoxLayout()
        kind = "영상" if row.get("kind") == "video" else "사진"
        title = QLabel(f"<b>{row.get('name') or ''}</b> · {kind} · {row.get('at') or ''}" + (" · 📦 저장소 공유" if row.get("shared") else ""))
        title.setTextFormat(Qt.RichText)
        v.addWidget(title)
        meas = QLabel(row.get("measured") or "")
        meas.setObjectName("stepHint")
        meas.setWordWrap(True)
        v.addWidget(meas)
        if row.get("analyzed"):
            body = QLabel(row.get("summary") or "")
            body.setWordWrap(True)
            v.addWidget(body)
            for lab, key in (("움직임", "motion"), ("글자", "type"), ("색", "color")):
                if row.get(key):
                    q = QLabel(f"{lab}: {row[key]}")
                    q.setObjectName("stepHint")
                    q.setWordWrap(True)
                    v.addWidget(q)
            if row.get("techniques"):
                q = QLabel("기법: " + " · ".join(t for t in row["techniques"][:6] if t))
                q.setWordWrap(True)
                v.addWidget(q)
        else:
            warn = QLabel("AI 분석 없음 — 측정값만 저장(" + (row.get("error") or "AI 연결이 없었음") + "). AI 가 연결된 뒤 다시 넣으면 규칙이 나옵니다.")
            warn.setObjectName("stepHint")
            warn.setWordWrap(True)
            v.addWidget(warn)
        v.addStretch(1)
        h.addLayout(v, 1)
        rm = QPushButton("삭제")
        rm.setObjectName("ghost")
        rm.setToolTip("이 레퍼런스의 규칙·시트를 지웁니다(원본 파일은 그대로)")
        rm.clicked.connect(lambda: self.deleted.emit(str(row.get("slug") or "")))
        h.addWidget(rm, 0, Qt.AlignTop)


class ReferenceDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("🎯 레퍼런스 분석 — 디자인 벤치마킹")
        self.resize(980, 760)
        self.settings = Settings.load()
        self.thread: Optional[QThread] = None
        self.worker: Optional[_Worker] = None
        self.cancel: Optional[CancelToken] = None
        self.queue: list[str] = []
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(10)
        head = QLabel("좋다고 느낀 디자인을 넣으면, 프로그램이 재고(컷 박자·색·밝기·선 밀도) Claude 가 보고(비전) **규칙과 기법**으로 옮깁니다. "
                      "다음 작업부터 스타일 프레임·모션 디자이너·시그니처 장면·심사가 매번 이 규칙과 컷 시트를 봅니다. "
                      "글·로고·사진은 가져오지 않고 결·움직임·배치의 문법만 가져옵니다.")
        head.setWordWrap(True)
        head.setTextFormat(Qt.MarkdownText)
        v.addWidget(head)
        self.zone = _DropZone()
        self.zone.dropped.connect(self.add_paths)
        v.addWidget(self.zone)
        row = QHBoxLayout()
        self.note = QLineEdit()
        self.note.setPlaceholderText("메모(선택) — 무엇이 좋은지 한 줄. 예: 글자가 적고 큰 숫자 하나가 시원하다 / 컷 박자가 말과 맞는다")
        row.addWidget(self.note, 1)
        v.addLayout(row)
        self.list = QListWidget()
        self.list.setMaximumHeight(110)
        v.addWidget(self.list)
        bar = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("stepHint")
        bar.addWidget(self.status, 1)
        self.clear_btn = QPushButton("목록 비우기")
        self.clear_btn.setObjectName("ghost")
        self.clear_btn.clicked.connect(self._clear_queue)
        bar.addWidget(self.clear_btn)
        self.open_btn = QPushButton("저장 폴더 열기")
        self.open_btn.setObjectName("ghost")
        self.open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(reference.ref_dir()))))
        bar.addWidget(self.open_btn)
        self.export_btn = QPushButton("zip 으로 내보내기")
        self.export_btn.setObjectName("ghost")
        self.export_btn.setToolTip("이 PC 의 분석 전부를 zip 하나로 — 이 파일을 넘기면 저장소(깃허브)에 올려 모든 설치본이 같은 규칙을 씁니다")
        self.export_btn.clicked.connect(self._export)
        bar.addWidget(self.export_btn)
        self.go = QPushButton("분석 시작  ▶")
        self.go.setObjectName("hero")
        self.go.clicked.connect(self._start)
        bar.addWidget(self.go)
        v.addLayout(bar)
        self.logview = QPlainTextEdit()
        self.logview.setReadOnly(True)
        self.logview.setMaximumHeight(120)
        self.logview.setPlaceholderText("분석 기록")
        v.addWidget(self.logview)
        lab = QLabel("분석한 레퍼런스(최근 순) — 디자이너와 심사가 매번 읽는 것")
        lab.setObjectName("panelTitle")
        v.addWidget(lab)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.cards_host = QWidget()
        self.cards = QVBoxLayout(self.cards_host)
        self.cards.setContentsMargins(0, 0, 0, 0)
        self.cards.setSpacing(8)
        self.cards.addStretch(1)
        self.scroll.setWidget(self.cards_host)
        v.addWidget(self.scroll, 1)
        self._ai_line()
        self.refresh()
        self._update()

    # ------------------------------------------------------------------
    def _ai_line(self) -> None:
        """AI 연결 표시 — claude CLI 를 부르므로 창을 멈추지 않게 백그라운드에서."""
        from .app import ai_status_text, run_bg
        self.status.setText("AI 연결 확인 중…")
        run_bg(self, lambda: ai_status_text(self.settings), self._on_ai)

    def _on_ai(self, res) -> None:
        if isinstance(res, Exception) or not isinstance(res, tuple):
            text, ok = "AI 연결 확인 실패", False
        else:
            text, ok = res
        self.status.setText(text + ("" if ok else " — 규칙 추출은 AI 가 있어야 합니다(측정값만 저장됨)"))

    def add_paths(self, paths: list[str]) -> None:
        for p in reference.expand_paths(paths):
            if p not in self.queue:
                self.queue.append(p)
                self.list.addItem(QListWidgetItem(("🎞 " if reference.kind_of(p) == "video" else "🖼 ") + Path(p).name))
        self._update()

    def _clear_queue(self) -> None:
        self.queue.clear()
        self.list.clear()
        self._update()

    def _update(self) -> None:
        busy = self.thread is not None
        self.go.setEnabled(bool(self.queue) and not busy)
        self.go.setText("분석 중…" if busy else f"분석 시작  ▶" + (f"  ({len(self.queue)}개)" if self.queue else ""))
        self.clear_btn.setEnabled(bool(self.queue) and not busy)

    def refresh(self) -> None:
        while self.cards.count() > 1:
            it = self.cards.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.rows = reference.summary_rows()
        for i, r in enumerate(self.rows):
            card = _RefCard(r)
            card.deleted.connect(self._delete)
            self.cards.insertWidget(i, card)

    def _export(self) -> None:
        try:
            out = reference.export_zip()
        except (FileNotFoundError, OSError) as e:
            QMessageBox.information(self, "내보내기", str(e))
            return
        QMessageBox.information(self, "내보냈습니다", f"{out}\n\n이 zip 을 넘기면 저장소에 올립니다(모든 설치본의 디자이너가 같은 규칙을 봅니다).")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(out.parent)))

    def _delete(self, slug: str) -> None:
        if not slug:
            return
        if QMessageBox.question(self, "삭제", "이 레퍼런스의 분석(규칙·시트)을 지울까요? 원본 파일은 그대로 둡니다.") == QMessageBox.Yes:
            reference.delete_ref(slug)
            self.refresh()

    # ------------------------------------------------------------------
    def _start(self) -> None:
        if self.thread is not None or not self.queue:
            return
        self.settings = Settings.load()
        self.cancel = CancelToken()
        self.logview.clear()
        self.thread = QThread(self)
        self.worker = _Worker(list(self.queue), self.note.text(), self.settings, self.cancel)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.logview.appendPlainText)
        self.worker.one.connect(lambda _rec: self.refresh())
        self.worker.done.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.worker.done.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._thread_done)
        self.thread.start()
        self._update()

    def _thread_done(self) -> None:
        self.thread = None
        self.worker = None
        self._update()

    def _done(self, ok: int, bad: int) -> None:
        self._clear_queue()
        self.refresh()
        self.logview.appendPlainText(f"끝: {ok}개 분석" + (f" · {bad}개 실패" if bad else "") +
                                     " — 다음 작업부터 모든 디자이너·심사가 이 규칙과 시트를 봅니다.")

    def _failed(self, msg: str) -> None:
        self.logview.appendPlainText("⚠ " + msg)
        self.refresh()

    def closeEvent(self, e):  # noqa: N802
        if self.thread is not None:
            if QMessageBox.question(self, "분석 중", "분석을 멈추고 닫을까요? 끝난 파일은 저장되어 있습니다.") != QMessageBox.Yes:
                e.ignore()
                return
            if self.cancel:
                self.cancel.cancel()
            self.thread.quit()
            self.thread.wait(3000)
        super().closeEvent(e)


def run_reference_tool() -> int:
    """독립 실행(run_reference.bat · python -m studio reference)."""
    from ..paths import ensure_user_dirs
    from . import theme
    ensure_user_dirs()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Choi Studio — 레퍼런스 분석")
    theme.apply(app, Settings.load().brand.accent)
    d = ReferenceDialog()
    d.show()
    return app.exec()
