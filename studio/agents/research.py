"""🔎 주제 조사 노트(docs/upgrade/14) — Claude 가 웹 검색·가져오기로 만든 조사 결과를 다듬고, 팀이 읽는 글로 바꾼다.

- `clean_research` : 스키마 결과를 믿을 수 있게(빈 칸·길이·커먼즈 파일 이름 정리)
- `research_block` : 모든 에이전트가 공유 컨텍스트로 읽는 조사 노트(마크다운)
- `commons_index`  : 대상 이름 → 조사자가 확인한 커먼즈 파일(조달 사다리가 먼저 쓴다)
- `research_notes` : 화자에게 주는 `부가자료/조사노트.md`(출처·대본 확인 포함)
"""
from __future__ import annotations

import re
from typing import Any

FILE_RE = re.compile(r"\.(jpe?g|png|tiff?|webp|gif|svg|pdf|djvu)$", re.I)
VERDICT_KO = {"wrong": "❌ 사실과 다름", "caution": "⚠ 주의", "unverifiable": "❓ 확인 못 함", "ok": "✅ 맞음"}


def commons_name(x: Any) -> str:
    """'File:Don Norman.jpg' · 커먼즈 URL · 'Don_Norman.jpg' → 'Don Norman.jpg'(확장자 없는 것은 버린다)."""
    s = str(x or "").strip()
    if not s:
        return ""
    if "/" in s:
        m = re.search(r"(?:File:|/)([^/?#]+\.[A-Za-z]{3,4})(?:[?#].*)?$", s)
        s = m.group(1) if m else ""
    s = re.sub(r"^(File|파일|Image):", "", s, flags=re.I).replace("_", " ").strip()
    try:
        from urllib.parse import unquote
        s = unquote(s)
    except Exception:  # noqa: BLE001
        pass
    return s if FILE_RE.search(s) and len(s) <= 240 else ""


def _s(x: Any, n: int = 400) -> str:
    return re.sub(r"\s+", " ", str(x or "")).strip()[:n]


def _url(x: Any) -> str:
    s = str(x or "").strip()
    return s[:400] if s.startswith(("http://", "https://")) else ""


def clean_research(d: Any) -> dict[str, Any]:
    d = d if isinstance(d, dict) else {}
    out: dict[str, Any] = {"topic_summary": _s(d.get("topic_summary"), 1200), "angle": _s(d.get("angle"), 300)}
    ents = []
    for e in d.get("entities") or []:
        if not isinstance(e, dict) or not (e.get("name_ko") or e.get("name_en")):
            continue
        files = list(dict.fromkeys(f for f in (commons_name(x) for x in e.get("commons_files") or []) if f))[:6]
        ents.append({"name_ko": _s(e.get("name_ko"), 80), "name_en": _s(e.get("name_en"), 120),
                     "kind": _s(e.get("kind"), 20) or "other", "role_in_script": _s(e.get("role_in_script"), 300),
                     "script_quote": _s(e.get("script_quote"), 120), "summary": _s(e.get("summary"), 600),
                     "facts": [{"fact": _s(f.get("fact"), 300), "source_url": _url(f.get("source_url"))}
                               for f in e.get("facts") or [] if isinstance(f, dict) and f.get("fact")][:8],
                     "years": _s(e.get("years"), 40), "visual_identity": _s(e.get("visual_identity"), 400),
                     "commons_files": files, "official_url": _url(e.get("official_url")),
                     "wikipedia_url": _url(e.get("wikipedia_url"))})
    out["entities"] = ents[:40]

    def rows(key: str, fields: tuple[str, ...], need: str, cap: int, n: int = 400) -> list[dict[str, Any]]:
        res = []
        for r in d.get(key) or []:
            if isinstance(r, dict) and r.get(need):
                row = {f: _s(r.get(f), n) for f in fields}
                if "source_url" in r:
                    row["source_url"] = _url(r.get("source_url"))
                res.append(row)
        return res[:cap]
    out["concepts"] = rows("concepts", ("term", "term_en", "plain", "canonical_example", "visual_metaphor"), "term", 30)
    out["timeline"] = rows("timeline", ("year", "event"), "event", 40)
    quotes = rows("quotes", ("text", "speaker", "work"), "text", 20, 500)
    for q, r in zip(quotes, [r for r in d.get("quotes") or [] if isinstance(r, dict) and r.get("text")]):
        q["verified"] = bool(r.get("verified"))
    out["quotes"] = quotes
    out["numbers"] = rows("numbers", ("value", "meaning"), "value", 30)
    out["recreations"] = rows("recreations", ("name", "what", "spec"), "name", 20, 1500)
    checks = rows("script_checks", ("sentence", "verdict", "note"), "sentence", 40, 500)
    out["script_checks"] = [c for c in checks if c["verdict"] in ("wrong", "caution", "unverifiable", "ok")]
    out["visual_directions"] = [_s(x, 400) for x in d.get("visual_directions") or [] if _s(x)][:8]
    out["sources"] = [{"title": _s(x.get("title"), 160), "url": _url(x.get("url"))}
                      for x in d.get("sources") or [] if isinstance(x, dict) and _url(x.get("url"))][:40]
    return out


def is_empty(d: dict[str, Any]) -> bool:
    return not (d.get("entities") or d.get("concepts") or d.get("topic_summary"))


def commons_index(d: dict[str, Any]) -> dict[str, list[str]]:
    """대상 이름(한국어·원어, 소문자·공백 정리) → 커먼즈 파일 이름들."""
    idx: dict[str, list[str]] = {}
    for e in d.get("entities") or []:
        files = e.get("commons_files") or []
        if not files:
            continue
        for name in (e.get("name_ko"), e.get("name_en")):
            k = norm_name(name)
            if k:
                idx.setdefault(k, [])
                idx[k] += [f for f in files if f not in idx[k]]
    return idx


def norm_name(x: Any) -> str:
    return re.sub(r"[\s·・.\-_'\"()]+", "", str(x or "").lower())


def files_for(d: dict[str, Any], *names: Any) -> list[str]:
    idx = commons_index(d)
    out: list[str] = []
    for n in names:
        for f in idx.get(norm_name(n), []):
            if f not in out:
                out.append(f)
    return out


def research_block(d: dict[str, Any]) -> str:
    """공유 컨텍스트에 붙이는 조사 노트 — 팀 전원이 같은 사실·같은 자료 목록에서 출발한다."""
    if not d or is_empty(d):
        return ""
    L = ["# 🔎 주제 조사 노트(리서치 디렉터가 웹에서 확인한 것 — 화면의 사실은 여기서만)", ""]
    if d.get("topic_summary"):
        L += [d["topic_summary"], ""]
    if d.get("angle"):
        L += [f"대본의 관점: {d['angle']}", ""]
    if d.get("entities"):
        L.append("## 대상")
        for e in d["entities"]:
            name = e["name_ko"] + (f" ({e['name_en']})" if e["name_en"] and e["name_en"] != e["name_ko"] else "")
            L.append(f"### {name} · {e['kind']}" + (f" · {e['years']}" if e["years"] else ""))
            for k, lab in (("role_in_script", "대본에서"), ("script_quote", "처음 나오는 문장"), ("summary", "요약"),
                           ("visual_identity", "생김새·알아보는 표지")):
                if e.get(k):
                    L.append(f"- {lab}: {e[k]}")
            for f in e.get("facts") or []:
                L.append(f"- 사실: {f['fact']}")
            if e.get("commons_files"):
                L.append("- 커먼즈 파일(확인됨): " + " · ".join(f"`{x}`" for x in e["commons_files"]))
        L.append("")
    if d.get("concepts"):
        L.append("## 개념")
        for c in d["concepts"]:
            L.append(f"- **{c['term']}**" + (f" ({c['term_en']})" if c.get("term_en") else "") + f": {c['plain']}"
                     + (f" — 대표 예: {c['canonical_example']}" if c.get("canonical_example") else "")
                     + (f" — 화면 은유: {c['visual_metaphor']}" if c.get("visual_metaphor") else ""))
        L.append("")
    if d.get("timeline"):
        L.append("## 연표")
        L += [f"- {t['year']}: {t['event']}" for t in d["timeline"]]
        L.append("")
    if d.get("numbers"):
        L.append("## 숫자(출처 확인)")
        L += [f"- {n['value']} — {n['meaning']}" for n in d["numbers"]]
        L.append("")
    if d.get("quotes"):
        L.append("## 인용(✔ = 원문 확인)")
        L += [f"- {'✔' if q.get('verified') else '·'} “{q['text']}” — {q['speaker']}" + (f", {q['work']}" if q.get("work") else "")
              for q in d["quotes"]]
        L.append("")
    if d.get("recreations"):
        L.append("## 화면으로 재현할 수 있는 것(사양)")
        L += [f"- **{r['name']}** — {r['what']}\n  사양: {r['spec']}" for r in d["recreations"]]
        L.append("")
    if d.get("visual_directions"):
        L.append("## 리서처의 연출 제안")
        L += [f"- {x}" for x in d["visual_directions"]]
        L.append("")
    bad = [c for c in d.get("script_checks") or [] if c["verdict"] in ("wrong", "caution")]
    if bad:
        L.append("## 대본 확인(화면 글자가 틀린 사실을 굳히지 않게 — 대본은 그대로 둔다)")
        L += [f"- {VERDICT_KO[c['verdict']]}: 「{c['sentence'][:60]}」 — {c['note']}" for c in bad]
        L.append("")
    return "\n".join(L).strip() + "\n"


def research_notes(d: dict[str, Any], *, title: str = "") -> str:
    """화자에게 주는 조사 노트(부가자료/조사노트.md) — 출처 링크와 대본 확인을 포함한다."""
    if not d or is_empty(d):
        return ""
    L = [f"# 조사 노트{(' — ' + title) if title else ''}", "",
         "이 영상의 그래픽·자료는 아래 조사에서 출발했습니다. 대본은 고치지 않았습니다 — '대본 확인'은 다음 녹화나 고정 댓글에 참고하세요.", ""]
    checks = [c for c in d.get("script_checks") or [] if c["verdict"] != "ok"]
    if checks:
        L.append("## 대본 확인")
        for c in checks:
            L.append(f"- {VERDICT_KO.get(c['verdict'], c['verdict'])} 「{c['sentence']}」  ")
            L.append(f"  {c['note']}" + (f" ([출처]({c['source_url']}))" if c.get("source_url") else ""))
        L.append("")
    body = research_block(d)
    body = body.split("\n", 1)[1] if body.startswith("# ") else body
    L.append(body)
    facts = [(e["name_ko"] or e["name_en"], f) for e in d.get("entities") or [] for f in e.get("facts") or []
             if f.get("source_url")]
    if facts:
        L.append("## 사실별 출처")
        L += [f"- {n}: {f['fact']} — {f['source_url']}" for n, f in facts]
        L.append("")
    if d.get("sources"):
        L.append("## 참고한 페이지")
        L += [f"- [{s['title'] or s['url']}]({s['url']})" for s in d["sources"]]
    return "\n".join(L).strip() + "\n"
