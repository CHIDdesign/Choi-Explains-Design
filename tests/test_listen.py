"""👂 소리 듣기(studio/sound/listen.py) — HTTP·earshot 은 가짜, 진짜 Gemini·claude CLI 를 부르지 않는다. 키 값은 어떤 로그에도 남지 않는다."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import gate, net  # noqa: E402
from studio.settings import Settings  # noqa: E402
from studio.sound import fetch as F  # noqa: E402
from studio.sound import listen as L  # noqa: E402
from test_sfx_fetch import Http, ff, fetcher, lib_of, need, row, wav_bytes  # noqa: E402,F401

KEY = "AIzaSyFAKE-KEY-0123456789"


def fake_excerpt(ff_, src, dst, start, sec):
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(b"ID3fake" + str(src).encode())
    return dst


def gemini(payload):
    return net.Response(200, json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}).encode())


class Net:
    """net.request 대역: 모델 확인(GET)과 generateContent(POST)를 기록한다."""

    def __init__(self, answer, *, status=200, raise_=None):
        self.answer, self.status, self.raise_, self.calls = answer, status, raise_, []

    def __call__(self, url, *, params=None, headers=None, timeout=30.0, dst=None, rounds=4, data=None):
        self.calls.append((url, dict(headers or {}), json.loads(data) if data else None))
        if self.raise_:
            raise self.raise_
        if data is None:
            return net.Response(200, b"{}")
        return gemini(self.answer) if self.status == 200 else net.Response(self.status, f"bad {KEY}".encode())


@pytest.fixture(autouse=True)
def _no_real_key(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(L, "ENV_FILE", tmp_path / "none.env")
    monkeypatch.setattr(L, "MUSIC_CACHE", tmp_path / "music_ears.json")


def ears(tmp_path, key=KEY, **kw):
    logs = []
    e = L.Ears(None, key, work=tmp_path / "w", log=logs.append, music_cache=tmp_path / "music_ears.json", excerpt_fn=fake_excerpt, **kw)
    return e, logs


def test_key_order_setting_env_then_watch_env_file(monkeypatch, tmp_path):
    assert L.api_key(SimpleNamespace(gemini_key=" a ")) == "a"
    monkeypatch.setenv("GEMINI_API_KEY", "b")
    assert L.api_key(SimpleNamespace(gemini_key="")) == "b"
    monkeypatch.delenv("GEMINI_API_KEY")
    (tmp_path / "none.env").write_text("OTHER=1\nexport GEMINI_API_KEY='c'\n", encoding="utf-8")
    assert L.api_key(None) == "c"
    (tmp_path / "none.env").unlink()
    assert L.api_key(None) == ""
    assert Settings.from_dict({"gemini_key": "x"}).gemini_key == "x" and Settings().gemini_key == ""


def test_without_key_nothing_is_sent(tmp_path, monkeypatch):
    monkeypatch.setattr(net, "request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no http")))
    e, logs = ears(tmp_path, key="")
    assert e.hear_sfx([("thud", [tmp_path / "a.wav"])]) == {} and e.hear_mix("m.wav", silences=[[1, 2]], cues=[], sfx=[]) is None
    assert e.hear_tracks([], {}) == {} and e.calls == 0 and e.dead == "Gemini 키 없음"


def test_sfx_scores_are_heard_once_per_call_and_key_stays_in_header(tmp_path, monkeypatch):
    http = Net([{"request": 1, "candidate": 1, "score": 0, "note": "파도"}, {"request": 1, "candidate": 2, "score": 3, "note": "나무 쿵"}])
    monkeypatch.setattr(net, "request", http)
    e, logs = ears(tmp_path)
    got = e.hear_sfx([("heavy wood thud", [tmp_path / "a.wav", tmp_path / "b.wav"])])
    assert got == {(0, 0): {"score": 0, "note": "파도"}, (0, 1): {"score": 3, "note": "나무 쿵"}} and e.calls == 1
    check, ask = http.calls
    assert check[0].endswith(f"/models/{L.MODEL}") and check[1]["x-goog-api-key"] == KEY and check[2] is None
    assert ask[0].endswith(":generateContent") and KEY not in ask[0] and ask[1]["x-goog-api-key"] == KEY
    parts = ask[2]["contents"][0]["parts"]
    assert sum("inline_data" in p for p in parts) == 2 and ask[2]["generationConfig"]["responseMimeType"] == "application/json"
    assert not (tmp_path / "w" / "ears").exists()                                   # 발췌는 보낸 뒤 지운다


def test_model_unavailable_api_error_and_bad_json_are_soft(tmp_path, monkeypatch):
    monkeypatch.setattr(net, "request", lambda url, **k: net.Response(404, b"{}"))
    e, logs = ears(tmp_path)
    assert e.hear_mix("m.wav", silences=[[3.0, 4.0]], cues=[], sfx=[]) is None and "HTTP 404" in e.dead and e.calls == 0
    http = Net(None, status=500)
    monkeypatch.setattr(net, "request", http)
    e, logs = ears(tmp_path)
    assert e.hear_mix("m.wav", silences=[[3.0, 4.0]], cues=[], sfx=[]) is None and e.calls == 1
    assert any("HTTP 500" in x for x in logs) and not any(KEY in x for x in logs)   # 키 값은 로그에 없다
    monkeypatch.setattr(net, "request", Net(None, raise_=net.NetError(f"generativelanguage 연결 실패 key={KEY}")))
    e, logs = ears(tmp_path)
    assert e.hear_mix("m.wav", silences=[[3.0, 4.0]], cues=[], sfx=[]) is None and not any(KEY in x for x in logs)
    monkeypatch.setattr(net, "request", lambda url, data=None, **k: net.Response(200, b'{"candidates": []}'))
    e, logs = ears(tmp_path)
    assert e.hear_mix("m.wav", silences=[[3.0, 4.0]], cues=[], sfx=[]) is None and any("못 읽음" in x for x in logs)


def test_cap_per_job(tmp_path, monkeypatch):
    http = Net({"music_covers_voice": False, "sfx_jumps_out": None, "silence_clear": True, "note": "좋음"})
    monkeypatch.setattr(net, "request", http)
    e, logs = ears(tmp_path, max_calls=1)
    assert e.hear_mix("m.wav", silences=[[3.0, 4.0]], cues=[], sfx=[])["silence_clear"] is True
    assert e.hear_mix("m.wav", silences=[[3.0, 4.0]], cues=[], sfx=[]) is None
    assert e.calls == 1 and len(http.calls) == 2 and sum("상한" in x for x in logs) == 1


def test_tracks_are_cached_by_file_and_notes_reach_the_supervisor(tmp_path, monkeypatch):
    http = Net([{"track": 1, "instruments": "펠트 피아노", "arc": "조용히 시작해 쌓임", "peak": "2분쯤", "under_speech": True, "note": "맞음"},
                {"track": 2, "instruments": "드럼", "arc": "처음부터 셈", "peak": "내내", "under_speech": False, "note": "말 아래 안 됨"}])
    monkeypatch.setattr(net, "request", http)
    a, b = tmp_path / "a.mp3", tmp_path / "b.mp3"
    a.write_bytes(b"a"), b.write_bytes(b"bb")
    feats = {"a.mp3": {"duration": 200.0, "curve": [-30, -20, -10, -20]}, "b.mp3": {}}
    e, logs = ears(tmp_path)
    heard = e.hear_tracks([a, b], feats)
    assert heard["a.mp3"]["under_speech"] is True and heard["b.mp3"]["instruments"] == "드럼" and e.calls == 1
    parts = http.calls[-1][2]["contents"][0]["parts"]
    assert sum("inline_data" in p for p in parts) == 6                                # 곡마다 시작·중간·정점 셋
    e2, _ = ears(tmp_path)
    assert e2.hear_tracks([a, b], feats) == heard and e2.calls == 0                   # 같은 파일은 다시 듣지 않는다
    text = L.music_notes(heard)
    assert "`a.mp3`" in text and "펠트 피아노" in text and "말 아래 안 됨" in text and "들어 본 소리" in text
    assert L.music_notes({}) == ""


def test_earshot_absent_or_broken_is_none_and_present_ranks(tmp_path, monkeypatch):
    paths = [tmp_path / "x.flac", tmp_path / "y.flac"]
    monkeypatch.setattr(L.shutil, "which", lambda name: None)
    assert L.earshot_rank("wood thud", paths) is None
    monkeypatch.setattr(L.shutil, "which", lambda name: "earshot")
    seen = []

    def run(args, **kw):
        seen.append(args)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"results": [{"path": str(paths[1]), "z": 3.1}, {"path": str(paths[0]), "z": 0.2}]}),
                               stderr="")
    monkeypatch.setattr(L.subprocess, "run", run)
    assert L.earshot_rank("wood thud", paths) == [paths[1], paths[0]] and seen[0][:3] == ["earshot", "rank", "wood thud"] and "--json" in seen[0]
    monkeypatch.setattr(L.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="boom"))
    assert L.earshot_rank("wood thud", paths) is None
    monkeypatch.setattr(L.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("earshot", 1)))
    assert L.earshot_rank("wood thud", paths) is None
    assert L.earshot_rank("wood thud", paths[:1]) is None                             # 후보가 하나면 고를 것이 없다


class FakeEars:
    def __init__(self, scores, ranked=None):
        self.scores, self.asked, self.dead = scores, [], ""

    def ok(self):
        return True

    def hear_sfx(self, requests):
        self.asked.append([(i, [p.name for p in ps]) for i, ps in requests])
        return {(0, k): {"score": s, "note": f"n{k}"} for k, s in enumerate(self.scores)}


def test_fetcher_uses_ears_and_earshot_before_ai(tmp_path, ff, monkeypatch):
    http = Http([row(1, "Wood Thud a"), row(2, "Wood Thud b"), row(3, "Wood Thud c")])
    monkeypatch.setattr(net, "request", http)
    order = []
    monkeypatch.setattr(F, "earshot_rank", lambda idea, paths, log=None: order.append(idea) or [paths[2], paths[1], paths[0]])
    seen = []
    e = FakeEars([0, 3])
    lib = lib_of()
    f = fetcher(lib, ff, tmp_path, ears=e, pick=lambda t: seen.append(t) or [])
    f.run([need()])
    assert order == ["heavy wood thud"]
    assert e.asked[0][0][0] == "heavy wood thud" and len(e.asked[0][0][1]) == L.SFX_TOP     # earshot 상위 둘만 Gemini 가 듣는다
    assert "들어 보니 0/3 n0" in seen[0] and "들어 보니 3/3 n1" in seen[0]
    assert lib.sfx[0].title == "Wood Thud b"                                              # 0점(다른 소리)은 뽑지 않는다
    index = json.loads((tmp_path / "cache" / "index.json").read_text(encoding="utf-8"))
    assert len(index["heard"]) == 2
    e2 = FakeEars([3, 3])
    fetcher(lib_of(), ff, tmp_path, ears=e2).run([need()])
    assert e2.asked == []                                                                 # 들은 것은 캐시 — 다시 보내지 않는다
    lib3 = lib_of()
    fetcher(lib3, ff, tmp_path / "p", ears=FakeEars([0, 3]), pick=lambda t: [{"request": 1, "candidate": 1, "reason": "x"}]).run([need()])
    assert lib3.sfx[0].title == "Wood Thud b"                                             # 글만 본 선택이 귀의 0점을 뒤집지 못한다


def test_gate_d13_and_sound_gate_wiring(tmp_path, monkeypatch):
    assert gate.d13_ears(None, "Gemini 키 없음").skipped
    bad = gate.d13_ears({"music_covers_voice": True, "sfx_jumps_out": None, "silence_clear": False, "note": "음악이 큼"})
    assert not bad.ok and bad.level == "warn" and "덮음" in bad.message and "침묵" in bad.message and "음악이 큼" in bad.message
    assert gate.d13_ears({"music_covers_voice": False, "sfx_jumps_out": False, "silence_clear": None, "note": ""}).ok
    assert gate.THRESHOLDS["D13_ears"][0] == "취향"

    import studio.pipeline as pl
    from studio.models import Span, TimeMap
    from test_gate import _pipe, _utt
    utts = [_utt(k, k, 5.0 * k) for k in range(12)]
    p = _pipe(tmp_path, utts)
    p.timemap = TimeMap([Span(0.0, utts[-1].end)])
    p.hl_duration, p.fps, p._music = 0.0, 30.0, {}
    p.sounds = SimpleNamespace(sfx=[SimpleNamespace(path=Path("x.flac"), source="openverse", license_class="A")])
    p.ff = SimpleNamespace(probe=lambda _: SimpleNamespace(duration=10.0))
    p.long_props = {"graphics": [], "captions": []}
    p.masters = [{"name": "롱폼", "short": False, "mix": "m.wav", "raw": "r.mp4", "voice": "v.wav", "edit": SimpleNamespace(sfx=[]),
                  "mix_report": {"voice_lufs": -16.0}, "sfx_used": [(3.0, "x.flac")], "music_silences": [[8.0, 9.0]]}]
    monkeypatch.setattr(pl, "voice_start", lambda *a: None)
    asked = []

    class Mix(FakeEars):
        def hear_mix(self, mix, *, silences, cues, sfx):
            asked.append((mix, silences, cues, sfx))
            return {"music_covers_voice": False, "sfx_jumps_out": True, "silence_clear": True, "note": "쿵이 큼"}
    p._ears_obj = Mix([])
    p._gate_sound()
    d13 = {r.id: r for r in p.gate_results}["D13_ears"]
    assert not d13.ok and d13.level == "warn" and asked == [("m.wav", [[8.0, 9.0]], [], [(3.0, "x.flac")])]
    rep = json.loads((tmp_path / "sound_report.json").read_text(encoding="utf-8"))
    assert rep["ears"]["note"] == "쿵이 큼" and any(g["id"] == "D13_ears" for g in rep["gates"])
    p._ears_obj = None                                                                    # 키가 없으면 건너뛴 채 기록
    p.settings = SimpleNamespace(glossary={}, gemini_key="")
    p._gate_sound()
    assert {r.id: r for r in p.gate_results}["D13_ears"].skipped


def test_excerpt_is_short_mono_mp3(tmp_path, ff):
    src = tmp_path / "long.wav"
    wav_bytes(src, lead=0.0, sec=30.0, decay=0.0)
    out = L.excerpt(ff, src, tmp_path / "w" / "x.mp3", 5.0, 12.0)
    info = ff.probe(out)
    assert 11.5 <= info.duration <= 12.6 and out.stat().st_size < 80_000
