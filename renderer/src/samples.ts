// Studio 미리보기 / 템플릿 갤러리용 기본 props (실제 작업에서는 Python 이 props 를 만든다)
import type {Brand, Episode, LongFormProps, ShortProps, ThumbnailProps} from './lib/types';

export const SAMPLE_BRAND: Brand = {
  name: 'CHOI EXPLAINS DESIGN',
  shortName: 'CHOI',
  handle: '',
  presenter: '최은준',
  presenterTitle: '홍익대학교 산업디자인 · 제품디자인',
  accent: '#F93107',
  ink: '#111111',
  paper: '#F4F4F2',
  year: '2026',
};

export const SAMPLE_EPISODE: Episode = {
  title: '좋은 디자인은 질문에서 시작한다',
  number: '01',
  subtitle: 'design theory, explained',
  series: '디자인 이론',
};

const g = (id: string, template: LongFormProps['graphics'][number]['template'], layout: LongFormProps['graphics'][number]['layout'],
  start: number, end: number, data: LongFormProps['graphics'][number]['data']) => ({id, template, layout, start, end, data});

export const SAMPLE_LONG: LongFormProps = {
  fps: 30,
  width: 1920,
  height: 1080,
  duration: 64,
  brand: SAMPLE_BRAND,
  episode: SAMPLE_EPISODE,
  clips: [],
  voice: null,
  bgm: null,
  sfx: [],
  captions: [
    {start: 0.5, end: 3.5, lines: [[{text: '디자인은', start: 0.5, end: 1}, {text: '먼저', start: 1, end: 1.4},
      {text: '넓게', start: 1.4, end: 1.8, em: true}, {text: '펼쳐야', start: 1.8, end: 2.4}, {text: '합니다.', start: 2.4, end: 3}]]},
  ],
  captionStyle: 'shadow',
  face: [{t: 0, x: 0.42, y: 0.4, s: 0.3}],
  camera: [{start: 0, end: 64, zoom: 1, zoomEnd: 1.03}],
  punches: [],
  graphics: [
    g('t', 'title', 'fullscreen', 0.2, 3.6, {title: '좋은 디자인은 질문에서 시작한다'}),
    g('c', 'chapter', 'fullscreen', 4, 7, {title: '문제를 다시 정의하기', subtitle: '더블 다이아몬드의 첫 번째 다이아몬드', number: '02'}),
    g('d', 'double_diamond', 'split', 7.5, 14, {title: '더블 다이아몬드', items: ['발견', '정의', '개발', '전달'], highlight: 1}),
    g('k', 'keyword', 'overlay', 14.5, 17.5, {title: '발산 먼저, 수렴은 나중', subtitle: '넓게 펼친 뒤에 좁힌다'}),
    g('p', 'process', 'fullscreen', 18, 25, {title: '디자인 씽킹 5단계', items: ['공감', '정의', '아이디어', '프로토타입', '테스트'], highlight: 2}),
    g('q', 'quote', 'fullscreen', 25.5, 31, {body: '좋은 디자인은 가능한 한 적게 디자인하는 것이다.', author: '디터 람스', source: '10 Principles of Good Design'}),
    g('l', 'list', 'split', 31.5, 38, {title: '좋은 질문의 조건', items: ['구체적이다', '열려 있다', '사용자를 향한다']}),
    g('v', 'compare', 'fullscreen', 38.5, 44, {title: '발산', items: ['넓게', '많이', '판단 보류'], title_b: '수렴', items_b: ['좁게', '깊게', '선택과 집중'], subtitle: '두 가지 사고방식'}),
    g('df', 'definition', 'fullscreen', 44.5, 50, {title: '어포던스', subtitle: 'Affordance', body: '사물의 형태가 사용 방법을 스스로 알려주는 성질'}),
    g('m', 'matrix', 'fullscreen', 50.5, 56, {title: '기능과 감성', items: ['감성 높음·기능 낮음', '둘 다 높음', '둘 다 낮음', '기능 높음·감성 낮음'], items_b: ['기능 낮음', '기능 높음', '감성 낮음', '감성 높음'], highlight: 1}),
    g('s', 'stat', 'overlay', 56.5, 60, {title: '85%', body: '다섯 명의 사용자가 찾아내는 사용성 문제', subtitle: 'Nielsen, 2000'}),
  ],
  chapters: [{start: 0, title: '들어가며', number: '01'}, {start: 4, title: '문제를 다시 정의하기', number: '02'}],
  panelSide: 'right',
  endcard: {start: 60.5, dur: 3.5},
  grain: 0,
  grainFrames: [],
  showChapterLabel: true,
};

export const SAMPLE_SHORT: ShortProps = {
  fps: 30,
  width: 1080,
  height: 1920,
  duration: 20,
  brand: SAMPLE_BRAND,
  episode: SAMPLE_EPISODE,
  clips: [],
  voice: null,
  bgm: null,
  sfx: [],
  captions: [
    {start: 0, end: 1.4, lines: [[{text: '대부분의', start: 0, end: 0.6}, {text: '학생들은', start: 0.6, end: 1.4}]]},
    {start: 1.4, end: 3, lines: [[{text: '이 단계를', start: 1.4, end: 2.1, em: true}, {text: '건너뜁니다', start: 2.1, end: 3}]]},
  ],
  face: [{t: 0, x: 0.45, y: 0.4, s: 0.3}],
  punches: [],
  graphics: [{id: 's1', template: 'double_diamond', layout: 'split', start: 6, end: 14,
    data: {title: '더블 다이아몬드', items: ['발견', '정의', '개발', '전달'], highlight: 0}}],
  hookTitle: '디자인과 학생들이\n몰래 건너뛰는 단계',
  hookHighlight: '건너뛰는',
  seriesLabel: '디자인 이론 #01',
  layout: 'full',
  progressBar: false,
  grain: 0,
  grainFrames: [],
};

export const SAMPLE_THUMB: ThumbnailProps = {
  width: 1280,
  height: 720,
  brand: SAMPLE_BRAND,
  episode: SAMPLE_EPISODE,
  image: '',
  text: '디자인은\n질문이다',
  highlight: '질문',
  variant: 'signal',
  faceX: 0.6,
};
