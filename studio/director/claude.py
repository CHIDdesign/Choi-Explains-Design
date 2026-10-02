"""Claude API 호출 — 구조화 출력(JSON Schema) + 적응형 사고 + 스트리밍 + 거절 시 서버측 폴백."""
from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from ..util import CancelToken, LogFn, noop_log


class DirectorError(RuntimeError):
    pass


WEB_FETCH_BETA = "web-fetch-2025-09-10"


def web_tools(tools: tuple[str, ...], max_uses: int = 0) -> list[dict[str, Any]]:
    """Claude Code 도구 이름 → API 서버 도구(웹 검색 · 웹 가져오기)."""
    n = max(4, int(max_uses or 20))
    out: list[dict[str, Any]] = []
    if "WebSearch" in tools:
        out.append({"type": "web_search_20250305", "name": "web_search", "max_uses": n})
    if "WebFetch" in tools:
        out.append({"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": n})
    return out


def _supports_adaptive(model: str) -> bool:
    return not model.startswith("claude-haiku")


def _supports_fallbacks(model: str) -> bool:
    return model in ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")


def extract_json(text: str) -> Any:
    """구조화 출력이 꺼진 경우를 대비한 관대한 JSON 추출."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise DirectorError("응답에서 JSON 을 찾지 못했습니다")
    return json.loads(text[start:end + 1])


class ClaudeClient:
    def __init__(self, api_key: str, model: str = "claude-opus-5-5", effort: str = "high",
                 log: LogFn = noop_log):
        import anthropic  # 지연 import
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key or None, max_retries=3, timeout=1800.0)
        self.model = model
        self.effort = effort
        self.log = log
        self.usage: list[dict] = []

    # ------------------------------------------------------------------
    def structured(
        self,
        *,
        system: str,
        shared_context: str,
        instruction: str,
        schema: dict,
        max_tokens: int = 48000,
        cancel: Optional[CancelToken] = None,
        label: str = "Claude",
        images: Optional[list[tuple[str, bytes, str]]] = None,
        effort: Optional[str] = None,
        model: Optional[str] = None,
        tools: tuple[str, ...] = (),
        max_turns: int = 0,
        timeout: Optional[float] = None,
    ) -> dict:
        """system + (캐시되는) 공통 컨텍스트 + [이미지들] + 작업 지시 → 스키마에 맞는 dict.

        images: [(라벨, 바이트, media_type)] — 아트 디렉터 검수·스톡 선택용
        tools: ("WebSearch", "WebFetch") — 서버 도구(web_search · web_fetch)로 웹 조사(🔎 주제 조사). 거부되면 웹 검색만 →
        도구 없이 순서로 물러난다. max_turns 는 도구 사용 횟수 상한(검색·가져오기 각각).
        """
        import base64
        system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        user_blocks: list[dict[str, Any]] = [
            {"type": "text", "text": shared_context, "cache_control": {"type": "ephemeral"}},
        ]
        for lab, data, media in images or []:
            user_blocks.append({"type": "text", "text": f"[이미지 {lab}]"})
            user_blocks.append({"type": "image", "source": {"type": "base64", "media_type": media,
                                                            "data": base64.b64encode(data).decode("ascii")}})
        user_blocks.append({"type": "text", "text": instruction})
        use_model = model or self.model
        base: dict[str, Any] = {
            "model": use_model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": [{"role": "user", "content": user_blocks}],
        }
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
        if _supports_adaptive(use_model):
            base["thinking"] = {"type": "adaptive"}
            output_config["effort"] = effort or self.effort
        base["output_config"] = output_config
        tool_sets = [web_tools(tools, max_turns)] if tools else [[]]
        if tools and "WebFetch" in tools:
            tool_sets.append(web_tools(("WebSearch",), max_turns))       # 가져오기(베타)가 거부되면 검색만
        if tools:
            tool_sets.append([])                                         # 그래도 안 되면 도구 없이(기억으로)
        last_err: Exception | None = None
        for k, ts in enumerate(tool_sets):
            try:
                return self._structured_once(base, ts, schema, use_model, cancel, label)
            except DirectorError as e:
                last_err = e
                if k + 1 < len(tool_sets):
                    self.log(f"{label}: 웹 도구 요청이 거부됨 → {'검색만' if tool_sets[k + 1] else '도구 없이'} 다시 시도")
        raise last_err if last_err else DirectorError(f"{label} 호출 실패")

    def _structured_once(self, base: dict, tools: list[dict], schema: dict, use_model: str,
                         cancel: Optional[CancelToken], label: str) -> dict:
        attempts = [("structured+fallback", True, True), ("structured", True, False), ("plain-json", False, False)]
        last_err: Exception | None = None
        for name, use_schema, use_fallback in attempts:
            if use_fallback and not _supports_fallbacks(use_model):
                continue
            kwargs = json.loads(json.dumps(base))  # 깊은 복사
            if tools:
                kwargs["tools"] = tools
            if not use_schema:
                kwargs["output_config"].pop("format", None)
                if not kwargs["output_config"]:
                    kwargs.pop("output_config")
                kwargs["messages"][0]["content"].append({
                    "type": "text",
                    "text": "반드시 아래 JSON 스키마를 따르는 JSON 객체 하나만 출력하세요. 다른 말은 쓰지 마세요.\n"
                            + json.dumps(schema, ensure_ascii=False)})
            try:
                return self._stream(kwargs, use_fallback, use_schema, cancel, label)
            except self.anthropic.BadRequestError as e:
                last_err = e
                self.log(f"{label}: '{name}' 요청 거부됨({e.message[:160]}) → 다른 방식으로 재시도")
                continue
            except DirectorError as e:
                last_err = e
                self.log(f"{label}: {e} → 다른 방식으로 재시도")
                continue
            except self.anthropic.APIError as e:
                # 키 오류·요청 한도(429)·과부하(529)·모델 없음(404)·연결 실패 — SDK 가 이미 재시도했다. 작업 전체를 멈추지
                # 않고 부르는 쪽(규칙 기반 기획·기본 룩·다른 전문가 결과 유지)으로 넘긴다
                raise DirectorError(f"{label} 호출 실패: {type(e).__name__}: {getattr(e, 'message', e)}") from e
        raise DirectorError(f"{label} 호출 실패: {last_err}")

    # ------------------------------------------------------------------
    def _stream(self, kwargs: dict, use_fallback: bool, use_schema: bool, cancel: Optional[CancelToken],
                label: str) -> dict:
        t0 = time.time()
        betas = (["server-side-fallback-2026-07-01"] if use_fallback else []) + \
            ([WEB_FETCH_BETA] if any(t.get("name") == "web_fetch" for t in kwargs.get("tools") or []) else [])
        chars = 0
        last_log = time.time()
        msg = None
        for _turn in range(8):          # 서버 도구가 길어지면 pause_turn — 받은 내용을 그대로 이어 붙여 계속한다
            if betas:
                extra = {"extra_body": {"fallbacks": "default"}} if use_fallback else {}
                ctx = self.client.beta.messages.stream(**kwargs, betas=betas, **extra)
            else:
                ctx = self.client.messages.stream(**kwargs)
            with ctx as stream:
                for event in stream:
                    if cancel and cancel.cancelled:
                        stream.close()
                        cancel.check()
                    if getattr(event, "type", "") == "content_block_delta":
                        delta = getattr(event, "delta", None)
                        chars += len(getattr(delta, "text", "") or getattr(delta, "partial_json", "") or "")
                    if time.time() - last_log > 8:
                        last_log = time.time()
                        self.log(f"{label}: 작성 중… ({int(time.time() - t0)}초, {chars}자)")
                msg = stream.get_final_message()
            if getattr(msg, "stop_reason", "") != "pause_turn":
                break
            kwargs = dict(kwargs)
            kwargs["messages"] = list(kwargs["messages"]) + [
                {"role": "assistant", "content": [b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else b
                                                  for b in msg.content]}]
        usage = getattr(msg, "usage", None)
        if usage is not None:
            u = {"input": getattr(usage, "input_tokens", 0), "output": getattr(usage, "output_tokens", 0),
                 "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
                 "cache_write": getattr(usage, "cache_creation_input_tokens", 0) or 0,
                 "label": label, "model": getattr(msg, "model", self.model)}
            self.usage.append(u)
            self.log(f"{label}: 완료 {time.time() - t0:.0f}s · 입력 {u['input']} (캐시 {u['cache_read']}) · 출력 {u['output']} 토큰")
        if msg.stop_reason == "refusal":
            detail = getattr(msg, "stop_details", None)
            raise DirectorError(f"모델이 요청을 거절했습니다: {getattr(detail, 'category', '')}")
        if msg.stop_reason == "max_tokens":
            raise DirectorError("출력이 max_tokens 에서 잘렸습니다")
        texts = [getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text"]
        text = "".join(texts)
        if not text.strip():
            raise DirectorError("빈 응답")
        # 도구를 쓴 응답은 중간에 설명 글이 끼일 수 있다 — 마지막 글 덩어리부터 JSON 을 찾는다
        for cand in ([texts[-1]] if len(texts) > 1 else []) + [text]:
            try:
                return json.loads(cand)
            except json.JSONDecodeError:
                try:
                    return extract_json(cand)
                except (DirectorError, json.JSONDecodeError):
                    continue
        raise DirectorError("응답에서 JSON 을 읽지 못했습니다")
