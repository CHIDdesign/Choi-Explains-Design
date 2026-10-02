"""이 PC 의 Claude Code(`claude -p`)로 Claude 를 부른다 — Pro/Max 구독 사용량에서 차감, API 키 불필요.

공식 CLI 의 headless 모드를 쓴다.
- `--input-format stream-json` : 전사본·이미지(검수 스틸, 스톡 후보 시트)를 담은 메시지를 stdin 으로
- `--json-schema`              : 구조화 출력 → 마지막 result 이벤트의 `structured_output`
- `--system-prompt-file`       : 스튜디오 헌장으로 기본(코딩 비서) 시스템 프롬프트를 대체
- `--tools ""`                 : 파일·명령 도구를 모두 끈다(판단만 한다). 단 🔎 주제 조사처럼 웹을 봐야 하는 호출은
                                `tools=("WebSearch", "WebFetch")` — 그 둘만 켜고 `--allowedTools` 로 미리 허락한다(묻지 않음)
- ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN 을 빼고 실행 → 구독 대신 API 종량제로 새지 않게
- 빈 작업 폴더에서 실행하고 MCP·스킬을 끈다 → 다른 프로젝트 설정이 섞이지 않게

2026-06-15 공지 기준 `claude -p` 사용량은 구독 한도(5시간·주간)에서 차감된다. 정책이 바뀌면 설정에서 API 키 방식으로 바꾸면 된다.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

from ..util import CancelToken, LogFn, noop_log
from .claude import DirectorError, extract_json

# 구독 로그인 대신 API 키로 과금되게 만드는 환경변수(실행할 때 뺀다)
STRIP_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")
# 오래된 Claude Code 에 없을 수 있는 선택 옵션(모르는 옵션이라고 하면 빼고 다시 실행)
OPTIONAL_FLAGS = ("--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence")
# 켤 수 있는 도구는 웹 조사 둘뿐(🔎 주제 조사·🛠 시그니처 장면) — 파일·명령·MCP 는 언제나 끈다
WEB_TOOLS = ("WebSearch", "WebFetch")


def _popen_kw() -> dict[str, Any]:
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if sys.platform == "win32" else {}


def clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in STRIP_ENV}


def _exe_near_cmd(cmd: Path) -> Optional[str]:
    """npm 으로 설치한 claude.cmd 옆의 실제 실행 파일(명령 창 따옴표 문제를 피하려고)."""
    base = cmd.parent / "node_modules" / "@anthropic-ai"
    if base.exists():
        for exe in base.glob("**/claude.exe"):
            return str(exe)
    return None


def find_claude(custom: str = "") -> Optional[str]:
    if custom and Path(custom).exists():
        return custom
    cands: list[Path] = []
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    if sys.platform == "win32":
        cands.append(home / ".local" / "bin" / "claude.exe")   # 공식 설치 스크립트 위치
    else:
        cands += [home / ".local" / "bin" / "claude", Path("/usr/local/bin/claude")]
    for c in cands:
        if c.exists():
            return str(c)
    p = shutil.which("claude")
    if p:
        if p.lower().endswith((".cmd", ".bat")):
            return _exe_near_cmd(Path(p)) or p
        return p
    if sys.platform == "win32":
        for c in (Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",):
            if c.exists():
                return _exe_near_cmd(c) or str(c)
    return None


def claude_version(exe: str) -> str:
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=30, env=clean_env(),
                             **_popen_kw())
        return (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def auth_status(exe: str) -> dict[str, Any]:
    """`claude auth status --json` → {loggedIn, authMethod, ...}. 실패하면 빈 dict."""
    try:
        out = subprocess.run([exe, "auth", "status", "--json"], capture_output=True, text=True, timeout=30,
                             env=clean_env(), encoding="utf-8", errors="replace", **_popen_kw())
        return json.loads(out.stdout) if out.stdout.strip().startswith("{") else {}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {}


def describe_auth(st: dict[str, Any]) -> str:
    if not st:
        return "상태를 확인하지 못했습니다"
    if not st.get("loggedIn"):
        return "로그인 필요"
    method = str(st.get("authMethod", ""))
    sub = str(st.get("subscriptionType") or st.get("subscription") or "")
    sub = {"max": "Claude Max", "pro": "Claude Pro", "team": "Claude Team", "enterprise": "Claude Enterprise"}.get(
        sub.lower(), sub)
    if "api" in method.lower() and "key" in method.lower():
        return "로그인됨 · API 키(종량제 과금) — 구독으로 쓰려면 다시 로그인하세요"
    hint = " (Max 로 바꿨는데 Pro 로 보이면: 로그아웃 → 다시 로그인)" if sub == "Claude Pro" else ""
    return "로그인됨" + (f" · {sub}" if sub else " · Claude 구독") + hint


def open_login(exe: str) -> None:
    """브라우저 로그인(구독 계정). Windows 는 새 콘솔 창에서 진행 상황을 보여 준다."""
    args = [exe, "auth", "login", "--claudeai"]
    if sys.platform == "win32":
        subprocess.Popen(args, env=clean_env(), creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    else:
        subprocess.Popen(args, env=clean_env())


class ClaudeCodeClient:
    """ClaudeClient 와 같은 모양(structured / usage)으로 로컬 Claude Code 를 부른다."""

    backend = "claude_code"

    def __init__(self, exe: str, model: str = "claude-opus-5-5", effort: str = "high", *, log: LogFn = noop_log,
                 workdir: Optional[Path] = None, timeout: float = 1800.0):
        self.exe = exe
        self.model = model
        self.effort = effort
        self.log = log
        self.workdir = Path(workdir) if workdir else Path.cwd()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.usage: list[dict] = []
        self._drop: set[str] = set()   # 이 버전이 모르는 선택 옵션
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def _system_file(self, system: str) -> Path:
        h = hashlib.sha1(system.encode("utf-8")).hexdigest()[:12]
        p = self.workdir / f"system_{h}.md"
        with self._lock:
            if not p.exists():
                p.write_text(system, encoding="utf-8")
        return p

    def _args(self, system_file: Path, schema: Optional[dict], model: str, effort: str,
              tools: tuple[str, ...] = (), max_turns: int = 0) -> list[str]:
        allowed = ",".join(t for t in tools if t in WEB_TOOLS)
        args = [self.exe, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                "--system-prompt-file", str(system_file), "--tools", allowed, "--model", model]
        if allowed:
            args += ["--allowedTools", allowed]
            if max_turns and "--max-turns" not in self._drop:
                args += ["--max-turns", str(max_turns)]
        if effort and "--effort" not in self._drop:
            args += ["--effort", effort]
        if schema is not None:
            args += ["--json-schema", json.dumps(schema, separators=(",", ":"))]
        args += [f for f in OPTIONAL_FLAGS if f not in self._drop]
        return args

    def structured(self, *, system: str, shared_context: str, instruction: str, schema: dict,
                   max_tokens: int = 48000, cancel: Optional[CancelToken] = None, label: str = "Claude",
                   images: Optional[list[tuple[str, bytes, str]]] = None, effort: Optional[str] = None,
                   model: Optional[str] = None, tools: tuple[str, ...] = (), max_turns: int = 0,
                   timeout: Optional[float] = None) -> dict:
        """tools: 웹 조사 도구(WebSearch·WebFetch)만 켤 수 있다 — 파일·명령 도구는 언제나 꺼져 있다."""
        import base64
        content: list[dict[str, Any]] = [{"type": "text", "text": shared_context}]
        for lab, data, media in images or []:
            content.append({"type": "text", "text": f"[이미지 {lab}]"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": media,
                                                        "data": base64.b64encode(data).decode("ascii")}})
        content.append({"type": "text", "text": instruction})
        sysf = self._system_file(system)
        use_model, use_effort = model or self.model, effort or self.effort
        use_schema: Optional[dict] = schema
        last = ""
        for attempt in range(3):
            msg_content = content if use_schema is not None else content + [{
                "type": "text", "text": "반드시 아래 JSON 스키마를 따르는 JSON 객체 하나만 출력하세요.\n"
                                        + json.dumps(schema, ensure_ascii=False)}]
            line = json.dumps({"type": "user", "message": {"role": "user", "content": msg_content}}, ensure_ascii=False)
            try:
                return self._run(self._args(sysf, use_schema, use_model, use_effort, tuple(tools), max_turns), line,
                                 cancel, label, use_schema is not None, timeout=timeout)
            except _UnknownOption as e:
                last = str(e)
                flag = e.flag
                if flag == "--json-schema":
                    use_schema = None
                elif flag:
                    self._drop.add(flag)
                else:
                    self._drop.update(OPTIONAL_FLAGS + ("--effort",))
                self.log(f"{label}: 이 버전의 Claude Code 가 모르는 옵션({flag or '?'}) → 빼고 다시 실행")
        raise DirectorError(f"{label}: Claude Code 실행 실패 — {last}")

    # ------------------------------------------------------------------
    def _run(self, args: list[str], stdin_line: str, cancel: Optional[CancelToken], label: str,
             schema_mode: bool, timeout: Optional[float] = None) -> dict:
        t0 = time.time()
        limit = float(timeout or self.timeout)
        searches = 0
        served = ""
        try:
            proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    cwd=str(self.workdir), env=clean_env(), text=True, encoding="utf-8",
                                    errors="replace", **_popen_kw())
        except OSError as e:
            raise DirectorError(f"Claude Code 를 실행할 수 없습니다({self.exe}): {e}") from e
        lines: "queue.Queue[Optional[str]]" = queue.Queue()
        err: list[str] = []

        def pump_out() -> None:
            assert proc.stdout
            for ln in proc.stdout:
                lines.put(ln)
            lines.put(None)

        def pump_err() -> None:
            assert proc.stderr
            for ln in proc.stderr:
                err.append(ln)

        def pump_in() -> None:
            # 입력(이미지가 들어가면 수 MB)도 별도 스레드로 — claude 가 읽기 전에 멈추면 여기서 막혀
            # 아래의 시간 제한·취소가 듣지 않던 것
            try:
                assert proc.stdin
                proc.stdin.write(stdin_line + "\n")
                proc.stdin.close()
            except (OSError, ValueError):
                pass

        if cancel is not None:
            cancel.register(proc)          # 취소하면 CancelToken 이 프로세스를 바로 끝낸다
        readers = [threading.Thread(target=pump_out, daemon=True), threading.Thread(target=pump_err, daemon=True)]
        for th in readers:
            th.start()
        threading.Thread(target=pump_in, daemon=True).start()
        result: Optional[dict] = None
        last_log = time.time()
        while True:
            if cancel and cancel.cancelled:
                proc.kill()
                cancel.check()
            if time.time() - t0 > limit:
                proc.kill()
                raise DirectorError(f"{label}: Claude Code 응답이 {limit / 60:.0f}분 넘게 없어 중단했습니다")
            try:
                ln = lines.get(timeout=0.5)
            except queue.Empty:
                ln = ""
            if ln is None:
                break
            if ln.strip().startswith("{"):
                try:
                    ev = json.loads(ln)
                except json.JSONDecodeError:
                    ev = {}
                if ev.get("type") == "result":
                    result = ev
                elif ev.get("type") == "system" and ev.get("subtype") == "init" and ev.get("model"):
                    served = str(ev["model"])
                elif ev.get("type") == "assistant":
                    served = str(((ev.get("message") or {}).get("model")) or served)
                    searches += sum(1 for b in (ev.get("message") or {}).get("content") or []
                                    if isinstance(b, dict) and b.get("type") == "tool_use")
            if time.time() - last_log > 10:
                last_log = time.time()
                self.log(f"{label}: 작업 중… ({int(time.time() - t0)}초, Claude Code"
                         + (f" · 웹 조사 {searches}회" if searches else "") + ")")
        proc.wait(timeout=30)
        # stderr 를 끝까지 읽은 뒤에 판단한다 — 읽기 스레드가 늦으면(바쁜 PC) '모르는 옵션'을 못 보고 옛 CLI 에서 그냥 실패했다
        for th in readers:
            th.join(timeout=5)
        if cancel is not None:
            cancel.unregister(proc)
        stderr = "".join(err)
        if result is None:
            unknown = _parse_unknown_option(stderr)
            if unknown is not None:
                raise _UnknownOption(unknown, stderr.strip()[-300:])
            raise DirectorError(f"{label}: Claude Code 가 결과 없이 끝났습니다(코드 {proc.returncode}). "
                                f"{stderr.strip()[-600:] or '로그인 상태를 확인하세요(설정 → AI → 로그인).'}")
        self._record(result, label, t0, served=served, requested=next((args[i + 1] for i, a in enumerate(args)
                                                                       if a == "--model" and i + 1 < len(args)), ""))
        if result.get("is_error") or result.get("subtype") not in (None, "success"):
            raise DirectorError(explain_error(str(result.get("result") or result.get("subtype") or "")))
        if schema_mode and isinstance(result.get("structured_output"), dict):
            return result["structured_output"]
        text = str(result.get("result") or "")
        try:
            return extract_json(text)
        except (DirectorError, json.JSONDecodeError) as e:
            raise DirectorError(f"{label}: 응답에서 JSON 을 읽지 못했습니다") from e

    def _record(self, ev: dict, label: str, t0: float, *, served: str = "", requested: str = "") -> None:
        u = ev.get("usage") or {}
        used = [m for m in (ev.get("modelUsage") or {}) if isinstance(m, str)]
        # 실제로 답한 모델 — 요청은 Opus 인데 다른 모델이 답했다면(구독 등급·한도·폴백) 화면에 알린다
        actual = served or (max(used, key=lambda m: ((ev.get("modelUsage") or {}).get(m) or {}).get("outputTokens", 0))
                            if used else "")
        rec = {"input": u.get("input_tokens", 0) or 0, "output": u.get("output_tokens", 0) or 0,
               "cache_read": u.get("cache_read_input_tokens", 0) or 0,
               "cache_write": u.get("cache_creation_input_tokens", 0) or 0, "label": label,
               "model": actual or requested or self.model, "requested": requested or self.model,
               "backend": "claude_code", "api_equiv_usd": ev.get("total_cost_usd") or 0}
        self.usage.append(rec)
        self.log(f"{label}: 완료 {time.time() - t0:.0f}s · 입력 {rec['input']} (캐시 {rec['cache_read']}) · "
                 f"출력 {rec['output']} 토큰 · {actual or '모델 미확인'} · Claude 구독")
        want = (requested or self.model).split("[")[0]
        if actual and want and not actual.startswith(want) and "opus" in want and "opus" not in actual:
            if not getattr(self, "_warned_model", False):
                self._warned_model = True
                self.log(f"⚠ 요청한 모델은 {want} 인데 {actual} 이 답했습니다 — 구독 등급·사용량 한도 때문일 수 있습니다. "
                         "Max 인데 Pro 로 보이면 `claude auth logout` → 설정 › AI › 로그인으로 다시 로그인하세요.")


class _UnknownOption(DirectorError):
    def __init__(self, flag: str, msg: str):
        super().__init__(msg)
        self.flag = flag


def _parse_unknown_option(stderr: str) -> Optional[str]:
    import re
    m = re.search(r"unknown option '([^']+)'", stderr)
    if m:
        return m.group(1).split("=")[0]
    return "" if "unknown option" in stderr else None


def explain_error(msg: str) -> str:
    low = msg.lower()
    if "limit" in low and ("usage" in low or "reached" in low or "rate" in low):
        return ("Claude 구독 사용량 한도에 도달했습니다(5시간·주간 한도). 한도가 풀린 뒤 '전체 제작'을 다시 누르면 "
                f"이미 끝난 단계는 건너뜁니다. ({msg[:160]})")
    if "login" in low or "log in" in low or "not logged" in low or "invalid api key" in low or "authenticat" in low:
        return f"Claude Code 로그인이 필요합니다: 설정 → AI → '로그인'을 누르세요. ({msg[:160]})"
    return f"Claude Code 오류: {msg[:400]}"


def resolve_backend(settings: Any) -> tuple[str, str]:
    """(claude_code|api|none, 설명). Claude Code 가 없으면 API 키로, 둘 다 없으면 none(규칙 기반)."""
    if getattr(settings, "ai_backend", "claude_code") == "api":
        if settings.anthropic_api_key:
            return "api", "Claude API 키(종량제)"
        exe = find_claude(getattr(settings, "claude_code_path", ""))
        return ("claude_code", "API 키가 없어 Claude Code 사용") if exe else ("none", "API 키 없음")
    exe = find_claude(getattr(settings, "claude_code_path", ""))
    if exe:
        return "claude_code", "Claude Code(구독)"
    if settings.anthropic_api_key:
        return "api", "Claude Code 를 찾지 못해 API 키 사용"
    return "none", "Claude Code 를 찾지 못함(setup_windows.bat 으로 설치)"
