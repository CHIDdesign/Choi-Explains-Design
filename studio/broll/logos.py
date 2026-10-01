"""브랜드·회사 로고 — '핀터레스트를 참고해서 디자인한다' 같은 문장에는 그 회사 임원 사진이 아니라 로고가 나와야 한다.

출처(순서):
  ① Simple Icons(CC0, 3400여 브랜드의 공식 마크 SVG + 브랜드 색) — CDN 의 목록(data/simple-icons.json)에서 이름·별칭이
     정확히 같은 것만(비슷한 이름 금지: 'Apple' ≠ 'Apple Music').
  ② 위키데이터 P154(로고 이미지) → 위키미디어 커먼즈 파일(대개 SVG). 로고는 저작권은 자유(PD-textlogo·CC0 등)여도
     상표 제한('trademarked')이 붙어 있는데, 브랜드를 설명하며 그 로고를 보여 주는 것은 상표의 지명 사용이라 이것만 허용한다.
     비자유(fair use) 로고는 쓰지 않는다.
결과는 크림 종이 위에 로고를 가운데 놓은 카드 SVG(1600×1000) — 렌더러의 모든 사진 자리(cover)에 그대로 들어가고
가장자리가 잘려도 로고는 남는다. 벡터라 어느 크기에서도 선명하다.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any, Optional

from .. import net
from ..util import LogFn, noop_log
from .images import ImageResult

SI_VERSION = "16"
SI_DATA = f"https://cdn.jsdelivr.net/npm/simple-icons@{SI_VERSION}/data/simple-icons.json"
SI_ICON = f"https://cdn.jsdelivr.net/npm/simple-icons@{SI_VERSION}/icons/{{slug}}.svg"
CARD_W, CARD_H = 1600, 1000
PAPER = "#F5F2EA"           # renderer tokens.ts NOTE.paper
INK = "#26211E"             # NOTE.ink
MAX_SVG = 1_500_000         # 이보다 큰 로고 SVG 는 PNG 썸네일로
_SUFFIX = re.compile(r"\b(inc|corp|corporation|co|ltd|llc|gmbh|ag|company|group|holdings|plc|sa)\b\.?", re.I)


def norm_brand(name: str) -> str:
    """비교용: 소문자, 법인 꼬리(Inc.·Corp.) 제거, 기호·공백 제거. '+'·'&'·'.' 는 Simple Icons 슬러그 규칙대로."""
    s = (name or "").strip().lower()
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s)
    s = _SUFFIX.sub("", s)
    s = s.replace("+", "plus").replace("&", "and").replace(".", "dot")
    return re.sub(r"[^0-9a-z가-힣]+", "", s)


def _luminance(hex6: str) -> float:
    r, g, b = (int(hex6[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(hex_a: str, hex_b: str) -> float:
    la, lb = _luminance(hex_a.lstrip("#")), _luminance(hex_b.lstrip("#"))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def icon_card_svg(path_d: str, hex6: str, *, view: float = 24.0) -> str:
    """Simple Icons 마크(24×24 경로 하나) → 크림 종이 카드. 브랜드 색이 종이 위에서 잘 안 보이면(대비 2.2 미만 — 카카오
    노랑 등) 브랜드 색 둥근 타일 위에 잉크색 마크(앱 아이콘처럼)."""
    hex6 = (hex6 or "26211E").lstrip("#").upper()
    if not re.fullmatch(r"[0-9A-F]{6}", hex6):
        hex6 = "26211E"
    size = 380.0
    x, y = (CARD_W - size) / 2, (CARD_H - size) / 2
    sc = size / view
    body = ""
    fill = f"#{hex6}"
    if contrast(fill, PAPER) < 2.2:
        tile = size * 1.45
        tx, ty = (CARD_W - tile) / 2, (CARD_H - tile) / 2
        body += (f'<rect x="{tx:.1f}" y="{ty:.1f}" width="{tile:.1f}" height="{tile:.1f}" rx="{tile * 0.22:.1f}" '
                 f'fill="{fill}"/>')
        fill = INK
    body += f'<g transform="translate({x:.1f} {y:.1f}) scale({sc:.4f})"><path d="{path_d}" fill="{fill}"/></g>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_W}" height="{CARD_H}" '
            f'viewBox="0 0 {CARD_W} {CARD_H}"><rect width="{CARD_W}" height="{CARD_H}" fill="{PAPER}"/>{body}</svg>')


def image_card_svg(data: bytes, mime: str) -> str:
    """로고 파일(SVG·PNG) → 크림 종이 카드(가운데 940×460 안에 비율 유지). SVG-as-image 안의 data: URI 는 브라우저가 그린다."""
    b64 = base64.b64encode(data).decode("ascii")
    w, h = 940, 460
    x, y = (CARD_W - w) / 2, (CARD_H - h) / 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{CARD_W}" '
            f'height="{CARD_H}" viewBox="0 0 {CARD_W} {CARD_H}"><rect width="{CARD_W}" height="{CARD_H}" fill="{PAPER}"/>'
            f'<image x="{x:.0f}" y="{y:.0f}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid meet" '
            f'href="data:{mime};base64,{b64}" xlink:href="data:{mime};base64,{b64}"/></svg>')


def _path_of(svg: str) -> str:
    m = re.search(r'<path[^>]*\sd="([^"]+)"', svg)
    return m.group(1) if m else ""


class SimpleIcons:
    def __init__(self, cache_dir: Optional[Path] = None, log: LogFn = noop_log):
        self.cache_dir = cache_dir
        self.log = log
        self._index: Optional[dict[str, dict[str, Any]]] = None

    def _load(self) -> list[dict[str, Any]]:
        cache = self.cache_dir / f"simple-icons-{SI_VERSION}.json" if self.cache_dir else None
        if cache and cache.exists():
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except ValueError:
                pass
        r = net.request(SI_DATA, timeout=30, rounds=2)
        if not r.ok:
            raise RuntimeError(f"Simple Icons 목록 HTTP {r.status}")
        data = r.json()
        data = data.get("icons", []) if isinstance(data, dict) else data
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    def index(self) -> dict[str, dict[str, Any]]:
        if self._index is None:
            idx: dict[str, dict[str, Any]] = {}
            try:
                icons = self._load()
            except Exception as e:  # noqa: BLE001 - 목록을 못 받으면 위키데이터 로고로
                self.log(f"Simple Icons 목록을 받지 못함: {e}")
                icons = []
            for ic in icons:
                if not isinstance(ic, dict) or not ic.get("slug"):
                    continue
                al = ic.get("aliases") or {}
                names = [ic.get("title", ""), ic["slug"], *(al.get("aka") or []),
                         *((al.get("loc") or {}).values()), *[d.get("title", "") for d in (al.get("dup") or [])]]
                for n in names:
                    k = norm_brand(n)
                    if k and k not in idx:
                        idx[k] = ic
            self._index = idx
        return self._index

    def find(self, names: list[str]) -> Optional[dict[str, Any]]:
        idx = self.index()
        for n in names:
            k = norm_brand(n)
            if k and k in idx:
                return idx[k]
        return None

    def fetch(self, names: list[str], dst_dir: Path) -> Optional[ImageResult]:
        ic = self.find(names)
        if not ic:
            return None
        slug = ic["slug"]
        dst = dst_dir / f"logo_{re.sub(r'[^0-9a-z]+', '_', slug)}.svg"
        if not dst.exists():
            r = net.request(SI_ICON.format(slug=slug), timeout=30, rounds=2)
            d = _path_of(r.text) if r.ok else ""
            if not d:
                self.log(f"Simple Icons '{ic.get('title')}' 아이콘을 받지 못함(HTTP {r.status})")
                return None
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst.write_text(icon_card_svg(d, ic.get("hex", "")), encoding="utf-8")
        return ImageResult(dst, f"{ic.get('title')} 로고 · Simple Icons(CC0)", "CC0", ic.get("source", ""), "logo")


def logo_from_commons(meta: dict[str, Any], brand: str, dst_dir: Path, *, ua: str, log: LogFn = noop_log
                      ) -> Optional[ImageResult]:
    """커먼즈 로고 파일(meta: WikipediaImages.file_meta 모양 + orig_url) → 카드 SVG."""
    mime = (meta.get("mime") or "").lower()
    safe = re.sub(r"[^0-9A-Za-z가-힣]+", "_", brand).strip("_")[:40] or "brand"
    dst = dst_dir / f"logo_wd_{safe}.svg"
    if not dst.exists():
        url, kind = (meta.get("orig_url") or meta.get("url"), "image/svg+xml") if "svg" in mime else \
            (meta.get("url"), "image/png")
        if not url:
            return None
        r = net.request(url, headers={"User-Agent": ua}, timeout=60, rounds=2)
        if not r.ok or not r.content:
            log(f"로고 다운로드 실패({brand}): HTTP {r.status}")
            return None
        data = r.content
        if kind == "image/svg+xml" and len(data) > MAX_SVG and meta.get("url"):
            r = net.request(meta["url"], headers={"User-Agent": ua}, timeout=60, rounds=2)
            if not r.ok:
                return None
            data, kind = r.content, "image/png"
        if kind == "image/png" and data[:4] != b"\x89PNG":
            kind = "image/jpeg" if data[:2] == b"\xff\xd8" else kind
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst.write_text(image_card_svg(data, kind), encoding="utf-8")
    lic = meta.get("license") or "PD"
    return ImageResult(dst, f"{brand} 로고 · {lic} · Wikimedia Commons", lic, meta.get("page", ""), "logo")
