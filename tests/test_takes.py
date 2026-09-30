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
