"""환경 설정: AI 연결(Claude Code 구독 / API 키) · 음성 인식·용어 사전 · 스톡 · 브랜드 · 경로·렌더."""
from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QButtonGroup, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QRadioButton, QSpinBox,
                               QTabWidget, QVBoxLayout, QWidget)

from ..director.claude_code import auth_status, claude_version, describe_auth, find_claude, open_login
from ..settings import Settings
from .widgets import hint


class _Probe(QObject):
    done = Signal(str, str)   # (경로·버전, 로그인 상태)

    def __init__(self, custom: str):
        super().__init__()
        self.custom = custom

    def run(self) -> None:
        exe = find_claude(self.custom)
        if not exe:
            self.done.emit("", "Claude Code 를 찾지 못했습니다 — setup_windows.bat 을 다시 실행하면 설치됩니다")
            return
        self.done.emit(f"{exe}  ·  {claude_version(exe) or '버전 확인 실패'}", describe_auth(auth_status(exe)))


class SettingsDialog(QDialog):
    def __init__(self, s: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("환경 설정")
        self.resize(720, 640)
        self.s = s
        tabs = QTabWidget()

        # --- AI 연결
        ai = QWidget()
        v = QVBoxLayout(ai)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)
        head = QLabel("AI 연결")
        head.setStyleSheet("font-size:14px; font-weight:800;")
        v.addWidget(head)
        self.rb_cc = QRadioButton("Claude Code — Pro/Max 구독 사용량으로 실행 (추천 · 추가 결제 없음)")
        self.rb_api = QRadioButton("Claude API 키 — 종량제 과금(console.anthropic.com)")
        grp = QButtonGroup(self)
        grp.addButton(self.rb_cc)
        grp.addButton(self.rb_api)
        (self.rb_api if s.ai_backend == "api" else self.rb_cc).setChecked(True)
        v.addWidget(self.rb_cc)
        cc = QFormLayout()
        cc.setContentsMargins(24, 0, 0, 0)
        self.cc_path = QLineEdit(s.claude_code_path)
        self.cc_path.setPlaceholderText("비우면 자동 탐색 (%USERPROFILE%\\.local\\bin\\claude.exe, PATH)")
        self.cc_info = QLabel("확인 중…")
        self.cc_info.setObjectName("hint")
        self.cc_info.setWordWrap(True)
        self.cc_auth = QLabel("")
        self.cc_auth.setStyleSheet("font-weight:700;")
        row = QHBoxLayout()
        b_check = QPushButton("연결 확인")
        b_check.clicked.connect(self._probe)
        b_login = QPushButton("로그인(브라우저)")
        b_login.setToolTip("Claude 구독 계정으로 로그인 — 창이 열리면 브라우저에서 승인하세요")
        b_login.clicked.connect(self._login)
        row.addWidget(b_check)
        row.addWidget(b_login)
        row.addStretch(1)
        cc.addRow("실행 파일", self.cc_path)
        cc.addRow("", self.cc_info)
        cc.addRow("상태", self.cc_auth)
        cc.addRow("", row)
        v.addLayout(cc)
        v.addWidget(hint("    Claude Code 의 `claude -p` 사용량은 현재 구독 한도(5시간·주간)에서 차감됩니다(2026-06-15 공지). "
                         "영상 한 편에 에이전트 호출이 10여 번 들어가며, 한도가 차면 풀린 뒤 다시 누르면 이어서 합니다."))
        v.addWidget(self.rb_api)
        api = QFormLayout()
        api.setContentsMargins(24, 0, 0, 0)
        self.key = QLineEdit(s.anthropic_api_key)
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("sk-ant-...  (console.anthropic.com 에서 발급 · 구독과 별도 결제)")
        api.addRow("API 키", self.key)
        v.addLayout(api)

        m = QFormLayout()
        m.setContentsMargins(0, 10, 0, 0)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(["claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1", "opus", "sonnet"])
        self.model.setCurrentText(s.claude_model)
        self.effort = QComboBox()
        self.effort.addItems(["low", "medium", "high", "xhigh", "max"])
        self.effort.setCurrentText(s.claude_effort)
        self.workers = QSpinBox()
        self.workers.setRange(1, 8)
        self.workers.setValue(s.studio_workers)
        self.workers.setToolTip("총괄 감독 아래에서 동시에 일하는 전문 에이전트 수(한도에 자주 걸리면 2로)")
        m.addRow("모델", self.model)
        m.addRow("사고 강도", self.effort)
        m.addRow("동시 에이전트", self.workers)
        v.addLayout(m)
        v.addStretch(1)
        tabs.addTab(ai, "AI 연결")

        # --- 음성 인식
        asr = QWidget()
        fa = QFormLayout(asr)
        self.whisper = QComboBox()
        self.whisper.setEditable(True)
        self.whisper.addItems(["large-v3", "large-v3-turbo", "medium"])
        self.whisper.setCurrentText(s.whisper_model)
        self.device = QComboBox()
        self.device.addItems(["auto", "cuda", "cpu"])
        self.device.setCurrentText(s.whisper_device)
        fa.addRow("Whisper 모델", self.whisper)
        fa.addRow("장치", self.device)
        fa.addRow("", hint("large-v3: 가장 정확(첫 실행 때 약 3GB 다운로드) · large-v3-turbo: 3~4배 빠름, 정확도 약간 낮음"))
        self.glossary = QPlainTextEdit("\n".join(f"{k}={v2}" for k, v2 in s.glossary.items()))
        fa.addRow("용어 사전", self.glossary)
        fa.addRow("", hint("한 줄에 하나씩  틀린말=맞는말  (예: 디자인 띵킹=디자인 씽킹)"))
        tabs.addTab(asr, "음성 인식")

        # --- 스톡
        st = QWidget()
        fs = QFormLayout(st)

        def key_edit(value: str, tip: str) -> QLineEdit:
            e = QLineEdit(value)
            e.setEchoMode(QLineEdit.Password)
            e.setPlaceholderText(tip)
            return e

        self.pixabay = key_edit(s.pixabay_api_key, "pixabay.com/api/docs 에 로그인하면 문서 안에 키가 보입니다")
        self.unsplash = key_edit(s.unsplash_access_key, "unsplash.com/developers → New Application → Access Key")
        self.coverr = key_edit(s.coverr_api_key, "coverr.co/developers (영상 전용)")
        self.pexels = key_edit(s.pexels_api_key, "이미 발급받은 키가 있을 때만")
        fs.addRow("Pixabay (추천)", self.pixabay)
        fs.addRow("Unsplash", self.unsplash)
        fs.addRow("Coverr", self.coverr)
        fs.addRow("Pexels", self.pexels)
        fs.addRow("", hint("키를 넣은 곳을 모두 검색해 후보를 섞고, 🎞 자료 리서처가 썸네일을 보고 고릅니다. "
                           "Pixabay 하나면 충분합니다(사진+영상+모션 그래픽용 벡터·일러스트, 한국어 검색). 키가 없어도 Openverse(CC 사진)는 "
                           "검색합니다. 출처는 화면 ▣ 와 설명란에 자동 표기."))
        tabs.addTab(st, "스톡")

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

        # --- 경로·렌더
        pa = QWidget()
        f3 = QFormLayout(pa)
        self.projects = QLineEdit(s.projects_dir)
        self.ffmpeg = QLineEdit(s.ffmpeg_path)
        self.ffmpeg.setPlaceholderText("비우면 자동 탐색(tools\\ffmpeg / PATH)")
        self.node = QLineEdit(s.node_path)
        self.node.setPlaceholderText("비우면 자동 탐색(tools\\node / PATH)")
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
        f3.addRow("ffmpeg", self.ffmpeg)
        f3.addRow("Node.js", self.node)
        f3.addRow("Chrome", self.browser)
        f3.addRow("렌더 동시 작업", self.concurrency)
        f3.addRow("CPU 인코딩 CRF", self.crf)
        f3.addRow("위키미디어 연락처", self.wm)
        tabs.addTab(pa, "경로 · 렌더")

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("저장")
        bb.button(QDialogButtonBox.Save).setObjectName("primary")
        bb.button(QDialogButtonBox.Cancel).setText("취소")
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(bb)
        self._probe()

    # ------------------------------------------------------------------
    def _probe(self) -> None:
        self.cc_info.setText("확인 중…")
        self.cc_auth.setText("")
        self._thread = QThread(self)
        self._worker = _Probe(self.cc_path.text().strip())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._probed)
        self._worker.done.connect(self._thread.quit)
        self._thread.start()

    def _probed(self, info: str, auth: str) -> None:
        self.cc_info.setText(info or "")
        ok = auth.startswith("로그인됨") and "API 키" not in auth
        self.cc_auth.setText(("● " if ok else "○ ") + auth)
        self.cc_auth.setStyleSheet(f"font-weight:700; color:{'#4CAF7A' if ok else '#E0A030'};")

    def _login(self) -> None:
        exe = find_claude(self.cc_path.text().strip())
        if not exe:
            self.cc_auth.setText("○ Claude Code 가 설치되어 있지 않습니다 — setup_windows.bat 을 다시 실행하세요")
            return
        open_login(exe)
        self.cc_auth.setText("브라우저에서 로그인한 뒤 '연결 확인'을 누르세요" + ("" if sys.platform == "win32" else ""))

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(self.b_accent.text()), self, "강조색")
        if c.isValid():
            self.b_accent.setText(c.name().upper())
            self.b_accent.setStyleSheet(f"background:{c.name()}; color:#111; font-weight:700;")

    def _save(self) -> None:
        s = self.s
        s.ai_backend = "api" if self.rb_api.isChecked() else "claude_code"
        s.claude_code_path = self.cc_path.text().strip()
        s.anthropic_api_key = self.key.text().strip()
        s.claude_model = self.model.currentText().strip()
        s.claude_effort = self.effort.currentText()
        s.studio_workers = self.workers.value()
        s.pixabay_api_key = self.pixabay.text().strip()
        s.unsplash_access_key = self.unsplash.text().strip()
        s.coverr_api_key = self.coverr.text().strip()
        s.pexels_api_key = self.pexels.text().strip()
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
                k, _, val = line.partition("=")
                if k.strip():
                    gloss[k.strip()] = val.strip()
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
