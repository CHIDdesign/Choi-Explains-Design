"""🚦 품질 게이트(studio/gate.py) — 10/1 테스트 영상의 수치를 그대로 옮긴 합성 픽스처로, 그때 동시에 실패했어야 할
A1·A3·A5·A6·A7·A8·A9 가 실제로 실패하는지, B3·B4·B5 가 화면 글자 누수('스케치북 넘기기'·'brand'·'motion')를 잡는지 본다.
(docs/upgrade/08_품질_게이트.md 2~3절, 09 작업지시서 WP2)"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from studio import gate  # noqa: E402
from studio.agents.studio import merge_plan  # noqa: E402
from studio.director.plan import _clean_graphic  # noqa: E402
from studio.models import Utterance, Word  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# 대본 95문장(한 문장 20글자 남짓) — 6분 20초 분량
SENTS = [f"디자인 원칙 {i}번째 문장은 이렇게 끝납니다" for i in range(95)]
SCRIPT = "\n".join(SENTS)


def _span(i: int) -> tuple[int, int]:
    a = sum(len(s) + 1 for s in SENTS[:i])
    return a, a + len(SENTS[i])


def _utt(uid: int, i: int, t: float, *, dur: float = 4.0, status: str = "keep", take: float = 0.5,
         text: str = "") -> Utterance:
    text = text or SENTS[i]
    words = [Word(w, t + k * dur / 6, t + (k + 1) * dur / 6, 0.9) for k, w in enumerate(text.split())]
    u = Utterance(id=uid, start=t, end=t + dur, text=text, asr_text=text, words=words, status=status)
    u.script_span = _span(i) if i >= 0 else None
    u.score = 92.0 if i >= 0 else 0.0
    u.take_score = take
    return u


def _double_pass() -> list[Utterance]:
    """10/1: 같은 대본을 두 번 읽은 원본이 둘 다 남아 12분 44초(대본 분량의 약 2배)."""
    utts = [_utt(k, k, 4.0 * k) for k in range(95)]
    utts += [_utt(100 + k, k, 400.0 + 4.0 * k, take=0.7) for k in range(95)]
    return utts


# ---------------------------------------------------------------------------
# 게이트 A — 구조
# ---------------------------------------------------------------------------

def test_a1_and_a3_fail_when_the_whole_script_is_in_twice():
    utts = _double_pass()
    a1 = gate.a1_length(utts, SCRIPT, 764.0)
    assert not a1.ok and a1.blocking and a1.measured["script_ratio"] > 1.9
    assert a1.measured["expected_sec"] < 764.0 / 1.8                          # 대본 한 번 = 절반쯤
    a3 = gate.a3_duplicates(utts, SCRIPT)
    assert not a3.ok and a3.blocking and a3.measured["pairs"] == 95
    # 한 회차만 남기면 둘 다 통과
    one = [u for u in utts if u.id >= 100]
    assert gate.a1_length(one, SCRIPT, 383.0).ok
    assert gate.a3_duplicates(one, SCRIPT).ok


def test_a1_ignores_adlibs_when_the_script_is_only_an_outline():
    """대본이 개요뿐이고 말이 훨씬 많은 녹음(대본 커버리지 낮음)은 애드리브 길이로 멈추지 않는다."""
    utts = [_utt(k, k, 4.0 * k) for k in range(95)]
    utts += [_utt(200 + k, -1, 500.0 + 4.0 * k, text="여기서 잠깐 제 경험을 말씀드리면 그때 정말 힘들었어요") for k in range(120)]
    assert not gate.a1_length(utts, SCRIPT, 900.0, coverage=0.95).ok
    assert gate.a1_length(utts, SCRIPT, 900.0, coverage=0.5).ok


def test_a3_short_spans_and_partial_overlap_are_not_duplicates():
    u1, u2 = _utt(1, 3, 10.0), _utt(2, 4, 14.0)
    assert gate.a3_duplicates([u1, u2], SCRIPT).ok
    # 앞 문장 끝 몇 글자만 겹침(A+B 뒤 B 다시 말하기를 잘라 남긴 것) — 60% 미만
    a, b = _span(3)
    u3 = _utt(3, 4, 20.0)
    u3.script_span = (b - 4, _span(4)[1])
    assert gate.a3_duplicates([u1, u3], SCRIPT).ok


def test_a5_greeting_in_the_middle_fails_unless_the_script_puts_it_there():
    utts = [_utt(k, k, 4.0 * k) for k in range(95)]
    hello = _utt(500, 0, 190.0, text="안녕하세요 디자인 원칙 0번째 문장은 이렇게 끝납니다")
    starts = {u.id: u.start for u in utts + [hello]}
    r = gate.a5_greetings(utts + [hello], starts, 383.0, len(SCRIPT))
    assert not r.ok and r.level == "repair" and r.measured["misplaced"][0]["id"] == 500
    # 대본에서도 가운데(인용 등)에 있는 인사는 그 자리가 맞다
    mid = _utt(501, 50, 190.0, text="그때 그가 안녕하세요 하고 말했습니다")
    starts[501] = 190.0
    assert gate.a5_greetings(utts + [mid], starts, 383.0, len(SCRIPT)).ok
    # 끝인사는 마지막 10% 안이면 정상
    bye = _utt(502, 94, 370.0, text="시청해 주셔서 감사합니다")
    starts[502] = 370.0
    assert gate.a5_greetings(utts + [bye], starts, 383.0, len(SCRIPT)).ok


def _g(t0: float, t1: float, template: str = "keyword", layout: str = "overlay") -> dict:
    return {"id": f"g{int(t0)}", "template": template, "layout": layout, "start": t0, "end": t1, "data": {}}


def test_screen_gates_fail_like_the_1001_video():
    """10/1: 앞 6분 37초가 그래픽 없는 맨얼굴(그래픽은 뒤 절반에만), 타이틀 06:48, 얼굴 비율 95%."""
    total = 764.0
    gs = [_g(408.0, 411.4, "title", "fullscreen")]
    gs += [_g(420.0 + 20 * k, 424.0 + 20 * k) for k in range(17)]
    a6 = gate.a6_distribution(gs, total)
    assert not a6.ok and a6.blocking and a6.measured["empty"] == [0, 1, 2, 3, 4]
    a7 = gate.a7_face_run(gs, total)
    assert not a7.ok and a7.blocking and a7.measured["max_face_run"] >= 397
    a8 = gate.a8_face_ratio(0.953)
    assert not a8.ok and a8.level == "repair" and a8.repair == "fill_gaps"
    a9 = gate.a9_title(gs)
    assert not a9.ok and a9.blocking and a9.measured["title_at"] == 408.0


def test_screen_gates_pass_on_a_well_spread_edit():
    total = 383.0
    gs = [_g(5.0, 8.4, "title", "fullscreen")] + [_g(10.0 + 15 * k, 14.0 + 15 * k) for k in range(25)]
    gs += [_g(30.0 + 60 * k, 36.0 + 60 * k, "motion", "fullscreen") for k in range(6)]
    assert gate.a6_distribution(gs, total).ok
    assert gate.a7_face_run(gs, total).ok
    assert gate.a9_title(gs).ok
    assert 0.35 <= gate.face_ratio(gs, total) <= 1.0
    # 25~40초 맨얼굴은 block 이 아니라 repair
    r = gate.a7_face_run([_g(0, 4), _g(34, 38)], 60.0)
    assert not r.ok and r.level == "repair"


def test_a6_bins_scale_with_length_and_ignore_auto_cards():
    # 1분 영상 = 30초 칸 2개. 타이틀·챕터 카드·이름 자막은 내용 그래픽이 아니다
    r = gate.a6_distribution([_g(2, 5, "title", "fullscreen"), _g(35, 39)], 60.0)
    assert r.measured["bins"] == 2 and r.measured["empty"] == [0]
    # 콜아웃도 그래픽으로 센다
    assert gate.a6_distribution([_g(35, 39)], 60.0, callouts=[{"start": 10.0, "end": 13.0}]).ok


def test_fill_targets_move_out_of_holds_instead_of_vanishing():
    """2026-10-03 실제 작업: 빈 칸 05:04–05:42 의 가운데와 맨얼굴 04:47–05:58 안 18초 자리가 모두 홀드(04:47–05:03 · 05:12–05:26 ·
    05:36–05:46) 안이라 보충 카드가 하나도 안 들어가고 A7 block — 자리를 홀드 밖 가장 가까운 곳으로 옮긴다."""
    holds = [(287.0, 303.0), (312.0, 326.0), (336.0, 346.0)]
    out = gate.fill_targets([[304.0, 342.0]], [(287.0, 358.0)], holds)
    assert out and not any(x - 2.0 <= t <= y for t in out for x, y in holds)
    assert 329.0 in out and 306.0 in out and 351.0 in out          # 칸 가운데 323 → 홀드 끝 +3 · 297 → 306 · 351 은 그대로
    assert gate.fill_targets([], [(0.0, 20.0)], []) == []              # 25초 이하 맨얼굴은 자리 없음
    assert gate.fill_targets([[0.0, 10.0]], [], [(0.0, 10.0)]) == []   # 칸 전체가 홀드면 버림


# ---------------------------------------------------------------------------
# 게이트 B — 화면 글자 위생
# ---------------------------------------------------------------------------

def test_b3_b4_b5_catch_the_1001_label_leaks_and_scrub_fixes_them():
    plan = [
        {"template": "broll", "start_seg": 30, "title": "스케치북 넘기기", "subtitle": "video",
         "body": "지난 프로젝트를 다시 꺼내 보는 전환점",
         "stock": {"kind": "video", "query_en": "flipping sketchbook pages", "query_ko": "스케치북 넘기기",
                   "purpose": "지난 프로젝트를 다시 꺼내 보는 전환점", "must_show": ""}},
        {"template": "photo", "start_seg": 40, "title": "핀터레스트", "body": "brand", "subtitle": "Pinterest"},
        {"template": "list", "start_seg": 50, "title": "( motion )", "items": ["리서치", "S12–S15 다시", "스케치"]},
        {"template": "keyword", "start_seg": 60, "title": "card"},
        {"template": "definition", "start_seg": 70, "title": "공간 연출", "body": "Galaxy S23 처럼 빛을 다루는 일"},
    ]
    b3, b4, b5 = gate.b3_query_labels(plan), gate.b4_direction_notes(plan), gate.b5_internal_names(plan)
    assert not b3.ok and {x["text"] for x in b3.measured["labels"]} >= {"스케치북 넘기기", "video"}
    assert not b4.ok and any("전환점" in x["text"] for x in b4.measured["notes"])
    assert not b5.ok and b5.blocking
    texts = {x["text"] for x in b5.measured["names"]}
    assert {"brand", "( motion )", "S12–S15 다시", "card"} <= texts
    assert not any("Galaxy" in t or "연출" in t for t in texts)          # 제품명 S23·'공간 연출'은 내용이다
    fixed, keep = gate.scrub_labels(plan)
    assert fixed >= 6
    assert [g["template"] for g in keep] == ["broll", "photo", "list", "definition"]   # 제목이 내부 이름뿐인 키워드는 뺀다
    assert keep[0]["title"] == keep[0]["subtitle"] == keep[0]["body"] == ""
    assert keep[1]["title"] == "핀터레스트" and keep[1]["body"] == ""
    assert keep[2]["title"] == "" and keep[2]["items"] == ["리서치", "스케치"]
    assert keep[3]["title"] == "공간 연출"
    assert gate.b3_query_labels(keep).ok and gate.b4_direction_notes(keep).ok and gate.b5_internal_names(keep).ok


def test_b5_reads_props_data_cards_and_motion_text():
    props = [{"id": "g3", "template": "card", "start": 1, "end": 5,
              "data": {"card": {"html": '<div class="card"><p class="k">keyword</p><h1>여백은 숨</h1></div>'}}},
             {"id": "g4", "template": "motion", "start": 6, "end": 9,
              "data": {"spec": {"elements": [{"type": "text", "text": "g12"}, {"type": "text", "text": "근접성"}]}}},
             {"id": "g5", "template": "keyword", "start": 10, "end": 12, "data": {"title": "근접", "label": "chapter"}}]
    r = gate.b5_internal_names(props)
    assert not r.ok and {x["text"] for x in r.measured["names"]} == {"keyword", "g12", "chapter"}
    fixed, keep = gate.scrub_labels(props)
    assert fixed == 3 and len(keep) == 3
    assert "keyword" not in keep[0]["data"]["card"]["html"] and "여백은 숨" in keep[0]["data"]["card"]["html"]
    assert [e["text"] for e in keep[1]["data"]["spec"]["elements"]] == ["근접성"]
    assert keep[2]["data"]["label"] == ""
    assert gate.b5_internal_names(keep).ok


def test_merge_plan_never_puts_query_purpose_or_kind_on_screen():
    """P0-2: 스톡의 query_ko·purpose, 사진의 kind 는 화면 글자(title/subtitle/body)가 아니다. caption 만 라벨이 된다."""
    raw, _ = merge_plan({"stock": {
        "requests": [{"start_seg": 2, "end_seg": 2, "start_word": "", "kind": "video", "query_en": "flipping sketchbook",
                      "query_ko": "스케치북 넘기기", "layout": "pip", "purpose": "지난 작업을 꺼내 보는 전환점",
                      "must_show": "", "caption": ""},
                     {"start_seg": 3, "end_seg": 3, "start_word": "", "kind": "photo", "query_en": "mood board",
                      "query_ko": "무드보드", "layout": "pip", "purpose": "참고", "must_show": "", "caption": "영감은 쌓인다"}],
        "photos": [{"start_seg": 4, "start_word": "", "name_ko": "핀터레스트", "name_en": "Pinterest", "kind": "brand",
                    "layout": "pip", "reason": ""}]}})
    gs = raw["graphics"]
    b1, b2 = [g for g in gs if g["template"] == "broll"]
    ph = next(g for g in gs if g["template"] == "photo")
    assert b1["title"] == b1["body"] == b1["subtitle"] == "" and b1["stock"]["query_ko"] == "스케치북 넘기기"
    assert b2["title"] == "영감은 쌓인다" and b2["body"] == ""
    assert ph["body"] == "" and ph["entity"] == "brand"
    for g in gs:
        assert gate.b3_query_labels([g]).ok and gate.b4_direction_notes([g]).ok and gate.b5_internal_names([g]).ok
    # 단일 디렉터·숏폼 PD 모양(title=검색어, subtitle=video, body=메모)도 정리에서 화면 글자가 빠진다
    old = {"template": "broll", "layout": "fullscreen", "start_seg": 2, "end_seg": 2, "start_word": "",
           "title": "노트북 컴퓨터", "subtitle": "video", "body": "작업하는 장면", "image": "designer working on laptop"}
    c = _clean_graphic(old, {2})
    assert c and c["title"] == "" and c["subtitle"] == "" and c["body"] == ""
    assert c["stock"]["query_ko"] == "노트북 컴퓨터" and c["stock"]["purpose"] == "작업하는 장면"


def test_renderer_template_labels_are_never_internal_names():
    """surfaces.ts TEMPLATE_LABEL — 내부 이름은 빈 문자열(쓰는 곳이 라벨을 그리지 않는다)."""
    src = (ROOT / "renderer" / "src" / "design" / "surfaces.ts").read_text(encoding="utf-8")
    body = src[src.index("export const TEMPLATE_LABEL"):]
    body = body[:body.index("};")]
    labels = dict(re.findall(r"(\w+):\s*'([^']*)'", body))
    assert labels and all(not gate._internal(v) for v in labels.values() if v), labels
    for k in ("chapter", "keyword", "motion", "card", "broll", "title"):
        assert labels[k] == "", k
    board = (ROOT / "renderer" / "src" / "components" / "longform" / "Board.tsx").read_text(encoding="utf-8")
    assert "] || g.template" not in board            # 라벨이 비면 내부 이름으로 돌아가지 않는다


# ---------------------------------------------------------------------------
# 결과 정리
# ---------------------------------------------------------------------------

def test_merge_demote_combine_and_report(tmp_path):
    first = [gate.a3_duplicates(_double_pass(), SCRIPT), gate.a8_face_ratio(0.95)]
    again = [gate.a3_duplicates([u for u in _double_pass() if u.id >= 100], SCRIPT), gate.a8_face_ratio(0.9)]
    res = gate.merge(first, again)
    assert res[0].ok and res[0].repaired and not res[1].ok
    gate.demote(res)
    assert res[1].level == "warn" and not gate.blocking(res)
    # 롱폼 통과 + 숏폼 실패 → 실패
    long_ok = gate.b5_internal_names([{"template": "keyword", "title": "근접"}])
    short_bad = gate.b5_internal_names([{"template": "keyword", "title": "motion"}])
    comb = gate.combine([long_ok, short_bad])
    assert len(comb) == 1 and not comb[0].ok
    md = gate.report_section(res)
    assert md.startswith("## 🚦 품질 게이트") and "검토 필요" in md and "통과(수리함)" in md
    gate.write(tmp_path / "gate.json", res)
    data = json.loads((tmp_path / "gate.json").read_text(encoding="utf-8"))
    assert data["ok"] is True and len(data["results"]) == 2
    err = gate.GateBlocked([gate.a9_title([_g(408, 411, "title", "fullscreen")])], "화면 구조")
    assert str(err).startswith("품질 게이트") and "A9_title" in str(err)


# ---------------------------------------------------------------------------
# 파이프라인 연결(수리 → 재검 → 멈춤)
# ---------------------------------------------------------------------------

def _pipe(tmp_path, utts):
    from types import SimpleNamespace

    import studio.pipeline as pl
    from studio.models import Span, TimeMap
    p = object.__new__(pl.Pipeline)
    p.spec = SimpleNamespace(script=SCRIPT)
    p.settings = SimpleNamespace(glossary={})
    p.utts = utts
    p.smap = SimpleNamespace(groups=[0], group_at=lambda t: 0)
    p.align_report = {"script_coverage": 1.0}
    p.plan_long = {"graphics": [], "emphasis": [], "moments": []}
    p.gate_results, p.force_render = [], False
    p.work = p.out = p.dir = tmp_path
    p.logs = []
    p.log = p.logs.append

    def make_edit():
        p.timemap = TimeMap([Span(u.start, u.end) for u in p.utts if u.kept])
    p._make_edit = make_edit
    make_edit()
    return p


def test_pipeline_cut_gate_drops_the_weaker_pass_and_recuts(tmp_path):
    p = _pipe(tmp_path, _double_pass())
    assert p.timemap.duration > 700
    p._gate_cut()
    assert not any(u.kept for u in p.utts if u.id < 100)          # 테이크 점수 0.5(1차) 를 뺐다
    assert all(u.kept for u in p.utts if u.id >= 100)
    assert p.timemap.duration < 400
    data = json.loads((tmp_path / "gate.json").read_text(encoding="utf-8"))
    by = {r["id"]: r for r in data["results"]}
    assert data["ok"] and by["A3_duplicates"]["repaired"] and by["A1_length"]["repaired"]


def test_pipeline_gate_blocks_and_explains_unless_forced(tmp_path):
    import pytest
    p = _pipe(tmp_path, [_utt(k, k, 4.0 * k) for k in range(95)])
    bad = [gate.a9_title([_g(408, 411, "title", "fullscreen")])]
    with pytest.raises(gate.GateBlocked) as e:
        p._gate_record(bad, "화면 구조")
    assert "A9_title" in str(e.value)
    stop = (tmp_path / "품질게이트_중단.md").read_text(encoding="utf-8")
    assert "--force-render" in stop and "A9_title" in stop
    p.force_render = True
    p._gate_record([gate.a9_title([_g(408, 411, "title", "fullscreen")])], "화면 구조")   # 멈추지 않는다
    assert json.loads((tmp_path / "gate.json").read_text(encoding="utf-8"))["forced"] is True


def test_pipeline_fills_face_only_stretches_with_sentence_keywords(tmp_path):
    from types import SimpleNamespace
    utts = [_utt(k, k, 4.0 * k) for k in range(95)]
    p = _pipe(tmp_path, utts)
    p.plan_long["emphasis"] = [{"seg": 30, "word": "원칙은", "kind": "highlight"}]
    total = p.timemap.duration
    lp = {"graphics": [_g(5.0, 8.4, "title", "fullscreen")]}
    ed = SimpleNamespace(callouts=[], stats={})
    added = p._fill_gaps(lp, ed)
    gs = p.plan_long["graphics"]
    assert added == len(gs) >= 10 and all(g["template"] == "keyword" and g["layout"] == "overlay" for g in gs)
    assert all(g["title"] and not gate._internal(g["title"]) for g in gs)
    # 강조어 '원칙'(2자 한 낱말)은 카드가 아니다 → 문장의 명사 구절 '디자인 원칙'
    assert any(g["start_seg"] == 30 and g["title"] == "디자인 원칙" for g in gs) or all(g["start_seg"] != 30 for g in gs)
    assert len({g["start_seg"] for g in gs}) == len(gs)             # 같은 문장에 두 번 넣지 않는다
    # 채운 자리로 다시 재면 맨얼굴 25초 이하·빈 칸 없음(카드 4초)
    from studio.director.plan import seg_edit_times
    seg_t = seg_edit_times(utts, p.timemap)
    timed = lp["graphics"] + [_g(seg_t[g["start_seg"]][0], seg_t[g["start_seg"]][0] + 4.0) for g in gs]
    assert gate.a6_distribution(timed, total).ok and gate.a7_face_run(timed, total).ok


# ---------------------------------------------------------------------------
# 리듬 게이트 A11~A17 — 10/1 후반부('모든 것이 중간': 빠른 묶음 0 · 사슬 10 · p90/p10 3.1 · 홀드 침범 · 단계 지연)
# ---------------------------------------------------------------------------

def _seq(gid, t0, t1, tpl="keyword", seq="", items=None, hl=-1, source="director"):
    d = {"items": items or []}
    if seq:
        d["seq_id"] = seq
    if hl >= 0:
        d["highlight"] = hl
    return {"id": gid, "template": tpl, "layout": "overlay", "start": t0, "end": t1, "data": d, "source": source,
            "priority": 5}


def test_rhythm_gates_fail_on_20261001_like_fixture():
    total = 383.0
    # 6초 간격으로 4~6초짜리 그래픽이 고르게 — 그중 10개는 0.5초 간격 사슬
    gs = [_seq(f"g{i}", 10.0 + 6.0 * i, 10.0 + 6.0 * i + 5.5) for i in range(10)]
    gs += [_seq(f"h{i}", 100.0 + 9.0 * i, 100.0 + 9.0 * i + 4.0 + (i % 3)) for i in range(20)]
    # 같은 도식을 강조만 바꿔 셋(단계마다 그래픽)
    dd = ["발견", "정의", "개발", "전달"]
    gs += [_seq("d0", 300.0, 303.5, "double_diamond", items=dd, hl=0), _seq("d1", 304.0, 307.5, "double_diamond",
                                                                          items=dd, hl=1),
           _seq("d2", 308.0, 311.5, "double_diamond", items=dd, hl=2)]
    a11 = gate.a11_fast_runs(gs, total)
    assert not a11.ok and a11.measured["sequences"] == 0
    a12 = gate.a12_chain(gs)
    assert not a12.ok and a12.measured["longest"] == 10 and a12.repair == "trim_chain"
    a13 = gate.a13_duration_spread(gs)
    assert not a13.ok and a13.measured["ratio"] < 4
    a14 = gate.a14_hold_guard(gs + [_seq("r1", 192.0, 197.0, "recap")], [(190.0, 205.0)])
    assert not a14.ok and a14.blocking
    a15 = gate.a15_step_sync(gs)
    assert not a15.ok and a15.measured["unmerged"] == [["d0", "d1", "d2"]] and a15.repair == "merge_steps"
    # 마지막 챕터(303초~)는 6초마다 그래픽 — 얼굴로 머무는 자리가 없다(10/1 챕터 3: 73초에 최장 5.6초)
    dense = gs + [_seq(f"k{i}", 312.0 + 6.0 * i, 312.0 + 6.0 * i + 5.0) for i in range(12)]
    chapters = [{"start": 0.0}, {"start": 230.0}, {"start": 303.0}]
    a16 = gate.a16_hold_presence(dense, chapters, total)
    assert not a16.ok and a16.measured["chapters_without_hold"][0]["chapter"] == 3


def test_rhythm_gates_pass_with_sequences_and_holds():
    total = 383.0
    # 증거 쌓기(1.8초 간격 4장) + 단발 그래픽 + 긴 얼굴 구간 + 단계 그래픽 하나(stepAt)
    gs = [_seq(f"q{i}", 40.0 + 1.8 * i, 40.0 + 1.8 * (i + 1), "photo", seq="q1") for i in range(4)]
    gs += [_seq("s1", 60.0, 66.0), _seq("s2", 80.0, 95.0, "process"), _seq("s3", 130.0, 133.0),
           _seq("s4", 200.0, 214.0, "motion"), _seq("s5", 260.0, 262.5), _seq("s6", 330.0, 340.0, "list")]
    gs.append({"id": "w1", "template": "double_diamond", "layout": "split", "start": 150.0, "end": 160.0,
               "data": {"items": ["a", "b", "c", "d"], "stepAt": [{"t": 0.5, "index": 0}, {"t": 4.0, "index": 1}]},
               "source": "director", "priority": 5})
    assert gate.a11_fast_runs(gs, total).ok
    assert gate.a12_chain(gs).ok
    assert gate.a13_duration_spread(gs).ok
    assert gate.a14_hold_guard(gs, [(100.0, 125.0)]).ok
    assert gate.a15_step_sync(gs).ok
    assert gate.a16_hold_presence(gs, [{"start": 0.0}, {"start": 230.0}], total).ok
    # 대본 태그 그래픽은 홀드 안이어도 명령(홀드가 그 앞까지 줄어든다)
    assert gate.a14_hold_guard([_seq("t", 110.0, 115.0, source="tag")], [(100.0, 125.0)]).ok


# ---------------------------------------------------------------------------
# 게이트 E — 타임라인 검수(docs/upgrade/05b)
# ---------------------------------------------------------------------------

def _tl(scores, findings=()):
    return {"thesis_read": "논지", "summary": "",
            "scores": [{"criterion": c, "evidence": ["00:01 x"], "score": v} for c, v in scores.items()],
            "findings": list(findings)}


def test_blocking_finding_marks_needs_review():
    """10/1 납품본: 가중 1.30 + duplicate_take(high, blocking) → 검토 필요."""
    tl = _tl({"follow": 1, "argument": 2, "rhythm": 1, "evidence": 1, "hierarchy": 2, "distinct": 1},
             [{"start": "00:12", "end": "06:48", "kind": "duplicate_take", "severity": "high", "target": "",
               "action": "escalate_edit", "blocking": True, "direction": "1차 테이크가 통째로 남음"}])
    r = gate.gate_e(tl)
    assert not r.ok and r.measured["verdict"] == "needs_review" and r.measured["weighted"] == pytest.approx(1.3)
    assert "검토 필요" in r.message
    md = gate.report_section([r])                                    # 리포트 첫 절에 기준별 점수·발견
    assert "타임라인 검수" in md and "follow 1" in md and "duplicate_take → escalate_edit" in md
    good = gate.gate_e(_tl({c: 4 for c in gate.RUBRIC_WEIGHT}))
    assert good.ok and good.measured["verdict"] == "pass"
    meh = gate.gate_e(_tl({**{c: 4 for c in gate.RUBRIC_WEIGHT}, "evidence": 2}))
    assert not meh.ok and meh.measured["verdict"] == "revise" and "evidence 2" in meh.message
    part = gate.gate_e(_tl({"follow": 5, "argument": 5}))            # 빠진 기준은 '채점 실패'(0점 아님)
    assert part.measured["missing"] and part.measured["weighted"] == 5.0


def test_timeline_findings_map_to_gate_ids_and_feedback():
    """게이트는 통과했는데 검수가 잡은 것 → gate_feedback(임계값을 고칠 신호)."""
    kinds = {"duplicate_take": "A1_length", "slide_chain": "A12_chain", "hold_broken": "A14_hold_guard",
             "late_step": "A15_step_sync", "label_leak": "B3_query_label"}
    for k, gid in kinds.items():
        assert gid in gate.TL_KIND_TO_GATE[k]
    from studio.agents import schemas as S
    assert set(gate.TL_KIND_TO_GATE) == set(S.TL_KINDS) and set(gate.RUBRIC_WEIGHT) == set(S.RUBRIC)
    passed = [gate.a12_chain([]), gate.b5_internal_names([])]
    tl = _tl({c: 3 for c in gate.RUBRIC_WEIGHT}, [{"start": "08:13", "end": "09:14", "kind": "slide_chain",
                                                    "severity": "medium", "direction": "보드 10개가 쉬지 않음"}])
    fb = gate.gate_feedback(passed, tl)
    assert [f["gate"] for f in fb] == ["A12_chain"] and fb[0]["finding"]["kind"] == "slide_chain"


def test_event_list_has_holds_sequences_and_text():
    from studio.export.events import event_list
    props = {"duration": 120.0, "chapters": [{"start": 0.0, "number": "01", "title": "들어가며"}],
             "graphics": [{"id": "g1", "template": "photo", "layout": "fullscreen", "start": 10.0, "end": 11.8,
                           "data": {"title": "스케치", "seq_id": "q1"}},
                          {"id": "g2", "template": "photo", "layout": "fullscreen", "start": 11.8, "end": 13.6,
                           "data": {"title": "장표", "seq_id": "q1"}},
                          {"id": "g3", "template": "process", "layout": "split", "start": 20.0, "end": 30.0,
                           "data": {"title": "더블 다이아몬드", "items": ["발견", "정의"],
                                    "stepAt": [{"t": 0.5, "index": 0}, {"t": 4.0, "index": 1}]}}],
             "callouts": [{"start": 40.0, "end": 43.0, "text": "연필보다\n질문 먼저"}],
             "transitions": [{"t": 50.0, "type": "wipe"}]}
    ev = event_list(props, holds=[(60.0, 75.0)], sequences={"q1": "evidence_stack"},
                    sfx=[{"t": 10.0, "category": "paper"}], peak_t=80.0)
    assert ev.startswith("# 길이 02:00") and "시퀀스 1" in ev and "홀드 1" in ev
    assert "SEQ  q1 evidence_stack 샷 2" in ev and '"스케치"' in ev and "└ photo" in ev
    assert "단계 2(낱말에서)" in ev and "HOLD 15.0s" in ev and "CALL \"연필보다 질문 먼저\"" in ev
    assert "TX   wipe" in ev and "SFX  paper" in ev and "PEAK" in ev
    lines = ev.splitlines()[1:]
    assert lines == sorted(lines, key=lambda x: x[:5])          # 시간순


# ---------------------------------------------------------------------------
# 색 게이트 F(docs/upgrade/07 7절) — 10/1 실측값 픽스처
# ---------------------------------------------------------------------------

def test_color_gates_use_measured_thresholds():
    assert not gate.f1_blotch({"ratio": 4.36, "off": 0.021, "frames": 3}).ok        # 설치본(수정 전 피부 보호)
    assert gate.f1_blotch({"ratio": 1.34, "off": 0.0, "frames": 3}).ok              # 지금 보정
    assert gate.f1_blotch({"ratio": 1.0, "off": 0.0, "frames": 0}).skipped
    r = gate.f3_sources(5.0, 1.8)
    assert r.ok and r.repaired                                                        # 매칭으로 통과
    assert not gate.f3_sources(11.2, 4.4).ok
    assert not gate.f4_clipping(0.0019, 0.0441).ok                                   # 2번 카메라 0.19% → 4.41%
    assert gate.f4_clipping(0.002, 0.0043).ok
    bad = gate.f6_tags({"long.mp4": ["color_range=pc", "color_space=bt470bg"], "short.mp4": []})
    assert not bad.ok and "long.mp4" in bad.message and gate.f6_tags({"a.mp4": []}).ok


def test_assert_bt709_and_nvenc_reason(monkeypatch):
    import subprocess
    from studio.media import ffmpeg as F
    ff = F.FFmpeg.__new__(F.FFmpeg)
    ff.ffmpeg, ff.ffprobe, ff.nvenc_error = "ffmpeg", "ffprobe", ""
    full601 = F.MediaInfo(path="x", duration=1.0, pix_fmt="yuvj420p", color_space="bt470bg", color_transfer="",
                          color_primaries="", color_range="pc")
    monkeypatch.setattr(F.FFmpeg, "probe", lambda self, p: full601)
    probs = ff.assert_bt709("x.mp4")
    assert "color_range=pc" in probs and "color_space=bt470bg" in probs and "pix_fmt=yuvj420p" in probs
    ok = F.MediaInfo(path="y", duration=1.0, pix_fmt="yuv420p", color_space="bt709", color_transfer="bt709",
                     color_primaries="bt709", color_range="tv")
    monkeypatch.setattr(F.FFmpeg, "probe", lambda self, p: ok)
    assert ff.assert_bt709("y.mp4") == []

    class R:
        returncode, stderr = 1, "[h264_nvenc] Driver does not support the required nvenc API version. minimum required Nvidia driver for nvenc is 610.00\nmore"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    assert ff._nvenc_variant() is None and "610.00" in ff.nvenc_error


def test_b11_motif_repeat_caps_same_diagram_and_logo():
    """2026-10-03 실제 계획: 더블 다이아몬드 장면 4개(예고 7요소 · 설명 13요소 · 시그니처 카드 · 되돌이 화살표), 학교 휘장 pip + 전면.
    같은 장치는 2회(시그니처는 남기고 요소가 적은 것부터 뺌), 로고는 1회."""
    def mg(t0, title, n_el=0, template="motion", signature=False, motif=""):
        g = _g(t0, t0 + 6.0, template, "fullscreen")
        g["id"] = f"g{int(t0)}"
        g["data"] = {"title": title, "spec": {"elements": [{"type": "text"}] * n_el} if n_el else None}
        if signature:
            g["data"]["signature"] = True
        if motif:
            g["data"]["motif"] = motif
        return g
    gs = [mg(10, "사라지는 이론 — 더블 다이아몬드 예고", 7),
          mg(60, "학교가 가르친 순서 — 씽킹과 더블 다이아몬드", 13),
          mg(200, "더블 다이아몬드 — 내가 건너뛴 곳", 0, "card", signature=True),
          mg(240, "실제 과정은 오간다 — 되돌이 화살표", 13, motif="더블 다이아몬드"),
          mg(300, "간극은 이론과 작업 사이", 11)]
    logo_pip = _g(30, 33, "photo", "pip"); logo_pip["id"] = "g30"
    logo_pip["data"] = {"title": "홍익대학교", "logo": True, "image": "images/own_logo_hongik.svg"}
    logo_full = _g(40, 52, "evidence", "fullscreen"); logo_full["id"] = "g40"
    logo_full["data"] = {"title": "학교와 현장 사이", "logo": True, "image": "images/own_logo_hongik.svg"}
    all_g = gs + [logo_pip, logo_full]
    r = gate.b11_motif_repeat(all_g)
    assert not r.ok and r.repair == "trim_motifs", r
    assert r.measured["over"] == {"title:더블 다이아몬드": 3, "logo:own_logo_hongik.svg": 2}, r.measured   # motif 표시는 따로 묶임
    drops = {g["id"] for g in gate.motif_drops(all_g)}
    assert drops == {"g10", "g40"}, drops          # 요소가 적은 '예고'와 전면 로고를 뺀다. 시그니처·13요소 설명·pip 이름표는 남는다
    kept = [g for g in all_g if g["id"] not in drops]
    assert gate.b11_motif_repeat(kept).ok
    # 되풀이가 상한 안이면 통과하고 묶음만 적는다
    assert gate.b11_motif_repeat(gs[1:3]).ok and gate.b11_motif_repeat(gs[1:3]).measured["groups"]


def test_gap_keyword_rejects_adverbs_and_verbs_and_prefers_concept_phrases(tmp_path):
    """2026-10-03 실제 출력 05:25~06:02: 보충 카드 넷이 '결국'·'이론'·'가르치려'·'디자인' — 아트 디렉터가 label_leak 로 뺐다.
    카드 글은 대본 용어 → 콜아웃 → 쓸 만한 강조어 → 두 낱말 명사 구절 → 4자 이상 명사. 없으면 카드를 넣지 않는다."""
    import studio.pipeline as pl
    texts = {40: "결국 디자인 이론 책들을 다시 펼쳐서 하나씩 공부할 거예요.", 41: "그래서 더 이상했어요.",
             42: "이걸 디자인 고착이라고 부릅니다.", 43: "여러분이 가르치려 하지 않아도 됩니다.", 44: "핀터레스트부터 열면 비슷해집니다."}
    utts = [_utt(k, k, 4.0 * k) for k in range(40)] + [_utt(k, -1, 4.0 * k, text=t) for k, t in texts.items()]
    p = _pipe(tmp_path, utts)
    p.spec.script = SCRIPT + "\n디자인 이론 책들을 다시 펼쳐서 하나씩 공부할 거예요. 이걸 '디자인 고착'이라고 부릅니다. 디자인 이론은 브레이크다."
    p.plan_long["emphasis"] = [{"seg": 40, "word": "결국", "kind": "highlight"}, {"seg": 43, "word": "가르치려", "kind": "highlight"},
                               {"seg": 44, "word": "핀터레스트부터", "kind": "highlight"}]
    by = {u.id: u for u in utts}
    assert p._gap_keyword(by[40]) == ("디자인 이론", "디자인")                 # 강조어 '결국'은 부사 → 명사 구절(대본에 자주 나옴)
    assert p._gap_keyword(by[41]) == ("", "")                               # 올릴 말이 없다 → 카드 없음
    assert p._gap_keyword(by[42])[0] == "디자인 고착"                          # 대본 용어가 먼저
    assert p._gap_keyword(by[43]) == ("", "")                               # '가르치려'는 동사 토막
    assert p._gap_keyword(by[44]) == ("핀터레스트", "핀터레스트부터")             # 4자 이상 고유명사 강조어는 쓴다
    assert p._gap_keyword(by[41], strict=False)[0] != ""                    # A7 block 을 막을 때만 예전 낱말
    assert pl.card_worthy("결국") is False and pl.card_worthy("이론") is False and pl.card_worthy("디자인") is False
    assert pl.card_worthy("프로세스 장표") and pl.card_worthy("어포던스") and not pl.card_worthy("이렇게 합니다")


def test_gap_cards_do_not_print_internal_markers():
    """2026-10-04 검토: 보충 카드 출처 칸에 내부 표시 'gate' 가 '( gate )'로, 키워드 위에 역할 배지 '키워드'가 나갔다."""
    from studio.director.plan import _clean_graphic
    g = _clean_graphic({"template": "keyword", "layout": "overlay", "title": "남의 예시", "source": "gate",
                        "start_seg": 3}, [1, 2, 3])
    assert g is not None and g["source"] == ""
    q = _clean_graphic({"template": "quote", "body": "Less but better", "source": "Dieter Rams", "start_seg": 3}, [3])
    assert q["source"] == "Dieter Rams"
    src = (Path(__file__).resolve().parents[1] / "studio" / "pipeline.py").read_text(encoding="utf-8")
    assert '"source": "gate"' not in src
    tsx = (Path(__file__).resolve().parents[1] / "renderer" / "src" / "components" / "longform" / "Plates.tsx").read_text(
        encoding="utf-8")
    assert "keyword: '키워드'" not in tsx
