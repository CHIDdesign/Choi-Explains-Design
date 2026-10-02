import React from 'react';
import {Img, interpolate, staticFile} from 'remotion';
import {EASE, tween, tweenOut} from '../../design/motion';
import {FONT, MODERN, PRESS_FONT, mix, rgba, softShadow} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {grainOffset, useNoiseTile} from '../../lib/noise';
import {fitBlock} from '../../lib/fit';

/**
 * 모던 모션 킷 — 디자인 v4(운영자 레퍼런스 2026-10-02: 테크 설명 영상의 모션 디자인).
 *  흰/옅은 디자인색 밝은 무대 또는 검정 어두운 무대 · 자간을 좁힌 굵은 산세리프(Pretendard 800) 키네틱 헤드라인(한 단어만
 *  Instrument Serif 이탤릭) · 둥근 흰 UI 카드·칩·말풍선(부드러운 그림자) · 모니터/노트북/폰 목업 · 아이소메트릭 블록 도시 ·
 *  큰 숫자 · 영상 위 가는+굵은 글자 · 모서리의 작은 기술 라벨.
 * 질감은 정적(노이즈 타일·그라데이션)뿐 — 프레임마다 바뀌는 필터 없음(렌더 속도 규칙). 움직임은 tween 만.
 */

export type ModernColors = {bg: string; bgGlow: string; ink: string; inkSoft: string; line: string; card: string; cardTint: string;
  accent: string; deep: string; tint: string; dark: boolean};

/** 모던 팔레트(테마의 디자인 색에서) */
export const modernColors = (theme: Theme, dark = false): ModernColors => {
  if (dark) {
    return {
      bg: MODERN.dark, bgGlow: rgba(theme.accent, 0.16), ink: MODERN.darkInk, inkSoft: MODERN.darkSoft,
      line: 'rgba(244,244,242,0.14)', card: '#17181A', cardTint: '#1E2022', accent: theme.accent, deep: theme.accentLight,
      tint: rgba(theme.accent, 0.22), dark: true,
    };
  }
  return {
    bg: MODERN.bg, bgGlow: mix(theme.accentTint, '#FFFFFF', 0.35), ink: MODERN.ink, inkSoft: MODERN.inkSoft,
    line: MODERN.line, card: MODERN.card, cardTint: mix(theme.accentTint, '#FFFFFF', 0.62), accent: theme.accent,
    deep: theme.accentDeep, tint: theme.accentTint, dark: false,
  };
};
/** 표면(Surface)만 있는 곳(모션 장면)에서 쓰는 팔레트 — 테마 없이 표면 색으로 */
export const modernColorsFromSurface = (s: {bg: string; fg: string; dim: string; faint: string; accent: string; name: string}): ModernColors => {
  const dark = s.name === 'dark' || s.name === 'ink' || s.name === 'board';
  return {
    bg: s.bg, bgGlow: rgba(s.accent, 0.16), ink: s.fg, inkSoft: s.dim, line: s.faint, card: dark ? '#17181A' : '#FFFFFF',
    cardTint: dark ? '#1E2022' : mix(s.accent, '#FFFFFF', 0.9), accent: s.accent, deep: s.accent,
    tint: dark ? rgba(s.accent, 0.22) : mix(s.accent, '#FFFFFF', 0.78), dark,
  };
};

/** 무대: 밝은 바탕 + 아래쪽에 옅은 디자인 색 번짐 + 아주 옅은 입자. dark 면 검정 + 가운데 색 번짐 */
export const ModernStage: React.FC<{theme: Theme; frame?: number; dark?: boolean; glow?: number}> = ({theme, frame = 0,
  dark = false, glow = 1}) => {
  const c = modernColors(theme, dark);
  const tile = useNoiseTile(13, 0.3, 0.5);
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: c.bg}}>
      <div style={{position: 'absolute', inset: 0, opacity: glow, background: dark
        ? `radial-gradient(60% 55% at 50% 50%, ${c.bgGlow} 0%, rgba(0,0,0,0) 100%)`
        : `radial-gradient(70% 60% at 50% 108%, ${c.bgGlow} 0%, rgba(255,255,255,0) 100%)`}} />
      <div style={{position: 'absolute', inset: 0, opacity: dark ? 0.08 : 0.05, mixBlendMode: dark ? 'screen' : 'multiply',
        backgroundImage: `url(${tile})`, backgroundSize: '256px 256px', backgroundPosition: grainOffset(Math.floor(frame / 4))}} />
    </div>
  );
};

/** 모서리의 작은 기술 라벨(레퍼런스 'SHOWREEL '26 — MOTION DESIGN' · '01 / KINETIC TYPOGRAPHY') — 한국어 역할명·카피만 */
export const CornerLabels: React.FC<{frame: number; W: number; H: number; c: ModernColors; tl?: string; tr?: string;
  bl?: string; br?: string; delay?: number; inset?: number}> = ({frame, W, H, c, tl, tr, bl, br, delay = 4, inset = 44}) => {
  const k = W / 1920;
  const op = tween(frame, delay, 10);
  const st = (x: 'left' | 'right', y: 'top' | 'bottom'): React.CSSProperties => ({position: 'absolute', [x]: inset * k,
    [y]: inset * k, fontFamily: FONT.sans, fontWeight: 600, fontSize: 16 * k, letterSpacing: '0.14em', color: c.inkSoft,
    textTransform: 'uppercase', whiteSpace: 'nowrap', opacity: op, lineHeight: 1});
  const mark = (x: 'left' | 'right', y: 'top' | 'bottom') => (
    <div style={{position: 'absolute', [x]: (inset - 14) * k, [y]: (inset - 14) * k, width: 10 * k, height: 10 * k,
      borderTop: y === 'top' ? `1.5px solid ${c.inkSoft}` : undefined, borderBottom: y === 'bottom' ? `1.5px solid ${c.inkSoft}` : undefined,
      borderLeft: x === 'left' ? `1.5px solid ${c.inkSoft}` : undefined, borderRight: x === 'right' ? `1.5px solid ${c.inkSoft}` : undefined,
      opacity: op * 0.8}} />
  );
  void H;
  return (
    <>
      {mark('left', 'top')}{mark('right', 'top')}{mark('left', 'bottom')}{mark('right', 'bottom')}
      {tl ? <div style={st('left', 'top')}>{tl}</div> : null}
      {tr ? <div style={st('right', 'top')}>{tr}</div> : null}
      {bl ? <div style={st('left', 'bottom')}>{bl}</div> : null}
      {br ? <div style={st('right', 'bottom')}>{br}</div> : null}
    </>
  );
};

/** 제목 둘레의 작은 네모 넷(레퍼런스 'TOOLS THAT DON'T TALK TO EACH OTHER') */
export const CornerMarks: React.FC<{x: number; y: number; w: number; h: number; c: ModernColors; p: number; size?: number}>
  = ({x, y, w, h, c, p, size = 16}) => {
  const dot = (dx: number, dy: number, i: number) => (
    <div key={i} style={{position: 'absolute', left: x + dx * w - size / 2, top: y + dy * h - size / 2, width: size, height: size,
      background: c.accent, opacity: 0.8 * Math.min(1, Math.max(0, p * 1.6 - i * 0.15)),
      scale: `${interpolate(Math.min(1, Math.max(0, p * 1.6 - i * 0.15)), [0, 1], [0.3, 1])}`}} />
  );
  return <>{dot(0, 0, 0)}{dot(1, 0, 1)}{dot(0, 1, 2)}{dot(1, 1, 3)}</>;
};

/** *별표* 로 감싼 어절은 이탤릭 세리프 강조(레퍼런스 'Every leak starts *small*.') */
export const splitAccent = (text: string): {word: string; accent: boolean}[] =>
  text.split(/\s+/).filter(Boolean).map((w) => {
    const m = w.match(/^\*(.+)\*([.,!?…]*)$/);
    return m ? {word: m[1] + m[2], accent: true} : {word: w, accent: false};
  });

/** 강조 어절의 글꼴: 한글은 번들 명조(고운바탕)에 기울임을 합성(Instrument Serif 에는 한글이 없어 시스템 글꼴로 떨어진다), 영문은 Instrument Serif 이탤릭 */
export const accentFont = (word: string): {font: string; weight: number; skew: boolean} =>
  /[\u3131-\uD79D]/.test(word) ? {font: PRESS_FONT.serif, weight: 700, skew: true} : {font: FONT.italic, weight: 400, skew: false};

/** 키네틱 헤드라인: 어절마다 아래에서 올라오며 등장(3f 간격), 자간 좁힌 굵은 산세리프, 강조 어절은 이탤릭 세리프 */
export const Headline: React.FC<{text: string; size: number; color: string; accentColor?: string; frame: number;
  delay?: number; weight?: number; align?: 'left' | 'center' | 'right'; maxW?: number; lineHeight?: number; stagger?: number;
  tracking?: string; style?: React.CSSProperties}> = ({text, size, color, accentColor, frame, delay = 0, weight = 800,
  align = 'left', maxW, lineHeight = 1.06, stagger = 3, tracking = '-0.035em', style}) => {
  const lines = text.split('\n').filter(Boolean);
  let n = 0;
  return (
    <div style={{display: 'flex', flexDirection: 'column', alignItems: align === 'center' ? 'center' : align === 'right'
      ? 'flex-end' : 'flex-start', maxWidth: maxW, ...style}}>
      {lines.map((line, li) => (
        <div key={li} style={{display: 'flex', flexWrap: 'wrap', justifyContent: align === 'center' ? 'center' : align === 'right'
          ? 'flex-end' : 'flex-start', columnGap: size * 0.22, rowGap: 0}}>
          {splitAccent(line).map((w, wi) => {
            const p = tween(frame, delay + (n++) * stagger, 14, 'enterText');
            const af = w.accent ? accentFont(w.word) : null;
            return (
              <span key={wi} style={{display: 'inline-block', overflow: 'hidden', paddingBottom: size * 0.1, marginBottom: -size * 0.1,
                verticalAlign: 'top', paddingRight: af ? size * 0.06 : 0}}>
                <span style={{display: 'inline-block', fontFamily: af ? af.font : FONT.sans, fontStyle: af && !af.skew ? 'italic' : 'normal',
                  fontWeight: af ? af.weight : weight, fontSize: af ? size * (af.skew ? 0.98 : 1.06) : size, lineHeight,
                  letterSpacing: af ? '-0.02em' : tracking, color: af ? (accentColor || color) : color,
                  translate: `0 ${interpolate(p, [0, 1], [102, 0])}%`, transform: af && af.skew ? 'skewX(-8deg)' : undefined,
                  opacity: p > 0 ? 1 : 0, whiteSpace: 'pre'}}>{w.word}</span>
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
};

/** 헤드라인의 메아리(레퍼런스 1: 같은 문장이 흐리게 둘레에 흩어짐) — 주 글자보다 먼저 아주 옅게 */
export const Echo: React.FC<{text: string; size: number; color: string; frame: number; W: number; H: number; delay?: number}>
  = ({text, size, color, frame, W, H, delay = 0}) => {
  const spots = [[0.08, 0.18], [0.5, 0.14], [0.86, 0.2], [0.14, 0.36], [0.8, 0.4], [0.5, 0.64], [0.1, 0.62], [0.9, 0.66]];
  return (
    <>
      {spots.map(([x, y], i) => {
        const p = tween(frame, delay + i * 2, 16, 'enter');
        return (
          <div key={i} style={{position: 'absolute', left: x * W, top: y * H, translate: '-50% -50%', fontFamily: FONT.sans,
            fontWeight: 700, fontSize: size * 0.42, letterSpacing: '-0.03em', color, opacity: 0.16 * p, whiteSpace: 'pre',
            textAlign: 'center', lineHeight: 1.1, filter: 'blur(0.4px)'}}>{text.replace(/\*/g, '')}</div>
        );
      })}
    </>
  );
};

const CheckIcon: React.FC<{size: number; color: string}> = ({size, color}) => (
  <svg width={size} height={size} viewBox="0 0 24 24" style={{flexShrink: 0}}>
    <circle cx={12} cy={12} r={11} fill={color} />
    <path d="M7 12.5l3.2 3.2L17 9" stroke="#fff" strokeWidth={2.4} fill="none" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const DotIcon: React.FC<{size: number; color: string}> = ({size, color}) => (
  <span style={{width: size * 0.5, height: size * 0.5, borderRadius: '50%', background: color, flexShrink: 0, display: 'inline-block'}} />
);
const SquareIcon: React.FC<{size: number; color: string; bg: string}> = ({size, color, bg}) => (
  <span style={{width: size, height: size, borderRadius: size * 0.28, background: bg, display: 'inline-flex', alignItems: 'center',
    justifyContent: 'center', flexShrink: 0}}>
    <svg width={size * 0.58} height={size * 0.58} viewBox="0 0 24 24">
      <circle cx={12} cy={12} r={4.2} fill="none" stroke={color} strokeWidth={2.2} />
      <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1"
        stroke={color} strokeWidth={2.2} strokeLinecap="round" />
    </svg>
  </span>
);
export type IconKind = 'check' | 'dot' | 'gear' | 'none';
export const Icon: React.FC<{kind: IconKind; size: number; c: ModernColors}> = ({kind, size, c}) =>
  kind === 'check' ? <CheckIcon size={size} color={c.accent} /> : kind === 'dot' ? <DotIcon size={size} color={c.accent} />
    : kind === 'gear' ? <SquareIcon size={size} color={c.deep} bg={c.tint} /> : null;

/** 알약 칩(레퍼런스 '✓ Zoning'): 흰 둥근 상자 + 얇은 선 + 부드러운 그림자, 정착 곡선으로 튀어나온다 */
export const Pill: React.FC<{text: string; c: ModernColors; frame: number; delay?: number; size?: number; icon?: IconKind;
  fill?: 'card' | 'tint' | 'accent'; style?: React.CSSProperties}> = ({text, c, frame, delay = 0, size = 28, icon = 'check',
  fill = 'card', style}) => {
  const p = tween(frame, delay, 12, 'settle');
  const op = tween(frame, delay, 6);
  const bg = fill === 'accent' ? c.accent : fill === 'tint' ? c.cardTint : c.card;
  const fg = fill === 'accent' ? '#FFFFFF' : c.ink;
  return (
    <div style={{display: 'inline-flex', alignItems: 'center', gap: size * 0.4, padding: `${size * 0.36}px ${size * 0.72}px ${size * 0.4}px`,
      borderRadius: 999, background: bg, border: `1px solid ${fill === 'accent' ? 'transparent' : c.line}`, boxShadow: softShadow(1, c.dark),
      fontFamily: FONT.sans, fontWeight: 600, fontSize: size, letterSpacing: '-0.015em', color: fg, whiteSpace: 'nowrap',
      opacity: op, scale: `${interpolate(p, [0, 1], [0.86, 1])}`, transformOrigin: '50% 50%', lineHeight: 1.1, ...style}}>
      {icon !== 'none' ? <Icon kind={icon} size={size * 0.86} c={fill === 'accent' ? {...c, accent: '#FFFFFF'} : c} /> : null}
      <span>{text}</span>
    </div>
  );
};

/** 말풍선(레퍼런스 '₹4.80 CR / Street 3' · 'Analyzing Neighborhood…'): 흰 둥근 상자 + 꼬리 */
export const Bubble: React.FC<{text: string; sub?: string; c: ModernColors; frame: number; delay?: number; size?: number;
  tail?: 'bottom' | 'left' | 'none'; icon?: IconKind; style?: React.CSSProperties}> = ({text, sub, c, frame, delay = 0,
  size = 34, tail = 'bottom', icon = 'none', style}) => {
  const p = tween(frame, delay, 14, 'settle');
  const op = tween(frame, delay, 6);
  const r = size * 0.7;
  return (
    <div style={{position: 'relative', display: 'inline-block', opacity: op, scale: `${interpolate(p, [0, 1], [0.8, 1])}`,
      transformOrigin: tail === 'bottom' ? '50% 110%' : '-10% 50%', ...style}}>
      <div style={{display: 'flex', alignItems: 'center', gap: size * 0.4, padding: `${size * 0.42}px ${size * 0.8}px`, borderRadius: r,
        background: c.card, border: `1px solid ${c.line}`, boxShadow: softShadow(2, c.dark)}}>
        {icon !== 'none' ? <Icon kind={icon} size={size * 0.9} c={c} /> : null}
        <div style={{display: 'flex', flexDirection: 'column', alignItems: 'flex-start', lineHeight: 1.1}}>
          <span style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: size, letterSpacing: '-0.03em', color: c.ink,
            whiteSpace: 'nowrap'}}>{text}</span>
          {sub ? <span style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: size * 0.58, color: c.inkSoft, marginTop: size * 0.12,
            whiteSpace: 'nowrap'}}>{sub}</span> : null}
        </div>
      </div>
      {tail === 'bottom' ? (
        <svg width={size * 0.9} height={size * 0.55} viewBox="0 0 30 18" style={{position: 'absolute', left: '50%', top: '100%',
          translate: '-50% -1px'}}>
          <path d="M0 0 L30 0 L15 17 Z" fill={c.card} />
          <path d="M0 0 L15 17 L30 0" fill="none" stroke={c.line} strokeWidth={1} />
        </svg>
      ) : tail === 'left' ? (
        <svg width={size * 0.55} height={size * 0.9} viewBox="0 0 18 30" style={{position: 'absolute', right: '100%', top: '50%',
          translate: '1px -50%'}}>
          <path d="M18 0 L18 30 L1 15 Z" fill={c.card} />
        </svg>
      ) : null}
    </div>
  );
};

export type PanelRow = {label: string; value?: string; icon?: IconKind; on?: boolean};

/** UI 패널(레퍼런스 'Project Pricing' · 'Vantage.'): 흰 둥근 카드 + 제목 줄 + 둥근 행(아이콘 · 라벨 · 값), 행마다 3f 간격 */
export const UIPanel: React.FC<{title?: string; rows: PanelRow[]; c: ModernColors; frame: number; delay?: number; w: number;
  size?: number; tilt?: boolean; windowDots?: boolean; style?: React.CSSProperties}> = ({title, rows, c, frame, delay = 0,
  w, size = 28, tilt = false, windowDots = true, style}) => {
  const p = tween(frame, delay, 16, 'enterLarge');
  const op = tween(frame, delay, 8);
  const pad = size * 0.9;
  const rowH = size * 2.2;
  return (
    <div style={{width: w, borderRadius: size * 1.0, background: c.card, border: `1px solid ${c.line}`, boxShadow: softShadow(3, c.dark),
      padding: pad, boxSizing: 'border-box', opacity: op, translate: `0 ${interpolate(p, [0, 1], [26, 0])}px`,
      transform: tilt ? 'perspective(1800px) rotateX(7deg) rotateY(-9deg)' : undefined, transformOrigin: '50% 50%', ...style}}>
      {windowDots ? (
        <div style={{display: 'flex', gap: size * 0.26, marginBottom: size * 0.5}}>
          {[0, 1, 2].map((i) => <span key={i} style={{width: size * 0.36, height: size * 0.36, borderRadius: '50%', background: c.line}} />)}
        </div>
      ) : null}
      {title ? (
        <div style={{display: 'flex', alignItems: 'center', gap: size * 0.4, marginBottom: size * 0.55, opacity: tween(frame, delay + 4, 8)}}>
          <Icon kind="gear" size={size * 1.1} c={c} />
          <span style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: size * 1.05, letterSpacing: '-0.03em', color: c.ink}}>{title}</span>
        </div>
      ) : null}
      <div style={{display: 'flex', flexDirection: 'column', gap: size * 0.32}}>
        {rows.map((r, i) => {
          const q = tween(frame, delay + 8 + i * 3, 12, 'enter');
          return (
            <div key={i} style={{height: rowH, borderRadius: size * 0.62, background: r.on ? c.tint : c.cardTint, border: `1px solid ${c.line}`,
              display: 'flex', alignItems: 'center', gap: size * 0.5, padding: `0 ${size * 0.7}px`, opacity: q,
              translate: `0 ${interpolate(q, [0, 1], [10, 0])}px`}}>
              <Icon kind={r.icon ?? 'dot'} size={size * 0.8} c={c} />
              <span style={{fontFamily: FONT.sans, fontWeight: 600, fontSize: size * 0.92, color: c.ink, letterSpacing: '-0.02em',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flex: 1}}>{r.label}</span>
              {r.value ? <span style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: size * 0.92, color: r.on ? c.deep : c.ink,
                fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em', whiteSpace: 'nowrap'}}>{r.value}</span> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
};

/** 기기 목업(레퍼런스: 모니터 위 지도 · 노트북 위 쇼릴): 화면 안에 children */
export const DeviceFrame: React.FC<{kind: 'monitor' | 'laptop' | 'phone'; w: number; c: ModernColors; frame: number; delay?: number;
  children?: React.ReactNode; screenBg?: string}> = ({kind, w, c, frame, delay = 0, children, screenBg = '#FFFFFF'}) => {
  const p = tween(frame, delay, 18, 'enterLarge');
  const bezel = '#1B1C1E';
  if (kind === 'phone') {
    const h = w * 2.05;
    const b = w * 0.035;
    return (
      <div style={{position: 'relative', width: w, height: h, opacity: p, translate: `0 ${interpolate(p, [0, 1], [30, 0])}px`}}>
        <div style={{position: 'absolute', inset: 0, borderRadius: w * 0.16, background: bezel, boxShadow: softShadow(3, c.dark)}} />
        <div style={{position: 'absolute', left: b, top: b, right: b, bottom: b, borderRadius: w * 0.13, overflow: 'hidden', background: screenBg}}>
          {children}
        </div>
        <div style={{position: 'absolute', left: '50%', top: b * 1.6, width: w * 0.3, height: w * 0.06, borderRadius: 999, background: bezel,
          translate: '-50% 0'}} />
      </div>
    );
  }
  if (kind === 'laptop') {
    const screenH = w * 0.6;
    const b = w * 0.018;
    return (
      <div style={{position: 'relative', width: w * 1.16, height: screenH + w * 0.06, opacity: p, translate: `0 ${interpolate(p, [0, 1], [30, 0])}px`}}>
        <div style={{position: 'absolute', left: w * 0.08, top: 0, width: w, height: screenH, borderRadius: w * 0.02, background: bezel,
          boxShadow: softShadow(3, c.dark)}} />
        <div style={{position: 'absolute', left: w * 0.08 + b, top: b, width: w - b * 2, height: screenH - b * 2, borderRadius: w * 0.012,
          overflow: 'hidden', background: screenBg}}>{children}</div>
        <div style={{position: 'absolute', left: 0, top: screenH - 2, width: w * 1.16, height: w * 0.05, borderRadius: `0 0 ${w * 0.02}px ${w * 0.02}px`,
          background: 'linear-gradient(180deg, #D9DADC, #B9BBBF)'}} />
        <div style={{position: 'absolute', left: w * 0.47, top: screenH - 2, width: w * 0.22, height: w * 0.012, borderRadius: 999,
          background: '#9A9CA1'}} />
      </div>
    );
  }
  const screenH = w * 0.5625;
  const b = w * 0.014;
  return (
    <div style={{position: 'relative', width: w, height: screenH + w * 0.12, opacity: p, translate: `0 ${interpolate(p, [0, 1], [30, 0])}px`}}>
      <div style={{position: 'absolute', left: 0, top: 0, width: w, height: screenH, borderRadius: w * 0.016, background: bezel,
        boxShadow: softShadow(3, c.dark)}} />
      <div style={{position: 'absolute', left: b, top: b, width: w - b * 2, height: screenH - b * 2, borderRadius: w * 0.01, overflow: 'hidden',
        background: screenBg}}>{children}</div>
      <div style={{position: 'absolute', left: '50%', top: screenH, width: w * 0.08, height: w * 0.08, translate: '-50% 0',
        background: 'linear-gradient(180deg, #C9CBCE, #A8ABB0)'}} />
      <div style={{position: 'absolute', left: '50%', top: screenH + w * 0.08, width: w * 0.3, height: w * 0.02, borderRadius: 999,
        translate: '-50% 0', background: '#B5B8BC'}} />
    </div>
  );
};

/** 아이소메트릭 블록 도시(레퍼런스: 흰 블록 + 옅은 초록 길) — SVG 정적, 블록은 시드로 높이·등장 순서 */
export const IsoBlocks: React.FC<{W: number; H: number; c: ModernColors; frame: number; seed?: number; cols?: number; rows?: number;
  road?: boolean; opacity?: number}> = ({W, H, c, frame, seed = 1, cols = 11, rows = 8, road = true, opacity = 1}) => {
  // 촘촘한 작은 블록(레퍼런스의 도시): 칸 = 폭 / (열 × 1.3), 높이는 칸의 0.1~0.5
  const cell = W / (cols * 1.3);
  const ox = W / 2;
  const oy = H * 0.08;
  const iso = (x: number, y: number, z: number): [number, number] => [ox + (x - y) * cell * 0.866, oy + (x + y) * cell * 0.5 - z];
  const rnd = (i: number) => {
    const v = Math.sin(i * 12.9898 + seed * 78.233) * 43758.5453;
    return v - Math.floor(v);
  };
  const blocks: React.ReactNode[] = [];
  const roadCells = new Set<string>();
  if (road) {
    for (let i = 0; i < cols; i++) {
      const j = Math.round(rows * 0.45 + Math.sin(i * 0.9 + seed) * 1.4);
      roadCells.add(`${i},${j}`);
      roadCells.add(`${i},${j + 1}`);
    }
  }
  let n = 0;
  for (let j = 0; j < rows; j++) {
    for (let i = 0; i < cols; i++) {
      const isRoad = roadCells.has(`${i},${j}`);
      const r = rnd(n++);
      const p = tween(frame, Math.floor((i + j) * 1.6 + r * 4), 12, 'enter');
      const h = isRoad ? 0 : (0.18 + r * 0.75) * cell * 0.55 * p;
      const g = 0.08;
      const [ax, ay] = iso(i + g, j + g, h);
      const [bx, by] = iso(i + 1 - g, j + g, h);
      const [cx, cy] = iso(i + 1 - g, j + 1 - g, h);
      const [dx, dy] = iso(i + g, j + 1 - g, h);
      const [, dy0] = iso(i + g, j + 1 - g, 0);
      const [, cy0] = iso(i + 1 - g, j + 1 - g, 0);
      const [, by0] = iso(i + 1 - g, j + g, 0);
      const top = isRoad ? (c.dark ? c.tint : mix(c.tint, '#FFFFFF', 0.35)) : (c.dark ? '#26282B' : '#FFFFFF');
      const left = c.dark ? '#1C1E21' : '#E3E6E1';
      const right = c.dark ? '#141517' : '#D2D6D0';
      blocks.push(
        <g key={`${i}-${j}`} opacity={isRoad ? 1 : p}>
          {h > 0 ? <polygon points={`${dx},${dy} ${cx},${cy} ${cx},${cy0} ${dx},${dy0}`} fill={left} /> : null}
          {h > 0 ? <polygon points={`${cx},${cy} ${bx},${by} ${bx},${by0} ${cx},${cy0}`} fill={right} /> : null}
          <polygon points={`${ax},${ay} ${bx},${by} ${cx},${cy} ${dx},${dy}`} fill={top} stroke={isRoad ? 'none' : c.line} strokeWidth={0.6} />
        </g>,
      );
    }
  }
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{position: 'absolute', inset: 0, opacity}}>
      {blocks}
    </svg>
  );
};

/** 큰 숫자(레퍼런스 '02:47'): Pretendard 900, 구두점은 디자인 색 */
export const BigNumeral: React.FC<{text: string; size: number; c: ModernColors; frame: number; delay?: number; unit?: string;
  color?: string}> = ({text, size, c, frame, delay = 0, unit, color}) => {
  const p = tween(frame, delay, 16, 'enterLarge');
  const chars = text.split('');
  return (
    <div style={{display: 'flex', alignItems: 'flex-start', opacity: p, scale: `${interpolate(p, [0, 1], [0.94, 1])}`,
      transformOrigin: '50% 60%'}}>
      <span style={{fontFamily: FONT.sans, fontWeight: 900, fontSize: size, lineHeight: 1, letterSpacing: '-0.05em',
        color: color || c.ink, fontVariantNumeric: 'tabular-nums', whiteSpace: 'pre'}}>
        {chars.map((ch, i) => /[:.,·]/.test(ch) ? <span key={i} style={{color: c.accent}}>{ch}</span> : ch)}
      </span>
      {unit ? <span style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: size * 0.2, color: c.accent, marginLeft: size * 0.06,
        marginTop: size * 0.08, letterSpacing: '0'}}>{unit}</span> : null}
    </div>
  );
};

/** 영상 위 글자(레퍼런스 'What your land / IS WORTH?'): 가는 머리말 + 굵은 본문, 왼쪽 아래 어둠 */
export const FootageText: React.FC<{kicker?: string; text: string; frame: number; W: number; H: number; delay?: number;
  align?: 'left' | 'center' | 'right'; accent?: string}> = ({kicker, text, frame, W, H, delay = 0, align = 'left', accent}) => {
  const k = W / 1920;
  const {size, lines} = fitBlock(text.replace(/\*/g, ''), W * 0.62, H * 0.36, 118 * k, 56 * k, 1.02, 3, -0.035);
  // 사진 분석(data.safe.side)이 정한 빈 쪽에 놓는다 — 어둠도 그쪽에서
  const left = align === 'left' ? 96 * k : 0;
  const right = align === 'right' ? 96 * k : 0;
  const scrim = align === 'center' ? 'radial-gradient(70% 70% at 50% 55%, rgba(0,0,0,0.42) 0%, rgba(0,0,0,0.2) 100%)'
    : align === 'right' ? 'linear-gradient(270deg, rgba(0,0,0,0.5) 0%, rgba(0,0,0,0.22) 45%, rgba(0,0,0,0) 80%)'
      : 'linear-gradient(90deg, rgba(0,0,0,0.5) 0%, rgba(0,0,0,0.22) 45%, rgba(0,0,0,0) 80%)';
  return (
    <>
      <div style={{position: 'absolute', inset: 0, background: scrim}} />
      <div style={{position: 'absolute', left, right, top: 0, bottom: H * 0.2, display: 'flex',
        flexDirection: 'column', justifyContent: 'center', alignItems: align === 'center' ? 'center' : align === 'right' ? 'flex-end' : 'flex-start'}}>
        {kicker ? (
          <div style={{overflow: 'hidden', paddingBottom: 4}}>
            <div style={{fontFamily: FONT.sans, fontWeight: 400, fontSize: size * 0.5, letterSpacing: '-0.01em', color: 'rgba(255,255,255,0.9)',
              translate: `0 ${interpolate(tween(frame, delay, 14, 'enterText'), [0, 1], [105, 0])}%`}}>{kicker}</div>
          </div>
        ) : null}
        <Headline text={lines.join('\n')} size={size} color="#FFFFFF" accentColor={accent} frame={frame} delay={delay + 4} align={align}
          style={{textShadow: '0 2px 24px rgba(0,0,0,0.35)'}} />
      </div>
    </>
  );
};

/** 오린 사진 장면(레퍼런스 '✓ Zoning' 건물): 밝은 무대 + 가운데 오린 사진(바닥 그림자) + 칩들 + 왼쪽 헤드라인 */
export const CutoutScene: React.FC<{src: string; w: number; h: number; cutout: boolean; title?: string; chips?: string[];
  year?: string; theme: Theme; frame: number; dur: number; W: number; H: number}> = ({src, w, h, cutout, title, chips = [], year,
  theme, frame, dur, W, H}) => {
  const c = modernColors(theme);
  const k = W / 1920;
  const out = tweenOut(frame, dur, 10);
  const p = tween(frame, 0, 16, 'enterLarge');   // 0.5초 안에 그림이 보인다(빈 무대 금지)
  const maxH = H * (title ? 0.66 : 0.72);
  const maxW = title ? W * 0.42 : W * 0.6;
  const s = Math.min(maxW / w, maxH / h);
  const iw = w * s;
  const ih = h * s;
  const cx = title ? W * 0.68 : W * 0.5;
  const cy = H * 0.47;
  const file = staticFile(src);
  return (
    <div style={{position: 'absolute', inset: 0, opacity: out}}>
      <ModernStage theme={theme} frame={frame} />
      <div style={{position: 'absolute', left: cx - iw * 0.42, top: cy + ih * 0.46, width: iw * 0.84, height: ih * 0.1, borderRadius: '50%',
        background: 'rgba(18,19,21,0.22)', filter: 'blur(18px)', opacity: p}} />
      <div style={{position: 'absolute', left: cx - iw / 2, top: cy - ih / 2, width: iw, height: ih, opacity: p,
        translate: `0 ${interpolate(p, [0, 1], [40, 0])}px`, borderRadius: cutout ? 0 : 22 * k, overflow: cutout ? 'visible' : 'hidden',
        boxShadow: cutout ? undefined : softShadow(3), filter: cutout ? `drop-shadow(0 ${18 * k}px ${30 * k}px rgba(18,19,21,0.22))` : undefined}}>
        <Img src={file} style={{width: '100%', height: '100%', objectFit: cutout ? 'contain' : 'cover'}} />
      </div>
      {chips.slice(0, 3).map((t, i) => (
        <div key={i} style={{position: 'absolute', left: cx + iw * (i === 0 ? 0.36 : i === 1 ? -0.62 : 0.3),
          top: cy + ih * (i === 0 ? -0.34 : i === 1 ? 0.1 : 0.36)}}>
          <Pill text={t} c={c} frame={frame} delay={10 + i * 5} size={26 * k} />
        </div>
      ))}
      {title ? (
        <div style={{position: 'absolute', left: 120 * k, top: 0, bottom: H * 0.16, width: W * 0.42, display: 'flex', flexDirection: 'column',
          justifyContent: 'center', gap: 22 * k}}>
          {year ? <div style={{fontFamily: FONT.italic, fontStyle: 'italic', fontSize: 44 * k, color: c.deep, opacity: tween(frame, 4, 10)}}>{year}</div> : null}
          <Headline text={title} size={Math.min(96 * k, fitBlock(title, W * 0.42, H * 0.4, 96 * k, 48 * k, 1.06, 3, -0.035).size)}
            color={c.ink} accentColor={c.deep} frame={frame} delay={5} />
        </div>
      ) : null}
    </div>
  );
};

/** 화자 액자(타이틀·split): 흰 테두리 둥근 카드 + 부드러운 그림자 */
export const SpeakerFrame: React.FC<{x: number; y: number; w: number; h: number; opacity: number; radius?: number}> = ({x, y, w, h,
  opacity, radius = 28}) => (
  <div style={{position: 'absolute', left: x - 8, top: y - 8, width: w + 16, height: h + 16, borderRadius: radius + 8, background: '#FFFFFF',
    boxShadow: softShadow(3), opacity}} />
);

export const easeNames = Object.keys(EASE);
