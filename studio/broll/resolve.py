"""고유명사 자료 이미지 해석 — 무엇인지(사람·브랜드·그 밖)를 먼저 알고 그에 맞는 이미지를 고른다.

  · 내 이미지 폴더에 있으면 그것(언제나 우선)
  · 브랜드·회사·서비스 → 로고(logos.py: Simple Icons → 위키데이터 P154). 문서 대표 이미지·커먼즈 검색으로 넘어가지
    않는다 — '핀터레스트' 문서의 대표 이미지는 창업자의 행사 사진이었다(틀린 사진보다 없는 게 낫다).
  · 사람 → 초상 후보 여러 장(위키데이터 P18 · 문서 대표 이미지 · 커먼즈 분류) 중 **가장 품위 있게 나온 사진**:
    🎞 비전(AI)이 고르고, AI 가 없으면 규칙 점수(얼굴 하나·정면·적당한 크기·선명함, 행사·인터뷰·단체 사진 감점).
  · 그 밖(작품·사물·장소·종교) → 예전처럼 문서 대표 이미지 → 커먼즈 검색.
무엇인지는 AI 자료 리서처가 문맥으로 준 kind(person|brand|…)와 위키데이터(P31 = 사람, P154 = 로고)를 함께 본다.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from .. import net
from ..util import LogFn, noop_log
from .images import ImageResult, Wikimedia, match_local
from .logos import SimpleIcons, logo_from_commons
from .wikipedia import WikipediaImages, _safe

# 파일 이름·설명에 이런 말이 있으면 행사·인터뷰·단체 사진(말하는 중·무대 위·여럿) — 초상으로 감점
EVENT_WORDS = re.compile(
    r"(?i)(?:^|[\s_(,.-])(at|speaking|speaks|speech|conference|keynote|panel|interview|talk|talks|event|festival|"
    r"summit|awards?|ceremony|press|meeting|forum|session|lecture|signing|visit|visiting|launch|presentation|"
    r"presenting|stage|sxsw|techcrunch|disrupt|wwdc|tedx?|with|and|eating|drinking|party|rally|crowd|group|team)"
    r"(?=$|[\s_),.-])")
PORTRAIT_WORDS = re.compile(r"(?i)(portrait|headshot|official|cropped|\bcrop\b|studio photo)")
SHEET_MAX = 6


@dataclass
class MediaPlan:
    query: str
    kind: str = ""                         # 해석한 종류: person | brand | other
    result: Optional[ImageResult] = None
    candidates: list[dict[str, Any]] = field(default_factory=list)   # person: 초상 후보(meta + thumb + score)
    info: Optional[dict[str, Any]] = None


def meta_score(m: dict[str, Any]) -> tuple[float, list[str]]:
    """파일 정보만으로: 큐레이션(위키데이터 대표 사진) 가산, 행사·인터뷰·단체 사진 감점, 초상 단어 가산, 세로 구도 가산."""
    s, why = 0.0, []
    if m.get("src") == "wikidata":
        s, why = s + 0.25, why + ["위키데이터 대표 사진"]
    elif m.get("src") == "lead":
        s, why = s + 0.12, why + ["문서 대표 이미지"]
    text = f"{Path(m.get('name', '')).stem} {m.get('description', '')}"
    if EVENT_WORDS.search(text):
        s, why = s - 0.3, why + ["행사·인터뷰·단체 사진"]
    if PORTRAIT_WORDS.search(text):
        s, why = s + 0.2, why + ["초상 사진"]
    w, h = m.get("width") or 0, m.get("height") or 0
    if h and 0.62 <= w / h <= 1.05:
        s += 0.1
    elif h and w / h > 1.6:
        s -= 0.1
    if min(w, h) >= 1200:
        s += 0.05
    return s, why


def image_score(img_bgr: np.ndarray, log: LogFn = noop_log) -> tuple[float, list[str]]:
    """사진으로: 얼굴이 하나(여럿이면 감점)·정면·적당한 크기(화면 높이의 16~55%)·가운데·선명·적당한 밝기."""
    import cv2

    from ..vision.face import _Detector, frame_quality
    h, w = img_bgr.shape[:2]
    det = _Detector(w, h, log)
    faces: list[tuple[float, float, float, float, float]] = []
    front = 0.6
    if det.yunet is not None:
        _, found = det.yunet.detect(img_bgr)
        for f in (found if found is not None else []):
            if float(f[-1]) >= 0.7 and float(f[3]) >= 0.05 * h:
                faces.append((float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])))
        big = det.detect_full(img_bgr)
        if big:
            front = big[5]
    elif det.haar is not None:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        for x, y, fw, fh in det.haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6,
                                                      minSize=(max(24, h // 14), max(24, h // 14))):
            faces.append((float(x), float(y), float(fw), float(fh), 0.8))
    s, why = 0.0, []
    if not faces:
        return -0.6, ["얼굴 없음"]
    if len(faces) >= 3:
        s, why = s - 0.4, why + [f"얼굴 {len(faces)}개(단체)"]
    elif len(faces) == 2:
        s, why = s - 0.2, why + ["얼굴 2개"]
    x, y, fw, fh, _ = max(faces, key=lambda r: r[2] * r[3])
    r = fh / h
    if 0.16 <= r <= 0.55:
        s, why = s + 0.3, why + ["초상 크기"]
    elif r < 0.08:
        s, why = s - 0.2, why + ["얼굴이 작음(행사·전신)"]
    s += 0.2 * front
    cx = (x + fw / 2) / w
    if 0.25 <= cx <= 0.75:
        s += 0.05
    sharp, bright, clip = frame_quality(img_bgr, (x, y, fw, fh))
    s += 0.1 * float(np.clip((sharp - 3.0) / 3.0, 0, 1))
    if 0.3 <= bright <= 0.78:
        s += 0.05
    if clip > 0.12:
        s -= 0.1
    return s, why


def _thumb_url(url: str, width: int = 500) -> str:
    """커먼즈 썸네일 주소의 너비만 바꾼다(…/1920px-Name.jpg → …/500px-Name.jpg). 원본 주소면 그대로."""
    return re.sub(r"/(\d+)px-([^/]+)$", lambda m: f"/{width}px-{m.group(2)}", url) if "/thumb/" in url else url


class MediaResolver:
    def __init__(self, *, local: list[Path], dst_dir: Path, work_dir: Path, wikimedia: Optional[Wikimedia],
                 wikipedia: Optional[WikipediaImages], logos: Optional[SimpleIcons], log: LogFn = noop_log):
        self.local = local
        self.dst_dir = dst_dir
        self.thumb_dir = work_dir / "portraits"
        self.wm = wikimedia
        self.wp = wikipedia
        self.logos = logos
        self.log = log

    # --- 1단계: 무엇인지 알고 후보 모으기 -------------------------------------------------
    def plan(self, query: str, kind: str = "", names: tuple[str, ...] = ()) -> MediaPlan:
        p = MediaPlan(query)
        hit = match_local(query, self.local) or next((h for n in names if n for h in [match_local(n, self.local)] if h),
                                                     None)
        if hit:
            self.dst_dir.mkdir(parents=True, exist_ok=True)
            dst = self.dst_dir / f"local_{re.sub(r'[^0-9A-Za-z가-힣._-]+', '_', hit.name)}"
            if not dst.exists():
                shutil.copyfile(hit, dst)
            p.kind, p.result = "local", ImageResult(dst, "", origin="local")
            return p
        kind = (kind or "").lower()
        info = None
        if self.wp is not None:
            try:
                info = self.wp.entity(query, tuple(n for n in names if n))
            except Exception as e:  # noqa: BLE001 - 위키데이터가 막히면 이름만으로
                self.log(f"위키데이터 조회 실패({query}): {e}")
        p.info = info
        human = bool(info and info.get("human"))
        if kind == "brand" and not human:
            p.kind = "brand"
        elif human or kind == "person":
            p.kind = "person"
        elif info and info.get("logos") and kind in ("", "name", "other", "object"):
            p.kind = "brand"           # 위키데이터에 로고가 있는 사람 아닌 것(회사·서비스·기관) — 규칙 경로 고유명사
        else:
            p.kind = "other"
        if p.kind == "brand":
            p.result = self._logo(query, names, info)
            if p.result is None:
                self.log(f"로고를 찾지 못함: '{query}' — 사진(임원·사옥)으로 대신하지 않고 뺍니다")
            return p
        if p.kind == "person" and info and self.wp is not None:
            try:
                p.candidates = self.wp.portrait_candidates(info)
            except Exception as e:  # noqa: BLE001
                self.log(f"인물 사진 후보 조회 실패({query}): {e}")
            if p.candidates:
                return p
        p.result = self._lead_or_search(query, names)
        return p

    def _logo(self, query: str, names: tuple[str, ...], info: Optional[dict[str, Any]]) -> Optional[ImageResult]:
        all_names = [*(n for n in names if n), query, *(((info or {}).get(k) or "") for k in ("label_en", "title"))]
        if self.logos is not None:
            try:
                res = self.logos.fetch(all_names, self.dst_dir)
            except Exception as e:  # noqa: BLE001
                self.log(f"Simple Icons 로고 실패({query}): {e}")
                res = None
            if res:
                self.log(f"로고(Simple Icons): '{query}' → {res.path.name}")
                return res
        if info and self.wp is not None and info.get("logos"):
            try:
                meta = self.wp.logo_meta(info)
                if meta:
                    res = logo_from_commons(meta, (info.get("label_en") or query), self.dst_dir, ua=self.wp.ua,
                                            log=self.log)
                    if res:
                        self.log(f"로고(위키데이터·커먼즈): '{query}' → {res.path.name} ({meta.get('license')})")
                        return res
            except Exception as e:  # noqa: BLE001
                self.log(f"위키데이터 로고 실패({query}): {e}")
        return None

    def _lead_or_search(self, query: str, names: tuple[str, ...] = ()) -> Optional[ImageResult]:
        """위키백과 대표 이미지(영어 위키는 원어/영어 이름부터) → 커먼즈 검색(한국어 → 원어 이름)."""
        alt = next((n for n in names if n and n.strip().lower() != query.strip().lower()), "")
        if self.wp is not None:
            self.dst_dir.mkdir(parents=True, exist_ok=True)
            res = self.wp.fetch(query, self.dst_dir, alt=alt) if alt else self.wp.fetch(query, self.dst_dir)
            if res:
                self.log(f"자료 사진(위키백과): '{query}' → {res.path.name} ({res.license})")
                return res
        if self.wm is not None:
            for q in [query] + ([alt] if alt else []):
                res = self.wm.fetch(q, self.dst_dir)
                if res:
                    self.log(f"자료 사진: '{q}' → {res.path.name} ({res.license})")
                    return res
        return None

    # --- 2단계: 인물 사진 고르기 ------------------------------------------------------
    def score_candidates(self, p: MediaPlan) -> None:
        """후보마다 500px 썸네일을 받아 규칙 점수(meta_score + image_score)를 매긴다. 받지 못한 후보는 뺀다."""
        import cv2
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        ua = self.wp.ua if self.wp else "ChoiStudio"
        keep = []
        for i, m in enumerate(p.candidates[:SHEET_MAX + 2]):
            dst = self.thumb_dir / f"{_safe(p.query, 30)}_{i}{Path(m['name']).suffix.lower() or '.jpg'}"
            try:
                net.download(_thumb_url(m["url"]), dst, timeout=40, headers={"User-Agent": ua}, rounds=2)
                img = cv2.imdecode(np.fromfile(str(dst), np.uint8), cv2.IMREAD_COLOR)
            except Exception as e:  # noqa: BLE001
                self.log(f"인물 사진 후보 썸네일 실패({m['name']}): {e}")
                continue
            if img is None:
                continue
            ms, mw = meta_score(m)
            try:
                isc, iw = image_score(img, self.log)
            except Exception as e:  # noqa: BLE001 - 얼굴 검출이 안 되면 파일 정보만
                isc, iw = 0.0, [f"얼굴 검사 실패: {e}"]
            keep.append({**m, "thumb": dst, "score": round(ms + isc, 3), "why": mw + iw})
            if len(keep) >= SHEET_MAX:
                break
        p.candidates = keep

    def best_by_rule(self, p: MediaPlan) -> int:
        return max(range(len(p.candidates)), key=lambda i: p.candidates[i]["score"]) if p.candidates else -1

    def finish(self, p: MediaPlan, idx: int) -> Optional[ImageResult]:
        """고른 후보(1920px)를 받아 ImageResult 로. idx < 0 이면 None."""
        if not (0 <= idx < len(p.candidates)):
            return None
        m = p.candidates[idx]
        ext = ".png" if "png" in (m.get("mime") or "") else ".jpg"
        dst = self.dst_dir / f"wp_{_safe(p.query)}_{_safe(Path(m['name']).stem, 24)}{ext}"
        try:
            self.dst_dir.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                net.download(m["url"], dst, timeout=60, headers={"User-Agent": self.wp.ua if self.wp else "ChoiStudio"})
        except Exception as e:  # noqa: BLE001
            self.log(f"인물 사진 다운로드 실패({p.query}): {e}")
            return None
        title = (p.info or {}).get("title") or p.query
        credit = f"{m.get('artist') or 'Unknown'} · {m.get('license')} · Wikimedia Commons ({title})"
        return ImageResult(dst, credit, m.get("license", ""), m.get("page", ""), "wikipedia")


def contact_rows(p: MediaPlan) -> list[tuple[str, Optional[bytes]]]:
    """비전 선택용 시트 칸: (라벨, 썸네일 JPEG/PNG 바이트)."""
    out = []
    for j, m in enumerate(p.candidates, start=1):
        try:
            data = Path(m["thumb"]).read_bytes()
        except OSError:
            data = None
        out.append((f"C{j}", data))
    return out


PickFn = Callable[[str, list[tuple[str, bytes, str]]], list[dict[str, Any]]]
