"""자료 사진 확보: ① 사용자 이미지 폴더(파일명 매칭) → ② 위키미디어 커먼즈(자유 라이선스 + 출처 표기).

위키미디어 이미지는 CC0/퍼블릭 도메인/CC BY/CC BY-SA 만 사용하고, 화면에 ▣ 크레딧을 넣는다.
(CC BY-SA 는 2차 저작물에 같은 조건이 붙을 수 있으니 리포트에 표시해 둔다)
"""
from __future__ import annotations

import html
import json
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz

from .. import __version__, net
from ..text.align import norm
from ..util import LogFn, noop_log

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
API = "https://commons.wikimedia.org/w/api.php"
OK_LICENSES = ("cc0", "public domain", "pd", "cc by", "cc-by", "cc by-sa", "cc-by-sa")


@dataclass
class ImageResult:
    path: Path
    credit: str
    license: str = ""
    source_url: str = ""
    origin: str = "local"   # local | wikimedia

    def to_dict(self) -> dict:
        return {"path": str(self.path), "credit": self.credit, "license": self.license,
                "source_url": self.source_url, "origin": self.origin}


def list_local_images(folder: Optional[str | Path]) -> list[Path]:
    if not folder:
        return []
    p = Path(folder)
    if not p.is_dir():
        return []
    return sorted(f for f in p.rglob("*") if f.suffix.lower() in IMAGE_EXT)


def match_local(query: str, images: list[Path], threshold: int = 72) -> Optional[Path]:
    q = norm(query)
    if not q:
        return None
    best, best_score = None, 0.0
    for img in images:
        stem = norm(img.stem)
        if not stem:
            continue
        score = 100.0 if stem == q else max(fuzz.ratio(q, stem), fuzz.partial_ratio(q, stem) * 0.95)
        if score > best_score:
            best, best_score = img, score
    return best if best_score >= threshold else None


def _strip_html(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


class Wikimedia:
    def __init__(self, contact: str = "", log: LogFn = noop_log, cache_dir: Optional[Path] = None):
        import requests
        self.requests = requests
        self.session = requests.Session()
        contact = contact or "https://github.com/chiddesign/choi-explains-design"
        self.session.headers["User-Agent"] = f"ChoiStudio/{__version__} ({contact}) python-requests"
        self.log = log
        self.cache_dir = cache_dir
        self._last = 0.0

    def _get(self, params: dict) -> dict:
        wait = 0.6 - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        params = {"format": "json", "formatversion": "2", "maxlag": "5", **params}
        hdr = {"User-Agent": self.session.headers["User-Agent"]}   # 위키미디어 정책: 연락처가 든 UA
        r = net.request(API, params=params, headers=hdr, timeout=20)
        if r.status == 429:
            time.sleep(float(r.headers.get("Retry-After", "5")))
            r = net.request(API, params=params, headers=hdr, timeout=20)
        if not r.ok:
            raise RuntimeError(f"Wikimedia HTTP {r.status}")
        return r.json()

    def search(self, query: str, limit: int = 8) -> list[dict]:
        cache = None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache = self.cache_dir / f"wm_{re.sub(r'[^0-9A-Za-z가-힣]+', '_', query)[:60]}.json"
            if cache.exists():
                return json.loads(cache.read_text(encoding="utf-8"))
        data = self._get({
            "action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap fileres:>900",
            "gsrnamespace": "6", "gsrlimit": str(limit), "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata", "iiurlwidth": "1920",
            "iiextmetadatafilter": "LicenseShortName|UsageTerms|AttributionRequired|Artist|Credit|ObjectName|Restrictions",
        })
        if isinstance(data, dict) and data.get("error"):
            # maxlag 등 서버 오류는 HTTP 200 + {"error": …} 로 온다 — '결과 없음'으로 캐시하면 그 사진이 계속 빠진다
            self.log(f"Wikimedia 오류({(data['error'] or {}).get('code', '?')}) — '{query}' 는 이번엔 건너뜀")
            return []
        pages = (data.get("query") or {}).get("pages") or []
        pages.sort(key=lambda p: p.get("index", 99))
        out = []
        for p in pages:
            ii = (p.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata") or {}
            lic = _strip_html((meta.get("LicenseShortName") or {}).get("value", ""))
            out.append({
                "title": p.get("title", ""),
                "url": ii.get("thumburl") or ii.get("url"),
                "page": ii.get("descriptionurl", ""),
                "width": ii.get("width", 0),
                "height": ii.get("height", 0),
                "mime": ii.get("mime", ""),
                "license": lic,
                "artist": _strip_html((meta.get("Artist") or {}).get("value", ""))[:80],
                "restrictions": _strip_html((meta.get("Restrictions") or {}).get("value", "")),
            })
        if cache:
            cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out

    def fetch(self, query: str, dst_dir: Path) -> Optional[ImageResult]:
        try:
            results = self.search(query)
        except Exception as e:  # noqa: BLE001 - 네트워크 오류는 사진 없이 진행
            self.log(f"위키미디어 검색 실패({query}): {e}")
            return None
        for r in results:
            lic = r["license"].lower()
            non_commercial_or_nd = re.search(r"(^|[\s-])n[cd]($|[\s-])", lic)
            if not r["url"] or not any(k in lic for k in OK_LICENSES) or non_commercial_or_nd or r["restrictions"]:
                continue
            if r["width"] and r["height"] and r["width"] / max(1, r["height"]) < 0.55:
                continue  # 너무 세로로 긴 이미지 제외
            ext = ".png" if "png" in r["mime"] else ".jpg"
            name = re.sub(r"[^0-9A-Za-z가-힣]+", "_", query)[:50] + ext
            dst = dst_dir / name
            try:
                if not dst.exists():
                    net.download(r["url"], dst, timeout=40,
                                 headers={"User-Agent": self.session.headers["User-Agent"]})
            except Exception as e:  # noqa: BLE001
                self.log(f"이미지 다운로드 실패: {e}")
                continue
            artist = r["artist"] or "Unknown"
            credit = f"{artist} · {r['license']} · Wikimedia Commons"
            return ImageResult(dst, credit, r["license"], r["page"], "wikimedia")
        return None


def resolve_image(query: str, *, local: list[Path], dst_dir: Path, wikimedia: Optional[Wikimedia],
                  log: LogFn = noop_log) -> Optional[ImageResult]:
    hit = match_local(query, local)
    if hit:
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / f"local_{re.sub(r'[^0-9A-Za-z가-힣._-]+', '_', hit.name)}"
        if not dst.exists():
            shutil.copyfile(hit, dst)
        return ImageResult(dst, "", origin="local")
    if wikimedia:
        res = wikimedia.fetch(query, dst_dir)
        if res:
            log(f"자료 사진: '{query}' → {res.path.name} ({res.license})")
            return res
    log(f"자료 사진을 찾지 못함: '{query}' (images 폴더에 '{query}.jpg' 로 넣으면 사용됩니다)")
    return None
