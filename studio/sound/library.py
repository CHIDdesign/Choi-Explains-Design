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
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .. import net
from ..paths import ROOT
from ..util import LogFn, noop_log
from . import synth

ASSETS_DIR = ROOT / "assets"
MANIFEST = ASSETS_DIR / "sound_manifest.json"
SOUND_DIR = ASSETS_DIR / "sound"

# 사용할 수 있는 카테고리가 없을 때 대신 쓸 카테고리
# 비슷한 카테고리로 대신하지 않는다 — 맞는 소리가 없으면 내지 않는다(docs/upgrade/04c 2절 7번)
FALLBACK: dict[str, list[str]] = {}

MOODS_LONG = ("minimal", "calm", "ambient", "lofi", "inspiring")
# 숏폼도 롱폼과 같은 계열 — 업비트·인스파이어링(코퍼레이트) 기본은 뺐다(docs/upgrade/04 11절 5번). 숏폼은 롱폼 곡을 물려받는다
MOODS_SHORT = MOODS_LONG
MOOD_ALIAS = {"piano": ("calm", "minimal"), "calm": ("calm", "minimal"), "minimal": ("minimal", "calm"),
              "ambient": ("ambient", "minimal"), "lofi": ("lofi",), "inspiring": ("inspiring",),
              "upbeat": ("ambient", "minimal", "calm")}


# 문구 팔레트 → 실제 파일이 있는 카테고리(매니페스트: Pixabay·Mixkit 의 종이·팝·클릭·휙). 모션 그래픽에서 흔히 쓰는 짝
REAL_FOR = {"paper_slide": "paper", "paper_place": "paper", "print_place": "paper", "page_turn": "paper", "tape": "paper",
            "pencil_stroke": "paper", "pencil_tick": "click", "stamp": "pop", "air_soft": "whoosh_soft"}


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
    attribution: str = ""        # 라이선스가 요구하는 출처 문구(CC BY 등) — 업로드 정보에 그대로
    lead_silence: float = 0.0    # 곡 앞 무음(초) — 건너뛰고 시작
    family: str = ""             # 같은 녹음 세션(한 영상은 한 세션의 변주만 — 04c 2절 4번)
    license_class: str = ""      # 저작권 위험 등급(A~D·X, 매니페스트 license.class) — 게이트 D9


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ext(url: str) -> str:
    tail = url.split("?")[0].rsplit(".", 1)
    return "." + tail[-1].lower() if len(tail) == 2 and len(tail[-1]) <= 4 else ".mp3"


def _download(url: str, dst: Path, timeout: float = 25.0, rounds: int = 2) -> None:
    """studio.net: requests → urllib(브라우저 헤더·Referer) → curl 순으로, 실패 이유는 net.ERRORS 에.
    효과음·음악은 없어도 되는 것이라 두 바퀴까지만(스톡처럼 오래 기다리지 않는다)."""
    dst.unlink(missing_ok=True)
    net.download(url, dst, timeout=timeout, rounds=rounds)


RETRY_AFTER = 6 * 3600       # 받지 못한 주소는 6시간 동안 다시 시도하지 않는다(작업마다 오래 기다리지 않게)
HOST_GIVE_UP = 2             # 이번 작업에서 연달아 두 번 실패한 호스트는 건너뛴다(아예 연결이 안 되면 바로)


class SoundLibrary:
    def __init__(self, root: Path = SOUND_DIR, manifest: Path = MANIFEST, *, log: LogFn = noop_log):
        self.root = Path(root)
        self.manifest_path = Path(manifest)
        self.log = log
        self.sfx: list[Sound] = []
        self.bgm: list[Sound] = []
        self.models: dict[str, Path] = {}
        self.failed: list[str] = []

    # ------------------------------------------------------------------
    def manifest(self) -> dict:
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"sfx": [], "bgm": [], "models": []}

    def ensure(self, *, download: bool = True, kinds: Optional[tuple[str, ...]] = None,
               progress: Callable[[float], None] = lambda f: None, cancel=None) -> "SoundLibrary":
        """목록의 파일을 준비(없으면 내려받기) + 절차적 효과음 생성. 여러 번 불러도 빠르다.

        kinds: ("sfx", "bgm", "models") 중 일부만(예: 목소리 단계에서는 잡음 제거 모델만).
        인터넷이 막힌 PC 에서 작업마다 수십 분씩 기다리지 않도록: 연달아 실패한 호스트는 이번 작업에서 건너뛰고,
        받지 못한 주소는 6시간 동안 다시 시도하지 않는다(root/.failed.json). 취소하면 바로 멈춘다.
        """
        import time as _time
        m = self.manifest()
        fail_path = self.root / ".failed.json"
        try:
            failed_at: dict[str, float] = json.loads(fail_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            failed_at = {}
        now = _time.time()
        host_fail: dict[str, int] = {}
        want = set(kinds or ("sfx", "bgm", "models"))
        # 권리(04b 7절): 끈 항목(Content ID 등록·AI 생성·장르)과 상업 이용이 안 되는 항목(CC BY-NC 등)은 받지도 싣지도 않는다
        entries = [(k, e) for k in ("sfx", "bgm", "models") if k in want for e in m.get(k, [])
                   if e.get("enabled", True) is not False and e.get("commercial_ok", True) is not False]
        self.sfx, self.bgm, self.models = [], [], {}
        failed: list[str] = []
        got = 0
        for i, (kind, e) in enumerate(entries):
            if cancel is not None:
                cancel.check()
            sub = {"sfx": "sfx", "bgm": "bgm", "models": "models"}[kind]
            dst = self.root / sub / (e["id"] + _ext(e.get("url", "")))
            ok = dst.exists() and dst.stat().st_size > 0 and (not e.get("bytes") or dst.stat().st_size == e["bytes"])
            if not ok and download:
                for url in [e.get("url", "")] + list(e.get("mirrors", []) or []):
                    if not url:
                        continue
                    host = net.host_of(url)
                    if host_fail.get(host, 0) >= HOST_GIVE_UP or now - failed_at.get(url, 0) < RETRY_AFTER:
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
                        host_fail[host] = 0
                        failed_at.pop(url, None)
                        break
                    except Exception as ex:  # noqa: BLE001 - 네트워크 오류는 대체 소리로(이유는 진단에)
                        dst.unlink(missing_ok=True)
                        net._note(host, "download", f"{type(ex).__name__}: {ex}")
                        dead = "연결 실패" in str(ex)     # 모든 접속 방식이 연결조차 못 함(방화벽·오프라인)
                        host_fail[host] = HOST_GIVE_UP if dead else host_fail.get(host, 0) + 1
                        failed_at[url] = now
                if not ok:
                    failed.append(f"{kind}:{e['id']}")
            if ok:
                attr = str(((e.get("license") or {}).get("attribution")) or "")
                lic = str(((e.get("license") or {}).get("class")) or "")
                if kind == "sfx":
                    self.sfx.append(Sound(e["id"], e.get("category", ""), dst, float(e.get("peak_s") or 0.0),
                                          float(e.get("duration") or 0.0), e.get("source", ""), e.get("lufs"),
                                          title=e.get("title", ""), attribution=attr, family=str(e.get("family") or ""),
                                          license_class=lic))
                elif kind == "bgm":
                    self.bgm.append(Sound(e["id"], "bgm", dst, 0.0, float(e.get("duration") or 0.0),
                                          e.get("source", ""), e.get("lufs"), mood=e.get("mood", ""),
                                          title=e.get("title", ""),
                                          credit=attr or " · ".join(x for x in (e.get("title"), e.get("artist"),
                                                                                e.get("source")) if x),
                                          attribution=attr, lead_silence=float(e.get("lead_silence_s") or 0.0),
                                          license_class=lic))
                else:
                    self.models[e["id"]] = dst
            progress((i + 1) / max(1, len(entries)) * 0.9)
        # 절차적 기본 세트(항상)
        if "sfx" in want:
            for d in synth.build(self.root / "synth"):
                self.sfx.append(Sound(d["id"], d["category"], Path(d["path"]), d["peak_s"], d["duration"], "synth",
                                      family="synth"))
        progress(1.0)
        if got:
            self.log(f"🔊 효과음·음악 {got}개 새로 받음")
        if failed:
            n_bgm = sum(1 for f in failed if f.startswith("bgm:"))
            self.log(f"⚠ 효과음·음악 {len(failed)}개를 받지 못했습니다(배경음악 {n_bgm}곡 포함) — "
                     f"받은 것: 효과음 {sum(1 for s in self.sfx if s.source != 'synth')}개 · 배경음악 {len(self.bgm)}곡")
            for line in net.summary()[:8]:
                self.log("   " + line)
        self.failed = failed
        if download:
            try:
                fail_path.parent.mkdir(parents=True, exist_ok=True)
                fail_path.write_text(json.dumps({u: t for u, t in failed_at.items() if now - t < RETRY_AFTER}),
                                     encoding="utf-8")
            except OSError:
                pass
        return self

    # ------------------------------------------------------------------
    def pick(self, category: str, *, seed: int = 0, prefer_real: bool = True) -> Optional[Sound]:
        """그 카테고리에서 하나(없으면 None — 비슷한 소리로 메우지 않는다). 내려받은 실제 효과음을 절차적보다 먼저,
        같은 세션(family)의 변주 안에서 돌리고 직전과 같은 파일은 피한다(04c 3절).
        문구 팔레트(paper_slide·page_turn·stamp…)는 실제 파일이 없어 절차적 소리뿐이었고 믹스가 절차적 소리를 거절해
        효과음이 하나도 들리지 않았다 — 실제 파일이 있는 가장 가까운 카테고리(`REAL_FOR`)로 받는다."""
        tiers = ([lambda s: s.source != "synth"] if prefer_real else []) + [lambda s: True]
        cats = [category] + ([REAL_FOR[category]] if category in REAL_FOR else [])
        for ok in tiers:
            pool = [s for s in self.sfx if s.category in cats and ok(s)]
            if any(s.category == category for s in pool):
                pool = [s for s in pool if s.category == category]
            if not pool:
                continue
            fam = getattr(self, "_family", {}).get(category)
            same = [s for s in pool if (getattr(s, "family", "") or "") == fam] if fam else []
            pool = same or pool
            last = getattr(self, "_last", {}).get(category)
            choice = pool[seed % len(pool)]
            if len(pool) > 1 and choice.path == last:
                choice = pool[(seed + 1) % len(pool)]
            self._family = {**getattr(self, "_family", {}), category: getattr(choice, "family", "") or ""}
            self._last = {**getattr(self, "_last", {}), category: choice.path}
            return choice
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
        return None        # 맞는 무드가 없으면 음악 없이 — 아무 곡이나 고르지 않는다(04 11절)

    def playlist(self, first: Sound, n: int, *, seed: int = 0) -> list[Sound]:
        """챕터마다 곡을 바꿀 때 쓸 목록: 첫 곡과 같은 무드(없으면 가까운 무드) 곡을 겹치지 않게."""
        family = MOOD_ALIAS.get(first.mood, (first.mood,))
        pool = [b for b in self.bgm if b.mood in family and b.id != first.id]
        random.Random(seed).shuffle(pool)
        out = [first] + pool
        base = len(out)          # 모자라면 목록을 처음부터 되풀이(예전엔 늘 첫 곡만 반복)
        while len(out) < n and self.bgm:
            out.append(out[len(out) % base])
        return out[:max(1, n)]

    def rnnoise_model(self) -> Optional[Path]:
        for k in ("rnnoise_std", "rnnoise_bd", "rnnoise_cb", "rnnoise_mp", "rnnoise_sh"):
            if k in self.models:
                return self.models[k]
        return None
