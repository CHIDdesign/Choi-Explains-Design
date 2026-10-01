import React, {useMemo} from 'react';
import {Img, staticFile} from 'remotion';
import {FONT} from '../../design/tokens';

/**
 * 종이 콜라주 스킨 — 사용자가 직접 편집한 레퍼런스(구겨진 짙은 종이 + 찢어진 흰 테두리 액자 + 회색 거친 테두리
 * + 흰 라벨 태그 + 주황 강조 헤드라인 + 우상단 출처)를 1920×1080 기준으로 옮긴 것.
 * 측정값: 종이 RGB(40,40,45) · 회색 테두리 #7F7F81 두께 약 38px · 액자 흰 테두리 약 12px · 강조 주황 #F85301.
 * TornFrame·LabelTag·SourceCredit·AccentText 는 classic 스킨의 레퍼런스 부분(사진 액자·개념 카드·출처)에서도 쓴다.
 */
export const PAPER = {
  bg: '#28282D',
  border: '#7F7F81',
  white: '#F4F4F5',
  ink: '#111111',
  accent: '#F85301',
  body: 'rgba(244,244,245,0.9)',
  note: '#8A8A93',
  // 회색 거친 테두리(레퍼런스: x 36~1886, y 78~1050)
  frame: {x: 36, y: 78, w: 1850, h: 972, t: 38},
  // 개념 카드 옆 화자 액자(레퍼런스 1: x 1072~1778, y 170~636)
  speaker: {x: 1072, y: 170, w: 706, h: 466},
  // 액자에 담긴 화자 전체(레퍼런스 2: x 72~1856, y 92~1006)
  framed: {x: 72, y: 92, w: 1784, h: 914},
};

export type Box = {x: number; y: number; w: number; h: number};

/** 결정적 난수(xorshift) — 같은 seed 면 매 프레임 같은 모양(깜빡이지 않게) */
export const seeded = (seed: number) => {
  let s = (Math.floor(seed * 9973) ^ 0x5bd1e995) >>> 0 || 1;
  return () => {
    s ^= s << 13;
    s >>>= 0;
    s ^= s >>> 17;
    s ^= s << 5;
    s >>>= 0;
    return s / 4294967296;
  };
};

export const hashSeed = (text: string) => {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619) >>> 0;
  return (h % 100000) + 1;
};

/**
 * 가장자리가 찢긴 사각형 경로. amp = 바깥쪽으로 튀어나오는 최대 폭(px), step = 점 간격.
 * 가끔 더 깊게 뜯긴 자리(notch)를 섞어 손으로 찢은 느낌을 낸다.
 */
export const tornRectPath = (b: Box, amp: number, step: number, seed: number, inward = false): string => {
  const pts: [number, number][] = [];
  let o = amp * 0.5;
  let edgeNo = 0;
  const edge = (x0: number, y0: number, x1: number, y1: number, nx: number, ny: number) => {
    // 변마다 따로 시드 — 한 난수열을 네 변이 나눠 쓰면 윗변 길이가 바뀔 때(액자가 커지고 작아지는 동안) 나머지 변의
    // 모양이 매 프레임 새로 뽑혀 가장자리가 지글거렸다. 이제 길이가 바뀌어도 이미 있던 점은 그대로다
    const r = seeded(seed * 31 + ++edgeNo);
    const len = Math.hypot(x1 - x0, y1 - y0);
    let d = 0;
    while (d < len) {
      const t = d / len;
      // 상관된 난수(앞 점을 따라가며 조금씩 흔들림) + 가끔 작은 뜯김/돌기
      o = o * 0.62 + r() * amp * 0.75;
      let v = o;
      const k = r();
      if (k < 0.05) v = amp * (1.5 + r() * 0.8);
      else if (k < 0.1) v = amp * 0.05;
      const s = inward ? -v : v;
      pts.push([x0 + (x1 - x0) * t + nx * s, y0 + (y1 - y0) * t + ny * s]);
      d += step * (0.45 + r() * 1.1);
    }
  };
  const {x, y, w, h} = b;
  edge(x, y, x + w, y, 0, -1);
  edge(x + w, y, x + w, y + h, 1, 0);
  edge(x + w, y + h, x, y + h, 0, 1);
  edge(x, y + h, x, y, -1, 0);
  return 'M' + pts.map(([px, py]) => `${px.toFixed(1)} ${py.toFixed(1)}`).join('L') + 'Z';
};

/** 구겨진 짙은 종이 배경(파이썬이 만든 텍스처, 없으면 단색) */
export const PaperBg: React.FC<{src?: string; opacity?: number; style?: React.CSSProperties}> = ({src, opacity = 1,
  style}) => (
  <div style={{position: 'absolute', inset: 0, background: PAPER.bg, opacity, overflow: 'hidden', ...style}}>
    {src ? <Img src={staticFile(src)} style={{position: 'absolute', inset: 0, width: '100%', height: '100%',
      objectFit: 'cover'}} /> : null}
  </div>
);

/**
 * 찢어진 흰 테두리 액자(뒤판). 내용(영상·사진)은 호출한 쪽이 b 안에 그린다 — 흰 종이가 b 밖으로 border 만큼 나온다.
 */
export const TornFrame: React.FC<{b: Box; border?: number; seed?: number; opacity?: number; shadow?: boolean;
  rotate?: number; children?: React.ReactNode}> = ({b, border = 12, seed = 3, opacity = 1, shadow = true, rotate = 0,
  children}) => {
  const pad = border + 14;
  const path = useMemo(() => tornRectPath({x: pad - border, y: pad - border, w: b.w + border * 2, h: b.h + border * 2},
    4.5, 6, seed), [b.w, b.h, border, seed, pad]);
  const fibers = useMemo(() => tornRectPath({x: pad - border - 1, y: pad - border - 1, w: b.w + border * 2 + 2,
    h: b.h + border * 2 + 2}, 6, 4, seed + 7), [b.w, b.h, border, seed, pad]);
  if (opacity <= 0) return null;
  return (
    <div style={{position: 'absolute', left: b.x - pad, top: b.y - pad, width: b.w + pad * 2, height: b.h + pad * 2,
      opacity, rotate: rotate ? `${rotate}deg` : undefined}}>
      <svg width={b.w + pad * 2} height={b.h + pad * 2} style={{position: 'absolute', inset: 0, overflow: 'visible',
        filter: shadow ? 'drop-shadow(0 12px 22px rgba(0,0,0,0.55))' : undefined}}>
        <path d={fibers} fill="rgba(200,200,204,0.3)" />
        <path d={path} fill={PAPER.white} />
      </svg>
      {children ? (
        <div style={{position: 'absolute', left: pad, top: pad, width: b.w, height: b.h, overflow: 'hidden',
          background: '#111'}}>{children}</div>
      ) : null}
    </div>
  );
};

/** 회색 거친 테두리 — 네 번의 붓질처럼 조금씩 겹치고 튀어나온 띠 */
export const RoughBorder: React.FC<{b?: Box; t?: number; seed?: number; opacity?: number; color?: string}> = ({
  b = PAPER.frame, t = PAPER.frame.t, seed = 5, opacity = 1, color = PAPER.border}) => {
  const strokes = useMemo(() => {
    const r = seeded(seed);
    const j = () => (r() - 0.5) * 10;
    return [
      {x: b.x - 6 + j(), y: b.y + j() * 0.4, w: b.w + 12, h: t},
      {x: b.x + b.w - t + j() * 0.4, y: b.y - 4 + j(), w: t, h: b.h + 8},
      {x: b.x - 4 + j(), y: b.y + b.h - t + j() * 0.4, w: b.w + 10, h: t},
      {x: b.x + j() * 0.4, y: b.y - 6 + j(), w: t, h: b.h + 12},
    ].map((s, i) => tornRectPath(s, 3.2, 6, seed * 13 + i));
  }, [b.x, b.y, b.w, b.h, t, seed]);
  if (opacity <= 0) return null;
  return (
    <svg width={1920} height={1080} style={{position: 'absolute', left: 0, top: 0, overflow: 'visible', opacity,
      pointerEvents: 'none'}}>
      {strokes.map((d, i) => <path key={i} d={d} fill={color} />)}
    </svg>
  );
};

/** 라벨 태그 — white: 흰 둥근 상자 + 검정 굵은 글씨(레퍼런스 1), black: 검정 상자 + 흰 글씨(레퍼런스 3).
 * 글자가 비면 그리지 않는다(빈 상자 금지 — 내부 이름 대신 빈 라벨이 오는 곳). */
export const LabelTag: React.FC<{text: string; variant?: 'white' | 'black'; size?: number;
  style?: React.CSSProperties}> = ({text, variant = 'white', size = 32, style}) => (
  text && text.trim() ? (
    <div style={{display: 'inline-block', fontFamily: FONT.sans, fontWeight: variant === 'white' ? 800 : 600,
      fontSize: size, lineHeight: 1.25, letterSpacing: '-0.02em', whiteSpace: 'nowrap',
      color: variant === 'white' ? PAPER.ink : PAPER.white,
      background: variant === 'white' ? PAPER.white : 'rgba(17,17,17,0.94)',
      borderRadius: variant === 'white' ? size * 0.22 : 2, padding: `${size * 0.14}px ${size * 0.42}px ${size * 0.18}px`,
      boxShadow: variant === 'black' ? '0 6px 18px rgba(0,0,0,0.35)' : undefined, ...style}}>
      {text}
    </div>
  ) : null
);

/** 우상단 출처 표기(레퍼런스: "출처: …") */
export const SourceCredit: React.FC<{text: string; opacity?: number; top?: number; right?: number; raw?: boolean}> = ({
  text, opacity = 1, top = 26, right = 34, raw = false}) => (
  text ? (
    <div style={{position: 'absolute', right, top, fontFamily: FONT.sans, fontWeight: 500, fontSize: 22,
      color: PAPER.white, opacity: opacity * 0.92, letterSpacing: '-0.01em', whiteSpace: 'nowrap',
      textShadow: '0 1px 6px rgba(0,0,0,0.5)'}}>
      {raw || text.startsWith('출처') ? text : `출처: ${text}`}
    </div>
  ) : null
);

const JOSA = /(으로써|으로서|에서는|에게서|으로|에서|에게|까지|부터|처럼|보다|라는|이란|이라|란|은|는|이|가|을|를|의|에|로|와|과|도|만)$/;

/** 강조할 낱말: 지정값 → 없으면 제목의 마지막 어절(조사를 뗀 어간). null 이면 강조 없음. */
export const pickAccent = (title: string, accent?: string | null): string => {
  if (accent === null) return '';
  if (accent && title.includes(accent)) return accent;
  const words = title.split(/\s+/).filter(Boolean);
  if (words.length < 2) return '';
  const last = words[words.length - 1].replace(/[.,!?…·:;"'”’)]+$/, '');
  const stem = last.replace(JOSA, '');
  return stem.length >= 1 ? stem : last;
};

/** 흰 헤드라인 + 한 낱말만 주황(레퍼런스 1 "이것은 [강조] 텍스트") */
export const AccentText: React.FC<{text: string; accent?: string | null; color?: string; accentColor?: string}> = ({text,
  accent, color = PAPER.white, accentColor = PAPER.accent}) => {
  const a = pickAccent(text, accent);
  const i = a ? text.lastIndexOf(a) : -1;
  if (i < 0) return <span style={{color}}>{text}</span>;
  return (
    <span style={{color}}>
      {text.slice(0, i)}
      <span style={{color: accentColor, fontWeight: 600}}>{a}</span>
      {text.slice(i + a.length)}
    </span>
  );
};
