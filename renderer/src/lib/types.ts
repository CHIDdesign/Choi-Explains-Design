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
  | 'broll' // 스톡 영상/사진(Pixabay·Unsplash·Coverr·Pexels)
  // 자동 템플릿(디렉터가 직접 고르지 않음)
  | 'title'
  | 'lower_third';

export type Layout = 'fullscreen' | 'split' | 'overlay' | 'pip';

export type GraphicData = {
  title?: string;
  subtitle?: string;
  body?: string;
  items?: string[];
  title_b?: string;
  items_b?: string[];
  highlight?: number;
  author?: string;
  source?: string;
  image?: string; // public 폴더 기준 상대경로 (예: images/braun.jpg)
  credit?: string;
  number?: string; // 챕터 번호 등
  spec?: MotionSpec; // motion
  scene?: string; // motion: 코드 생성 장면 id(실험적)
  kind?: 'video' | 'photo'; // broll
  src?: string; // broll: public 기준 경로
  kenburns?: 'in' | 'out' | 'left' | 'right'; // broll 사진 움직임
};

// ---------------------------------------------------------------------------
// MotionSpec — 모션 디자이너 에이전트가 JSON 으로 쓰는 장면 기술(코드 실행 없이 안전하게 렌더)
// 좌표는 장면 상자 기준 퍼센트(x: 0~100 가로, y: 0~100 세로), 시간은 장면 시작 기준 초.
// ---------------------------------------------------------------------------
export type MotionColor = 'fg' | 'dim' | 'faint' | 'accent' | 'bg' | 'white' | 'ink';
export type MotionEnter = 'fade' | 'up' | 'down' | 'left' | 'right' | 'scale' | 'mask' | 'draw' | 'pop' | 'none';
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
  ease?: 'out' | 'inOut' | 'back' | 'linear';
  keys?: MotionKey[]; // 이동·확대·회전 키프레임
};

export type MotionText = MotionElBase & {
  type: 'text';
  text: string;
  size: number; // 장면 높이 대비 %
  weight?: number;
  font?: 'sans' | 'display' | 'serif' | 'latin';
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
export type MotionImage = MotionElBase & {type: 'image'; src: string; w: number; h: number; radius?: number};

export type MotionEl = MotionText | MotionRect | MotionCircle | MotionLine | MotionPath | MotionDots | MotionCounter |
  MotionBar | MotionImage;

export type MotionSpec = {
  bg?: 'board' | 'paper' | 'ink' | 'signal' | 'transparent';
  grid?: boolean;
  label?: string; // 괄호 라벨(예: 게슈탈트 · 근접성)
  elements: MotionEl[];
};

export type Graphic = {
  id: string;
  template: TemplateName;
  layout: Layout;
  start: number; // 편집 시간(초)
  end: number;
  data: GraphicData;
};

// 강조 종류: keyword(핵심어 밑줄 스윕) · term(전문용어 형광 마커) · number(숫자 Anton) · contrast(대비어)
export type EmType = 'keyword' | 'term' | 'number' | 'contrast';
export type CaptionWord = {text: string; start: number; end: number; em?: boolean | EmType};
export type LongCaptionPreset = 'editorial' | 'documentary' | 'glass' | 'boxed';
export type ShortCaptionPreset = 'kinetic' | 'clean' | 'boxed';
export type CaptionCue = {start: number; end: number; lines: CaptionWord[][]};

export type Clip = {
  src: string; // public 기준 경로
  srcStart: number; // 원본(proxy) 시각(초)
  start: number; // 편집 타임라인 시각(초)
  dur: number;
};

export type FaceSample = {t: number; x: number; y: number; s: number};
export type CameraShot = {start: number; end: number; zoom: number; zoomEnd: number};
export type Punch = {t: number; end: number; amount: number};
export type Keyframe = {t: number; v: number};
export type Chapter = {start: number; title: string; number: string};

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
  chapters: Chapter[];
  panelSide: 'left' | 'right';
  endcard: {start: number; dur: number} | null;
  grain: number; // 0 = 끔, 0.04~0.08 권장
  grainFrames: string[];
  showChapterLabel: boolean;
};

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
  punches: Punch[];
  graphics: Graphic[];
  hookTitle: string; // 줄바꿈 \n
  hookHighlight: string;
  seriesLabel: string;
  layout: 'full' | 'framed';
  progressBar: boolean;
  grain: number;
  grainFrames: string[];
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
