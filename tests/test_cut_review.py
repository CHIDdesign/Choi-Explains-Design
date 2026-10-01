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
