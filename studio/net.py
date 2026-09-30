"""네트워크 공통: 여러 방식으로 받아 보고, 안 되면 '왜' 안 됐는지 남긴다.

Windows PC 에서 스톡·효과음 다운로드가 조용히 실패하던 원인 후보
  - 백신·보안 프로그램의 HTTPS 검사(자체 인증서) → requests(certifi) 만 인증서 오류
  - Cloudflare 차단(403) → 헤더 조합에 따라 결과가 다름(같은 주소도 UA 에 따라 200/403)
  - 방화벽·프록시
를 한 번에 피하려고 방식을 차례로 바꿔 본다:
  requests(기본 헤더) → urllib(브라우저 헤더 + Referer, OS 인증서) → curl(Windows 기본 curl.exe = OS 인증서)
실측(2026-09-30): Pixabay CDN(Cloudflare)은 약 4초에 3건 정도만 받고 그 이상 몰리면 2초가량 403 을 준다.
예전에는 효과음 66개·스톡 썸네일을 쉬지 않고 연달아 받다가 거의 다 403 → 조용히 대체음·스톡 없음이 됐다.
그래서 호스트별 간격(HOST_GAPS)을 두고, 다 막히면 잠깐 쉬었다가 다시 돈다. 성공한 방식은 호스트마다 기억하고,
실패 이유는 ERRORS 에 모아 진단 자료에 넣는다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/126.0 Safari/537.36")
REFERERS = {"pixabay.com": "https://pixabay.com/", "mixkit.co": "https://mixkit.co/"}
BLOCKED = (403, 406, 503)          # 차단·보호 페이지로 보이는 응답 → 다른 방식으로 다시
STRATEGIES = ("requests", "urllib", "curl")
ROUND_WAIT = (0.0, 2.5, 6.0, 12.0)   # 모든 방식이 막혔을 때 다시 돌기 전 대기(초)
HOST_GAP = 0.35                      # 같은 호스트 요청 사이 최소 간격(초)
HOST_GAPS = {"cdn.pixabay.com": 1.6, "pixabay.com": 0.7}   # 속도 제한이 있는 곳

_lock = threading.Lock()
_best: dict[str, str] = {}                              # 호스트 → 먼저 쓸 방식
_last_hit: dict[str, float] = {}                        # 호스트 → 마지막 요청 시각
ERRORS: dict[str, list[str]] = defaultdict(list)        # 호스트 → 실패 이유(최근 몇 개)
STATS: dict[str, Counter] = defaultdict(Counter)        # 호스트 → {ok, fail}


class NetError(RuntimeError):
    pass


@dataclass
class Response:
    status: int
    content: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    via: str = ""
    url: str = ""

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


def host_of(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").lower()


def _referer(host: str) -> str:
    return next((v for k, v in REFERERS.items() if host == k or host.endswith("." + k)), "")


def _note(host: str, via: str, reason: str) -> None:
    with _lock:
        lst = ERRORS[host]
        msg = f"{via}: {reason}"[:240]
        if msg not in lst:
            lst.append(msg)
            del lst[:-6]


def _full_url(url: str, params: Optional[dict[str, Any]]) -> str:
    if not params:
        return url
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
    return url + ("&" if "?" in url else "?") + q


# ---------------------------------------------------------------------------
# 방식별 구현(dst 가 있으면 파일로 스트리밍)
# ---------------------------------------------------------------------------

def _via_requests(url: str, headers: dict[str, str], timeout: float, dst: Optional[Path]) -> Response:
    import requests
    with requests.get(url, headers=headers, timeout=timeout, stream=dst is not None) as r:
        if dst is not None and r.ok:
            with open(dst, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
            return Response(r.status_code, b"", dict(r.headers), "requests", r.url)
        return Response(r.status_code, r.content, dict(r.headers), "requests", r.url)


def _via_urllib(url: str, headers: dict[str, str], timeout: float, dst: Optional[Path]) -> Response:
    h = {"User-Agent": BROWSER_UA, "Accept": "*/*", "Accept-Language": "ko,en;q=0.8"}
    ref = _referer(host_of(url))
    if ref:
        h["Referer"] = ref
    h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            hdr = {k: v for k, v in r.headers.items()}
            if dst is not None:
                with open(dst, "wb") as f:
                    while True:
                        b = r.read(1 << 16)
                        if not b:
                            break
                        f.write(b)
                return Response(r.status, b"", hdr, "urllib", r.geturl())
            return Response(r.status, r.read(), hdr, "urllib", r.geturl())
    except urllib.error.HTTPError as e:
        return Response(e.code, e.read() or b"", dict(e.headers or {}), "urllib", url)


def _curl_exe() -> Optional[str]:
    return shutil.which("curl.exe" if sys.platform == "win32" else "curl") or shutil.which("curl")


def _via_curl(url: str, headers: dict[str, str], timeout: float, dst: Optional[Path]) -> Response:
    exe = _curl_exe()
    if not exe:
        raise NetError("curl 없음")
    with tempfile.TemporaryDirectory() as td:
        out = dst or Path(td) / "body"
        hdr_file = Path(td) / "headers"
        args = [exe, "-sS", "-L", "--max-time", str(int(timeout)), "-o", str(out), "-D", str(hdr_file),
                "-w", "%{http_code}"]
        if sys.platform == "win32":
            args.append("--ssl-no-revoke")   # 인증서 폐기 목록 서버에 못 닿는 환경(백신·방화벽)에서도 검증은 그대로
        ref = _referer(host_of(url))
        if ref and "Referer" not in headers:
            args += ["-e", ref]
        for k, v in headers.items():
            args += ["-H", f"{k}: {v}"]
        args.append(url)
        kw: dict[str, Any] = {}
        if sys.platform == "win32":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = subprocess.run(args, capture_output=True, timeout=timeout + 15, **kw)
        code = p.stdout.decode("ascii", "ignore").strip()[-3:]
        if p.returncode != 0 or not code.isdigit() or code == "000":
            raise NetError(f"curl 종료 {p.returncode}: {p.stderr.decode('utf-8', 'replace').strip()[:160]}")
        hdr: dict[str, str] = {}
        if hdr_file.exists():
            for line in hdr_file.read_text("latin-1").splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    hdr[k.strip()] = v.strip()
        body = b"" if dst is not None else (out.read_bytes() if out.exists() else b"")
        return Response(int(code), body, hdr, "curl", url)


_IMPL = {"requests": _via_requests, "urllib": _via_urllib, "curl": _via_curl}


def _pace(host: str) -> None:
    gap = HOST_GAPS.get(host, HOST_GAP)
    with _lock:
        wait = gap - (time.monotonic() - _last_hit.get(host, 0.0))
        _last_hit[host] = time.monotonic() + max(0.0, wait)
    if wait > 0:
        time.sleep(wait)


def request(url: str, *, params: Optional[dict[str, Any]] = None, headers: Optional[dict[str, str]] = None,
            timeout: float = 30.0, dst: Optional[Path] = None, rounds: int = len(ROUND_WAIT)) -> Response:
    """GET. 차단(403 등)·인증서·연결 오류면 다음 방식으로, 다 막히면 쉬었다가 한 바퀴 더.
    끝까지 안 되면 마지막 응답을 돌려주거나 NetError."""
    full = _full_url(url, params)
    host = host_of(full)
    order = list(STRATEGIES)
    with _lock:
        if host in _best:
            order.remove(_best[host])
            order.insert(0, _best[host])
    last: Optional[Response] = None
    reasons: list[str] = []
    tmp = None
    attempts = [(rnd, via) for rnd in range(max(1, rounds)) for via in order]
    for rnd, via in attempts:
        if via == order[0] and rnd > 0:
            time.sleep(ROUND_WAIT[min(rnd, len(ROUND_WAIT) - 1)])
        _pace(host)
        if dst is not None:
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(dst.name + ".part")
        try:
            r = _IMPL[via](full, dict(headers or {}), timeout, tmp)
        except Exception as e:  # noqa: BLE001 - 인증서·연결·타임아웃 → 다음 방식
            reason = f"{type(e).__name__}: {e}"
            reasons.append(f"{via} {reason[:120]}")
            _note(host, via, reason)
            if tmp is not None:
                tmp.unlink(missing_ok=True)
            continue
        if r.status in BLOCKED:
            reasons.append(f"{via} HTTP {r.status}")
            _note(host, via, f"HTTP {r.status}")
            last = r
            if tmp is not None:
                tmp.unlink(missing_ok=True)
            continue
        if dst is not None and tmp is not None:
            if r.ok and tmp.exists() and tmp.stat().st_size > 0:
                tmp.replace(dst)
            else:
                tmp.unlink(missing_ok=True)
                if r.ok:
                    reasons.append(f"{via} 빈 파일")
                    _note(host, via, "빈 파일")
                    continue
        with _lock:
            _best[host] = via
            STATS[host]["ok" if r.ok else f"http{r.status}"] += 1
        return r
    with _lock:
        STATS[host]["fail"] += 1
    if last is not None:
        return last
    raise NetError(f"{host} 연결 실패 — " + " / ".join(reasons))


def get_json(url: str, **kw: Any) -> Any:
    r = request(url, **kw)
    if not r.ok:
        raise NetError(f"{host_of(url)} HTTP {r.status}: {r.text[:160]}")
    return r.json()


def download(url: str, dst: Path, *, timeout: float = 180.0, headers: Optional[dict[str, str]] = None) -> Path:
    if dst.exists() and dst.stat().st_size > 0:
        return dst
    r = request(url, dst=dst, timeout=timeout, headers=headers)
    if not r.ok or not dst.exists():
        raise NetError(f"{host_of(url)} 다운로드 실패 HTTP {r.status}")
    return dst


def summary() -> list[str]:
    """진단용: 호스트별 성공/실패와 실패 이유."""
    out = []
    with _lock:
        for host in sorted(set(STATS) | set(ERRORS)):
            st = ", ".join(f"{k} {v}" for k, v in sorted(STATS[host].items())) or "기록 없음"
            line = f"- {host}: {st}" + (f" · 성공 방식 {_best[host]}" if host in _best else "")
            out.append(line)
            for e in ERRORS.get(host, [])[-3:]:
                out.append(f"    · {e}")
    return out


def use_os_certificates() -> bool:
    """가능하면 OS 인증서 저장소를 쓰게 한다(백신·회사망 HTTPS 검사 환경). truststore 가 없으면 그대로."""
    try:
        import truststore
        truststore.inject_into_ssl()
        return True
    except Exception:  # noqa: BLE001
        return False
