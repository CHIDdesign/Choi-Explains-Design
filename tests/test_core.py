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


def _write_wav(path: Path, samples, rate: int, channels: int = 1) -> None:
    import wave

    import numpy as np
    data = (np.asarray(samples, dtype=np.float64) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


def test_load_audio_16k_reads_and_resamples(tmp_path):
    import numpy as np
    from studio.asr.transcribe import load_audio_16k

    t = np.arange(16000) / 16000
    tone = 0.5 * np.sin(2 * np.pi * 220 * t)
    _write_wav(tmp_path / "mono16k.wav", tone, 16000)
    a = load_audio_16k(tmp_path / "mono16k.wav")
    assert a.dtype == np.float32 and len(a) == 16000
    assert np.abs(a - tone).max() < 1e-4

    # 48kHz 스테레오 → 16kHz 모노(채널 평균)
    t48 = np.arange(48000) / 48000
    left, right = 0.4 * np.sin(2 * np.pi * 220 * t48), 0.2 * np.sin(2 * np.pi * 220 * t48)
    _write_wav(tmp_path / "st48k.wav", np.stack([left, right], axis=1).ravel(), 48000, channels=2)
    b = load_audio_16k(tmp_path / "st48k.wav")
    assert b.dtype == np.float32 and len(b) == 16000
    assert np.abs(b - 0.3 * np.sin(2 * np.pi * 220 * t)).max() < 1e-3


def test_transcribe_passes_array_and_drops_unknown_options(tmp_path, monkeypatch):
    """faster-whisper 에 경로가 아닌 배열을 넘긴다(PyAV 19 에서 경로 디코딩이 깨짐). 모르는 옵션은 미리 뺀다."""
    import types

    import numpy as np
    from studio.asr import transcribe as tr

    seen: dict = {}

    class FakeModel:
        def __init__(self, *_a, **_k):
            pass

        def transcribe(self, audio, language=None, beam_size=5, word_timestamps=False, vad_filter=False,
                       vad_parameters=None, condition_on_previous_text=True, initial_prompt=None):
            seen["audio"], seen["language"] = audio, language
            if seen.get("raise"):
                raise TypeError("내부 오류")
            w = types.SimpleNamespace(word=" 안녕", start=0.1, end=0.5, probability=0.9)
            seg = types.SimpleNamespace(start=0.0, end=1.0, text=" 안녕", words=[w], avg_logprob=-0.2, no_speech_prob=0.0)
            return iter([seg]), types.SimpleNamespace(duration=1.0, language="ko")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    _write_wav(tmp_path / "asr16k.wav", np.zeros(16000), 16000)
    logs: list[str] = []
    res = tr.transcribe(tmp_path / "asr16k.wav", model_name="tiny", device="cpu", compute_type="int8",
                        hint_terms=["어포던스"], log=logs.append)
    assert isinstance(seen["audio"], np.ndarray) and seen["audio"].dtype == np.float32
    assert len(seen["audio"]) == 16000 and seen["language"] == "ko"
    assert [w["text"] for w in res["words"]] == ["안녕"]
    assert any("hotwords" in m and "hallucination_silence_threshold" in m for m in logs)

    # 라이브러리 안에서 난 TypeError 는 옵션을 빼고 재시도하며 가리지 않고 그대로 올린다
    seen["raise"] = True
    import pytest
    with pytest.raises(TypeError, match="내부 오류"):
        tr.transcribe(tmp_path / "asr16k.wav", model_name="tiny", device="cpu", compute_type="int8")


def test_transcribe_batched_and_memory_fallback(tmp_path, monkeypatch):
    """배치 추론을 쓰고(배치 크기 전달), GPU 메모리가 모자라면 배치를 줄였다가 순차로 다시 한다. 결과는 시간순."""
    import types

    import numpy as np
    from studio.asr import transcribe as tr

    calls: list = []

    def seg(t, text):
        w = types.SimpleNamespace(word=" " + text, start=t + 0.1, end=t + 0.5, probability=0.9)
        return types.SimpleNamespace(start=t, end=t + 1.0, text=" " + text, words=[w], avg_logprob=-0.2,
                                     no_speech_prob=0.0)

    class FakeModel:
        def __init__(self, *_a, **_k):
            pass

        def transcribe(self, audio, language=None, word_timestamps=False, initial_prompt=None):
            calls.append(("seq", None))
            return iter([seg(0.0, "하나"), seg(1.0, "둘")]), types.SimpleNamespace(duration=2.0, language="ko")

    class FakeBatched:
        def __init__(self, model):
            self.model = model

        def transcribe(self, audio, language=None, word_timestamps=False, initial_prompt=None, batch_size=16):
            calls.append(("batch", batch_size))
            if batch_size > 2:
                def boom():
                    raise RuntimeError("CUDA failed with error out of memory")
                    yield  # noqa
                return boom(), types.SimpleNamespace(duration=2.0, language="ko")
            # 섞여 와도 시간순으로 맞춘다
            return iter([seg(1.0, "둘"), seg(0.0, "하나")]), types.SimpleNamespace(duration=2.0, language="ko")

    monkeypatch.setitem(sys.modules, "faster_whisper",
                        types.SimpleNamespace(WhisperModel=FakeModel, BatchedInferencePipeline=FakeBatched))
    tr._MODELS.clear()
    _write_wav(tmp_path / "asr16k.wav", np.zeros(16000), 16000)
    logs: list[str] = []
    res = tr.transcribe(tmp_path / "asr16k.wav", model_name="tiny", device="cpu", compute_type="int8", batch_size=8,
                        log=logs.append)
    assert calls == [("batch", 8), ("batch", 4), ("batch", 2)]
    assert [w["text"] for w in res["words"]] == ["하나", "둘"] and res["info"]["batch"] == 2
    assert any("메모리 부족" in m for m in logs)
    calls.clear()
    tr._MODELS.clear()
    tr.transcribe(tmp_path / "asr16k.wav", model_name="tiny", device="cpu", compute_type="int8", batch_size=1)
    assert calls == [("seq", None)]
    tr._MODELS.clear()


def test_gpu_expected_follows_explicit_setting():
    from studio.asr.transcribe import gpu_expected
    assert gpu_expected("cuda") is True and gpu_expected("cpu") is False


def test_losing_take_keeps_its_unique_script_sentence():
    """A+B 를 한 번에 말한 뒤 B 만 더 또렷하게 다시 말함 → B 는 둘째 테이크, A 는 첫 테이크에서 살아남아야 한다
    (예전엔 첫 테이크가 통째로 retake 가 되어 A 문장이 영상에서 사라졌다)."""
    p = parse_script(SCRIPT)
    words = _words([("안녕하세요.", 0.8),
                    ("디자인은 먼저 넓게 펼쳐야 합니다 그 다음에 좁히죠.", 1.2),
                    ("그 다음에 좁히죠.", 0.8)])
    for w in words[1:10]:
        w.prob = 0.6
    for w in words[10:]:
        w.prob = 0.98
    utts, _, rep = ScriptAligner(p).run(build_utterances(words))
    kept = [u.text for u in utts if u.kept]
    assert any(t.startswith("디자인은 먼저 넓게") for t in kept), kept
    assert sum("좁히죠" in t for t in kept) == 1, kept
    assert rep.trimmed_takes == 1 and rep.script_coverage > 0.3
    assert not any("디자인은 먼저" in m for m in (rep.missing_sentences or []))


def test_shorts_coherence_repairs_stitched_segments_and_prefers_one_good_short():
    """숏폼 PD 가 떨어진 발화를 이어 붙이거나 '그래서…' 로 시작하면 이해 가능성이 떨어진다 → 연속 구간으로 고치고,
    둘째 편은 8점 이상·다른 구간일 때만 남긴다."""
    from studio.director.plan import short_coherence
    from studio.models import Utterance
    texts = ["좋은 디자인은 무엇일까요?", "그래서 저는 질문부터 봅니다.", "문 손잡이를 보면 밀지 당길지 압니다.",
             "이걸 어포던스라고 부릅니다.", "형태가 사용법을 말해 주는 성질이죠.", "결국 좋은 디자인은 설명이 필요 없습니다.",
             "다음 주제는 게슈탈트입니다.", "가까운 것은 한 무리로 보입니다."]
    utts = []
    t = 0.0
    for i, tx in enumerate(texts):
        ws = [Word(w, t + k * 0.9, t + k * 0.9 + 0.8) for k, w in enumerate(tx.split())]
        utts.append(Utterance(i, ws[0].start, ws[-1].end, tx, tx, ws))
        t += len(ws) * 0.9 + 1.0        # 어절마다 0.9초 → 네 문장이면 12초 하한을 넘는다
    kept = [u.id for u in utts]
    by_id = {u.id: u for u in utts}
    good, prob = short_coherence([2, 3, 4, 5], by_id, kept, hook_title="문 손잡이의\n비밀")
    assert good == 1.0 and not prob
    bad, prob = short_coherence([1, 3, 7], by_id, kept, hook_title="색채 이론")
    assert bad < 0.5 and len(prob) >= 3, prob
    raw = {"shorts": [
        {"title": "A", "hook_type": "everyday_why", "hook_title": "문 손잡이의\n비밀", "hook_highlight": "", "cold_open_seg": 5,
         "segments": [2, 4, 7], "graphics": [], "emphasis": [], "beats": [], "cta": "", "loop_line": "", "caption": "",
         "hashtags": [], "viewer_takeaway": "형태가 사용법을 말한다", "why": "", "score": 8},
        {"title": "B", "hook_type": "open_loop", "hook_title": "질문이\n먼저", "hook_highlight": "", "cold_open_seg": -1,
         "segments": [3, 4, 5], "graphics": [], "emphasis": [], "beats": [], "cta": "", "loop_line": "", "caption": "",
         "hashtags": [], "viewer_takeaway": "", "why": "", "score": 7}]}
    logs = []
    out = normalize_shorts(raw, utts, count=2, max_sec=60, log=logs.append)
    assert len(out) == 1, [(s["title"], s["score"], s["coherence"]) for s in out]      # 둘째는 7점·겹침 → 만들지 않음
    a = out[0]
    assert a["segments"] == [5, 2, 3, 4] and a["coherence"] >= 0.7, a["segments"]   # 콜드 오픈 + 연속 구간으로 고침
    assert a["viewer_takeaway"] == "형태가 사용법을 말한다" and "연속 구간으로 고침" in a["why"]
    assert any("연속 구간" in m for m in logs) and any("만들지 않음" in m for m in logs)


def test_highlights_normalized_and_fallback_picks_hooky_sentences():
    utts, tags, _ = _aligned(per=0.8)
    kept = [u.id for u in utts if u.kept]
    raw = fallback.long_plan(JobBrief(title="t"), utts, tags)
    raw["highlights"] = [{"seg": kept[0], "reason": "첫 발화(제외돼야 함)"}, {"seg": kept[-1], "reason": "결론"},
                         {"seg": kept[-1], "reason": "중복"}, {"seg": 999, "reason": "없는 발화"}]
    plan = normalize_long(raw, utts, tags)
    assert plan["highlights"] == [{"seg": kept[-1], "reason": "결론"}]
    # 규칙 후보: 첫 두 발화 뒤, 앞 문맥에 매달리지 않는 짧은 문장만
    hl = fallback.highlight_segs(utts)
    assert all(h["seg"] not in kept[:2] for h in hl)


def test_evidence_shifts_to_free_slot_after_title_card():
    """P0-7(10/1): 홍익대 사진(408.4~414.0)이 타이틀 카드(408.8~412.2, 우선순위 12)에 밀려 지워졌다 — 바로 뒤가 비어 있었다.
    실물 자료는 버리지 않고 다음 빈 자리로 옮긴다(원래 자리에서 8초 안). 도식은 예전처럼 짧아지면 버린다."""
    from studio.director.plan import TimedGraphic, resolve_overlaps
    title = TimedGraphic("title", "title", "fullscreen", 408.8, 412.2, {}, 12, "auto")
    photo = TimedGraphic("g31", "photo", "pip", 408.4, 414.0, {"image": "images/hongik.jpg"}, 6)
    out = resolve_overlaps([title, photo], total=700.0)
    got = {g.id: g for g in out}
    assert "g31" in got and got["g31"].start >= 412.2 and got["g31"].end - got["g31"].start >= 4.0
    # 앞에 같은 우선순위 도식이 있으면 그 뒤로(버리지 않음), 너무 멀어지면(8초 넘게) 그때만 뺀다
    diag = TimedGraphic("g5", "process", "split", 100.0, 107.0, {}, 6)
    stock = TimedGraphic("g33", "broll", "fullscreen", 101.0, 104.0, {"src": "broll/a.mp4"}, 6)
    out = {g.id: g for g in resolve_overlaps([diag, stock], total=700.0)}
    assert out["g33"].start >= 107.0 and out["g33"].end - out["g33"].start >= 3.0
    far = TimedGraphic("g6", "process", "split", 200.0, 215.0, {}, 6)
    stock2 = TimedGraphic("g34", "broll", "fullscreen", 201.0, 204.0, {"src": "broll/b.mp4"}, 6)
    assert "g34" not in {g.id for g in resolve_overlaps([far, stock2], total=700.0)}
    # 사진이 앞에 있고 더 중요한 도식이 곧바로 오면 사진을 도식 뒤로 옮긴다
    ph = TimedGraphic("g40", "photo", "pip", 300.0, 304.0, {}, 6)
    big = TimedGraphic("g41", "process", "fullscreen", 300.5, 305.0, {}, 9)
    out = {g.id: g for g in resolve_overlaps([ph, big], total=700.0)}
    assert out["g41"].start == 300.5 and out["g40"].start >= 305.0


def test_quantize_keeps_reordered_spans_cold_open():
    """2026-10-03 숏폼: 콜드 오픈(S57, 388초)을 맨 앞에 두면 그 뒤의 S47–S56(340초~)이 '앞 구간 끝 뒤'로 밀려 사라졌다
    (45초 → 11.8초). 뒤로 돌아가는 구간은 그대로, 1초 안에서 겹치는 이음새만 앞 구간 끝으로."""
    from studio.edit.cuts import quantize
    from studio.models import Span
    keeps = [Span(388.0, 392.0), Span(340.0, 345.0), Span(344.9, 350.0), Span(393.0, 396.0)]
    out = quantize(keeps, 30.0, 600.0)
    assert [round(k.start, 2) for k in out] == [388.0, 340.0, 345.0, 393.0]      # 재배치 유지 · 겹침 0.1초만 밀림
    assert abs(sum(k.dur for k in out) - (4 + 5 + 5 + 3)) < 0.2
    assert [round(k.start, 2) for k in quantize([Span(10.0, 12.0), Span(11.5, 14.0)], 30.0, 100.0)] == [10.0, 12.0]


def test_false_start_fragment_before_restart_is_cut():
    """2026-10-03 실제 영상: '바로' 한 토막 뒤에 같은 문장을 처음부터 다시 읽었는데, 토막이 '대본 밖' 짧은 발화라 어떤 규칙에도
    안 걸리고 컷 총괄도 '대본 내용'이라 남겨 더듬는 소리가 들어갔다. 바로 뒤 발화가 그 말로 다시 시작하면 앞 토막은 뺀다."""
    p = parse_script(SCRIPT)
    words = _words([("안녕하세요.", 0.8), ("오늘은", 0.6), ("오늘은 더블 다이아몬드 이야기를 해볼게요.", 0.9),
                    ("디자인은 먼저 넓게 펼쳐야 합니다.", 0.7), ("그 다음에 좁히죠.", 0.8)])
    utts, _, _ = ScriptAligner(p).run(build_utterances(words))
    frag = next(u for u in utts if u.asr_text.strip() == "오늘은")
    full = next(u for u in utts if u.asr_text.startswith("오늘은 더블"))
    assert frag.status == "retake" and "끊긴 앞부분" in frag.note and full.kept
    # 같은 말로 시작하는 다른 완결 문장은 둘 다 남는다(8자 넘고 맺은 문장 → 리테이크 판정에 맡김)
    words = _words([("좋은 디자인은 단순합니다.", 0.6), ("좋은 디자인은 정직합니다.", 0.8)])
    utts, _, _ = ScriptAligner(parse_script("좋은 디자인은 단순합니다. 좋은 디자인은 정직합니다.")).run(build_utterances(words))
    assert [u.kept for u in utts] == [True, True]
