"""🔍 효과음 자동 조달 — HTTP 는 가짜, ffmpeg 는 진짜. 진짜 claude CLI·Openverse 를 부르지 않는다."""
from __future__ import annotations

import json
import shutil
import struct
import sys
import wave
from functools import partial
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import gate, net  # noqa: E402
from studio.agents import schemas as S  # noqa: E402
from studio.director.plan import clean_sound_gags  # noqa: E402
from studio.edit.grammar import PARAMS, directed_sfx, gag_category, gag_events  # noqa: E402
from studio.media.ffmpeg import FFmpeg  # noqa: E402
from studio.sound import fetch as F  # noqa: E402
from studio.sound.library import Sound, SoundLibrary  # noqa: E402

CC_ZERO = '<a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0</a>'
CC_BY = '<a href="https://creativecommons.org/licenses/by/4.0/">BY</a>'
CC_NC = '<a href="https://creativecommons.org/licenses/by-nc/4.0/">BY-NC</a>'


def wav_bytes(path: Path, *, lead=0.3, sec=0.5, freq=300.0, amp=0.6, decay=3.0, sr=48000) -> None:
    t = np.arange(int(sec * sr)) / sr
    x = np.concatenate([np.zeros(int(lead * sr)), amp * np.sin(2 * np.pi * freq * t) * np.exp(-decay * t)])
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(struct.pack(f"<{len(x)}h", *(int(v * 32767) for v in x)))


def row(i, title, lic="cc0", ms=900, tags=("wood", "thud"), creator="kim"):
    return {"id": f"id-{i}", "title": title, "url": f"https://cdn.test/{i}.wav", "foreign_landing_url": f"https://src.test/{i}",
            "license": lic, "license_version": "4.0" if lic != "cc0" else "1.0", "duration": ms, "filesize": 5000, "creator": creator,
            "source": "freesound", "tags": [{"name": t} for t in tags],
            "attribution": f'"{title}" by {creator} is licensed under CC BY 4.0.' if lic == "by" else ""}


class Http:
    """net.request 대역: 검색·원문 페이지·다운로드를 흉내 내고 어떤 주소를 불렀는지 남긴다."""

    def __init__(self, results, pages=None, tone=None, mixkit=""):
        self.results, self.pages, self.tone, self.calls, self.mixkit = results, pages or {}, tone or {}, [], mixkit
        self.fail = None

    def __call__(self, url, params=None, headers=None, timeout=30.0, dst=None, rounds=4):
        self.calls.append(url)
        if self.fail == "down":
            raise net.NetError("api.openverse.org 연결 실패")
        if self.fail == 429 and "openverse" in url:
            return net.Response(429, b"{}", {"Retry-After": "0"})
        if "openverse" in url:
            return net.Response(200, json.dumps({"results": self.results}).encode())
        if "mixkit.co/free-sound-effects" in url:
            return net.Response(self.fail if self.fail == 403 else 200, self.mixkit.encode())
        if "src.test" in url:
            return net.Response(200, self.pages.get(url, CC_ZERO).encode())
        dst.parent.mkdir(parents=True, exist_ok=True)
        wav_bytes(dst, **self.tone.get(url, {}))
        return net.Response(200, b"", {}, "fake", url)


@pytest.fixture
def ff(monkeypatch):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg 없음")
    monkeypatch.setattr(F, "SEARCH_GAP", 0.0)
    monkeypatch.setattr(F, "MIXKIT_GAP", 0.0)
    return FFmpeg()


def lib_of(*sounds, tmp=None):
    lib = SoundLibrary(root=tmp or Path("."), manifest=Path("없음.json"))
    lib.sfx = list(sounds)
    return lib


def need(idea="heavy wood thud", queries=("wood thud",), kind="thud"):
    return F.Need(gag_category(idea), list(queries), idea, kind)


def fetcher(lib, ff, tmp, **kw):
    return F.Fetcher(lib, ff, cache=tmp / "cache", user_dir=tmp / "sfx", **kw)


def mixkit_item(i, title, sec="0:01", tags=("Wood", "Thud")):
    links = "".join(f'<a class="meta-links__link" data-x="link" href="/free-sound-effects/{t.lower()}/">{t}</a>' for t in tags)
    return (f'<div class="item-grid__item"><div data-audio-player-preview-url-value="https://assets.mixkit.co/active_storage/sfx/{i}/{i}-preview.mp3" '
            f'data-audio-player-item-id-value="{i}"></div><h2 class="item-grid-card__title">\n  {title}\n</h2>{links}'
            f'<div class="item-grid-sfx-preview__meta-time" data-test-id="duration">\n {sec}\n</div></div>')


def test_mixkit_is_fetched_without_a_license_page_when_openverse_is_blocked(tmp_path, ff, monkeypatch):
    http = Http([row(1, "Wood Thud")], pages={"https://src.test/1": CC_NC},
                mixkit=mixkit_item(7, "Wood thud") + mixkit_item(8, "Wood thud long", "0:12") + mixkit_item(9, "Wood thud song", tags=("Music",)))
    monkeypatch.setattr(net, "request", http)
    lib = lib_of()
    fetcher(lib, ff, tmp_path).run([need()])
    s = next(x for x in lib.sfx)
    assert (s.title, s.license_class, s.attribution, s.source) == ("Wood thud", "A", "", "mixkit")
    assert not any("/8-preview" in u or "/9-preview" in u for u in http.calls)       # 8초 이상·음악 태그는 받지 않는다
    assert any("/discover/wood-thud/" in u for u in http.calls)


def test_mixkit_empty_phrase_falls_back_to_last_word_and_403_stops_knocking(tmp_path, ff, monkeypatch):
    http = Http([])
    monkeypatch.setattr(net, "request", http)
    f = fetcher(lib_of(), ff, tmp_path)
    assert f._search_mixkit("rubber stamp") == []
    assert [u.rsplit("/discover/")[1] for u in http.calls] == ["rubber-stamp/", "stamp/", "rubber/"]
    http.calls.clear()
    http.fail = 403
    assert f._search_mixkit("door knock") == [] and f.index["blocked"]["mixkit.co"]
    assert len(http.calls) == 1 and f._search_mixkit("paper tear") == [] and len(http.calls) == 1


def test_gag_downloads_measures_trims_and_never_touches_nc_or_mismatch(tmp_path, ff, monkeypatch):
    http = Http([row(1, "Wood Thud"), row(2, "Wood Thud NC", "by-nc"), row(3, "Wood Thud stale"), row(4, "Wood Thud long")],
                pages={"https://src.test/3": CC_NC}, tone={"https://cdn.test/4.wav": {"sec": 9.0, "decay": 0.0}})
    monkeypatch.setattr(net, "request", http)
    lib = lib_of()
    fetcher(lib, ff, tmp_path).run([need()])
    assert not any("cdn.test/2." in u or "cdn.test/3." in u for u in http.calls)     # NC·원문 불일치는 받지 않는다
    s = next(x for x in lib.sfx)
    assert (s.title, s.license_class, s.attribution, s.source) == ("Wood Thud", "A", "", "openverse")
    assert F.measure(np.zeros(100), 48000) is None
    from studio.media.mix import decode
    x = decode(ff, s.path).mean(axis=1)
    assert F.measure(x, 48000)["lead"] < 0.03                                        # 앞 무음 0.3초가 잘렸다
    index = json.loads((tmp_path / "cache" / "index.json").read_text(encoding="utf-8"))
    assert "불일치" in index["files"]["id-3"]["rejected"] and index["files"]["id-4"]["rejected"] == "너무 김"
    assert not (tmp_path / "cache" / "raw").exists()


def test_cc_by_credit_and_gate_d9(tmp_path, ff, monkeypatch):
    monkeypatch.setattr(net, "request", Http([row(1, "Wood Thud", "by")], pages={"https://src.test/1": CC_BY}))
    lib = lib_of()
    fetcher(lib, ff, tmp_path).run([need()])
    s = lib.sfx[0]
    assert s.license_class == "C" and s.attribution == '"Wood Thud" by kim is licensed under CC BY 4.0. https://src.test/1'
    assert gate.d9_license([(s.path.name, s.license_class)]).ok


def test_page_license_must_be_same_kind_not_just_prefix(tmp_path, ff, monkeypatch):
    """Openverse 'by' 인데 원문이 BY-SA(커먼즈 바닥글 등) — 'CC-BY-' 앞글자만 보면 통과해 틀린 크레딧이 나갔다."""
    by_sa = '<a href="https://creativecommons.org/licenses/by-sa/4.0/">BY-SA</a>'
    http = Http([row(1, "Wood Thud", "by")], pages={"https://src.test/1": by_sa})
    monkeypatch.setattr(net, "request", http)
    lib = lib_of()
    fetcher(lib, ff, tmp_path).run([need()])
    assert lib.sfx == [] and not any("cdn.test" in u for u in http.calls)
    index = json.loads((tmp_path / "cache" / "index.json").read_text(encoding="utf-8"))
    assert "CC-BY-SA" in index["files"]["id-1"]["rejected"]


def test_by_without_creator_and_sa_are_refused(tmp_path, ff, monkeypatch):
    http = Http([row(1, "Wood Thud", "by", creator=""), row(2, "Wood Thud", "by-sa")])
    monkeypatch.setattr(net, "request", http)
    logs = []
    lib = lib_of()
    fetcher(lib, ff, tmp_path, log=logs.append).run([need()])
    assert lib.sfx == [] and any("찾지 못해" in x for x in logs) and not any("cdn.test" in u for u in http.calls)


def test_ai_picks_by_text_and_may_reject(tmp_path, ff, monkeypatch):
    monkeypatch.setattr(net, "request", Http([row(1, "Wood Thud a"), row(2, "Wood Thud b")]))
    seen = []
    lib = lib_of()
    f = fetcher(lib, ff, tmp_path, pick=lambda t: seen.append(t) or [{"request": 1, "candidate": 2, "reason": "x"}])
    f.run([need()])
    assert lib.sfx[0].title == "Wood Thud b" and "어택" in seen[0] and "밝기" in seen[0]
    lib2 = lib_of()
    f2 = fetcher(lib2, ff, tmp_path, pick=lambda t: pytest.fail("같은 목록은 다시 묻지 않는다"))
    f2.run([need()])
    assert lib2.sfx[0].title == "Wood Thud b"
    lib3 = lib_of()
    fetcher(lib3, ff, tmp_path / "n", pick=lambda t: [{"request": 1, "candidate": -1, "reason": "없음"}]).run([need()])
    assert lib3.sfx == []


def test_ai_failure_falls_back_to_score_and_needs_text_match(tmp_path, ff, monkeypatch):
    monkeypatch.setattr(net, "request", Http([row(1, "ocean ambience", tags=("sea",)), row(2, "Wood Thud")]))
    def boom(_):
        raise RuntimeError("no ai")
    lib = lib_of()
    fetcher(lib, ff, tmp_path, pick=boom).run([need()])
    assert [s.title for s in lib.sfx] == ["Wood Thud"]


@pytest.mark.parametrize("fail", ["down", 429])
def test_network_problems_never_raise(tmp_path, ff, monkeypatch, fail):
    http = Http([row(1, "Wood Thud")])
    http.fail = fail
    monkeypatch.setattr(net, "request", http)
    monkeypatch.setattr(F, "Fetcher", partial(F.Fetcher, cache=tmp_path / "cache", user_dir=tmp_path / "sfx"))
    lib = lib_of()
    F.run(lib, {"sound_gags": [{"sound_idea": "wood thud", "type": "thud", "queries": ["wood thud"]}]}, [], ff)
    assert lib.sfx == []


def test_blocked_source_page_means_no_download_and_no_more_knocks(tmp_path, ff, monkeypatch):
    class Blocked(Http):
        def __call__(self, url, **kw):
            if "src.test" in url:
                self.calls.append(url)
                return net.Response(403)
            return super().__call__(url, **kw)
    http = Blocked([row(i, "Wood Thud") for i in range(5)])
    monkeypatch.setattr(net, "request", http)
    lib = lib_of()
    logs = []
    fetcher(lib, ff, tmp_path, log=logs.append).run([need()])
    assert lib.sfx == [] and not any("cdn.test" in u for u in http.calls) and sum("src.test" in u for u in http.calls) == 1
    assert lib.failed == ["heavy wood thud(출처 확인 불가)"] and any("뺀 후보 4개" in x for x in logs)   # 조용히 빠지지 않는다
    fetcher(lib_of(), ff, tmp_path).run([need()])
    assert sum("src.test" in u for u in http.calls) == 1                 # 다음 작업도 한동안 두드리지 않는다


def test_blocked_source_leaves_slots_to_other_sources(tmp_path, ff, monkeypatch):
    """Freesound 가 막혀도 다른 출처(wikimedia_audio)의 후보가 뒤에 있으면 그것을 확인해 쓴다."""
    rows = [row(i, "Wood Thud") for i in range(5)] + [{**row(9, "Wood Thud wiki"), "foreign_landing_url": "https://wiki.test/9"}]

    class Blocked(Http):
        def __call__(self, url, **kw):
            if "src.test" in url:
                self.calls.append(url)
                return net.Response(403)
            if "wiki.test" in url:
                self.calls.append(url)
                return net.Response(200, CC_ZERO.encode())
            return super().__call__(url, **kw)
    http = Blocked(rows)
    monkeypatch.setattr(net, "request", http)
    lib = lib_of()
    fetcher(lib, ff, tmp_path).run([need()])
    assert [s.title for s in lib.sfx] == ["Wood Thud wiki"] and sum("src.test" in u for u in http.calls) == 1


def test_order_user_folder_then_library_then_openverse(tmp_path, ff, monkeypatch):
    http = Http([row(1, "Wood Thud")])
    monkeypatch.setattr(net, "request", http)
    (tmp_path / "sfx").mkdir()
    wav_bytes(tmp_path / "sfx" / "wood_thud_big.wav")
    lib = lib_of()
    fetcher(lib, ff, tmp_path).run([need()])
    assert lib.sfx[0].source == "user" and lib.sfx[0].license_class == "A" and http.calls == []
    shutil.rmtree(tmp_path / "sfx")
    own = Sound("s", "impact", tmp_path / "w.wav", title="Wood Thud Heavy", license_class="A", source="mixkit")
    lib2 = lib_of(own)
    fetcher(lib2, ff, tmp_path).run([need()])
    assert lib2.sfx[-1].source == "mixkit" and lib2.sfx[-1].category == need().category and http.calls == []


def test_needs_cover_gags_and_short_categories_only():
    full = [Sound(f"p{i}", "pop", Path(f"{i}"), license_class="A", source="x") for i in range(3)]
    plan = {"sound_gags": [{"sound_idea": "ferry horn", "type": "literal", "queries": []}, {"sound_idea": "", "type": "silence_beat"}],
            "graphics": [{"template": "keyword"}, {"template": "chapter"}], "studio": {"treatment": {"segments": [{"sfx": "none"}]}}}
    out = {n.category: n for n in F.needs_for(plan, [], lib_of(*full))}
    assert set(out) == {gag_category("ferry horn"), "pop", "page_turn"}
    assert (out["pop"].count, out["page_turn"].count) == (0, 3) and out[gag_category("ferry horn")].queries == ["ferry horn"]


def test_same_file_not_reused_while_alternatives_exist(tmp_path):
    lib = lib_of(*[Sound(str(i), "pop", tmp_path / f"{i}.wav", source="x", license_class="A") for i in range(3)])
    picks = [lib.pick("pop", seed=0).path for _ in range(3)]
    assert len(set(picks)) == 3
    lib2 = lib_of(Sound("a", "pop", tmp_path / "a.wav", source="x", license_class="A"), Sound("u", "pop", tmp_path / "u.wav", source="user", license_class="A"))
    assert lib2.pick("pop", seed=0).source == "user"


def test_cache_cap_evicts_oldest_but_keeps_this_job(tmp_path, ff, monkeypatch):
    monkeypatch.setattr(F, "CAP_BYTES", 10)
    old = tmp_path / "cache" / "old.flac"
    old.parent.mkdir()
    old.write_bytes(b"x" * 100)
    monkeypatch.setattr(net, "request", Http([row(1, "Wood Thud")]))
    lib = lib_of()
    fetcher(lib, ff, tmp_path).run([need()])
    assert not old.exists() and lib.sfx[0].path.exists()


def _utt_times():
    return {1: (10.0, 12.0), 2: (40.0, 42.0), 3: (45.0, 47.0)}


def test_gag_events_anchor_cap_and_missing_file():
    idea = "wood thud"
    cat = gag_category(idea)
    gs = [{"seg": 1, "anchor": "after_seg", "sound_idea": idea, "pre_silence_s": 0.5, "type": "thud", "why": "w"},
          {"seg": 2, "anchor": "after_seg", "sound_idea": "", "pre_silence_s": 0.7, "type": "silence_beat", "why": "w"},
          {"seg": 3, "anchor": "graphic_landing", "sound_idea": "other", "type": "mickey", "why": "w"}]
    ev = gag_events(gs, _utt_times(), [], [], None, {cat})
    assert [(e["t"], e["category"]) for e in ev] == [(12.0, cat)]        # 60초 안 둘째는 뒤로 밀리고, 착지 없는 셋째는 빠진다
    assert ev[0]["pre"] == 0.5 and ev[0]["gain_db"] == PARAMS["sfx_gain"]["gag"]
    assert gag_events(gs[:1], _utt_times(), [], [], None, set()) == []   # 파일을 못 구한 소리는 자리를 차지하지 않는다
    out = directed_sfx([], [(12.5, "pop")], total=100.0, gags=ev)
    assert [(e["category"], e["gain_db"]) for e in out] == [(cat, PARAMS["sfx_gain"]["gag"])]   # 근처의 다른 소리를 밀어낸다
    from studio.edit.grammar import gag_dips
    beat = [{"t": 30.0, "category": "", "pre": 0.7, "prio": 4}]
    assert gag_dips(out, ev + beat) == [(11.5, 12.0), pytest.approx((29.3, 30.0))]
    held = directed_sfx([], [], total=100.0, gags=ev, holds=[(11.0, 13.0)])
    assert held == [] and gag_dips(held, ev + beat) == [pytest.approx((29.3, 30.0))]   # 홀드로 빠진 소리 자리에 음악 구멍을 내지 않는다


def test_plan_keeps_valid_gags_only_and_schema_requires_keys():
    raw = [{"seg": 1, "anchor": "word", "anchor_word": "쿵", "type": "thud", "sound_idea": "wood thud", "queries": ["wood thud", "쿵"], "pre_silence_s": 9, "why": "기대→어긋남"},
           {"seg": 99, "type": "thud", "sound_idea": "x", "why": "y"}, {"seg": 2, "type": "thud", "sound_idea": "한글", "why": "y"},
           {"seg": 2, "type": "thud", "sound_idea": "x", "why": ""}, {"seg": 2, "type": "silence_beat", "sound_idea": "x", "why": "y"}]
    out = clean_sound_gags(raw, [1, 2])
    assert [(g["seg"], g["sound_idea"]) for g in out] == [(1, "wood thud"), (2, "")]
    assert out[0]["pre_silence_s"] == 1.0 and out[0]["queries"] == ["wood thud"] and clean_sound_gags(out, [1, 2]) == out
    item = S.TREATMENT["properties"]["sound_gags"]["items"]
    assert item["additionalProperties"] is False and set(item["required"]) == set(item["properties"])


def test_pipeline_uses_fetched_gag_and_carries_cc_by_credit(tmp_path, monkeypatch):
    """stage_sound 이 조달기를 부르고, 믹스가 위트 소리를 넣고 CC BY 문구를 업로드 정보로 보낸다."""
    from types import SimpleNamespace

    from studio import pipeline as P
    from studio.edit.grammar import EditDecisions
    from studio.util import CancelToken
    cat = gag_category("wood thud")
    snd = Sound("ov", cat, tmp_path / "a.flac", source="openverse", attribution="credit text", license_class="C")
    lib = lib_of(snd)
    seen = {}
    monkeypatch.setattr(P, "fetch_sfx", lambda *a, **k: seen.update(a=a, k=k))
    monkeypatch.setattr(P, "mix", lambda *a, **k: seen.update(cues=k["sfx"]) or {})
    pl = P.Pipeline.__new__(P.Pipeline)
    pl.spec = SimpleNamespace(sfx=True, music=False, bgm="")
    pl.work, pl.cancel, pl.log, pl.studio = tmp_path, CancelToken(), lambda s: None, None
    pl.settings, pl.ff, pl.sounds, pl._sound_lock = SimpleNamespace(), SimpleNamespace(ffmpeg="ffmpeg"), lib, __import__("threading").Lock()
    pl.plan_long, pl.plan_shorts = {}, []
    lib._full = True
    pl.stage_sound()
    assert seen["a"][0] is lib and seen["k"]["download"] is True
    ed = EditDecisions(sfx=[{"t": 5.0, "category": cat, "gain_db": -12}])
    pl.masters = [{"short": False, "total": 10.0, "edit": ed, "voice": "v.wav"}]
    pl._ears_obj = SimpleNamespace(hear_mix=lambda mix, **k: {"note": "ok"}, dead="")
    pl._mix_all()
    assert seen["cues"][0].path == str(snd.path) and pl.masters[0]["sfx_credits"] == ["credit text"]
    assert pl.masters[0]["ears"] == {"note": "ok"}            # 👂 믹스 듣기는 렌더 옆 믹스 작업에서 미리
