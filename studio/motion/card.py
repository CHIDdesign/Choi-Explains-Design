"""자유 HTML 카드 검증·정리 — HyperFrames talking-head-recut 카드 규약 호환(renderer/vendor/hyperframes/NOTICE.md).

모션 디자이너가 쓴 HTML/CSS/data-anim 선언을 렌더러가 안전하게 붙일 수 있는 값으로 만든다.
- HTML: 허용 태그·속성만 남기고 <script>·<iframe>·외부 URL·인라인 이벤트는 지운다. <style> 은 CSS 로 뽑는다.
- CSS: 주석·@import·@font-face·url()·transition/animation(GSAP 만 움직인다)·position:fixed 를 지우고,
  모든 선택자를 `.card[data-card-id="ID"]` 로 스코프한다(이미 붙어 있던 다른 id 는 새 id 로 바꾼다).
- data-anim: 종류·수치 범위를 검사한다(renderer/vendor/hyperframes/card-anim.mjs 와 같은 목록).
- 크기 상한(HTML·CSS 24KB, 요소 260개 — 🛠 시그니처 장면의 UI·제품 재현이 들어가게). 넘으면 카드 전체를 버린다(반쯤 잘린 카드보다 없는 게 낫다).

렌더러 계약(renderer/src/lib/types.ts CardSpec): {id, html(.card 안쪽), css(스코프됨), w, h, style}.
"""
from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser
from typing import Any, Optional

# 작성 캔버스(px) — 렌더러가 상자에 맞춰 축소한다. prompts/card_dsl.md 의 표와 같아야 한다.
CANVAS = {"fullscreen": (1920, 1080), "split": (1080, 792), "overlay": (1728, 810)}
STYLES = ("editorial", "academic", "whiteboard", "swiss", "minimal", "board")

MAX_HTML = 24000
MAX_CSS = 24000
MAX_TIMELINE = 6000   # 직접 쓴 GSAP 타임라인 코드(글자 수)
# 타임라인 코드에서 금지: 전역·네트워크·시계·난수·콜백·동적 코드 — 결정론(seek 로만 그려진다)과 격리를 지킨다
TIMELINE_FORBIDDEN = re.compile(
    r"\b(?:fetch|XMLHttpRequest|WebSocket|importScripts|import|eval|Function|setTimeout|setInterval|requestAnimationFrame|"
    r"Date|window|document|globalThis|self|location|navigator|localStorage|sessionStorage|indexedDB|parent|top|postMessage|"
    r"onUpdate|onComplete|onStart|onRepeat|onReverseComplete|call|eventCallback|random|innerHTML|outerHTML|insertAdjacentHTML|"
    r"createElement|appendChild|remove|while|do|with|async|await|Promise|then|constructor|prototype|__proto__)\b|<\/?script|=>\s*\{[^}]*\bthis\b",
    re.I)
MAX_ELEMENTS = 260

ANIM_KINDS = {"fade-in", "fade-out", "slide-in", "kinetic-chars", "typewriter", "count-up", "draw-path", "grow-x", "grow-y",
              "scale-pop", "blur-in", "mask-reveal", "morph-to", "highlight", "stagger-in", "pulse",
              # GSAP 무료 플러그인(SplitText·DrawSVG·MorphSVG·MotionPath) — card-anim.mjs 와 같은 목록
              "split-words", "split-lines", "split-chars", "draw-svg", "morph-svg", "follow-path"}
SEL_RE = re.compile(r"^[#.][A-Za-z][A-Za-z0-9_-]{0,40}$")   # morph-svg 의 target · follow-path 의 path(카드 안 선택자)
ANIM_EASES = {"power1.out", "power2.out", "power3.out", "power4.out", "power2.in", "power2.inOut", "power3.inOut",
              "expo.out", "back.out(1.6)", "back.out(1.2)", "sine.inOut", "none"}
# data-anim-* 값의 범위(초·px). 밖이면 잘라 넣는다.
ANIM_RANGES = {"at": (0.0, 60.0), "duration": (0.05, 4.0), "stagger": (0.005, 0.6), "distance": (0.0, 600.0),
               "target-w": (0.0, 4000.0), "target-h": (0.0, 4000.0), "from": None, "to": None, "scale": (1.0, 1.3)}
ANIM_ENUMS = {"from": {"left", "right", "top", "bottom"}, "direction": {"left", "right", "top", "bottom"},
              "pattern": {"pop", "fade"}, "format": {".0f", ".1f", ".2f", ",d"}, "origin": {"start", "center", "end"}}

VOID_TAGS = {"br", "hr", "img", "path", "circle", "rect", "line", "polyline", "polygon", "ellipse", "use", "stop"}
ALLOWED_TAGS = {"a", "div", "span", "p", "h1", "h2", "h3", "h4", "h5", "ul", "ol", "li", "em", "strong", "b", "i", "u", "s", "small",
                "mark", "sup", "sub", "br", "hr", "blockquote", "section", "header", "footer", "figure", "figcaption",
                "table", "thead", "tbody", "tr", "th", "td", "img", "svg", "g", "path", "circle", "rect", "line",
                "polyline", "polygon", "ellipse", "text", "tspan", "defs", "linearGradient", "radialGradient", "stop",
                "clipPath", "use"}
COMMON_ATTRS = {"class", "id", "style", "title", "alt", "role", "aria-label", "aria-hidden", "lang", "dir"}
SVG_ATTRS = {"viewBox", "preserveAspectRatio", "xmlns", "d", "cx", "cy", "r", "rx", "ry", "x", "y", "x1", "y1", "x2", "y2",
             "width", "height", "points", "fill", "fill-opacity", "stroke", "stroke-width", "stroke-linecap",
             "stroke-linejoin", "stroke-dasharray", "stroke-dashoffset", "stroke-opacity", "opacity", "transform",
             "text-anchor", "dominant-baseline", "font-size", "font-family", "font-weight", "letter-spacing", "offset",
             "stop-color", "stop-opacity", "gradientUnits", "clip-path", "href", "xlink:href", "vector-effect",
             "paint-order", "pathLength"}
IMG_ATTRS = {"src", "width", "height", "loading", "decoding"}
ATTR_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9:_-]*$")
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
LOCAL_SRC_RE = re.compile(r"^(images|fx|broll|stock|cards)/[A-Za-z0-9_./-]+$")
SCOPE_RE = re.compile(r"""\.card\[data-card-id=(?:"[^"]*"|'[^']*'|[^\]]*)\]\s*""")
FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;}]+)", re.I)
FONT_SHORTHAND_RE = re.compile(r"(?<![a-z-])font\s*:\s*([^;}]+)", re.I)
FONT_OK = {"pretendard", "noto serif kr", "anton", "jua", "black han sans", "nanum pen script", "playfair display",
           "instrument serif", "gowun batang", "hahmlet", "song myung", "press serif",
           "serif", "sans-serif", "monospace", "system-ui", "ui-serif",
           "ui-sans-serif", "ui-monospace", "inherit", "apple sd gothic neo", "malgun gothic", "nanum myeongjo"}
CSS_FORBIDDEN = re.compile(r"@import|@font-face|@charset|expression\s*\(|behavior\s*:|-moz-binding|javascript:|"
                           r"position\s*:\s*fixed|url\s*\(|@keyframes|\btransition\b|\banimation\b", re.I)
STYLE_ATTR_FORBIDDEN = re.compile(r"expression\s*\(|url\s*\(|javascript:|position\s*:\s*fixed|\btransition\b|\banimation\b", re.I)


def _num(v: Any, lo: float, hi: float) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return max(lo, min(hi, f))


def _fmt(f: float) -> str:
    return f"{f:.3f}".rstrip("0").rstrip(".") or "0"


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

class _Sanitizer(HTMLParser):
    """허용 태그·속성만 다시 써서 내보낸다. 금지 태그는 자식까지 통째로 버린다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.css: list[str] = []
        self.problems: list[str] = []
        self.n_elements = 0
        self.anims: list[dict[str, str]] = []
        self.text: list[str] = []
        self._skip: list[str] = []      # 통째로 버리는 중인 태그 스택
        self._in_style = False
        self._depth = 0
        self.card_attrs: Optional[dict[str, str]] = None   # 바깥 .card 래퍼가 있었으면 그 속성

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        tag_l = tag.lower()
        if self._skip:
            if tag_l not in VOID_TAGS:
                self._skip.append(tag_l)
            return
        if tag_l == "style":
            self._in_style = True
            return
        ad = {k: (v or "") for k, v in attrs if k}
        # 바깥 .card 래퍼는 벗긴다(렌더러가 다시 씌운다)
        if tag_l == "div" and self._depth == 0 and "card" in ad.get("class", "").split() and self.card_attrs is None:
            self.card_attrs = ad
            self._depth += 1
            self.out.append("")
            return
        if tag_l not in ALLOWED_TAGS:
            self.problems.append(f"html_tag_removed:{tag_l}")
            if tag_l not in VOID_TAGS:
                self._skip.append(tag_l)
            return
        clean = self._attrs(tag_l, ad)
        if tag_l == "img" and not any(k == "src" for k, _ in clean):
            return   # 로컬 파일이 아닌 이미지는 요소째 버린다
        self.n_elements += 1
        self.out.append("<" + tag + "".join(f' {k}="{escape(v, quote=True)}"' for k, v in clean) + ">")
        if tag_l not in VOID_TAGS:
            self._depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        tag_l = tag.lower()
        if self._skip or self._in_style:
            return
        if tag_l not in ALLOWED_TAGS:
            self.problems.append(f"html_tag_removed:{tag_l}")
            return
        clean = self._attrs(tag_l, {k: (v or "") for k, v in attrs if k})
        if tag_l == "img" and not any(k == "src" for k, _ in clean):
            return
        self.n_elements += 1
        self.out.append("<" + tag + "".join(f' {k}="{escape(v, quote=True)}"' for k, v in clean) + "/>")

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if self._in_style:
            if tag_l == "style":
                self._in_style = False
            return
        if self._skip:
            if self._skip[-1] == tag_l:
                self._skip.pop()
            return
        if tag_l in VOID_TAGS:
            return
        if tag_l not in ALLOWED_TAGS:
            return
        self._depth -= 1
        if self._depth == 0 and self.card_attrs is not None and tag_l == "div":
            self.out.append("")   # 래퍼 닫힘
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.css.append(data)
            return
        if self._skip:
            return
        self.out.append(escape(data, quote=False))
        if data.strip():
            self.text.append(data.strip())

    def handle_entityref(self, name: str) -> None:
        if not self._skip and not self._in_style:
            self.out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._skip and not self._in_style:
            self.out.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        return

    def _attrs(self, tag: str, ad: dict[str, str]) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        anim: dict[str, str] = {}
        for k, v in ad.items():
            kl = k.lower()
            if not ATTR_RE.match(kl):
                continue
            if kl.startswith("on") or kl in ("srcdoc", "formaction", "action", "srcset"):
                self.problems.append(f"html_attr_removed:{kl}")
                continue
            if kl.startswith("data-anim"):
                anim[kl] = v.strip()
                continue
            if kl == "href" or kl == "xlink:href":
                # svg <use href="#id"> 만
                if tag == "use" and v.startswith("#") and ID_RE.match(v[1:] or "x"):
                    out.append((k, v))
                else:
                    self.problems.append("html_href_removed")
                continue
            if kl == "src":
                if tag == "img" and LOCAL_SRC_RE.match(v.strip()) and ".." not in v:
                    out.append(("src", v.strip()))
                else:
                    self.problems.append("html_external_src_removed")
                continue
            if kl == "style":
                if STYLE_ATTR_FORBIDDEN.search(v):
                    self.problems.append("html_style_attr_forbidden")
                    continue
                out.append(("style", _check_fonts(v, self.problems)))
                continue
            if kl == "id":
                if ID_RE.match(v.strip()):
                    out.append(("id", v.strip()))
                continue
            if kl in COMMON_ATTRS or kl in SVG_ATTRS or (tag == "img" and kl in IMG_ATTRS):
                out.append((k, v))
        if anim:
            cleaned = clean_anim(anim, self.problems)
            if cleaned:
                out.extend(sorted(cleaned.items()))
                self.anims.append(cleaned)
        return out


def clean_anim(attrs: dict[str, str], problems: Optional[list[str]] = None) -> dict[str, str]:
    """data-anim-* 속성 묶음 → 검증된 속성(종류가 틀리면 빈 dict)."""
    problems = problems if problems is not None else []
    kind = attrs.get("data-anim", "")
    if kind not in ANIM_KINDS:
        problems.append(f"anim_unknown_kind:{kind}")
        return {}
    out = {"data-anim": kind}
    for k, v in attrs.items():
        if k == "data-anim":
            continue
        p = k[len("data-anim-"):]
        if p == "ease":
            if v in ANIM_EASES:
                out[k] = v
            continue
        if p in ANIM_ENUMS:
            if v in ANIM_ENUMS[p]:
                out[k] = v
            continue
        if p == "props":
            if kind == "morph-to" and len(v) <= 400 and "url" not in v.lower():
                out[k] = v
            continue
        if p in ("prefix", "suffix"):
            out[k] = v[:8]
            continue
        if p in ("target", "path"):
            if SEL_RE.match(v):
                out[k] = v
            else:
                problems.append(f"anim_bad_selector:{p}")
            continue
        if p in ANIM_RANGES:
            rng = ANIM_RANGES[p]
            if rng is None:
                f = _num(v, -1e9, 1e9)
            else:
                f = _num(v, rng[0], rng[1])
            if f is not None:
                out[k] = _fmt(f)
            continue
        problems.append(f"anim_unknown_param:{p}")
    return out


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

def _strip_css_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", " ", css, flags=re.S)


def _scope_selector(sel: str, scope: str) -> str:
    sel = SCOPE_RE.sub("", sel).strip()
    if not sel:
        return scope
    if sel in (":root", "html", "body"):
        return scope
    return f"{scope} {sel}"


def _scope_block(css: str, scope: str, problems: list[str], depth: int = 0) -> str:
    """중괄호 블록을 따라가며 선택자를 스코프한다. @media/@container/@supports 안은 재귀, 다른 @규칙은 버린다."""
    out: list[str] = []
    i = 0
    n = len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            break
        head = css[i:j].strip()
        # 블록 끝 찾기(중첩 고려)
        k = j + 1
        level = 1
        while k < n and level:
            if css[k] == "{":
                level += 1
            elif css[k] == "}":
                level -= 1
            k += 1
        body = css[j + 1:k - 1]
        i = k
        if not head:
            continue
        if head.startswith("@"):
            name = head.split("(")[0].split()[0].lower()
            if name in ("@media", "@container", "@supports") and depth < 2:
                out.append(f"{head}{{{_scope_block(body, scope, problems, depth + 1)}}}")
            else:
                problems.append(f"css_at_rule_removed:{name}")
            continue
        sels = [s for s in (x.strip() for x in head.split(",")) if s]
        scoped = ", ".join(_scope_selector(s, scope) for s in sels)
        decl = body.strip()
        if not decl:
            continue
        out.append(f"{scoped}{{{decl}}}")
    return "\n".join(out)


def _check_fonts(css: str, problems: list[str]) -> str:
    """허용되지 않은 글꼴 이름은 var(--font-body) 로 바꾼다(조용한 폴백 방지 — 렌더러가 가진 글꼴만)."""
    def fix_families(value: str) -> str:
        parts = [p.strip() for p in value.split(",")]
        keep: list[str] = []
        for p in parts:
            name = p.strip().strip("'\"").strip()
            if not name:
                continue
            if name.startswith("var("):
                keep.append(p)
                continue
            if name.lower() in FONT_OK:
                keep.append(p)
            else:
                problems.append(f"font_family_not_bundled:{name}")
        return ", ".join(keep) if keep else "var(--font-body)"

    css = FONT_FAMILY_RE.sub(lambda m: "font-family: " + fix_families(m.group(1)), css)

    def fix_short(m: re.Match) -> str:
        v = m.group(1)
        # 'italic 700 40px/1.2 Family, Family2' — 마지막 슬래시·크기 뒤가 글꼴
        mm = re.match(r"^(.*?\d[\d.]*(?:px|em|rem|%)(?:\s*/\s*[\d.]+(?:px|em|%)?)?)\s+(.+)$", v.strip())
        if not mm:
            return "font: " + v
        return "font: " + mm.group(1) + " " + fix_families(mm.group(2))

    css = FONT_SHORTHAND_RE.sub(fix_short, css)
    return css


PURE_BG = re.compile(r"(background(?:-color)?\s*:\s*)(#fff(?:fff)?|white|#000(?:000)?|black|#111(?:111)?|#0b0b0b)\b", re.I)


def house_backgrounds(css: str, problems: list[str]) -> str:
    """배경의 순백·순흑을 하우스 토큰으로(크림 종이 var(--paper) · 따뜻한 잉크 var(--ink)) — 10/1: 흰 카드·검은 카드가
    크림 메모·회색 종이 사이에 끼어 재질이 네 가지였다(docs/upgrade/06 F-10, 게이트 B9). 글자색은 건드리지 않는다."""
    def sub(m: re.Match) -> str:
        v = m.group(2).lower()
        return m.group(1) + ("var(--paper)" if v in ("#fff", "#ffffff", "white") else "var(--ink)")
    new = PURE_BG.sub(sub, css)
    if new != css:
        problems.append("순백·순흑 배경 → 크림 종이·잉크")
    return new


def clean_css(css: str, card_id: str, problems: list[str]) -> str:
    css = _strip_css_comments(css)
    if CSS_FORBIDDEN.search(css):
        # 금지 항목은 선언 단위로 지운다
        def drop_decl(m: re.Match) -> str:
            return ""
        css = re.sub(r"[^;{}]*?(?:@import|@font-face|@charset|expression\s*\(|behavior\s*:|-moz-binding|javascript:|url\s*\()[^;{}]*;?",
                     drop_decl, css, flags=re.I)
        css = re.sub(r"(?:^|;|\{)\s*position\s*:\s*fixed\s*;?", lambda m: m.group(0)[0] if m.group(0)[0] in ";{" else "",
                     css, flags=re.I)
        css = re.sub(r"(?:^|;|\{)\s*(?:-webkit-)?(?:transition|animation)(?:-[a-z-]+)?\s*:[^;}]*;?",
                     lambda m: m.group(0)[0] if m.group(0)[0] in ";{" else "", css, flags=re.I)
        css = re.sub(r"@keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", "", css, flags=re.I)
        problems.append("css_forbidden_removed")
    css = _check_fonts(css, problems)
    scope = f'.card[data-card-id="{card_id}"]'
    return _scope_block(css, scope, problems)


# ---------------------------------------------------------------------------
# 카드
# ---------------------------------------------------------------------------

def fragment(card: dict[str, Any]) -> str:
    """정리된 카드 → 에이전트에게 다시 보여 줄 완전한 조각(HyperFrames 카드 모양)."""
    return f'<div class="card" data-card-id="{card["id"]}">\n<style>\n{card["css"]}\n</style>\n{card["html"]}\n</div>'


def clean_card(card: Any, *, layout: str = "fullscreen", card_id: str = "", strict: bool = False) -> Optional[dict[str, Any]]:
    """모션 디자이너의 카드(dict {html[, css, style, id]} 또는 HTML 문자열) → 렌더 가능한 CardSpec dict. 못 쓰면 None.

    card_id 를 주면 그 id 로 스코프한다(계획 안에서 그래픽 id 와 맞춘다). strict=True 면 문제가 하나라도 있으면 None.
    """
    if isinstance(card, str):
        card = {"html": card}
    if not isinstance(card, dict):
        return None
    html = str(card.get("html") or "")
    css_in = str(card.get("css") or "")
    if not html.strip():
        return None
    if len(html) > MAX_HTML or len(css_in) > MAX_CSS:
        return None
    p = _Sanitizer()
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001 — 파서가 못 읽는 HTML 은 버린다
        return None
    problems = list(p.problems)
    if p.n_elements == 0 or p.n_elements > MAX_ELEMENTS:
        return None
    cid = card_id or str(card.get("id") or (p.card_attrs or {}).get("data-card-id") or "card")
    if not ID_RE.match(cid):
        cid = re.sub(r"[^A-Za-z0-9_-]", "", cid)[:32] or "card"
        if not cid[0].isalpha():
            cid = "c" + cid
    css = house_backgrounds(clean_css("\n".join(p.css) + "\n" + css_in, cid, problems), problems)
    if len(css) > MAX_CSS:
        return None
    inner = "".join(p.out).strip()
    if not inner:
        return None
    if strict and problems:
        return None
    w, h = CANVAS.get(layout, CANVAS["fullscreen"])
    try:
        if card.get("w") and card.get("h"):
            w, h = int(card["w"]), int(card["h"])
            if not (320 <= w <= 3840 and 320 <= h <= 3840):
                w, h = CANVAS.get(layout, CANVAS["fullscreen"])
    except (TypeError, ValueError):
        pass
    style = str(card.get("style") or "")
    out = {"id": cid, "html": inner, "css": css, "w": w, "h": h, "style": style if style in STYLES else ""}
    tl = clean_timeline(card.get("timeline"), problems)
    if tl:
        out["timeline"] = tl
    if isinstance(card.get("archetype"), str) and re.fullmatch(r"[a-z_]{3,24}", card["archetype"]):
        out["archetype"] = card["archetype"]          # 구도 원형(prompts/layouts.md) — 재정규화에도 남는다
    if card.get("settle_s") is not None:
        try:
            out["settle_s"] = float(card["settle_s"])
        except (TypeError, ValueError):
            pass
    if problems:
        out["problems"] = sorted(set(problems))
    return out


def clean_timeline(code: Any, problems: list[str]) -> str:
    """직접 쓴 GSAP 타임라인 코드(fn(tl, q, gsap, ctx) 의 본문) — 크기·금지 토큰 검사. 못 쓰면 '' 와 문제 기록.
    런타임 격리(전역 이름 가리기·콜백 제거)는 card-anim.mjs runTimeline 이, 실행 오류는 check.mjs 가 잡는다."""
    if not code or not isinstance(code, str) or not code.strip():
        return ""
    if len(code) > MAX_TIMELINE:
        problems.append("timeline_too_long")
        return ""
    m = TIMELINE_FORBIDDEN.search(code)
    if m:
        problems.append(f"timeline_forbidden:{m.group(0)[:24]}")
        return ""
    if "tl." not in code and "gsap." not in code:
        problems.append("timeline_no_tweens")
        return ""
    return code.strip()


def card_text(card: dict[str, Any]) -> str:
    """보이는 글(자막 숨김·읽기 시간용)."""
    html = card.get("html") or ""
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"&[a-z#0-9]+;", " ", txt)
    return " ".join(txt.split())


def card_settle_time(card: dict[str, Any]) -> float:
    """모든 data-anim 이 끝나는 시각(초) — 검수 스틸·읽기 시간 계산용. 직접 쓴 타임라인은 렌더 전 검사가 잰 길이(settle_s)."""
    t = 0.0
    try:
        t = max(t, float(card.get("settle_s") or 0.0))
    except (TypeError, ValueError):
        pass
    for m in re.finditer(r"<[^>]*data-anim=\"([^\"]+)\"[^>]*>", card.get("html") or ""):
        tag = m.group(0)
        at = re.search(r'data-anim-at="([^"]+)"', tag)
        du = re.search(r'data-anim-duration="([^"]+)"', tag)
        st = re.search(r'data-anim-stagger="([^"]+)"', tag)
        a = _num(at.group(1) if at else 0, 0, 60) or 0.0
        d = _num(du.group(1) if du else 0.5, 0.05, 4) or 0.5
        s = _num(st.group(1) if st else 0, 0, 0.6) or 0.0
        if m.group(1) in ("kinetic-chars", "typewriter", "stagger-in"):
            d += s * 12   # 글자 12개쯤
        t = max(t, a + d)
    return t

