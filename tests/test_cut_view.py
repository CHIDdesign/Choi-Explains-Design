"""✂️ 컷 경계 그림 — 애매한 쉼(150~400ms)·리테이크 비교만 고르고 한 장으로 그린다(studio/text/cut_view.py)."""
import numpy as np
from PIL import Image

from studio.models import Utterance, Word
from studio.text import cut_view as CV


def _utt(i, words, status="keep", span=None):
    return Utterance(i, words[0].start, words[-1].end, " ".join(w.text for w in words), " ".join(w.text for w in words),
                     words=words, script_span=span, status=status)


def test_picks_only_ambiguous_pauses_and_retake_pairs():
    w = [Word("좋은", 0.0, 0.4), Word("음", 0.6, 0.8), Word("디자인은", 1.0, 1.5),      # 음: 앞 0.2초(애매) · 뒤 0.2초
         Word("단순", 3.0, 3.4), Word("어", 3.5, 3.6), Word("합니다", 4.2, 4.6)]        # 어: 앞 0.1(위험) · 뒤 0.6(안전)
    take_a = [Word("정직한", 6.0, 6.5), Word("디자인", 6.6, 7.0)]
    take_b = [Word("정직한", 8.0, 8.5), Word("디자인", 8.6, 9.0)]
    utts = [_utt(0, w), _utt(1, take_a, "retake", (10, 20)), _utt(2, take_b, "keep", (10, 20))]
    removals = [{"start": 0.6, "end": 0.8, "text": "음"}, {"start": 3.5, "end": 3.6, "text": "어"}]
    views = CV.ambiguous_views(utts, removals, w + take_a + take_b)
    assert [v.kind for v in views] == ["retake", "pause"]          # 리테이크 먼저, '음' 경계 하나(앞뒤가 1.5초 안이라 한 장)
    assert "U1" in views[0].rows[0][0] and "U2" in views[0].rows[1][0]
    assert "R0" in views[1].note and [v.id for v in views] == ["V1", "V2"]
    assert "V2" in CV.views_text(views)


def test_render_view_draws_rows_even_without_frames(tmp_path):
    w = [Word("좋은", 0.0, 0.4), Word("디자인", 0.6, 1.0)]
    v = CV.View("V1", "retake", [("뺀", 0.0, 1.0), ("남긴", 0.0, 1.0)], [(0.4, 0.6)], "")
    audio = (np.sin(np.linspace(0, 400, 16000)) * 0.3).astype(np.float32)
    frames = iter([Image.new("RGB", (64, 36), (200, 0, 0)), None] * 8)
    p = CV.render_view(v, audio, w, lambda t: next(frames), tmp_path / "V1.jpg")
    im = Image.open(p)
    assert im.width == CV.W and im.height > 2 * 300
    assert CV.ambiguous_views([], [], []) == [] and CV.views_text([]) == ""
