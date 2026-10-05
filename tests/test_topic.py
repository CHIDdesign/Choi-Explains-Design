"""주제 설명의 라벨 읽기(studio/text/topic.py) — 2026-10-04 채널 주인: '제목: 000의 0000' 을 라벨째 타이틀 카드에 찍었다."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.director.context import JobBrief, shared_context  # noqa: E402
from studio.pipeline import JobSpec  # noqa: E402
from studio.text.topic import owner_block, parse_topic, strip_label  # noqa: E402


def test_labels_are_read_and_removed_from_the_body():
    tf = parse_topic("제목: 000의 0000\n부제 : 왜 질문이 먼저인가\n[키워드] 디자인, 질문 · 더블 다이아몬드\n썸네일:\n질문이 먼저\n\n"
                     "이 영상은 디자인 과정에서 질문의 역할을 설명한다.")
    assert tf.title == "000의 0000" and tf.subtitle == "왜 질문이 먼저인가" and tf.thumbnail == "질문이 먼저"
    assert tf.keywords == ["디자인", "질문", "더블 다이아몬드"]
    assert tf.body == "이 영상은 디자인 과정에서 질문의 역할을 설명한다."
    assert "- 제목: 000의 0000" in owner_block(tf.as_dict()) and "그대로" in owner_block(tf.as_dict())
    assert not parse_topic("디자인 이야기를 편하게 적은 설명").any and owner_block({}) == ""


def test_strip_label_removes_only_leading_labels():
    assert strip_label("제목: 질문이 먼저다") == "질문이 먼저다"
    assert strip_label("【제목】질문이 먼저다") == "질문이 먼저다"
    assert strip_label("Title: Why ask first") == "Why ask first"
    assert strip_label("- 타이틀 : X") == "X" and strip_label("제목:제목: X") == "X"
    assert strip_label("질문이 먼저다") == "질문이 먼저다" and strip_label("제목이 중요하다") == "제목이 중요하다"


def test_working_title_and_brief_use_the_owner_title():
    spec = JobSpec(video="a.mp4", topic="제목: 000의 0000\n\n설명이 길게 이어진다.")
    assert spec.working_title() == "000의 0000" and spec.owner_fields()["title"] == "000의 0000"
    assert JobSpec(video="a.mp4", topic="게슈탈트 원리 — 입문자용").working_title() == "게슈탈트 원리 — 입문자용"
    assert JobSpec(video="a.mp4", title="제목: X").working_title() == "X"
    ctx = shared_context(JobBrief(title="000의 0000", owner=spec.owner_fields()), [], [], None, 60.0)
    assert "## 채널 주인이 정한 것" in ctx and "- 제목: 000의 0000" in ctx
    assert "채널 주인이 정한 것" not in shared_context(JobBrief(title="t"), [], [], None, 60.0)
