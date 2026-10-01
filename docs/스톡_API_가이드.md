# 무료 스톡 API 가이드 (Pixabay · Unsplash · Coverr · Pexels)

🎞 자료 리서처 에이전트는 **키를 넣은 모든 스톡 사이트를 한 번에 검색**합니다. 제공처별 후보를 번갈아 섞어 요청마다 6개를 한 장의 썸네일 시트로 만들고, Claude 가 그 시트를 **직접 보고** 고릅니다. 맞는 게 없으면 넣지 않습니다.

> 하나만 넣는다면 **Pixabay** 를 추천합니다. 사진과 영상을 모두 주고, 한국어 검색이 되며, 한도가 넉넉합니다.

## 한눈에 비교 (2026-09-29, 각 공식 문서 기준)

| 제공처 | 미디어 | 무료 한도 | 출처 표기 | 상업적 이용 | 앱에서의 역할 |
|---|---|---|---|---|---|
| **Pixabay** | 사진 + 영상 | **60초당 100회** | 권장("어디서 왔는지 보여 달라") | 가능 | 기본. 한국어 검색(`lang=ko`) |
| **Unsplash** | 사진만 | 데모 **시간당 50회**(승인 뒤 1,000회) | **필수** ("Photo by 작가 on Unsplash") | 가능 | 고해상도 사진(최대 2400px로 받음) |
| **Coverr** | 영상만 | 데모 **시간당 50회**(프로덕션 2,000회는 유료 플랜) | **필수**(로고·링크) | developers 페이지는 "가능", docs 소개 페이지는 "상업적 이용 불가"로 **서로 다름** → [coverr.co/license](https://coverr.co/license) 직접 확인 | 시네마틱 영상(선택) |
| Pexels | 사진 + 영상 | 시간당 200회 | 권장 | 가능 | 이미 키가 있을 때만 |

- 찾아보신 표에서 Coverr 는 "월 1,000회"로 되어 있었지만, 현재 공식 문서(api.coverr.co/docs/start)에는 **데모 시간당 50회**로 나옵니다.
- Pixabay 사진은 일반 키로 받으면 **긴 변 최대 1280px**입니다(원본·Full HD 는 '전체 API 접근' 승인 계정만). 칠판 패널·PiP 에는 충분하고, 풀스크린 사진은 Unsplash 가 더 선명합니다. 영상은 대부분 1920×1080 으로 받습니다.

## 키 발급

### Pixabay (추천)
1. [pixabay.com](https://pixabay.com) 무료 가입 후 로그인
2. [pixabay.com/api/docs](https://pixabay.com/api/docs/) 를 엽니다. 로그인한 상태면 문서의 **Parameters → key** 항목에 **내 API 키가 이미 적혀** 있습니다(별도 신청 없음).
3. 앱 **설정 → 스톡 → Pixabay API 키**에 붙여넣기

### Unsplash (선택, 사진 품질이 중요할 때)
1. [unsplash.com/developers](https://unsplash.com/developers) → **Your apps → New Application**
2. 약관 동의 후 앱 이름(예: Choi Studio)을 적으면 **Access Key** 가 나옵니다(Secret Key 는 필요 없음).
3. 설정 → 스톡 → Unsplash Access Key
- 앱이 사진을 내려받을 때마다 Unsplash 가이드라인대로 다운로드 집계 주소를 자동으로 호출합니다.

### Coverr (선택, 영상)
1. [coverr.co](https://coverr.co) 가입 → [coverr.co/developers](https://coverr.co/developers) 에서 앱 생성 → API 키
2. 설정 → 스톡 → Coverr API 키
- 수익 채널이라면 켜기 전에 라이선스 페이지를 확인하세요(위 표 참고).

## "pixabay 를 GitHub 에서 검색하면 나오는 저장소들"은 뭔가요?

[github.com/search?q=pixabay](https://github.com/search?q=pixabay&type=repositories) 결과는 대부분 **Pixabay 가 만든 게 아닌 커뮤니티 프로젝트**입니다. Pixabay API 는 키 하나로 쓰는 단순한 웹 주소라서, 개발 입문 강의·포트폴리오 예제로 아주 많이 쓰이기 때문입니다.

| 종류 | 예 | 설명 |
|---|---|---|
| 예제 앱(가장 많음) | `bradtraversy/react-tailwind-pixabay-gallery`, `pixabay_image_finder`, `ng-pixabay-api-search`, `pixabay_flutter_demo`, 안드로이드 `pixabayapp` | React·Angular·Flutter·안드로이드 **연습용 갤러리 앱** |
| 비공식 라이브러리(래퍼) | `dderevjanik/pixabay-api`(TypeScript), `zoonman/pixabay-php-api`(PHP) | API 호출을 감싼 코드 |
| 수집기 | `pixabay-crawler` 등 | 대량 다운로드용. Pixabay 는 "체계적인 대량 다운로드 금지"라서 쓰면 안 됩니다 |
| Pixabay 공식 | `Pixabay/jQuery-autoComplete`, `Pixabay/JavaScript-PixabayWidget` | Pixabay 가 공개한 **웹 UI 부품**. API 사용과는 무관 |

**Choi Studio 는 이 저장소들이 필요 없습니다.** 공식 API 를 직접 호출하는 클라이언트(`studio/stock/pixabay.py`)가 들어 있고, 키만 넣으면 됩니다.

## 그래픽 이미지(모션 장면 안)

🎨 모션 디자이너는 장면 안 이미지 요소의 `src` 에 `pixabay:<종류>:<영어 검색어>` 를 쓸 수 있습니다. 🎞 자료 리서처 단계가 Pixabay 에서 받아 `broll/img_…` 파일로 바꿉니다(키가 없으면 사진은 Openverse).

| 종류 | 받는 것 | 화면에서 |
|---|---|---|
| `vector` | 대개 투명 배경 PNG 오브젝트·아이콘 | 오려 붙인 듯 그림자만(`frame: "cutout"`) |
| `illustration` | 그림 | 그대로 또는 액자 |
| `photo` | 사진 | 찢어진 흰 액자(`frame: "torn"`) |

못 구한 이미지는 그 요소만 빠지고 장면은 남습니다. 위키미디어에서 못 찾은 자료 사진(`photo` 템플릿)도 버리지 않고 스톡 사진 요청으로 넘깁니다.

## 앱이 지키는 규칙

- **캐시**: 같은 검색은 작업 폴더(`work/stock_cache/`)에 저장해 다시 부르지 않습니다(Pixabay: "요청은 24시간 캐시").
- **핫링크 금지**: 모든 소재를 내려받아 렌더합니다(`work/stock_raw/` → `render/public_src/broll/`).
- **출처**: 화면 오른쪽 위 “출처: …” + `업로드정보.txt` 설명란에 작가·제공처·원본 링크를 자동으로 넣습니다.
- **한도·일시 차단**: 429(한도 초과)면 기다렸다 다시 시도합니다. 일시 차단(403)·연결 실패는 잠깐 쉬었다가 다음 검색에서 다시 쓰고(3번 연속이면 그 작업에서 제외), **키가 틀릴 때만** 곧바로 그 제공처를 뺍니다. 예전에는 한 번 막히면 작업 끝까지 빠져서 뒤 요청이 전부 '후보 없음'이 됐습니다.
- **내려받기**: Pixabay CDN 은 몰아서 받으면 잠시 403 을 줍니다. `studio/net.py` 가 호스트별 간격을 두고, requests → urllib(브라우저 UA) → curl 순으로 방식을 바꿔 다시 받으며, 실패 이유를 `진단.md` 에 남깁니다.
- **검색어**: 긴 묘사형 검색어는 결과가 0~1건이라 핵심 명사만 남을 때까지 줄여 가며 다시 검색하고, 그래도 없으면 한국어 검색어로 찾습니다.
- **캐시의 '없음'**: 에이전트가 직접 뺀 요청만 확정합니다. 검색 0건·네트워크·다운로드 실패는 다음 실행에 다시 시도합니다.
- **안전**: Pixabay `safesearch=true`, Unsplash `content_filter=high`, Unsplash+(유료) 사진 제외, 세로 영상 제외.
- 알아볼 수 있는 인물·상표가 크게 나오는 컷은 피하라고 에이전트에게 지시하지만, 업로드 전 최종 확인은 직접 하세요(스톡 라이선스도 초상권·상표권까지 보장하지는 않습니다).

## 출처

- Pixabay API 문서: https://pixabay.com/api/docs/
- Unsplash API 문서: https://unsplash.com/documentation
- Coverr API: https://api.coverr.co/docs/start/ · https://api.coverr.co/docs/videos/ · https://coverr.co/developers
