"""✂️ 컷 편집 총괄(Opus): 규칙 초안을 대본과 함께 보여 주고, 틀린 판단만 고친 결과를 적용한다."""
from __future__ import annotations

from studio.models import Utterance, Word
from studio.text import cut_review
from studio.text.script import parse_script


def _ws(text: str, t0: float) -> list[Word]:
    return [Word(w, t0 + i * 0.3, t0 + i * 0.3 + 0.25, 0.9) for i, w in enumerate(text.split())]


def test_draft_shows_script_verdicts_and_removed_words_with_context():
    raw = _ws("좋은 디자인은 단순합니다. 좋은 디자인은 정직합니다.", 0.0)
    u0 = Utterance(0, 1.8, 2.6, "좋은 디자인은 정직합니다.", "좋은 디자인은 정직합니다.", raw[3:])
    u1 = Utterance(1, 5.0, 6.0, "아 다시 할게요", "아 다시 할게요", _ws("아 다시 할게요", 5.0), status="meta", note="NG")
    removals = [{"start": 0.0, "end": 0.85, "text": "좋은 디자인은 단순합니다.", "reason": "되풀이(다시 말한 앞부분)"}]
    text = cut_review.draft_text(parse_script("좋은 디자인은 단순합니다. 좋은 디자인은 정직합니다.").sentences,
                                 [u0, u1], removals, raw)
    assert "[1] 좋은 디자인은 단순합니다." in text and "[2] 좋은 디자인은 정직합니다." in text
    assert "U0" in text and "[남김]" in text and "U1" in text and "[뺌: NG·메타 발화" in text
    assert "R0" in text and "「좋은 디자인은 단순합니다.」" in text and "뒤: 좋은 디자인은 정직합니다." in text


def test_apply_restores_wrong_cuts_and_cuts_what_rules_missed():
    raw = _ws("좋은 디자인은 단순합니다. 좋은 디자인은 정직합니다.", 0.0) + _ws("음 카메라 괜찮나", 4.0)
    keep = Utterance(0, 0.9, 1.7, "좋은 디자인은 정직합니다.", "좋은 디자인은 정직합니다.", raw[3:6])
    retake = Utterance(1, 10.0, 11.0, "형태는 기능을 따른다", "형태는 기능을 따른다", _ws("형태는 기능을 따른다", 10.0),
                       status="retake", note="#3 가 더 또렷함")
    chatter = Utterance(2, 4.0, 4.9, "음 카메라 괜찮나", "음 카메라 괜찮나", raw[6:])
    removals = [{"start": 0.0, "end": 0.85, "text": "좋은 디자인은 단순합니다.", "reason": "되풀이"},
                {"start": 20.0, "end": 20.3, "text": "어", "reason": "추임새"}]
    res = {"utterances": [{"id": 1, "keep": True, "reason": "다른 문장"}, {"id": 2, "keep": False, "reason": "카메라 확인"}],
           "removals": [{"id": 0, "keep_removed": True, "reason": "끝난 다른 문장"}], "notes": "병렬 문장 살림"}
    rv, remaining = cut_review.apply(res, [keep, retake, chatter], removals, raw)
    assert retake.kept and not chatter.kept and chatter.status == "editor_cut"
    assert remaining == removals[1:]                                    # 되살린 말은 지운 목록에서 빠진다
    assert [w.text for w in keep.words][:3] == ["좋은", "디자인은", "단순합니다."]   # 그 시각의 발화에 단어가 돌아왔다
    assert keep.start == 0.0 and rv.summary() == "되살린 발화 1 · 더 뺀 발화 1 · 되살린 말 1"


def test_vocal_events_find_cough_between_words_and_default_cut_is_conservative():
    """기침: VAD 말소리는 있는데 인식 단어가 없는 토막. 또렷이 떨어진 파열음만 AI 없이 자른다."""
    import numpy as np
    from studio.media.vocal_events import as_removals, default_cuts, vocal_events
    sr = 16000
    audio = np.zeros(sr * 6, dtype=np.float32)
    rng = np.random.default_rng(1)
    audio[int(1.0 * sr):int(1.8 * sr)] = 0.05 * np.sin(np.arange(int(0.8 * sr)) * 2 * np.pi * 180 / sr)   # 말 1
    audio[int(2.4 * sr):int(2.7 * sr)] = 0.3 * rng.standard_normal(int(0.3 * sr)).astype(np.float32)        # 기침(큰 파열음)
    audio[int(3.4 * sr):int(4.2 * sr)] = 0.05 * np.sin(np.arange(int(0.8 * sr)) * 2 * np.pi * 180 / sr)   # 말 2
    audio[int(4.25 * sr):int(4.45 * sr)] = 0.004 * rng.standard_normal(int(0.2 * sr)).astype(np.float32)   # 말 끝의 숨(약함)
    vad = [(1.0, 1.8), (2.4, 2.7), (3.4, 4.45)]
    words = [Word("디자인은", 1.0, 1.4), Word("과정이다", 1.4, 1.8), Word("결과가", 3.4, 3.8), Word("전부가", 3.8, 4.2)]
    ev = vocal_events(audio, vad, words)
    kinds = {(e["start"], e["kind"]) for e in ev}
    assert (2.4, "burst") in kinds, ev
    cough = next(e for e in ev if e["start"] == 2.4)
    assert cough["prev"] == "과정이다" and cough["next"] == "결과가" and cough["gap_prev"] > 0.5
    assert default_cuts(ev) == [cough["id"]]                                   # 숨(약한 소리·말에 붙음)은 두고 기침만
    rem = as_removals(ev, [cough["id"]], {cough["id"]: "헛기침"})
    assert rem and rem[0]["start"] == 2.4 and rem[0]["reason"].startswith("비언어 소리")


def test_draft_lists_events_and_apply_returns_event_cuts():
    raw = _ws("좋은 디자인은 정직합니다.", 0.0)
    u0 = Utterance(0, 0.0, 0.85, "좋은 디자인은 정직합니다.", "좋은 디자인은 정직합니다.", raw, script_span=(0, 10), score=91)
    events = [{"id": 0, "start": 1.2, "end": 1.5, "dur": 0.3, "dbfs": -22.0, "kind": "burst", "prev": "정직합니다.", "next": "",
               "gap_prev": 0.35, "gap_next": 9.9}]
    text = cut_review.draft_text(parse_script("좋은 디자인은 정직합니다.").sentences, [u0], [], raw, events, {0: 0})
    assert "# 비언어 소리" in text and "A0" in text and "파열음" in text and "(대본 91)" in text
    res = {"utterances": [{"id": 0, "keep": True, "reason": "대본 문장"}], "removals": [],
           "audio_events": [{"id": 0, "cut": True, "reason": "헛기침"}, {"id": 7, "cut": True, "reason": "없는 id"}], "notes": ""}
    rv, remaining = cut_review.apply(res, [u0], [], raw)
    assert u0.kept and rv.summary() == "초안 그대로"
    assert cut_review.event_cuts(res, events) == ([0], {0: "헛기침"})


def test_vocal_events_flag_isolated_filler_words_for_the_editor():
    """2026-10-03 채널 주인: 헛기침 같은 소리 NG 가 그대로 들어간다 — 인식기가 '흠'·'음' 같은 단어로 적은 홀로 떨어진 토막을
    '의심 단어' 이벤트로 컷 총괄에게 넘기고, 자르기로 하면 그 낱말로 removed 구간이 된다."""
    import numpy as np
    from studio.media.vocal_events import SR, as_removals, default_cuts, vocal_events
    from studio.models import Word
    words = [Word("디자인은", 1.0, 1.5, 0.95), Word("흠", 2.0, 2.3, 0.4), Word("먼저", 2.8, 3.2, 0.95),
             Word("넓게", 3.25, 3.6, 0.95), Word("음", 3.62, 3.8, 0.3)]      # 마지막 '음'은 말에 붙어 있다 → 의심하지 않음
    audio = np.full(int(4.5 * SR), 0.1, dtype=np.float32)
    ev = vocal_events(audio, [(0.9, 4.0)], words)
    words_ev = [e for e in ev if e["kind"] == "word"]
    assert [e["text"] for e in words_ev] == ["흠"] and words_ev[0]["gap_prev"] == 0.5 and words_ev[0]["gap_next"] == 0.5
    assert default_cuts(ev) == [e["id"] for e in ev if e["kind"] == "burst" and e["gap_prev"] >= 0.25 and e["gap_next"] >= 0.25]
    rem = as_removals(ev, [words_ev[0]["id"]], {words_ev[0]["id"]: "헛기침"})
    assert rem == [{"start": 2.0, "end": 2.3, "text": "흠", "reason": "비언어 소리: 헛기침"}]
