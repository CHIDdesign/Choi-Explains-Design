"""연출 문법 조사(reports/롱폼 숏폼 디렉팅 문법 조사.md)를 옮긴 것 — 숫자의 지위 · 컷어웨이 임무 · 단락 연결 · 질문 재소환 · 침묵 · 숏폼 단서 ·
모델 폴백과 캐시 키. 진짜 Claude 없이."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from studio import gate  # noqa: E402
from studio.agents import studio as ST  # noqa: E402
from studio.director.claude import ClaudeClient, Refused, served_mismatch  # noqa: E402
from studio.director.claude_code import ClaudeCodeClient, is_refusal  # noqa: E402
from studio.director.plan import normalize_long  # noqa: E402
from test_gate import _pipe, _utt  # noqa: E402


def _g(i: int, a: float, b: float, tpl: str = "keyword", layout: str = "fullscreen", **data) -> dict:
    return {"id": f"g{i}", "template": tpl, "layout": layout, "start": a, "end": b, "data": data}


def test_only_structural_gates_block_or_repair():
    """차단·수리는 프로그램이 판정할 수 있는 것만 — 취향 숫자가 다시 수리로 올라가면 여기서 걸린다."""
    src = Path(gate.__file__).read_text(encoding="utf-8")
    used = set(re.findall(r'_(?:ok|bad|skip)\("(\w+)", "(?:block|repair|warn)"', src))
    assert used <= set(gate.THRESHOLDS), used - set(gate.THRESHOLDS)
    for gid, level in re.findall(r'_bad\("(\w+)", "(block|repair)"', src):
        assert gate.THRESHOLDS[gid][0] == "구조", f"{gid} {level}"


def test_cutaway_roles_and_mood_cap():
    gs = [_g(0, 0, 10, "broll", src="a.mp4"), _g(1, 10, 20, "broll", src="b.mp4"), _g(2, 30, 34, "keyword", "overlay")]
    plan = [{"start_seg": 1, "evidence": {"role": "proof"}}, {"start_seg": 5, "evidence": {"role": "mood"}}, {"start_seg": 9}]
    beats = [{"start_seg": 0, "end_seg": 4, "cutaway": "prove"}, {"start_seg": 5, "end_seg": 8, "cutaway": "explain"}]
    roles = gate.cutaway_roles(gs, plan, beats)
    assert roles == {"g0": "prove", "g1": "reset", "g2": ""}          # 자료가 mood 면 비트가 뭐라 했든 분위기
    r = gate.b12_cutaway_role(gs, roles)
    assert not r.ok and r.level == "warn" and not r.repair and r.measured["mood_share"] == 0.5
    assert r.measured["undeclared"] == []                             # 얼굴 위 글자는 컷어웨이가 아니다
    ok = gate.b12_cutaway_role(gs, {"g0": "prove", "g1": "context"})
    assert ok.ok
    missing = gate.b12_cutaway_role(gs, {"g0": "prove"})
    assert not missing.ok and missing.measured["undeclared"] == ["g1"]
    assert gate.b12_cutaway_role([], {}).skipped
    assert gate.b12_cutaway_role(gs, {"g0": "", "g1": ""}).skipped     # 규칙 폴백(비트 없음) — 알릴 것이 없다
    # 비트에 선언이 없으면 자료의 role 로
    assert gate.cutaway_roles(gs[:1], plan, []) == {"g0": "prove"}


def test_link_audit_changes_staging_only():
    segs = [{"start_seg": 0, "end_seg": 3, "link": "none"}, {"start_seg": 4, "end_seg": 6, "link": "and"},
            {"start_seg": 7, "end_seg": 9, "link": "and"}, {"start_seg": 10, "end_seg": 12, "link": "and"},
            {"start_seg": 13, "end_seg": 15, "link": "but"}]
    r = gate.a19_link_audit(segs)
    assert not r.ok and r.level == "warn" and r.measured["runs"] == [[4, 12]] and r.measured["and"] == 3
    assert gate.a19_link_audit(segs[:3] + segs[4:]).ok                # 두 번까지는 괜찮다
    assert gate.a19_link_audit([{"start_seg": 0}]).skipped
    assert [p["after_seg"] for p in ST.link_pauses(segs)] == [9]      # 세 번째 '그리고' 앞에 쉼
    brief = {"treatment": {"segments": segs, "silences": [{"after_seg": 12, "sec": 1.2, "before": "turn", "why": "w"}]}}
    raw, _ = ST.merge_plan({"director": brief})
    assert [p["after_seg"] for p in raw["pauses"]] == [9] and raw["silences"][0]["after_seg"] == 12


def test_silences_become_pauses_and_survive_renormalizing():
    utts = [_utt(k, k, 4.0 * k) for k in range(10)]
    raw = {"silences": [{"after_seg": 3, "sec": 9.0, "before": "peak", "why": "반전 전"}, {"after_seg": 999, "sec": 1.0}],
           "pauses": [{"after_seg": 3, "sec": 0.8, "reason": "r"}]}
    plan = normalize_long(raw, utts, [])
    assert plan["silences"] == [{"after_seg": 3, "sec": 1.6, "before": "peak", "why": "반전 전"}]
    assert plan["pauses"] == [{"after_seg": 3, "sec": 1.6, "reason": "r"}]
    assert normalize_long(plan, utts, [])["pauses"] == plan["pauses"]  # 저장된 계획을 다시 읽어도 그대로


def test_d12_counts_only_real_silences():
    spans = [(10.0, 11.0), (50.0, 51.0), (90.0, 90.2)]
    r = gate.d12_silences(spans, [], [])
    assert r.ok and r.measured["real"] == 2                           # 0.2초는 침묵이 아니다
    one = gate.d12_silences(spans[:1], [], [])
    assert not one.ok and one.level == "warn" and not one.repair
    busy = gate.d12_silences(spans, [{"start": 5.0, "end": 20.0}], [])
    assert not busy.ok and busy.measured["real"] == 1
    assert not gate.d12_silences(spans, [], [(50.5, "x.wav")]).ok
    assert gate.d12_silences(spans, [{"start": 2.0, "end": 10.0}, {"start": 11.0, "end": 45.0}], []).ok   # 큐가 침묵에 닿기만 하면 비운 것
    assert gate.d12_silences(None, [], []).skipped


def test_reprise_slot_is_nearest_free_room_before_the_answer():
    assert gate.reprise_slot([], 100.0) == (95.8, 99.8)
    assert gate.reprise_slot([(90.0, 99.0)], 100.0) == (85.7, 89.7)
    assert gate.reprise_slot([(95.0, 99.7), (70.0, 90.0)], 100.0) == (90.7, 94.7)
    assert gate.reprise_slot([(70.0, 101.0)], 100.0) is None          # 25초 안에 빈 자리가 없다


def test_a20_reprise_gate():
    assert gate.a20_reprise(None, []).skipped
    assert gate.a20_reprise((0.0, 100.0), []).ok                      # 2분 안
    r = gate.a20_reprise((0.0, 300.0), [])
    assert not r.ok and r.level == "warn"
    assert gate.a20_reprise((0.0, 300.0), [{"id": "reprise"}]).ok


def test_pipeline_reprises_question_and_finds_real_silences(tmp_path):
    utts = [_utt(k, k, 4.0 * k) for k in range(95)]
    p = _pipe(tmp_path, utts)
    p.plan_long.update(central_question="왜 좋은 디자인은 설명이 없을까", payoff_seg=60, hook_segs=[0],
                       silences=[{"after_seg": 10, "sec": 1.0}, {"after_seg": 94, "sec": 1.0}])
    span = p._question_span()
    assert span[0] == 0.0 and span[1] > 200.0
    g = p._reprise([], [])
    assert g is not None and g.id == "reprise" and g.template == "quote" and g.end <= span[1] and g.data["body"] == "왜 좋은 디자인은 설명이 없을까"
    assert p._reprise([], [(0.0, 400.0)]) is None                     # 홀드로 덮이면 넣지 않는다(A20 이 알린다)
    p.plan_long["payoff_seg"] = 10
    assert p._reprise([], []) is None                                 # 2분 안이면 다시 띄우지 않는다
    assert p._silence_spans() == []                                   # 붙여 놓은 컷에는 쉼이 없다 · 마지막 발화 뒤는 쉼이 아니다


def test_silence_span_is_the_real_gap_in_the_edit(tmp_path):
    from studio.models import Span, TimeMap
    utts = [_utt(k, k, 5.0 * k) for k in range(12)]
    p = _pipe(tmp_path, utts)
    p.timemap = TimeMap([Span(0.0, utts[-1].end)])
    p.plan_long["silences"] = [{"after_seg": 3, "sec": 1.0}, {"after_seg": 11, "sec": 1.0}]
    assert p._silence_spans() == [(19.0, 20.0)]


def test_music_stays_out_of_silences(tmp_path):
    from studio.models import Span, TimeMap
    utts = [_utt(k, k, 5.0 * k) for k in range(12)]
    p = _pipe(tmp_path, utts)
    p.timemap = TimeMap([Span(0.0, utts[-1].end)])
    p.hl_duration = 0.0
    p.plan_long["silences"] = [{"after_seg": 5, "sec": 1.0}]
    a, b = p._silence_spans()[0]
    sheet = {"cues": [{"id": "m1", "start_seg": 0, "end_seg": 11, "role": "bed", "energy": 1, "entry": "fade_in", "exit": "fade_bar"}]}
    cues, silences = p._long_music_cues(sheet, p.timemap.duration)
    assert (a, b) in silences and len(cues) == 2
    assert not any(q["start"] < b and q["end"] > a for q in cues)


def test_gate_sound_reports_declared_silences(tmp_path, monkeypatch):
    import studio.pipeline as pl
    from studio.models import Span, TimeMap
    utts = [_utt(k, k, 5.0 * k) for k in range(12)]
    p = _pipe(tmp_path, utts)
    p.timemap = TimeMap([Span(0.0, utts[-1].end)])
    p.hl_duration, p.fps, p.sounds, p._music = 2.0, 30.0, None, {}
    p.ff = SimpleNamespace(probe=lambda _: SimpleNamespace(duration=10.0))
    p.long_props = {"graphics": [], "captions": []}
    p.masters = [{"name": "롱폼", "short": False, "mix": "m.wav", "raw": "r.mp4", "voice": "v.wav", "edit": SimpleNamespace(sfx=[]),
                  "mix_report": {"voice_lufs": -16.0}, "sfx_used": []}]
    monkeypatch.setattr(pl, "voice_start", lambda *a: None)
    p.plan_long.update(studio={"treatment": {"concept": "c"}},
                       silences=[{"after_seg": 2, "sec": 1.0}, {"after_seg": 5, "sec": 1.0}])
    p._gate_sound()
    d12 = {r.id: r for r in p.gate_results}["D12_silences"]
    assert d12.ok and d12.measured["real"] == 2 and d12.measured["spans"][0] == [16.0, 17.0]   # 하이라이트 2초만큼 밀린 시각


def test_reprise_text_passes_screen_hygiene():
    g = {"template": "quote", "data": {"body": "왜 좋은 디자인은 설명이 없을까", "author": "앞에서 던진 질문"}}
    assert gate.b4_direction_notes([g]).ok and gate.b5_internal_names([g]).ok


def test_s1_hedge_finds_dropped_qualifiers():
    text = {1: "연구에 따르면 30%가 늘었습니다.", 2: "효과가 분명합니다.", 3: "숫자가 말해 줍니다.", 4: "다만 표본은 12명뿐입니다.", 5: "다음 이야기입니다."}
    r = gate.s1_hedge([2, 3], text, [1, 2, 3, 4, 5])
    assert not r.ok and r.level == "warn" and not r.repair and r.measured["lost"] == [1, 4]
    assert gate.s1_hedge([1, 2, 3, 4], text, [1, 2, 3, 4, 5]).ok
    assert gate.s1_hedge([5], text, [1, 2, 3, 4, 5]).measured["lost"] == [4]
    assert gate.s1_hedge([], text, [1, 2]).skipped


def test_signature_scene_keeps_its_reason():
    director = {"treatment": {"signature_scenes": [{"id": "s", "start_seg": 1, "end_seg": 2, "kind": "diagram", "title": "t", "brief": "b", "why": "이유"}]}}
    assert ST.signature_scenes(director)[0]["why"] == "이유"


# --- 모델 폴백 · 캐시 키 ------------------------------------------------------------------------------
class Fake:
    model, effort = "claude-opus-5-5", "high"

    def __init__(self, fail: Exception):
        self.calls, self.fail = [], fail

    def structured(self, **kw):
        self.calls.append(kw.get("model"))
        if kw.get("model") is not None:
            raise self.fail
        return {"ok": True}


def test_refusal_falls_back_to_global_model():
    fc = Fake(Refused("모델이 요청을 거절했습니다: bio"))             # 영어 'model' 이 없는 한국어 메시지
    assert ST.Studio(fc, routing="auto").call("director", "x", "do") == {"ok": True}
    assert fc.calls == [ST.FABLE, None]
    pinned = Fake(Refused("거절"))
    ST.Studio(pinned, models={"director": "claude-sonnet-5-5"}).call("director", "x", "do")
    assert pinned.calls == ["claude-sonnet-5-5", None]                # 파일로 고정한 모델이어도 거절이면 넘어간다


def test_refusal_is_not_retried_when_already_global():
    fc = Fake(Refused("거절"))
    with pytest.raises(Refused):
        ST.Studio(fc, models={"director": "claude-opus-5-5"}).call("director", "x", "do")
    assert fc.calls == ["claude-opus-5-5"]


def test_other_errors_still_do_not_fall_back():
    fc = Fake(RuntimeError("overloaded"))
    with pytest.raises(RuntimeError):
        ST.Studio(fc, routing="auto").call("director", "x", "do")
    assert fc.calls == [ST.FABLE]


class _Stream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(())

    def get_final_message(self):
        return self.msg


def _api(msg):
    c = ClaudeClient("test-key-not-real")
    calls: list[dict] = []
    logs: list[str] = []
    c.log = logs.append

    def stream(**kw):
        calls.append(kw)
        return _Stream(msg)
    c.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)),
                               messages=SimpleNamespace(stream=stream))
    return c, calls, logs


def test_api_refusal_is_not_retried_on_the_same_model():
    msg = SimpleNamespace(stop_reason="refusal", stop_details=SimpleNamespace(category="bio"), model="claude-fable-5-1", usage=None, content=[])
    c, calls, _ = _api(msg)
    with pytest.raises(Refused):
        c.structured(system="s", shared_context="c", instruction="i", schema={"type": "object"}, model="claude-fable-5-1",
                     tools=("WebSearch", "WebFetch"), max_turns=4)
    assert len(calls) == 1                                            # 예전: 세 방식 × 도구 세트마다 같은 모델로 다시


def test_api_warns_when_another_model_answers():
    text = SimpleNamespace(type="text", text='{"a": 1}')
    msg = SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5", usage=None, content=[text])
    c, _, logs = _api(msg)
    assert c.structured(system="s", shared_context="c", instruction="i", schema={"type": "object"}, model="claude-fable-5-1") == {"a": 1}
    assert any("claude-fable-5-1" in x and "claude-opus-5-5" in x for x in logs)


def test_cli_recognises_refusal():
    assert is_refusal({"stop_reason": "refusal"})
    assert is_refusal({"result": "API Error: Claude Code is unable to respond to this request, which appears to violate our Usage Policy"})
    assert not is_refusal({"stop_reason": "end_turn", "result": "{}"})


def test_served_mismatch_is_not_only_for_opus(tmp_path):
    assert served_mismatch("claude-fable-5-1", "claude-opus-5-5")
    assert served_mismatch("claude-opus-5-5", "claude-sonnet-5-5")
    assert served_mismatch("sonnet", "claude-opus-5-5")               # 별칭은 계열로
    assert not served_mismatch("opus", "claude-opus-5-5")
    assert not served_mismatch("claude-opus-5-5[1m]", "claude-opus-5-5")
    assert not served_mismatch("claude-fable-5-1", "")
    logs: list[str] = []
    c = ClaudeCodeClient("claude", model="claude-opus-5-5", log=logs.append, workdir=tmp_path)
    for _ in range(2):
        c._record({"usage": {}}, "🎬", 0.0, served="claude-opus-5-5", requested="claude-fable-5-1")
    assert sum("요청한 모델은" in x for x in logs) == 1


def test_cache_keys_see_the_model():
    fc = Fake(RuntimeError("x"))
    base = ST.Studio(fc, routing="auto").plan_models()
    assert ST.FABLE in base
    assert ST.Studio(fc, routing="auto", models={"editor": "claude-sonnet-5-5"}).plan_models() != base
    assert ST.Studio(fc).model_for("cut_editor") == "claude-opus-5-5"
    assert ST.Studio(fc, routing="auto").model_for("cut_editor") == ST.FABLE


def test_cut_editor_has_room_for_thinking_and_every_utterance():
    assert ST.AGENTS["cut_editor"].max_tokens >= 64000


def test_answer_mentioning_usage_policy_is_not_a_refusal():
    assert not is_refusal({"is_error": False, "result": "서비스 약관(usage policy)을 다룬다", "structured_output": {"a": 1}})
    assert not is_refusal({"result": '{"thesis": "usage policy 는 아무도 읽지 않는다"}'})        # 옛 CLI: result 가 답 전체


def test_pip_photo_over_the_face_is_not_a_cutaway():
    gs = [_g(0, 0, 10, "broll", src="a.mp4"), _g(1, 12, 15, "photo", "pip", image="p.jpg")]
    r = gate.b12_cutaway_role(gs, {"g0": "prove", "g1": ""})
    assert r.ok and r.measured["undeclared"] == []


def test_platform_names_are_not_sources():
    from studio.assets.license import AssetMeta, classify, credits
    meta = AssetMeta(origin="web", institution="유튜브", creator="홍길동", source_url="https://www.kma.go.kr/a", license=classify("CC BY 4.0"))
    assert "유튜브" not in credits(meta)[0] and "kma.go.kr" in credits(meta)[0]
