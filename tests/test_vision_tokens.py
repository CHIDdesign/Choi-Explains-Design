"""그림 보기·토큰 절약·음성 인식 속도(채널 주인 2026-10-04: "보면서 작업해야 퀄리티가 난다", "토큰은 아낄 수 있는 곳에서",
"10분짜리에 2시간").

- 그림 한도: 20장 넘는 요청은 장마다 2000px 이하, media_type 은 실제 형식(platform.claude.com vision 문서).
- 같은 역할을 여러 번 부를 때 공통 자료는 시스템 프롬프트 끝(캐시), 동시에 뜬 호출은 첫 호출이 캐시를 쓸 시간을 준다.
- 디자인 규칙 전부가 필요 없는 역할은 가벼운 시스템 프롬프트.
- 자기 검토: 고칠 것이 없으면 그대로(None), 수정에는 정지 화면 + 움직임 시트.
- 음성 인식 배치는 여유 VRAM 과 지난 실측 속도로.
"""
from __future__ import annotations

import io
import json
import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.director.images import MANY_EDGE, fit_images  # noqa: E402


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 120, 40)).save(buf, "PNG")
    return buf.getvalue()


def _jpg(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (40, 120, 200)).save(buf, "JPEG", quality=85)
    return buf.getvalue()


def test_many_images_are_kept_under_2000px_and_typed_correctly():
    imgs = [(f"s{i}", _jpg(1920, 1080), "image/jpeg") for i in range(20)] + [("big", _jpg(2400, 1200), "image/jpeg"),
                                                                            ("png", _png(800, 450), "image/jpeg")]
    out = fit_images(imgs)
    assert len(out) == 22
    sizes = {lab: Image.open(io.BytesIO(d)).size for lab, d, _ in out}
    assert max(sizes["big"]) <= MANY_EDGE and sizes["s0"] == (1920, 1080)      # 1920 은 그대로(줄일 필요 없음)
    assert dict((lab, m) for lab, _, m in out)["png"] == "image/png"            # PNG 를 jpeg 로 보내면 거절된다
    few = fit_images([("big", _jpg(2400, 1200), "image/jpeg")])
    assert Image.open(io.BytesIO(few[0][1])).size == (2400, 1200)              # 20장 이하면 2576 까지 그대로
    assert fit_images(None) is None and fit_images([("x", b"not an image", "image/jpeg")])[0][1] == b"not an image"


class _FakeClaude:
    effort = "high"

    def __init__(self):
        self.calls: list[dict] = []
        self.lock = threading.Lock()

    def structured(self, **kw):
        with self.lock:
            self.calls.append(dict(kw, t=time.time()))
        time.sleep(0.3)
        return {"spec_json": "", "changes": "그대로 — 0.5초 무대·위계·글자 모두 괜찮다", "html": "", "timeline": ""}


def test_lean_system_repeated_context_and_staggered_starts(monkeypatch):
    from studio.agents import studio as S
    monkeypatch.setattr(S, "PRIME_S", 0.6)
    fake = _FakeClaude()
    st = S.Studio(fake)
    st.call("colorist", "공통 자료", "색을 본다")
    st.call("director", "공통 자료", "브리프")
    by = {c["label"]: c for c in fake.calls}
    lean, full = by["🎨 컬러리스트"]["system"], by["🎬 총괄 감독"]["system"]
    assert len(lean) * 4 < len(full) and "모션" not in lean.split("# 채널 스타일 가이드")[0][-50:]
    assert "ctx_in_system" not in by["🎬 총괄 감독"]                   # 한 번만 부르는 역할은 그대로

    fake.calls.clear()
    threads = [threading.Thread(target=st.call, args=("motion_revise", "공통 자료", f"장면 {i}")) for i in range(3)]
    for th in threads:
        th.start()
        time.sleep(0.02)
    for th in threads:
        th.join()
    ts = sorted(c["t"] for c in fake.calls)
    assert all(c.get("ctx_in_system") for c in fake.calls)              # 반복 역할 → 자료를 캐시되는 시스템 쪽으로
    assert ts[1] - ts[0] >= 0.5 and ts[2] - ts[0] >= 0.5                # 첫 호출이 캐시를 쓸 시간을 준 뒤 나머지
    assert st._running.get("motion_revise") == 0


@pytest.mark.skipif(sys.platform == "win32", reason="sh shim")
def test_cli_puts_context_into_system_when_asked(tmp_path, monkeypatch):
    from test_claude_code import FAKE, SCHEMA
    from studio.director.claude_code import ClaudeCodeClient
    script = tmp_path / "fake_claude.py"
    script.write_text(FAKE, encoding="utf-8")
    shim = tmp_path / "claude"
    shim.write_text(f"#!/bin/sh\nexec {sys.executable} {script} \"$@\"\n")
    shim.chmod(0o755)
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_LOG", str(log))
    logs: list[str] = []
    c = ClaudeCodeClient(str(shim), "claude-opus-5-5", "high", log=logs.append, workdir=tmp_path / "wd")
    c.structured(system="헌장", shared_context="대본 전사 자료", instruction="지시", schema=SCHEMA, ctx_in_system=True,
                 images=[("g3#seq", _png(640, 360), "image/jpeg")])
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    texts = [b.get("text", "") for b in rec["content"] if b.get("type") == "text"]
    assert "대본 전사 자료" in rec["system"] and not any("대본 전사 자료" in t for t in texts)
    img = next(b for b in rec["content"] if b.get("type") == "image")
    assert img["source"]["media_type"] == "image/png"
    assert any("캐시 읽기 7" in m and "캐시 쓰기" in m for m in logs)


def test_self_review_keeps_scene_when_designer_sees_nothing_to_fix():
    from studio.agents import studio as S
    fake = _FakeClaude()
    st = S.Studio(fake)
    img = ("g3", _jpg(64, 36), "image/jpeg")
    strip = ("g3#seq", _jpg(64, 36), "image/jpeg")
    assert st.revise_scene("자료", {"elements": []}, 6.0, "", "", [img, strip], self_review="자기 검토") is None
    sent = fake.calls[-1]
    assert [i[0] for i in sent["images"]] == ["g3", "g3#seq"] and "자기 검토" in sent["instruction"]
    assert st.revise_card("자료", {"id": "card1", "html": "<div class='card'></div>", "css": ""}, 6.0, "", "", None,
                          self_review="자기 검토") is None


def test_revisions_get_still_and_motion_strip():
    from studio.pipeline import qa_images
    stills = {"g2": ("g2", b"a", "image/jpeg"), "g2#seq": ("g2#seq", b"b", "image/jpeg"), "g5": ("g5", b"c", "image/jpeg")}
    assert [x[0] for x in qa_images(stills, "g2")] == ["g2", "g2#seq"]
    assert [x[0] for x in qa_images(stills, "g5")] == ["g5"] and qa_images(stills, "g9") == []


def test_whisper_batch_follows_free_vram_and_learns_from_slow_runs(tmp_path, monkeypatch):
    from studio.asr import transcribe as T
    monkeypatch.setattr(T, "_tuning_file", lambda: tmp_path / "asr_tuning.json")
    assert T.batch_for_gpu(8, "large-v3", ("RTX 3060", 12.0, 11.0)) == 8
    assert T.batch_for_gpu(8, "large-v3", ("RTX 3050 Laptop", 6.0, 5.0)) == 1     # 넘치면 시스템 메모리로 — 순차가 더 빠르다
    assert T.batch_for_gpu(8, "large-v3", None) == 8 and T.batch_for_gpu(8, "medium", ("x", 4.0, 3.0)) == 8
    T._save_tuning("RTX 3060", 8, 0.6, 4)              # 10/03 실측처럼 실시간보다 느렸다 → 다음엔 4
    assert T._tuned_cap("RTX 3060") == 4 and T.batch_for_gpu(8, "large-v3", ("RTX 3060", 12.0, 11.0), 4) == 4


def test_align_waits_for_face_but_not_research(tmp_path):
    from studio import pipeline as pl
    from studio.util import CancelToken
    p = object.__new__(pl.Pipeline)
    p.cancel = CancelToken()
    p._stage_done = {k: threading.Event() for k in pl.STAGE_LABEL}
    done = []
    th = threading.Thread(target=lambda: (p._await_stage("face"), done.append(time.time())))
    th.start()
    time.sleep(0.3)
    assert not done
    t_set = time.time()
    p._stage_done["face"].set()
    th.join(timeout=3)
    assert done and done[0] >= t_set
    lane = next(lane for st in pl.SCHEDULE for lane in st if "align" in lane)
    assert "research" not in lane and lane[-2:] == ["asr", "align"]
