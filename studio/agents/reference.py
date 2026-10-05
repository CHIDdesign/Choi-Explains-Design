"""🎯 레퍼런스 분석기 — 운영자가 끌어다 놓은 사진·영상(릴스 등)을 **재고(측정) · 보고(Claude 비전) · 규칙으로 옮긴다**.

채널 주인 2026-10-04: "디자인 벤치마킹 — 사진이나 영상 레퍼런스를 넣으면 그걸 직접 읽고 디자인 스킬로 만들어 반영" · "깃 못 다룬다 —
자료 드래그드롭 해 넣으면 알아서 벤치마킹하고 디자인 분석하는 것". 운영자는 디자인 용어를 쓰지 않는다 — '이게 좋다'만 준다.

흐름: 파일 → `measure_*`(코드가 잰다: 영상은 2fps 표본 → 히스토그램 차이로 컷 → 샷 길이·컷/분·움직임 양, 사진·영상 모두 팔레트 6색·밝기·대비·채도·
선 밀도) → 컷 시트(샷마다 한 칸, 시각 표시) → Claude(`REFERENCE` 스키마, 프롬프트 `prompts/agents/reference_analyst.md`: STYLE_FRAME 과 같은
`rules` + 기법마다 우리 카드 런타임 레시피 + 가져오지 않을 것) → `user/taste/refs/<slug>.json` + `<slug>_sheet.jpg`.
→ 디자인 역할마다 `rules_block()`(지시 끝) + `ref_sheets()`(보드 그림)로 **매번** 들어간다(`Studio.taste_notes` · `taste.board_images`).

저장소에는 넣지 않는다(user/ 는 gitignore — 측정값·규칙만 user 폴더에). AI 가 없으면 측정값만 저장하고 블록에는 측정 줄만 들어간다.
"""
from __future__ import annotations

import io
import json
import shutil
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

from ..util import Cancelled, CancelToken, LogFn, file_fingerprint, noop_log, read_json, slugify, write_json

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")
VERSION = 1
SAMPLE_FPS = 2.0          # 영상 표본 간격(릴스 컷은 0.5초 넘는 것이 보통)
MAX_FRAMES = 360          # 3분까지 2fps, 더 길면 간격을 늘린다
FRAME_W = 480
SHEET_CELLS = 12          # 컷 시트 칸 수(샷이 많으면 고르게 고른다)
CUT_MIN = 0.30            # 히스토그램 차이(0~1) 최소 임계
CUT_HARD = 0.60           # 이 이상은 이웃과 상관없이 컷
PALETTE_K = 6
Image3 = tuple[str, bytes, str]


def ref_dir() -> Path:
    from . import taste
    d = taste.TASTE_DIR / "refs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def kind_of(path: str | Path) -> str:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return ""


def expand_paths(paths: list[str]) -> list[str]:
    """끌어다 놓은 것 중 폴더는 안의 사진·영상으로 펼친다(한 단계). 같은 파일은 한 번."""
    out: list[str] = []
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            out += [str(f) for f in sorted(pp.iterdir()) if f.is_file() and kind_of(f)]
        elif pp.is_file() and kind_of(pp):
            out.append(str(pp))
    return [p for i, p in enumerate(out) if p not in out[:i]]


# ---------------------------------------------------------------------------
# 측정(순수 함수 — PIL + numpy)
# ---------------------------------------------------------------------------
def _load_rgb(path: str | Path, max_w: int = FRAME_W) -> np.ndarray:
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, max(1, round(im.height * max_w / im.width))))
        return np.asarray(im, dtype=np.uint8)


def _hist(img: np.ndarray) -> np.ndarray:
    """8×8×8 RGB 히스토그램(합 1)."""
    q = (img // 32).reshape(-1, 3).astype(np.int32)
    idx = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
    h = np.bincount(idx, minlength=512).astype(np.float64)
    return h / max(1.0, h.sum())


def _gray(img: np.ndarray) -> np.ndarray:
    f = img.astype(np.float32)
    return 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]


def _edge_ratio(gray: np.ndarray, thr: float = 40.0) -> float:
    """선 밀도: 이웃과 밝기 차가 큰 화소의 비율(글자·선·사진 디테일이 많으면 높다)."""
    if gray.shape[0] < 2 or gray.shape[1] < 2:
        return 0.0
    dx = np.abs(np.diff(gray, axis=1))[:-1, :]
    dy = np.abs(np.diff(gray, axis=0))[:, :-1]
    return float(np.mean((dx + dy) > thr))


def _tone(img: np.ndarray) -> dict[str, Any]:
    g = _gray(img)
    f = img.astype(np.float32) / 255.0
    mx, mn = f.max(axis=2), f.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    p10, p90 = np.percentile(g, 10), np.percentile(g, 90)
    return {"luminance": round(float(g.mean()) / 255.0, 3), "contrast": round(float(p90 - p10) / 255.0, 3),
            "saturation": round(float(sat.mean()), 3), "edge_ratio": round(_edge_ratio(g), 3),
            "dark": bool(g.mean() < 110)}


def palette(imgs: list[np.ndarray], k: int = PALETTE_K) -> list[dict[str, Any]]:
    """여러 프레임의 색을 한 모자이크로 모아 중앙값 분할 양자화 → 지분 순 k 색(hex · share)."""
    from PIL import Image
    if not imgs:
        return []
    tiles = []
    for a in imgs:
        im = Image.fromarray(a).resize((96, 54))
        tiles.append(np.asarray(im))
    mosaic = Image.fromarray(np.concatenate(tiles, axis=0))
    q = mosaic.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: k * 3]
    counts = np.bincount(np.asarray(q, dtype=np.int64).ravel(), minlength=k)[:k]
    total = max(1, int(counts.sum()))
    out = []
    for i in np.argsort(-counts):
        if counts[i] <= 0:
            continue
        r, g, b = pal[i * 3: i * 3 + 3]
        out.append({"hex": f"#{r:02X}{g:02X}{b:02X}", "share": round(int(counts[i]) / total, 3)})
    return out


def measure_image(path: str | Path) -> dict[str, Any]:
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
    a = _load_rgb(path)
    return {"kind": "image", "width": w, "height": h, "aspect": round(w / max(1, h), 3),
            **_tone(a), "palette": palette([a])}


def detect_cuts(hists: list[np.ndarray]) -> tuple[list[int], list[float]]:
    """연속 표본의 히스토그램 차이(0~1)로 컷. 차이가 CUT_HARD(0.6) 이상이면 언제나 컷, 그 아래는 이웃(±5 표본)의 중앙값보다 3배 + 0.08
    넘게 튀어야 컷 — 한 장면 안의 움직임(이웃도 같이 높다)은 넘지 않고 컷만 넘게. 짧은 클립에서 전체 평균·표준편차를 쓰면 컷 둘이
    임계를 스스로 올려 하나도 못 잡았다. 반환: (새 샷이 시작하는 표본 번호들, 차이 곡선)."""
    if len(hists) < 2:
        return [], []
    d = [0.5 * float(np.abs(hists[i] - hists[i - 1]).sum()) for i in range(1, len(hists))]
    arr = np.asarray(d)
    cuts: list[int] = []
    for i, v in enumerate(d):
        lo, hi = max(0, i - 5), min(len(d), i + 6)
        nb = np.concatenate([arr[lo:i], arr[i + 1:hi]])
        base = float(np.median(nb)) if nb.size else 0.0
        if v >= CUT_HARD or (v >= CUT_MIN and v >= 3.0 * base + 0.08):
            if cuts and cuts[-1] == i:          # 바로 앞 표본도 컷(디졸브) — 한 번만
                continue
            cuts.append(i + 1)
    return cuts, [round(v, 3) for v in d]


def _shots(cuts: list[int], n: int, step: float) -> list[tuple[float, float]]:
    bounds = [0] + cuts + [n]
    return [(round(bounds[i] * step, 2), round(bounds[i + 1] * step, 2)) for i in range(len(bounds) - 1) if bounds[i + 1] > bounds[i]]


def measure_frames(frames: list[Path], step: float) -> tuple[dict[str, Any], list[int]]:
    """표본 프레임들 → 샷 통계·움직임 양·팔레트·톤. 반환 (측정값, 샷 대표 프레임 번호들)."""
    imgs = [_load_rgb(f) for f in frames]
    hists = [_hist(a) for a in imgs]
    cuts, diffs = detect_cuts(hists)
    shots = _shots(cuts, len(imgs), step)
    lens = [b - a for a, b in shots]
    # 움직임: 컷이 아닌 이웃 사이 회색 차이 평균(0~1) — 작은 크기로
    small = [_gray(a)[::4, ::4] for a in imgs]
    moves = [float(np.abs(small[i] - small[i - 1]).mean()) / 255.0 for i in range(1, len(small)) if i not in set(cuts)]
    tones = [_tone(a) for a in imgs[:: max(1, len(imgs) // 24)]]
    keys = [min(len(imgs) - 1, (s + e) // 2) for s, e in zip([0] + cuts, cuts + [len(imgs)]) if e > s]
    dur = len(imgs) * step
    m: dict[str, Any] = {
        "kind": "video", "duration": round(dur, 1), "sampled_fps": round(1.0 / step, 2), "frames": len(imgs),
        "shots": len(shots), "cuts_per_min": round(len(cuts) / max(dur / 60.0, 1e-6), 1),
        "shot_median_s": round(float(np.median(lens)), 2) if lens else round(dur, 2),
        "shot_min_s": round(min(lens), 2) if lens else round(dur, 2), "shot_max_s": round(max(lens), 2) if lens else round(dur, 2),
        "motion": round(float(np.mean(moves)), 3) if moves else 0.0,          # 0 정지 · 0.02 잔잔 · 0.08 활발
        "luminance": round(float(np.mean([t["luminance"] for t in tones])), 3),
        "contrast": round(float(np.mean([t["contrast"] for t in tones])), 3),
        "saturation": round(float(np.mean([t["saturation"] for t in tones])), 3),
        "edge_ratio": round(float(np.mean([t["edge_ratio"] for t in tones])), 3),
        "dark": bool(np.mean([t["luminance"] for t in tones]) < 110 / 255.0),
        "palette": palette(imgs[:: max(1, len(imgs) // 40)]),
        "shot_list": [[a, b] for a, b in shots[:60]],
    }
    return m, keys


def extract_frames(src: str | Path, out: Path, duration: float, *, ffmpeg=None, log: LogFn = noop_log,
                   cancel: Optional[CancelToken] = None) -> tuple[list[Path], float]:
    """영상 → 표본 프레임(jpg). 반환 (프레임 경로들, 표본 간격 초)."""
    from ..media.ffmpeg import FFmpeg
    ff = ffmpeg or FFmpeg()
    fps = SAMPLE_FPS if duration <= 0 else min(SAMPLE_FPS, MAX_FRAMES / max(duration, 1.0))
    fps = max(0.2, fps)
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.jpg"):
        f.unlink()
    ff.run(["-i", str(src), "-vf", f"fps={fps:.4f},scale={FRAME_W}:-2:flags=area", "-q:v", "3", str(out / "%05d.jpg")],
           duration=duration, log=log, cancel=cancel, what="레퍼런스 프레임")
    return sorted(out.glob("*.jpg")), 1.0 / fps


def measure_video(src: str | Path, work: Path, *, ffmpeg=None, log: LogFn = noop_log,
                  cancel: Optional[CancelToken] = None) -> tuple[dict[str, Any], list[Path], list[int], float]:
    from ..media.ffmpeg import FFmpeg
    ff = ffmpeg or FFmpeg()
    info = ff.probe(src)
    frames, step = extract_frames(src, work, info.duration, ffmpeg=ff, log=log, cancel=cancel)
    if not frames:
        raise RuntimeError("영상에서 프레임을 뽑지 못했습니다")
    m, keys = measure_frames(frames, step)
    w, h = info.display_size
    m.update({"width": w, "height": h, "aspect": round(w / max(1, h), 3), "duration": round(info.duration or m["duration"], 1),
              "fps": round(float(info.fps or 0), 2)})
    return m, frames, keys, step


# ---------------------------------------------------------------------------
# 컷 시트
# ---------------------------------------------------------------------------
def _fmt(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def cut_sheet(frames: list[Path], keys: list[int], step: float, *, cols: int = 4, cell_w: int = 420,
              cells: int = SHEET_CELLS) -> Optional[bytes]:
    """샷마다 대표 프레임 한 칸(시각 표시). 샷이 많으면 고르게 고른다."""
    from PIL import Image, ImageDraw
    if not frames:
        return None
    idx = list(keys) or [0]
    if len(idx) > cells:
        pick = np.linspace(0, len(idx) - 1, cells).round().astype(int)
        idx = [idx[i] for i in pick]
    ims = []
    for i in idx:
        try:
            with Image.open(frames[i]) as im:
                im = im.convert("RGB")
                k = cell_w / im.width
                ims.append((im.resize((cell_w, max(1, int(im.height * k)))), i * step))
        except OSError:
            continue
    if not ims:
        return None
    cols = min(cols, len(ims))
    ch = max(im.height for im, _ in ims)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell_w + (cols + 1) * 8, rows * (ch + 26) + 8), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for n, (im, t) in enumerate(ims):
        x, y = 8 + (n % cols) * (cell_w + 8), 8 + (n // cols) * (ch + 26)
        sheet.paste(im, (x, y + 18))
        d.text((x, y + 2), f"{n + 1}  {_fmt(t)}", fill=(240, 240, 240))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=84)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Claude 연결(파이프라인 밖에서도 — Pipeline._client_locked 와 같은 선택)
# ---------------------------------------------------------------------------
def make_client(settings: Any, log: LogFn = noop_log) -> tuple[Any, str]:
    """(클라이언트 또는 None, 설명). Claude Code(구독) → API 키 → 없음."""
    from ..director.claude_code import ClaudeCodeClient, find_claude, resolve_backend, scratch_dir
    backend, why = resolve_backend(settings)
    if backend == "claude_code":
        exe = find_claude(getattr(settings, "claude_code_path", "")) or "claude"
        return (ClaudeCodeClient(exe, settings.claude_model, settings.claude_effort, log=log,
                                 workdir=scratch_dir("reference", log=log)), f"Claude Code · {exe}")
    if backend == "api":
        from ..director.claude import ClaudeClient
        return ClaudeClient(settings.anthropic_api_key, settings.claude_model, settings.claude_effort, log=log), why
    return None, why


def _system() -> str:
    from .studio import lean_system_prompt
    return lean_system_prompt(("layouts.md", "skills/agents/jitter.md"))


def _instruction(rec: dict[str, Any]) -> str:
    from ..director.context import load_prompt
    tpl = load_prompt("agents/reference_analyst.md")
    m = {k: v for k, v in rec["measure"].items() if k != "shot_list"}
    if rec["measure"].get("shot_list"):
        m["shot_list_head"] = rec["measure"]["shot_list"][:20]
    return (tpl.replace("{{name}}", rec["name"]).replace("{{kind}}", "영상" if rec["kind"] == "video" else "사진")
            .replace("{{note}}", rec.get("note") or "(없음)").replace("{{measure}}", json.dumps(m, ensure_ascii=False, indent=1)))


def _ask(client: Any, rec: dict[str, Any], images: list[Image3], *, log: LogFn, cancel: Optional[CancelToken]) -> dict[str, Any]:
    from ..director.images import fit_images
    from . import schemas as S
    return client.structured(system=_system(), shared_context="", instruction=_instruction(rec), schema=S.REFERENCE,
                             max_tokens=8000, cancel=cancel, label=f"🎯 레퍼런스 분석 · {rec['name']}",
                             images=fit_images(images, log), effort=None)


# ---------------------------------------------------------------------------
# 분석 한 건
# ---------------------------------------------------------------------------
def analyze_file(path: str | Path, *, client: Any = None, note: str = "", ffmpeg=None, log: LogFn = noop_log,
                 cancel: Optional[CancelToken] = None) -> dict[str, Any]:
    """파일 하나 → 측정 + 시트 + (AI 가 있으면) 규칙 → user/taste/refs/<slug>.json. 반환: 저장한 레코드."""
    p = Path(path)
    kind = kind_of(p)
    if not kind:
        raise ValueError(f"사진·영상 파일이 아닙니다: {p.name}")
    d = ref_dir()
    slug = f"{slugify(p.stem, 32)}_{file_fingerprint(p)[:8]}"
    rec: dict[str, Any] = {"version": VERSION, "slug": slug, "name": p.stem, "file": p.name, "kind": kind,
                           "analyzed_at": time.strftime("%Y-%m-%d %H:%M"), "note": (note or "").strip()[:300],
                           "measure": {}, "sheet": "", "analysis": None, "error": ""}
    images: list[Image3] = []
    work = d / f"_{slug}_frames"
    try:
        if kind == "image":
            rec["measure"] = measure_image(p)
            data = p.read_bytes()
            media = "image/png" if p.suffix.lower() == ".png" else ("image/webp" if p.suffix.lower() == ".webp" else "image/jpeg")
            if p.suffix.lower() == ".bmp":
                from PIL import Image
                buf = io.BytesIO()
                with Image.open(p) as im:
                    im.convert("RGB").save(buf, "JPEG", quality=90)
                data, media = buf.getvalue(), "image/jpeg"
            images.append((f"레퍼런스 사진: {p.name}", data, media))
            sheet = None
            from PIL import Image
            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((1280, 720))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=84)
                sheet = buf.getvalue()
        else:
            m, frames, keys, step = measure_video(p, work, ffmpeg=ffmpeg, log=log, cancel=cancel)
            rec["measure"] = m
            sheet = cut_sheet(frames, keys, step)
            if sheet:
                images.append((f"컷 시트(샷마다 한 칸 · 시각): {p.name}", sheet, "image/jpeg"))
            # 주요 프레임 셋(첫 샷 · 가운데 샷 · 마지막 샷)은 표본 해상도 그대로 — 글자·질감을 본다
            for i in sorted({keys[0], keys[len(keys) // 2], keys[-1]} if keys else {0}):
                try:
                    images.append((f"프레임 {_fmt(i * step)}", frames[i].read_bytes(), "image/jpeg"))
                except (IndexError, OSError):
                    continue
        if sheet:
            (d / f"{slug}_sheet.jpg").write_bytes(sheet)
            rec["sheet"] = f"{slug}_sheet.jpg"
        log(f"🎯 측정: {p.name} — " + measured_line(rec))
        if client is not None:
            try:
                rec["analysis"] = _ask(client, rec, images, log=log, cancel=cancel)
                log(f"🎯 분석: {p.name} — {str(rec['analysis'].get('summary') or '')[:120]}")
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001 - 측정값은 남긴다
                rec["error"] = f"{e.__class__.__name__}: {str(e)[:300]}"
                log(f"⚠ 레퍼런스 AI 분석 실패({p.name}): {rec['error']}")
        write_json(d / f"{slug}.json", rec)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return rec


def measured_line(rec: dict[str, Any]) -> str:
    m = rec.get("measure") or {}
    cols = " ".join(c["hex"] for c in (m.get("palette") or [])[:4])
    stage = "어두운 무대" if m.get("dark") else "밝은 무대"
    if rec.get("kind") == "video":
        return (f"영상 {_fmt(float(m.get('duration') or 0))} · 샷 {m.get('shots', 0)}개(중앙값 {m.get('shot_median_s', 0)}초 · "
                f"{m.get('cuts_per_min', 0)}컷/분) · 움직임 {m.get('motion', 0)} · {stage} · 선 밀도 {m.get('edge_ratio', 0)} · 색 {cols}")
    return (f"사진 {m.get('width', 0)}×{m.get('height', 0)} · {stage} · 대비 {m.get('contrast', 0)} · 채도 {m.get('saturation', 0)} · "
            f"선 밀도 {m.get('edge_ratio', 0)} · 색 {cols}")


# ---------------------------------------------------------------------------
# 저장된 분석 → 디자인 역할에게
# ---------------------------------------------------------------------------
def load_refs() -> list[dict[str, Any]]:
    d = ref_dir()
    out = []
    for f in d.glob("*.json"):
        rec = read_json(f, {})
        if isinstance(rec, dict) and rec.get("slug"):
            out.append(rec)
    return sorted(out, key=lambda r: str(r.get("analyzed_at") or ""), reverse=True)


def delete_ref(slug: str) -> None:
    d = ref_dir()
    (d / f"{slug}.json").unlink(missing_ok=True)
    (d / f"{slug}_sheet.jpg").unlink(missing_ok=True)


def _clip(s: Any, n: int) -> str:
    s = str(s or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def rules_block(limit: int = 6, max_chars: int = 9000) -> str:
    """레퍼런스 분석 → 디자인 역할의 지시 끝 블록. 분석이 없으면 ''(측정만 있는 것은 측정 줄만). 실제 Opus 분석(2026-10-05)은
    움직임 규칙 한 칸이 1000자 넘는 안무 레시피였다 — 자르는 폭은 넉넉히(채널 주인: 비용보다 퀄리티)."""
    refs = load_refs()[:limit]
    if not refs:
        return ""
    lines = [f"## 🎯 레퍼런스 분석(운영자가 넣은 레퍼런스 {len(refs)}개 — 결·기법·박자를 가져오고 글·로고·사진·배치는 가져오지 않는다)"]
    for n, r in enumerate(refs, 1):
        a = r.get("analysis") or {}
        head = f"### {n}. {_clip(r.get('name'), 40)} — {measured_line(r)}"
        if r.get("note"):
            head += f" · 운영자 메모: {_clip(r['note'], 80)}"
        lines.append(head)
        if not a:
            lines.append("- (AI 분석 없음 — 측정값만. 같은 박자·색 배분을 참고한다)")
            continue
        if a.get("summary"):
            lines.append(f"- 요약: {_clip(a['summary'], 360)}")
        rl = a.get("rules") or {}
        for k, lab in (("type", "글자"), ("color", "색"), ("shape", "도형·재질"), ("motif", "모티프"), ("motion", "움직임"), ("grid", "그리드")):
            if str(rl.get(k) or "").strip():
                lines.append(f"- {lab}: {_clip(rl[k], 520 if k == 'motion' else 360)}")
        if a.get("rhythm"):
            lines.append(f"- 박자: {_clip(a['rhythm'], 300)}")
        for t in (a.get("techniques") or [])[:4]:
            if not isinstance(t, dict):
                continue
            how = _clip(t.get("how"), 200)
            rt = _clip(t.get("our_runtime"), 220)
            lines.append(f"- 기법 「{_clip(t.get('name'), 30)}」: {how}" + (f" → {rt}" if rt else ""))
        if rl.get("do"):
            lines.append("- 한다: " + " · ".join(_clip(x, 110) for x in rl["do"][:5]))
        if rl.get("dont"):
            lines.append("- 하지 않는다: " + " · ".join(_clip(x, 110) for x in rl["dont"][:5]))
        if a.get("transfer"):
            lines.append(f"- 우리 채널로 옮길 때: {_clip(a['transfer'], 400)}")
        if a.get("keep_out"):
            lines.append("- 가져오지 않는다: " + " · ".join(_clip(x, 90) for x in a["keep_out"][:5]))
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
    return text + "\n"


def ref_sheets(limit: int = 2) -> list[Image3]:
    """최근 레퍼런스의 컷 시트(사진은 그 사진) — 보드 그림으로."""
    out: list[Image3] = []
    d = ref_dir()
    for r in load_refs():
        if len(out) >= limit:
            break
        f = d / str(r.get("sheet") or "")
        if r.get("sheet") and f.is_file():
            try:
                out.append((f"운영자 레퍼런스 분석 시트: {_clip(r.get('name'), 40)}" + (" (영상 — 샷마다 한 칸)" if r.get("kind") == "video" else ""),
                            f.read_bytes(), "image/jpeg"))
            except OSError:
                continue
    return out


def summary_rows(refs: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """GUI·CLI 목록용 요약."""
    d = ref_dir()
    rows = []
    for r in (refs if refs is not None else load_refs()):
        a = r.get("analysis") or {}
        rl = a.get("rules") or {}
        rows.append({"slug": r.get("slug"), "name": r.get("name"), "kind": r.get("kind"), "at": r.get("analyzed_at"),
                     "sheet": str(d / r["sheet"]) if r.get("sheet") else "", "measured": measured_line(r),
                     "summary": str(a.get("summary") or ""), "motion": str(rl.get("motion") or ""),
                     "type": str(rl.get("type") or ""), "color": str(rl.get("color") or ""),
                     "techniques": [str(t.get("name") or "") for t in (a.get("techniques") or []) if isinstance(t, dict)],
                     "error": str(r.get("error") or ""), "analyzed": bool(a)})
    return rows
