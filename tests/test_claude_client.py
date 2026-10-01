"""ClaudeClient 를 가짜 로컬 API 서버(SSE)로 검증: 요청 형식 + 스트림 파싱 + 폴백 재시도."""
from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.director.claude import ClaudeClient  # noqa: E402
from studio.director.schema import SHORTS_PLAN  # noqa: E402

SEEN: list[dict] = []


def _sse(text: str) -> bytes:
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 12, "output_tokens": 1}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                           "usage": {"output_tokens": 9}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return b"".join(f"event: {e}\ndata: {json.dumps(d)}\n\n".encode() for e, d in events)


class Handler(BaseHTTPRequestHandler):
    reject_fallback = True

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        SEEN.append({"path": self.path, "body": body, "beta": self.headers.get("anthropic-beta", "")})
        if "fallbacks" in body and Handler.reject_fallback:
            msg = json.dumps({"type": "error", "error": {"type": "invalid_request_error", "message": "fallbacks not enabled"}})
            self.send_response(400)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(msg.encode())
            return
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        self.wfile.write(_sse(json.dumps({"shorts": []})))

    def log_message(self, *a):
        pass


def test_structured_call_and_fallback_retry(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{srv.server_port}")
    logs: list[str] = []
    c = ClaudeClient("sk-test", "claude-opus-5-5", "high", log=logs.append)
    c.client = c.anthropic.Anthropic(api_key="sk-test", base_url=f"http://127.0.0.1:{srv.server_port}", max_retries=0)
    out = c.structured(system="sys", shared_context="ctx", instruction="do", schema=SHORTS_PLAN, label="t")
    srv.shutdown()
    assert out == {"shorts": []}
    first, second = SEEN[0], SEEN[1]
    assert "server-side-fallback-2026-07-01" in first["beta"] and first["body"]["fallbacks"] == "default"
    b = second["body"]
    assert "fallbacks" not in b
    assert b["thinking"] == {"type": "adaptive"}
    assert b["output_config"]["effort"] == "high"
    assert b["output_config"]["format"]["type"] == "json_schema"
    assert b["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert b["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert "temperature" not in b
    assert c.usage and c.usage[0]["output"] == 9
