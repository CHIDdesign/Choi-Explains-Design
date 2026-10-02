"""ClaudeCodeClient 를 가짜 claude CLI 로 검증: 인자·stdin 메시지·이미지·환경변수·오류 처리."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.director.claude import DirectorError  # noqa: E402
from studio.director.claude_code import (ClaudeCodeClient, _scratch_bases, describe_auth, explain_error,  # noqa: E402
                                         resolve_backend, scratch_dir)

FAKE = r'''
import json, os, sys
argv = sys.argv[1:]
mode = os.environ.get("FAKE_MODE", "ok")
log = os.environ["FAKE_LOG"]
if mode == "old" and "--strict-mcp-config" in argv:
    print("error: unknown option '--strict-mcp-config'", file=sys.stderr); sys.exit(1)
if mode == "late_err" and "--strict-mcp-config" in argv:
    # stdout 을 먼저 닫고 잠깐 뒤 stderr — 읽기 스레드가 늦으면 '모르는 옵션'을 못 보던 경합
    sys.stdout.close(); os.close(1)
    sys.stderr.write(("warning: " + "x" * 200 + "\n") * 4000)       # 파이프 버퍼보다 훨씬 많이 — 마지막 줄은 끝난 뒤에 읽힌다
    print("error: unknown option '--strict-mcp-config'", file=sys.stderr); sys.stderr.flush(); os._exit(1)
msg = json.loads(sys.stdin.readline())
opts = {argv[i]: argv[i + 1] for i in range(len(argv) - 1) if argv[i].startswith("--")}
with open(log, "a", encoding="utf-8") as f:
    f.write(json.dumps({"argv": argv, "content": msg["message"]["content"], "api_key": "ANTHROPIC_API_KEY" in os.environ,
                        "claude_mds_off": os.environ.get("CLAUDE_CODE_DISABLE_CLAUDE_MDS"),
                        "cwd": os.getcwd(), "system": open(opts["--system-prompt-file"], encoding="utf-8").read()}) + "\n")
print(json.dumps({"type": "system", "subtype": "init"}))
if mode == "limit":
    print(json.dumps({"type": "result", "subtype": "success", "is_error": True, "result": "Claude AI usage limit reached|1790000000"}))
elif mode == "login":
    print(json.dumps({"type": "result", "subtype": "success", "is_error": True, "result": "Not logged in · Please run /login"}))
elif mode == "text":
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "```json\n{\"a\": 2}\n```"}))
else:
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "{}",
                      "structured_output": {"a": 1}, "usage": {"input_tokens": 10, "output_tokens": 5,
                      "cache_read_input_tokens": 7}, "total_cost_usd": 0.003}))
'''


@pytest.fixture()
def fake(tmp_path, monkeypatch):
    script = tmp_path / "fake_claude.py"
    script.write_text(FAKE, encoding="utf-8")
    shim = tmp_path / "claude"
    shim.write_text(f"#!/bin/sh\nexec {sys.executable} {script} \"$@\"\n")
    shim.chmod(0o755)
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-must-not-leak")

    def calls():
        return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return shim, calls, tmp_path


SCHEMA = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"], "additionalProperties": False}


@pytest.mark.skipif(sys.platform == "win32", reason="sh shim")
def test_structured_call_args_images_env(fake):
    shim, calls, tmp = fake
    logs: list[str] = []
    c = ClaudeCodeClient(str(shim), "claude-opus-5-5", "high", log=logs.append, workdir=tmp / "wd")
    out = c.structured(system="스튜디오 헌장", shared_context="전사본", instruction="지시", schema=SCHEMA,
                       images=[("g1", b"\xff\xd8jpeg", "image/jpeg")], effort="low", label="🧐")
    assert out == {"a": 1}
    call = calls()[0]
    argv = call["argv"]
    assert argv[:1] == ["-p"] and "--json-schema" in argv and json.loads(argv[argv.index("--json-schema") + 1]) == SCHEMA
    assert argv[argv.index("--tools") + 1] == "" and argv[argv.index("--effort") + 1] == "low"
    assert argv[argv.index("--model") + 1] == "claude-opus-5-5"
    assert call["system"] == "스튜디오 헌장" and not call["api_key"]  # API 키는 자식 프로세스에 넘기지 않는다
    assert call["claude_mds_off"] == "1"   # 어느 폴더에서 돌든 CLAUDE.md 를 읽지 않게
    kinds = [b["type"] for b in call["content"]]
    assert kinds == ["text", "text", "image", "text"] and call["content"][-1]["text"] == "지시"
    assert Path(call["cwd"]) == tmp / "wd"
    assert c.usage[0]["backend"] == "claude_code" and c.usage[0]["cache_read"] == 7
    assert any("Claude 구독" in m for m in logs)


@pytest.mark.skipif(sys.platform == "win32", reason="sh shim")
@pytest.mark.parametrize("mode, needle", [("limit", "사용량 한도"), ("login", "로그인")])
def test_errors_are_explained(fake, monkeypatch, mode, needle):
    shim, _, tmp = fake
    monkeypatch.setenv("FAKE_MODE", mode)
    c = ClaudeCodeClient(str(shim), workdir=tmp / "wd")
    with pytest.raises(DirectorError) as e:
        c.structured(system="s", shared_context="c", instruction="i", schema=SCHEMA)
    assert needle in str(e.value)


@pytest.mark.skipif(sys.platform == "win32", reason="sh shim")
def test_old_cli_drops_unknown_option_and_text_fallback(fake, monkeypatch):
    shim, calls, tmp = fake
    monkeypatch.setenv("FAKE_MODE", "old")
    logs: list[str] = []
    c = ClaudeCodeClient(str(shim), workdir=tmp / "wd", log=logs.append)
    assert c.structured(system="s", shared_context="c", instruction="i", schema=SCHEMA) == {"a": 1}
    assert "--strict-mcp-config" not in calls()[-1]["argv"] and any("모르는 옵션" in m for m in logs)
    monkeypatch.setenv("FAKE_MODE", "text")
    assert c.structured(system="s", shared_context="c", instruction="i", schema=SCHEMA) == {"a": 2}


def test_resolve_backend_and_auth_text(tmp_path, monkeypatch):
    from studio.settings import Settings
    s = Settings()
    s.claude_code_path = str(tmp_path / "nope")
    monkeypatch.setattr("studio.director.claude_code.find_claude", lambda custom="": None)
    assert resolve_backend(s)[0] == "none"
    s.anthropic_api_key = "k"
    assert resolve_backend(s)[0] == "api"
    monkeypatch.setattr("studio.director.claude_code.find_claude", lambda custom="": "/x/claude")
    assert resolve_backend(s)[0] == "claude_code"   # 기본은 구독(Claude Code)
    s.ai_backend = "api"
    assert resolve_backend(s)[0] == "api"
    assert describe_auth({"loggedIn": False}) == "로그인 필요"
    assert "API 키" in describe_auth({"loggedIn": True, "authMethod": "api_key"})
    assert "한도" in explain_error("Claude AI usage limit reached|123")
    assert os.environ.get("FAKE_MODE") is None


def test_unknown_option_is_seen_even_when_stderr_arrives_late(fake, monkeypatch):
    """stdout 이 먼저 닫히고 stderr 가 프로세스 끝 직전에 와도 '모르는 옵션'을 읽고 그 옵션을 빼고 다시 실행한다
    (읽기 스레드를 기다리지 않아 바쁜 PC 에서 옛 CLI 가 그냥 실패하던 경합)."""
    shim, calls, tmp = fake
    monkeypatch.setenv("FAKE_MODE", "late_err")
    logs: list[str] = []
    c = ClaudeCodeClient(str(shim), workdir=tmp / "wd", log=logs.append)
    assert c.structured(system="s", shared_context="c", instruction="i", schema=SCHEMA) == {"a": 1}
    assert any("모르는 옵션" in m for m in logs)


def test_scratch_dir_avoids_temp_under_install_claude_md(tmp_path):
    """2026-10-03 실제 작업: run_studio.bat 이 TEMP 를 설치 폴더 안 tools\\tmp 로 돌려 두어 임시 폴더 위에 개발 메모 CLAUDE.md 가
    있었고, 주제 조사는 건너뛰고 ✂️ 컷 총괄에서 작업이 멈췄다 — 다음 후보(사용자 로컬 임시 폴더)로 피한다."""
    install = tmp_path / "Choi-Explains-Design-main"
    (install / "tools" / "tmp").mkdir(parents=True)
    (install / "CLAUDE.md").write_text("# 개발 메모", encoding="utf-8")
    local_temp = tmp_path / "AppData" / "Local" / "Temp"
    logs: list[str] = []
    d = scratch_dir("20261003_0436_주제는 디자인", bases=[install / "tools" / "tmp", local_temp], log=logs.append)
    assert d.is_dir() and local_temp in d.parents and install not in d.parents
    assert d.name.startswith("20261003_0436_")      # 꼬리표에서 공간·한글은 _ 로
    assert any("CLAUDE.md" in m for m in logs)      # 피한 이유를 로그에
    # 첫 후보가 깨끗하면 그대로, 로그 없음
    logs.clear()
    assert local_temp in scratch_dir("x", bases=[local_temp, install / "tools" / "tmp"], log=logs.append).parents and not logs


def test_scratch_dir_stops_when_every_base_is_under_claude_md(tmp_path):
    (tmp_path / "CLAUDE.local.md").write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError) as e:
        scratch_dir("job", bases=[tmp_path / "a", tmp_path / "b"])
    assert "CLAUDE.local.md" in str(e.value) and "옮기거나 지우고" in str(e.value)


def test_scratch_bases_start_at_tempdir_and_end_at_home(tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setenv("TMP", str(tmp_path))
    monkeypatch.setattr(tempfile, "tempdir", None)      # gettempdir 캐시 초기화
    bases = _scratch_bases()
    assert bases[0] == Path(tempfile.gettempdir()) and bases[-1] == Path.home() / ".choi_studio"
    assert len(bases) == len(set(bases)) and len(bases) >= 3
