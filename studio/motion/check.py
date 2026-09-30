"""자유 HTML 카드의 렌더 전 검사 — renderer/scripts/check.mjs 를 렌더와 같은 Chrome 으로 돌린다.

HyperFrames `check` 의 우리 판: 카드를 실제 캔버스 크기로 붙이고 정착 시각으로 seek 한 뒤
runtime_error · anim_* · font_not_loaded · font_family_not_bundled · text_overflow · outside_canvas · text_too_small ·
low_contrast 를 본다. 결과는 카드 id → {"ok", "problems": [{code, detail, selector}], "metrics"}.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ..paths import RENDERER_DIR
from ..util import CancelToken, LogFn, noop_log, run_process, write_json
from .card import card_settle_time


class CheckError(RuntimeError):
    pass


def problem_lines(result: dict[str, Any]) -> list[str]:
    """에이전트에게 보낼 한 줄 요약들("code: detail (selector)")."""
    out = []
    for p in result.get("problems", []) or []:
        sel = f" ({p['selector']})" if p.get("selector") else ""
        out.append(f"{p.get('code', '?')}: {p.get('detail', '')}{sel}")
    return out


def check_cards(cards: list[dict[str, Any]], *, node: str, out_dir: Path, fps: int, durations: dict[str, float],
                browser_executable: str = "", gl: str = "", log: LogFn = noop_log,
                cancel: Optional[CancelToken] = None) -> dict[str, dict[str, Any]]:
    """cards: 정리된 CardSpec(id 포함) 목록. durations: id → 카드 길이(초)."""
    if not cards:
        return {}
    out_dir.mkdir(parents=True, exist_ok=True)
    job = {
        "browserExecutable": browser_executable, "gl": gl, "outDir": str(out_dir),
        "cards": [{
            "id": c["id"], "html": c["html"], "css": c["css"], "w": int(c.get("w", 1920)), "h": int(c.get("h", 1080)),
            "fps": int(fps), "duration": float(durations.get(c["id"], 8.0)),
            "settle": min(float(durations.get(c["id"], 8.0)) - 0.2, card_settle_time(c) + 0.3),
            "layout": c.get("layout", "fullscreen"),
        } for c in cards],
    }
    job_file = out_dir / "check_job.json"
    write_json(job_file, job)
    results: dict[str, dict[str, Any]] = {}
    err = {"msg": ""}

    def on_line(line: str) -> None:
        line = line.strip()
        if not line.startswith("{"):
            return
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            return
        if ev.get("type") == "card":
            results[ev["id"]] = {"ok": bool(ev.get("ok")), "problems": ev.get("problems", []), "metrics": ev.get("metrics", {})}
        elif ev.get("type") == "error":
            err["msg"] = str(ev.get("message", ""))[:600]

    code, tail = run_process([node, str(RENDERER_DIR / "scripts" / "check.mjs"), str(job_file)], cwd=str(RENDERER_DIR),
                             on_line=on_line, cancel=cancel)
    if code != 0 and not results:
        raise CheckError(err["msg"] or tail[-600:])
    for c in cards:
        r = results.get(c["id"])
        if r is None:
            results[c["id"]] = {"ok": False, "problems": [{"code": "runtime_error", "detail": "검사 결과 없음", "selector": ""}],
                                "metrics": {}}
            continue
        if r["ok"]:
            log(f"🃏 카드 {c['id']} 검사 통과 · 애니메이션 {len(r['metrics'].get('anims', []))} · 글자 {r['metrics'].get('chars', 0)}")
        else:
            log(f"🃏 카드 {c['id']} 검사 실패: " + " · ".join(problem_lines(r)[:4]))
    return results
