"""🛫 렌더 전 자산 확인 — props 가 가리키는 그림·영상·소리 파일이 렌더 폴더(publicDir)에 정말 있는지 렌더 직전에 본다.

Remotion 은 <Img>·<OffthreadVideo> 하나가 404 를 받으면 렌더 전체를 멈춘다(2026-10-04: 모션 장면 기기 화면의
'pixabay:photo:design portfolio layout' 이 파일로 바뀌지 않은 채 넘어가 검수 스틸과 본 렌더가 모두 실패했다). 앞 단계가 무엇을
놓치든 여기서 한 번 더 본다 — 없는(또는 깨진) 파일을 가리키는 부품은 그 부품만 빼고, 그 그림 없이는 안 되는 그래픽(사진·스톡)은
그래픽째 빼고, 이유를 로그에 남긴다. 화자 영상(clips)이 없으면 렌더할 수 없으므로 멈춘다(`fatal`).

`studio/render/remotion.py run_render` 가 모든 렌더(검수 스틸·롱폼·숏폼·썸네일) 앞에서 부른다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Optional

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
IMG_TAG_RE = re.compile(r"""<img\b[^>]*?\bsrc\s*=\s*(["'])(.*?)\1[^>]*>""", re.I | re.S)


class MediaCheck:
    """publicDir 기준 상대 경로가 렌더러가 읽을 수 있는 파일인지(같은 경로는 한 번만 잰다).

    linked = {publicDir 안 자리: 실제 원본} — render.mjs 가 렌더 직전에 링크하는 프록시(media/proxy*.mp4)."""

    def __init__(self, public: Path, linked: Optional[dict[str, Path]] = None):
        self.public = Path(public)
        self.linked = {_norm(k): Path(v) for k, v in (linked or {}).items()}
        self._seen: dict[str, bool] = {}

    def ok(self, rel: Any) -> bool:
        if not isinstance(rel, str) or not rel.strip():
            return False
        r = _norm(rel)
        if r not in self._seen:
            self._seen[r] = self._check(r)
        return self._seen[r]

    def _check(self, r: str) -> bool:
        # 'pixabay:…'·'http://…'·'C:\…' 처럼 해석되지 않은 참조, 폴더 밖으로 나가는 경로
        if ":" in r.split("/")[0] or ".." in r.split("/"):
            return False
        p = self.linked.get(r) or (self.public / r)
        try:
            if not p.is_file() or p.stat().st_size == 0:
                return False
        except OSError:
            return False
        ext = p.suffix.lower()
        if ext in IMAGE_EXT:
            try:
                from PIL import Image
                with Image.open(p) as im:      # 머리만 읽는다 — 오류 페이지(HTML)를 .jpg 로 받은 것 등
                    w, h = im.size
                return w > 0 and h > 0
            except Exception:  # noqa: BLE001
                return False
        if ext == ".svg":
            try:
                head = p.read_bytes()[:2048].lower()
            except OSError:
                return False
            return b"<svg" in head or head.lstrip().startswith(b"<?xml")
        return True


def _norm(rel: str) -> str:
    return rel.strip().replace("\\", "/").lstrip("/")


def _short(v: Any, n: int = 48) -> str:
    s = str(v or "(빈 값)")
    return s if len(s) <= n else s[: n - 1] + "…"


def fix_graphic(g: dict[str, Any], chk: MediaCheck, notes: list[str]) -> bool:
    """그래픽 하나를 고친다. 그래픽째 빼야 하면 False."""
    t = g.get("template")
    d = g.get("data")
    if not isinstance(d, dict):
        return True
    at = f"{float(g.get('start', 0) or 0):.1f}초"
    if t == "photo":
        if not chk.ok(d.get("image")):
            notes.append(f"사진 그래픽({at}) — 파일 없음 {_short(d.get('image'))}")
            return False
    elif d.get("image") and not chk.ok(d["image"]):
        d["image"] = ""                 # 사진 템플릿만 읽는 칸 — 스톡은 여기에 검색어가 남아 있다(화면에 안 나감)
    if t == "broll" and not chk.ok(d.get("src")):
        notes.append(f"스톡 그래픽({at}) — 파일 없음 {_short(d.get('src'))}")
        return False
    if d.get("cut") and not chk.ok(d["cut"]):
        d.pop("cut")                    # 오린 PNG 가 없으면 원본 사진으로 그린다
        notes.append(f"오린 사진({at}) — 원본 사진으로")
    assets = d.get("assets")
    if isinstance(assets, list) and assets:
        keep = []
        for a in assets:
            if not isinstance(a, dict) or not chk.ok(a.get("src")):
                notes.append(f"자료 그림({at}) — 파일 없음 {_short((a or {}).get('src'))}")
                continue
            if a.get("cut") and not chk.ok(a["cut"]):
                a.pop("cut")
            keep.append(a)
        d["assets"] = keep
        if not keep and not (d.get("archive") or d.get("title")):
            return False                # 그림도 글도 없는 자료 카드는 빈 판이다
    spec = d.get("spec")
    if isinstance(spec, dict) and isinstance(spec.get("elements"), list):
        els = []
        for el in spec["elements"]:
            if isinstance(el, dict) and "src" in el and not chk.ok(el.get("src")):
                what = {"image": "그림", "device": "기기 화면"}.get(str(el.get("type")), str(el.get("type")))
                notes.append(f"모션 장면({at}) {what} — 파일 없음 {_short(el.get('src'))}")
                if el.get("type") == "image":
                    continue            # 그림 부품은 장면에서 뺀다
                el.pop("src")           # 기기 등은 그림 없이(행·제목으로) 그린다
            els.append(el)
        spec["elements"] = els
    card = d.get("card")
    if isinstance(card, dict) and isinstance(card.get("html"), str) and "<img" in card["html"].lower():
        def _img(m: re.Match) -> str:
            if chk.ok(m.group(2)):
                return m.group(0)
            notes.append(f"카드({at}) 그림 — 파일 없음 {_short(m.group(2))}")
            return ""
        card["html"] = IMG_TAG_RE.sub(_img, card["html"])
    return True


def fix_props(props: dict[str, Any], chk: MediaCheck) -> tuple[list[str], list[str]]:
    """props 를 제자리에서 고친다. 반환 (고친 것, 렌더할 수 없는 이유)."""
    notes: list[str] = []
    fatal: list[str] = []
    bad_clips = sorted({str(c.get("src")) for c in props.get("clips") or []
                        if isinstance(c, dict) and not chk.ok(c.get("src"))})
    fatal += [f"화자 영상 {s} 이 없습니다(편집본 만들기 단계 결과)" for s in bad_clips]
    if "image" in props and not props.get("clips") and not chk.ok(props.get("image")):
        fatal.append(f"썸네일 그림 {_short(props.get('image'))} 이 없습니다")
    for key, label in (("voice", "목소리"), ("bgm", "배경음악")):
        tr = props.get(key)
        if isinstance(tr, dict) and not chk.ok(tr.get("src")):
            notes.append(f"{label} — 파일 없음 {_short(tr.get('src'))}")
            props[key] = None
    if isinstance(props.get("sfx"), list):
        keep = [s for s in props["sfx"] if isinstance(s, dict) and chk.ok(s.get("src"))]
        if len(keep) < len(props["sfx"]):
            notes.append(f"효과음 {len(props['sfx']) - len(keep)}개 — 파일 없음")
            props["sfx"] = keep
    if isinstance(props.get("grainFrames"), list):
        props["grainFrames"] = [f for f in props["grainFrames"] if chk.ok(f)]
    if props.get("paperTexture") and not chk.ok(props["paperTexture"]):
        props["paperTexture"] = ""
    if isinstance(props.get("graphics"), list):
        props["graphics"] = [g for g in props["graphics"] if not isinstance(g, dict) or fix_graphic(g, chk, notes)]
    return notes, fatal


def summary(notes: Iterable[str], limit: int = 6) -> str:
    notes = list(notes)
    more = f" 외 {len(notes) - limit}곳" if len(notes) > limit else ""
    return " · ".join(notes[:limit]) + more
