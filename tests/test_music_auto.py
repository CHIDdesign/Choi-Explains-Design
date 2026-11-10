"""music_mode='auto' — 음악 감독이 검색어를 쓰고, Openverse 후보를 받아 재고, 큐 시트의 track 으로 고른다(HTTP 는 가짜)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import gate, net  # noqa: E402
from studio import pipeline as pl  # noqa: E402
from studio.director.claude import DirectorError  # noqa: E402
from studio.settings import Settings  # noqa: E402
from studio.sound import tracks as T  # noqa: E402


def row(i, lic="by", **kw):
    r = {"id": f"id{i:04d}xxxx", "title": f"Song &amp; {i}", "creator": f"artist{i}", "license": lic, "license_version": "3.0",
         "source": "jamendo", "url": f"https://audio.test/{i}.mp3", "foreign_landing_url": f"https://www.jamendo.com/track/{i}",
         "attribution": f'"Song &amp; {i}" by artist{i} is licensed under CC BY 3.0.', "duration": 200_000,
         "tags": [{"name": "instrumental"}, {"name": "piano"}], "genres": ["classical"]}
    return {**r, **kw}


def fake_http(monkeypatch, results, *, fail_download=(), pages=None):
    """pages: 원문 페이지 주소 → 실제 라이선스 코드(없으면 Openverse 응답과 같은 것으로 꾸민다)."""
    calls = []
    seen = {}

    def get_json(url, params=None, **kw):
        calls.append(params)
        rows = results(params["q"]) if callable(results) else results
        if isinstance(rows, Exception):
            raise rows
        seen.update({r["foreign_landing_url"]: r["license"] for r in rows})
        return {"results": rows}

    def request(url, **kw):
        code = (pages or {}).get(url, seen.get(url, ""))
        if not code:                                   # 라이선스 링크가 없는 페이지
            return net.Response(200, b"<html>track</html>")
        href = "publicdomain/zero/1.0" if code == "cc0" else f"licenses/{code}/3.0"
        return net.Response(200, f'<a href="https://creativecommons.org/{href}/">x</a>'.encode())

    def download(url, dst, **kw):
        if url in fail_download:
            raise net.NetError("막힘")
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_bytes(b"x" * 100)
        return Path(dst)
    monkeypatch.setattr(T.net, "get_json", get_json)
    monkeypatch.setattr(T.net, "request", request)
    monkeypatch.setattr(T.net, "download", download)
    monkeypatch.setattr(T, "features", lambda ps, *a, **k: {p.name: {"duration": 200.0} for p in ps})
    return calls


def test_search_keeps_only_free_full_instrumental_tracks(monkeypatch):
    bad = [row(1, "by-nc"), row(2, "by-nd"), row(3, "pdm"), row(4, source="freesound"), row(5, duration=60_000), row(6, duration=600_000),
           row(7, tags=[{"name": "instrumental"}, {"name": "female"}]), row(8, tags=[{"name": "pop"}]), row(9, url="")]
    calls = fake_http(monkeypatch, bad + [row(10, "cc0"), row(11, "by"), row(12, "by-sa")])
    got = T.search_auto(["piano"])
    assert [c["class"] for c in got] == ["A", "A", "A-sa"]
    p = calls[0]
    assert p["category"] == "music" and p["license_type"] == "commercial" and set(p["license"].split(",")) == {"cc0", "by", "by-sa"}
    assert got[1]["title"] == "Song & 11" and got[1]["credit"].endswith("https://www.jamendo.com/track/11") and "&amp;" not in got[1]["credit"]


def test_search_falls_back_to_first_word_and_spreads(monkeypatch):
    def results(q):
        if q == "pizzicato orchestra":
            return []
        base = 100 if q == "pizzicato" else 200
        who = {"creator": "same"} if q == "pizzicato" else {}
        return [row(base + i, **who) for i in range(10)]
    calls = fake_http(monkeypatch, results)
    got = T.search_auto(["pizzicato orchestra", "piano"], want=8)
    assert [x["q"] for x in calls] == ["pizzicato orchestra", "pizzicato", "piano"]
    assert len(got) == 8 and sum(c["creator"] == "same" for c in got) == T.AUTO_PER_ARTIST


def test_fetch_writes_credit_next_to_track_and_passes_d9(monkeypatch, tmp_path):
    fake_http(monkeypatch, [row(1, "by"), row(2, "by-sa"), row(3, "by")], fail_download={"https://audio.test/3.mp3"})
    got = T.fetch_auto(T.search_auto(["piano"]), tmp_path)
    assert len(got) == 2
    notes = [T.sidecar(p) for p in got]
    assert [n[0] for n in notes] == ["A", "A-sa"] and "by artist1" in notes[0][1] and "jamendo.com/track/1" in notes[0][1]
    assert gate.d9_license([(n[1], n[0]) for n in notes]).ok


def test_fetch_checks_source_page_license_before_download(monkeypatch, tmp_path):
    """Openverse 색인이 늦어 'by' 로 내려온 곡이 원문에서 BY-NC(또는 BY-SA)면 받지 않는다 — NC 곡이 'CC BY' 크레딧으로 나가지 않게."""
    pages = {"https://www.jamendo.com/track/2": "by-nc", "https://www.jamendo.com/track/3": "by-sa", "https://www.jamendo.com/track/4": ""}
    logs = []
    fake_http(monkeypatch, [row(1, "by"), row(2, "by"), row(3, "by"), row(4, "by")], pages=pages)
    got = T.fetch_auto(T.search_auto(["piano"]), tmp_path, log=logs.append)
    assert [p.name for p in got] == [T._candidate(row(1))["name"]] and len(list(tmp_path.glob("*.mp3"))) == 1
    assert sum("확인하지 못해" in x for x in logs) == 3
    assert T.fetch_auto([{k: v for k, v in T._candidate(row(1)).items() if k != "page"}], tmp_path / "old") == []   # 옛 후보(페이지 없음)도 안 쓴다


def test_offline_stops_after_first_query(monkeypatch):
    calls = fake_http(monkeypatch, net.NetError("막힘"))
    assert T.search_auto(["piano arpeggio", "strings", "felt piano"]) == [] and len(calls) == 1


def test_fetch_drops_unmeasurable_and_caps_cache(monkeypatch, tmp_path):
    fake_http(monkeypatch, [row(1), row(2)])
    monkeypatch.setattr(T, "features", lambda ps, *a, **k: {ps[0].name: {"duration": 200.0}, ps[1].name: {}})
    old = tmp_path / "old_track.mp3"
    old.write_bytes(b"y" * 500)
    old.with_suffix(".txt").write_text("A\nx", encoding="utf-8")
    monkeypatch.setattr(T, "AUTO_CAP", 250)
    got = T.fetch_auto(T.search_auto(["piano"]), tmp_path)
    assert len(got) == 1 and got[0].exists() and not old.exists() and not old.with_suffix(".txt").exists()


class Studio:
    def __init__(self, track="", search=None):
        self.track, self.search, self.scored = track, search, []

    def music_search(self, seed):
        assert seed["sound_concept"] == "피아노에서 스트링으로"
        if self.search:
            raise self.search
        return {"queries": ["piano arpeggio"], "arc": "piano then strings, then cut"}

    def score(self, listing, brief, tracks=""):
        self.scored.append(tracks)
        return {"suite": "felt", "fit_score": 8, "cues": [], "track": self.track, "track_reason": "쌓임이 맞다"}


def bare(tmp_path, monkeypatch, studio, *, ai=True):
    p = pl.Pipeline.__new__(pl.Pipeline)
    p.log = p._log_file_only = lambda *_: None
    p.work = tmp_path / "work"
    p.work.mkdir()
    p.cancel = None
    p.ff = SimpleNamespace(ffmpeg="ffmpeg")
    p.spec = SimpleNamespace(music=True, bgm="", topic="주제", make_long=True, studio_mode=True, highlight_min_sec=20, highlight_max_sec=30,
                             opening_highlight=False)
    p.plan_long = {"studio": {"thesis": "논지", "treatment": {"sound_concept": "피아노에서 스트링으로"}}, "music": {}, "chapters": []}
    p.utts, p.timemap = [], SimpleNamespace(duration=60.0)
    p._auto_music = True
    p._use_api = lambda: ai
    p._ensure_studio = lambda: studio
    monkeypatch.setattr(pl, "USER_DIR", tmp_path / "user")
    monkeypatch.setattr(pl, "track_listing", lambda ts, *a, **k: "\n".join(f"- `{x.name}`" for x in ts))
    monkeypatch.setattr(pl, "clean_music", lambda raw, ids: {"suite": raw.get("suite"), "fit_score": raw.get("fit_score"), "cues": [], "silences": []})
    monkeypatch.setattr(pl, "seg_edit_times", lambda *a: {})
    return p


def test_supervisor_picks_from_candidates_with_credit(monkeypatch, tmp_path):
    fake_http(monkeypatch, [row(1), row(2)])
    name = T._candidate(row(2))["name"]
    st = Studio(track=name)
    p = bare(tmp_path, monkeypatch, st)
    p.stage_music()
    assert p.spec.music and p.spec.bgm.endswith(name)
    assert name in st.scored[0] and "piano then strings" in st.scored[0] and "classical" in st.scored[0]
    assert T.sidecar(p.spec.bgm)[0] == "A"
    saved = json.loads((p.work / "music_auto.json").read_text(encoding="utf-8"))
    assert saved["queries"] == ["piano arpeggio"]


@pytest.mark.parametrize("case", ["rejects", "no_results", "offline", "search_error", "no_ai"])
def test_no_blind_pick_and_no_crash(monkeypatch, tmp_path, case):
    results = [] if case == "no_results" else net.NetError("막힘") if case == "offline" else [row(1), row(2)]
    calls = fake_http(monkeypatch, results)
    st = Studio(search=DirectorError("실패") if case == "search_error" else None)
    p = bare(tmp_path, monkeypatch, st, ai=case != "no_ai")
    p.stage_music()
    assert p.spec.music is False and p.spec.bgm == "" and p._music_note
    assert (case != "no_ai") or calls == []


def test_supervisor_failure_never_uses_first_candidate(monkeypatch, tmp_path):
    fake_http(monkeypatch, [row(1), row(2)])
    st = Studio()
    st.score = lambda *a, **k: (_ for _ in ()).throw(DirectorError("실패"))
    p = bare(tmp_path, monkeypatch, st)
    monkeypatch.setattr(pl, "fallback_music", lambda *a, **k: {"cues": []})
    p.stage_music()
    assert p.spec.music is False and p.spec.bgm == ""


def test_old_saved_mine_becomes_auto_but_explicit_choice_stays():
    assert Settings().music_mode == "auto"
    assert Settings.from_dict({"music_mode": "mine"}).music_mode == "auto"
    assert Settings.from_dict({"music_mode": "off"}).music_mode == "off"
    assert Settings.from_dict({"music_mode": "mine", "music_mode_v": 2}).music_mode == "mine"
