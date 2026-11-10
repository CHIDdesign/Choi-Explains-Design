"""NASA Image and Video Library — 키 없이 되는 사진·영상 제공처(우주·항공·공학 실물). 영상을 키 없이 주는 유일한 곳.

지침(nasa.gov/nasa-brand-center/images-and-media, 2026-11-09 확인): 출처 NASA 표기, 제3자 저작물은 표시되어 있음,
식별 가능한 인물의 상업 이용은 본인 허락이 필요. 그래서 설명에 권리 표시가 있거나, 협력사가 찍었거나, 사람이 주제인 항목은 뺀다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from .. import net
from ..assets.museums import UA, relevant
from .base import StockCandidate, StockProvider

API = "https://images-api.nasa.gov/search"
HEADERS = {"User-Agent": UA, "Accept": "application/json"}
RIGHTS = re.compile(r"courtesy|copyright|©|all rights reserved", re.I)
# shortcut: 2026-11-09 실측한 사례('photographer: Rocket Lab')와 주요 협력사만, 다른 이름이 대장에서 보이면 더한다
PARTNERS = re.compile(r"rocket lab|spacex|boeing|lockheed|northrop|blue origin|united launch|\besa\b|jaxa|roscosmos|"
                      r"getty|reuters|\bafp\b", re.I)
# shortcut: 메타데이터로만 거른다(배경의 얼굴은 비전 선택 몫 — alt 앞머리로 알린다), 얼굴 검출이 필요해지면 받은 뒤에 잰다
PEOPLE = re.compile(r"\b(astronauts?|cosmonauts?|portraits?|crew|administrator|president|senator|engineers?|technicians?|"
                    r"scientists?|employees?|workers?|students?|briefing|conference|interview|ceremony)\b", re.I)
VIDEO_ORDER = ("~large.mp4", "~medium.mp4", "~orig.mp4", "~mobile.mp4")     # orig 는 ~large 의 5배쯤(실측 105MB : 20MB)


def _https(url: str) -> str:
    return str(url or "").replace("http://", "https://", 1).replace(" ", "%20")


def usable(d: dict[str, Any]) -> bool:
    """권리 표시·협력사·사람 주제가 아닌가(제목·설명·촬영자·키워드 전부 본다)."""
    who = f"{d.get('photographer') or ''} {d.get('secondary_creator') or ''}"
    text = " ".join([str(d.get("title") or ""), str(d.get("description") or ""), who, " ".join(map(str, d.get("keywords") or []))])
    return not (RIGHTS.search(text) or PARTNERS.search(who) or PEOPLE.search(text))


def seconds(meta: dict[str, Any]) -> float:
    """metadata.json 의 길이('12.3 s' · '0:01:23') → 초. 없으면 0."""
    raw = str(meta.get("Composite:Duration") or meta.get("QuickTime:Duration") or meta.get("Video:Duration") or "")
    if ":" in raw:
        total = 0.0
        for part in raw.split(":"):
            total = total * 60 + float(re.sub(r"[^0-9.]", "", part) or 0)
        return total
    m = re.search(r"[0-9.]+", raw)
    return float(m.group()) if m else 0.0


class Nasa(StockProvider):
    name = "NASA"
    photos = videos = True

    def __init__(self, key: str = "", **kw: Any):
        super().__init__(**kw)

    def _search(self, query: str, media: str, per_page: int) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        data = self._get_json(API, {"q": query, "media_type": media, "page_size": max(10, min(100, per_page * 5))}, HEADERS)
        out = []
        for it in (data.get("collection") or {}).get("items") or []:
            d = (it.get("data") or [{}])[0]
            # 검색이 느슨해서('coffee desk' 에도 답한다) 낱말이 맞는 것만 — 맞지 않는 후보가 다른 제공처의 자리를 먹지 않게
            hay = {"title": d.get("title"), "description": f"{d.get('description') or ''} {' '.join(map(str, d.get('keywords') or []))}"}
            if d.get("nasa_id") and usable(d) and relevant(query, hay):
                out.append((it, d))
        return out

    def _cand(self, kind: str, it: dict[str, Any], d: dict[str, Any], *, download: str, w: int, h: int) -> StockCandidate:
        thumb = next((_https(x["href"]) for x in it.get("links") or [] if x.get("rel") == "preview" and x.get("href")), "")
        who = str(d.get("photographer") or d.get("secondary_creator") or "").strip()
        keywords = ", ".join(map(str, d.get("keywords") or []))
        return StockCandidate(
            kind=kind, id=d["nasa_id"], url=f"https://images.nasa.gov/details/{d['nasa_id']}", thumb=thumb, download=download,
            width=w, height=h, author="" if who.upper() == "NASA" else who, provider=self.name,
            alt=f"식별 인물 금지 · {d.get('title') or ''} · {keywords}", extra={"manifest": _https(it.get("href", ""))})

    def search_photos(self, query: str, *, per_page: int = 6, locale: str = "") -> list[StockCandidate]:
        if locale.lower().startswith("ko"):
            return []
        out: list[StockCandidate] = []
        for it, d in self._search(query, "image", per_page):
            jpgs = sorted((x for x in it.get("links") or [] if str(x.get("href", "")).lower().endswith((".jpg", ".jpeg"))
                           and x.get("width") and x.get("height")), key=lambda x: int(x["width"]))
            best: Optional[dict[str, Any]] = next((x for x in jpgs if int(x["width"]) >= 1920), jpgs[-1] if jpgs else None)
            if best is None or int(best["width"]) < 900 or int(best["height"]) > int(best["width"]):   # Openverse 의 wide 와 같은 기준
                continue
            out.append(self._cand("photo", it, d, download=_https(best["href"]), w=int(best["width"]), h=int(best["height"])))
            if len(out) >= per_page:
                break
        return out

    def search_videos(self, query: str, *, per_page: int = 6, locale: str = "") -> list[StockCandidate]:
        if locale.lower().startswith("ko"):
            return []
        # 파일 주소는 항목마다 따로 받아야 해서 고른 뒤에(download) — 검색마다 후보 수만큼 더 부르지 않게
        return [self._cand("video", it, d, download="", w=0, h=0) for it, d in self._search(query, "video", per_page)[:per_page]]

    def download(self, c: StockCandidate, dst: Path) -> Path:
        if c.kind == "video" and not c.download:
            files = [_https(u) for u in net.get_json(c.extra["manifest"], headers=HEADERS, timeout=25)]
            c.download = next((u for suffix in VIDEO_ORDER for u in files if u.endswith(suffix)), "")
            if not c.download:
                raise RuntimeError(f"NASA {c.id}: 영상 파일 없음")
            meta = next((u for u in files if u.endswith("metadata.json")), "")
            if meta:         # 길이를 알아야 짧은 영상을 반복하고 앞 타이틀을 건너뛴다(prepare_video)
                c.duration = seconds(net.get_json(meta, headers=HEADERS, timeout=25))
        return super().download(c, dst)
