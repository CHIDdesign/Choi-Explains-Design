"""✂️ 컷 경계 그림 — 애매한 컷만 컷 총괄에게 그림으로 보여 준다(채널 주인 2026-10-27).

글자 전사만으로는 '이 쉼에서 자르면 말끝이 잘리는가', '두 테이크 중 어느 쪽이 더 잘 나왔는가'를 알 수 없다. 그래서 browser-use/video-use
(MIT)의 timeline_view 생각을 옮겼다 — 전부가 아니라 **판단이 갈리는 곳만** 필름스트립 + 파형 + 단어 라벨 한 장으로:
- 쉼: 초안이 자르는 구간의 가장자리와 이웃 단어 사이 무음이 AMBIG(150~400ms)인 곳 — 400ms 이상은 안전, 150ms 미만은 판단 대상이 아님
  (video-use: ≥400 안전 · 150–400 확인 · <150 위험).
- 리테이크: 초안이 뺀 테이크와 같은 대본 구간을 남긴 테이크를 위아래로 나란히.
그림은 Claude 에게만 가고 결과물에는 영향이 없다. 시각은 모두 가상 타임라인(발화·단어와 같은 시각).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from ..models import Utterance, Word

AMBIG = (0.15, 0.40)    # 확인이 필요한 경계 무음(초)
PAD = 1.5               # 쉼 그림: 경계 앞뒤
TAKE_MAX = 6.0          # 리테이크 그림: 테이크 앞부분 최대 길이
MAX_PAUSES, MAX_TAKES = 8, 4
FRAMES = 4              # 줄마다 화면 칸 수
W = 1600


@dataclass
class View:
    id: str
    kind: str                                    # pause | retake
    rows: list[tuple[str, float, float]]         # (라벨, 시작, 끝)
    cuts: list[tuple[float, float]] = field(default_factory=list)   # 초안이 자르는 구간(빨간 띠)
    note: str = ""


def _overlap(a: Optional[tuple[int, int]], b: Optional[tuple[int, int]]) -> int:
    return max(0, min(a[1], b[1]) - max(a[0], b[0])) if a and b else 0


def ambiguous_views(utts: list[Utterance], removals: list[dict], raw: list[Word]) -> list[View]:
    """판단이 갈리는 컷 경계만 고른다 — 리테이크 비교 먼저(최대 MAX_TAKES), 그다음 쉼이 짧은 경계부터(최대 MAX_PAUSES)."""
    kept = [u for u in utts if u.kept and u.words]
    views: list[View] = []
    for u in sorted((u for u in utts if u.status == "retake" and u.words and u.script_span), key=lambda u: u.start):
        rival = max(kept, key=lambda v: _overlap(u.script_span, v.script_span), default=None)
        if rival is None or not _overlap(u.script_span, rival.script_span):
            continue
        views.append(View("", "retake", [(f"뺀 테이크 U{u.id}", u.start, min(u.end, u.start + TAKE_MAX)),
                                         (f"남긴 테이크 U{rival.id}", rival.start, min(rival.end, rival.start + TAKE_MAX))],
                          [(u.start, u.end)], f"리테이크 비교: 뺀 U{u.id} / 남긴 U{rival.id}"))
        if len(views) >= MAX_TAKES:
            break

    def in_kept(t: float) -> bool:
        return any(v.start - 0.05 <= t <= v.end + 0.05 for v in kept)

    ws = sorted(raw, key=lambda w: w.start)
    spans = [(float(r["start"]), float(r["end"]), f"R{i}") for i, r in enumerate(removals)]
    spans += [(u.start, u.end, f"U{u.id}") for u in utts if not u.kept and u.status != "noise" and u.words]
    pauses: list[tuple[float, View]] = []
    for a, b, name in spans:
        prev = next((w for w in reversed(ws) if w.end <= a + 0.01), None)
        nxt = next((w for w in ws if w.start >= b - 0.01), None)
        for gap, edge, side, nb in ((a - prev.end if prev else -1, a, "앞", prev), (nxt.start - b if nxt else -1, b, "뒤", nxt)):
            if AMBIG[0] <= gap < AMBIG[1] and nb is not None and in_kept(nb.start):
                pauses.append((gap, View("", "pause", [(f"{name} {side} 경계 · 쉼 {gap * 1000:.0f}ms", edge - PAD, edge + PAD)],
                                         [(a, b)], f"{name} {side} 경계 쉼 {gap * 1000:.0f}ms")))
    seen: list[float] = []
    for _, v in sorted(pauses, key=lambda p: p[0]):
        mid = (v.rows[0][1] + v.rows[0][2]) / 2
        if any(abs(mid - s) < PAD for s in seen):
            continue
        seen.append(mid)
        views.append(v)
        if len(seen) >= MAX_PAUSES:
            break
    for i, v in enumerate(views, 1):
        v.id = f"V{i}"
    return views


def views_text(views: list[View]) -> str:
    if not views:
        return ""
    lines = ["\n# 컷 경계 그림(애매한 곳만 — [이미지 V번호]. 위: 화면 · 가운데: 파형(빨간 띠 = 초안이 자르는 구간) · 아래: 단어)"]
    lines += [f"{v.id} {v.note}" for v in views]
    return "\n".join(lines)


def _font(size: int):
    from ..review import _font as f
    return f(size)


def render_view(view: View, audio16k: np.ndarray, words: list[Word], frame_at: Callable[[float], Optional["object"]],
                dst: Path, sr: int = 16000) -> Path:
    """한 장: 줄마다 [라벨 · 필름스트립 FRAMES 칸 · 파형(+빨간 띠·경계선) · 단어 라벨]."""
    from PIL import Image, ImageDraw
    fw, fh, wave_h, word_h, head = W // FRAMES, W * 9 // 16 // FRAMES, 140, 64, 40
    row_h = head + fh + wave_h + word_h
    img = Image.new("RGB", (W, row_h * len(view.rows)), (24, 24, 26))
    d = ImageDraw.Draw(img, "RGBA")
    f_head, f_word = _font(24), _font(20)
    for r, (label, t0, t1) in enumerate(view.rows):
        y0, span = r * row_h, max(0.1, t1 - t0)
        x_of = (lambda t: int((t - t0) / span * (W - 1)))
        d.text((12, y0 + 8), f"{view.id} · {label} · {t0:.2f}–{t1:.2f}s", font=f_head, fill=(240, 240, 240))
        for k in range(FRAMES):
            fr = frame_at(t0 + span * (k + 0.5) / FRAMES)
            if fr is not None:
                img.paste(fr.convert("RGB").resize((fw, fh)), (k * fw, y0 + head))
            else:
                d.rectangle((k * fw, y0 + head, (k + 1) * fw - 2, y0 + head + fh), fill=(60, 60, 64))
        wy = y0 + head + fh
        d.rectangle((0, wy, W, wy + wave_h), fill=(14, 14, 16))
        # 화소마다 그 시각의 표본 — 창이 0초 앞이나 오디오 끝 뒤로 나가도 단어 라벨과 같은 자리에 그린다
        edges = np.clip(((t0 + span * np.arange(W + 1) / W) * sr).astype(int), 0, len(audio16k))
        amp = np.array([float(np.abs(audio16k[a:b]).max()) if b > a else 0.0 for a, b in zip(edges[:-1], edges[1:])])
        if amp.size and amp.max() > 0:
            mid = wy + wave_h // 2
            for x, v in enumerate(amp / amp.max()):
                h = int(v * (wave_h // 2 - 4))
                d.line((x, mid - h, x, mid + h), fill=(120, 200, 255))
        for a, b in view.cuts:
            if b > t0 and a < t1:
                d.rectangle((max(0, x_of(a)), wy, min(W, x_of(b)), wy + wave_h), fill=(230, 40, 40, 110))
        for a, b in view.cuts:
            for t in (a, b):
                if t0 <= t <= t1:
                    d.line((x_of(t), wy, x_of(t), wy + wave_h), fill=(255, 80, 80), width=2)
        ty = wy + wave_h + 6
        for j, w in enumerate(x for x in words if x.end > t0 and x.start < t1):
            x = max(0, x_of(w.start))
            d.line((x, wy + wave_h, x, ty + (j % 2) * 26), fill=(160, 160, 160))
            d.text((x + 3, ty + (j % 2) * 26), w.text, font=f_word, fill=(250, 220, 120))
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, quality=85)
    return dst
