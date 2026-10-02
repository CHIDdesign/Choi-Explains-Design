"""AI 스튜디오 전체 흐름 E2E — 가짜 Claude API + 가짜 Pixabay·Unsplash 서버(네트워크·API 키 불필요).

🎬 총괄 감독 → (✂️🎨🎞🔤📱✍️ 병렬) → 🎞 Pixabay·Unsplash 검색·비전 선택·다운로드 → 🧐 아트 디렉터 스틸 검수
→ 🎨 장면 수정 → Remotion 렌더 → 내보내기까지 실제로 실행한다.

    python tests/e2e_studio.py [--browser /path/to/chrome] [--keep]
"""
from __future__ import annotations

import argparse
import copy
import os
import io
import json
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import e2e_synthetic as base  # noqa: E402
from e2e_synthetic import make_media, make_words  # noqa: E402
from studio import pipeline as pl  # noqa: E402
from studio.settings import Settings  # noqa: E402
from studio.stock import pixabay as pixabay_mod  # noqa: E402
from studio.stock import unsplash as unsplash_mod  # noqa: E402

# 모션 장면·스톡 컷이 들어갈 여유 구간(대본 태그 없는 문장들)을 끝부분 앞에 추가
EXTRA = [
    ("점들이 가까이 모이면 우리는 하나의 무리로 봅니다.", 1.0),
    ("이것을 게슈탈트의 근접성 원리라고 부릅니다.", 1.2),
    ("생각보다 많은 곳에 숨어 있는 원리입니다.", 1.4),
    ("학생들의 책상 위에는 늘 스케치가 가득합니다.", 1.2),
    ("하지만 그 스케치가 무엇을 위한 것인지는 잘 묻지 않습니다.", 1.2),
    ("질문 없는 스케치는 방향 없는 여행과 같습니다.", 1.4),
    ("그래서 저는 늘 연필보다 질문을 먼저 듭니다.", 1.2),
]
base.SPOKEN[-1:-1] = EXTRA
SCRIPT = base.SCRIPT.replace("결국 좋은 디자인은", " ".join(t for t, _ in EXTRA) + "\n결국 좋은 디자인은")

LOCK = threading.Lock()
CALL_LOG = Path(os.environ.get("FAKE_CLAUDE_LOG", "/tmp/fake_claude_calls.jsonl"))


def load_calls() -> list[dict]:
    """가짜 API 서버·가짜 Claude Code CLI 가 공통으로 남기는 호출 기록."""
    if not CALL_LOG.exists():
        return []
    return [json.loads(x) for x in CALL_LOG.read_text(encoding="utf-8").splitlines() if x.strip()]


def record_call(entry: dict) -> None:
    with LOCK, CALL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
EXAMPLES = json.loads((ROOT / "prompts" / "examples" / "motion_examples.json").read_text(encoding="utf-8"))
CARD_EXAMPLES = json.loads((ROOT / "prompts" / "examples" / "card_examples.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 가짜 Claude
# ---------------------------------------------------------------------------

def _sse(text: str) -> bytes:
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [],
            "stop_reason": None, "stop_sequence": None,
            "usage": {"input_tokens": 1000, "output_tokens": 1, "cache_read_input_tokens": 800}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                           "usage": {"output_tokens": 50}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return b"".join(f"event: {e}\ndata: {json.dumps(d, ensure_ascii=False)}\n\n".encode() for e, d in events)


def _segs(body: dict) -> dict[int, str]:
    text = "\n".join(b.get("text", "") for b in body["messages"][0]["content"] if b.get("type") == "text")
    return {int(m.group(1)): m.group(2) for m in re.finditer(r"^\[S(\d+) \|[^\]]*\] (.+)$", text, re.M)}


def _seg_with(segs: dict[int, str], word: str) -> int:
    return next((k for k, v in segs.items() if word in v), min(segs))


def fake_answer(agent: str, body: dict, n_images: int, instruction: str) -> dict:
    if agent == "cut_editor":  # 대본 + 컷 초안을 받는다(그림 없음)
        assert n_images == 0 and "# 전사와 컷 초안" in json.dumps(body, ensure_ascii=False)
        return {"utterances": [], "removals": [], "notes": "초안 그대로"}
    if agent == "colorist":  # 전사본 없이 비교 시트 + 원본 스코프 시트 두 장
        assert n_images == 2, n_images
        return {"look": "warm_film", "strength": 0.7, "exposure": 0.0, "warmth": 0.05, "saturation": 1.0,
                "reason": "피부가 가장 자연스럽다"}
    segs = _segs(body)
    ids = sorted(segs)
    first, last = ids[0], ids[-1]
    s_wide = _seg_with(segs, "넓게")
    s_skip = _seg_with(segs, "건너뜁니다")
    s_q = _seg_with(segs, "조건")
    s_aff = _seg_with(segs, "어포던스")
    s_dots = _seg_with(segs, "점들이")
    s_gestalt = _seg_with(segs, "게슈탈트")
    s_sketch = _seg_with(segs, "스케치가 가득")
    s_trip = _seg_with(segs, "방향 없는")
    s_ask = _seg_with(segs, "잘 묻지")     # 태그·다른 그래픽이 없는 문장 → 자유 HTML 카드 자리
    s_hidden = _seg_with(segs, "숨어 있는")  # 얼굴 홀드(여운)
    if agent == "director":
        return {"title": "질문이 먼저다", "logline": "좋은 디자인은 좋은 질문에서 시작한다", "audience": "디자인 전공 1~2학년",
                "thesis": "좋은 디자인은 해결책이 아니라 문제 정의에서 갈린다",
                "tone": "차분한 강의", "bgm_mood": "minimal", "shorts_bgm_mood": "upbeat",
                "structure": [{"title": "들어가며", "start_seg": first, "end_seg": s_wide, "purpose": "문제 제기", "claim": ""},
                              {"title": "문제를 다시 정의하기", "start_seg": s_skip, "end_seg": last, "purpose": "원리",
                               "claim": "해결책보다 질문이 먼저다"}],
                "beats": [{"start_seg": s_dots, "end_seg": s_gestalt, "intent": "name_concept", "show": "structure",
                           "function": "name", "visual": "motion", "idea": "점들이 모이며 무리로 보임", "on_screen_text": "근접성",
                           "sequence_id": "", "priority": 1},
                          {"start_seg": s_sketch, "end_seg": s_sketch, "intent": "example", "show": "example",
                           "function": "example", "visual": "stock_video", "idea": "스케치하는 손", "on_screen_text": "",
                           "sequence_id": "q1", "priority": 2}],
                "central_question": "좋은 디자인은 어디에서 시작할까", "payoff_seg": last,
                "sequences": [{"id": "q1", "type": "evidence_stack", "start_seg": s_sketch, "end_seg": s_trip,
                               "claim": "해결책부터 그리는 습관", "shots": [{"seg": s_sketch, "word": "스케치가", "show": "스케치"},
                                                                     {"seg": s_trip, "word": "질문", "show": "물음표"}],
                               "layout": "fullscreen", "audio": "bed", "enter": "on_word", "exit": "on_sentence",
                               "fallback": "single", "priority": 2, "reason": "사례를 쌓는다"}],
                "hook_segs": [first], "title_card_seg": ids[1], "shorts_ideas": [{"segments": ids[-5:], "angle": "통념 반박"}],
                "caption_direction": "절제된 다큐멘터리 톤, 전문용어만 마커", "music": {"mood": "calm piano", "notes": ""},
                "notes_for_team": "화자 중심, 도식은 크게"}
    if agent == "editor":
        s_pencil = _seg_with(segs, "연필보다")   # 그래픽이 없는(얼굴만 보이는) 문장 → 콜아웃 자리
        return {"drop": [], "moments": [
            {"seg": s_pencil, "word": "질문", "kind": "punchline", "intensity": 3, "callout": "연필보다\n질문 먼저",
             "label": "핵심"},
            {"seg": last, "word": "", "kind": "conclusion", "intensity": 2, "callout": "", "label": ""},
            {"seg": s_q, "word": "", "kind": "number", "intensity": 2, "callout": "", "label": ""}],
            # ⚡ 펀치 구간: 핵심 한 방 문장 하나만 — 그 안의 강조는 하드 펀치인(cut)이 된다
            "energy_spans": [{"start_seg": s_pencil, "end_seg": s_pencil, "reason": "핵심 한 방"}],
            # 🙂 얼굴 홀드(여운 문장) · 리듬 · 정점(docs/upgrade/05)
            "holds": [{"start_seg": s_hidden, "end_seg": s_hidden, "reason": "여운"}],
            "rhythm": [{"start_seg": first, "end_seg": s_hidden, "level": "steady", "reason": "설명"},
                       {"start_seg": s_sketch, "end_seg": s_trip, "level": "fast", "reason": "사례"},
                       {"start_seg": s_pencil, "end_seg": last, "level": "slow", "reason": "결론"}],
            "peak_seg": s_pencil,
            # 🎬 오프닝 하이라이트: 숫자 문장 + 결론 문장(첫 두 발화는 앱이 제외한다)
            "highlights": [{"seg": ids[0], "reason": "첫 발화(제외돼야 함)"}, {"seg": s_q, "reason": "숫자"},
                           {"seg": last, "reason": "결론"}],
            "pacing_notes": "차분하게"}
    if agent == "motion":
        # 자료가 먼저, 모션이 나중(13 문서 2-2): 확보 목록 + 재현 요청 + 컨택트 시트를 받는다
        assert "## 확보된 자료" in instruction and "재현 요청" in instruction and n_images == 1, (n_images, instruction[:300])
        spec = copy.deepcopy(EXAMPLES["proximity"])
        card = CARD_EXAMPLES["slam_minimal"]["html"]   # 글자가 적어(35자) 한 문장 안에 끝나는 카드 — 뒤 스톡 사진 자리를 침범하지 않게
        return {"graphics": [], "scenes": [{"start_seg": s_dots, "end_seg": s_gestalt, "start_word": "", "layout": "fullscreen",
                                            "title": "근접성", "spec_json": json.dumps(spec, ensure_ascii=False),
                                            "reason": "모이는 움직임이 곧 설명"}],
                # 🃏 자유 HTML 카드(HyperFrames 규약) — 렌더 전 검사(check)를 거쳐 렌더된다
                "cards": [{"start_seg": s_ask, "end_seg": s_ask, "start_word": "", "layout": "fullscreen", "style": "editorial",
                           "title": "문제를 정의하라", "html": card, "reason": "한 문장 한 방"}]}
    if agent == "card_revise":
        m = re.search(r"```html\n(.*?)\n```", instruction, re.S)
        return {"html": m.group(1) if m else "", "changes": "지적대로 수정"}
    if agent == "stock":
        # 🎞 자료 리서처 v2(EVIDENCE): 화자 자료 · 1차 자료 · 재현 · 스톡 — ④ 자료 폴더 목록과 썸네일 시트를 받는다
        assert "M1 `해결책_스케치.jpg`" in instruction and n_images == 1, (n_images, instruction[:400])
        s_draw = _seg_with(segs, "해결책부터")

        def ev(seg, need, **kw):
            it = {"start_seg": seg, "end_seg": seg, "start_word": "", "claim": "", "need": need, "role": "example",
                  "subject": {"name_ko": "", "name_en": "", "kind": "other", "shot": "subject", "creator_en": "",
                              "year": "", "qid": ""},
                  "source": {"citation": "", "doi": "", "url": "", "as_of": "", "locator": ""},
                  "stock": {"kind": "photo", "query_en": "", "query_ko": ""}, "local_file": "", "must_show": "",
                  "avoid": "", "count": 1, "label": "", "caption": "", "treatment": "hero", "focus": "", "annotations": [],
                  "pair": {"name_ko": "", "name_en": "", "label": ""}, "tier_max": "A", "fallback": "face",
                  "priority": 1, "sequence_id": ""}
            it.update(kw)
            return it
        return {"items": [
            ev(s_sketch, "stock", claim="스케치가 가득한 책상", treatment="full", sequence_id="q1",
               stock={"kind": "video", "query_en": "student sketching", "query_ko": "스케치하는 학생"}, must_show="손과 연필"),
            ev(s_trip, "stock", claim="방향 없는 여행", treatment="pip",
               stock={"kind": "photo", "query_en": "question mark notebook", "query_ko": "물음표 노트"}, must_show="물음표"),
            ev(s_draw, "own_material", claim="해결책부터 그린 스케치", local_file="해결책_스케치.jpg",
               label="해결책부터 그린 손", caption="2학년 과제 · 2024"),
            ev(s_skip, "primary_source", claim="고착 실험", role="proof", treatment="archive_card", fallback="type_card",
               source={"citation": "Jansson & Smith (1991) Design fixation. Design Studies 12(1)", "doi": "", "url": "",
                       "as_of": "", "locator": "예시를 본 뒤 그 형태에 묶인다"}, label="고착 실험"),
            ev(s_gestalt, "code_drawn", claim="근접성 실험 설계", must_show="점 사이 간격을 바꾼 두 판", fallback="code_drawn")],
            "notes": "최종 렌더링 1장이 있으면 좋다"}
    if agent == "stock_pick":
        # 후보 고르기 v2(EVIDENCE_PICK): 0~3점, 2점 이상만 — C1 은 뻔한 스톡(1점 상한)이라 빠지고 C2 가 뽑혀야 한다
        n = len(re.findall(r"^- R\d+", instruction, re.M))
        return {"picks": [{"request": i + 1, "reason": "톤이 맞음", "choices": [
            {"candidate": 1, "score": 3, "main_subject": True, "cliche": True, "shows": "노트북 자판 위 손", "focus_box": []},
            {"candidate": 2, "score": 3, "main_subject": True, "cliche": False, "shows": "손과 연필",
             "focus_box": [0.2, 0.2, 0.5, 0.5]}]} for i in range(n)]}
    if agent == "captions":
        return {"emphasis": [{"seg": s_aff, "word": "어포던스라는", "type": "term"},
                             {"seg": s_q, "word": "세", "type": "number"}],
                "notes": "용어만 마커"}
    if agent == "shorts":
        seg = [i for i in ids if i >= s_skip][:6]
        seg2 = [i for i in ids if i < s_skip][:6]
        return {"shorts": [{"title": "질문", "hook_type": "contrarian", "hook_title": "해결책부터 그리면\n망합니다",
                            "hook_highlight": "", "cold_open_seg": last, "segments": seg, "graphics": [],
                            "emphasis": [{"seg": last, "word": "질문에서"}], "cta": "", "loop_line": "", "caption": "질문",
                            "hashtags": ["#디자인"], "viewer_takeaway": "해결책보다 질문이 먼저다", "why": "통념 반박",
                            "score": 8},
                           # 둘째 편은 다른 구간·8점 이상일 때만 만들어진다(제대로 된 한 편 우선)
                           {"title": "넓게", "hook_type": "everyday_why", "hook_title": "디자인은 왜\n넓게 시작할까",
                            "hook_highlight": "넓게", "cold_open_seg": -1, "segments": seg2, "graphics": [],
                            "emphasis": [], "cta": "", "loop_line": "", "caption": "넓게", "hashtags": ["#디자인"],
                            "viewer_takeaway": "디자인은 넓게 펼친 뒤 좁힌다", "why": "일상의 왜", "score": 8}]}
    if agent == "copy":
        return {"titles": ["디자인 학생 90%가 건너뛰는 단계"], "description": "#디자인 #더블다이아몬드\n요약\n\n{{CHAPTERS}}",
                "hashtags": ["#디자인"], "tags": ["디자인"], "thumbnail_texts": ["질문이 먼저"], "pinned_comment": "여러분은?"}
    if agent == "art_director":
        m = re.search(r"- (g\d+) · motion", instruction)
        rounds = sum(1 for c in load_calls() if c["agent"] == "art_director")
        if m and rounds == 0:
            return {"verdict": "revise", "summary": "모션 장면 글자가 작다",
                    "issues": [{"target": m.group(1), "severity": "medium", "problem": "라벨이 작아 읽기 어렵다",
                                "action": "revise_scene", "new_title": "", "new_body": "", "new_items": [],
                                "new_layout": "", "direction": "라벨 크게"}]}
        return {"verdict": "pass", "summary": "좋음", "issues": []}
    if agent == "timeline_review":
        # 🧐 게이트 E: 검토 시트 전부를 받는다 — 이벤트 목록에 홀드가 있어야 한다
        assert n_images >= 1 and "HOLD" in instruction, (n_images, instruction[:300])
        return {"thesis_read": "좋은 디자인은 질문에서 시작한다",
                "scores": [{"criterion": c, "evidence": ["00:05 화면 예시"], "score": 4}
                           for c in ("follow", "argument", "rhythm", "evidence", "hierarchy", "distinct")],
                "findings": [{"start": "00:20", "end": "00:24", "kind": "no_evidence", "severity": "low", "target": "",
                              "action": "request_owner", "blocking": False, "direction": "스케치 실물 사진을 주세요"}],
                "summary": "대체로 좋음"}
    if agent == "motion_revise":
        spec = json.loads(re.search(r"현재 spec_json:\n(\{.*\})\n", instruction, re.S).group(1))
        for el in spec["elements"]:
            if el.get("type") == "text":
                el["size"] = min(40, float(el.get("size", 7)) * 1.2)
        return {"spec_json": json.dumps(spec, ensure_ascii=False), "changes": "텍스트 20% 확대"}
    raise AssertionError(agent)


def agent_of(schema: dict) -> str:
    props = set(schema.get("properties", {}))
    for key, marker in (("cut_editor", "removals"), ("director", "logline"), ("editor", "moments"), ("motion", "scenes"),
                        ("stock", "requests"), ("stock", "items"),
                        ("colorist", "strength"),
                        ("stock_pick", "picks"), ("captions", "emphasis"), ("shorts", "shorts"),
                        ("copy", "pinned_comment"), ("art_director", "verdict"), ("card_revise", "html"),
                        ("motion_revise", "changes"), ("timeline_review", "thesis_read")):
        if marker in props:
            return key
    return "unknown"


class ClaudeHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        schema = body.get("output_config", {}).get("format", {}).get("schema", {})
        agent = agent_of(schema)
        blocks = body["messages"][0]["content"]
        n_images = sum(1 for b in blocks if b.get("type") == "image")
        instruction = blocks[-1].get("text", "")
        ans = fake_answer(agent, body, n_images, instruction)
        if True:
            record_call({"agent": agent, "images": n_images, "effort": body.get("output_config", {}).get("effort"),
                          "cache": [b.get("cache_control") is not None for b in blocks[:1]]})
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        self.wfile.write(_sse(json.dumps(ans, ensure_ascii=False)))

    def log_message(self, *a):
        pass


# ---------------------------------------------------------------------------
# 가짜 스톡(Pixabay + Unsplash)
# ---------------------------------------------------------------------------

class StockHandler(BaseHTTPRequestHandler):
    """가짜 Pixabay(/pixabay/…) + Unsplash(/unsplash/…) + 파일 서버."""
    base = ""
    files: dict[str, bytes] = {}
    tracked: list[str] = []

    def _json(self, data) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("X-RateLimit-Remaining", "99")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        b = self.base
        if u.path in self.files:
            data = self.files[u.path]
            self.send_response(200)
            self.send_header("content-type", "video/mp4" if u.path.endswith(".mp4") else "image/jpeg")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if u.path.startswith("/pixabay/"):
            assert q.get("key") == ["pb-test"], "Pixabay 키 누락"
            if u.path == "/pixabay/videos/":
                self._json({"total": 3, "totalHits": 3, "hits": [
                    {"id": 1000 + i, "pageURL": f"https://pixabay.com/videos/id-{1000 + i}/", "type": "film",
                     "tags": "sketch", "duration": 4 + i, "user": f"작가{i}", "user_id": i,
                     "videos": {"large": {"url": f"{b}/v.mp4", "width": 1920, "height": 1080, "size": 1,
                                          "thumbnail": f"{b}/thumb{i % 2}.jpg"},
                                "medium": {"url": f"{b}/v.mp4", "width": 1280, "height": 720, "size": 1,
                                           "thumbnail": f"{b}/thumb{i % 2}.jpg"}}} for i in range(3)]})
            else:
                self._json({"total": 3, "totalHits": 3, "hits": [
                    {"id": 2000 + i, "pageURL": f"https://pixabay.com/photos/id-{2000 + i}/", "tags": "question",
                     "webformatURL": f"{b}/thumb{i % 2}.jpg", "largeImageURL": f"{b}/p.jpg", "imageWidth": 2400,
                     "imageHeight": 1600, "user": f"사진가{i}", "user_id": i} for i in range(3)]})
            return
        if u.path.startswith("/unsplash/"):
            assert self.headers.get("Authorization") == "Client-ID us-test", "Unsplash 키 헤더 누락"
            if u.path == "/unsplash/search/photos":
                self._json({"total": 3, "results": [
                    {"id": f"us{i}", "width": 6000, "height": 4000, "alt_description": "question",
                     "urls": {"raw": f"{b}/u.jpg?ixid=1", "small": f"{b}/thumb{(i + 1) % 2}.jpg"},
                     "links": {"html": f"https://unsplash.com/photos/us{i}",
                               "download_location": f"{b}/unsplash/photos/us{i}/download"},
                     "user": {"name": f"Jane {i}", "links": {"html": "https://unsplash.com/@jane"}}} for i in range(3)]})
            elif u.path.endswith("/download"):
                StockHandler.tracked.append(u.path)
                self._json({"url": "ok"})
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *a):
        pass


def _jpeg(color: tuple[int, int, int], size=(1280, 720)) -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", size, color)
    d = ImageDraw.Draw(im)
    for i in range(0, size[0], 80):
        d.line([(i, 0), (i + 300, size[1])], fill=(255, 255, 255), width=6)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def start(handler) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main() -> int:
    global CALL_LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", default="")
    ap.add_argument("--backend", default="claude_code", choices=["claude_code", "api"],
                    help="claude_code = 가짜 Claude Code CLI(tests/fake_claude.py), api = 가짜 API 서버")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--work", default=str(ROOT / "projects" / "_e2e_studio"))
    args = ap.parse_args()
    work = Path(args.work)
    if work.exists() and not args.keep:
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    CALL_LOG = work / "fake_calls.jsonl"
    CALL_LOG.unlink(missing_ok=True)
    os.environ["FAKE_CLAUDE_LOG"] = str(CALL_LOG)

    words, duration = make_words()
    video = work / "source.mp4"
    if not video.exists():
        make_media(video, words, duration)
    clip = work / "stock_src.mp4"
    if not clip.exists():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=1280x720:rate=25:duration=3", "-pix_fmt", "yuv420p", str(clip)], check=True)

    claude = start(ClaudeHandler)
    os.environ["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{claude.server_port}"
    px = start(StockHandler)
    StockHandler.base = f"http://127.0.0.1:{px.server_port}"
    StockHandler.files = {"/v.mp4": clip.read_bytes(), "/p.jpg": _jpeg((40, 60, 90), (2400, 1600)),
                           "/thumb0.jpg": _jpeg((200, 90, 40)), "/thumb1.jpg": _jpeg((30, 120, 80))}
    StockHandler.files["/u.jpg"] = StockHandler.files["/p.jpg"]
    pixabay_mod.API = StockHandler.base + "/pixabay"
    unsplash_mod.API = StockHandler.base + "/unsplash"

    def fake_transcribe(*_a, **_k):
        return {"words": words, "segments": [], "info": {"model": "synthetic", "duration": duration}}
    pl.transcribe = fake_transcribe

    settings = Settings()
    settings.anthropic_api_key = "sk-ant-test"
    settings.pixabay_api_key = "pb-test"
    settings.unsplash_access_key = "us-test"
    settings.projects_dir = str(work)
    settings.render.browser_executable = args.browser
    settings.render.gl = "swangle" if sys.platform != "win32" else "angle"
    settings.render.concurrency = 3
    settings.agent_effort = {"copy": "low"}
    settings.keyless_stock = False       # 테스트는 인터넷(Openverse)에 나가지 않는다
    settings.download_sounds = False     # 이미 받아 둔 효과음·음악만(없으면 절차적 효과음)
    settings.ai_backend = args.backend
    if args.backend == "claude_code":
        # 진짜 Claude Code 대신 가짜 CLI(같은 가짜 답변 로직, 호출은 CALL_LOG 에 기록)
        shim = work / "fake_claude"
        shim.write_text(f"#!/bin/sh\nexec {sys.executable} {ROOT / 'tests' / 'fake_claude.py'} \"$@\"\n")
        shim.chmod(0o755)
        settings.claude_code_path = str(shim)
        os.environ["ANTHROPIC_API_KEY"] = "sk-should-be-stripped"  # 구독 모드에서는 자식 프로세스에 넘어가면 안 된다
    # ④ 자료 폴더(화자 자료) — 자료 리서처가 own_material 로 고르고 사다리가 hero 로 넣는다
    mats = work / "materials"
    mats.mkdir(parents=True, exist_ok=True)
    from PIL import Image, ImageDraw
    sk = Image.new("RGB", (1800, 1200), (238, 232, 220))
    dr = ImageDraw.Draw(sk)
    for i in range(14):
        dr.line([(120 + i * 110, 200), (220 + i * 95, 1000)], fill=(60, 50, 45), width=6)
    dr.ellipse([700, 380, 1100, 780], outline=(232, 104, 44), width=12)
    sk.save(mats / "해결책_스케치.jpg", quality=90)

    # 1차 자료의 서지 확인(Crossref)은 네트워크 없이 — 같은 메타를 돌려주는 가짜
    from studio.assets import scholar as sch_mod
    real_deps = pl.Pipeline._evidence_deps

    class FakeScholar:
        def resolve(self, citation, doi=""):
            return sch_mod._meta({"DOI": "10.1016/0142-694X(91)90003-F", "title": ["Design fixation"],
                                  "author": [{"family": "Jansson"}, {"family": "Smith"}],
                                  "container-title": ["Design Studies"], "issued": {"date-parts": [[1991]]},
                                  "volume": "12", "issue": "1", "page": "3-11"}) if "Jansson" in citation else None

    def deps_with_fake_scholar(self):
        d = real_deps(self)
        d.scholar = FakeScholar()
        return d
    pl.Pipeline._evidence_deps = deps_with_fake_scholar
    spec = pl.JobSpec(video=str(video), topic="좋은 디자인은 질문에서 시작한다 — 디자인 전공 1~2학년 대상", episode="01",
                      script=SCRIPT, fetch_broll=False, thumbnails=False, short_max_sec=40, verify_edit=False, qa_rounds=2,
                      direction="모션 장면은 크게", images_dir=str(mats))
    job = work / "job"
    previews: list[str] = []
    res = pl.Pipeline(spec, settings, job, log=lambda m: print(m, flush=True), eta=pl.Eta(None),
                      preview=lambda _p, cap: previews.append(cap)).run()
    out = Path(res["output"])
    # 진행 화면 미리보기: 색보정 전후 → 검수 장면(라운드별) → 렌더 중 프레임
    print("미리보기:", previews[:2], "…", previews[-2:], f"(총 {len(previews)})")
    assert previews[0].startswith("자동 색보정")
    assert any("검수 1라운드 · 장면 1/" in c for c in previews) and any("검수 2라운드" in c for c in previews)
    assert any(c.startswith("롱폼 렌더링") for c in previews) and any(c.startswith("숏폼 2 렌더링") for c in previews)
    files = sorted(p.name for p in out.iterdir())
    print("\n출력:", json.dumps(files, ensure_ascii=False, indent=1))
    CALLS = load_calls()
    print("에이전트 호출:", json.dumps(CALLS, ensure_ascii=False))

    agents = [c["agent"] for c in CALLS]
    for a in ("director", "editor", "motion", "stock", "captions", "shorts", "copy", "stock_pick", "art_director",
              "motion_revise", "colorist", "cut_editor"):
        assert a in agents, f"{a} 호출 없음: {agents}"
    # 색보정(컬러리스트)은 AI 기획과 동시에 돈다(pipeline.SCHEDULE) — 순서 대신: 총괄 감독이 전문가보다 먼저, 색은 검수 전
    assert agents.index("director") < min(agents.index(a) for a in ("editor", "motion", "stock", "captions", "shorts",
                                                                     "copy")), agents
    assert agents.index("colorist") < agents.index("art_director"), agents
    assert next(c for c in CALLS if c["agent"] == "stock_pick")["images"] == 2
    assert next(c for c in CALLS if c["agent"] == "art_director")["images"] >= 2
    assert next(c for c in CALLS if c["agent"] == "copy")["effort"] == "low"
    assert agents.count("art_director") == 2, agents  # 수정 후 재검수에서 통과

    lp = json.loads((job / "render" / "props_long.json").read_text(encoding="utf-8"))
    assert lp["captionPreset"] == "paper", lp["captionPreset"]        # 채널 템플릿 자막(흰 종이 상자)
    tpl = [g["template"] for g in lp["graphics"]]
    assert "motion" in tpl and "broll" in tpl, tpl
    motion = next(g for g in lp["graphics"] if g["template"] == "motion")
    assert motion["data"]["spec"]["elements"], motion
    # 🃏 자유 HTML 카드: 정리(스코프)·렌더 전 검사 통과·props 에 그대로
    assert "card" in tpl, tpl
    card = next(g for g in lp["graphics"] if g["template"] == "card")
    cid = card["data"]["card"]["id"]   # 카드 스코프 id(card{n}) — 그래픽 id(g{n}) 와 다르다
    assert card["data"]["card"]["html"].startswith('<div class="root">') and card["data"]["card"]["css"].count(f'.card[data-card-id="{cid}"]') > 3, cid
    plan = json.loads((job / "work" / "plan.json").read_text(encoding="utf-8"))
    checks = plan["long"].get("card_checks") or {}
    assert checks and all(v["ok"] for v in checks.values()), checks
    brolls = [g for g in lp["graphics"] if g["template"] == "broll"]
    for g in brolls:
        assert (job / "render" / "public_src" / g["data"]["src"]).exists(), g
        assert "Pixabay" in g["data"]["credit"] or "Unsplash" in g["data"]["credit"], g
    assert any(g["data"]["kind"] == "video" for g in brolls) and any(g["data"]["kind"] == "photo" for g in brolls)
    ems = [w.get("em") for c in lp["captions"] for line in c["lines"] for w in line if w.get("em")]
    assert "term" in ems, ems
    for c in lp["captions"]:
        assert sum(1 for line in c["lines"] for w in line if w.get("em")) <= 1, c
    sp = json.loads((job / "render" / "props_short_1.json").read_text(encoding="utf-8"))
    assert sp["layout"] == "reel" and sp["camera"], sp["layout"]
    assert (job / "render" / "props_short_2.json").exists()
    # 편집 문법 엔진: 부드러운 프레이밍(100↔106%)·글라이드 강조·콜아웃·챕터 전환
    # 젠틀 편집: 프레이밍은 100↔106%(콜아웃 110%)에 느린 푸시(최대 +5%)뿐. 콜아웃 뒤 조각은 원래 푸시가 닿았을 값(예 1.05)에서
    # 이어지므로 정확한 집합이 아니라 범위로 본다
    assert lp["camera"] and all(1.0 <= c["zoom"] <= 1.12 and c["zoomEnd"] <= 1.17 for c in lp["camera"]), lp["camera"]
    # 강조 글라이드: 있으면 glide 뿐이고, 그래픽(전면·분할) 위에는 놓이지 않는다. 몇 개인지는 기획의 그래픽 배치에 따라
    # 0 도 될 수 있다(그래픽 위 · 콜아웃 40초 안의 강조 순간은 건너뛴다)
    # ⚡ 펀치 구간(s_pencil) 안의 강조는 하드 펀치인(cut, +10% 이상), 그 밖은 글라이드뿐
    assert all(p.get("style") in ("glide", "cut") for p in lp["punches"]), lp["punches"]
    hl_dur = next(t["t"] for t in lp["transitions"] if t["type"] == "leak" and t["t"] > 2.0)   # 🎬 하이라이트 → 본편
    # 📋 챕터 정리 보드(있으면)는 펀치 구간·강조 순간을 덮지 않는다 — 이 대본은 2챕터 끝이 펀치 구간이라 건너뛸 수 있다
    for g in lp["graphics"]:
        if g["template"] == "recap":
            assert g["layout"] == "split" and 2 <= len(g["data"]["items"]) <= 4, g
            assert not any(p["style"] == "cut" and g["start"] < p["end"] and g["end"] > p["t"] for p in lp["punches"]), g
    hot = [p for p in lp["punches"] if p["style"] == "cut" and p["t"] >= hl_dur]
    assert len(hot) == 1 and hot[0]["amount"] >= 0.1 and hot[0]["end"] - hot[0]["t"] <= 2.3, lp["punches"]
    assert plan["long"]["energy_spans"] and plan["long"]["energy_spans"][0]["reason"] == "핵심 한 방", plan["long"].get("energy_spans")
    # 시퀀스·리듬·홀드가 계획에 남고(재정규화에도), 품질 게이트가 홀드 보호를 확인했다
    assert plan["long"]["holds"] and plan["long"]["sequences"][0]["id"] == "q1" and plan["long"]["rhythm"], plan["long"].get("holds")
    gate_json = json.loads((job / "work" / "gate.json").read_text(encoding="utf-8"))
    by_gate = {r["id"]: r for r in gate_json["results"]}
    assert gate_json["ok"] and by_gate["A14_hold_guard"]["ok"] and by_gate["B5_internal"]["ok"], gate_json
    # 🧐 게이트 E(타임라인 검수): 통과(가중 4.0) — 검토 필요 딱지 없음
    assert by_gate["E_timeline"]["ok"] and by_gate["E_timeline"]["measured"]["weighted"] == 4.0, by_gate.get("E_timeline")
    assert not (out / "⚠검토필요.md").exists()
    covers = [(g["start"], g["end"]) for g in lp["graphics"] if g["layout"] in ("fullscreen", "split")]
    assert not any(a - 0.4 <= p["t"] <= b + 0.4 for p in lp["punches"] for a, b in covers), (lp["punches"], covers)
    assert lp["callouts"] and "질문" in lp["callouts"][0]["text"], lp["callouts"]
    assert lp["callouts"][0]["label"] == "핵심" and lp["callouts"][0]["highlight"] == "질문"
    assert any(t["type"] in ("wipe", "leak") for t in lp["transitions"]), lp["transitions"]
    assert lp["voice"] is None and lp["sfx"] == []          # 음향은 FFmpeg 에서 따로 믹스
    # 🎬 오프닝 하이라이트: 편집 감독이 고른 문장 2개(첫 발화는 제외)가 본편 앞에 붙고, 본편(타이틀·챕터)은 그만큼 뒤로
    hl = plan["long"]["highlights"]
    assert [h["reason"] for h in hl] == ["숫자", "결론"], hl
    assert 3.0 <= hl_dur <= 20.0, hl_dur
    assert lp["chapters"][0]["start"] == 0.0 or lp["chapters"][0]["start"] >= hl_dur - 0.01, lp["chapters"][:2]
    title_g = next(g for g in lp["graphics"] if g["template"] == "title")   # 타이틀은 본편 훅 뒤 발화에(하이라이트 뒤로 밀림)
    assert hl_dur <= title_g["start"] <= hl_dur + 4.0, (title_g["start"], hl_dur)
    first_src = lp["clips"][0]["srcStart"]
    main_first = next(c for c in lp["clips"] if c["start"] >= hl_dur - 0.01)["srcStart"]
    assert first_src > main_first, (first_src, main_first)                  # 하이라이트는 뒤쪽 문장에서 가져온다
    assert lp["captions"][0]["start"] < hl_dur and lp["captions"][0]["lines"][0][0]["text"], lp["captions"][:1]
    assert any(p["style"] == "cut" and p["t"] < hl_dur for p in lp["punches"]), lp["punches"]   # 조각마다 펀치인
    report_hl = (out / "부가자료" / "편집리포트.md").read_text(encoding="utf-8")
    assert "오프닝 하이라이트" in report_hl
    # 🎬 챕터 카드 부제 = 총괄 감독의 챕터 주장(claim) — 시청자가 '지금 무슨 이야기인지' 안다
    ch2 = next(g for g in lp["graphics"] if g["template"] == "chapter")
    assert ch2["data"]["subtitle"] == "해결책보다 질문이 먼저다", ch2["data"]
    assert plan["long"]["chapters"][1].get("claim") == "해결책보다 질문이 먼저다", plan["long"]["chapters"]
    grade_info = json.loads((job / "work" / "grade.json").read_text(encoding="utf-8"))
    assert grade_info["choice"]["look"] == "warm_film" and grade_info["choice"]["by"] == "ai", grade_info["choice"]
    assert (job / "media" / "grade.cube").exists() and (out / "부가자료" / "색보정_전후.jpg").exists()

    plan = json.loads((job / "work" / "plan.json").read_text(encoding="utf-8"))
    assert plan["long"]["qa"]["rounds"], plan["long"].get("qa")
    assert plan["director"].startswith("AI 스튜디오")
    if args.backend == "claude_code":
        assert "Claude Code" in plan["director"], plan["director"]
        assert all(c.get("backend") == "claude_code" and not c.get("api_key_env") for c in CALLS), CALLS
        assert all(u.get("backend") == "claude_code" for u in plan["usage"]), plan["usage"][:2]
    upload = (out / "업로드정보.txt").read_text(encoding="utf-8")
    assert "Pixabay" in upload and "Unsplash" in upload, upload[-500:]
    assert StockHandler.tracked == ["/unsplash/photos/us0/download"], StockHandler.tracked  # 다운로드 집계
    report = (out / "부가자료" / "편집리포트.md").read_text(encoding="utf-8")
    assert "AI 스튜디오 브리프" in report and "아트 디렉터 검수" in report and "자동 후반 작업" in report
    # 🎞 자료 조달 v2(WP7): 자료 리서처 → 사다리(화자 자료 · 출처 카드 · 스톡 · 재현) → 확보 목록 → 모션 디자이너
    evj = json.loads((job / "work" / "evidence.json").read_text(encoding="utf-8"))
    st = evj["rounds"][0]["summary"]
    assert st["requests"] == 5 and st["rungs"].get("local") == 1 and st["rungs"].get("scholar") == 1 \
        and st["rungs"].get("code_drawn") == 1 and st["rungs"].get("stock") == 2, st
    evs = [g for g in lp["graphics"] if g["template"] == "evidence"]
    print("증거 그래픽:", [(g["id"], g["data"].get("treatment"), round(g["start"], 1), round(g["end"], 1)) for g in evs])
    hero = next(g for g in evs if g["data"].get("treatment") == "hero")
    a0 = hero["data"]["assets"][0]
    assert (job / "render" / "public_src" / a0["src"]).exists() and a0["tier"] == "own", hero
    assert hero["data"]["title"] == "해결책부터 그린 손" and hero["data"]["caption"] == "2학년 과제 · 2024", hero["data"]
    assert any(g["data"].get("archive", {}).get("variant") == "source" for g in evs), evs
    assert (out / "부가자료" / "자료_대장.csv").exists() and "Jansson" in upload, upload[-600:]
    longs = [f for f in files if f.startswith("1_롱폼") and f.endswith(".mp4")]
    shorts = [f for f in files if "숏폼" in f and f.endswith(".mp4")]
    assert len(longs) == 1 and len(shorts) == 2, files
    assert "질문이_먼저다" in longs[0], longs          # 🎬 감독이 정한 제목(파일 이름은 공백 → _)
    from studio.media.ffmpeg import FFmpeg
    from studio.media.mix import measure_lufs
    ff = FFmpeg()
    for f in longs + shorts:
        info = ff.probe(out / f)
        assert info.has_audio and info.has_video, f
        lufs = measure_lufs(ff, out / f)
        assert lufs is not None and abs(lufs + 14) < 1.5, (f, lufs)   # -14 LUFS 마스터
    qa_dir = job / "work" / "qa" / "r1"
    assert any(qa_dir.glob("g*.jpg")), list(qa_dir.iterdir())

    # 재실행: 계획·스톡·검수 캐시 사용(새 Claude 호출 없음) — 렌더 직전 단계까지
    before = len(load_calls())
    logs: list[str] = []
    p2 = pl.Pipeline(spec, settings, job, log=logs.append)
    for fn in (p2.stage_probe, p2.stage_audio, p2.stage_asr, p2.stage_align, p2.stage_face, p2.stage_grade,
               p2.stage_director, p2.stage_proxy, p2.stage_broll, p2.stage_stock, p2.stage_qa):
        fn()
    assert len(load_calls()) == before, load_calls()[before:]
    assert any("이전 검수 결과 사용" in m for m in logs), logs[-10:]
    assert any(g["template"] == "broll" and g.get("src") for g in p2.plan_long["graphics"])
    print("E2E STUDIO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
