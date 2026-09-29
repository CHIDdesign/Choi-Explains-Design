"""핵심 로직 단위 테스트 (GPU·네트워크·ffmpeg 불필요).  python -m pytest tests -q"""
from __future__ import annotations

import json
import sys
import xml.dom.minidom
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.director import fallback  # noqa: E402
from studio.director.context import JobBrief  # noqa: E402
from studio.director.plan import graphic_from_tag, normalize_long, normalize_shorts, time_graphics  # noqa: E402
from studio.director.schema import LONG_PLAN, SHORTS_PLAN  # noqa: E402
from studio.edit.cuts import PACES, build_keeps, keeps_for_segments  # noqa: E402
from studio.export.premiere import export_xml  # noqa: E402
from studio.models import Span, Tag, TimeMap, Word  # noqa: E402
from studio.text.align import ScriptAligner, build_utterances  # noqa: E402
from studio.text.captions import build_cues, build_short_chunks, cues_to_srt  # noqa: E402
from studio.text.script import parse_script  # noqa: E402

SCRIPT = """# 들어가며
안녕하세요. 오늘은 [도식: 더블다이아몬드 | 정의] 더블 다이아몬드 이야기를 해볼게요.
[강조: 발산] 디자인은 먼저 넓게 펼쳐야 합니다. 그 다음에 좁히죠.
[숏폼 시작]사실 대부분의 학생들은 이 단계를 건너뜁니다. [줌]정말로요.[숏폼 끝]
[비교: 발산 : 넓게 ; 많이 | 수렴 : 좁게 ; 깊게]
"""


def _words(spoken: list[tuple[str, float]], per: float = 0.35) -> list[Word]:
    out, t = [], 0.5
    for sent, gap in spoken:
        for w in sent.split():
            out.append(Word(w, t, t + per - 0.05))
            t += per
        t += gap
    return out


def _aligned(per: float = 0.35):
    p = parse_script(SCRIPT)
    words = _words([("안녕하세요.", 0.8), ("오늘은 더블 다이어몬드 이야기를 해볼게요.", 0.9),
                    ("디자인은 먼저 넓게", 0.9), ("아 다시 할게요", 1.0),
                    ("디자인은 먼저 넓게 펼쳐야 합니다.", 0.7), ("그 다음에 좁히죠.", 0.8),
                    ("사실 대부분의 학생들은 이 단계를 건너뜁니다.", 0.5), ("정말로요.", 1.0)], per=per)
    utts = build_utterances(words)
    return ScriptAligner(p, {"다이어몬드": "다이아몬드"}).run(utts)


def test_script_tags():
    p = parse_script(SCRIPT)
    kinds = [t.kind for t in p.tags]
    assert kinds == ["chapter", "diagram", "keyword", "short", "zoom", "compare"]
    short = [t for t in p.tags if t.kind == "short"][0]
    assert short.end_pos and short.end_pos > short.pos
    assert "[" not in p.clean


def test_retake_and_meta_removed():
    utts, tags, rep = _aligned()
    statuses = [u.status for u in utts]
    assert statuses.count("retake") == 1
    assert statuses.count("meta") == 1
    assert rep.matched >= 5
    assert all(t.utt_id is not None for t in tags)
    assert len(tags) == len(parse_script(SCRIPT).tags)  # 대본 끝 태그도 빠짐없이
    kept_text = " ".join(u.text for u in utts if u.kept)
    assert "다이아몬드" in kept_text  # 용어 사전 교정


def test_best_take_wins_not_last_take():
    """같은 문장을 두 번 말했을 때 '마지막'이 아니라 '가장 또렷한' 테이크를 남긴다."""
    p = parse_script(SCRIPT)
    words = _words([("안녕하세요.", 0.8), ("오늘은 더블 다이아몬드 이야기를 해볼게요.", 1.2),
                    ("음 오늘은 어 더블 더블 다이아몬드 이야기를 해볼게요.", 1.0),
                    ("디자인은 먼저 넓게 펼쳐야 합니다.", 0.7)])
    for w in words[1:6]:
        w.prob = 0.97          # 첫 테이크: 또렷
    for w in words[6:14]:
        w.prob = 0.55          # 둘째 테이크: 웅얼거림 + 추임새 + 말더듬
    utts, _, rep = ScriptAligner(p).run(build_utterances(words))
    first = next(u for u in utts if u.asr_text.startswith("오늘은"))
    second = next(u for u in utts if u.asr_text.startswith("음 오늘은"))
    assert first.kept and second.status == "retake"
    assert f"#{first.id}" in second.note and first.take_score > second.take_score


def test_partial_take_loses_to_complete_take():
    p = parse_script(SCRIPT)
    words = _words([("디자인은 먼저 넓게 펼쳐야 합니다.", 1.2), ("디자인은 먼저", 1.0)])
    utts, _, _ = ScriptAligner(p).run(build_utterances(words))
    assert [u.status for u in utts] == ["keep", "retake"]  # 나중 테이크여도 중간에 끊겼으면 버린다


def test_cuts_and_timemap():
    utts, _, _ = _aligned()
    keeps = build_keeps(utts, pace=PACES["calm"], vad=[], media_duration=30, fps=30)
    tm = TimeMap(keeps)
    assert tm.duration < 30
    for k in keeps:  # 프레임 격자
        assert abs(k.start * 30 - round(k.start * 30)) < 1e-6
    first = next(u for u in utts if u.kept)
    assert tm.src_to_edit(first.words[0].start) is not None
    # 재배치 편집
    ids = [u.id for u in utts if u.kept]
    sk = keeps_for_segments(utts, [ids[-1]] + ids[:2], pace=PACES["shorts"], vad=[], media_duration=30, fps=30)
    stm = TimeMap(sk, preserve_order=True)
    assert not stm.monotonic
    mapped = stm.map_words(utts[-1].words)
    assert mapped and mapped[0].start < 1.0


def test_captions():
    ws = [Word(w, i * 0.4, i * 0.4 + 0.35) for i, w in enumerate(
        "디자인은 먼저 넓게 펼쳐야 합니다. 그 다음에 좁히죠. 사실 대부분의 학생들은 이 단계를 건너뜁니다.".split())]
    cues = build_cues([ws], emphasis={(0.8, "넓게")})
    assert all(c["lines"] and all(line for line in c["lines"]) for c in cues)
    assert any(w.get("em") for c in cues for line in c["lines"] for w in line)
    for c in cues:
        for line in c["lines"]:
            assert len(" ".join(w["text"] for w in line)) <= 20
    chunks = build_short_chunks([ws])
    assert all(len(c["lines"][0]) <= 3 for c in chunks)
    assert "-->" in cues_to_srt(cues)


def test_tag_to_graphic():
    t = Tag("diagram", ["더블다이아몬드", "정의"], "", 0)
    g = graphic_from_tag(t, 3)
    assert g["template"] == "double_diamond" and g["highlight"] == 1
    t = Tag("compare", ["발산 : 넓게 ; 많이", "수렴 : 좁게 ; 깊게"], "", 0)
    g = graphic_from_tag(t, 3)
    assert g["title"] == "발산" and g["items_b"] == ["좁게", "깊게"]


def test_plan_normalize_and_timing():
    utts, tags, _ = _aligned(per=0.8)
    brief = JobBrief(title="테스트")
    raw = fallback.long_plan(brief, utts, tags)
    raw["graphics"].append({"template": "nope"})  # 잘못된 항목은 버려져야 함
    plan = normalize_long(raw, utts, tags)
    templates = {g["template"] for g in plan["graphics"]}
    assert {"double_diamond", "keyword", "compare"} <= templates
    tm = TimeMap(build_keeps(utts, pace=PACES["calm"], vad=[], media_duration=60, fps=30))
    timed = time_graphics(plan["graphics"], utts, tm, total=tm.duration)
    for a, b in zip(timed, timed[1:]):
        assert a.end <= b.start + 1e-6  # 겹치지 않음
    shorts = normalize_shorts({"shorts": [{"segments": [u.id for u in utts if u.kept], "cold_open_seg": -1,
                                           "hook_type": "bogus", "graphics": [], "emphasis": []}]}, utts, count=1)
    assert shorts and shorts[0]["hook_type"] == "open_loop"


def test_schema_is_strict():
    def walk(s):
        if s.get("type") == "object":
            assert s.get("additionalProperties") is False
            assert set(s["required"]) == set(s["properties"])
            for v in s["properties"].values():
                walk(v)
        if s.get("type") == "array":
            walk(s["items"])
    walk(LONG_PLAN)
    walk(SHORTS_PLAN)
    json.dumps(LONG_PLAN)


def test_premiere_xml(tmp_path):
    dst = tmp_path / "a.xml"
    export_xml(dst, name="테스트", video=tmp_path / "원본 영상.mp4", audio=tmp_path / "voice.wav", src_fps=29.97,
               src_duration=60, width=3840, height=2160, seq_width=1920, seq_height=1080,
               keeps=[Span(1, 3), Span(5, 9.5)], markers=[(1.0, "챕터", "메모 & <특수문자>")])
    doc = xml.dom.minidom.parse(str(dst))
    assert len(doc.getElementsByTagName("clipitem")) == 4
    assert doc.getElementsByTagName("ntsc")[0].firstChild.data == "TRUE"


def test_camera_shots_mask_big_jumps():
    from studio.render.props import camera_shots
    tm = TimeMap([Span(0, 5), Span(5.6, 9), Span(12, 20), Span(20.5, 40), Span(41, 60)])
    shots = camera_shots(tm, tm.duration, [0.0, 30.0])
    starts = [s["start"] for s in shots]
    assert 8.4 in starts           # NG 제거(3초 건너뜀) 지점은 프레이밍 전환
    assert 16.4 not in starts      # 짧은 쉼 컷은 12초 안 지났으면 유지
    assert 30.0 in starts and shots[starts.index(30.0)]["zoom"] == 1.0  # 챕터는 와이드로
    assert all(s["zoomEnd"] <= s["zoom"] * 1.036 for s in shots)
