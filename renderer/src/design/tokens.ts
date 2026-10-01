// 채널 디자인 시스템 — Musicbed/Filmsupply 2026 트렌드 리포트의 에디토리얼 문법을 한국어 교육 채널에 맞게 옮김.
// 네 가지 표면(surface): Ink(챕터) · Board(칠판 패널/도식) · Paper(인용/정의) · Signal(키워드/타이틀)
import type {Brand} from '../lib/types';

const hexToRgb = (hex: string): [number, number, number] => {
  const h = hex.replace('#', '');
  const v = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  const n = parseInt(v, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

export const rgba = (hex: string, a: number) => {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${a})`;
};

export const mix = (a: string, b: string, t: number) => {
  const [r1, g1, b1] = hexToRgb(a);
  const [r2, g2, b2] = hexToRgb(b);
  const m = (x: number, y: number) => Math.round(x + (y - x) * t);
  return `rgb(${m(r1, r2)}, ${m(g1, g2)}, ${m(b1, b2)})`;
};

export const makeTheme = (brand: Brand) => ({
  accent: brand.accent,
  // 표지처럼 같은 색 위에 올리는 짙은 강조색
  accentDeep: mix(brand.accent, '#000000', 0.32),
  // 어두운 배경에서 읽히는 밝은 강조색
  accentLight: mix(brand.accent, '#ffffff', 0.18),
  ink: brand.ink,
  inkSoft: '#1C1C1C',
  paper: brand.paper,
  paperLine: '#D9D6CF',
  board: '#1A1C1B',
  boardEdge: '#2A2D2B',
  chalk: '#F1ECDD',
  chalkDim: 'rgba(241, 236, 221, 0.58)',
  chalkFaint: 'rgba(241, 236, 221, 0.18)',
  white: '#FFFFFF',
  captionAccent: mix(brand.accent, '#ffb000', 0.35),
});

export type Theme = ReturnType<typeof makeTheme>;

// 롱폼 무대 재질 v2 — 종이 메모 룩(docs/롱폼_무대_디자인.md 5장): 크림 종이 · 웜 잉크 · 시그널(테마 accent) 세 색뿐
export const NOTE = {
  paper: '#F5F2EA',
  paperDeep: '#E9E4D8',
  ink: '#26211E',
  inkSoft: 'rgba(38,33,30,0.72)',
  note: 'rgba(38,33,30,0.5)',
  rule: 'rgba(38,33,30,0.16)',
  dots: 'rgba(38,33,30,0.13)',
} as const;

export const FONT = {
  sans: '"Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif',
  display: '"Pretendard", "Malgun Gothic", sans-serif',
  latin: '"Anton", "Pretendard", sans-serif',
  serif: '"Noto Serif KR", "Nanum Myeongjo", serif',
  mono: '"Pretendard", monospace',
};

// 1920 기준 타입 스케일(짧은 쪽 1080 기준으로 비례)
export const TYPE = {
  micro: 18,
  label: 22,
  body: 34,
  lead: 44,
  h3: 64,
  h2: 96,
  h1: 150,
  poster: 260,
};

// 에디토리얼 여백
export const GRID = {
  margin: 72,
  gutter: 24,
  headerH: 44,
};
