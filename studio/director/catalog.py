"""그래픽 템플릿 카탈로그 — Claude 프롬프트, 검증, Remotion 렌더러가 공유하는 계약.

renderer/src/lib/types.ts 의 TemplateName 과 반드시 같은 목록을 유지한다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Template:
    name: str
    label: str                 # 한글 이름
    use: str                   # 언제 쓰는가
    fields: str                # 어떤 필드를 어떻게 채우는가
    layouts: tuple[str, ...]   # 허용 레이아웃(첫 번째가 기본)
    min_dur: float
    max_dur: float
    priority: int = 5          # 겹칠 때 우선순위(높을수록 유지)


LAYOUTS = ("fullscreen", "split", "overlay", "pip")

TEMPLATES: dict[str, Template] = {t.name: t for t in [
    Template("chapter", "챕터 카드",
             "큰 전환의 첫 문장에(빈도는 영상 형식 문서). 목차 없음.",
             "title=챕터 제목(대상·사례 명사구, 12자 이내), subtitle=한 줄 부제(선택)",
             ("fullscreen",), 2.2, 3.0, 9),
    Template("keyword", "키워드 슬램",
             "핵심 비유·개념어를 이름 붙이는 순간(예: '여백은 숨 쉴 공간') — 화면 중앙 핵심어 슬롯.",
             "title=핵심어/비유(12자 이내), subtitle=작은 보조문(선택)",
             ("overlay", "split", "fullscreen"), 2.0, 3.0, 6),
    Template("definition", "용어 정의",
             "처음 등장하는 이론 용어를 정의할 때.",
             "title=용어, subtitle=영문 원어, body=정의(40자 이내)",
             ("split", "fullscreen"), 3.0, 5.0, 7),
    Template("quote", "인용 카드",
             "화자가 책/인물의 문장을 인용할 때만(대본에 있거나 실제로 말한 경우).",
             "body=인용문(60자 이내), author=인물, source=책/출처와 연도",
             ("fullscreen",), 4.0, 6.0, 7),
    Template("list", "목록",
             "조건·특징·원칙 등을 나열할 때. 말하는 순서대로 항목이 하나씩 나타난다.",
             "title=목록 제목, items=항목 2~6개(각 16자 이내)",
             ("split", "fullscreen"), 5.0, 16.0, 6),
    Template("process", "단계 프로세스",
             "선형 단계(예: 디자인 씽킹 5단계)를 설명할 때. 현재 설명 중인 단계를 강조.",
             "title=프로세스 이름, items=단계 3~7개(각 8자 이내), highlight=강조할 단계 인덱스(0부터, 없으면 -1)",
             ("fullscreen", "split"), 8.0, 14.0, 7),
    Template("cycle", "순환 구조",
             "반복/순환하는 과정(빌드-측정-학습, 반복적 디자인)을 설명할 때.",
             "title=이름, items=단계 3~6개, highlight=강조 인덱스 또는 -1",
             ("fullscreen", "split"), 8.0, 14.0, 7),
    Template("double_diamond", "더블 다이아몬드",
             "영국 디자인 카운슬의 더블 다이아몬드(발견-정의-개발-전달)를 설명할 때.",
             "title=제목, items=4단계 이름(비우면 기본값 발견/정의/개발/전달), highlight=강조 단계 0~3 또는 -1",
             ("fullscreen", "split"), 8.0, 14.0, 8),
    Template("matrix", "2x2 매트릭스",
             "두 축으로 분류하는 개념(예: 긴급/중요, 기능/감성)을 설명할 때.",
             "title=제목, items=사분면 4개 [좌상, 우상, 좌하, 우하], items_b=축 이름 4개 [x낮음, x높음, y낮음, y높음], highlight=강조 사분면 0~3 또는 -1",
             ("fullscreen",), 8.0, 14.0, 7),
    Template("compare", "비교(A vs B)",
             "두 개념을 대조할 때(발산 vs 수렴, 형태 vs 기능).",
             "subtitle=비교 질문(선택), title=A 이름, items=A 특징 1~4개, title_b=B 이름, items_b=B 특징 1~4개",
             ("fullscreen", "split"), 8.0, 14.0, 7),
    Template("timeline", "연표",
             "역사적 흐름(바우하우스→울름→브라운→애플)을 말할 때.",
             "title=제목, items='연도|사건' 형식 2~6개",
             ("fullscreen",), 8.0, 14.0, 6),
    Template("stat", "숫자 강조",
             "화자가 구체적 수치를 말할 때만. 수치를 지어내지 않는다.",
             "title=숫자(예: 85%), body=의미(24자 이내), subtitle=출처(선택)",
             ("overlay", "fullscreen"), 3.0, 6.0, 6),
    Template("venn", "벤 다이어그램",
             "두세 개념의 교집합(예: 매력성·실현성·지속가능성)을 설명할 때.",
             "title=제목, items=원 2~3개 이름, body=교집합 이름",
             ("fullscreen",), 8.0, 14.0, 6),
    Template("pyramid", "피라미드/위계",
             "위계 구조(매슬로 욕구, 사용성 위계)를 설명할 때.",
             "title=제목, items=아래→위 순서 3~5개, highlight=강조 인덱스 또는 -1",
             ("fullscreen", "split"), 8.0, 14.0, 6),
    Template("photo", "자료 사진",
             "고유명사(제품·건축·디자이너·브랜드·작품)가 처음 나오면 1초 안에 실제 사진. 지나가는 언급은 pip, 근거는 풀스크린.",
             "image=로컬 이미지 파일명 또는 영어 검색어(예: 'Braun SK 4 radio'), title=대상 이름, body=짧은 캡션(연도·디자이너 등, 선택)",
             ("fullscreen", "split", "pip"), 2.0, 5.0, 6),
    Template("motion", "모션 장면(직접 설계)",
             "움직임 자체가 설명인 짧은 장면(게슈탈트 근접성, 비례 변화 등). 그래픽 담당 전용.",
             "spec_json=MotionSpec JSON(모션 DSL 참고)",
             ("fullscreen", "split"), 5.0, 14.0, 8),
    Template("card", "자유 HTML 카드",
             "실물 자료가 보여 줄 수 없는 메커니즘(단면·흐름·변화)에만 — 그래픽 담당이 `cards` 로만 낸다(카드 DSL 참고). graphics 목록에는 쓰지 않는다.",
             "html=카드 조각(<div class=\"card\" data-card-id=…><style>…</style>…), style=editorial|board",
             ("fullscreen", "split", "overlay"), 5.0, 14.0, 8),
    Template("broll", "스톡 B-roll",
             "구체적 장면·사물·분위기를 실제 영상/사진으로 보여줄 때(무료 스톡: Pixabay·Unsplash·Coverr·Pexels). 고유명사 실물은 photo(위키미디어) 우선.",
             "image=영어 검색어(구체적 명사·장면), title=한국어 검색어(화면 라벨로도 씀), subtitle=video|photo, body=이 장면의 목적",
             ("fullscreen", "split", "pip"), 2.0, 5.0, 6),
    Template("stamp", "도장",
             "자료 위에 판정을 찍을 때(철거 예정·미완공처럼 짧은 사실). 영상당 3개 이하.",
             "title=도장 글자(6자 이내), subtitle=아랫줄(연도·기관, 선택)",
             ("overlay",), 1.5, 2.5, 5),
    Template("cutout_stack", "오림 스택",
             "자료 리서처 전용 — 말에 맞춰 사례를 하나씩 쌓을 때. 화자 옆 오른쪽 위에서 아래로.",
             "(앱이 채움) cutouts=[{image, label, at}]",
             ("overlay",), 3.0, 12.0, 6),
    Template("collage", "콜라주",
             "자료 리서처 전용 — 역사 속 인물·건물을 호명하는 비트(영상당 3~5곳). 흑백 망점으로 오린 사람·건물 덩어리 + 평면색 원 + 찢긴 이름표.",
             "(앱이 채움) cutouts · name=이름 · name_sub=영문·연도 · disc=mint|orange",
             ("fullscreen",), 3.0, 6.0, 9),
    Template("keyword_montage", "핵심어 몽타주",
             "자료 리서처 전용 — 한 낱말로 묶이는 사례를 잇달아 호명할 때. 가운데 고정된 큰 흰 낱말 뒤로 사진이 0.7~1.5초마다 하드 컷.",
             "(앱이 채움) title=핵심어(8자 이내) · cutouts=사진 3~5장, 각각 그 사례를 말한 낱말에 착지",
             ("fullscreen",), 2.8, 6.0, 8),
    Template("lower_third", "인물·기관 슈퍼",
             "대본에 나온 인물·기관의 이름을 처음 말할 때, 화자 위 좌하단에 이름표로(실물 자료가 그 이름을 이미 보여 주면 쓰지 않는다).",
             "title=이름, subtitle=소속·직함(사실만, 16자 이내)",
             ("overlay",), 3.0, 4.0, 5),
    Template("evidence", "증거 자료",
             "자료 리서처 전용 — 화자가 말한 대상·출처·화면을 실물로(사진 여러 장·출처 카드·화면 캡처·화자 자료). 앱이 조달해 채운다."
             " 모션 디자이너는 쓰지 않는다.",
             "(앱이 채움) assets · treatment(hero|full|archive_card|doc_highlight|browser_frame|grid|compare_pair) · "
             "title=주장 한 조각(label) · body=사실 캡션 · overlays 의 dimension=두 끝점 + 말한 실제 숫자 · "
             "expand=앞 전면 그래픽의 조각이 이 화면이 되는 전환(맞붙은 전면끼리만, 영상당 2회까지 — 화자 ↔ 자료는 하드 컷)",
             ("fullscreen", "split", "pip"), 2.5, 12.0, 8),
]}

TEMPLATE_NAMES = tuple(TEMPLATES.keys())
# 디렉터가 고르지 않는 자동 템플릿(types.ts TemplateName 에도 있다): 타이틀
AUTO_TEMPLATES = ("title",)
# 디렉터·모션 디자이너가 고르지 않고 자료 리서처의 증거 계획에서만 나오는 템플릿(카탈로그 표에서 뺀다)
RESEARCHER_TEMPLATES = ("evidence", "cutout_stack", "collage", "keyword_montage")

# 대본 태그 종류 → 템플릿
TAG_TO_TEMPLATE = {
    "chapter": "chapter", "keyword": "keyword", "definition": "definition", "quote": "quote",
    "list": "list", "process": "process", "cycle": "cycle", "matrix": "matrix", "compare": "compare",
    "timeline": "timeline", "stat": "stat", "venn": "venn", "pyramid": "pyramid", "photo": "photo",
}

DIAGRAM_ALIASES = {
    "더블다이아몬드": "double_diamond", "더블 다이아몬드": "double_diamond", "double diamond": "double_diamond",
    "doublediamond": "double_diamond",
    "디자인씽킹": "process", "디자인 씽킹": "process", "design thinking": "process",
    "순환": "cycle", "사이클": "cycle", "매트릭스": "matrix", "사분면": "matrix",
    "피라미드": "pyramid", "벤": "venn", "벤다이어그램": "venn", "연표": "timeline",
}

# 널리 알려진 도식의 기본 데이터
PRESET_DIAGRAMS = {
    "디자인씽킹": {"template": "process", "title": "디자인 씽킹 5단계",
                "items": ["공감", "정의", "아이디어", "프로토타입", "테스트"]},
    "design thinking": {"template": "process", "title": "Design Thinking",
                        "items": ["Empathize", "Define", "Ideate", "Prototype", "Test"]},
    "더블다이아몬드": {"template": "double_diamond", "title": "더블 다이아몬드",
                 "items": ["발견", "정의", "개발", "전달"]},
    "린": {"template": "cycle", "title": "빌드-측정-학습", "items": ["만들기", "측정", "학습"]},
    "매슬로": {"template": "pyramid", "title": "매슬로 욕구 단계",
            "items": ["생리", "안전", "소속", "존중", "자아실현"]},
    "사용성위계": {"template": "pyramid", "title": "디자인 욕구 위계",
              "items": ["기능성", "신뢰성", "사용성", "숙련성", "창의성"]},
}


def catalog_markdown() -> str:
    lines = ["| template | 이름 | 언제 | 필드 | 레이아웃 | 길이(초) |", "|---|---|---|---|---|---|"]
    for t in TEMPLATES.values():
        if t.name in RESEARCHER_TEMPLATES:
            continue
        lines.append(f"| `{t.name}` | {t.label} | {t.use} | {t.fields} | {'/'.join(t.layouts)} | "
                     f"{t.min_dur:g}–{t.max_dur:g} |")
    return "\n".join(lines)
