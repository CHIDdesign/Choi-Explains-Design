# Choi Studio 워크플로 확장용 MCP 서버 리서치

- 조사 기준일: **2026-09-29**
- 대상 워크플로: Python(PySide6) 파이프라인 + Remotion 4.0.530 렌더, Claude API 감독(director) 에이전트, Pexels B-roll, 모션그래픽·자막·썸네일 자동화, Premiere용 FCP7 XML 내보내기(`studio/export/premiere.py`), Windows 우선 환경. Claude Code와 Claude Desktop 병행 사용.
- 범위: 조사만 했고 아무것도 설치하지 않았습니다.

---

## 0. 먼저 알아둘 것 (전제 바로잡기와 핵심 발견)

1. **Remotion MCP 서버는 지원 종료(deprecated)됐습니다.** Remotion 공식 문서에 따르면 종료 시점은 "2026-08-31 이후"이고, 대체재로 **Remotion Agent Skills**(`npx remotion skills add`)를 권합니다. [공식 자료] 기준일(2026-09-29)에 서버가 실제로 꺼졌는지는 확인하지 못했습니다.
2. **ElevenLabs 로컬 MCP(`elevenlabs/elevenlabs-mcp`)는 저장소가 보관(archived)됐고**, 호스팅 MCP(`https://api.elevenlabs.io/v1/mcp`, OAuth)로 옮기라고 안내합니다. 다만 호스팅 서버 공식 문서가 밝히는 범위는 "에이전트 관리 + TTS"입니다. 효과음(SFX)·음악·STT·음성 복제 도구는 **보관된 로컬 서버**에 있습니다. [공식 자료] 한편 공식 MCP 레지스트리의 `io.elevenlabs/mcp` 설명에는 "speech, music, sound effects, images, video"가 적혀 있어 **문서와 서로 맞지 않습니다** → 연결한 뒤 실제 도구 목록을 확인해야 합니다.
3. **Notion 오픈소스 로컬 서버(`makenotion/notion-mcp-server`)는 더 이상 적극 유지보수되지 않습니다.** 공식적으로는 원격 Notion MCP(`https://mcp.notion.com/mcp`)를 권장합니다. [공식 자료]
4. **공식 YouTube MCP는 없습니다.** Google 관리형 MCP 목록(Drive, Gmail 등)에 YouTube는 빠져 있습니다. [2차 인용] 그래서 커뮤니티 서버를 써야 하는데, 대부분 스타 수가 적고 성숙도가 낮습니다.
5. **썸네일 CTR은 이제 API로 받을 수 있습니다.** YouTube Reporting API의 reach 리포트(`channel_reach_basic_a1`, `channel_reach_combined_a1`)에 `video_thumbnail_impressions`, `video_thumbnail_impressions_ctr` 지표가 들어 있습니다(2026-01-15 추가). [공식 자료] 반면 YouTube Studio "Test & Compare"(썸네일 A/B 테스트) 결과를 주는 API는 **찾지 못했습니다.**
6. **2026-04-28 Anthropic이 크리에이티브 커넥터 9종을 출시했습니다.** Adobe for creativity, Blender, Affinity by Canva, Autodesk Fusion, SketchUp, Splice, Ableton, Resolume 등이 포함됩니다. [공식 자료: anthropic.com/news/claude-for-creative-work] 이 가운데 Blender 커넥터는 Blender Lab의 공식 MCP 서버를 쓴다고 알려져 있습니다. [2차 인용]
7. **Higgsfield MCP는 이 Claude 세션에 이미 연결돼 있습니다.** 세션의 도구 목록에서 `generate_video`, `virality_predictor`, `tiktok_prepare_publish` 같은 도구 이름을 직접 확인했습니다. 계정 크레딧이 소모될 수 있어 도구를 호출해 보지는 않았습니다.
8. `blender-mcp`(ahujasid)는 **`mcp-for-blender`로 이름이 바뀌었습니다.** 기존 `uvx blender-mcp` 설정도 계속 동작합니다. [README]

---

## 1. 표기 규칙

| 표기 | 의미 |
|---|---|
| [공식 자료] | 벤더 공식 문서나 벤더 소유 GitHub README를 이번에 직접 읽고 확인함 |
| [README] | 커뮤니티 저장소 README를 이번에 직접 읽고 확인함 (raw.githubusercontent.com) |
| [2차 인용] | 검색 결과 스니펫이나 제3자 블로그만 확인함. 원문 확인 필요 |
| [해석] | 조사자가 이 워크플로에 적용해 추론한 내용 |
| [미확인] | 확인하지 못함 |

- ★ 수와 업데이트 날짜는 2026-09-29에 GitHub 검색 API로 조회한 값입니다. npm·PyPI 버전과 게시일은 각 레지스트리 JSON으로 확인했습니다.
- 접근이 막혔던 곳: pexels.com(403), projects.blender.org(403), api.github.com(403). 대신 GitHub MCP 검색과 raw 파일을 썼습니다.
- 공식 MCP 레지스트리(`registry.modelcontextprotocol.io/v0/servers?search=`)에는 접속했지만, 일부 검색(runway, blender)은 타임아웃이 났습니다.

---

## 2. 우선순위 표

추천도는 이 채널(디자인 교육, 토킹헤드 + 모션그래픽, 쇼츠)에 얼마나 맞는지를 기준으로 매겼습니다. **상** = 바로 써볼 가치가 큼, **중** = 조건이 맞으면 유용, **하** = 참고용이거나 위험·비용 대비 이득이 적음.

| 추천도 | 서버 | 분류 | 관리 주체 | 인증 | 비용 | 라이선스 | 성숙도 신호 | 이 워크플로에서의 쓰임 |
|---|---|---|---|---|---|---|---|---|
| **상** | Figma MCP (`https://mcp.figma.com/mcp`) | 디자인 | **공식**(Figma) | OAuth(클라이언트 로그인) | Starter 플랜과 View/Collab 시트는 **월 6회 호출 제한**. 캔버스 쓰기는 베타 기간 무료 | 서비스 약관 | 레지스트리 `com.figma.mcp/mcp` 1.0.3, 가이드 저장소 2.0k★ | 디자인 사례 프레임 캡처, 디자인 토큰을 Remotion 테마로, 모션 컨텍스트(`get_motion_context`) 추출, 썸네일 템플릿 |
| **상** | Canva MCP (`https://mcp.canva.com/mcp`) | 디자인·썸네일 | **공식**(Canva) | OAuth(사용자별) | 기본 기능은 무료 플랜 포함. 리사이즈·브랜드킷·autofill은 Pro 이상 | 서비스 약관 | 레지스트리 `com.canva.mcp/mcp` | 썸네일 시안 생성·편집·PNG 내보내기, 쇼츠 커버 리사이즈 |
| **상** | Remotion Agent Skills (MCP 대체) | 모션그래픽 | **공식**(Remotion) | 없음 | 무료 (Remotion 자체 라이선스는 별도) | 저장소에 LICENSE 파일 없음 [미확인] | 4.8k★ | Claude Code가 `renderer/` 템플릿을 고칠 때 최신 Remotion 모범사례 참조 |
| **상** | claude-video-vision | 영상 이해(QA) | 커뮤니티 | 로컬 Whisper 선택 시 키 불필요. Gemini/OpenAI 백엔드 선택 시 키 필요 | 무료 (백엔드 API 비용 별도) | MIT | 1.3k★, npm 1.3.2 | 렌더된 MP4를 Claude가 **직접 보고** 자막 겹침·그래픽 타이밍을 점검 |
| **상** | Playwright MCP | 브라우저 | **공식**(Microsoft) | 없음 | 무료 | Apache-2.0 | 37.7k★, npm 0.0.83 (09-28) | 웹 디자인 사례 스크린샷, 스크롤 **영상 녹화**(`browser_start_video`)로 B-roll 확보 |
| **상** | Exa MCP (`https://mcp.exa.ai/mcp`) | 웹 리서치 | **공식**(Exa) | 익명 사용 가능(속도 제한). OAuth나 API 키로 한도 상향 | 익명 무료, 유료 요금제 [미확인] | MIT | 5.1k★ | 대본 팩트체크, 디자인사 레퍼런스 검색 |
| **상** | YouTube 읽기 전용: kirbah/mcp-youtube, jkawamoto/mcp-youtube-transcript | YouTube 분석 | 커뮤니티 | 자막은 키 불필요. 검색·통계는 API 키 필요 | 무료 (API 할당량 10,000/일) | MIT | 29★ / 486★ | 경쟁·레퍼런스 채널 분석, 한국어 자막(`lang=ko`) 수집 |
| 중 | Firecrawl MCP | 웹 리서치 | **공식** | 키 없이 scrape/search/parse만. 키나 OAuth로 26개 도구 전부 | 키리스 무료 등급 + 크레딧 | MIT | 7.5k★, npm 3.26.0 | 긴 아티클·문서 크롤링 (Exa 대신 쓸 수 있음) |
| 중 | Brave Search MCP | 웹 리서치 | **공식**(Brave) | API 키 | 1,000건당 $5, **매월 $5 무료 크레딧** | MIT | 1.5k★ | 이미지·비디오·뉴스 검색 |
| 중 | Notion MCP (`https://mcp.notion.com/mcp`) | 지식·노트 | **공식** | OAuth | 일부 도구는 Business 플랜이나 Notion AI 필요 | 서비스 약관 | 레지스트리 `com.notion/mcp` | 대본 DB, 콘텐츠 캘린더, 업로드 체크리스트 |
| 중 | Google Drive MCP (`https://drivemcp.googleapis.com/mcp/v1`) | 지식·파일 | **공식**(Google) | OAuth | [미확인] | 서비스 약관 | **Developer Preview** | 원본 촬영본·대본 파일 검색·읽기 |
| 중 | Obsidian: Local REST API 플러그인(MCP 내장), mcpvault | 지식·노트 | 커뮤니티 | 로컬 Bearer 토큰 / 없음 | 무료 | MIT | 3.0k★ / 1.7k★ | Obsidian으로 강의 노트를 관리한다면 연결 |
| 중 | YouTube 관리(쓰기 가능): pauling-ai/youtube-mcp-server, i1s-abhishek/youtube-studio-mcp | YouTube 운영 | 커뮤니티 | Google OAuth(데스크톱 클라이언트) | 무료 (할당량) | MIT | 23★ / 17★ (**성숙도 낮음**) | 메타데이터·썸네일 교체, 댓글, Analytics와 reach 리포트(CTR) |
| 중 | anwerj/youtube-uploader-mcp | 업로드 | 커뮤니티 | Google OAuth | 무료 | MIT | 55★ | 비공개 업로드와 예약 공개, 썸네일·자막 첨부 |
| 중 | Pexels MCP (garylab / CaullenOmdahl) | 스톡 | 커뮤니티 | API 키 | 무료 (200건/시간, 20,000건/월) [2차 인용] | README 표기 MIT / ISC | 25★ / 9★ | Claude Code에서 대화형으로 B-roll 후보 탐색 (앱에는 이미 Pexels 통합이 있음) |
| 중 | open-museum-mcp | 저작권 안전 이미지 | 커뮤니티 | 대부분 키 불필요 | 무료 | MIT | 13★ (2026-04 신규) | **디자인사·명화 자료**(CC0/PD만 반환) + 인용문 자동 생성 |
| 중 | Wikimedia image search / Openverse MCP | 스톡(CC) | 커뮤니티 | 없음 | 무료 | MIT | 3★ / 18★ | 역사적 디자인 자료, CC 라이선스 필터 |
| 중 | Unsplash MCP (hellokaton / cevatkerim) | 스톡 | 커뮤니티 | Access Key | 무료 (데모 50건/시간) | MIT | 237★ / 29★ | 사진 B-roll, 출처 표기 문자열 자동 생성 |
| 중 | ElevenLabs (호스팅 / 로컬 보관본) | 음성·SFX·음악 | **공식** | 호스팅은 OAuth, 로컬은 API 키 | 크레딧 (로컬 README 기준 무료 월 10k 크레딧) | 로컬 MIT | 로컬 1.5k★ (보관됨) | 모션그래픽 효과음, 쇼츠 BGM, `isolate_audio`로 잡음 제거 |
| 중 | Higgsfield MCP (`https://mcp.higgsfield.ai/mcp`) | AI 영상·이미지·오디오 | **공식** | 계정 로그인 ("no API key required") | 크레딧 [상세 미확인] | 서비스 약관 | 이 세션에 이미 연결돼 있음 | 생성 B-roll, `virality_predictor`, TikTok 게시 |
| 중 | fal.ai MCP (`https://mcp.fal.ai/mcp`) | AI 생성 (1,000개 이상 모델) | **공식** | `Authorization: Bearer FAL_KEY` | 종량제, `get_pricing` 도구 제공 | 서비스 약관 | 공식 문서 확인 | 필요할 때만 이미지·영상·음악 생성, 배경 제거 |
| 중 | Runway MCP (`https://mcp.runwayml.com/mcp`) | AI 영상 | **공식** | OAuth 2.1 | Runway 요금제 크레딧 차감 | 플러그인 MIT | 로컬 서버 23★ | 이미지 → 영상, 영상 편집(Aleph) |
| 중 | Kinocut | FFmpeg 편집 | 커뮤니티 | 없음 | 무료 | Apache-2.0 | 177★, PyPI 1.15.3 (09-25), 레지스트리 등재 | 쇼츠 재가공, 자막 번인, 결과물 품질 게이트 |
| 중 | DaVinci Resolve MCP (samuelgursky) | NLE | 커뮤니티 | 없음 (로컬) | 무료. 외부 스크립팅에는 **Resolve Studio** 필요 | MIT | 3.2k★, npm 4.8.22 | Resolve로 마무리 작업을 한다면 사용 |
| 중 | Premiere Pro MCP (hetpatel-11) | NLE | 커뮤니티 | 없음 (로컬 CEP 브리지) | 무료 | MIT | 626★, npm 1.2.8 | 앱이 내보낸 FCP7 XML을 Premiere로 가져온 뒤 마무리 보정 |
| 중 | Adobe for creativity (Claude 커넥터) | Adobe 앱 전반 | **공식**(Adobe) | Adobe 로그인 | 설치·사용 무료, 로그인하면 한도 상향 | 서비스 약관 | 2026-04-28 출시 | 썸네일 인물 리터칭(Photoshop), 영상 비율 변환(Premiere/Express) |
| 중 | Postiz (호스팅 MCP) | 소셜 배포 | 커뮤니티 기업 | OAuth | 클라우드는 유료 [미확인], 셀프호스팅 가능 | 앱은 AGPL-3.0 | 앱 36.5k★ | 쇼츠를 Reels·TikTok 등으로 크로스포스팅, 예약 |
| 하 | Replicate MCP (`https://mcp.replicate.com`) | AI 생성 | **공식** | API 토큰 | 종량제 | npm은 Apache-2.0 | npm 최신 0.9.0 (2025-06) | 모델 탐색 (fal과 역할이 겹침) |
| 하 | MiniMax MCP | TTS·영상·이미지 | **공식** | API 키 (리전별 호스트) | 종량제 | MIT | 1.6k★ | TTS와 음성 디자인 (README는 이제 자사 CLI를 권장) |
| 하 | Stability AI MCP (tadasant) | 이미지 | 커뮤니티 (**비공식**) | API 키 | 무료 25크레딧, 이후 크레딧당 $0.01 | MIT | 84★ | 배경 제거, 아웃페인팅 |
| 하 | Luma API MCP | AI 영상 | **공식**(Luma) | API 키 | 종량제 | MIT | 26★, README가 빈약함 | 참고용 |
| 하 | Google genmedia MCP (Veo·Lyria·TTS) | AI 생성 | Google 샘플 ("**not an officially supported Google product**") | GCP 프로젝트 | Vertex AI 과금 | Apache-2.0 | 저장소 1.2k★ | GCP를 이미 쓰고 있을 때만 |
| 하 | After Effects MCP (Dakkshin) | 모션그래픽 | 커뮤니티 | 없음 | 무료 | MIT | 672★ | Remotion으로 표현하기 어려운 모션에만 |
| 하 | CapCut 계열 (VectCutAPI, capcut-ai-editor) | 편집 초안 | 커뮤니티 (공식 없음) | 없음·클라우드 | 무료·클라우드 | Apache-2.0 / MIT | 2.3k★ / 115★ | CapCut 초안 생성 (현재 파이프라인과 겹침) |
| 하 | Blender: Blender Lab 공식 / mcp-for-blender | 3D | 공식 / 커뮤니티 | 없음 | 무료 | GPL-3.0 이상 [2차 인용] / MIT | Lab v1.0.3 / 29.6k★ | 형태·조명 원리를 3D로 시연하는 장면 |
| 하 | ig-mcp (Instagram Graph API) | 소셜 | 커뮤니티 | Meta 장기 토큰 + 권한 다수 | 무료 | MIT | 195★ | 비즈니스 계정 게시와 인사이트 |
| 하 | Taisly Agent | 소셜 배포 | 커뮤니티 기업 | 계정 | 무료로 시작 가능, 확장은 유료 | MIT | 215★, 레지스트리 등재 | TikTok, Reels, Shorts 게시 |
| 하 | Memory (reference) / basic-memory | 메모리 | 공식 레퍼런스 / 커뮤니티 | 없음 | 무료 | Apache/MIT 전환 중 / AGPL-3.0 | 90.7k★(모노레포) / 4.1k★ | 채널 톤·결정 기록 (CLAUDE.md로도 충분) |
| 하 | Chrome DevTools MCP | 브라우저 | 공식(Google) | 없음 | 무료 | Apache-2.0 | 52.7k★ (사용 통계 수집이 기본) | Playwright와 역할이 겹침 |
| 하 | Context7 (`https://mcp.context7.com/mcp`) | 라이브러리 문서 | 커뮤니티 기업(Upstash) | 선택 | 무료 등급 | MIT | 62.5k★ | PySide6 등의 문서 조회 (Remotion은 Skills 권장) |

---

## 3. 서버별 상세

### 3-1. 스톡·오픈 라이선스 미디어

**Pexels**
- 공식 MCP는 없습니다. 레지스트리에도 커뮤니티 5종(codeChap, developer-ishan, hanoak, mrfentmen, pipeworx-io)만 있습니다. [공식 자료: 레지스트리 검색]
- `garylab/pexels-mcp-server` (Python, PyPI `pexels-mcp-server` 0.0.4, 2025-09-15, 25★) [README]
  - 도구: `photos_search`, `photos_curated`, `photo_get`, `videos_search`, `videos_popular`, `video_get`, `collections_featured`, `collections_media`
  - 인증: `PEXELS_API_KEY`
  - 라이선스: README에 MIT로 표기돼 있지만 루트에 LICENSE 파일은 없습니다.
- `CaullenOmdahl/pexels-mcp-server` (TypeScript, 9★, README 표기 ISC) [README]
  - 도구: `searchPhotos`, `downloadPhoto`, `searchVideos`, `downloadVideo`, `getPopularVideos`, `getCollectionMedia` 등
  - 응답에 출처 표기 정보와 **남은 요청 한도**가 함께 담깁니다.
- Pexels API 조건: 무료, 기본 200건/시간·20,000건/월, 출처 표기를 갖추면 한도 상향 가능 [2차 인용: pexels.com이 403으로 막혀 검색 스니펫만 확인]
- 워크플로 연결 [해석]: 앱의 `studio/stock/pexels.py`가 이미 자동 검색을 합니다. MCP는 Claude Code에서 "이 구간에 맞는 세로 영상 5개 후보"처럼 **사람이 보고 고르는 탐색용**으로 적합합니다. 앱과 **다른 API 키**를 써서 할당량 충돌을 피하세요.

**Pixabay**
- `Unlock-MCP/pixabay-mcp-server` (10★, MIT), `zym9863/pixabay-mcp` (9★, MIT) [README]
  - zym9863 도구: `search_pixabay_images`, `search_pixabay_videos` (영상 길이 필터 지원)
- API 조건 [공식 자료]: 무료, 60초당 100건, **응답을 24시간 캐시해야 함**, 영구 핫링크 금지, 출처 노출 요청

**Unsplash**
- `hellokaton/unsplash-mcp-server` (237★, MIT, 검색 중심) [README]
- `cevatkerim/unsplash-mcp` (29★, MIT) [README]: `attribution_text`/`attribution_html`을 자동 생성하고 다운로드 트래킹을 지원합니다.
- API 조건 [공식 자료]: 무료, 데모 50건/시간, 프로덕션 1,000건/시간. **이미지 URL 핫링크가 의무**이고, 다운로드할 때마다 download 엔드포인트를 호출해야 합니다.
- [해석] 영상에 넣으려면 파일을 내려받아야 하므로, 다운로드 트래킹을 지원하는 서버를 고르는 편이 안전합니다.

**Openverse / Wikimedia / 박물관**
- `neno-is-ooo/mcp-openverse` (18★, MIT) [README]
  - 도구: `search_images`(`license_type=commercial`/`modification` 필터), `get_image_details`, `get_related_images`, `search_images_for_essay`
  - README의 설치 명령은 `@mcp/openverse`이지만, 이 이름의 패키지는 **npm에 없습니다** → 소스에서 빌드해야 합니다.
- `yanexr/wikimedia-image-search-mcp` (3★, MIT, npm 1.0.2) [README]
  - 단일 도구 `wikimedia_search_images`
  - **썸네일 합성 이미지**를 돌려줘서 Claude가 후보를 눈으로 비교할 수 있습니다.
- `cfpramod/open-museum-mcp` (13★, MIT) [README]
  - 대상: Met, Rijksmuseum, Smithsonian, Cleveland, AIC, SMK, Walters, Wellcome, NGA, Harvard, Getty, Wikimedia Commons, Europeana
  - **권리가 모호한 레코드는 버리는(strict-deny) 방식**이라 CC0/PD 등만 반환합니다.
  - 도구: `search_artworks`, `get_artwork`, `cite`
  - [해석] 디자인사 강의(바우하우스 포스터, 고전 회화 구도 분석 등)에 특히 잘 맞습니다. 다만 신생 프로젝트라 결과를 사람이 검수해야 합니다.
- 레지스트리의 `com.wikimedia.enterprise/docs`는 이름으로 보아 문서용 항목으로 보입니다. 상세는 [미확인]입니다.

### 3-2. AI 생성 (이미지·영상·음성·음악·SFX)

**ElevenLabs** [공식 자료]
- 호스팅 서버
  - 주소: `https://api.elevenlabs.io/v1/mcp` (EU·인도·싱가포르 리전 URL 별도)
  - 인증: OAuth. Claude Desktop에서는 Settings → Connectors → "ElevenLabs"로 연결합니다.
  - 문서가 밝히는 범위: 에이전트 생성·관리·대화 기록 + **TTS**(단기 다운로드 링크로 반환)
  - 툴별 승인 설정을 할 수 있습니다.
- 로컬 서버 `elevenlabs/elevenlabs-mcp` (**보관됨**, MIT, PyPI 0.12.2)
  - 소스 코드에서 확인한 도구: `text_to_speech`, `speech_to_text`, `text_to_sound_effects`, `voice_clone`, `isolate_audio`, `speech_to_speech`, `text_to_voice`, `compose_music`, `create_composition_plan`, `video_to_music`, `play_audio`, `check_subscription` 등
  - `ELEVENLABS_MCP_BASE_PATH`가 입력 파일 접근 경계 역할을 합니다.
- 워크플로 연결 [해석]
  - 모션그래픽 등장음(whoosh, UI 클릭)을 `text_to_sound_effects`로 만듭니다.
  - 쇼츠 BGM은 `compose_music`으로 만듭니다.
  - 잡음 섞인 원본 녹음은 `isolate_audio`로 정리합니다. **단 앱의 샘플 단위 오디오 컷보다 먼저 적용해야 싱크 규칙을 지킬 수 있습니다.**
  - 보관된 서버는 향후 호환성이 보장되지 않습니다.

**Higgsfield** [공식 자료: higgsfield.ai/mcp + 이 세션의 도구 목록]
- 주소: `https://mcp.higgsfield.ai/mcp`, 인증: "no API key required"(계정 로그인)
- 이 세션에서 확인한 도구 이름
  - 생성: `generate_image`, `generate_video`, `generate_audio`, `create_voice`, `dubbing`, `voice_change`
  - 보정: `upscale_video`, `reframe`, `remove_background`, `outpaint_image`, `generate_3d`
  - 쇼츠·분석: `shorts_studio_create`, `video_analysis_create`, `virality_predictor`
  - TikTok: `tiktok_connect`, `tiktok_prepare_publish`, `tiktok_publish_status`, `tiktok_music_trending`
  - 계정: `balance`, `show_plans_and_credits`
  - 그 밖에 `sandbox_exec`, `deploy_website`, `website_secrets` 같은 **범용 실행·배포 도구**도 들어 있습니다.
- 요금: 크레딧 기반. 무료 크레딧 여부는 [미확인]
- 워크플로 연결 [해석]: 이미 연결돼 있으므로 가장 빠르게 시험할 수 있습니다. `reframe`(16:9 → 9:16)과 `virality_predictor`(쇼츠 사전 점검)가 쓸 만합니다. 반면 `sandbox_exec`, `website_secrets` 등은 이 워크플로에 필요 없으니 Claude 커넥터 설정에서 **꺼 두기를 권합니다.**

**Runway**
- 호스팅: `https://mcp.runwayml.com/mcp`, OAuth 2.1 + PKCE, 이용자의 Runway 요금제 크레딧을 씁니다. [공식 자료: runwayml/runway-mcp-plugin README]
- 로컬: `runwayml/runway-api-mcp-server` (23★, MIT) [README]
  - 도구: `runway_listModels`, `runway_generateVideo`, `runway_generateImage`, `runway_upscaleVideo`, `runway_editVideo`, `runway_generateAudio`, `runway_getTask`, `runway_cancelTask`, `runway_getOrg`
  - API 키와 결제 수단 등록이 필요합니다.

**fal.ai** [공식 자료: fal.ai/docs/model-apis/mcp]
- 주소: `https://mcp.fal.ai/mcp`, 인증: `Authorization: Bearer <FAL_KEY>`
- 도구 11개: `search_models`, `get_model_schema`, `get_pricing`, `search_docs`, `run_model`, `submit_job`, `check_job`, `get_job_result`, `cancel_job`, `upload_file`, `recommend_model`
- Claude Code 연결: `claude mcp add --transport http fal-ai https://mcp.fal.ai/mcp --header "Authorization: Bearer $FAL_KEY"`
- 커뮤니티 `luminarylane/fal-mcp-server` (57★, MIT) [README]: 도구 18개. `resize_image`(YouTube/TikTok 규격), `remove_background`, `generate_music`, `get_usage` 등이 있습니다.

**Replicate** [공식 자료: replicate.com/docs/reference/mcp]
- 원격: `https://mcp.replicate.com` (웹 인증 흐름에서 API 토큰 입력)
- 로컬: npm `replicate-mcp` (Apache-2.0)
- "code mode"(`--tools=code`, Deno 샌드박스)는 실험 기능입니다.
- 커뮤니티 `deepfates/mcp-replicate`는 보관됐습니다.

**MiniMax** [공식 자료: README]
- `MiniMax-AI/MiniMax-MCP` (1.6k★, MIT)
- 도구: `text_to_audio`, `list_voices`, `voice_clone`, `voice_design`, `generate_video`, `query_video_generation`, `text_to_image`
- **API 키와 호스트 리전이 맞아야 합니다**(글로벌 `api.minimax.io`).
- README 상단에서 자사 CLI(mmx-cli)를 우선 권장합니다.

**Stability AI** [README]
- 공식 MCP는 찾지 못했습니다.
- `tadasant/mcp-server-stability-ai` (84★, MIT, "NOT officially affiliated")
- 도구 12개: `generate-image`, `remove-background`, `outpaint`, `search-and-replace`, `upscale-creative`, `replace-background-and-relight` 등. README에 도구별 예상 비용이 있습니다.

**Luma** [README]
- `lumalabs/luma-api-mcp` (26★, MIT)
- Photon(이미지)과 Ray(영상) 생성을 지원하지만, README가 짧고 모델 목록(ray-2)이 오래돼 보입니다.

**Google genmedia** [공식 자료: README]
- `GoogleCloudPlatform/genmedia-creative-studio` 저장소의 `experiments/mcp-genmedia`
- 지원: Gemini Image, Veo 3/3.1, Gemini TTS/Chirp 3 HD, Lyria, AVTool(합성·편집)
- 설치는 `curl … | bash` 방식입니다.
- 저장소 README가 "not an officially supported Google product", "demonstration purposes only"라고 밝힙니다.

### 3-3. 영상 도구

**Remotion** [공식 자료]
- MCP 서버(`remotion-documentation`)는 deprecated입니다.
- 공식 이유: 중복된 기능, 문서 최신성 부족, 토큰 비용, 에이전트가 MCP를 불안정하게 호출함
- **대체: `npx remotion skills add`** (또는 `npx skills add remotion-dev/skills`)
- 스킬 목록: `/remotion-best-practices`, `/remotion-create`, `/remotion-markup`, `/remotion-studio`, `/remotion-render`, `/remotion-captions`, `/remotion-maps`, `/remotion-interactivity` 등
- 레지스트리에서 "remotion"으로 검색한 결과: 0건
- 워크플로 연결 [해석]
  - `renderer/`에 스킬을 설치하면 `graphics/` 템플릿을 고칠 때 `useCurrentFrame()`/`interpolate()` 규칙과 최신 API를 참조하게 됩니다.
  - 단 CLAUDE.md가 4.0.530에 고정돼 있으므로, 스킬이 더 새 버전 API를 제안하면 걸러내야 합니다.
- 참고로 HeyGen의 **HyperFrames**(54k★, Apache-2.0)는 HTML을 MP4로 만드는 프레임워크입니다. Claude Code 플러그인과 스킬 21개를 제공하고 `/remotion-to-hyperframes` 이식 스킬도 있지만, 자체 MCP 서버는 아닙니다. 현재 Remotion 파이프라인을 바꿀 이유는 없어 보입니다. [README, 해석]

**FFmpeg 계열**
- `KyaniteLabs/kinocut` (177★, Apache-2.0, PyPI 1.15.3 2026-09-25, 레지스트리 `io.github.KyaniteLabs/kinocut`) [README]
  - 예전 이름은 mcp-video입니다.
  - 트림, 자막, 세로 변환, 품질 게이트, "Video Receipts"(작업 이력)를 **타입이 정해진 도구**로 제공합니다. 로컬에서 FFmpeg가 PATH에 있어야 합니다.
- `misbahsy/video-audio-mcp` (87★, MIT) [README]
  - `remove_silence`, `add_subtitles`, `add_b_roll`, `concatenate_videos`, `change_aspect_ratio` 등 도구 27개
- `egoist/ffmpeg-mcp` (120★): npm 0.0.3(2025-03), LICENSE 파일 없음 → 하
- 워크플로 연결 [해석]: 앱에 이미 정교한 FFmpeg 단계가 있으므로 MCP는 **마스터 이후의 부가 작업**에만 씁니다. 예: 쇼츠 파생본, 라우드니스 검사, 비교용 GIF. 마스터 오디오를 다시 인코딩하는 작업은 CLAUDE.md의 싱크 규칙과 충돌할 수 있습니다.

**영상 이해 (렌더 QA·레퍼런스 분석)**
- `jordanrendric/claude-video-vision` (1.3k★, MIT, npm 1.3.2) [README]
  - Claude Code 플러그인입니다. ffmpeg로 프레임을 뽑고, 오디오는 Gemini·로컬 Whisper·OpenAI 중 하나로 받아씁니다.
  - YouTube URL을 넣으면 yt-dlp로 받아서 처리합니다.
- `guimatheus92/mcp-video-analyzer` (80★, MIT) [README]
  - `analyze_video` 하나로 자막, 키프레임, OCR, 메타데이터를 돌려줍니다.
- [해석] 저장소에 `docs/research/레퍼런스_채널_편집스타일_리서치.md`가 있는 것으로 보아 **레퍼런스 편집 스타일 분석**을 이미 하고 있습니다. 이 작업을 반자동화할 수 있습니다.

**DaVinci Resolve** [README]
- `samuelgursky/davinci-resolve-mcp` (3.2k★, MIT, npm 4.8.22)
- 기본 도구 37개(전체 모드 389개)로 공식 Scripting API를 100% 다룹니다.
- **외부 스크립팅은 Studio 에디션 전용**입니다. 무료판 브리지는 21.0.x까지만 동작하고, 21.1부터는 Python 스크립팅이 Studio로 옮겨졌습니다.
- 설치 도구가 Claude Desktop/Code 설정까지 자동으로 해 줍니다.

**Premiere Pro / After Effects / Adobe**
- `hetpatel-11/Adobe_Premiere_Pro_MCP` (626★, MIT, npm `adobe-premiere-pro-mcp` 1.2.8) [README]
  - 도구 283개를 `search_tools`/`invoke_tool` 뒤에 두는 구조이고, CEP 패널 브리지로 동작합니다.
  - **익명 텔레메트리가 기본으로 켜져 있습니다.** 끄려면 `PREMIERE_MCP_TELEMETRY=0` 또는 `DO_NOT_TRACK=1`을 설정합니다.
  - Claude Code처럼 도구 검색을 지원하는 호스트에서는 `PREMIERE_MCP_TOOLSET=full`을 권장합니다.
- `leancoderkavy/premiere-pro-mcp` (302★, MIT, 레지스트리 등재)
- `Dakkshin/after-effects-mcp` (672★, MIT) [README]: ExtendScript로 컴포지션, 텍스트·셰이프 레이어, 키프레임을 다룹니다.
- **Adobe for creativity** 커넥터 (2026-04-28, 공식) [공식 자료: blog.adobe.com, claude.com/connectors]
  - 대상 앱: Photoshop, Illustrator, Firefly, Express, Premiere, Lightroom, InDesign, Stock (claude.com 페이지는 Acrobat도 포함)
  - 도구 수: Adobe 블로그는 "50+", claude.com 페이지는 "67+"라고 적고 있어 **수치가 서로 다릅니다.**
  - 설치·사용은 무료이고, Adobe로 로그인하면 한도가 늘어납니다.
  - Claude Code에서 직접 연결할 수 있는 URL은 [미확인]입니다.
- 워크플로 연결 [해석]: 앱이 FCP7 XML을 내보내므로 **"자동 편집 → Premiere에서 사람이 마무리"** 단계에서 Premiere MCP로 마커 점검이나 시퀀스 설정 확인을 맡길 수 있습니다. 썸네일 인물 보정은 Adobe 커넥터(Photoshop)로 하면 됩니다.

**CapCut**
- 공식 MCP는 없습니다.
- `sun-guannan/VectCutAPI` (2.3k★, Apache-2.0) [README]: CapCut/剪映(Jianying) 초안 파일을 만들고, MCP 도구 11개를 제공합니다. 클라우드 버전(vectcut.com)도 있습니다.
- `mrbuslov/capcut-ai-editor` (115★, MIT): 휴지(pause) 제거, 중복 테이크 감지, 자막 생성 후 CapCut 프로젝트로 내보냅니다.
- [해석] 현재 파이프라인과 기능이 겹쳐서 우선순위는 낮습니다.

### 3-4. 디자인 도구

**Figma (공식 원격)** [공식 자료: figma/mcp-server-guide README + developers.figma.com]
- 연결
  - `claude plugin install figma@claude-plugins-official` (Claude Code 권장. 스킬 포함)
  - 또는 `claude mcp add --transport http figma https://mcp.figma.com/mcp`
- 읽기 도구
  - `get_design_context`, `get_screenshot`, `get_metadata`, `get_variable_defs`
  - **`get_motion_context`**(키프레임 애니메이션 데이터와 코드 스니펫)
  - `download_assets`, `search_design_system`, `get_figjam`, `get_libraries`, `whoami`
- 쓰기 도구: `use_figma`, `generate_figma_design`, `create_new_file`, `upload_assets`, `generate_diagram`(Mermaid → FigJam), 셰이더 관련 도구, Weave 워크플로 도구
- 제한
  - **Starter 플랜이나 View/Collab 시트는 월 6회까지만** 호출할 수 있습니다.
  - Professional 이상 플랜의 Dev/Full 시트는 REST API Tier 1 분당 한도를 따릅니다.
  - 캔버스 쓰기는 베타 기간에만 무료이고, 이후 사용량 기반 유료로 바뀔 예정입니다.
- 커뮤니티 대안: `GLips/Figma-Context-MCP` (15.9k★, MIT, 개인 토큰 필요, 읽기 중심), `grab/cursor-talk-to-figma-mcp` (7.0k★, MIT, 플러그인 기반 읽기·쓰기)
- 워크플로 연결 [해석]
  - 디자인 교육 영상의 "좋은 예/나쁜 예" 프레임을 `get_screenshot`으로 뽑아 Remotion 비교 템플릿에 넣습니다.
  - `get_variable_defs`로 채널 디자인 시스템(`docs/디자인_시스템.md`)과 Remotion 테마 토큰을 맞춥니다.
  - `get_motion_context`로 Figma에서 만든 모션 시안을 Remotion 코드로 옮깁니다.
  - `generate_diagram`으로 설명용 다이어그램을 만듭니다.

**Canva (공식 원격)** [공식 자료: canva.dev 문서, llms.txt]
- 주소: `https://mcp.canva.com/mcp`, OAuth(사용자마다 개별 인증)
- 모든 플랜에서 쓸 수 있는 도구
  - 디자인: `search-designs`, `get-design`, `get-design-content`, `generate-design` → `create-design-from-candidate`
  - 편집: `start-editing-transaction` / `perform-editing-operations` / `commit-editing-transaction`, `get-design-thumbnail`
  - 내보내기·자산: `export-design`(PNG/JPG/PDF/PPTX/MP4 등), `upload-asset-from-url`, `import-design-from-url`, `comment-on-design`
- Pro 이상 전용 도구: `resize-design`, `autofill-design`, `list-brand-kits`, `create-design-from-brand-template`
- 속도 제한: 생성·내보내기는 분당 20건. 무료 플랜 내보내기는 표준 화질입니다.
- 워크플로 연결 [해석]: 브랜드 템플릿 + `autofill-design`으로 썸네일 문구만 바꾼 시안 여러 장 → `export-design`으로 PNG → YouTube 썸네일 교체. 브랜드 템플릿 기능은 Pro 이상에서만 됩니다.

### 3-5. 3D (Blender)

- **Blender Lab 공식 MCP**
  - 요구 사항: Blender 5.1 이상, 페이지 기준 v1.0.3
  - 용도: 씬 분석, Python API를 자연어로 다루기, 문서 탐색
  - 공식 경고: "LLM이 생성한 코드를 **아무 보호장치 없이** 실행하니 VM이나 민감 정보가 없는 시스템을 쓰라" [공식 자료: blender.org/lab/mcp-server]
  - 라이선스(GPL-3.0 이상)와 Claude 커넥터에서 쓰인다는 점은 [2차 인용]입니다.
- `ahujasid/mcp-for-blender` (29.6k★, MIT, PyPI 2.1.1 2026-09-27) [README]
  - 제3자가 만든 서버이고, 임의 Python 실행 도구가 있습니다.
  - 에셋: Poly Haven(CC0), Sketchfab, Hyper3D Rodin, Hunyuan3D
  - 텔레메트리 설정 항목이 있고, 유료 프리미엄 3D 생성 옵션도 있습니다.
- [해석] "형태·명암·원근" 같은 주제에서 3D 턴테이블 스틸을 만들 때만 가치가 있습니다.

### 3-6. YouTube

- 공식 MCP는 없습니다. [2차 인용]
- 레지스트리에서 "youtube"를 검색하면 30건 이상 나오지만, 대부분 다운로더나 스크래퍼입니다. [공식 자료: 레지스트리]
- **읽기·리서치용**
  - `kirbah/mcp-youtube` (29★, MIT, npm 1.1.14 2026-09-11) [README]
    - 토큰을 아낀 응답이 장점입니다.
    - 도구: `getVideoDetails`, `searchVideos`, `getTranscripts`, `getChannelStatistics`, `getChannelTopVideos`, `getTrendingVideos`, `getVideoComments`, `findConsistentOutlierChannels`(MongoDB 필요)
    - 자막은 키 없이 가져올 수 있습니다.
  - `jkawamoto/mcp-youtube-transcript` (486★, MIT) [README]: `get_transcript`, `get_timed_transcript`, `get_video_info`, `get_available_languages`
  - `kimtaeyoon83/mcp-server-youtube-transcript` (598★, MIT, 한국 개발자) [README]
    - `lang: 'ko'`, 광고 구간 제거 옵션, TwelveLabs 영상 분석 도구가 있습니다.
    - npm 최신 버전은 0.1.1(2024-11)로, 저장소보다 뒤처져 있습니다 [확인].
  - `ZubeidHendricks/youtube-mcp-server` (577★, MIT)
    - 저장소 설명은 "video management, Shorts creation"을 내세우지만, README에 적힌 도구는 **읽기 전용 10개**뿐입니다(`YOUTUBE_API_KEY` 사용) → 설명과 실제가 다릅니다.
- **채널 운영용 (OAuth, 쓰기 가능)**
  - `pauling-ai/youtube-mcp-server` (23★, MIT) [README]
    - 도구 40개가 Data·Analytics·Reporting API를 모두 다룹니다.
    - 주요 도구: `youtube_upload_video`, `youtube_update_video`, `youtube_delete_video`, `youtube_set_thumbnail`, `youtube_post_comment`, `youtube_reply_to_comment`, `youtube_analytics_retention`, `youtube_analytics_traffic_sources`, `youtube_reporting_create_job`/`_download`, `youtube_search_suggestions`
    - Analytics는 **채널 소유 계정**으로 로그인해야 합니다.
    - ⚠ README의 설치 명령은 `pip install youtube-studio-mcp`인데, 이 PyPI 패키지(0.3.0)에는 프로젝트 URL이 없습니다. 게다가 같은 이름의 다른 저장소(i1s-abhishek)가 있어 **어느 쪽 패키지인지 확인하지 못했습니다.** 소스에서 직접 설치하기를 권합니다.
  - `i1s-abhishek/youtube-studio-mcp` (17★, MIT) [README]: 표준 라이브러리만 쓰는 stdio 서버입니다. 메타데이터 수정, 썸네일 업로드, Analytics, 댓글을 지원합니다.
  - `anwerj/youtube-uploader-mcp` (55★, MIT, Go 바이너리) [README]
    - 업로드, 공개 상태 지정, 예약 공개, 재생목록, 썸네일(2MB 미만), 자막 첨부를 지원합니다.
    - 설치 스크립트가 `curl | bash` 방식입니다.
- **썸네일 CTR 데이터** [공식 자료: developers.google.com/youtube/reporting]
  - Reporting API의 `channel_reach_basic_a1`(날짜·영상별)과 `channel_reach_combined_a1`(트래픽 소스·기기별)에서 `video_thumbnail_impressions`, `video_thumbnail_impressions_ctr`를 받을 수 있습니다.
  - Reporting API 도구가 있는 서버(pauling-ai)라면 MCP로 가져올 수 있습니다 [해석].
  - Test & Compare(A/B) 결과를 주는 API는 찾지 못했습니다.

### 3-7. 소셜 배포 (Instagram, TikTok 등)

- **Instagram**
  - Meta가 공식으로 낸 Instagram(오가닉 게시) MCP는 없습니다. Meta가 공식으로 낸 것은 광고(Ads) 커넥터뿐입니다. [2차 인용]
  - `jlbadano/ig-mcp` (195★, MIT) [README]: Graph API 기반이고, Facebook 페이지에 연결된 비즈니스 계정과 장기 토큰이 필요합니다. `instagram_content_publish`, `instagram_manage_messages` 등 **넓은 권한**을 요구합니다.
- **TikTok**
  - 공식 TikTok Ads MCP가 발표됐을 뿐, 오가닉 게시용 공식 서버는 없습니다. [2차 인용]
  - Higgsfield의 `tiktok_*` 도구로 게시할 수 있습니다 [세션 도구 목록 확인].
- **Postiz** [README]
  - 앱 저장소: `gitroomhq/postiz-app` (36.5k★, AGPL-3.0)
  - 호스팅 MCP: `https://mcp.postiz.com/mcp-oauth-dynamic` (OAuth)
  - 도구 예: `integrationList`, `integrationSchema`, `schedulePostTool`
  - TikTok, Instagram, YouTube는 **미디어를 먼저 Postiz에 업로드해야** 게시할 수 있습니다.
  - Claude Code용 플러그인에는 MCP 등록이 없고 CLI와 스킬만 들어 있습니다.
- **Taisly** (215★, MIT) [README]
  - 레지스트리 `io.github.taisly/agent`, 원격 주소 `https://app.taisly.com/mcp`
  - TikTok, Reels, Shorts, X, Facebook에 게시합니다. 무료로 시작할 수 있고 확장은 유료입니다.

### 3-8. 지식·노트

- **Notion 원격** [공식 자료]
  - 도구: `notion-search`, `notion-fetch`, `notion-create-pages`, `notion-update-page`, `notion-create-database`, `notion-query-data-sources`(SQL), `notion-create-view`, `notion-create-comment`, `notion-create-file-upload`(최대 20MiB) 등
  - `notion-search`와 `notion-query-data-sources`는 각각 **10초에 20회**로 제한됩니다.
  - 일부 도구는 Business 플랜이나 Notion AI가 필요합니다.
- **Google Drive** [공식 자료: developers.google.com]
  - 주소: `https://drivemcp.googleapis.com/mcp/v1` (Developer Preview)
  - 도구: `search_files`, `read_file_content`, `download_file_content`, `get_file_metadata`, `get_file_permissions`, `list_recent_files`, `create_file`, `copy_file`
  - 커뮤니티 대안: `taylorwilsdon/google_workspace_mcp` (3.3k★, MIT)
- **Obsidian** [README]
  - `coddingtonbear/obsidian-local-rest-api`(3.0k★, MIT): 플러그인에 **MCP가 내장돼** 있습니다(`https://127.0.0.1:27124/mcp/`, Bearer 토큰).
  - `MarkusPfundstein/mcp-obsidian`(4.5k★, MIT): 위 REST API 플러그인을 거쳐 동작합니다.
  - `bitbonsai/mcpvault`(1.7k★, MIT): 플러그인 없이 볼트 파일에 직접 접근하되, 볼트 루트 밖으로는 못 나가게 막습니다.

### 3-9. 웹 리서치·브라우저·메모리

- **Brave** [공식 자료]
  - 도구: `brave_web_search`, `brave_image_search`, `brave_video_search`, `brave_news_search`, `brave_local_search`, `brave_summarizer`, `brave_llm_context`
  - 요금: 1,000건당 $5, 매월 $5 무료 크레딧 (brave.com)
- **Exa** [공식 자료]
  - 주소: `https://mcp.exa.ai/mcp`. **익명으로도 동작**하며 속도 제한이 걸립니다.
  - `?login` 또는 `/mcp/oauth` 경로로 OAuth 로그인을 강제할 수 있습니다.
  - 도구: `web_search_exa`, `web_fetch_exa`, `web_search_advanced_exa` 등
- **Firecrawl** [공식 자료]
  - 키리스 호스팅 `https://mcp.firecrawl.dev/v2/mcp`는 scrape, search, parse 3개만 제공합니다.
  - 키나 OAuth를 쓰면 crawl, map, agent, monitor, 논문 검색 등 26개 도구를 모두 씁니다.
- **Playwright** [공식 자료]
  - 접근성 스냅샷 기반으로 동작합니다.
  - 도구 예: `browser_navigate`, `browser_snapshot`, `browser_take_screenshot`, `browser_start_video`/`browser_stop_video`, `browser_start_recording`, `browser_pdf_save`, `browser_run_code_unsafe`
- **Chrome DevTools MCP**: README에 "Google collects usage statistics"라고 명시돼 있습니다. [공식 자료]
- **Memory**
  - `modelcontextprotocol/servers`의 memory 서버: 지식 그래프 방식(`create_entities`, `create_relations`, `add_observations`, `read_graph` 등). 저장소가 "production-ready가 아닌 레퍼런스"라고 경고합니다.
  - `basic-memory`(AGPL-3.0): 마크다운 파일 기반입니다.
  - [해석] 채널 톤과 규칙은 이미 `CLAUDE.md`와 `prompts/style_guide.md`로 관리되고 있어 별도 메모리 서버는 우선순위가 낮습니다.

---

## 4. 바로 써볼 조합 TOP 5

### ① 렌더 QA 루프
구성: claude-video-vision + Remotion Agent Skills (+ 선택: Kinocut)

- 설정 [README 기준, 미실행]
  - Claude Code에서 `/plugin marketplace add https://github.com/jordanrendric/claude-video-vision` → `/plugin install claude-video-vision` 실행 (Whisper 로컬 백엔드 선택)
  - `renderer/`에서 `npx remotion skills add` 실행
- 사용 예: "`renderer/out/final.mp4`의 0:30–1:10을 2fps로 보고 자막과 그래픽이 겹치는지, 얼굴 박스가 가려지는지, 전환 타이밍이 대본 태그와 맞는지 점검해서 `graphics/` 템플릿 수정안을 내줘"
- 효과 [해석]: CLAUDE.md의 "템플릿 시각 확인" 단계(`--sequence --frames`)를 Claude가 직접 보고 판단하게 됩니다.

### ② 썸네일 스튜디오 + CTR 추적
구성: Figma MCP(또는 Canva MCP) + YouTube 운영 서버(pauling-ai 또는 i1s-abhishek)

- 흐름
  1. Figma 썸네일 템플릿 프레임을 `get_screenshot`/`download_assets`로 받습니다. Canva라면 `autofill-design` → `export-design`을 씁니다.
  2. 시안 3장 중 1장을 `youtube_set_thumbnail`로 적용합니다.
  3. A/B 테스트는 Studio의 Test & Compare에서 **사람이 직접** 돌립니다.
  4. 1~2주 뒤 Reporting API의 reach 리포트에서 `video_thumbnail_impressions_ctr`를 트래픽 소스별로 비교합니다.
- 주의: CTR은 노출 경로(탐색, 추천, 검색)에 따라 크게 달라지므로 `channel_reach_combined_a1`의 `traffic_source_type`으로 나눠 봐야 합니다. [2차 인용 + 해석] Figma Starter 플랜의 월 6회 제한도 고려해야 합니다.

### ③ 리서치 → 대본 → 노트
구성: Exa(호스팅, 익명 가능) 또는 Firecrawl + jkawamoto/kimtaeyoon83 YouTube 자막(`lang=ko`) + Notion 원격 MCP

- 사용 예: "게슈탈트 원리 영상 대본의 사실관계를 원 출처로 확인하고, 같은 주제의 국내 인기 영상 자막 3개에서 구성을 비교해 Notion '대본 DB'에 저장"
- 결과물을 `samples/sample_script.txt` 형식의 대본으로 만들어 앱에 넣습니다 [해석].

### ④ 저작권 안전 시각 자료 수집
구성: open-museum-mcp + wikimedia-image-search-mcp + Openverse(`license_type=commercial`) + Pexels MCP

- 흐름: 디자인사 이미지(PD/CC0)와 현대 B-roll(Pexels)을 모읍니다. 출처와 라이선스를 `projects/<job>/credits.md`로 정리해서 영상 설명란 크레딧에 씁니다.
- 주의 [해석]: 수익화 채널에서는 CC BY-NC 계열을 쓸 수 없습니다. BY와 BY-SA는 표기 의무가 있습니다.

### ⑤ 배포 자동화 (사람 승인 전제)
구성: anwerj/youtube-uploader-mcp(**비공개 업로드 + 예약**) + Postiz 호스팅 MCP(Shorts를 Reels·TikTok으로 크로스포스팅). 대안으로 Higgsfield의 `tiktok_prepare_publish`를 쓸 수 있습니다.

- 원칙
  - 업로드는 항상 `private` 또는 `unlisted`로 올리고, 공개 전환은 사람이 합니다.
  - 제목·설명·태그는 Claude가 초안을 쓰고 사람이 승인합니다.

(번외) 생성형 보강: ElevenLabs로 SFX와 BGM, fal.ai나 Higgsfield로 생성 B-roll을 만듭니다. 생성 결과물의 상업적 이용 조건은 각 서비스 약관을 확인하세요.

---

## 5. 연결 방식 메모 (Claude Code, Desktop, 자체 앱)

1. **Claude Code**
   - 원격 서버: `claude mcp add --transport http <name> <url>`
   - 로컬 stdio 서버: `claude mcp add <name> -- <command>`
   - **키가 필요한 서버는 `--scope user`로 등록**하세요. 프로젝트 `.mcp.json`은 git에 커밋되기 때문입니다. `.mcp.json`에서 환경변수 치환(`${VAR}`)을 쓸 수 있다는 점은 일반 지식이며 이번에 다시 확인하지는 않았습니다.
2. **Claude Desktop**
   - Figma, Canva, Notion, Adobe, ElevenLabs 같은 공식 원격 서버는 Settings → Connectors에서 OAuth로 연결하는 방식이 기본입니다.
   - 로컬 서버는 `claude_desktop_config.json`에 등록합니다. 과거 README들(ElevenLabs, MiniMax)에는 Windows에서 "Developer Mode"를 켜야 한다는 안내가 있었는데, 지금도 필요한지는 [미확인]입니다.
3. **자체 Python 앱(director 에이전트)에서 쓰려면**
   - Messages API의 **MCP connector**(베타 `mcp-client-2025-11-20`)를 씁니다.
   - `mcp_servers=[{"type":"url","url":…,"name":…,"authorization_token":…}]`와 `tools=[{"type":"mcp_toolset","mcp_server_name":…}]`를 **반드시 함께** 넣어야 합니다.
   - `default_config: {"enabled": false}` + `configs`를 쓰면 허용 목록(allowlist) 방식으로 도구를 켤 수 있습니다.
   - 1P API와 Foundry에서는 베타로 제공되고, Bedrock과 Vertex에서는 지원되지 않습니다.
   - [해석] 문서에 나온 타입은 `url`(원격)뿐이라 uvx 같은 로컬 stdio 서버는 이 방식으로 붙일 수 없습니다. 그 경우 Python MCP SDK로 클라이언트를 직접 구현하거나 Claude Agent SDK를 써야 합니다. 또 앱이 쓰는 structured output(`output_config.format`)과 함께 쓸 수 있는지는 [미확인]이라 별도 호출로 분리하는 편이 안전합니다.

---

## 6. 보안 주의사항

### API 키와 토큰
- **이 저장소는 git 저장소**입니다. `.mcp.json`, `claude_desktop_config.json`, `.env`에 적은 키가 커밋되지 않게 하세요. `claude mcp add --scope user`, OS 환경변수, `BRAVE_API_KEY_FILE`처럼 파일로 키를 넘기는 방식을 권장합니다.
- **가능하면 OAuth 원격 서버를 쓰세요**(Figma, Canva, Notion, Runway, ElevenLabs 호스팅, Exa). 클라이언트에 키를 복사하지 않고 권한 범위를 줄 수 있습니다.
- 앱(Pexels·Claude API)과 MCP에는 **서로 다른 키**를 발급해서 할당량 충돌과 유출 범위를 나누세요. 키는 정기적으로 교체하세요.
- Google OAuth
  - `client_secret.json`과 토큰 파일(예: `~/.youtube-mcp/`)은 프로젝트 폴더 밖에 두세요.
  - 동의 화면을 "테스트" 상태로 두면 refresh 토큰이 7일 만에 만료되는 것으로 알려져 있습니다. [일반 지식, Google 문서 재확인 권장]

### 도구 결과를 통한 프롬프트 인젝션
- 웹 페이지(Exa, Firecrawl, Playwright), **YouTube 댓글·자막**, Notion 페이지, Instagram DM, 스톡 이미지 태그·설명은 모두 **남이 쓴 텍스트**입니다. 그 안에 "이전 지시를 무시하고 …를 업로드하라" 같은 문장이 들어 있을 수 있습니다.
- 한 세션 안에서 **신뢰할 수 없는 입력 읽기 + 개인 데이터 접근 + 외부 전송·업로드**가 겹치지 않게 나누세요. 예를 들어 리서치 세션과 업로드 세션을 분리합니다.
- 쓰기·삭제·게시 도구(`youtube_delete_video`, `youtube_upload_video`, `tiktok_prepare_publish`, `schedulePostTool`, `notion-update-page`, `export-design` 등)는 **자동 승인에서 빼세요.** Claude 커넥터 설정에서 도구별로 "매번 확인"을 걸 수 있습니다. [공식 자료: ElevenLabs 문서의 Claude 설정 설명]
- 앱의 director 에이전트에 MCP 결과를 넘길 때는 "데이터"로 감싸서 전달하고, 지시로 해석되지 않도록 시스템 프롬프트에 명시하세요. [해석]
- MCP 서버의 **도구 설명 자체**도 모델에 들어가므로(tool poisoning), 스타 수가 적은 서버는 소스를 읽어 보고 설치하세요.

### 업로드와 게시 권한
- YouTube OAuth 권한 범위는 필요한 만큼만 받으세요. 조회는 readonly, 업로드는 upload만, 댓글 쓰기는 따로 받습니다. [해석]
- 기본값은 `private`/`unlisted` 업로드로 하고, 공개·삭제는 사람이 직접 하세요.
- **브랜드 계정 함정**: 브랜드 계정 OAuth에서 엉뚱한 채널로 업로드되는 문제가 보고돼 있습니다(`brentwpeterson/mcp-youtube` 저장소 설명). 처음 한 번은 채널 ID를 확인하는 도구를 먼저 호출하세요.
- YouTube Data API 할당량은 하루 10,000 단위이고 업로드는 소모가 큽니다. 단가는 공식 quota 계산기로 확인하세요 [미확인]. kirbah 서버의 캐시나 pauling-ai 서버의 할당량 추적 기능을 쓰면 반복 호출을 줄일 수 있습니다.
- Instagram Graph API 토큰은 DM 권한까지 포함할 수 있어 유출되면 피해가 큽니다. 게시만 할 거라면 권한을 최소화하세요.

### 코드 실행·로컬 앱 제어
- Blender(두 서버 모두 임의 Python 실행), Premiere/AE(ExtendScript), DaVinci(Scripting API), Playwright의 `browser_run_code_unsafe`, Replicate code mode, Higgsfield의 `sandbox_exec`는 **로컬 파일 삭제나 외부 전송도 가능한 강한 권한**입니다. 원본 촬영본 폴더와 분리된 환경에서 쓰세요. Blender Lab도 공식적으로 VM 사용을 권합니다.
- ElevenLabs 로컬 서버의 `ELEVENLABS_MCP_BASE_PATH`처럼 **파일 접근 경계**를 지정할 수 있는 서버는 작업 폴더로 좁혀 두세요.

### 텔레메트리와 공급망
- 텔레메트리가 기본으로 켜진 서버: Premiere MCP(hetpatel-11), Chrome DevTools MCP. Blender MCP에는 텔레메트리 설정 항목이 있습니다.
- `curl | bash` 설치(anwerj, genmedia)는 스크립트를 먼저 읽어 보세요.
- 패키지 이름이 겹치는 경우(`youtube-studio-mcp`)와 보관·미유지보수 저장소(ElevenLabs 로컬, Notion 로컬, deepfates/mcp-replicate, Remotion MCP)에 주의하세요.
- 버전을 고정하세요. uvx/npx `@latest`는 매번 새 코드를 실행합니다.

### 비용
- 생성형 도구(Runway, Higgsfield, fal, ElevenLabs, MiniMax, Replicate)는 호출할 때마다 크레딧이 빠집니다. 일괄 작업 전에 `get_pricing`(fal), `balance`(Higgsfield), `check_subscription`(ElevenLabs 로컬)으로 먼저 확인하게 하세요.

### 미디어 라이선스
- Pixabay는 응답을 24시간 캐시해야 하고 영구 핫링크가 금지됩니다.
- Unsplash는 핫링크와 다운로드 트래킹이 의무입니다.
- Pexels는 출처 표기를 권장합니다.
- CC 라이선스는 NC/ND 조건을 확인해야 합니다. MCP가 돌려주는 라이선스 필드를 그대로 믿지 말고 원본 페이지에서 한 번 더 확인하세요. [해석]

---

## 7. 반대 증거와 리스크

- **MCP가 늘 최선은 아닙니다.** Remotion은 "에이전트가 MCP를 불안정하게 호출하고 토큰 비용이 든다"는 이유로 MCP를 접고 Skills로 옮겼습니다. [공식 자료] 문서 참조나 절차형 지식은 Skills나 CLAUDE.md가 더 나을 수 있습니다.
- 도구가 많은 서버(Premiere 283개, DaVinci 389개, Firecrawl 26개)는 컨텍스트를 많이 차지합니다. 도구 검색을 지원하는 모드나 도구 허용 목록을 쓰세요.
- YouTube와 소셜 분야는 **공식 서버가 없고 커뮤니티 서버의 성숙도가 낮습니다**(★ 20~50). API 정책이 바뀌면 깨질 위험이 큽니다.
- 앱이 이미 Pexels, FFmpeg, Claude 감독 기능을 내장하고 있어서, 같은 기능의 MCP를 붙이면 **중복 관리 부담**이 생깁니다. MCP는 "사람과 Claude Code가 대화하며 하는 작업"에 집중하는 편이 낫습니다. [해석]

## 8. 조사의 한계

- 설치하거나 실행해 보지 않았습니다. 모든 동작은 README와 문서 기준입니다.
- 원문을 직접 확인하지 못한 항목
  - Pexels 요금·한도(pexels.com 403)
  - Blender Lab 라이선스·버전 이력(projects.blender.org 403)
  - Adobe 커넥터의 원격 URL과 Claude Code 지원 여부
  - Higgsfield, Runway, Exa, Postiz 요금제 세부
  - 공식 YouTube MCP가 없다는 점, Meta와 TikTok 공식 MCP 현황(모두 2차 인용)
- ElevenLabs 호스팅 MCP의 실제 도구 목록은 문서와 레지스트리 설명이 달라 연결해 봐야 알 수 있습니다.
- Remotion MCP가 실제로 종료됐는지 확인하지 못했습니다.
- `youtube-studio-mcp` PyPI 패키지의 소유 저장소를 확인하지 못했습니다.
- 레지스트리 검색 API는 일부 키워드에서 타임아웃이 났습니다(runway, blender).

## 9. 주요 출처

- 공식 MCP 레지스트리: https://registry.modelcontextprotocol.io (v0 API로 검색)
- Figma MCP 가이드: https://github.com/figma/mcp-server-guide · 도구 목록: https://developers.figma.com/docs/figma-mcp-server/tools-and-prompts/
- Canva MCP: https://www.canva.dev/docs/apps/mcp/ · 도구와 한도: https://www.canva.dev/docs/apps/mcp/tools/
- Notion MCP: https://developers.notion.com/docs/mcp · 도구: https://developers.notion.com/guides/mcp/mcp-supported-tools
- Google Drive MCP: https://developers.google.com/workspace/drive/api/reference/mcp
- ElevenLabs 호스팅 MCP: https://elevenlabs.io/docs/agents-platform/operate/hosted-mcp · 로컬(보관됨): https://github.com/elevenlabs/elevenlabs-mcp
- Remotion MCP 종료 안내: https://www.remotion.dev/docs/ai/mcp · Skills: https://github.com/remotion-dev/skills
- Runway: https://github.com/runwayml/runway-mcp-plugin · https://github.com/runwayml/runway-api-mcp-server
- fal.ai MCP: https://fal.ai/docs/model-apis/mcp · Replicate MCP: https://replicate.com/docs/reference/mcp
- Higgsfield MCP: https://higgsfield.ai/mcp
- MiniMax: https://github.com/MiniMax-AI/MiniMax-MCP · Google genmedia: https://github.com/GoogleCloudPlatform/genmedia-creative-studio
- Anthropic 크리에이티브 커넥터: https://www.anthropic.com/news/claude-for-creative-work · Adobe: https://blog.adobe.com/en/publish/2026/04/28/adobe-for-creativity-connector
- Blender Lab MCP: https://www.blender.org/lab/mcp-server/ · mcp-for-blender: https://github.com/ahujasid/mcp-for-blender
- DaVinci: https://github.com/samuelgursky/davinci-resolve-mcp · Premiere: https://github.com/hetpatel-11/Adobe_Premiere_Pro_MCP · AE: https://github.com/Dakkshin/after-effects-mcp
- Kinocut: https://github.com/KyaniteLabs/kinocut · video-audio-mcp: https://github.com/misbahsy/video-audio-mcp · VectCutAPI: https://github.com/sun-guannan/VectCutAPI
- claude-video-vision: https://github.com/jordanrendric/claude-video-vision · mcp-video-analyzer: https://github.com/guimatheus92/mcp-video-analyzer
- YouTube Reporting reach 리포트: https://developers.google.com/youtube/reporting/v1/reports/channel_reports · 변경 이력: https://developers.google.com/youtube/analytics/revision_history
- YouTube MCP: https://github.com/pauling-ai/youtube-mcp-server · https://github.com/i1s-abhishek/youtube-studio-mcp · https://github.com/kirbah/mcp-youtube · https://github.com/jkawamoto/mcp-youtube-transcript · https://github.com/kimtaeyoon83/mcp-server-youtube-transcript · https://github.com/anwerj/youtube-uploader-mcp · https://github.com/ZubeidHendricks/youtube-mcp-server
- 스톡: https://github.com/garylab/pexels-mcp-server · https://github.com/CaullenOmdahl/pexels-mcp-server · https://github.com/zym9863/pixabay-mcp · https://github.com/hellokaton/unsplash-mcp-server · https://github.com/cevatkerim/unsplash-mcp · https://github.com/neno-is-ooo/mcp-openverse · https://github.com/yanexr/wikimedia-image-search-mcp · https://github.com/cfpramod/open-museum-mcp
- API 약관: https://pixabay.com/api/docs/ · https://unsplash.com/documentation · Pexels(2차 인용): https://www.pexels.com/api/documentation/
- 소셜: https://github.com/gitroomhq/postiz-agent · https://github.com/taisly/agent · https://github.com/jlbadano/ig-mcp
- 리서치·브라우저: https://github.com/brave/brave-search-mcp-server · https://brave.com/search/api/ · https://github.com/exa-labs/exa-mcp-server · https://github.com/firecrawl/firecrawl-mcp-server · https://github.com/microsoft/playwright-mcp · https://github.com/ChromeDevTools/chrome-devtools-mcp
- 노트·메모리: https://github.com/coddingtonbear/obsidian-local-rest-api · https://github.com/MarkusPfundstein/mcp-obsidian · https://github.com/bitbonsai/mcpvault · https://github.com/modelcontextprotocol/servers · https://github.com/basicmachines-co/basic-memory · https://github.com/upstash/context7
- 2차 인용(검색 스니펫): YouTube 공식 MCP 부재 https://www.usecarly.com/blog/youtube-mcp/ · Instagram https://www.usecarly.com/blog/instagram-mcp/ · Blender 공식 서버 비교 https://www.strayspark.studio/blog/official-blender-mcp-server-comparison-2026 · 크리에이티브 커넥터 보도 https://9to5mac.com/2026/04/28/anthropic-releases-9-new-claude-connectors-for-creative-tools-including-blender-and-adobe/
