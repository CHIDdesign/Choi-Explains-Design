"""스톡·자료 제공처 안내표 — 환경 설정의 표와 부가자료/못구한자료.md 가 같은 표를 본다. 키 값은 다루지 않고 있음/없음만."""
from __future__ import annotations

from typing import Any

# attr=None 은 키 없이 동작. 발급 상태는 2026-11-09 각 사이트에서 확인한 것 — 바뀌면 여기만 고친다.
SOURCES: list[dict[str, Any]] = [
    {"name": "Pixabay", "attr": "pixabay_api_key", "signup": "https://pixabay.com/api/docs/",
     "unlocks": "사진·영상·벡터, 한국어 검색", "cost": "무료",
     "note": "로그인하면 문서 안에 키가 보입니다. 사진은 긴 변 1280px", "recommended": True},
    {"name": "Google 이미지(SerpApi)", "attr": "serpapi_key", "signup": "https://serpapi.com/users/sign_up",
     "unlocks": "재사용 가능 라이선스 웹 이미지", "cost": "무료 월 250회",
     "note": "원문 페이지에서 라이선스를 다시 확인한 것만 씁니다", "recommended": True},
    {"name": "Unsplash", "attr": "unsplash_access_key", "signup": "https://unsplash.com/developers",
     "unlocks": "사진만", "cost": "무료", "note": "앱 승인을 기다려야 합니다", "recommended": False},
    {"name": "Coverr", "attr": "coverr_api_key", "signup": "https://coverr.co/developers",
     "unlocks": "영상만", "cost": "무료(시간당 50회)",
     "note": "상업 이용 문구가 문서마다 달라 불명확 — coverr.co/license 확인 후 사용", "recommended": False},
    {"name": "Pexels", "attr": "pexels_api_key", "signup": "https://www.pexels.com/api/",
     "unlocks": "사진·영상", "cost": "무료",
     "note": "새 키 발급 중단(2026-11-09 확인) — 이미 받은 키만", "recommended": False},
    {"name": "Openverse", "attr": None, "signup": "", "unlocks": "CC 사진", "cost": "무료",
     # 약관 4절: Openverse 를 쓴다는 것과 보증받지 않았다는 것을 눈에 띄게 밝힌다
     "note": "이 앱은 Openverse 를 사용하지만 Openverse 의 보증·인증을 받지 않았습니다", "recommended": False},
    {"name": "NASA", "attr": None, "signup": "", "unlocks": "우주·항공 사진·영상", "cost": "무료",
     "note": "출처 NASA 자동 표기. 제3자 권리·식별 인물 항목은 뺍니다", "recommended": False},
    {"name": "위키미디어·미술관", "attr": None, "signup": "", "unlocks": "고유명사 실물·소장품(CC0·퍼블릭 도메인)", "cost": "무료",
     "note": "시카고·메트·클리블랜드·라익스 미술관", "recommended": False},
]

# 못 구한 자리에 어떤 키가 도움이 되는가(자료 리서처의 need, 스톡은 need:종류)
HELPS = {"stock:video": ("pixabay_api_key",), "stock:photo": ("pixabay_api_key", "serpapi_key"),
         "entity": ("serpapi_key",)}


def status(settings: Any) -> list[dict[str, Any]]:
    """표의 각 줄 + state(set·empty·keyless). 키 값은 담지 않는다."""
    return [{**s, "state": "keyless" if not s["attr"] else "set" if getattr(settings, s["attr"], "") else "empty"}
            for s in SOURCES]


def key_hint(need: str, kind: str, settings: Any) -> list[str]:
    """이 자리를 채우는 데 도움이 되는데 아직 없는 키의 제공처 이름."""
    wanted = HELPS.get(f"stock:{kind or 'photo'}" if need == "stock" else need, ())
    return [s["name"] for s in status(settings) if s["attr"] in wanted and s["state"] == "empty"]
