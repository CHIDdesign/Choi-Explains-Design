"""🎼 내 음악 폴더의 곡 목록 — 음악 감독(Claude)이 이 영상에 맞는 곡을 고르도록 측정값과 함께 적는다.

예전에는 파일 이름 해시로 아무 곡이나 돌렸다. 이제는 곡마다 한 번 재서(user/cache/music_features.json, 파일 크기·시각으로 캐시)
길이 · 템포 · 라우드니스 · 온셋 밀도(초당) · 말 대역(1~4 kHz) 비율 · 앞 무음을 목록으로 준다. 측정은
`scripts/sound_ingest.py measure` 와 같은 식이다(입고 게이트와 같은 숫자).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Optional

from ..paths import ROOT

MAX_TRACKS = 40


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
        if k in store:
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
        lines.append(f"- `{p.name}`" + (" · " + " · ".join(bits) if bits else ""))
    return "\n".join(lines)
