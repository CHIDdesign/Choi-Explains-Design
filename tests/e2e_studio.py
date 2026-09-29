"""AI 스튜디오 전체 흐름 E2E — 가짜 Claude API + 가짜 Pixabay·Unsplash 서버(네트워크·API 키 불필요).

🎬 총괄 감독 → (✂️🎨🎞🔤📱✍️ 병렬) → 🎞 Pixabay·Unsplash 검색·비전 선택·다운로드 → 🧐 아트 디렉터 스틸 검수
→ 🎨 장면 수정 → Remotion 렌더 → 내보내기까지 실제로 실행한다.

    python tests/e2e_studio.py [--browser /path/to/chrome] [--keep]
"""
from __future__ import annotations

import argparse
import copy
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

CALLS: list[dict] = []
LOCK = threading.Lock()
EXAMPLES = json.loads((ROOT / "prompts" / "examples" / "motion_examples.json").read_text(encoding="utf-8"))


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
    if agent == "director":
        return {"logline": "좋은 디자인은 좋은 질문에서 시작한다", "audience": "디자인 전공 1~2학년", "tone": "차분한 강의",
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
        return {"drop": [], "punch": [{"seg": last, "word": "결국"}], "pacing_notes": "차분하게"}
    if agent == "motion":
        spec = copy.deepcopy(EXAMPLES["proximity"])
        return {"graphics": [], "scenes": [{"start_seg": s_dots, "end_seg": s_gestalt, "start_word": "", "layout": "fullscreen",
                                            "title": "근접성", "spec_json": json.dumps(spec, ensure_ascii=False),
                                            "reason": "모이는 움직임이 곧 설명"}]}
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
                "preset_long": "documentary", "preset_short": "kinetic", "notes": "용어만 마커"}
    if agent == "shorts":
        seg = [i for i in ids if i >= s_skip][:6]
        return {"shorts": [{"title": "질문", "hook_type": "contrarian", "hook_title": "해결책부터 그리면\n망합니다",
                            "hook_highlight": "망합니다", "cold_open_seg": last, "segments": seg, "graphics": [],
                            "emphasis": [{"seg": last, "word": "질문에서"}], "cta": "", "loop_line": "", "caption": "질문",
                            "hashtags": ["#디자인"], "why": "통념 반박", "score": 8}]}
    if agent == "copy":
        return {"titles": ["디자인 학생 90%가 건너뛰는 단계"], "description": "#디자인 #더블다이아몬드\n요약\n\n{{CHAPTERS}}",
                "hashtags": ["#디자인"], "tags": ["디자인"], "thumbnail_texts": ["질문이 먼저"], "pinned_comment": "여러분은?"}
    if agent == "art_director":
        m = re.search(r"- (g\d+) · motion", instruction)
        with LOCK:
            rounds = sum(1 for c in CALLS if c["agent"] == "art_director")
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
    for key, marker in (("director", "logline"), ("editor", "punch"), ("motion", "scenes"), ("stock", "requests"),
                        ("stock_pick", "picks"), ("captions", "preset_long"), ("shorts", "shorts"),
                        ("copy", "pinned_comment"), ("art_director", "verdict"), ("motion_revise", "changes")):
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
        with LOCK:
            CALLS.append({"agent": agent, "images": n_images, "effort": body.get("output_config", {}).get("effort"),
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
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser", default="")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--work", default=str(ROOT / "projects" / "_e2e_studio"))
    args = ap.parse_args()
    work = Path(args.work)
    if work.exists() and not args.keep:
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)

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
    spec = pl.JobSpec(video=str(video), title="좋은 디자인은 질문에서 시작한다", episode="01", script=SCRIPT,
                      notes="테스트", shorts_count=1, use_claude=True, fetch_broll=False, thumbnails=False,
                      short_max_sec=40, qa_rounds=2, direction="모션 장면은 크게")
    job = work / "job"
    res = pl.Pipeline(spec, settings, job, log=lambda m: print(m, flush=True)).run()
    out = Path(res["output"])
    files = sorted(p.name for p in out.iterdir())
    print("\n출력:", json.dumps(files, ensure_ascii=False, indent=1))
    print("에이전트 호출:", json.dumps(CALLS, ensure_ascii=False))

    agents = [c["agent"] for c in CALLS]
    for a in ("director", "editor", "motion", "stock", "captions", "shorts", "copy", "stock_pick", "art_director",
              "motion_revise"):
        assert a in agents, f"{a} 호출 없음: {agents}"
    assert agents[0] == "director", agents
    assert next(c for c in CALLS if c["agent"] == "stock_pick")["images"] == 2
    assert next(c for c in CALLS if c["agent"] == "art_director")["images"] >= 2
    assert next(c for c in CALLS if c["agent"] == "copy")["effort"] == "low"
    assert agents.count("art_director") == 2, agents  # 수정 후 재검수에서 통과

    lp = json.loads((job / "render" / "props_long.json").read_text(encoding="utf-8"))
    assert lp["captionPreset"] == "documentary", lp["captionPreset"]
    tpl = [g["template"] for g in lp["graphics"]]
    assert "motion" in tpl and "broll" in tpl, tpl
    motion = next(g for g in lp["graphics"] if g["template"] == "motion")
    assert motion["data"]["spec"]["elements"], motion
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
    assert sp["captionPreset"] == "kinetic"

    plan = json.loads((job / "work" / "plan.json").read_text(encoding="utf-8"))
    assert plan["long"]["qa"]["rounds"], plan["long"].get("qa")
    assert plan["director"].startswith("AI 스튜디오")
    upload = next(out.glob("*_업로드정보.txt")).read_text(encoding="utf-8")
    assert "Pixabay" in upload and "Unsplash" in upload, upload[-500:]
    assert StockHandler.tracked == ["/unsplash/photos/us0/download"], StockHandler.tracked  # 다운로드 집계
    report = next(out.glob("*_편집리포트.md")).read_text(encoding="utf-8")
    assert "AI 스튜디오 브리프" in report and "아트 디렉터 검수" in report and "🎨 모션 디자이너" in report
    assert any(f.endswith("_롱폼.mp4") for f in files) and any("숏폼1" in f and f.endswith(".mp4") for f in files)
    qa_dir = job / "work" / "qa" / "r1"
    assert any(qa_dir.glob("g*.jpg")), list(qa_dir.iterdir())

    # 재실행: 계획·스톡·검수 캐시 사용(새 Claude 호출 없음) — 렌더 직전 단계까지
    before = len(CALLS)
    logs: list[str] = []
    p2 = pl.Pipeline(spec, settings, job, log=logs.append)
    for fn in (p2.stage_probe, p2.stage_audio, p2.stage_asr, p2.stage_align, p2.stage_face, p2.stage_director,
               p2.stage_proxy, p2.stage_broll, p2.stage_stock, p2.stage_qa):
        fn()
    assert len(CALLS) == before, CALLS[before:]
    assert any("이전 검수 결과 사용" in m for m in logs), logs[-10:]
    assert any(g["template"] == "broll" and g.get("src") for g in p2.plan_long["graphics"])
    print("E2E STUDIO OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
