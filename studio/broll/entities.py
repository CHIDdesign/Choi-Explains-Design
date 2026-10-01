"""대본에서 '위키백과에 있을 법한 고유명사' 후보를 규칙으로 찾는다(AI 가 놓쳤을 때의 안전망).

보수적으로 잡는다 — 틀린 사진보다 없는 게 낫다:
- 라틴 문자 이름: 대문자로 시작하는 낱말 2~4개(Dieter Rams, Braun SK 4, Massimo Vignelli). 문장 첫 낱말 하나만은 안 잡는다.
- 겹낫표·겹화살괄호 안의 제목: 『디자인의 디자인』 《Less but Better》 「형태는 기능을 따른다」(작품·책)
- 종교·사상 이름: 기독교·불교·이슬람교·힌두교·유대교 …
한국어 인명·브랜드(디터 람스, 바우하우스)는 규칙으로 못 가리므로 🎞 자료 리서처(AI)의 `photos` 가 맡는다.
찾은 후보는 photo 그래픽(wiki=True)이 되고, 위키백과에 문서·자유 이미지가 없으면 스톡으로 넘기지 않고 뺀다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

STOP_FIRST = {"The", "And", "But", "This", "That", "These", "Those", "With", "From", "For", "Not", "Yes", "No", "It",
              "In", "On", "At", "To", "Of", "By", "As", "Is", "Are", "Was", "Were", "Be", "Do", "So", "If", "Or",
              "How", "What", "Why", "When", "Where", "Who", "Which", "Good", "Bad", "New", "Old", "Big",
              "Less", "More", "Simple", "Easy", "Hard", "First", "Last", "Next", "Step", "Rule", "Rules", "Point",
              "Chapter", "Part", "Note", "Today", "Now", "Here", "There", "Then", "Also", "Just", "Very", "Really"}
LATIN_NAME = re.compile(r"(?<![A-Za-z])([A-Z][A-Za-z&.'\-]+(?:\s+(?:[A-Z][A-Za-z&.'\-]+|\d[\dA-Za-z\-]*)){1,3})(?![A-Za-z])")
QUOTED = re.compile(r"[『《「〈]\s*([^『』《》「」〈〉\n]{2,30}?)\s*[』》」〉]")
# 뒤에는 조사가 바로 붙으므로(불교와·기독교의) 뒤쪽 경계는 보지 않는다
RELIGION = re.compile(r"(?<![가-힣])(기독교|천주교|가톨릭|개신교|정교회|불교|이슬람교|이슬람|힌두교|유대교|도교|유교|시크교|조로아스터교)")
MAX_ENTITIES = 12


@dataclass(frozen=True)
class Entity:
    term: str      # 위키백과에서 찾을 말(원문 표기)
    kind: str      # name | work | religion
    pos: int       # 대본 안 위치(첫 등장)


def find_entities(text: str) -> list[Entity]:
    found: dict[str, Entity] = {}

    def add(term: str, kind: str, pos: int) -> None:
        term = " ".join(term.split())
        key = term.lower()
        if len(term) < 2 or key in found:
            return
        found[key] = Entity(term, kind, pos)

    for m in QUOTED.finditer(text):
        add(m.group(1), "work", m.start())
    for m in RELIGION.finditer(text):
        add(m.group(1), "religion", m.start())
    for m in LATIN_NAME.finditer(text):
        words = m.group(1).split()
        if words[0] in STOP_FIRST or all(w in STOP_FIRST for w in words):
            continue
        if sum(1 for w in words if w[0].isupper()) < 2:
            continue
        add(m.group(1), "name", m.start())
    out = sorted(found.values(), key=lambda e: e.pos)
    return out[:MAX_ENTITIES]
