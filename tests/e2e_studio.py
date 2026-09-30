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
    if agent == "colorist":  # 전사본 없이 비교 시트 한 장만 받는다
        assert n_images == 1, n_images
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
    if agent == "director":
        return {"title": "질문이 먼저다", "logline": "좋은 디자인은 좋은 질문에서 시작한다", "audience": "디자인 전공 1~2학년",
                "tone": "차분한 강의", "bgm_mood": "minimal", "shorts_bgm_mood": "upbeat",
                "structure": [{"title": "들어가며", "start_seg": first, "end_seg": s_wide, "purpose": "문제 제기"},
                              {"title": "문제를 다시 정의하기", "start_seg": s_skip, "end_seg": last, "purpose": "원리"}],
                "beats": [{"start_seg": s_dots, "end_seg": s_gestalt, "intent": "name_concept", "visual": "motion",
                           "idea": "점들이 모이며 무리로 보임", "priority": 1},
                          {"start_seg": s_sketch, "end_seg": s_sketch, "intent": "example", "visual": "stock_video",
                           "idea": "스케치하는 손", "priority": 2}],
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
            "pacing_notes": "차분하게"}
    if agent == "motion":
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
        return {"requests": [
            {"start_seg": s_sketch, "end_seg": s_sketch, "start_word": "", "kind": "video", "query_en": "student sketching",
             "query_ko": "스케치하는 학생", "layout": "fullscreen", "purpose": "해결책부터 그리는 모습", "must_show": "손과 연필"},
            {"start_seg": s_trip, "end_seg": s_trip, "start_word": "", "kind": "photo", "query_en": "question mark notebook",
             "query_ko": "질문", "layout": "split", "purpose": "질문의 상징", "must_show": "물음표"}]}
    if agent == "stock_pick":
        n = len(re.findall(r"^- R\d+", instruction, re.M))
        return {"picks": [{"request": i + 1, "candidate": 2, "reason": "톤이 맞음"} for i in range(n)]}
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
                            "hashtags": ["#디자인"], "why": "통념 반박", "score": 8},
                           {"title": "넓게", "hook_type": "everyday_why", "hook_title": "디자인은 왜\n넓게 시작할까",
                            "hook_highlight": "넓게", "cold_open_seg": -1, "segments": seg2, "graphics": [],
                            "emphasis": [], "cta": "", "loop_line": "", "caption": "넓게", "hashtags": ["#디자인"],
                            "why": "일상의 왜", "score": 7}]}
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
    if agent == "motion_revise":
        spec = json.loads(re.search(r"현재 spec_json:\n(\{.*\})\n", instruction, re.S).group(1))
        for el in spec["elements"]:
            if el.get("type") == "text":
                el["size"] = min(40, float(el.get("size", 7)) * 1.2)
        return {"spec_json": json.dumps(spec, ensure_ascii=False), "changes": "텍스트 20% 확대"}
    raise AssertionError(agent)


def agent_of(schema: dict) -> str:
    props = set(schema.get("properties", {}))
    for key, marker in (("director", "logline"), ("editor", "moments"), ("motion", "scenes"), ("stock", "requests"),
                        ("colorist", "strength"),
                        ("stock_pick", "picks"), ("captions", "emphasis"), ("shorts", "shorts"),
                        ("copy", "pinned_comment"), ("art_director", "verdict"), ("card_revise", "html"),
                        ("motion_revise", "changes")):
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
    spec = pl.JobSpec(video=str(video), topic="좋은 디자인은 질문에서 시작한다 — 디자인 전공 1~2학년 대상", episode="01",
                      script=SCRIPT, fetch_broll=False, thumbnails=False, short_max_sec=40, verify_edit=False, qa_rounds=2,
                      direction="모션 장면은 크게")
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
              "motion_revise", "colorist"):
        assert a in agents, f"{a} 호출 없음: {agents}"
    assert agents[0] == "colorist" and agents[1] == "director", agents   # 색보정 → 기획
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
    assert all(p.get("style") == "glide" for p in lp["punches"]), lp["punches"]
    covers = [(g["start"], g["end"]) for g in lp["graphics"] if g["layout"] in ("fullscreen", "split")]
    assert not any(a - 0.4 <= p["t"] <= b + 0.4 for p in lp["punches"] for a, b in covers), (lp["punches"], covers)
    assert lp["callouts"] and "질문" in lp["callouts"][0]["text"], lp["callouts"]
    assert lp["callouts"][0]["label"] == "핵심" and lp["callouts"][0]["highlight"] == "질문"
    assert any(t["type"] in ("wipe", "leak") for t in lp["transitions"]), lp["transitions"]
    assert lp["voice"] is None and lp["sfx"] == []          # 음향은 FFmpeg 에서 따로 믹스
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
