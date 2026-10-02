"""공용 위젯: 끌어다 놓는 미디어 슬롯, 접히는 섹션, 폼 줄."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)


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
