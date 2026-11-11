// 채널 디자인 토큰 — 현재 룩은 디자인 v5(docs/디자인_v5_토크쇼.md). NOTE·HOUSE·종이 그림자는 시험용 종이 스킨(components/paper/)만 쓴다.
import type {Brand} from '../lib/types';

const hexToRgb = (hex: string): [number, number, number] => {
  // 'rgb(r, g, b)' / 'rgba(…)' 도 받는다 — mix() 결과를 다시 mix() 에 넣으면 NaN 색(검정)이 되던 것(IsoBlocks 길 색)
  const m = hex.match(/^rgba?\(([^)]+)\)/);
  if (m) {
    const p = m[1].split(',').map((x) => parseFloat(x));
    return [p[0] || 0, p[1] || 0, p[2] || 0];
  }
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
  // 표지처럼 같은 색 위에 올리는 짙은 강조색(디자인 팔레트가 정해 주면 그 값 — 레퍼런스의 짙은 초록 큰 글자)
  accentDeep: brand.deep || mix(brand.accent, '#000000', 0.32),
  // 디자인 v5: 띠(챕터 배지·용어·아이덴트)의 짙은 숲색 — 채널 오렌지(accent)는 작은 표식과 밑줄에만
  band: brand.band || '#1E2A3A',
  // 형광펜·바닥 타원·이름표(디자인 v3 종이 콜라주 — 레퍼런스의 민트)
  accentTint: brand.tint || mix(brand.accent, '#ffffff', 0.5),
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

// ─────────────────────────────────────────────────────────────────────────────
// 디자인 v5 — 1인 시사교양 토크쇼(docs/디자인_v5_토크쇼.md). 화면의 주인공은 디자인된 면이 아니라 사람과 자료다.
// 도식 면은 평면 #F4F3EE 또는 차콜 #1E2124, 그라디언트·번짐·카드 그림자 없음(글자 가독 그림자 TEXT_SHADOW 만).
export const DESIGN = 'v5' as const;
export const MODERN = {
  bg: '#F4F3EE',
  ink: '#1E2124',
  inkSoft: 'rgba(30,33,36,0.66)',
  line: 'rgba(30,33,36,0.16)',
  card: '#F4F3EE',
  dark: '#1E2124',
  darkInk: '#F4F3EE',
  darkSoft: 'rgba(244,243,238,0.66)',
} as const;
/** 재질 키트 색(디자인 v5.1, 팔레트 B 2026-11-11). 이름은 역할이다 — forest = 띠(잉크 네이비), mint = 머리표(옅은 골드),
 *  orange = 표식(바랜 골드: 테이프·표식·형광 밑줄에만, 넓은 면을 채우지 않는다). */
export const MAT = {forest: '#1E2A3A', mint: '#D8C49A', eggshell: '#F4F3EE', parchment: '#EFE9DC', memo: '#FBF9F3', kraft: '#B89B72', charcoal: '#1E2124',
  ink: '#22211E', inkSoft: 'rgba(34,33,30,0.68)', orange: '#B08D57', graphite: '#3C3B38', stamp: '#8E3B2E', fibre: '#EFE6D2'} as const;

export const TEXT_SHADOW = '0 2px 4px rgba(0,0,0,0.55), 0 0 18px rgba(0,0,0,0.35)';

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

const SANS = '"Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif';
const ITALIC = '"Instrument Serif", "Playfair Display", serif';
/** 디자인 v5: Pretendard 하나(라벨 600 · 본문 500 · 핵심어 800). 명조는 인용에만(quote), 기울임은 영문 원어 표기에만(italic). */
export const FONT = {
  sans: SANS,
  display: SANS,
  latin: SANS,
  serif: SANS,
  editorial: SANS,
  poster: SANS,
  italic: ITALIC,
  heavy: SANS,
  round: SANS,
  memo: SANS,
  numeral: SANS,
  hand: SANS,
  mono: SANS,
  quote: '"Gowun Batang", "Noto Serif KR", serif',
  masthead: '"Hahmlet", "Noto Serif KR", serif',      // 저널 제호(콜라주 이름표)
  pen: '"Nanum Pen Script", "Pretendard", sans-serif', // 메모지 위 짧은 글에만
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

/** 종이 그림자 v5.1: 접촉(선명) + 넓은 부드러운(들뜸) 두 겹. 광원은 위 왼쪽 하나. 놓인 곳마다 다르다 — photo: 사진·화자·책상 위(순수 어둠) · board: 밝은 종이 위(따뜻한 어둠) · dark: 아주 어두운 사진 위(넓은 그림자는 배경보다 밝아 안개가 된다) */
const LIFT = {
  photo: {rgb: '0,0,0', ca: 0.5, wy: [2, 3], wb: [6, 6], wa: [0.23, 0.06], dx: 0.25},
  board: {rgb: '60,50,35', ca: 0.35, wy: [2, 6], wb: [4, 12], wa: [0.1, 0.06], dx: 0.43},
  dark: {rgb: '0,0,0', ca: 0.5, wy: [0, 0], wb: [0, 0], wa: [0, 0], dx: 0},
} as const;
export type LiftOn = keyof typeof LIFT;
/** level 0~3 실수, k = 종이마다 다른 들뜸(시드, ±30%) */
const liftAt = (level: number, k: number, on: LiftOn) => {
  const l = Math.max(0, Math.min(3, level));
  const c = LIFT[on];
  return {rgb: c.rgb, ca: c.ca, dx: c.dx, wy: (c.wy[0] + l * c.wy[1]) * k, wb: (c.wb[0] + l * c.wb[1]) * k, wa: (c.wa[0] + l * c.wa[1]) * k};
};
export const lift = (level: number, k = 1, on: LiftOn = 'photo'): string => {
  const e = liftAt(level, k, on);
  return `0 1px 2px rgba(${e.rgb},${e.ca}), ${(e.wy * e.dx).toFixed(1)}px ${e.wy.toFixed(1)}px ${e.wb.toFixed(1)}px rgba(${e.rgb},${e.wa.toFixed(3)})`;
};
/** 모양을 따라가는 같은 두 겹(찢긴 종이·오린 그림) — filter 값 */
export const liftDrop = (level: number, k = 1, on: LiftOn = 'photo'): string => {
  const e = liftAt(level, k, on);
  return `drop-shadow(0 1px 1px rgba(${e.rgb},${e.ca})) drop-shadow(${(e.wy * e.dx).toFixed(1)}px ${e.wy.toFixed(1)}px ${(e.wb * 0.5).toFixed(1)}px rgba(${e.rgb},${e.wa.toFixed(3)}))`;
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

/** 고정 자리 글자(1080p px · 비율은 그 자리 크기에 곱함). 렌더러와 게이트 P1(studio/gate.py slot_px)이 같이 읽는다. */
export const SLOT_TYPE = {
  caption: 40, band: 34, bandBody: 0.783, definition: 46, superName: 42, superSub: 28, credit: 18,
  keywordMin: 44, keywordSub: 0.46, keywordSubMin: 28, quote: 0.06, quoteWho: 0.52, statSub: 28,
} as const;

/** 모션 DSL 의 size(상자 높이 대비 %)가 실제 몇 px 인지 — spec.py 의 검증과 같은 식. */
export const pxOfSize = (sizePct: number, boxH: number): number => (sizePct / 100) * boxH;

/** 채움 규칙(게이트 C2·C4 와 같은 값) */
export const FILL = {minInk: 0.45, minInkAtHalfSec: 0.35, maxEmptyStage: 0.3} as const;
