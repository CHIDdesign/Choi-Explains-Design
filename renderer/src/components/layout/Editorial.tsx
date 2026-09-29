import React from 'react';
import {interpolate} from 'remotion';
import {EASE_OUT, enter} from '../../lib/anim';
import {FONT} from '../../design/tokens';
import type {Surface} from '../../design/surfaces';

/** 리포트 페이지 상단의 러닝 헤더: 브랜드 | 에피소드 | 연도 | 페이지 */
export const RunningHeader: React.FC<{
  surface: Surface;
  cells: string[];
  frame: number;
  width: number;
  size?: number;
}> = ({surface, cells, frame, width, size = 18}) => {
  const p = enter(frame, 2, 12);
  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width,
        height: size * 2.4,
        display: 'grid',
        gridTemplateColumns: `1.2fr 2fr 0.8fr 0.6fr`,
        alignItems: 'center',
        padding: `0 ${size * 2.4}px`,
        borderBottom: `1px solid ${surface.rule}`,
        fontFamily: FONT.sans,
        fontWeight: 500,
        fontSize: size,
        letterSpacing: '0.01em',
        color: surface.fg,
        opacity: p,
        boxSizing: 'border-box',
      }}
    >
      {cells.map((c, i) => (
        <div key={i} style={{textAlign: i === cells.length - 1 ? 'right' : i === 0 ? 'left' : 'center',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', opacity: i === 0 ? 1 : 0.85}}>
          {c}
        </div>
      ))}
    </div>
  );
};

/** 마스크 안에서 아래→위로 올라오는 텍스트 줄 */
export const MaskLine: React.FC<{
  frame: number;
  delay?: number;
  dur?: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({frame, delay = 0, dur = 16, children, style}) => {
  const p = enter(frame, delay, dur, EASE_OUT);
  return (
    <div style={{overflow: 'hidden', paddingBottom: '0.08em', ...style}}>
      <div style={{translate: `0 ${interpolate(p, [0, 1], [105, 0])}%`, opacity: interpolate(p, [0, 0.3, 1], [0, 1, 1])}}>
        {children}
      </div>
    </div>
  );
};

/** ( 괄호 라벨 ) — 리포트의 괄호 캡션 */
export const ParenLabel: React.FC<{text: string; surface: Surface; size?: number; frame: number; delay?: number}> = ({
  text,
  surface,
  size = 22,
  frame,
  delay = 0,
}) => (
  <div
    style={{
      fontFamily: FONT.sans,
      fontSize: size,
      fontWeight: 500,
      color: surface.dim,
      letterSpacing: '0.02em',
      opacity: enter(frame, delay, 12),
    }}
  >
    ( {text} )
  </div>
);

/** ▣ 크레딧 라벨 */
export const Credit: React.FC<{text: string; color: string; size?: number; style?: React.CSSProperties}> = ({
  text,
  color,
  size = 16,
  style,
}) => (
  <div style={{display: 'flex', alignItems: 'center', gap: size * 0.5, fontFamily: FONT.sans, fontSize: size,
    fontWeight: 500, color, letterSpacing: '0.02em', ...style}}>
    <span style={{display: 'inline-block', width: size * 0.7, height: size * 0.7, border: `1.5px solid ${color}`,
      position: 'relative'}}>
      <span style={{position: 'absolute', inset: 2, background: color, opacity: 0.8}} />
    </span>
    <span style={{whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 900}}>{text}</span>
  </div>
);

/** 가로 괘선이 왼→오로 그려짐 */
export const DrawRule: React.FC<{frame: number; delay?: number; color: string; width?: number | string; thick?: number}> = ({
  frame,
  delay = 0,
  color,
  width = '100%',
  thick = 1,
}) => {
  const p = enter(frame, delay, 18);
  return <div style={{width, height: thick, background: color, transformOrigin: 'left center', scale: `${p} 1`}} />;
};

/** 분필 질감 SVG 필터(칠판 표면 도식의 선을 살짝 거칠게) */
export const ChalkFilter: React.FC<{id: string; on: boolean}> = ({id, on}) =>
  on ? (
    <defs>
      <filter id={id} x="-5%" y="-5%" width="110%" height="110%">
        <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="7" result="n" />
        <feDisplacementMap in="SourceGraphic" in2="n" scale="2.4" xChannelSelector="R" yChannelSelector="G" />
      </filter>
    </defs>
  ) : null;
