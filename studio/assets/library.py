"""채널 자산 라이브러리(사다리 0번 칸 — 03 문서 4절) — 한 번 확보한 자료(본인 자료·A 등급)를 다음 영상이 다시 쓴다.

`user/asset_library/` 에 파일 사본 + `index.json`(이름·QID → 파일 · 사이드카 메타). C 등급(인용)과 스톡은 넣지 않는다 —
인용은 그 영상의 그 문장에서만 정당하고, 스톡은 제공처에서 다시 받으면 된다.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Optional

KEEP_TIERS = ("own", "A", "A-sa")


def _key(s: str) -> str:
    return re.sub(r"[\s_\-·.()]+", "", (s or "").lower())


def _sig(path: Path) -> str:
    """같은 파일을 두 번 넣지 않게(앞 1MB + 크기)."""
    import hashlib
    with path.open("rb") as f:
        return hashlib.sha1(f.read(1 << 20) + str(path.stat().st_size).encode()).hexdigest()[:20]


class AssetLibrary:
    def __init__(self, root: Path):
        self.root = root
        self.file = root / "index.json"
        self._lock = threading.Lock()
        try:
            self.entries: list[dict[str, Any]] = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.entries = []

    def find(self, *names: str, qid: str = "", role: str = "") -> list[dict[str, Any]]:
        """이름(대본 표기·원어)이나 위키데이터 QID 가 같은 자산들(파일이 있는 것만, 최근 것 먼저)."""
        keys = {_key(n) for n in names if _key(n)}
        out = []
        for e in reversed(self.entries):
            if not (self.root / e.get("file", "")).exists():
                continue
            if role and e.get("role") and e["role"] != role:
                continue
            if (qid and e.get("qid") == qid) or keys & set(e.get("keys") or []):
                out.append(e)
        return out

    def add(self, path: Path, meta: dict[str, Any], names: list[str], *, qid: str = "") -> Optional[dict[str, Any]]:
        tier = str(((meta.get("license") or {}).get("tier")) or meta.get("tier") or "")
        if tier not in KEEP_TIERS or not path.exists():
            return None
        keys = sorted({_key(n) for n in names if _key(n)})
        if not keys and not qid:
            return None
        sig = _sig(path)
        with self._lock:
            for e in self.entries:
                if e.get("sig") == sig or (e.get("source") and e.get("source") == meta.get("source_url")):
                    return e
            self.root.mkdir(parents=True, exist_ok=True)
            dst = self.root / f"{len(self.entries) + 1:05d}_{re.sub(r'[^0-9A-Za-z가-힣._-]+', '_', path.name)[-60:]}"
            if not dst.exists():
                shutil.copyfile(path, dst)
            e = {"file": dst.name, "keys": keys, "qid": qid, "role": meta.get("role", ""), "sig": sig,
                 "source": meta.get("source_url", ""), "meta": meta}
            self.entries.append(e)
            tmp = self.file.with_suffix(".part")
            tmp.write_text(json.dumps(self.entries, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.file)
            return e

    def path_of(self, e: dict[str, Any]) -> Path:
        return self.root / e["file"]
