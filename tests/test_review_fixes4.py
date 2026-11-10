"""콜라주 조각의 시각·재료·출처, 끊는 큐의 곡 위치, 해시 없는 효과음 검사(디자인 v5.1 리뷰)."""
from __future__ import annotations

import numpy as np
from PIL import Image

from studio.assets import cutout, graphics as evg
from studio.director import plan as P
from studio.edit.grammar import auto_motion_sfx
from studio.media import mix as M
from studio.pipeline import short_retype
from studio.sound import library as L


def _piece(n, **kw):
    return {"image": f"images/{n}.jpg", "orig": f"images/{n}.jpg", "credit": f"사진 {n}", **kw}


def test_piece_past_the_end_is_dropped_with_its_credit(monkeypatch):
    monkeypatch.setattr(P, "step_times", lambda g, *a, **k: [{"index": i, "t": t} for i, t in enumerate((0.5, 5.45, 10.45))])
    class TG:
        start, end = 10.0, 17.45
        data = {"credit": "사진 a · 사진 b · 사진 c"}
    g = {"template": "collage", "cutouts": [_piece(n, word=n, seg=1) for n in "abc"]}
    P.land_marks(TG, g, [], None)
    assert [c["image"] for c in TG.data["cutouts"]] == ["images/a.jpg", "images/b.jpg"]
    assert TG.data["credit"] == "사진 a · 사진 b" and len(TG.data["wordMarks"]) == 2


def test_credit_line_keeps_whole_names_only():
    long = [{"credit": f"작가 {i} 이름이 조금 긴 사람 · CC BY 4.0 · Wikipedia (문서 {i})"} for i in range(4)]
    line = P.credit_line(long)
    assert len(line) <= P.CREDIT_MAX and line.endswith("(문서 1)") and "작가 2" not in line


def test_pick_forgets_the_beat_time():
    got = evg._pick([_piece("a", cut=True, at=4.9), _piece("b", cut=True, at=2.4)], 4)
    assert len(got) == 2 and all("at" not in c for c in got)


def test_quoted_photos_are_not_collage_material():
    ev = {"template": "evidence", "data": {"assets": [{"src": "a.jpg", "kind": "photo", "tier": "C"}, {"src": "b.jpg", "kind": "photo", "tier": "A"}]}}
    assert [c["image"] for c in evg._real_photos(ev)] == ["b.jpg"]
    assert evg._real_photos({"template": "photo", "data": {"image": "a.jpg", "tier": "C"}}) == []
    short = short_retype({"template": "evidence", "assets": [{"src": "a.jpg", "kind": "photo", "tier": "C"}], "start_seg": 1})
    assert short["template"] == "photo" and short["tier"] == "C"
    pip, _ = evg.to_graphics([{"start_seg": 1, "end_seg": 1, "need": "entity", "treatment": "pip", "label": "x", "claim": "c", "subject": {"name_ko": "x"}}],
                             [{"i": 0, "assets": [{"src": "a.jpg", "kind": "photo", "tier": "C"}], "archive": None, "stock": None}])
    assert pip[0]["template"] == "photo" and pip[0]["tier"] == "C"


def test_only_the_stack_gets_one_thud_per_piece():
    pieces = [{"image": "a"}, {"image": "b"}, {"image": "c"}]
    for tpl, first in (("collage", ["paper_place"]), ("keyword_montage", [])):
        ev = auto_motion_sfx([{"template": tpl, "layout": "fullscreen", "start": 10.0, "end": 16.0, "data": {"cutouts": pieces}}])
        assert [e["category"] for e in ev] == first
    assert sum(1 for e in auto_motion_sfx([{"template": "cutout_stack", "layout": "overlay", "start": 10.0, "end": 16.0, "data": {"cutouts": pieces}}]) if e.get("thud")) == 3


def test_collage_with_too_few_cuts_goes_back_to_full_photos(tmp_path, monkeypatch):
    (tmp_path / "images").mkdir()
    for n in "abc":
        Image.new("RGB", (400, 300), (90, 90, 90)).save(tmp_path / "images" / f"{n}.jpg")
    monkeypatch.setattr(cutout, "press_cutout", lambda p, kind="": (p, False, "person"))
    g = {"template": "collage", "layout": "fullscreen", "start": 5.0, "end": 11.0,
         "data": {"cutouts": [_piece(n, w=400, h=300, at=i * 1.0) for i, n in enumerate("abc")], "name": "링컨", "credit": "c", "wordMarks": [{}]}}
    evg.press_collages([g], tmp_path)
    assert g["template"] == "evidence" and g["data"]["treatment"] == "hero" and "cutouts" not in g["data"] and "name" not in g["data"] and "wordMarks" not in g["data"]
    assert [a["src"] for a in g["data"]["assets"]] == ["images/a.jpg", "images/b.jpg", "images/c.jpg"] and g["data"]["credit"] == "c"


def test_duplicate_source_is_pressed_once_at_a_time(tmp_path, monkeypatch):
    (tmp_path / "images").mkdir()
    Image.new("RGB", (40, 30)).save(tmp_path / "images" / "a.jpg")
    calls = []
    def press(p, kind=""):
        calls.append(p.name)
        return p, False, "person"
    monkeypatch.setattr(cutout, "press_cutout", press)
    got = evg._press_many([_piece("a"), _piece("a")], tmp_path)
    assert len(got) == 2 and calls == ["a.jpg"] * 3            # 동시에는 한 번, 나머지는 끝난 뒤 차례로


def test_stop_cue_does_not_replay_what_the_last_cue_played(monkeypatch):
    sr = M.SR
    x = np.ones(60 * sr, np.float32) * 0.05
    x[40 * sr:45 * sr] = 0.5                                   # 정점 45초
    monkeypatch.setattr(M, "decode", lambda ff, path, start=0.0, duration=None: np.stack([x, x], axis=1)[int(start * sr):])
    plan = M.BgmPlan(path="x", lufs=-14.0, cues=[{"id": "m1", "start": 0.0, "end": 40.0, "exit": "fade_bar", "track_from": -1.0},
                                                 {"id": "m2", "start": 50.0, "end": 60.0, "exit": "stop", "track_from": -1.0},
                                                 {"id": "m3", "start": 70.0, "end": 75.0, "exit": "stop", "track_from": -1.0}])
    src = M._BgmSource(None, plan, 90 * sr)
    assert plan.cues[1]["track_from"] == -1.0 and plan.cues[1]["start"] == 50.0
    ends = [o + L_ for o, (_, L_, _) in zip(src.offsets, src.pieces)]
    assert all(o >= e - sr // 10 for o, e in zip(src.offsets[1:], ends))     # 다음 큐는 앞 큐가 끝난 곡 위치 뒤에서 시작(멈춤 스냅 0.15초 안)
    first = M.BgmPlan(path="x", lufs=-14.0, cues=[{"id": "m", "start": 5.0, "end": 25.0, "exit": "stop", "track_from": -1.0}])
    M._BgmSource(None, first, 70 * sr)
    assert first.cues[0]["track_from"] == 25.0                  # 첫 큐는 그대로 정점에 맞춘다


def test_unhashed_sound_must_be_audio(tmp_path, monkeypatch):
    (tmp_path / "m.json").write_text('{"sfx": [{"id": "a", "category": "paper", "url": "https://h/a.mp3"}], "bgm": [], "models": []}', encoding="utf-8")
    bad = b"<html>blocked</html>"
    monkeypatch.setattr(L, "_download", lambda url, dst: dst.write_bytes(bad))
    lib = L.SoundLibrary(tmp_path / "s", tmp_path / "m.json").ensure(kinds=("sfx",))
    assert not (tmp_path / "s" / "sfx" / "a.mp3").exists() and not [x for x in lib.sfx if x.id == "a"]
    (tmp_path / "s" / ".failed.json").unlink(missing_ok=True)
    (tmp_path / "s" / "sfx").mkdir(parents=True, exist_ok=True)
    (tmp_path / "s" / "sfx" / "a.mp3").write_bytes(bad)        # 예전에 받아 둔 것도 다시 받는다
    monkeypatch.setattr(L, "_download", lambda url, dst: dst.write_bytes(b"ID3\x04\x00" + bytes(40)))
    lib = L.SoundLibrary(tmp_path / "s", tmp_path / "m.json").ensure(kinds=("sfx",))
    assert [x.id for x in lib.sfx if x.id == "a"] == ["a"]
