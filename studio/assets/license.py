"""라이선스 문자열 → 등급·권한·크레딧(docs/upgrade/저작권_위험등급_정책.md 3·6·7절, 03 문서 8절).

등급: own(화자 자료) · made(앱이 만든 것: 출처 카드·자료 카드) · A(CC0·PD·CC BY·공공누리 1) · A-sa(CC BY-SA) ·
stock(스톡 제공처 약관) · B(프레스 — 허용 목록만) · C(인용: 비자유 이미지·화면 캡처·논문 첫 쪽) · D(금지: NC·ND·출처 불명).
기계가 막는 것: D 는 언제나, 요청의 tier_max 를 넘는 것, C 는 설정 allow_quote 가 꺼져 있으면(기본 끔 — 작업지시서 WP7).
"""
from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

STOCK_ORIGINS = ("pixabay", "pexels", "unsplash", "coverr")
OWN_ORIGINS = ("user", "local", "own")
TIER_RANK = {"own": 0, "made": 0, "A": 1, "A-sa": 1, "stock": 1, "B": 2, "C": 3, "D": 9}
NC_ND = re.compile(r"(?i)(^|[\s\-_/(])(nc|nd)($|[\s\-_/).\d])|noncommercial|non-commercial|noderiv|no derivative")


@dataclass
class License:
    id: str = ""                     # "CC-BY-SA-4.0"
    name: str = ""                   # "CC BY-SA 4.0"
    url: str = ""
    tier: str = "D"
    commercial: bool = False
    derivatives: bool = False
    share_alike: bool = False
    attribution_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cc_url(kind: str, ver: str) -> str:
    if kind == "zero":
        return "https://creativecommons.org/publicdomain/zero/1.0/"
    return f"https://creativecommons.org/licenses/{kind}/{ver or '4.0'}/"


def classify(license: str, *, origin: str = "", nonfree: bool = False, restrictions: str = "") -> License:
    """라이선스 문자열(커먼즈 LicenseShortName·Openverse license·스톡 제공처)을 등급으로."""
    o = (origin or "").lower()
    raw = (license or "").strip()
    low = raw.lower()
    if o in OWN_ORIGINS:
        return License("own", "본인 자료", "", "own", True, True, False, False)
    if o == "made":
        return License("made", "자체 제작", "", "made", True, True, False, False)
    if o in STOCK_ORIGINS:
        return License(o, f"{o.capitalize()} License", "", "stock", True, True, False, False)
    if o == "screenshot":
        return License("quote", "화면 캡처(인용)", "", "C", True, False, False, True)
    if nonfree or any(k in low for k in ("fair use", "non-free", "비자유", "공정 이용")):
        return License("quote", "인용", "", "C", True, False, False, True)
    if not low or "all rights reserved" in low or NC_ND.search(low):
        return License(raw, raw, "", "D")
    restr = {r.strip().lower() for r in re.split(r"[|,;]", restrictions or "") if r.strip()}
    if restr - {"trademarked", "personality"}:
        return License(raw, raw, "", "D")
    m = re.search(r"(\d\.\d)", low)
    ver = m.group(1) if m else ""
    if "cc0" in low or "cc-zero" in low or "cc zero" in low:
        return License("CC0-1.0", "CC0", _cc_url("zero", ""), "A", True, True, False, False)
    if "public domain" in low or low in ("pd", "pdm") or low.startswith("pd-") or "퍼블릭 도메인" in low:
        return License("PD", "퍼블릭 도메인", "https://creativecommons.org/publicdomain/mark/1.0/", "A", True, True,
                       False, False)
    if "공공누리" in low or "kogl" in low:
        if re.search(r"(제?\s*1\s*유형|type\s*1)", low):
            return License("KOGL-1", "공공누리 제1유형", "https://www.kogl.or.kr/info/licenseType1.do", "A", True, True,
                           False, True)
        return License(raw, raw, "", "D")
    if re.search(r"by[\s\-_]?sa", low):
        return License(f"CC-BY-SA-{ver or '4.0'}", f"CC BY-SA {ver or '4.0'}".strip(), _cc_url("by-sa", ver), "A-sa",
                       True, True, True, True)
    if re.search(r"(^|[\s\-_])by($|[\s\-_\d])", low) or low.startswith("cc by") or low == "by":
        return License(f"CC-BY-{ver or '4.0'}", f"CC BY {ver or '4.0'}".strip(), _cc_url("by", ver), "A", True, True,
                       False, True)
    if "copyrighted free use" in low:
        return License("Copyrighted-free-use", "Copyrighted free use", "", "A", True, True, False, False)
    if any(k in low for k in ("gfdl", "free art", "attribution")):
        return License(raw, raw, "", "A-sa" if "gfdl" in low else "A", True, True, "gfdl" in low, True)
    return License(raw, raw, "", "D")


def allowed(lic: License, tier_max: str = "A", *, allow_quote: bool = False) -> bool:
    """쓸 수 있는가: D 는 언제나 아니다, C 는 allow_quote 가 켜져 있고 요청이 C 를 허용할 때만, B 는 쓰지 않는다
    (프레스 허용 목록은 아직 없다), 나머지(own·made·A·A-sa·stock)는 언제나."""
    if lic.tier == "D":
        return False
    if lic.tier == "C":
        return allow_quote and (tier_max or "A") == "C"
    if lic.tier == "B":
        return False
    return True


@dataclass
class AssetMeta:
    """자산마다 사이드카(03 문서 8절의 줄임판). 화면에는 credit_short, 업로드정보·자료 대장에는 credit_full."""
    path: str = ""
    origin: str = ""                 # user|commons|wikipedia|openverse|logo|scholar|screenshot|made|pixabay|…
    source_url: str = ""
    title: str = ""
    creator: str = ""
    year: str = ""
    institution: str = ""
    license: License = field(default_factory=License)
    credit_short: str = ""
    credit_full: str = ""
    shows: str = ""
    entity_qid: str = ""
    role: str = ""                   # subject|screen|logo|portrait|detail|context|document
    width: int = 0
    height: int = 0
    focus_box: list[float] = field(default_factory=list)
    score: int = -1                  # 비전 점수 0~3(채점하지 않았으면 -1)
    quote: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["license"] = self.license.to_dict()
        return d


def credits(meta: AssetMeta) -> tuple[str, str]:
    """(화면용, 설명란용) — 정책 6절 형식. 검색어·내부 식별자·라이선스 약칭만 덩그러니 두지 않는다."""
    lic, who = meta.license, (meta.creator or "작가 미상").strip()
    t = lic.tier
    if t in ("own", "made"):
        return "", ""
    if t == "stock":
        prov = lic.id.capitalize()
        short = f"Photo by {who} on Unsplash" if lic.id == "unsplash" else f"{who} / {prov}"
        return short, f"{short} — {meta.source_url}".rstrip(" —")
    if t == "C":
        if meta.origin == "screenshot":
            dom = re.sub(r"^https?://(www\.)?", "", meta.source_url).split("/")[0]
            return f"화면: {dom}", f"{meta.title or dom} 화면 캡처. 비평·교육 목적의 인용 — {meta.source_url}"
        return (f"{meta.title}, {who}" + (f", {meta.year}" if meta.year else "") + " · 인용",
                f"{meta.title}({meta.year}), {who}. 비평·교육 목적의 인용(저작권법 제28조). {meta.source_url}".strip())
    repo = {"commons": "Wikimedia Commons", "wikipedia": "Wikimedia Commons", "openverse": "Openverse",
            "logo": "Wikimedia Commons"}.get(meta.origin, meta.institution or meta.origin)
    if lic.tier == "A" and not lic.attribution_required:
        short = (f"{meta.title}, {who}" if meta.title and meta.origin not in ("commons", "wikipedia") else f"사진: {who}") \
            + f" · {lic.name} · {repo}"
    else:
        short = f"사진: {who} · {lic.name} · {repo}"
    full = (f"\"{meta.title}\" by {who} — {lic.name}" + (f" ({lic.url})" if lic.url else "")
            + (f" — {meta.source_url}" if meta.source_url else ""))
    return short, full


def finish(meta: AssetMeta) -> AssetMeta:
    """credit_short·credit_full 을 채운다(이미 있으면 그대로)."""
    s, f = credits(meta)
    meta.credit_short = meta.credit_short or s
    meta.credit_full = meta.credit_full or f
    return meta


LEDGER_FIELDS = ["자산", "등급", "라이선스", "시작", "초", "크기", "출처", "출처 URL", "대체", "인용 사유"]


def write_ledger(path: Path, rows: list[dict[str, Any]]) -> None:
    """부가자료/자료_대장.csv — 자산 · 등급 · 쓰인 시각 · 크기 · 출처 · 대체 여부(검토 시트와 함께 본다)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in LEDGER_FIELDS})


def tier_of(d: Optional[dict[str, Any]]) -> str:
    return str(((d or {}).get("license") or {}).get("tier") or (d or {}).get("tier") or "")
