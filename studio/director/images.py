"""Claude 에게 보낼 그림을 문서의 한도 안으로 맞춘다(https://platform.claude.com/docs/en/build-with-claude/vision).

- 한 요청에 그림이 20장을 넘으면 장마다 긴 변 2000px 이하여야 한다 — 넘으면 요청이 통째로 거절된다
  (아트 디렉터 검수는 정지 화면 + 움직임 시트 + 폰 시트로 20장을 넘길 수 있다. 검수는 말단 단계라 거절되면 조용히 건너뛴다).
- 긴 변 2576px(Opus 5.5 등 고해상도 등급)를 넘으면 서버가 줄인다 — 미리 줄이면 보내는 양과 지연이 준다.
- 장당 base64 10MB · 요청 32MB.
- media_type 이 실제 형식과 다르면 거절된다(PNG 바이트를 image/jpeg 로 보냄 등) — 실제 형식으로 고친다.
"""
from __future__ import annotations

import io
from typing import Optional

from ..util import LogFn, noop_log

MAX_EDGE = 2576          # 고해상도 등급의 긴 변(그보다 크면 서버가 줄인다)
MANY = 20                # 이보다 많으면 장마다 MANY_EDGE 이하
MANY_EDGE = 2000
MAX_IMAGES = 100         # 200k 문맥 모델의 한 요청 상한(더 큰 모델도 이 값으로 묶는다)
PER_IMAGE_B64 = 9_500_000
REQUEST_B64 = 28_000_000  # 32MB 요청 한도 안에서 글·스키마 몫을 남긴다
FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "GIF": "image/gif", "WEBP": "image/webp"}

Image3 = tuple[str, bytes, str]


def _b64(n: int) -> int:
    return (n + 2) // 3 * 4


def _fit_one(lab: str, data: bytes, media: str, edge: int, *, quality: int = 88) -> Image3:
    """한 장을 긴 변 edge·장당 크기 안으로. 읽을 수 없으면 그대로(서버가 판단)."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            fmt = FORMATS.get(str(im.format or "").upper())
            w, h = im.size
            if max(w, h) <= edge and _b64(len(data)) <= PER_IMAGE_B64 and fmt:
                return lab, data, fmt                  # 형식만 바로잡는다
            k = min(1.0, edge / max(w, h))
            out = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") and fmt == "image/png" else "RGB")
            if k < 1.0:
                out = out.resize((max(1, round(w * k)), max(1, round(h * k))), Image.LANCZOS)
            buf = io.BytesIO()
            if out.mode == "RGBA":
                out.save(buf, "PNG", optimize=True)
                media = "image/png"
            else:
                out.save(buf, "JPEG", quality=quality)
                media = "image/jpeg"
            return lab, buf.getvalue(), media
    except Exception:  # noqa: BLE001 - 그림이 아니면 손대지 않는다
        return lab, data, media


def fit_images(images: Optional[list[Image3]], log: LogFn = noop_log) -> Optional[list[Image3]]:
    """요청 하나에 실을 그림 목록을 한도 안으로(장수 · 긴 변 · 장당·요청 크기 · 형식)."""
    if not images:
        return images
    imgs = list(images)
    if len(imgs) > MAX_IMAGES:
        log(f"(그림 {len(imgs)}장 중 앞 {MAX_IMAGES}장만 보냅니다 — 한 요청 한도)")
        imgs = imgs[:MAX_IMAGES]
    edge = MANY_EDGE if len(imgs) > MANY else MAX_EDGE
    out = [_fit_one(lab, data, media, edge) for lab, data, media in imgs]
    # 요청 전체가 크면 큰 것부터 줄여 다시(긴 변 ×0.75, 품질 80)
    for _ in range(4):
        total = sum(_b64(len(d)) for _, d, _ in out)
        if total <= REQUEST_B64:
            break
        order = sorted(range(len(out)), key=lambda i: -len(out[i][1]))
        for i in order[: max(1, len(out) // 3)]:
            lab, data, media = out[i]
            try:
                from PIL import Image
                with Image.open(io.BytesIO(data)) as im:
                    e = int(max(im.size) * 0.75)
            except Exception:  # noqa: BLE001
                continue
            out[i] = _fit_one(lab, data, media, e, quality=80)
    return out
