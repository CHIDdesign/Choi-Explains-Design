"""업로드용 메타데이터(제목 후보·설명란·태그·고정댓글)와 편집 리포트."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..util import fmt_ts


def chapter_lines(chapters: list[dict]) -> str:
    lines = []
    for i, c in enumerate(chapters):
        t = 0.0 if i == 0 else c["start"]
        lines.append(f"{fmt_ts(t)} {c['title']}")
    return "\n".join(lines)


def youtube_text(plan: dict[str, Any], chapters: list[dict], shorts: list[dict], image_credits: list[str]) -> str:
    yt = plan.get("youtube") or {}
    desc = yt.get("description") or ""
    chap = chapter_lines(chapters)
    desc = desc.replace("{{CHAPTERS}}", chap) if "{{CHAPTERS}}" in desc else (desc + "\n\n" + chap).strip()
    if image_credits:
        desc += "\n\n이미지 출처\n" + "\n".join(f"- {c}" for c in image_credits)
    parts = ["# 롱폼 업로드 정보", "", "## 제목 후보"]
    parts += [f"{i + 1}. {t}" for i, t in enumerate(yt.get("titles") or [])]
    parts += ["", "## 설명란", "", desc, "", "## 태그", ", ".join(yt.get("tags") or []), "",
              "## 썸네일 문구 후보"] + [f"- {t}" for t in yt.get("thumbnail_texts") or []]
    parts += ["", "## 고정 댓글", yt.get("pinned_comment", ""), ""]
    music = plan.get("music") or {}
    if music:
        parts += ["## 음악 추천", f"- 무드: {music.get('mood', '')}", f"- 운용: {music.get('notes', '')}", ""]
    for i, s in enumerate(shorts, 1):
        parts += [f"# 숏폼 {i}: {s.get('title', '')}", "",
                  f"- 훅 유형: {s.get('hook_type', '')}",
                  f"- 상단 타이틀: {s.get('hook_title', '').replace(chr(10), ' / ')}",
                  "", "캡션:", s.get("caption", ""), s.get("cta", ""), " ".join(s.get("hashtags") or []), ""]
    return "\n".join(parts)


def edit_report(*, title: str, source_duration: float, long_duration: float, align_report: dict,
                utts: list, graphics: list[dict], chapters: list[dict], shorts: list[dict],
                director: str, usage: list[dict], broll: list[dict], studio: dict | None = None,
                qa: list[dict] | None = None) -> str:
    removed = [u for u in utts if not u.kept]
    lines = [f"# 편집 리포트 — {title}", "",
             f"- 편집 판단: {director}",
             f"- 원본 길이 {fmt_ts(source_duration)} → 롱폼 {fmt_ts(long_duration)} "
             f"({(1 - long_duration / max(1e-6, source_duration)) * 100:.0f}% 단축)",
             f"- 대본 일치 발화 {align_report.get('matched', 0)}개 · 리테이크 제거 {align_report.get('retakes', 0)}개 · "
             f"NG/추임새 제거 {align_report.get('meta', 0)}개 · 대본 밖 애드리브 {align_report.get('unmatched', 0)}개",
             f"- 대본 커버리지 {align_report.get('script_coverage', 0) * 100:.0f}%", ""]
    if studio:
        lines += ["## 🎬 AI 스튜디오 브리프", "",
                  f"- 로그라인: {studio.get('logline', '')}",
                  f"- 대상: {studio.get('audience', '')} · 톤: {studio.get('tone', '')}",
                  f"- 팀 메모: {studio.get('notes_for_team', '')}",
                  f"- ✂️ 호흡: {studio.get('pacing_notes', '')}",
                  f"- 🔤 자막: {studio.get('caption_notes', '')}",
                  f"- 🎨 모션 장면 {studio.get('motion_scenes', 0)}개 · 🎞 스톡 요청 {studio.get('stock_requests', 0)}건", ""]
        beats = studio.get("beats") or []
        if beats:
            lines += ["| 발화 | 의도 | 시각 수단 | 아이디어 |", "|---|---|---|---|"]
            for b in beats:
                lines.append(f"| S{b.get('start_seg')}–S{b.get('end_seg')} | {b.get('intent')} | {b.get('visual')} | "
                             f"{str(b.get('idea', ''))[:60]} |")
            lines.append("")
    if qa:
        lines += ["## 🧐 아트 디렉터 검수", ""]
        for r in qa:
            lines.append(f"### {r.get('round')}라운드 — {r.get('verdict')} (반영 {r.get('applied', 0)}건)")
            lines.append(f"{r.get('summary', '')}")
            for i in r.get("issues", []) or []:
                lines.append(f"- {i.get('target')} [{i.get('severity')}] {i.get('problem')} → {i.get('action')}")
            lines.append("")
        lines += ["> 페이싱의 느낌·음악 취향·그래픽의 전반적 인상은 기계가 판단할 수 없습니다. 위 타임코드를 직접 확인하세요.", ""]
    missing = align_report.get("missing_sentences") or []
    if missing:
        lines += ["## 영상에서 찾지 못한 대본 문장(말하지 않았거나 인식 실패)", ""] + [f"- {m}" for m in missing] + [""]
    if removed:
        lines += ["## 잘라낸 발화", "", "| 원본 시각 | 이유 | 내용 |", "|---|---|---|"]
        for u in removed[:200]:
            lines.append(f"| {fmt_ts(u.start, True)} | {u.status} {u.note} | {u.asr_text[:60]} |")
        lines.append("")
    lines += ["## 챕터", ""] + [f"- {fmt_ts(c['start'])} ({c['number']}) {c['title']}" for c in chapters] + [""]
    lines += ["## 그래픽", "", "| 시각 | 템플릿 | 레이아웃 | 내용 |", "|---|---|---|---|"]
    for g in graphics:
        d = g.get("data", {})
        text = d.get("title") or d.get("body") or ", ".join(d.get("items") or [])
        lines.append(f"| {fmt_ts(g['start'], True)}–{fmt_ts(g['end'], True)} | {g['template']} | {g['layout']} | {str(text)[:50]} |")
    lines.append("")
    if broll:
        lines += ["## 자료 사진·스톡 출처(라이선스 확인)", ""]
        for b in broll:
            lines.append(f"- {b.get('query')}: {b.get('origin')} {b.get('credit', '')} {b.get('license', '')} "
                         f"{b.get('source_url', '') or b.get('url', '')}".rstrip())
        lines.append("")
    if shorts:
        lines += ["## 숏폼", ""]
        for i, s in enumerate(shorts, 1):
            lines += [f"### {i}. {s.get('title')}  (점수 {s.get('score')}, {s.get('duration', 0):.0f}초)",
                      f"- 훅: {s.get('hook_type')} — {s.get('hook_title', '').replace(chr(10), ' / ')}",
                      f"- 콜드 오픈: {'S' + str(s['cold_open_seg']) if s.get('cold_open_seg', -1) >= 0 else '없음'}",
                      f"- 구간: {', '.join('S' + str(x) for x in s.get('segments', []))}",
                      f"- 이유: {s.get('why', '')}", ""]
    if usage:
        inp = sum(u.get("input", 0) for u in usage)
        out = sum(u.get("output", 0) for u in usage)
        lines += ["## Claude 사용량", "", f"- 입력 {inp:,} 토큰(캐시 읽기 {sum(u.get('cache_read', 0) for u in usage):,}) · 출력 {out:,} 토큰",
                  "- 요금은 모델별 단가로 계산됩니다(Opus 5.5 기준 입력 $4 / 출력 $20 per 1M 토큰).", ""]
        by: dict[str, list[int]] = {}
        for u in usage:
            acc = by.setdefault(str(u.get("label", "")), [0, 0, 0, 0])
            acc[0] += 1
            acc[1] += u.get("input", 0)
            acc[2] += u.get("cache_read", 0)
            acc[3] += u.get("output", 0)
        if len(by) > 1:
            lines += ["| 에이전트 | 호출 | 입력 | 캐시 읽기 | 출력 |", "|---|---|---|---|---|"]
            for lab, (n, i, c, o) in by.items():
                lines.append(f"| {lab} | {n} | {i:,} | {c:,} | {o:,} |")
            lines.append("")
    return "\n".join(lines)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
