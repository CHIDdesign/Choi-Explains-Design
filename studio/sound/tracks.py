"""🎼 내 음악 폴더의 곡 목록 — 음악 감독(Claude)이 이 영상에 맞는 곡을 고르도록 측정값과 함께 적는다.

예전에는 파일 이름 해시로 아무 곡이나 돌렸다. 이제는 곡마다 한 번 재서(user/cache/music_features.json, 파일 크기·시각으로 캐시)
길이 · 템포 · 라우드니스 · 온셋 밀도(초당) · 말 대역(1~4 kHz) 비율 · 앞 무음 · 5초 단위 곡선을 목록으로 준다. 측정은
`scripts/sound_ingest.py measure` 와 같은 식이다(입고 게이트와 같은 숫자).
"""
from __future__ import annotations

import html
import importlib.util
import json
import re
from pathlib import Path
from typing import Any, Callable, Optional

from .. import net
from ..assets.license import classify, family
from ..paths import ROOT
from ..stock.google import license_from_html
from ..stock.openverse import AUDIO_API, license_label
from .cues import PEAK_HOP, peak_time

MAX_TRACKS = 40
CLASSES = ("own", "A", "A-sa", "B", "C", "D", "X")   # 게이트 D9 가 읽는 등급
AUTO_LICENSES = ("cc0", "by", "by-sa")               # NC·ND 는 받지도 않는다
FAMILY = {"cc0": "CC0", "by": "CC-BY", "by-sa": "CC-BY-SA"}   # Openverse 코드 → 원문 페이지에서 확인해야 하는 종류(license.family)
AUTO_MIN_SEC, AUTO_MAX_SEC = 120.0, 480.0
AUTO_WANT = 12
AUTO_PER_ARTIST = 3
AUTO_CAP = 300 * 1024 * 1024                         # 곡당 3~9MB — 작업 세 번치쯤
NOT_INSTRUMENTAL = {"male", "female", "vocal", "vocals", "singer", "voice", "rap"}   # 말 아래에 가사가 깔리면 안 된다


def sidecar(track: Path | str) -> Optional[tuple[str, str]]:
    """곡 옆 `곡이름.txt`: 첫 줄 = 저작권 등급, 나머지 = 크레딧 전문 → (등급, 크레딧). 파일이 없으면 None.
    첫 줄이 등급이 아니면(크레딧만 붙여 넣은 경우) 전체가 크레딧이고 등급은 own 그대로."""
    try:
        raw = Path(track).with_suffix(".txt").read_bytes()
    except OSError:
        return None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:              # 메모장의 ANSI(한국어 Windows)
        text = raw.decode("cp949", "replace")
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    if lines and lines[0] in CLASSES:
        return lines[0], " ".join(lines[1:])
    return "own", " ".join(lines)


def _ingest():
    spec = importlib.util.spec_from_file_location("sound_ingest", ROOT / "scripts" / "sound_ingest.py")
    mod = importlib.util.module_from_spec(spec)          # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)                          # type: ignore[union-attr]
    return mod


def _key(p: Path) -> str:
    st = p.stat()
    return f"{p.name}|{st.st_size}|{int(st.st_mtime)}"


def features(tracks: list[Path], ffmpeg: str = "ffmpeg", cache: Optional[Path] = None) -> dict[str, dict[str, Any]]:
    """{파일 이름: 측정값}. 재지 못한 곡은 길이만 비운 채로 남긴다(목록에서 빠지지 않게)."""
    store: dict[str, Any] = {}
    if cache and cache.exists():
        try:
            store = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            store = {}
    out: dict[str, dict[str, Any]] = {}
    mod = None
    changed = False
    for p in tracks[:MAX_TRACKS]:
        k = _key(p)
        if k in store and ("curve" in store[k] or not store[k]):
            out[p.name] = store[k]
            continue
        try:
            mod = mod or _ingest()
            m = mod.measure(p, ffmpeg)
        except Exception:  # noqa: BLE001 - 못 재도 목록에는 남긴다
            m = {}
        out[p.name] = store[k] = m
        changed = True
    if cache and changed:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return out


def track_listing(tracks: list[Path], ffmpeg: str = "ffmpeg", cache: Optional[Path] = None) -> str:
    """음악 감독이 읽는 곡 목록(파일 이름 그대로 — 그 이름으로 고른다)."""
    feats = features(tracks, ffmpeg, cache)
    lines = []
    for p in tracks[:MAX_TRACKS]:
        m = feats.get(p.name) or {}
        bits = []
        if m.get("duration"):
            d = float(m["duration"])
            bits.append(f"{int(d // 60)}:{int(d % 60):02d}")
        if m.get("bpm"):
            bits.append(f"{m['bpm']:.0f} BPM")
        if m.get("lufs_i") is not None and m.get("lufs_i") != "":
            bits.append(f"{m['lufs_i']} LUFS")
        if m.get("onsets_per_s") is not None:
            bits.append(f"밀도 {m['onsets_per_s']}/초")
        if m.get("band_1_4k") is not None:
            bits.append(f"말 대역 {m['band_1_4k']}")
        if m.get("lead_silence_s"):
            bits.append(f"앞 무음 {m['lead_silence_s']}초")
        if m.get("curve"):
            t = peak_time(m["curve"])
            bits.append(f"정점 {int(t // 60)}:{int(t % 60):02d} · {PEAK_HOP:.0f}초마다 dB " + " ".join(f"{v:.0f}" for v in m["curve"]))
        lines.append(f"- `{p.name}`" + (" · " + " · ".join(bits) if bits else ""))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# music_mode='auto' — 이 작업에 맞는 곡을 찾아 받는다. 고르는 것은 🎼 음악 감독(MUSIC.track)이다
def _usable(r: dict[str, Any]) -> bool:
    tags = {str(t.get("name", "")).lower() for t in r.get("tags") or [] if isinstance(t, dict)}
    sec = float(r.get("duration") or 0) / 1000.0
    # Jamendo 만(가사 없는 곡 태그가 믿을 만하다). 라이선스는 받기 전에 fetch_auto 가 원문 페이지와 대조한다
    return (r.get("source") == "jamendo" and bool(r.get("url")) and bool(r.get("foreign_landing_url")) and r.get("license") in AUTO_LICENSES
            and AUTO_MIN_SEC <= sec <= AUTO_MAX_SEC and "instrumental" in tags and not tags & NOT_INSTRUMENTAL)


def _candidate(r: dict[str, Any]) -> dict[str, Any]:
    title = html.unescape(str(r.get("title") or "track"))
    page = str(r.get("foreign_landing_url") or "")
    label = license_label(r["license"], str(r.get("license_version") or ""))
    credit = html.unescape(str(r.get("attribution") or f'"{title}" by {r.get("creator") or "unknown"}, {label}'))
    return {"name": f"{re.sub(r'[^0-9A-Za-z가-힣]+', '_', title).strip('_')[:40] or 'track'}_{str(r.get('id'))[:8]}.mp3",
            "url": r["url"], "page": page, "title": title, "creator": html.unescape(str(r.get("creator") or "")), "license": label,
            "code": str(r["license"]), "class": classify(label).tier, "credit": f"{credit} {page}".strip(),
            "tags": sorted({str(t.get("name", "")) for t in r.get("tags") or [] if isinstance(t, dict)} | set(r.get("genres") or []))}


def _search(q: str, log: Callable[[str], None]) -> Optional[list[dict[str, Any]]]:
    """None = 연결 실패(다음 검색어도 같은 벽에 막힌다 — 타임아웃형 오프라인에서 검색어마다 1분씩 기다리지 않게)."""
    try:
        data = net.get_json(AUDIO_API, params={"q": q, "page_size": 20, "category": "music", "license_type": "commercial",
                                               "license": ",".join(AUTO_LICENSES), "mature": "false"}, timeout=20.0, rounds=1)
    except (net.NetError, OSError) as e:
        log(f"   (곡 검색 실패 '{q}' — 나머지 검색어는 건너뜀: {e})")
        return None
    except ValueError as e:
        log(f"   (곡 검색 실패 '{q}': {e})")
        return []
    return [r for r in (data.get("results") or []) if _usable(r)]


def search_auto(queries: list[str], log: Callable[[str], None] = lambda _: None, want: int = AUTO_WANT) -> list[dict[str, Any]]:
    """검색어마다 Openverse(음악) → 후보 want 곡. 검색어를 돌아가며 뽑아 한 검색어·한 작곡가로 쏠리지 않게."""
    hits: list[list[dict[str, Any]]] = []
    for q in queries[:4]:
        q = " ".join(str(q).split())
        if not q:
            continue
        rows = _search(q, log)             # 낱말이 모두 맞아야 나온다 — 'pizzicato orchestra' 0건, 'pizzicato' 8건(2026-11-10)
        if rows == [] and " " in q:
            rows = _search(q.split()[0], log)
        if rows is None:
            break
        hits.append(rows)
    out: dict[str, dict[str, Any]] = {}
    artists: dict[str, int] = {}
    for i in range(20):
        for rows in hits:
            if len(out) >= want or i >= len(rows):
                continue
            r = rows[i]
            who = str(r.get("creator") or "")
            if r["id"] not in out and artists.get(who, 0) < AUTO_PER_ARTIST:
                out[r["id"]] = r
                artists[who] = artists.get(who, 0) + 1
    return [_candidate(r) for r in out.values()]


def fetch_auto(cands: list[dict[str, Any]], folder: Path, ffmpeg: str = "ffmpeg", cache: Optional[Path] = None,
               cancel: Any = None, log: Callable[[str], None] = lambda _: None) -> list[Path]:
    """후보를 받아 곡 옆에 등급·크레딧(sidecar)을 쓰고 잰다 — 믹스·업로드 정보·게이트 D9 는 내 음악 폴더의 곡과 같은 길을 간다.
    받기 전에 원문(Jamendo) 페이지의 라이선스가 Openverse 응답과 같은 종류인지 본다(색인이 늦어 BY→BY-NC 로 바뀐 곡을 걸러 내는
    마지막 자리 — 효과음 fetch._prepare 와 같은 원칙). 못 받거나 길이가 안 재지는 곡은 뺀다."""
    got: list[Path] = []
    for c in cands:
        if cancel is not None:
            cancel.check()
        dst = folder / c["name"]
        try:
            want = FAMILY.get(str(c.get("code") or ""), "")
            page = net.request(str(c["page"]), timeout=15.0, rounds=1) if c.get("page") and want else None
            lic = license_from_html(c["page"], page.text) if page is not None and page.ok else None
            if lic is None or family(lic.id) != want:
                log(f"   (곡 {c['name']} 은 원문 라이선스를 확인하지 못해 쓰지 않음: {lic.id if lic else '확인 안 됨'})")
                continue
            net.download(c["url"], dst, timeout=120.0, rounds=1)
            dst.with_suffix(".txt").write_text(f"{c['class']}\n{c['credit']}\n", encoding="utf-8")
        except (net.NetError, OSError) as e:
            log(f"   (곡 받기 실패 {c['name']}: {e})")
            continue
        got.append(dst)
    feats = features(got, ffmpeg, cache)
    good = [p for p in got if AUTO_MIN_SEC * 0.9 <= float((feats.get(p.name) or {}).get("duration") or 0) <= AUTO_MAX_SEC * 1.1]
    _prune(folder, set(good), AUTO_CAP)
    return good


def _prune(folder: Path, keep: set[Path], cap: int) -> None:
    files = sorted(folder.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in files)
    for p in files:
        if total <= cap:
            break
        if p not in keep:
            try:
                size = p.stat().st_size
                p.unlink()
                p.with_suffix(".txt").unlink(missing_ok=True)
                total -= size
            except OSError:
                pass


def auto_notes(cands: list[dict[str, Any]], tracks: list[Path], arc: str) -> str:
    """음악 감독이 곡 목록과 함께 읽는 것: 받은 곡의 제목·작곡가·태그·라이선스 + 바라던 곡의 아크."""
    names = {p.name for p in tracks}
    rows = [f"- `{c['name']}` · 「{c['title']}」 {c['creator']} · {', '.join(c['tags'][:8])} · {c['license']}"
            for c in cands if c["name"] in names]
    return "# 곡 정보\n" + "\n".join(rows) + (f"\n\n# 바라던 곡의 아크\n{arc}" if arc else "")
