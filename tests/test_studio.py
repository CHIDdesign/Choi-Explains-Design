"""AI 스튜디오 · 스톡 · 모션 · 자막 강조 단위 테스트(네트워크·API 불필요)."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.agents import schemas as S  # noqa: E402
from studio.agents.studio import AGENTS, merge_plan, parse_spec, studio_system_prompt  # noqa: E402
from studio.director.plan import normalize_long, spec_settle_time, time_graphics  # noqa: E402
from studio.models import Span, TimeMap, Utterance, Word  # noqa: E402
from studio.stock.base import StockCandidate, StockError  # noqa: E402
from studio.stock.coverr import Coverr  # noqa: E402
from studio.stock.pexels import pick_video_file  # noqa: E402
from studio.stock.pixabay import Pixabay  # noqa: E402
from studio.stock.providers import StockHub, interleave  # noqa: E402
from studio.stock.research import StockResearcher, contact_sheet, request_key  # noqa: E402
from studio.stock.unsplash import Unsplash  # noqa: E402
from studio.text.captions import build_cues, one_em_per_cue  # noqa: E402

EXAMPLES = json.loads((ROOT / "prompts" / "examples" / "motion_examples.json").read_text(encoding="utf-8"))


def _utts() -> list[Utterance]:
    out, t = [], 0.0
    texts = ["디자인은 질문에서 시작합니다", "점들이 가까우면 한 무리로 보입니다", "학생들은 해결책부터 그립니다",
             "어포던스라는 말을 아시나요", "결국 좋은 질문이 먼저입니다"]
    for i, text in enumerate(texts):
        words = []
        for w in text.split():
            words.append(Word(w, t, t + 0.45))
            t += 0.5
        out.append(Utterance(id=i, start=words[0].start, end=words[-1].end, text=text, asr_text=text, words=words))
        t += 2.0
    return out


def _schema_ok(schema: dict) -> None:
    """구조화 출력 제약: 모든 object 에 additionalProperties=false + 모든 속성 required."""
    if schema.get("type") == "object":
        assert schema.get("additionalProperties") is False, schema
        assert set(schema["required"]) == set(schema["properties"]), schema
        for v in schema["properties"].values():
            _schema_ok(v)
    if schema.get("type") == "array":
        _schema_ok(schema["items"])


def test_agent_schemas_valid_for_structured_outputs():
    for a in AGENTS.values():
        _schema_ok(a.schema)
    assert S.QA["properties"]["issues"]["items"]["properties"]["action"]["enum"][-2:] == ["revise_scene", "revise_card"]


def test_studio_system_prompt_includes_skills_and_dsl():
    sp = studio_system_prompt()
    for needle in ("총괄 감독", "모션 DSL", "MotionSpec", "그래픽 템플릿 카탈로그", "자막"):
        assert needle in sp, needle
    for key in AGENTS:
        if key == "shorts":  # 숏폼 PD 는 기존 task_shorts.md + 감독의 숏폼 아이디어를 쓴다
            continue
        assert (ROOT / "prompts" / "agents" / f"{AGENTS[key].prompt}.md").exists(), key


def test_parse_spec_tolerates_fences():
    spec = EXAMPLES["proximity"]
    assert parse_spec(json.dumps(spec))["elements"]
    assert parse_spec("```json\n" + json.dumps(spec) + "\n```")["elements"]
    assert parse_spec("not json") is None


def test_merge_plan_builds_long_plan_with_motion_and_stock():
    results = {
        "director": {"logline": "L", "structure": [{"title": "들어가며", "start_seg": 0, "end_seg": 2, "purpose": ""}],
                     "hook_segs": [0], "title_card_seg": 1, "music": {"mood": "calm", "notes": ""},
                     "beats": [], "caption_direction": "", "notes_for_team": "", "audience": "", "tone": ""},
        "editor": {"drop": [{"seg": 4, "reason": "반복"}], "punch": [{"seg": 4, "word": "결국"}], "pacing_notes": ""},
        "motion": {"graphics": [], "scenes": [
            {"start_seg": 1, "end_seg": 1, "start_word": "", "layout": "fullscreen", "title": "근접성",
             "spec_json": json.dumps(EXAMPLES["proximity"]), "reason": ""},
            {"start_seg": 2, "end_seg": 2, "start_word": "", "layout": "split", "title": "깨짐", "spec_json": "{oops",
             "reason": ""}]},
        "stock": {"requests": [{"start_seg": 2, "end_seg": 2, "start_word": "", "kind": "video", "query_en": "hand sketch",
                                "query_ko": "스케치", "layout": "fullscreen", "purpose": "p", "must_show": ""}]},
        "captions": {"emphasis": [{"seg": 3, "word": "어포던스라는", "type": "term"}], "notes": ""},
        "copy": {"titles": ["t"], "description": "d", "hashtags": [], "tags": [], "thumbnail_texts": ["x"],
                 "pinned_comment": "q"},
    }
    logs: list[str] = []
    raw_long, raw_shorts = merge_plan(results, log=logs.append)
    assert any("올바르지 않아" in m for m in logs)
    tpl = [g["template"] for g in raw_long["graphics"]]
    assert tpl == ["motion", "broll"], tpl
    assert raw_long["captions"] == {}                      # 자막 모양은 템플릿 고정, 디자이너는 강조어만
    assert raw_shorts == {"shorts": []}
    utts = _utts()
    plan = normalize_long(raw_long, utts, [])
    assert {"seg": 3, "word": "어포던스라는", "kind": "highlight", "type": "term"} in plan["emphasis"]
    assert plan["graphics"][0]["spec"]["elements"]
    assert plan["graphics"][1]["stock"]["query_en"] == "hand sketch"
    assert plan["chapters"][0] == {"seg": 0, "title": "들어가며"}


def test_time_graphics_motion_spec_and_broll_rules():
    utts = _utts()
    tm = TimeMap([Span(0.0, utts[-1].end + 6.0)])
    total = tm.duration
    motion = {"template": "motion", "layout": "fullscreen", "start_seg": 1, "end_seg": 1, "start_word": "",
              "title": "근접성", "subtitle": "", "body": "", "items": [], "title_b": "", "items_b": [], "highlight": -1,
              "author": "", "source": "", "image": "", "reason": "", "spec": EXAMPLES["proximity"]}
    broll_missing = dict(motion, template="broll", start_seg=3, end_seg=3, spec=None,
                         stock={"kind": "video", "query_en": "x", "query_ko": "", "purpose": "", "must_show": ""})
    broll_ok = dict(broll_missing, start_seg=4, end_seg=4, src="broll/v1.mp4", kind="video", credit="A / Pexels")
    timed = time_graphics([motion, broll_missing, broll_ok], utts, tm, total=total, min_start=0.0)
    by_t = {g.template: g for g in timed}
    assert "motion" in by_t and by_t["motion"].data["spec"]["elements"]
    assert by_t["motion"].end - by_t["motion"].start >= min(spec_settle_time(EXAMPLES["proximity"]) + 1.2, 12) - 0.01
    # 소재 없는 B-roll 은 버리고, 있는 B-roll 은 말보다 조금 먼저(0.3초) 들어간다(참고 채널: 화면이 말보다 먼저)
    brolls = [g for g in timed if g.template == "broll"]
    assert len(brolls) == 1 and brolls[0].data["src"] == "broll/v1.mp4" and brolls[0].data["credit"] == "A / Pexels"
    assert utts[4].start - 0.35 <= brolls[0].start <= utts[4].start - 0.25


def test_caption_emphasis_types_and_one_per_cue():
    words = [Word("어포던스라는", 0.0, 0.5), Word("말을", 0.5, 0.8), Word("세", 0.9, 1.1), Word("가지로", 1.1, 1.5)]
    em = {(0.0, "어포던스라는"): "term", (0.9, "세"): "number"}
    cues = build_cues([words], emphasis=em)
    ems = [w.get("em") for c in cues for line in c["lines"] for w in line if w.get("em")]
    assert ems == ["term"], ems  # 한 큐에 하나(전문용어 우선)
    # 이전 형식(set)도 계속 동작
    cues2 = build_cues([words[:2]], emphasis={(0.0, "어포던스라는")})
    assert cues2[0]["lines"][0][0]["em"] is True
    c = [{"lines": [[{"text": "a", "em": "keyword"}, {"text": "1", "em": "number"}]]}]
    one_em_per_cue(c)
    assert [w.get("em") for w in c[0]["lines"][0]] == [None, "number"]


def test_long_captions_max_16_chars_per_line():
    words = [Word(w, i * 0.4, i * 0.4 + 0.35) for i, w in enumerate(
        "좋은 디자인은 결국 사용자를 향한 좋은 질문에서 시작한다고 저는 생각합니다".split())]
    for c in build_cues([words]):
        for line in c["lines"]:
            text = " ".join(w["text"] for w in line)
            assert len(text.replace(" ", "")) <= 17, text


def test_pick_video_file_prefers_1080():  # Pexels
    files = [{"link": "a", "file_type": "video/mp4", "width": 3840, "height": 2160, "fps": 30},
             {"link": "b", "file_type": "video/mp4", "width": 1920, "height": 1080, "fps": 30},
             {"link": "c", "file_type": "video/mp4", "width": 640, "height": 360, "fps": 30}]
    assert pick_video_file(files)["link"] == "b"


def test_contact_sheet_is_jpeg():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (320, 180), (200, 10, 10)).save(buf, "JPEG")
    data = contact_sheet([("C1 5s", buf.getvalue()), ("C2", None), ("C3 photo", b"broken")])
    im = Image.open(io.BytesIO(data))
    assert im.format == "JPEG" and im.size[0] > 1000


class FakePexels:
    name = "Pexels"
    videos = photos = korean = True

    def __init__(self):
        self.calls: list[tuple] = []
        self.remaining = 199

    def search_videos(self, q, **k):
        self.calls.append(("v", q, k.get("locale", "")))
        if q in ("nothing", "없음"):
            return []
        return [StockCandidate("video", 10 + i, f"https://pexels.com/v/{i}", "", f"dl{i}", 1920, 1080, 6.0, f"작가{i}")
                for i in range(3)]

    def search_photos(self, q, **k):
        self.calls.append(("p", q, k.get("locale", "")))
        return [StockCandidate("photo", 90, "https://pexels.com/p/90", "", "dlp", 3000, 2000, 0, "사진가")]


def test_stock_researcher_pick_fallback_and_cache(tmp_path, monkeypatch):
    px = FakePexels()
    public = tmp_path / "public"
    fetched: list[int] = []

    def fake_fetch(self, c):
        fetched.append(c.id)
        dst = public / "broll" / f"{c.kind[0]}{c.id}.bin"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"x")
        return {"src": f"broll/{dst.name}", "kind": c.kind, "credit": c.credit, "url": c.url, "author_url": ""}

    monkeypatch.setattr(StockResearcher, "_fetch", fake_fetch)
    monkeypatch.setattr(StockResearcher, "_thumb", lambda self, c: None)
    picks_seen: list[str] = []

    def pick(text, sheets):
        picks_seen.append(text)
        assert len(sheets) == 3 and all(s[2] == "image/jpeg" for s in sheets)
        return [{"request": 1, "candidate": 2, "reason": ""}, {"request": 2, "candidate": -1, "reason": "없음"},
                {"request": 3, "candidate": 1, "reason": ""}]

    def g(kind, qe, qk=""):
        return {"template": "broll", "stock": {"kind": kind, "query_en": qe, "query_ko": qk, "purpose": "", "must_show": ""}}

    lists = [[g("video", "hands"), g("video", "abstract"), {"template": "list"}], [g("video", "nothing", "없음")]]
    r = StockResearcher(StockHub([px]), ff=None, work=tmp_path, public=public, pick=pick)
    r.run(lists)
    assert picks_seen and "R3" in picks_seen[0]
    # 1번: 두 번째 후보, 2번: 에이전트가 거절 → 제외, 3번: 영상 없음 → 한국어 → 사진으로 확장
    assert [x["template"] for x in lists[0]] == ["broll", "list"]
    assert lists[0][0]["src"] == "broll/v11.bin" and lists[0][0]["credit"] == "작가1 / Pexels"
    assert lists[1][0]["kind"] == "photo" and lists[1][0]["kenburns"] == "in"
    assert ("v", "없음", "ko-KR") in px.calls and ("p", "nothing", "") in px.calls
    assert len(r.credits) == 2
    # 재실행: 캐시 → 검색·선택·다운로드 없음
    px.calls.clear()
    fetched.clear()
    lists2 = [[g("video", "hands"), g("video", "abstract")]]
    r2 = StockResearcher(StockHub([px]), ff=None, work=tmp_path, public=public, pick=lambda *a: 1 / 0)
    r2.run(lists2)
    assert px.calls == [] and fetched == [] and len(lists2[0]) == 1
    assert request_key(lists2[0][0]["stock"]) in json.loads((tmp_path / "stock.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 무료 스톡 제공처(응답 예시는 각 API 문서의 필드 구조를 따름)
# ---------------------------------------------------------------------------

PIXABAY_VIDEOS = {"total": 2, "totalHits": 2, "hits": [
    {"id": 125, "pageURL": "https://pixabay.com/videos/id-125/", "type": "film", "tags": "sketch, hand", "duration": 12,
     "videos": {"large": {"url": "https://cdn.pixabay.com/v/large.mp4", "width": 1920, "height": 1080, "size": 1,
                          "thumbnail": "https://cdn.pixabay.com/v/large.jpg"},
                "medium": {"url": "https://cdn.pixabay.com/v/medium.mp4", "width": 1280, "height": 720, "size": 1,
                           "thumbnail": "https://cdn.pixabay.com/v/medium.jpg"}},
     "user_id": 7, "user": "Coverr-Free-Footage"},
    {"id": 126, "pageURL": "p", "duration": 9, "user": "b", "user_id": 8,
     "videos": {"large": {"url": "", "width": 0, "height": 0, "thumbnail": ""},
                "medium": {"url": "https://cdn.pixabay.com/v/m2.mp4", "width": 1280, "height": 720,
                           "thumbnail": "https://cdn.pixabay.com/v/m2.jpg"}}},
    {"id": 127, "pageURL": "p", "duration": 2, "user": "short", "videos": {}},
]}
PIXABAY_PHOTOS = {"hits": [
    {"id": 195893, "pageURL": "https://pixabay.com/photos/id-195893/", "tags": "desk", "previewURL": "prev",
     "webformatURL": "https://pixabay.com/get/x_640.jpg", "largeImageURL": "https://pixabay.com/get/x_1280.jpg",
     "imageWidth": 4000, "imageHeight": 2250, "user_id": 1, "user": "Josch13"}]}


def test_pixabay_parsing_and_korean_query(monkeypatch):
    seen: list[tuple] = []

    def fake_get(self, url, params, headers=None):
        seen.append((url, dict(params)))
        return PIXABAY_VIDEOS if url.endswith("/videos/") else PIXABAY_PHOTOS

    monkeypatch.setattr(Pixabay, "_get_json", fake_get)
    px = Pixabay("k")
    vids = px.search_videos("sketch", per_page=6)
    assert [v.id for v in vids] == ["125", "126"]  # 2초짜리는 제외
    assert vids[0].download.endswith("large.mp4") and vids[0].width == 1920 and vids[0].thumb.endswith("large.jpg")
    assert vids[1].download.endswith("m2.mp4") and vids[1].provider == "Pixabay"
    assert vids[0].credit == "Coverr-Free-Footage / Pixabay"
    px.search_videos("스케치", per_page=6, locale="ko-KR")
    assert seen[-1][1]["lang"] == "ko" and seen[-1][1]["video_type"] == "film" and seen[-1][1]["safesearch"] == "true"
    photos = px.search_photos("desk")
    assert photos[0].download.endswith("_1280.jpg") and photos[0].width == 1280 and photos[0].height == 720
    assert seen[-1][1]["image_type"] == "photo" and seen[-1][1]["orientation"] == "horizontal"


def test_unsplash_parsing_credit_and_download_tracking(monkeypatch):
    data = {"total": 2, "results": [
        {"id": "abc", "width": 6000, "height": 4000, "alt_description": "desk",
         "urls": {"raw": "https://images.unsplash.com/photo-1?ixid=x", "small": "https://images.unsplash.com/s"},
         "links": {"html": "https://unsplash.com/photos/abc", "download_location": "https://api.unsplash.com/photos/abc/download"},
         "user": {"name": "Jane Doe", "links": {"html": "https://unsplash.com/@jane"}}},
        {"id": "plus1", "premium": True, "urls": {"raw": "r"}, "links": {}, "user": {}}]}
    monkeypatch.setattr(Unsplash, "_get_json", lambda self, url, params, headers=None: data)
    u = Unsplash("key")
    got = u.search_photos("desk")
    assert [c.id for c in got] == ["abc"]  # Unsplash+ 제외
    c = got[0]
    assert c.download == "https://images.unsplash.com/photo-1?ixid=x&w=2400&q=85&fm=jpg"
    assert c.credit == "Photo by Jane Doe on Unsplash"
    assert u.search_photos("책상", locale="ko-KR") == []  # 한국어 검색은 승인 앱만
    hits: list[str] = []
    monkeypatch.setattr(u.session, "get", lambda url, **k: hits.append(url))
    u.register_download(c)
    assert hits == ["https://api.unsplash.com/photos/abc/download"]
    assert u.auth["Authorization"] == "Client-ID key"


def test_coverr_parsing_skips_vertical():
    data = {"page": 0, "pages": 1, "total": 2, "hits": [
        {"id": "S1YbPl1NfI", "title": "Sketching", "thumbnail": "t.jpg", "poster": "p.jpg", "is_vertical": False,
         "duration": 11.6, "max_width": 2048, "max_height": 1152,
         "urls": {"mp4": "a.mp4", "mp4_download": "d.mp4", "mp4_preview": "pv.mp4"}},
        {"id": "vert", "is_vertical": True, "duration": 10, "urls": {"mp4": "v.mp4"}}]}
    cv = Coverr("k")
    cv._get_json = lambda url, params, headers=None: data
    got = cv.search_videos("sketch")
    assert len(got) == 1 and got[0].download == "d.mp4" and got[0].credit == "Coverr" and got[0].key == "covS1YbPl1NfI"


class _Prov:
    def __init__(self, name, n, videos=True, photos=True, fail=False, korean=False):
        self.name, self.videos, self.photos, self.korean, self.remaining = name, videos, photos, korean, None
        self.n, self.fail, self.calls = n, fail, []

    def _mk(self, kind, q, k):
        self.calls.append((kind, q, k.get("locale", "")))
        if self.fail:
            raise StockError("bad key")
        return [StockCandidate(kind, f"{self.name}{i}", "", "", "", 1920, 1080, provider=self.name) for i in range(self.n)]

    def search_videos(self, q, **k):
        return self._mk("video", q, k)

    def search_photos(self, q, **k):
        return self._mk("photo", q, k)


def test_stock_hub_interleaves_and_disables_bad_provider():
    a, b, bad = _Prov("Pixabay", 4, korean=True), _Prov("Coverr", 4, photos=False), _Prov("X", 3, fail=True)
    logs: list[str] = []
    hub = StockHub([a, bad, b], log=logs.append)
    got = hub.search({"kind": "video", "query_en": "desk", "query_ko": "책상"}, 6)
    assert [c.provider for c in got] == ["Pixabay", "Coverr"] * 3
    assert "X" in hub.disabled and any("제외" in m for m in logs)
    hub.search({"kind": "video", "query_en": "desk"}, 6)
    assert len(bad.calls) == 1  # 한 번 실패한 제공처는 다시 부르지 않는다
    # 영상이 없으면 사진으로 넓히고, 한국어 검색은 한국어 지원 제공처만
    empty_v = _Prov("Pixabay", 0, korean=True)
    hub2 = StockHub([empty_v, _Prov("Unsplash", 2, videos=False)])
    got2 = hub2.search({"kind": "video", "query_en": "q", "query_ko": "큐"}, 6)
    assert {c.kind for c in got2} == {"photo"} and ("video", "큐", "ko-KR") in empty_v.calls
    assert interleave([[], got2], 1) == got2[:1]


def test_stock_hub_from_settings_order():
    from studio.settings import Settings
    s = Settings()
    s.unsplash_access_key, s.pixabay_api_key, s.coverr_api_key = "u", "p", "c"
    assert StockHub.from_settings(s).names == ["Pixabay", "Coverr", "Unsplash", "Openverse"]
    # 키가 하나도 없어도 Openverse(CC 사진)는 항상 켜져 있다
    assert StockHub.from_settings(Settings()).names == ["Openverse"]
    off = Settings()
    off.keyless_stock = False
    assert StockHub.from_settings(off).names == []


def test_normalize_long_is_idempotent_with_script_tags():
    """저장된 plan.json 을 다시 정규화해도 같아야 재실행 때 검수·렌더 캐시가 맞는다."""
    from studio.models import Tag
    utts = _utts()
    tags = [Tag(kind="keyword", args=["질문"], raw="[강조: 질문]", pos=0, utt_id=0),
            Tag(kind="zoom", args=[], raw="[줌]", pos=0, utt_id=2),
            Tag(kind="cut", args=[], raw="[컷]", pos=0, utt_id=3),
            Tag(kind="list", args=["조건", "구체적 ; 열린"], raw="[목록: 조건 | 구체적 ; 열린]", pos=0, utt_id=1)]
    raw = {"summary": "", "hook_segs": [0], "title_card_seg": 1, "chapters": [], "emphasis": [], "drop": [],
           "youtube": {}, "music": {}, "graphics": [
               {"template": "keyword", "layout": "split", "start_seg": 0, "end_seg": 0, "title": "질문", "reason": "감독"}]}
    first = normalize_long(raw, utts, tags)
    second = normalize_long(json.loads(json.dumps(first)), utts, tags)
    assert json.dumps(first, sort_keys=True, ensure_ascii=False) == json.dumps(second, sort_keys=True, ensure_ascii=False)
    assert sum(1 for e in second["emphasis"] if e["kind"] == "punch") == 1
    assert sum(1 for d in second["drop"] if d["seg"] == 3) == 1
