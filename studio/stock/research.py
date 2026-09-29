"""🎞 자료 리서처: B-roll 요청 → 무료 스톡 검색(Pixabay·Pexels·Coverr·Unsplash) → 후보 컨택트 시트
→ Claude 가 보고 선택 → 다운로드·정리.

- 요청마다 후보 최대 6개를 한 장의 시트(C1~C6 라벨)로 묶어 비전으로 보낸다(이미지 수·토큰 절약).
- 제공처별 후보를 번갈아 섞는다. 영상 요청이 비면 한국어 검색어 → 사진 순으로 넓힌다. 끝까지 못 찾거나 에이전트가 -1 을 고르면
  그 B-roll 은 쓰지 않는다(틀린 B-roll 보다 없는 게 낫다).
- 결과는 work/stock.json 에 캐시 → 재실행 때 검색·선택·다운로드를 반복하지 않는다.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Callable, Optional

from ..media.ffmpeg import FFmpeg
from ..util import CancelToken, LogFn, noop_log, read_json, text_hash, write_json
from .base import StockCandidate, StockError
from .providers import StockHub
from .process import prepare_photo, prepare_video

PickFn = Callable[[str, list[tuple[str, bytes, str]]], list[dict[str, Any]]]

CELL_W, CELL_H, COLS = 400, 225, 3
NEED_SEC = 8.0   # broll 템플릿 최대 7초 + 여유


def request_key(st: dict[str, Any]) -> str:
    return text_hash(st.get("kind", ""), st.get("query_en", ""), st.get("query_ko", ""), "stock-v1")


def contact_sheet(thumbs: list[tuple[str, Optional[bytes]]]) -> bytes:
    """[(라벨, jpeg 바이트)] → 3열 격자 JPEG. 라벨은 ASCII 만(PIL 기본 폰트)."""
    from PIL import Image, ImageDraw, ImageOps

    rows = max(1, (len(thumbs) + COLS - 1) // COLS)
    sheet = Image.new("RGB", (CELL_W * COLS + 8 * (COLS + 1), CELL_H * rows + 8 * (rows + 1)), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for i, (label, data) in enumerate(thumbs):
        x = 8 + (i % COLS) * (CELL_W + 8)
        y = 8 + (i // COLS) * (CELL_H + 8)
        if data:
            try:
                im = Image.open(io.BytesIO(data)).convert("RGB")
                im = ImageOps.fit(im, (CELL_W, CELL_H), Image.LANCZOS)
                sheet.paste(im, (x, y))
            except Exception:  # noqa: BLE001 - 깨진 썸네일은 빈 칸
                pass
        tw = 8 + 7 * len(label)
        draw.rectangle([x, y, x + tw, y + 18], fill=(0, 0, 0))
        draw.text((x + 4, y + 3), label, fill=(255, 255, 255))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=85)
    return buf.getvalue()


class StockResearcher:
    def __init__(self, hub: StockHub, ff: FFmpeg, *, work: Path, public: Path, fps: int = 30,
                 pick: Optional[PickFn] = None, log: LogFn = noop_log, cancel: Optional[CancelToken] = None,
                 per_request: int = 6):
        self.hub = hub
        self.ff = ff
        self.work = work
        self.public = public
        self.fps = fps
        self.pick = pick
        self.log = log
        self.cancel = cancel
        self.per_request = per_request
        self.cache_file = work / "stock.json"
        self.cache: dict[str, Any] = read_json(self.cache_file, {})
        self.credits: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    def search(self, st: dict[str, Any]) -> list[StockCandidate]:
        return self.hub.search(st, self.per_request)

    def _thumb(self, c: StockCandidate) -> Optional[bytes]:
        import requests
        if not c.thumb:
            return None
        try:
            r = requests.get(c.thumb, timeout=20)
            r.raise_for_status()
            return r.content
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------
    def run(self, graphic_lists: list[list[dict[str, Any]]], progress: Callable[[float], None] = lambda f: None) -> None:
        """broll 그래픽에 src/kind/credit 를 채우고, 소재를 못 구한 것은 목록에서 뺀다."""
        reqs: dict[str, dict[str, Any]] = {}
        for gl in graphic_lists:
            for g in gl:
                if g.get("template") == "broll" and isinstance(g.get("stock"), dict):
                    reqs.setdefault(request_key(g["stock"]), g["stock"])
        if not reqs:
            return
        self.log(f"🎞 스톡 요청 {len(reqs)}건 · 검색처: {', '.join(self.hub.names) or '없음'}")
        todo = [k for k in reqs if not self._cached_ok(k)]
        # 1) 검색
        cands: dict[str, list[StockCandidate]] = {}
        for i, k in enumerate(todo):
            if self.cancel:
                self.cancel.check()
            try:
                cands[k] = self.search(reqs[k])
            except StockError as e:
                self.log(f"🎞 {e}")
                break
            except Exception as e:  # noqa: BLE001 - 네트워크 오류는 그 요청만 건너뜀
                self.log(f"🎞 검색 실패 '{reqs[k].get('query_en')}': {e}")
                cands[k] = []
            progress(0.3 * (i + 1) / max(1, len(todo)))
        # 2) 선택(Claude 비전) — 후보가 있는 요청만 시트로
        live = [k for k in todo if cands.get(k)]
        choice: dict[str, int] = {k: 0 for k in live}
        if live and self.pick:
            sheets, lines = [], []
            for n, k in enumerate(live, 1):
                st = reqs[k]
                thumbs = [(f"C{j} {c.provider[:7]}" + (f" {c.duration:.0f}s" if c.kind == "video" else " photo"),
                           self._thumb(c))
                          for j, c in enumerate(cands[k], 1)]
                sheets.append((f"R{n}", contact_sheet(thumbs), "image/jpeg"))
                lines.append(f"- R{n} ({st.get('kind')}) 검색어: {st.get('query_en')} / {st.get('query_ko')}"
                             f" · 목적: {st.get('purpose', '')} · must_show: {st.get('must_show', '')}")
            try:
                picks = self.pick("\n".join(lines), sheets)
                choice = {}
                for p in picks:
                    r, c = int(p.get("request", 0)), int(p.get("candidate", -1))
                    if 1 <= r <= len(live):
                        choice[live[r - 1]] = c - 1 if c >= 1 else -1
                        if c < 1:
                            self.log(f"🎞 R{r}: 맞는 소재 없음 → 제외 ({p.get('reason', '')})")
                for k in live:
                    choice.setdefault(k, 0)
            except Exception as e:  # noqa: BLE001 - 선택 실패 시 첫 후보
                self.log(f"🎞 자동 선택 실패 → 첫 후보 사용: {e}")
                choice = {k: 0 for k in live}
        progress(0.5)
        # 3) 다운로드·정리
        for i, k in enumerate(todo):
            if self.cancel:
                self.cancel.check()
            idx = choice.get(k, -1)
            if k not in cands or idx < 0 or idx >= len(cands.get(k, [])):
                self.cache[k] = {"none": True}
                continue
            c = cands[k][idx]
            try:
                self.cache[k] = self._fetch(c)
            except Exception as e:  # noqa: BLE001
                self.log(f"🎞 다운로드 실패({c.url}): {e}")
                self.cache[k] = {"none": True}
            progress(0.5 + 0.5 * (i + 1) / max(1, len(todo)))
        write_json(self.cache_file, self.cache)
        # 4) 그래픽에 반영
        used: set[str] = set()
        for gl in graphic_lists:
            keep = []
            for g in gl:
                if g.get("template") != "broll":
                    keep.append(g)
                    continue
                res = self.cache.get(request_key(g.get("stock") or {}), {})
                if not res or res.get("none") or not (self.public / res["src"]).exists():
                    continue
                g.update(src=res["src"], kind=res["kind"], credit=res["credit"], stock_url=res["url"])
                if res["kind"] == "photo":
                    g.setdefault("kenburns", "in")
                keep.append(g)
                if res["src"] not in used:
                    used.add(res["src"])
                    self.credits.append({"query": g["stock"].get("query_en"), "origin": res.get("provider", "stock"),
                                         "credit": res["credit"], "url": res["url"], "author_url": res.get("author_url", "")})
            gl[:] = keep
        self.log(f"🎞 스톡 확보 {len(used)}건")

    def _cached_ok(self, k: str) -> bool:
        res = self.cache.get(k)
        if not res:
            return False
        if res.get("none"):
            return True
        return (self.public / res.get("src", "__")).exists()

    def _fetch(self, c: StockCandidate) -> dict[str, Any]:
        raw_dir = self.work / "stock_raw"
        out_dir = self.public / "broll"
        out_dir.mkdir(parents=True, exist_ok=True)
        if c.kind == "video":
            raw = self.hub.download(c, raw_dir / f"{c.key}.mp4")
            dst = out_dir / f"{c.key}.mp4"
            if not dst.exists():
                prepare_video(self.ff, raw, dst, need=NEED_SEC, fps=self.fps, src_duration=c.duration, log=self.log,
                              cancel=self.cancel)
        else:
            raw = self.hub.download(c, raw_dir / f"{c.key}.jpg")
            dst = out_dir / f"{c.key}.jpg"
            if not dst.exists():
                prepare_photo(raw, dst)
        self.log(f"🎞 {c.provider} {c.kind} {c.id} · {c.credit}")
        return {"src": f"broll/{dst.name}", "kind": c.kind, "credit": c.credit, "url": c.url,
                "author_url": c.author_url, "provider": c.provider}
