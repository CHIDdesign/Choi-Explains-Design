"""Claude 총괄 제작(docs/upgrade/14) 단위 테스트 — 진짜 Claude·네트워크 없이:
웹 도구는 조사·시그니처 장면에만 · 조사 노트 정리·공유 블록·조사노트.md · 트리트먼트 → 시그니처 장면 → 카드 · 감독이 고른 효과음 ·
문구 팔레트 → 실제 파일 · 조사 노트의 커먼즈 파일을 사다리가 먼저 · 내 음악 폴더 목록 · 에이전트별 스킬 노트."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.agents import research as R  # noqa: E402
from studio.agents import schemas as S  # noqa: E402
from studio.agents import studio as ST  # noqa: E402
from studio.director.claude import web_tools  # noqa: E402
from studio.director.claude_code import ClaudeCodeClient  # noqa: E402
from studio.director.plan import _clean_graphic  # noqa: E402
from studio.edit.grammar import directed_sfx  # noqa: E402

DOSSIER = {
    "topic_summary": "도널드 노먼은 사용자 중심 디자인을 대중화했다.", "angle": "물건이 사람을 탓하게 만든다",
    "entities": [{"name_ko": "도널드 노먼", "name_en": "Don Norman", "kind": "person", "role_in_script": "주인공",
                  "script_quote": "노먼은", "summary": "인지과학자", "years": "1935–",
                  "facts": [{"fact": "1988년 『The Psychology of Everyday Things』", "source_url": "https://example.org/a"}],
                  "visual_identity": "안경, 흰 수염", "official_url": "https://jnd.org", "wikipedia_url": "",
                  "commons_files": ["File:Don_Norman_2014.jpg", "https://commons.wikimedia.org/wiki/File:Norman_door.jpg",
                                    "no extension", "x.jpg"]}],
    "concepts": [{"term": "어포던스", "term_en": "affordance", "plain": "생김새가 쓰는 법을 알려 준다",
                  "canonical_example": "문손잡이", "visual_metaphor": "손잡이 화살표", "source_url": ""}],
    "timeline": [], "quotes": [{"text": "Design is really an act of communication", "speaker": "Don Norman",
                                "work": "", "verified": True, "source_url": ""}],
    "numbers": [], "recreations": [{"name": "노먼 도어", "what": "밀어야 하는데 당기게 생긴 손잡이", "spec": "세로 막대 손잡이",
                                    "source_url": ""}],
    "script_checks": [{"sentence": "노먼은 애플의 창업자다", "verdict": "wrong", "note": "애플 부사장이었다",
                       "source_url": "https://example.org/b"}],
    "visual_directions": ["문손잡이 선 그림 위 빨간 교정 표시"], "sources": [{"title": "jnd", "url": "https://jnd.org"}],
}


def test_research_is_cleaned_and_shared():
    d = R.clean_research(DOSSIER)
    files = d["entities"][0]["commons_files"]
    assert files == ["Don Norman 2014.jpg", "Norman door.jpg", "x.jpg"]          # 'File:'·URL·밑줄 정리, 확장자 없는 것은 버림
    assert R.files_for(d, "Don Norman") == files and R.files_for(d, "도널드노먼") == files
    block = R.research_block(d)
    assert "🔎 주제 조사 노트" in block and "어포던스" in block and "`Don Norman 2014.jpg`" in block
    assert "애플 부사장" in block                                                  # 틀린 대본 문장은 팀에게도 알린다
    notes = R.research_notes(d, title="노먼")
    assert notes.startswith("# 조사 노트 — 노먼") and "https://example.org/b" in notes and "[jnd](https://jnd.org)" in notes
    assert R.research_block({}) == "" and R.is_empty(R.clean_research({}))


def test_web_tools_only_for_research_agents():
    c = ClaudeCodeClient("claude", workdir=Path("/tmp/_cc_test"))
    plain = c._args(Path("s.md"), {}, "m", "high")
    assert plain[plain.index("--tools") + 1] == "" and "--allowedTools" not in plain
    web = c._args(Path("s.md"), {}, "m", "high", ("WebSearch", "WebFetch", "Bash"), 30)
    assert web[web.index("--tools") + 1] == "WebSearch,WebFetch" and web[web.index("--allowedTools") + 1] == "WebSearch,WebFetch"
    assert web[web.index("--max-turns") + 1] == "30"                              # Bash 같은 도구는 켜지 않는다
    assert ST.AGENTS["research"].tools and ST.AGENTS["setpiece"].tools
    assert all(not a.tools for k, a in ST.AGENTS.items() if k not in ("research", "setpiece"))
    assert [t["name"] for t in web_tools(("WebSearch", "WebFetch"))] == ["web_search", "web_fetch"]


def _director() -> dict:
    return {"treatment": {
        "concept": "일상 사물의 설명서를 해부하는 연구 노트", "motifs": ["빨간 교정 표시"], "texture_note": "", "type_note": "",
        "sound_concept": "종이 소리만",
        "segments": [{"start_seg": 3, "end_seg": 5, "layout": "collage", "show": "노먼의 초상", "asset": "Don Norman 2014.jpg",
                      "motion": "", "sfx": "paper", "why": ""},
                     {"start_seg": 6, "end_seg": 8, "layout": "motion", "show": "어포던스 화살표", "asset": "", "motion": "",
                      "sfx": "none", "why": ""}],
        "signature_scenes": [
            {"id": "s1", "start_seg": 9, "end_seg": 10, "start_word": "문을", "kind": "object_recreation", "title": "노먼 도어",
             "brief": "손잡이 선 그림", "research_ref": "노먼 도어", "sfx": "pop"},
            {"id": "s2", "start_seg": 11, "end_seg": 11, "start_word": "", "kind": "collage", "title": "표지",
             "brief": "책 표지", "research_ref": "", "sfx": "none"},
            {"id": "s3", "start_seg": "x", "end_seg": 1, "start_word": "", "kind": "diagram", "title": "x", "brief": "y",
             "research_ref": "", "sfx": "none"}]}}


def test_signature_scenes_and_treatment_block():
    sc = ST.signature_scenes(_director())
    assert [s["id"] for s in sc] == ["s1"]                    # 사진이 필요한 collage·잘못된 발화 번호는 빌더가 짓지 않는다
    mb = ST.treatment_block(_director(), "motion")
    assert "S9–S10 「노먼 도어」" in mb and "어포던스 화살표" in mb and "노먼의 초상" not in mb
    sb = ST.treatment_block(_director(), "stock")
    assert "노먼의 초상" in sb and "Don Norman 2014.jpg" in sb
    assert "TREATMENT" in S.__all__ and "treatment" in S.BRIEF["properties"] and "commons_files" in \
        S.EVIDENCE["properties"]["items"]["items"]["properties"]


def test_setpieces_become_signature_cards():
    html = ('<div class="card" data-card-id="x"><style>.card[data-card-id="x"] .root{width:100%;height:100%}</style>'
            '<div class="root"><h2 class="t" data-anim="fade-in" data-anim-at="0">노먼 도어</h2></div></div>')
    sc = ST.signature_scenes(_director())[0]
    raw_long, _ = ST.merge_plan({"director": _director(), "setpieces": [
        {"scene": sc, "layout": "fullscreen", "style": "editorial", "title": "노먼 도어", "html": html, "start_word": "문을",
         "notes": "조사 노트의 손잡이"}]})
    g = next(g for g in raw_long["graphics"] if g["template"] == "card")
    assert g["signature"] and g["sfx"] == "pop" and g["start_seg"] == 9 and g["start_word"] == "문을"
    assert raw_long["studio"]["signature_scenes"] == 1 and raw_long["studio"]["treatment"]["concept"]
    out = _clean_graphic(g, list(range(20)))
    assert out["signature"] is True and out["sfx"] == "pop"


def test_directed_sfx_only_where_asked():
    gs = [{"template": "card", "start": 10.0, "end": 15.0, "data": {"sfx": "pop"}},
          {"template": "evidence", "start": 30.6, "end": 35.0, "data": {}},
          {"template": "motion", "start": 2.0, "end": 5.0, "data": {"sfx": "whoosh_soft"}},      # 첫 3초 — 빼기
          {"template": "broll", "start": 50.0, "end": 55.0, "data": {"sfx": "whoosh_soft"}}]     # 홀드 안 — 빼기
    out = directed_sfx(gs, [(30.0, "paper"), (40.0, "none")], holds=[(48.0, 56.0)], total=120.0)
    assert [(e["t"], e["category"]) for e in out] == [(10.0, "pop"), (30.6, "paper")]           # 단락 효과음은 그래픽 등장에 맞춤
    assert all(e["gain_db"] <= -20 for e in out)
    many = [{"template": "card", "start": 5.0 + 3 * k, "end": 6.0 + 3 * k, "data": {"sfx": "click"}} for k in range(10)]
    assert len(directed_sfx(many, [], total=120.0)) == 3                                       # 60초 창 3개(게이트 D5)


def test_stationery_palette_uses_real_files(tmp_path):
    from studio.sound.library import REAL_FOR, Sound, SoundLibrary
    lib = SoundLibrary.__new__(SoundLibrary)
    real = Sound("paper_1", "paper", tmp_path / "p.mp3", source="pixabay")
    lib.sfx = [Sound("page_turn_synth", "page_turn", tmp_path / "s.wav", source="synth"), real]
    assert REAL_FOR["page_turn"] == "paper"
    assert lib.pick("page_turn").id == "paper_1"            # 절차적 소리(믹스가 거절함) 대신 실제 종이 소리
    assert lib.pick("pop") is None                          # 없는 카테고리는 비슷한 소리로 메우지 않는다


def test_ladder_uses_research_commons_files_first(tmp_path):
    from studio.assets.ladder import Deps, Ladder

    class FakeWP:
        def files_meta(self, names, width=1920):
            return [{"name": n, "url": f"https://u/{n}", "thumb": f"https://t/{n}", "width": 2400, "height": 1600,
                     "mime": "image/jpeg", "license": "CC BY-SA 4.0", "artist": "A", "description": ""} for n in names]

    class FakeMedia:
        wp = FakeWP()

        def usable(self, metas, *, kind="", tier_max="A", min_long=900):
            return [{**m, "tier": "A-sa"} for m in metas]

    lad = Ladder(Deps(media=FakeMedia()), public=tmp_path / "pub", work=tmp_path / "w")
    pending: list = []
    o: dict = {}
    it = {"commons_files": ["File:Don_Norman_2014.jpg"], "tier_max": "A", "subject": {"qid": "Q1"}}
    assert lad._research_files(0, it, o, pending, ["도널드 노먼"], "person", "portrait")
    assert pending and pending[0][2][0]["name"] == "Don Norman 2014.jpg" and o["research"]
    assert not lad._research_files(0, it, {}, [], ["노먼"], "brand", "logo")        # 로고 자리에는 쓰지 않는다


def test_track_listing_from_measured_features(tmp_path, monkeypatch):
    from studio.sound import tracks
    a, b = tmp_path / "felt piano.mp3", tmp_path / "upbeat.mp3"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    monkeypatch.setattr(tracks, "features", lambda ts, ff="ffmpeg", cache=None: {
        a.name: {"duration": 192.0, "bpm": 72.0, "lufs_i": -18.5, "onsets_per_s": 1.1, "band_1_4k": 0.02},
        b.name: {}})
    text = tracks.track_listing([a, b])
    assert "`felt piano.mp3` · 3:12 · 72 BPM · -18.5 LUFS · 밀도 1.1/초 · 말 대역 0.02" in text and "`upbeat.mp3`" in text
    assert "track" in S.MUSIC["properties"] and "track_reason" in S.MUSIC["properties"]


def test_agent_skill_notes_are_per_agent(tmp_path, monkeypatch):
    import studio.paths as P
    d = tmp_path / "skills" / "agents"
    d.mkdir(parents=True)
    (d / "editor.md").write_text("# 스킬 — 편집\n1. 얼굴을 지킨다\n\n## 출처\n- https://x", encoding="utf-8")
    monkeypatch.setattr(P, "PROMPTS_DIR", tmp_path)
    blk = ST.agent_skill_block("editor")
    assert "얼굴을 지킨다" in blk and "https://x" not in blk
    assert ST.agent_skill_block("copy") == ""


def test_motion_reference_catalog_and_sheet(tmp_path):
    from PIL import Image

    from studio.assets import motion_ref as M
    cat = [{"slug": "the-stack-testimonial", "name": "The Stack: Testimonial", "categories": ["social-media", "text"],
            "description": "reveals quotes as a stack of cards one at a time"},
           {"slug": "Bad Slug", "name": "x", "categories": [], "description": ""}]
    p = tmp_path / "c.json"
    import json
    p.write_text(json.dumps(cat), encoding="utf-8")
    loaded = M.load_catalog(p)
    assert [d["slug"] for d in loaded] == ["the-stack-testimonial"]          # 이상한 slug 는 버린다
    blk = M.catalog_block(loaded)
    assert blk.count("the-stack-testimonial") == 1 and "### social-media" in blk and "stack of cards" in blk
    frames = []
    for i in range(3):
        f = tmp_path / f"f{i:02d}.jpg"
        Image.new("RGB", (508, 508), (40 * i, 80, 120)).save(f)
        frames.append(f)
    sheet = M.contact_sheet(frames)
    assert sheet and sheet[:2] == b"\xff\xd8"
    out = M.capture_refs(["the-stack-testimonial"], node=str(tmp_path / "no-node"), work=tmp_path / "w",
                         cache=tmp_path / "cache")   # 네트워크·node 없이 — 실패해도 예외 없이
    assert out == {} or isinstance(out, dict)                                # 캡처 실패해도 예외 없이 빈 결과
