"""🎯 장면 평가 — 완성 영상의 장면마다 👍/👎 + 한 줄. user/taste 에 쌓여 다음 작업부터 모든 디자이너·심사가 본다
(채널 주인 2026-10-04: "디자인 taste 를 대폭 업그레이드" — 말보다 고른 그림이 취향을 정확히 전한다)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QButtonGroup, QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..agents import taste
from ..util import read_json
from .widgets import hint

KIND_LABEL = {"motion": "모션", "card": "카드", "broll": "스톡", "photo": "자료 사진", "evidence": "자료", "keyword": "키워드",
              "title": "타이틀", "chapter": "챕터", "list": "목록", "definition": "정의", "number": "숫자", "quote": "인용"}


class _Row(QFrame):
    def __init__(self, row: dict, parent=None):
        super().__init__(parent)
        self.row = row
        self.setObjectName("panel")
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 10, 10, 10)
        pic = QLabel()
        pm = QPixmap(str(row.get("still") or ""))
        if not pm.isNull():
            pic.setPixmap(pm.scaledToWidth(320, Qt.SmoothTransformation))
        h.addWidget(pic)
        v = QVBoxLayout()
        kind = KIND_LABEL.get(str(row.get("template") or ""), str(row.get("template") or ""))
        t = float(row.get("t") or 0)
        v.addWidget(QLabel(f"{int(t // 60):02d}:{t % 60:04.1f} · {kind}" + (f" · 「{row['title']}」" if row.get("title") else "")))
        btns = QHBoxLayout()
        self.up, self.down = QPushButton("👍 좋다"), QPushButton("👎 별로")
        self.group = QButtonGroup(self)
        self.group.setExclusive(False)
        for b in (self.up, self.down):
            b.setCheckable(True)
            self.group.addButton(b)
            btns.addWidget(b)
        self.up.toggled.connect(lambda on: on and self.down.setChecked(False))
        self.down.toggled.connect(lambda on: on and self.up.setChecked(False))
        btns.addStretch(1)
        v.addLayout(btns)
        self.note = QLineEdit()
        self.note.setPlaceholderText("한 줄(선택): 무엇이 좋았나 / 무엇이 싸 보였나 — 예) 큰 숫자 하나가 시원하다 · 제목+목록이라 PPT 같다")
        v.addWidget(self.note)
        v.addStretch(1)
        h.addLayout(v, 1)

    def entry(self) -> dict:
        verdict = "up" if self.up.isChecked() else "down" if self.down.isChecked() else ""
        return {"gid": self.row.get("gid"), "verdict": verdict, "note": self.note.text().strip(),
                "title": self.row.get("title", ""), "kind": self.row.get("kind") or self.row.get("template", ""),
                "still": self.row.get("still", "")}


class RateDialog(QDialog):
    """rate.json(파이프라인 export 의 _rating_stills) → 장면 목록 → 저장하면 taste.record."""

    def __init__(self, rate_json: str, job: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("장면 평가 — 다음 영상의 디자인 취향")
        self.resize(980, 760)
        self.job = job
        rows = [r for r in read_json(Path(rate_json), []) if isinstance(r, dict) and Path(str(r.get("still") or "")).exists()]
        v = QVBoxLayout(self)
        v.addWidget(hint("장면마다 👍/👎 를 누르고 이유를 한 줄 적으면, 다음 작업부터 모션 디자이너·시그니처 장면·심사·아트 디렉터가 "
                         "이 그림과 메모를 매번 봅니다. 몇 개만 평가해도 됩니다. (좋아하는 다른 영상의 정지 화면은 user/taste 폴더에)"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        grid = QGridLayout(body)
        self.rows = [_Row(r) for r in rows]
        for i, w in enumerate(self.rows):
            grid.addWidget(w, i, 0)
        if not self.rows:
            grid.addWidget(QLabel("평가할 장면이 없습니다(롱폼이 없거나 정지 화면을 만들지 못했습니다)."), 0, 0)
        scroll.setWidget(body)
        v.addWidget(scroll, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("저장")
        bb.button(QDialogButtonBox.Cancel).setText("닫기")
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def entries(self) -> list[dict]:
        return [e for e in (r.entry() for r in self.rows) if e["verdict"]]

    def _save(self) -> None:
        es = self.entries()
        if not es:
            self.reject()
            return
        n = taste.record(es, job=self.job)
        QMessageBox.information(self, "장면 평가", f"{n}개 장면을 기억했습니다. 다음 작업부터 디자이너와 심사가 이 취향을 봅니다.")
        self.accept()
