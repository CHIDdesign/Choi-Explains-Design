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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ..director.catalog import catalog_markdown
from ..director.claude import ClaudeClient, DirectorError, extract_json
from ..director.context import JobBrief, load_prompt, shorts_instruction
from ..motion.card import STYLES, clean_card, fragment
from ..motion.spec import clean_spec
from ..util import CancelToken, LogFn, noop_log
from . import schemas as S


@dataclass(frozen=True)
class Agent:
    key: str
    label: str
    prompt: str          # prompts/agents/<prompt>.md
    schema: dict
    effort: str          # 기본 사고 강도(설정에서 바꿀 수 있음)
    max_tokens: int = 32000


AGENTS: dict[str, Agent] = {a.key: a for a in [
    Agent("director", "🎬 총괄 감독", "director", S.BRIEF, "high"),
    Agent("editor", "✂️ 편집 감독", "editor", S.EDITOR, "medium", 16000),
    Agent("motion", "🎨 모션 디자이너", "motion", S.MOTION, "high", 48000),
    Agent("stock", "🎞 자료 리서처", "stock", S.STOCK, "medium", 16000),
    Agent("captions", "🔤 자막 디자이너", "captions", S.CAPTIONS, "medium", 24000),
    Agent("shorts", "📱 숏폼 PD", "shorts", S.SHORTS, "high", 32000),
    Agent("copy", "✍️ 카피라이터", "copy", S.COPY, "medium", 16000),
    Agent("stock_pick", "🎞 자료 리서처(선택)", "stock_pick", S.STOCK_PICK, "low", 8000),
    Agent("art_director", "🧐 아트 디렉터", "art_director", S.QA, "high", 24000),
    Agent("motion_revise", "🎨 모션 디자이너(수정)", "motion_revise", S.MOTION_REVISE, "high", 24000),
    Agent("card_revise", "🃏 카드 디자이너(수정)", "card_revise", S.CARD_REVISE, "high", 32000),
    Agent("colorist", "🎨 컬러리스트", "colorist", S.GRADE, "medium", 8000),
]}

SPECIALISTS = ("editor", "motion", "stock", "captions", "shorts", "copy")


def studio_system_prompt() -> str:
    """모든 에이전트가 공유하는 시스템 프롬프트(한 번 캐시되면 모든 호출이 재사용)."""
    parts = [
        load_prompt("system_studio.md"),
        "\n\n# 채널 스타일 가이드\n\n" + load_prompt("style_guide.md"),
        "\n\n# 숏폼 후킹 가이드\n\n" + load_prompt("hooks.md"),
        "\n\n" + playbook_block(),
        "\n\n# 그래픽 템플릿 카탈로그\n\n" + catalog_markdown(),
        "\n\n" + load_prompt("motion_dsl.md") + motion_examples_block(),
        "\n\n" + load_prompt("card_dsl.md") + card_examples_block(),
        "\n\n# 디자인 스킬 노트(오픈소스 스킬에서 정리)\n\n" + load_prompt("skills/motion_principles.md"),
        "\n\n" + load_prompt("skills/caption_design.md"),
        "\n\n" + load_prompt("skills/editing_principles.md"),
    ]
    return "\n".join(p for p in parts if p.strip())


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
    parts = ["\n\n## 카드 예시(실제 렌더 검증됨 — 구조·크기·타이밍을 따르고 내용만 바꾼다)\n"]
    for name, ex in data.items():
        parts.append(f"\n### {name} — {ex.get('title', '')} ({ex.get('style', '')}, {ex.get('layout', 'fullscreen')})\n"
                     f"```html\n{ex.get('html', '').strip()}\n```\n")
    return "".join(parts)


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
# 합치기(순수 함수 — 테스트 가능)
# ---------------------------------------------------------------------------

def _g(template: str, layout: str, start: int, end: int, word: str = "", **kw: Any) -> dict[str, Any]:
    g = {"template": template, "layout": layout, "start_seg": start, "end_seg": end, "start_word": word,
         "title": "", "subtitle": "", "body": "", "items": [], "title_b": "", "items_b": [], "highlight": -1,
         "author": "", "source": "", "image": "", "reason": ""}
    g.update(kw)
    return g


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
        graphics.append(_g("motion", sc.get("layout") or "fullscreen", sc.get("start_seg", -1),
                           sc.get("end_seg", sc.get("start_seg", -1)), sc.get("start_word", ""),
                           title=sc.get("title", ""), reason="모션 디자이너: " + str(sc.get("reason", "")), spec=spec))
        n_scene += 1
    n_card = 0
    for cd in motion.get("cards", []) or []:
        if not isinstance(cd, dict):
            continue
        layout = cd.get("layout") if cd.get("layout") in ("fullscreen", "split", "overlay") else "fullscreen"
        card = clean_card(cd.get("html", ""), layout=layout, card_id=f"card{n_card + 1}")
        if not card:
            log(f"🃏 카드 '{cd.get('title', '')}' 의 HTML 이 올바르지 않아 제외")
            continue
        if not card.get("style") and cd.get("style") in STYLES:
            card["style"] = cd["style"]
        if card.get("problems"):
            log(f"🃏 카드 '{cd.get('title', '')}' 정리: {', '.join(card['problems'][:4])}")
        graphics.append(_g("card", layout, cd.get("start_seg", -1), cd.get("end_seg", cd.get("start_seg", -1)),
                           cd.get("start_word", ""), title=cd.get("title", ""),
                           reason="모션 디자이너(카드): " + str(cd.get("reason", "")), card=card))
        n_card += 1
    # 📷 고유명사 자료 사진 — 위키백과 문서의 대표 이미지(인물·작품·사물·브랜드·장소·종교). 없으면 스톡으로 넘기지 않는다
    for ph in stock.get("photos", []) or []:
        if not isinstance(ph, dict):
            continue
        name_ko = str(ph.get("name_ko") or "").strip()
        name_en = str(ph.get("name_en") or "").strip()
        if not (name_ko or name_en):
            continue
        layout = ph.get("layout") if ph.get("layout") in ("pip", "split", "fullscreen") else "pip"
        graphics.append(_g("photo", layout, ph.get("start_seg", -1), ph.get("start_seg", -1), ph.get("start_word", ""),
                           title=name_ko or name_en, image=name_ko or name_en, subtitle=name_en,
                           body=str(ph.get("kind") or ""), reason="자료 리서처(위키백과): " + str(ph.get("reason", "")),
                           wiki=True))
    for r in stock.get("requests", []) or []:
        if not (r.get("query_en") or r.get("query_ko")):
            continue
        graphics.append(_g("broll", r.get("layout") or "fullscreen", r.get("start_seg", -1),
                           r.get("end_seg", r.get("start_seg", -1)), r.get("start_word", ""),
                           title=r.get("query_ko", ""), image=r.get("query_en", ""), subtitle=r.get("kind", "video"),
                           body=r.get("purpose", ""), reason="자료 리서처: " + str(r.get("purpose", "")),
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
        "youtube": {k: copy.get(k, [] if k not in ("description", "pinned_comment") else "")
                    for k in ("titles", "description", "hashtags", "tags", "thumbnail_texts", "pinned_comment")},
        "music": brief.get("music") or {},
        "captions": {},   # 자막 모양은 채널 템플릿(흰 종이 상자 + 두 층 강조)로 고정 — 디자이너는 강조어만 정한다
        "studio": {
            "logline": brief.get("logline", ""), "thesis": brief.get("thesis", ""), "audience": brief.get("audience", ""),
            "tone": brief.get("tone", ""),
            "beats": brief.get("beats", []), "notes_for_team": brief.get("notes_for_team", ""),
            "pacing_notes": editor.get("pacing_notes", ""), "caption_notes": caps.get("notes", ""),
            "motion_scenes": n_scene, "cards": n_card, "stock_requests": len(stock.get("requests", []) or []),
            "wiki_photos": len(stock.get("photos", []) or []),
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
        self.results: dict[str, Any] = {}
        self.errors: dict[str, str] = {}

    # ------------------------------------------------------------------
    def call(self, key: str, ctx: str, instruction: str, *, images=None) -> dict[str, Any]:
        a = AGENTS[key]
        eff = self.effort.get(key) or a.effort
        model = self.models.get(key) or None
        return self.claude.structured(system=self.system, shared_context=ctx, instruction=instruction, schema=a.schema,
                                      max_tokens=a.max_tokens, cancel=self.cancel, label=a.label, images=images,
                                      effort=eff, model=model)

    def _instruction(self, key: str, brief: JobBrief, director: dict[str, Any]) -> str:
        text = load_prompt(f"agents/{AGENTS[key].prompt}.md")
        text = (text.replace("{{title}}", brief.title)
                .replace("{{brief}}", compact_brief(director))
                .replace("{{caption_direction}}", str(director.get("caption_direction", "")) or "절제된 에디토리얼")
                .replace("{{user_direction}}", direction_block(self.direction)))
        if key == "shorts":
            ideas = json.dumps(director.get("shorts_ideas", []), ensure_ascii=False)
            text = (shorts_instruction(brief) + f"\n\n## 총괄 감독의 숏폼 아이디어(참고)\n{ideas}\n"
                    + direction_block(self.direction))
        if key == "motion" and not self.use_motion:
            text += "\n\n(이번 작업은 모션 DSL 장면·HTML 카드를 만들지 않는다: scenes 와 cards 는 빈 배열.)"
        return text

    def plan(self, brief: JobBrief, ctx: str, *, shorts_count: int,
             progress: Callable[[float], None] = lambda f: None) -> tuple[dict[str, Any], dict[str, Any]]:
        """🎬 → 병렬 전문가 → 합치기. 총괄 감독이 실패하면 DirectorError."""
        self.log("🎬 총괄 감독: 전사본을 읽고 크리에이티브 브리프 작성")
        director = self.call("director", ctx, load_prompt("agents/director.md")
                             .replace("{{title}}", brief.title)
                             .replace("{{user_direction}}", direction_block(self.direction)))
        self.results["director"] = director
        self.log(f"🎬 브리프: {director.get('logline', '')}")
        beats = director.get("beats", []) or []
        self.log(f"🎬 비트 {len(beats)}개 · 챕터 {len(director.get('structure', []) or [])}개 → 팀에 전달")
        progress(0.3)

        jobs = [k for k in SPECIALISTS if not (k == "stock" and not self.use_stock)
                and not (k == "shorts" and shorts_count <= 0)]
        done = [0]

        def run(key: str) -> tuple[str, Optional[dict[str, Any]]]:
            if self.cancel:
                self.cancel.check()
            try:
                res = self.call(key, ctx, self._instruction(key, brief, director))
                return key, res
            except DirectorError as e:
                self.errors[key] = str(e)
                self.log(f"{AGENTS[key].label}: 실패({e}) → 이 파트 없이 진행")
                return key, None
            finally:
                done[0] += 1
                progress(0.3 + 0.7 * done[0] / max(1, len(jobs)))

        self.log("동시 작업: " + " · ".join(AGENTS[k].label for k in jobs))
        with ThreadPoolExecutor(max_workers=min(self.workers, len(jobs) or 1)) as pool:
            for key, res in pool.map(run, jobs):
                if res is not None:
                    self.results[key] = res
        if self.cancel:
            self.cancel.check()
        self._report()
        return merge_plan(self.results, log=self.log)

    def _report(self) -> None:
        r = self.results
        parts = []
        if "editor" in r:
            parts.append(f"✂️ 추가 컷 {len(r['editor'].get('drop', []))} · 강조 순간 {len(r['editor'].get('moments', []))}")
        if "motion" in r:
            parts.append(f"🎨 그래픽 {len(r['motion'].get('graphics', []))} · 모션 장면 {len(r['motion'].get('scenes', []))}")
        if "stock" in r:
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
    def pick_stock(self, ctx: str, requests_text: str, sheets: list[tuple[str, bytes, str]]) -> list[dict[str, Any]]:
        instr = load_prompt("agents/stock_pick.md").replace("{{requests}}", requests_text)
        res = self.call("stock_pick", ctx, instr, images=sheets)
        return res.get("picks", []) or []

    def grade(self, ctx: str, notes: str, sheet: tuple[str, bytes, str]) -> dict[str, Any]:
        """🎨 컬러리스트: 원본 + 룩 5가지 비교 시트를 보고 룩·세기·미세 조정을 고른다."""
        instr = load_prompt("agents/colorist.md").replace("{{notes}}", notes)
        return self.call("colorist", ctx, instr, images=[sheet])

    def review(self, ctx: str, graphics_text: str, stills: list[tuple[str, bytes, str]]) -> dict[str, Any]:
        instr = load_prompt("agents/art_director.md").replace("{{graphics}}", graphics_text)
        return self.call("art_director", ctx, instr, images=stills)

    def revise_card(self, ctx: str, card: dict[str, Any], dur: float, problem: str, direction: str,
                    still: Optional[tuple[str, bytes, str]], *, layout: str = "fullscreen",
                    checks: tuple[str, ...] = ()) -> Optional[dict[str, Any]]:
        """🃏 카드 수정: 아트 디렉터 지적 또는 렌더 전 검사(check) 결과를 주고 고친 카드 조각을 받는다."""
        instr = (load_prompt("agents/card_revise.md").replace("{{dur}}", f"{dur:.1f}")
                 .replace("{{canvas}}", f"{card.get('w', 1920)}×{card.get('h', 1080)}")
                 .replace("{{card}}", fragment(card))
                 .replace("{{problem}}", problem or "(없음)").replace("{{direction}}", direction or "(없음)")
                 .replace("{{checks}}", "\n".join(f"- {c}" for c in checks) or "- (없음)"))
        res = self.call("card_revise", ctx, instr, images=[still] if still else None)
        new = clean_card(res.get("html", ""), layout=layout, card_id=str(card.get("id") or ""))
        if new:
            if not new.get("style"):
                new["style"] = card.get("style", "")
            self.log(f"🃏 카드 수정: {res.get('changes', '')}")
        return new

    def revise_scene(self, ctx: str, spec: dict[str, Any], dur: float, problem: str, direction: str,
                     still: Optional[tuple[str, bytes, str]]) -> Optional[dict[str, Any]]:
        instr = (load_prompt("agents/motion_revise.md").replace("{{dur}}", f"{dur:.1f}")
                 .replace("{{spec}}", json.dumps(spec, ensure_ascii=False))
                 .replace("{{problem}}", problem or "").replace("{{direction}}", direction or ""))
        res = self.call("motion_revise", ctx, instr, images=[still] if still else None)
        new = parse_spec(res.get("spec_json", ""))
        cleaned = clean_spec(new, dur) if new else None
        if cleaned:
            self.log(f"🎨 수정: {res.get('changes', '')}")
        return cleaned
