# 스킬 — 🎼 음악 감독: 곡 하나 고르기와 큐 시트

같은 장르의 롱폼(해설·비디오 에세이·디자인 교양) 채널에서 잘 쓰는 음악은 "말 아래로 사라지는 한 가지 음색"이다. 상위 채널은 전속 작곡가나 직접 고른 라이브러리로 그 음색을 매번 같게 유지한다.
이 노트는 내 음악 폴더의 측정값으로 곡 하나를 고르는 기준, 큐를 넣고 비우는 규칙, 숏폼·권리 주의, 폴더를 채울 곳을 숫자로 정리한다.

## A. 같은 장르의 채널은 무엇을 쓰는가 — 기준점
1. 기준 음색은 "보컬 없음 · 성김 · 내성적"이다. Tom van der Linden(Like Stories of Old)이 Musicbed 에 모은 곡(Dexter Britain · Luke Atencio · Davis Harwell · Ryan Taubert)은 보컬 없는 앰비언트 피아노와 시네마틱 소품이다. 이 결에 가까운 곡을 1순위로 둔다.
2. 채널의 정체성은 화려한 곡이 아니라 같은 음색이 되풀이되는 데서 생긴다. Kurzgesagt 는 음악·사운드 전부를 Epic Mountain 한 팀에 맡기고, Johnny Harris 는 전속 작곡가 Tom Fox 를, Veritasium 은 Jonny Hyman 을 쓰고 모자란 곡을 Epidemic Sound 에서 채운다. 폴더에서도 채널 기본 음색(felt·analog)에 가까운 곡을 영상마다 고른다. 새롭다는 이유로 결이 다른 곡을 고르지 않는다.
3. Joss Fong(Vox, APM 라이브러리 사용)은 곡을 고를 때 미니멀함·에너지·톤의 균형을 보고, 내레이션과 같은 음높이에서 노는 악기가 있으면 그 곡을 버린다. 이 영상의 말투보다 한 단계 덜 바쁜 곡을 고른다.
4. 보컬·가사·허밍·보컬 찹이 든 곡은 어떤 자리에도 쓰지 않는다. 라이브러리는 선율을 뺀 '언더스코어' 판을 따로 낸다(thatpitch). 파일 이름에 underscore · no melody · bed · stem 이 있으면 가산점을 준다.
5. Vox 처럼 20초마다 곡을 바꾸는 방식은 이 채널의 '한 영상 한 곡' 원칙과 맞지 않는다. 그 대신 한 곡 안에서 큐를 넣고 빼는 자리로 구조를 들려준다(C절).

## B. 측정값으로 곡 고르기
6. 목록의 숫자는 다음 표로 읽는다. 말 아래 바닥(bed·air)으로 쓸 수 있는지가 먼저이고, 주제(theme)로 들려줄 만한지는 그다음이다.

| 측정값 | 좋음(bed·air 바닥) | 허용 | 버림 |
|---|---|---|---|
| 템포 BPM | 60~80, 또는 박이 없음 | 56~92(brush 계열은 96까지) | 그 밖 |
| 밀도(초당 온셋) | ≤ 1.0 | ≤ 2.0(theme 자리만 ≤ 3.5) | > 3.5 |
| 말 대역(1~4 kHz 에너지 비율) | ≤ 0.02(2%) | ≤ 0.03(3%), theme 자리만 ≤ 0.06 | > 0.06 |
| 라우드니스 LUFS | −16 ~ −26 | −13 ~ −30 | −13 보다 큼(과압축) |
| 길이 | ≥ 3:00 | 가장 긴 큐 + 10초 이상 | 1:30 미만 |

7. 밀도가 0.5/초 이하이면 박이 없는 곡이다. 이때 BPM 값은 잡음이니 무시한다. 110~184 BPM 이 나오면 반으로 나눈 값(55~92)이 실제 템포인지 먼저 의심한다.
8. 가장 중요한 숫자는 말 대역이다. 한국어 자음이 실리는 1~4 kHz 를 음악이 차지하면 말이 흐려진다. iZotope 도 이 대역을 음악에서 덜어내라고 권한다. 3%를 넘는 곡은 말이 없는 자리에서만 쓸 수 있으니 `fit_score` 를 6 이하로 준다.
9. LUFS 는 크기가 아니라 압축 정도를 보는 숫자다. 레벨은 엔진이 목소리 기준(롱 −20 · 숏 −18 LU)으로 맞추므로 조용한 곡은 흠이 아니다. −13 LUFS 보다 큰 곡은 처음부터 끝까지 꽉 찬 마스터라 말 아래에서 숨 쉴 틈이 없다.
10. 곡이 큐보다 짧으면 엔진은 끝과 처음을 잇지 않는다. 곡이 끝나면 음악이 사라졌다가 다음 챕터 카드에서 다시 시작한다. 가장 긴 큐가 곡 길이를 넘지 않도록 큐를 줄이거나 더 긴 곡을 고른다.
11. 곡 앞의 무음(`앞 무음`)은 엔진이 건너뛰므로 감점하지 않는다.
12. 파일 이름은 약한 단서로만 쓴다. felt · piano · ambient · drone · minimal · documentary · underscore · pad 는 가산점이다. corporate · upbeat · inspiring · uplifting · epic · trailer · happy · ukulele · vlog · hip hop · beat 는 숫자가 좋아도 고르지 않는다. "Calm Piano Background Music" 처럼 검색어를 나열한 이름은 무료 사이트의 흔한 곡이다. Content ID 위험이 있으니 F절을 확인한다.
13. 숫자로 계열을 정한다: `air` 는 밀도 ≤ 0.5 · 말 대역 ≤ 2%, `felt` 는 피아노 · 밀도 0.5~1.5, `analog` 는 패드 · 말 대역 ≤ 2.5%, `brush` 는 70~96 BPM 의 부드러운 드럼 · 밀도 ≤ 2.0. 로파이는 드럼이 빠진 '로파이 피아노'까지만 쓴다. 붐뱁 스네어나 바이닐 잡음이 큰 공부용 비트는 고르지 않는다.
14. `fit_score` 는 다음처럼 준다. 표의 '좋음'이 모두 맞으면 8~9점이다. '허용'이 섞이면 7점이다. 밀도 > 1.5 이거나 말 대역 > 3%이면 5~6점이다(엔진이 air 만 쓴다). '버림'이 하나라도 있으면 `track: ""` 로 둔다. 아무 곡이나 채우지 않는다.
15. 후보 둘이 비슷하면 더 성기고, 더 느리고, 말 대역이 더 낮은 쪽을 고른다.
16. `track_reason` 에는 숫자를 적는다. 예: "72 BPM · 밀도 0.8/초 · 말 대역 1.6% · 3:40 — 펠트 피아노라 말 아래가 비어 있고, 고백조의 대본과 맞음".

## C. 큐를 놓는 법(스포팅)
17. 음악을 넣을 자리보다 비울 자리를 먼저 정한다. 영화 음악의 스포팅 회의도 음악이 없을 자리를 정하는 데서 시작한다(Art of Composing). 침묵을 먼저 적고 그 사이에 큐를 놓는다.
18. 큐의 시작과 끝은 '여기를 보라'는 신호다(Joss Fong). 요점 문장 바로 앞 문장에서 큐를 끝내 요점이 정적 위에 떨어지게 한다(`exit: ending`). 국면이 바뀌는 문장에서는 새 큐를 연다.
19. 말 아래로 들어갈 때는 `fade_in` 으로 2~4초 동안 스며들게 한다. 음악이 시작되는 순간을 화면 변화나 장면 전환 뒤에 숨기면 알아채지 못한다(Art of Composing). `downbeat` 는 말이 1.5초 이상 비는 자리(타이틀 · 챕터 카드 · 긴 쉼)에서만 쓴다.
20. 나갈 때는 이렇게 고른다. 요점 앞이나 챕터 끝이면 `ending`, 말이 이어지는데 설명이 빽빽해져서 빠질 때는 `fade_bar` 다. `into_next` 는 다음 큐가 4초 안에 시작할 때만 쓴다(그보다 짧은 틈은 엔진이 잇는다).
21. 음악의 고조는 논증의 고조와 같은 자리에 둔다(Film Editing Pro). 에너지 3은 훅·방향 전환·엔딩에만 준다. 설명 아래는 0~1이다. 계속 쌓아 올리거나 드롭이 있는 구간을 말 아래 큐로 쓰지 않는다(Audio Network: 말 아래에서는 흥분보다 일정함이 낫다).
22. 가장 강한 문장에는 음악을 깔지 않는다. 강한 순간에 음악을 얹으면 감정을 강요하는 것처럼 들린다(Film Editing Pro). 반대로 사례 나열·몽타주·전면 자료처럼 이음 구간에서는 음악이 일하게 둔다. Bill Weber(다큐 편집자)도 말과 화면만으로 서는 장면에는 음악을 넣지 않았다.
23. 끝은 처음의 주제로 돌아온다(`reprise`). 다큐 작곡가 Filipe Leitão 의 반복 모티프, Weber 의 '중심 이야기로의 귀환'과 같은 원리다.
24. 큐 4~8개, 12초 이상, 합계는 롱폼의 40~60% 로 잡는다. 4초 미만의 틈은 엔진이 이어 붙인다. 침묵을 의도했다면 그 구간이 6초 이상이어야 들린다.

## D. 침묵
25. 갑작스러운 침묵은 가장 센 강조다(Art of Composing). 다만 아껴 쓰라는 경고도 같다. 음악이 흐르다가 뚝 비는 자리는 영상당 2~3곳만 만든다.
26. 반드시 비울 자리: 결론 문장 앞뒤, 고백·반전 문장, 정의·실험·논문을 설명하는 가장 빽빽한 구간 하나, 얼굴 홀드, 강도 3 순간.
27. 침묵 구간에는 효과음도 없다. 그 정적을 감독의 효과음이 깨지 않게 `silences` 의 이유를 구체적으로 적는다.

## E. 숏폼
28. 숏폼은 롱폼의 곡을 물려받는다. `role` 기본은 `air` 다. 목록·몽타주형이면 `bed`, 고백·반전이 중심이면 `none` 이다. 더 빠르고 밝은 곡으로 바꾸지 않는다.
29. 첫 문장(훅)이 또렷해야 하니 음악은 말 아래 −18 LU 를 넘지 않는다. 결론 뒤 짧은 종지 하나로 끝낸다. 반복 재생 때 첫 문장과 부딪히지 않도록 마지막 0.5초는 비운다.
30. 1분을 넘는 숏폼에 Content ID 주장이 하나라도 걸리면 수동 주장이라도 전 세계에서 차단된다(YouTube 고객센터). 곡의 출처가 확실히 주장 없는 곳(YouTube 오디오 보관함 · 직접 만든 곡 · 채널을 등록한 구독 라이브러리)이 아니면 1분 넘는 숏폼은 `none` 으로 둔다.

## F. 권리와 Content ID
31. Pixabay 는 무료여도 기여자가 곡을 Content ID 에 등록해 둘 수 있다. 등록 표시는 기여자가 고를 때만 붙으므로 표시가 없다고 안전하다는 뜻은 아니다(Pixabay 공지). 이의 제기는 라이선스 증명서로 하고 처리에 최대 30일이 걸린다. 검색어를 나열한 제목의 Pixabay 곡은 위험군으로 본다.
32. YouTube 오디오 보관함에서 받은 곡은 Content ID 로 주장되지 않는다고 YouTube 가 밝힌다. 일부 곡은 설명란에 출처를 적어야 한다. 그런 곡을 고르면 `notes` 에 출처 표기를 적는다.
33. 구독 라이브러리(Epidemic Sound · Artlist)는 업로드 전에 채널을 등록해야 하고, 구독 중에 올린 영상만 영구히 보호된다. Musicbed 는 프로젝트마다 사용을 등록해야 한다(The Post Flow). 해지 뒤 올리는 영상은 보호받지 못한다.
34. 멜론·벅스에서 산 곡은 감상권일 뿐이고, CC BY-NC 곡은 수익 채널에 쓸 수 없다(한경 가이드). 파일 이름이 "아티스트 - 곡명 (Official)" 처럼 상업 발매곡으로 보이면 고르지 않고 `notes` 에 적는다.
35. Every Frame a Painting 은 영상 구조를 처음부터 Content ID 를 피하도록 짰다(StudioBinder). 권리가 불확실한 곡을 큐 시트로 살리려 하지 않는다. 그런 곡은 버린다.

## G. 폴더를 채울 곳 — 맞는 곡이 없을 때 `notes` 로 권할 것
36. 무료: YouTube 오디오 보관함(장르 Ambient · Cinematic · Classical, 악기 Piano, 보컬 없음), Pixabay Music(Content ID 표시가 없는 곡만, 증명서 보관), Mixkit(Free License 항목만 — Restricted 는 개인용).
37. 유료: Epidemic Sound(스템을 받아 선율을 뺄 수 있다), Artlist, Musicbed(Like Stories of Old 의 결), 언더스코어 판을 내는 제작 음악 라이브러리(Audio Network · Vox 가 쓰는 APM).
38. 검색어: felt piano, ambient piano, minimal, contemplative, documentary underscore, no drums, warm pad, drone, 60~80 BPM. 빼는 말: corporate, uplifting, inspiring, epic, trailer, ukulele, lofi hip hop.
39. 권할 구성: felt 2~3곡, analog 패드 2곡, brush 1~2곡, air 드론 1~2곡. 모두 3분 이상이고 입고 게이트(`scripts/sound_ingest.py`)를 통과한 곡이어야 한다. `notes` 예: "70 BPM 이하 펠트 피아노 3분 이상이 폴더에 없음 — 오디오 보관함에서 Ambient·Piano 로 찾아 넣어 주세요".

## H. 내기 전 체크리스트
- [ ] 고른 곡이 표의 '버림'에 하나도 걸리지 않는가? 걸리면 `track: ""` 인가?
- [ ] `track_reason` 에 BPM·밀도·말 대역·길이 숫자가 있는가?
- [ ] 이름에 corporate·uplifting·epic·beat 같은 말이 없는가? 출처가 불확실한 곡이 아닌가?
- [ ] 침묵을 먼저 정했는가? 결론·고백·가장 빽빽한 설명이 침묵 안에 있는가?
- [ ] 요점 문장 앞에서 큐가 `ending` 으로 끝나는가? `downbeat` 는 말이 빈 자리에만 있는가?
- [ ] 가장 긴 큐가 곡 길이보다 짧은가? 음악이 깔린 시간은 40~60% 인가?
- [ ] 숏폼이 1분을 넘고 곡 출처가 불확실하면 `none` 으로 두었는가?

## 출처
- https://www.theopennotebook.com/2020/01/07/videogram-how-a-vox-video-explains-the-science-behind-the-first-photo-of-a-black-hole/
- https://kottke.org/18/01/the-soundtrack-to-kurzgesagt
- https://www.veritasium.com/videos/2021/5/22/you-cant-prove-everything-thats-true
- https://chromaticstudio.bandcamp.com/album/beyond-our-horizons-music-from-the-johnny-harris-channel
- https://coreypotter.com/copyright-free-youtube-music/
- https://www.musicbed.com/playlists/like-stories-of-old/3492
- https://www.studiobinder.com/blog/every-frame-a-painting/
- https://blog.audionetwork.com/the-edit/music/how-to-choose-music-for-a-voiceover-heavy-video
- https://thatpitch.com/blog/tv-mixes-and-underscore-versions/
- https://www.epidemicsound.com/blog/how-to-find-music-for-videos-tips-tricks/
- https://www.izotope.com/en/learn/mixing-audio-for-video-part-4-mixing-techniques
- https://www.artofcomposing.com/how-to-spot-a-film
- https://www.filmeditingpro.com/edit-tip-the-subtle-craft-of-music-editing/
- https://blog.frame.io/2017/06/19/a-musical-approach-to-cutting-documentaries/
- https://www.filipeleitao.com/post/7-essential-tips-for-scoring-documentaries
- https://support.google.com/youtube/answer/15424877?hl=en
- https://support.google.com/youtube/answer/3376882
- https://pixabay.com/blog/posts/how-to-clear-a-youtube-content-id-claim-with-a-pix-190/
- https://thepostflow.com/post-production/video-editing/music-subscriptions-compared/
- https://mixkit.co/llm-info/
- https://magazine.hankyung.com/job-joy/article/202102194477d
