"""👂 소리 듣기 — Gemini 가 짧은 모노 발췌를 듣고 구조화 JSON 으로 답한다(채널 주인 2026-11-10 승인: 이 PC 의 Gemini 키, 후보·믹스를 Google 로).

Claude 는 소리를 못 듣는다. 지금까지 곡·효과음은 제목·태그·측정값(글)만 보고 골랐고 완성 믹스는 LUFS 수치만 봤다. 여기서는
  · 곡 후보: 악기 · 시간에 따른 흐름 · 정점 · 말 아래 깔리는가 → 🎼 음악 감독이 읽는 곡 목록 끝에
  · 효과음 후보: 요청한 소리처럼 들리는가 0~3 → 고르기 점수·목록에(earshot 이 있으면 먼저 걸러 상위만 듣는다)
  · 완성 롱폼 믹스: 음악이 말을 덮는가 · 효과음이 튀는가 · 계획한 침묵이 들리는가 → 게이트 D13(경고만, 믹스를 바꾸지 않는다)
전부 말단(실패해도 작업은 계속), 작업당 호출 상한(MAX_CALLS). 발췌는 ffmpeg 로 16 kHz 모노 MP3 몇 초 — 통째로 보내지 않는다.
키 값은 로그·오류 어디에도 적지 않는다(_redact).
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

from .. import net
from ..paths import USER_DIR
from ..util import LogFn, noop_log

MODEL = "gemini-3.7-flash"          # watch 플러그인(claude-video/watch 0.3.2 config.py DEFAULT_GEMINI_MODEL)과 같은 모델
API = "https://generativelanguage.googleapis.com/v1beta"
ENV_FILE = Path.home() / ".config" / "watch" / ".env"
MAX_CALLS = 6                       # 작업당: 곡 1 · 효과음 1~2 · 믹스 1 + 여유
EXCERPT_SEC = 12.0
MIX_EXCERPT_SEC = 20.0
SFX_TOP = 2                         # earshot 이 걸러 준 뒤 Gemini 가 듣는 후보 수(요청마다)
MUSIC_CACHE = USER_DIR / "cache" / "music_ears.json"
CACHE_CAP = 200
_BOOL = {"type": "boolean", "nullable": True}
_STR = {"type": "string"}


def api_key(settings: Any = None) -> str:
    """설정 gemini_key → 환경 GEMINI_API_KEY → ~/.config/watch/.env 의 GEMINI_API_KEY= 줄."""
    key = str(getattr(settings, "gemini_key", "") or "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            k, _, v = line.strip().removeprefix("export ").partition("=")
            if k.strip() == "GEMINI_API_KEY":
                return v.strip().strip("\"'")
    except OSError:
        pass
    return ""


def excerpt(ff: Any, src: Path | str, dst: Path, start: float, sec: float = EXCERPT_SEC) -> Path:
    """start 부터 sec 초를 16 kHz 모노 32 kbps MP3 로(12초 ≈ 50KB)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    ff.run(["-ss", f"{max(0.0, start):.2f}", "-t", f"{sec:.2f}", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "libmp3lame", "-b:a", "32k", str(dst)], what="소리 발췌")
    return dst


def earshot_rank(query: str, paths: list[Path], log: LogFn = noop_log, timeout: float = 300.0) -> Optional[list[Path]]:
    """earshot(github.com/Leonxlnx/earshot, MIT) 이 PATH 에 있으면 `earshot rank` 로 후보를 설명과 대조해 정렬. 없거나 실패하면 None."""
    exe = shutil.which("earshot")
    if not exe or len(paths) < 2:
        return None
    kw: dict[str, Any] = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}
    try:
        p = subprocess.run([exe, "rank", query, *map(str, paths), "--json"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, **kw)
        if p.returncode != 0:
            log(f"(earshot rank 실패: {p.stderr.strip()[-160:]})")
            return None
        data = json.loads(p.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError) as e:
        log(f"(earshot 실행 실패: {type(e).__name__})")
        return None
    # shortcut: 출력 모양은 README 만 보고 짐작(목록 + path 칸), earshot 을 실제로 설치하면 `earshot rank --json` 한 번으로 확인할 것
    items = data if isinstance(data, list) else next((v for k in ("results", "ranked", "ranking", "items", "candidates")
                                                      if isinstance(v := data.get(k), list)), [])
    by = {str(p): p for p in paths} | {p.name: p for p in paths}
    ranked = [by[s] for x in items if isinstance(x, dict)
              for s in [str(x.get("path") or x.get("file") or x.get("name") or "")] if s in by]
    return ranked or None


class Ears:
    ask_timeout = 180.0

    def __init__(self, ff: Any, key: str, *, work: Path, max_calls: int = MAX_CALLS, log: LogFn = noop_log,
                 music_cache: Path = MUSIC_CACHE, excerpt_fn: Callable[..., Path] = excerpt):
        self.ff, self.key, self.work, self.max_calls, self.log = ff, key, Path(work) / "ears", max_calls, log
        self.music_cache, self._excerpt = music_cache, excerpt_fn
        self.calls = 0
        self.dead = "" if key else "Gemini 키 없음"
        self._checked = self._capped = False

    # ------------------------------------------------------------------
    def _redact(self, text: Any) -> str:
        s = net.redact(str(text))
        return s.replace(self.key, "***") if self.key else s

    def ok(self) -> bool:
        if self.dead:
            return False
        if self.calls >= self.max_calls:
            if not self._capped:
                self._capped = True
                self.log(f"👂 소리 듣기 상한({self.max_calls}회)에 닿아 더 듣지 않습니다")
            return False
        return True

    def _available(self) -> bool:
        if self._checked:
            return not self.dead
        self._checked = True
        try:
            r = net.request(f"{API}/models/{MODEL}", headers={"x-goog-api-key": self.key}, timeout=20, rounds=1)
            if not r.ok:
                self.dead = f"모델 {MODEL} 확인 실패(HTTP {r.status})"
        except net.NetError as e:
            self.dead = f"Gemini 연결 실패: {self._redact(e)[:80]}"
        if self.dead:
            self.log(f"👂 소리 듣기 끔 — {self.dead}")
        return not self.dead

    def _ask(self, question: str, parts: list[tuple[str, Path]], schema: dict) -> Any:
        """question + [(라벨, 발췌 파일)] → 스키마대로 파싱한 JSON. 못 들으면 None(이유는 로그)."""
        if not self.ok() or not self._available():
            return None
        self.calls += 1
        content = [{"text": question}]
        for label, p in parts:
            content += [{"text": label}, {"inline_data": {"mime_type": "audio/mp3", "data": base64.b64encode(p.read_bytes()).decode()}}]
        body = {"contents": [{"parts": content}],
                "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema, "temperature": 0}}
        try:
            r = net.request(f"{API}/models/{MODEL}:generateContent", data=json.dumps(body).encode("utf-8"), timeout=self.ask_timeout, rounds=1,
                            headers={"x-goog-api-key": self.key, "Content-Type": "application/json"})
            if not r.ok:
                self.log(f"(👂 Gemini HTTP {r.status}: {self._redact(r.text)[:160]})")
                return None
            return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        except (net.NetError, ValueError, KeyError, IndexError, TypeError) as e:
            self.log(f"(👂 Gemini 응답 못 읽음: {self._redact(e)[:160]})")
            return None

    def _clip(self, name: str, src: Path | str, start: float, sec: float) -> Optional[Path]:
        try:
            return self._excerpt(self.ff, src, self.work / f"{name}.mp3", start, sec)
        except Exception as e:  # noqa: BLE001 - 발췌 못 한 파일은 듣지 않는다
            self.log(f"(👂 발췌 실패 {Path(str(src)).name}: {type(e).__name__})")
            return None

    def _clean(self) -> None:
        shutil.rmtree(self.work, ignore_errors=True)

    # ------------------------------------------------------------------
    def hear_tracks(self, tracks: list[Path], feats: dict[str, dict]) -> dict[str, dict]:
        """곡마다 시작·중간·정점 12초씩 → {파일 이름: {instruments, arc, peak, under_speech, note}}. 들은 곡은 캐시(파일 이름·크기·시각)."""
        from .tracks import _key
        from .cues import peak_time
        store: dict[str, dict] = {}
        try:
            store = json.loads(self.music_cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        out = {p.name: store[_key(p)] for p in tracks if _key(p) in store}
        todo = [p for p in tracks if p.name not in out]
        if todo and self.ok():
            parts, names = [], []
            for i, p in enumerate(todo, 1):
                m = feats.get(p.name) or {}
                dur = float(m.get("duration") or 0) or 180.0
                peak = peak_time(m["curve"]) if m.get("curve") else dur * 0.6
                clips = [self._clip(f"t{i}_{k}", p, t, EXCERPT_SEC) for k, t in enumerate((2.0, dur / 2, max(0.0, peak - 4.0)))]
                if all(clips):
                    names.append(p.name)
                    parts += [(f"곡 {len(names)} — {lab} 12초", c) for lab, c in zip(("시작", "중간", "정점 부근"), clips)]
            if names:
                schema = {"type": "array", "items": {"type": "object", "properties": {
                    "track": {"type": "integer"}, "instruments": _STR, "arc": _STR, "peak": _STR, "under_speech": {"type": "boolean"},
                    "note": _STR}, "required": ["track", "instruments", "arc", "peak", "under_speech", "note"]}}
                ans = self._ask("아래는 한국어 교양 토크 영상의 배경음악 후보들이다. 곡마다 시작·중간·정점 부근 12초씩 들린다. 곡 번호(track)마다 "
                                "악기 편성(instruments), 시간에 따른 흐름(arc: 어떻게 시작해 어디로 가는가), 정점이 어디쯤이며 어떤가(peak), "
                                "말소리 아래 깔려도 되는가(under_speech: 보컬·강한 멜로디·급한 리듬이 없으면 true), 한 줄 메모(note). 한국어로.",
                                parts, schema)
                for row in ans if isinstance(ans, list) else []:
                    try:
                        name = names[int(row["track"]) - 1]
                    except (KeyError, ValueError, TypeError, IndexError):
                        continue
                    out[name] = {k: row.get(k) for k in ("instruments", "arc", "peak", "under_speech", "note")}
                    store[_key(next(p for p in todo if p.name == name))] = out[name]
                try:
                    self.music_cache.parent.mkdir(parents=True, exist_ok=True)
                    self.music_cache.write_text(json.dumps(dict(list(store.items())[-CACHE_CAP:]), ensure_ascii=False), encoding="utf-8")
                except OSError:
                    pass
            self._clean()
        return out

    def hear_sfx(self, requests: list[tuple[str, list[Path]]]) -> dict[tuple[int, int], dict]:
        """[(요청한 소리, [후보 파일])] → {(요청 번호, 후보 번호): {score 0~3, note}} (0부터)."""
        if not self.ok():
            return {}
        parts, idx = [], []
        for i, (idea, paths) in enumerate(requests):
            for k, p in enumerate(paths):
                c = self._clip(f"s{i}_{k}", p, 0.0, 8.0)
                if c:
                    idx.append((i, k))
                    parts.append((f"요청 {i + 1} 「{idea}」 후보 {k + 1}", c))
        if not parts:
            return {}
        schema = {"type": "array", "items": {"type": "object", "properties": {
            "request": {"type": "integer"}, "candidate": {"type": "integer"}, "score": {"type": "integer"}, "note": _STR},
            "required": ["request", "candidate", "score", "note"]}}
        ans = self._ask("효과음 후보 듣기. 요청마다 후보가 실제로 그 요청한 소리처럼 들리는지 0~3 으로(0 = 다른 소리, 1 = 비슷한 계열, "
                        "2 = 맞음, 3 = 딱 그 소리이고 깨끗함). 되풀이 녹음·말소리·음악·잡음이 섞이면 깎는다. 모든 (request, candidate) 에 "
                        "답하고 note 는 한국어 한 줄.", parts, schema)
        self._clean()
        out: dict[tuple[int, int], dict] = {}
        for row in ans if isinstance(ans, list) else []:
            try:
                key = (int(row["request"]) - 1, int(row["candidate"]) - 1)
                score = max(0, min(3, int(row["score"])))
            except (KeyError, ValueError, TypeError):
                continue
            if key in idx:
                out[key] = {"score": score, "note": str(row.get("note") or "")[:80]}
        return out

    def hear_mix(self, mix: Path | str, *, silences: list, cues: list[dict], sfx: list) -> Optional[dict]:
        """완성 롱폼 믹스의 세 발췌(계획한 침묵 · 말 아래 음악 · 효과음) → {music_covers_voice, sfx_jumps_out, silence_clear, note}."""
        self.ask_timeout = 45.0             # 렌더 뒤 완성본 출력 앞이라 — 경고만 내는 말단 기능이 영상 완성을 수 분 늦추지 않게
        if not self.ok():
            return None
        parts = []
        if silences:
            a, b = float(silences[0][0]), float(silences[0][1])
            t0 = max(0.0, a - 8.0)
            c = self._clip("m_silence", mix, t0, MIX_EXCERPT_SEC)
            if c:
                parts.append((f"발췌 {len(parts) + 1}: 계획한 침묵이 이 발췌의 {a - t0:.0f}~{b - t0:.0f}초에 있어야 한다(말 쉼 + 음악·효과음 없음)", c))
        long_cue = next((q for q in cues if float(q.get("end", 0)) - float(q.get("start", 0)) >= MIX_EXCERPT_SEC + 4), None)
        if long_cue:
            c = self._clip("m_music", mix, float(long_cue["start"]) + 4.0, MIX_EXCERPT_SEC)
            if c:
                parts.append((f"발췌 {len(parts) + 1}: 말 아래 음악({long_cue.get('role', '')})", c))
        if sfx:
            t = float(sfx[0][0])
            t0 = max(0.0, t - 5.0)
            c = self._clip("m_sfx", mix, t0, 10.0)
            if c:
                parts.append((f"발췌 {len(parts) + 1}: {t - t0:.1f}초에 효과음 {Path(str(sfx[0][1])).stem}", c))
        if not parts:
            return None
        schema = {"type": "object", "properties": {"music_covers_voice": _BOOL, "sfx_jumps_out": _BOOL, "silence_clear": _BOOL, "note": _STR},
                  "required": ["music_covers_voice", "sfx_jumps_out", "silence_clear", "note"]}
        ans = self._ask("한국어 교양 토크 영상의 완성 믹스 발췌다. 음악이 말소리를 덮어 알아듣기 어려운가(music_covers_voice), 효과음이 "
                        "말·음악보다 튀어 거슬리는가(sfx_jumps_out), 계획한 침묵이 분명히 들리는가(silence_clear). 해당 발췌가 없으면 null. "
                        "note 는 한국어 한 줄.", parts, schema)
        self._clean()
        return ans if isinstance(ans, dict) else None


def music_notes(heard: dict[str, dict]) -> str:
    """음악 감독이 곡 목록과 함께 읽는 '들어 본 것'."""
    rows = [f"- `{n}` · 악기 {h.get('instruments', '')} · 흐름 {h.get('arc', '')} · 정점 {h.get('peak', '')} · "
            f"말 아래 {'됨' if h.get('under_speech') else '안 됨'}" + (f" · {h['note']}" if h.get("note") else "")
            for n, h in heard.items()]
    return "# 들어 본 소리(Gemini)\n" + "\n".join(rows) if rows else ""
