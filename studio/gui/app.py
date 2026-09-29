"""Choi Studio 메인 창 — 편집 툴 구조(프리미어 프로식 도킹 패널).

┌ 헤더: ☰ 메뉴 · 로고 · 작업 공간(편집 / 검토 / 결과) · AI 연결 상태 · [편집 계획만] [▶ 전체 제작] ┐
│ 스크립트(대본·메모·편집 지시) │        프로그램 모니터        │ 인스펙터(출력·자막·AI·오디오) │
│ 프로젝트(시퀀스·미디어·최근)   ├────────── 타임라인 ──────────┤ AI 팀 · 콘솔 · 결과물         │
└ 상태 표시줄: 단계 · 진행률 · 스톡 ──────────────────────────────────────────────────────┘
패널은 끌어서 옮기거나 탭으로 합칠 수 있고, 배치는 저장된다(☰ → 보기 → 레이아웃 초기화).
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QSettings, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QDockWidget, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QToolButton, QVBoxLayout, QWidget)

from .. import __version__
from ..director.claude_code import auth_status, describe_auth, find_claude, open_login, resolve_backend
from ..paths import ROOT, USER_DIR, ensure_user_dirs
from ..pipeline import STAGES, JobSpec, Pipeline, new_job_dir
from ..settings import Settings
from ..util import CancelToken, Cancelled, read_json, write_json
from . import theme
from .monitor import ProgramMonitor
from .panels import (LONG_PRESETS, SHORT_PRESETS, ConsolePanel, ExportsPanel, InspectorPanel, ProjectPanel,
                     ScriptPanel, TeamPanel)
from .settings_dialog import SettingsDialog
from .timeline import TimelineData, TimelineView

LAST_JOB = USER_DIR / "last_job.json"
TEXT_FILTER = "텍스트 (*.txt *.md);;모든 파일 (*)"
LAYOUT_VERSION = 2


class Worker(QObject):
    log = Signal(str)
    progress = Signal(str, float, float)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, spec: JobSpec, settings: Settings, job_dir: Path, until: str, cancel: CancelToken):
        super().__init__()
        self.spec, self.settings, self.job_dir, self.until, self.cancel = spec, settings, job_dir, until, cancel

    def run(self) -> None:
        try:
            p = Pipeline(self.spec, self.settings, self.job_dir, log=self.log.emit,
                         progress=lambda k, f, o: self.progress.emit(k, f, o), cancel=self.cancel)
            res = p.run(until=self.until)
            res["until"] = self.until
            self.finished.emit(res)
        except Cancelled:
            self.failed.emit("사용자가 취소했습니다.")
        except Exception as e:  # noqa: BLE001 - 모든 오류를 창에 표시
            self.failed.emit(f"{e}\n\n{traceback.format_exc()[-2500:]}")


class _AIProbe(QObject):
    """AI 연결 상태 확인(Claude Code 로그인 여부) — 창이 멈추지 않도록 별도 스레드."""

    done = Signal(str)

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

    def run(self) -> None:
        backend, why = resolve_backend(self.settings)
        if backend == "claude_code":
            exe = find_claude(self.settings.claude_code_path)
            self.done.emit(f"Claude Code · {describe_auth(auth_status(exe)) if exe else '없음'}")
        elif backend == "api":
            self.done.emit("Claude API 키 · 종량제")
        else:
            self.done.emit(f"AI 없음 · {why}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings.load()
        self.accent = self.settings.brand.accent
        self.setWindowTitle(f"Choi Studio {__version__}")
        self.resize(1600, 960)
        self.job_dir: Optional[Path] = None
        self.cancel: Optional[CancelToken] = None
        self.thread: Optional[QThread] = None
        self._build()
        self._restore()
        QTimer.singleShot(200, self._probe_ai)

    # ------------------------------------------------------------------
    def _dock(self, title: str, name: str, widget: QWidget, area) -> QDockWidget:
        d = QDockWidget(title, self)
        d.setObjectName(name)
        d.setWidget(widget)
        d.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable)
        self.addDockWidget(area, d)
        return d

    def _build(self) -> None:
        self.setDockOptions(QMainWindow.AnimatedDocks | QMainWindow.AllowTabbedDocks | QMainWindow.AllowNestedDocks)
        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)

        # 가운데: 프로그램 모니터
        self.monitor = ProgramMonitor()
        central = QWidget()
        central.setObjectName("root")
        cv = QVBoxLayout(central)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        cap = QLabel("  프로그램 모니터")
        cap.setStyleSheet(f"background:{theme.BG2}; color:{theme.TEXT2}; font-weight:600; padding:7px 4px;"
                          f"border-bottom:1px solid {theme.LINE};")
        cv.addWidget(cap)
        cv.addWidget(self.monitor, 1)
        self.setCentralWidget(central)
        self.setMenuWidget(self._header())

        # 패널
        self.project = ProjectPanel()
        self.script = ScriptPanel()
        self.inspector = InspectorPanel()
        self.team = TeamPanel()
        self.console = ConsolePanel()
        self.exports = ExportsPanel()
        self.timeline = TimelineView(self.accent)
        self.d_script = self._dock("스크립트", "dock_script", self.script, Qt.LeftDockWidgetArea)
        self.d_project = self._dock("프로젝트", "dock_project", self.project, Qt.LeftDockWidgetArea)
        self.d_inspector = self._dock("인스펙터", "dock_inspector", self.inspector, Qt.RightDockWidgetArea)
        self.d_team = self._dock("AI 팀", "dock_team", self.team, Qt.RightDockWidgetArea)
        self.d_console = self._dock("콘솔", "dock_console", self.console, Qt.RightDockWidgetArea)
        self.d_exports = self._dock("결과물", "dock_exports", self.exports, Qt.RightDockWidgetArea)
        self.d_timeline = self._dock("타임라인", "dock_timeline", self.timeline, Qt.BottomDockWidgetArea)
        self.splitDockWidget(self.d_script, self.d_project, Qt.Vertical)
        self.splitDockWidget(self.d_inspector, self.d_team, Qt.Vertical)
        self.tabifyDockWidget(self.d_team, self.d_console)
        self.tabifyDockWidget(self.d_console, self.d_exports)
        self.d_team.raise_()
        self.resizeDocks([self.d_script, self.d_inspector], [380, 360], Qt.Horizontal)
        self.resizeDocks([self.d_script, self.d_project], [360, 440], Qt.Vertical)
        self.resizeDocks([self.d_inspector, self.d_team], [470, 330], Qt.Vertical)
        self.resizeDocks([self.d_timeline], [300], Qt.Vertical)
        self._default_state = self.saveState(LAYOUT_VERSION)

        # 연결
        self.project.open_job.connect(self._load_job_dir)
        self.project.video.changed.connect(lambda _p: self._refresh_sources())
        self.script.load_script.connect(self._load_script)
        self.script.open_guide.connect(lambda: self._open_path(ROOT / "docs" / "대본_태그_가이드.md"))
        self.inspector.open_settings.connect(self._open_settings)
        self.monitor.position.connect(self._on_monitor_pos)
        self.timeline.seek.connect(self._on_timeline_seek)
        self.exports.play.connect(lambda p: self.monitor.set_sources(self._sources(), prefer=p))
        self.exports.open_file.connect(lambda p: self._open_path(Path(p)))
        self.exports.open_folder.connect(self._open_output)

        self._menus()
        self._statusbar()
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self._space)

    def _header(self) -> QWidget:
        w = QWidget()
        w.setObjectName("header")
        h = QHBoxLayout(w)
        h.setContentsMargins(8, 6, 12, 6)
        h.setSpacing(6)
        self.menu_btn = QToolButton()
        self.menu_btn.setText("☰")
        self.menu_btn.setToolTip("메뉴 — 파일 · 제작 · 보기 · 도구 · 도움말")
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.menu_btn.setStyleSheet("font-size:16px; padding:3px 9px;")
        h.addWidget(self.menu_btn)
        dot = QLabel("●")
        dot.setObjectName("brandDot")
        brand = QLabel("CHOI STUDIO")
        brand.setObjectName("brand")
        h.addWidget(dot)
        h.addWidget(brand)
        h.addSpacing(18)
        self.ws_group = QButtonGroup(self)
        for i, (name, tip) in enumerate([("편집", "대본·미디어·옵션을 넣고 제작"),
                                         ("검토", "모니터와 타임라인을 크게 — AI 편집 결과 확인"),
                                         ("결과", "결과물 · AI 팀 · 콘솔")]):
            b = QPushButton(name)
            b.setObjectName("workspace")
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setChecked(i == 0)
            self.ws_group.addButton(b, i)
            h.addWidget(b)
        self.ws_group.idClicked.connect(self._workspace)
        h.addStretch(1)
        self.ai_chip = QLabel("AI 연결 확인 중…")
        self.ai_chip.setObjectName("chip")
        self.ai_chip.setToolTip("AI 연결 — ☰ → 도구 → 환경 설정에서 바꿉니다")
        h.addWidget(self.ai_chip)
        h.addSpacing(10)
        self.b_plan = QPushButton("편집 계획만")
        self.b_plan.setToolTip("음성 인식·정렬·AI 편집 계획까지만 하고 멈춥니다. 타임라인에서 검토한 뒤 전체 제작\n"
                               "(Ctrl+Shift+Enter)")
        self.b_plan.clicked.connect(lambda: self._start("plan"))
        self.b_run = QPushButton("▶  전체 제작")
        self.b_run.setObjectName("primary")
        self.b_run.setToolTip("롱폼 · 숏폼 · 썸네일 · 자막 · 프리미어 XML 까지 끝까지 자동 제작 (Ctrl+Enter)")
        self.b_run.clicked.connect(lambda: self._start("all"))
        self.b_cancel = QPushButton("취소")
        self.b_cancel.setEnabled(False)
        self.b_cancel.clicked.connect(self._cancel)
        for b in (self.b_plan, self.b_run, self.b_cancel):
            h.addWidget(b)
        return w

    def _menus(self) -> None:
        menu = QMenu(self)
        m_file = menu.addMenu("파일")
        self._act(m_file, "작업 폴더 열기…", self._open_job, "Ctrl+O")
        self._act(m_file, "대본 파일 불러오기…", self._load_script)
        m_file.addSeparator()
        self._act(m_file, "결과 폴더 열기", self._open_output)
        self._act(m_file, "편집 계획 열기(plan.json)", self._open_plan)
        m_file.addSeparator()
        self._act(m_file, "종료", self.close, "Ctrl+Q")
        m_run = menu.addMenu("제작")
        self._act(m_run, "편집 계획만", lambda: self._start("plan"), "Ctrl+Shift+Return")
        self._act(m_run, "전체 제작", lambda: self._start("all"), "Ctrl+Return")
        self._act(m_run, "취소", self._cancel)
        m_run.addSeparator()
        self._act(m_run, "Remotion Studio 에서 미리보기", self._preview)
        m_view = menu.addMenu("보기")
        for d in (self.d_script, self.d_project, self.d_inspector, self.d_timeline, self.d_team, self.d_console,
                  self.d_exports):
            m_view.addAction(d.toggleViewAction())
        m_view.addSeparator()
        self._act(m_view, "레이아웃 초기화", lambda: self.restoreState(self._default_state, LAYOUT_VERSION))
        m_tools = menu.addMenu("도구")
        self._act(m_tools, "환경 설정…", self._open_settings, "Ctrl+,")
        self._act(m_tools, "Claude 로그인(구독 계정)", self._claude_login)
        m_help = menu.addMenu("도움말")
        self._act(m_help, "사용 설명서", lambda: self._open_path(ROOT / "README.md"))
        self._act(m_help, "대본 태그 가이드", lambda: self._open_path(ROOT / "docs" / "대본_태그_가이드.md"))
        self._act(m_help, "AI 스튜디오 설명", lambda: self._open_path(ROOT / "docs" / "AI_스튜디오.md"))
        self._act(m_help, "스톡 API 가이드", lambda: self._open_path(ROOT / "docs" / "스톡_API_가이드.md"))
        m_help.addSeparator()
        self._act(m_help, "Choi Studio 정보", lambda: QMessageBox.about(
            self, "Choi Studio", f"<b>Choi Studio {__version__}</b><br>디자인 이론 교육 영상 자동 편집기<br><br>"
                                 "faster-whisper · Claude · Remotion · FFmpeg"))
        self.menu_btn.setMenu(menu)

    def _act(self, menu, text: str, slot, shortcut: str = "") -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            a.setShortcutContext(Qt.ApplicationShortcut)
            self.addAction(a)
        a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def _statusbar(self) -> None:
        sb = self.statusBar()
        self.stage_label = QLabel("  준비")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setFixedWidth(260)
        self.stock_chip = QLabel("")
        self.stock_chip.setObjectName("hint")
        sb.addWidget(self.stage_label, 1)
        sb.addPermanentWidget(self.stock_chip)
        sb.addPermanentWidget(self.bar)
        self._refresh_chips()

    def _refresh_chips(self) -> None:
        s = self.settings
        names = [n for n, k in (("Pixabay", s.pixabay_api_key), ("Unsplash", s.unsplash_access_key),
                                ("Coverr", s.coverr_api_key), ("Pexels", s.pexels_api_key)) if k]
        self.stock_chip.setText("스톡  " + (" · ".join(names) if names else "키 없음") + "   ")

    # ------------------------------------------------------------------
    def _workspace(self, i: int) -> None:
        self.restoreState(self._default_state, LAYOUT_VERSION)
        if i == 1:     # 검토: 모니터·타임라인
            for d in (self.d_script, self.d_project, self.d_inspector):
                d.hide()
            self.resizeDocks([self.d_timeline], [340], Qt.Vertical)
        elif i == 2:   # 결과: 결과물·AI 팀·콘솔
            self.d_script.hide()
            self.d_exports.raise_()
            self.resizeDocks([self.d_inspector], [480], Qt.Horizontal)

    def _probe_ai(self) -> None:
        self._probe_thread = QThread(self)
        self._probe_worker = _AIProbe(self.settings)
        self._probe_worker.moveToThread(self._probe_thread)
        self._probe_thread.started.connect(self._probe_worker.run)
        self._probe_worker.done.connect(self._on_ai_probe)
        self._probe_worker.done.connect(self._probe_thread.quit)
        self._probe_thread.start()

    def _on_ai_probe(self, text: str) -> None:
        ok = ("로그인됨" in text and "API 키(종량제" not in text) or text.startswith("Claude API")
        self.ai_chip.setText(("●  " if ok else "○  ") + text)
        self.ai_chip.setStyleSheet(f"color:{'#4CAF7A' if ok else '#E0A030'};")
        self.inspector.ai_status.setText(text)
        if not ok:
            self.console.log("ℹ AI 연결: " + text + " — ☰ → 도구 → Claude 로그인(구독 계정), 또는 환경 설정")

    # ------------------------------------------------------------------
    def _spec(self) -> JobSpec:
        pj, ins, sc = self.project, self.inspector, self.script
        heights = [1080, 1440, 2160]
        paces = ["calm", "normal", "fast"]
        return JobSpec(
            video=pj.video.text().strip(), title=pj.title.text().strip(), audio=pj.audio.text().strip(),
            episode=pj.episode.text().strip(), subtitle=pj.subtitle.text().strip(), series=pj.series.text().strip(),
            notes=sc.notes.toPlainText(), script=sc.script.toPlainText(), images_dir=pj.images.text().strip(),
            bgm=pj.bgm.text().strip(), lut=pj.lut.text().strip(),
            make_long=ins.make_long.isChecked(), shorts_count=ins.shorts.value(), short_max_sec=ins.short_len.value(),
            out_height=heights[ins.height_box.currentIndex()], pace=paces[ins.pace.currentIndex()],
            use_claude=ins.use_claude.isChecked(), fetch_broll=ins.fetch_broll.isChecked(), grain=ins.grain.isChecked(),
            caption_preset=LONG_PRESETS[ins.caption_style.currentIndex()],
            short_caption_preset=SHORT_PRESETS[ins.short_caption.currentIndex()],
            studio_mode=ins.studio_mode.isChecked(), fetch_stock=ins.fetch_stock.isChecked(),
            motion_scenes=ins.motion_scenes.isChecked(), qa_rounds=ins.qa_rounds.value(),
            direction=sc.direction.toPlainText().strip(), thumbnails=ins.thumbs.isChecked(), sfx=ins.sfx.isChecked(),
            enhance_voice=ins.enhance.isChecked(), shorts_layout=["full", "framed"][ins.shorts_layout.currentIndex()],
            progress_bar=ins.progress_bar.isChecked(), endcard=ins.endcard.isChecked(),
            reuse_plan=ins.reuse.isChecked(), export_xml=ins.xml.isChecked())

    def _apply_spec(self, s: JobSpec) -> None:
        pj, ins, sc = self.project, self.inspector, self.script
        pj.video.setText(s.video)
        pj.audio.setText(s.audio)
        pj.title.setText(s.title)
        pj.episode.setText(s.episode)
        pj.subtitle.setText(s.subtitle)
        pj.series.setText(s.series)
        pj.images.setText(s.images_dir)
        pj.bgm.setText(s.bgm)
        pj.lut.setText(s.lut)
        sc.notes.setPlainText(s.notes)
        sc.script.setPlainText(s.script)
        sc.direction.setPlainText(s.direction)
        ins.make_long.setChecked(s.make_long)
        ins.shorts.setValue(s.shorts_count)
        ins.short_len.setValue(max(25, min(60, s.short_max_sec)))
        ins.height_box.setCurrentIndex({1080: 0, 1440: 1, 2160: 2}.get(s.out_height, 0))
        ins.pace.setCurrentIndex({"calm": 0, "normal": 1, "fast": 2}.get(s.pace, 0))
        ins.use_claude.setChecked(s.use_claude)
        ins.fetch_broll.setChecked(s.fetch_broll)
        ins.grain.setChecked(s.grain)
        ins.caption_style.setCurrentIndex(LONG_PRESETS.index(s.caption_preset)
                                          if s.caption_preset in LONG_PRESETS else 0)
        ins.short_caption.setCurrentIndex(SHORT_PRESETS.index(s.short_caption_preset)
                                          if s.short_caption_preset in SHORT_PRESETS else 0)
        ins.studio_mode.setChecked(s.studio_mode)
        ins.fetch_stock.setChecked(s.fetch_stock)
        ins.motion_scenes.setChecked(s.motion_scenes)
        ins.qa_rounds.setValue(max(0, min(3, s.qa_rounds)))
        ins.thumbs.setChecked(s.thumbnails)
        ins.sfx.setChecked(s.sfx)
        ins.enhance.setChecked(s.enhance_voice)
        ins.shorts_layout.setCurrentIndex(0 if s.shorts_layout == "full" else 1)
        ins.progress_bar.setChecked(s.progress_bar)
        ins.endcard.setChecked(s.endcard)
        ins.reuse.setChecked(s.reuse_plan)
        ins.xml.setChecked(s.export_xml)

    def _restore(self) -> None:
        st = QSettings(str(USER_DIR / "ui.ini"), QSettings.IniFormat)
        geo, state = st.value("geometry"), st.value("state")
        if geo is not None:
            self.restoreGeometry(geo)
        if state is not None:
            self.restoreState(state, LAYOUT_VERSION)
        d = read_json(LAST_JOB, None)
        if d and d.get("spec"):
            try:
                self._apply_spec(JobSpec.from_dict(d["spec"]))
                jd = d.get("job_dir")
                if jd and Path(jd).exists():
                    self._set_job(Path(jd))
            except (TypeError, KeyError):
                pass
        self.project.refresh_recent(self.settings.projects_dir)
        s = self.settings
        if not any([s.pixabay_api_key, s.unsplash_access_key, s.coverr_api_key, s.pexels_api_key]):
            self.console.log("ℹ 환경 설정 → 스톡 탭에 Pixabay API 키(무료)를 넣으면 🎞 스톡 영상·사진을 자동으로 찾아 넣습니다.")
        self._refresh_sources()

    def closeEvent(self, e):  # noqa: N802
        ensure_user_dirs()
        st = QSettings(str(USER_DIR / "ui.ini"), QSettings.IniFormat)
        st.setValue("geometry", self.saveGeometry())
        st.setValue("state", self.saveState(LAYOUT_VERSION))
        super().closeEvent(e)

    # ------------------------------------------------------------------
    def _set_job(self, job_dir: Optional[Path]) -> None:
        self.job_dir = job_dir
        self.timeline.set_data(TimelineData.load(job_dir))
        self.exports.refresh(job_dir)
        self._refresh_sources()
        self.setWindowTitle(f"Choi Studio {__version__} — {job_dir.name if job_dir else '새 작업'}")

    def _sources(self) -> list[tuple[str, str, bool]]:
        items: list[tuple[str, str, bool]] = []
        if self.job_dir and (self.job_dir / "output").exists():
            for f in sorted((self.job_dir / "output").glob("*.mp4")):
                long = "롱폼" in f.name
                items.append((("롱폼 결과 · " if long else "숏폼 · ") + f.name, str(f), long))
        v = self.project.video.text().strip()
        if v:
            items.append(("원본 · " + Path(v).name, v, False))
        return items

    def _refresh_sources(self) -> None:
        self.monitor.set_sources(self._sources())

    def _on_monitor_pos(self, t: float, edit_time: bool) -> None:
        if edit_time:
            self.timeline.set_playhead(t)

    def _on_timeline_seek(self, t: float) -> None:
        if self.monitor.current_is_edit():
            self.monitor.seek(t)

    def _space(self) -> None:
        if isinstance(QApplication.focusWidget(), (QLineEdit, QPlainTextEdit)):
            return
        self.monitor.toggle()

    # ------------------------------------------------------------------
    def _start(self, until: str) -> None:
        if self.thread is not None and self.thread.isRunning():
            return
        spec = self._spec()
        if not spec.video or not Path(spec.video).exists():
            QMessageBox.warning(self, "확인", "프로젝트 패널에 원본 영상을 넣어 주세요.")
            return
        if not spec.title:
            QMessageBox.warning(self, "확인", "프로젝트 패널 → 시퀀스 → 제목을 입력하세요.")
            return
        self.settings = Settings.load()
        same = False
        if self.job_dir and (self.job_dir / "job.json").exists():
            prev = read_json(self.job_dir / "job.json", {})
            same = prev.get("video") == spec.video and prev.get("title") == spec.title
        if not same:
            self.job_dir = new_job_dir(self.settings, spec.title)
        ensure_user_dirs()
        write_json(LAST_JOB, {"spec": spec.to_dict(), "job_dir": str(self.job_dir)})
        self.console.log(f"\n▶ 작업 폴더: {self.job_dir}")
        self.team.reset()
        self.d_team.raise_()
        self.cancel = CancelToken()
        self.thread = QThread()
        self.worker = Worker(spec, self.settings, self.job_dir, until, self.cancel)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self._log)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self._busy(True)
        self.thread.start()

    def _log(self, msg: str) -> None:
        self.console.log(msg)
        self.team.on_log(msg)

    def _busy(self, on: bool) -> None:
        self.b_run.setEnabled(not on)
        self.b_plan.setEnabled(not on)
        self.b_cancel.setEnabled(on)

    def _on_progress(self, key: str, frac: float, overall: float) -> None:
        self.bar.setValue(int(overall * 1000))
        label = dict((k, v) for k, v, _ in STAGES).get(key, key)
        self.stage_label.setText(f"  {label}  {frac * 100:.0f}%   ·   전체 {overall * 100:.0f}%")
        self.team.on_progress(key, frac)

    def _on_done(self, res: dict) -> None:
        self._busy(False)
        self.bar.setValue(1000)
        plan_only = res.get("until") == "plan"
        self.stage_label.setText("  편집 계획 완료 — 타임라인을 검토하세요" if plan_only else "  완료")
        self.console.log(f"✔ 완료 → {res.get('output')}")
        self._set_job(self.job_dir)
        self.project.refresh_recent(self.settings.projects_dir)
        if plan_only:
            self.ws_group.button(1).click()
        else:
            self.ws_group.button(2).click()
            longs = [s for s in self._sources() if s[2]]
            if longs:
                self.monitor.set_sources(self._sources(), prefer=longs[0][1])

    def _on_fail(self, msg: str) -> None:
        self._busy(False)
        self.stage_label.setText("  중단됨")
        self.console.log("✖ " + msg)
        self.d_console.raise_()
        QMessageBox.critical(self, "오류", msg[:1500])

    def _cancel(self) -> None:
        if self.cancel:
            self.cancel.cancel()
            self.console.log("취소 요청…")

    # ------------------------------------------------------------------
    def _open_settings(self) -> None:
        dlg = SettingsDialog(Settings.load(), self)
        if dlg.exec():
            self.settings = Settings.load()
            theme.apply(QApplication.instance(), self.settings.brand.accent)
            self._refresh_chips()
            self._probe_ai()
            self.console.log("환경 설정 저장됨")

    def _claude_login(self) -> None:
        exe = find_claude(self.settings.claude_code_path)
        if not exe:
            QMessageBox.information(self, "Claude Code", "Claude Code 가 설치되어 있지 않습니다.\n"
                                                         "setup_windows.bat 을 다시 실행하면 설치와 로그인을 함께 진행합니다.")
            return
        open_login(exe)
        self.console.log("브라우저에서 Claude 구독 계정으로 로그인하세요. 끝나면 헤더의 AI 상태가 자동으로 갱신됩니다.")
        QTimer.singleShot(20000, self._probe_ai)
        QTimer.singleShot(60000, self._probe_ai)

    def _load_script(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "대본 파일", "", TEXT_FILTER)
        if p:
            for enc in ("utf-8", "cp949", "utf-16"):
                try:
                    self.script.script.setPlainText(Path(p).read_text(encoding=enc))
                    self.script.tabs.setCurrentIndex(0)
                    return
                except UnicodeDecodeError:
                    continue

    def _open_job(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "작업 폴더 선택", self.settings.projects_dir)
        if d:
            self._load_job_dir(d)

    def _load_job_dir(self, d: str) -> None:
        data = read_json(Path(d) / "job.json", None)
        if not data:
            QMessageBox.warning(self, "확인", "job.json 이 없는 폴더입니다.")
            return
        self._apply_spec(JobSpec.from_dict(data))
        self._set_job(Path(d))
        self.console.log(f"작업 불러옴: {d}  (전체 제작을 누르면 분석 결과를 재사용해 다시 렌더합니다)")

    def _open_path(self, p: Path) -> None:
        if not p.exists():
            QMessageBox.information(self, "안내", f"아직 없습니다: {p}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def _open_output(self) -> None:
        if self.job_dir:
            self._open_path(self.job_dir / "output")

    def _open_plan(self) -> None:
        if not self.job_dir:
            return
        out = self.job_dir / "output" / "plan.json"
        work = self.job_dir / "work" / "plan.json"
        if not out.exists() and work.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(work.read_bytes())
        self._open_path(out)

    def _preview(self) -> None:
        if not self.job_dir:
            return
        from ..render.remotion import find_node, open_studio
        pub = self.job_dir / "render" / "bundle" / "public"
        props = self.job_dir / "render" / "props_long.json"
        if not pub.exists() or not props.exists():
            QMessageBox.information(self, "안내", "한 번 이상 렌더한 작업에서 미리보기를 열 수 있습니다.")
            return
        try:
            open_studio(pub, props, find_node(self.settings.node_path))
            self.console.log("Remotion Studio 를 여는 중… 브라우저에서 http://localhost:3000")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "오류", str(e))


def run_gui() -> int:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
    app = QApplication(sys.argv)
    app.setApplicationName("Choi Studio")
    theme.apply(app, Settings.load().brand.accent)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
