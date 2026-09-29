"""API 키 없이도 동작하는 규칙 기반 디렉터.

대본 태그를 그대로 그래픽으로 만들고, 챕터·숏폼 후보를 휴리스틱으로 고른다.
Claude 결과와 같은 JSON 모양을 반환하므로 이후 단계는 동일하다.
"""
from __future__ import annotations

import re
from collections import Counter

from ..models import Tag, Utterance
from .context import JobBrief

STOPWORDS = set("""그리고 그래서 그런데 하지만 이제 그냥 정말 진짜 이렇게 저렇게 그렇게 어떤 이런 저런 그런 우리 여러분 저는 제가 이건
그건 저건 있는 있습니다 합니다 하는 하고 해서 했던 되는 됩니다 것은 것이 것을 거죠 거예요 때문에 대한 통해 위해 이것 저것
그거 이거 사실 약간 뭔가 조금 많이 아주 매우 너무 같은 같아요 있어요 없어요 이야기 오늘 영상""".split())

HOOK_CUES = {
    "everyday_why": ["왜", "이유"],
    "reframe_definition": ["한마디로", "이란", "라고 부릅", "정의"],
    "payoff_first": ["결국", "핵심은", "정리하면"],
    "hidden_mechanism": ["숨어", "디테일", "사실 이"],
    "compare_contrast": ["반면", "달리", "차이"],
    "contrarian": ["흔히", "사실은", "아니라"],
    "number_list": ["첫째", "세 가지", "두 가지", "단계"],
    "pain_point": ["학생들", "실수", "처음에"],
}


def _keywords(texts: list[str], k: int = 2) -> list[str]:
    c: Counter[str] = Counter()
    for t in texts:
        for w in re.findall(r"[가-힣A-Za-z]{2,}", t):
            w = re.sub(r"(은|는|이|가|을|를|의|에|에서|으로|로|와|과|도|만|까지|부터|이라는|라는|입니다|이에요|예요)$", "", w)
            if len(w) >= 2 and w not in STOPWORDS:
                c[w] += 1
    return [w for w, _ in c.most_common(k)]


def _hookiness(text: str) -> tuple[int, str]:
    best, kind = 0, "open_loop"
    for k, cues in HOOK_CUES.items():
        s = sum(2 for c in cues if c in text)
        if s > best:
            best, kind = s, k
    if text.rstrip().endswith("?"):
        best += 1
    if re.search(r"\d", text):
        best += 1
    return best, kind


def long_plan(brief: JobBrief, utts: list[Utterance], tags: list[Tag]) -> dict:
    kept = [u for u in utts if u.kept]
    chapters: list[dict] = []
    if not any(t.kind == "chapter" for t in tags) and kept:
        # 약 4분마다 챕터, 제목은 구간 키워드
        chapters.append({"seg": kept[0].id, "title": "들어가며"})
        acc_start = kept[0].start
        block: list[Utterance] = []
        for u in kept[1:]:
            block.append(u)
            if u.start - acc_start >= 240:
                kw = _keywords([b.text for b in block], 1)
                chapters.append({"seg": block[0].id, "title": kw[0] if kw else f"Part {len(chapters) + 1}"})
                acc_start = u.start
                block = []
    hook = [u.id for u in kept[:2]]
    emphasis = []
    moments = []
    for u in kept:
        if re.search(r"(결국|핵심은|정리하면|한마디로)", u.text):
            emphasis.append({"seg": u.id, "word": "", "kind": "punch"})
            moments.append({"seg": u.id, "word": "", "kind": "conclusion", "intensity": 2})
        elif re.search(r"(사실은|아니라|반대로|그런데 말이죠)", u.text):
            moments.append({"seg": u.id, "word": "", "kind": "reveal", "intensity": 2})
        elif u.text.rstrip().endswith("?") and len(u.text) < 40:
            moments.append({"seg": u.id, "word": "", "kind": "question", "intensity": 1})
    terms = sorted({a for t in tags for a in t.args if 1 < len(a) <= 12})[:12]
    return {
        "summary": brief.title,
        "hook_segs": hook,
        "title_card_seg": kept[1].id if len(kept) > 3 else -1,
        "chapters": chapters,
        "graphics": [],   # 대본 태그는 plan.enforce_tags 에서 추가된다
        "emphasis": emphasis[:30],
        "moments": moments[:40],
        "drop": [],
        "youtube": {
            "titles": [brief.title],
            "description": f"#디자인 #제품디자인 #디자인이론\n{brief.title}\n\n{{{{CHAPTERS}}}}\n",
            "hashtags": ["#디자인", "#제품디자인", "#디자인이론"],
            "tags": ["디자인", "제품디자인", "디자인 이론"] + terms,
            "thumbnail_texts": [brief.title[:12]],
            "pinned_comment": "여러분은 어떻게 생각하시나요?",
        },
        "music": {"mood": "솔로 피아노, 잔잔한 언더스코어, 80~90 BPM", "notes": "인트로와 챕터 전환에서만 음량을 올린다."},
        "title": brief.title,
        "bgm_mood": "minimal",
        "shorts_bgm_mood": "upbeat",
    }


def shorts_plan(brief: JobBrief, utts: list[Utterance], tags: list[Tag], *, count: int, max_sec: int) -> dict:
    kept = [u for u in utts if u.kept]
    by_id = {u.id: u for u in kept}
    shorts: list[dict] = []
    used: set[int] = set()
    # 1) 대본의 [숏폼 시작]~[숏폼 끝] 범위
    for t in tags:
        if t.kind != "short" or t.utt_id is None:
            continue
        seg_ids = [u.id for u in kept if u.script_span and t.pos <= u.script_span[0] < (t.end_pos or t.pos + 400)]
        if not seg_ids:
            seg_ids = [t.utt_id]
        shorts.append(_make_short(seg_ids, by_id, " ".join(t.args), max_sec))
        used.update(seg_ids)
    # 2) 휴리스틱 창(window) 채점
    windows: list[tuple[float, list[int]]] = []
    for i in range(len(kept)):
        ids: list[int] = []
        dur = 0.0
        score = 0.0
        for u in kept[i:]:
            d = u.end - u.start
            if dur + d > max_sec - 8:
                break
            ids.append(u.id)
            dur += d
            h, _ = _hookiness(u.text)
            score += h
        if dur >= 28 and not (set(ids) & used):
            windows.append((score / max(1.0, dur / 10), ids))
    windows.sort(key=lambda w: -w[0])
    for _, ids in windows:
        if len(shorts) >= count:
            break
        if set(ids) & used:
            continue
        shorts.append(_make_short(ids, by_id, "", max_sec))
        used.update(ids)
    return {"shorts": shorts[:count]}


def _make_short(ids: list[int], by_id: dict[int, Utterance], hint: str, max_sec: int) -> dict:
    scored = [(_hookiness(by_id[i].text), i) for i in ids]
    (best_score, hook_type), best_id = max(scored, key=lambda x: x[0][0])
    cold = best_id if best_score >= 3 and best_id != ids[0] else -1
    first_text = by_id[cold if cold >= 0 else ids[0]].text
    title_src = hint or first_text
    title = re.sub(r"[.?!…]+$", "", title_src).strip()
    if len(title) > 24:
        # 말줄임 대신 어절 단위로 자른다(훅 타이틀 2줄 × 8~12자)
        words, acc = [], 0
        for w in title.split():
            if words and acc + len(w) + 1 > 24:
                break
            words.append(w)
            acc += len(w) + (1 if acc else 0)
        title = " ".join(words) if words else title[:24]
        title = re.sub(r"[,，·]+$", "", title)
    spaces = [i for i, ch in enumerate(title) if ch == " "]
    if len(title) > 12 and spaces:
        sp = min(spaces, key=lambda i: abs(i - len(title) / 2))
        hook_title = title[:sp] + "\n" + title[sp + 1:]
    else:
        hook_title = title
    kw = _keywords([by_id[i].text for i in ids], 3)
    return {
        "title": kw[0] if kw else "short",
        "hook_type": hook_type,
        "hook_title": hook_title,
        "hook_highlight": kw[0] if kw else "",
        "cold_open_seg": cold,
        "segments": ids,
        "graphics": [],
        "emphasis": [{"seg": i, "word": w} for i in ids[:1] for w in kw[:2]],
        "cta": "전체 이야기는 채널의 롱폼 영상에서",
        "loop_line": "",
        "caption": first_text,
        "hashtags": ["#디자인", "#제품디자인", "#디자인이론"],
        "why": "규칙 기반 자동 선택(API 키 없음)",
        "score": 5,
    }
