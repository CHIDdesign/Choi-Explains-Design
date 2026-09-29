"""편집 툴의 패널들: 프로젝트 · 스크립트 · 인스펙터 · AI 팀 · 콘솔 · 결과물."""
from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QProgressBar, QScrollArea, QSpinBox, QTabWidget,
                               QVBoxLayout, QWidget)

from ..pipeline import STAGES
from .widgets import MediaSlot, Section, button, hint

VIDEO_FILTER = "영상 (*.mp4 *.mov *.mkv *.m4v *.avi *.mts *.MP4 *.MOV);;모든 파일 (*)"
AUDIO_FILTER = "오디오 (*.wav *.mp3 *.m4a *.aac *.flac);;모든 파일 (*)"
LONG_PRESETS = ["auto", "editorial", "documentary", "glass", "boxed"]
SHORT_PRESETS = ["auto", "kinetic", "clean", "boxed"]


def _scroll(inner: QWidget) -> QScrollArea:
    s = QScrollArea()
    s.setWidget(inner)
    s.setWidgetResizable(True)
    s.setFrameShape(QScrollArea.NoFrame)
    return s


# ---------------------------------------------------------------------------
class ProjectPanel(QWidget):
    """시퀀스 정보 + 미디어 빈 + 최근 작업."""

    open_job = Signal(str)

    def __init__(self):
        super().__init__()
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)
        seq = QGridLayout()
        seq.setHorizontalSpacing(8)
        seq.setVerticalSpacing(6)
        self.title = QLineEdit()
        self.title.setPlaceholderText("영상 제목(가제)  예: 좋은 디자인은 질문에서 시작한다")
        self.episode = QLineEdit()
        self.episode.setPlaceholderText("01")
        self.series = QLineEdit("디자인 이론")
        self.subtitle = QLineEdit()
        self.subtitle.setPlaceholderText("(선택) 부제")
        for r, (lab, w) in enumerate([("제목 *", self.title), ("회차", self.episode), ("시리즈", self.series),
                                      ("부제", self.subtitle)]):
            l = QLabel(lab)
            l.setObjectName("fieldLabel")
            seq.addWidget(l, r, 0)
            seq.addWidget(w, r, 1)
        v.addWidget(self._caption("시퀀스"))
        v.addLayout(seq)
        v.addWidget(self._caption("미디어"))
        self.video = MediaSlot("🎬", "원본 영상", "여기로 끌어다 놓기 · 4K/아이폰 HDR 가능", filt=VIDEO_FILTER, required=True)
        self.audio = MediaSlot("🎙", "별도 녹음", "(선택) 마이크 음성 — 자동 싱크", filt=AUDIO_FILTER)
        self.images = MediaSlot("🖼", "자료 이미지 폴더", "(선택) 파일명이 곧 설명 — 예: Braun SK 4.jpg", folder=True)
        self.bgm = MediaSlot("♪", "배경음악", "(선택) 라이선스 있는 곡 — 자동 덕킹", filt=AUDIO_FILTER)
        self.lut = MediaSlot("◐", "LUT", "(선택) 색보정 .cube", filt="LUT (*.cube);;모든 파일 (*)")
        for w in (self.video, self.audio, self.images, self.bgm, self.lut):
            v.addWidget(w)
        v.addWidget(self._caption("최근 작업"))
        self.recent = QListWidget()
        self.recent.setMinimumHeight(110)
        self.recent.itemDoubleClicked.connect(lambda it: self.open_job.emit(it.data(Qt.UserRole)))
        v.addWidget(self.recent, 1)
        v.addWidget(hint("더블클릭하면 그 작업을 불러옵니다(분석 결과를 재사용해 빠르게 다시 렌더)."))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(_scroll(inner))

    @staticmethod
    def _caption(text: str) -> QLabel:
        lab = QLabel(text.upper())
        lab.setStyleSheet("color:#8A8A8A; font-size:10px; font-weight:800; letter-spacing:1px; padding-top:4px;")
        return lab

    def refresh_recent(self, projects_dir: str) -> None:
        self.recent.clear()
        base = Path(projects_dir)
        if not base.exists():
            return
        jobs = sorted((p for p in base.glob("*/job.json") if not p.parent.name.startswith("_")),
                      key=lambda p: p.stat().st_mtime, reverse=True)[:12]
        import json
        for j in jobs:
            try:
                d = json.loads(j.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            when = dt.datetime.fromtimestamp(j.stat().st_mtime).strftime("%m.%d %H:%M")
            has_out = any((j.parent / "output").glob("*.mp4"))
            it = QListWidgetItem(f"{'●' if has_out else '○'}  {d.get('title', j.parent.name)}   ·  {when}")
            it.setData(Qt.UserRole, str(j.parent))
            it.setToolTip(str(j.parent))
            self.recent.addItem(it)


# ---------------------------------------------------------------------------
class ScriptPanel(QWidget):
    load_script = Signal()
    open_guide = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.tabs = QTabWidget()
        self.script = QPlainTextEdit()
        self.script.setPlaceholderText(
            "촬영에 쓴 대본을 붙여넣으세요 — 자막 오타 교정, NG·리테이크 자동 제거, 연출 태그에 쓰입니다.\n\n"
            "연출 태그 예)\n[챕터: 문제 정의]   [도식: 더블다이아몬드 | 정의]   [강조: 발산]   [이미지: Braun SK 4]\n"
            "[정의: 어포던스 | Affordance | 형태가 사용법을 알려주는 성질]   [인용: 문장 | 저자 | 책]\n"
            "[숏폼 시작] … [숏폼 끝]")
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText(
            "주제·의도·주요 장면을 자유롭게 — 🎬 총괄 감독이 브리프를 쓸 때 읽습니다.\n\n"
            "예)\n- 핵심 메시지: 발산 없이 수렴하면 뻔한 답이 나온다\n- 03:20 더블다이아몬드 설명은 도식으로 크게\n"
            "- 참고 도서: 디자인과 인간 심리(도널드 노먼)\n- 숏폼은 '학생들이 건너뛰는 단계' 부분으로")
        self.direction = QPlainTextEdit()
        self.direction.setPlaceholderText(
            "AI 스튜디오 전체에 주는 편집 지시(선택) — 모든 에이전트가 최우선으로 따릅니다.\n\n"
            "예)\n- 이번 편은 모션 그래픽을 평소보다 많이, 스톡 영상은 자연광 톤만\n"
            "- 인트로는 30초 안에 끝내고 첫 장면은 의자 사진으로\n- 자막은 다큐멘터리 스타일로 절제해서")
        mono = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
        for w in (self.script, self.notes, self.direction):
            w.setFont(mono)
            w.textChanged.connect(self._count)
        self.tabs.addTab(self.script, "대본")
        self.tabs.addTab(self.notes, "메모 · 주요 장면")
        self.tabs.addTab(self.direction, "편집 지시")
        self.tabs.currentChanged.connect(self._count)
        v.addWidget(self.tabs, 1)
        bar = QHBoxLayout()
        bar.setContentsMargins(8, 5, 8, 6)
        bar.addWidget(button("대본 파일 불러오기", self.load_script.emit, ghost=True))
        bar.addWidget(button("태그 가이드", self.open_guide.emit, ghost=True))
        bar.addStretch(1)
        self.count = QLabel("")
        self.count.setObjectName("hint")
        bar.addWidget(self.count)
        v.addLayout(bar)

    def _count(self, *_a) -> None:
        w = self.tabs.currentWidget()
        if isinstance(w, QPlainTextEdit):
            t = w.toPlainText()
            self.count.setText(f"{len(t.replace(chr(10), '')):,}자 · {t.count(chr(10)) + (1 if t else 0)}줄")


# ---------------------------------------------------------------------------
class InspectorPanel(QWidget):
    """출력·자막·AI 스튜디오·오디오 옵션(접히는 섹션)."""

    open_settings = Signal()

    def __init__(self):
        super().__init__()
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        out = Section("출력")
        self.make_long = out.row("", QCheckBox("롱폼 16:9"), "유튜브 가로 영상")
        self.make_long.setChecked(True)
        self.shorts = QSpinBox()
        self.shorts.setRange(0, 5)
        self.shorts.setValue(2)
        self.shorts.setSuffix(" 편")
        out.row("숏폼", self.shorts, "릴스·쇼츠 9:16 — 후킹 구조를 적용해 자동 기획")
        self.short_len = QSpinBox()
        self.short_len.setRange(25, 60)
        self.short_len.setValue(50)
        self.short_len.setSuffix(" 초")
        out.row("숏폼 최대", self.short_len)
        self.height_box = QComboBox()
        self.height_box.addItems(["1080p", "1440p", "2160p (4K)"])
        out.row("해상도", self.height_box)
        self.pace = QComboBox()
        self.pace.addItems(["차분하게 (셜록현준식 호흡)", "보통", "빠르게"])
        out.row("편집 템포", self.pace, "쉼(무음)을 얼마나 줄일지")
        self.shorts_layout = QComboBox()
        self.shorts_layout.addItems(["풀프레임 얼굴 + 상단 도식", "가운데 16:9 (3단)"])
        out.row("숏폼 구성", self.shorts_layout)
        self.thumbs = out.row("", QCheckBox("썸네일 3종"))
        self.xml = out.row("", QCheckBox("프리미어 프로 XML"), "원본을 참조하는 컷 편집 시퀀스 + 챕터·그래픽 마커")
        self.endcard = out.row("", QCheckBox("엔드카드"))
        self.progress_bar = out.row("", QCheckBox("숏폼 진행 바"))
        for cb, on in ((self.thumbs, True), (self.xml, True), (self.endcard, True), (self.progress_bar, False)):
            cb.setChecked(on)
        v.addWidget(out)

        cap = Section("자막 스타일")
        self.caption_style = QComboBox()
        self.caption_style.addItems(["자동 — 🔤 자막 디자이너가 선택", "에디토리얼 (그림자 · 마스크 리빌)",
                                     "다큐멘터리 (왼쪽 정렬 · 세로 룰)", "글래스 (반투명 유리 알약)",
                                     "박스 (잉크 박스 · 강조색 엣지)"])
        cap.row("롱폼", self.caption_style)
        self.short_caption = QComboBox()
        self.short_caption.addItems(["자동 — 🔤 자막 디자이너가 선택", "키네틱 (단어가 올라옴)", "클린 (카라오케)",
                                     "박스 (활성 단어 알약)"])
        cap.row("숏폼", self.short_caption)
        cap.note("강조어는 유형별로: 전문용어 = 형광 마커, 핵심어 = 밑줄 스윕, 숫자 = 팝, 대비 = 외곽선. "
                 "한 줄에 하나, 조사는 빼고 어간만. 줄당 16자·최대 2줄.")
        v.addWidget(cap)

        ai = Section("AI 스튜디오")
        self.ai_status = QLabel("확인 중…")
        self.ai_status.setWordWrap(True)
        ai.row("AI 연결", self.ai_status)
        ai.row("", button("AI 연결 설정…", self.open_settings.emit, tip="Claude Code(구독) / API 키, 로그인"))
        self.use_claude = ai.row("", QCheckBox("Claude 편집 판단"), "끄면 대본 태그만으로 규칙 기반 편집")
        self.studio_mode = ai.row("", QCheckBox("멀티 에이전트 팀(🎬 감독 + 전문가 6명)"),
                                  "끄면 Claude 한 번 호출로 계획(빠르고 사용량 적음, 모션 장면·스톡 없음)")
        self.motion_scenes = ai.row("", QCheckBox("🎨 모션 장면 직접 설계"))
        self.fetch_stock = ai.row("", QCheckBox("🎞 무료 스톡 영상·사진"), "설정 → 스톡의 Pixabay 등 키로 자동 검색·선택")
        self.qa_rounds = QSpinBox()
        self.qa_rounds.setRange(0, 3)
        self.qa_rounds.setValue(1)
        self.qa_rounds.setSpecialValueText("끔")
        self.qa_rounds.setSuffix(" 라운드")
        ai.row("🧐 검수", self.qa_rounds, "아트 디렉터가 렌더된 장면을 직접 보고 고치는 횟수")
        self.reuse = ai.row("", QCheckBox("저장된 편집 계획 재사용"), "plan.json 을 고쳤다면 그 내용으로 다시 렌더")
        for cb in (self.use_claude, self.studio_mode, self.motion_scenes, self.fetch_stock, self.reuse):
            cb.setChecked(True)
        v.addWidget(ai)

        au = Section("오디오 · 룩", expanded=False)
        self.enhance = au.row("", QCheckBox("보이스 보정(노이즈·EQ·라우드니스)"))
        self.sfx = au.row("", QCheckBox("은은한 효과음"))
        self.grain = au.row("", QCheckBox("필름 그레인"))
        self.fetch_broll = au.row("", QCheckBox("자료 사진 자동 검색(위키미디어)"))
        for cb in (self.enhance, self.sfx, self.grain, self.fetch_broll):
            cb.setChecked(True)
        v.addWidget(au)
        v.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(_scroll(inner))


# ---------------------------------------------------------------------------
AGENTS = [("🎬", "총괄 감독", "구조·비트·톤 브리프"), ("✂️", "편집 감독", "추가 컷·펀치인"),
          ("🎨", "모션 디자이너", "도식·모션 장면"), ("🎞", "자료 리서처", "스톡 검색·선택"),
          ("🔤", "자막 디자이너", "강조·프리셋"), ("📱", "숏폼 PD", "후킹·구간"),
          ("✍️", "카피라이터", "제목·설명란"), ("🧐", "아트 디렉터", "렌더 검수")]
STATE_TEXT = {"idle": ("대기", "#6E6E6E"), "work": ("작업 중", "#E0A030"), "done": ("완료", "#4CAF7A"),
              "fail": ("실패", "#E0533A")}


class TeamPanel(QWidget):
    """AI 팀 현황 + 작업 단계."""

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(4)
        self.rows: dict[str, tuple[QLabel, QLabel]] = {}
        self.t0: dict[str, float] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)
        for r, (emo, name, role) in enumerate(AGENTS):
            icon = QLabel(emo)
            icon.setStyleSheet("font-size:15px;")
            lab = QLabel(f"<b>{name}</b>  <span style='color:#6E6E6E'>{role}</span>")
            st = QLabel()
            tm = QLabel("")
            tm.setObjectName("hint")
            grid.addWidget(icon, r, 0)
            grid.addWidget(lab, r, 1)
            grid.addWidget(tm, r, 2)
            grid.addWidget(st, r, 3)
            self.rows[emo] = (st, tm)
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)
        self.reset()
        line = QLabel("작업 단계")
        line.setStyleSheet("color:#8A8A8A; font-size:10px; font-weight:800; letter-spacing:1px; padding-top:10px;")
        v.addWidget(line)
        self.stages = QListWidget()
        for _k, label, _w in STAGES:
            self.stages.addItem(QListWidgetItem(f"○  {label}"))
        v.addWidget(self.stages, 1)
        self.stage_bar = QProgressBar()
        self.stage_bar.setRange(0, 1000)
        v.addWidget(self.stage_bar)

    def reset(self) -> None:
        for emo in self.rows:
            self._set(emo, "idle")
        self.t0.clear()

    def _set(self, emo: str, state: str) -> None:
        st, tm = self.rows[emo]
        text, col = STATE_TEXT[state]
        st.setText(f"<span style='color:{col}'>●</span> {text}")
        if state == "work":
            self.t0.setdefault(emo, time.time())
        elif state in ("done", "fail") and emo in self.t0:
            tm.setText(f"{time.time() - self.t0.pop(emo):.0f}s")

    def on_log(self, msg: str) -> None:
        m = msg.strip()
        if m.startswith("동시 작업:"):
            for emo in self.rows:
                if emo in m:
                    self._set(emo, "work")
            return
        for emo in self.rows:
            if m.startswith(emo):
                if "실패" in m:
                    self._set(emo, "fail")
                elif "완료" in m:
                    self._set(emo, "done")
                else:
                    self._set(emo, "work")
                return

    def on_progress(self, key: str, frac: float) -> None:
        keys = [k for k, _, _ in STAGES]
        idx = keys.index(key) if key in keys else -1
        for i, (_k, label, _w) in enumerate(STAGES):
            it = self.stages.item(i)
            if i < idx or (i == idx and frac >= 1):
                it.setText(f"●  {label}")
            elif i == idx:
                it.setText(f"◐  {label}   {frac * 100:.0f}%")
            else:
                it.setText(f"○  {label}")
        self.stage_bar.setValue(int(frac * 1000))


# ---------------------------------------------------------------------------
class ConsolePanel(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.box = QPlainTextEdit()
        self.box.setReadOnly(True)
        self.box.setMaximumBlockCount(8000)
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        mono.setPointSize(9)
        self.box.setFont(mono)
        self.box.setStyleSheet("border:none; background:#141414;")
        v.addWidget(self.box)

    def log(self, msg: str) -> None:
        self.box.appendPlainText(msg)


# ---------------------------------------------------------------------------
ICON = {".mp4": "🎬", ".jpg": "🖼", ".png": "🖼", ".srt": "💬", ".xml": "🎞", ".txt": "📝", ".md": "📄",
        ".json": "{ }"}


class ExportsPanel(QWidget):
    play = Signal(str)
    open_file = Signal(str)
    open_folder = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._activate)
        self.empty = QLabel("아직 결과물이 없습니다")
        self.empty.setObjectName("panelEmpty")
        self.empty.setAlignment(Qt.AlignCenter)
        v.addWidget(self.empty)
        v.addWidget(self.list, 1)
        bar = QHBoxLayout()
        bar.addWidget(button("결과 폴더 열기", self.open_folder.emit))
        bar.addStretch(1)
        bar.addWidget(hint("영상은 더블클릭하면 모니터에서 재생"))
        v.addLayout(bar)

    def refresh(self, job_dir: Optional[Path]) -> list[Path]:
        self.list.clear()
        out = Path(job_dir) / "output" if job_dir else None
        files = sorted(out.iterdir(), key=lambda p: (p.suffix != ".mp4", p.name)) if out and out.exists() else []
        files = [f for f in files if f.is_file()]
        for f in files:
            size = f.stat().st_size
            s = f"{size / 1e6:.1f} MB" if size > 1e6 else f"{size / 1e3:.0f} KB"
            it = QListWidgetItem(f"{ICON.get(f.suffix.lower(), '•')}   {f.name}      {s}")
            it.setData(Qt.UserRole, str(f))
            it.setToolTip(str(f))
            self.list.addItem(it)
        self.empty.setVisible(not files)
        self.list.setVisible(bool(files))
        return files

    def _activate(self, it: QListWidgetItem) -> None:
        p = it.data(Qt.UserRole)
        if p.lower().endswith(".mp4"):
            self.play.emit(p)
        else:
            self.open_file.emit(p)
