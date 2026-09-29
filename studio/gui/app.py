"""Choi Studio — 세 가지만 넣으면 끝까지 만들어 주는 오토파일럿 창.

┌ 헤더: 로고 · 최근 작업 · AI 연결 상태 · ⚙ ─────────────────────────────────────────┐
│ ① 주제          │ ② 원본 영상(끌어다 놓기·클릭·Ctrl+V) │ ③ 대본(붙여넣기·파일)          │
│                          [ 영상 만들기 ▶ ]                                            │
└──────────────────────────────────────────────────────────────────────────────────────┘
→ 진행 화면(단계 체크리스트 · AI 팀 작업 기록 · 색보정 전후) → 결과 화면(롱폼 1 · 숏폼 2 · 업로드 정보)

편집 툴처럼 만질 것이 없다: 구성·컷·얼굴/그래픽 배분·색·자막·효과음·음악은 전부 자동.
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
                               QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
                               QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from .. import __version__
from ..director.claude_code import auth_status, describe_auth, find_claude, open_login, resolve_backend
from ..eta import Eta, EtaDisplay, fmt_left
from ..paths import USER_DIR, ensure_user_dirs
from ..pipeline import EXTRAS, STAGES, JobSpec, Pipeline, new_job_dir
from ..settings import Settings
from ..text.docfile import TEXT_EXTS, read_text_file
from ..util import CancelToken, Cancelled, fmt_ts, read_json, write_json
from . import theme
from .poster import make_poster
from .settings_dialog import SettingsDialog
from .winshell import enable_elevated_drop, is_admin

LAST_INPUTS = USER_DIR / "last_inputs.json"
VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".m4v", ".avi", ".mts", ".m2ts", ".webm", ".mxf")
VIDEO_FILTER = "영상 (" + " ".join("*" + e for e in VIDEO_EXTS) + ");;모든 파일 (*)"
TEXT_FILTER = "대본 (*.txt *.md *.docx *.hwpx);;모든 파일 (*)"


# ---------------------------------------------------------------------------
# 백그라운드 작업
# ---------------------------------------------------------------------------

class Worker(QObject):
    log = Signal(str)
    progress = Signal(str, float, float)
    preview = Signal(str, str)          # 이미지 경로, 설명
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, spec: JobSpec, settings: Settings, job_dir: Path, cancel: CancelToken, until: str = "all"):
        super().__init__()
        self.spec, self.settings, self.job_dir, self.cancel, self.until = spec, settings, job_dir, cancel, until
        self.eta = Eta(USER_DIR / "eta_history.json")   # 창이 1초마다 남은 시간을 읽는다(스레드 안전)

    def run(self) -> None:
        try:
            p = Pipeline(self.spec, self.settings, self.job_dir, log=self.log.emit,
                         progress=lambda k, f, o: self.progress.emit(k, f, o), cancel=self.cancel, eta=self.eta,
                         preview=self.preview.emit)
            self.finished.emit(p.run(until=self.until))
        except Cancelled:
            self.failed.emit("취소했습니다.")
        except Exception as e:  # noqa: BLE001 - 모든 오류를 창에 표시
            self.failed.emit(f"{e}\n\n{traceback.format_exc()[-2500:]}")


class _Call(QObject):
    """짧은 작업을 창을 멈추지 않고 실행(영상 정보·포스터·AI 연결 확인)."""
    done = Signal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self.fn())
        except Exception as e:  # noqa: BLE001
            self.done.emit(e)


_BG: list[tuple[QThread, QObject]] = []


def run_bg(parent: QObject, fn, on_done) -> None:
    th = QThread()
    call = _Call(fn)
    call.moveToThread(th)
    th.started.connect(call.run)
    call.done.connect(on_done)
    call.done.connect(th.quit)
    _BG.append((th, call))  # 참조 유지(끝나면 정리)
    th.finished.connect(lambda: _BG.remove((th, call)) if (th, call) in _BG else None)
    th.start()


def wait_bg(ms: int = 3000) -> None:
    for th, _ in list(_BG):
        th.quit()
        th.wait(ms)


def ai_status_text(settings: Settings) -> tuple[str, bool]:
    backend, why = resolve_backend(settings)
    if backend == "claude_code":
        exe = find_claude(settings.claude_code_path)
        st = auth_status(exe) if exe else {}
        ok = bool(st.get("loggedIn"))
        return (f"Claude Code · {describe_auth(st)}" if exe else "Claude Code 없음"), ok
    if backend == "api":
        return "Claude API 키 연결됨", True
    return f"AI 없음 · {why}", False


# ---------------------------------------------------------------------------
# 위젯
# ---------------------------------------------------------------------------

def _label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


class StepCard(QFrame):
    """① ② ③ 입력 카드."""

    def __init__(self, num: str, title: str, hint: str, body: QWidget, extra: Optional[QWidget] = None):
        super().__init__()
        self.setObjectName("stepCard")
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 20)
        v.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(10)
        badge = _label(num, "stepNum")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(30, 30)
        head.addWidget(badge)
        head.addWidget(_label(title, "stepTitle"))
        head.addStretch(1)
        if extra is not None:
            head.addWidget(extra)
        v.addLayout(head)
        v.addWidget(_label(hint, "stepHint", wrap=True))
        v.addWidget(body, 1)


class VideoDrop(QFrame):
    """원본 영상 칸: 클릭 → 찾아보기, 끌어다 놓기, 파일 복사 후 Ctrl+V."""
    changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("videoDrop")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(260)
        self.path = ""
        self._pix: Optional[QPixmap] = None
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(8)
        self.poster = QLabel()
        self.poster.setAlignment(Qt.AlignCenter)
        self.poster.setObjectName("poster")
        self.poster.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.empty = _label("＋\n\n여기를 눌러 영상 선택\n또는 탐색기에서 끌어다 놓기", "dropEmpty")
        self.empty.setAlignment(Qt.AlignCenter)
        self.name = _label("", "dropName")
        self.name.setAlignment(Qt.AlignCenter)
        self.meta = _label("", "dropMeta")
        self.meta.setAlignment(Qt.AlignCenter)
        v.addWidget(self.empty, 1)
        v.addWidget(self.poster, 1)
        v.addWidget(self.name)
        v.addWidget(self.meta)
        self.poster.hide()
        if not is_admin():
            self.setAcceptDrops(True)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            p, _ = QFileDialog.getOpenFileName(self, "원본 영상 선택", str(Path(self.path).parent) if self.path else "",
                                               VIDEO_FILTER)
            if p:
                self.set_path(p)

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        for u in e.mimeData().urls():
            if u.isLocalFile():
                self.set_path(u.toLocalFile())
                break

    def set_path(self, p: str) -> None:
        self.path = p
        self.empty.setVisible(not p)
        self.poster.setVisible(bool(p))
        self.name.setText(Path(p).name if p else "")
        self.meta.setText("영상 정보를 읽는 중…" if p else "")
        self._pix = None
        self.poster.clear()
        self.changed.emit(p)

    def set_info(self, text: str, poster: Optional[Path]) -> None:
        self.meta.setText(text)
        if poster and Path(poster).exists():
            self._pix = QPixmap(str(poster))
            self._fit()

    def _fit(self) -> None:
        if self._pix and not self._pix.isNull():
            self.poster.setPixmap(self._pix.scaled(self.poster.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._fit()


class ResultCard(QFrame):
    def __init__(self, title: str, path: str, vertical: bool):
        super().__init__()
        self.setObjectName("resultCard")
        self.path = path
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)
        self.poster = QLabel()
        self.poster.setAlignment(Qt.AlignCenter)
        self.poster.setObjectName("poster")
        self.poster.setFixedSize(QSize(170, 302) if vertical else QSize(420, 236))
        v.addWidget(self.poster, 0, Qt.AlignHCenter)
        v.addWidget(_label(title, "resultTitle"))
        self.meta = _label(Path(path).name if path else "만들지 못했습니다", "stepHint", wrap=True)
        v.addWidget(self.meta)
        row = QHBoxLayout()
        play = QPushButton("▶ 재생")
        play.setObjectName("primarySmall")
        play.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.path)))
        show = QPushButton("폴더에서 보기")
        show.clicked.connect(lambda: reveal(self.path))
        for b in (play, show):
            b.setEnabled(bool(path) and Path(path).exists())
            row.addWidget(b)
        v.addLayout(row)
        v.addStretch(1)
        if path and Path(path).exists():
            run_bg(self, lambda: make_poster(path), self._on_poster)

    def _on_poster(self, p) -> None:
        if isinstance(p, Path) and p.exists():
            pix = QPixmap(str(p))
            self.poster.setPixmap(pix.scaled(self.poster.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                                  .copy(0, 0, self.poster.width(), self.poster.height()))


def reveal(path: str) -> None:
    p = Path(path)
    if sys.platform == "win32" and p.exists():
        import subprocess
        subprocess.Popen(["explorer", "/select,", str(p)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent if p.is_file() else p)))


# ---------------------------------------------------------------------------
# 메인 창
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings.load()
        self.setWindowTitle(f"Choi Studio {__version__}")
        try:
            from .icon import qicon
            self.setWindowIcon(qicon())
        except Exception:  # noqa: BLE001
            pass
        self.resize(1320, 820)
        self.job_dir: Optional[Path] = None
        self.cancel: Optional[CancelToken] = None
        self.thread: Optional[QThread] = None
        self.worker: Optional[Worker] = None
        self.t_start = 0.0
        self.video_seconds = 0.0
        self._build()
        self._restore_inputs()
        QTimer.singleShot(150, self._probe_ai)
        QTimer.singleShot(400, lambda: enable_elevated_drop(self, self._on_files))

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self._header())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._input_page())
        self.pages.addWidget(self._progress_page())
        self.pages.addWidget(self._result_page())
        v.addWidget(self.pages, 1)
        QShortcut(QKeySequence.Paste, self, activated=self._paste)

    def _header(self) -> QWidget:
        w = QWidget()
        w.setObjectName("header")
        h = QHBoxLayout(w)
        h.setContentsMargins(22, 12, 18, 12)
        h.setSpacing(12)
        dot = _label("●", "brandDot")
        h.addWidget(dot)
        h.addWidget(_label("CHOI STUDIO", "brand"))
        h.addWidget(_label("디자인 이론 영상 오토파일럿", "brandSub"))
        h.addStretch(1)
        self.recent_btn = QToolButton()
        self.recent_btn.setText("최근 작업 ▾")
        self.recent_btn.setPopupMode(QToolButton.InstantPopup)
        self.recent_menu = QMenu(self)
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        self.recent_btn.setMenu(self.recent_menu)
        h.addWidget(self.recent_btn)
        self.ai_chip = QPushButton("AI 연결 확인 중…")
        self.ai_chip.setObjectName("chip")
        self.ai_chip.clicked.connect(self._on_chip)
        h.addWidget(self.ai_chip)
        gear = QToolButton()
        gear.setText("⚙")
        gear.setToolTip("고급 설정(AI 연결 · 스톡 키 · 브랜드 · 경로) — 보통은 만질 필요 없습니다")
        gear.clicked.connect(self._open_settings)
        h.addWidget(gear)
        return w

    # ---------------- 입력 ----------------
    def _input_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)
        outer.addWidget(_label("새 영상 만들기", "pageTitle"))
        outer.addWidget(_label("세 가지를 넣으면 기획, 컷 편집, 색보정, 모션그래픽, 자막, 효과음과 음악, 렌더링을 차례로 "
                               "진행해 롱폼 1편과 숏폼 2편을 만듭니다.", "pageSub", wrap=True))
        grid = QHBoxLayout()
        grid.setSpacing(16)
        self.topic = QPlainTextEdit()
        self.topic.setPlaceholderText("무엇을, 누구에게, 왜 이야기하는지 편하게 적어 주세요.\n\n"
                                      "예) 게슈탈트 원리 — 왜 우리는 점 세 개를 삼각형으로 볼까. 디자인 입문자 대상, "
                                      "일상 사물 예시 위주. 꼭 보여 주고 싶은 장면: 신호등, 애플 로고.")
        self.video = VideoDrop()
        self.video.changed.connect(self._on_video)
        self.script = QPlainTextEdit()
        self.script.setPlaceholderText("녹화할 때 읽은 대본을 그대로 붙여 넣으세요.\n\n"
                                       "대본과 다르게 말한 부분·같은 문장을 여러 번 말한 부분은 알아서 정리하고, "
                                       "가장 또렷하게 말한 테이크를 씁니다.")
        load = QPushButton("파일 불러오기")
        load.setObjectName("ghost")
        load.clicked.connect(self._load_script)
        for w in (self.topic, self.script):
            w.textChanged.connect(self._update_ready)
        grid.addWidget(StepCard("1", "주제", "이 영상이 무엇에 관한 것인지", self.topic), 3)
        grid.addWidget(StepCard("2", "원본 영상", "대본을 말하는 모습을 찍은 긴 원본 그대로(여러 번 다시 말한 것 포함)",
                                self.video), 4)
        grid.addWidget(StepCard("3", "대본", "읽은 대본 전체", self.script, load), 3)
        outer.addLayout(grid, 1)
        bar = QHBoxLayout()
        self.summary = _label("", "stepHint", wrap=True)
        bar.addWidget(self.summary, 1)
        self.go = QPushButton("영상 만들기  ▶")
        self.go.setObjectName("hero")
        self.go.setCursor(Qt.PointingHandCursor)
        self.go.clicked.connect(self._start)
        bar.addWidget(self.go)
        outer.addLayout(bar)
        return page

    # ---------------- 진행 ----------------
    def _progress_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(14)
        top = QHBoxLayout()
        box = QVBoxLayout()
        self.p_title = _label("만드는 중…", "pageTitle")
        self.p_sub = _label("", "pageSub")
        box.addWidget(self.p_title)
        box.addWidget(self.p_sub)
        top.addLayout(box, 1)
        self.p_pct = _label("0%", "bigPct")
        top.addWidget(self.p_pct)
        v.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setObjectName("thick")
        self.bar.setRange(0, 1000)
        v.addWidget(self.bar)
        body = QHBoxLayout()
        body.setSpacing(16)
        stages = QFrame()
        stages.setObjectName("panel")
        sv = QVBoxLayout(stages)
        sv.setContentsMargins(18, 16, 18, 16)
        sv.setSpacing(7)
        sv.addWidget(_label("진행 단계", "panelTitle"))
        self.stage_rows: dict[str, QLabel] = {}
        for key, label, _ in STAGES:
            lab = _label(f"○  {label}", "stageTodo")
            self.stage_rows[key] = lab
            sv.addWidget(lab)
        sv.addStretch(1)
        body.addWidget(stages, 2)
        right = QVBoxLayout()
        logbox = QFrame()
        logbox.setObjectName("panel")
        lv = QVBoxLayout(logbox)
        lv.setContentsMargins(18, 16, 18, 16)
        lv.addWidget(_label("AI 팀 작업 기록", "panelTitle"))
        self.logview = QPlainTextEdit()
        self.logview.setReadOnly(True)
        self.logview.setObjectName("log")
        self.logview.setMaximumBlockCount(4000)
        lv.addWidget(self.logview, 1)
        right.addWidget(logbox, 3)
        # 실시간 미리보기: 색보정 전후 → 자료 사진 → 검수 장면 → 렌더 중인 프레임 → 썸네일 순으로 바뀐다
        self.peek_box = QFrame()
        self.peek_box.setObjectName("panel")
        pv = QVBoxLayout(self.peek_box)
        pv.setContentsMargins(18, 14, 18, 14)
        pv.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(_label("실시간 미리보기", "panelTitle"))
        head.addStretch(1)
        self.peek_cap = _label("", "stepHint")
        head.addWidget(self.peek_cap)
        pv.addLayout(head)
        self.peek = QLabel()
        self.peek.setObjectName("poster")
        self.peek.setAlignment(Qt.AlignCenter)
        self.peek.setMinimumHeight(120)
        self.peek.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        pv.addWidget(self.peek, 1)
        self.peek_box.hide()
        self._peek_pix: Optional[QPixmap] = None
        right.addWidget(self.peek_box, 4)
        body.addLayout(right, 3)
        v.addLayout(body, 1)
        row = QHBoxLayout()
        row.addWidget(_label("창을 닫지 마세요. 절전 모드도 잠시 꺼 두면 좋습니다. 끝나면 결과 화면이 열립니다.",
                             "stepHint"), 1)
        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.clicked.connect(self._cancel)
        row.addWidget(self.cancel_btn)
        v.addLayout(row)
        self.tick = QTimer(self)
        self.tick.timeout.connect(self._tick)
        return page

    # ---------------- 결과 ----------------
    def _result_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(14)
        self.r_title = _label("완성!", "pageTitle")
        self.r_sub = _label("", "pageSub", wrap=True)
        v.addWidget(self.r_title)
        v.addWidget(self.r_sub)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.r_body = QWidget()
        self.r_body.setObjectName("root")
        scroll.viewport().setObjectName("root")
        self.r_grid = QGridLayout(self.r_body)
        self.r_grid.setSpacing(16)
        scroll.setWidget(self.r_body)
        v.addWidget(scroll, 1)
        row = QHBoxLayout()
        self.r_upload = QPushButton("업로드 정보(제목·설명·태그) 열기")
        self.r_upload.clicked.connect(lambda: self._open(self.results.get("upload_info", "")))
        self.r_folder = QPushButton("결과 폴더 열기")
        self.r_folder.clicked.connect(lambda: self._open(self.results.get("output", "")))
        again = QPushButton("새 영상 만들기")
        again.setObjectName("hero")
        again.clicked.connect(self._new)
        row.addWidget(self.r_upload)
        row.addWidget(self.r_folder)
        row.addStretch(1)
        row.addWidget(again)
        v.addLayout(row)
        self.results: dict = {}
        return page

    # ------------------------------------------------------------------
    # 입력 처리
    # ------------------------------------------------------------------
    def _on_files(self, paths: list[str]) -> None:
        """탐색기에서 끌어다 놓거나 붙여넣은 파일: 영상이면 ②, 글이면 ③(또는 비어 있으면 ①)."""
        for p in paths:
            ext = Path(p).suffix.lower()
            if ext in VIDEO_EXTS:
                self.video.set_path(p)
            elif ext in TEXT_EXTS:
                self._set_script_file(p)

    def _paste(self) -> None:
        md = QApplication.clipboard().mimeData()
        files = [u.toLocalFile() for u in md.urls() if u.isLocalFile()] if md and md.hasUrls() else []
        if files and self.pages.currentIndex() == 0:
            self._on_files(files)
            return
        fw = QApplication.focusWidget()
        if isinstance(fw, QPlainTextEdit):
            fw.paste()

    def _load_script(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "대본 파일", "", TEXT_FILTER)
        if p:
            self._set_script_file(p)

    def _set_script_file(self, p: str) -> None:
        try:
            text = read_text_file(p)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "대본", f"파일을 읽지 못했습니다: {e}")
            return
        self.script.setPlainText(text)

    def _on_video(self, p: str) -> None:
        self._update_ready()
        if not p:
            return

        def info():
            from ..media.ffmpeg import FFmpeg
            ff = FFmpeg(self.settings.ffmpeg_path, self.settings.ffprobe_path)
            mi = ff.probe(p)
            return mi, make_poster(p)

        run_bg(self, info, self._on_video_info)

    def _on_video_info(self, res) -> None:
        if isinstance(res, Exception):
            self.video.set_info(f"영상 정보를 읽지 못했습니다: {res}", None)
            return
        mi, poster = res
        w, h = mi.display_size
        self.video_seconds = mi.duration
        extra = "" if mi.has_audio else "  ·  ⚠ 소리 없음"
        self.video.set_info(f"{fmt_ts(mi.duration)}  ·  {w}×{h}  ·  {mi.fps:.0f}fps{extra}", poster)
        self._update_ready()

    def _update_ready(self) -> None:
        has_video = bool(self.video.path) and Path(self.video.path).exists()
        has_text = bool(self.script.toPlainText().strip() or self.topic.toPlainText().strip())
        self.go.setEnabled(has_video and has_text and self.thread is None)
        need = []
        if not self.topic.toPlainText().strip():
            need.append("① 주제")
        if not has_video:
            need.append("② 원본 영상")
        if not self.script.toPlainText().strip():
            need.append("③ 대본")
        if need:
            self.summary.setText("남은 입력: " + " · ".join(need)
                                 + ("  (대본이 없어도 만들 수는 있지만 결과가 훨씬 좋아집니다)" if "③ 대본" in need and has_video else ""))
        else:
            mins = self.video_seconds / 60
            est = f"약 {max(5, int(8 + mins * 1.4))}분" if mins else "영상 길이에 따라 다름"
            self.summary.setText(f"결과: 롱폼 1편 · 숏폼 2편 · 썸네일 3장 · 자막 · 업로드 정보   |   예상 {est}")

    def _spec(self) -> JobSpec:
        return JobSpec(video=self.video.path, topic=self.topic.toPlainText().strip(),
                       script=self.script.toPlainText())

    def _save_inputs(self) -> None:
        ensure_user_dirs()
        write_json(LAST_INPUTS, {"topic": self.topic.toPlainText(), "script": self.script.toPlainText(),
                                 "video": self.video.path})

    def _restore_inputs(self) -> None:
        d = read_json(LAST_INPUTS, {})
        if d:
            self.topic.setPlainText(d.get("topic", ""))
            self.script.setPlainText(d.get("script", ""))
            if d.get("video") and Path(d["video"]).exists():
                self.video.set_path(d["video"])
        self._update_ready()

    # ------------------------------------------------------------------
    # 실행
    # ------------------------------------------------------------------
    def _start(self, job_dir: Optional[Path] = None, spec: Optional[JobSpec] = None) -> None:
        if self.thread is not None:
            return
        spec = spec or self._spec()
        if not spec.video or not Path(spec.video).exists():
            QMessageBox.information(self, "원본 영상", "② 원본 영상을 선택해 주세요.")
            return
        self._save_inputs()
        self.settings = Settings.load()
        self.job_dir = job_dir or new_job_dir(self.settings, spec.working_title())
        self.cancel = CancelToken()
        for key, label, _ in STAGES:
            self.stage_rows[key].setText(f"○  {label}")
            self.stage_rows[key].setObjectName("stageTodo")
            self._restyle(self.stage_rows[key])
        self.logview.clear()
        self.peek_box.hide()
        self._peek_pix = None
        self.p_title.setText(f"「{spec.working_title()}」 만드는 중…")
        self.p_sub.setText("AI 팀이 기획하고, 편집하고, 렌더링까지 합니다.")
        self.bar.setValue(0)
        self.p_pct.setText("0%")
        self.pages.setCurrentIndex(1)
        self.t_start = self._t_tick = time.time()
        self.eta_view = EtaDisplay()
        self.tick.start(1000)
        self._current = ""
        self.thread = QThread(self)
        self.worker = Worker(spec, self.settings, self.job_dir, self.cancel)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self._log)
        self.worker.progress.connect(self._on_progress)
        self.worker.preview.connect(self._on_preview)
        self.worker.finished.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._thread_done)
        self.thread.start()
        self._update_ready()

    def _thread_done(self) -> None:
        self.thread = None
        self.tick.stop()
        self._update_ready()

    def _restyle(self, w: QWidget) -> None:
        w.style().unpolish(w)
        w.style().polish(w)

    def _log(self, msg: str) -> None:
        self.logview.appendPlainText(msg)

    def _on_preview(self, path: str, caption: str) -> None:
        pix = QPixmap(path)
        if pix.isNull():   # 렌더러가 아직 쓰는 중이거나 이미 지운 파일
            return
        self._peek_pix = pix
        self.peek_cap.setText(caption)
        self.peek_box.show()
        self._fit_peek()
        QTimer.singleShot(0, self._fit_peek)   # 처음 보일 때는 배치가 끝난 뒤 크기에 맞춤

    def _fit_peek(self) -> None:
        if self._peek_pix is not None and self.peek.width() > 10 and self.peek.height() > 10:
            self.peek.setPixmap(self._peek_pix.scaled(self.peek.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, e) -> None:  # noqa: N802 - Qt
        super().resizeEvent(e)
        if getattr(self, "_peek_pix", None) is not None:
            self._fit_peek()

    def _set_overall(self, overall: float) -> None:
        v = max(self.bar.value(), int(overall * 1000))   # 막대는 뒤로 가지 않게
        self.bar.setValue(v)
        self.p_pct.setText(f"{v / 10:.0f}%")

    def _on_progress(self, key: str, frac: float, overall: float) -> None:
        self._set_overall(overall)
        keys = [k for k, _, _ in STAGES]
        if key in keys:
            idx = keys.index(key)
            for i, (k, label, _) in enumerate(STAGES):
                lab = self.stage_rows[k]
                if i < idx:
                    text, name = f"✓  {label}", "stageDone"
                elif i == idx:
                    text, name = f"●  {label}  {frac * 100:.0f}%", "stageNow"
                else:
                    continue
                if lab.text() != text:
                    lab.setText(text)
                if lab.objectName() != name:
                    lab.setObjectName(name)
                    self._restyle(lab)

    def _tick(self) -> None:
        now = time.time()
        dt, self._t_tick = now - self._t_tick, now
        eta = getattr(self.worker, "eta", None)
        left = self.eta_view.step(eta.remaining() if eta else None, dt)
        if eta is not None and (f := eta.fraction()) is not None:
            self._set_overall(f)
        self.p_sub.setText(f"경과 {fmt_ts(now - self.t_start)} · {fmt_left(left)}")

    def _on_done(self, res: dict) -> None:
        for k, label, _ in STAGES:
            self.stage_rows[k].setText(f"✓  {label}")
        self._show_results(res, elapsed=time.time() - self.t_start)

    def _on_fail(self, msg: str) -> None:
        self.tick.stop()
        self.logview.appendPlainText("\n⚠ " + msg)
        if msg.startswith("취소"):
            self.pages.setCurrentIndex(0)
            return
        QMessageBox.critical(self, "만들지 못했습니다",
                             msg.split("\n\n")[0] + "\n\n아래 'AI 팀 작업 기록'에 자세한 내용이 있습니다. "
                             "같은 입력으로 다시 누르면 끝난 단계는 건너뛰고 이어서 합니다.")
        self.cancel_btn.setText("입력 화면으로")
        self.cancel_btn.clicked.disconnect()
        self.cancel_btn.clicked.connect(self._back_to_input)

    def _back_to_input(self) -> None:
        self.cancel_btn.setText("취소")
        self.cancel_btn.clicked.disconnect()
        self.cancel_btn.clicked.connect(self._cancel)
        self.pages.setCurrentIndex(0)

    def _cancel(self) -> None:
        if self.cancel and QMessageBox.question(self, "취소", "만들기를 멈출까요? 끝난 단계는 저장되어 다음에 이어서 합니다.") \
                == QMessageBox.Yes:
            self.cancel.cancel()

    # ------------------------------------------------------------------
    def _show_results(self, res: dict, elapsed: Optional[float] = None) -> None:
        self.results = res
        while self.r_grid.count():
            it = self.r_grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        title = res.get("title") or ""
        self.r_title.setText(f"완성! 「{title}」" if title else "완성!")
        took = f"걸린 시간 {fmt_ts(elapsed)} · " if elapsed else ""
        self.r_sub.setText(took + "색보정과 음향 마스터링(-14 LUFS)까지 적용했습니다. 올리기 전에 한 번 확인해 보세요. "
                           f"썸네일·자막(.srt)·편집 리포트는 '{EXTRAS}' 폴더에 있습니다.")
        cards = [("롱폼 16:9", res.get("long", ""), False)]
        cards += [(f"숏폼 {i} · 9:16", p, True) for i, p in enumerate(res.get("shorts", []) or [], 1)]
        for i, (t, p, vert) in enumerate(cards):
            self.r_grid.addWidget(ResultCard(t, p, vert), 0, i, Qt.AlignTop)
        extras = Path(res.get("extras") or Path(res.get("output", "")) / EXTRAS)
        thumbs = sorted(extras.glob("썸네일*.jpg")) if extras.exists() else []
        side = QFrame()
        side.setObjectName("panel")
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 14, 14, 14)
        sv.addWidget(_label("썸네일 후보", "panelTitle"))
        for t in thumbs[:3]:
            lab = QLabel()
            lab.setPixmap(QPixmap(str(t)).scaledToWidth(240, Qt.SmoothTransformation))
            lab.setCursor(Qt.PointingHandCursor)
            lab.mousePressEvent = lambda _e, p=str(t): QDesktopServices.openUrl(QUrl.fromLocalFile(p))
            sv.addWidget(lab)
        ba = extras / "색보정_전후.jpg"
        if ba.exists():
            sv.addWidget(_label("색보정 전 | 후", "panelTitle"))
            lab = QLabel()
            lab.setPixmap(QPixmap(str(ba)).scaledToWidth(240, Qt.SmoothTransformation))
            sv.addWidget(lab)
        sv.addStretch(1)
        self.r_grid.addWidget(side, 0, len(cards), Qt.AlignTop)
        self.r_grid.setColumnStretch(len(cards) + 1, 1)
        self.r_upload.setEnabled(bool(res.get("upload_info")))
        self.pages.setCurrentIndex(2)

    def _new(self) -> None:
        self.pages.setCurrentIndex(0)

    def _open(self, p: str) -> None:
        if p and Path(p).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    # ------------------------------------------------------------------
    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        base = Path(self.settings.projects_dir)
        jobs = sorted([d for d in base.glob("*") if d.is_dir() and not d.name.startswith("_")],
                      key=lambda d: d.stat().st_mtime, reverse=True)[:15] if base.exists() else []
        if not jobs:
            self.recent_menu.addAction("아직 만든 영상이 없습니다").setEnabled(False)
            return
        for d in jobs:
            res = read_json(d / "work" / "result.json", {})
            if res.get("long") or res.get("shorts"):
                self.recent_menu.addAction(f"✓  {res.get('title') or d.name}", lambda r=res: self._show_results(r))
            else:
                self.recent_menu.addAction(f"…  {d.name}  (이어서 만들기)", lambda j=d: self._resume(j))
        self.recent_menu.addSeparator()
        self.recent_menu.addAction("작업 폴더 열기", lambda: self._open(str(base)))

    def _resume(self, job: Path) -> None:
        data = read_json(job / "job.json", {})
        if not data.get("video"):
            QMessageBox.information(self, "이어서 만들기", "이 작업의 입력 정보를 찾지 못했습니다.")
            return
        spec = JobSpec.from_dict(data)
        self.topic.setPlainText(spec.topic_text)
        self.script.setPlainText(spec.script)
        self.video.set_path(spec.video)
        self._start(job_dir=job, spec=spec)

    # ------------------------------------------------------------------
    def _probe_ai(self) -> None:
        run_bg(self, lambda: ai_status_text(self.settings), self._on_ai)

    def _on_ai(self, res) -> None:
        if isinstance(res, Exception):
            self.ai_chip.setText("AI 연결 확인 실패")
            return
        text, ok = res
        self._ai_ok = ok
        self.ai_chip.setText(("●  " if ok else "○  ") + text + ("" if ok else "  — 눌러서 연결"))
        self.ai_chip.setProperty("ok", ok)
        self._restyle(self.ai_chip)

    def _on_chip(self) -> None:
        if getattr(self, "_ai_ok", False):
            self._open_settings()
            return
        exe = find_claude(self.settings.claude_code_path)
        if exe:
            open_login(exe)
            QMessageBox.information(self, "Claude 로그인", "브라우저에서 Claude(Pro/Max) 계정으로 로그인한 뒤 확인을 누르세요.")
            self._probe_ai()
        else:
            self._open_settings()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            self.settings = Settings.load()
            self._probe_ai()

    def closeEvent(self, e):  # noqa: N802
        if self.thread is not None:
            if QMessageBox.question(self, "종료", "아직 만드는 중입니다. 멈추고 닫을까요?(끝난 단계는 저장됩니다)") \
                    != QMessageBox.Yes:
                e.ignore()
                return
            if self.cancel:
                self.cancel.cancel()
        self._save_inputs()
        wait_bg()
        super().closeEvent(e)


def run_gui() -> int:
    ensure_user_dirs()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Choi Studio")
    theme.apply(app, Settings.load().brand.accent)
    w = MainWindow()
    w.show()
    return app.exec()
