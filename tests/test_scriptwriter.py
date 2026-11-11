from studio.agents.scriptwriter import to_markdown


def test_markdown_pairs_each_paragraph_with_its_beat_and_visual():
    md = to_markdown({"title": "의자", "hooks": [{"type": "반직관", "line": "이 의자는 실패작입니다.", "why": "통념을 깸"}],
                      "chosen_hook": 0, "script": "첫 문단.\n\n둘째 문단.", "beats": ["훅", "증거"],
                      "visual_notes": ["의자 실물", ""], "fact_checks": [], "open_questions": ["관점?"]})
    assert md.startswith("# 의자") and "← 대본에 씀" in md
    assert "첫 문단.\n\n> 훅 · 화면: 의자 실물" in md and "둘째 문단.\n\n> 증거" in md
    assert "- 관점?" in md and "- (없음)" in md
