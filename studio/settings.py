"""사용자 설정(API 키, 브랜드, 경로) — user/settings.json 에 저장."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .paths import DEFAULT_PROJECTS_DIR, SETTINGS_FILE, USER_DIR, ensure_user_dirs


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
    claude_effort: str = "xhigh"      # 사고 강도 하나가 모든 에이전트에(채널 주인 2026-10-03: 에이전트별 조절 대신 전역 하나)
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
    # Google 이미지(SerpApi — serpapi.com 가입하면 대시보드에 키, 무료 월 250회·카드 없음). 재사용 가능 라이선스만 쓰고 원문 페이지에서
    # 라이선스를 다시 확인한다. 인용(아래 allow_quote)이 켜져 있으면 그 대상 자체를 설명하는 문장에서 인용 이미지도(출처·사유 표기)
    serpapi_key: str = ""
    museum_search: bool = True       # 미술관 오픈 액세스(시카고·메트·클리블랜드, CC0) — 이름 있는 작품·제품·사물(키 없음)
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
    sfx_motion_auto: bool = True      # 장면 전환·모션 등장에 흔한 효과음(우시·스우시·팝·클릭·타이핑·딩)을 자동으로(감독 지정과 함께)
    studio_workers: int = 6           # 동시에 일하는 전문 에이전트 수(전문가 여섯이 한 번에 — 줄이면 둘째 줄이 기다린다)
    # 🎨 디자인 취향(채널 주인 2026-10-04: "PPT 같다 — 디자인 taste 를 대폭 업그레이드")
    style_frame: bool = True          # 장면을 짓기 전에 이 영상의 룩(스타일 프레임 한 장 + 규칙)을 먼저 확정해 모든 디자이너에게
    design_variants: int = 3          # 🛠 시그니처 장면마다 시안 수(렌더해 🧑‍⚖️ 심사가 고름) — 1 이면 경쟁 없이 한 안
    # 🧑‍⚖️ 장면 심사(2026-10-04 채널 주인: "AI 슬롭 느낌 · 불안정") — 카드·모션 장면마다 만든 역할이 아닌 심사가 렌더를 보고
    # 하드 실패(네온·가짜 UI·PPT·내레이션 되풀이 …)·점수로 거른다. 탈락 → 고쳐서 재심사 → 그래도 탈락이면 단순 카드로(fail-closed)
    design_critic: bool = True
    # 🖥 모니터 질감(2026-10-04 채널 주인 레퍼런스 릴스): 전면 그래픽·숏폼 위 카드에 아주 약간의 흐림·개체마다 번지는 빛·
    # 서브픽셀 격자·주사선·입자·비네트. 0 = 끔, 1 = 기본(화자·사진·스톡·자막에는 얹지 않는다)
    screen_look: float = 1.0
    # (예전) 에이전트별 덮어쓰기 — 설정 창에서 뺐다(모델·사고 강도는 전역 하나). 파일에 남아 있으면 그 에이전트에만 적용된다
    agent_effort: dict[str, str] = field(default_factory=dict)
    agent_models: dict[str, str] = field(default_factory=dict)
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


# ---- 사용량 장부(user/usage.json): 작업마다 에이전트 호출 토큰·API 환산 비용·마지막 한도 창 ----
USAGE_FILE = USER_DIR / "usage.json"


def load_usage() -> dict:
    try:
        return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"jobs": [], "last_quota": {}}


def record_usage(title: str, usage: list[dict], quota: dict) -> dict:
    """작업 하나의 호출 목록을 합쳐 장부에 더한다(최근 60개). 반환: 이 작업 요약."""
    import datetime as _dt
    agg = {"title": title[:60], "at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "calls": len(usage), "input": 0, "output": 0,
           "cache_read": 0, "cache_write": 0, "api_equiv_usd": 0.0, "models": {}}
    for u in usage:
        for k in ("input", "output", "cache_read", "cache_write"):
            agg[k] += int(u.get(k, 0) or 0)
        agg["api_equiv_usd"] += float(u.get("api_equiv_usd", 0) or 0)
        m = str(u.get("model") or "")
        if m:
            agg["models"][m] = agg["models"].get(m, 0) + 1
    agg["api_equiv_usd"] = round(agg["api_equiv_usd"], 2)
    book = load_usage()
    book.setdefault("jobs", []).append(agg)
    book["jobs"] = book["jobs"][-60:]
    if quota:
        book["last_quota"] = quota
    try:
        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        USAGE_FILE.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return agg


def save_quota(quota: dict) -> None:
    """설정 창의 '한도 확인'이 받은 창 사용률을 장부에 남긴다."""
    book = load_usage()
    book["last_quota"] = quota
    try:
        USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        USAGE_FILE.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass


def usage_summary() -> str:
    """설정 창에 보이는 한 줄: 최근 작업 + 누적 API 환산 + 마지막 한도 창."""
    from .director.claude_code import format_quota
    book = load_usage()
    jobs = book.get("jobs") or []
    if not jobs and not book.get("last_quota"):
        return "아직 기록 없음 — 작업을 한 번 돌리면 호출 수·토큰·한도 창 사용률이 여기에 쌓입니다"
    parts = []
    if jobs:
        j = jobs[-1]
        parts.append(f"최근 작업 「{j['title']}」({j['at']}): 호출 {j['calls']}회 · 입력 {j['input'] + j['cache_read']:,} · "
                     f"출력 {j['output']:,} 토큰 · API 환산 약 ${j['api_equiv_usd']:.2f}")
        tot = sum(float(x.get("api_equiv_usd", 0) or 0) for x in jobs)
        parts.append(f"누적 {len(jobs)}개 작업 · API 환산 약 ${tot:.2f}(구독이라 실제 청구 없음)")
    q = format_quota(book.get("last_quota") or {})
    if q:
        parts.append("한도 창(마지막 확인): " + q)
    return "\n".join(parts)
