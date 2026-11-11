"""환경 설정: AI·팀(연결·역할별 모델) · 기획·디자인 · 소리 · 자료(스톡) · 음성 인식 · 브랜드·화자 · 경로·렌더."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QObject, QRectF, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontMetrics, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QRadioButton, QSpinBox,
                               QTabWidget, QVBoxLayout, QWidget)

from ..director.claude_code import auth_status, claude_version, describe_auth, find_claude, format_quota, open_login, probe_quota
from ..settings import save_quota, usage_summary
from ..paths import KEY_DIR, USER_DIR
from ..settings import Settings, key_dir_keys, parse_keys
from ..stock.providers import StockHub
from ..stock.sources import status as source_status
from .widgets import hint, section


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


class _StockCheck(QObject):
    """입력한 키로 제공처를 한 번씩 불러 본다 — 창을 얼리지 않게 스레드에서"""
    done = Signal(str)

    def __init__(self, keys: dict[str, str]):
        super().__init__()
        self.keys = keys

    def run(self) -> None:
        try:
            self.done.emit(StockHub.from_settings(SimpleNamespace(**self.keys)).check())
        except Exception as e:  # noqa: BLE001 - 어떤 실패든 창에 이유만 보이면 된다
            self.done.emit(f"확인 실패: {type(e).__name__}: {str(e)[:120]}")


# 모델·사고 강도는 선택만(직접 입력 없음 — 오타가 곧 오류였다) · 하나가 모든 에이전트에(채널 주인 2026-10-03)
MODEL_CHOICES = [("claude-opus-5-5", "Opus 5.5 — 기본(기획·편집·디자인 전부)"),
                 ("claude-fable-5-1", "Fable 5.1 — 최상위(더 느리고 비쌈)"),
                 ("claude-sonnet-5-5", "Sonnet 5.5 — 빠르고 저렴"),
                 ("claude-haiku-4-5-20251001", "Haiku 4.5 — 가장 저렴(시험용)")]
EFFORT_CHOICES = [("xhigh", "xhigh — 아주 높음(기본)"), ("max", "max — 최대(가장 느림)"), ("high", "high — 높음"),
                  ("medium", "medium — 보통"), ("low", "low — 낮음(시험용)")]


# 🏢 역할 이름(studio/agents/studio.py ROUTING 의 키) — 설정 창에 실제 배정표를 그대로 보여 준다
ROLE_NAMES = {"director": "총괄 감독", "cut_editor": "컷 총괄", "editor": "편집 감독", "shorts": "숏폼", "copy": "카피",
              "setpiece": "시그니처 장면", "motion": "모션 디자이너", "style_frame": "스타일 프레임", "research": "리서치",
              "stock": "자료 리서처", "timeline_review": "타임라인 검수", "art_director": "아트 디렉터",
              "card_critic": "카드 심사", "design_judge": "장면 심사", "card_revise": "카드 수정",
              "motion_revise": "모션 수정", "captions": "자막", "music": "음악 감독", "music_search": "음악 찾기",
              "colorist": "컬러리스트", "stock_pick": "사진 고르기", "portrait_pick": "효과음 고르기"}


def routing_text() -> str:
    """ROUTING 을 모델·강도별로 묶은 줄들(예: 'Opus 5.5 · xhigh — 편집 감독, 숏폼, …')."""
    from ..agents.studio import ROUTING
    label = {mid: lab.split(" — ")[0] for mid, lab in MODEL_CHOICES}
    groups: dict[tuple[str, str], list[str]] = {}
    for role, (model, eff) in ROUTING.items():
        groups.setdefault((model, eff), []).append(ROLE_NAMES.get(role, role))
    return "\n".join(f"{label.get(m, m)} · {e}  —  {', '.join(names)}" for (m, e), names in groups.items())


def open_folder(p: Path) -> None:
    """탐색기로 폴더를 연다(아직 없으면 만든다 — 열 곳이 있어야 거기에 넣는다)."""
    p.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))


def library_music_count() -> int:
    """기본 곡(assets/sound_manifest.json 의 bgm) 중 실제로 쓰는 것 — 끈 곡·비상업은 받지도 싣지도 않는다."""
    from ..sound.library import MANIFEST
    try:
        bgm = json.loads(MANIFEST.read_text(encoding="utf-8")).get("bgm", [])
    except (OSError, ValueError):
        return 0
    rows = bgm if isinstance(bgm, list) else list(bgm.values())
    return sum(1 for e in rows if e.get("enabled", True) is not False and e.get("commercial_ok", True) is not False)


PREVIEW = (480, 270)          # 1920×1080 의 1/4
SUPER_EDGE = 1920 - 64        # 슈퍼는 줄바꿈 없이 한 줄 — 이 너머는 화면 밖


def super_preview(name: str, sub: str, accent: str) -> tuple[QPixmap, QPixmap, float]:
    """롱폼 앞 이름 자막을 렌더러와 같은 치수로 1920×1080 에 그려 (전체 1/4, 왼쪽 아래 확대 1/2, 글자 오른쪽 끝 px).
    renderer/src/components/modern/Modern.tsx Super: 왼쪽 64 · 바닥에서 150 · 강조색 선 6 + 틈 20 · 이름 42/굵게 · 소개 28/중간,
    흰 글자 + 그림자(화자 위)."""
    W, H = 1920, 1080
    img = QImage(W, H, QImage.Format_RGB32)
    img.fill(QColor("#1D1916"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#3A322C"))                       # 화자 자리(얼굴·몸) — 자막이 어디에 얹히는지 보이게
    p.drawEllipse(QRectF(830, 210, 260, 330))
    p.drawRoundedRect(QRectF(620, 560, 680, 640), 220, 220)
    fam = QApplication.font().family()
    fn, fs = QFont(fam), QFont(fam)
    fn.setPixelSize(42)
    fn.setWeight(QFont.Bold)
    fs.setPixelSize(28)
    fs.setWeight(QFont.Medium)
    name_h, sub_h = 42 * 1.2, (4 + 28 * 1.3) if sub else 0.0
    top = H - 150 - (name_h + sub_h + 4)
    right = 90 + max(QFontMetrics(fn).horizontalAdvance(name), QFontMetrics(fs).horizontalAdvance(sub) if sub else 0)
    p.setBrush(QColor(accent or "#B08D57"))
    p.drawRect(QRectF(64, top, 6, name_h + sub_h + 4))

    def text(font: QFont, y: float, h: float, s: str, alpha: int) -> None:
        p.setFont(font)
        for dy, col in ((2, QColor(0, 0, 0, 140)), (0, QColor(255, 255, 255, alpha))):
            p.setPen(col)
            p.drawText(QRectF(90, y + dy, W, h), Qt.AlignLeft | Qt.AlignVCenter, s)

    text(fn, top + 2, name_h, name, 255)
    if sub:
        text(fs, top + 2 + name_h + 4, 28 * 1.3, sub, 240)
    p.end()
    zoom = img.copy(0, 760, 960, 260).scaled(480, 130, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return (QPixmap.fromImage(img.scaled(*PREVIEW, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)),
            QPixmap.fromImage(zoom), right)


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
        self.resize(1000, 700)
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
        v.addWidget(hint("    키는 'API 키' 탭에 넣습니다."))

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
        self.routing = QComboBox()
        self.routing.addItem("🏢 자동 — 일마다 맞는 모델·사고 강도(권장)", "auto")
        self.routing.addItem("전역 하나 — 아래 모델·강도를 모든 에이전트에", "global")
        _pick(self.routing, getattr(s, "agent_routing", "auto"), "auto")
        m.addRow("배정", self.routing)
        self.routing_table = QLabel(routing_text())
        self.routing_table.setObjectName("stepHint")
        self.routing_table.setWordWrap(True)
        m.addRow("", self.routing_table)
        m.addRow("모델", self.model)
        m.addRow("사고 강도", self.effort)
        m.addRow("", hint("위 표가 '자동' 배정입니다(긴 녹화는 한 단계 더 생각). 모델·사고 강도는 '전역 하나'일 때 모든 역할에, "
                          "자동이면 표에 없는 역할과 배정 모델을 못 쓸 때의 대체로 쓰입니다."))
        m.addRow("동시 에이전트", self.workers)
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
        tabs.addTab(ai, "AI · 팀")

        # --- API 키(예전엔 AI 연결·스톡·소리 탭에 흩어져 있었다). 키의 자리는 key 폴더 JSON 하나(settings.write_key_dir)
        kt = QWidget()
        fk = QFormLayout(kt)

        def key_edit(value: str, tip: str) -> QLineEdit:
            e = QLineEdit(value)
            e.setEchoMode(QLineEdit.Password)
            e.setPlaceholderText(tip)
            return e

        in_dir = key_dir_keys()
        has_dir = any(KEY_DIR.glob("*.json"))
        fk.addRow(hint(f"키는 {KEY_DIR}\\*.json 에서 읽습니다. 여기서 고쳐 저장하면 그 파일에 씁니다(지우려면 파일에서)." if has_dir
                       else "key 폴더에 키 파일(*.json)이 없어 설정 파일(user\\settings.json)에 저장합니다."))
        open_keys = QPushButton("키 폴더 열기")
        open_keys.clicked.connect(lambda: open_folder(KEY_DIR))
        fk.addRow(open_keys)
        self.key = key_edit(s.anthropic_api_key, "sk-ant-…  console.anthropic.com")
        self.gemini = key_edit(getattr(s, "gemini_key", ""), "aistudio.google.com/apikey (비우면 환경 변수 GEMINI_API_KEY)")
        self.pixabay = key_edit(s.pixabay_api_key, "pixabay.com/api/docs 에 로그인하면 문서 안에 키가 보입니다")
        self.serpapi = key_edit(getattr(s, "serpapi_key", ""), "serpapi.com 가입 → 대시보드의 API Key")
        self.unsplash = key_edit(s.unsplash_access_key, "unsplash.com/developers → New Application → Access Key")
        self.coverr = key_edit(s.coverr_api_key, "coverr.co/developers")
        self.pexels = key_edit(s.pexels_api_key, "이미 발급받은 키가 있을 때만")
        for name, field, edit, use in (
                ("Claude API", "anthropic_api_key", self.key,
                 "AI 연결에서 'Claude API 키'를 고를 때만 — 종량제 별도 결제. 구독(Claude Code)을 쓰면 비워 둡니다."),
                ("Gemini · 👂 소리 듣기", "gemini_key", self.gemini,
                 "곡·효과음 후보와 완성 믹스를 실제로 들어 보고 고릅니다. 없으면 측정값(길이·BPM·음량)으로만."),
                ("Pixabay (추천)", "pixabay_api_key", self.pixabay,
                 "자료 사진·영상·벡터(한국어 검색, 무료). 없으면 키 없는 출처(Openverse·NASA·위키미디어·미술관)만."),
                ("Google 이미지 (SerpApi)", "serpapi_key", self.serpapi,
                 "재사용 가능 라이선스 이미지(무료 월 250회) — 원문 페이지에서 라이선스를 다시 확인한 것만 씁니다."),
                ("Unsplash", "unsplash_access_key", self.unsplash, "사진 전용(데모 키는 시간당 50회)."),
                ("Coverr", "coverr_api_key", self.coverr, "영상 전용(데모 키는 시간당 50회)."),
                ("Pexels", "pexels_api_key", self.pexels, "새 키 발급이 멈췄습니다 — 예전에 받은 키가 있을 때만.")):
            row = QHBoxLayout()
            row.addWidget(edit, 1)
            where = "key 폴더" if field in in_dir else ("설정 파일" if edit.text().strip() else "없음")
            row.addWidget(QLabel(where))
            fk.addRow(name, row)
            fk.addRow("", hint(use))
        self.stock_keys = {"pixabay_api_key": self.pixabay, "unsplash_access_key": self.unsplash, "coverr_api_key": self.coverr,
                           "pexels_api_key": self.pexels, "serpapi_key": self.serpapi}
        self.key_paste = QPlainTextEdit()
        self.key_paste.setPlaceholderText("여러 키를 한 번에: 줄마다 이름=값 (예: PIXABAY_API_KEY=… / GEMINI_API_KEY=… / Unsplash: …)")
        self.key_paste.setFixedHeight(60)
        key_fill = QPushButton("칸에 나눠 넣기")
        key_note = QLabel("")

        def fill_keys() -> None:
            boxes = {**self.stock_keys, "gemini_key": self.gemini, "anthropic_api_key": self.key}
            got = parse_keys(self.key_paste.toPlainText())
            for name, value in got.items():
                boxes[name].setText(value)
            self.key_paste.clear()              # 키가 화면에 남지 않게
            key_note.setText(f"{len(got)}개 칸에 넣었습니다 — 저장을 눌러야 적용됩니다" if got else "알아본 키가 없습니다 — 줄마다 이름=값")

        key_fill.clicked.connect(fill_keys)
        fk.addRow("키 한 번에 넣기", self.key_paste)
        fk.addRow(key_fill, key_note)
        self.check_stock = QPushButton("자료 키 확인")
        self.check_stock.clicked.connect(self._check_stock)
        self.stock_msg = QLabel("누르면 자료(스톡) 제공처마다 한 번씩 불러 봅니다.")
        self.stock_msg.setWordWrap(True)
        check_row = QHBoxLayout()
        check_row.addWidget(self.check_stock)
        check_row.addWidget(self.stock_msg, 1)
        fk.addRow(check_row)
        tabs.addTab(kt, "API 키")

        # --- 기획 · 디자인(예전엔 AI 연결 탭에 섞여 있었다)
        pl = QWidget()
        fp = QFormLayout(pl)
        fp.addRow(section("🔎 주제 조사"))
        self.research_web = QCheckBox("웹 조사 — 리서치 디렉터·시그니처 장면이 인물·제품·개념을 검색해 사실·출처를 확인한다(권장)")
        self.research_web.setChecked(bool(getattr(s, "research_web", True)))
        fp.addRow(self.research_web)
        fp.addRow(hint("끄면 기억으로만 조사합니다. 결과는 부가자료/조사노트.md 에 남습니다."))
        fp.addRow(section("🎨 디자인"))
        self.style_frame = QCheckBox("스타일 프레임 — 장면을 짓기 전에 이 영상의 룩을 한 장으로 먼저 정해 모든 디자이너가 따른다")
        self.style_frame.setChecked(bool(getattr(s, "style_frame", False)))
        fp.addRow(self.style_frame)
        self.design_critic = QCheckBox("🧑‍⚖️ 장면 심사 — 만든 역할이 아닌 심사가 카드·모션 장면의 렌더를 보고 거른다(탈락이면 고치고, 그래도면 단순 카드로)")
        self.design_critic.setChecked(bool(getattr(s, "design_critic", True)))
        fp.addRow(self.design_critic)
        self.variants = QSpinBox()
        self.variants.setRange(1, 4)
        self.variants.setValue(int(getattr(s, "design_variants", 1) or 1))
        self.variants.setToolTip("시그니처 장면마다 서로 다른 방향의 시안을 이만큼 지어 렌더한 뒤 심사가 하나를 고릅니다. "
                                 "1 이면 경쟁 없이 한 안(토큰이 가장 적음).")
        fp.addRow("시안 경쟁(장면마다)", self.variants)
        fp.addRow(section("🎯 취향 기억"))
        ref = QPushButton("레퍼런스 보드 열기")
        ref.clicked.connect(self._open_reference)
        fp.addRow(ref)
        fp.addRow(hint("좋다고 느낀 사진·영상을 넣으면 Claude 가 디자인 규칙으로 옮겨 모든 디자이너·심사가 매번 봅니다. "
                       "결과 화면의 '장면 평가 👍/👎'도 여기에 쌓입니다. 장면만 다시 지어 보고 싶으면 결과 화면이나 "
                       "'최근 작업'의 🧪 디자인 벤치(렌더 없이 장면 시트까지)를 쓰세요."))
        tabs.addTab(pl, "기획 · 디자인")

        # --- 음성 인식
        asr = QWidget()
        fa = QFormLayout(asr)
        self.language = QComboBox()
        for code, label in (("auto", "자동 감지"), ("ko", "한국어"), ("en", "영어"), ("ja", "일본어"), ("zh", "중국어")):
            self.language.addItem(f"{label} ({code})", code)
        _pick(self.language, getattr(s, "whisper_language", "auto"), "auto")
        fa.addRow("말하는 언어", self.language)
        fa.addRow("", hint("원본 영상에서 말하는 언어. 다른 언어 인터뷰를 쓸 때만 바꾸세요(자막·컷 판단이 이 언어로)."))
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
        fs.addRow(hint("키는 'API 키' 탭에 넣습니다. 아래 상태는 그 칸을 따라 바뀝니다."))
        table = QGridLayout()
        for c, head in enumerate(["제공처", "상태", "여는 것", "비용", "알아 둘 것"]):
            table.addWidget(QLabel(f"<b>{head}</b>"), 0, c)
        self.source_state: dict[str, QLabel] = {}
        for r, row in enumerate(source_status(s), start=1):
            table.addWidget(QLabel(row["name"] + (" (추천)" if row["recommended"] else "")), r, 0)
            self.source_state[row["name"]] = QLabel()
            table.addWidget(self.source_state[row["name"]], r, 1)
            table.addWidget(QLabel(row["unlocks"]), r, 2)
            table.addWidget(QLabel(row["cost"]), r, 3)
            note = QLabel(row["note"])
            note.setWordWrap(True)
            table.addWidget(note, r, 4)
            if row["signup"]:
                btn = QPushButton("가입")
                btn.clicked.connect(lambda _=False, u=row["signup"]: QDesktopServices.openUrl(QUrl(u)))
                table.addWidget(btn, r, 5)
        table.setColumnStretch(4, 1)
        fs.addRow(table)
        for e in self.stock_keys.values():
            e.textChanged.connect(self._refresh_sources)
        self._refresh_sources()
        self.museums = QCheckBox("미술관 소장품 사진(시카고·메트·클리블랜드·라익스, CC0 — 키 없음)")
        self.museums.setChecked(bool(getattr(s, "museum_search", True)))
        fs.addRow("", self.museums)
        self.quote = QCheckBox("인용 자료 쓰기(웹·앱 화면 캡처 · 논문 첫 화면 · 그 대상 자체의 웹 이미지) — C 등급")
        self.quote.setChecked(bool(getattr(s, "allow_quote", False)))
        fs.addRow("", self.quote)
        fs.addRow("", hint("키를 넣은 곳을 모두 검색해 후보를 섞고, 🎞 자료 리서처가 썸네일을 보고 고릅니다. "
                           "Pixabay(사진+영상+벡터, 한국어 검색)가 기본, Google 이미지는 재사용 가능 라이선스만 찾고 원문 페이지에서 "
                           "라이선스를 다시 확인한 것만 씁니다. 키가 없어도 Openverse(CC 사진)·NASA(사진·영상)·위키미디어·미술관은 검색합니다. "
                           "출처는 화면 ▣ 와 설명란·자료 대장에 자동 표기."))
        tabs.addTab(st, "자료(스톡)")

        # --- 소리
        so = QWidget()
        fso = QFormLayout(so)
        fso.addRow(section("배경음악"))
        self.music = QComboBox()
        n_lib = library_music_count()
        modes = [("auto", "자동 — 내 음악 폴더의 곡, 비어 있으면 영상마다 맞는 곡을 찾아 받기(기본)"),
                 ("mine", "내 음악 폴더의 곡만 — 비어 있으면 음악 없이"),
                 ("library", f"기본 곡 — 프로그램에 든 곡 {n_lib}개" + (" (임시, 말 없는 자리용)" if n_lib <= 1 else "")),
                 ("off", "배경음악 없음")]
        for key, label in modes:
            self.music.addItem(label, key)
        keys = [k for k, _ in modes]
        mode = getattr(s, "music_mode", "auto")
        self.music.setCurrentIndex(keys.index(mode) if mode in keys else 0)
        fso.addRow("방식", self.music)
        self.music_dir = QLineEdit(getattr(s, "music_dir", ""))
        self.music_dir.setPlaceholderText(f"비우면 {USER_DIR / 'music'}")
        mrow = QHBoxLayout()
        mrow.addWidget(self.music_dir, 1)
        b_mine = QPushButton("열기")
        b_mine.clicked.connect(lambda: open_folder(Path(self.music_dir.text().strip() or USER_DIR / "music")))
        mrow.addWidget(b_mine)
        fso.addRow("내 음악 폴더", mrow)
        fso.addRow("", hint("곡이 여러 개면 🎼 음악 감독이 길이·빠르기·음량을 재 보고 영상에 맞는 한 곡을 고릅니다. 곡 옆에 같은 이름의 "
                            ".txt(첫 줄 등급, 그 아래 출처 문구)를 두면 업로드 정보에 출처를 그대로 적습니다."))
        b_auto = QPushButton("받은 음악 폴더 열기")
        b_auto.clicked.connect(lambda: open_folder(USER_DIR / "cache" / "music_auto"))
        fso.addRow("자동으로 받은 곡", b_auto)
        fso.addRow("", hint("Jamendo 의 연주곡 중 CC0·CC BY·CC BY-SA 만(받기 전에 원문 페이지 라이선스를 다시 확인), "
                            "출처는 업로드 정보 '배경음악'에 자동으로. 300MB 를 넘으면 오래된 곡부터 지웁니다. "
                            "맞는 곡이 없으면 아무 곡이나 쓰지 않고 음악 없이 만듭니다."))
        fso.addRow(section("효과음"))
        self.sfx = QComboBox()
        for key, lab in (("directed", "감독 지정 — 🎬 총괄 감독이 고른 장면에만(기본)"),
                         ("auto", "그래픽마다 — 템플릿별 규칙으로(예전 방식)"), ("off", "효과음 없음")):
            self.sfx.addItem(lab, key)
        cur = "auto" if getattr(s, "sfx_enabled", False) else str(getattr(s, "sfx_mode", "directed") or "directed")
        self.sfx.setCurrentIndex(max(0, self.sfx.findData(cur)))
        fso.addRow("방식", self.sfx)
        self.sfx_motion = QCheckBox("그래픽이 들어올 때 종이 소리 자동으로 — 타이틀 찢기·챕터 넘김·도장 (사진·문서는 무음, 1분에 4개까지)")
        self.sfx_motion.setChecked(bool(getattr(s, "sfx_motion_auto", True)))
        fso.addRow("", self.sfx_motion)
        b_sfx = QPushButton("받은 효과음 폴더 열기")
        b_sfx.clicked.connect(lambda: open_folder(USER_DIR / "cache" / "sfx_auto"))
        fso.addRow("자동으로 받은 소리", b_sfx)
        fso.addRow("", hint("감독이 고른 이름의 소리가 내 효과음 폴더(user\\sfx)·기본 소리에 없으면 Mixkit·Openverse 에서 상업 이용 가능한 "
                            "것(CC0·CC BY)만 찾아 받습니다. CC BY 출처는 업로드 정보 '효과음 출처'에 자동으로. 40MB 를 넘으면 오래된 것부터 지웁니다."))
        fso.addRow(hint("👂 Gemini 키가 있으면 곡·효과음 후보를 실제로 들어 보고 고릅니다 — 키는 'API 키' 탭."))
        tabs.addTab(so, "소리")

        # --- 브랜드
        br = QWidget()
        bl = QHBoxLayout(br)
        f2 = QFormLayout()
        b = s.brand
        self.b_name = QLineEdit(b.name)
        self.b_short = QLineEdit(b.short_name)
        self.b_presenter = QLineEdit(b.presenter)
        self.b_ptitle = QLineEdit(b.presenter_title)
        self.b_ptitle.setPlaceholderText("예) 홍익대 산업디자인 · 제품디자이너")
        self.b_bio = QPlainTextEdit(b.presenter_bio)
        self.b_bio.setPlaceholderText("전문 분야와 이력을 자유롭게 여러 줄로.\n예) 제품디자인 10년 · 가전 회사 인하우스 디자이너 출신\n"
                                      "디자인 이론을 입문자 눈높이로 설명하는 채널")
        self.b_bio.setFixedHeight(96)
        self.b_tone = QLineEdit(b.presenter_tone)
        self.b_tone.setPlaceholderText("예) 차분한 해설 · 존댓말 · 과장 없이 근거 위주")
        self.b_year = QLineEdit(b.year)
        self.b_accent = QPushButton(b.accent)
        self.b_accent.setStyleSheet(f"background:{b.accent}; color:#111; font-weight:700;")
        self.b_accent.clicked.connect(self._pick_color)
        f2.addRow(section("화자"))
        f2.addRow("이름", self.b_presenter)
        f2.addRow("한 줄 소개", self.b_ptitle)
        self.b_warn = QLabel("")
        self.b_warn.setObjectName("hint")
        f2.addRow("", self.b_warn)
        f2.addRow("전문 분야·이력", self.b_bio)
        f2.addRow("채널 톤", self.b_tone)
        f2.addRow("", hint("이름·한 줄 소개는 롱폼 앞 이름 자막에 나옵니다. 이력·톤은 화면에 쓰지 않고 AI 기획에 '화자 프로필'로 "
                           "넘겨, 설명 수준·예시·말투를 이 사람에게 맞춥니다(비우면 넘기지 않음)."))
        f2.addRow(section("채널"))
        f2.addRow("채널명(영문 러닝헤더)", self.b_name)
        f2.addRow("짧은 이름", self.b_short)
        f2.addRow("연도", self.b_year)
        f2.addRow("강조색", self.b_accent)
        # 디자인 v3(종이 콜라주): 레퍼런스의 초록 팔레트 또는 위 강조색
        self.b_palette = QComboBox()
        self.b_palette.addItem("토크쇼(오렌지 표식 + 숲색 띠 — 기본)", "talk")
        self.b_palette.addItem("채널 오렌지(#FC5400)", "ember")
        self.b_palette.addItem("숲 초록(짙은 초록 글자 + 민트)", "forest")
        self.b_palette.addItem("브랜드 강조색에서 만들기", "brand")
        self.b_palette.setCurrentIndex({"talk": 0, "ember": 1, "forest": 2}.get(getattr(b, "palette", "talk"), 3))
        f2.addRow("디자인 색", self.b_palette)
        fcol = QVBoxLayout()           # 칸이 위에 모이게(아래는 빈 공간)
        fcol.addLayout(f2)
        fcol.addStretch(1)
        bl.addLayout(fcol, 3)
        pv = QVBoxLayout()
        pv.addWidget(QLabel("<b>미리보기</b> — 롱폼 앞 이름 자막(실제 크기 비율)"))
        self.b_preview = QLabel()
        self.b_preview.setFixedSize(*PREVIEW)
        pv.addWidget(self.b_preview)
        pv.addWidget(hint("왼쪽 아래 확대(2배)"))
        self.b_zoom = QLabel()
        self.b_zoom.setFixedSize(480, 130)
        pv.addWidget(self.b_zoom)
        pv.addStretch(1)
        bl.addLayout(pv, 2)
        for e in (self.b_presenter, self.b_ptitle):
            e.textChanged.connect(self._refresh_super)
        self._refresh_super()
        tabs.addTab(br, "브랜드 · 화자")

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
        self.tabs = tabs
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

    def _keys(self) -> dict[str, str]:
        return {attr: e.text().strip() for attr, e in self.stock_keys.items()}

    def _refresh_sources(self) -> None:
        names = {"set": "키 있음", "empty": "키 없음", "keyless": "키 필요 없음"}
        for row in source_status(SimpleNamespace(**self._keys())):
            self.source_state[row["name"]].setText(names[row["state"]])

    def _check_stock(self) -> None:
        self.stock_msg.setText("확인 중…")
        self.check_stock.setEnabled(False)
        self._sthread = QThread(self)
        self._sworker = _StockCheck(self._keys())
        self._sworker.moveToThread(self._sthread)
        self._sthread.started.connect(self._sworker.run)
        self._sworker.done.connect(self.stock_msg.setText)
        self._sworker.done.connect(lambda _: self.check_stock.setEnabled(True))
        self._sworker.done.connect(self._sthread.quit)
        self._sthread.start()

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
            self._refresh_super()

    def _refresh_super(self) -> None:
        """화자 이름·한 줄 소개가 바뀔 때마다 이름 자막 미리보기와 길이 경고."""
        name, sub = self.b_presenter.text().strip(), self.b_ptitle.text().strip()
        pix, zoom, right = super_preview(name or "이름", sub, self.b_accent.text().strip())
        self.b_preview.setPixmap(pix)
        self.b_zoom.setPixmap(zoom)
        if right > SUPER_EDGE:
            warn = "⚠ 화면 밖으로 잘립니다 — 줄여 주세요"
        elif right > 960:
            warn = "⚠ 화면 가운데(화자 쪽)까지 닿습니다 — 짧을수록 좋습니다"
        else:
            warn = ""
        self.b_warn.setText(f"{len(sub)}자 · " + (warn or "한 줄로 나옵니다(줄바꿈 없음)"))
        self.b_warn.setObjectName("warn" if warn else "hint")
        self.b_warn.style().unpolish(self.b_warn)
        self.b_warn.style().polish(self.b_warn)

    def show_tab(self, name: str) -> None:
        """이름이 name 으로 시작하는 탭을 연다(메인 창 칩에서 바로 그 탭으로)."""
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i).startswith(name):
                self.tabs.setCurrentIndex(i)
                return

    def _open_reference(self) -> None:
        from .reference_dialog import ReferenceDialog
        ReferenceDialog(self).exec()

    def _save(self) -> None:
        s = self.s
        s.ai_backend = "api" if self.rb_api.isChecked() else "claude_code"
        s.claude_code_path = self.cc_path.text().strip()
        s.anthropic_api_key = self.key.text().strip()
        s.claude_model = str(self.model.currentData() or "claude-opus-5-5")
        s.claude_effort = str(self.effort.currentData() or "xhigh")
        s.agent_routing = str(self.routing.currentData() or "auto")
        s.agent_models, s.agent_effort = {}, {}      # 옛 에이전트별 덮어쓰기는 저장할 때 지운다(배정은 agent_routing)
        s.studio_workers = self.workers.value()
        s.research_web = self.research_web.isChecked()
        s.style_frame = self.style_frame.isChecked()
        s.design_critic = self.design_critic.isChecked()
        s.design_variants = self.variants.value()
        s.pixabay_api_key = self.pixabay.text().strip()
        s.unsplash_access_key = self.unsplash.text().strip()
        s.coverr_api_key = self.coverr.text().strip()
        s.pexels_api_key = self.pexels.text().strip()
        s.serpapi_key = self.serpapi.text().strip()
        s.gemini_key = self.gemini.text().strip()
        s.museum_search = self.museums.isChecked()
        s.whisper_model = self.whisper.currentText().strip()
        s.whisper_device = self.device.currentText()
        s.whisper_language = str(self.language.currentData() or "auto")
        s.brand.name = self.b_name.text().strip()
        s.brand.short_name = self.b_short.text().strip()
        s.brand.presenter = self.b_presenter.text().strip()
        s.brand.presenter_title = self.b_ptitle.text().strip()
        s.brand.presenter_bio = self.b_bio.toPlainText().strip()
        s.brand.presenter_tone = self.b_tone.text().strip()
        s.brand.year = self.b_year.text().strip()
        s.brand.accent = self.b_accent.text().strip()
        s.brand.palette = self.b_palette.currentData() or "talk"
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
        s.sfx_motion_auto = self.sfx_motion.isChecked()
        s.music_mode = self.music.currentData() or "auto"
        s.music_dir = self.music_dir.text().strip()
        s.save()
        self.accept()
