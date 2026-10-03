"""모션 타이밍·구도 린트(docs/upgrade/06c 4장) — 렌더도 LLM 도 쓰지 않고 MotionSpec + 장면 길이(+ 단어 시각)만으로 판정.

원형은 `.claude/skills/choi-motion-review/scripts/motion_lint.py`(작업 폴더 진단 CLI). 이 모듈이 파이프라인 판이다:
`Pipeline._lint_motion`(감독 단계 끝)이 error 를 모션 디자이너 수정(`Studio.revise_scene`) 1회로 보낸다.
게이트와의 관계: C1 = L17 · C2 = L18(+L19) · C4 = L02 · C5 = L25 · C6 = L21 · B8 = L23 — 게이트는 렌더한 픽셀로, 린트는 스펙으로.
DSL v2(06 7-1): `ghost` 는 0초부터 자리 표시로 보이니 첫 무대에 넣고(잉크 절반), `mark` 는 선(15%), `tint` 가 있는 이미지는
클립아트가 아니다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

FPS = 30
# 16:9 모션 상자(px): 전면 무대(GraphicLayer stage: 좌우 96 · 위 72 · 아래 170) · 보드 판(split) · 종이 챕터
BOXES = {"fullscreen": (1728, 838), "split": (1069, 644), "paper": (860, 644), "desk": (1048, 700)}
P = {
    "first_visible_s": 0.3, "open_ink_share": 0.35, "open_min_elements": 2,     # 06 4-1, motion_craft 2 (게이트 C4)
    "overlap_share": 0.12,                                                     # L27 요소 겹침(작은 쪽 넓이 대비)
    "caption_zone": 0.90,                                                      # L28 전면 무대 아래 10% 는 자막이 올라오는 자리
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
    if t in ("line", "arrow", "path", "mark"):
        return "draw"
    if t == "text":
        return "mask"
    if t == "image":
        return "scale"
    if t == "bar":
        return "fade"
    if t in ("panel", "chip", "bubble", "device", "iso"):
        return "none"                   # v4 부품은 스스로 등장한다
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
    if t == "panel":
        return at + (8 + 3 * len(el.get("rows") or []) + 12) / FPS
    if t in ("chip", "bubble"):
        return at + 14 / FPS
    if t == "device":
        return at + 18 / FPS
    if t == "iso":
        return at + 1.2
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
    if t == "mark":                      # 손 주석: 가리키는 상자(x, y 가운데 · w, h)
        w, h = el.get("w", 10) / 100 * W, el.get("h", 6) / 100 * H
        return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    if t == "bar":                       # BarEl 은 x 에서 오른쪽으로 자란다(가운데 기준이 아니다)
        w, h = el["w"] / 100 * W, el["h"] / 100 * H
        top = y - h / 2 - ((max(18, h * 0.8) + 8) if el.get("label") else 0)
        return (x, top, x + w, y + h / 2)
    if t == "panel":                     # 흰 둥근 카드: 폭 w%, 높이 = 제목 줄 + 행 수
        w = el["w"] / 100 * W
        fs = el.get("size", 2.6) / 100 * H
        h = fs * 0.9 * 2 + (fs * 1.1 if el.get("title") else 0) + fs * 0.5 + len(el.get("rows") or []) * fs * 2.52
        return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    if t in ("chip", "bubble"):
        fs = el.get("size", 2.6) / 100 * H
        w = sum(_cw(c) for c in el["text"]) * fs + fs * (2.2 if t == "chip" else 2.6)
        h = fs * (1.9 if t == "chip" else (2.6 if el.get("sub") else 1.9))
        return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    if t == "device":
        w = el["w"] / 100 * W
        h = w * (0.68 if el["kind"] == "monitor" else 0.66 if el["kind"] == "laptop" else 2.05)
        return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    if t == "iso":
        return (0, 0, W, H)
    return (x, y, x, y)


def _clip(b, W, H):
    return (max(0, b[0]), max(0, b[1]), min(W, b[2]), min(H, b[3]))


def _area(b) -> float:
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def _ink(el: dict, b) -> float:
    """잉크 면적 근사: 글자·이미지·채운 도형은 외접 상자 그대로, 선만 있는 도형은 15%, 점 격자는 35%."""
    t = el["type"]
    if t == "mark":
        return _area(b) * 0.15
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
    if not n:
        return [Issue("L00_empty", "error", "요소가 없다")]
    ats = [e.get("at", 0.0) for e in els]
    shown = [0.0 if e.get("ghost") else a for e, a in zip(els, ats)]     # 자리 표시(ghost)는 0초부터 보인다
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
    if min(shown) > P["first_visible_s"]:
        add("L01_first_visible", "error", f'첫 요소가 {min(shown):.2f}초에 시작(기준 {P["first_visible_s"]}초 이내)')
    total_ink = sum(inks) or 1
    started = [i for i in range(n) if shown[i] <= 0.5]
    ink05 = sum(inks[i] * (1.0 if ats[i] <= 0.5 else 0.5) for i in started) / total_ink
    if ink05 < P["open_ink_share"] or len(started) < P["open_min_elements"]:
        add("L02_open_empty", "error",
            f'0.5초 시점: 요소 {len(started)}개, 잉크 {ink05:.0%}(기준 {P["open_min_elements"]}개, {P["open_ink_share"]:.0%} 이상) - 게이트 C4 예비 판정')
    fin = _union(bbs)
    share = _area(_union([bbs[i] for i in range(n) if shown[i] <= P["stage_by_s"]])) / (_area(fin) or 1)
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

    # ── 겹침(L27, 채널 주인 2026-10-02: 예시에서 그래픽끼리 겹쳤다) ─────────────────────────────────────
    # 같은 시간에 보이는 글·숫자·패널·칩·말풍선·기기·사진의 상자가 서로 12% 넘게 겹치면 오류(배경 면·선·점·주석·막대는 제외).
    # 글이 사진 위에 놓이는 것(영상 위 글자)은 경고만.
    solid = {"text", "counter", "panel", "chip", "bubble", "device", "image"}
    for i in range(n):
        if els[i]["type"] not in solid:
            continue
        ai, bi = els[i].get("at", 0.0), els[i].get("out", dur)
        for j in range(i + 1, n):
            if els[j]["type"] not in solid:
                continue
            aj, bj = els[j].get("at", 0.0), els[j].get("out", dur)
            if max(ai, aj) >= min(bi, bj) - 0.05:
                continue                                     # 같은 시간에 보이지 않는다
            x0 = max(bbs[i][0], bbs[j][0]); y0 = max(bbs[i][1], bbs[j][1])
            x1 = min(bbs[i][2], bbs[j][2]); y1 = min(bbs[i][3], bbs[j][3])
            if x1 <= x0 or y1 <= y0:
                continue
            inter = (x1 - x0) * (y1 - y0)
            small = max(1.0, min(_area(bbs[i]), _area(bbs[j])))
            if inter / small <= P["overlap_share"]:
                continue
            pair = {els[i]["type"], els[j]["type"]}
            level = "warn" if "image" in pair and "text" in pair else "error"
            add("L27_overlap", level, f'요소가 겹친다({inter / small:.0%} - 기준 {P["overlap_share"]:.0%} 이하) - 자리를 옮기거나 등장·퇴장 시각을 나눈다',
                [_name(i, els[i]), _name(j, els[j])])
    # ── 자막 자리(L28, E2E 10/2: y=95 글자가 자막 상자와 겹쳤다) — 전면 무대 아래 10% 에는 글·숫자·칩·말풍선을 두지 않는다
    if box == BOXES["fullscreen"]:
        for i in range(n):
            if els[i]["type"] in solid and bbs[i][3] > P["caption_zone"] * H:
                add("L28_caption_zone", "error", f'아래 {100 - P["caption_zone"] * 100:.0f}% 는 자막 자리(y {els[i]["y"]:.0f} → 아래 끝 {bbs[i][3] / H:.0%}) - y 를 올린다',
                    [_name(i, els[i])])

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
    clip = [i for i, e in enumerate(els) if e["type"] == "image" and e.get("tint", "none") == "none" and (
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


def lint_scene(spec: dict, dur: float, words=None, box=BOXES["paper"]) -> list[Issue]:
    """계획에 저장된 **원본** spec 을 린트한다 — 먼저 `clean_spec` 으로 렌더러가 받을 모양(기본값·범위·stage_first)으로 만든다.
    계획(merge_plan·_clean_graphic)은 spec 을 검사만 하고 원본 그대로 두므로, 디자이너가 생략한 선택 값(dots 의 gap·r 등)이
    없는 채로 `lint` 에 들어가면 KeyError 로 작업이 멈췄다(2026-10-03 실제 작업). 정리가 안 되는 spec 은 L00 오류 하나."""
    from .spec import clean_spec
    cleaned = clean_spec(spec, dur) if isinstance(spec, dict) else None
    if not cleaned:
        return [Issue("L00_empty", "error", "요소가 없거나 spec 이 올바르지 않다")]
    return lint(cleaned, dur, words, box)


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


# 수정 호출을 부르는 규칙(06c 4장 — error). 나머지 warn 은 기록과 아트 디렉터 입력에만.
def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.level == "error"]


def box_for(layout: str) -> tuple[float, float]:
    return BOXES["split"] if layout == "split" else BOXES["fullscreen"]


def describe(issues: list[Issue]) -> list[str]:
    """motion_revise 입력·리포트용 한 줄씩."""
    return [f"{i.rule}: {i.msg}" + (f" [{', '.join(map(str, i.els))}]" if i.els else "") for i in issues]


def bump_small_text(spec: dict, box_h: float, min_px: float = P["label_min_px"]) -> int:
    """규칙 보정(L17): 최종 px 이 라벨 최소(28px)보다 작은 글자를 그 크기까지 키운다. 반환: 키운 수."""
    n = 0
    need = min_px / box_h * 100 + 0.05
    for e in spec.get("elements") or []:
        if e.get("type") == "text" and e.get("size", 0) < need:
            e["size"] = round(need, 2)
            n += 1
    return n
