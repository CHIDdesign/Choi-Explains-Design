"""Premiere Pro 에서 열 수 있는 FCP7 XML(xmeml v4) 내보내기.

V1 = 원본 영상의 컷(원본 참조, 재인코딩 없음), A1 = 정리된 보이스(voice.wav, 원본과 같은 타임라인),
마커 = 챕터/그래픽(이름·내용). 자동 결과에서 한두 군데만 손보고 싶을 때 사용.
Premiere: 파일 > 가져오기 > .xml
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from ..models import Span


def _rate(fps: float) -> tuple[int, bool]:
    for base, real in ((24, 23.976), (30, 29.97), (60, 59.94)):
        if abs(fps - real) < 0.02:
            return base, True
    return int(round(fps)), False


def _pathurl(p: Path) -> str:
    s = str(Path(p).resolve()).replace("\\", "/")
    if sys.platform == "win32" or (len(s) > 1 and s[1] == ":"):
        return "file://localhost/" + quote(s, safe="/")
    return "file://localhost" + quote(s, safe="/")


def _rate_xml(timebase: int, ntsc: bool) -> str:
    return f"<rate><timebase>{timebase}</timebase><ntsc>{'TRUE' if ntsc else 'FALSE'}</ntsc></rate>"


def export_xml(
    dst: Path,
    *,
    name: str,
    video: Path,
    audio: Path,
    src_fps: float,
    src_duration: float,
    width: int,
    height: int,
    seq_width: int,
    seq_height: int,
    keeps: list[Span],
    markers: list[tuple[float, str, str]],
) -> None:
    timebase, ntsc = _rate(src_fps)
    real_fps = src_fps
    rate = _rate_xml(timebase, ntsc)
    f = lambda t: int(round(t * real_fps))  # noqa: E731
    file_dur = f(src_duration)
    v_items: list[str] = []
    a_items: list[str] = []
    tl = 0
    for i, k in enumerate(keeps):
        src_in, src_out = f(k.start), f(k.end)
        length = src_out - src_in
        if length <= 0:
            continue
        start, end = tl, tl + length
        tl = end
        vfile = (f"<file id=\"file-v\"><name>{escape(video.name)}</name><pathurl>{escape(_pathurl(video))}</pathurl>"
                 f"{rate}<duration>{file_dur}</duration><media><video><samplecharacteristics>{rate}"
                 f"<width>{width}</width><height>{height}</height></samplecharacteristics></video></media></file>"
                 if i == 0 else "<file id=\"file-v\"/>")
        afile = (f"<file id=\"file-a\"><name>{escape(audio.name)}</name><pathurl>{escape(_pathurl(audio))}</pathurl>"
                 f"{rate}<duration>{file_dur}</duration><media><audio><samplecharacteristics><depth>16</depth>"
                 f"<samplerate>48000</samplerate></samplecharacteristics><channelcount>2</channelcount></audio>"
                 f"</media></file>" if i == 0 else "<file id=\"file-a\"/>")
        v_items.append(
            f"<clipitem id=\"v-{i}\"><name>{escape(video.name)}</name><enabled>TRUE</enabled>"
            f"<duration>{file_dur}</duration>{rate}<start>{start}</start><end>{end}</end>"
            f"<in>{src_in}</in><out>{src_out}</out>{vfile}"
            f"<link><linkclipref>v-{i}</linkclipref><mediatype>video</mediatype><trackindex>1</trackindex><clipindex>{i + 1}</clipindex></link>"
            f"<link><linkclipref>a-{i}</linkclipref><mediatype>audio</mediatype><trackindex>1</trackindex><clipindex>{i + 1}</clipindex></link>"
            f"</clipitem>")
        a_items.append(
            f"<clipitem id=\"a-{i}\"><name>{escape(audio.name)}</name><enabled>TRUE</enabled>"
            f"<duration>{file_dur}</duration>{rate}<start>{start}</start><end>{end}</end>"
            f"<in>{src_in}</in><out>{src_out}</out>{afile}"
            f"<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack></clipitem>")
    marker_xml = "".join(
        f"<marker><name>{escape(title[:60])}</name><comment>{escape(comment[:500])}</comment>"
        f"<in>{int(round(t * real_fps))}</in><out>-1</out></marker>"
        for t, title, comment in markers)
    xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE xmeml>\n<xmeml version=\"4\">"
        f"<sequence id=\"seq-1\"><name>{escape(name)}</name><duration>{tl}</duration>{rate}"
        f"<timecode>{rate}<string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode>"
        "<media><video><format><samplecharacteristics>"
        f"{rate}<width>{seq_width}</width><height>{seq_height}</height><anamorphic>FALSE</anamorphic>"
        "<pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance>"
        f"</samplecharacteristics></format><track>{''.join(v_items)}</track></video>"
        "<audio><numOutputChannels>2</numOutputChannels><format><samplecharacteristics><depth>16</depth>"
        f"<samplerate>48000</samplerate></samplecharacteristics></format><track>{''.join(a_items)}</track></audio>"
        f"</media>{marker_xml}</sequence></xmeml>\n")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(xml, encoding="utf-8")
