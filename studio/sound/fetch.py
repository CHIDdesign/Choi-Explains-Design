"""🔍 효과음 자동 조달 — 작업마다 총괄 감독의 위트 소리(sound_gags)와 파일이 모자란 카테고리를 프로그램이 직접 찾아 받는다.

순서: user/sfx(이름이 맞을 때) → 기존 라이브러리 → Mixkit(사이트 전체 무료 라이선스) + Openverse(CC0·CC BY, 8초 미만) → 없으면 로그 한 줄 남기고 뺀다.
Claude 는 소리를 듣지 못하므로 제목·태그 + 측정값(길이·RMS·스펙트럼 중심·어택)을 글로 읽고 고른다. AI 가 없으면 규칙 점수.
Openverse 의 라이선스는 원문보다 늦을 수 있어(2026-11-10 cc0 로 나온 곡이 원문은 CC BY-NC) 받기 전에 원문 페이지와 대조한다.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from .. import net
from ..assets.license import family
from ..edit.grammar import AUTO_SFX_FOR_TEMPLATE, gag_category
from ..media.mix import decode
from ..paths import USER_DIR
from ..stock.google import license_from_html
from ..stock.openverse import AUDIO_API, license_label
from ..util import CancelToken, Cancelled, LogFn, noop_log, text_hash
from .library import RETRY_AFTER, Sound, SoundLibrary, _ext, _is_audio
from .listen import SFX_TOP, Ears, earshot_rank
from .tracks import FAMILY, sidecar

CACHE = USER_DIR / "cache" / "sfx_auto"
USER_SFX = USER_DIR / "sfx"
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
MAX_SEC = 8.0
MAX_BYTES = 6 << 20
CAP_BYTES = 40 << 20            # 캐시 상한(FLAC 8초 하나가 1MB 안쪽) — 오래 안 쓴 것부터 지운다
MIN_LOCAL = 3                   # 카테고리에 실제 파일이 이보다 적으면 찾아 채운다
KEEP_CANDS = 3                  # 요청마다 재서 고르는 후보 수
SEARCH_GAP = 3.2                # Openverse 익명 한도 분당 20회
MAX_PAGES = 12                  # 한 작업에서 새로 확인하는 원문 페이지 수 — 확인한 것은 캐시에 남아 다음 작업은 확인 없이 쓴다
SEARCH_TTL = 30 * 86400
DEADLINE = 180.0                # 이번 작업에서 찾는 데 쓰는 시간 상한
MIXKIT = "https://mixkit.co/free-sound-effects/discover/"
MIXKIT_LICENSE = "mixkit"       # Mixkit Sound Effects Free License — YouTube·상업 사용 가능, 출처 표기 불필요(2026-11-10 mixkit.co/license 원문). 낱개 재배포·Content ID 등록은 금지
MIXKIT_GAP = 1.0
LICENSE_CLASS = {"cc0": "A", "by": "C", MIXKIT_LICENSE: "A"}     # 효과음은 CC0·CC BY·Mixkit 만(게이트 D9 등급, 매니페스트의 Mixkit 과 같은 A)
USABLE = ("A", "A-sa", "B", "C")
STOP = {"a", "an", "the", "of", "on", "in", "with", "and", "no", "sound", "effect", "effects", "sfx", "wav", "mp3"}
JUNK = {"song", "music", "melody", "vocal", "voice", "speech", "talking", "scream", "loop", "remix", "beat"}
CATEGORY_QUERIES = {
    "whoosh_soft": ["soft whoosh", "air whoosh"], "whoosh_fast": ["fast whoosh"], "whoosh_deep": ["deep whoosh"],
    "swoosh_short": ["short swoosh", "swish"], "swipe": ["swipe", "fast swish"], "pop": ["pop", "bubble pop"],
    "click": ["mouse click", "button click"], "typing": ["keyboard typing", "typewriter"],
    "camera_shutter": ["camera shutter"], "paper": ["paper rustle", "paper flip"],
    "paper_place": ["paper drop", "paper table"], "paper_slide": ["paper slide", "paper sliding"],
    "paper_tear": ["paper tear", "paper rip"], "page_turn": ["page turn", "book page"], "pencil_tick": ["pencil tap"],
    "pencil_stroke": ["pencil writing", "pencil scribble"], "stamp": ["rubber stamp"], "tape": ["tape peel"],
    "ding": ["ding bell"], "bell_soft": ["soft bell", "desk bell"], "notification": ["notification chime"],
}
PICK_RULES = ("효과음 후보 고르기. 너는 소리를 들을 수 없다 — 위 목록의 제목·태그와 측정값만 읽고 판단한다. 요청마다 그 순간에 가장 맞는 후보 "
              "하나를 고른다(request = 요청 번호, candidate = 후보 번호, 1부터). 제목·태그의 사물·동작이 요청과 다르면 고르지 않는다. "
              "어택이 30ms 이하면 타격·클릭, 길면 바람·스윕이다. 밝기(스펙트럼 중심)가 낮으면 둔탁하고 높으면 날카롭다. "
              "같은 소리가 여러 번 되풀이되는 녹음('x times'), 말소리·음악·비명은 피한다. 맞는 후보가 없으면 candidate -1. reason 은 한 줄.")


@dataclass
class Need:
    category: str
    queries: list[str]
    idea: str = ""
    kind: str = ""      # 위트 소리 유형(thud·mickey…) — 카테고리 요청은 ""
    count: int = 1


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in STOP}


def _hit(word: str, have: set[str]) -> bool:
    stem = word[:max(3, len(word) - 2)]         # sliding·slides·slide 는 같은 낱말로
    return any(t.startswith(stem) for t in have)


def _overlap(query: str, have: set[str]) -> float:
    ws = _words(query)
    return sum(_hit(w, have) for w in ws) / len(ws) if ws else 0.0


def _matches(need: Need, have: set[str]) -> bool:
    """검색 1위를 그냥 쓰지 않는다 — 어떤 검색어의 낱말이 제목·태그에 모두 있어야 한다."""
    return any(_overlap(q, have) >= 1.0 for q in [*need.queries, need.category.replace("_", " ")])


def _cand_words(c: dict[str, Any]) -> set[str]:
    return _words(c["title"] + " " + " ".join(c["tags"]))


def _score(need: Need, c: dict[str, Any]) -> float:
    """AI 가 없을 때의 규칙 점수: 글자 일치 → CC0 → 짧음 → 타격음이면 빠른 어택·낮은 밝기."""
    s = 3.0 * max(_overlap(q, _cand_words(c)) for q in need.queries) + 0.3 * (c["license"] == "cc0") + 1.5 * c.get("heard", 0)
    if "duration" in c:
        s -= c["duration"] / MAX_SEC
        if need.kind in ("thud", "mickey"):
            s -= min(1.0, c["attack_ms"] / 100.0) + (min(1.0, c["centroid_hz"] / 4000.0) if need.kind == "thud" else 0.0)
    return s


def measure(x: np.ndarray, sr: int) -> Optional[dict[str, float]]:
    """모노 신호 → 앞 무음·실제 길이·RMS·스펙트럼 중심·어택(5ms 포락선이 최대의 90%에 닿는 시각). 소리가 없으면 None."""
    a = np.abs(x)
    peak = float(a.max()) if len(a) else 0.0
    if peak < 1e-4:
        return None
    on = np.nonzero(a > peak * 0.01)[0]                 # 최대보다 −40 dB(말 아래에서 들리지 않는 앞뒤)
    y = x[on[0]: on[-1] + 1]
    spec = np.abs(np.fft.rfft(y))
    hop = max(1, int(0.005 * sr))
    n = len(y) // hop
    env = np.sqrt((y[:n * hop].reshape(n, hop) ** 2).mean(axis=1)) if n else np.array([peak])
    return {"lead": round(float(on[0]) / sr, 3), "duration": round(len(y) / sr, 3),
            "rms_db": round(float(20 * np.log10(np.sqrt((y ** 2).mean()) + 1e-9)), 1),
            "centroid_hz": round(float((np.fft.rfftfreq(len(y), 1 / sr) * spec).sum() / (spec.sum() + 1e-9))),
            "attack_ms": round(float(np.argmax(env >= env.max() * 0.9)) * 5.0, 1), "clipped": round(float((a >= 0.999).mean()), 4)}


def _reject(m: Optional[dict[str, float]]) -> str:
    if m is None:
        return "소리 없음"
    if m["duration"] >= MAX_SEC:
        return "너무 김"
    if m["duration"] < 0.04 or m["rms_db"] < -48.0:
        return "쓸 수 없음"
    return "찌그러짐" if m["clipped"] > 0.02 else ""


def parse_mixkit(text: str, page: str, ban: set[str]) -> list[dict[str, Any]]:
    """Mixkit 목록 페이지 → 후보들. 미리 듣기 mp3 가 곧 받을 파일이다."""
    out = []
    for block in text.split('class="item-grid__item"')[1:]:
        url = re.search(r'preview-url-value="(https://assets\.mixkit\.co/[^"]+\.mp3)"', block)
        item = re.search(r'item-id-value="(\d+)"', block)
        name = re.search(r'item-grid-card__title">\s*([^<]+?)\s*<', block)
        length = re.search(r'data-test-id="duration">\s*(\d+):(\d+)', block)
        if not (url and item and name and length) or int(length[1]) * 60 + int(length[2]) >= MAX_SEC:
            continue
        title = html.unescape(name[1])
        tags = [html.unescape(t) for t in re.findall(r'href="/free-sound-effects/[^"/]+/">([^<]+)</a>', block)]
        if not _words(f"{title} {' '.join(tags)}") & ban:
            out.append({"id": f"mixkit-{item[1]}", "title": title, "tags": tags[:12], "url": url[1], "page": page,
                        "license": MIXKIT_LICENSE, "label": "Mixkit Free License", "credit": "", "source": "mixkit"})
    return out


def needs_for(plan: dict[str, Any], shorts: list[dict[str, Any]], lib: SoundLibrary) -> list[Need]:
    """이번 작업에서 찾을 것: 감독의 위트 소리 + 이 영상에 쓰이는데 실제 파일이 MIN_LOCAL 개보다 적은 카테고리."""
    out: dict[str, Need] = {}
    for g in plan.get("sound_gags") or []:
        idea = str(g.get("sound_idea") or "")
        if idea:
            cat = gag_category(idea)                    # 콜백은 같은 sound_idea → 같은 파일
            out.setdefault(cat, Need(cat, list(g.get("queries") or []) or [idea], idea, str(g.get("type") or "")))
    tr = (plan.get("studio") or {}).get("treatment") or {}
    used = {x for gr in [plan, *shorts] for g in gr.get("graphics") or []
            for x in (AUTO_SFX_FOR_TEMPLATE.get(str(g.get("template")), ""), g.get("sfx"))}
    used |= {s.get("sfx") for s in [*(tr.get("segments") or []), *(tr.get("signature_scenes") or [])] if isinstance(s, dict)}
    for cat in sorted(c for c in used if c and c != "none"):
        real = sum(1 for s in lib.sfx if s.category == cat and s.source != "synth" and s.license_class in USABLE)
        out[cat] = Need(cat, CATEGORY_QUERIES.get(cat, [cat.replace("_", " ")]), count=max(0, MIN_LOCAL - real))
    return list(out.values())


class Fetcher:
    def __init__(self, lib: SoundLibrary, ff: Any, *, pick: Optional[Callable[[str], list[dict]]] = None, download: bool = True,
                 log: LogFn = noop_log, cancel: Optional[CancelToken] = None, cache: Path = CACHE, user_dir: Path = USER_SFX,
                 ears: Optional[Ears] = None):
        self.lib, self.ff, self.pick, self.download, self.log, self.cancel = lib, ff, pick, download, log, cancel
        self.cache, self.user_dir, self.ears = Path(cache), Path(user_dir), ears
        self.dead = ""                          # 이번 작업에서 Openverse 를 그만 부르는 이유
        self.unverified = 0                     # 출처가 라이선스 확인을 막아(Freesound 403 등) 쓰지 않은 후보 수
        self.taken: set[str] = set()            # 다른 요청이 이미 쓰는 파일
        self.deadline = time.monotonic() + DEADLINE
        self._next_search = 0.0
        self._next_mixkit = 0.0
        self.pages_left = MAX_PAGES
        self.index: dict[str, dict[str, Any]] = {"search": {}, "files": {}, "ai": {}, "blocked": {}, "heard": {}}

    def _check(self) -> None:
        if self.cancel is not None:
            self.cancel.check()

    # ------------------------------------------------------------------
    def run(self, needs: list[Need]) -> None:
        if not needs:
            return
        self.cache.mkdir(parents=True, exist_ok=True)
        try:
            self.index.update(json.loads((self.cache / "index.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        pending: list[tuple[Need, list[dict[str, Any]]]] = []
        for need in needs:
            self._check()
            need.count -= self._from_user(need)
            if need.count > 0 and need.kind and self._from_library(need):
                need.count = 0
            if need.count <= 0:
                continue
            cands = self._candidates(need) if self.download else []
            if cands:
                pending.append((need, cands))
            else:
                self._drop(need)
        self._choose(pending)
        self._save()

    def _drop(self, need: Need) -> None:
        why = f"({self.dead})" if self.dead else f"(출처가 라이선스 확인을 막아 뺀 후보 {self.unverified}개)" if self.unverified else ""
        self.log(f"🔇 효과음 '{need.idea or need.category}' 을(를) 찾지 못해 뺍니다{why}")
        if self.unverified:                     # 조용히 빠지지 않게 — sfx_failed 로 소리 리포트·편집리포트에 남는다
            self.lib.failed.append(f"{need.idea or need.category}(출처 확인 불가)")

    def _from_user(self, need: Need) -> int:
        if not self.user_dir.is_dir():
            return 0
        got = 0
        for p in sorted(self.user_dir.rglob("*")):
            if p.suffix.lower() not in AUDIO_EXT or not _matches(need, _words(" ".join(p.relative_to(self.user_dir).with_suffix("").parts))):
                continue
            note = sidecar(p)                   # 곡 옆 이름.txt = 등급 + 크레딧, 없으면 직접 받아 넣은 무료 소리
            cls = note[0] if note else "A"
            if cls in ("D", "X"):
                continue
            self.lib.sfx.append(Sound(f"user_{p.stem}", need.category, p, source="user", title=p.stem,
                                      attribution=note[1] if note else "", license_class="A" if cls == "own" else cls))
            self.taken.add(str(p))
            got += 1
            if need.kind:
                break
        return got

    def _from_library(self, need: Need) -> bool:
        for s in list(self.lib.sfx):
            if (s.source != "synth" and s.license_class in USABLE and str(s.path) not in self.taken
                    and _matches(need, _words(f"{s.category.replace('_', ' ')} {s.title}"))):
                self.lib.sfx.append(replace(s, category=need.category))
                self.taken.add(str(s.path))
                return True
        return False

    # ------------------------------------------------------------------
    def _search(self, q: str) -> list[dict[str, Any]]:
        hit = self.index["search"].get(q)
        if hit and time.time() - hit["t"] < SEARCH_TTL:
            return hit["r"]
        if self.dead or time.monotonic() > self.deadline:
            self.dead = self.dead or "시간 초과"
            return []
        params = {"q": q, "page_size": 20, "license_type": "commercial", "length": "shortest", "mature": "false"}
        try:
            for attempt in range(2):
                time.sleep(max(0.0, self._next_search - time.monotonic()))
                self._next_search = time.monotonic() + SEARCH_GAP
                r = net.request(AUDIO_API, params=params, timeout=12, rounds=1)
                if r.status != 429:
                    break
                if attempt == 0:
                    wait = str(r.headers.get("Retry-After") or r.headers.get("retry-after") or "")
                    self.log(f"Openverse 한도 — {min(30, int(wait) if wait.isdigit() else 20)}초 쉽니다")
                    time.sleep(min(30, int(wait) if wait.isdigit() else 20))
                    self._check()
            if not r.ok:
                self.dead = f"Openverse HTTP {r.status}"
                return []
            data = r.json()
        except (net.NetError, ValueError) as e:
            self.dead = "Openverse 연결 실패"
            self.log(f"(Openverse 연결 실패 — 찾기를 멈춥니다: {net.redact(str(e))[:120]})")
            return []
        out = []
        ban = JUNK - _words(q)
        for x in data.get("results") or []:
            lic = str(x.get("license") or "").lower()
            sec = float(x.get("duration") or 0) / 1000.0
            title, who, page = str(x.get("title") or ""), str(x.get("creator") or ""), str(x.get("foreign_landing_url") or "")
            tags = [str(t.get("name") or "") for t in x.get("tags") or [] if isinstance(t, dict)]
            if (lic not in LICENSE_CLASS or not x.get("url") or not page or not 0 < sec < MAX_SEC or int(x.get("filesize") or 0) > MAX_BYTES
                    or (lic == "by" and not who) or _words(f"{title} {' '.join(tags)}") & ban):
                continue
            label = license_label(lic, str(x.get("license_version") or ""))
            credit = "" if lic == "cc0" else " ".join([str(x.get("attribution") or f'"{title}" by {who} is licensed under {label}.'), page])
            out.append({"id": str(x["id"]), "title": title, "tags": tags[:12], "url": x["url"], "page": page, "license": lic,
                        "label": label, "credit": credit, "source": str(x.get("source") or "")})
        self.index["search"][q] = {"t": time.time(), "r": out}
        return out

    def _search_mixkit(self, q: str) -> list[dict[str, Any]]:
        """Openverse 의 효과음은 대부분 Freesound 라 라이선스 확인이 막힌다 — Mixkit 은 키 없이 열리고 사이트 전체가 한 라이선스다."""
        key = f"mixkit:{q}"
        hit = self.index["search"].get(key)
        if hit and time.time() - hit["t"] < SEARCH_TTL:
            return hit["r"]
        blocked = self.index.setdefault("blocked", {})
        if time.time() - blocked.get("mixkit.co", 0) < RETRY_AFTER or time.monotonic() > self.deadline:
            return []
        ws = re.findall(r"[a-z0-9]+", q.lower())
        out: list[dict[str, Any]] = []
        for slug in dict.fromkeys(["-".join(ws), *reversed(ws)]):   # 'door-knock' 이 0건이면 'knock' → 'door' — 뒤의 _matches 가 맞는 것만 남긴다
            time.sleep(max(0.0, self._next_mixkit - time.monotonic()))
            self._next_mixkit = time.monotonic() + MIXKIT_GAP
            try:
                r = net.request(f"{MIXKIT}{slug}/", timeout=15, rounds=1)
            except net.NetError as e:
                self.log(f"(Mixkit 연결 실패: {net.redact(str(e))[:120]})")
                return []
            if r.status in (403, 429):              # 차단을 우회하지 않는다 — 한동안 두드리지 않는다
                blocked["mixkit.co"] = time.time()
                return []
            if r.ok:
                out = parse_mixkit(r.text, f"{MIXKIT}{slug}/", JUNK - _words(q))
            if out:
                break
        self.index["search"][key] = {"t": time.time(), "r": out}
        return out

    def _candidates(self, need: Need) -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for q in need.queries[:3]:
            for c in [*self._search_mixkit(q), *self._search(q)]:
                found.setdefault(c["id"], c)
            if sum(_matches(need, _cand_words(c)) for c in found.values()) >= KEEP_CANDS:
                break
        ranked = sorted(found.values(), key=lambda c: -_score(need, c))
        out: list[dict[str, Any]] = []
        tries = 0
        for c in ranked:
            self._check()
            if self._blocked(c):               # 막힌 출처는 자리를 차지하지 않는다 — 다른 출처(wikimedia_audio 등)의 후보가 올라온다
                self.unverified += 1
                continue
            tries += 1
            ready = self._prepare(c)
            if ready:
                out.append(ready)
            if len(out) >= KEEP_CANDS or tries > KEEP_CANDS or time.monotonic() > self.deadline:
                break
        return out

    def _blocked(self, c: dict[str, Any]) -> bool:
        blocked = self.index.setdefault("blocked", {})
        return any(time.time() - blocked.get(h, 0) < RETRY_AFTER for h in (net.host_of(c["page"]), net.host_of(c["url"])))

    def _prepare(self, c: dict[str, Any]) -> Optional[dict[str, Any]]:
        """원문 페이지 라이선스 확인 → 받기 → 재기 → 앞 무음을 잘라 FLAC 로. 받기 전에 확인한다(NC·ND 는 받지 않는다)."""
        known = self.index["files"].get(c["id"])
        if known is not None and (known.get("rejected") or (self.cache / known["file"]).exists()):
            return None if known.get("rejected") else known
        raw = self.cache / "raw" / f"{re.sub(r'[^a-zA-Z0-9-]', '', c['id'])}{_ext(c['url'])}"
        host = net.host_of(c["page"])
        blocked = self.index.setdefault("blocked", {})
        cdn = net.host_of(c["url"])
        sitewide = c["license"] == MIXKIT_LICENSE      # 항목별 라이선스 페이지가 없다 — 사이트 전체가 한 라이선스
        if (self.pages_left <= 0 and not sitewide) or self._blocked(c):
            return None                        # 확인 못 한 후보는 쓰지 않는다
        try:
            if not sitewide:
                self.pages_left -= 1
                page = net.request(c["page"], timeout=15, rounds=1)
                if page.status in (403, 429):       # 차단을 우회하지 않는다 — 한동안 그 사이트를 두드리지 않는다
                    blocked[host] = time.time()
                    self.log(f"({host} 가 라이선스 확인을 막아({page.status}) 확인 못 한 후보는 쓰지 않습니다)")
                    return None
                if not page.ok:
                    return None                     # 일시 오류일 수 있어 '거절'로 기억하지 않는다
                lic = license_from_html(c["page"], page.text)
                if lic is None or family(lic.id) != FAMILY[c["license"]]:     # 종류가 같아야(BY 와 BY-SA 는 다른 크레딧)
                    self.index["files"][c["id"]] = {"rejected": f"원문 라이선스 불일치({lic.id if lic else '확인 안 됨'})"}
                    return None
            net.download(c["url"], raw, timeout=25, rounds=1)
            if raw.stat().st_size > MAX_BYTES or not _is_audio(raw):
                self.index["files"][c["id"]] = {"rejected": "오디오가 아니거나 너무 큼"}
                return None
            x = decode(self.ff, raw).mean(axis=1)
            m = measure(x, 48000)
            why = _reject(m)
            if why:
                self.index["files"][c["id"]] = {"rejected": why}
                return None
            dst = self.cache / f"{raw.stem}.flac"
            self.ff.run(["-ss", f"{max(0.0, m['lead'] - 0.005):.3f}", "-i", str(raw), "-t", f"{MAX_SEC:.0f}",
                         "-af", "afade=t=in:d=0.005", "-c:a", "flac", str(dst)], cancel=self.cancel, what="효과음 다듬기")
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001 - 후보 하나의 네트워크·디코딩 오류는 다음 후보로
            net._note(cdn, "sfx", f"{type(e).__name__}: {e}")
            if isinstance(e, net.NetError) and re.search(r"HTTP (403|429)", str(e)):
                blocked[cdn] = time.time()
            return None
        finally:
            raw.unlink(missing_ok=True)
        entry = {**c, **m, "file": dst.name}
        self.index["files"][c["id"]] = entry
        return entry

    # ------------------------------------------------------------------
    def _ask(self, pending: list[tuple[Need, list[dict[str, Any]]]]) -> dict[int, int]:
        """글로 고르기(Sonnet) → {요청 번호: 후보 번호(-1 = 맞는 것 없음)}. 같은 목록이면 지난 답을 다시 쓴다."""
        if not self.pick or not pending:
            return {}
        lines = []
        for i, (need, cands) in enumerate(pending, 1):
            lines.append(f"요청 {i}: {need.idea or need.category}" + (f" (유형 {need.kind})" if need.kind else ""))
            lines += [f"  후보 {k}: {c['title']} · 태그 {', '.join(c['tags'][:8])} · {c['duration']}초 · RMS {c['rms_db']} dB · "
                      f"밝기 {c['centroid_hz']} Hz · 어택 {c['attack_ms']} ms · {c['label']}"
                      + (f" · 들어 보니 {c['heard']}/3 {c.get('heard_note', '')}" if "heard" in c else "") for k, c in enumerate(cands, 1)]
        listing = "\n".join(lines)
        key = text_hash(listing)
        if key in self.index["ai"]:
            return {int(k): v for k, v in self.index["ai"][key].items()}
        try:
            picks = self.pick(listing)
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001 - AI 가 안 되면 규칙 점수로
            self.log(f"(효과음 고르기 AI 실패 → 규칙 점수로: {e})")
            return {}
        out: dict[int, int] = {}
        for p in picks:
            try:
                r, k = int(p.get("request", 0)) - 1, int(p.get("candidate", 0)) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= r < len(pending):
                out[r] = k if 0 <= k < len(pending[r][1]) else -1
        self.index["ai"][key] = out
        return out

    def _hear(self, pending: list[tuple[Need, list[dict[str, Any]]]]) -> None:
        """👂 earshot(있으면)이 설명과 대조해 상위 SFX_TOP 만 남기고 → Gemini 가 듣고 0~3(c['heard']). 들은 것은 캐시."""
        if self.ears is None:
            return
        heard = self.index.setdefault("heard", {})
        ask: list[tuple[str, list[Path]]] = []
        slots: list[tuple[int, list[dict[str, Any]]]] = []
        for i, (need, cands) in enumerate(pending):
            idea = need.idea or need.category.replace("_", " ")
            ranked = earshot_rank(idea, [self.cache / c["file"] for c in cands], self.log)
            if ranked:
                order = {p.name: k for k, p in enumerate(ranked)}
                cands.sort(key=lambda c: order.get(c["file"], len(order)))
                del cands[SFX_TOP:]
            fresh = [c for c in cands if f"{idea}|{c['file']}" not in heard]
            for c in cands:
                if c not in fresh:
                    c.update(heard[f"{idea}|{c['file']}"])
            if fresh:
                ask.append((idea, [self.cache / c["file"] for c in fresh]))
                slots.append((i, fresh))
        if not ask:
            return
        got = self.ears.hear_sfx(ask)
        for j, (i, fresh) in enumerate(slots):
            for k, c in enumerate(fresh):
                if (j, k) in got:
                    c["heard"], c["heard_note"] = got[(j, k)]["score"], got[(j, k)]["note"]
                    heard[f"{ask[j][0]}|{c['file']}"] = {"heard": c["heard"], "heard_note": c["heard_note"]}

    def _choose(self, pending: list[tuple[Need, list[dict[str, Any]]]]) -> None:
        self._hear(pending)
        ai = self._ask(pending)
        for i, (need, cands) in enumerate(pending):
            ranked = sorted((c for c in cands if _matches(need, _cand_words(c)) and c.get("heard", 1) > 0), key=lambda c: -_score(need, c))
            if i in ai:
                top = cands[ai[i]] if ai[i] >= 0 else None
                if top is not None and top.get("heard", 1) == 0:   # 👂 '다른 소리'로 들은 후보는 글만 본 선택이어도 쓰지 않는다
                    top = None
                ranked = [] if ai[i] < 0 else ([top, *(c for c in ranked if c is not top)] if top else ranked)
            free = [c for c in ranked if str(self.cache / c["file"]) not in self.taken]
            chosen = free[:need.count] or ranked[:1 if need.kind else 0]
            if not chosen:
                self._drop(need)
                continue
            for c in chosen:
                path = self.cache / c["file"]
                os.utime(path)                  # 캐시 상한: 오래 안 쓴 것부터 지운다
                self.taken.add(str(path))
                self.lib.sfx.append(Sound(f"ov_{path.stem[:8]}", need.category, path, duration=c["duration"], source=c["source"] if c["source"] == "mixkit" else "openverse",
                                          title=c["title"], attribution=c["credit"], license_class=LICENSE_CLASS[c["license"]]))
                self.log(f"🔊 효과음 '{need.idea or need.category}' → {c['title']} ({c['label']} · {c['source']})")

    def _save(self) -> None:
        total = 0
        for p in sorted(self.cache.glob("*.flac"), key=lambda f: f.stat().st_mtime, reverse=True):
            size = p.stat().st_size
            if total + size > CAP_BYTES and str(p) not in self.taken:
                p.unlink(missing_ok=True)
                self.index["files"] = {k: v for k, v in self.index["files"].items() if v.get("file") != p.name}
            else:
                total += size
        shutil.rmtree(self.cache / "raw", ignore_errors=True)
        self.index = {**self.index, "search": dict(list(self.index["search"].items())[-150:]), "ai": dict(list(self.index["ai"].items())[-40:]),
                      "files": dict(list(self.index["files"].items())[-800:]), "heard": dict(list(self.index.get("heard", {}).items())[-400:])}
        (self.cache / "index.json").write_text(json.dumps(self.index, ensure_ascii=False), encoding="utf-8")


def run(lib: SoundLibrary, plan: dict[str, Any], shorts: list[dict[str, Any]], ff: Any, *, studio: Any = None, download: bool = True,
        log: LogFn = noop_log, cancel: Optional[CancelToken] = None, ears: Optional[Ears] = None) -> None:
    """파이프라인 진입점 — 네트워크·API·디스크 오류는 로그만 남기고 작업을 멈추지 않는다(있는 소리로 계속)."""
    pick = (lambda text: studio.call("portrait_pick", text, PICK_RULES, label="🔊 효과음 고르기").get("picks") or []) if studio else None
    try:
        Fetcher(lib, ff, pick=pick, download=download, log=log, cancel=cancel, ears=ears).run(needs_for(plan, shorts, lib))
    except Cancelled:
        raise
    except Exception as e:  # noqa: BLE001 - 효과음은 말단 작업이다
        log(f"(효과음 찾기 실패 — 있는 소리로 계속합니다: {e})")
