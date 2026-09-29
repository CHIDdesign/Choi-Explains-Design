<div align="center">

<img src="docs/images/logo.png" width="84" alt="Choi Studio 로고">

# Choi Studio

**토킹헤드 원본을 유튜브 롱폼과 숏폼으로 자동 편집하는 Windows 데스크톱 앱**

[![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-222222?style=flat-square&logo=windows&logoColor=white)](#요구-사항)
[![Python](https://img.shields.io/badge/Python-3.10%E2%80%933.13-222222?style=flat-square&logo=python&logoColor=white)](#요구-사항)
[![Remotion](https://img.shields.io/badge/Remotion-4.0.530-222222?style=flat-square)](https://www.remotion.dev)
[![Claude](https://img.shields.io/badge/Claude-Pro%20%C2%B7%20Max-222222?style=flat-square&logo=anthropic&logoColor=white)](#ai-연결과-비용)

[빠른 시작](#빠른-시작) · [결과물](#결과물) · [작동 방식](#작동-방식) · [편집 원칙](#편집-원칙) · [자주 묻는 질문](#자주-묻는-질문)

</div>

<br>

<p align="center">
  <img src="docs/images/app_input.jpg" width="900" alt="Choi Studio 입력 화면">
</p>

## 소개

Choi Studio 는 디자인 이론 채널 *Choi Explains Design* 을 만들면서 쓰려고 개발한 개인용 편집 도구입니다. 입력은 세 가지입니다.
- 대본을 읽으며 찍은 원본 영상
- 그 대본
- 짧은 주제 설명

이 세 가지로 컷 편집, 모션그래픽, 자막, 색보정, 효과음과 음악, 렌더링을 차례로 처리합니다.

| 입력 | 결과 |
|---|---|
| **주제 설명**: 무엇을, 누구에게, 왜 | **롱폼 1편**: 16:9 · 1080p · −14 LUFS |
| **원본 영상**: 다시 말한 부분과 NG 가 섞인 그대로 | **숏폼 2편**: 9:16 · 서로 다른 훅 |
| **대본**: 붙여넣기 또는 `.txt` `.docx` `.hwpx` | **부가 자료**: 썸네일 3장 · 자막(SRT) · 업로드 정보 · 편집 리포트 |

편집 판단은 두 단계로 나눕니다.
1. **Claude 로 구성한 AI 제작팀**이 무엇을 강조하고 어디에 그래픽을 넣을지 정합니다.
2. **편집 문법 엔진**이 레퍼런스 연구에서 정리한 수치대로 앵글·전환·효과음을 입힙니다.

<br>

## 결과물

<p align="center">
  <img src="docs/images/sample_output.png" width="900" alt="롱폼과 숏폼 렌더 예시">
</p>

<sub>위 화면은 스톡 인물 클립과 합성 음성으로 돌린 테스트 렌더입니다. 실제 녹화와 대본을 넣으면 AI 제작팀이 구성·그래픽·강조 문구를 정합니다.</sub>

<br>

## 작동 방식

네 단계로 처리합니다. 단계마다 결과를 저장해 두기 때문에, 중간에 멈춰도 다시 실행하면 끝난 단계는 건너뜁니다.

<p align="center">
  <img src="docs/images/how_it_works.png" width="900" alt="분석 → 기획 → 편집 → 마무리">
</p>

<details>
<summary><b>단계별로 자세히</b></summary>

<br>

**01 분석**
- 목소리: 신경망 잡음 제거(RNNoise)와 방송용 EQ·컴프레서로 다듬습니다.
- 음성 인식: Whisper large-v3 로 단어 단위 시각을 얻습니다.
- 대본 정렬: 같은 문장을 여러 번 말했으면 **가장 또렷한 테이크**를 남깁니다. 비교 기준은 대본 일치도, 끝까지 말했는지, 발음 확신도, 추임새·말더듬, 음량입니다.
- 얼굴 추적: YuNet 으로 얼굴 위치를 따라갑니다.
- 자동 색보정: 화이트밸런스, 노출(피부 60–70 IRE), 명암, 채도를 교정하고 3D LUT 로 굽습니다.

**02 기획**
- 총괄 감독이 브리프를 쓰면 전문가 여섯 명(편집, 모션, 자료, 자막, 숏폼, 카피)이 동시에 일합니다.
- 컬러리스트는 룩 4종 비교 시트를 보고 톤을 고릅니다.
- 아트 디렉터는 실제 렌더된 화면을 보고 글자 넘침이나 가독성 문제를 찾아 수정을 지시합니다.

**03 편집**
- 컷마다 와이드 ↔ 미디엄 앵글을 교차하고, 강조 순간에는 펀치인을 넣습니다.
- 화자 반대편에 키워드 콜아웃을 띄웁니다.
- 장면 전환은 절제해서 씁니다. 전환은 컷 지점을 중심으로 한 오버레이라 영상 길이와 음성 싱크가 바뀌지 않습니다.

**04 마무리**
- Remotion 으로 프레임 단위 렌더를 합니다.
- 목소리, 덕킹한 배경음악, 효과음을 섞어 −14 LUFS · −1 dBTP 로 마스터링합니다.
- 업로드용 제목 후보, 챕터 타임코드가 들어간 설명란, 태그, 썸네일을 만듭니다.

</details>

<br>

## 편집 원칙

기본값은 모두 레퍼런스 연구에서 가져왔습니다. 연구에는 셜록현준 등 롱폼 9편과 숏폼 10편 실측, 리텐션 편집 가이드, 교육 영상 연구가 들어갑니다. 수치와 출처는 [`docs/research`](docs/research) 에, 에이전트가 읽는 요약본은 [`prompts/playbook`](prompts/playbook) 에 있습니다.

| 항목 | 기본값 | 근거 |
|---|---|---|
| 얼굴 노출 | 전체의 약 50% | 셜록현준 롱폼 3편 스토리보드 실측 |
| 앵글 교차 | 5–8초마다 100% ↔ 112% | 같은 실측(2–3 앵글 교차) |
| 장면 전환 | 하드컷 90% 이상, 스타일 전환은 챕터 경계 위주 | 리텐션 편집 가이드 |
| 펀치인 | +15–20%, 1–4초 유지, 영상당 최대 12회 | 토킹헤드 편집 가이드 |
| 효과음 | 분당 약 2개, 결론·감정 문장에는 넣지 않음 | 사운드 디자인 가이드 |
| 배경음악 | 목소리보다 약 20 LU 아래, 챕터마다 곡 교체 | 믹싱 가이드 |
| 최종 음량 | −14 LUFS, −1 dBTP | YouTube 재생 기준 |
| 숏폼 | 40초 안팎, 첫 3초 훅, 두 편은 서로 다른 훅 | Shorts 5,400편 분석, 국내 숏폼 실측 |

<br>

## 빠른 시작

### 요구 사항

| | |
|---|---|
| 운영체제 | Windows 10 / 11 (64비트) |
| 그래픽 | NVIDIA GPU 권장. 없으면 CPU 로 동작하지만 느립니다 |
| 저장 공간 | 설치 약 7GB, 작업까지 20GB 이상 |
| AI | Claude Pro 또는 Max 구독(Claude Code). 없으면 규칙 기반으로 편집합니다 |
| 네트워크 | 설치, 자료 검색, 효과음·음악 내려받기에 필요 |

### 설치

1. 이 페이지의 **Code → Download ZIP** 으로 받아 여유 있는 드라이브에 풉니다(예: `D:\ChoiStudio`).
2. **`setup_windows.bat`** 을 더블클릭합니다.
   - 관리자 권한으로 다시 열리므로 사용자 계정 컨트롤 창에서 **예**를 누릅니다.
   - 처음 한 번 20–40분 걸립니다.
3. 바탕화면의 **Choi Studio** 를 엽니다.

<details>
<summary>설치 과정에서 하는 일</summary>

<br>

- Python · Node.js · FFmpeg(NVENC)가 없으면 프로그램 폴더 안에 설치합니다(winget 불필요).
- 파이썬 패키지와 GPU 음성 인식 라이브러리를 설치합니다.
- 렌더러(Remotion)와 렌더링용 Chrome 을 설치합니다.
- Claude Code 를 설치하고 Claude 계정 로그인을 안내합니다.
- 효과음·배경음악·잡음 제거 모델(약 80MB)을 내려받습니다.
- Pixabay API 키를 물어봅니다(선택). 키가 있으면 스톡 영상 B-roll 도 씁니다.
- 바탕화면 바로가기를 만듭니다(항상 관리자 권한으로 실행).
- Whisper 음성 인식 모델(약 3GB)을 미리 받을 수 있습니다.

</details>

### 사용

세 칸을 채우고 **영상 만들기**를 누릅니다.
- 원본 영상은 칸을 눌러 고르거나, 탐색기에서 끌어다 놓거나, 파일을 복사한 뒤 `Ctrl+V` 로 넣습니다.
- 진행 화면에서 단계와 AI 팀 작업 기록을 볼 수 있습니다.
- 끝나면 결과 화면에서 바로 재생하거나 폴더를 엽니다.

<table>
  <tr>
    <td width="50%"><img src="docs/images/app_progress.jpg" alt="진행 화면"></td>
    <td width="50%"><img src="docs/images/app_result.jpg" alt="결과 화면"></td>
  </tr>
  <tr>
    <td align="center"><sub>진행 화면</sub></td>
    <td align="center"><sub>결과 화면</sub></td>
  </tr>
</table>

결과는 `projects/<날짜_제목>/output/` 에 저장됩니다.

```
output/
├── 1_롱폼_<제목>.mp4
├── 2_숏폼1_<제목>.mp4
├── 3_숏폼2_<제목>.mp4
├── 업로드정보.txt
└── 부가자료/
```

- `업로드정보.txt`: 제목 후보, 설명란(챕터 타임코드 포함), 태그, 고정 댓글, 숏폼 캡션
- `부가자료/`: 썸네일 3장, 자막(.srt), 색보정 전후, 편집 리포트, Premiere Pro XML

<br>

## AI 연결과 비용

기본으로 이 PC 의 **Claude Code** 를 통해 Claude 를 부릅니다.
- Claude Code 의 `claude -p` 사용량은 Pro/Max **구독 한도에서 차감**되므로 API 를 따로 결제하지 않습니다([Anthropic 안내](https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan)).
- 실행할 때 `ANTHROPIC_API_KEY` 환경변수를 빼고 호출하므로 API 요금으로 새지 않습니다.
- 영상 한 편에 에이전트 호출은 12–15회입니다.
- 한도에 걸리면 한도가 풀린 뒤 **최근 작업 → 이어서 만들기**를 누르면 끝난 단계는 건너뜁니다.
- API 키 방식으로도 바꿀 수 있습니다(⚙ 고급 설정, 종량제).

<br>

## 자주 묻는 질문

<details>
<summary><b>설정할 것이 있나요?</b></summary>

<br>

없습니다. 제목, 구성, 얼굴과 그래픽 배분, 강조, 음악, 숏폼 구간은 모두 자동으로 정합니다. 오른쪽 위 ⚙(고급 설정)에서 바꿀 수 있는 것은 AI 연결 방식, 스톡 키, 브랜드 색·이름, 저장 경로 정도입니다.

</details>

<details>
<summary><b>왜 관리자 권한으로 실행되나요?</b></summary>

<br>

설치 중 사용자 폴더 쓰기 제한 때문에 생기던 오류(`ENOSPC`, `not enough space`)를 피하기 위해서입니다. 관리자 창에서도 탐색기 끌어다 놓기가 되도록 따로 처리했습니다.

</details>

<details>
<summary><b>내려받은 ZIP 이 왜 작나요?</b></summary>

<br>

저장소에는 소스 코드만 있습니다. 무거운 부품(Whisper 모델 3GB, GPU 라이브러리 1.5GB, 렌더러 0.5GB 등)은 설치할 때 각 배포처에서 받습니다. 설치가 끝나면 폴더는 약 6GB 입니다.

</details>

<details>
<summary><b>GPU 가 없어도 되나요?</b></summary>

<br>

됩니다. 음성 인식과 인코딩이 CPU 로 바뀌어 시간이 몇 배 더 걸립니다.

</details>

<details>
<summary><b>결과를 직접 손보고 싶어요.</b></summary>

<br>

`부가자료/롱폼_premiere.xml` 을 Premiere Pro 에서 열면 컷이 그대로 들어옵니다. AI 가 정한 구성과 강조는 `부가자료/plan.json` 과 `편집리포트.md` 에 남아 있습니다.

</details>

<br>

## 문제 해결

<details>
<summary><b>증상별 해결 방법 펼치기</b></summary>

<br>

| 증상 | 해결 |
|---|---|
| 설치 창이 바로 닫힘 | 사용자 계정 컨트롤 창에서 **예**를 눌렀는지 확인하세요. 파일을 오른쪽 클릭 → *관리자 권한으로 실행*도 됩니다 |
| `No space left on device` · `ENOSPC` | 설치 첫 화면의 쓰기 테스트 표에서 `WRITE FAILED` 인 위치가 원인입니다. 폴더를 여유 있는 드라이브로 옮겨 다시 실행하세요 |
| `HF_TOKEN` 경고 | 정상입니다. 토큰 없이도 모델을 받습니다. 속도 제한(429)으로 멈출 때만 Hugging Face *Read* 토큰을 만들어 `setx HF_TOKEN <토큰>` 후 다시 실행하세요 |
| 헤더에 `○ Claude Code · 로그인 필요` | 그 표시를 누르면 로그인 창이 열립니다 |
| `Claude 구독 사용량 한도에 도달` | 한도가 풀린 뒤 **최근 작업 → 이어서 만들기** |
| `cublas64_12.dll` / `cudnn` 오류 | `setup_windows.bat` 을 다시 실행하거나 ⚙ → 음성 인식 → 장치 `cpu` |
| 효과음·음악이 기본음으로 나옴 | 네트워크 문제로 받지 못한 것입니다. 다른 네트워크에서 `setup_windows.bat` 을 다시 실행하세요 |
| 자막 용어가 틀림 | 대본을 넣으면 대본 표기로 교정됩니다. 그 밖에는 ⚙ → 음성 인식 → 용어 사전 |

</details>

<br>

## 현재 한계

- Windows 전용입니다. 리눅스에서는 개발과 테스트만 합니다.
- 결과 품질은 녹화 상태, 대본, AI 판단에 따라 달라집니다. 중요한 영상은 올리기 전에 한 번 보세요.
- AI 제작팀은 Claude 구독 사용량을 씁니다. 긴 영상을 여러 편 연달아 만들면 한도에 걸릴 수 있습니다.
- 효과음·배경음악은 무료 배포처(Pixabay, Mixkit, Freesound, Incompetech)에서 받습니다. 각 라이선스를 따르고, 곡명은 업로드 정보에 적어 둡니다.

<br>

<details>
<summary><b>프로젝트 구조</b></summary>

<br>

| 경로 | 내용 |
|---|---|
| `studio/pipeline.py` | 단계 오케스트레이션(분석 → 기획 → 편집 → 마무리), 단계별 캐시 |
| `studio/gui/` | 데스크톱 창(입력 · 진행 · 결과), 관리자 창 끌어다 놓기 |
| `studio/agents/` · `studio/director/` | AI 제작팀, Claude 연결(Claude Code / API), 규칙 기반 대체 |
| `studio/edit/grammar.py` | 편집 문법 엔진. 수치는 `PARAMS` 한 곳 |
| `studio/grade/` | 자동 색보정 |
| `studio/sound/` · `studio/media/mix.py` | 효과음·음악 라이브러리, 믹스와 마스터링 |
| `studio/text/align.py` | 대본 정렬, 테이크 선택 |
| `studio/stock/` | 스톡 검색(Pixabay · Unsplash · Coverr · Pexels · Openverse) |
| `renderer/` | Remotion 프로젝트(템플릿, 자막, 콜아웃, 전환) |
| `prompts/` | 팀 헌장, 에이전트 지시문, 편집 플레이북 |
| `docs/research/` | 레퍼런스 연구 원문 |

</details>

<details>
<summary><b>개발</b></summary>

<br>

```bash
# 단위 테스트, 렌더러 타입 검사
python -m pytest tests -q
cd renderer && npx tsc --noEmit

# AI 없이 전체 파이프라인
python tests/e2e_synthetic.py --browser <chrome> --face 얼굴.mp4

# 가짜 Claude Code·스톡 서버로 AI 제작팀까지 전체
python tests/e2e_studio.py --browser <chrome>

# 창 없이 실행
python -m studio run --video 원본.mp4 --topic "주제" --script 대본.txt
```

개발 규칙은 [`CLAUDE.md`](CLAUDE.md) 에 있습니다.

</details>

<br>

## 크레딧

- 렌더링: [Remotion](https://www.remotion.dev)(개인·3인 이하 회사 무료, 그 이상은 회사 라이선스)
- 음성 인식: [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- 얼굴 검출: [YuNet](https://github.com/opencv/opencv_zoo)(MIT)
- 잡음 제거: [RNNoise](https://github.com/xiph/rnnoise) 모델(BSD)
- 폰트: Pretendard · Anton · Noto Serif KR(SIL OFL)
- 효과음·음악: Pixabay · Mixkit · Freesound · Incompetech(처음 실행할 때 원 배포처에서 받으며 저장소에는 포함하지 않음)
- 스톡·자료 사진: 각 제공처 라이선스를 따르고, 출처를 설명란에 자동으로 적습니다
