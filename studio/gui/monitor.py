"""프로그램 모니터 — 원본 또는 렌더 결과(롱폼·숏폼)를 재생. 롱폼 결과는 타임라인 재생 헤드와 연동."""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QSlider, QStackedLayout, QToolButton,
                               QVBoxLayout, QWidget)

from .timeline import tc

try:  # QtMultimedia 가 없는 환경에서도 창은 뜨게
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    HAVE_MM = True
except Exception:  # noqa: BLE001
    HAVE_MM = False


def poster_path(video: str) -> Path:
    from ..paths import USER_DIR
    st = Path(video).stat()
    key = hashlib.sha1(f"{video}|{st.st_size}|{st.st_mtime}".encode()).hexdigest()[:16]
    return USER_DIR / "cache" / "posters" / f"{key}.jpg"


def make_poster(video: str) -> Optional[Path]:
    """재생 전 모니터에 띄울 정지 화면(영상 3초 지점, 짧으면 첫 프레임)."""
    out = poster_path(video)
    if out.exists():
        return out
    try:
        from ..media.ffmpeg import FFmpeg, hdr_to_sdr_filter
        ff = FFmpeg()
        info = ff.probe(video)
        out.parent.mkdir(parents=True, exist_ok=True)
        t = 3.0 if info.duration > 6 else 0.0
        ff.grab_frame(video, t, out, width=1280, extra_vf=hdr_to_sdr_filter() if info.is_hdr else "")
        return out if out.exists() else None
    except Exception:  # noqa: BLE001 - 정지 화면은 없어도 된다
        return None


class _PosterSignal(QObject):
    ready = Signal(str, str)   # (영상 경로, 정지 화면 경로)


class ProgramMonitor(QWidget):
    position = Signal(float, bool)   # (초, 편집 시간 기준인가 = 롱폼 결과)

    def __init__(self):
        super().__init__()
        self.fps = 30
        self._sources: list[tuple[str, str, bool]] = []
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(6)
        top = QHBoxLayout()
        self.src = QComboBox()
        self.src.setMinimumWidth(220)
        self.src.currentIndexChanged.connect(self._load_current)
        top.addWidget(QLabel("소스"))
        top.addWidget(self.src, 1)
        top.addStretch(1)
        self.res = QLabel("")
        self.res.setObjectName("hint")
        top.addWidget(self.res)
        v.addLayout(top)

        frame = QFrame()
        frame.setObjectName("monitor")
        self.stack = QStackedLayout(frame)
        self.empty = QLabel("원본 영상을 프로젝트 패널에 끌어다 놓으세요\n렌더가 끝나면 결과물을 바로 여기서 확인합니다")
        self.empty.setObjectName("panelEmpty")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setMinimumSize(320, 180)
        self._poster: Optional[QPixmap] = None
        self._poster_sig = _PosterSignal()
        self._poster_sig.ready.connect(self._on_poster)
        self.stack.addWidget(self.empty)
        self.player = None
        if HAVE_MM:
            try:
                self.video = QVideoWidget()
                self.video.setStyleSheet("background:#000;")
                self.stack.addWidget(self.video)
                self.player = QMediaPlayer(self)
                self.audio = QAudioOutput(self)
                self.audio.setVolume(0.9)
                self.player.setAudioOutput(self.audio)
                self.player.setVideoOutput(self.video)
                self.player.positionChanged.connect(self._on_pos)
                self.player.durationChanged.connect(self._on_dur)
                self.player.playbackStateChanged.connect(self._on_state)
            except Exception:  # noqa: BLE001
                self.player = None
        v.addWidget(frame, 1)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(lambda ms: self.player and self.player.setPosition(ms))
        v.addWidget(self.slider)
        bar = QHBoxLayout()
        self.tc = QLabel(tc(0))
        self.tc.setObjectName("timecode")
        self.total = QLabel("/ " + tc(0))
        self.total.setObjectName("timecodeDim")
        bar.addWidget(self.tc)
        bar.addWidget(self.total)
        bar.addStretch(1)
        for text, tip, fn in [("⏮", "처음으로", lambda: self.seek(0)),
                              ("◀◀", "5초 뒤로", lambda: self.step(-5)),
                              ("◀|", "1프레임 뒤로", lambda: self.step(-1 / self.fps)),
                              ("▶", "재생/일시정지 (Space)", self.toggle),
                              ("|▶", "1프레임 앞으로", lambda: self.step(1 / self.fps)),
                              ("▶▶", "5초 앞으로", lambda: self.step(5))]:
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            b.setStyleSheet("font-size:14px; padding:4px 8px;")
            if text == "▶":
                self.play_btn = b
            bar.addWidget(b)
        bar.addStretch(1)
        self.mode = QLabel("")
        self.mode.setObjectName("hint")
        bar.addWidget(self.mode)
        v.addLayout(bar)

    # ------------------------------------------------------------------
    def set_sources(self, items: list[tuple[str, str, bool]], prefer: Optional[str] = None) -> None:
        """[(라벨, 경로, 편집시간기준)] — 있는 파일만."""
        items = [it for it in items if it[1] and Path(it[1]).exists()]
        cur = self._sources[self.src.currentIndex()][1] if 0 <= self.src.currentIndex() < len(self._sources) else ""
        if [i[1] for i in items] == [s[1] for s in self._sources]:
            return
        self._sources = items
        self.src.blockSignals(True)
        self.src.clear()
        for label, _p, _e in items:
            self.src.addItem(label)
        idx = 0
        for i, (_l, p, _e) in enumerate(items):
            if prefer and p == prefer or (not prefer and p == cur):
                idx = i
        self.src.setCurrentIndex(idx if items else -1)
        self.src.blockSignals(False)
        self._load_current()

    def _load_current(self) -> None:
        i = self.src.currentIndex()
        if not (0 <= i < len(self._sources)) or self.player is None:
            self.stack.setCurrentIndex(0)
            return
        label, path, edit = self._sources[i]
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(path))
        self.stack.setCurrentIndex(0)     # 재생 전에는 정지 화면
        self._poster = None
        self.empty.setText("불러오는 중…")
        threading.Thread(target=lambda: self._poster_sig.ready.emit(path, str(make_poster(path) or "")),
                         daemon=True).start()
        self.mode.setText("타임라인 연동" if edit else "원본 시간")
        self.res.setText(Path(path).name)

    def current_is_edit(self) -> bool:
        i = self.src.currentIndex()
        return 0 <= i < len(self._sources) and self._sources[i][2]

    def toggle(self) -> None:
        if not self.player:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.stack.setCurrentIndex(1)
            self.player.play()

    def _on_poster(self, video: str, poster: str) -> None:
        i = self.src.currentIndex()
        if not (0 <= i < len(self._sources)) or self._sources[i][1] != video:
            return
        self._poster = QPixmap(poster) if poster else None
        if self._poster is None or self._poster.isNull():
            self.empty.setText("▶ 을 눌러 재생")
            return
        self._fit_poster()

    def _fit_poster(self) -> None:
        if self._poster is not None and not self._poster.isNull():
            self.empty.setPixmap(self._poster.scaled(self.empty.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._fit_poster()

    def seek(self, t: float) -> None:
        if self.player:
            self.stack.setCurrentIndex(1)
            self.player.setPosition(int(max(0.0, t) * 1000))

    def step(self, dt: float) -> None:
        if self.player:
            self.seek(self.player.position() / 1000 + dt)

    def _on_pos(self, ms: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(ms)
        self.slider.blockSignals(False)
        self.tc.setText(tc(ms / 1000, self.fps))
        self.position.emit(ms / 1000, self.current_is_edit())

    def _on_dur(self, ms: int) -> None:
        self.slider.setRange(0, ms)
        self.total.setText("/ " + tc(ms / 1000, self.fps))

    def _on_state(self, st) -> None:
        self.play_btn.setText("⏸" if self.player and st == QMediaPlayer.PlayingState else "▶")
