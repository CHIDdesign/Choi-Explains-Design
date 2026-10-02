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

/**
 * 서체 역할표(docs/롱폼_무대_디자인.md 6장) — 내용·성격·크기·자리로 고른다. 한 화면에 세 가족까지.
 *  sans    Pretendard 400~700   읽는 글: 자막·본문·목록·각주·작은 라벨(26px 미만은 늘 이것)
 *  display Pretendard 800~900   정밀한 제목: 용어(정의)·도식·목록 제목
 *  heavy   Black Han Sans       한 방(1~4어절, 90px 이상, 화면 중앙·전면): 키워드 슬램·훅 타이틀·챕터 제목·두 층 자막 핵심어
 *  round   Jua                  말하듯 붙인 메모(2~8어절, 40~70px, 얼굴 옆·위): 메모 헤드라인·소제목 바·콜아웃·반전 상자
 *  serif   Noto Serif KR        문장(주장·인용·여운, 40~60px): 인용 카드·챕터 주장·정리 보드 헤드라인·엔드카드
 *  latin   Anton                큰 숫자: 챕터 번호·카운터·순번
 *  numeral Playfair Display     이탤릭 세리프 숫자·영문(본문 옆 작은 것): 연도·영문 원어·단위 — <Numerals> 가 자동으로 감싼다
 *  hand    Nanum Pen Script     손글씨 주석(26px 이상, 종이 위에만): 메모 각주·사진 캡션 설명·엔드카드 메모
 */
export const FONT = {
  sans: '"Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif',
  display: '"Pretendard", "Malgun Gothic", sans-serif',
  latin: '"Anton", "Pretendard", sans-serif',
  serif: '"Noto Serif KR", "Nanum Myeongjo", serif',
  heavy: '"Black Han Sans", "Pretendard", sans-serif',
  round: '"Jua", "Pretendard", sans-serif',
  numeral: '"Playfair Display", "Noto Serif KR", serif',
  hand: '"Nanum Pen Script", "Pretendard", cursive',
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

// ─────────────────────────────────────────────────────────────────────────────
// 하우스 재질 v2(docs/upgrade/06 3장 · 06b 3·4절) — 한 영상 = 한 재질: 웜 잉크 책상 위의 크림 종이.
// 순백·순흑·#111 전면은 쓰지 않는다. 값은 [제안](스틸로 확정).
export const HOUSE = {
  paper: NOTE.paper, // 모든 그래픽의 바탕
  paperLight: '#FBF9F3', // 종이 위에 덧붙인 쪽지·사진 테두리만. 전면 금지
  paperDeep: NOTE.paperDeep, // 겹친 아랫장·괘선 종이
  ink: NOTE.ink, // 글자·선·배지 — 종이 위 대비 약 14:1
  inkSoft: NOTE.inkSoft,
  stage: '#1D1916', // 책상(무대): 화자가 줄어들 때 뒤, 챕터 카드·반전 면
  rule: NOTE.rule,
} as const;

/** 광원은 위 왼쪽 하나. 모든 그림자는 오른쪽 아래(dx : dy = 2 : 3), 색은 웜 잉크. */
export const LIGHT = {dx: 2, dy: 3, rgb: '38,33,30'} as const;

/** 높이 3단: 1 붙음(메모·자막 상자·테이프) · 2 살짝 뜸(사진·겹친 윗장·화자 사진) · 3 들림(진입·퇴장 중) */
export const ELEV = {
  1: {off: 3, blur: 6, a: 0.26, contact: 0.3},
  2: {off: 7, blur: 16, a: 0.22, contact: 0.22},
  3: {off: 14, blur: 34, a: 0.18, contact: 0},
} as const;

const mixN = (a: number, b: number, t: number) => a + (b - a) * t;
const elevAt = (level: number) => {
  const l = Math.max(1, Math.min(3, level));
  const lo = ELEV[Math.floor(l) as 1 | 2 | 3];
  const hi = ELEV[Math.ceil(l) as 1 | 2 | 3];
  const t = l - Math.floor(l);
  return {off: mixN(lo.off, hi.off, t), blur: mixN(lo.blur, hi.blur, t), a: mixN(lo.a, hi.a, t),
    contact: mixN(lo.contact, hi.contact, t)};
};

/** 사각 종이·사진·자막 상자의 box-shadow: 접촉 그림자(선명) + 주변 그림자(부드러움) 두 겹. level 은 1~3 실수. */
export const paperShadow = (level: number): string => {
  const e = elevAt(level);
  const x = (LIGHT.dx / LIGHT.dy) * e.off;
  return `1px 1.5px 1px rgba(${LIGHT.rgb},${e.contact.toFixed(3)}), `
    + `${x.toFixed(1)}px ${e.off.toFixed(1)}px ${e.blur.toFixed(1)}px rgba(${LIGHT.rgb},${e.a.toFixed(3)})`;
};

/** 찢긴 모양(SVG path)·잘린 그림의 drop-shadow — 블러 값은 고정, 위치·불투명도만(렌더 속도 규칙). */
export const paperDropShadow = (level: number): string => {
  const e = elevAt(level);
  return `drop-shadow(${((LIGHT.dx / LIGHT.dy) * e.off).toFixed(1)}px ${e.off.toFixed(1)}px ${e.blur.toFixed(1)}px `
    + `rgba(${LIGHT.rgb},${(e.a + e.contact * 0.4).toFixed(3)}))`;
};

/** 종이 물성 — 0°·완전한 직선·완벽한 정렬은 디지털의 표식이다. 값은 시드로 고정한다. */
export const PAPER_MAT = {
  rotate: {note: [0.6, 1.8], photo: [1, 3], tape: [3, 8], sticker: [2, 4], speaker: [0.3, 0.6]}, // ±도, 0 금지
  jitter: 4,
  photo: {saturate: 0.75, border: [10, 14]},
} as const;

/** 시드 → 도착 각(도). 부호도 시드가 정한다. */
export const paperRotate = (seed: number, kind: keyof typeof PAPER_MAT.rotate): number => {
  const [lo, hi] = PAPER_MAT.rotate[kind];
  const u = Math.abs(Math.sin(seed * 12.9898 + 78.233) * 43758.5453) % 1;
  const sign = Math.sin(seed * 3.1) >= 0 ? 1 : -1;
  return sign * (lo + (hi - lo) * u);
};

/** 16:9 12열 그리드. 글자·출처는 좌우 96 · 위 54 안쪽. y 900~1026 은 자막 띠. */
export const GRID16 = {W: 1920, H: 1080, margin: 96, gutter: 24, cols: 12, col: 122,
  safeTop: 54, stageTop: 84, stageBottom: 880, captionTop: 900} as const;
export const colX = (n: number): number => GRID16.margin + n * (GRID16.col + GRID16.gutter); // n = 0..11
/** k 열 폭: 4→560 · 5→706 · 8→1144 · 12→1728 (06b 의 span — 지역 변수 span 과 헷갈리지 않게 이름만 바꿈) */
export const colSpan = (k: number): number => GRID16.col * k + GRID16.gutter * (k - 1);

/** 9:16 6열 그리드. 꼭 읽혀야 하는 글자는 x 64~940, y 270~1248 안. */
export const GRID9 = {W: 1080, H: 1920, margin: 64, gutter: 20, cols: 6, col: 142,
  textLeft: 64, textRight: 940, textTop: 270, textBottom: 1248} as const;

/** 최소 글자 크기 — 캔버스가 아니라 '최종 프레임 px'(축소 배율을 곱한 값)로 잰다. check.mjs · spec.py 와 같은 값. */
export const TYPE_MIN = {
  long: {headSide: 56, headSheet: 72, body: 34, label: 28, credit: 22},
  short: {head: 72, body: 44, label: 32, credit: 26},
} as const;

/** 모션 DSL 의 size(상자 높이 대비 %)가 실제 몇 px 인지 — spec.py 의 검증과 같은 식. */
export const pxOfSize = (sizePct: number, boxH: number): number => (sizePct / 100) * boxH;

/** 채움 규칙(게이트 C2·C4 와 같은 값) */
export const FILL = {minInk: 0.45, minInkAtHalfSec: 0.35, maxEmptyStage: 0.3} as const;
