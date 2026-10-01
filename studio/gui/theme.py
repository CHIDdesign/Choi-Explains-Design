"""다크 테마 — 깊은 잉크 바탕 + 채널 시그널 레드 한 곳(버튼·진행 표시)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from ..paths import RENDERER_FONTS

# 패널 회색 단계(어두운 → 밝은)
BG0 = "#141414"      # 창 바탕·패널 사이 틈
BG1 = "#1C1C1C"      # 패널 본문
BG2 = "#232323"      # 패널 헤더·입력칸
BG3 = "#2C2C2C"      # 호버·선택
LINE = "#343434"     # 구분선
TEXT = "#E4E4E4"
TEXT2 = "#A3A3A3"    # 보조 글자
TEXT3 = "#6E6E6E"    # 비활성

# 타임라인 클립 색(카테고리)
CLIP = {
    "video": "#3F6FA0",     # V1 영상(컷)
    "audio": "#3E8A5E",     # A1 음성
    "graphic": "#7A5BB5",   # 도식·카드
    "motion": "#C6902F",    # 모션 장면
    "broll": "#2F9A91",     # 스톡·자료 사진
    "caption": "#4F4F4F",   # 자막
    "title": "#B8402A",     # 표지·챕터
}

UI_FONT = "Pretendard"


def load_fonts() -> str:
    """renderer/assets/fonts/ui 의 Pretendard OTF 를 등록(없으면 시스템 한글 글꼴)."""
    fam = ""
    ui = Path(RENDERER_FONTS) / "ui"
    if ui.exists():
        for f in sorted(ui.glob("*.otf")):
            fid = QFontDatabase.addApplicationFont(str(f))
            fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            fam = fam or (fams[0] if fams else "")
    if not fam:
        for name in ("Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", "Segoe UI"):
            if name in QFontDatabase.families():
                fam = name
                break
    return fam or QApplication.font().family()


def apply(app: QApplication, accent: str) -> None:
    fam = load_fonts()
    f = QFont(fam, 10)
    f.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(f)
    app.setStyle("Fusion")
    pal = QPalette()
    for role, col in [(QPalette.Window, BG1), (QPalette.WindowText, TEXT), (QPalette.Base, BG2),
                      (QPalette.AlternateBase, BG1), (QPalette.Text, TEXT), (QPalette.Button, BG2),
                      (QPalette.ButtonText, TEXT), (QPalette.Highlight, accent), (QPalette.HighlightedText, "#111111"),
                      (QPalette.ToolTipBase, BG3), (QPalette.ToolTipText, TEXT), (QPalette.PlaceholderText, TEXT3)]:
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(qss(accent, fam))


def qss(accent: str, fam: str = UI_FONT) -> str:
    return f"""
    * {{ font-family: "{fam}"; }}
    QMainWindow, QWidget#root {{ background: {BG0}; }}
    QWidget {{ color: {TEXT}; font-size: 12px; }}
    QToolTip {{ background: {BG3}; color: {TEXT}; border: 1px solid {LINE}; padding: 5px 7px; }}

    /* ---------- 탭·분리선 ---------- */
    QDockWidget {{ titlebar-close-icon: none; titlebar-normal-icon: none; }}
    QDockWidget::title {{ background: {BG2}; padding: 7px 10px; border-bottom: 1px solid {LINE};
        text-align: left; font-weight: 600; color: {TEXT2}; }}
    QDockWidget > QWidget {{ background: {BG1}; }}
    QMainWindow::separator {{ background: {BG0}; width: 4px; height: 4px; }}
    QMainWindow::separator:hover {{ background: {accent}; }}
    QTabBar {{ background: {BG2}; }}
    QTabBar::tab {{ background: transparent; color: {TEXT3}; padding: 7px 12px; border: none;
        border-bottom: 2px solid transparent; font-weight: 600; }}
    QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {accent}; }}
    QTabBar::tab:hover {{ color: {TEXT}; }}
    QTabWidget::pane {{ border: none; background: {BG1}; }}

    /* ---------- 헤더 바 ---------- */
    QWidget#header {{ background: {BG0}; border-bottom: 1px solid {LINE}; }}
    QLabel#brand {{ font-size: 13px; font-weight: 800; letter-spacing: 1px; color: {TEXT}; }}
    QLabel#brandDot {{ color: {accent}; font-size: 16px; }}
    QPushButton#workspace {{ background: transparent; color: {TEXT3}; border: none; padding: 6px 10px;
        font-weight: 600; border-bottom: 2px solid transparent; border-radius: 0; }}
    QPushButton#workspace:checked {{ color: {TEXT}; border-bottom: 2px solid {accent}; }}
    QPushButton#workspace:hover {{ color: {TEXT}; }}
    QLabel#chip {{ background: {BG2}; border: 1px solid {LINE}; border-radius: 10px; padding: 3px 10px;
        color: {TEXT2}; font-size: 11px; }}

    /* ---------- 입력 ---------- */
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {{ background: {BG0}; border: 1px solid {LINE};
        border-radius: 3px; padding: 5px 7px; selection-background-color: {accent}; selection-color: #111; }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {accent}; }}
    QPlainTextEdit {{ font-size: 13px; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{ background: {BG2}; border: 1px solid {LINE}; selection-background-color: {BG3}; }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 14px; border: none; background: {BG2}; }}

    QPushButton {{ background: {BG2}; border: 1px solid {LINE}; border-radius: 3px; padding: 6px 12px; color: {TEXT}; }}
    QPushButton:hover {{ background: {BG3}; border-color: #4A4A4A; }}
    QPushButton:pressed {{ background: {BG0}; }}
    QPushButton:disabled {{ color: {TEXT3}; }}
    QPushButton#primary {{ background: {accent}; border: none; color: #111; font-weight: 800; padding: 7px 16px; }}
    QPushButton#primary:hover {{ background: #FF5A34; }}
    QPushButton#primary:disabled {{ background: #4A2A22; color: #8A6A62; }}
    QPushButton#ghost {{ background: transparent; border: none; color: {TEXT2}; padding: 4px 6px; }}
    QPushButton#ghost:hover {{ color: {TEXT}; background: {BG3}; }}
    QToolButton {{ background: transparent; border: none; color: {TEXT2}; padding: 4px; border-radius: 3px; }}
    QToolButton:hover {{ background: {BG3}; color: {TEXT}; }}
    QToolButton:checked {{ color: {accent}; }}

    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid #555; border-radius: 3px; background: {BG0}; }}
    QCheckBox::indicator:checked {{ background: {accent}; border: 1px solid {accent}; }}
    QRadioButton::indicator {{ width: 13px; height: 13px; border: 1px solid #555; border-radius: 7px; background: {BG0}; }}
    QRadioButton::indicator:checked {{ background: {accent}; border: 3px solid {BG0}; outline: 1px solid {accent}; }}

    QProgressBar {{ background: {BG0}; border: 1px solid {LINE}; border-radius: 2px; height: 8px; text-align: center;
        color: transparent; }}
    QProgressBar::chunk {{ background: {accent}; border-radius: 2px; }}
    QSlider::groove:horizontal {{ height: 4px; background: {LINE}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: {TEXT}; }}

    QScrollBar:vertical, QScrollBar:horizontal {{ background: {BG1}; border: none; width: 10px; height: 10px; }}
    QScrollBar::handle {{ background: #3C3C3C; border-radius: 4px; min-height: 24px; min-width: 24px; }}
    QScrollBar::handle:hover {{ background: #555; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QListWidget, QTreeWidget {{ background: {BG1}; border: none; outline: none; }}
    QListWidget::item, QTreeWidget::item {{ padding: 4px; border-radius: 3px; }}
    QListWidget::item:selected, QTreeWidget::item:selected {{ background: {BG3}; color: {TEXT}; }}
    QListWidget::item:hover, QTreeWidget::item:hover {{ background: {BG2}; }}
    QHeaderView::section {{ background: {BG2}; color: {TEXT2}; border: none; border-bottom: 1px solid {LINE};
        padding: 4px 6px; font-weight: 600; }}

    QMenuBar {{ background: {BG0}; color: {TEXT2}; }}
    QMenuBar::item {{ padding: 5px 10px; background: transparent; }}
    QMenuBar::item:selected {{ background: {BG3}; color: {TEXT}; }}
    QMenu {{ background: {BG2}; border: 1px solid {LINE}; padding: 4px; }}
    QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 3px; }}
    QMenu::item:selected {{ background: {BG3}; }}
    QMenu::separator {{ height: 1px; background: {LINE}; margin: 4px 6px; }}

    QStatusBar {{ background: {BG0}; color: {TEXT2}; border-top: 1px solid {LINE}; }}
    QStatusBar::item {{ border: none; }}

    /* ---------- 오토파일럿 화면 ---------- */
    QLabel#brandSub {{ color: {TEXT3}; font-size: 12px; padding-left: 6px; }}
    QLabel#pageTitle {{ font-size: 26px; font-weight: 800; letter-spacing: -0.5px; color: {TEXT}; }}
    QLabel#pageSub {{ font-size: 13px; color: {TEXT2}; }}
    QFrame#stepCard {{ background: {BG1}; border: 1px solid {LINE}; border-radius: 14px; }}
    QLabel#stepNum {{ background: {accent}; color: #111; border-radius: 15px; font-weight: 800; font-size: 14px; }}
    QLabel#stepTitle {{ font-size: 17px; font-weight: 800; }}
    QLabel#stepHint {{ color: {TEXT2}; font-size: 12px; }}
    QFrame#stepCard QPlainTextEdit {{ background: {BG0}; border: 1px solid {LINE}; border-radius: 10px;
        padding: 10px 12px; font-size: 14px; line-height: 150%; }}
    QFrame#stepCard QPlainTextEdit:focus {{ border: 1px solid {accent}; }}
    QFrame#videoDrop {{ background: {BG0}; border: 2px dashed #3A3A3A; border-radius: 12px; }}
    QFrame#videoDrop:hover {{ border-color: {accent}; }}
    QLabel#dropEmpty {{ color: {TEXT3}; font-size: 15px; font-weight: 600; }}
    QLabel#dropName {{ font-size: 14px; font-weight: 700; }}
    QLabel#dropMeta {{ color: {TEXT2}; font-size: 12px; }}
    QLabel#poster {{ background: #000; border-radius: 8px; }}
    QPushButton#hero {{ background: {accent}; color: #111; border: none; border-radius: 12px; font-size: 17px;
        font-weight: 900; padding: 15px 34px; }}
    QPushButton#hero:hover {{ background: #FF5A34; }}
    QPushButton#hero:disabled {{ background: #3A2520; color: #7A5A52; }}
    QPushButton#primarySmall {{ background: {accent}; color: #111; border: none; border-radius: 6px; font-weight: 800;
        padding: 7px 14px; }}
    QPushButton#primarySmall:disabled {{ background: #3A2520; color: #7A5A52; }}
    QPushButton#chip {{ background: {BG2}; border: 1px solid {LINE}; border-radius: 13px; padding: 5px 12px;
        color: {TEXT2}; font-size: 12px; }}
    QPushButton#chip[ok="true"] {{ color: #8FD6A0; border-color: #2F5B3A; }}
    QPushButton#chip[ok="false"] {{ color: #FFB199; border-color: #6A3325; }}
    QLabel#bigPct {{ font-size: 44px; font-weight: 900; color: {accent}; }}
    QProgressBar#thick {{ height: 10px; border-radius: 5px; border: none; background: {BG2}; }}
    QProgressBar#thick::chunk {{ border-radius: 5px; background: {accent}; }}
    QFrame#panel {{ background: {BG1}; border: 1px solid {LINE}; border-radius: 14px; }}
    QLabel#panelTitle {{ font-size: 13px; font-weight: 800; color: {TEXT2}; letter-spacing: 0.5px; }}
    QLabel#stageTodo {{ color: {TEXT3}; font-size: 13px; }}
    QLabel#stageNow {{ color: {TEXT}; font-size: 13px; font-weight: 800; }}
    QLabel#stageDone {{ color: #8FD6A0; font-size: 13px; }}
    QPlainTextEdit#log {{ background: {BG0}; border: none; border-radius: 8px; font-size: 12px; color: {TEXT2};
        font-family: "{fam}"; }}
    QFrame#resultCard {{ background: {BG1}; border: 1px solid {LINE}; border-radius: 14px; }}
    QLabel#resultTitle {{ font-size: 16px; font-weight: 800; }}
    QLabel#hint {{ color: {TEXT3}; font-size: 11px; }}
    QLabel#fieldLabel {{ color: {TEXT2}; }}
    """
