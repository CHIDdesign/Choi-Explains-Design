"""디자인 취향 업그레이드(채널 주인 2026-10-04: "PPT 같다 — 디자인 taste 를 대폭 업그레이드") 단위 테스트 — 진짜 Claude 없이:
🎯 장면 평가 기억·레퍼런스 보드 · 🎨 스타일 프레임이 모션·시그니처 장면보다 먼저 서고 디자인 역할만 그 그림·규칙을 받는다 ·
🧑‍⚖️ 시안 경쟁(첫 안만 웹 도구, 렌더한 그림으로 심사, 이긴 시안 + 심사의 지적 반영) · 미리보기 프레임."""
from __future__ import annotations

import json
import re
import shutil
import sys
import threading
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.agents import studio as ST  # noqa: E402
from studio.agents import taste  # noqa: E402
from studio.director.context import JobBrief  # noqa: E402
from studio.motion.check import preview_images  # noqa: E402

EX = json.loads((ROOT / "prompts" / "examples" / "card_examples.json").read_text(encoding="utf-8"))


@pytest.fixture()
def taste_dir(tmp_path, monkeypatch):
    d = tmp_path / "taste"
    monkeypatch.setattr(taste, "TASTE_DIR", d)
    return d


def _jpg(path: Path, color=(200, 80, 40)) -> Path:
    Image.new("RGB", (320, 180), color).save(path)
    return path


def test_scene_ratings_become_memory_notes_and_board(tmp_path, taste_dir):
    still = _jpg(tmp_path / "g3.jpg")
    n = taste.record([{"gid": "g3", "verdict": "up", "note": "큰 숫자 하나가 좋다", "title": "38%", "kind": "card",
                       "still": str(still)},
                      {"gid": "g4", "verdict": "down", "note": "제목 + 목록, PPT 같다", "title": "세 가지", "kind": "keyword"},
                      {"gid": "g5", "verdict": ""}], job="job1")
    assert n == 2
    assert (taste_dir / "liked" / "job1_g3.jpg").exists()
    notes = taste.notes_block()
    assert notes.startswith("## 🎯 운영자 취향 메모") and "👍 card · 38% — 큰 숫자 하나가 좋다" in notes
    assert notes.index("PPT 같다") < notes.index("큰 숫자")                      # 최근 것이 위
    # 같은 장면을 다시 평가하면 바뀐다(좋아함 → 싫어함: 그림도 옮긴다, 기억은 하나)
    taste.record([{"gid": "g3", "verdict": "down", "note": "다시 보니 빈약", "still": str(still)}], job="job1")
    assert not (taste_dir / "liked" / "job1_g3.jpg").exists() and (taste_dir / "disliked" / "job1_g3.jpg").exists()
    mem = taste.load_memory()
    assert [m["gid"] for m in mem].count("g3") == 1 and len(mem) == 2
    # 보드: 운영자 레퍼런스 · 싫어한 장면(피할 것) — 좋아한 장면은 이제 없다
    _jpg(taste_dir / "ref1.png", (30, 30, 30))
    labels = [b[0] for b in taste.board_images()]
    assert labels == ["운영자 레퍼런스 보드", "운영자가 싫어한 장면(👎 — 피할 것)"]
    assert (taste.taste_dir() / "여기에_레퍼런스_그림을_넣으세요.txt").exists()


def test_empty_taste_dir_gives_no_board_or_notes(taste_dir):
    assert taste.board_images() == [] and taste.notes_block() == ""


# ---------------------------------------------------------------------------
# 스튜디오: 스타일 프레임 → 시안 경쟁 → 심사
# ---------------------------------------------------------------------------

class FakeClaude:
    def __init__(self):
        self.calls: list[dict] = []
        self.lock = threading.Lock()

    def structured(self, *, system, shared_context, instruction, schema, images=None, label="", **kw):
        key = next(k for k, a in ST.AGENTS.items() if a.schema is schema)
        with self.lock:
            self.calls.append({"key": key, "instruction": instruction, "images": [i[0] for i in images or []],
                               "tools": kw.get("tools") or (), "label": label})
        if key == "director":
            return {"title": "t", "logline": "l", "thesis": "좋은 디자인은 설명이 필요 없다", "beats": [], "structure": [],
                    "treatment": {"concept": "모이는 점", "motifs": ["점"],
                                  "signature_scenes": [{"id": "sig1", "start_seg": 2, "end_seg": 3, "kind": "diagram",
                                                        "title": "근접성 도식", "brief": "점이 무리를 짓는다"}]}}
        if key == "style_frame":
            ex = EX["statement"]
            return {"archetype": "statement", "html": ex["html"], "timeline": ex["timeline"],
                    "rules": {"grid": "왼쪽 150px 축", "type": "제목 150px", "color": "오렌지는 한 낱말", "shape": "모서리 28px",
                              "motif": "모이는 점", "motion": "어절 마스크 상승", "do": ["주인공 하나"], "dont": ["가운데 3단"]},
                    "notes": "보드의 statement 결"}
        if key == "setpiece":
            k = int(re.search(r"이번 시안의 방향 \((\d)/", instruction).group(1))
            name = ("statement", "object_callouts", "data_bars")[k - 1]
            return {"layout": "fullscreen", "style": "editorial", "archetype": EX[name]["archetype"], "title": name,
                    "html": EX[name]["html"], "timeline": EX[name]["timeline"], "start_word": "", "notes": name}
        if key == "design_judge":
            return {"ranking": [{"variant": 1, "score": 7.0, "strengths": "", "flaws": ""},
                                {"variant": 2, "score": 8.5, "strengths": "", "flaws": ""}],
                    "winner": 2, "reason": "주인공이 분명", "fix": "라벨을 40px 로"}
        if key == "card_revise":
            m = re.search(r"```html\n(.*?)\n```", instruction, re.S)
            return {"html": m.group(1) if m else "", "timeline": "", "changes": "라벨 키움"}
        if key == "motion":
            return {"graphics": [], "scenes": [], "cards": []}
        return {}


def _preview(items):
    return {it["id"]: {"ok": True, "problems": [],
                       "images": [(it["label"], b"still", "image/jpeg"), (it["label"] + "#seq", b"seq", "image/jpeg")]}
            for it in items}


def test_style_frame_first_then_variants_judged_and_fixed(taste_dir):
    fc = FakeClaude()
    st = ST.Studio(fc, workers=4, use_stock=False)
    st.preview = _preview
    st.house_board = lambda: b"board"
    st.variants = 3
    raw, _ = st.plan(JobBrief(title="t"), "ctx", shorts_count=0)
    keys = [c["key"] for c in fc.calls]
    # 🎨 스타일 프레임이 모션·시그니처 장면보다 먼저 — 하우스 예시 보드(운영자 그림이 없을 때)를 보고 짓는다
    assert keys.index("style_frame") < min(keys.index("motion"), keys.index("setpiece")), keys
    sf = next(c for c in fc.calls if c["key"] == "style_frame")
    assert sf["images"] == ["하우스 예시 보드(렌더로 확인한 카드 예시 — 이 수준이 바닥)"]
    # 🛠 시안 셋 — 첫 안만 웹 도구, 모두 스타일 프레임 규칙 + 그림(정지·움직임) + 보드를 받는다
    sets = [c for c in fc.calls if c["key"] == "setpiece"]
    assert len(sets) == 3 and sum(1 for c in sets if c["tools"]) == 1
    for c in sets:
        assert "## 🎨 이 영상의 스타일 프레임" in c["instruction"] and "모이는 점" in c["instruction"]
        assert c["images"][:2] == ["스타일 프레임", "스타일 프레임#seq"] and len(c["images"]) == 3
    motion = next(c for c in fc.calls if c["key"] == "motion")
    assert "## 🎨 이 영상의 스타일 프레임" in motion["instruction"] and len(motion["images"]) == 3
    # 디자인 역할이 아닌 역할은 스타일 프레임을 받지 않는다(토큰)
    ed = next(c for c in fc.calls if c["key"] == "editor")
    assert "스타일 프레임" not in ed["instruction"] and not ed["images"]
    # 🧑‍⚖️ 심사: 기준 그림(3) + 시안마다 정지·움직임(6) → V2 → 지적을 카드 수정으로 반영(스타일 프레임 정지 화면 + 이긴 시안 그림)
    judge = next(c for c in fc.calls if c["key"] == "design_judge")
    assert len(judge["images"]) == 9 and judge["images"][3:5] == ["V1", "V1#seq"], judge["images"]
    rev = next(c for c in fc.calls if c["key"] == "card_revise")
    assert "라벨을 40px 로" in rev["instruction"] and rev["images"] == ["스타일 프레임", "V2", "V2#seq"]
    sig = [g for g in raw["graphics"] if g.get("signature")]
    assert len(sig) == 1 and sig[0]["card"]["archetype"] == "object_callouts" and sig[0]["card"]["id"] == "card1"
    assert "[B안/3]" in sig[0]["reason"]
    assert raw["studio"]["style_frame"]["rules"]["motif"] == "모이는 점" and raw["studio"]["style_frame"]["html"]


def test_one_variant_means_no_contest_and_style_frame_can_be_off(taste_dir):
    fc = FakeClaude()
    st = ST.Studio(fc, workers=4, use_stock=False)
    st.preview = _preview
    st.style_on = False
    st.variants = 1

    real = fc.structured

    def no_hint(**kw):          # 시안 방향 없이 부르면 A안 예시
        if "이번 시안의 방향" not in kw["instruction"] and next(
                k for k, a in ST.AGENTS.items() if a.schema is kw["schema"]) == "setpiece":
            kw = dict(kw, instruction=kw["instruction"] + "\n## 이번 시안의 방향 (1/1)")
        return real(**kw)
    fc.structured = no_hint
    raw, _ = st.plan(JobBrief(title="t"), "ctx", shorts_count=0)
    keys = [c["key"] for c in fc.calls]
    assert "style_frame" not in keys and "design_judge" not in keys and keys.count("setpiece") == 1
    assert all("스타일 프레임" not in c["instruction"] for c in fc.calls)
    assert "style_frame" not in raw["studio"]


def test_failed_render_or_judge_keeps_first_variant(taste_dir):
    fc = FakeClaude()
    st = ST.Studio(fc, workers=2, use_stock=False)
    st.variants = 2
    st.preview = None                      # 미리보기를 못 하면 심사도 없다 — A안
    raw, _ = st.plan(JobBrief(title="t"), "ctx", shorts_count=0)
    keys = [c["key"] for c in fc.calls]
    assert keys.count("setpiece") == 2 and "design_judge" not in keys and "card_revise" not in keys
    sig = next(g for g in raw["graphics"] if g.get("signature"))
    assert sig["card"]["archetype"] == "statement"


def test_saved_style_frame_is_reloaded_for_later_design_calls(taste_dir):
    fc = FakeClaude()
    st = ST.Studio(fc)
    st.load_style({"rules": {"motif": "트레이싱지 선", "do": ["선 3px"]}, "archetype": "bento"},
                  [("스타일 프레임", b"x", "image/jpeg")])
    st.call("card_revise", "ctx", "고친다")
    st.call("copy", "ctx", "카피")
    rev, cp = fc.calls[-2], fc.calls[-1]
    assert "트레이싱지 선" in rev["instruction"] and rev["images"] == ["스타일 프레임"]
    assert "트레이싱지 선" not in cp["instruction"] and not cp["images"]


def test_operator_notes_reach_design_roles_only(tmp_path, taste_dir):
    taste.record([{"gid": "g1", "verdict": "down", "note": "가운데 정렬 목록은 싫다", "kind": "card"}], job="j")
    fc = FakeClaude()
    st = ST.Studio(fc)
    st._board = []
    st.call("motion", "ctx", "짓는다")
    st.call("editor", "ctx", "자른다")
    assert "가운데 정렬 목록은 싫다" in fc.calls[0]["instruction"]
    assert "가운데 정렬 목록은 싫다" not in fc.calls[1]["instruction"]


def test_preview_images_picks_settled_frame_and_builds_sheet(tmp_path):
    shots = []
    for k, t in enumerate((0.5, 1.0, 2.0, 2.9, 7.6)):
        shots.append({"t": t, "path": str(_jpg(tmp_path / f"s{k}.jpg", (40 * k, 80, 120)))})
    out = preview_images({}, {"shots": shots, "metrics": {"settle": 3.0}}, label="V1")
    assert [o[0] for o in out] == ["V1", "V1#seq"]
    assert out[0][1] == Path(shots[3]["path"]).read_bytes()             # 정착에 가장 가까운 칸
    with Image.open(__import__("io").BytesIO(out[1][1])) as sheet:
        assert sheet.width > 1000                                          # 다섯 칸 시트


def test_checker_takes_auto_preview_shots(tmp_path):
    """check.mjs shots='auto': 정착을 잰 뒤 0.5초 · 35% · 70% · 정착 · 머무는 끝 — 스타일 프레임·시안 심사가 보는 그림."""
    from studio.motion.card import clean_card
    from studio.motion.check import check_cards
    from studio.render.remotion import find_node
    browser = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"
    if not (shutil.which("node") and Path(browser).exists() and (ROOT / "renderer" / "node_modules").exists()):
        pytest.skip("node·브라우저·renderer/node_modules 가 있어야 한다")
    ex = EX["statement"]
    card = clean_card({"html": ex["html"], "timeline": ex["timeline"]}, layout="fullscreen", card_id="pv1")
    res = check_cards([dict(card, shots="auto")], node=find_node(""), out_dir=tmp_path, fps=30, durations={"pv1": 7.0},
                      browser_executable=browser)
    r = res["pv1"]
    assert r["ok"], r["problems"]
    ts = [s["t"] for s in r["shots"]]
    assert len(ts) == 5 and ts == sorted(ts) and ts[0] == 0.5 and abs(ts[3] - r["metrics"]["settle"]) < 0.01
    imgs = preview_images(card, r, label="스타일 프레임")
    assert [i[0] for i in imgs] == ["스타일 프레임", "스타일 프레임#seq"]
    # 0.5초 화면과 정착 화면은 다르다(움직임이 있다)
    assert Path(r["shots"][0]["path"]).read_bytes() != Path(r["shots"][3]["path"]).read_bytes()
