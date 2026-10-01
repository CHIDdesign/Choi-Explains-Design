"""모션 타이밍·구도 린트 — `studio/motion/lint.py` 로 옮길 원형(docs/upgrade/06c_모션_검수_파이프라인.md).

순수 함수다. 렌더도 LLM 도 쓰지 않고 MotionSpec + 장면 길이(+ 단어 시각)만으로 판정한다.
수치는 P 한 곳에 있다. 근거: docs/upgrade/06_모션_그래픽_v2.md 4-1·6-4, prompts/skills/motion_craft.md, 06c 3장.

읽기 전용 CLI:
    python motion_lint.py "projects/<job>"            # 작업 폴더의 모션 장면 전부
    python motion_lint.py "projects/<job>" --json     # 기계가 읽는 출력
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

FPS = 30
BOXES = {"paper": (860, 644), "classic": (1069, 644), "desk": (1048, 700)}   # 16:9 모션 상자(px)
P = {
    "first_visible_s": 0.3, "open_ink_share": 0.35, "open_min_elements": 2,     # 06 4-1, motion_craft 2 (게이트 C4)
    "stage_by_s": 1.5, "stage_share": 0.5,
    "same_frame_s": 0.1, "same_frame_max": 2,                                   # motion_craft 3
    "burst_window_s": 0.5, "burst_max": 3,
    "read_base_s": 0.4, "read_cps": 12.0, "read_cap_s": 2.0, "read_min_chars": 4,
    "hold_min_s": 1.2, "hold_cps": 7.0,                                         # 06 6-4, 06b HOLD
    "frozen_tail_s": 4.0, "frozen_share": 0.45, "second_act_from_s": 8.0,
    "stagger_total_s": 0.5,                                                     # 06 6-4 (15f)
    "late_vs_word_s": 0.5, "early_vs_word_s": 1.5,
    "sparse_span_s": 3.0,                                                       # motion_craft "하지 않는다"
    "same_enter_share": 0.6, "fade_share": 0.34, "pop_max": 0,                  # motion_craft 6, 12
    "dur_min_s": 0.2, "dur_max_s": 1.0,                                         # motion_craft 5 (30f 상한)
    "label_min_px": 28,                                                         # 06 4-1 (본문은 34)
    "fill_min": 0.45, "ink_min": 0.16, "hero_min": 0.08,                        # C2, 06c
    "accent_max": 1, "texts_max": 7, "words_max": 24, "anchor_tol_pct": 6.0,
    "hero_move_pct": 5.0, "hero_move_scale": 0.05,                              # motion_craft 3
}


@dataclass
class Issue:
    rule: str
    level: str          # error | warn
    msg: str
    els: list = field(default_factory=list)


def _cw(ch: str) -> float:
    c = ord(ch)
    if 0xAC00 <= c <= 0xD7A3:
        return 0.94
    if ch == " ":
        return 0.26
    if ch.isdigit():
        return 0.6
    if "A" <= ch <= "Z":
        return 0.66
    if "a" <= ch <= "z":
        return 0.54
    if ch in ".,':;!|·":
        return 0.28
    return 0.6


def enter_of(el: dict) -> str:
    """MotionScene.tsx 의 기본 진입과 같다."""
    t = el["type"]
    if el.get("enter"):
        return el["enter"]
    if t in ("line", "arrow", "path"):
        return "draw"
    if t == "text":
        return "mask"
    if t == "image":
        return "scale"
    if t == "bar":
        return "fade"
    return "up"


def settle_of(el: dict) -> float:
    """요소가 다 도착하는 시각(초). MotionScene.tsx 의 실제 길이 계산을 따른다."""
    at, t = el.get("at", 0.0), el["type"]
    if t == "text" and enter_of(el) == "mask":
        rv, txt = el.get("reveal", "words"), el["text"]
        if rv == "chars":
            n, step = len(txt.replace(" ", "")), 1
        elif rv == "lines":
            n, step = len(txt.split("\n")), 6
        elif rv == "words":
            n, step = len(txt.split()), 2
        else:
            n, step = 1, 0
        return at + ((max(1, n) - 1) * step + 12) / FPS
    if t == "counter":
        return at + el.get("dur", 1.2)
    if t == "bar":
        return at + el.get("dur", 0.9)
    if t == "dots":
        return at + ((el["count"] - 1) * 1.2 + 8) / FPS
    return at + el.get("dur", 0.4)


def bbox(el: dict, W: float, H: float):
    """요소의 외접 상자(px, 처음 놓인 자리). 글자 폭은 renderer/src/lib/fit.ts 의 근사 계수."""
    t, x, y = el["type"], el["x"] / 100 * W, el["y"] / 100 * H
    if t in ("text", "counter"):
        if t == "counter":
            s = f'{el.get("prefix", "")}{el["to"]:.{el.get("decimals", 0)}f}{el.get("suffix", "")}'
            fs, lines, k = el["size"] / 100 * H, [s], 0.5
        else:
            fs, k, lines = el["size"] / 100 * H, 1.0, el["text"].split("\n")
        w = max(sum(_cw(c) for c in ln) * fs * k for ln in lines)
        nlines = len(lines)
        if el.get("maxWidth"):
            mw = el["maxWidth"] / 100 * W
            if w > mw:
                nlines, w = nlines * int(-(-w // mw)), mw
        h = nlines * 1.12 * fs
        a = el.get("anchor", "center")
        x0 = x if a == "left" else x - w if a == "right" else x - w / 2
        return (x0, y - h / 2, x0 + w, y + h / 2)
    if t in ("rect", "image"):
        w, h = el["w"] / 100 * W, el["h"] / 100 * H
        return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    if t == "circle":
        r = el["r"] / 100 * W
        return (x - r, y - r, x + r, y + r)
    if t in ("line", "arrow"):
        x2, y2 = el["x2"] / 100 * W, el["y2"] / 100 * H
        pad = abs(el.get("curve", 0)) * (((x2 - x) ** 2 + (y2 - y) ** 2) ** 0.5) * 0.25
        return (min(x, x2) - pad, min(y, y2) - pad, max(x, x2) + pad, max(y, y2) + pad)
    if t == "path":
        nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", el["d"])]
        xs, ys = nums[0::2], nums[1::2]
        return (min(xs) / 100 * W, min(ys) / 100 * H, max(xs) / 100 * W, max(ys) / 100 * H)
    if t == "dots":
        cols = el["cols"]
        rows = -(-el["count"] // cols)
        gap, r = el["gap"] / 100 * W, el["r"] / 100 * W
        extra = (len(el["groups"]) - 1) * el.get("groupGap", 0) / 100 * W if el.get("groups") else 0
        w, h = (cols - 1) * gap + 2 * r + extra, (rows - 1) * gap + 2 * r
        return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    if t == "bar":                       # BarEl 은 x 에서 오른쪽으로 자란다(가운데 기준이 아니다)
        w, h = el["w"] / 100 * W, el["h"] / 100 * H
        top = y - h / 2 - ((max(18, h * 0.8) + 8) if el.get("label") else 0)
        return (x, top, x + w, y + h / 2)
    return (x, y, x, y)


def _clip(b, W, H):
    return (max(0, b[0]), max(0, b[1]), min(W, b[2]), min(H, b[3]))


def _area(b) -> float:
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def _ink(el: dict, b) -> float:
    """잉크 면적 근사: 글자·이미지·채운 도형은 외접 상자 그대로, 선만 있는 도형은 15%, 점 격자는 35%."""
    t = el["type"]
    if t in ("line", "arrow", "path", "rect", "circle") and el.get("fill") in (None, "none"):
        return _area(b) * 0.15
    if t == "dots":
        return _area(b) * 0.35
    return _area(b)


def _union(bs):
    if not bs:
        return (0, 0, 0, 0)
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))


def _name(i: int, el: dict) -> str:
    return f'#{i}:{el["type"]}' + (f'"{el["text"][:10]}"' if el["type"] == "text" else "")


def _chars(el: dict) -> int:
    return len(re.sub(r"\s", "", el["text"])) if el["type"] == "text" else 0


def _big_move(el: dict):
    """히어로 무브 구간: 거리 5% 이상, 배율 5% 이상, 회전 5° 이상 바뀌는 keys 의 (시작, 끝)."""
    keys = el.get("keys") or []
    if not keys:
        return None
    base = {"x": el["x"], "y": el["y"], "scale": 1.0, "rotate": 0.0}
    big = False
    for prop, thr in (("x", P["hero_move_pct"]), ("y", P["hero_move_pct"]), ("scale", P["hero_move_scale"]), ("rotate", 5.0)):
        vals = [base[prop]] + [k[prop] for k in keys if prop in k]
        if max(vals) - min(vals) >= thr:
            big = True
    if not big:
        return None
    ts = [k["t"] for k in keys if any(p in k for p in ("x", "y", "scale", "rotate"))]
    return (min(ts), max(ts))


def lint(spec: dict, dur: float, words=None, box=BOXES["paper"]) -> list[Issue]:
    """words: [(t0, t1, text)] 장면 시작 기준 초. 없으면 말-동기 규칙(L11)은 건너뛴다."""
    W, H = box
    els = spec["elements"]
    out: list[Issue] = []

    def add(rule, level, msg, e=()):
        out.append(Issue(rule, level, msg, list(e)))

    n = len(els)
    ats = [e.get("at", 0.0) for e in els]
    settles = [settle_of(e) for e in els]
    bbs = [_clip(bbox(e, W, H), W, H) for e in els]
    inks = [_ink(els[i], bbs[i]) for i in range(n)]
    order = sorted(range(n), key=lambda i: ats[i])
    events = sorted([k["t"] for e in els for k in e.get("keys", [])]
                    + [e["groupAt"] + 0.8 for e in els if "groupAt" in e]
                    + [e["out"] for e in els if "out" in e]
                    + [settle_of(e) for e in els if e["type"] in ("bar", "counter")])
    last_change = max(settles + events)
    text_ids = [i for i, e in enumerate(els) if e["type"] == "text"]
    early = [i for i in text_ids if ats[i] <= 1.0]
    headline = (max(early, key=lambda i: els[i]["size"]) if early
                else min(text_ids, key=lambda i: ats[i]) if text_ids else -1)

    def groups(ids):                                     # 같은 종류·같은 진입이 0.2초 이내로 이어지면 한 묶음
        g, prev = 0, None
        for j in ids:
            key = (els[j]["type"], enter_of(els[j]))
            if not (prev is not None and els[j]["type"] != "text" and key == prev[0] and ats[j] - prev[1] <= 0.2):
                g += 1
            prev = (key, ats[j])
        return g

    # ── 시작: 0프레임 무대 ───────────────────────────────────────────
    if min(ats) > P["first_visible_s"]:
        add("L01_first_visible", "error", f'첫 요소가 {min(ats):.2f}초에 시작(기준 {P["first_visible_s"]}초 이내)')
    total_ink = sum(inks) or 1
    started = [i for i in range(n) if ats[i] <= 0.5]
    ink05 = sum(inks[i] for i in started) / total_ink
    if ink05 < P["open_ink_share"] or len(started) < P["open_min_elements"]:
        add("L02_open_empty", "error",
            f'0.5초 시점: 요소 {len(started)}개, 잉크 {ink05:.0%}(기준 {P["open_min_elements"]}개, {P["open_ink_share"]:.0%} 이상) - 게이트 C4 예비 판정')
    fin = _union(bbs)
    share = _area(_union([bbs[i] for i in range(n) if ats[i] <= P["stage_by_s"]])) / (_area(fin) or 1)
    if share < P["stage_share"]:
        add("L03_stage_late", "warn", f'{P["stage_by_s"]}초까지 잡힌 구도가 최종 외접 상자의 {share:.0%}(기준 {P["stage_share"]:.0%} 이상)')

    # ── 동시 등장·몰림·성김 ──────────────────────────────────────────
    for i in order:
        same = [j for j in order if ats[i] <= ats[j] < ats[i] + P["same_frame_s"] - 1e-9]
        if len(same) > P["same_frame_max"]:
            add("L04_simultaneous", "error", f'{ats[i]:.2f}초에 요소 {len(same)}개가 동시에 등장(기준 {P["same_frame_max"]}개 이하)',
                [_name(j, els[j]) for j in same])
            break
    for i in order:
        burst = [j for j in order if ats[i] <= ats[j] < ats[i] + P["burst_window_s"]]
        if groups(burst) > P["burst_max"]:
            add("L05_burst", "error",
                f'{ats[i]:.2f}~{ats[i] + P["burst_window_s"]:.2f}초 사이 {groups(burst)}묶음 등장(기준 {P["burst_max"]}묶음 이하)',
                [_name(j, els[j]) for j in burst])
            break
    if n >= 3 and ats[order[2]] - ats[order[0]] >= P["sparse_span_s"]:
        add("L12_sparse_long", "warn", f'세 번째 요소가 {ats[order[2]]:.2f}초에 온다 - 그때까지 화면에 요소가 둘 이하')

    # ── 읽는 시간 ────────────────────────────────────────────────────
    for idx, i in enumerate(order):
        e = els[i]
        if e["type"] != "text" or _chars(e) < P["read_min_chars"]:
            continue
        need = min(P["read_cap_s"], P["read_base_s"] + _chars(e) / P["read_cps"])
        nxt = [ats[j] for j in order[idx + 1:] if els[j]["type"] == "text"]
        until = min(nxt[0] if nxt else dur, e.get("out", dur))
        if until - settles[i] < need - 1e-6:
            add("L06_read_hold", "warn",
                f'{_chars(e)}자 글 안착 {settles[i]:.2f}초, 다음 글 {until:.2f}초 - 읽는 시간 {until - settles[i]:.2f}초 < {need:.2f}초',
                [_name(i, e)])
    last_texts = [i for i in text_ids if settles[i] >= max(settles) - 1.5]
    need_hold = max(P["hold_min_s"], sum(_chars(els[i]) for i in last_texts) / P["hold_cps"])
    if dur - last_change < need_hold - 1e-6:
        add("L07_final_hold", "error",
            f'마지막 움직임 {last_change:.2f}초, 장면 끝 {dur:.2f}초 - 정지 {dur - last_change:.2f}초 < {need_hold:.2f}초')
    tail = dur - last_change
    if tail > max(P["frozen_tail_s"], P["frozen_share"] * dur):
        add("L08_frozen_tail", "warn", f'마지막 변화 {last_change:.2f}초 뒤 {tail:.2f}초 동안 아무것도 안 바뀜(장면의 {tail / dur:.0%})')
    if dur >= P["second_act_from_s"] and not events:
        add("L09_no_second_act", "warn", f'{dur:.1f}초 장면인데 등장 뒤 상태 변화(keys, groupAt, out, 막대, 숫자)가 없다')

    # ── 스태거 ───────────────────────────────────────────────────────
    def flush(run):
        if len(run) >= 3 and ats[run[-1]] - ats[run[0]] > P["stagger_total_s"] + 1e-6:
            add("L10_stagger_total", "warn",
                f'같은 종류 {len(run)}개가 {ats[run[-1]] - ats[run[0]]:.2f}초에 걸쳐 차례로 등장(묶음 기준 {P["stagger_total_s"]}초 이하)',
                [_name(j, els[j]) for j in run])

    run = [order[0]]
    for a, b in zip(order, order[1:]):
        if (els[a]["type"] == els[b]["type"] and els[a]["type"] != "text"
                and enter_of(els[a]) == enter_of(els[b]) and ats[b] - ats[a] <= 0.5):
            run.append(b)
        else:
            flush(run)
            run = [b]
    flush(run)

    # ── 말과의 동기 ──────────────────────────────────────────────────
    if words:
        for i in text_ids:
            toks = [t for t in re.findall(r"[가-힣]+", els[i]["text"]) if len(t) >= 2]
            hits = [w for w in words for t in toks if w[2].startswith(t[:2])]
            if not hits:
                continue
            d = min((settles[i] - w[0] for w in hits), key=abs)
            if d > P["late_vs_word_s"]:
                add("L11_late_vs_speech", "error", f'그 말이 나온 뒤 {d:.2f}초에 안착(기준 {P["late_vs_word_s"]}초 이내)', [_name(i, els[i])])
            elif d < -P["early_vs_word_s"] and i != headline:
                add("L11_early_vs_speech", "warn", f'그 말보다 {-d:.2f}초 먼저 안착(기준 {P["early_vs_word_s"]}초 이내)', [_name(i, els[i])])

    # ── 진입 어휘·움직임 ─────────────────────────────────────────────
    kinds = [enter_of(e) for e in els]
    if n >= 4:
        top = max(set(kinds), key=kinds.count)
        if len(set(kinds)) < 2 or kinds.count(top) / n > P["same_enter_share"]:
            add("L13_same_entrance", "warn", f'{n}개 중 {kinds.count(top)}개가 같은 진입({top})')
    single = [i for i, k in enumerate(kinds) if k in ("fade", "none")]
    if n and len(single) / n > P["fade_share"]:
        add("L14_single_property", "warn", f'한 속성(fade, none) 진입이 {len(single)}/{n}')
    pops = [i for i, e in enumerate(els) if kinds[i] == "pop" or e.get("ease") == "back"]
    if len(pops) > P["pop_max"]:
        add("L15_pop", "error", f'pop/back 이 {len(pops)}개 - 롱폼 본편에서는 쓰지 않는다(펀치 구간·숏폼 훅만)', [_name(i, els[i]) for i in pops])
    for i, e in enumerate(els):
        d = e.get("dur")
        if d is not None and e["type"] not in ("counter", "bar", "path", "line", "arrow") and not (P["dur_min_s"] <= d <= P["dur_max_s"]):
            add("L16_pace", "warn", f'등장 길이 {d}초(0.2~1.0초 밖)', [_name(i, e)])
    spans = sorted(s for s in (_big_move(e) for e in els) if s)
    merged = []
    for s in spans:
        if merged and s[0] <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], s[1]))
        else:
            merged.append(s)
    if len(merged) > 1:
        add("L26_hero_moves", "warn", f'크게 움직이는 구간이 {len(merged)}번({", ".join(f"{a:.1f}~{b:.1f}초" for a, b in merged)}) - 히어로 무브는 하나')

    # ── 크기·구도 ────────────────────────────────────────────────────
    small = [i for i in text_ids if els[i]["size"] / 100 * H < P["label_min_px"] - 1e-6]
    if small:
        add("L17_text_small", "error",
            f'글자 {len(small)}개가 {P["label_min_px"]}px 미만(상자 높이 {H}px 에서 size {P["label_min_px"] / H * 100:.1f} 미만) - 게이트 C1',
            [f'{_name(i, els[i])} {els[i]["size"]}%={els[i]["size"] / 100 * H:.0f}px' for i in small])
    for i, e in enumerate(els):
        if e["type"] == "bar" and e.get("label") and max(18, e["h"] / 100 * H * 0.8) < P["label_min_px"]:
            add("L17_text_small", "error", f'bar.label 이 {max(18, e["h"] / 100 * H * 0.8):.0f}px 로 그려진다(막대 높이의 0.8배)', [_name(i, e)])
    fill = _area(fin) / (W * H)
    if fill < P["fill_min"]:
        add("L18_fill", "error", f'요소 외접 상자가 상자의 {fill:.0%}(기준 {P["fill_min"]:.0%} 이상) - 게이트 C2 예비 판정')
    cover = sum(inks) / (W * H)
    if cover < P["ink_min"]:
        add("L19_ink_cover", "error", f'잉크 면적이 상자의 {cover:.0%}(기준 {P["ink_min"]:.0%} 이상) - 외접 상자는 넓어도 요소가 작다')
    biggest = max(range(n), key=lambda i: _area(bbs[i]))
    if _area(bbs[biggest]) / (W * H) < P["hero_min"]:
        add("L20_no_hero", "warn", f'가장 큰 요소가 상자의 {_area(bbs[biggest]) / (W * H):.1%}(기준 {P["hero_min"]:.0%} 이상) - 주인공이 없다',
            [_name(biggest, els[biggest])])
    faint = [i for i in text_ids if els[i].get("color") == "faint"]
    if faint:
        add("L21_faint_text", "error", "faint 색 글자 - 대비 미달(게이트 C6)", [_name(i, els[i]) for i in faint])
    acc = [i for i, e in enumerate(els)
           if e.get("color") == "accent" or e.get("fill") == "accent" or e.get("stroke") == "accent"
           or (e["type"] == "text" and e.get("highlight")) or (e["type"] == "dots" and e.get("highlight"))
           or (e["type"] in ("counter", "bar") and e.get("color") in (None, "accent"))]
    if len(acc) > P["accent_max"]:
        add("L22_accent", "warn", f'강조색이 {len(acc)}곳(기준 한 화면에 한 곳)', [_name(i, els[i]) for i in acc])
    clip = [i for i, e in enumerate(els) if e["type"] == "image" and (
        e.get("frame") == "cutout" or re.match(r"pixabay:(vector|illustration)", e.get("src", "")) or e.get("src", "").endswith(".png"))]
    if clip:
        add("L23_clipart", "warn", "컬러 클립아트(벡터, 일러스트, cutout) - 게이트 B8", [_name(i, els[i]) for i in clip])
    tol = P["anchor_tol_pct"] / 100
    for i, e in enumerate(els):
        if e["type"] not in ("line", "arrow"):
            continue
        for (px, py), end in (((e["x"], e["y"]), "시작"), ((e["x2"], e["y2"]), "끝")):
            X, Y = px / 100 * W, py / 100 * H
            if not any(b[0] - tol * W <= X <= b[2] + tol * W and b[1] - tol * H <= Y <= b[3] + tol * H
                       for j, b in enumerate(bbs) if j != i and els[j]["type"] not in ("line", "arrow")):
                add("L24_unanchored", "warn", f'선의 {end}점 ({px},{py}) 근처에 아무 요소도 없다', [_name(i, e)])
    wc = sum(len(els[i]["text"].split()) for i in text_ids)
    if len(text_ids) > P["texts_max"] or wc > P["words_max"]:
        add("L25_density", "warn", f'글 덩어리 {len(text_ids)}개, 낱말 {wc}개(기준 {P["texts_max"]}개, {P["words_max"]}개 이하) - 게이트 C5')
    return out


def metrics(spec: dict, dur: float, box=BOXES["paper"]) -> dict:
    W, H = box
    els = spec["elements"]
    bbs = [_clip(bbox(e, W, H), W, H) for e in els]
    inks = [_ink(e, b) for e, b in zip(els, bbs)]
    settles = [settle_of(e) for e in els]
    started = [i for i, e in enumerate(els) if e.get("at", 0) <= 0.5]
    return {"n": len(els), "fill": round(_area(_union(bbs)) / (W * H), 2), "ink": round(sum(inks) / (W * H), 2),
            "ink_at_0.5s": round(sum(inks[i] for i in started) / (sum(inks) or 1), 2),
            "hero": round(max(_area(b) for b in bbs) / (W * H), 3), "last_settle": round(max(settles), 2),
            "min_text_px": round(min((e["size"] / 100 * H for e in els if e["type"] == "text"), default=0))}


def scenes_of_job(job: Path):
    """작업 폴더에서 (id, 제목, spec, 길이, 단어 시각, 상자)를 꺼낸다. 아무것도 쓰지 않는다."""
    plan_p = next(p for p in (job / "output" / "부가자료" / "plan.json", job / "work" / "plan.json") if p.exists())
    plan = json.loads(plan_p.read_text(encoding="utf-8"))
    props = json.loads((job / "render" / "props_long.json").read_text(encoding="utf-8"))
    by_id = {g["id"]: g for g in props["graphics"]}
    words = [w for c in props.get("captions", []) for line in c.get("lines", []) for w in line]
    for i, g in enumerate(plan["long"]["graphics"]):
        pg = by_id.get(f"g{i}")
        if g.get("template") != "motion" or not g.get("spec") or not pg:
            continue
        s, e = pg["start"], pg["end"]
        ws = [(round(w["start"] - s, 2), round(w["end"] - s, 2), w["text"]) for w in words if w["end"] > s - 0.2 and w["start"] < e + 0.2]
        yield f"g{i}", g.get("title", ""), g["spec"], round(e - s, 3), ws, BOXES.get(pg.get("skin") or "paper", BOXES["paper"])


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    try:                                    # 앱 루트에서 돌리면 HEAD 의 검증기를 먼저 통과시킨다
        sys.path.insert(0, str(Path.cwd()))
        from studio.motion.spec import clean_spec
    except Exception:                       # noqa: BLE001
        clean_spec = None
    report = []
    for gid, title, spec, dur, words, box in scenes_of_job(Path(argv[1])):
        spec = (clean_spec(spec, dur) if clean_spec else spec) or spec
        issues = lint(spec, dur, words, box)
        report.append({"id": gid, "title": title, "dur": dur, "box": box, "metrics": metrics(spec, dur, box),
                       "issues": [asdict(i) for i in issues]})
    if "--json" in argv:
        sys.stdout.buffer.write(json.dumps(report, ensure_ascii=False, indent=1).encode("utf-8"))
        return 0
    for r in report:
        line = f'\n== {r["id"]} "{r["title"]}" {r["dur"]}초 상자 {r["box"]} {r["metrics"]}\n'
        for i in r["issues"]:
            line += f'  [{i["level"]}] {i["rule"]}: {i["msg"]}' + (f'  <- {", ".join(i["els"])}' if i["els"] else "") + "\n"
        sys.stdout.buffer.write(line.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
