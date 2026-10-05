"""단어 단위 되풀이·추임새 정리(studio/text/takes.py) — 실제 업로드 영상 음성 인식에서 나온 유형들."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.models import Word  # noqa: E402
from studio.text.takes import clean_words, vad_pause  # noqa: E402


def say(*parts):
    """문자열은 말(어절마다 0.3초), 숫자는 쉼(초)."""
    out, t = [], 0.0
    for p in parts:
        if isinstance(p, (int, float)):
            t += p
            continue
        for w in p.split():
            out.append(Word(w, round(t, 3), round(t + 0.28, 3), 0.9))
            t += 0.3
    return out


def text(ws):
    return " ".join(w.text for w in ws)


def test_restart_after_pause_drops_the_aborted_part():
    kept, rem = clean_words(say("완성도가 얼마나 높은지, 그리고 그것의 평가가 거의", 1.2,
                                "그것의 평가가 거의 전부처럼 느껴질 때가 많습니다."))
    assert text(kept) == "완성도가 얼마나 높은지, 그리고 그것의 평가가 거의 전부처럼 느껴질 때가 많습니다."
    assert rem[0].reason.startswith("되풀이")


def test_multiple_attempts_keep_only_the_last():
    kept, _ = clean_words(say("일종의 실험이기도 합니다. 먼저 발견이에요.",
                              "제가 편집에서 시간을 가장 많이 쓰는 곳이 어디서", 2.0,
                              "먼저 발견이에요. 제가 편집에서 시간을 가장 많이 쓰는 곳이 어디", 2.3,
                              "제가 편집에서 시간을 가장 많이 쓰는 곳이 어디인지부터 봤어요."))
    t = text(kept)
    assert t.count("제가 편집에서") == 1 and t.count("발견이에요") == 1
    assert t.endswith("어디인지부터 봤어요.")


def test_three_tries_with_divergent_tails():
    kept, _ = clean_words(say("그리고 이왕 공부하는 거 혼자 알고 끝내지 말.", 0.4, "아", 0.3,
                              "그리고 이왕 공부하는 거 혼자 말고 끝.", 2.8,
                              "그리고 이왕 공부하는 거 나누자고 생각을 했습니다."))
    assert text(kept) == "그리고 이왕 공부하는 거 나누자고 생각을 했습니다."


def test_immediate_correction_without_pause_when_long_match():
    kept, _ = clean_words(say("이제 그 과정을 여러분과 같이 이제 그 과정을 여러분들이랑 같이 하나씩 밟아 보려고 합니다."))
    assert text(kept) == "이제 그 과정을 여러분들이랑 같이 하나씩 밟아 보려고 합니다."


def test_intentional_repetition_is_kept():
    s = ("첫 번째 다이아몬드는 문제를 발견하는 단계입니다. 두 번째 다이아몬드는 해결책을 만드는 단계입니다. "
         "좋은 과정이 좋은 결과를 만듭니다.")
    kept, rem = clean_words(say(s))
    assert text(kept) == s and not rem


def test_completed_sentence_between_similar_openings_is_not_a_restart():
    """'좋은 질문에는 … 있습니다.' 다음 문장이 '좋은 질문에서'를 다시 말해도 앞 문장은 완성된 문장 — 지우면 안 된다.
    (VAD 가 어절마다 쉼을 잡아도)"""
    ws = say("좋은 질문에는 세 가지 조건이 있습니다.", 0.9, "결국 좋은 디자인은", 0.4, "좋은 질문에서 시작합니다.")
    kept, rem = clean_words(ws, pause=lambda a, b: 0.5)
    assert text(kept) == text(ws) and not rem
    # 끝난 문장이라도 'NG(다시 할게요)'가 끼어 있으면 버린 시도
    ws = say("좋은 질문에는 세 가지가 있습니다.", 0.6, "아 다시 할게요", 1.0, "좋은 질문에는 세 가지 조건이 있습니다.")
    kept, _ = clean_words(ws, pause=lambda a, b: 0.5)
    assert text(kept) == "좋은 질문에는 세 가지 조건이 있습니다."


def test_fillers_are_removed_but_words_starting_with_them_stay():
    kept, rem = clean_words(say("어", 0.3, "저는 일단", 0.2, "어", 0.2, "홍익대학교 산업 디자인을 전공하고 있어요. 아이디어가 중요해요."))
    assert text(kept) == "저는 일단 홍익대학교 산업 디자인을 전공하고 있어요. 아이디어가 중요해요."
    assert [r.reason for r in rem] == ["추임새", "추임새"]


def test_vad_reveals_pause_hidden_by_stretched_whisper_words():
    # Whisper 가 '거의' 를 다음 단어 직전까지 늘려 쉼이 0초로 보여도, VAD 로는 1초 넘게 조용하다
    ws = [Word("그것의", 0.0, 0.3, 1), Word("평가가", 0.3, 0.6, 1), Word("거의", 0.6, 2.0, 1),
          Word("그것의", 2.0, 2.3, 1), Word("평가가", 2.3, 2.6, 1), Word("거의", 2.6, 2.9, 1), Word("전부입니다.", 2.9, 3.4, 1)]
    vad = [(0.0, 0.85), (2.0, 3.4)]
    kept, _ = clean_words(ws, pause=vad_pause(vad))
    assert text(kept) == "그것의 평가가 거의 전부입니다."


def test_dead_air_inside_keep_is_trimmed_unless_a_word_starts_there():
    from studio.edit.cuts import trim_dead_air
    from studio.models import Span
    vad = [(0.0, 1.5), (3.8, 5.0)]            # 2.3초 무음(Whisper 는 '끝.' 을 늘려 이 쉼을 덮음)
    out = trim_dead_air([Span(0.0, 5.0)], vad, [0.1, 0.6, 1.0, 3.9], max_silence=0.6)
    assert len(out) == 2 and out[0].end < 1.8 and out[1].start > 3.5
    kept_silence = (out[1].start - out[0].end)
    assert 3.5 - 1.5 < kept_silence + 1.5          # 대부분 잘림
    # 조용한 구간에서 시작하는 단어가 있으면(작은 소리) 건드리지 않음
    same = trim_dead_air([Span(0.0, 5.0)], vad, [0.1, 2.4, 3.9], max_silence=0.6)
    assert same == [Span(0.0, 5.0)]


def test_verify_maps_issues_back_to_source_and_subtracts():
    from studio.edit.verify import Issue, find_issues, subtract, to_source
    from studio.models import Span, TimeMap
    tm = TimeMap([Span(10.0, 14.0), Span(20.0, 26.0)])          # 편집 0~4 → 원본 10~14, 편집 4~10 → 원본 20~26
    src = to_source([Issue(3.0, 5.0, "되풀이")], tm)              # 경계를 넘는 문제 → 원본 두 조각
    assert [(round(s.start, 2), round(s.end, 2)) for s in src] == [(13.0, 14.0), (20.0, 21.0)]
    keeps = subtract(tm.keeps, src)
    assert [(k.start, k.end) for k in keeps] == [(10.0, 13.0), (21.0, 26.0)]
    # 편집된 목소리에 남은 긴 무음·되풀이를 찾는다
    words = say("그리고 그것의 평가가 거의", 1.0, "그것의 평가가 거의 전부입니다.")
    vad = [(0.0, 1.5), (4.0, 6.0)]
    kinds = [i.reason for i in find_issues(words, vad, max_silence=0.6, duration=6.0)]
    assert any(k.startswith("되풀이") for k in kinds) and "긴 무음" in kinds


def test_keep_extends_early_whisper_word_end_to_real_speech_end():
    """Whisper 가 '안녕하세요' 끝을 0.96초로(실제 1.50초) 찍어 '요' 가 잘리던 문제."""
    from studio.edit.cuts import PACES, build_keeps
    from studio.models import Span, Utterance
    u = Utterance(id=0, start=0.44, end=0.96, text="안녕하세요.", asr_text="안녕하세요.",
                  words=[Word("안녕하세요.", 0.44, 0.96, 0.9)])
    nxt = Utterance(id=1, start=2.48, end=3.0, text="오늘은", asr_text="오늘은", words=[Word("오늘은", 2.48, 3.0, 0.9)])
    nxt.status = "retake"
    vad = [(0.58, 1.63), (2.5, 5.47)]
    keeps = build_keeps([u, nxt], pace=PACES["normal"], vad=vad, media_duration=10, fps=30)
    assert keeps[0].end >= 1.5
    # 바로 뒤에 지운 구간이 붙어 있으면 그 전까지만
    keeps2 = build_keeps([u], pace=PACES["normal"], vad=[(0.58, 3.0)], media_duration=10, fps=30,
                         exclude=[Span(1.2, 2.9)])
    assert keeps2[0].end <= 1.25          # 프레임 격자(1/30초) 반올림까지


def test_captions_are_short_phrases_and_follow_speech():
    from studio.text.captions import _clen, build_phrase_cues, snap_cues_to_speech
    ws = say("제품 디자인은 굉장히 실무적인 분야입니다.", 0.4,
             "렌더링이 얼마나 설득력이 있는지, 목업의 완성도가 얼마나 높은지, 그 평가가 거의 전부처럼 느껴질 때가 많습니다.")
    cues = build_phrase_cues([ws])
    texts = [" ".join(w["text"] for w in c["lines"][0]) for c in cues]
    assert all(len(c["lines"]) == 1 for c in cues)
    assert all(sum(_clen(w["text"]) for w in c["lines"][0]) <= 16 for c in cues), texts
    assert all(c["end"] - c["start"] <= 2.6 for c in cues)
    # 구 단위로(호흡): 목적어·관형어·부사는 뒷말과 함께, 이음 어미·쉼표 뒤에서 끊는다
    assert "설득력이 있는지" in texts and "목업의 완성도가" in texts and "거의 전부처럼" in texts, texts
    assert all(len(c["lines"][0]) <= 3 for c in cues), texts
    # 자막 시작을 실제 말소리 시작에 맞춤(Whisper 단어 시작이 0.2초 이른 경우)
    c0 = [{"start": 1.0, "end": 2.0, "lines": [[{"text": "안녕"}]]}]
    snap_cues_to_speech(c0, [1.2])
    assert abs(c0[0]["start"] - 1.16) < 1e-6


def test_same_word_needs_same_stem_not_just_prefix():
    from studio.text.takes import same_word
    assert same_word("평가가", "평가는") and same_word("어디서", "어디인지") and same_word("여러분과", "여러분들이랑")
    assert not same_word("디자인은", "디자이너는") and not same_word("말", "말고")


def test_sentences_sharing_a_discourse_marker_are_not_a_restart():
    """'그래서 이제 …' 로 시작하는 문장이 잇달아 나와도(끝말이 어미로 안 잡혀도) 되풀이가 아니다."""
    ws = say("그래서 이제 형태를 먼저 그리게 되죠", 0.9, "그래서 이제 문제를 정의하는 단계로 갑니다.")
    kept, rem = clean_words(ws)
    assert text(kept) == text(ws) and not rem


def test_strict_mode_only_removes_certain_restarts():
    ws = say("좋은 디자인은", 0.8, "좋은 디자인은 설명이 필요 없습니다.")      # 2어절 되풀이 — 1차에서는 지움, 2차(strict)는 안 지움
    kept, rem = clean_words(ws)
    assert text(kept) == "좋은 디자인은 설명이 필요 없습니다." and rem
    kept2, rem2 = clean_words(ws, strict=True)
    assert text(kept2) == text(ws) and not rem2
    ws3 = say("그것의 평가가 거의 전부처럼", 0.8, "그것의 평가가 거의 전부처럼 느껴집니다.")
    kept3, _ = clean_words(ws3, strict=True)
    assert text(kept3) == "그것의 평가가 거의 전부처럼 느껴집니다."


def test_removed_span_is_cut_inside_real_silence():
    """지운 되풀이의 경계를 Whisper 단어 시각이 아니라 실제 쉼(VAD)에 맞춘다 — 꼬리가 새지 않고 다음 말 앞에 숨 한 번."""
    from studio.edit.cuts import PACES, build_keeps
    from studio.models import Span, Utterance
    # 남는 말: 0.0–1.0 '좋은 디자인은' … 지운 시도: 1.3–2.0(Whisper) 실제 말소리 1.25–2.35 … 다시 말함 2.9–4.0
    u = Utterance(id=0, start=0.0, end=4.0, text="좋은 디자인은 설명이 필요 없습니다.", asr_text="",
                  words=[Word("좋은", 0.0, 0.4), Word("디자인은", 0.45, 1.0), Word("설명이", 2.9, 3.4), Word("필요", 3.45, 3.7),
                         Word("없습니다.", 3.72, 4.0)])
    vad = [(0.0, 1.05), (1.25, 2.35), (2.85, 4.1)]
    keeps = build_keeps([u], pace=PACES["calm"], vad=vad, media_duration=10, fps=30, exclude=[Span(1.3, 2.0)])
    assert len(keeps) == 2
    assert keeps[0].end <= 1.3 + 0.02 + 1 / 30            # 지운 시도의 말소리(1.25~) 앞에서 끊고
    assert 2.35 <= keeps[1].start <= 2.85                  # 꼬리(2.0~2.35)는 버리고 다음 말 앞 쉼에서 다시 시작


def test_captions_break_on_phrase_breath_not_char_count():
    """채널 피드백 예시: '철수는 오늘 / 비행기를 타고 / 로스앤젤레스로 향하는 / 길이었다' — 글자 수로만 끊으면
    '철수는 오늘 비행기를 / 타고 로스앤젤레스로 / 향하는 길이었다' 처럼 구가 갈라진다."""
    from studio.text.captions import build_phrase_cues, split_phrases
    ws = say("철수는 오늘 비행기를 타고 로스앤젤레스로 향하는 길이었다.")
    cues = build_phrase_cues([ws])
    texts = [" ".join(w["text"] for w in c["lines"][0]) for c in cues]
    assert texts == ["철수는 오늘", "비행기를 타고", "로스앤젤레스로 향하는", "길이었다"], texts
    # 부사·관형사·목적어·'수/것' 앞에서는 끊지 않는다
    ws = say("그래서 우리는 이 문제를 해결할 수 있는 방법을 찾아야 합니다.")
    texts = [" ".join(w["text"] for w in c["lines"][0]) for c in build_phrase_cues([ws])]
    joined = " / ".join(texts)
    assert "이 / 문제를" not in joined and "해결할 / 수" not in joined and "방법을 / 찾아야" not in joined, joined
    # 실제 쉼(0.6초)은 강한 경계
    items = [{"text": w.text, "raw": w.text, "start": w.start, "end": w.end} for w in say("좋은 디자인은", 0.7, "설명이 필요 없다")]
    chunks = split_phrases(items)
    assert [len(c) for c in chunks] == [2, 3] or [" ".join(x["text"] for x in c) for c in chunks][0] == "좋은 디자인은"


def test_captions_keep_adjective_modifiers_with_their_noun():
    """'결국 좋은 / 디자인은' 처럼 형용사 관형어와 명사를 떼지 않는다(실전 검토 시트에서 발견)."""
    from studio.text.captions import build_phrase_cues
    texts = [" ".join(w["text"] for w in c["lines"][0])
             for c in build_phrase_cues([say("결국 좋은 디자인은 좋은 질문에서 시작합니다.")])]
    assert texts == ["결국 좋은 디자인은", "좋은 질문에서", "시작합니다"], texts
    texts = [" ".join(w["text"] for w in c["lines"][0])
             for c in build_phrase_cues([say("가장 중요한 것은 문제를 정의하는 일입니다.")])]
    assert texts[0] == "가장 중요한 것은", texts


def test_consecutive_sentences_with_the_same_opening_are_both_kept():
    """설명하는 대본은 같은 주어로 연달아 시작한다 — 앞 문장이 끝까지 말해졌으면(…다/요) 되풀이가 아니다.
    예전엔 꼬리의 마지막 어절(문장 끝)을 보지 않아 앞 문장이 통째로 지워졌다(채널 주인: '내용을 잘라먹었다')."""
    cases = [
        ("디자인 씽킹은 공감에서 시작합니다.", "디자인 씽킹은 다섯 단계로 이루어집니다."),
        ("좋은 디자인은 단순합니다.", "좋은 디자인은 정직합니다."),
        ("이 원칙은 건축에서 시작됐습니다.", "이 원칙은 지금도 유효합니다."),
        ("좋은 디자인은 사용자를 배려합니다.", "좋은 디자인은 사용자를 설득합니다."),
    ]
    for a, b in cases:
        for strict in (False, True):
            kept, rem = clean_words(say(a, 0.6, b), strict=strict)
            assert text(kept) == f"{a} {b}", (a, b, strict, rem)


def test_same_ending_a_few_sentences_later_is_not_a_repeat():
    """다음 시도의 그 문장 안에서만 끝말을 찾는다 — 몇 문장 뒤의 같은 끝말('시작합니다')을 반복으로 보지 않는다."""
    kept, _ = clean_words(say("디자인 씽킹은 공감에서 시작합니다.", 0.6, "디자인 씽킹은 다섯 단계입니다.", 0.5,
                              "모든 단계는 질문에서 시작합니다."))
    assert text(kept).startswith("디자인 씽킹은 공감에서 시작합니다.")


def test_whole_sentence_said_twice_and_cut_off_attempts_still_go():
    kept, _ = clean_words(say("좋은 디자인은 단순합니다.", 1.0, "좋은 디자인은 단순합니다."))
    assert text(kept) == "좋은 디자인은 단순합니다."
    # 위스퍼는 끊긴 시도에도 마침표를 찍는다 — 맺는 어미가 아니면 끊긴 시도
    kept, _ = clean_words(say("오늘은 좋은 디자인이 어디서 시작하는지.", 1.2,
                              "오늘은 좋은 디자인이 어디에서 시작하는지 이야기해 볼게요."))
    assert text(kept) == "오늘은 좋은 디자인이 어디에서 시작하는지 이야기해 볼게요."


def test_stutter_restart_with_fragment_is_cut():
    """2026-10-04 채널 주인: '안녕하세요 쵀 / 안녕하세요 최은준입니다' — 절어서 다시 시작했는데 앞 토막이 안 잘리고 둘 다 나갔다.
    같은 말 한 어절 + 끊긴 토막(다음에 올 낱말의 앞부분) + 다시 시작이면 앞 시도를 지운다. 쉼이 없어도 같은 말이 4글자 이상이면."""
    kept, rem = clean_words(say("안녕하세요 쵀", 0.6, "안녕하세요 최은준입니다."))
    assert text(kept) == "안녕하세요 최은준입니다." and rem[0].reason.startswith("되풀이")
    kept, _ = clean_words(say("안녕하세요 쵀 안녕하세요 최은준입니다."))
    assert text(kept) == "안녕하세요 최은준입니다."
    kept, _ = clean_words(say("오늘은 안녕하세요 쵀", 0.5, "안녕하세요 최은준입니다. 반갑습니다."))
    assert text(kept) == "오늘은 안녕하세요 최은준입니다. 반갑습니다."
    # 다시 말한 그 낱말의 앞부분('디자' → '디자인은')도 토막이다
    kept, _ = clean_words(say("디자인은 디자", 0.4, "디자인은 문제를 정의하는 일입니다."))
    assert text(kept) == "디자인은 문제를 정의하는 일입니다."


def test_stutter_rule_does_not_eat_a_clause_before_a_comma_pause():
    """'배울 때, 디자인을 …' — 쉼표 뒤 같은 낱말로 이어 가는 말은 토막이 아니다(앞 낱말이 다음 말의 앞부분이 아님)."""
    kept, _ = clean_words(say("우리가 디자인을 배울 때", 0.5, "디자인을 공부하는 이유는 하나입니다."))
    assert text(kept) == "우리가 디자인을 배울 때 디자인을 공부하는 이유는 하나입니다."
    kept, _ = clean_words(say("네", 0.4, "네 맞습니다."))
    assert text(kept) == "네 네 맞습니다."
