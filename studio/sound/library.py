"""사운드 라이브러리 — 효과음·배경음악을 준비하고 카테고리/무드로 골라 준다.

- 목록: assets/sound_manifest.json (저장소에 포함, 주소·해시·피크 위치만)
- 파일: assets/sound/ (처음 실행 때 내려받음, 저장소에는 넣지 않는다 — 개인 사용 전제)
- 내려받기에 실패한 카테고리는 studio/sound/synth.py 의 절차적 효과음으로 채운다(항상 동작).
- 배경음악은 내려받은 곡이 없으면 음악 없이(효과음만) 진행한다.
"""
from __future__ import annotations

import hashlib
import json
import random
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..paths import ROOT
from ..util import LogFn, noop_log
from . import synth

ASSETS_DIR = ROOT / "assets"
MANIFEST = ASSETS_DIR / "sound_manifest.json"
SOUND_DIR = ASSETS_DIR / "sound"

# 사용할 수 있는 카테고리가 없을 때 대신 쓸 카테고리
FALLBACK = {
    "whoosh_fast": ["whoosh_soft", "swoosh_short"], "whoosh_soft": ["whoosh_fast", "swoosh_short"],
    "whoosh_deep": ["whoosh_soft"], "swoosh_short": ["whoosh_fast"], "swipe": ["swoosh_short"],
    "tick": ["click"], "click": ["tick", "pop"], "pop": ["bubble", "click"], "bubble": ["pop"],
    "impact": ["sub_drop"], "sub_drop": ["impact"], "chime": ["ding"], "ding": ["chime", "bell_soft"],
    "bell_soft": ["ding"], "reverse_cymbal": ["reverse"], "reverse": ["reverse_cymbal", "riser"],
    "page_flip": ["paper"], "paper": ["page_flip"], "notification": ["ding", "pop"],
}

MOODS_LONG = ("minimal", "calm", "ambient", "lofi", "inspiring")
MOODS_SHORT = ("upbeat", "inspiring", "lofi", "minimal")
MOOD_ALIAS = {"piano": ("calm", "minimal"), "calm": ("calm", "minimal"), "minimal": ("minimal", "calm"),
              "ambient": ("ambient", "minimal"), "lofi": ("lofi",), "inspiring": ("inspiring",),
              "upbeat": ("upbeat", "inspiring")}


@dataclass
class Sound:
    id: str
    category: str
    path: Path
    peak: float = 0.0
    duration: float = 0.0
    source: str = ""
    lufs: Optional[float] = None
    mood: str = ""
    title: str = ""
    credit: str = ""


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ext(url: str) -> str:
    tail = url.split("?")[0].rsplit(".", 1)
    return "." + tail[-1].lower() if len(tail) == 2 and len(tail[-1]) <= 4 else ".mp3"


def _download(url: str, dst: Path, timeout: float = 40.0) -> None:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/126.0 Safari/537.36", "Accept": "*/*", "Referer": "https://pixabay.com/"})
    tmp = dst.with_suffix(dst.suffix + ".part")
    with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
        while True:
            b = r.read(1 << 16)
            if not b:
                break
            f.write(b)
    tmp.replace(dst)


class SoundLibrary:
    def __init__(self, root: Path = SOUND_DIR, manifest: Path = MANIFEST, *, log: LogFn = noop_log):
        self.root = Path(root)
        self.manifest_path = Path(manifest)
        self.log = log
        self.sfx: list[Sound] = []
        self.bgm: list[Sound] = []
        self.models: dict[str, Path] = {}

    # ------------------------------------------------------------------
    def manifest(self) -> dict:
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"sfx": [], "bgm": [], "models": []}

    def ensure(self, *, download: bool = True, kinds: Optional[tuple[str, ...]] = None,
               progress: Callable[[float], None] = lambda f: None) -> "SoundLibrary":
        """목록의 파일을 준비(없으면 내려받기) + 절차적 효과음 생성. 여러 번 불러도 빠르다.

        kinds: ("sfx", "bgm", "models") 중 일부만(예: 목소리 단계에서는 잡음 제거 모델만).
        """
        m = self.manifest()
        want = set(kinds or ("sfx", "bgm", "models"))
        entries = [(k, e) for k in ("sfx", "bgm", "models") if k in want for e in m.get(k, [])]
        self.sfx, self.bgm, self.models = [], [], {}
        failed = 0
        got = 0
        for i, (kind, e) in enumerate(entries):
            sub = {"sfx": "sfx", "bgm": "bgm", "models": "models"}[kind]
            dst = self.root / sub / (e["id"] + _ext(e.get("url", "")))
            ok = dst.exists() and dst.stat().st_size > 0 and (not e.get("bytes") or dst.stat().st_size == e["bytes"])
            if not ok and download:
                for url in [e.get("url", "")] + list(e.get("mirrors", []) or []):
                    if not url:
                        continue
                    try:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        _download(url, dst)
                        if e.get("sha256") and _sha256(dst) != e["sha256"]:
                            self.log(f"(해시 불일치, 다른 주소 시도) {e['id']}")
                            dst.unlink(missing_ok=True)
                            continue
                        ok = True
                        got += 1
                        break
                    except Exception:  # noqa: BLE001 - 네트워크 오류는 대체 소리로
                        dst.unlink(missing_ok=True)
                if not ok:
                    failed += 1
            if ok:
                if kind == "sfx":
                    self.sfx.append(Sound(e["id"], e.get("category", ""), dst, float(e.get("peak_s") or 0.0),
                                          float(e.get("duration") or 0.0), e.get("source", ""), e.get("lufs"),
                                          title=e.get("title", "")))
                elif kind == "bgm":
                    self.bgm.append(Sound(e["id"], "bgm", dst, 0.0, float(e.get("duration") or 0.0),
                                          e.get("source", ""), e.get("lufs"), mood=e.get("mood", ""),
                                          title=e.get("title", ""),
                                          credit=" · ".join(x for x in (e.get("title"), e.get("artist"),
                                                                        e.get("source")) if x)))
                else:
                    self.models[e["id"]] = dst
            progress((i + 1) / max(1, len(entries)) * 0.9)
        # 절차적 기본 세트(항상)
        if "sfx" in want:
            for d in synth.build(self.root / "synth"):
                self.sfx.append(Sound(d["id"], d["category"], Path(d["path"]), d["peak_s"], d["duration"], "synth"))
        progress(1.0)
        if got:
            self.log(f"🔊 효과음·음악 {got}개 새로 받음")
        if failed:
            self.log(f"🔊 {failed}개는 받지 못해 기본 효과음으로 대체")
        return self

    # ------------------------------------------------------------------
    def pick(self, category: str, *, seed: int = 0, prefer_real: bool = True) -> Optional[Sound]:
        """카테고리(없으면 비슷한 카테고리)에서 하나. 내려받은 실제 효과음을 절차적 효과음보다 먼저."""
        cats = [category] + FALLBACK.get(category, [])
        tiers = ([lambda s: s.source != "synth"] if prefer_real else []) + [lambda s: True]
        for ok in tiers:
            for c in cats:
                pool = [s for s in self.sfx if s.category == c and ok(s)]
                if pool:
                    return pool[seed % len(pool)]
        return None

    def pick_bgm(self, moods: tuple[str, ...], *, min_duration: float = 60.0, seed: int = 0,
                 wanted: str = "") -> Optional[Sound]:
        if not self.bgm:
            return None
        order: list[str] = []
        for m in ([wanted] if wanted else []) + list(moods):
            for alias in MOOD_ALIAS.get(m, (m,)):
                if alias not in order:
                    order.append(alias)
        for mood in order:
            pool = [b for b in self.bgm if b.mood == mood and (b.duration or 999) >= min_duration]
            if pool:
                return random.Random(seed).choice(pool)
        return random.Random(seed).choice(self.bgm)

    def playlist(self, first: Sound, n: int, *, seed: int = 0) -> list[Sound]:
        """챕터마다 곡을 바꿀 때 쓸 목록: 첫 곡과 같은 무드(없으면 가까운 무드) 곡을 겹치지 않게."""
        family = MOOD_ALIAS.get(first.mood, (first.mood,))
        pool = [b for b in self.bgm if b.mood in family and b.id != first.id]
        random.Random(seed).shuffle(pool)
        out = [first] + pool
        while len(out) < n and self.bgm:
            out.append(out[len(out) % max(1, len(out))])
        return out[:max(1, n)]

    def rnnoise_model(self) -> Optional[Path]:
        for k in ("rnnoise_std", "rnnoise_bd", "rnnoise_cb", "rnnoise_mp", "rnnoise_sh"):
            if k in self.models:
                return self.models[k]
        return None
