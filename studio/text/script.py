"""대본 파싱: 연출 태그 추출 + 정제 텍스트 + 문장 분리.

대본 태그 문법 (docs/대본_태그_가이드.md 참고)
    [챕터: 문제를 다시 정의하기]      또는  # 문제를 다시 정의하기
    [도식: 더블다이아몬드 | 정의]      → 도식 + 강조할 단계
    [강조: 발산]
    [정의: 발산적 사고 | Divergent Thinking | 가능한 많은 대안을 펼치는 사고]
    [인용: 좋은 디자인은 가능한 적게 디자인하는 것이다 | 디터 람스 | 10 Principles]
    [이미지: Braun SK 4]               → 로컬 이미지 파일명 또는 검색어
    [목록: 좋은 질문의 조건 | 구체적이다 ; 열려있다 ; 사용자를 향한다]
    [비교: 발산 : 넓게 ; 많이 | 수렴 : 좁게 ; 깊게]
    [단계: 디자인 씽킹 | 공감 ; 정의 ; 아이디어 ; 프로토타입 ; 테스트 | 2]
    [숫자: 85% | 사용성 문제를 5명이 찾아낸다]
    [줌]  [숏폼 시작] ... [숏폼 끝]  [메모: 여기는 천천히]
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import Tag

TAG_ALIASES: dict[str, str] = {
    "챕터": "chapter", "장": "chapter", "chapter": "chapter", "섹션": "chapter",
    "도식": "diagram", "다이어그램": "diagram", "diagram": "diagram", "그림": "diagram",
    "강조": "keyword", "키워드": "keyword", "keyword": "keyword", "자막강조": "keyword",
    "정의": "definition", "용어": "definition", "definition": "definition",
    "인용": "quote", "quote": "quote", "명언": "quote",
    "이미지": "photo", "사진": "photo", "image": "photo", "photo": "photo", "자료화면": "photo",
    "목록": "list", "리스트": "list", "list": "list",
    "비교": "compare", "대조": "compare", "compare": "compare", "vs": "compare",
    "단계": "process", "프로세스": "process", "process": "process", "순서": "process",
    "순환": "cycle", "사이클": "cycle", "cycle": "cycle",
    "매트릭스": "matrix", "사분면": "matrix", "matrix": "matrix", "2x2": "matrix",
    "타임라인": "timeline", "연표": "timeline", "timeline": "timeline", "연대기": "timeline",
    "숫자": "stat", "통계": "stat", "stat": "stat", "수치": "stat",
    "벤": "venn", "벤다이어그램": "venn", "venn": "venn",
    "피라미드": "pyramid", "위계": "pyramid", "pyramid": "pyramid",
    "줌": "zoom", "zoom": "zoom", "펀치": "zoom",
    "숏폼": "short", "쇼츠": "short", "릴스": "short", "short": "short", "shorts": "short",
    "메모": "note", "note": "note", "연출": "note",
    "음악": "music", "bgm": "music",
    "컷": "cut", "삭제": "cut", "cut": "cut",
}

TAG_RE = re.compile(r"\[([^\[\]\n]{1,300})\]")
HEADING_RE = re.compile(r"^\s{0,3}#{1,4}\s+(.+?)\s*#*\s*$")
SENT_END_RE = re.compile(r"(?<=[.?!…。？！])[\"'”’)]*\s+|\n+")


@dataclass
class ParsedScript:
    raw: str
    clean: str                  # 태그/마크다운을 제거한 발화 텍스트
    tags: list[Tag]
    sentences: list[tuple[int, int, str]]  # (start, end, text) — clean 기준

    @property
    def has_text(self) -> bool:
        return bool(self.clean.strip())


def _normalize_kind(head: str) -> tuple[str, list[str]]:
    head = head.strip()
    # "숏폼 시작" 처럼 인자 없이 공백으로 붙은 경우
    first, _, rest = head.partition(" ")
    key = first.strip().lower()
    kind = TAG_ALIASES.get(key) or TAG_ALIASES.get(head.lower())
    extra = [rest.strip()] if rest.strip() and kind else []
    return (kind or "unknown"), extra


def parse_tag(body: str) -> tuple[str, list[str]]:
    m = re.match(r"\s*([^:：]+)[:：](.*)$", body, re.S)
    if m:
        head, argstr = m.group(1), m.group(2)
        kind, extra = _normalize_kind(head)
        args = extra + [a.strip() for a in argstr.split("|")]
    else:
        kind, extra = _normalize_kind(body)
        args = extra
    args = [a for a in args if a != ""]
    return kind, args


def parse_script(raw: str) -> ParsedScript:
    raw = (raw or "").replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    tags: list[Tag] = []
    pos = 0  # clean 텍스트 길이

    for line in raw.split("\n"):
        m = HEADING_RE.match(line)
        if m:
            tags.append(Tag("chapter", [m.group(1).strip()], line.strip(), pos))
            continue
        # 마크다운 장식 제거
        line = re.sub(r"^\s*(?:[-*>]+|\d+[.)])\s+", "", line)
        line = line.replace("**", "").replace("__", "")
        cursor = 0
        buf: list[str] = []
        for tm in TAG_RE.finditer(line):
            seg = line[cursor:tm.start()]
            buf.append(seg)
            pos_here = pos + len("".join(buf))
            body = tm.group(1).strip()
            kind, args = parse_tag(body)
            if kind == "unknown":
                # 대괄호가 태그가 아니라 본문인 경우 그대로 둔다
                buf.append(tm.group(0))
            else:
                tags.append(Tag(kind, args, tm.group(0), pos_here))
            cursor = tm.end()
        buf.append(line[cursor:])
        text = re.sub(r"[ \t]+", " ", "".join(buf)).strip()
        if text:
            out.append(text)
            pos += len(text) + 1
        else:
            # 빈 줄: 문단 구분
            pass
    clean = "\n".join(out)
    # 태그 위치가 clean 길이를 넘지 않게
    for t in tags:
        t.pos = min(t.pos, len(clean))
    _pair_range_tags(tags)
    return ParsedScript(raw=raw, clean=clean, tags=tags, sentences=split_sentences(clean))


def _pair_range_tags(tags: list[Tag]) -> None:
    """[숏폼 시작] … [숏폼 끝] 을 하나의 범위 태그로 합친다."""
    open_tag: Tag | None = None
    remove: list[Tag] = []
    for t in tags:
        if t.kind != "short":
            continue
        a0 = (t.args[0] if t.args else "").strip()
        if a0 in ("시작", "start", "begin"):
            open_tag = t
            t.args = t.args[1:]
        elif a0 in ("끝", "end", "종료") and open_tag is not None:
            open_tag.end_pos = t.pos
            remove.append(t)
            open_tag = None
    for t in remove:
        tags.remove(t)


def split_sentences(clean: str) -> list[tuple[int, int, str]]:
    sents: list[tuple[int, int, str]] = []
    start = 0
    for m in SENT_END_RE.finditer(clean):
        end = m.start()
        text = clean[start:end].strip()
        if text:
            s = clean.find(text, start)
            sents.append((s, s + len(text), text))
        start = m.end()
    tail = clean[start:].strip()
    if tail:
        s = clean.find(tail, start)
        sents.append((s, s + len(tail), tail))
    return sents


def glossary_terms(parsed: ParsedScript, extra: list[str] | None = None, limit: int = 60) -> list[str]:
    """Whisper 힌트용 핵심 용어: 태그 인자, 영문 단어, 따옴표 속 용어."""
    terms: list[str] = []
    for t in parsed.tags:
        for a in t.args:
            for piece in re.split(r"[;,/·:：]", a):
                piece = piece.strip()
                if 1 < len(piece) <= 20:
                    terms.append(piece)
    terms += re.findall(r"[A-Za-z][A-Za-z0-9\-\.]{2,}(?:\s[A-Z][A-Za-z0-9\-]+)*", parsed.clean)
    terms += re.findall(r"[‘'\"“]([^’'\"”]{2,20})[’'\"”]", parsed.clean)
    if extra:
        terms += extra
    seen: set[str] = set()
    uniq: list[str] = []
    for t in terms:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(t)
    return uniq[:limit]
