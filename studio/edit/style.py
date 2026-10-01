"""화면 구성 자동 선택 — 하이브리드(기본 에디토리얼 × 사용자 템플릿 종이 콜라주를 섞는다).

사용자가 스타일을 고르지 않는다. 대본·전사·기획(그래픽 종류)을 보고 챕터마다 어울리는 구성을 정하고,
그래픽마다 한 번 더 고른다.

- 챕터 성격: 개념·사례·이야기가 중심(키워드·정의·인용·숫자·자료 사진·스톡, "예를 들어·제가·경험·사례…")이면 **종이**
  (구겨진 종이·찢어진 액자·개념 카드 — 사용자 템플릿), 구조·과정이 중심(프로세스·순환·매트릭스·비교·연표·목록·모션,
  "단계·구조·비교·첫째…")이면 **기본**(칠판 패널·잉크 — 도식이 또렷하다).
- 한 가지로만 쏠리면 섞이지 않으므로, 챕터가 둘 이상인데 모두 같은 쪽이면 차이가 가장 작은 챕터를 반대로 둔다.
- 그래픽: 타이틀은 어느 챕터에서든 종이(사용자 템플릿의 타이틀 구도). 그 밖(개념 카드·도식·사진·스톡·모션·챕터 카드·정리
  보드)은 그 챕터의 구성을 따른다 — 기본 챕터의 개념 카드는 롱폼 무대의 플레이트·보드(docs/롱폼_무대_디자인.md), 종이
  챕터의 개념 카드는 사용자 템플릿(검정 라벨 + 큰 흰 글씨 · 개념 카드 + 화자 액자).
- 액자 샷(화자를 찢어진 액자에 담는 세 번째 앵글)은 종이 챕터에서만.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

CONCEPT = {"keyword", "definition", "quote", "stat"}
PAPER_LEAN = {"keyword": 2.0, "definition": 2.0, "quote": 2.0, "stat": 1.5, "photo": 1.5, "broll": 1.0, "card": 1.0}
CLASSIC_LEAN = {"process": 2.0, "cycle": 2.0, "double_diamond": 2.0, "matrix": 2.0, "compare": 1.5, "timeline": 1.5,
                "venn": 1.5, "pyramid": 1.5, "list": 1.0, "motion": 1.0}
NARRATIVE = ("예를 들", "예컨대", "제가", "저는", "저도", "이야기", "경험", "사례", "사진", "보시면", "느낌", "생각해 보",
             "기억", "처음", "좋아하")
STRUCTURE = ("단계", "구조", "비교", "첫째", "둘째", "셋째", "첫 번째", "두 번째", "세 번째", "과정", "원리", "정리",
             "종류", "분류", "순서", "모델", "공식")


@dataclass
class LookPlan:
    chapters: list[dict[str, Any]] = field(default_factory=list)   # {start, end, look, paper, classic, why}
    graphic_skins: dict[str, str] = field(default_factory=dict)

    def look_at(self, t: float) -> str:
        for c in self.chapters:
            if c["start"] <= t < c["end"]:
                return c["look"]
        return self.chapters[-1]["look"] if self.chapters else "classic"

    def paper_ranges(self) -> list[tuple[float, float]]:
        return [(c["start"], c["end"]) for c in self.chapters if c["look"] == "paper"]

    def summary(self) -> str:
        names = {"paper": "종이", "classic": "기본"}
        return " · ".join(f"챕터 {i + 1} {names[c['look']]}({c['why']})" for i, c in enumerate(self.chapters))


def _count(text: str, words: tuple[str, ...]) -> int:
    return sum(text.count(w) for w in words)


def choose_looks(graphics: list[dict[str, Any]], chapters: list[dict[str, Any]], total: float,
                 text_at: Callable[[float, float], str]) -> LookPlan:
    starts = sorted(float(c["start"]) for c in chapters) or [0.0]
    if starts[0] > 0.05:
        starts.insert(0, 0.0)
    bounds = starts + [total]
    plan = LookPlan()
    for a, b in zip(bounds, bounds[1:]):
        if b - a <= 0.05:
            continue
        gs = [g for g in graphics if a <= g["start"] < b]
        paper = sum(PAPER_LEAN.get(g.get("template", ""), 0.0) for g in gs)
        classic = sum(CLASSIC_LEAN.get(g.get("template", ""), 0.0) for g in gs)
        text = text_at(a, b)
        paper += 0.5 * min(6, _count(text, NARRATIVE))
        classic += 0.5 * min(6, _count(text, STRUCTURE))
        look = "paper" if paper >= classic else "classic"
        why = "개념·사례 중심" if look == "paper" else "구조·도식 중심"
        if paper == classic == 0:
            why = "그래픽 적음"
        plan.chapters.append({"start": round(a, 3), "end": round(b, 3), "look": look, "paper": round(paper, 2),
                              "classic": round(classic, 2), "why": why})
    # 한쪽으로만 쏠리면 차이가 가장 작은 챕터를 반대로(하이브리드)
    if len(plan.chapters) >= 2 and len({c["look"] for c in plan.chapters}) == 1:
        flip = min(plan.chapters[1:] or plan.chapters, key=lambda c: abs(c["paper"] - c["classic"]))
        flip["look"] = "classic" if flip["look"] == "paper" else "paper"
        flip["why"] += " → 섞기 위해 반대로"
    for g in graphics:
        tpl = g.get("template", "")
        if tpl == "title":
            skin = "paper"
        elif tpl == "lower_third":
            skin = "classic"
        else:
            skin = plan.look_at(float(g["start"]))
        plan.graphic_skins[str(g.get("id"))] = skin
    return plan


def apply_looks(props: dict[str, Any], plan: LookPlan) -> None:
    """long props 에 반영: 그래픽마다 skin, 챕터마다 look, props.skin='hybrid'.
    종이 개념 카드가 전면이면 '글 왼쪽 + 화자 액자'(레퍼런스 1)로 바꾼다."""
    from ..render.props import PAPER_SPLIT
    for g in props.get("graphics", []):
        skin = plan.graphic_skins.get(str(g.get("id")), plan.look_at(g["start"]))
        g["skin"] = skin
        if skin == "paper" and g.get("template") in PAPER_SPLIT and g.get("layout") == "fullscreen":
            g["layout"] = "split"
    for c in props.get("chapters", []):
        c["look"] = plan.look_at(float(c["start"]) + 0.01)
    props["skin"] = "hybrid"
