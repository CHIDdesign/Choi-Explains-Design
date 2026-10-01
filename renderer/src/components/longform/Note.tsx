import React, {useMemo} from 'react';
import {interpolate} from 'remotion';
import {EASE, LONG, tween, tweenOut} from '../../design/motion';
import {FONT, NOTE} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {fitSize} from '../../lib/fit';
import {seeded, tornRectPath} from '../paper/Paper';
import {slideIn, slideOut} from './Stage';

/**
 * 롱폼 무대 재질 v2 — **종이 메모 룩**(2026-10-01 운영자 레퍼런스 10장, docs/롱폼_무대_디자인.md 5장).
 * 세 색뿐: 크림 종이 · 웜 잉크(레퍼런스의 진초록 자리) · 시그널(테마 accent — 테이프·'!'·자막 아래 테두리·반전 상자·강조어).
 * 레퍼런스와 다르게: 둥근 고딕 대신 Pretendard Black, 종이는 **위가 찢긴** 메모(아래 아님), 테이프는 위 가운데, 그림자 판은 잉크.
 */
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/** 위 변만 들쭉날쭉한 종이 경로(0..w × 0..h) */
export const tornTopPath = (w: number, h: number, seed: number, amp = 6, step = 9): string => {
  const r = seeded(seed);
  let o = amp * 0.5;
  let x = 0;
  const pts: string[] = [];
  while (x < w) {
    o = o * 0.6 + r() * amp;
    const k = r();
    let v = o;
    if (k < 0.06) v = amp * 1.9;
    else if (k < 0.12) v = amp * 0.1;
    pts.push(`${x.toFixed(1)} ${v.toFixed(1)}`);
    x += step * (0.5 + r());
  }
  return `M 0 ${amp} L ${pts.join(' L ')} L ${w} ${(amp * 0.6).toFixed(1)} L ${w} ${h} L 0 ${h} Z`;
};

/** 하프톤 점(인쇄물 질감) — multiply 로 아주 옅게 */
export const Halftone: React.FC<{opacity?: number; size?: number; color?: string}> = ({opacity = 0.55, size = 5,
  color = NOTE.dots}) => (
  <div style={{position: 'absolute', inset: 0, pointerEvents: 'none', opacity, mixBlendMode: 'multiply',
    backgroundImage: `radial-gradient(${color} 0.9px, transparent 1.2px)`, backgroundSize: `${size}px ${size}px`}} />
);

/** 종이 질감(섬유 + 아주 옅은 얼룩) */
export const PaperFiber: React.FC<{id: string; opacity?: number}> = ({id, opacity = 0.16}) => (
  <svg width="100%" height="100%" style={{position: 'absolute', inset: 0, pointerEvents: 'none', opacity,
    mixBlendMode: 'multiply'}}>
    <filter id={`fiber-${id}`}>
      <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="3" />
      <feColorMatrix type="saturate" values="0" />
    </filter>
    <rect width="100%" height="100%" filter={`url(#fiber-${id})`} />
  </svg>
);

/** 테이프 한 조각(시그널색, 반투명, 옅은 줄무늬) */
export const Tape: React.FC<{x: number; y: number; w?: number; h?: number; rotate?: number; color: string;
  opacity?: number}> = ({x, y, w = 128, h = 34, rotate = -4, color, opacity = 1}) => (
  <div style={{position: 'absolute', left: x, top: y, width: w, height: h, rotate: `${rotate}deg`, opacity: 0.9 * opacity,
    background: `repeating-linear-gradient(90deg, ${color} 0 9px, rgba(255,255,255,0.14) 9px 11px)`,
    backgroundColor: color, boxShadow: '0 2px 6px rgba(0,0,0,0.22)',
    clipPath: 'polygon(1% 0, 99% 2%, 100% 100%, 0 96%)'}} />
);

/** 배지 — 잉크 알약 + 크림 글씨(기본) / 시그널 + 흰 글씨 */
export const Badge: React.FC<{text: string; size?: number; accent?: string; opacity?: number}> = ({text, size = 22,
  accent, opacity = 1}) => (
  <span style={{display: 'inline-block', fontFamily: FONT.sans, fontWeight: 800, fontSize: size, lineHeight: 1.2,
    letterSpacing: '-0.01em', whiteSpace: 'nowrap', color: accent ? '#FFFFFF' : NOTE.paper,
    background: accent || NOTE.ink, borderRadius: size * 0.28, padding: `${size * 0.2}px ${size * 0.55}px ${size * 0.26}px`,
    opacity}}>{text}</span>
);

/** 반전 상자 문구(레퍼런스: 두 줄 중 핵심 줄만 색 상자) — 왼→오 와이프 8f */
export const ReverseLine: React.FC<{text: string; size: number; bg: string; color?: string; p: number}> = ({text, size,
  bg, color = '#FFFFFF', p}) => (
  <span style={{display: 'inline-block', fontFamily: FONT.display, fontWeight: 900, fontSize: size, lineHeight: 1.22,
    letterSpacing: '-0.035em', whiteSpace: 'nowrap', color, background: bg, padding: `${size * 0.04}px ${size * 0.3}px ${size * 0.1}px`,
    borderRadius: 4, clipPath: `inset(0 ${(1 - Math.max(0, Math.min(1, p))) * 100}% 0 0)`}}>{text}</span>
);

/**
 * 종이 메모 — 위가 찢긴 크림 종이 + 뒤의 잉크 판(오프셋) + 위 가운데 테이프. 안쪽은 children.
 * from = 메모가 붙어 있는 바깥쪽(쓸어 들어오는 방향).
 */
export const PaperNote: React.FC<{x: number; y: number; w: number; h: number; frame: number; dur: number;
  from: 'left' | 'right' | 'top'; theme: Theme; seed: number; tape?: boolean; pad?: number; id: string;
  children?: React.ReactNode}> = ({x, y, w, h, frame, dur, from, theme, seed, tape = true, pad = 36, id, children}) => {
  const path = useMemo(() => tornTopPath(w, h, seed), [w, h, seed]);
  const tapeW = Math.round(Math.min(150, w * 0.22));
  // 바깥 여백(M): 쓸어 들어오는 clip-path 가 테이프(위로 14px)와 잉크 판(오른쪽·아래 9px)까지 자르지 않게
  const M = 28;
  return (
    <div style={{position: 'absolute', left: x - M, top: y - M, width: w + M * 2, height: h + M * 2,
      ...slideIn(frame, LONG.plateIn, from), ...slideOut(frame, dur, from)}}>
      <div style={{position: 'absolute', left: M, top: M, width: w, height: h}}>
        <svg width={w + 12} height={h + 12} style={{position: 'absolute', left: 0, top: 0, overflow: 'visible'}}>
          <path d={path} fill={NOTE.ink} opacity={0.92} transform="translate(7 9)" />
          <path d={path} fill={NOTE.paper} style={{filter: 'drop-shadow(0 10px 22px rgba(0,0,0,0.28))'}} />
        </svg>
        <div style={{position: 'absolute', inset: 0, clipPath: `path('${path}')`}}>
          <Halftone opacity={0.5} />
          <PaperFiber id={id} />
        </div>
        {tape ? <Tape x={w / 2 - tapeW / 2} y={-14} w={tapeW} color={theme.accent}
          rotate={(seeded(seed * 3)() - 0.5) * 8} /> : null}
        <div style={{position: 'absolute', left: pad, top: pad + 6, width: w - pad * 2, height: h - pad * 2 - 6}}>
          {children}
        </div>
      </div>
    </div>
  );
};

/**
 * 소제목 바(레퍼런스: 화면 위 거친 종이 띠 + 사각 배지 '!' + 굵은 제목) — 짧은 키워드, 머리 위가 비어 있을 때.
 * 우리 식: 잉크 사각 배지에 시그널 '!', 종이 띠는 거친 가장자리, 위에서 내려앉는다.
 */
export const SectionBar: React.FC<{text: string; frame: number; dur: number; W: number; theme: Theme; seed: number;
  maxW?: number; y?: number}> = ({text, frame, dur, W, theme, seed, maxW = 1240, y = 56}) => {
  const h = 112;
  const badge = 78;
  const size = Math.min(52, fitSize(text, maxW - badge - 150, 52, 30, -0.035));
  const textW = Math.min(maxW - badge - 150, Math.ceil(text.length * size * 0.96));
  const w = Math.max(520, badge + 150 + textW);
  const x = Math.round((W - w) / 2);
  const path = useMemo(() => tornRectPath({x: 0, y: 0, w, h}, 3.2, 7, seed), [w, seed]);
  const p = tween(frame, 0, 14, 'outQuint');
  const out = tweenOut(frame, dur, LONG.out);
  return (
    <div style={{position: 'absolute', left: x, top: y, width: w, height: h, opacity: p * out,
      translate: `0 ${interpolate(p, [0, 1], [-36, 0])}px`}}>
      <svg width={w + 20} height={h + 20} style={{position: 'absolute', left: -10, top: -10, overflow: 'visible'}}>
        <g transform="translate(10 10)">
          <path d={path} fill={NOTE.ink} opacity={0.9} transform="translate(6 7)" />
          <path d={path} fill={NOTE.paper} style={{filter: 'drop-shadow(0 8px 18px rgba(0,0,0,0.3))'}} />
        </g>
      </svg>
      <div style={{position: 'absolute', inset: 0, clipPath: `path('${path}')`}}><Halftone opacity={0.45} /></div>
      <div style={{position: 'absolute', left: 30, top: (h - badge) / 2, width: badge, height: badge, background: NOTE.ink,
        borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center',
        scale: `${interpolate(tween(frame, 4, 10, 'outBack'), [0, 1], [0.6, 1])}`}}>
        <span style={{fontFamily: FONT.latin, fontSize: badge * 0.82, lineHeight: 1, color: theme.accent,
          translate: '0 2px'}}>!</span>
      </div>
      <div style={{position: 'absolute', left: 30 + badge + 34, top: 0, height: h, display: 'flex', alignItems: 'center',
        fontFamily: FONT.display, fontWeight: 900, fontSize: size, letterSpacing: '-0.035em', color: NOTE.ink,
        whiteSpace: 'nowrap', opacity: tween(frame, 6, 10)}}>{text}</div>
    </div>
  );
};

/** 아카이브 사진·스톡 위 필름 룩: 비네팅 + 미세 입자(프레임마다 조금씩 다른 노이즈) */
export const FilmLook: React.FC<{frame: number; strength?: number; id: string}> = ({frame, strength = 1, id}) => (
  <div style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}>
    <div style={{position: 'absolute', inset: 0, background:
      `radial-gradient(120% 100% at 50% 48%, rgba(0,0,0,0) 48%, rgba(0,0,0,${0.42 * strength}) 100%)`}} />
    <svg width="100%" height="100%" style={{position: 'absolute', inset: 0, opacity: 0.16 * strength,
      mixBlendMode: 'overlay'}}>
      <filter id={`grain-${id}`}>
        <feTurbulence type="fractalNoise" baseFrequency="0.95" numOctaves="1" seed={1 + (frame % 6)} />
        <feColorMatrix type="saturate" values="0" />
      </filter>
      <rect width="100%" height="100%" filter={`url(#grain-${id})`} />
    </svg>
  </div>
);

/**
 * 키워드 슬램(레퍼런스: 같은 사진이 이어진 채 어두워지며 큰 흰 키워드 + 'A → B'): f = 슬램 시작 기준 프레임.
 * 등장 12f: 배율 1.06→1 + 흐림 8→0(리서치 R6.2 depth text), 짧은 시그널 괘선, 아랫줄은 4f 뒤.
 */
export const KeywordSlam: React.FC<{keyword: string; sub?: string; f: number; W: number; theme: Theme}> = ({keyword, sub,
  f, W, theme}) => {
  const dim = tween(f, 0, 10);
  const p = interpolate(f, [0, 12], [0, 1], {...clamp, easing: EASE.outQuint});
  const size = Math.min(190, fitSize(keyword, W * 0.8, 190, 90, -0.045));
  const subText = (sub || '').replace(/\s*->\s*|\s*→\s*/g, '  →  ');
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <div style={{position: 'absolute', inset: 0, background: 'rgba(16,12,10,0.58)', opacity: dim}} />
      <div style={{position: 'absolute', left: 0, right: 0, top: '50%', translate: '0 -56%', display: 'flex',
        flexDirection: 'column', alignItems: 'center', opacity: p, filter: `blur(${interpolate(p, [0, 1], [8, 0])}px)`,
        scale: `${interpolate(p, [0, 1], [1.06, 1])}`}}>
        <div style={{fontFamily: FONT.display, fontWeight: 900, fontSize: size, lineHeight: 1.05, letterSpacing: '-0.045em',
          color: '#FFFFFF', whiteSpace: 'nowrap', textShadow: '0 4px 0 rgba(0,0,0,0.35), 0 16px 40px rgba(0,0,0,0.45)'}}>
          {keyword}
        </div>
        <div style={{width: 56, height: 4, background: theme.accent, marginTop: 22, borderRadius: 2,
          transformOrigin: 'left center', scale: `${tween(f, 8, 10, 'outQuint')} 1`}} />
        {subText ? (
          <div style={{marginTop: 18, fontFamily: FONT.sans, fontWeight: 600, fontSize: 38, color: 'rgba(255,255,255,0.9)',
            letterSpacing: '-0.01em', whiteSpace: 'nowrap', opacity: tween(f, 12, 10),
            textShadow: '0 2px 10px rgba(0,0,0,0.5)'}}>{subText}</div>
        ) : null}
      </div>
    </div>
  );
};

/** 우하단 출처(레퍼런스: "출처:…" 작게, 사진 위) */
export const CornerCredit: React.FC<{text: string; opacity?: number}> = ({text, opacity = 1}) => (
  text ? (
    <div style={{position: 'absolute', right: 40, bottom: 22, fontFamily: FONT.sans, fontWeight: 500, fontSize: 20,
      color: 'rgba(255,255,255,0.86)', letterSpacing: '-0.01em', whiteSpace: 'nowrap', opacity,
      textShadow: '0 1px 6px rgba(0,0,0,0.6)'}}>
      {text.startsWith('출처') ? text : `출처: ${text}`}
    </div>
  ) : null
);
