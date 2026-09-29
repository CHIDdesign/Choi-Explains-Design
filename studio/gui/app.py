"""데스크톱 창(PySide6). 입력 → 옵션 → 실행/진행/로그 → 결과 폴더."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QScrollArea, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..paths import ROOT, USER_DIR, ensure_user_dirs
from ..pipeline import STAGES, JobSpec, Pipeline, new_job_dir
from ..settings import Settings
from ..util import CancelToken, Cancelled, read_json, write_json

LAST_JOB = USER_DIR / "last_job.json"
VIDEO_FILTER = "영상 (*.mp4 *.mov *.mkv *.m4v *.avi *.mts *.MP4 *.MOV);;모든 파일 (*)"
AUDIO_FILTER = "오디오 (*.wav *.mp3 *.m4a *.aac *.flac);;모든 파일 (*)"
TEXT_FILTER = "텍스트 (*.txt *.md);;모든 파일 (*)"


def _qss(accent: str) -> str:
    return f"""
    QWidget {{ background: #121212; color: #EDEDED; font-size: 13px; }}
    QLabel#title {{ font-size: 20px; font-weight: 800; letter-spacing: -0.5px; }}
    QLabel#sub {{ color: #9A9A9A; }}
    QLabel#stage {{ color: #CFCFCF; font-weight: 600; }}
    QGroupBox {{ border: 1px solid #2A2A2A; border-radius: 6px; margin-top: 14px; padding: 10px 10px 8px 10px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #BDBDBD; font-weight: 700; }}
    QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{ background: #1C1C1C; border: 1px solid #333; border-radius: 4px;
        padding: 5px; selection-background-color: {accent}; }}
    QLineEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {accent}; }}
    QPushButton {{ background: #242424; border: 1px solid #3A3A3A; border-radius: 4px; padding: 6px 12px; }}
    QPushButton:hover {{ border-color: #6A6A6A; }}
    QPushButton#primary {{ background: {accent}; border: none; color: #111; font-weight: 800; padding: 9px 18px; }}
    QPushButton#primary:disabled {{ background: #553; color: #888; }}
    QProgressBar {{ background: #1C1C1C; border: 1px solid #333; border-radius: 3px; height: 14px; text-align: center; }}
    QProgressBar::chunk {{ background: {accent}; }}
    QTabWidget::pane {{ border: 1px solid #2A2A2A; }}
    QTabBar::tab {{ background: #1A1A1A; padding: 7px 14px; border: 1px solid #2A2A2A; }}
    QTabBar::tab:selected {{ background: #242424; color: #fff; }}
    QCheckBox::indicator:checked {{ background: {accent}; border: 1px solid {accent}; }}
    QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid #555; background: #1C1C1C; }}
    """


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
            self.finished.emit(res)
        except Cancelled:
            self.failed.emit("사용자가 취소했습니다.")
        except Exception as e:  # noqa: BLE001 - 모든 오류를 창에 표시
            self.failed.emit(f"{e}\n\n{traceback.format_exc()[-2500:]}")


class SettingsDialog(QDialog):
    def __init__(self, s: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.resize(640, 640)
        self.s = s
        tabs = QTabWidget()
        # --- AI
        ai = QWidget()
        f = QFormLayout(ai)
        self.key = QLineEdit(s.anthropic_api_key)
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("sk-ant-...  (console.anthropic.com 에서 발급)")
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(["claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1"])
        self.model.setCurrentText(s.claude_model)
        self.effort = QComboBox()
        self.effort.addItems(["low", "medium", "high", "xhigh", "max"])
        self.effort.setCurrentText(s.claude_effort)
        self.whisper = QComboBox()
        self.whisper.setEditable(True)
        self.whisper.addItems(["large-v3", "large-v3-turbo", "medium"])
        self.whisper.setCurrentText(s.whisper_model)
        self.device = QComboBox()
        self.device.addItems(["auto", "cuda", "cpu"])
        self.device.setCurrentText(s.whisper_device)
        f.addRow("Claude API 키", self.key)
        f.addRow("Claude 모델", self.model)
        f.addRow("사고 강도(effort)", self.effort)
        f.addRow("Whisper 모델", self.whisper)
        f.addRow("Whisper 장치", self.device)
        hint = QLabel("· large-v3: 가장 정확(첫 실행 시 약 3GB 다운로드)\n· large-v3-turbo: 약 3~4배 빠름, 정확도 약간 낮음")
        hint.setObjectName("sub")
        f.addRow("", hint)
        tabs.addTab(ai, "AI")
        # --- 브랜드
        br = QWidget()
        f2 = QFormLayout(br)
        b = s.brand
        self.b_name = QLineEdit(b.name)
        self.b_short = QLineEdit(b.short_name)
        self.b_presenter = QLineEdit(b.presenter)
        self.b_ptitle = QLineEdit(b.presenter_title)
        self.b_year = QLineEdit(b.year)
        self.b_accent = QPushButton(b.accent)
        self.b_accent.setStyleSheet(f"background:{b.accent}; color:#111; font-weight:700;")
        self.b_accent.clicked.connect(self._pick_color)
        f2.addRow("채널명(영문 러닝헤더)", self.b_name)
        f2.addRow("짧은 이름", self.b_short)
        f2.addRow("화자 이름", self.b_presenter)
        f2.addRow("화자 소개", self.b_ptitle)
        f2.addRow("연도", self.b_year)
        f2.addRow("강조색", self.b_accent)
        tabs.addTab(br, "브랜드")
        # --- 용어 사전
        gl = QWidget()
        v = QVBoxLayout(gl)
        lab = QLabel("음성인식 교정 사전: 한 줄에 하나씩  틀린말=맞는말")
        lab.setObjectName("sub")
        self.glossary = QPlainTextEdit("\n".join(f"{k}={v2}" for k, v2 in s.glossary.items()))
        v.addWidget(lab)
        v.addWidget(self.glossary)
        tabs.addTab(gl, "용어 사전")
        # --- 경로/렌더
        pa = QWidget()
        f3 = QFormLayout(pa)
        self.projects = QLineEdit(s.projects_dir)
        self.ffmpeg = QLineEdit(s.ffmpeg_path)
        self.ffmpeg.setPlaceholderText("비우면 자동 탐색(PATH / winget)")
        self.node = QLineEdit(s.node_path)
        self.node.setPlaceholderText("비우면 자동 탐색")
        self.browser = QLineEdit(s.render.browser_executable)
        self.browser.setPlaceholderText("비우면 Remotion 이 자동 설치")
        self.concurrency = QSpinBox()
        self.concurrency.setRange(0, 32)
        self.concurrency.setValue(s.render.concurrency)
        self.concurrency.setSpecialValueText("자동")
        self.crf = QSpinBox()
        self.crf.setRange(10, 30)
        self.crf.setValue(s.render.crf)
        self.wm = QLineEdit(s.wikimedia_contact)
        self.wm.setPlaceholderText("위키미디어 API 예절: 연락처(이메일/URL) 권장")
        f3.addRow("작업 저장 폴더", self.projects)
        f3.addRow("ffmpeg 경로", self.ffmpeg)
        f3.addRow("Node.js 경로", self.node)
        f3.addRow("Chrome 경로", self.browser)
        f3.addRow("렌더 동시 작업 수", self.concurrency)
        f3.addRow("CPU 인코딩 CRF", self.crf)
        f3.addRow("위키미디어 연락처", self.wm)
        tabs.addTab(pa, "경로·렌더")
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(bb)

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(self.b_accent.text()), self, "강조색")
        if c.isValid():
            self.b_accent.setText(c.name().upper())
            self.b_accent.setStyleSheet(f"background:{c.name()}; color:#111; font-weight:700;")

    def _save(self) -> None:
        s = self.s
        s.anthropic_api_key = self.key.text().strip()
        s.claude_model = self.model.currentText().strip()
        s.claude_effort = self.effort.currentText()
        s.whisper_model = self.whisper.currentText().strip()
        s.whisper_device = self.device.currentText()
        s.brand.name = self.b_name.text().strip()
        s.brand.short_name = self.b_short.text().strip()
        s.brand.presenter = self.b_presenter.text().strip()
        s.brand.presenter_title = self.b_ptitle.text().strip()
        s.brand.year = self.b_year.text().strip()
        s.brand.accent = self.b_accent.text().strip()
        gloss = {}
        for line in self.glossary.toPlainText().splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                if k.strip():
                    gloss[k.strip()] = v.strip()
        s.glossary = gloss
        s.projects_dir = self.projects.text().strip() or s.projects_dir
        s.ffmpeg_path = self.ffmpeg.text().strip()
        s.node_path = self.node.text().strip()
        s.render.browser_executable = self.browser.text().strip()
        s.render.concurrency = self.concurrency.value()
        s.render.crf = self.crf.value()
        s.wikimedia_contact = self.wm.text().strip()
        s.save()
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings.load()
        self.setWindowTitle(f"Choi Studio {__version__} — 디자인 이론 영상 자동 편집")
        self.resize(1320, 900)
        self.thread: Optional[QThread] = None
        self.worker: Optional[Worker] = None
        self.cancel: Optional[CancelToken] = None
        self.job_dir: Optional[Path] = None
        self._build()
        self._restore()
        self.setStyleSheet(_qss(self.settings.brand.accent))

    # ------------------------------------------------------------------
    def _file_row(self, line: QLineEdit, filt: str | None, folder: bool = False) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton("찾기")

        def pick():
            if folder:
                p = QFileDialog.getExistingDirectory(self, "폴더 선택")
            else:
                p, _ = QFileDialog.getOpenFileName(self, "파일 선택", "", filt or "모든 파일 (*)")
            if p:
                line.setText(p)
        btn.clicked.connect(pick)
        h.addWidget(line, 1)
        h.addWidget(btn)
        return w

    def _build(self) -> None:
        root = QWidget()
        outer = QVBoxLayout(root)
        head = QHBoxLayout()
        t = QLabel("CHOI STUDIO")
        t.setObjectName("title")
        st = QLabel("원본 영상 + 대본 + 메모 → 롱폼 · 숏폼 · 썸네일 · 자막 · 프리미어 XML")
        st.setObjectName("sub")
        head.addWidget(t)
        head.addSpacing(12)
        head.addWidget(st)
        head.addStretch(1)
        b_open = QPushButton("저장된 작업 열기…")
        b_open.clicked.connect(self._open_job)
        b_set = QPushButton("설정")
        b_set.clicked.connect(self._open_settings)
        head.addWidget(b_open)
        head.addWidget(b_set)
        outer.addLayout(head)

        split = QSplitter(Qt.Horizontal)
        # ---------------- 입력
        left = QWidget()
        lv = QVBoxLayout(left)
        g1 = QGroupBox("1. 소스")
        f = QFormLayout(g1)
        self.video = DropLine("원본 영상 파일을 끌어다 놓거나 찾기")
        self.audio = DropLine("(선택) 따로 녹음한 마이크 음성 — 자동 싱크")
        f.addRow("원본 영상 *", self._file_row(self.video, VIDEO_FILTER))
        f.addRow("별도 녹음", self._file_row(self.audio, AUDIO_FILTER))
        lv.addWidget(g1)

        g2 = QGroupBox("2. 영상 정보")
        f2 = QGridLayout(g2)
        self.title = QLineEdit()
        self.title.setPlaceholderText("예) 좋은 디자인은 질문에서 시작한다")
        self.episode = QLineEdit()
        self.episode.setPlaceholderText("01")
        self.subtitle = QLineEdit()
        self.subtitle.setPlaceholderText("(선택) 부제")
        self.series = QLineEdit("디자인 이론")
        f2.addWidget(QLabel("제목 *"), 0, 0)
        f2.addWidget(self.title, 0, 1, 1, 3)
        f2.addWidget(QLabel("회차"), 1, 0)
        f2.addWidget(self.episode, 1, 1)
        f2.addWidget(QLabel("시리즈"), 1, 2)
        f2.addWidget(self.series, 1, 3)
        f2.addWidget(QLabel("부제"), 2, 0)
        f2.addWidget(self.subtitle, 2, 1, 1, 3)
        lv.addWidget(g2)

        tabs = QTabWidget()
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText(
            "주제·의도·주요 장면을 자유롭게 적어주세요. (Claude 가 편집 판단에 사용)\n"
            "예)\n- 핵심 메시지: 발산 없이 수렴하면 뻔한 답이 나온다\n- 03:20 더블다이아몬드 설명은 도식으로 크게\n"
            "- 참고 도서: 디자인과 인간 심리(도널드 노먼)\n- 숏폼은 '학생들이 건너뛰는 단계' 부분으로")
        self.script = QPlainTextEdit()
        self.script.setPlaceholderText(
            "촬영에 사용한 대본을 붙여넣으세요. 자막 오타 교정 + NG/리테이크 자동 제거에 쓰입니다.\n"
            "연출 태그 예) [챕터: 문제 정의]  [도식: 더블다이아몬드 | 정의]  [강조: 발산]  [이미지: Braun SK 4]\n"
            "[정의: 어포던스 | Affordance | 형태가 사용법을 알려주는 성질]  [인용: 문장 | 저자 | 책]  [숏폼 시작] … [숏폼 끝]")
        sw = QWidget()
        sv = QVBoxLayout(sw)
        sv.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        b_load = QPushButton("대본 파일 불러오기")
        b_load.clicked.connect(self._load_script)
        b_guide = QPushButton("태그 가이드")
        b_guide.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ROOT / "docs" / "대본_태그_가이드.md"))))
        bar.addWidget(b_load)
        bar.addWidget(b_guide)
        bar.addStretch(1)
        sv.addLayout(bar)
        sv.addWidget(self.script)
        tabs.addTab(sw, "3. 대본")
        tabs.addTab(self.notes, "4. 메모 · 주요 장면")
        lv.addWidget(tabs, 1)

        g3 = QGroupBox("5. 선택 자료")
        f3 = QFormLayout(g3)
        self.images = DropLine("(선택) 자료 이미지 폴더 — 파일명이 곧 설명(예: Braun SK 4.jpg)")
        self.bgm = DropLine("(선택) 배경음악 — 라이선스 있는 곡(가사 없는 곡 권장)")
        self.lut = DropLine("(선택) 색보정 LUT(.cube)")
        f3.addRow("이미지 폴더", self._file_row(self.images, None, folder=True))
        f3.addRow("BGM", self._file_row(self.bgm, AUDIO_FILTER))
        f3.addRow("LUT", self._file_row(self.lut, "LUT (*.cube);;모든 파일 (*)"))
        lv.addWidget(g3)
        split.addWidget(left)

        # ---------------- 옵션/실행
        right = QWidget()
        rv = QVBoxLayout(right)
        go = QGroupBox("출력 옵션")
        og = QGridLayout(go)
        self.make_long = QCheckBox("롱폼(16:9)")
        self.make_long.setChecked(True)
        self.shorts = QSpinBox()
        self.shorts.setRange(0, 5)
        self.shorts.setValue(2)
        self.short_len = QSpinBox()
        self.short_len.setRange(25, 60)
        self.short_len.setValue(50)
        self.short_len.setSuffix(" 초")
        self.height_box = QComboBox()
        self.height_box.addItems(["1080p", "1440p", "2160p (4K)"])
        self.pace = QComboBox()
        self.pace.addItems(["차분하게 (셜록현준식 호흡)", "보통", "빠르게"])
        self.caption_style = QComboBox()
        self.caption_style.addItems(["그림자 자막", "박스 자막"])
        self.shorts_layout = QComboBox()
        self.shorts_layout.addItems(["풀프레임 얼굴(+상단 도식)", "가운데 16:9 (3단)"])
        og.addWidget(self.make_long, 0, 0)
        og.addWidget(QLabel("숏폼 개수"), 0, 1)
        og.addWidget(self.shorts, 0, 2)
        og.addWidget(QLabel("숏폼 최대"), 1, 1)
        og.addWidget(self.short_len, 1, 2)
        og.addWidget(QLabel("해상도"), 2, 0)
        og.addWidget(self.height_box, 2, 1, 1, 2)
        og.addWidget(QLabel("편집 템포"), 3, 0)
        og.addWidget(self.pace, 3, 1, 1, 2)
        og.addWidget(QLabel("롱폼 자막"), 4, 0)
        og.addWidget(self.caption_style, 4, 1, 1, 2)
        og.addWidget(QLabel("숏폼 레이아웃"), 5, 0)
        og.addWidget(self.shorts_layout, 5, 1, 1, 2)
        rv.addWidget(go)

        gx = QGroupBox("편집 기능")
        xg = QGridLayout(gx)
        self.use_claude = QCheckBox("Claude 편집 판단")
        self.fetch_broll = QCheckBox("자료 사진 자동 검색(위키미디어)")
        self.grain = QCheckBox("필름 그레인")
        self.sfx = QCheckBox("은은한 효과음")
        self.endcard = QCheckBox("엔드카드")
        self.thumbs = QCheckBox("썸네일 3종")
        self.enhance = QCheckBox("보이스 보정")
        self.xml = QCheckBox("프리미어 XML")
        self.progress_bar = QCheckBox("숏폼 진행바")
        self.reuse = QCheckBox("저장된 편집 계획 재사용")
        for i, (cb, on) in enumerate([(self.use_claude, True), (self.fetch_broll, True), (self.grain, True),
                                       (self.sfx, True), (self.endcard, True), (self.thumbs, True),
                                       (self.enhance, True), (self.xml, True), (self.progress_bar, False),
                                       (self.reuse, True)]):
            cb.setChecked(on)
            xg.addWidget(cb, i // 2, i % 2)
        rv.addWidget(gx)

        runbar = QHBoxLayout()
        self.b_plan = QPushButton("편집 계획만")
        self.b_plan.setToolTip("음성 인식·정렬·Claude 계획까지만 실행하고 멈춥니다. output/plan.json 을 고친 뒤 전체 제작하세요.")
        self.b_plan.clicked.connect(lambda: self._start("plan"))
        self.b_run = QPushButton("전체 제작 ▶")
        self.b_run.setObjectName("primary")
        self.b_run.clicked.connect(lambda: self._start("all"))
        self.b_cancel = QPushButton("취소")
        self.b_cancel.setEnabled(False)
        self.b_cancel.clicked.connect(self._cancel)
        runbar.addWidget(self.b_plan)
        runbar.addWidget(self.b_run, 1)
        runbar.addWidget(self.b_cancel)
        rv.addLayout(runbar)

        self.stage_label = QLabel("대기 중")
        self.stage_label.setObjectName("stage")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.stage_bar = QProgressBar()
        self.stage_bar.setRange(0, 1000)
        self.stage_bar.setTextVisible(False)
        self.stage_bar.setMaximumHeight(6)
        rv.addWidget(self.stage_label)
        rv.addWidget(self.bar)
        rv.addWidget(self.stage_bar)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(2)
        self.stage_labels: list[QLabel] = []
        half = (len(STAGES) + 1) // 2
        for i, (_, label, _) in enumerate(STAGES):
            lab = QLabel(f"○ {label}")
            lab.setObjectName("sub")
            self.stage_labels.append(lab)
            grid.addWidget(lab, i % half, i // half)
        rv.addLayout(grid)

        post = QHBoxLayout()
        self.b_out = QPushButton("결과 폴더 열기")
        self.b_out.clicked.connect(self._open_output)
        self.b_planfile = QPushButton("편집 계획 열기(plan.json)")
        self.b_planfile.clicked.connect(self._open_plan)
        self.b_preview = QPushButton("미리보기(Remotion Studio)")
        self.b_preview.clicked.connect(self._preview)
        post.addWidget(self.b_out)
        post.addWidget(self.b_planfile)
        post.addWidget(self.b_preview)
        rv.addLayout(post)

        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setMaximumBlockCount(5000)
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        mono.setPointSize(9)
        self.logbox.setFont(mono)
        self.logbox.setMinimumHeight(220)
        rv.addWidget(self.logbox, 1)
        split.addWidget(right)
        split.setSizes([700, 620])

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(split)
        outer.addWidget(scroll, 1)
        self.setCentralWidget(root)

    # ------------------------------------------------------------------
    def _spec(self) -> JobSpec:
        heights = [1080, 1440, 2160]
        paces = ["calm", "normal", "fast"]
        return JobSpec(
            video=self.video.text().strip(), title=self.title.text().strip(), audio=self.audio.text().strip(),
            episode=self.episode.text().strip(), subtitle=self.subtitle.text().strip(),
            series=self.series.text().strip(), notes=self.notes.toPlainText(), script=self.script.toPlainText(),
            images_dir=self.images.text().strip(), bgm=self.bgm.text().strip(), lut=self.lut.text().strip(),
            make_long=self.make_long.isChecked(), shorts_count=self.shorts.value(),
            short_max_sec=self.short_len.value(), out_height=heights[self.height_box.currentIndex()],
            pace=paces[self.pace.currentIndex()], use_claude=self.use_claude.isChecked(),
            fetch_broll=self.fetch_broll.isChecked(), grain=self.grain.isChecked(),
            caption_style=["shadow", "box"][self.caption_style.currentIndex()], thumbnails=self.thumbs.isChecked(),
            sfx=self.sfx.isChecked(), enhance_voice=self.enhance.isChecked(),
            shorts_layout=["full", "framed"][self.shorts_layout.currentIndex()],
            progress_bar=self.progress_bar.isChecked(), endcard=self.endcard.isChecked(),
            reuse_plan=self.reuse.isChecked(), export_xml=self.xml.isChecked())

    def _apply_spec(self, s: JobSpec) -> None:
        self.video.setText(s.video)
        self.audio.setText(s.audio)
        self.title.setText(s.title)
        self.episode.setText(s.episode)
        self.subtitle.setText(s.subtitle)
        self.series.setText(s.series)
        self.notes.setPlainText(s.notes)
        self.script.setPlainText(s.script)
        self.images.setText(s.images_dir)
        self.bgm.setText(s.bgm)
        self.lut.setText(s.lut)
        self.make_long.setChecked(s.make_long)
        self.shorts.setValue(s.shorts_count)
        self.short_len.setValue(max(25, min(60, s.short_max_sec)))
        self.height_box.setCurrentIndex({1080: 0, 1440: 1, 2160: 2}.get(s.out_height, 0))
        self.pace.setCurrentIndex({"calm": 0, "normal": 1, "fast": 2}.get(s.pace, 0))
        self.use_claude.setChecked(s.use_claude)
        self.fetch_broll.setChecked(s.fetch_broll)
        self.grain.setChecked(s.grain)
        self.caption_style.setCurrentIndex(0 if s.caption_style == "shadow" else 1)
        self.thumbs.setChecked(s.thumbnails)
        self.sfx.setChecked(s.sfx)
        self.enhance.setChecked(s.enhance_voice)
        self.shorts_layout.setCurrentIndex(0 if s.shorts_layout == "full" else 1)
        self.progress_bar.setChecked(s.progress_bar)
        self.endcard.setChecked(s.endcard)
        self.reuse.setChecked(s.reuse_plan)
        self.xml.setChecked(s.export_xml)

    def _restore(self) -> None:
        d = read_json(LAST_JOB, None)
        if d and d.get("spec"):
            try:
                self._apply_spec(JobSpec.from_dict(d["spec"]))
                jd = d.get("job_dir")
                self.job_dir = Path(jd) if jd and Path(jd).exists() else None
            except (TypeError, KeyError):
                pass
        if not self.settings.anthropic_api_key:
            self._log("ℹ 설정에서 Claude API 키를 입력하면 편집 판단(그래픽·챕터·숏폼 후킹)을 Claude 가 합니다. "
                      "키가 없으면 대본 태그 기반 규칙 편집으로 동작합니다.")

    def _log(self, msg: str) -> None:
        self.logbox.appendPlainText(msg)

    # ------------------------------------------------------------------
    def _start(self, until: str) -> None:
        spec = self._spec()
        if not spec.video or not Path(spec.video).exists():
            QMessageBox.warning(self, "확인", "원본 영상 파일을 지정하세요.")
            return
        if not spec.title:
            QMessageBox.warning(self, "확인", "제목을 입력하세요.")
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
        self._log(f"\n▶ 작업 폴더: {self.job_dir}")
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

    def _busy(self, on: bool) -> None:
        self.b_run.setEnabled(not on)
        self.b_plan.setEnabled(not on)
        self.b_cancel.setEnabled(on)

    def _on_progress(self, key: str, frac: float, overall: float) -> None:
        self.bar.setValue(int(overall * 1000))
        self.stage_bar.setValue(int(frac * 1000))
        keys = [k for k, _, _ in STAGES]
        idx = keys.index(key) if key in keys else -1
        label = dict((k, v) for k, v, _ in STAGES).get(key, key)
        self.stage_label.setText(f"{label} — {frac * 100:.0f}%   (전체 {overall * 100:.0f}%)")
        for i, (k, lab, _) in enumerate(STAGES):
            mark = "●" if i < idx or (i == idx and frac >= 1) else ("◐" if i == idx else "○")
            self.stage_labels[i].setText(f"{mark} {lab}")

    def _on_done(self, res: dict) -> None:
        self._busy(False)
        self.bar.setValue(1000)
        self.stage_label.setText("완료")
        self._log(f"✔ 완료 → {res.get('output')}")
        QMessageBox.information(self, "완료", f"결과물이 저장되었습니다.\n{res.get('output')}")

    def _on_fail(self, msg: str) -> None:
        self._busy(False)
        self.stage_label.setText("중단됨")
        self._log("✖ " + msg)
        QMessageBox.critical(self, "오류", msg[:1500])

    def _cancel(self) -> None:
        if self.cancel:
            self.cancel.cancel()
            self._log("취소 요청…")

    # ------------------------------------------------------------------
    def _open_settings(self) -> None:
        dlg = SettingsDialog(Settings.load(), self)
        if dlg.exec():
            self.settings = Settings.load()
            self.setStyleSheet(_qss(self.settings.brand.accent))
            self._log("설정 저장됨")

    def _load_script(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "대본 파일", "", TEXT_FILTER)
        if p:
            for enc in ("utf-8", "cp949", "utf-16"):
                try:
                    self.script.setPlainText(Path(p).read_text(encoding=enc))
                    return
                except UnicodeDecodeError:
                    continue

    def _open_job(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "작업 폴더 선택", self.settings.projects_dir)
        if not d:
            return
        data = read_json(Path(d) / "job.json", None)
        if not data:
            QMessageBox.warning(self, "확인", "job.json 이 없는 폴더입니다.")
            return
        self._apply_spec(JobSpec.from_dict(data))
        self.job_dir = Path(d)
        self._log(f"작업 불러옴: {d}  (전체 제작을 누르면 캐시를 활용해 다시 렌더합니다)")

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
            self._log("Remotion Studio 를 여는 중… 브라우저에서 http://localhost:3000")
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
    for name in ("Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR"):
        if name in QFontDatabase.families():
            app.setFont(QFont(name, 10))
            break
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
