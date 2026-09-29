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
};

export type Graphic = {
  id: string;
  template: TemplateName;
  layout: Layout;
  start: number; // 편집 시간(초)
  end: number;
  data: GraphicData;
};

export type CaptionWord = {text: string; start: number; end: number; em?: boolean};
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
  captionStyle: 'shadow' | 'box';
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
