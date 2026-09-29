"""프로젝트 경로 모음."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RENDERER_DIR = ROOT / "renderer"
RENDERER_FONTS = RENDERER_DIR / "assets" / "fonts"
PROMPTS_DIR = ROOT / "prompts"
MODELS_DIR = ROOT / "models"
USER_DIR = Path(os.environ.get("CHOI_STUDIO_USER_DIR", ROOT / "user"))
DEFAULT_PROJECTS_DIR = ROOT / "projects"
SETTINGS_FILE = USER_DIR / "settings.json"


def ensure_user_dirs() -> None:
    USER_DIR.mkdir(parents=True, exist_ok=True)
