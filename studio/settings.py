"""사용자 설정(API 키, 브랜드, 경로) — user/settings.json 에 저장."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .paths import DEFAULT_PROJECTS_DIR, SETTINGS_FILE, ensure_user_dirs


@dataclass
class Brand:
    # 채널 브랜딩. 디자인 시스템의 모든 그래픽이 이 값을 사용한다.
    name: str = "CHOI EXPLAINS DESIGN"
    short_name: str = "CHOI"
    handle: str = ""
    presenter: str = "최은준"
    presenter_title: str = "홍익대학교 산업디자인 · 제품디자인"
    accent: str = "#F93107"   # Musicbed 2026 리포트 표지의 시그널 레드-오렌지
    ink: str = "#111111"
    paper: str = "#F4F4F2"
    year: str = "2026"
    # 디자인 색: ember = 채널 오렌지(#FC5400, 디자인 v4 기본) · forest = v3 레퍼런스의 짙은 초록 + 민트 · brand = 위 강조색에서 계산
    palette: str = "ember"


@dataclass
class RenderSettings:
    concurrency: int = 0            # 0 = 자동(코어 수 기반)
    crf: int = 18
    x264_preset: str = "medium"
    gl: str = "angle"               # Windows + NVIDIA 에서 가장 안정적
    browser_executable: str = ""    # 비우면 Remotion 이 chrome-headless-shell 을 자동 설치/사용


@dataclass
class Settings:
    # AI 연결: claude_code = 이 PC 의 Claude Code(Pro/Max 구독 사용량, 추가 결제 없음) | api = Claude API 키(종량제)
    ai_backend: str = "claude_code"
    claude_code_path: str = ""        # 비우면 자동 탐색(%USERPROFILE%\.local\bin\claude.exe, PATH)
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "high"
    whisper_model: str = "large-v3"
    whisper_device: str = "auto"      # auto | cuda | cpu
    whisper_compute: str = "auto"     # auto | float16 | int8_float16 | int8
    whisper_batch: int = 8            # 배치 추론 크기(GPU 약 3~4배·CPU 약 2배 빠름, 메모리가 모자라면 자동으로 줄임). 1 = 순차
    ffmpeg_path: str = ""
    ffprobe_path: str = ""
    node_path: str = ""
    projects_dir: str = str(DEFAULT_PROJECTS_DIR)
    wikimedia_contact: str = ""       # Wikimedia API User-Agent 연락처(권장)
    # 🎞 무료 스톡(상업적 이용 가능) — 키가 있는 곳을 모두 검색
    pixabay_api_key: str = ""        # https://pixabay.com/api/docs/ (로그인하면 문서에 키가 보임) — 기본 추천
    unsplash_access_key: str = ""    # https://unsplash.com/developers (사진 전용, 데모 시간당 50회)
    coverr_api_key: str = ""         # https://coverr.co/developers (영상 전용, 데모 시간당 50회)
    pexels_api_key: str = ""         # https://www.pexels.com/ko-kr/api/ (이미 키가 있으면)
    keyless_stock: bool = True       # 키 없이 되는 Openverse(CC 사진) 검색도 함께
    # C 등급(인용) 자료 — 웹·앱 화면 캡처, 논문 첫 화면, 비자유 대표 이미지. 그 대상을 설명하는 문장에서만 6초 이내·종이 위.
    # 기본 끔(작업지시서 WP7) — 켜면 자료 대장·검토 시트에 인용 목록이 남는다(docs/upgrade/저작권_위험등급_정책.md)
    allow_quote: bool = False
    download_sounds: bool = True     # 효과음·배경음악(Pixabay 등)을 처음 실행 때 내려받기
    # 🔊 소리 — 채널 주인: "효과음과 음원이 싹 다 별로". 이상한 소리를 넣느니 넣지 않는다
    sfx_enabled: bool = False        # (예전) 효과음 켜기 — True 면 sfx_mode 'auto' 와 같다
    # 효과음: directed = 🎬 총괄 감독(Claude)이 트리트먼트에서 고른 곳에만(기본, docs/upgrade/14) · auto = 예전 규칙(템플릿마다)
    #         · off = 없음
    sfx_mode: str = "directed"
    music_mode: str = "mine"         # 배경음악: mine = 내 음악 폴더의 곡만 · library = 기본 라이브러리 · off = 없음
    music_dir: str = ""              # 내 음악 폴더(비우면 user/music)
    # 🎬 AI 스튜디오(멀티 에이전트) — Claude 총괄 제작(docs/upgrade/14): 조사·기획·디자인 판단은 Claude 가 하고,
    # 같은 품질을 낼 수 있는 기계적인 일(음성 인식·얼굴 추적·색 측정·렌더·믹스)만 다른 알고리즘이 한다
    research_web: bool = True         # 🔎 주제 조사·🛠 시그니처 장면이 웹 검색·가져오기를 쓴다(끄면 기억으로만)
    studio_workers: int = 6           # 동시에 일하는 전문 에이전트 수(전문가 여섯이 한 번에 — 줄이면 둘째 줄이 기다린다)
    agent_effort: dict[str, str] = field(default_factory=dict)   # 예: {"motion": "max", "copy": "low", "timeline_review": "high"}
    agent_models: dict[str, str] = field(default_factory=dict)   # 예: {"copy": "claude-sonnet-5-5"}
    glossary: dict[str, str] = field(default_factory=lambda: {
        "디자인 띵킹": "디자인 씽킹",
        "더블 다이어몬드": "더블 다이아몬드",
        "프로토 타입": "프로토타입",
    })
    brand: Brand = field(default_factory=Brand)
    render: RenderSettings = field(default_factory=RenderSettings)

    # ------------------------------------------------------------------
    @classmethod
    def load(cls) -> "Settings":
        if not SETTINGS_FILE.exists():
            return cls()
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Settings":
        s = cls()
        for f in fields(cls):
            if f.name not in raw:
                continue
            if f.name == "brand":
                s.brand = _merge(Brand(), raw["brand"])
            elif f.name == "render":
                s.render = _merge(RenderSettings(), raw["render"])
            else:
                setattr(s, f.name, raw[f.name])
        # 예전 기본값(4)으로 저장된 설정: 전문가 여섯 중 둘이 앞 넷을 기다려 기획이 한 바퀴 더 걸렸다 → 6
        if raw.get("studio_workers") == 4:
            s.studio_workers = 6
        # 작업 폴더: 비어 있으면 기본(프로그램 폴더/projects). 프로그램 폴더를 옮기고 예전 폴더를 지웠으면(설치 안내대로
        # D:\ChoiStudio 로 옮긴 경우) 예전 절대 경로 대신 기본으로 — 꽉 찬 C: 에 예전 경로를 다시 만들지 않게
        pd = str(s.projects_dir or "")
        if not pd or (Path(pd).name == DEFAULT_PROJECTS_DIR.name and not Path(pd).parent.exists()):
            s.projects_dir = str(DEFAULT_PROJECTS_DIR)
        return s

    def save(self) -> None:
        ensure_user_dirs()
        d = asdict(self)
        if Path(d.get("projects_dir") or "") == DEFAULT_PROJECTS_DIR:
            d["projects_dir"] = ""          # 기본 폴더는 비워 저장 → 프로그램 폴더를 옮겨도 따라간다
        SETTINGS_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _merge(obj, raw: dict[str, Any]):
    if not isinstance(raw, dict):
        return obj
    names = {f.name for f in fields(obj)}
    for k, v in raw.items():
        if k in names:
            setattr(obj, k, v)
    return obj
