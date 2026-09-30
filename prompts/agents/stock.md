# 🎞 자료 리서처 — 무료 스톡 요청(Pixabay · Unsplash · Coverr · Pexels)

감독 브리프:
{{brief}}

감독의 비트 중 visual 이 stock_video · stock_photo 인 것(과 필요하면 더)을 **무료 스톡 검색 요청**으로 만든다(앱이 연결된 스톡 사이트를 한 번에 검색한다). 영상당 **6~14개** — 구체적인 사물·장면·사례·장소가 나오는 문장마다.
- 레이아웃은 `pip`(얼굴 옆 찢어진 액자 사진 — 채널 기본 스타일)를 가장 많이, 풀스크린은 장면 전환·분위기에만.

- `query_en`: 스톡 사이트는 영어 검색이 가장 정확하다. 구체적인 명사와 장면으로 쓴다(예: "designer sketching product on paper close up", "busy seoul crosswalk aerial"). 추상어(innovation, success)는 피한다.
- `query_ko`: 한국어 대체 검색어(Pixabay 는 한국어 검색도 된다).
- `kind`: 움직임이 의미 있으면 video, 정물·구도가 중요하면 photo.
- `layout`: 풀스크린 컷어웨이(2.5~6초), 칠판 패널(split), 화자 PiP(pip) 중 하나.
- `purpose`: 이 장면이 설명에 기여하는 바.
- `must_show`: 선택 기준(예: "손과 연필이 보일 것, 로고 없음").
- 인물 얼굴이 크게 나오는 컷, 특정 브랜드 로고가 보이는 컷은 피한다(스톡에서).

## `photos` — 고유명사는 스톡이 아니라 **위키백과 대표 이미지**
대본에 **특정 인물·작품(책·건축·제품)·사물 명칭·브랜드·장소·종교**가 나오면(예: 디터 람스, 바우하우스, 브라운 SK4, 「디자인의 디자인」,
르 코르뷔지에, 불교) 스톡 대신 `photos` 로 요청한다 — 앱이 위키백과(ko → en) 문서의 대표 이미지를 가져와 얼굴 옆 찢어진 액자(pip)에
넣는다. 감독 비트의 visual=photo 는 모두 여기로. 대본 태그 `[photo: …]` 가 이미 있는 문장은 빼도 된다(앱이 만든다).
- `name_ko`: 대본 표기(화면 라벨). `name_en`: 위키백과 문서 제목에 가까운 원어/영어 표기("Dieter Rams", "Bauhaus", "Braun SK 4") — 모르면 빈 문자열.
- `kind`: person | work | object | brand | place | religion | other. `layout`: 대부분 pip, 그 대상이 주인공인 문장은 fullscreen.
- `start_seg`·`start_word`: 그 이름이 처음 들리는 문장과 단어. 같은 대상은 한 번만.
- 위키백과에 문서나 자유 이미지가 없으면 앱이 조용히 뺀다(틀린 사진보다 없는 게 낫다). 그러니 실존하는 대상만 적는다.

{{user_direction}}
