"""🚦 품질 게이트(studio/gate.py) — 10/1 테스트 영상의 수치를 그대로 옮긴 합성 픽스처로, 그때 동시에 실패했어야 할
A1·A3·A5·A6·A7·A8·A9 가 실제로 실패하는지, B3·B4·B5 가 화면 글자 누수('스케치북 넘기기'·'brand'·'motion')를 잡는지 본다.
(docs/upgrade/08_품질_게이트.md 2~3절, 09 작업지시서 WP2)"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

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
    assert any(g["start_seg"] == 30 and g["title"] == "원칙" for g in gs) or all(g["start_seg"] != 30 for g in gs)
    assert len({g["start_seg"] for g in gs}) == len(gs)             # 같은 문장에 두 번 넣지 않는다
    # 채운 자리로 다시 재면 맨얼굴 25초 이하·빈 칸 없음(카드 4초)
    from studio.director.plan import seg_edit_times
    seg_t = seg_edit_times(utts, p.timemap)
    timed = lp["graphics"] + [_g(seg_t[g["start_seg"]][0], seg_t[g["start_seg"]][0] + 4.0) for g in gs]
    assert gate.a6_distribution(timed, total).ok and gate.a7_face_run(timed, total).ok
