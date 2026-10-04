"""자유 HTML 카드(HyperFrames 카드 규약 호환) — 검증·정리·계획 반영."""
from __future__ import annotations

import json
from pathlib import Path

from studio.agents import schemas as S
from studio.agents.studio import merge_plan
from studio.director.catalog import TEMPLATES
from studio.director.plan import reading_chars
from studio.motion.card import CANVAS, card_settle_time, card_text, clean_anim, clean_card, fragment
from studio.render.props import _graphic_text

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = json.loads((ROOT / "prompts" / "examples" / "card_examples.json").read_text(encoding="utf-8"))

GOOD = '''<div class="card" data-card-id="c-x">
<style>
.card[data-card-id="c-x"] .root { width:100%; height:100%; background: var(--paper); font-family: var(--font-body); }
.card[data-card-id="c-x"] .title { font: 800 120px/1.05 var(--font-head); color: var(--ink); }
</style>
<div class="root">
  <h2 class="title" data-anim="kinetic-chars" data-anim-at="0.3" data-anim-duration="0.5" data-anim-stagger="0.04">질문이 먼저다</h2>
  <p class="body" data-anim="fade-in" data-anim-at="1.0" data-anim-duration="0.4">좋은 디자인은 좋은 질문에서 시작한다</p>
</div>
</div>'''


def test_examples_are_clean_and_render_ready():
    """예시 카드(구도 원형 12, prompts/layouts.md)는 정화에 걸리는 것이 없고, 안무(data-anim 또는 GSAP timeline)가 있다.
    렌더 전 검사·실제 렌더는 예시를 바꿀 때 직접 돌려 확인한다(2026-10-04 12개 모두 check 통과·Remotion 렌더 확인)."""
    import re
    layouts = (ROOT / "prompts" / "layouts.md").read_text(encoding="utf-8")
    assert len(EXAMPLES) >= 10
    for name, ex in EXAMPLES.items():
        c = clean_card({"html": ex["html"], "timeline": ex.get("timeline", "")}, layout=ex.get("layout", "fullscreen"))
        assert c and not c.get("problems"), (name, c and c.get("problems"))
        assert (c["w"], c["h"]) == CANVAS[ex.get("layout", "fullscreen")]
        assert (card_settle_time(c) > 0 or c.get("timeline")) and card_text(c)
        assert f"`{ex['archetype']}`" in layouts, name                    # 예시마다 원형 설명이 있다
        assert not re.search(r"font-size:\s*(1\d|2[0-7])px", ex["html"]), name   # 28px 미만 글자 없음


def test_clean_card_rescopes_css_and_strips_wrapper():
    c = clean_card(GOOD, card_id="g7")
    assert c["id"] == "g7"
    assert 'data-card-id="c-x"' not in c["css"] and c["css"].count('.card[data-card-id="g7"]') == 2
    assert c["html"].startswith('<div class="root">') and "<style" not in c["html"]
    assert c["w"], c["h"] == (1920, 1080)
    # 멱등: 정리된 카드를 다시 정리해도 같다(재실행 시 plan.json 재정규화)
    again = clean_card(c, layout="fullscreen")
    assert again["css"] == c["css"] and again["html"] == c["html"] and not again.get("problems")
    # 조각으로 되돌리면 에이전트에게 보여 줄 수 있는 완전한 카드
    assert fragment(c).startswith('<div class="card" data-card-id="g7">')


def test_clean_card_removes_scripts_urls_events_and_bad_css():
    hostile = ('<div class="root" onclick="x()"><script>alert(1)</script><iframe src="https://e"></iframe>'
               '<img src="https://evil/x.png" onerror="alert(1)"><img src="images/ok.png">'
               '<a href="https://x">링크</a><p style="position:fixed">글</p>'
               '<p style="font: 700 40px Comic Sans, sans-serif">글꼴</p></div>'
               '<style>@import url(x); .root{transition:all 1s; background:url(https://x/a.png); font-family: Inter}'
               '@keyframes k{from{opacity:0}to{opacity:1}} .t{animation:k 1s; position:fixed; color: red}</style>')
    c = clean_card(hostile, card_id="g1")
    assert c is not None
    html, css = c["html"], c["css"]
    for bad in ("script", "iframe", "evil", "onerror", "onclick", "https://", "position:fixed", "Comic Sans"):
        assert bad not in html, bad
    assert 'src="images/ok.png"' in html and html.count("<img") == 1 and "링크" in html and "href" not in html
    for bad in ("@import", "url(", "transition", "@keyframes", "animation", "fixed", "Inter"):
        assert bad not in css, bad
    assert "color: red" in css and 'font: 700 40px sans-serif' in html   # 번들에 없는 글꼴만 빠진다
    assert set(c["problems"]) >= {"html_tag_removed:script", "html_tag_removed:iframe", "html_external_src_removed",
                                  "html_attr_removed:onerror", "css_forbidden_removed", "font_family_not_bundled:Inter"}
    assert clean_card(hostile, card_id="g1", strict=True) is None


def test_clean_card_limits_and_rejects_empty():
    assert clean_card("", card_id="a") is None
    assert clean_card({"html": ""}) is None
    assert clean_card("<script>1</script>", card_id="a") is None          # 요소가 하나도 안 남음
    assert clean_card("<div>" * 300 + "x" + "</div>" * 300, card_id="a") is None   # 요소 상한(260 — 시그니처 장면 재현)
    big = "<div class='root'>" + "<p>가</p>" * 3000 + "</div>"
    assert clean_card(big, card_id="a") is None                          # HTML 상한


def test_clean_anim_validates_kinds_and_ranges():
    probs: list[str] = []
    a = clean_anim({"data-anim": "slide-in", "data-anim-at": "99", "data-anim-duration": "0.01", "data-anim-from": "diag",
                    "data-anim-distance": "-5", "data-anim-ease": "bounce", "data-anim-zzz": "1"}, probs)
    assert a == {"data-anim": "slide-in", "data-anim-at": "60", "data-anim-duration": "0.05", "data-anim-distance": "0"}
    assert "anim_unknown_param:zzz" in probs
    assert clean_anim({"data-anim": "explode"}, probs) == {} and "anim_unknown_kind:explode" in probs
    cu = clean_anim({"data-anim": "count-up", "data-anim-from": "0", "data-anim-to": "1250", "data-anim-format": ",d",
                     "data-anim-suffix": "명"})
    assert cu["data-anim-to"] == "1250" and cu["data-anim-format"] == ",d" and cu["data-anim-suffix"] == "명"
    m = clean_anim({"data-anim": "morph-to", "data-anim-props": '{"x": 40, "backgroundImage": "url(x)"}'})
    assert "data-anim-props" not in m   # url 이 든 props 는 버린다


def test_settle_time_and_text():
    c = clean_card(GOOD, card_id="g")
    assert abs(card_settle_time(c) - 1.4) < 1e-6   # 늦게 끝나는 fade-in(1.0 + 0.4) 이 정착 시각
    assert card_text(c) == "질문이 먼저다 좋은 디자인은 좋은 질문에서 시작한다"
    g = {"template": "card", "card": c}
    assert reading_chars(g) == len("질문이먼저다좋은디자인은좋은질문에서시작한다")
    assert "질문이 먼저다" in _graphic_text({"template": "card", "data": {"card": c}})


def test_merge_plan_turns_cards_into_card_graphics():
    raw, _ = merge_plan({"motion": {"graphics": [], "scenes": [], "cards": [
        {"start_seg": 3, "end_seg": 4, "start_word": "질문", "layout": "fullscreen", "style": "editorial",
         "title": "질문이 먼저다", "html": GOOD, "reason": "선언"},
        {"start_seg": 5, "end_seg": 5, "start_word": "", "layout": "split", "style": "swiss", "title": "빈 카드",
         "html": "<script>x</script>", "reason": "깨진 카드"}]}})
    cards = [g for g in raw["graphics"] if g["template"] == "card"]
    assert len(cards) == 1 and cards[0]["card"]["style"] == "editorial" and cards[0]["start_word"] == "질문"
    assert cards[0]["card"]["w"] == 1920 and raw["studio"]["cards"] == 1
    assert "card" in TEMPLATES and TEMPLATES["card"].layouts == ("fullscreen", "split", "overlay")
    assert "cards" in S.MOTION["properties"] and "html" in S.CARD_REVISE["properties"]


def test_check_accepts_bundled_display_fonts(tmp_path):
    """F-4(10/1): 카드의 --font-heavy·--font-round·--font-hand·--font-numeral(Black Han Sans·Jua·Nanum Pen Script·
    Playfair Display)을 check.mjs 가 '번들 아님'으로 걸러 키워드 카드로 바뀌었다. 렌더와 같은 Chrome 으로 확인."""
    import shutil

    import pytest

    from studio.motion.check import check_cards
    from studio.render.remotion import find_node
    browser = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"
    if not (shutil.which("node") and Path(browser).exists() and (ROOT / "renderer" / "node_modules").exists()):
        pytest.skip("node·브라우저·renderer/node_modules 가 있어야 한다")
    html = ('<div class="card"><p class="k">핵심</p><h1 class="h">여백은 숨</h1><p class="m">손으로 쓴 메모</p>'
            '<p class="n">1956</p></div>')
    css = (".card{background:#F5F2EA;color:#26211E;padding:80px;width:1920px;height:1080px;box-sizing:border-box}"
           ".k{font-family:var(--font-round);font-size:48px}.h{font-family:var(--font-heavy);font-size:120px}"
           ".m{font-family:var(--font-hand);font-size:56px}"
           ".n{font-family:var(--font-numeral);font-style:italic;font-weight:700;font-size:64px}")
    card = clean_card({"id": "f1", "html": html, "css": css, "style": "editorial"}, layout="fullscreen")
    card["id"] = "f1"
    res = check_cards([card], node=find_node(""), out_dir=tmp_path, fps=30, durations={"f1": 5.0},
                      browser_executable=browser)
    assert res["f1"]["ok"], res["f1"]["problems"]


def test_card_pure_white_and_black_backgrounds_become_house_paper_and_ink():
    """F-10(10/1): 순백·순흑 카드가 크림 메모 사이에 끼어 재질이 네 가지였다 — 배경만 하우스 토큰으로(글자색은 그대로)."""
    c = clean_card({"id": "w", "html": '<div class="card"><h1 class="t">근접성</h1></div>',
                    "css": ".card{background:#ffffff;color:#000}.t{background-color: black;color:#fff}"}, layout="fullscreen")
    assert c and "var(--paper)" in c["css"] and "var(--ink)" in c["css"]
    assert "#ffffff" not in c["css"].lower() and "black" not in c["css"].lower()
    assert "color:#000" in c["css"].replace(" ", "") and "color:#fff" in c["css"].replace(" ", "")
    tsx = (ROOT / "renderer" / "src" / "components" / "card" / "HtmlCard.tsx").read_text(encoding="utf-8")
    assert "'--white': MODERN.card" in tsx and "'--ink': MODERN.ink" in tsx      # 디자인 v4: 흰 카드는 룩이다


def test_card_timeline_is_kept_and_forbidden_tokens_reject_it():
    """디자인 v4 — 직접 쓴 GSAP 타임라인(card_dsl.md 7절): 트윈만 쓰면 남고, 전역·시계·난수·콜백·타이머는 거절."""
    from studio.motion.card import clean_card, card_settle_time
    html = '<div class="card" data-card-id="t"><style>.card[data-card-id="t"] .root{background:var(--paper)}</style>' \
           '<div class="root"><h1 class="w">하나</h1><h1 class="w">둘</h1></div></div>'
    good = "tl.set(q('.w'), {opacity: 0});\ntl.to(q('.w'), {opacity: 1, duration: 0.5, stagger: 0.06}, 0.1);"
    c = clean_card({"html": html, "timeline": good}, card_id="t")
    assert c and c["timeline"] == good and "problems" not in c
    for bad in ("setTimeout(() => {}, 1);", "const d = Date.now();", "tl.to(q('.w'), {onUpdate: () => {}});",
                "window.alert(1);", "fetch('x');", "Math.random();", "tl.call(() => {});", "while (true) {}"):
        c2 = clean_card({"html": html, "timeline": good + "\n" + bad}, card_id="t")
        assert c2 and "timeline" not in c2 and any(p.startswith("timeline_forbidden") for p in c2.get("problems", [])), bad
    c3 = clean_card({"html": html, "timeline": "const x = 1;"}, card_id="t")
    assert c3 and "timeline" not in c3 and "timeline_no_tweens" in c3.get("problems", [])
    c4 = clean_card({"html": html, "timeline": good, "settle_s": 2.4}, card_id="t")
    assert c4 and c4["settle_s"] == 2.4 and card_settle_time(c4) >= 2.4



def test_gsap_plugin_kinds_are_validated_and_render_in_the_checker(tmp_path):
    """2026-10-04 '기본 PPT 같다': GSAP 무료 플러그인(SplitText·DrawSVG·MorphSVG·MotionPath·CustomEase)을 카드에서 쓴다 —
    정화가 새 종류·선택자를 받아들이고, 렌더와 같은 Chrome 검사가 실제로 트윈을 짓는다(렌더러도 같은 것을 등록)."""
    import shutil

    import pytest

    from studio.motion.card import clean_anim
    from studio.motion.check import check_cards
    from studio.render.remotion import find_node
    probs: list[str] = []
    assert clean_anim({"data-anim": "morph-svg", "data-anim-target": "#sq", "data-anim-at": "1"}, probs)["data-anim-target"] == "#sq"
    assert "data-anim-path" not in clean_anim({"data-anim": "follow-path", "data-anim-path": "url(x)"}, probs)
    assert any(p.startswith("anim_bad_selector") for p in probs)
    assert clean_anim({"data-anim": "draw-svg", "data-anim-origin": "center"})["data-anim-origin"] == "center"
    tsx = (ROOT / "renderer" / "src" / "components" / "card" / "HtmlCard.tsx").read_text(encoding="utf-8")
    chk = (ROOT / "renderer" / "scripts" / "check.mjs").read_text(encoding="utf-8")
    for name in ("SplitText", "CustomEase", "DrawSVGPlugin", "MorphSVGPlugin", "MotionPathPlugin"):
        assert name in tsx and name in chk
    browser = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"
    if not (shutil.which("node") and Path(browser).exists() and (ROOT / "renderer" / "node_modules").exists()):
        pytest.skip("node·브라우저·renderer/node_modules 가 있어야 한다")
    html = ('<div class="card" data-card-id="p1"><style>.card[data-card-id="p1"] .root{width:100%;height:100%;'
            'position:relative;background:var(--paper)}.card[data-card-id="p1"] .h{position:absolute;left:140px;top:150px;'
            'font-family:var(--font-head);font-size:120px;margin:0;color:var(--ink)}.card[data-card-id="p1"] svg{position:absolute;'
            'left:900px;top:420px;width:820px;height:420px}.card[data-card-id="p1"] .dot{position:absolute;left:0;top:0;'
            'width:36px;height:36px;border-radius:50%;background:var(--accent)}</style><div class="root">'
            '<h1 class="h" data-anim="split-words" data-anim-at="0.1" data-anim-duration="0.7">처음 본 것에 붙잡힌다</h1>'
            '<svg viewBox="0 0 820 420"><path id="route" d="M20 380 C 220 380, 260 60, 420 60 S 640 360, 800 40" fill="none" '
            'stroke="var(--ink)" stroke-width="6" data-anim="draw-svg" data-anim-at="0.2" data-anim-duration="1.2"/>'
            '<path id="blob" d="M60 200 a80 80 0 1 0 160 0 a80 80 0 1 0 -160 0" fill="var(--accent)" data-anim="morph-svg" '
            'data-anim-target="#sq" data-anim-at="1.8" data-anim-duration="0.8"/><path id="sq" d="M560 120 h180 v180 h-180 z" '
            'fill="none" stroke="none"/></svg><div class="dot" data-anim="follow-path" data-anim-path="#route" '
            'data-anim-at="1.0" data-anim-duration="1.6"></div></div></div>')
    tl = ("const p = gsap.splitText('.h', {type: 'chars'});\nconst e = gsap.customEase('M0,0 C0.12,0.9 0.2,1 1,1');\n"
          "tl.fromTo(p.chars, {opacity: 0.4}, {opacity: 1, duration: 0.3, stagger: 0.02, ease: e}, 1.0);")
    card = clean_card({"id": "p1", "html": html, "timeline": tl, "style": "editorial"}, layout="fullscreen", card_id="p1")
    res = check_cards([card], node=find_node(""), out_dir=tmp_path, fps=30, durations={"p1": 6.0}, browser_executable=browser)
    assert res["p1"]["ok"], res["p1"]["problems"]
    assert {"split-words", "draw-svg", "morph-svg", "follow-path"} <= set(res["p1"]["metrics"]["anims"])


def test_merge_plan_keeps_card_and_setpiece_timelines():
    """2026-10-04 발견: merge_plan 이 카드 HTML 만 정리해 넘겨 모션 디자이너·시그니처 빌더가 쓴 GSAP timeline 이 모두 버려졌다
    (실제 10/04 계획의 카드 6개 모두 timeline 없음). 카드·시그니처·수정 카드 모두 timeline 과 구도 원형을 지킨다."""
    from studio.agents.studio import merge_plan
    from studio.director.plan import _clean_graphic
    html = ('<div class="card" data-card-id="x"><style>.card[data-card-id="x"] .root{background:var(--paper)}</style>'
            '<div class="root"><h1 class="h">처음 본 것이 답을 잡는다</h1></div></div>')
    tl = "tl.from(q('.h'), {yPercent: 110, duration: 0.7}, 0.1);"
    results = {"director": {"beats": []},
               "motion": {"graphics": [], "scenes": [], "cards": [{"start_seg": 1, "end_seg": 2, "start_word": "", "layout": "fullscreen",
                                                                   "style": "editorial", "title": "t", "html": html,
                                                                   "timeline": tl, "archetype": "statement", "reason": ""}]},
               "setpieces": [{"scene": {"start_seg": 3, "end_seg": 4, "title": "s", "kind": "diagram"}, "layout": "fullscreen",
                              "style": "editorial", "archetype": "process_path", "html": html, "timeline": tl, "notes": ""}]}
    long_plan, _ = merge_plan(results)
    cards = [g for g in long_plan["graphics"] if g["template"] == "card"]
    assert len(cards) == 2 and all(g["card"].get("timeline") == tl for g in cards)
    assert [g["card"].get("archetype") for g in cards] == ["statement", "process_path"]
    again = _clean_graphic(cards[0], [1, 2, 3, 4])           # 저장된 계획을 다시 정규화해도 남는다
    assert again["card"]["timeline"] == tl and again["card"]["archetype"] == "statement"
