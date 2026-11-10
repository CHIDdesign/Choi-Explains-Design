"""디자인 v5.1 검토에서 나온 결함 — 낱말 착지·도장·오림 스택·슈퍼·배지·숏폼·자막 상한."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from studio import gate  # noqa: E402
from studio.agents import schemas as S  # noqa: E402
from studio.assets import graphics as evg  # noqa: E402
from studio.director.plan import (TimedGraphic, argument_badges, cap_cards, clean_overlays, normalize_long,  # noqa: E402
                                  resolve_overlaps, time_graphics)
from studio.edit.grammar import HIGH_PITCH_MAX, directed_sfx  # noqa: E402
from studio.models import Span, TimeMap, Utterance, Word  # noqa: E402
from studio.motion.card import clean_card  # noqa: E402
from studio.pipeline import short_retype  # noqa: E402
from studio.stock.research import StockResearcher, request_key  # noqa: E402
from studio.text.captions import build_phrase_cues  # noqa: E402


def _utt(uid, t, text, per=0.45):
    words = [Word(w, t + k * per, t + k * per + per * 0.9, 0.95) for k, w in enumerate(text.split())]
    return Utterance(id=uid, start=t, end=words[-1].end, text=text, asr_text=text, words=words, status="keep")


def _tg(gid, tpl, layout, a, b, prio=6, **data):
    return TimedGraphic(gid, tpl, layout, a, b, data, priority=prio, source="director")


def test_badge_never_overlaps_a_hold_that_starts_after_it():
    assert argument_badges([{"seg": 1, "tag": "이유 1"}], {1: (100.0, 105.0)}, [(101.0, 115.0)], 500.0) == []
    [b] = argument_badges([{"seg": 1, "tag": "이유 1"}], {1: (100.0, 105.0)}, [(101.0, 109.0)], 500.0)
    assert b.start == 109.3


def test_director_schema_has_the_argument_tag():
    assert "argument_tag" in S.BRIEF["properties"]["beats"]["items"]["required"]


def test_stock_key_is_bound_to_the_marks():
    st = {"kind": "photo", "query_en": "bridge"}
    assert request_key({**st, "annotations": [{"kind": "circle", "target": "왼쪽 기둥"}]}) != request_key(st)
    assert request_key({**st, "annotations": [{"kind": "circle", "target": "왼쪽 기둥"}]}) != request_key(
        {**st, "annotations": [{"kind": "circle", "target": "오른쪽 탑"}]})


def test_procured_stock_is_not_searched_again(tmp_path):
    public = tmp_path / "public"
    (public / "broll").mkdir(parents=True)
    (public / "broll" / "a.jpg").write_bytes(b"x")

    class Hub:
        names = ["x"]

        def search(self, *_a, **_k):
            raise AssertionError("이미 고른 그림을 다시 찾았다")
    g = {"template": "broll", "src": "broll/a.jpg", "kind": "photo", "stock": {"kind": "photo", "query_en": "q"},
         "overlays": [{"kind": "circle", "box": [0.1, 0.1, 0.2, 0.2]}]}
    lists = [[g]]
    StockResearcher(Hub(), ff=None, work=tmp_path, public=public).run(lists)
    assert lists == [[g]] and g["src"] == "broll/a.jpg" and g["overlays"]


def test_card_pushed_by_overlaps_still_lands_on_its_word():
    utts = [_utt(1, 0.0, "먼저 하나의 카드가 길게 나오고 있고 그다음 둘째가 온다"), _utt(2, 5.0, "새로운 낱말이 여기서 들린다 그리고 길게 이어지는 말이 끝에 정말로")]
    tm = TimeMap([Span(0.0, 40.0)])
    html = '<div class="card"><div class="root"><span data-anim="fade-in" data-at-word="정말로">가</span></div></div>'
    a = {"template": "card", "layout": "fullscreen", "start_seg": 1, "end_seg": 1, "start_word": "먼저", "title": "a",
         "card": clean_card({"html": html.replace("정말로", "둘째가")}, layout="fullscreen", card_id="c1")}
    b = {"template": "card", "layout": "fullscreen", "start_seg": 2, "end_seg": 2, "start_word": "새로운", "title": "b",
         "card": clean_card({"html": html}, layout="fullscreen", card_id="c2")}
    out = time_graphics([a, b], utts, tm, total=40.0, min_start=0.0)
    late = next(g for g in out if g.id == "g1")
    spoken = next(w.start for w in utts[1].words if w.text == "정말로")
    at = float(re.search(r'data-anim-at="([^"]+)"', late.data["card"]["html"]).group(1))
    assert late.start > 4.6 and abs(late.start + at + 0.5 + 0.2 - spoken) <= 0.05


def test_stamp_sits_on_the_material_or_not_at_all():
    both = resolve_overlaps([_tg("e", "evidence", "fullscreen", 5.0, 12.0, 8), _tg("s", "stamp", "overlay", 6.0, 8.5, 5)])
    assert [g.id for g in both] == ["e", "s"] and both[1].start == 6.0
    tail = resolve_overlaps([_tg("e", "evidence", "fullscreen", 5.0, 9.0, 8), _tg("s", "stamp", "overlay", 7.0, 12.0, 5)])
    assert tail[1].end == 9.0
    assert [g.id for g in resolve_overlaps([_tg("s", "stamp", "overlay", 7.0, 9.5, 5)])] == []          # 얼굴 위에는 찍지 않는다
    assert [g.id for g in resolve_overlaps([_tg("k", "keyword", "overlay", 5.0, 9.0), _tg("s", "stamp", "overlay", 6.0, 8.5, 5)])] == ["k"]


def _photo(src, **kw):
    return {"src": src, "kind": "photo", "w": 800, "h": 600, "credit": "사진: A", "tier": "A", **kw}


def test_researcher_stack_becomes_one_cutout_stack_on_the_spoken_names():
    items = [{"start_seg": i, "end_seg": i, "start_word": w, "need": "entity", "treatment": "stack", "label": w, "claim": "c", "subject": {"name_ko": w}}
             for i, w in ((1, "바실리"), (2, "체스카"))]
    outs = [{"i": i, "assets": [_photo(f"images/{i}.jpg")], "archive": None, "stock": None} for i in range(2)]
    graphics, _ = evg.to_graphics(items, outs)
    assert [g["template"] for g in graphics] == ["cutout_stack"] and len(graphics[0]["cutouts"]) == 2
    utts = [_utt(1, 0.0, "먼저 바실리 의자가 있고"), _utt(2, 3.0, "다음은 체스카 의자입니다")]
    plan = normalize_long({"graphics": graphics}, utts, [])
    [g] = time_graphics(plan["graphics"], utts, TimeMap([Span(0.0, 20.0)]), total=20.0, min_start=0.0)
    cuts = g.data["cutouts"]
    assert all("seg" not in c and "word" not in c for c in cuts)
    assert abs(g.start + cuts[1]["at"] + 0.33 + 0.2 - utts[1].words[1].start) <= 0.05
    # 앱이 채우는 템플릿 — 그림 없이 고르면 빠진다
    assert normalize_long({"graphics": [{"template": "cutout_stack", "start_seg": 1}]}, utts, [])["graphics"] == []
    rows = evg.ledger_rows([{"template": "cutout_stack", "start": 0, "end": 1, "data": {"cutouts": cuts}}], "롱폼")
    assert [r["자산"] for r in rows] == ["images/0.jpg", "images/1.jpg"]


def test_person_super_is_a_selectable_template():
    utts = [_utt(1, 0.0, "르코르뷔지에는 이렇게 말했습니다 정말")]
    plan = normalize_long({"graphics": [{"template": "lower_third", "start_seg": 1, "title": "르코르뷔지에", "subtitle": "건축가"}]}, utts, [])
    [g] = time_graphics(plan["graphics"], utts, TimeMap([Span(0.0, 10.0)]), total=10.0, min_start=0.0)
    assert g.data["slot"] == "super" and g.data["title"] == "르코르뷔지에" and g.data["subtitle"] == "건축가"


def test_highlight_mark_needs_a_box_from_vision():
    assert clean_overlays([{"kind": "highlight", "box": [0.1, 0.2, 0.6, 0.03], "at_word": "주권은"}])[0]["kind"] == "highlight"
    assert clean_overlays([{"kind": "highlight"}]) == []


def test_free_cards_are_capped_keeping_the_signature():
    gs = [{"template": "card", "start_seg": i} for i in range(8)]
    gs[7]["signature"] = True
    cap_cards(gs, 300.0)
    assert len(gs) == 3 and any(g.get("signature") for g in gs)
    long_gs = [{"template": "card", "start_seg": i} for i in range(9)]
    cap_cards(long_gs, 900.0)
    assert len(long_gs) == 6


def test_shorts_keep_whole_documents_and_focus_and_drop_logos():
    doc = short_retype({"template": "evidence", "assets": [{"src": "d.jpg", "kind": "document", "w": 800, "h": 1100}], "title": "t"})
    assert doc["fit"] == "contain" and (doc["w"], doc["h"]) == (800, 1100)
    photo = short_retype({"template": "evidence", "assets": [{"src": "p.jpg", "kind": "photo", "focus": [0.6, 0.2, 0.2, 0.4]}], "title": "t"})
    assert photo["focus"] == [0.7, 0.4] and "fit" not in photo
    assert short_retype({"template": "evidence", "assets": [{"src": "l.png", "kind": "logo"}], "title": "t"}) is None
    assert short_retype({"template": "photo", "logo": True, "image": "l.png"}) is None


def test_fixed_slots_only_except_the_credit():
    r = gate.p1_phone_px(gate.slot_px())
    assert r.ok and list(r.measured["below"]) == ["출처"]


def test_caption_tail_merge_respects_the_hard_limits():
    long_word = "가" * 24
    ws = [Word(long_word, 0.0, 2.0, 0.9), Word("다.", 2.1, 2.3, 0.9)]
    cues = build_phrase_cues([ws], max_chars=24, max_dur=4.0, max_words=8)
    assert all(sum(len(x["text"]) for x in c["lines"][0]) <= 24 for c in cues)
    slow = [Word("느리게", 0.0, 3.9, 0.9), Word("다.", 3.95, 4.5, 0.9)]
    assert all(c["end"] - c["start"] <= 4.0 for c in build_phrase_cues([slow], max_chars=24, max_dur=4.0, max_words=8))


def test_high_pitched_sfx_are_capped_for_the_whole_video():
    gs = [{"template": "quote", "layout": "overlay", "start": 20.0 + i * 30.0, "end": 24.0 + i * 30.0} for i in range(6)]
    assert sum(e["category"] == "bell_soft" for e in directed_sfx(gs, [], total=300.0, auto=True)) == HIGH_PITCH_MAX
