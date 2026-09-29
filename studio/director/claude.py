"""Claude API 호출 — 구조화 출력(JSON Schema) + 적응형 사고 + 스트리밍 + 거절 시 서버측 폴백."""
from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from ..util import CancelToken, LogFn, noop_log


class DirectorError(RuntimeError):
    pass


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
    ) -> dict:
        """system + (캐시되는) 공통 컨텍스트 + 작업 지시 → 스키마에 맞는 dict."""
        system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        user_blocks = [
            {"type": "text", "text": shared_context, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": instruction},
        ]
        base: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": [{"role": "user", "content": user_blocks}],
        }
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
        if _supports_adaptive(self.model):
            base["thinking"] = {"type": "adaptive"}
            output_config["effort"] = self.effort
        base["output_config"] = output_config

        attempts = [("structured+fallback", True, True), ("structured", True, False), ("plain-json", False, False)]
        last_err: Exception | None = None
        for name, use_schema, use_fallback in attempts:
            if use_fallback and not _supports_fallbacks(self.model):
                continue
            kwargs = json.loads(json.dumps(base))  # 깊은 복사
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
        raise DirectorError(f"{label} 호출 실패: {last_err}")

    # ------------------------------------------------------------------
    def _stream(self, kwargs: dict, use_fallback: bool, use_schema: bool, cancel: Optional[CancelToken],
                label: str) -> dict:
        t0 = time.time()
        if use_fallback:
            ctx = self.client.beta.messages.stream(
                **kwargs, betas=["server-side-fallback-2026-07-01"], extra_body={"fallbacks": "default"})
        else:
            ctx = self.client.messages.stream(**kwargs)
        chars = 0
        last_log = time.time()
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
                    self.log(f"{label}: 편집 계획 작성 중… ({int(time.time() - t0)}초, {chars}자)")
            msg = stream.get_final_message()
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
        text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
        if not text.strip():
            raise DirectorError("빈 응답")
        if use_schema:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return extract_json(text)
        return extract_json(text)
