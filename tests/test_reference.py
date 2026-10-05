"""🎯 레퍼런스 분석기: 영상 → 컷·샷 길이·움직임·팔레트 측정, 사진 → 톤·팔레트, 컷 시트, Claude(가짜) 규칙 → user/taste/refs 저장 →
디자인 역할의 규칙 블록·보드 시트. 진짜 모델은 부르지 않는다."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.agents import reference as R  # noqa: E402
from studio.agents import taste  # noqa: E402

FFMPEG = shutil.which("ffmpeg")


@pytest.fixture
def taste_dir(tmp_path, monkeypatch):
    d = tmp_path / "taste"
    monkeypatch.setattr(taste, "TASTE_DIR", d)
    return d


def _clip(path: Path) -> Path:
    """세 샷: 어두운 회색 2초 → 크림 3초 → 움직이는 테스트 패턴 2.5초(30fps)."""
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=0x202020:s=320x180:d=2,format=yuv420p",
                    "-f", "lavfi", "-i", "color=c=0xF5F2EA:s=320x180:d=3,format=yuv420p",
                    "-f", "lavfi", "-i", "testsrc2=s=320x180:d=2.5,format=yuv420p",
                    "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-r", "30", str(path)],
                   check=True)
    return path


def _photo(path: Path, dark: bool = True) -> Path:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (1200, 675), (18, 18, 20) if dark else (245, 242, 234))
    d = ImageDraw.Draw(im)
    d.rectangle((100, 100, 700, 300), fill=(252, 84, 0))
    d.text((120, 400), "HELLO", fill=(245, 242, 234) if dark else (38, 33, 30))
    im.save(path)
    return path


class FakeClient:
    """structured() 만 흉내 — 받은 그림 수·스키마를 기록하고 규칙을 돌려준다."""

    def __init__(self):
        self.calls = []

    def structured(self, *, system, shared_context, instruction, schema, images=None, **kw):
        self.calls.append({"system": system, "instruction": instruction, "schema": schema, "images": images or []})
        return {"summary": "큰 숫자 하나와 적은 글자, 컷이 말에 맞는다", "genre": "릴스",
                "rules": {"grid": "바깥 여백 120px", "type": "제목 120px/900 · 라벨 28px 대문자", "color": "어두운 무대 + 오렌지 한 낱말",
                          "shape": "모서리 24px · 선 2px", "motif": "밑줄 스윕", "motion": "어절 마스크 상승 0.6초 · 묶음 간격 0.45초",
                          "do": ["주인공 하나"], "dont": ["되튐", "디졸브"]},
                "rhythm": "샷 2.5초 중앙값, 컷마다 큰 글자 한 방",
                "techniques": [{"name": "어절 마스크", "how": "yPercent 110 → 0, 0.6초", "when": "제목", "our_runtime": "data-anim=\"split-words\""}],
                "palette": [{"hex": "#1F1F1F", "role": "무대"}, {"hex": "#F5F2E9", "role": "판"}],
                "archetypes": ["statement", "stat_ring"], "transfer": "오렌지는 한 낱말에만", "keep_out": ["브랜드 로고", "원문 글"]}


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg 없음")
def test_video_cuts_shots_and_motion(tmp_path, taste_dir):
    clip = _clip(tmp_path / "ref.mp4")
    rec = R.analyze_file(clip, note="컷이 좋다")
    m = rec["measure"]
    assert m["kind"] == "video" and m["shots"] == 3                       # 세 샷을 모두 잡는다(짧은 클립에서도)
    assert [round(a) for a, _ in m["shot_list"]] == [0, 2, 5]
    assert 2.0 <= m["shot_median_s"] <= 3.0 and m["cuts_per_min"] > 10
    assert 0.0 <= m["motion"] <= 0.3 and m["width"] == 320
    hexes = [c["hex"] for c in m["palette"]]
    assert any(h.upper().startswith("#F5") for h in hexes) and any(h.upper() in ("#1F1F1F", "#202020") for h in hexes)
    # 저장: json + 컷 시트, 프레임 작업 폴더는 지운다
    d = R.ref_dir()
    assert (d / f"{rec['slug']}.json").exists() and (d / rec["sheet"]).stat().st_size > 1000
    assert not list(d.glob("_*_frames"))
    assert rec["analysis"] is None and rec["note"] == "컷이 좋다"
    # AI 없이도 블록에는 측정 줄이 들어간다
    block = R.rules_block()
    assert "샷 3개" in block and "AI 분석 없음" in block and "컷이 좋다" in block
    assert len(R.ref_sheets()) == 1 and R.ref_sheets()[0][2] == "image/jpeg"


def test_detect_cuts_ignores_steady_motion_but_catches_hard_cuts():
    rng = np.random.default_rng(1)

    def scene(bins: list[int]) -> np.ndarray:
        """실제 화면처럼 몇 개 색 칸에 몰린 히스토그램 + 작은 흔들림(같은 장면 안의 움직임)."""
        h = np.full(512, 1e-5)
        for b in bins:
            h[b] = 1.0
        h += rng.random(512) * 0.001
        return h / h.sum()

    hists = [scene([10, 11, 300]) for _ in range(8)] + [scene([400, 401, 77]) for _ in range(12)]   # 8번째 표본에서 하드 컷
    cuts, diffs = R.detect_cuts(hists)
    assert cuts == [8] and diffs[7] >= R.CUT_HARD and max(diffs[:7] + diffs[8:]) < R.CUT_MIN
    # 움직임이 큰 장면(이웃도 모두 높다 — 표본마다 색 분포가 흔들림)에서는 컷으로 보지 않는다
    busy = []
    for _ in range(16):
        h = rng.random(512)
        busy.append(h / h.sum())
    cuts2, d2 = R.detect_cuts(busy)
    assert all(R.CUT_MIN < v < R.CUT_HARD for v in d2) and cuts2 == []


def test_photo_measure_and_fake_claude_rules(tmp_path, taste_dir):
    photo = _photo(tmp_path / "ref.png")
    fake = FakeClient()
    rec = R.analyze_file(photo, client=fake, note="시원하다")
    m = rec["measure"]
    assert m["kind"] == "image" and m["dark"] and m["width"] == 1200 and 0.1 < m["contrast"] < 0.8
    assert any(c["hex"].upper() in ("#FC5400", "#FF5500") for c in m["palette"][:3])
    # Claude 는 그 사진을 받고, 지시에는 측정값·메모가 들어간다
    call = fake.calls[0]
    assert len(call["images"]) == 1 and call["images"][0][2] == "image/png"
    assert "시원하다" in call["instruction"] and '"dark": true' in call["instruction"]
    assert "rules" in call["schema"]["properties"] and "layouts" in call["system"].lower() or "구도 원형" in call["system"]
    assert rec["analysis"]["summary"].startswith("큰 숫자")
    # 디자인 역할의 블록: 요약·규칙·기법·우리 런타임·가져오지 않을 것
    block = R.rules_block()
    for s in ("큰 숫자 하나", "어절 마스크 상승", 'data-anim="split-words"', "되튐", "브랜드 로고", "오렌지는 한 낱말에만"):
        assert s in block, s
    rows = R.summary_rows()
    assert rows[0]["analyzed"] and rows[0]["techniques"] == ["어절 마스크"]
    # 보드 시트(사진은 그 사진)와 taste.board_images 에 합쳐진다
    assert any("레퍼런스 분석 시트" in lab for lab, _, _ in taste.board_images())
    R.delete_ref(rec["slug"])
    assert R.load_refs() == [] and R.rules_block() == ""


def test_ai_failure_keeps_measurement(tmp_path, taste_dir):
    class Broken:
        def structured(self, **kw):
            raise RuntimeError("limit")

    rec = R.analyze_file(_photo(tmp_path / "a.jpg", dark=False), client=Broken())
    assert rec["analysis"] is None and "limit" in rec["error"] and not rec["measure"]["dark"]
    assert "AI 분석 없음" in R.rules_block()


def test_expand_paths_and_kinds(tmp_path):
    (tmp_path / "a.PNG").write_bytes(b"x")
    (tmp_path / "b.mov").write_bytes(b"x")
    (tmp_path / "c.txt").write_bytes(b"x")
    assert R.kind_of("x.webp") == "image" and R.kind_of("x.MP4") == "video" and R.kind_of("x.txt") == ""
    got = R.expand_paths([str(tmp_path), str(tmp_path / "b.mov"), str(tmp_path / "c.txt")])
    assert [Path(p).name for p in got] == ["a.PNG", "b.mov"]


def test_studio_taste_notes_include_reference_rules(tmp_path, taste_dir, monkeypatch):
    """디자인 역할의 지시 끝(Studio.taste_notes)에 장면 평가 메모와 레퍼런스 규칙이 함께 붙는다."""
    from studio.agents.studio import Studio
    d = R.ref_dir()
    (d / "x.json").write_text(json.dumps({"slug": "x", "name": "릴스A", "kind": "video", "analyzed_at": "2026-10-05 01:00",
                                          "measure": {"duration": 30, "shots": 12, "shot_median_s": 2.1, "cuts_per_min": 22,
                                                      "motion": 0.03, "dark": True, "edge_ratio": 0.05, "palette": []},
                                          "analysis": {"summary": "컷이 말에 맞는다", "rules": {"motion": "마스크 상승", "do": [], "dont": []},
                                                       "techniques": [], "keep_out": []}}, ensure_ascii=False), encoding="utf-8")
    st = Studio.__new__(Studio)
    text = Studio.taste_notes(st)
    assert "레퍼런스 분석" in text and "컷이 말에 맞는다" in text and "마스크 상승" in text


def test_shared_repo_refs_merge_with_local_and_roundtrip_zip(tmp_path, taste_dir, monkeypatch):
    """저장소 공유 폴더(assets/taste/refs) + 로컬(user/taste/refs)을 합쳐 읽고(같은 slug 는 로컬), 로컬 → zip 내보내기 → 공유 폴더 가져오기.
    공개 저장소라 기본은 JSON 만(시트 없음), --with-sheets 면 시트도."""
    shared = tmp_path / "repo_refs"
    monkeypatch.setattr(R, "SHARED_DIR", shared)
    shared.mkdir()
    from PIL import Image
    from studio.util import write_json
    base = {"version": 1, "kind": "video", "analyzed_at": "2026-10-04 10:00", "note": "", "sheet": "", "error": "",
            "measure": {"duration": 30, "shots": 10, "shot_median_s": 2.5, "cuts_per_min": 18, "motion": 0.03, "dark": False,
                        "edge_ratio": 0.04, "palette": []},
            "analysis": {"summary": "공유본 요약", "rules": {"motion": "공유 움직임", "do": [], "dont": []}, "techniques": [], "keep_out": []}}
    write_json(shared / "shared_a.json", {**base, "slug": "shared_a", "name": "공유A"})
    write_json(shared / "dup.json", {**base, "slug": "dup", "name": "겹침(공유)"})
    local = R.ref_dir()
    write_json(local / "dup.json", {**base, "slug": "dup", "name": "겹침(로컬)", "analyzed_at": "2026-10-05 09:00",
                                    "sheet": "dup_sheet.jpg"})
    Image.new("RGB", (640, 360), (40, 40, 40)).save(local / "dup_sheet.jpg")
    refs = R.load_refs()
    assert [r["name"] for r in refs] == ["겹침(로컬)", "공유A"]              # 같은 slug 는 로컬, 최근 순
    rows = {r["slug"]: r for r in R.summary_rows()}
    assert rows["shared_a"]["shared"] and not rows["dup"]["shared"] and rows["dup"]["sheet"].endswith("dup_sheet.jpg")
    assert "공유본 요약" in R.rules_block() and len(R.ref_sheets()) == 1  # 시트는 로컬 것만
    # 내보내기 → 가져오기(새 공유 폴더로)
    z = R.export_zip(tmp_path / "out.zip")
    import zipfile
    assert sorted(zipfile.ZipFile(z).namelist()) == ["dup.json", "dup_sheet.jpg"]
    target = tmp_path / "repo2"
    assert R.import_refs(z, dst=target) == ["dup"]
    rec = json.loads((target / "dup.json").read_text(encoding="utf-8"))
    assert rec["sheet"] == "" and "_dir" not in rec and not (target / "dup_sheet.jpg").exists()   # 기본: JSON 만
    assert R.import_refs(z, dst=tmp_path / "repo3", with_sheets=True) == ["dup"]
    assert (tmp_path / "repo3" / "dup_sheet.jpg").exists()
    # 폴더에서도, 그리고 delete 는 양쪽 다
    assert R.import_refs(local, dst=tmp_path / "repo4") == ["dup"]
    R.delete_ref("dup")
    assert not (local / "dup.json").exists() and not (shared / "dup.json").exists() and [r["slug"] for r in R.load_refs()] == ["shared_a"]
