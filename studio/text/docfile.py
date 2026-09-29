"""대본·주제 파일 읽기: .txt/.md(UTF-8·CP949), .docx(워드), .hwpx(한글) — 추가 설치 없이."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

TEXT_EXTS = (".txt", ".md", ".docx", ".hwpx")


def _xml_paragraphs(data: bytes, para_tag: str, text_tag: str) -> list[str]:
    root = ET.fromstring(data)
    out = []
    for p in root.iter():
        if p.tag.endswith("}" + para_tag) or p.tag == para_tag:
            texts = [t.text or "" for t in p.iter() if t.tag.endswith("}" + text_tag) or t.tag == text_tag]
            out.append("".join(texts))
    return out


def read_text_file(path: str | Path) -> str:
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".docx":
        with zipfile.ZipFile(p) as z:
            paras = _xml_paragraphs(z.read("word/document.xml"), "p", "t")
        return "\n".join(paras).strip()
    if ext == ".hwpx":
        with zipfile.ZipFile(p) as z:
            names = sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml", n))
            paras: list[str] = []
            for n in names:
                paras += _xml_paragraphs(z.read(n), "p", "t")
        return "\n".join(paras).strip()
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "cp949", "utf-16"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")
