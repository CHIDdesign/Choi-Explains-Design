// Python(studio/render/props.py) 이 만드는 props 의 타입. 두 쪽을 함께 수정할 것.

export type TemplateName =
  | 'chapter'
  | 'keyword'
  | 'definition'
  | 'quote'
  | 'list'
  | 'process'
  | 'cycle'
  | 'double_diamond'
  | 'matrix'
  | 'compare'
  | 'timeline'
  | 'stat'
  | 'venn'
  | 'pyramid'
  | 'photo'
  | 'motion' // 모션 디자이너 에이전트가 설계한 장면(MotionSpec)
  | 'card' // 자유 HTML 카드(HyperFrames 카드 규약 호환, components/card/HtmlCard.tsx)
  | 'broll' // 스톡 영상/사진(Pixabay·Unsplash·Coverr·Pexels)
  | 'evidence' // 증거 자료(자료 리서처 → 조달 사다리, components/longform/Evidence.tsx — 03b)
  // 자동 템플릿(디렉터가 직접 고르지 않음)
  | 'title'
  | 'lower_third'
  | 'recap'; // 챕터 끝 정리 보드(studio/render/props.py chapter_recaps — 그 챕터의 핵심 개념 2~4개)

export type Layout = 'fullscreen' | 'split' | 'overlay' | 'pip';

// 증거 자료(docs/upgrade/03b 1절) — studio/assets/ladder.py 가 채운다
export type Treatment = 'hero' | 'full' | 'pip' | 'archive_card' | 'doc_highlight' | 'browser_frame' | 'grid'
  | 'compare_pair' | 'collage';
export type NBox = [number, number, number, number]; // x, y, w, h — 0~1, 이미지 기준
export type EvidenceAsset = {
  src: string; // public 기준 경로
  kind: 'photo' | 'video' | 'screen' | 'document' | 'logo';
  w: number;
  h: number; // 원본 픽셀
  focus?: NBox | null; // 비전 선택이 준 초점 상자
  credit?: string; // credit_short
  tier?: string; // own | made | A | A-sa | stock | B | C
  meta?: {title?: string; creator?: string; year?: string; ref?: string};
  cut?: string; // 배경을 오려 낸 PNG(studio/assets/cutout.py) — 콜라주에서 바닥 타원 위에 선다
};
export type Archive = {
  variant: 'photo' | 'source' | 'type'; // 자료 카드 · 출처 카드(논문·책) · 타이포 자료 카드
  title: string;
  rows?: {k: string; v: string}[];
  label?: string;
  quote?: string;
  ref?: string;
};

export type GraphicData = {
  title?: string;
  subtitle?: string;
  body?: string;
  items?: string[];
  title_b?: string;
  items_b?: string[];
  highlight?: number;
  stepAt?: {t: number; index: number}[]; // 단계 그래픽: 그래픽 시작 기준 초 — 그 낱말에서 강조 단계가 바뀐다
  author?: string;
  source?: string;
  image?: string; // public 폴더 기준 상대경로 (예: images/braun.jpg)
  credit?: string;
  number?: string; // 챕터 번호 등
  spec?: MotionSpec; // motion
  card?: CardSpec; // card
  scene?: string; // motion: 코드 생성 장면 id(실험적)
  kind?: 'video' | 'photo'; // broll
  logo?: boolean; // photo: 브랜드 로고 카드(크림 종이 위 로고 SVG) — 어두운 그라데이션·필름 룩 없이, 글은 잉크색
  mat?: boolean; // photo: 세로 사진을 크림 종이 여백 액자(1600×1000)에 넣은 것 — 로고 카드처럼 그린다
  src?: string; // broll: public 기준 경로
  kenburns?: 'in' | 'out' | 'left' | 'right'; // broll 사진 움직임
  w?: number; // broll 사진 원본 크기(콜라주 배치용)
  h?: number;
  cut?: string; // 배경을 오려 낸 PNG(콜라주)
  accent?: string; // 개념 카드·사진 액자 글(두 스킨): 헤드라인에서 주황으로 칠할 낱말(없으면 마지막 어절)
  // 전면 사진·스톡 위 키워드 슬램(studio/render/props.py fold_keywords_into_media): keyword_at 초부터 사진이 어두워지며
  // 큰 키워드 + 아랫줄(keyword_sub, 예: "수렵·채집 → 농경")
  keyword?: string;
  keyword_sub?: string;
  keyword_at?: number;
  // evidence
  assets?: EvidenceAsset[];
  treatment?: Treatment;
  archive?: Archive;
  caption?: string; // 사실 캡션(연도·작가·출처)
  year?: string; // 콜라주의 이탤릭 세리프 연도(레퍼런스 '1853') — 4자리
  display?: string; // 콜라주의 큰 인쇄 글자(2~6자, 레퍼런스 '설계안 채택')
  quote?: string; // 영상·사진 위 명조 인용(줄바꿈 \n, 40자 이내)
  tier?: string;
  lines?: NBox[]; // doc_highlight: 밑줄 칠 줄
};

// 화면 스킨(기본 classic):
//  classic = 에디토리얼(칠판·잉크) + 레퍼런스 일부 — 얼굴 위 찢어진 사진 액자·검정 라벨·큰 개념 텍스트(화자는 전체 화면 그대로),
//            칠판 split 패널 안 개념 카드 글 위계, 타이틀 = 글 왼쪽 + 화자 액자 오른쪽, 우상단 출처, 오늘의 정리 엔드카드,
//            레퍼런스식 콜아웃
//  paper   = 레퍼런스 종이 콜라주 전체 — 구겨진 짙은 종이·회색 거친 테두리·찢어진 액자·화자 액자 샷(CameraShot.framed),
//            전면 개념 카드는 split 으로(props.paper_layouts)
export type Skin = 'paper' | 'classic' | 'hybrid';
// 그래픽·챕터 하나의 모양(하이브리드에서 파이썬 studio/edit/style.py 가 정한다)
export type Look = 'paper' | 'classic';

// ---------------------------------------------------------------------------
// MotionSpec — 모션 디자이너 에이전트가 JSON 으로 쓰는 장면 기술(코드 실행 없이 안전하게 렌더)
// 좌표는 장면 상자 기준 퍼센트(x: 0~100 가로, y: 0~100 세로), 시간은 장면 시작 기준 초.
// ---------------------------------------------------------------------------
export type MotionColor = 'fg' | 'dim' | 'faint' | 'accent' | 'bg' | 'white' | 'ink';
// v2(docs/upgrade/06 7-1): place 붙이기 · unfold 펼치기 · write 손글씨처럼 왼→오
export type MotionEnter = 'fade' | 'up' | 'down' | 'left' | 'right' | 'scale' | 'mask' | 'draw' | 'pop' | 'none' | 'place'
  | 'unfold' | 'write';
export type MotionKey = {t: number; x?: number; y?: number; scale?: number; rotate?: number; opacity?: number};

export type MotionElBase = {
  id?: string;
  at?: number; // 등장 시각
  dur?: number; // 등장 애니메이션 길이(초)
  out?: number; // 퇴장 시각(없으면 장면 끝까지)
  x: number;
  y: number;
  anchor?: 'center' | 'left' | 'right';
  color?: MotionColor;
  opacity?: number;
  enter?: MotionEnter;
  ease?: 'out' | 'inOut' | 'back' | 'linear' | 'enterLarge' | 'move' | 'settle';
  keys?: MotionKey[]; // 이동·확대·회전 키프레임
  ghost?: boolean; // 0초부터 흐린 자리 표시(0.22)로 서 있다가 at 에 채워진다(빈 화면 금지)
};

export type MotionText = MotionElBase & {
  type: 'text';
  text: string;
  size: number; // 장면 높이 대비 %
  weight?: number;
  // 디자인 v3: display=고운바탕 700 명조 · serif=고운바탕 · poster=송명 · italic=Instrument Serif · heavy=Black Han Sans · round=도장 명조 · hand=손글씨
  font?: 'sans' | 'display' | 'serif' | 'poster' | 'italic' | 'latin' | 'heavy' | 'round' | 'hand';
  maxWidth?: number; // %
  align?: 'left' | 'center' | 'right';
  highlight?: string; // 강조색으로 칠할 부분 문자열
  reveal?: 'words' | 'chars' | 'lines' | 'none';
};
export type MotionRect = MotionElBase & {type: 'rect'; w: number; h: number; radius?: number; fill?: MotionColor | 'none';
  stroke?: MotionColor | 'none'; strokeWidth?: number};
export type MotionCircle = MotionElBase & {type: 'circle'; r: number; fill?: MotionColor | 'none'; stroke?: MotionColor | 'none';
  strokeWidth?: number};
export type MotionLine = MotionElBase & {type: 'line' | 'arrow'; x2: number; y2: number; strokeWidth?: number; dashed?: boolean;
  curve?: number};
export type MotionPath = MotionElBase & {type: 'path'; d: string; fill?: MotionColor | 'none'; stroke?: MotionColor | 'none';
  strokeWidth?: number};
export type MotionDots = MotionElBase & {type: 'dots'; count: number; cols: number; gap: number; r: number;
  fill?: MotionColor; highlight?: number[];
  groups?: number[]; // 예: [4,4,4] → groupAt 에 세 무리로 재배치(게슈탈트 근접성 등)
  groupAt?: number;
  groupGap?: number; // 무리 사이 추가 간격(%)
};
export type MotionCounter = MotionElBase & {type: 'counter'; from: number; to: number; decimals?: number; prefix?: string;
  suffix?: string; size: number};
export type MotionBar = MotionElBase & {type: 'bar'; w: number; h: number; value: number; label?: string};
// frame: torn = 찢어진 흰 액자(사진), cutout = 오려 붙인 듯 그림자만(투명 PNG 오브젝트), none = 그대로
// print = 종이 위에 붙인 프린트(얇은 종이 테두리 + 높이 2 그림자 + 시드 각도)
// tint: ink = 잉크 단색(컬러 클립아트 금지, 게이트 B8) · duotone = 잉크→종이 두 색
export type MotionImage = MotionElBase & {type: 'image'; src: string; w: number; h: number; radius?: number;
  frame?: 'torn' | 'cutout' | 'none' | 'print'; tint?: 'none' | 'ink' | 'duotone'};
// 손으로 친 주석 — 가리킬 상자(가운데 x, y · w, h %)에 동그라미·밑줄·화살표·괄호·취소선을 그려 넣는다
export type MotionMark = MotionElBase & {type: 'mark'; kind: 'circle' | 'underline' | 'arrow' | 'bracket' | 'strike';
  w: number; h: number; strokeWidth?: number};

export type MotionEl = MotionText | MotionRect | MotionCircle | MotionLine | MotionPath | MotionDots | MotionCounter |
  MotionBar | MotionImage | MotionMark;

export type MotionSpec = {
  bg?: 'board' | 'paper' | 'ink' | 'signal' | 'transparent';
  grid?: boolean;
  label?: string; // 괄호 라벨(예: 게슈탈트 · 근접성)
  hero?: number; // 크게 움직이는 주 요소의 번호(린트 L26)
  layout_intent?: 'asym';
  elements: MotionEl[];
};

// 자유 HTML 카드(studio/motion/card.py clean_card 가 정리한 것만 들어온다):
// html = .card 안쪽 조각, css = `.card[data-card-id="id"]` 로 스코프된 규칙, w×h = 작성 캔버스(렌더러가 상자에 맞춰 축소)
// timeline: 모션 디자이너가 직접 쓴 GSAP 타임라인 코드(card_dsl.md 7절) — fn(tl, q, gsap, ctx) 본문, 결정적(seek 로만)
export type CardSpec = {id: string; html: string; css: string; w: number; h: number; style?: string; timeline?: string};

// 얼굴 옆 액자·개념 텍스트의 자리(studio/render/props.py face_safe_layouts): 얼굴 트랙으로 고른 빈 쪽 + 여유에 맞춘 크기.
// side 'top' = 짧은 키워드를 화면 위 소제목 바(종이 띠 + '!' 배지)로 — 머리 위가 비어 있을 때만
export type PipPlacement = {side: 'left' | 'right' | 'top'; w: number; h: number};

export type Graphic = {
  id: string;
  template: TemplateName;
  layout: Layout;
  start: number; // 편집 시간(초)
  end: number;
  data: GraphicData;
  skin?: Look; // 하이브리드: 이 그래픽을 종이 콜라주로 그릴지 기본 디자인으로 그릴지(없으면 props.skin)
  pip?: PipPlacement; // pip/overlay: 얼굴을 가리지 않는 자리(없으면 렌더러가 faceX 로 반대편)
  // 시퀀스(한 주장을 받치는 연속 화면)의 몇 번째 샷인가 — 둘째 샷부터는 등장 애니메이션 없이 같은 틀 안의 컷(docs/upgrade/05 6-5)
  seq?: {id: string; type: string; index: number; count: number};
};

// 강조 종류: keyword(핵심어 밑줄 스윕) · term(전문용어 형광 마커) · number(숫자 Anton) · contrast(대비어)
export type EmType = 'keyword' | 'term' | 'number' | 'contrast';
export type CaptionWord = {text: string; start: number; end: number; em?: boolean | EmType};
export type LongCaptionPreset = 'paper' | 'editorial' | 'documentary' | 'glass' | 'boxed';
export type ShortCaptionPreset = 'paper' | 'kinetic' | 'clean' | 'boxed' | 'bar';
// style: 'impact' = 강조 순간(강조 줌·효과음과 함께) 자막을 크게 가운데로 — 셜록현준·지식 채널식 강조 자막
//        (paper 자막 프리셋은 크기를 바꾸지 않는다)
// hidden: 화면 그래픽(개념 카드·도식·콜아웃·숏폼 카드)이 같은 말을 이미 보여 줄 때 — 화면 자막만 끈다(SRT 에는 남음)
// style: impact(편집 엔진이 고른 강조 순간) · stack(몇 초에 한 번, 핵심어가 든 한 마디) — 둘 다 두 층 강조 자막으로 그린다
export type CaptionCue = {start: number; end: number; lines: CaptionWord[][]; style?: 'impact' | 'stack';
  hidden?: boolean};

export type Clip = {
  src: string; // public 기준 경로
  srcStart: number; // 원본(proxy) 시각(초)
  start: number; // 편집 타임라인 시각(초)
  dur: number;
  soft?: number; // 같은 프레이밍의 점프컷: 앞 장면 마지막 프레임을 이 초만큼 섞는다
};

export type FaceSample = {t: number; x: number; y: number; s: number};
// 점프컷 프레이밍: 컷 지점에서 와이드(1.00) ↔ 미디엄(1.06)(콜아웃 자리 만들기는 1.10), zoom→zoomEnd 는 샷 안 느린 드리프트,
// x 는 얼굴을 옆으로 옮길 비율(-0.1~0.1)
// glide: 이 샷이 시작할 때 앞 샷의 프레이밍에서 이 초만큼 천천히 옮겨 온다(없으면 컷)
// framed: 종이 스킨에서 화자를 찢어진 액자에 담아 종이 위에(레퍼런스 2)
export type CameraShot = {start: number; end: number; zoom: number; zoomEnd: number; x?: number; glide?: number;
  framed?: boolean};
// 강조 줌: 강조 순간 카메라를 당김. style glide = 0.7초에 걸쳐 당기고 0.9초에 걸쳐 풀림(편집 문법 엔진이 쓰는 것),
// ease = 5프레임 푸시, cut = 하드컷(한 프레임) — ease·cut 은 렌더러에만 남아 있다
export type Punch = {t: number; end: number; amount: number; style?: 'cut' | 'ease' | 'glide'};

// 장면 전환(컷 지점 t 를 가운데 두고 앞뒤로 dur/2 씩): 나가는 장면이 가속하며 빠지고 들어오는 장면이 감속하며 안착.
// 편집 문법 엔진은 blur·push·wipe·leak 만 만든다(whip·zoom·flash·dip 은 렌더러에만 남아 있다)
export type TransitionType = 'whip' | 'zoom' | 'blur' | 'push' | 'flash' | 'dip' | 'wipe' | 'leak';
export type Transition = {
  t: number;
  type: TransitionType;
  dur: number; // 초(전체)
  dir?: 'left' | 'right' | 'up' | 'down';
  color?: string; // wipe/dip 색(없으면 테마)
};
export type Keyframe = {t: number; v: number};
export type Chapter = {start: number; title: string; number: string; look?: Look};

// 키워드 콜아웃: 화자 반대편, 얼굴을 피한 빈 공간에 2줄 굵은 흰 글씨 + 검정 맥락 라벨(레퍼런스식). 자막과 별도 레이어.
export type Callout = {start: number; end: number; text: string; highlight: string; label: string;
  side: 'left' | 'right'};

export type Brand = {
  name: string;
  shortName: string;
  handle: string;
  presenter: string;
  presenterTitle: string;
  accent: string;
  ink: string;
  paper: string;
  year: string;
  deep?: string; // 디자인 팔레트의 짙은 색(큰 글자·연도) — 없으면 accent 에서
  tint?: string; // 디자인 팔레트의 옅은 색(형광펜·바닥 타원·이름표) — 없으면 accent 에서
};

export type Episode = {title: string; number: string; subtitle: string; series: string};

export type AudioTrack = {src: string; volume: number};
export type Bgm = {src: string; envelope: Keyframe[]; loop: boolean};
export type Sfx = {src: string; t: number; volume: number};

export type LongFormProps = {
  fps: number;
  width: number;
  height: number;
  duration: number; // 초
  brand: Brand;
  episode: Episode;
  clips: Clip[];
  voice: AudioTrack | null;
  bgm: Bgm | null;
  sfx: Sfx[];
  captions: CaptionCue[];
  captionPreset: LongCaptionPreset;
  face: FaceSample[];
  camera: CameraShot[];
  punches: Punch[];
  graphics: Graphic[];
  transitions: Transition[];
  callouts: Callout[];
  chapters: Chapter[];
  panelSide: 'left' | 'right';
  endcard: {start: number; dur: number} | null;
  grain: number; // 0 = 끔, 0.04~0.08 권장
  grainFrames: string[];
  showChapterLabel: boolean;
  peekEvery: number; // 렌더 중 진행 화면 미리보기 간격(프레임), 0 = 끔
  skin?: Skin;
  paperTexture?: string; // public 기준 구겨진 종이 텍스처(없으면 단색)
};

// 숏폼 개념 텍스트(3~5초마다 바뀜): reel 은 위 카드(흰 개념 카드 + 형광펜), 종이 스킨 숏폼은 하단(검정 라벨 + 큰 글씨)
export type ShortBeat = {start: number; end: number; text: string; label?: string; accent?: string};

export type ShortProps = {
  fps: number;
  width: number;
  height: number;
  duration: number;
  brand: Brand;
  episode: Episode;
  clips: Clip[];
  voice: AudioTrack | null;
  bgm: Bgm | null;
  sfx: Sfx[];
  captions: CaptionCue[];
  captionPreset: ShortCaptionPreset;
  face: FaceSample[];
  camera: CameraShot[];
  punches: Punch[];
  graphics: Graphic[];
  transitions: Transition[];
  hookTitle: string; // 줄바꿈 \n
  hookHighlight: string;
  seriesLabel: string;
  // window = 셜록현준식 레터박스(상단 2줄 제목 · 가운데 1080×1030 창 · 창 안 하단 자막 · 로고)
  // reel = 참고 릴스식(위 큰 카드 · 아래 얼굴 · 이음새 굵은 자막) — 기본
  layout: 'full' | 'framed' | 'window' | 'reel';
  progressBar: boolean;
  grain: number;
  grainFrames: string[];
  peekEvery: number; // 렌더 중 진행 화면 미리보기 간격(프레임), 0 = 끔
  skin?: Skin;
  paperTexture?: string;
  beats?: ShortBeat[];
};

export type ThumbnailProps = {
  width: number;
  height: number;
  brand: Brand;
  episode: Episode;
  image: string;
  text: string; // 줄바꿈 \n
  highlight: string;
  variant: 'signal' | 'ink' | 'photo';
  faceX: number;
};

export type GalleryProps = {
  brand: Brand;
  episode: Episode;
  template: TemplateName;
  layout: Layout;
  data: GraphicData;
  video: string;
};
