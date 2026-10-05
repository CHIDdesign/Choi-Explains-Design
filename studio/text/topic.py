"""주제 설명글의 라벨 읽기 — 채널 주인이 '제목: 000의 0000' 처럼 적은 것을 알아듣는다.

2026-10-04 채널 주인: "제목: 000의 0000 이라고 쓰면 라벨을 떼고 그 값을 제목으로 써야지, '제목: …' 을 통째로 타이틀 카드에
찍어 버리면 어떡하나." 주제 설명의 줄마다 `라벨: 값`(또는 `[라벨] 값`)을 읽어 제목·부제·키워드·대상·태그·썸네일 문구로 나누고,
나머지 글은 본문(설명)으로 남긴다. 제목·헤드라인·챕터 제목에 라벨 글자가 남지 않게 `strip_label` 로 한 번 더 지운다.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

LABELS: dict[str, tuple[str, ...]] = {
    "title": ("영상 제목", "영상제목", "제목", "타이틀", "title"),
    "subtitle": ("부제목", "부제", "subtitle"),
    "topic": ("주제", "topic"),
    "keywords": ("핵심 키워드", "핵심어", "키워드", "keywords", "keyword"),
    "audience": ("시청자", "대상", "타깃", "타겟", "audience", "target"),
    "tags": ("태그", "tags"),
    "hashtags": ("해시태그", "hashtags"),
    "thumbnail": ("썸네일 문구", "썸네일 텍스트", "썸네일", "thumbnail"),
    "series": ("시리즈", "series"),
    "tone": ("분위기", "톤", "tone"),
    "description": ("설명", "소개", "개요", "내용", "description"),
}
LIST_FIELDS = ("keywords", "tags", "hashtags")
_KEY_OF = {w.lower(): k for k, ws in LABELS.items() for w in ws}
_ALT = "|".join(re.escape(w) for w in sorted(_KEY_OF, key=len, reverse=True))
# '제목: X' · '제목 : X' · '[제목] X' · '【제목】 X' · '- 제목: X' · 'Title: X'
LINE_RE = re.compile(r"^\s*(?:[-*•·]\s*)?(?:(?P<open>[\[【「])\s*)?(?P<label>" + _ALT + r")\s*(?(open)[\]】」]\s*[:：]?|[:：])\s*(?P<value>.*?)\s*$",
                     re.IGNORECASE)
_LEAD_RE = re.compile(r"^\s*(?:[-*•·]\s*)?(?:[\[【「]\s*)?(?:" + _ALT + r")\s*(?:[\]】」])?\s*[:：]\s*", re.IGNORECASE)
_LEAD_BRACKET_RE = re.compile(r"^\s*[\[【「]\s*(?:" + _ALT + r")\s*[\]】」]\s*", re.IGNORECASE)


@dataclass
class TopicFields:
    title: str = ""
    subtitle: str = ""
    topic: str = ""
    keywords: list[str] = field(default_factory=list)
    audience: str = ""
    tags: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    thumbnail: str = ""
    series: str = ""
    tone: str = ""
    description: str = ""
    body: str = ""          # 라벨 줄을 뺀 나머지 설명글

    def as_dict(self) -> dict[str, Any]:
        """프롬프트·브리프에 넘길 '채널 주인이 정한 것'(비어 있는 칸·본문은 뺀다)."""
        return {k: v for k, v in asdict(self).items() if k != "body" and v}

    @property
    def any(self) -> bool:
        return bool(self.as_dict())


def _split_list(v: str) -> list[str]:
    parts = re.split(r"[,，·/|]|\s{2,}|(?=\s#)", v)
    out = [p.strip().strip("#").strip() for p in parts]
    return [p for p in out if p]


def parse_topic(text: str) -> TopicFields:
    """주제 설명글 → 라벨 값 + 본문. 값이 비어 있으면('제목:' 뒤 줄바꿈) 다음 줄이 값이다."""
    tf = TopicFields()
    lines = (text or "").replace("\r", "").split("\n")
    body: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = LINE_RE.match(ln) if ln.strip() else None
        if not m:
            body.append(ln)
            i += 1
            continue
        key = _KEY_OF.get(m.group("label").lower())
        value = m.group("value").strip()
        if not value and i + 1 < len(lines) and lines[i + 1].strip() and not LINE_RE.match(lines[i + 1]):
            value = lines[i + 1].strip()
            i += 1
        value = value.strip("「」\"'“” ")
        if key and value:
            if key in LIST_FIELDS:
                setattr(tf, key, getattr(tf, key) + _split_list(value))
            elif not getattr(tf, key):
                setattr(tf, key, value)
            else:
                body.append(ln)
        else:
            body.append(ln)
        i += 1
    tf.body = "\n".join(body).strip()
    return tf


def strip_label(text: str) -> str:
    """제목·헤드라인·챕터 제목 앞에 남은 라벨('제목: ', '[제목] ', 'Title: ')을 뗀다. 라벨이 없으면 그대로."""
    s = str(text or "").strip()
    for _ in range(3):
        n = _LEAD_RE.sub("", s, count=1)
        n = _LEAD_BRACKET_RE.sub("", n, count=1)
        if n == s:
            break
        s = n.strip()
    return s


def owner_block(fields: dict[str, Any]) -> str:
    """에이전트 지시·공유 컨텍스트에 붙이는 '채널 주인이 정한 것' 블록(없으면 '')."""
    if not fields:
        return ""
    names = {"title": "제목", "subtitle": "부제", "topic": "주제", "keywords": "키워드", "audience": "대상", "tags": "태그",
             "hashtags": "해시태그", "thumbnail": "썸네일 문구", "series": "시리즈", "tone": "톤", "description": "설명"}
    lines = ["## 채널 주인이 정한 것(주제 설명에 라벨로 적은 것 — 그대로 쓴다. 라벨 글자('제목:')는 화면·제목에 넣지 않는다)"]
    for k, lab in names.items():
        v = fields.get(k)
        if not v:
            continue
        lines.append(f"- {lab}: " + (" · ".join(str(x) for x in v) if isinstance(v, list) else str(v)))
    if fields.get("title"):
        lines.append("- 영상 제목(`title`)·오프닝 타이틀·파일 이름은 위 제목 **그대로**(줄이거나 바꾸지 않는다). 유튜브 제목 5안의 1안도 이것.")
    return "\n".join(lines)
