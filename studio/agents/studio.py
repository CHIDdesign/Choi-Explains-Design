"""🎬 AI 영상 스튜디오 — 총괄 감독 한 명이 전문 에이전트들을 병렬로 굴린다.

1. 🎬 총괄 감독: 전사본 전체 → 크리에이티브 브리프(구조·비트·톤·숏폼 아이디어)
2. 브리프를 받은 전문 에이전트들이 **동시에** 작업(같은 시스템 프롬프트 + 전사본 → 프롬프트 캐시 공유):
   ✂️ 편집 감독 · 🎨 모션 디자이너 · 🎞 자료 리서처 · 🔤 자막 디자이너 · 📱 숏폼 PD · ✍️ 카피라이터
3. 결과를 기존 편집 계획 모양(LONG_PLAN / SHORTS_PLAN)으로 합친다(+ spec · stock · 강조 유형 확장 키).
4. 렌더 단계에서 🧐 아트 디렉터가 실제로 렌더된 스틸만 보고(블라인드 비평) 수정 지시,
   🎨 모션 디자이너가 지적받은 장면을 다시 설계한다.

에이전트 하나가 실패해도 나머지 결과로 계속 진행한다(총괄 감독이 실패하면 단일 디렉터 모드로 폴백).
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ..text.topic import strip_label
from ..director.catalog import catalog_markdown
from ..director.claude import ClaudeClient, DirectorError, extract_json
from ..director.context import JobBrief, load_prompt, shorts_instruction
from ..motion.card import STYLES, clean_card, fragment
from ..motion.spec import clean_spec
from ..util import Cancelled, CancelToken, LogFn, noop_log
from . import schemas as S


@dataclass(frozen=True)
class Agent:
    key: str
    label: str
    prompt: str          # prompts/agents/<prompt>.md
    schema: dict
    effort: str          # 기본 사고 강도(설정에서 바꿀 수 있음)
    max_tokens: int = 32000
    tools: tuple[str, ...] = ()     # 웹 조사 도구(WebSearch·WebFetch) — 🔎 주제 조사·🛠 시그니처 장면만
    max_turns: int = 0              # 도구를 쓰는 에이전트의 도구 사용 상한
    timeout: float = 0.0            # 0 = 클라이언트 기본(30분)


WEB = ("WebSearch", "WebFetch")

AGENTS: dict[str, Agent] = {a.key: a for a in [
    # 🔎 리서치 디렉터(docs/upgrade/14): 대본·주제만 보고 웹에서 조사 — 팀 전원이 같은 사실·자료 목록에서 출발한다
    Agent("research", "🔎 리서치 디렉터", "researcher", S.RESEARCH, "high", 64000, WEB, 60, 3000.0),
    Agent("director", "🎬 총괄 감독", "director", S.BRIEF, "high", 48000),
    # 🛠 시그니처 장면 빌더: 트리트먼트의 시그니처 장면 하나를 자유 HTML 카드로 정밀 재현(UI·제품·데이터 이야기)
    Agent("setpiece", "🛠 시그니처 장면", "setpiece", S.SETPIECE, "high", 48000, WEB, 16, 2400.0),
    Agent("cut_editor", "✂️ 컷 편집 총괄", "cut_editor", S.CUT_REVIEW, "high", 16000),
    Agent("editor", "✂️ 편집 감독", "editor", S.EDITOR, "high", 16000),
    Agent("motion", "🎨 모션 디자이너", "motion", S.MOTION, "high", 48000),
    # 자료 리서처 v2: 증거 계획(need·트리트먼트) — 증거 설계가 영상의 인상을 좌우한다(13 문서 3절: medium → high)
    Agent("stock", "🎞 자료 리서처", "visual_researcher", S.EVIDENCE, "high", 24000),
    Agent("captions", "🔤 자막 디자이너", "captions", S.CAPTIONS, "high", 24000),
    Agent("shorts", "📱 숏폼 PD", "shorts", S.SHORTS, "high", 32000),
    Agent("copy", "✍️ 카피라이터", "copy", S.COPY, "high", 16000),
    # 그림 고르기는 보는 판단이라 Claude 가 한다(토큰보다 맞는 그림) — 예전 low
    Agent("stock_pick", "🎞 자료 리서처(선택)", "stock_pick_v2", S.EVIDENCE_PICK, "medium", 8000),
    Agent("portrait_pick", "📷 자료 리서처(인물 사진)", "portrait_pick", S.STOCK_PICK, "medium", 8000),
    Agent("art_director", "🧐 아트 디렉터", "art_director", S.QA, "high", 24000),
    Agent("motion_revise", "🎨 모션 디자이너(수정)", "motion_revise", S.MOTION_REVISE, "high", 24000),
    Agent("card_revise", "🃏 카드 디자이너(수정)", "card_revise", S.CARD_REVISE, "high", 32000),
    Agent("colorist", "🎨 컬러리스트", "colorist", S.GRADE, "medium", 8000),
    Agent("timeline_review", "🧐 타임라인 검수", "timeline_review", S.TIMELINE_QA, "high", 16000),
    # 🎼 음악 감독 — SPECIALISTS 에 넣지 않는다: 컷이 확정된 뒤 따로 부른다(13 문서 3절)
    Agent("music", "🎼 음악 감독", "music_supervisor", S.MUSIC, "high", 12000),
    # 🎨 스타일 프레임 — 장면을 짓기 전에 이 영상의 룩을 한 장 + 규칙으로 확정(모든 디자인 역할이 그림으로 받는다)
    Agent("style_frame", "🎨 스타일 프레임", "style_frame", S.STYLE_FRAME, "high", 32000),
    # 🧑‍⚖️ 시안 심사 — 시그니처 장면의 시안 여럿을 렌더해 나란히 보고 하나를 고른다(설정 design_variants)
    Agent("design_judge", "🧑‍⚖️ 시안 심사", "design_judge", S.DESIGN_JUDGE, "high", 8000),
    # 🧑‍⚖️ 장면 심사 — 카드·모션 장면마다 독립 critic(만든 역할이 아닌 눈): 하드 실패·점수 → pass/reject(설정 design_critic)
    Agent("card_critic", "🧑‍⚖️ 장면 심사", "card_critic", S.CARD_CRITIC, "high", 6000),
]}

SPECIALISTS = ("editor", "motion", "stock", "captions", "shorts", "copy")


def studio_system_prompt(*, design: bool = True) -> str:
    """에이전트 시스템 프롬프트. design=True(디자인을 짓거나 고치거나 심사하는 역할)는 구도 원형·렌더 검증 카드 예시까지,
    그 밖의 역할(기획·편집·자막·카피·숏폼 …)은 문법만 — 예시 약 1.4만 토큰은 디자인 역할만 읽는다(🪶). CLI 의 구조화 출력은
    역할마다 앞부분을 달리 붙여 역할 사이 시스템 캐시가 어차피 나뉘므로 따로 두어도 캐시 손해가 없다."""
    parts = [
        load_prompt("system_studio.md"),
        "\n\n# 채널 스타일 가이드\n\n" + load_prompt("style_guide.md"),
        "\n\n# 숏폼 후킹 가이드\n\n" + load_prompt("hooks.md"),
        "\n\n" + playbook_block(),
        "\n\n# 그래픽 템플릿 카탈로그\n\n" + catalog_markdown(),
        "\n\n" + load_prompt("motion_dsl.md") + (motion_examples_block() if design else ""),
        "\n\n" + load_prompt("card_dsl.md"),
        ("\n\n" + load_prompt("layouts.md") + "\n\n" + load_prompt("icons.md") + card_examples_block()) if design else "",
        "\n\n# 디자인 스킬 노트(오픈소스 스킬·편집 이론에서 정리)\n\n" + skills_block(),
    ]
    return "\n".join(p for p in parts if p.strip())


# 디자인을 짓거나 고치거나 심사하는 역할 — 구도 원형·검증된 카드 예시를 시스템에 받는다(그 밖은 studio_system_prompt(design=False))
DESIGN_AGENTS = frozenset({"motion", "motion_revise", "card_revise", "setpiece", "art_director", "style_frame", "design_judge",
                           "card_critic"})


# 🪶 토큰 절약 — 디자인 규칙 전부(플레이북·카탈로그·모션/카드 DSL·예제·스킬, 약 5~6만 토큰)가 필요 없는 역할은
# 채널 헌장 + 스타일 가이드(+ 그 일의 플레이북 한 장)만 받는다. 이 역할들의 지시(prompts/agents/*.md)는 그것만으로 완결이다.
LEAN_AGENTS: dict[str, tuple[str, ...]] = {
    "cut_editor": (), "colorist": (), "portrait_pick": (),
    "stock_pick": ("playbook/04_visual_evidence.md",),
    "music": ("playbook/07_sound.md", "skills/music_direction.md"),
}
# 같은 역할을 한 작업에서 여러 번 부르는 것 — 공통 자료를 시스템 프롬프트 끝에 붙여 캐시에서 읽게 한다(ctx_in_system)
REPEATED_AGENTS = frozenset({"stock_pick", "portrait_pick", "motion_revise", "card_revise", "art_director", "card_critic"})
# 같은 역할의 호출이 한꺼번에 뜨면 서로의 캐시를 못 읽는다(쓰는 중) — 첫 호출이 앞부분을 처리할 시간을 주고 나머지를 띄운다
PRIME_S = 15.0


def lean_system_prompt(extra: tuple[str, ...] = ()) -> str:
    parts = [load_prompt("system_studio.md"), "\n\n# 채널 스타일 가이드\n\n" + load_prompt("style_guide.md")]
    for rel in extra:
        try:
            parts.append("\n\n" + load_prompt(rel))
        except OSError:
            continue
    return "\n".join(p for p in parts if p.strip())


# 에이전트별 스킬 노트(prompts/skills/agents/*.md — 전문가·제작자 자료에서 정리, 그 에이전트의 지시 끝에만 붙는다)
AGENT_SKILLS: dict[str, tuple[str, ...]] = {
    "research": ("research",), "director": ("director", "sound_design"), "editor": ("editor",),
    "cut_editor": ("editor",), "motion": ("motion", "jitter"), "motion_revise": ("motion",),
    "setpiece": ("setpiece", "motion", "jitter"),
    "card_revise": ("setpiece", "jitter"), "art_director": ("art_director",), "timeline_review": ("art_director", "editor"),
    "music": ("music",), "captions": ("captions",), "copy": ("copy",), "shorts": ("shorts",),
    "stock": ("stock",), "stock_pick": ("stock",), "portrait_pick": ("stock",),
    "style_frame": ("setpiece", "motion", "jitter"), "design_judge": ("art_director", "jitter"),
    "card_critic": ("art_director", "jitter"),
}

# 🎨 스타일 프레임·🎯 취향 보드를 그림으로 받는 역할 — 짓는 역할·심사는 둘 다(정지 화면 + 움직임 칸 + 보드),
# 고치는 역할은 스타일 프레임 정지 화면 한 장만(여러 번 불려 그림 토큰이 쌓인다)
REF_FULL = frozenset({"motion", "setpiece", "design_judge", "art_director", "card_critic"})
REF_STILL = frozenset({"motion_revise", "card_revise"})
# 시안 경쟁(Best-of-N)의 방향 — 같은 장면을 서로 다른 구도로 지어 심사가 고른다. 첫 안만 웹 도구를 쓴다(사양 확인은 한 번이면 된다)
VARIANT_HINTS = (
    "A안 — 장면 정보·트리트먼트가 가리키는 가장 정확한 구도(원형은 네 판단).",
    "B안 — A안과 다른 구도 원형으로: 주인공을 하나의 큰 사물·숫자·도형으로 키우고 글자는 최소로(화면의 60% 이상이 형태).",
    "C안 — 또 다른 방향: 과정·변화·관계를 움직임으로 보여 준다(경로 이동·쌓임·모양 바꾸기·선 그리기 중 하나가 주인공).",
    "D안 — 어두운 무대(.root 배경 var(--ink))와 큰 타이포 하나로 대담하게, 오렌지는 한 곳.",
)
Image3 = tuple[str, bytes, str]


def _images(x: Any) -> Optional[list[tuple[str, bytes, str]]]:
    """그림 하나(라벨, 바이트, 형식) 또는 그 목록 → 목록(빈 것은 None)."""
    if not x:
        return None
    items = [x] if isinstance(x, tuple) else list(x)
    items = [i for i in items if i]
    return items or None


def agent_skill_block(key: str) -> str:
    """그 에이전트의 스킬 노트(있는 것만). 출처 목록은 지시에 넣지 않는다(토큰만 든다)."""
    from ..paths import PROMPTS_DIR
    parts = []
    for name in AGENT_SKILLS.get(key, ()):
        f = PROMPTS_DIR / "skills" / "agents" / f"{name}.md"
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8").strip()
        text = text.split("\n## 출처", 1)[0].strip()
        if text:
            parts.append(text)
    return ("\n\n---\n# 이 역할의 스킬 노트(전문가·제작자에게서 배운 것 — 지시와 부딪히면 지시가 이긴다)\n\n"
            + "\n\n".join(parts) + "\n") if parts else ""


def skills_block() -> str:
    """prompts/skills/*.md 전부(이름순) — 새 스킬 노트는 파일을 넣기만 하면 모든 에이전트가 읽는다."""
    from ..paths import PROMPTS_DIR
    files = sorted((PROMPTS_DIR / "skills").glob("*.md"))
    return "\n\n".join(f.read_text(encoding="utf-8").strip() for f in files)


def playbook_block() -> str:
    """🎓 편집 플레이북 — 잘 만든 채널들을 연구해 정리한 편집 문법(prompts/playbook/*.md)."""
    from ..paths import PROMPTS_DIR
    files = sorted((PROMPTS_DIR / "playbook").glob("*.md"))
    parts = [f.read_text(encoding="utf-8").strip() for f in files]
    parts = [p for p in parts if p]
    return ("# 편집 플레이북(레퍼런스 연구)\n\n" + "\n\n".join(parts)) if parts else ""


def motion_examples_block() -> str:
    """렌더로 검증된 모션 장면 예제(prompts/examples/motion_examples.json)."""
    from ..paths import PROMPTS_DIR
    path = PROMPTS_DIR / "examples" / "motion_examples.json"
    try:
        examples = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    parts = [f"\n{name}:\n```json\n{json.dumps(spec, ensure_ascii=False)}\n```" for name, spec in examples.items()]
    return "\n" + "\n".join(parts) + "\n"


def card_examples_block() -> str:
    """렌더로 검증된 자유 HTML 카드 예제(prompts/examples/card_examples.json) — cards[].html 에 그대로 쓸 수 있는 조각."""
    from ..paths import PROMPTS_DIR
    path = PROMPTS_DIR / "examples" / "card_examples.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    parts = ["\n\n## 카드 예시 — 구도 원형 12(prompts/layouts.md)를 실제로 렌더해 확인한 것\n"
             "구도·글자 크기 단계·안무(timeline)·재질을 이 수준으로 맞춘다. **내용과 배치는 장면마다 새로** — 같은 영상에서 예시의 "
             "좌표를 그대로 베끼지 않는다(같은 원형도 방향·비율·주인공을 바꾼다).\n"]
    for name, ex in data.items():
        parts.append(f"\n### {name} — 원형 `{ex.get('archetype', name)}` · {ex.get('title', '')} "
                     f"({ex.get('style', '')}, {ex.get('layout', 'fullscreen')}, {ex.get('duration', 6)}초)\n"
                     f"```html\n{ex.get('html', '').strip()}\n```\n"
                     + (f"timeline:\n```js\n{ex['timeline'].strip()}\n```\n" if (ex.get("timeline") or "").strip() else ""))
    return "".join(parts)


CRITIC_MIN_SCORE = 6
CRITIC_MIN_AVG = 7.0


def critic_verdict(res: dict[str, Any], *, min_score: int = CRITIC_MIN_SCORE, min_avg: float = CRITIC_MIN_AVG) -> tuple[bool, list[str]]:
    """🧑‍⚖️ 심사 결과 → (통과?, 이유들). fail-closed: 하드 실패 하나, 점수 하나라도 min_score 미만, 평균 min_avg 미만, 심사가 reject 라
    했으면 탈락. 점수 칸이 비었으면(응답 모양이 틀림) 통과로 보지 않는다."""
    why: list[str] = []
    hard = [str(x).strip() for x in (res.get("hard_failures") or []) if str(x).strip()]
    why += [f"하드 실패: {h}" for h in hard]
    scores = res.get("scores") if isinstance(res.get("scores"), dict) else {}
    vals: list[int] = []
    for k in S.CRITIC_SCORES:
        try:
            v = int(scores.get(k))
        except (TypeError, ValueError):
            why.append(f"점수 없음: {k}")
            continue
        vals.append(v)
        if v < min_score:
            why.append(f"{k} {v} < {min_score}")
    if vals and len(vals) == len(S.CRITIC_SCORES):
        avg = sum(vals) / len(vals)
        if avg < min_avg:
            why.append(f"평균 {avg:.1f} < {min_avg}")
    if str(res.get("verdict") or "") != "pass" and not why:
        why.append("심사 reject")
    return (not why), why


def direction_block(text: str) -> str:
    text = (text or "").strip()
    return f"\n## 사용자 편집 지시(최우선)\n{text}\n" if text else ""


def compact_brief(brief: dict[str, Any]) -> str:
    """전문 에이전트에게 넘길 브리프(JSON 그대로 — 요약하면 감독 의도가 새어 나간다)."""
    return json.dumps(brief, ensure_ascii=False, indent=1)


def parse_spec(text: str) -> Optional[dict[str, Any]]:
    if not text or not text.strip():
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        try:
            obj = extract_json(text)
        except (DirectorError, json.JSONDecodeError):
            return None
    return obj if isinstance(obj, dict) else None


# ---------------------------------------------------------------------------
# 트리트먼트(총괄 감독의 시각·소리 설계) — 시그니처 장면 고르기 · 전문가에게 주는 블록
# ---------------------------------------------------------------------------
BUILDABLE = ("ui_recreation", "object_recreation", "data_story", "diagram", "timeline")


def signature_scenes(director: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    """트리트먼트의 시그니처 장면 중 🛠 빌더가 HTML 로 지을 것(실물 사진이 필요한 document·collage 는 자료 리서처 몫)."""
    tr = director.get("treatment") if isinstance(director.get("treatment"), dict) else {}
    out: list[dict[str, Any]] = []
    for n, sc in enumerate(tr.get("signature_scenes") or []):
        if not isinstance(sc, dict) or sc.get("kind") not in BUILDABLE or not str(sc.get("brief") or "").strip():
            continue
        try:
            a, b = int(sc.get("start_seg", -1)), int(sc.get("end_seg", sc.get("start_seg", -1)))
        except (TypeError, ValueError):
            continue
        if a < 0:
            continue
        out.append({"id": str(sc.get("id") or f"sig{n + 1}")[:16], "start_seg": a, "end_seg": max(a, b),
                    "start_word": str(sc.get("start_word") or ""), "kind": sc["kind"],
                    "title": str(sc.get("title") or sc["kind"])[:40], "brief": str(sc["brief"])[:3000],
                    "research_ref": str(sc.get("research_ref") or "")[:300], "sfx": str(sc.get("sfx") or "none"),
                    "motion_ref": str(sc.get("motion_ref") or "").strip()[:80]})
    return out[:limit]


WORLD_ROWS = (("who", "누구"), ("where", "어디"), ("era", "언제"), ("props", "사물·도구"), ("look", "화면 결"),
              ("never", "이 세계가 아닌 것(나오면 0점)"))


def world_block(treatment: Optional[dict[str, Any]], topic: str = "") -> str:
    """🌍 이 영상의 세계(총괄 감독 treatment.world) — 자료 리서처의 검색어·후보 고르기·모션 그림 부품·검수가 모두 받는다.
    2026-10-04 채널 주인: '학교'라는 말에 아이들 연필 스톡 — 맥락은 미술대학 디자인과다. 세계가 없으면 주제 설명으로."""
    w = (treatment or {}).get("world") if isinstance((treatment or {}).get("world"), dict) else {}
    rows = [(label, str(w.get(k) or "").strip()) for k, label in WORLD_ROWS]
    rows = [(label, v) for label, v in rows if v]
    if not rows and not topic.strip():
        return ""
    lines = ["## 🌍 이 영상의 세계 — 모든 자료·스톡·그림이 이 안에 있어야 한다"]
    lines += [f"- {label}: {v}" for label, v in rows] or [f"- 주제 설명: {topic.strip()[:400]}"]
    lines.append("- 낱말이 아니라 이 세계로 판단한다: 대본의 '학교'·'작업'·'책상'은 이 사람의 학교·작업·책상이다. 나이·장소·시대·"
                 "직업 도구가 이 세계와 다르면(어른 디자인 전공생의 이야기에 아이 공책·색연필, 실기실 이야기에 사무실 회의) "
                 "낱말이 맞아도 쓰지 않는다.")
    return "\n".join(lines) + "\n\n"


def treatment_block(director: dict[str, Any], key: str) -> str:
    """전문가 지시 끝에 붙는 트리트먼트 요약 — 콘셉트·모티프와, 시그니처 장면 구간(겹쳐 내지 않는다)."""
    tr = director.get("treatment") if isinstance(director.get("treatment"), dict) else {}
    if not tr:
        return ""
    lines = ["", "", "## 🎨 총괄 감독의 트리트먼트(이 영상만의 설계 — 따른다)"]
    if tr.get("concept"):
        lines.append(f"- 콘셉트: {tr['concept']}")
    if tr.get("motifs"):
        lines.append("- 모티프: " + " · ".join(str(m) for m in tr["motifs"][:6]))
    wb = world_block(tr) if key in ("motion", "stock", "captions") else ""
    if wb:
        lines += ["", wb.strip()]
    sigs = [sc for sc in tr.get("signature_scenes") or [] if isinstance(sc, dict)]
    if sigs and key in ("motion", "stock"):
        lines.append("- 시그니처 장면 구간(🛠 빌더가 짓는다 — 이 구간에는 다른 화면을 내지 않는다): "
                     + " · ".join(f"S{sc.get('start_seg')}–S{sc.get('end_seg')} 「{sc.get('title', '')}」" for sc in sigs))
    segs = [s for s in tr.get("segments") or [] if isinstance(s, dict)]
    if segs and key in ("motion", "stock"):
        want = {"motion": ("motion", "board", "timeline", "compare", "face_callout"),
                "stock": ("collage", "photo_full", "stock_video", "quote_over_footage", "document", "face_photo")}[key]
        mine = [s for s in segs if s.get("layout") in want]
        if mine:
            lines.append("- 화면 구성표 중 네 몫(이 구간을 이 구성으로 채운다):")
            lines += [f"  - S{s.get('start_seg')}–S{s.get('end_seg')} [{s.get('layout')}] {s.get('show', '')}"
                      + (f" — 자료: {s['asset']}" if s.get("asset") else "") + (f" — 움직임: {s['motion']}" if s.get("motion") else "")
                      for s in mine[:40]]
    if key == "editor" and tr.get("sound_concept"):
        lines.append(f"- 소리 콘셉트: {tr['sound_concept']}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 합치기(순수 함수 — 테스트 가능)
# ---------------------------------------------------------------------------

def _g(template: str, layout: str, start: int, end: int, word: str = "", **kw: Any) -> dict[str, Any]:
    g = {"template": template, "layout": layout, "start_seg": start, "end_seg": end, "start_word": word,
         "title": "", "subtitle": "", "body": "", "items": [], "title_b": "", "items_b": [], "highlight": -1,
         "author": "", "source": "", "image": "", "reason": ""}
    g.update(kw)
    return g


def legacy_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """조달 결과가 없을 때 증거 항목 → 예전 그래픽: 고유명사 → photo(wiki), 화자 자료 → photo(자료 폴더 이름으로 찾음),
    스톡 → broll. 1차 자료·화면·재현은 조달 없이는 만들 수 없어 뺀다(로그는 사다리 쪽)."""
    out = []
    for it in items:
        s = it.get("subject") if isinstance(it.get("subject"), dict) else {}
        name = str(s.get("name_ko") or s.get("name_en") or "").strip()
        need, tr = it.get("need"), it.get("treatment") or "hero"
        layout = "pip" if tr == "pip" else "fullscreen"
        seg, end, word = it.get("start_seg", -1), it.get("end_seg", it.get("start_seg", -1)), it.get("start_word", "")
        if need == "entity" and name:
            kind = {"site_app": "brand", "brand": "brand", "person": "person"}.get(str(s.get("kind") or ""), "")
            out.append(_g("photo", layout, seg, seg, word, title=it.get("label") or name, image=name, subtitle="",
                          body="", reason="자료 리서처: " + str(it.get("claim", ""))[:60], wiki=True, entity=kind,
                          name_en=str(s.get("name_en") or "")))
        elif need == "own_material" and (it.get("local_file") or name):
            out.append(_g("photo", layout, seg, seg, word, title=it.get("label") or "", image=it.get("local_file") or name,
                          reason="자료 리서처(화자 자료): " + str(it.get("claim", ""))[:60], wiki=True))
        elif need == "stock":
            st = it.get("stock") if isinstance(it.get("stock"), dict) else {}
            if st.get("query_en") or st.get("query_ko"):
                out.append(_g("broll", layout, seg, end, word, title=str(it.get("label") or "")[:14],
                              image=st.get("query_en", ""), reason="자료 리서처: " + str(it.get("claim", ""))[:60],
                              stock={"kind": st.get("kind") or "photo", "query_en": st.get("query_en", ""),
                                     "query_ko": st.get("query_ko", ""), "purpose": str(it.get("claim", ""))[:60],
                                     "must_show": it.get("must_show", "")}))
    return out


def merge_plan(results: dict[str, Any], *, log: LogFn = noop_log) -> tuple[dict[str, Any], dict[str, Any]]:
    """에이전트 결과 → (raw_long, raw_shorts). 없는 결과는 빈 값으로."""
    brief = results.get("director") or {}
    editor = results.get("editor") or {}
    motion = results.get("motion") or {}
    stock = results.get("stock") or {}
    caps = results.get("captions") or {}
    copy = results.get("copy") or {}
    shorts = results.get("shorts") or {"shorts": []}

    graphics: list[dict[str, Any]] = [dict(g) for g in motion.get("graphics", []) or [] if isinstance(g, dict)]
    n_scene = 0
    for sc in motion.get("scenes", []) or []:
        spec = parse_spec(sc.get("spec_json", ""))
        if not spec or not clean_spec(spec, 12.0):
            log(f"🎨 모션 장면 '{sc.get('title', '')}' 의 spec 이 올바르지 않아 제외")
            continue
        try:
            hero = int(sc.get("hero", -1))
        except (TypeError, ValueError):
            hero = -1
        if 0 <= hero < len(spec.get("elements") or []) and "hero" not in spec:
            spec["hero"] = hero
        why = str(sc.get("reason", "")) + (f" · 움직임: {sc['motion_reason']}" if sc.get("motion_reason") else "")
        graphics.append(_g("motion", sc.get("layout") or "fullscreen", sc.get("start_seg", -1),
                           sc.get("end_seg", sc.get("start_seg", -1)), sc.get("start_word", ""),
                           title=sc.get("title", ""), reason="모션 디자이너: " + why, spec=spec,
                           sequence_id=str(sc.get("sequence_id") or ""), motif=str(sc.get("motif") or "")[:24]))
        n_scene += 1
    n_card = 0
    for cd in motion.get("cards", []) or []:
        if not isinstance(cd, dict):
            continue
        layout = cd.get("layout") if cd.get("layout") in ("fullscreen", "split", "overlay") else "fullscreen"
        # html 만 넘기면 직접 쓴 GSAP timeline 이 버려진다(2026-10-04 발견: 실제 10/04 계획의 카드 6개 모두 timeline 없이 렌더 —
        # 디자이너가 쓴 안무가 하나도 화면에 나오지 않았다)
        card = clean_card({"html": cd.get("html", ""), "timeline": cd.get("timeline", "")}, layout=layout,
                          card_id=f"card{n_card + 1}")
        if not card:
            log(f"🃏 카드 '{cd.get('title', '')}' 의 HTML 이 올바르지 않아 제외")
            continue
        if not card.get("style") and cd.get("style") in STYLES:
            card["style"] = cd["style"]
        if cd.get("archetype") in S.ARCHETYPES:
            card["archetype"] = cd["archetype"]
        if card.get("problems"):
            log(f"🃏 카드 '{cd.get('title', '')}' 정리: {', '.join(card['problems'][:4])}")
        graphics.append(_g("card", layout, cd.get("start_seg", -1), cd.get("end_seg", cd.get("start_seg", -1)),
                           cd.get("start_word", ""), title=cd.get("title", ""),
                           reason="모션 디자이너(카드): " + str(cd.get("reason", "")), card=card,
                           sequence_id=str(cd.get("sequence_id") or ""), motif=str(cd.get("motif") or "")[:24]))
        n_card += 1
    # 🛠 시그니처 장면(트리트먼트) — 자유 HTML 카드로 정밀 재현. 겹치면 이긴다(signature → 우선순위 +3)
    n_sig = 0
    for sp in results.get("setpieces") or []:
        sc = sp.get("scene") or {}
        layout = sp.get("layout") if sp.get("layout") in ("fullscreen", "split", "overlay") else "fullscreen"
        card = clean_card({"html": sp.get("html", ""), "timeline": sp.get("timeline", "")}, layout=layout,
                          card_id=f"card{n_card + 1}")
        if not card:
            log(f"🛠 시그니처 장면 「{sc.get('title', '')}」 의 HTML 이 올바르지 않아 제외")
            continue
        if sp.get("style") in STYLES:
            card["style"] = sp["style"]
        if sp.get("archetype") in S.ARCHETYPES:
            card["archetype"] = sp["archetype"]
        graphics.append(_g("card", layout, sc.get("start_seg", -1), sc.get("end_seg", sc.get("start_seg", -1)),
                           str(sp.get("start_word") or sc.get("start_word") or ""), title=str(sc.get("title", "")),
                           reason=f"🛠 시그니처 장면({sc.get('kind', '')}): {str(sp.get('notes', ''))[:80]}", card=card,
                           signature=True, sfx=str(sc.get("sfx") or "")))
        n_card += 1
        n_sig += 1
    # 🎞 자료 리서처 v2 — 증거 항목(need·트리트먼트) + 조달 결과(사다리) → 그래픽(studio/assets/graphics.py)
    ev_items = [it for it in stock.get("items", []) or [] if isinstance(it, dict)]
    if ev_items:
        outcomes = results.get("evidence_outcomes")
        if isinstance(outcomes, list) and len(outcomes) == len(ev_items):
            from ..assets.graphics import to_graphics
            g_ev, _drawn = to_graphics(ev_items, outcomes, log=log)
            graphics += g_ev
        else:
            graphics += legacy_evidence(ev_items)      # 조달 전(콜백 없음·실패): 예전 경로(자료 사진·스톡 단계)가 찾는다
    # 📷 고유명사 자료 사진(v1 스키마 — 저장된 계획 재실행용) — 위키백과 문서의 대표 이미지. 없으면 스톡으로 넘기지 않는다
    for ph in stock.get("photos", []) or []:
        if not isinstance(ph, dict):
            continue
        name_ko = str(ph.get("name_ko") or "").strip()
        name_en = str(ph.get("name_en") or "").strip()
        if not (name_ko or name_en):
            continue
        layout = ph.get("layout") if ph.get("layout") in ("pip", "split", "fullscreen") else "pip"
        kind = str(ph.get("kind") or "")
        # 화면 글자는 이름뿐 — 종류(kind)는 내부 분류라 화면에 내지 않는다(10/1: 핀터레스트 사진 위 검은 라벨 'brand').
        # 인물은 자료 사진 단계가 위키백과 짧은 설명을 body 에 넣는다
        graphics.append(_g("photo", layout, ph.get("start_seg", -1), ph.get("start_seg", -1), ph.get("start_word", ""),
                           title=name_ko or name_en, image=name_ko or name_en, subtitle=name_en,
                           body="", reason="자료 리서처(위키백과): " + str(ph.get("reason", "")),
                           wiki=True, entity=kind, name_en=name_en))
    for r in stock.get("requests", []) or []:
        if not (r.get("query_en") or r.get("query_ko")):
            continue
        # 검색어·연출 메모(purpose)는 화면에 내지 않는다(10/1: 스톡 위 큰 글씨 '스케치북 넘기기', 검은 라벨 '…전환점') —
        # 화면 라벨은 자료 리서처가 따로 준 caption(그 문장의 주장)이 있을 때만
        graphics.append(_g("broll", r.get("layout") or "fullscreen", r.get("start_seg", -1),
                           r.get("end_seg", r.get("start_seg", -1)), r.get("start_word", ""),
                           title=str(r.get("caption") or "").strip()[:14], image=r.get("query_en", ""), subtitle="",
                           body="", reason="자료 리서처: " + str(r.get("purpose", "")),
                           stock={k: r.get(k, "") for k in ("kind", "query_en", "query_ko", "purpose", "must_show")}))

    moments = [m for m in editor.get("moments", []) or [] if isinstance(m, dict)]
    # 예전 스키마(punch) 호환
    moments += [{"seg": p.get("seg"), "word": p.get("word", ""), "kind": "punchline", "intensity": 2}
                for p in editor.get("punch", []) or [] if isinstance(p, dict)]
    emphasis = [{"seg": m.get("seg"), "word": m.get("word", ""), "kind": "punch"} for m in moments
                if int(m.get("intensity", 2) or 2) >= 2]
    emphasis += [{"seg": e.get("seg"), "word": e.get("word", ""), "kind": "highlight", "type": e.get("type", "keyword")}
                 for e in caps.get("emphasis", []) or [] if e.get("word")]

    chapters = [{"seg": c.get("start_seg"), "title": c.get("title", ""), "claim": str(c.get("claim", "") or "")}
                for c in brief.get("structure", []) or []]
    raw_long = {
        "title": brief.get("title", ""),
        "moments": moments,
        "energy_spans": [e for e in editor.get("energy_spans", []) or [] if isinstance(e, dict)],
        "holds": [h for h in editor.get("holds", []) or [] if isinstance(h, dict)],
        "pauses": [p for p in editor.get("pauses", []) or [] if isinstance(p, dict)],
        "rhythm": [r for r in editor.get("rhythm", []) or [] if isinstance(r, dict)],
        "peak_seg": editor.get("peak_seg", -1),
        "sequences": [q for q in brief.get("sequences", []) or [] if isinstance(q, dict)],
        "central_question": brief.get("central_question", ""),
        "payoff_seg": brief.get("payoff_seg", -1),
        "highlights": [h for h in editor.get("highlights", []) or [] if isinstance(h, dict)],
        "bgm_mood": brief.get("bgm_mood", ""),
        "shorts_bgm_mood": brief.get("shorts_bgm_mood", ""),
        "summary": brief.get("thesis") or brief.get("logline", ""),
        "hook_segs": brief.get("hook_segs", []) or [],
        "title_card_seg": brief.get("title_card_seg", -1),
        "chapters": chapters,
        "graphics": graphics,
        "emphasis": emphasis,
        "drop": editor.get("drop", []) or [],
        "youtube": {k: ([strip_label(str(x)) for x in (copy.get(k) or []) if str(x).strip()] if k in ("titles", "thumbnail_texts")
                        else copy.get(k, [] if k not in ("description", "pinned_comment") else ""))
                    for k in ("titles", "description", "hashtags", "tags", "thumbnail_texts", "pinned_comment")},
        "music": brief.get("music") or {},
        "captions": {},   # 자막 모양은 채널 템플릿(흰 종이 상자 + 두 층 강조)로 고정 — 디자이너는 강조어만 정한다
        "studio": {
            "logline": brief.get("logline", ""), "thesis": brief.get("thesis", ""), "audience": brief.get("audience", ""),
            "tone": brief.get("tone", ""),
            "beats": brief.get("beats", []), "notes_for_team": brief.get("notes_for_team", ""),
            "pacing_notes": editor.get("pacing_notes", ""), "caption_notes": caps.get("notes", ""),
            "motion_scenes": n_scene, "cards": n_card, "signature_scenes": n_sig,
            "stock_requests": len(stock.get("requests", []) or []),
            "wiki_photos": len(stock.get("photos", []) or []),
            "evidence_items": len(ev_items), "evidence_notes": str(stock.get("notes", "") or "")[:400],
            "integrity": brief.get("integrity") or {},
            "treatment": brief.get("treatment") or {},
            **({"style_frame": results["style_frame"]} if results.get("style_frame") else {}),
        },
    }
    return raw_long, shorts


# ---------------------------------------------------------------------------
# 스튜디오
# ---------------------------------------------------------------------------

class Studio:
    def __init__(self, claude: ClaudeClient, *, log: LogFn = noop_log, cancel: Optional[CancelToken] = None,
                 workers: int = 4, effort: Optional[dict[str, str]] = None, models: Optional[dict[str, str]] = None,
                 user_direction: str = "", use_stock: bool = True, use_motion: bool = True):
        self.claude = claude
        self.log = log
        self.cancel = cancel
        self.workers = max(1, int(workers or 1))
        self.effort = effort or {}
        self.models = models or {}
        self.direction = user_direction
        self.use_stock = use_stock
        self.use_motion = use_motion
        self.system = studio_system_prompt()
        self._plain_system: Optional[str] = None      # 디자인 역할이 아닌 역할의 시스템(예시 없이) — 처음 쓸 때 만든다
        self._lean: dict[str, str] = {}
        self._prime_lock = threading.Lock()
        self._prime: dict[str, float] = {}      # 역할마다 이번 묶음의 첫 호출 시각
        self._running: dict[str, int] = {}
        self.results: dict[str, Any] = {}
        self.errors: dict[str, str] = {}
        self.web = True                                                   # 🔎·🛠 에이전트에 웹 도구를 준다
        self.materials: tuple[str, Optional[bytes]] = ("", None)        # ④ 자료 폴더 목록 + 썸네일 시트(자료 리서처에게)
        self.evidence: tuple[str, Optional[bytes]] = ("", None)         # 확보 목록 + 컨택트 시트(모션 디자이너에게)
        # 🌍 세계 블록 — 저장된 기획을 다시 쓸 때는 파이프라인이 계획의 treatment·주제 설명으로 준다(호출 때 읽는다)
        self.world_fn: Optional[Callable[[], str]] = None
        # 🖼 카드 미리보기(파이프라인이 준다: check.mjs 를 렌더와 같은 Chrome 으로 — 정착 화면 + 움직임 칸)
        #   items [{id, card(clean_card), layout, dur, label}] → {id: {ok, problems[str], images[(label, bytes, mime)]}}
        self.preview: Optional[Callable[[list[dict[str, Any]]], dict[str, dict[str, Any]]]] = None
        self.style_on = True                  # 🎨 스타일 프레임(설정 style_frame)
        self.variants = 1                     # 🧑‍⚖️ 시그니처 장면 시안 수(설정 design_variants, 1 = 경쟁 없음)
        self.style: dict[str, Any] = {}       # {rules, archetype, notes, card, images}
        self.house_board: Optional[Callable[[], Optional[bytes]]] = None   # 운영자 보드가 없을 때 하우스 예시 카드 보드
        self._board: Optional[list[Image3]] = None

    def world_text(self) -> str:
        """지금 쓸 🌍 세계 블록 — 이번 기획의 총괄 감독 treatment 가 있으면 그것, 없으면 파이프라인이 준 것."""
        tr = (self.results.get("director") or {}).get("treatment")
        out = world_block(tr if isinstance(tr, dict) else None)
        if not out and self.world_fn is not None:
            try:
                out = self.world_fn() or ""
            except Exception:  # noqa: BLE001 - 세계 블록 없이도 고른다
                out = ""
        return out

    # ------------------------------------------------------------------
    def call(self, key: str, ctx: str, instruction: str, *, images=None, system: Optional[str] = None,
             label: str = "", web: Optional[bool] = None) -> dict[str, Any]:
        a = AGENTS[key]
        # 사고 강도: 파일의 에이전트별 덮어쓰기 → 설정의 전역 값(모든 에이전트 같은 강도) → 에이전트 기본
        eff = self.effort.get(key) or getattr(self.claude, "effort", "") or a.effort
        model = self.models.get(key) or None
        kw: dict[str, Any] = {}
        if a.tools and (self.web if web is None else (web and self.web)):
            kw = {"tools": a.tools, "max_turns": a.max_turns}
            if a.timeout:
                kw["timeout"] = a.timeout
        instruction = instruction + agent_skill_block(key)
        if key in DESIGN_AGENTS:
            # 🎨 스타일 프레임 규칙 + 🎯 운영자 취향 메모 — 그림(스타일 프레임·보드)은 앞에(같은 역할의 호출마다 같은 앞부분)
            if key != "style_frame":
                instruction += self.style_block()
                refs = self.design_refs(key)
                if refs:
                    images = refs + (_images(images) or [])
            instruction += self.taste_notes()
        if system is None and key in LEAN_AGENTS:
            system = self._lean.get(key) or self._lean.setdefault(key, lean_system_prompt(LEAN_AGENTS[key]))
        elif system is None and key not in DESIGN_AGENTS:
            if self._plain_system is None:
                self._plain_system = studio_system_prompt(design=False)
            system = self._plain_system
        if key in REPEATED_AGENTS:
            kw["ctx_in_system"] = True
        try:
            self._stagger(key)
            return self.claude.structured(system=system or self.system, shared_context=ctx, instruction=instruction,
                                          schema=a.schema, max_tokens=a.max_tokens, cancel=self.cancel,
                                          label=label or a.label, images=images, effort=eff, model=model, **kw)
        finally:
            with self._prime_lock:
                self._running[key] = max(0, self._running.get(key, 1) - 1)

    def _stagger(self, key: str) -> None:
        """같은 역할의 호출이 동시에 여러 개 뜰 때 — 첫 호출이 공통 앞부분(시스템·자료)을 캐시에 쓸 시간(PRIME_S)을 준 뒤 나머지를
        보낸다. 동시에 보내면 모두 새로 읽고(캐시 쓰기 1.25배) 아무도 캐시를 읽지 못한다. 첫 호출이 이미 끝났거나
        PRIME_S 가 지났으면 기다리지 않는다."""
        with self._prime_lock:
            now = time.time()
            busy = self._running.get(key, 0)
            first = self._prime.get(key)
            if first is None or busy == 0:
                self._prime[key] = now
                wait = 0.0
            else:
                wait = max(0.0, first + PRIME_S - now)
            self._running[key] = busy + 1
        end = time.time() + wait
        while time.time() < end:
            if self.cancel:
                self.cancel.check()
            time.sleep(min(0.5, max(0.0, end - time.time())))

    # ------------------------------------------------------------------
    # 🎨 스타일 프레임 · 🎯 취향 보드 · 🧑‍⚖️ 시안 심사
    # ------------------------------------------------------------------
    def board(self) -> list[Image3]:
        """🎯 레퍼런스 보드(운영자 그림 · 좋아한/싫어한 장면). 하나도 없으면 하우스 예시 카드 보드. 작업마다 한 번 만든다."""
        if self._board is None:
            from . import taste
            try:
                b = taste.board_images()
            except Exception as e:  # noqa: BLE001 - 보드 없이도 짓는다
                self.log(f"🎯 레퍼런스 보드를 읽지 못했습니다: {e}")
                b = []
            if not b and self.house_board is not None:
                try:
                    hb = self.house_board()
                except Exception:  # noqa: BLE001
                    hb = None
                if hb:
                    b = [("하우스 예시 보드(렌더로 확인한 카드 예시 — 이 수준이 바닥)", hb, "image/jpeg")]
            self._board = b
        return self._board

    def taste_notes(self) -> str:
        from . import taste
        try:
            text = taste.notes_block()
        except Exception:  # noqa: BLE001
            return ""
        return ("\n\n" + text) if text else ""

    def design_refs(self, key: str) -> list[Image3]:
        """디자인 역할에게 앞에 붙일 기준 그림 — 스타일 프레임(정지 화면 · 움직임 칸)과 레퍼런스 보드."""
        out: list[Image3] = []
        imgs = list(self.style.get("images") or [])
        if key in REF_STILL:
            out += imgs[:1]
        elif key in REF_FULL:
            out += imgs[:2] + self.board()
        return out

    def style_block(self) -> str:
        """🎨 스타일 프레임 규칙 → 디자인 역할의 지시 끝(그림은 design_refs 가 따로 붙인다)."""
        r = self.style.get("rules") or {}
        if not any(r.get(k) for k in ("grid", "type", "color", "shape", "motif", "motion", "do", "dont")):
            return ""
        lines = ["", "", "## 🎨 이 영상의 스타일 프레임(먼저 확정한 룩 — 모든 장면이 같은 결로; 첨부 그림 '스타일 프레임')"]
        for k, lab in (("grid", "그리드"), ("type", "글자"), ("color", "색"), ("shape", "도형·재질"), ("motif", "모티프"),
                       ("motion", "움직임 서명")):
            if str(r.get(k) or "").strip():
                lines.append(f"- {lab}: {str(r[k]).strip()[:400]}")
        if r.get("do"):
            lines.append("- 한다: " + " · ".join(str(x)[:120] for x in r["do"][:6]))
        if r.get("dont"):
            lines.append("- 하지 않는다: " + " · ".join(str(x)[:120] for x in r["dont"][:6]))
        lines.append("- 스타일 프레임의 좌표·문장을 베끼지 않는다 — 결(재질·도형·모티프·움직임 서명)을 맞추고, 구도 원형은 장면마다 바꾼다.")
        return "\n".join(lines) + "\n"

    def load_style(self, saved: dict[str, Any], images: list[Image3]) -> None:
        """저장된 계획의 스타일 프레임(규칙)과 그 그림을 다시 쓴다 — 기획을 다시 쓰는 작업의 자기 검토·검수도 같은 기준으로."""
        if isinstance(saved, dict) and saved.get("rules"):
            self.style = {"rules": saved.get("rules") or {}, "archetype": saved.get("archetype", ""),
                          "notes": saved.get("notes", ""), "card": None, "images": list(images or [])}

    def _preview(self, items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if self.preview is None or not items:
            return {}
        try:
            return self.preview(items) or {}
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001 - 미리보기 없이도 진행(그림 없이 규칙만)
            self.log(f"🖼 카드 미리보기 실패 → 그림 없이: {str(e)[:160]}")
            return {}

    def make_style_frame(self, ctx: str, director: dict[str, Any]) -> dict[str, Any]:
        """🎨 장면을 짓기 전에 이 영상의 룩(스타일 프레임 한 장 + 규칙)을 확정한다 — 실패하면 {}(스타일 프레임 없이)."""
        tr = {k: v for k, v in (director.get("treatment") or {}).items() if k not in ("segments", "signature_scenes")}
        text = (load_prompt("agents/style_frame.md")
                .replace("{{treatment}}", json.dumps(tr, ensure_ascii=False, indent=1))
                .replace("{{thesis}}", str(director.get("thesis") or director.get("logline") or ""))
                .replace("{{user_direction}}", direction_block(self.direction)))
        board = self.board()
        self.log("🎨 스타일 프레임: 이 영상의 룩을 한 장으로 먼저 정합니다" + (f"(레퍼런스 그림 {len(board)}장)" if board else ""))
        try:
            res = self.call("style_frame", ctx, text, images=board or None)
        except DirectorError as e:
            self.errors["style_frame"] = str(e)
            self.log(f"🎨 스타일 프레임 실패({e}) → 스타일 프레임 없이 진행")
            return {}
        rules = res.get("rules") if isinstance(res.get("rules"), dict) else {}
        card = clean_card({"html": res.get("html", ""), "timeline": res.get("timeline", "")}, layout="fullscreen",
                          card_id="styleframe")
        style: dict[str, Any] = {"rules": rules, "archetype": str(res.get("archetype") or ""),
                                 "notes": str(res.get("notes") or "")[:300], "card": card, "images": []}
        if card:
            pv = self._preview([{"id": "styleframe", "card": card, "layout": "fullscreen", "dur": 7.0,
                                 "label": "스타일 프레임"}]).get("styleframe") or {}
            style["images"] = list(pv.get("images") or [])
            if pv and not pv.get("ok", True):
                self.log("🎨 스타일 프레임 검사: " + " · ".join(str(x) for x in (pv.get("problems") or [])[:3])
                         + " (기준 그림으로는 그대로 쓴다)")
        self.style = style
        self.results["style_frame"] = {"rules": rules, "archetype": style["archetype"], "notes": style["notes"],
                                       "html": fragment(card) if card else "", "timeline": (card or {}).get("timeline", "")}
        self.log(f"🎨 스타일 프레임: 원형 {style['archetype'] or '-'} · 모티프 {str(rules.get('motif') or '-')[:60]}"
                 + (" · 그림 확인" if style["images"] else ""))
        return style

    def judge_variants(self, ctx: str, sc: dict[str, Any], variants: list[tuple[int, dict[str, Any]]],
                       layout_of: Callable[[dict[str, Any]], str]) -> tuple[int, str, list[Image3]]:
        """🧑‍⚖️ 시안 여럿 → 렌더 → 심사 → (이긴 시안의 목록 위치, 고칠 것, 이긴 시안 그림). 렌더·심사를 못 하면 첫 시안."""
        items, meta = [], []
        for pos, (k, v) in enumerate(variants):
            card = clean_card({"html": v.get("html", ""), "timeline": v.get("timeline", "")}, layout=layout_of(v),
                              card_id=f"{sc['id'][:10]}v{k + 1}")
            if card:
                items.append({"id": card["id"], "card": card, "layout": layout_of(v), "dur": 8.0,
                              "label": f"V{k + 1}"})
                meta.append((pos, k, v, card["id"]))
        if len(meta) < 2:
            return (meta[0][0] if meta else 0), "", []
        pv = self._preview(items)
        if not pv:
            return meta[0][0], "", []
        imgs: list[Image3] = []
        lines = []
        for pos, k, v, cid in meta:
            r = pv.get(cid) or {}
            imgs += list(r.get("images") or [])
            probs = [str(x) for x in r.get("problems") or []]
            lines.append(f"- V{k + 1}: {VARIANT_HINTS[k % len(VARIANT_HINTS)]} · 원형 {v.get('archetype') or '-'} · "
                         + ("검사 통과" if r.get("ok", True) else "검사 실패: " + " · ".join(probs[:3])))
        if not imgs:
            return meta[0][0], "", []
        instr = (load_prompt("agents/design_judge.md").replace("{{n}}", str(len(meta)))
                 .replace("{{scene}}", json.dumps({x: sc.get(x) for x in ("title", "kind", "brief")}, ensure_ascii=False))
                 .replace("{{speech}}", f"공유 컨텍스트 전사본의 S{sc['start_seg']}–S{sc['end_seg']}")
                 + "\n\n## 시안\n" + "\n".join(lines)
                 + "\n\n검사 실패(넘침·작은 글자·대비·잘림)는 고치기 어려우면 지게 한다. `winner` 는 V 뒤의 번호.\n")
        try:
            res = self.call("design_judge", ctx, instr, images=imgs, label=f"🧑‍⚖️ 시안 심사 「{sc['title'][:16]}」")
        except DirectorError as e:
            self.log(f"🧑‍⚖️ 시안 심사 실패({e}) → A안")
            return meta[0][0], "", []
        try:
            w = int(res.get("winner", 1))
        except (TypeError, ValueError):
            w = 1
        pick = next((m for m in meta if m[1] + 1 == w), meta[0])
        scores = {int(x.get("variant", 0) or 0): x.get("score") for x in res.get("ranking") or [] if isinstance(x, dict)}
        self.log(f"🧑‍⚖️ 「{sc['title'][:20]}」 시안 {len(meta)}개 → V{pick[1] + 1} 선택"
                 + (" (" + " · ".join(f"V{k}:{v}" for k, v in sorted(scores.items())) + ")" if scores else "")
                 + f" — {str(res.get('reason') or '')[:100]}")
        win_imgs = list((pv.get(pick[3]) or {}).get("images") or [])
        return pick[0], str(res.get("fix") or "").strip(), win_imgs

    def research(self, *, title: str, topic: str, script: str) -> dict[str, Any]:
        """🔎 주제 조사 — 대본·주제 설명만 보고(영상·전사 없이) 웹에서 조사한 노트. 실패하면 DirectorError."""
        from .research import clean_research
        if not (topic.strip() or script.strip()):
            return {}
        text = (load_prompt("agents/researcher.md").replace("{{title}}", title or "(미정)")
                .replace("{{topic}}", topic.strip() or "(주제 설명 없음 — 대본에서 읽는다)")
                .replace("{{script}}", script.strip() or "(대본 없음)")
                .replace("{{user_direction}}", direction_block(self.direction)))
        system = load_prompt("system_studio.md")
        self.log("🔎 리서치 디렉터: 대본의 인물·제품·개념을 웹에서 조사"
                 + ("" if self.web else "(이 연결은 웹 도구를 못 써 기억으로만)"))
        res = clean_research(self.call("research", "# 조사 의뢰", text, system=system))
        self.results["research"] = res
        n_files = sum(len(e.get("commons_files") or []) for e in res.get("entities") or [])
        self.log(f"🔎 조사 노트: 대상 {len(res.get('entities') or [])} · 개념 {len(res.get('concepts') or [])} · "
                 f"재현 사양 {len(res.get('recreations') or [])} · 커먼즈 파일 {n_files} · "
                 f"대본 확인 {sum(1 for c in res.get('script_checks') or [] if c['verdict'] in ('wrong', 'caution'))}건")
        return res

    def _instruction(self, key: str, brief: JobBrief, director: dict[str, Any]) -> str:
        text = load_prompt(f"agents/{AGENTS[key].prompt}.md")
        text = (text.replace("{{title}}", brief.title)
                .replace("{{brief}}", compact_brief(director))
                .replace("{{caption_direction}}", str(director.get("caption_direction", "")) or "절제된 에디토리얼")
                .replace("{{user_direction}}", direction_block(self.direction))
                .replace("{{materials}}", self.materials[0] or "(자료 폴더 없음)")
                .replace("{{evidence}}", self.evidence[0] or "(자료 리서처의 확보 목록 없음 — 이번에는 자료 조달이 모션보다 먼저 끝나지 않았다)"))
        if key == "shorts":
            ideas = json.dumps(director.get("shorts_ideas", []), ensure_ascii=False)
            text = (shorts_instruction(brief) + f"\n\n## 총괄 감독의 숏폼 아이디어(참고)\n{ideas}\n"
                    + direction_block(self.direction))
        if key == "motion" and not self.use_motion:
            text += "\n\n(이번 작업은 모션 DSL 장면·HTML 카드를 만들지 않는다: scenes 와 cards 는 빈 배열.)"
        if key in ("motion", "stock", "editor", "captions"):
            text += treatment_block(director, key)
        return text

    def plan(self, brief: JobBrief, ctx: str, *, shorts_count: int,
             progress: Callable[[float], None] = lambda f: None,
             procure: Optional[Callable[[dict[str, Any], int], dict[str, Any]]] = None,
             materials: tuple[str, Optional[bytes]] = ("", None),
             refs: Optional[Callable[[list[str]], dict[str, bytes]]] = None) -> tuple[dict[str, Any], dict[str, Any]]:
        """🎬 → 전문가들. 자료가 먼저, 모션이 나중(13 문서 2-2): 🎞 자료 리서처(증거 계획) → procure(조달 사다리 →
        확보 목록·컨택트 시트, 부족하면 보충 요청 블록) → 🎨 모션 디자이너(확보한 자료를 받고 설계). 나머지 전문가는 그동안
        동시에. 총괄 감독이 실패하면 DirectorError."""
        self.materials = materials
        self.log("🎬 총괄 감독: 전사본을 읽고 크리에이티브 브리프 작성")
        from ..assets.motion_ref import catalog_block
        mref = catalog_block() if (refs is not None and self.use_motion) else ""
        director = self.call("director", ctx, load_prompt("agents/director.md")
                             .replace("{{title}}", brief.title)
                             .replace("{{user_direction}}", direction_block(self.direction))
                             + (f"\n\n{mref}\n시그니처 장면마다 위 목록에서 움직임이 가장 맞는 것 하나를 `motion_ref`(slug)로 "
                                "고른다 — 이름이 아니라 **움직임**(쌓임·마스크·회전·늘어남·숫자 세기 등)이 장면의 뜻과 맞는 것. 맞는 것이 "
                                "없으면 \"\". 앱이 그 템플릿의 미리보기를 찍어 🛠 빌더에게 보여 주고, 빌더는 우리 종이 콜라주 "
                                "스타일로 다시 짓는다." if mref else ""))
        self.results["director"] = director
        self.log(f"🎬 브리프: {director.get('logline', '')}")
        beats = director.get("beats", []) or []
        self.log(f"🎬 비트 {len(beats)}개 · 챕터 {len(director.get('structure', []) or [])}개 → 팀에 전달")
        progress(0.3)

        jobs = [k for k in SPECIALISTS if not (k == "stock" and not self.use_stock)
                and not (k == "shorts" and shorts_count <= 0)]
        scenes = signature_scenes(director) if self.use_motion else []
        ref_sheets: dict[str, bytes] = {}
        if scenes:
            self.log(f"🛠 시그니처 장면 {len(scenes)}개를 따로 짓습니다: " + " · ".join(f"「{sc['title']}」" for sc in scenes))
            want = [sc["motion_ref"] for sc in scenes if sc.get("motion_ref")]
            if want and refs is not None:
                try:
                    ref_sheets = refs(want)
                except Exception as e:  # noqa: BLE001 - 레퍼런스 없이도 짓는다
                    self.log(f"🎞 모션 레퍼런스 캡처 실패 → 레퍼런스 없이: {e}")
        chain = procure is not None and "stock" in jobs and "motion" in jobs
        done = [0]
        # 🎨 스타일 프레임 — 다른 전문가와 동시에 짓고, 🎨 모션·🛠 시그니처 장면은 그것이 끝난 뒤 시작한다(같은 룩에서 출발)
        style_ready = threading.Event()
        want_style = (self.style_on and self.use_motion and not self.style
                      and ("motion" in jobs or bool(scenes)))
        if not want_style:
            style_ready.set()

        def make_style() -> list[tuple[str, Optional[dict[str, Any]]]]:
            try:
                self.make_style_frame(ctx, director)
            finally:
                style_ready.set()
            return []

        def wait_style() -> None:
            while not style_ready.wait(0.5):
                if self.cancel:
                    self.cancel.check()

        def run(key: str, extra: str = "") -> tuple[str, Optional[dict[str, Any]]]:
            if self.cancel:
                self.cancel.check()
            if key == "motion":
                wait_style()
            imgs = None
            if key == "stock" and self.materials[1]:
                imgs = [("자료폴더", self.materials[1], "image/jpeg")]
            if key == "motion" and self.evidence[1]:
                imgs = [("확보자료", self.evidence[1], "image/jpeg")]
            try:
                res = self.call(key, ctx, self._instruction(key, brief, director) + extra, images=imgs)
                return key, res
            except DirectorError as e:
                self.errors[key] = str(e)
                self.log(f"{AGENTS[key].label}: 실패({e}) → 이 파트 없이 진행")
                return key, None
            finally:
                if not extra:
                    done[0] += 1
                    progress(0.3 + 0.7 * done[0] / max(1, len(jobs)))

        def research_then_motion() -> list[tuple[str, Optional[dict[str, Any]]]]:
            out = [run("stock")]
            res = out[0][1]
            if res is not None and procure is not None:
                try:
                    self._procure(res, procure, run)
                except Cancelled:
                    raise
                except Exception as e:  # noqa: BLE001 - 조달이 실패해도 모션은 계속(자료는 예전 단계가 찾는다)
                    self.log(f"🎞 자료 조달 실패 → 모션 디자이너는 확보 목록 없이: {e}")
                    self.results.pop("evidence_outcomes", None)
            out.append(run("motion"))
            return out

        self.log("동시 작업: " + " · ".join(AGENTS[k].label for k in jobs)
                 + (" (🎞 자료 → 조달 → 🎨 모션은 차례로)" if chain else ""))
        def build_scene(sc: dict[str, Any]) -> tuple[str, Optional[dict[str, Any]]]:
            if self.cancel:
                self.cancel.check()
            wait_style()
            text = (load_prompt("agents/setpiece.md")
                    .replace("{{scene}}", json.dumps(sc, ensure_ascii=False, indent=1))
                    .replace("{{treatment}}", json.dumps({k: v for k, v in (director.get("treatment") or {}).items()
                                                          if k not in ("segments", "signature_scenes")},
                                                         ensure_ascii=False, indent=1))
                    .replace("{{user_direction}}", direction_block(self.direction)))
            sheet = ref_sheets.get(sc.get("motion_ref") or "")
            imgs = [(f"모션 레퍼런스 {sc['motion_ref']}(1→8 시간 순서)", sheet, "image/jpeg")] if sheet else None
            if sheet:
                text += ("\n\n## 모션 레퍼런스\n첨부 이미지는 총괄 감독이 고른 레퍼런스 템플릿의 미리보기를 시간 순서로 찍은 것이다. "
                         "그 **움직임**(무엇이 어떤 순서로·어떤 이징으로 들어오고 쌓이고 사라지는지, 마스크·흐림·늘어남·회전)을 읽어 "
                         "이 장면의 내용과 우리 종이 콜라주 스타일(서체·색·질감)로 다시 짓는다. 레퍼런스의 글자·로고·사진·색을 "
                         "그대로 옮기지 않는다. `notes` 에 무엇을 가져왔는지 한 줄.")
            n = max(1, min(len(VARIANT_HINTS), int(self.variants or 1)))
            if n == 1:
                try:
                    res = self.call("setpiece", ctx, text, images=imgs, label=f"🛠 시그니처 장면 「{sc['title'][:16]}」")
                    return "setpiece", {"scene": sc, **res}
                except DirectorError as e:
                    self.errors[f"setpiece:{sc['id']}"] = str(e)
                    self.log(f"🛠 시그니처 장면 「{sc['title']}」 실패({e}) → 이 장면 없이 진행")
                    return "setpiece", None
            return "setpiece", self._build_variants(ctx, sc, text, imgs, n)

        workers = min(self.workers + len(scenes), len(jobs) + len(scenes) or 1) + (1 if want_style else 0)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(make_style)] if want_style else []
            futs += [pool.submit(run, k) for k in jobs if not (chain and k in ("stock", "motion"))]
            if chain:
                futs.append(pool.submit(research_then_motion))
            futs += [pool.submit(build_scene, sc) for sc in scenes]
            setpieces: list[dict[str, Any]] = []
            for f in futs:
                r = f.result()
                for key, res in (r if isinstance(r, list) else [r]):
                    if res is None:
                        continue
                    if key == "setpiece":
                        setpieces.append(res)
                    else:
                        self.results[key] = res
            if setpieces:
                self.results["setpieces"] = sorted(setpieces, key=lambda x: x["scene"]["start_seg"])
        if self.cancel:
            self.cancel.check()
        self._report()
        return merge_plan(self.results, log=self.log)

    def _build_variants(self, ctx: str, sc: dict[str, Any], text: str, imgs: Optional[list[Image3]],
                        n: int) -> Optional[dict[str, Any]]:
        """🧑‍⚖️ 시안 경쟁: 같은 장면을 n 개 방향으로 동시에 짓고(첫 안만 웹 도구) → 렌더해 심사가 고르고 → 심사의 '고칠 것'을
        한 번 반영(렌더 전 검사를 통과할 때만). 모두 실패하면 None."""
        def one(k: int) -> Optional[dict[str, Any]]:
            hint = (f"\n\n## 이번 시안의 방향 ({k + 1}/{n})\n{VARIANT_HINTS[k]}\n같은 장면을 다른 디자이너들도 다른 방향으로 짓고, "
                    "심사가 렌더한 화면을 나란히 보고 하나를 고른다 — 이 방향을 끝까지 밀고 간다.")
            try:
                return self.call("setpiece", ctx, text + hint, images=imgs, web=(k == 0),
                                 label=f"🛠 시그니처 장면 「{sc['title'][:14]}」 {chr(65 + k)}안")
            except DirectorError as e:
                self.log(f"🛠 「{sc['title'][:20]}」 {chr(65 + k)}안 실패({e})")
                return None

        with ThreadPoolExecutor(max_workers=n) as pool:
            outs = list(pool.map(one, range(n)))
        got = [(k, r) for k, r in enumerate(outs) if r]
        if not got:
            self.errors[f"setpiece:{sc['id']}"] = "모든 시안 실패"
            return None

        def layout_of(v: dict[str, Any]) -> str:
            return v.get("layout") if v.get("layout") in ("fullscreen", "split", "overlay") else "fullscreen"

        pos, fix, win_imgs = self.judge_variants(ctx, sc, got, layout_of) if len(got) > 1 else (0, "", [])
        k, best = got[pos]
        best = dict(best, notes=(f"[{chr(65 + k)}안/{len(got)}] " + str(best.get("notes") or ""))[:400])
        if fix and win_imgs:
            card = clean_card({"html": best.get("html", ""), "timeline": best.get("timeline", "")}, layout=layout_of(best),
                              card_id=f"{sc['id'][:10]}fix")
            new = None
            if card:
                try:
                    new = self.revise_card(ctx, card, 8.0, "시안 심사가 고칠 것", fix, win_imgs, layout=layout_of(best))
                except DirectorError as e:
                    self.log(f"🧑‍⚖️ 심사 반영 실패({e}) → 이긴 시안 그대로")
            if new:
                chk = self._preview([{"id": new["id"], "card": new, "layout": layout_of(best), "dur": 8.0,
                                      "label": "수정안"}]).get(new["id"]) or {}
                if chk.get("ok", False):
                    best = dict(best, html=fragment(new), timeline=new.get("timeline", ""))
                    self.log(f"🧑‍⚖️ 「{sc['title'][:20]}」 심사의 지적 반영: {fix[:80]}")
                else:
                    self.log(f"🧑‍⚖️ 「{sc['title'][:20]}」 심사 반영본이 검사에 걸려 이긴 시안 그대로")
        return {"scene": sc, **best}

    def _procure(self, res: dict[str, Any], procure: Callable[[dict[str, Any], int], dict[str, Any]],
                 run: Callable[..., tuple[str, Optional[dict[str, Any]]]]) -> None:
        """조달 1회 → (부족하면) 자료 리서처 보충 호출 1회 → 조달 → 확보 목록. 보충분은 res["items"] 뒤에 붙는다."""
        pr = procure(res, 1)
        outcomes = list(pr.get("outcomes") or [])
        back = str(pr.get("backfill") or "").strip()
        if back:
            self.log("🎞 자료가 부족합니다 → 자료 리서처 보충 호출(1회): " + back.splitlines()[0][:80])
            _, more = run("stock", "\n\n" + back)
            add = [it for it in (more or {}).get("items", []) or [] if isinstance(it, dict)]
            if add:
                pr2 = procure({"items": add, "notes": (more or {}).get("notes", "")}, 2)
                res["items"] = list(res.get("items") or []) + add
                outcomes += list(pr2.get("outcomes") or [])
                pr = {**pr, "brief": pr2.get("brief") or pr.get("brief"), "sheet": pr2.get("sheet") or pr.get("sheet")}
        for n, o in enumerate(outcomes):
            o["i"] = n
        self.results["evidence_outcomes"] = outcomes
        self.evidence = (str(pr.get("brief") or ""), pr.get("sheet"))

    def _report(self) -> None:
        r = self.results
        parts = []
        if "editor" in r:
            parts.append(f"✂️ 추가 컷 {len(r['editor'].get('drop', []))} · 강조 순간 {len(r['editor'].get('moments', []))}")
        if "motion" in r:
            parts.append(f"🎨 그래픽 {len(r['motion'].get('graphics', []))} · 모션 장면 {len(r['motion'].get('scenes', []))}")
        if "stock" in r:
            items = r["stock"].get("items", []) or []
            if items:
                needs: dict[str, int] = {}
                for it in items:
                    needs[str(it.get("need"))] = needs.get(str(it.get("need")), 0) + 1
                parts.append(f"🎞 증거 {len(items)}건(" + " · ".join(f"{k} {v}" for k, v in needs.items()) + ")")
            else:
                parts.append(f"🎞 스톡 요청 {len(r['stock'].get('requests', []))}")
        if "captions" in r:
            parts.append(f"🔤 강조 {len(r['captions'].get('emphasis', []))}")
        if "shorts" in r:
            parts.append(f"📱 숏폼 후보 {len(r['shorts'].get('shorts', []))}")
        if "copy" in r:
            parts.append(f"✍️ 제목안 {len(r['copy'].get('titles', []))}")
        for p in parts:
            self.log(p)

    # ------------------------------------------------------------------
    def pick_evidence(self, ctx: str, requests_text: str, sheets: list[tuple[str, bytes, str]]) -> list[dict[str, Any]]:
        """🎞 후보 시트를 보고 0~3점 채점(EVIDENCE_PICK) — 2점 이상만 쓴다(게이트 B6). 고르는 규칙은 assets/ladder.choose."""
        instr = load_prompt("agents/stock_pick_v2.md").replace("{{requests}}", self.world_text() + requests_text)
        res = self.call("stock_pick", ctx, instr, images=sheets)
        return res.get("picks", []) or []

    def pick_stock(self, ctx: str, requests_text: str, sheets: list[tuple[str, bytes, str]]) -> list[dict[str, Any]]:
        """스톡 후보 선택(StockResearcher 용 모양: request · candidate · reason). 채점은 v2(EVIDENCE_PICK) — 2점 이상 중 최고점,
        뻔한 스톡은 1점 상한이라 빠진다. 2점 이상이 없으면 candidate -1(그 요청은 쓰지 않는다)."""
        from ..assets.ladder import choose
        out = []
        for pk in self.pick_evidence(ctx, requests_text, sheets):
            if "choices" not in pk:              # 예전 모양(가짜·저장된 응답)
                out.append(pk)
                continue
            n = max([int(c.get("candidate", 0) or 0) for c in pk.get("choices") or []] + [0])
            best = choose(pk, n, 1, "")
            out.append({"request": pk.get("request"), "candidate": best[0][0] + 1 if best else -1,
                        "reason": pk.get("reason", ""), "shows": best[0][1].get("shows", "") if best else "",
                        "retry_query_en": str(pk.get("retry_query_en") or "").strip() if not best else ""})
        return out

    def pick_portrait(self, ctx: str, requests_text: str, sheets: list[tuple[str, bytes, str]]) -> list[dict[str, Any]]:
        """📷 인물마다 후보 시트를 보고 가장 품위 있게 나온 사진을 고른다(스키마는 stock_pick 과 같다)."""
        instr = load_prompt("agents/portrait_pick.md").replace("{{requests}}", requests_text)
        res = self.call("portrait_pick", ctx, instr, images=sheets)
        return res.get("picks", []) or []

    def grade(self, ctx: str, notes: str, sheet: tuple[str, bytes, str],
              scope_sheet: Optional[tuple[str, bytes, str]] = None) -> dict[str, Any]:
        """🎨 컬러리스트: 원본 + 룩 5가지 비교 시트(와 원본 스코프)를 보고 룩·세기·미세 조정을 고른다."""
        instr = load_prompt("agents/colorist.md").replace("{{notes}}", notes)
        return self.call("colorist", ctx, instr, images=[sheet] + ([scope_sheet] if scope_sheet else []))

    def score(self, ctx: str, brief: dict[str, Any], tracks: str = "") -> dict[str, Any]:
        """🎼 음악 감독: 컷이 확정된 전사본(편집 시각) + 감독 브리프 → 큐 시트(MUSIC). tracks: 내 음악 폴더의 곡 목록(측정값)
        — 있으면 그중 이 영상에 맞는 곡을 고른다(예전엔 파일 이름 해시로 아무 곡이나 돌렸다)."""
        instr = (load_prompt("agents/music_supervisor.md").replace("{{brief}}", compact_brief(brief))
                 .replace("{{user_direction}}", direction_block(self.direction)))
        if tracks:
            instr += ("\n\n## 내 음악 폴더(채널 주인이 고른 곡 — 이 안에서만 고른다)\n" + tracks
                      + "\n\n`track` 에 이 영상에 쓸 곡의 파일 이름을 그대로 적는다. 고르는 기준: 말 아래 바닥이 되는가(느린 템포·"
                        "낮은 밀도·말 대역이 비어 있음), 트리트먼트의 소리 콘셉트·이 주제의 시대와 질감에 맞는가, 같은 장르의 롱폼 "
                        "해설 채널(디자인·건축·인문 교양)이 실제로 쓰는 결(잔잔한 피아노·앰비언트·로파이·어쿠스틱 미니멀)인가. "
                        "맞는 곡이 없으면 \"\" — 아무 곡이나 고르지 않는다. `track_reason` 한 줄.")
        return self.call("music", ctx, instr)

    def review_timeline(self, ctx: str, events: str, srt: str, plan_text: str, gate_text: str,
                        sheets: list[tuple[str, bytes, str]]) -> dict[str, Any]:
        """🧐 게이트 E: 완성본 검토 시트(2.5초 간격) + 자막 + 이벤트 목록 + 계획 + 게이트 결과 → 루브릭 채점·발견."""
        instr = (load_prompt("agents/timeline_review.md").replace("{{events}}", events).replace("{{srt}}", srt[:12000])
                 .replace("{{plan}}", plan_text).replace("{{gate}}", gate_text))
        if self.world_text():
            instr += "\n\n" + self.world_text() + ("자료·스톡이 이 세계 밖이면(나이·장소·시대·도구) wrong_image 로 적는다.")
        return self.call("timeline_review", ctx, instr, images=sheets)

    def review(self, ctx: str, graphics_text: str, stills: list[tuple[str, bytes, str]]) -> dict[str, Any]:
        instr = load_prompt("agents/art_director.md").replace("{{graphics}}", graphics_text)
        if self.world_text():
            instr += ("\n\n" + self.world_text() + "사진·스톡·그림 부품이 이 세계 밖이면(나이·장소·시대·직업 도구) R19 로 "
                      "적고 revise_scene 으로 그 그림을 이 세계의 손·도구·과정으로 바꾸게 한다.")
        return self.call("art_director", ctx, instr, images=stills)

    def critique(self, ctx: str, gid: str, kind: str, speech: str, images: list[Image3]) -> dict[str, Any]:
        """🧑‍⚖️ 장면 심사(독립 critic): 렌더 그림(정착 화면 + 움직임 시트)만 보고 하드 실패·점수·고칠 것을 낸다."""
        instr = (load_prompt("agents/card_critic.md").replace("{id}", gid).replace("{speech}", speech or "(말 없음)")
                 .replace("{kind}", kind))
        if self.world_text():
            instr += "\n\n" + self.world_text() + "그림·사물이 이 세계 밖이면(나이·장소·시대·직업 도구) specificity 를 낮게 보고 fix 에 적는다."
        return self.call("card_critic", ctx, instr, images=images, label=f"🧑‍⚖️ 장면 심사 {gid}")

    def revise_card(self, ctx: str, card: dict[str, Any], dur: float, problem: str, direction: str,
                    still: Any, *, layout: str = "fullscreen", checks: tuple[str, ...] = (),
                    self_review: str = "") -> Optional[dict[str, Any]]:
        """🃏 카드 수정: 아트 디렉터 지적 또는 렌더 전 검사(check) 결과를 주고 고친 카드 조각을 받는다.
        still: 그림 하나 또는 여럿(정지 화면 + 움직임 시트 · 검사 화면). self_review: 자기 검토 지시(그대로면 html 을 비움)."""
        instr = (load_prompt("agents/card_revise.md").replace("{{dur}}", f"{dur:.1f}")
                 .replace("{{canvas}}", f"{card.get('w', 1920)}×{card.get('h', 1080)}")
                 # 지금 timeline 은 html 코드 블록 밖에 따로(안에 넣으면 html 블록 끝에 설명 글이 붙어 그대로 돌려받는다 — 2026-10-04)
                 .replace("{{card}}\n```", fragment(card) + "\n```" + (
                     f"\n\n지금 timeline(직접 쓴 GSAP — html 의 선택자를 바꾸면 함께 고쳐 낸다):\n```js\n{card['timeline']}\n```"
                     if card.get("timeline") else ""))
                 .replace("{{problem}}", problem or "(없음)").replace("{{direction}}", direction or "(없음)")
                 .replace("{{checks}}", "\n".join(f"- {c}" for c in checks) or "- (없음)"))
        if self_review:
            instr += "\n\n" + self_review
        res = self.call("card_revise", ctx, instr, images=_images(still))
        if self_review and not str(res.get("html") or "").strip():
            self.log(f"🔍 카드 {card.get('id', '')}: 그대로 — {res.get('changes', '')}")
            return None
        # 고친 timeline 이 비어 있으면 원래 것을 그대로(안무를 잃지 않게 — 선택자가 사라졌으면 렌더 전 검사가 잡는다)
        new = clean_card({"html": res.get("html", ""),
                          "timeline": str(res.get("timeline") or "").strip() or card.get("timeline", "")},
                         layout=layout, card_id=str(card.get("id") or ""))
        if new:
            if not new.get("style"):
                new["style"] = card.get("style", "")
            self.log(f"{'🔍' if self_review else '🃏'} 카드 수정: {res.get('changes', '')}")
        return new

    def revise_scene(self, ctx: str, spec: dict[str, Any], dur: float, problem: str, direction: str,
                     still: Any, *, self_review: str = "") -> Optional[dict[str, Any]]:
        """🎨 모션 장면 수정. still: 그림 하나 또는 여럿(정지 화면 + 움직임 6칸 시트).
        self_review: 자기 검토 지시 — 고칠 것이 없다고 보면 spec_json 을 비워 None 을 돌려준다."""
        instr = (load_prompt("agents/motion_revise.md").replace("{{dur}}", f"{dur:.1f}")
                 .replace("{{spec}}", json.dumps(spec, ensure_ascii=False))
                 .replace("{{problem}}", problem or "").replace("{{direction}}", direction or ""))
        if self.world_text():
            instr += "\n\n" + self.world_text() + "그림 부품('pixabay:…' 검색어)도 이 세계 안의 구체 명사 2~4낱말로 쓴다."
        if self_review:
            instr += "\n\n" + self_review
        res = self.call("motion_revise", ctx, instr, images=_images(still))
        if self_review and not str(res.get("spec_json") or "").strip():
            self.log(f"🔍 장면: 그대로 — {res.get('changes', '')}")
            return None
        new = parse_spec(res.get("spec_json", ""))
        cleaned = clean_spec(new, dur) if new else None
        if cleaned:
            self.log(f"{'🔍' if self_review else '🎨'} 수정: {res.get('changes', '')}")
        return cleaned
