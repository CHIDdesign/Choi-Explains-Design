"""공용 위젯: 끌어다 놓는 미디어 슬롯, 접히는 섹션, 폼 줄."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)


class DropLine(QLineEdit):
    """파일을 끌어다 놓을 수 있는 경로 입력칸."""

    def __init__(self, placeholder: str = ""):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        urls = e.mimeData().urls()
        if urls:
            self.setText(urls[0].toLocalFile())


class MediaSlot(QFrame):
    """프로젝트 패널의 미디어 카드: 썸네일 + 이름 + 경로, 끌어다 놓기·찾아보기·비우기."""

    changed = Signal(str)

    def __init__(self, icon: str, title: str, hint: str, *, filt: Optional[str] = None, folder: bool = False,
                 required: bool = False):
        super().__init__()
        self.setObjectName("card")
        self.setAcceptDrops(True)
        self.filt, self.folder = filt, folder
        self._path = ""
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 7, 6, 7)
        lay.setSpacing(9)
        self.thumb = QLabel(icon)
        self.thumb.setFixedSize(64, 36)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet("background:#111; border-radius:3px; font-size:16px;")
        lay.addWidget(self.thumb)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.name = QLabel(f"{title}{'  *' if required else ''}")
        self.name.setStyleSheet("font-weight:700;")
        self.sub = QLabel(hint)
        self.sub.setObjectName("hint")
        self.sub.setMinimumWidth(10)
        self.sub.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        col.addWidget(self.name)
        col.addWidget(self.sub)
        lay.addLayout(col, 1)
        self.hint = hint
        b = QToolButton()
        b.setText("…")
        b.setToolTip("찾아보기")
        b.clicked.connect(self._pick)
        x = QToolButton()
        x.setText("✕")
        x.setToolTip("비우기")
        x.clicked.connect(lambda: self.setText(""))
        lay.addWidget(b)
        lay.addWidget(x)

    # QLineEdit 과 같은 사용법
    def text(self) -> str:
        return self._path

    def setText(self, p: str) -> None:  # noqa: N802
        self._path = p or ""
        if self._path:
            self.sub.setText(Path(self._path).name + ("" if Path(self._path).exists() else "  (찾을 수 없음)"))
            self.sub.setToolTip(self._path)
        else:
            self.sub.setText(self.hint)
            self.sub.setToolTip("")
        self.changed.emit(self._path)

    def setThumbnail(self, pix: Optional[QPixmap]) -> None:  # noqa: N802
        if pix and not pix.isNull():
            self.thumb.setPixmap(pix.scaled(64, 36, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))

    def _pick(self) -> None:
        if self.folder:
            p = QFileDialog.getExistingDirectory(self, self.name.text())
        else:
            p, _ = QFileDialog.getOpenFileName(self, self.name.text(), "", self.filt or "")
        if p:
            self.setText(p)

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        urls = e.mimeData().urls()
        if urls:
            self.setText(urls[0].toLocalFile())


class Section(QWidget):
    """접히는 섹션(고급 설정 등)."""

    def __init__(self, title: str, *, expanded: bool = True):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.head = QPushButton()
        self.head.setObjectName("sectionHeader")
        self.head.setCheckable(True)
        self.head.setChecked(expanded)
        self.head.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.title = title
        self.body = QWidget()
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(12, 10, 12, 12)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(8)
        self.grid.setColumnStretch(1, 1)
        v.addWidget(self.head)
        v.addWidget(self.body)
        self.head.toggled.connect(self._toggle)
        self._toggle(expanded)
        self._row = 0

    def _toggle(self, on: bool) -> None:
        self.head.setText(("▾  " if on else "▸  ") + self.title)
        self.body.setVisible(on)

    def row(self, label: str, w: QWidget, tip: str = "") -> QWidget:
        if label:
            lab = QLabel(label)
            lab.setObjectName("fieldLabel")
            if tip:
                lab.setToolTip(tip)
                w.setToolTip(tip)
            self.grid.addWidget(lab, self._row, 0)
            self.grid.addWidget(w, self._row, 1)
        else:
            if tip:
                w.setToolTip(tip)
            self.grid.addWidget(w, self._row, 0, 1, 2)
        self._row += 1
        return w

    def note(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("hint")
        lab.setWordWrap(True)
        self.grid.addWidget(lab, self._row, 0, 1, 2)
        self._row += 1
        return lab


def button(text: str, slot: Callable, *, primary: bool = False, ghost: bool = False, tip: str = "") -> QPushButton:
    b = QPushButton(text)
    if primary:
        b.setObjectName("primary")
    elif ghost:
        b.setObjectName("ghost")
    if tip:
        b.setToolTip(tip)
    b.clicked.connect(slot)
    return b


def hint(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("hint")
    lab.setWordWrap(True)
    return lab
