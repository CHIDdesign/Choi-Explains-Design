"""환경 설정: AI 연결(Claude Code 구독 / API 키) · 음성 인식·용어 사전 · 스톡 · 브랜드 · 경로·렌더."""
from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QRadioButton, QSpinBox,
                               QTabWidget, QVBoxLayout, QWidget)

from ..director.claude_code import auth_status, claude_version, describe_auth, find_claude, format_quota, open_login, probe_quota
from ..settings import save_quota, usage_summary
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


class _Quota(QObject):
    """한도 창 확인(아주 작은 호출 한 번, 가장 싼 모델) — 창을 얼리지 않게 스레드에서"""
    done = Signal(str)

    def __init__(self, custom: str):
        super().__init__()
        self.custom = custom

    def run(self) -> None:
        exe = find_claude(self.custom)
        if not exe:
            self.done.emit("Claude Code 를 찾지 못했습니다")
            return
        r = probe_quota(exe)
        if r.get("quota"):
            save_quota(r["quota"])
            self.done.emit("한도 창(방금 확인): " + format_quota(r["quota"]))
        else:
            self.done.emit("한도 창을 받지 못했습니다: " + (r.get("error") or "응답에 rate_limit 정보 없음(Claude Code 를 업데이트하세요)"))


# 모델·사고 강도는 선택만(직접 입력 없음 — 오타가 곧 오류였다) · 하나가 모든 에이전트에(채널 주인 2026-10-03)
MODEL_CHOICES = [("claude-opus-5-5", "Opus 5.5 — 기본(기획·편집·디자인 전부)"),
                 ("claude-fable-5-1", "Fable 5.1 — 최상위(더 느리고 비쌈)"),
                 ("claude-sonnet-5-5", "Sonnet 5.5 — 빠르고 저렴"),
                 ("claude-haiku-4-5-20251001", "Haiku 4.5 — 가장 저렴(시험용)")]
EFFORT_CHOICES = [("xhigh", "xhigh — 아주 높음(기본)"), ("max", "max — 최대(가장 느림)"), ("high", "high — 높음"),
                  ("medium", "medium — 보통"), ("low", "low — 낮음(시험용)")]


def _pick(combo: QComboBox, value: str, fallback: str) -> None:
    """콤보의 userData 가 value 인 항목을 고른다. 없으면(옛 설정 파일의 낯선 id) 그 값을 항목으로 더해 고른다."""
    for i in range(combo.count()):
        if combo.itemData(i) == value:
            combo.setCurrentIndex(i)
            return
    if value:
        combo.addItem(value, value)
        combo.setCurrentIndex(combo.count() - 1)
        return
    _pick(combo, fallback, fallback)


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
        for mid, label in MODEL_CHOICES:
            self.model.addItem(label, mid)
        _pick(self.model, s.claude_model, "claude-opus-5-5")
        self.model.setToolTip("\n".join(f"{mid}: {label}" for mid, label in MODEL_CHOICES))
        self.effort = QComboBox()
        for val, label in EFFORT_CHOICES:
            self.effort.addItem(label, val)
        _pick(self.effort, s.claude_effort, "xhigh")
        self.workers = QSpinBox()
        self.workers.setRange(1, 8)
        self.workers.setValue(s.studio_workers)
        self.workers.setToolTip("총괄 감독 아래에서 동시에 일하는 전문 에이전트 수(한도에 자주 걸리면 2로)")
        m.addRow("모델", self.model)
        m.addRow("사고 강도", self.effort)
        m.addRow("", hint("모델과 사고 강도 하나가 모든 에이전트(조사·기획·컷·모션·자료·검수)에 똑같이 쓰입니다. "
                          "xhigh 는 high 보다 오래 생각하고 토큰을 더 씁니다."))
        m.addRow("동시 에이전트", self.workers)
        self.research_web = QCheckBox("웹 조사 — 🔎 리서치 디렉터·🛠 시그니처 장면이 인물·제품·개념을 검색해 확인한다(권장)")
        self.research_web.setChecked(bool(getattr(s, "research_web", True)))
        m.addRow("조사", self.research_web)
        self.style_frame = QCheckBox("스타일 프레임 — 장면을 짓기 전에 이 영상의 룩을 한 장으로 먼저 정해 모든 디자이너가 따른다(권장)")
        self.style_frame.setChecked(bool(getattr(s, "style_frame", True)))
        m.addRow("디자인", self.style_frame)
        self.variants = QSpinBox()
        self.variants.setRange(1, 4)
        self.variants.setValue(int(getattr(s, "design_variants", 3) or 1))
        self.variants.setToolTip("시그니처 장면마다 서로 다른 방향의 시안을 이만큼 지어 렌더한 뒤 심사가 하나를 고릅니다. "
                                 "1 이면 경쟁 없이 한 안(토큰이 가장 적음).")
        m.addRow("시안 수", self.variants)
        self.screen_look = QCheckBox("모니터 질감 — 그래픽 위에 아주 약간의 흐림·빛 번짐·화면 격자·입자(레트로하면서 디지털한 화면)")
        self.screen_look.setChecked(float(getattr(s, "screen_look", 1.0) or 0) > 0)
        m.addRow("화면 질감", self.screen_look)
        m.addRow("", hint("레퍼런스 보드: user/taste 폴더에 좋아하는 모션 디자인의 정지 화면을 넣으면 모든 디자이너·심사가 매번 그림으로 봅니다. "
                          "결과 화면의 '장면 평가'(👍/👎)도 여기에 쌓여 다음 작업부터 반영됩니다."))
        v.addLayout(m)
        # 📊 사용량·한도
        self.usage_lbl = QLabel(usage_summary())
        self.usage_lbl.setObjectName("hint")
        self.usage_lbl.setWordWrap(True)
        b_quota = QPushButton("한도 확인(소량 호출)")
        b_quota.setToolTip("가장 싼 모델로 아주 작은 호출을 한 번 보내 5시간·주간 한도 창의 사용률을 받습니다")
        b_quota.clicked.connect(self._check_quota)
        urow = QHBoxLayout()
        urow.addWidget(b_quota)
        urow.addStretch(1)
        u = QFormLayout()
        u.setContentsMargins(0, 8, 0, 0)
        u.addRow("사용량", self.usage_lbl)
        u.addRow("", urow)
        v.addLayout(u)
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
        self.pexels = key_edit(s.pexels_api_key, "이미 발급받은 키가 있을 때만(새 키 발급은 멈춤)")
        self.serpapi = key_edit(getattr(s, "serpapi_key", ""), "serpapi.com 가입 → 대시보드의 API Key (무료 월 250회, 카드 없음)")
        fs.addRow("Pixabay (추천)", self.pixabay)
        fs.addRow("Google 이미지 (SerpApi)", self.serpapi)
        fs.addRow("Unsplash", self.unsplash)
        fs.addRow("Coverr", self.coverr)
        fs.addRow("Pexels", self.pexels)
        self.museums = QCheckBox("미술관 소장품 사진(시카고·메트·클리블랜드, CC0 — 키 없음)")
        self.museums.setChecked(bool(getattr(s, "museum_search", True)))
        fs.addRow("", self.museums)
        self.quote = QCheckBox("인용 자료 쓰기(웹·앱 화면 캡처 · 논문 첫 화면 · 그 대상 자체의 웹 이미지) — C 등급")
        self.quote.setChecked(bool(getattr(s, "allow_quote", False)))
        fs.addRow("", self.quote)
        fs.addRow("", hint("키를 넣은 곳을 모두 검색해 후보를 섞고, 🎞 자료 리서처가 썸네일을 보고 고릅니다. "
                           "Pixabay(사진+영상+벡터, 한국어 검색)가 기본, Google 이미지는 재사용 가능 라이선스만 찾고 원문 페이지에서 "
                           "라이선스를 다시 확인한 것만 씁니다. 키가 없어도 Openverse(CC 사진)·위키미디어·미술관은 검색합니다. "
                           "출처는 화면 ▣ 와 설명란·자료 대장에 자동 표기."))
        tabs.addTab(st, "스톡")

        # --- 소리
        so = QWidget()
        fso = QFormLayout(so)
        self.sfx = QComboBox()
        for key, lab in (("directed", "감독(Claude)이 고른 곳에만 — 기본"), ("auto", "자동(그래픽마다, 예전 방식)"), ("off", "끔")):
            self.sfx.addItem(lab, key)
        cur = "auto" if getattr(s, "sfx_enabled", False) else str(getattr(s, "sfx_mode", "directed") or "directed")
        self.sfx.setCurrentIndex(max(0, self.sfx.findData(cur)))
        self.music = QComboBox()
        modes = [("mine", "내 음악 폴더의 곡만"), ("library", "기본 라이브러리(자동 선곡)"), ("off", "배경음악 없음")]
        for key, label in modes:
            self.music.addItem(label, key)
        keys = [k for k, _ in modes]
        mode = getattr(s, "music_mode", "mine")
        self.music.setCurrentIndex(keys.index(mode) if mode in keys else 0)
        self.music_dir = QLineEdit(getattr(s, "music_dir", ""))
        self.music_dir.setPlaceholderText("비우면 user\\music 폴더")
        fso.addRow("효과음", self.sfx)
        fso.addRow("배경음악", self.music)
        fso.addRow("내 음악 폴더", self.music_dir)
        fso.addRow("", hint("기본은 효과음 없이, 배경음악은 내 음악 폴더에 넣은 곡만 씁니다(mp3·wav·m4a 등, 목소리 아래로 "
                            "작게 깔림). 폴더가 비어 있으면 배경음악 없이 만듭니다. 마음에 들지 않는 소리를 넣느니 넣지 않습니다."))
        tabs.addTab(so, "소리")

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
        # 디자인 v3(종이 콜라주): 레퍼런스의 초록 팔레트 또는 위 강조색
        self.b_palette = QComboBox()
        self.b_palette.addItem("채널 오렌지(#FC5400 — 디자인 v4 기본)", "ember")
        self.b_palette.addItem("숲 초록(짙은 초록 글자 + 민트)", "forest")
        self.b_palette.addItem("브랜드 강조색에서 만들기", "brand")
        self.b_palette.setCurrentIndex({"ember": 0, "forest": 1}.get(getattr(b, "palette", "ember"), 2))
        f2.addRow("디자인 색", self.b_palette)
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

    def _check_quota(self) -> None:
        self.usage_lbl.setText(usage_summary() + "\n한도 창 확인 중…")
        self._qthread = QThread(self)
        self._qworker = _Quota(self.cc_path.text().strip())
        self._qworker.moveToThread(self._qthread)
        self._qthread.started.connect(self._qworker.run)
        self._qworker.done.connect(lambda msg: self.usage_lbl.setText(usage_summary() + "\n" + msg))
        self._qworker.done.connect(self._qthread.quit)
        self._qthread.start()

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
        s.claude_model = str(self.model.currentData() or "claude-opus-5-5")
        s.claude_effort = str(self.effort.currentData() or "xhigh")
        s.agent_models, s.agent_effort = {}, {}      # 전역 하나로 통합 — 옛 에이전트별 덮어쓰기는 저장할 때 지운다
        s.studio_workers = self.workers.value()
        s.research_web = self.research_web.isChecked()
        s.style_frame = self.style_frame.isChecked()
        s.design_variants = self.variants.value()
        s.screen_look = 1.0 if self.screen_look.isChecked() else 0.0
        s.pixabay_api_key = self.pixabay.text().strip()
        s.unsplash_access_key = self.unsplash.text().strip()
        s.coverr_api_key = self.coverr.text().strip()
        s.pexels_api_key = self.pexels.text().strip()
        s.serpapi_key = self.serpapi.text().strip()
        s.museum_search = self.museums.isChecked()
        s.whisper_model = self.whisper.currentText().strip()
        s.whisper_device = self.device.currentText()
        s.brand.name = self.b_name.text().strip()
        s.brand.short_name = self.b_short.text().strip()
        s.brand.presenter = self.b_presenter.text().strip()
        s.brand.presenter_title = self.b_ptitle.text().strip()
        s.brand.year = self.b_year.text().strip()
        s.brand.accent = self.b_accent.text().strip()
        s.brand.palette = self.b_palette.currentData() or "ember"
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
        s.allow_quote = self.quote.isChecked()
        s.sfx_mode = str(self.sfx.currentData() or "directed")
        s.sfx_enabled = False
        s.music_mode = self.music.currentData() or "mine"
        s.music_dir = self.music_dir.text().strip()
        s.save()
        self.accept()
