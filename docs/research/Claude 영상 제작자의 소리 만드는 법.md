# 사건마다 이름 붙은 소리를 생성한다

> **대체됨(2026-11-10 채널 주인 결정)** — 아래 결론의 ElevenLabs 추천은 쓰지 않는다. 소리는 프로그램이 매번 Pixabay(매니페스트)·Openverse(CC0·CC BY, NC/ND 제외, 원문 페이지 대조)에서 스스로 찾아 받는다(`studio/sound/fetch.py`·`tracks.py`, `.omc/handoffs/2026-11-09_design_v5/인수인계.md` 104행). 유료 서비스 없음. 남는 가치는 '위트는 화면 사건과 1:1 로 묶인 소리에서 나온다' 는 관찰(`sound_gags`)뿐이다.

Claude로 영상을 다 만드는 사람들에게 비밀 도구는 없다. **효과음과 음악은 numpy·Web Audio 코드로 직접 합성하거나, ElevenLabs로 생성하거나, Mixkit 같은 무료 라이브러리에서 받는다.** 공개 프롬프트 703개를 세어 보니 코드 합성이 고유 본문 기준 30~33개로 가장 많았고, ElevenLabs와 Mixkit이 각 14개로 같았다. ElevenLabs 14개 중 효과음·음악을 명시한 것은 8개이고, Mixkit 14개 중 13개는 효과음이 아니라 노래의 출처로 적혀 있다. 그리고 **"boing, record scratch, rimshot, vine boom" 같은 코믹 효과음을 지정한 프롬프트는 0개였다.** 위트는 소리 파일이 아니라 침묵 뒤의 첫 소리, 화면 사건과 1:1로 묶인 소리에서 나온다. 앞선 보고서의 "AI 생성은 추천 금지"는 틀렸으니 철회한다. 유료 플랜의 생성물은 약관상 온라인 상업 이용이 되고, 남은 문제는 금지가 아니라 Content ID 보증이 어디에도 없다는 사실 하나다. 우리가 못 찾은 이유는 라이브러리와 권리만 파고드는 동안, 감독 스키마가 "이 순간에 페리 갑판 쿵 소리"를 말할 수 없는 고정 목록(`SFX_KINDS`)이었기 때문이다. 바로 쓸 조합은 **ElevenLabs Creator 플랜 하나로, 효과음은 위트 순간마다 생성하고 음악은 세 판을 만들어 귀로 고르는 것**이다. 일반 휙·종이·클릭은 이미 켜 둔 75개 파일을 그대로 쓴다. 코드 합성이 가장 많다는 사실은 이 조합을 뒤집지 않는다. ElevenLabs를 고른 기준이 인기가 아니었기 때문이다. 다만 돈이 들지 않으니 청취 시험에 비교 후보로 같이 올릴 값은 있다. 이 보고서의 어떤 소리도 사람이 들어 본 것이 아니고, 레퍼런스 릴스 제작자의 실제 도구는 어느 출처에서도 확인되지 않았다.

등급 표기는 **[코드]** 저장소 코드·문서를 직접 읽음, **[측정]** 직접 세거나 API로 조회함, **[판매자]** 판매자 페이지를 직접 읽음, **[제작자]** 만든 사람의 주장, **[2차]** 요약·제3자 글이다.

## 703개를 세어 보면 코드 합성이 가장 많고 세 갈래가 공존한다

아래 표의 숫자는 [공개 프롬프트 모음](https://github.com/yihui-dev/awesome-opus5-5-videos/blob/main/data/videos.json)을 스크립트로 센 값이다. 703개 중 고유 본문은 684개이고, 소리 낱말 목록에 따라 164~197개(고유 156~189개, 약 23~28%)가 소리를 언급한다 **[측정]**. 코드 합성은 후보 42개를 사람이 읽어 분류했고, 낱말 정의에 따라 달라지는 항목은 범위로 적었다. 별 수는 2026-11-10 GitHub API 값이며 소리 품질의 증거가 아니다.

| 방식 | 실제로 쓰는 곳 | 등급 | 703개 안의 측정치(고유 본문) |
|---|---|---|---|
| 생성: ElevenLabs 효과음·음악 | [digitalsamba toolkit](https://github.com/digitalsamba/claude-code-video-toolkit)(별 2,497) · krusemedia video-editor-agent · ["음악 + 효과음 159개를 ElevenLabs로"](https://x.com/PiyushAaryan2/status/2103603040079196586) | 코드 / 제작자 | ElevenLabs 14(효과음·음악 명시 8 · 음성 전용 3 · 용도 불명 3) · 생성형 AI·TTS 전체 약 28~32 |
| 라이브러리 + 측정 피크 정렬: Mixkit | [twoclipping 틀](https://x.com/twoclipping/status/2103273003555402193) · [ultimaxbt](https://x.com/ultimaxbt/status/2108210884799549714) | 코드(프롬프트 본문) | Mixkit 14(게시물 21 — 13개는 노래 출처, 효과음 출처로 명시 3개, 둘 다 2개) · 라이브러리 전체 15 · measured peak 10(게시물 17) |
| CC 검색: Openverse·Freesound | [HyperFrames](https://github.com/heygen-com/hyperframes/blob/main/skills/media-use/audio/references/sfx.md)(81,804) · [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft)(18,243) | 코드 | Freesound 0 |
| 코드 합성 | [lemo-opuscar](https://raw.githubusercontent.com/lemomo-ai/lemo-opuscar/main/core/audio/sfx.py)(14,140) · huashu-art-motion(6,633) · [huashu-motion](https://raw.githubusercontent.com/alchaincyf/huashu-motion/main/skills/huashu-motion/references/sound.md)(2,577) · [charles-video-maker](https://raw.githubusercontent.com/anneheartrecord/charles-video-maker/main/skills/charles-video-maker/scripts/audio_tools.py)(81) | 코드 | 코드 합성 30~33(수작업 분류) · 그중 Web Audio 8 |
| 음악 API 한 곡 + 덕킹, 효과음 단계 없음 | [vox-director](https://github.com/Alisa0808/vox-director)(2,741, MiniMax) · [vox-explainer-skill](https://github.com/CK42BB/vox-explainer-skill)(184, MiniMax) · [vox-ai-motion-graphics-generator](https://github.com/Anil-matcha/vox-ai-motion-graphics-generator)(335, 제3자 MuAPI를 거친 Suno) | 코드 | Suno 4 · MiniMax 0 |
| 내가 준 곡 | mv-director(66) | 코드 | 약 10~21(정의에 따라) |
| 밈 번들 | [@remotion/sfx](https://www.remotion.dev/docs/sfx)(vineBoom·recordScratch 등 32개) | 코드 | 코믹 소리 지정 0 |
| 소리는 안 주고 규율만 | [video-use](https://raw.githubusercontent.com/browser-use/video-use/main/SKILL.md)(30,833) | 코드 | 비트·피크 동기 약 23~30 · LUFS·덕킹·dB 약 10~13 |

읽을 때 네 가지를 감안해야 한다. ElevenLabs 14에는 내레이션만 쓴 경우가 섞여 있다. Mixkit은 같은 틀이 여러 계정으로 복사된 결과라 사람 수보다 부풀어 있고(최대 7번 중복), 대부분 곡을 받는 곳으로 적혀 있다. 코드 합성은 "전부 코드로 만들었다"를 내세운 게시물이 많아 치우쳤을 수 있다. 207개는 본문이 일부만 공개됐다 **[측정]**. 게다가 프롬프트는 의도일 뿐이고, 결과 영상을 들어 본 사람은 이 조사에 없다. 표본이 작아도 결론은 분명하다. **고급 파이프라인일수록 소리를 "화면 이벤트의 함수"로 다룬다.** lemo-opuscar는 타임라인 파일 하나를 악보·믹서·자막·검사가 같이 읽고, 효과음 큐는 페이지의 이벤트에서 뽑는다 ([TECHNIQUE.md](https://raw.githubusercontent.com/lemomo-ai/lemo-opuscar/main/TECHNIQUE.md)) **[코드]**.

우리 코드와 대조하면 많은 부분이 이미 있다. `mix.py` 397·406행은 파일의 최대점을 큐 시각에 맞추고, 덕킹·−14 LUFS 마스터·분당 상한도 있다 **[코드]**. 조사 노트 한 곳이 "피크 정렬이 빠졌을 것"이라 추정했지만 사실이 아니다. video-use의 "18초에 20개는 흔하고 8개면 설계"와 "모든 효과는 보이는 사건에 묶어라"도 게이트 D가 이미 구현한 방향이다. 빠진 것은 **이름 있는 일회성 소리를 지정하는 칸과 그것을 만들어 내는 생성 한 칸, 그리고 곡 파일**이다. `user/music`은 오늘도 비어 있어서 음악은 지금 아예 나오지 않는다 **[측정]**.

## 이번 주 조합은 ElevenLabs 플랜 하나와 귀 30초다

ElevenLabs를 고른 이유는 소리가 가장 좋아서가 아니다. 품질 비교 자료는 없다. **프로그램으로 호출되고 초 단위로 길이를 지정할 수 있으며, 조사 대상 가운데 효과음·음악 모두 판매자 약관을 직접 읽을 수 있었던 유일한 곳**이기 때문이다.

| | 효과음 | 음악 |
|---|---|---|
| 서비스 | ElevenLabs Sound Effects v3. 기본값은 곧 없어질 v2라(2027-03-01 제거) `model_id: eleven_text_to_sound_v3`을 꼭 적는다. 길이는 [문서](https://elevenlabs.io/docs/overview/capabilities/sound-effects) 0.1~30초, [API 참조](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert) `duration_seconds` 0.5~30초로 서로 다르니 0.5초 이상으로 쓴다 | Eleven Music, [API 가격](https://elevenlabs.io/pricing/api)에는 최대 5분([API 참조](https://elevenlabs.io/docs/api-reference/music/compose)는 `music_length_ms` 최대 600,000), `force_instrumental` 지정 |
| 비용(판매자 페이지) | 길이 지정 시 초당 40크레딧, 미지정이면 가격 FAQ의 생성당 200크레딧. API 페이지는 분당 $0.12와 "생성당 과금"을 함께 적어 둘이 맞춰지지 않는다 | API 분당 $0.15 · 구독 분당 900크레딧 |
| 플랜 | Creator **월 $22(첫 달 $11), 121,000크레딧** · Starter 월 $6(첫 달 $1), 30,000크레딧 ([가격](https://elevenlabs.io/pricing)) | 같은 플랜. 월 생성 한도는 Creator 62분 · Starter 17분 · Free 11분([음악 약관](https://elevenlabs.io/eleven-music-model-specific-terms)) |
| 필요한 것 | 계정 + API 키(설정의 키 칸 하나). 설치 없음 | 계정만. 웹 화면에서 만들어 받으면 키도 필요 없다 |
| 영상당 어림 | 위트 4곳 × 3초 × 40 = 480크레딧(Creator 월량의 0.4%) | 5분 × 3판 = 13,500크레딧(Creator 월량의 11%, 월 62분 한도의 24%). API 단가로는 $2.25. 판을 재사용하면 0 |
| 코드 크기 | 아래 스키마 절의 약 60~80줄(설계, 미구현) | **0줄**: `user/music`에 파일과 `곡이름.txt` |

Creator를 권하는 이유는 권리가 아니라 분량과 음질이다. 음악 월 생성 한도가 Starter 17분, Creator 62분이라 5분 세 판(15분)을 Starter에서는 한 번밖에 못 돌린다. 효과음 API의 192kbps MP3도 Creator부터다 ([API 참조](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert)). 음악의 고음질 다운로드(WAV·192kbps)는 Pro부터여서 Creator도 받지 못하니, 받은 파일의 음질은 귀로 확인해야 한다 **[판매자]**.

권리는 Starter와 Creator가 거의 같다. 매체 권리는 Free부터 Pro까지 모두 "영화·TV·라디오·스튜디오 게임을 뺀 온·오프라인 상업 이용"이고, 약관 4.8(d)가 영상에 맞춰 넣는 동기화 권리를 매체 권리에 넣는다. Free·Starter에 금지된 스트리밍 배포는 4.8(g)가 "음악 스트리밍 플랫폼에 올리는 것"으로 정의한다 ([음악 약관](https://elevenlabs.io/eleven-music-model-specific-terms)) **[판매자]**. 그 플랫폼의 범위는 정의되어 있지 않고 YouTube 이름도 없지만, 내레이션 영상의 배경음악을 여기에 넣어 읽기는 어렵다(해석). 곡만 음원으로 유통하지 않는다면 시험 한 달은 Starter(첫 달 $1)로도 15분 한도 안에서 된다.

권리 사실은 이렇다. 효과음은 "플랜이 상업 이용을 허용하는 경우" 상업 이용이 되고, 출력물을 **단독 파일이나 샘플로 팔거나 재배포하는 것은 금지**다 ([효과음 약관](https://elevenlabs.io/sound-effects-terms)) **[판매자]**. 그래서 생성 파일은 공개 저장소에 넣지 않는다. 지금처럼 gitignore 쪽에 두면 된다. 음악은 입력과 출력의 권리가 사용자에게 있다고 적혀 있고, 플랜은 개인 사용 기준이라 1인 채널에 맞는다. 프롬프트에 아티스트 이름·곡명·앨범명을 쓰면 안 되고, AI 표시 의무는 사용자 몫이며 권리 검토 책임도 사용자에게 있다 **[판매자]**. 음악 페이지는 "아티스트·레이블·퍼블리셔와 협력해 만들었다"고 적는다 ([Eleven Music](https://elevenlabs.io/music)) **[판매자]**. 무료 플랜은 가격표에 상업 라이선스가 없고 음악 다운로드도 안 되므로 시험 청취까지만 쓸 수 있다.

**약관 어디에도 YouTube 수익화나 Content ID는 이름으로 나오지 않는다.** 수익 영상이 허용된다는 것은 "온라인 상업 이용"을 읽은 해석이지 명시 문구가 아니고, 어느 생성 업체도 클레임이 안 난다고 보증하지 않는다. AI 곡을 쓴 영상이 지문 충돌이나 제3자 등록으로 걸린다는 이야기는 상업 블로그의 일화 수준이다 ([예](https://sunowatermark.com/youtube-content-id-ai-music/)) **[2차]**. 제3자가 Content ID로 사람 음악가의 실제 연주 영상을 클레임한 사건은 보도됐지만(Murphy Campbell, [MBW](https://musicbusinessworldwide.com/a-folk-musician-had-her-voice-cloned-by-ai-and-her-recordings-claimed-by-a-copyright-troll-welcome-to-2026)) **[2차]**, AI 곡 사용자의 사례는 아니고 유통사는 클레임에 AI가 없었다고 반박한다. 대응은 간단하다. 첫 영상을 비공개로 올려 클레임이 뜨는지 보고, 생성곡을 Content ID에 직접 등록하지 않는다. 한국 문체부·저작권위원회의 2025년 7월 안내서는 사람의 창작적 기여가 없는 생성형 AI 산출물은 저작물이 아니고, 그대로 저작물로 등록하면 허위 등록으로 처벌될 수 있다고 적었다([법률신문](https://www.lawtimes.co.kr/news/articleView.html?idxno=209882), 음악을 특정한 글은 아니다) **[2차]**. 남이 같은 곡을 써도 막기 어렵다는 뜻이지 쓰면 안 된다는 뜻이 아니다. YouTube 공개 의무는 "영상의 주된 초점인 음악"을 공개 대상으로 적고 예시 목록에 "AI generated music"을 넣었다([도움말](https://support.google.com/youtube/answer/14328491)) **[판매자]**. 말 아래 깔리는 배경음악과 효과음은 따로 다루지 않으니, 곡을 전면에 내는 장면이 있으면 업로드 때 표시를 켠다.

음악은 프로그램을 건드리지 않고 시작한다. 프롬프트는 [vox-explainer](https://raw.githubusercontent.com/CK42BB/vox-explainer-skill/main/SKILL.md)의 공식 `{분위기} {질감}, {템포}, {악기}, {곡선}`을 따른다. 예를 들면 `contemplative cinematic underscore, felt piano and soft strings, 84 bpm, sparse then slowly building, instrumental, no vocals`이다. 세 판을 받아 `user/music`에 넣고, 같은 파일명의 `곡이름.txt`를 곁에 둔다. 첫 줄이 등급, 나머지가 크레딧으로 읽힌다(`tracks.py sidecar`) **[코드]**. 비교 대상으로 무료 곡 하나를 같이 놓고, 같은 내레이션 30초 위에서 이름을 가린 채 폰 스피커로 듣는다. 이 청취는 AI를 통과시키는 관문이 아니라 곡을 고르는 절차다. video-use도 "음악 취향은 사용자 몫이니 대비되는 두 곡을 들려주라"고 적었다 **[코드]**.

일반 효과음을 새로 생성하지 않는 것은 이미 매니페스트에 75개가 켜져 있고(A 73, C 2) 종이·찢기·테이프·도장까지 카테고리가 나뉘어 있기 때문이다 **[측정]**. 다만 이 PC에 실제로 있는 것은 53개이고, 종이·찢기·테이프·도장 26개는 첫 작업 때 내려받는다(주소는 모두 응답함). 조사 노트의 "15개를 한 번 생성" 제안은 이 파일들이 들어오기 전 상태를 전제로 했다. 생성의 값어치는 라이브러리에 없는 **사건 고유의 소리**에 있다.

다른 생성처는 두 번째 줄이다. Lyria는 곡당 $0.08로 가장 싸지만 상업 조건을 판매자 페이지에서 읽지 못했다 ([Google](https://aistudio.google.com/docs/pricing)) **[판매자, 가격만]**. ACE-Step 1.5는 MIT이고 2B 모델은 VRAM 6GB 이하 표기라 8GB에 맞을 수 있으나 속도는 미측정이고 README에 학습 데이터 언급이 없다 ([README](https://cdn.jsdelivr.net/gh/ace-step/ace-step-1.5@main/README.md)) **[판매자]**. 이 PC의 디스크 여유가 6.3GB뿐이어서 지금 설치할 대상은 아니다 **[측정]**. Suno는 누구나 신청하는 공개 API가 아직 없고, 2026년 7월 초대제 파트너 프로그램을 열었다 ([Digital Music News](https://www.digitalmusicnews.com/2026/07/03/suno-is-opening-an-api-partner-program/)) **[2차]**.

## 계정 없이도 같은 구조로 돌아간다

**효과음은 Openverse 검색이다.** 키가 필요 없고(익명은 분당 20회·하루 200회, [HyperFrames 문서](https://github.com/heygen-com/hyperframes/blob/main/skills/media-use/audio/references/sfx.md) **[코드]**), 종이·테이프·휙·폴리·책장·클릭은 검색어마다 240건 상한까지 나오며 상업 필터 뒤에는 CC0·CC BY가 대부분이다 ([API](https://api.openverse.org/v1/audio/stats/)) **[측정]**. `sound_idea`의 핵심 낱말로 찾고 `license=cc0`만, 3초 이하만 받되 `category=sound_effect` 필터는 쓰지 않는다(결과 0건). 원문 페이지에서 CC0를 재확인하는 절차는 매니페스트에 이미 적혀 있다. thud·뱃고동 같은 낱말의 검색 품질은 재지 않았고, 결과는 128kbps 미리듣기다. 찾지 못하면 소리를 넣지 않고 침묵만 남긴다. 그것도 연출이다.

**음악은 Scott Buckley의 [Wildflowers](https://www.scottbuckley.com.au/library/wildflowers/)다.** CC BY 4.0, 상업 허용, 피아노와 현이 조용히 시작해 쌓이는 곡으로 권리자가 설명한다 **[판매자]**. `user/music`에 넣고 `Wildflowers.txt` 첫 줄에 `C`, 다음 줄에 `'Wildflowers' by Scott Buckley - released under CC-BY 4.0. www.scottbuckley.com.au`를 적으면 크레딧이 업로드 정보로 간다. 이 크레딧은 영상 설명란에 반드시 넣어야 한다. 곡 페이지는 설명란에 크레딧이 없으면 작곡가가 저작권 클레임을 걸 수 있다고 적었다 **[판매자]**. 합성이 더 맞는 소리는 lemo-opuscar의 numpy 레시피(creak·thump·crash·step)가 MIT로 열려 있다. 다만 `pipeline.py` 4346행이 절차적 소리를 완성본에서 막고 있어 쓰려면 방침을 바꿔야 하고, 네 저장소가 주력으로 쓰며 703개에서도 가장 많이 지정한 길이지만 들어 본 사람이 없다.

피해야 할 것은 유튜브→mp3와 밈 묶음이다. `@remotion/sfx`의 Vine boom 페이지는 출처가 myinstants이고 "자유 라이선스로 공개되지 않았다"고 스스로 밝힌다 ([Remotion](https://www.remotion.dev/docs/sfx/vine-boom)) **[코드]**. 703개에서 아무도 지정하지 않았으니 잃는 것도 적다.

## 위트는 기대를 만들고 한 번 어긋나게 하는 설계다

코퍼스에서 가장 위트 있는 프롬프트는 앞 12초를 무음으로 두고, 떨어진 공이 부딪히는 블록마다 음을 내다가 마지막 타격 뒤 다시 침묵한다. "보이는 움직임과 모든 소리를 맞추라"는 지시뿐이고 코믹 낱말은 없다 **[코드]**. lemo-opuscar도 전환 앞 진짜 정적과 정적 뒤 첫 소리를 의무로 둔다 ([DIRECTOR.md](https://raw.githubusercontent.com/lemomo-ai/lemo-opuscar/main/DIRECTOR.md)) **[코드]**. 이론 쪽 근거는 얇다. 워너 카툰 쪽 자료도 Ben Burtt가 Treg Brown이 실제 효과음을 코믹 목적으로 썼다고 회고한 정도이고, 어울리지 않는 소리가 더 웃기다는 Brown 본인의 견해는 적혀 있지 않다 ([Designing Sound](https://designingsound.org/2009/12/treg-brown-and-the-sound-of-looney-tunes/)) **[2차]**. 한국 예능 편집자의 효과음·침묵 규칙을 담은 1차 자료는 찾지 못했다.

감독에게는 여섯 가지 어휘를 준다. 낙하 뒤 음악을 끊는 `thud`, 펀치라인 앞의 `silence_beat`, 말은 거창한데 소리는 사소한 `mismatch`, 추상어를 문자 그대로 들려주는 `literal`, 화면 움직임에 1:1로 붙는 `mickey`, 앞의 소리를 되돌리는 `callback`이다. 이 분류는 위 자료를 종합한 우리 어휘이지 외부 표준이 아니다. 교양 채널에서 레코드 스크래치와 웃음소리를 뺀 것은 근거 없는 취향 판단이고 권리 불확실이 더 분명한 이유다. 청취로 뒤집어도 된다. 레퍼런스 릴스의 "절벽에서 걷다 페리에 착지"는 낙하 무음 → `thud` → 음악 컷으로, "타이핑되는 메일 + CRT 파괴"는 타자·알림으로 리듬을 쌓다 전부 끊고 유리 소리로 번역된다. 다만 이 두 편은 요청문의 묘사로만 분석했고 직접 듣지 못했다.

## 스키마는 일곱 칸, 호출은 기존 길에 얹는다

`studio/agents/schemas.py`의 `TREATMENT`, `silences` 아래에 넣는다. 아래는 설계이며 구현하지 않았다.

```python
"sound_gags": {"type": "array", "items": _obj({
    "seg": INT,                # 이 소리가 걸리는 발화
    "anchor": {"type": "string", "enum": ["word", "after_seg", "graphic_landing"]},
    "anchor_word": STR,        # anchor=word 일 때만
    "type": {"type": "string", "enum": ["thud", "silence_beat", "mismatch", "literal", "mickey", "callback"]},
    "sound_idea": STR,         # 영어 한 문장: "heavy wooden thud on a ferry deck, dry, no reverb" (silence_beat 는 "")
    "pre_silence_s": NUM,      # 직전 실제 침묵 0~1.0 — 이 구간 음악·효과음 비움
    "why": STR,                # 기대 → 어긋남 한 줄. 못 쓰면 넣지 않는다
})},
```

노트 초안의 `offset_s`, `music`, `ref_id`는 뺐다. 믹스가 이미 피크를 맞추니 오프셋이 필요 없고, `pre_silence_s`가 음악 비우기를 겸하며, 콜백은 같은 `sound_idea` 문장을 쓰면 캐시의 같은 파일이 나온다. `director.md` 규칙은 한 절이면 된다. 영상당 최대 4개, 60초 창에 1개, 첫 3초·홀드 제외, `why`에 어긋남이 없으면 삭제, `thud`·`mickey`는 화면 사건이 있을 때만, `silence_beat`는 `silences`와 겹치지 않게, 스크래치·웃음소리·밈 금지다.

연결 지점은 코드에서 확인했다. 계획 보존은 `silences`와 같은 자리(`plan.py` 706·777행, `studio.py` 342·552행)에 넣고 계획 키를 `plan-v16`으로 올린다. 생성은 새 파일 `studio/sound/generate.py` 하나가 `sound_idea` 해시로 `user/cache/sfx_gen/`에 캐시하며, 설정 `elevenlabs_api_key`는 `serpapi_key`와 같은 방식으로 추가한다. `pipeline.py` 4097행의 `directed_sfx` 결과에 위트 큐를 더하되 앞뒤 1.5초의 다른 효과음은 뺀다. 파일은 `_mix_all` 첫머리에서 `lib.sfx`에 `Sound(category="gag_N", license_class="G")`로 넣으면 `lib.pick`과 게이트 D9 등급 표가 그대로 작동한다. 등급 `G`(유료 플랜 생성, 프롬프트 기록이 증빙)는 `pipeline.py` 4348행, `gate.py` 1061행, `tracks.py CLASSES`에 한 낱말씩 더하고, 매니페스트 `about`의 "X … AI 생성" 문구를 고친다. `pre_silence_s`는 `_long_music_cues` 3259행의 `holds`에 한 줄로 더한다. 게인은 `gag_` 카테고리가 기본 −25로 떨어지지 않도록 큐에 −12를 시작값으로 직접 준다. 키가 없거나 호출이 실패하면 소리 없이 침묵만 남기고, 숏폼은 두 번째 단계로 미룬다. 테스트는 저장된 계획 보존, 키 없음, 콜백의 같은 파일 세 가지면 된다.

에이전트는 들을 수 없으므로 코드가 답할 수 있는 것은 간격과 레벨까지다. 그러니 작업 끝에 `위트 순간 목록`(시각, 유형, `why`, 파일)을 리포트로 내고, 주인이 그 지점들만 듣는다.

## 결론

"왜 못 찾느냐"의 답은 찾을 곳을 잘못 봤다는 것이다. 우리는 어느 사이트가 안전한지를 물었고, 저들은 이 순간에 무슨 소리가 나야 하는지를 물었다. 도구는 평범했고, 703개 프롬프트에서 위트를 만드는 것은 소리의 종류가 아니라 자리였다. 그래서 투자 순서가 뒤집힌다. 파일을 더 모으는 일보다 감독이 사건 하나에 이름을 붙이게 하는 일곱 칸이 먼저다.

가장 큰 미지수는 여전히 귀다. 이 설계가 실제로 더 웃긴지, ElevenLabs의 쿵 소리가 교양 톤에서 값싸게 들리지 않는지는 어떤 문서도 답하지 않는다. 첫 달 $11(시험만이면 Starter $1)과 레퍼런스 두 장면을 재현한 시험 한 번이면 알 수 있고, 그 결과가 이번 조사 전체보다 많은 것을 정해 줄 것이다.

## 검증 기록

2026-11-10에 추천 조합이 기대는 주장을 원 출처에서 다시 확인하고 반박을 시도했다. 703개 수치는 저장소를 얕게 받아 `data/videos.json`만 꺼내 다시 셌다(커밋 `92aee2f`, 실행한 코드 없음, 확인 뒤 삭제). 원래 집계 스크립트는 남아 있지 않아, 낱말 정의에 좌우되는 수치는 범위로 바꿨다.

**결과: 50건 점검 · 확인 33 · 수정 15 · 제거 1 · 확인 불가 1**

| # | 항목 | 판정 | 근거·바뀐 점 |
|---|---|---|---|
| 1 | 703 · 고유 684 · 일부 공개 207 · 최대 중복 7 | 확인 | 재집계 일치 |
| 2 | ElevenLabs 14 | 수정 | 수는 맞음. 효과음·음악 명시 8, 음성 전용 3, 불명 3으로 나눠 적음 |
| 3 | Mixkit 14(게시물 21) | 수정 | 수는 맞음. 13개가 곡 출처, 효과음 출처 명시 3개 |
| 4 | measured peak 10(17) | 확인 | 재집계 일치, 문맥도 효과음 배치 |
| 5 | 라이브러리 15 · Freesound 0 · MiniMax 0 · Suno 4 · Web Audio 8 | 확인 | 재집계 일치 |
| 6 | 코믹 소리 지정 0 | 확인 | 더 넓은 낱말로도 0 |
| 7 | 코드 합성 18 | 수정 | 후보 42개를 읽어 분류하니 30~33. 가장 큰 갈래여서 요약·제목도 고침 |
| 8 | 소리 언급 171(163) | 수정 | 재현 안 됨. 164~197(156~189)로 |
| 9 | 생성형 28 · 비트 27 · LUFS 10 · 내가 준 곡 10 | 수정 | 정의에 따라 움직여 범위로 |
| 10 | 12초 무음 공 프롬프트 | 확인 | adrianduta96 본문 |
| 11 | 159개 · twoclipping · ultimaxbt 문구 | 확인 | 코퍼스 사본 기준 |
| 12 | `eleven_text_to_sound_v3` | 확인 | 기본값이 v2임을 덧붙임 |
| 13 | 0.1~30초 · "0.1초 단위" | 수정 | API 참조는 최소 0.5초. 단위가 아니라 범위 |
| 14 | 초당 40크레딧 · $0.12/분 · 생성당 과금 | 확인 | 생성당 200크레딧 덧붙임 |
| 15 | 음악 $0.15/분 · 최대 5분 | 확인 | API 참조의 600,000ms 병기 |
| 16 | `force_instrumental` | 확인 | 공식 API 참조 |
| 17 | Creator·Starter 가격·크레딧 | 확인 | 가격 페이지 |
| 18 | 음악 분량 미상 · 영상당 $2.25 | 수정 | 900크레딧/분, 월 62·17·11분. 13,500크레딧 |
| 19 | Creator를 권하는 이유(스트리밍) | 수정 | 4.8(g)·4.8(d)를 읽으면 근거가 약함. 분량·음질로 교체, Starter 시험 추가 |
| 20 | 효과음 약관(상업·단독 금지) | 확인 | Exhibit 4 §2 |
| 21 | 음악 권리·개인 사용·프롬프트 금지·표시·검토 책임 | 확인 | 2.1 · 2.2 · 3.1 · 4.4 |
| 22 | "아티스트·레이블·퍼블리셔와 협력" | 확인 | 음악 페이지 |
| 23 | 무료 플랜 상업 라이선스·다운로드 없음 | 확인 | 가격표에 없음, 다운로드 불가. 음악 약관 표의 매체 권리 칸은 Free도 같은 문구 |
| 24 | 약관에 YouTube 수익화·Content ID 없음 | 확인 | YouTube는 더빙 조항의 예시로만 나옴 |
| 25 | MBW 사례 | 수정 | 원문 403, 검색 요약으로 확인. AI 곡 사용자 사례가 아니어서 다시 씀 |
| 26 | 법률신문 안내 | 수정 | 음악 특정이 아닌 생성형 AI 일반 안내로, 허위 등록 처벌 덧붙임 |
| 27 | YouTube 공개 의무 미확인 | 수정 | 도움말 페이지로 확인 |
| 28 | Treg Brown의 "어울리지 않는 소리" 견해 | 제거 | 인용 페이지에 없음. 페이지가 실제로 적은 내용으로 교체 |
| 29 | Lyria $0.08/곡 | 확인 | 가격 페이지 |
| 30 | ACE-Step 1.5 MIT · 2B ≤6GB · 학습 데이터 언급 없음 | 확인 | README |
| 31 | Suno 공식 API 없음 | 수정 | 초대제 파트너 프로그램 반영 |
| 32 | Openverse 240건 상한 · 라이선스 분포 · `category` 0건 · 128kbps | 확인 | API 직접 조회 |
| 33 | Wildflowers CC BY · 크레딧 문구 | 수정 | 사실은 맞음. 빠진 조건(설명란 크레딧, 없으면 클레임) 추가 |
| 34 | `곡이름.txt` 첫 줄 `C` | 확인 | `tracks.py`, 매니페스트의 C = 크레딧 필요 |
| 35 | Vine boom 출처·라이선스 | 확인 | Remotion 문서 |
| 36 | `@remotion/sfx` 32개 | 확인 | npm 4.0.542 타입 선언 |
| 37 | 저장소 별 수 12개 | 확인 | API 3개, 나머지는 shields 반올림 값과 일치. 오늘 안의 변동은 몇 개 수준 |
| 38 | toolkit · krusemedia의 ElevenLabs 사용 | 확인 | 스킬 문서·README |
| 39 | HyperFrames(Openverse) · shotcraft(Freesound) | 확인 | 문서·README |
| 40 | lemo-opuscar 레시피·MIT·침묵 규칙·타임라인 | 확인 | 원문 |
| 41 | huashu-motion · charles 코드 합성 | 확인 | 원문 |
| 42 | vox 저장소 이름·경로 | 수정 | 소유자 표기, vox-ai-motion 정식 이름, MuAPI 경유 |
| 43 | vox-explainer 음악 프롬프트 공식 | 확인 | SKILL.md 128행 |
| 44 | mv-director 내가 준 곡 | 확인 | README |
| 45 | video-use 인용 두 곳 | 확인 | SKILL.md 276·280행 |
| 46 | 우리 코드 행 번호·`-25`·`plan-v15`·`SFX_KINDS` | 확인 | 전부 해당 행에 있음 |
| 47 | 켜 둔 효과음 75개(A 73, C 2) | 수정 | 수는 맞음. 디스크에는 53개, 26개는 첫 실행 때 받음 |
| 48 | `user/music` 비어 있음 · `music_mode=mine` | 확인 | 폴더·설정 |
| 49 | 디스크 여유 6.3GB | 확인 | `df` |
| 50 | X 게시물 원문 | 확인 불가 | 직접 열리지 않아(402) 코퍼스 사본으로만 봄 |

이번 검증도 소리를 들어 보지 않았다. Mixkit 약관과 Lyria 상업 조건은 추천 조합 밖이라 다시 읽지 않았고, 구현 설계의 동작은 코드 위치까지만 확인했다.
