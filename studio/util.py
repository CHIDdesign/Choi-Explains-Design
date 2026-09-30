"""공용 유틸: 로깅 콜백, 해시 캐시, JSON 입출력, 서브프로세스, 취소 토큰."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Iterable

LogFn = Callable[[str], None]
ProgressFn = Callable[[float], None]


class Cancelled(Exception):
    """사용자가 작업을 취소했을 때."""


class CancelToken:
    def __init__(self) -> None:
        self._ev = threading.Event()
        self._procs: list[subprocess.Popen] = []
        self._lock = threading.Lock()

    def cancel(self) -> None:
        self._ev.set()
        with self._lock:
            for p in self._procs:
                try:
                    p.kill()
                except OSError:
                    pass

    @property
    def cancelled(self) -> bool:
        return self._ev.is_set()

    def check(self) -> None:
        if self._ev.is_set():
            raise Cancelled()

    def register(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.append(proc)
        if self._ev.is_set():
            proc.kill()

    def unregister(self, proc: subprocess.Popen) -> None:
        with self._lock:
            if proc in self._procs:
                self._procs.remove(proc)


def noop_log(_: str) -> None:
    pass


def noop_progress(_: float) -> None:
    pass


# ----------------------------------------------------------------------------
# 파일/해시
# ----------------------------------------------------------------------------

_FP_CACHE: dict[tuple[str, int, int], str] = {}


def file_fingerprint(path: str | Path) -> str:
    """큰 영상 파일도 빠르게: 크기 + 수정시각 + 앞/뒤 1MB 해시. 같은 파일(경로·크기·수정시각)은 한 번만 읽는다
    (단계마다 카메라마다 부르므로)."""
    p = Path(path)
    st = p.stat()
    ck = (str(p.resolve()), st.st_size, st.st_mtime_ns)
    if ck in _FP_CACHE:
        return _FP_CACHE[ck]
    _FP_CACHE[ck] = fp = _fingerprint(p, st)
    return fp


def _fingerprint(p: Path, st: os.stat_result) -> str:
    h = hashlib.sha1()
    h.update(f"{st.st_size}:{int(st.st_mtime)}".encode())
    with p.open("rb") as f:
        h.update(f.read(1 << 20))
        if st.st_size > (2 << 20):
            f.seek(-(1 << 20), os.SEEK_END)
            h.update(f.read(1 << 20))
    return h.hexdigest()[:16]


def text_hash(*parts: Any) -> str:
    h = hashlib.sha1()
    for part in parts:
        if not isinstance(part, (str, bytes)):
            part = json.dumps(part, ensure_ascii=False, sort_keys=True, default=str)
        if isinstance(part, str):
            part = part.encode("utf-8")
        h.update(part)
        h.update(b"\x00")
    return h.hexdigest()[:16]


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=_json_default), encoding="utf-8")
    os.replace(tmp, p)


def _json_default(o: Any) -> Any:
    if hasattr(o, "to_dict"):
        return o.to_dict()
    if isinstance(o, Path):
        return str(o)
    if hasattr(o, "__dict__"):
        return o.__dict__
    raise TypeError(f"not serializable: {type(o)}")


def slugify(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[\\/:*?\"<>|\s]+", "_", text.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:max_len] or "untitled"


def fmt_ts(sec: float, with_ms: bool = False) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    if with_ms:
        base = f"{m:02d}:{s:04.1f}"
    else:
        base = f"{m:02d}:{int(s):02d}"
    return f"{h}:{base}" if h else base


# ----------------------------------------------------------------------------
# 서브프로세스
# ----------------------------------------------------------------------------

def _popen_kwargs() -> dict[str, Any]:
    kw: dict[str, Any] = {}
    if sys.platform == "win32":
        # GUI 에서 실행할 때 콘솔 창이 깜빡이지 않도록
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kw


def run_process(
    args: list[str],
    *,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    on_line: Callable[[str], None] | None = None,
    cancel: CancelToken | None = None,
    stdin_data: bytes | None = None,
) -> tuple[int, str]:
    """프로세스를 실행하고 stdout+stderr 를 줄 단위로 on_line 에 전달한다.

    반환: (returncode, 마지막 출력 4000자)
    """
    proc = subprocess.Popen(
        args,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **_popen_kwargs(),
    )
    if cancel:
        cancel.register(proc)
    tail: list[str] = []
    try:
        if stdin_data is not None and proc.stdin:
            proc.stdin.write(stdin_data)
            proc.stdin.close()
        assert proc.stdout is not None
        buf = b""
        while True:
            chunk = proc.stdout.read1(65536) if hasattr(proc.stdout, "read1") else proc.stdout.read(4096)
            if not chunk:
                break
            buf += chunk
            # ffmpeg 는 진행 상황을 \r 로 갱신하므로 \r 도 줄바꿈으로 취급
            parts = re.split(rb"\r\n|\n|\r", buf)
            buf = parts.pop()
            for raw in parts:
                line = raw.decode("utf-8", errors="replace")
                tail.append(line)
                if len(tail) > 200:
                    tail = tail[-100:]
                if on_line:
                    on_line(line)
        if buf:
            line = buf.decode("utf-8", errors="replace")
            tail.append(line)
            if on_line:
                on_line(line)
        code = proc.wait()
    finally:
        if cancel:
            cancel.unregister(proc)
    if cancel and cancel.cancelled:
        raise Cancelled()
    return code, "\n".join(tail)[-4000:]


def chunks(seq: list, n: int) -> Iterable[list]:
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v
