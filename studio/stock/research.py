"""🎞 자료 리서처: B-roll 요청 → 무료 스톡 검색(Pixabay·Pexels·Coverr·Unsplash·Openverse) → 후보 컨택트 시트
→ Claude 가 보고 선택 → 다운로드·정리.

- 요청마다 후보 최대 6개를 한 장의 시트(C1~C6 라벨)로 묶어 비전으로 보낸다(이미지 수·토큰 절약).
- 제공처별 후보를 번갈아 섞는다. 영상 요청이 비면 한국어 검색어 → 사진 순으로 넓힌다. 끝까지 못 찾거나 에이전트가 -1 을 고르면
  그 B-roll 은 쓰지 않는다(틀린 B-roll 보다 없는 게 낫다).
- 모션 장면 안의 'pixabay:<vector|illustration|photo>:<검색어>' 이미지(image·device 부품)는 resolve_images 가 broll/img_* 로 바꾼다.
- 결과는 work/stock.json 에 캐시 → 재실행 때 검색·선택·다운로드를 반복하지 않는다.
  단, 캐시에 남기는 '없음'은 에이전트가 직접 뺀 것뿐이다. 검색 0건·네트워크·다운로드 실패는 다음 실행에 다시 시도한다
  (예전에는 한 번 실패하면 영원히 '없음'으로 남았다).
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Callable, Optional

from .. import net
from ..media.ffmpeg import FFmpeg
from ..util import Cancelled, CancelToken, LogFn, noop_log, read_json, text_hash, write_json
from ..director.plan import type_card
from .base import StockCandidate, StockError
from .providers import StockHub
from .process import prepare_photo, prepare_video

PickFn = Callable[[str, list[tuple[str, bytes, str]]], list[dict[str, Any]]]

CELL_W, CELL_H, COLS = 400, 225, 3
NEED_SEC = 8.0   # broll 템플릿 최대 7초 + 여유


def stock_refs(spec: Any) -> list[dict[str, Any]]:
    """모션 장면 안에서 아직 파일로 바뀌지 않은 'pixabay:' 참조를 가진 부품 — 이미지(image)와 기기 화면(device).
    2026-10-04: device.src 의 'pixabay:photo:…' 를 image 만 보던 해석이 놓쳐 렌더가 404 로 멈췄다."""
    if not isinstance(spec, dict):
        return []
    return [e for e in spec.get("elements", []) or []
            if isinstance(e, dict) and str(e.get("src", "")).startswith("pixabay:")]


def drop_ref(spec: dict[str, Any], el: dict[str, Any]) -> None:
    """못 구한 참조: 이미지 부품은 장면에서 빼고, 기기(device)는 화면 그림만 비운다(행·제목으로 그려진다)."""
    if el.get("type") == "image":
        spec["elements"] = [e for e in spec.get("elements", []) or [] if e is not el]
    else:
        el.pop("src", None)


def strip_stock_images(graphic_lists: list[list[dict[str, Any]]]) -> int:
    """아직 파일로 바뀌지 않은 'pixabay:' 참조를 뺀다(스톡이 꺼졌거나 실패했을 때)."""
    n = 0
    for gl in graphic_lists:
        for g in gl:
            spec = g.get("spec") if g.get("template") == "motion" else None
            for el in stock_refs(spec):
                drop_ref(spec, el)
                n += 1
    return n


def request_key(st: dict[str, Any]) -> str:
    return text_hash(st.get("kind", ""), st.get("query_en", ""), st.get("query_ko", ""), "stock-v1")


def contact_sheet(thumbs: list[tuple[str, Optional[bytes]]], *, cell: tuple[int, int] = (0, 0),
                  contain: bool = False) -> bytes:
    """[(라벨, jpeg 바이트)] → 3열 격자 JPEG. 라벨은 ASCII 만(PIL 기본 폰트). contain: 자르지 않고 칸 안에 맞춤
    (인물 사진 — 가운데를 잘라 내면 머리·턱이 잘려 표정을 볼 수 없다)."""
    from PIL import Image, ImageDraw, ImageOps

    cw, ch = cell if cell[0] and cell[1] else (CELL_W, CELL_H)
    rows = max(1, (len(thumbs) + COLS - 1) // COLS)
    sheet = Image.new("RGB", (cw * COLS + 8 * (COLS + 1), ch * rows + 8 * (rows + 1)), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for i, (label, data) in enumerate(thumbs):
        x = 8 + (i % COLS) * (cw + 8)
        y = 8 + (i // COLS) * (ch + 8)
        if data:
            try:
                im = Image.open(io.BytesIO(data)).convert("RGB")
                if contain:
                    im = ImageOps.contain(im, (cw, ch), Image.LANCZOS)
                    sheet.paste(im, (x + (cw - im.width) // 2, y + (ch - im.height) // 2))
                else:
                    im = ImageOps.fit(im, (cw, ch), Image.LANCZOS)
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
        self.fallbacks: list[dict[str, Any]] = []        # 못 구한 요청 → 자료 카드(type_card) 또는 잃음(lost)
        self.stats: dict[str, int] = {}

    # ------------------------------------------------------------------
    def search(self, st: dict[str, Any]) -> list[StockCandidate]:
        return self.hub.search(st, self.per_request)

    def _pick_round(self, live: list[str], reqs: dict[str, dict[str, Any]], cands: dict[str, list[StockCandidate]],
                    *, retried: bool = False) -> tuple[dict[str, int], dict[str, str]]:
        """후보 시트 → Claude 비전 선택 → (요청 → 후보 번호(0부터, 거절은 −1), 요청 → 다시 찾을 검색어). 선택 실패면 첫 후보."""
        sheets, lines = [], []
        for n, k in enumerate(live, 1):
            st = reqs[k]
            thumbs = [(f"C{j} {c.provider[:7]}" + (f" {c.duration:.0f}s" if c.kind == "video" else " photo"),
                       self._thumb(c))
                      for j, c in enumerate(cands[k], 1)]
            sheets.append((f"R{n}", contact_sheet(thumbs), "image/jpeg"))
            # 낱말이 아니라 문장의 뜻으로 고르게: 그 장면에서 하는 말 + 후보마다 제공처의 설명(태그)
            lines.append(f"- R{n} ({st.get('kind')}) 검색어: {st.get('query_en')} / {st.get('query_ko')}"
                         f" · 목적: {st.get('purpose', '')} · must_show: {st.get('must_show', '')}"
                         + (f"\n  그 장면의 말: 「{st['context']}」" if st.get("context") else "")
                         + "".join(f"\n  C{j}: {c.alt[:70]}" for j, c in enumerate(cands[k], 1) if c.alt)
                         + ("\n  (리서처의 새 검색어로 다시 찾은 후보)" if retried else ""))
        choice: dict[str, int] = {}
        retry: dict[str, str] = {}
        try:
            picks = self.pick("\n".join(lines), sheets) if self.pick else []
            for p in picks:
                r, c = int(p.get("request", 0)), int(p.get("candidate", -1))
                if 1 <= r <= len(live):
                    choice[live[r - 1]] = c - 1 if c >= 1 else -1
                    if c < 1:
                        self.stats["rejected"] += 1
                        retry[live[r - 1]] = str(p.get("retry_query_en") or "").strip()
                        self.log(f"🎞 R{r}: 맞는 소재 없음 → {'제외' if retried or not retry[live[r - 1]] else '다시 검색'}"
                                 f" ({p.get('reason', '')})")
            for k in live:
                choice.setdefault(k, 0)
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001 - 선택 실패 시 첫 후보
            self.log(f"🎞 자동 선택 실패 → 첫 후보 사용: {e}")
            choice = {k: 0 for k in live}
        return choice, retry

    def _thumb(self, c: StockCandidate) -> Optional[bytes]:
        if not c.thumb:
            return None
        try:
            r = net.request(c.thumb, timeout=20)
            return r.content if r.ok else None
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
        self.stats = {"requests": len(reqs), "cached": len(reqs) - len(todo), "found": 0, "rejected": 0,
                      "no_results": 0, "download_failed": 0, "used": 0}
        for i, k in enumerate(todo):
            if self.cancel:
                self.cancel.check()
            try:
                cands[k] = self.search(reqs[k])
            except StockError as e:                    # 한 요청의 오류로 나머지 요청을 모두 버리지 않는다
                self.log(f"🎞 {e}")
                cands[k] = []
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001 - 네트워크 오류는 그 요청만 건너뜀
                self.log(f"🎞 검색 실패 '{reqs[k].get('query_en')}': {e}")
                cands[k] = []
            trace = getattr(self.hub, "last_trace", [])
            if cands.get(k):
                self.stats["found"] += 1
                self.log(f"🎞 '{reqs[k].get('query_en')}' 후보 {len(cands[k])}개 ({trace[-1] if trace else ''})")
            else:
                self.stats["no_results"] += 1
                self.log(f"🎞 '{reqs[k].get('query_en')}' 후보 없음 — " + " | ".join(trace[:6]))
            progress(0.3 * (i + 1) / max(1, len(todo)))
        # 2) 선택(Claude 비전) — 후보가 있는 요청만 시트로
        live = [k for k in todo if cands.get(k)]
        choice: dict[str, int] = {k: 0 for k in live}
        if live and self.pick:
            choice, retry = self._pick_round(live, reqs, cands)
            # 2b) 거절된 요청은 리서처가 적은 새 검색어로 한 번 더(2026-10-03: 거절한 자리가 그대로 얼굴로 남아 뒤 절반이 맨얼굴)
            again = {k: q for k, q in retry.items() if choice.get(k, 0) < 0 and q
                     and q.strip().lower() != str(reqs[k].get("query_en", "")).strip().lower()}
            if again:
                self.stats["retried"] = len(again)
                live2 = []
                for k, q in again.items():
                    try:
                        found = self.search({**reqs[k], "query_en": q, "query_ko": ""})
                    except Cancelled:
                        raise
                    except Exception as e:  # noqa: BLE001
                        self.log(f"🎞 다시 검색 실패 '{q}': {e}")
                        found = []
                    self.log(f"🎞 '{reqs[k].get('query_en')}' → 리서처의 검색어 '{q}' 로 다시: 후보 {len(found)}개")
                    if found:
                        cands[k] = found
                        live2.append(k)
                if live2:
                    choice2, _ = self._pick_round(live2, reqs, cands, retried=True)
                    for k in live2:
                        choice[k] = choice2.get(k, -1)
                        if choice[k] >= 0:
                            self.stats["retry_ok"] = self.stats.get("retry_ok", 0) + 1
        progress(0.5)
        # 3) 다운로드·정리
        for i, k in enumerate(todo):
            if self.cancel:
                self.cancel.check()
            idx = choice.get(k, -1)
            if k not in cands or not cands.get(k):
                self.cache[k] = {"none": True, "why": "no_results"}      # 다음 실행에 다시 검색
                continue
            if idx >= len(cands[k]):
                idx = 0                                                  # 없는 번호를 골랐으면 첫 후보(영구 제외 아님)
            if idx < 0:
                self.cache[k] = {"none": True, "why": "rejected"}        # 에이전트가 뺀 것만 확정
                continue
            # 고른 후보가 안 받아지면 다음 후보로
            got = None
            for c in [cands[k][idx]] + [x for j, x in enumerate(cands[k]) if j != idx][:2]:
                try:
                    got = self._fetch(c)
                    break
                except Cancelled:
                    raise
                except Exception as e:  # noqa: BLE001
                    self.log(f"🎞 다운로드 실패({c.provider} {c.id}): {e}")
            if got is None:
                self.stats["download_failed"] += 1
            self.cache[k] = got or {"none": True, "why": "download_failed"}
            progress(0.5 + 0.5 * (i + 1) / max(1, len(todo)))
        write_json(self.cache_file, self.cache)
        # 4) 그래픽에 반영 — 못 구한 요청은 조용히 지우지 않는다: 리서처가 준 화면 글(caption)이 있으면 타이포 자료 카드로,
        #    없으면 그 자리를 비우고 무엇을 잃었는지 로그(P0-4)
        used: set[str] = set()
        self.stats.setdefault("fallback", 0)
        self.stats.setdefault("lost", 0)
        for gl in graphic_lists:
            keep = []
            for g in gl:
                if g.get("template") != "broll":
                    keep.append(g)
                    continue
                res = self.cache.get(request_key(g.get("stock") or {}), {})
                if not res or res.get("none") or not (self.public / res["src"]).exists():
                    why = (res or {}).get("why", "no_results")
                    card = type_card(g)
                    st = g.get("stock") or {}
                    if card is not None:
                        self.stats["fallback"] += 1
                        keep.append(card)
                        self.log(f"🎞 '{st.get('query_en')}' 소재 없음({why}) → 자료 카드 「{card['title']}」")
                    else:
                        self.stats["lost"] += 1
                        self.log(f"🎞 '{st.get('query_en')}' 소재 없음({why}) — 그 자리는 비웁니다")
                    self.fallbacks.append({"query": st.get("query_en"), "origin": "type_card" if card else "lost",
                                           "why": why})
                    continue
                g.update(src=res["src"], kind=res["kind"], credit=res["credit"], stock_url=res["url"])
                if res["kind"] == "photo":
                    g.setdefault("kenburns", "in")
                    # 하우스 트리트먼트(07b): 놓이는 곳(전면 · 종이 위)에 맞춰 [잉크, 종이] 안으로 — 캐시는 원본 그대로 두고
                    # 그래픽마다 처리한 사본을 쓴다(파일 이름에 처리·판)
                    g["src"] = self._house(res["src"], "photo", "full" if g.get("layout") == "fullscreen" else "paper")
                    if g.get("layout") == "fullscreen":
                        self._collage_extras(g)
                keep.append(g)
                if res["src"] not in used:
                    used.add(res["src"])
                    self.stats["used"] += 1
                    self.credits.append({"query": g["stock"].get("query_en"), "origin": res.get("provider", "stock"),
                                         "credit": res["credit"], "url": res["url"], "author_url": res.get("author_url", ""),
                                         "attribution": res.get("attribution", "")})
            gl[:] = keep
        self.log(f"🎞 스톡 확보 {len(used)}건")

    # ------------------------------------------------------------------
    def resolve_images(self, graphic_lists: list[list[dict[str, Any]]]) -> int:
        """모션 장면 안의 'pixabay:<vector|illustration|photo>:<영어 검색어>' 이미지(image·device 부품)를 Pixabay 에서
        받아 broll/img_….png|jpg 로 바꾼다(키가 없으면 사진은 Openverse). 못 구한 이미지 부품은 장면에서 빼고, 기기는
        화면 그림만 비운다 — 장면은 남는다."""
        refs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for gl in graphic_lists:
            for g in gl:
                spec = g.get("spec") if g.get("template") == "motion" else None
                if not isinstance(spec, dict):
                    continue
                refs += [(spec, el) for el in stock_refs(spec)]
        if not refs:
            return 0
        got: dict[str, Optional[dict[str, Any]]] = {}
        n = 0
        for spec, el in refs:
            ref = el["src"]
            if ref not in got:
                got[ref] = self._image_for(ref)
            res = got[ref]
            if res:
                # 하우스 트리트먼트(07b 7절): 클립아트(vector·illustration)는 언제나 잉크 한 색 선화, 사진은 듀오톤 —
                # 칠판·크림 화면 위 원색 클립아트(10/1 커피컵·책 더미)가 '붙여 넣은 것'으로 보이던 것
                kind = (ref.split(":", 2) + ["", ""])[1] or "vector"
                dark = str(spec.get("bg") or "") in ("board", "ink", "dark", "stage", "chalk")
                clip = kind in ("vector", "illustration")
                # 기기 화면 속 그림은 화면이라 색을 지키고 톤만 맞춘다(듀오톤 모니터는 고장 난 화면처럼 보인다)
                el["src"] = self._house(res["src"], "vector" if clip else "photo", "stage" if dark else "paper",
                                        treatment="lineart" if clip else
                                        ("graded" if el.get("type") == "device" else "duotone"))
                n += 1
            else:
                drop_ref(spec, el)
        write_json(self.cache_file, self.cache)
        ok = sum(1 for v in got.values() if v)
        self.log(f"🖼 모션 그래픽 이미지 {ok}/{len(got)}건 확보(Pixabay)")
        self.stats["images"] = ok
        return n

    def _image_for(self, ref: str) -> Optional[dict[str, Any]]:
        parts = ref.split(":", 2)
        kind, query = (parts[1], parts[2]) if len(parts) == 3 else ("vector", parts[-1])
        key = text_hash(ref, "img-v1")
        res = self.cache.get(key)
        if res and not res.get("none") and (self.public / res.get("src", "__")).exists():
            return res
        from .providers import query_variants
        pix = next((p for p in self.hub.providers if p.name == "Pixabay"), None)
        ov = next((p for p in self.hub.providers if p.name == "Openverse"), None)
        cands: list[StockCandidate] = []
        for q in query_variants(query):
            if pix is not None:
                cands = self.hub._call(pix, "search_images", q, image_type=kind, per_page=5)
            if not cands and kind != "vector" and ov is not None:
                cands = self.hub._call(ov, "search_photos", q, per_page=5)
            if cands:
                break
        for c in cands[:3]:
            try:
                raw = self.hub.download(c, self.work / "stock_raw" / f"img_{c.key}.bin")
                dst = self._prepare_image(raw, f"img_{c.key}")
                res = {"src": f"broll/{dst.name}", "kind": "image", "credit": c.credit, "url": c.url,
                       "author_url": c.author_url, "provider": c.provider, "attribution": c.attribution}
                self.cache[key] = res
                self.credits.append({"query": query, "origin": c.provider, "credit": c.credit, "url": c.url,
                                     "author_url": c.author_url, "attribution": c.attribution})
                return res
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                self.log(f"🖼 이미지 다운로드 실패({c.provider} {c.id}): {e}")
        self.log(f"🖼 '{query}'({kind}) 이미지 없음 → 그 요소만 뺌")
        return None

    def _collage_extras(self, g: dict[str, Any]) -> None:
        """디자인 v3: 전면 스톡 사진의 크기와, 바탕이 고르면 오린 PNG(→ 종이 무대 위 콜라주). 실패해도 그대로 둔다."""
        from PIL import Image
        from ..assets.cutout import cutout
        p = self.public / g["src"]
        try:
            with Image.open(p) as im:
                g["w"], g["h"] = im.size
            c = cutout(p)
        except Exception:  # noqa: BLE001 - 콜라주는 덤
            return
        if c is not None and c.is_relative_to(self.public):
            g["cut"] = c.relative_to(self.public).as_posix()
            g["treatment"] = "collage"
            self.stats["cutout"] = self.stats.get("cutout", 0) + 1

    def _house(self, src: str, kind: str, surface: str, treatment: str = "auto") -> str:
        """public 기준 경로 → 하우스 트리트먼트를 거친 사본의 경로(`이름.표면.h판.jpg|png`). 실패하면 원본 그대로."""
        from ..grade.house import HOUSE_VERSION, treat_file
        p = self.public / src
        if not p.exists() or f".h{HOUSE_VERSION}." in p.name:
            return src
        base = p.with_name(f"{p.stem}.{surface}.h{HOUSE_VERSION}")
        for ext in (".jpg", ".png"):
            if base.with_suffix(ext).exists():
                return base.with_suffix(ext).relative_to(self.public).as_posix()
        try:
            out, t = treat_file(p, base, kind=kind, treatment=treatment, surface=surface)
        except Exception as e:  # noqa: BLE001 - 처리 실패는 원본으로
            self.log(f"🎞 자료 톤 처리 실패({p.name}): {e}")
            return src
        self.stats.setdefault("house", {})
        self.stats["house"][t] = self.stats["house"].get(t, 0) + 1
        return out.relative_to(self.public).as_posix()

    def _prepare_image(self, raw: Path, name: str, max_side: int = 1400) -> Path:
        """투명 PNG 는 그대로(알파 유지), 나머지는 JPEG. 긴 변 1400px."""
        from PIL import Image
        out_dir = self.public / "broll"
        out_dir.mkdir(parents=True, exist_ok=True)
        im = Image.open(raw)
        alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
        im = im.convert("RGBA" if alpha else "RGB")
        s = max_side / max(im.size)
        if s < 1:
            im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        dst = out_dir / f"{name}.{'png' if alpha else 'jpg'}"
        im.save(dst, **({"optimize": True} if alpha else {"quality": 90}))
        return dst

    def _cached_ok(self, k: str) -> bool:
        res = self.cache.get(k)
        if not res:
            return False
        if res.get("none"):
            return res.get("why") == "rejected"
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
                "author_url": c.author_url, "provider": c.provider, "attribution": c.attribution}
