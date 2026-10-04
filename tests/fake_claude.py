"""가짜 Claude Code CLI — e2e_studio.py 의 claude_code 백엔드 테스트용(진짜 모델을 부르지 않는다).

`claude -p --input-format stream-json --output-format stream-json --json-schema … --system-prompt-file …` 처럼
불리면 stdin 의 메시지를 읽고, e2e_studio.fake_answer 로 만든 답을 result 이벤트(structured_output)로 낸다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def main(argv: list[str]) -> int:
    if "--version" in argv:
        print("9.9.9 (Claude Code)")
        return 0
    if argv[:2] == ["auth", "status"]:
        print(json.dumps({"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"}))
        return 0
    for known in ("-p", "--input-format", "--output-format", "--json-schema", "--system-prompt-file", "--tools"):
        if known not in argv:
            print(f"fake claude: missing {known}", file=sys.stderr)
            return 2
    opts = {argv[i]: argv[i + 1] for i in range(len(argv) - 1) if argv[i].startswith("--")}
    schema = json.loads(opts["--json-schema"])
    system = Path(opts["--system-prompt-file"]).read_text(encoding="utf-8")
    assert system.strip(), "빈 시스템 프롬프트"
    msg = json.loads(sys.stdin.readline())
    content = msg["message"]["content"]
    # 같은 역할을 여러 번 부르는 호출은 공통 자료(대본·전사)를 시스템 프롬프트 끝에 둔다(ctx_in_system — 캐시) —
    # 진짜 모델처럼 그 자료도 본다
    mark = "# 이 작업의 공통 자료"
    if mark in system:
        content = [{"type": "text", "text": system.split(mark, 1)[1]}] + list(content)
    import e2e_studio as E  # noqa: E402 - 같은 가짜 답변 로직
    agent = E.agent_of(schema)
    # 웹 도구는 🔎 리서치 디렉터·🛠 시그니처 장면만(미리 허락) — 나머지는 도구 없이 판단만.
    # 시그니처 장면 시안 경쟁은 첫 안(A)만 웹 도구를 쓴다
    if agent == "setpiece" and opts["--tools"] == "":
        pass
    elif agent in ("research", "setpiece"):
        assert opts["--tools"] == "WebSearch,WebFetch" and opts.get("--allowedTools") == "WebSearch,WebFetch", opts
    else:
        assert opts["--tools"] == "", f"도구는 꺼져 있어야 한다({agent})"
    n_images = sum(1 for b in content if b.get("type") == "image")
    instruction = next(b["text"] for b in reversed(content) if b.get("type") == "text")
    ans = E.fake_answer(agent, {"messages": [{"content": content}]}, n_images, instruction)
    E.record_call({"agent": agent, "images": n_images, "effort": opts.get("--effort"), "backend": "claude_code",
                   "model": opts.get("--model"), "api_key_env": "ANTHROPIC_API_KEY" in os.environ,
                   "tools": opts.get("--tools"), "world": "이 영상의 세계" in instruction})
    print(json.dumps({"type": "system", "subtype": "init", "model": opts.get("--model")}))
    print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "num_turns": 2,
                      "result": json.dumps(ans, ensure_ascii=False), "structured_output": ans,
                      "usage": {"input_tokens": 1200, "output_tokens": 80, "cache_read_input_tokens": 900,
                                "cache_creation_input_tokens": 0}, "total_cost_usd": 0.01}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
