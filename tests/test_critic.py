"""🧑‍⚖️ 장면 심사(독립 critic, Promptible remotion-motion-graphics-skill 의 visual-critic 을 우리 구조로) — 진짜 Claude 없이:
fail-closed 판정 · 심사 호출이 렌더 그림·말·종류를 받는다 · 설정 design_critic."""
from __future__ import annotations

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.agents import schemas as S  # noqa: E402
from studio.agents import studio as ST  # noqa: E402


def _scores(v: int) -> dict:
    return {k: v for k in S.CRITIC_SCORES}


def test_verdict_is_fail_closed():
    ok, why = ST.critic_verdict({"verdict": "pass", "hard_failures": [], "scores": _scores(8)})
    assert ok and why == []
    assert not ST.critic_verdict({"verdict": "pass", "hard_failures": ["네온 글로우"], "scores": _scores(9)})[0]
    assert not ST.critic_verdict({"verdict": "pass", "hard_failures": [], "scores": {**_scores(9), "motion": 5}})[0]
    ok, why = ST.critic_verdict({"verdict": "pass", "hard_failures": [], "scores": _scores(6)})
    assert not ok and any("평균" in w for w in why)                      # 모두 6 → 평균 6.0 < 7
    assert not ST.critic_verdict({"verdict": "reject", "hard_failures": [], "scores": _scores(8)})[0]
    ok, why = ST.critic_verdict({"verdict": "pass", "hard_failures": [], "scores": {}})
    assert not ok and len(why) == len(S.CRITIC_SCORES)                  # 점수 칸이 비면 통과가 아니다


class FakeClaude:
    def __init__(self):
        self.calls: list[dict] = []
        self.lock = threading.Lock()

    def structured(self, *, system, shared_context, instruction, schema, images=None, label="", **kw):
        key = next(k for k, a in ST.AGENTS.items() if a.schema is schema)
        with self.lock:
            self.calls.append({"key": key, "instruction": instruction, "images": [i[0] for i in images or []], "label": label,
                               "ctx_in_system": kw.get("ctx_in_system")})
        return {"verdict": "reject", "hard_failures": ["가운데 정렬 3단 스택"], "scores": _scores(6), "fix": "제목을 왼쪽 축으로", "notes": "n"}


def test_critique_sends_render_images_speech_and_kind():
    fc = FakeClaude()
    st = ST.Studio(fc, workers=2, use_stock=False)
    st.house_board = lambda: None
    res = st.critique("ctx", "g3", "자유 카드", "좋은 질문이 먼저입니다", [("g3", b"still", "image/jpeg"), ("g3#seq", b"seq", "image/jpeg")])
    assert res["verdict"] == "reject"
    c = fc.calls[-1]
    assert c["key"] == "card_critic" and c["images"] == ["g3", "g3#seq"] and c["ctx_in_system"]
    assert "- `g3`: 정착 시각의 화면" in c["instruction"] and "좋은 질문이 먼저입니다" in c["instruction"] and "자유 카드" in c["instruction"]
    assert "## 하드 실패" in c["instruction"] and "card_critic" in ST.DESIGN_AGENTS and "card_critic" in ST.REF_FULL
    ok, why = ST.critic_verdict(res)
    assert not ok and why[0].startswith("하드 실패")


def test_design_critic_setting_default_on():
    from studio.settings import Settings
    assert Settings().design_critic is True


def test_scene_sheet_collects_qa_stills(tmp_path):
    """🖼 렌더 전 장면 시트: 검수 스틸을 한 장으로 모아 부가자료에 — 렌더(50분)를 기다리지 않고 장면을 본다."""
    from PIL import Image
    from studio.pipeline import scene_sheet
    stills = []
    for i in range(4):
        p = tmp_path / f"g{i}.jpg"
        Image.new("RGB", (1920, 1080), (40 * i, 120, 200)).save(p, quality=70)
        stills.append((f"g{i} card", p))
    out = scene_sheet(stills + [("g9 missing", tmp_path / "nope.jpg")], tmp_path / "out" / "장면시트_렌더전.jpg")
    assert out and out.exists()
    with Image.open(out) as im:
        assert im.width >= 640 * 2 and im.height >= 360 * 2
    assert scene_sheet([], tmp_path / "x.jpg") is None


def test_design_bench_schedule_stops_before_render():
    """🧪 디자인 벤치(until='design'): 검수(자기 검토·장면 심사·장면 시트)까지만 — 렌더·마스터·마무리 칸은 없다."""
    from studio.pipeline import schedule_for
    keys = {k for st in schedule_for("design") for lane in st for k in lane}
    assert {"director", "qa", "music", "stock"} <= keys and not ({"render", "master", "export"} & keys)
    assert {k for st in schedule_for("all") for lane in st for k in lane} >= {"render", "master", "export"}
