"""Claude 에게 보낼 공통 컨텍스트(전사본·태그·메모)와 시스템 프롬프트 조립."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..models import Tag, TimeMap, Utterance
from ..paths import PROMPTS_DIR
from ..util import fmt_ts
from .catalog import catalog_markdown


@dataclass
class JobBrief:
    title: str
    notes: str = ""
    episode: str = ""
    subtitle: str = ""
    local_images: list[str] = field(default_factory=list)
    shorts_count: int = 2
    short_max_sec: int = 60
    presenter: str = ""
    brand: str = ""


def load_prompt(name: str) -> str:
    p = PROMPTS_DIR / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def system_prompt() -> str:
    parts = [
        load_prompt("system_director.md"),
        "\n\n# 채널 스타일 가이드\n\n" + load_prompt("style_guide.md"),
        "\n\n# 숏폼 후킹 가이드\n\n" + load_prompt("hooks.md"),
        "\n\n# 그래픽 템플릿 카탈로그\n\n" + catalog_markdown(),
    ]
    return "\n".join(p for p in parts if p.strip())


def _tag_str(t: Tag) -> str:
    return t.raw or f"[{t.kind}: {' | '.join(t.args)}]"


def transcript_block(utts: list[Utterance], tags: list[Tag], timemap: TimeMap | None) -> str:
    by_utt: dict[int, list[Tag]] = {}
    for t in tags:
        if t.utt_id is not None:
            by_utt.setdefault(t.utt_id, []).append(t)
    lines = []
    for u in utts:
        if not u.kept:
            continue
        edit = ""
        if timemap is not None:
            e = timemap.src_to_edit(u.start)
            if e is not None:
                edit = f" | 편집 {fmt_ts(e, True)}"
        lines.append(f"[S{u.id} | 원본 {fmt_ts(u.start, True)}{edit} | {u.end - u.start:.1f}s] {u.text}")
        for t in by_utt.get(u.id, []):
            lines.append(f"    ↳ 대본 태그: {_tag_str(t)}")
    return "\n".join(lines)


def shared_context(brief: JobBrief, utts: list[Utterance], tags: list[Tag], timemap: TimeMap | None,
                   duration: float) -> str:
    kept = [u for u in utts if u.kept]
    parts = [
        "# 이번 영상 정보",
        f"- 제목(가제): {brief.title}",
    ]
    if brief.episode:
        parts.append(f"- 에피소드: {brief.episode}")
    if brief.subtitle:
        parts.append(f"- 부제: {brief.subtitle}")
    if brief.presenter:
        parts.append(f"- 화자: {brief.presenter}")
    parts.append(f"- 컷 편집 후 예상 길이: {fmt_ts(duration)} ({len(kept)}개 발화 구간)")
    if brief.local_images:
        parts.append("- 사용 가능한 로컬 이미지 파일(파일명이 곧 설명): " + ", ".join(brief.local_images[:80]))
    else:
        parts.append("- 로컬 이미지 없음 → photo 템플릿의 image 에는 위키미디어 검색용 영어 검색어를 적는다")
    parts.append("\n# 화자의 메모(주제·주요 장면·의도)\n")
    parts.append(brief.notes.strip() or "(없음)")
    parts.append("\n# 전사본 (S번호 = 발화 ID. 이미 NG/리테이크/무음은 제거된 상태)\n")
    parts.append(transcript_block(utts, tags, timemap))
    return "\n".join(parts)


def long_instruction(brief: JobBrief) -> str:
    return load_prompt("task_longform.md").replace("{{title}}", brief.title)


def shorts_instruction(brief: JobBrief) -> str:
    return (load_prompt("task_shorts.md")
            .replace("{{count}}", str(brief.shorts_count))
            .replace("{{max_sec}}", str(brief.short_max_sec)))


def prompt_files_present() -> list[str]:
    return [p.name for p in Path(PROMPTS_DIR).glob("*.md")]
