"""대본 읽기 회차(studio/text/passes.py) — 같은 대본을 두 번 찍은 원본이 둘 다 들어가던 10/1 테스트의 P0 버그."""
from __future__ import annotations

from types import SimpleNamespace

from studio.models import Utterance, Word
from studio.pipeline import Pipeline, covered_elsewhere
from studio.text.align import ScriptAligner
from studio.text.passes import detect_passes
from studio.text.script import parse_script

LINES = ["디자인 이론은 작업에서 자주 사라집니다", "학교에서 배운 원칙이 현장에서는 잊힙니다",
         "첫 아이디어에 쉽게 고착되기 때문입니다", "레퍼런스를 먼저 보면 생각이 좁아집니다",
         "그래서 질문을 먼저 적어야 합니다", "질문이 방향을 정하고 스케치가 따라옵니다",
         "오늘은 그 과정을 함께 보겠습니다", "다음 영상에서 실험을 소개하겠습니다"]
SCRIPT = ". ".join(LINES) + "."


def _utts(seq: list[tuple[str, float]], start_id: int = 0) -> list[Utterance]:
    out = []
    for k, (text, t0) in enumerate(seq):
        ws = [Word(w, t0 + i * 0.3, t0 + i * 0.3 + 0.25, 0.95) for i, w in enumerate(text.split())]
        out.append(Utterance(start_id + k, ws[0].start, ws[-1].end, text, text, ws))
    return out


def _read(lines, t0, step=5.0):
    return [(t, t0 + i * step) for i, t in enumerate(lines)]


def _align(seq, **kw):
    utts = _utts(seq)
    return ScriptAligner(parse_script(SCRIPT), **kw).run(utts)


def test_single_read_is_one_pass_and_nothing_changes():
    utts, _, rep = _align(_read(LINES, 0))
    assert rep.passes is None and rep.pass_mode == "single" and all(u.kept for u in utts)


def test_two_full_reads_keep_one_main_take():
    utts, _, rep = _align(_read(LINES, 0) + _read(LINES, 600))
    assert rep.pass_mode == "best_pass" and len(rep.passes) == 2
    kept = [u for u in utts if u.kept]
    assert len(kept) == len(LINES)                                         # 두 배가 아니다
    assert all(u.note.startswith("다른 회차") for u in utts if not u.kept)
    texts = [u.text for u in sorted(kept, key=lambda u: u.start)]
    assert len(set(texts)) == len(texts)                                   # 같은 대본 문장이 두 번 나오지 않는다


def test_two_reads_with_a_break_in_the_second_still_cover_everything():
    second = _read(LINES[:5], 600) + _read(LINES[5:], 700)                 # 2차를 중간에 끊고 이어 찍음
    utts, _, rep = _align(_read(LINES, 0) + second)
    assert len(rep.passes) == 2
    kept = [u for u in utts if u.kept]
    assert len(kept) == len(LINES)


def test_partial_reshoot_is_not_a_new_pass():
    """다른 파일에서 두 문장만 다시 찍음(부분 다시 찍기): 회차는 하나, 다시 찍은 문장은 거리와 상관없이 하나씩만."""
    utts, _, rep = _align(_read(LINES, 0) + _read(LINES[2:4], 300), source_of=lambda u: 0 if u.start < 200 else 1)
    assert rep.passes is None or len(rep.passes) == 1
    assert sum(1 for u in utts if u.kept) == len(LINES)
    # 같은 파일 안에서 한참(2분 넘게) 뒤에 같은 말을 다시 하면 의도적 반복으로 본다(지금 규칙 유지)
    utts, _, _ = _align(_read(LINES, 0) + _read(LINES[2:3], 300))
    assert sum(1 for u in utts if u.kept) == len(LINES) + 1


def test_same_sentence_twice_in_the_script_is_not_a_second_pass():
    script = SCRIPT + " " + LINES[0] + "."                               # 대본 끝에 첫 문장을 일부러 한 번 더
    utts = _utts(_read(LINES + [LINES[0]], 0))
    utts, _, rep = ScriptAligner(parse_script(script)).run(utts)
    assert rep.passes is None or len(rep.passes) == 1
    assert sum(1 for u in utts if u.kept) == len(LINES) + 1


def test_file_change_is_a_strong_hint():
    seq = _read(LINES, 0) + _read(LINES, 600)
    utts = _utts(seq)
    for u in utts:
        u.script_span = (0, 1)
    utts, _, _ = ScriptAligner(parse_script(SCRIPT)).run(_utts(seq))
    passes = detect_passes(utts, len(parse_script(SCRIPT).clean), source_of=lambda u: 0 if u.start < 500 else 1)
    assert len(passes) == 2 and passes[0].source == 0 and passes[1].source == 1


def test_director_may_drop_a_whole_read_when_the_other_read_covers_it():
    """'대본 문장은 빼지 않는다'는 '정확히 한 번'이다 — 다른 회차가 덮으면 감독의 삭제를 받아들인다."""
    utts = _utts(_read(LINES, 0) + _read(LINES, 600))
    ScriptAligner(parse_script(SCRIPT))._match_all(utts)
    first = {u.id for u in utts if u.start < 500}
    assert all(covered_elsewhere(u, utts, first) for u in utts if u.id in first)
    second = {u.id for u in utts if u.start >= 500}
    assert not any(covered_elsewhere(u, utts, first | second) for u in utts if u.id in first)   # 둘 다 지우면 거절


def test_sentence_restored_from_the_other_read_plays_in_script_order():
    """주 테이크(2차)에서 빠진 문장을 1차에서 되살리면 시간순(영상 맨 앞)이 아니라 대본 자리에 넣는다."""
    from studio.models import Span
    utts = _utts(_read(LINES, 0) + _read(LINES[:3] + LINES[4:], 600))   # 2차에 4번째 문장이 없다
    utts, _, rep = ScriptAligner(parse_script(SCRIPT), prefer_pass=1).run(utts)   # 2차를 주 테이크로(감독 판단 등)
    assert rep.pass_mode == "best_pass" and rep.main_pass == 1
    restored = [u for u in utts if u.kept and u.start < 500]
    assert len(restored) == 1 and restored[0].text.startswith("레퍼런스를")       # 1차에서 그 문장만 보강
    keeps = [Span(u.start - 0.1, u.end + 0.1) for u in sorted(utts, key=lambda u: u.start) if u.kept]
    me = SimpleNamespace(align_report=rep.to_dict(), utts=utts)
    out = Pipeline._order_by_script(me, keeps)
    order = [next(u.text for u in utts if u.kept and u.start >= k.start and u.end <= k.end).rstrip(".") for k in out]
    assert order == LINES, order
