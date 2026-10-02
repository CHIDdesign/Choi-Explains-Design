"""MotionSpec 검증·정리 — 모션 디자이너 에이전트의 JSON 을 렌더 가능한 안전한 값으로.

renderer/src/lib/types.ts 의 MotionSpec 과 같은 계약. 모르는 필드는 버리고, 숫자는 범위로 자른다.
"""
from __future__ import annotations

import re
from typing import Any

EL_TYPES = {"text", "rect", "circle", "line", "arrow", "path", "dots", "counter", "bar", "image", "mark",
            # 디자인 v4 모던 부품(components/modern/Modern.tsx): 자기 등장 애니메이션을 가진다(enter 기본 none)
            "panel", "chip", "bubble", "device", "iso"}
V4_TYPES = {"panel", "chip", "bubble", "device", "iso"}
ICONS = {"check", "dot", "gear", "none"}
FILLS = {"card", "tint", "accent"}
TAILS = {"bottom", "left", "none"}
DEVICES = {"monitor", "laptop", "phone"}
COLORS = {"fg", "dim", "faint", "accent", "bg", "white", "ink"}
# v2(docs/upgrade/06 7-1): place 붙이기 · unfold 펼치기 · write 손글씨처럼 왼→오(4프레임 스텝)
ENTERS = {"fade", "up", "down", "left", "right", "scale", "mask", "draw", "pop", "none", "place", "unfold", "write"}
EASES = {"out", "inOut", "back", "linear", "enterLarge", "move", "settle"}
MARK_KINDS = {"circle", "underline", "arrow", "bracket", "strike"}
TINTS = {"none", "ink", "duotone"}
LAYOUT_NAMES = {"side", "desk", "sheet", "evidence", "stack", "strip"}
BGS = {"board", "paper", "ink", "signal", "transparent"}
MAX_ELEMENTS = 36
PATH_RE = re.compile(r"^[MmLlHhVvCcSsQqTtAaZz0-9.,\s\-]+$")


def _num(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f:  # NaN
        return default
    return max(lo, min(hi, f))


def _color(v: Any, default: str | None = None) -> str | None:
    if v == "none":
        return "none"
    return v if v in COLORS else default


def clean_element(el: dict[str, Any], scene_dur: float) -> dict[str, Any] | None:
    t = el.get("type")
    if t not in EL_TYPES:
        return None
    out: dict[str, Any] = {"type": t, "x": _num(el.get("x"), -20, 120, 50), "y": _num(el.get("y"), -20, 120, 50)}
    out["at"] = _num(el.get("at"), 0, max(0.0, scene_dur - 0.3), 0)
    if "dur" in el:
        out["dur"] = _num(el.get("dur"), 0.1, 3.0, 0.4)
    if "out" in el and el.get("out") is not None:
        o = _num(el.get("out"), out["at"] + 0.3, scene_dur, scene_dur)
        if o < scene_dur - 0.05:
            out["out"] = o
    if el.get("enter") in ENTERS:
        out["enter"] = el["enter"]
    elif t in V4_TYPES:
        out["enter"] = "none"        # 부품이 스스로 등장한다(칩은 정착, 패널은 큰 면, 말풍선은 꼬리 쪽에서)
    if el.get("ease") in EASES:
        out["ease"] = el["ease"]
    if el.get("ghost") is True and t != "mark":
        out["ghost"] = True      # 0초부터 흐린 자리 표시(0.22)로 서 있다가 at 에 채워진다 — 빈 화면 금지(06 F-6)
    if el.get("anchor") in ("center", "left", "right"):
        out["anchor"] = el["anchor"]
    c = _color(el.get("color"))
    if c and c != "none":
        out["color"] = c
    if "opacity" in el:
        out["opacity"] = _num(el.get("opacity"), 0, 1, 1)
    keys = []
    for k in (el.get("keys") or [])[:12]:
        if not isinstance(k, dict):
            continue
        kk: dict[str, Any] = {"t": _num(k.get("t"), 0, scene_dur, 0)}
        for prop, lo, hi in (("x", -20, 120), ("y", -20, 120), ("scale", 0, 6), ("rotate", -720, 720), ("opacity", 0, 1)):
            if prop in k:
                kk[prop] = _num(k.get(prop), lo, hi, 0)
        if len(kk) > 1:
            keys.append(kk)
    if keys:
        out["keys"] = keys
    if t == "text":
        text = str(el.get("text", "")).strip()[:80]
        if not text:
            return None
        out.update(text=text, size=_num(el.get("size"), 2, 40, 7))
        if "weight" in el:
            out["weight"] = int(_num(el.get("weight"), 300, 900, 800))
        if el.get("font") in ("sans", "display", "serif", "latin", "heavy", "round", "hand", "poster", "italic"):
            out["font"] = el["font"]
        if "maxWidth" in el:
            out["maxWidth"] = _num(el.get("maxWidth"), 10, 100, 80)
        if el.get("align") in ("left", "center", "right"):
            out["align"] = el["align"]
        if el.get("highlight"):
            out["highlight"] = str(el["highlight"])[:30]
        if el.get("reveal") in ("words", "chars", "lines", "none"):
            out["reveal"] = el["reveal"]
    elif t == "rect":
        out.update(w=_num(el.get("w"), 0.5, 100, 20), h=_num(el.get("h"), 0.5, 100, 20),
                   radius=_num(el.get("radius"), 0, 200, 0), strokeWidth=_num(el.get("strokeWidth"), 0, 20, 3))
        for k in ("fill", "stroke"):
            if _color(el.get(k)):
                out[k] = _color(el.get(k))
    elif t == "circle":
        out.update(r=_num(el.get("r"), 0.3, 50, 6), strokeWidth=_num(el.get("strokeWidth"), 0, 20, 3))
        for k in ("fill", "stroke"):
            if _color(el.get(k)):
                out[k] = _color(el.get(k))
    elif t in ("line", "arrow"):
        out.update(x2=_num(el.get("x2"), -20, 120, 60), y2=_num(el.get("y2"), -20, 120, 50),
                   strokeWidth=_num(el.get("strokeWidth"), 1, 16, 3), curve=_num(el.get("curve"), -1, 1, 0))
        if el.get("dashed"):
            out["dashed"] = True
    elif t == "path":
        d = str(el.get("d", ""))[:1500]
        if not d or not PATH_RE.match(d):
            return None
        out.update(d=d, strokeWidth=_num(el.get("strokeWidth"), 0, 16, 3))
        for k in ("fill", "stroke"):
            if _color(el.get(k)):
                out[k] = _color(el.get(k))
    elif t == "dots":
        count = int(_num(el.get("count"), 1, 60, 12))
        out.update(count=count, cols=int(_num(el.get("cols"), 1, 30, min(count, 12))), gap=_num(el.get("gap"), 0.5, 30, 5),
                   r=_num(el.get("r"), 0.2, 8, 1.2))
        if _color(el.get("fill")):
            out["fill"] = _color(el.get("fill"))
        hl = [int(i) for i in (el.get("highlight") or []) if isinstance(i, (int, float)) and 0 <= i < count]
        if hl:
            out["highlight"] = hl
        groups = [int(g) for g in (el.get("groups") or []) if isinstance(g, (int, float)) and g > 0]
        if groups and sum(groups) <= out["cols"]:
            out["groups"] = groups
            out["groupAt"] = _num(el.get("groupAt"), 0, scene_dur, 1.5)
            out["groupGap"] = _num(el.get("groupGap"), 0, 40, out["gap"] * 1.6)
    elif t == "counter":
        out.update(**{"from": _num(el.get("from"), -1e9, 1e9, 0), "to": _num(el.get("to"), -1e9, 1e9, 100),
                      "size": _num(el.get("size"), 3, 60, 20), "decimals": int(_num(el.get("decimals"), 0, 3, 0))})
        for k in ("prefix", "suffix"):
            if el.get(k):
                out[k] = str(el[k])[:6]
    elif t == "bar":
        out.update(w=_num(el.get("w"), 2, 100, 40), h=_num(el.get("h"), 0.5, 20, 2.5), value=_num(el.get("value"), 0, 1, 0.5))
        if el.get("label"):
            out["label"] = str(el["label"])[:24]
    elif t == "image":
        src = str(el.get("src", "")).strip()
        # 'pixabay:<vector|illustration|photo>:<영어 검색어>' 는 스톡 단계가 실제 파일(broll/img_…)로 바꾼다
        if not src.startswith(("images/", "broll/", "pixabay:")):
            return None
        out.update(src=src[:120], w=_num(el.get("w"), 2, 100, 30), h=_num(el.get("h"), 2, 100, 30),
                   radius=_num(el.get("radius"), 0, 100, 0))
        fr = str(el.get("frame", "")).strip()
        if fr in ("torn", "cutout", "none", "print"):
            out["frame"] = fr
        # 컬러 클립아트 금지(게이트 B8): 벡터·일러스트는 기본 잉크 단색
        tint = el.get("tint")
        if tint in TINTS:
            out["tint"] = tint
        elif src.startswith(("pixabay:vector:", "pixabay:illustration:")):
            out["tint"] = "ink"
    elif t == "panel":
        # UI 패널(레퍼런스 'Project Pricing'): 제목 줄 + 둥근 행. rows 는 "라벨" 또는 "라벨|값"
        rows = [str(r).strip()[:30] for r in (el.get("rows") or []) if str(r).strip()][:8]
        if not rows and not el.get("title"):
            return None
        out.update(rows=rows, w=_num(el.get("w"), 12, 100, 36))
        if el.get("title"):
            out["title"] = str(el["title"]).strip()[:24]
        if el.get("tilt") is True:
            out["tilt"] = True
        if "on" in el:
            out["on"] = int(_num(el.get("on"), -1, 7, -1))
        out["size"] = _num(el.get("size"), 1.6, 5, 2.6)        # 행 글자 크기(장면 높이 %)
    elif t == "chip":
        text = str(el.get("text", "")).strip()[:20]
        if not text:
            return None
        out.update(text=text, size=_num(el.get("size"), 1.6, 6, 2.6))
        out["icon"] = el.get("icon") if el.get("icon") in ICONS else "check"
        out["fill"] = el.get("fill") if el.get("fill") in FILLS else "card"
    elif t == "bubble":
        text = str(el.get("text", "")).strip()[:24]
        if not text:
            return None
        out.update(text=text, size=_num(el.get("size"), 2, 8, 3.2))
        if el.get("sub"):
            out["sub"] = str(el["sub"]).strip()[:30]
        out["tail"] = el.get("tail") if el.get("tail") in TAILS else "bottom"
        out["icon"] = el.get("icon") if el.get("icon") in ICONS else "none"
    elif t == "device":
        kind = el.get("kind") if el.get("kind") in DEVICES else "monitor"
        out.update(kind=kind, w=_num(el.get("w"), 8, 100, 50))
        src = str(el.get("src", "")).strip()
        if src.startswith(("images/", "broll/", "pixabay:")):
            out["src"] = src[:120]
        rows = [str(r).strip()[:30] for r in (el.get("rows") or []) if str(r).strip()][:6]
        if rows:
            out["rows"] = rows
        if el.get("title"):
            out["title"] = str(el["title"]).strip()[:24]
    elif t == "iso":
        # 아이소메트릭 블록 도시(배경): 장면 전체를 덮는다 — x, y 는 무시
        out.update(cols=int(_num(el.get("cols"), 4, 16, 11)), rows=int(_num(el.get("rows"), 3, 12, 8)),
                   seed=int(_num(el.get("seed"), 0, 999, 1)))
        out["road"] = el.get("road") is not False
        out["opacity"] = _num(el.get("opacity"), 0.1, 1, 0.9)
    elif t == "mark":
        # 손으로 친 주석: 가리킬 상자(가운데 x, y · w, h %) 둘레·아래에 그린다. 강조는 색이 아니라 mark 로
        kind = el.get("kind")
        if kind not in MARK_KINDS:
            return None
        out.update(kind=kind, w=_num(el.get("w"), 1, 100, 20), h=_num(el.get("h"), 1, 100, 8),
                   strokeWidth=_num(el.get("strokeWidth"), 1, 12, 5))
        out.setdefault("dur", _num(el.get("dur"), 0.2, 1.5, 0.5))
    return out


STAGE_BY = 0.5          # 이 시각까지 무대(구도)가 서 있어야 한다 — 빈 배경만 2~3초 뜨지 않게(게이트 C4)


def stage_first(els: list[dict[str, Any]]) -> int:
    """0프레임 무대(docs/upgrade/06 F-6): 0.5초까지 아무것도 서지 않는 장면이면 구도를 먼저 세운다 — 판·상자(rect)와 가장 큰
    제목 글자를 0초로. 선·화살표·점·숫자·작은 글자는 말에 맞춘 시각 그대로(강조는 말에서 온다). 그래도 없으면 가장 먼저 오는
    요소를 0초로. 반환: 옮긴 요소 수."""
    if not els or any(float(e.get("at", 0)) <= STAGE_BY or e.get("ghost") for e in els):
        return 0
    moved = 0
    texts = [e for e in els if e["type"] == "text"]
    big = max((float(e.get("size", 0)) for e in texts), default=0.0)
    for e in els:
        if e["type"] == "rect" or (e["type"] == "text" and big and float(e.get("size", 0)) >= big - 1e-6):
            e["at"] = 0.0
            moved += 1
    if not moved:
        first = min(els, key=lambda e: float(e.get("at", 0)))
        first["at"] = 0.0
        moved = 1
    return moved


def clean_spec(spec: Any, scene_dur: float) -> dict[str, Any] | None:
    if not isinstance(spec, dict):
        return None
    els = [e for e in (clean_element(e, scene_dur) for e in (spec.get("elements") or [])[:MAX_ELEMENTS]
                       if isinstance(e, dict)) if e]
    if not els:
        return None
    stage_first(els)
    out: dict[str, Any] = {"elements": els}
    try:
        hero = int(spec.get("hero", -1))
    except (TypeError, ValueError):
        hero = -1
    if 0 <= hero < len(els):
        out["hero"] = hero           # 크게 움직이는 주 요소 하나(린트 L26)
    if spec.get("layout_intent") == "asym":
        out["layout_intent"] = "asym"
    if spec.get("bg") in BGS:
        out["bg"] = spec["bg"]
    if spec.get("grid"):
        out["grid"] = True
    if spec.get("label"):
        out["label"] = str(spec["label"])[:30]
    return out
