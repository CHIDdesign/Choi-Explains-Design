"""🫁 호흡 설계(studio/edit/breath.py) — 2026-10-04 채널 주인: "마디마디에 자연스러운 공백이 있어야 하는데 훅훅 넘어간다".
실측(6:25 롱폼): 말 사이 쉼 중앙값 0.15초 · 0.4초 넘는 쉼 8곳 — 이어 붙인 곳의 쉼이 경계와 상관없이 0.34초로 같았다."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.edit.breath import BREATHS, breathe, ends_sentence, join_kinds  # noqa: E402
from studio.models import Span, Utterance, Word  # noqa: E402


def utt(i, start, text, *, span=None, step=0.3):
    words, t = [], start
    for w in text.split():
        words.append(Word(w, round(t, 3), round(t + step - 0.02, 3), 0.9))
        t += step
    return Utterance(i, words[0].start, words[-1].end, text, text, words, script_span=span)


def speech_of(utts):
    return [(w.start, w.end) for u in utts for w in u.words]


def gap(keeps, utts, i):
    """keeps[i-1] 끝의 말소리 뒤 + keeps[i] 앞 말소리 전 — 들리는 쉼."""
    sp = speech_of(utts)
    a, b = keeps[i - 1], keeps[i]
    tail = a.end - max(e for s, e in sp if s < a.end and e > a.start)
    head = min(s for s, e in sp if s < b.end and e > b.start) - b.start
    return tail + head


def test_sentence_join_between_takes_gets_a_real_breath():
    # 1회차에서 문장 하나(0~1.5초), 그 뒤 리테이크(지운 말 2.4~3.6초), 다음 문장(5.0초~) — 이어 붙이면 0.34초였다
    u1 = utt(1, 0.0, "결과는 증명이고 과정은 실력입니다.", span=(0, 19))
    junk = utt(2, 2.4, "아 다시 할게요", span=None)
    junk.status = "retake"
    u3 = utt(3, 5.0, "그래서 저는 다시 이론을 펼쳤습니다.", span=(20, 39))
    keeps = [Span(0.0, u1.end + 0.22), Span(u3.start - 0.12, u3.end + 0.2)]
    utts = [u1, junk, u3]
    clean = "결과는 증명이고 과정은 실력입니다. 그래서 저는 다시 이론을 펼쳤습니다."
    kind = join_kinds(keeps, utts, clean=clean, sentence_spans=[(0, 18), (20, 39)])
    assert kind(1) == ("sentence", None)
    out, rep = breathe(keeps, speech=speech_of(utts), kind_of=kind, breath=BREATHS["calm"], media_duration=10.0)
    assert gap(out, utts, 1) >= BREATHS["calm"].sentence - 0.02
    # 지운 리테이크(2.4초~)로 넘어가지 않는다
    assert out[0].end <= junk.start - 0.05
    assert rep.joins[0].before < 0.4 and rep.joins[0].after >= 0.6


def test_paragraph_join_is_longer_than_sentence():
    u1 = utt(1, 0.0, "여기까지가 제 고백입니다.", span=(0, 14))
    u2 = utt(2, 6.0, "이제 연구를 보겠습니다.", span=(14, 27))     # 정렬 오차로 줄바꿈 위치에서 시작해도 문단
    clean = "여기까지가 제 고백입니다.\n이제 연구를 보겠습니다."
    keeps = [Span(0.0, u1.end + 0.22), Span(u2.start - 0.12, u2.end + 0.2)]
    kind = join_kinds(keeps, [u1, u2], clean=clean, sentence_spans=[(0, 14), (15, 27)])
    assert kind(1)[0] == "paragraph"
    out, _ = breathe(keeps, speech=speech_of([u1, u2]), kind_of=kind, breath=BREATHS["calm"], media_duration=10.0)
    assert gap(out, [u1, u2], 1) >= BREATHS["calm"].paragraph - 0.02


def test_inner_join_stays_short_and_no_overlap_when_adjacent_in_source():
    # 같은 문장 안의 조각(가운데 머뭇거림을 잘라 낸 곳): 문장 안 쉼만, 그리고 원본에서 이웃이면 두 구간이 겹치지 않는다
    u = utt(1, 0.0, "그때 저는 이 아이디어를 골랐습니다.")
    u.script_span = (0, 20)
    a = Span(0.0, 0.9 + 0.1)          # "그때 저는 이" 까지
    b = Span(1.1, u.end + 0.2)        # 나머지(0.9초 뒤 말소리)
    kind = join_kinds([a, b], [u], clean="그때 저는 이 아이디어를 골랐습니다.", sentence_spans=[(0, 20)])
    assert kind(1)[0] == "inner"
    out, _ = breathe([a, b], speech=speech_of([u]), kind_of=kind, breath=BREATHS["calm"], media_duration=5.0)
    assert out[0].end <= out[1].start + 1e-9
    assert gap(out, [u], 1) <= BREATHS["calm"].inner + 0.12


def test_no_silence_is_invented_when_speech_follows_immediately():
    # 원본에서 다음 말이 바로 붙어 있으면(무음 없음) 늘리지 않는다 — 영상·소리 싱크는 원본 무음으로만
    u1 = utt(1, 0.0, "첫 문장입니다.", span=(0, 7))
    other = utt(2, 0.62, "남기지 않는 말", span=None)
    other.status = "retake"
    u3 = utt(3, 3.0, "둘째 문장입니다.", span=(8, 16))
    other_end = other.end
    u3_prev_speech = [(2.95, 2.99)]               # 둘째 문장 바로 앞에도 말소리(숨이 아닌 소리)
    keeps = [Span(0.0, u1.end + 0.02), Span(u3.start - 0.02, u3.end + 0.2)]
    kind = join_kinds(keeps, [u1, other, u3], clean="첫 문장입니다. 둘째 문장입니다.", sentence_spans=[(0, 7), (8, 16)])
    out, rep = breathe(keeps, speech=speech_of([u1, other, u3]) + u3_prev_speech, kind_of=kind, breath=BREATHS["calm"],
                       media_duration=6.0)
    assert out[0].end <= other.start
    assert out[1].start == keeps[1].start           # 바로 앞이 말소리라 당기지 않는다
    assert other_end < out[1].start
    assert rep.joins[0].after < BREATHS["calm"].sentence           # 모자란 채로 둔다(지어내지 않음)


def test_explicit_pause_and_beat_after_peak():
    u1 = utt(1, 0.0, "남의 레퍼런스보다 무서운 건 내 첫 아이디어였습니다.", span=(0, 27))
    u2 = utt(2, 8.0, "그럼 무엇을 건너뛴 걸까요?", span=(28, 42))
    u3 = utt(3, 14.0, "의심하는 시간입니다.", span=(43, 53))
    clean = "남의 레퍼런스보다 무서운 건 내 첫 아이디어였습니다. 그럼 무엇을 건너뛴 걸까요? 의심하는 시간입니다."
    keeps = [Span(u.start - 0.12, u.end + 0.22) for u in (u1, u2, u3)]
    sents = [(0, 27), (28, 42), (43, 53)]
    kind = join_kinds(keeps, [u1, u2, u3], clean=clean, sentence_spans=sents, explicit_after={2: 1.5}, beat_after=[1])
    assert kind(1) == ("beat", None)
    assert kind(2) == ("beat", 1.5)
    out, rep = breathe(keeps, speech=speech_of([u1, u2, u3]), kind_of=kind, breath=BREATHS["calm"], media_duration=20.0)
    assert gap(out, [u1, u2, u3], 1) >= BREATHS["calm"].beat - 0.02
    assert gap(out, [u1, u2, u3], 2) >= 1.48
    assert rep.joins[1].explicit


def test_budget_limits_total_added_time_for_shorts():
    us = [utt(i, i * 4.0, f"문장 {i} 입니다.", span=(i * 10, i * 10 + 8)) for i in range(6)]
    clean = " ".join(u.text for u in us)
    keeps = [Span(u.start - 0.04, u.end + 0.08) for u in us]
    sents = [(i * 10, i * 10 + 8) for i in range(6)]
    kind = join_kinds(keeps, us, clean=clean, sentence_spans=sents)
    total0 = sum(k.dur for k in keeps)
    out, rep = breathe(keeps, speech=speech_of(us), kind_of=kind, breath=BREATHS["shorts_calm"], media_duration=30.0,
                       budget=0.5)
    assert sum(k.dur for k in out) - total0 <= 0.5 + 1e-6
    out2, _ = breathe(keeps, speech=speech_of(us), kind_of=kind, breath=BREATHS["shorts_calm"], media_duration=30.0)
    assert all(gap(out2, us, i) >= BREATHS["shorts_calm"].sentence - 0.02 for i in range(1, 6))


def test_does_not_cross_source_boundary_or_other_keeps():
    # 원본 두 파일(가상 타임라인: 0~10 · 12~22). A 는 첫 파일 끝, B 는 둘째 파일 — 늘려도 파일 경계를 넘지 않는다
    u1 = utt(1, 9.0, "끝 문장입니다.", span=(0, 7))
    u2 = utt(2, 12.3, "새 문장입니다.", span=(8, 15))
    keeps = [Span(8.9, u1.end + 0.1), Span(12.2, u2.end + 0.1)]
    kind = join_kinds(keeps, [u1, u2], clean="끝 문장입니다. 새 문장입니다.", sentence_spans=[(0, 7), (8, 15)])
    out, _ = breathe(keeps, speech=speech_of([u1, u2]), kind_of=kind, breath=BREATHS["calm"], media_duration=22.0,
                     bounds=[(0.0, 10.0), (12.0, 22.0)])
    assert out[0].end <= 10.0 and out[1].start >= 12.0


def test_ends_sentence():
    assert ends_sentence("실력입니다.") and ends_sentence("그랬어요") and ends_sentence("걸까요?")
    assert not ends_sentence("그래서 저는") and not ends_sentence("첫 아이디어를")


def test_pipeline_breathe_on_two_reads_reassembled_in_script_order():
    """실제 경로(Pipeline._breathe): 대본을 두 번 읽은 원본에서 대목마다 회차를 골라 대본 순서로 이어 붙인 keep — 모든 문장 경계가
    이어 붙인 곳이다. 문장 사이 쉼이 0.34초(앞 0.12 + 뒤 0.22)에서 0.6초 이상으로 늘고, 지운 테이크로는 넘어가지 않는다."""
    from types import SimpleNamespace

    from studio.edit.cuts import quantize
    from studio.pipeline import Pipeline
    from studio.text.align import ScriptAligner
    from studio.text.script import parse_script

    lines = ["디자인 이론은 작업에서 자주 사라집니다", "학교에서 배운 원칙이 현장에서는 잊힙니다",
             "첫 아이디어에 쉽게 고착되기 때문입니다", "레퍼런스를 먼저 보면 생각이 좁아집니다"]
    script = ". ".join(lines) + "."

    def read(t0):
        out = []
        for k, text in enumerate(lines):
            s0 = t0 + k * 5.0
            ws = [Word(w, s0 + i * 0.3, s0 + i * 0.3 + 0.25, 0.95) for i, w in enumerate(text.split())]
            out.append(Utterance(0, ws[0].start, ws[-1].end, text, text, ws))
        return out
    utts = read(0.0) + read(600.0)
    for i, u in enumerate(utts):
        u.id = i
    utts, _, rep = ScriptAligner(parse_script(script)).run(utts)
    kept = sorted((u for u in utts if u.kept), key=lambda u: u.start)
    keeps = quantize([Span(u.start - 0.12, u.end + 0.22) for u in kept], 30, 1300.0)
    me = SimpleNamespace(info=SimpleNamespace(duration=1300.0), spec=SimpleNamespace(script=script, pace="calm"),
                         plan_long={"pauses": [], "peak_seg": -1, "payoff_seg": -1}, utts=utts,
                         vad=[(w.start, w.end) for u in utts for w in u.words], smap=SimpleNamespace(single=True),
                         fps=30, _raw_words=lambda: [], _removed_spans=lambda: [])
    out, rep2 = Pipeline._breathe(me, keeps, "calm", [])
    assert len(out) == len(keeps) and len(rep2.joins) == len(keeps) - 1
    assert all(j.before < 0.4 for j in rep2.joins)
    assert all(j.after >= BREATHS["calm"].sentence - 0.05 for j in rep2.joins)
    # 다른 회차(지운 테이크)의 말소리로 넘어가지 않는다
    dropped = [w for u in utts if not u.kept for w in u.words]
    assert not any(k.start < w.end and w.start < k.end for k in out for w in dropped)
