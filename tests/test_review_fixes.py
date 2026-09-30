"""코드 점검에서 찾은 문제들의 회귀 테스트(대본 정렬 · 컷 경계 · 자막 · 그래픽 시간)."""
from studio.director.plan import TimedGraphic, resolve_overlaps, word_edit_time
from studio.edit.cuts import PACES, _snap_to_vad, build_keeps, keeps_for_segments
from studio.models import Span, TimeMap, Utterance, Word
from studio.render.props import emphasis_keys
from studio.text.align import ScriptAligner, build_utterances
from studio.text.script import parse_script
from studio.text.takes import clean_words


def U(i, words, status="keep"):
    ws = [Word(t, s, e) for t, s, e in words]
    return Utterance(i, ws[0].start, ws[-1].end, " ".join(w.text for w in ws), "", ws, status=status)


def _spoken(lines, gap=0.8):
    words, t = [], 0.0
    for line in lines:
        for w in line.split():
            words.append(Word(w, t, t + 0.35))
            t += 0.4
        t += gap
    return words


def test_script_with_same_sentence_twice_keeps_both():
    """대본 처음과 끝에 같은 문장 — 뒤의 것을 앞 문장의 다시 말하기로 보고 첫 문장을 지우던 것."""
    script = ("형태는 기능을 따른다.\n이 말은 루이스 설리번이 남긴 말입니다. 건축에서 시작된 이 원칙은 제품 디자인으로 "
              "이어졌습니다.\n그리고 오늘날 화면 디자인에서도 여전히 유효합니다. 버튼은 눌릴 것처럼 보여야 합니다.\n"
              "형태는 기능을 따른다.")
    lines = ["형태는 기능을 따른다.", "이 말은 루이스 설리번이 남긴 말입니다.", "건축에서 시작된 이 원칙은 제품 디자인으로 이어졌습니다.",
             "그리고 오늘날 화면 디자인에서도 여전히 유효합니다.", "버튼은 눌릴 것처럼 보여야 합니다.", "형태는 기능을 따른다."]
    utts, _, rep = ScriptAligner(parse_script(script)).run(build_utterances(_spoken(lines)))
    assert [u.status for u in utts] == ["keep"] * 6 and not rep.missing_sentences
    # 진짜 다시 말하기(방금 한 문장을 다시)는 여전히 하나만
    lines2 = lines[:2] + ["이 말은 루이스 설리번이 남긴 말입니다."] + lines[2:]
    utts2, _, _ = ScriptAligner(parse_script(script)).run(build_utterances(_spoken(lines2)))
    assert sum(u.status == "retake" for u in utts2) == 1


def test_short_keep_does_not_bleed_into_unselected_neighbour():
    u0 = U(0, [("색은", 10.0, 10.5), ("빛입니다.", 10.55, 11.3)])
    u1 = U(1, [("그래서", 11.45, 11.9), ("우리는", 11.95, 12.4)])
    vad = [(9.9, 12.5)]          # 두 문장 사이 쉼이 짧아 VAD 한 구간
    k = keeps_for_segments([u0, u1], [0], pace=PACES["shorts"], vad=vad, media_duration=100, fps=30)
    assert k[-1].end <= 11.45 + 1 / 60 + 1e-6      # 다음 문장 첫 단어로 넘어가지 않음(프레임 반올림 반 프레임까지)


def test_dropped_utterance_not_revived_by_padding():
    a = U(0, [("원칙입니다.", 1.0, 2.0)])
    b = U(1, [("다시.", 2.15, 2.55)], status="meta")
    c = U(2, [("근접성은", 2.7, 3.3), ("가깝다는", 3.35, 4.0)])
    k = build_keeps([a, b, c], pace=PACES["calm"], vad=[], media_duration=100, fps=30)
    assert not any(s.start <= 2.2 and s.end >= 2.5 for s in k)


def test_end_inside_speech_is_not_snapped_back():
    vad = [(5.0, 5.8), (5.93, 6.6)]
    assert _snap_to_vad(6.05, vad, [r[0] for r in vad], is_start=False) == 6.05
    u = U(0, [("색채는", 5.0, 5.75), ("중요합니다.", 5.85, 6.05)])     # Whisper 가 마지막 단어 끝을 일찍 찍음
    for p in ("calm", "shorts"):
        assert build_keeps([u], pace=PACES[p], vad=vad, media_duration=100, fps=30)[-1].end >= 6.55


def test_meta_patterns_keep_real_content():
    ws = [Word("엔지니어와", 0, 0.5), Word("협업합니다.", 0.55, 1.2), Word("처음부터", 2.0, 2.5), Word("완벽할", 2.55, 2.9),
          Word("순", 2.95, 3.0), Word("없어요.", 3.05, 3.5), Word("Kerning이죠.", 4.3, 5.0),
          Word("아", 6.0, 6.2), Word("NG", 6.3, 6.6), Word("다시", 7.5, 7.8), Word("할게요", 7.85, 8.3)]
    utts, _, _ = ScriptAligner(parse_script("")).run(build_utterances(ws))
    by = {u.text: u.status for u in utts}
    assert by["엔지니어와 협업합니다."] == "keep" and by["처음부터 완벽할 순 없어요."] == "keep"
    assert by["Kerning이죠."] == "keep"
    assert any(s == "meta" for t, s in by.items() if "NG" in t or "다시" in t)


def test_word_straddling_trimmed_pause_stays_in_captions():
    u = U(0, [("디자인은", 9.4, 10.0), ("그래서", 10.0, 11.5), ("중요합니다.", 11.55, 12.3)])
    keeps = build_keeps([u], pace=PACES["calm"], vad=[(9.3, 10.0), (11.15, 12.4)], media_duration=100, fps=30)
    assert [w.text for w in TimeMap(keeps).map_words(u.words)] == ["디자인은", "그래서", "중요합니다."]


def test_retake_search_does_not_wrap_to_last_word():
    ws = [Word("색채", 0.0, 0.4), Word("이론의", 0.45, 0.9), Word("기초를", 0.95, 1.4),
          Word("자", 2.0, 2.2), Word("색채", 2.3, 2.7), Word("이론의", 2.75, 3.2), Word("기초를", 3.25, 3.7),
          Word("알아봅니다.", 3.75, 4.4), Word("오늘도", 5.0, 5.4), Word("감사합니다.", 5.5, 6.0), Word("자", 7.0, 7.2)]
    kept, _ = clean_words(ws)
    assert kept[-1].text == "자" and kept[-1].start == 7.0


def test_emphasis_prefers_whole_word_over_one_syllable():
    u = U(1, [("이", 1.0, 1.2), ("이론은", 1.3, 1.8), ("중요합니다.", 1.9, 2.6)])
    tm = TimeMap([Span(0, 3)])
    assert word_edit_time(u, "이론", tm) == 1.3
    assert list(emphasis_keys([{"seg": 1, "word": "이론", "kind": "highlight"}], [u], tm)) == [(1.3, "이론은")]


def test_pushed_graphic_does_not_run_past_speech():
    a = TimedGraphic("g1", "process", "fullscreen", 95.0, 99.7, {}, 9, "tag")
    b = TimedGraphic("g2", "process", "fullscreen", 96.0, 99.0, {}, 8, "tag")
    out = resolve_overlaps([a, b], total=100.0)
    assert all(g.end <= 99.7 + 1e-6 for g in out)
