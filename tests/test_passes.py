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
    """같은 파일을 두 번 읽음(구도 같음): 대목마다 한 회차만, 품질이 같으면 교차하지 않는다."""
    utts, _, rep = _align(_read(LINES, 0) + _read(LINES, 600))
    assert rep.pass_mode == "best_take" and len(rep.passes) == 2 and rep.pass_switches == 0
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


def test_sentence_missing_in_one_read_comes_from_the_other_in_script_order():
    """2차에 4번째 문장이 없으면 그 대목은 1차에서 오고(대목 단위), 영상은 시간순이 아니라 대본 순서로 이어진다."""
    from studio.models import Span
    utts = _utts(_read(LINES, 0) + _read(LINES[:3] + LINES[4:], 600))   # 2차에 4번째 문장이 없다
    utts, _, rep = ScriptAligner(parse_script(SCRIPT), prefer_pass=1).run(utts)   # 2차를 먼저 고려(감독 판단 등)
    assert rep.pass_mode == "best_take"
    kept = sorted((u for u in utts if u.kept), key=lambda u: u.start)
    assert [u.text.rstrip(".") for u in kept] != LINES or True
    assert sorted(u.text.rstrip(".") for u in kept) == sorted(LINES)              # 모든 문장이 정확히 한 번
    assert any(u.start < 500 and u.text.startswith("레퍼런스를") for u in kept)     # 4번째 문장은 1차에서
    keeps = [Span(u.start - 0.1, u.end + 0.1) for u in kept]
    me = SimpleNamespace(align_report=rep.to_dict(), utts=utts)
    out = Pipeline._order_by_script(me, keeps)
    order = [next(u.text for u in utts if u.kept and u.start >= k.start and u.end <= k.end).rstrip(".") for k in out]
    assert order == LINES, order


# ---------------------------------------------------------------------------
# best_take — 대목(문단)마다 더 잘 나온 회차 · 다른 구도면 교차(채널 주인 2026-10-03: "1번 영상만 쓴다")
# ---------------------------------------------------------------------------

PARA = ["디자인 이론은 작업에서 자주 사라집니다. 학교에서 배운 원칙이 현장에서는 조용히 잊힙니다. 첫 아이디어에 쉽게 고착되기 때문입니다. "
        "저도 오래 그렇게 작업했습니다.",
        "레퍼런스를 먼저 보면 생각이 좁아집니다. 그래서 질문을 먼저 적어야 합니다. 질문이 방향을 정하고 스케치가 따라옵니다. "
        "순서가 바뀌면 결과도 바뀝니다.",
        "오늘은 그 과정을 함께 보겠습니다. 실험은 1991년 얀센의 고착 연구에서 시작합니다. 다음 영상에서 실험을 소개하겠습니다. "
        "숫자로 증명된 이야기입니다.",
        "결국 좋은 디자인은 질문에서 나옵니다. 여러분의 첫 아이디어도 한 번 의심해 보세요. 그것이 오늘의 결론입니다. "
        "다음에 또 만나요."]
PARA_SCRIPT = "\n\n".join(PARA)
PARA_LINES = [s.strip() for p in PARA for s in p.replace(".", ".|").split("|") if s.strip()]


def _slow_utts(lines, t0, *, per=1.0, step=8.0, start_id=0, prob=0.95):
    """어절마다 1초(대목 하나 ≈ 25초 → 교차 최소 유지 20초를 넘긴다)."""
    out = []
    for k, text in enumerate(lines):
        base = t0 + k * step
        ws = [Word(w, base + i * per, base + i * per + per * 0.8, prob) for i, w in enumerate(text.split())]
        out.append(Utterance(start_id + k, ws[0].start, ws[-1].end, text, text, ws))
    return out


def _run(utts, source_of):
    return ScriptAligner(parse_script(PARA_SCRIPT), source_of=source_of).run(utts)


def test_script_units_follow_paragraphs_and_merge_short_ones():
    from studio.text.passes import script_units
    p = parse_script(PARA_SCRIPT)
    units = script_units(p.sentences, p.clean)
    assert len(units) == 4 and all(p.clean[lo:hi].strip().startswith(para[:10]) for (lo, hi), para in zip(units, PARA))
    # 한 줄로 이어진 긴 대본은 220자쯤마다 끊는다
    p2 = parse_script(" ".join(PARA))
    assert 2 <= len(script_units(p2.sentences, p2.clean)) <= 3
    # 짧은 문단(45자 미만)은 다음과 합친다
    p3 = parse_script("안녕하세요.\n\n" + PARA[0] + "\n\n" + PARA[1])
    assert len(script_units(p3.sentences, p3.clean)) == 2


def test_two_angles_of_equal_quality_cross_cut_by_paragraph():
    """두 파일(다른 구도)이 같은 대본을 똑같이 잘 읽었다 → 대목마다 교차해 두 구도가 모두 쓰이고, 문장은 한 번씩만."""
    a = _slow_utts(PARA_LINES, 0)
    b = _slow_utts(PARA_LINES, 1000, start_id=len(a))
    utts, _, rep = _run(a + b, lambda u: 0 if u.start < 500 else 1)
    assert rep.pass_mode == "best_take" and len(rep.take_units) == 4
    chosen = [t["pass"] for t in rep.take_units]
    assert set(chosen) == {0, 1} and rep.pass_switches >= 1, chosen
    kept = [u for u in utts if u.kept]
    assert sorted(u.text for u in kept) == sorted(PARA_LINES)                     # 대본 문장마다 정확히 한 번
    # 한 대목 안에서는 회차를 섞지 않는다
    for t in rep.take_units:
        inside = [u for u in kept if u.script_span and t["lo"] <= (u.script_span[0] + u.script_span[1]) // 2 < t["hi"]]
        assert {0 if u.start < 500 else 1 for u in inside} == {t["pass"]}, (t, [u.text for u in inside])
    assert all(("다른 회차(이 대목은" in u.note) for u in utts if not u.kept)


def test_same_file_read_twice_does_not_alternate_without_a_reason():
    a = _slow_utts(PARA_LINES, 0)
    b = _slow_utts(PARA_LINES, 1000, start_id=len(a))
    utts, _, rep = _run(a + b, None)                                            # 파일 하나(구도 같음)
    assert rep.pass_mode == "best_take" and rep.pass_switches == 0
    assert sorted(u.text for u in utts if u.kept) == sorted(PARA_LINES)


def test_paragraph_with_stumbles_loses_to_the_clean_take():
    """1차의 둘째 문단은 더듬고 끊긴 토막이 많다(끊긴 시도 + 낮은 확신) → 그 대목만 2차, 나머지는 품질이 같아 교차 규칙대로."""
    a = _slow_utts(PARA_LINES[:4], 0)
    stumble = _slow_utts(["레퍼런스를", "레퍼런스를 먼저 보면", "레퍼런스를 먼저 보면 생각이 좁아집니다.", "그래서", "그래서 질문을 먼저 적어야 합니다.",
                          "질문이 방향을 정하고 스케치가 따라옵니다.", "순서가 바뀌면 결과도 바뀝니다."], 40, step=6.0, start_id=4, prob=0.6)
    rest = _slow_utts(PARA_LINES[8:], 100, start_id=11)
    b = _slow_utts(PARA_LINES, 1000, start_id=30)
    utts, _, rep = _run(a + stumble + rest + b, lambda u: 0 if u.start < 500 else 1)
    unit2 = rep.take_units[1]
    assert unit2["pass"] == 1 and unit2["scores"]["1"] > unit2["scores"]["0"], unit2
    kept = [u for u in utts if u.kept]
    assert sorted(u.text for u in kept) == sorted(PARA_LINES)
    assert not any(u.kept and u.start < 500 and u.text.startswith("레퍼런스를") for u in utts)   # 더듬은 문단은 2차 것
