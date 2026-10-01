"""대본 충실 보증: 대본 문장이 편집본에서 빠지면(테이크 오인·편집 감독 drop·단어 정리·편집 검사) 원본에서 되살린다."""
from __future__ import annotations

from types import SimpleNamespace

from studio.models import Span, Utterance, Word
from studio.pipeline import Pipeline
from studio.text import fidelity
from studio.text.script import parse_script

SCRIPT = ("디자인은 문제를 정의하는 일에서 시작합니다. 첫째, 색은 사람의 감정을 움직입니다. "
          "둘째, 형태는 기능을 따라야 합니다. 셋째, 여백은 시선이 쉴 자리를 만듭니다. 그래서 좋은 디자인은 질문에서 시작합니다.")


def _words(text: str, t0: float, step: float = 0.32) -> list[Word]:
    out, t = [], t0
    for w in text.split():
        out.append(Word(w, t, t + step * 0.85, 0.95))
        t += step
    return out


def _utt(i: int, text: str, t0: float, status: str = "keep") -> Utterance:
    ws = _words(text, t0)
    return Utterance(i, ws[0].start, ws[-1].end, text, text, ws, status=status)


SAID = [  # (문장, 시작 시각) — 녹음 순서
    ("디자인은 문제를 정의하는 일에서 시작합니다", 0.0),
    ("첫째 색은 사람의 감정을 움직입니다", 4.0),
    ("둘째 형태는 기능을 따라야 합니다", 8.0),
    ("셋째 여백은 시선이 쉴 자리를 만듭니다", 12.0),
    ("그래서 좋은 디자인은 질문에서 시작합니다", 16.0),
]


def test_coverage_finds_the_missing_sentence():
    sents = fidelity.sentences_of(parse_script(SCRIPT).sentences)
    assert len(sents) == 5
    edit = [w for i, (t, t0) in enumerate(SAID) if i != 2 for w in _words(t, t0)]
    cov = fidelity.coverage(sents, edit)
    assert cov[2] < fidelity.COVERED and all(c >= 0.85 for i, c in enumerate(cov) if i != 2), cov


def test_restore_prefers_the_take_between_neighbors_then_the_later_take():
    sents = fidelity.sentences_of(parse_script(SCRIPT).sentences)
    early = _words("둘째 형태는 기능을 따라야", 7.0)               # 끊긴 첫 시도
    late = _words("둘째 형태는 기능을 따라야 합니다", 9.0)          # 고쳐 말한 테이크
    far = _words("둘째 형태는 기능을 따라야 합니다", 40.0)          # 한참 뒤 같은 말(순서가 안 맞음)
    r = fidelity.find_restore(sents[2], [early, late, far], in_edit=lambda w: False, after=7.5, before=12.0)
    assert r is not None and r.start == late[0].start and r.ratio >= 0.9


def _fake(utts, keeps_words=None):
    logs: list[str] = []
    me = SimpleNamespace(spec=SimpleNamespace(script=SCRIPT), utts=utts, align_report={}, log=logs.append,
                         info=SimpleNamespace(duration=60.0), fps=30.0,
                         smap=SimpleNamespace(clamp_keeps=lambda k, fps: k))
    me._script_sents = lambda: fidelity.sentences_of(parse_script(SCRIPT).sentences)
    raw = [w for u in utts for w in u.words] if keeps_words is None else keeps_words
    me._raw_words = lambda: raw
    me._caption_restored = lambda rs: Pipeline._caption_restored(me, rs)
    return me, logs


def test_wrongly_dropped_utterances_are_restored_before_cutting():
    """병렬 문장('둘째…')을 앞 문장의 다시 말하기로 오인(retake)했거나 편집 감독이 뺀(director_drop) 대본 문장."""
    utts = [_utt(i, t, t0) for i, (t, t0) in enumerate(SAID)]
    utts[2].status, utts[2].note = "retake", "#1 가 더 또렷함"
    utts[3].status = "director_drop"
    me, logs = _fake(utts)
    Pipeline._ensure_script_utts(me)
    assert utts[2].kept and utts[3].kept
    assert len(me.align_report["fidelity_restored"]) == 2 and any("대본 충실" in m for m in logs)


def test_final_edit_puts_back_script_words_removed_by_later_cuts():
    """단어 정리·편집 검사가 대본 문장을 지운 편집본(keep 구간에 셋째 문장이 없음) → 원본에서 다시 넣고 자막도 보이게."""
    utts = [_utt(i, t, t0) for i, (t, t0) in enumerate(SAID)]
    raw = [w for u in utts for w in u.words]
    utts[3].words = utts[3].words[:1]                      # 단어 정리가 대부분을 지웠다고 치자
    keeps = [Span(0.0, 11.0), Span(16.0, 19.0)]            # 12~15초(셋째 문장)가 빠진 편집본
    me, logs = _fake(utts, raw)
    out = Pipeline._ensure_script_keeps(me, keeps)
    assert any(k.start <= 12.3 and k.end >= 14.0 for k in out), out
    assert me.fidelity["restored"] and not me.fidelity["missing"]
    assert len(utts[3].words) == len(SAID[3][0].split())   # 자막용 단어도 되돌아왔다


def test_sentence_never_recorded_is_reported_not_invented():
    utts = [_utt(i, t, t0) for i, (t, t0) in enumerate(SAID) if i != 4]
    me, _ = _fake(utts)
    keeps = [Span(0.0, 15.0)]
    out = Pipeline._ensure_script_keeps(me, keeps)
    assert out == keeps
    assert me.fidelity["missing"] == ["그래서 좋은 디자인은 질문에서 시작합니다."]


def test_badly_recognized_sentence_already_in_edit_is_not_duplicated():
    """인식이 틀려 들리는 비율이 낮을 뿐 편집본에 있는 문장 — 같은 말의 다른 테이크를 또 넣지 않는다."""
    sents = fidelity.sentences_of(parse_script(SCRIPT).sentences)
    kept = _words("둘째 형대는 기능을 따라 아 합니다", 8.0)              # 인식 오차
    other = _words("둘째 형태는 기능을 따라야 합니다", 30.0)              # 버린 다른 테이크
    in_edit = lambda w: w in kept   # noqa: E731
    r = fidelity.find_restore(sents[2], [kept, other], in_edit=in_edit, after=7.0, before=12.0)
    assert r is None


def test_aligner_plus_guarantee_keep_every_parallel_sentence():
    """나열하는 병렬 문장(첫째·둘째·셋째)과 한 문장 다시 말하기가 섞인 녹음 — 정렬 뒤 대본 문장이 모두 남는다."""
    from studio.text.align import ScriptAligner
    said = SAID[:2] + [("둘째 형태는 기능을", 7.0), ("둘째 형태는 기능을 따라야 합니다", 8.5)] + \
        [(t, t0 + 2.0) for t, t0 in SAID[3:]]
    utts = [_utt(i, t, t0) for i, (t, t0) in enumerate(said)]
    utts, _, rep = ScriptAligner(parse_script(SCRIPT)).run(utts)
    me, _ = _fake(utts)
    Pipeline._ensure_script_utts(me)
    sents = fidelity.sentences_of(parse_script(SCRIPT).sentences)
    cov = fidelity.coverage(sents, [w for u in sorted(utts, key=lambda u: u.start) if u.kept for w in u.words])
    assert all(c >= fidelity.COVERED for c in cov), cov
    assert not utts[2].kept                                   # 끊긴 첫 시도는 그대로 빠진다


def test_speech_whisper_skipped_is_put_back_between_its_neighbors():
    """위스퍼가 받아 적지 못한 문장(단어 없음)이라도 앞뒤 대본 문장 사이 원본에 그만한 말소리가 있으면 넣고 자막은 대본으로."""
    utts = [_utt(i, t, t0) for i, (t, t0) in enumerate(SAID) if i != 3]   # 셋째 문장(12~14.5초)은 인식 결과에 없음
    me, logs = _fake(utts)
    me.vad = [(0.0, 2.4), (4.0, 6.1), (8.0, 10.2), (12.0, 14.4), (16.0, 18.2)]
    out = Pipeline._ensure_script_keeps(me, [Span(0.0, 11.0), Span(15.9, 19.0)])
    assert any(k.start <= 12.0 and k.end >= 14.3 for k in out), out
    assert "셋째, 여백은 시선이 쉴 자리를 만듭니다." in me.fidelity["restored"] and not me.fidelity["missing"]
    assert any(w.text == "여백은" for u in utts if u.kept for w in u.words)       # 자막은 대본 문장


def test_speech_recognized_as_another_take_is_not_inserted():
    """그 자리 말소리를 인식기가 다른 문장(다음 문장의 다시 말하기)으로 받아 적었으면 넣지 않는다 — 같은 말이 두 번 나온다."""
    utts = [_utt(i, t, t0) for i, (t, t0) in enumerate(SAID) if i != 3]
    retake = _utt(9, "그래서 좋은 디자인은 질문에서", 12.0, status="retake")       # 12~14초: 다음 문장의 끊긴 시도
    me, _ = _fake(utts + [retake])
    me.vad = [(0.0, 2.4), (4.0, 6.1), (8.0, 10.2), (12.0, 14.4), (16.0, 18.2)]
    out = Pipeline._ensure_script_keeps(me, [Span(0.0, 11.0), Span(15.9, 19.0)])
    assert out == [Span(0.0, 11.0), Span(15.9, 19.0)]
    assert me.fidelity["missing"] == ["셋째, 여백은 시선이 쉴 자리를 만듭니다."]
