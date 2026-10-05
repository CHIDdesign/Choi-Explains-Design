"""④ 자료 폴더(studio/assets/local.py) — 2026-10-04 채널 주인: '참고자료를 줘도 제대로 쓰지 않는다'. 못 읽는 파일을 알리고,
조달 결과에서 어느 파일이 화면에 배치됐는지 센다."""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.assets import local  # noqa: E402
from studio.export.report import edit_report  # noqa: E402


def test_index_lists_unreadable_files_and_counts_used_ones(tmp_path):
    Image.new("RGB", (40, 30), (200, 100, 50)).save(tmp_path / "더블 다이아몬드 도식.png")
    Image.new("RGB", (40, 30), (20, 100, 50)).save(tmp_path / "IMG_2034.jpg")
    (tmp_path / "참고 논문.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "메모.txt").write_text("x", encoding="utf-8")
    items = local.index(tmp_path)
    others = local.other_files(tmp_path)
    assert [it.name for it in items] == ["IMG_2034.jpg", "더블 다이아몬드 도식.png"] and [p.name for p in others] == ["참고 논문.pdf"]
    text = local.listing(items, others)
    assert "M1 `IMG_2034.jpg` (40×30)" in text and "`참고 논문.pdf`" in text and "PNG·JPG" in text
    # 조달 사다리가 복사한 이름(own_<이름>)으로 사용 여부를 센다 — 하우스 톤 처리 꼬리(.full.h1)가 붙어도
    outcomes = [{"assets": [{"src": "images/own_더블_다이아몬드_도식.png", "kind": "photo"}]},
                {"assets": [{"path": "/x/public/images/own_other.full.h1.jpg"}]}, {"assets": []}]
    assert local.used_files(items, outcomes) == {"더블 다이아몬드 도식.png"}


def test_report_lists_unused_materials():
    rep = edit_report(title="t", source_duration=100.0, long_duration=80.0, align_report={}, utts=[], graphics=[],
                      chapters=[], shorts=[], director="d", usage=[], broll=[],
                      materials={"total": 3, "used": 1, "unused": ["a.png", "b.png"]})
    assert "## 🗂 ④ 자료 폴더" in rep and "3개 중 1개" in rep and "안 쓴 파일: a.png, b.png" in rep
