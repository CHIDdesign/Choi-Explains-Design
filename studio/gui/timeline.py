"""타임라인 패널 — AI 편집 결과(컷·그래픽·모션·스톡·자막·챕터)를 트랙으로 보여 준다.

데이터: 작업 폴더의 work/timeline.json(편집 계획만 했을 때) 또는 render/props_long.json(렌더 후).
시간은 모두 '편집 후' 기준 초. 재생 헤드는 프로그램 모니터(롱폼 결과)와 연동된다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QScrollArea, QSlider, QToolButton, QToolTip, QVBoxLayout,
                               QWidget)

from . import theme

RULER_H = 30
TRACKS = [  # (키, 이름, 높이)
    ("v3", "V3  모션·스톡", 30),
    ("v2", "V2  그래픽", 30),
    ("v1", "V1  영상", 38),
    ("a1", "A1  음성", 26),
    ("cc", "CC  자막", 24),
]
HEADER_W = 118

TEMPLATE_KO = {"chapter": "챕터", "keyword": "키워드", "definition": "정의", "quote": "인용", "list": "목록",
               "process": "프로세스", "cycle": "순환", "double_diamond": "더블 다이아몬드", "matrix": "매트릭스",
               "compare": "비교", "timeline": "연표", "stat": "숫자", "venn": "벤", "pyramid": "피라미드",
               "photo": "자료 사진", "motion": "모션", "broll": "스톡", "title": "표지", "lower_third": "자막바"}


@dataclass
class Clip:
    track: str
    start: float
    end: float
    label: str
    color: str
    tip: str = ""


@dataclass
class TimelineData:
    duration: float = 0.0
    fps: int = 30
    clips: list[Clip] = field(default_factory=list)
    chapters: list[tuple[float, str]] = field(default_factory=list)
    source: str = ""

    @classmethod
    def load(cls, job_dir: Optional[Path]) -> "TimelineData":
        if not job_dir:
            return cls()
        props = Path(job_dir) / "render" / "props_long.json"
        prev = Path(job_dir) / "work" / "timeline.json"
        path = props if props.exists() and (not prev.exists() or props.stat().st_mtime >= prev.stat().st_mtime) else prev
        if not path.exists():
            return cls()
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        return cls.from_dict(d, source="render" if path == props else "plan")

    @classmethod
    def from_dict(cls, d: dict, source: str = "") -> "TimelineData":
        t = cls(duration=float(d.get("duration") or 0), fps=int(d.get("fps") or 30), source=source)
        for i, c in enumerate(d.get("clips") or []):
            s = float(c["start"])
            e = s + float(c.get("dur", 0))
            t.clips.append(Clip("v1", s, e, f"컷 {i + 1}", theme.CLIP["video"], f"원본 {c.get('srcStart', 0):.1f}s부터"))
            t.clips.append(Clip("a1", s, e, "", theme.CLIP["audio"]))
        for g in d.get("graphics") or []:
            tpl = g.get("template", "")
            data = g.get("data") or {}
            name = TEMPLATE_KO.get(tpl, tpl)
            title = str(data.get("title") or data.get("body") or "")[:28]
            if tpl in ("motion", "broll", "photo"):
                track, color = "v3", theme.CLIP["motion" if tpl == "motion" else "broll"]
            elif tpl in ("title", "chapter"):
                track, color = "v2", theme.CLIP["title"]
            else:
                track, color = "v2", theme.CLIP["graphic"]
            tip = f"{name} · {g.get('layout', '')}\n{float(g['start']):.1f}–{float(g['end']):.1f}s"
            if title:
                tip += f"\n{title}"
            if data.get("credit"):
                tip += f"\n▣ {data['credit']}"
            t.clips.append(Clip(track, float(g["start"]), float(g["end"]), f"{name}  {title}".strip(), color, tip))
        for c in d.get("captions") or []:
            text = c.get("text")
            if text is None:
                text = " ".join(w.get("text", "") for line in c.get("lines", []) for w in line)
            t.clips.append(Clip("cc", float(c["start"]), float(c["end"]), text, theme.CLIP["caption"], text))
        for ch in d.get("chapters") or []:
            t.chapters.append((float(ch.get("start", 0)), f"{ch.get('number', '')} {ch.get('title', '')}".strip()))
        if not t.duration and t.clips:
            t.duration = max(c.end for c in t.clips)
        return t


def tc(t: float, fps: int = 30) -> str:
    t = max(0.0, t)
    f = int(round(t * fps))
    return f"{f // (3600 * fps):02d}:{f // (60 * fps) % 60:02d}:{f // fps % 60:02d}:{f % fps:02d}"


class _Canvas(QWidget):
    seek = Signal(float)

    def __init__(self, view: "TimelineView"):
        super().__init__()
        self.view = view
        self.setMouseTracking(True)
        self.setMinimumHeight(RULER_H + sum(h for _, _, h in TRACKS) + 8)

    # 좌표 변환
    def x_of(self, t: float) -> float:
        return 8 + t * self.view.pps

    def t_of(self, x: float) -> float:
        return max(0.0, min(self.view.data.duration, (x - 8) / max(1e-6, self.view.pps)))

    def track_rect(self, key: str) -> QRectF:
        y = RULER_H + 4
        for k, _, h in TRACKS:
            if k == key:
                return QRectF(0, y, self.width(), h)
            y += h + 2
        return QRectF()

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        d = self.view.data
        p.fillRect(self.rect(), QColor(theme.BG1))
        # 트랙 바탕
        for k, _, _h in TRACKS:
            r = self.track_rect(k)
            p.fillRect(r, QColor("#191919"))
        # 눈금자
        p.fillRect(QRectF(0, 0, self.width(), RULER_H), QColor(theme.BG2))
        p.setPen(QPen(QColor(theme.LINE)))
        p.drawLine(0, RULER_H, self.width(), RULER_H)
        if d.duration <= 0:
            p.setPen(QColor(theme.TEXT3))
            p.drawText(self.rect().adjusted(0, RULER_H, 0, 0), Qt.AlignCenter,
                       "편집 계획을 만들면 여기에 컷·그래픽·모션·스톡·자막이 트랙으로 표시됩니다")
            return
        step = self._tick_step()
        small = QFont(self.font())
        small.setPointSizeF(7.5)
        p.setFont(small)
        t = 0.0
        while t <= d.duration + 1e-6:
            x = self.x_of(t)
            major = abs((t / (step * 5)) - round(t / (step * 5))) < 1e-6
            p.setPen(QPen(QColor(theme.TEXT3 if not major else theme.TEXT2)))
            p.drawLine(QPointF(x, RULER_H - (10 if major else 5)), QPointF(x, RULER_H))
            if major:
                p.drawText(QPointF(x + 3, 12), tc(t, d.fps)[3:8])
            t += step
        # 클립
        lab = QFont(self.font())
        lab.setPointSizeF(8)
        p.setFont(lab)
        for c in d.clips:
            r = self.track_rect(c.track)
            x0, x1 = self.x_of(c.start), self.x_of(c.end)
            box = QRectF(x0, r.top() + 2, max(2.0, x1 - x0 - 1), r.height() - 4)
            col = QColor(c.color)
            if c is self.view.hover:
                col = col.lighter(125)
            path = QPainterPath()
            path.addRoundedRect(box, 3, 3)
            p.fillPath(path, col)
            p.setPen(QPen(col.darker(160), 1))
            p.drawPath(path)
            if c.label and box.width() > 26:
                p.setPen(QColor("#F2F2F2" if c.track != "cc" else "#CFCFCF"))
                p.drawText(box.adjusted(5, 0, -3, 0), Qt.AlignVCenter | Qt.AlignLeft, c.label)
        # 챕터 마커
        acc = QColor(self.view.accent)
        for t0, name in d.chapters:
            x = self.x_of(t0)
            p.setPen(QPen(acc, 1))
            p.drawLine(QPointF(x, RULER_H), QPointF(x, self.height()))
            tri = QPolygonF([QPointF(x - 5, 14), QPointF(x + 5, 14), QPointF(x, 22)])
            p.setBrush(acc)
            p.drawPolygon(tri)
            p.setPen(QColor(theme.TEXT))
            p.drawText(QPointF(x + 7, 25), name[:24])
        # 재생 헤드
        xh = self.x_of(self.view.playhead)
        p.setPen(QPen(acc, 1.5))
        p.drawLine(QPointF(xh, 0), QPointF(xh, self.height()))
        p.setBrush(acc)
        p.drawPolygon(QPolygonF([QPointF(xh - 6, 0), QPointF(xh + 6, 0), QPointF(xh + 6, 8), QPointF(xh, 14),
                                 QPointF(xh - 6, 8)]))
        p.end()

    def _tick_step(self) -> float:
        for s in (0.5, 1, 2, 5, 10, 15, 30, 60, 120):
            if s * self.view.pps >= 14:
                return s
        return 300

    def _clip_at(self, pos) -> Optional[Clip]:
        t = self.t_of(pos.x())
        for c in reversed(self.view.data.clips):
            if self.track_rect(c.track).contains(pos) and c.start <= t <= c.end:
                return c
        return None

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            self.seek.emit(self.t_of(e.position().x()))

    def mouseMoveEvent(self, e):  # noqa: N802
        if e.buttons() & Qt.LeftButton:
            self.seek.emit(self.t_of(e.position().x()))
            return
        c = self._clip_at(e.position())
        if c is not self.view.hover:
            self.view.hover = c
            self.update()
        if c and c.tip:
            QToolTip.showText(e.globalPosition().toPoint(), c.tip, self)
        else:
            QToolTip.hideText()

    def wheelEvent(self, e):  # noqa: N802
        if e.modifiers() & Qt.ControlModifier:
            self.view.zoom_by(1.15 if e.angleDelta().y() > 0 else 1 / 1.15)
            e.accept()
            return
        sb = self.view.scroll.horizontalScrollBar()
        sb.setValue(sb.value() - e.angleDelta().y())
        e.accept()


class _Headers(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(HEADER_W)

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG2))
        p.setPen(QColor(theme.TEXT3))
        p.drawText(QRectF(10, 0, HEADER_W, RULER_H), Qt.AlignVCenter, "트랙")
        y = RULER_H + 4
        for _k, name, h in TRACKS:
            p.fillRect(QRectF(0, y, HEADER_W, h), QColor("#202020"))
            p.setPen(QColor(theme.TEXT2))
            p.drawText(QRectF(10, y, HEADER_W - 10, h), Qt.AlignVCenter, name)
            y += h + 2
        p.setPen(QColor(theme.LINE))
        p.drawLine(HEADER_W - 1, 0, HEADER_W - 1, self.height())
        p.end()


class TimelineView(QWidget):
    seek = Signal(float)

    def __init__(self, accent: str):
        super().__init__()
        self.accent = accent
        self.data = TimelineData()
        self.pps = 12.0          # 초당 픽셀
        self.playhead = 0.0
        self.hover: Optional[Clip] = None
        self._auto_fit = True     # 사용자가 확대/축소하기 전까지는 창 너비에 맞춤
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(10, 5, 10, 5)
        self.tc = QLabel(tc(0))
        self.tc.setObjectName("timecode")
        self.info = QLabel("")
        self.info.setObjectName("hint")
        bar.addWidget(self.tc)
        bar.addSpacing(12)
        bar.addWidget(self.info, 1)
        fit = QToolButton()
        fit.setText("⤢ 맞춤")
        fit.setToolTip("타임라인 전체를 창 너비에 맞춤")
        fit.clicked.connect(self.fit)
        self.zoom = QSlider(Qt.Horizontal)
        self.zoom.setRange(2, 200)
        self.zoom.setValue(12)
        self.zoom.setFixedWidth(130)
        self.zoom.setToolTip("확대/축소 (Ctrl + 휠)")
        self.zoom.valueChanged.connect(self._on_zoom_slider)
        bar.addWidget(QLabel("🔍"))
        bar.addWidget(self.zoom)
        bar.addWidget(fit)
        v.addLayout(bar)
        row = QHBoxLayout()
        row.setSpacing(0)
        self.headers = _Headers()
        self.canvas = _Canvas(self)
        self.canvas.seek.connect(self._on_seek)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(False)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        row.addWidget(self.headers)
        row.addWidget(self.scroll, 1)
        v.addLayout(row, 1)
        self._resize_canvas()

    # ------------------------------------------------------------------
    def set_data(self, data: TimelineData) -> None:
        self.data = data
        self.hover = None
        n_g = sum(1 for c in data.clips if c.track in ("v2", "v3"))
        n_cut = sum(1 for c in data.clips if c.track == "v1")
        src = {"render": "렌더 결과", "plan": "편집 계획(렌더 전)"}.get(data.source, "")
        self.info.setText(f"{src} · 길이 {tc(data.duration, data.fps)} · 컷 {n_cut} · 그래픽 {n_g} · 챕터 "
                          f"{len(data.chapters)}" if data.duration else "")
        self._auto_fit = True
        self.fit()

    def set_playhead(self, t: float) -> None:
        self.playhead = max(0.0, t)
        self.tc.setText(tc(self.playhead, self.data.fps))
        self.canvas.update()
        x = self.canvas.x_of(self.playhead)
        sb = self.scroll.horizontalScrollBar()
        if not (sb.value() <= x <= sb.value() + self.scroll.viewport().width() - 20):
            sb.setValue(int(x - 60))

    def fit(self) -> None:
        self._auto_fit = True
        if self.data.duration > 0:
            w = max(200, self.scroll.viewport().width() - 24)
            self.zoom.blockSignals(True)
            self._set_pps(max(0.5, w / self.data.duration))
            self.zoom.setValue(int(max(2, min(200, self.pps))))
            self.zoom.blockSignals(False)
        else:
            self._resize_canvas()

    def _on_zoom_slider(self, v: int) -> None:
        self._auto_fit = False
        self._set_pps(float(v))

    def zoom_by(self, k: float) -> None:
        self._auto_fit = False
        self._set_pps(max(0.5, min(400.0, self.pps * k)))
        self.zoom.blockSignals(True)
        self.zoom.setValue(int(max(2, min(200, self.pps))))
        self.zoom.blockSignals(False)

    def _set_pps(self, pps: float) -> None:
        self.pps = pps
        self._resize_canvas()

    def _resize_canvas(self) -> None:
        w = int(16 + max(self.data.duration, 1) * self.pps)
        self.canvas.setFixedSize(max(w, self.scroll.viewport().width()), self.canvas.minimumHeight())
        self.canvas.update()

    def _on_seek(self, t: float) -> None:
        self.set_playhead(t)
        self.seek.emit(t)

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if self._auto_fit:
            self.fit()
        else:
            self._resize_canvas()

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        if self._auto_fit:
            self.fit()
