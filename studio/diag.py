"""진단 자료: 작업이 끝나거나 실패하면 부가자료/진단자료.zip 을 만든다(작은 텍스트 파일만, 키 값은 넣지 않음).

문제가 생겼을 때 이 파일 하나만 보내면 원인(스톡·효과음이 왜 안 받아졌는지, 컷·자막·색보정이 어떻게 됐는지)을 볼 수 있다.
"""
from __future__ import annotations

import datetime as dt
import platform
import sys
import zipfile
from pathlib import Path
from typing import Any

from . import __version__, net

KEEP_EXT = {".json", ".md", ".txt", ".srt", ".xml", ".log"}
MAX_FILE = 3 * 1024 * 1024
SECRET_KEYS = ("api_key", "access_key", "token", "secret", "password")


def settings_summary(settings: Any) -> list[str]:
    """설정 요약 — 키는 '있음/없음'만."""
    out = []
    for k, v in sorted(vars(settings).items()):
        if any(s in k for s in SECRET_KEYS):
            out.append(f"- {k}: {'있음' if v else '없음'}" + (f" ({len(str(v))}자)" if v else ""))
        elif isinstance(v, (str, int, float, bool)) and len(str(v)) < 120:
            out.append(f"- {k}: {v}")
    return out


def write(pipeline: Any, error: str = "") -> Path | None:
    """work/진단.md 를 쓰고 부가자료/진단자료.zip 으로 묶는다. 실패해도 작업에는 영향 없음."""
    try:
        p = pipeline
        lines = [f"# 진단 — {p.title}", "",
                 f"- 시각: {dt.datetime.now():%Y-%m-%d %H:%M:%S}",
                 f"- Choi Studio {__version__} · Python {sys.version.split()[0]} · {platform.platform()}",
                 f"- 결과: {'실패 — ' + error.splitlines()[0][:200] if error else '완료'}", ""]
        info = getattr(p, "info", None)
        if info is not None:
            w, h = info.display_size
            lines += [f"- 원본: {w}x{h} · {info.fps:.2f}fps{' VFR' if info.vfr else ''} · {info.duration:.1f}s · "
                      f"{info.vcodec}/{getattr(info, 'acodec', '')}", ""]
        lines += ["## 설정(키 값은 넣지 않음)"] + settings_summary(p.settings) + [""]
        snd = getattr(p, "sounds", None)
        if snd is not None:
            real = [s for s in snd.sfx if s.source != "synth"]
            lines += ["## 효과음·배경음악",
                      f"- 받은 효과음 {len(real)}개 · 대체(합성) 효과음 {len(snd.sfx) - len(real)}개 · 배경음악 {len(snd.bgm)}곡",
                      f"- 받지 못한 것 {len(getattr(snd, 'failed', []))}개: " + ", ".join(getattr(snd, "failed", [])[:12]), ""]
        st = getattr(p, "stock_stats", None)
        if st:
            lines += ["## 스톡(B-roll)", "- " + " · ".join(f"{k} {v}" for k, v in st.items()), ""]
        lines += ["## 네트워크(호스트별 성공·실패와 이유)"] + (net.summary() or ["- 기록 없음"]) + [""]
        if error:
            lines += ["## 오류", "```", error[-4000:], "```", ""]
        diag_md = p.work / "진단.md"
        diag_md.write_text("\n".join(lines), encoding="utf-8")

        dst = p.extras / "진단자료.zip"
        dst.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
            for base in (p.work, p.extras, p.render_dir):
                if not base.exists():
                    continue
                for f in sorted(base.rglob("*")):
                    if (f.is_file() and f.suffix.lower() in KEEP_EXT and f.stat().st_size <= MAX_FILE
                            and "bundle" not in f.parts and "node_modules" not in f.parts and f != dst):
                        z.write(f, f.relative_to(p.dir).as_posix())
        return dst
    except Exception:  # noqa: BLE001 - 진단 실패가 결과를 막으면 안 됨
        return None
