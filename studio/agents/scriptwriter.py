"""✍ 대본 생성기 — 채널 주인의 아이디어·메모(글·파일) → 첫 3초 훅과 사람 말투의 대본 초안.

채널 주인 2026-11-11: "내가 생각한 아이디어나 내용을 파일이나 텍스트로 넣으면, 후킹과 가장 인간적이고 자연스러우며 직관적인 말투로
대본을 클로드가 생성해 주는 거지." 사실은 웹으로 확인하고(지어내지 않는다), 결과는 마크다운 한 장으로 남긴다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..util import LogFn, noop_log


def write_script(idea: str, settings: Any, *, minutes: float = 0.0, log: LogFn = noop_log) -> dict[str, Any]:
    from ..director.context import load_prompt
    from . import schemas as S
    from .reference import make_client
    from .studio import lean_system_prompt
    client, why = make_client(settings, log)
    if client is None:
        raise RuntimeError(f"Claude 에 연결할 수 없습니다: {why}")
    length = f"약 {minutes:g}분(한국어 말 기준 분당 약 300자)" if minutes else "아이디어에 맞게(논점 하나를 끝내는 가장 짧은 길이)"
    instr = (load_prompt("agents/scriptwriter.md").replace("{{idea}}", idea.strip()).replace("{{length}}", length))
    return client.structured(system=lean_system_prompt(("skills/expression_palette.md",)), shared_context="",
                             instruction=instr, schema=S.SCRIPT, max_tokens=16000, label="✍ 대본 작가",
                             tools=("WebSearch", "WebFetch"), max_turns=16)


def to_markdown(r: dict[str, Any]) -> str:
    hooks = "\n".join(f"{i + 1}. **[{h['type']}]** {h['line']} — {h['why']}" + (" ← 대본에 씀" if i == r.get("chosen_hook") else "")
                      for i, h in enumerate(r.get("hooks") or []))
    paras = [p for p in str(r.get("script", "")).split("\n\n") if p.strip()]
    beats, notes = r.get("beats") or [], r.get("visual_notes") or []
    body = "\n\n".join(p.strip() + (f"\n\n> {beats[i]}" if i < len(beats) and beats[i] else "")
                       + (f" · 화면: {notes[i]}" if i < len(notes) and notes[i] else "") for i, p in enumerate(paras))
    facts = "\n".join(f"- {f['claim']} — {f['source']}" for f in r.get("fact_checks") or []) or "- (없음)"
    qs = "\n".join(f"- {q}" for q in r.get("open_questions") or []) or "- (없음)"
    return (f"# {r.get('title', '대본')}\n\n## 훅 후보\n{hooks}\n\n## 대본\n\n{body}\n\n## 사실 확인\n{facts}\n\n"
            f"## 정해 주세요\n{qs}\n")


def run(idea_arg: str, settings: Any, *, minutes: float = 0.0, out: str = "", log: LogFn = noop_log) -> Path:
    p = Path(idea_arg)
    if idea_arg and len(idea_arg) < 260 and p.exists():
        from ..text.docfile import read_text_file
        idea, base = read_text_file(str(p)), p.parent
    else:
        idea, base = idea_arg, Path.cwd()
    if not idea.strip():
        raise ValueError("아이디어가 비어 있습니다 — 글이나 파일 경로를 주세요")
    r = write_script(idea, settings, minutes=minutes, log=log)
    dst = Path(out) if out else base / f"대본_{''.join(c for c in r.get('title', '초안') if c not in chr(92) + '/:*?\"<>|')[:40]}.md"
    dst.write_text(to_markdown(r), encoding="utf-8")
    return dst
