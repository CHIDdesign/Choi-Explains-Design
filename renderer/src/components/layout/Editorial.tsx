import React from 'react';
import {interpolate} from 'remotion';
import {EASE_OUT, enter} from '../../lib/anim';

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

/** 분필 질감 SVG 필터(칠판 표면 도식의 선을 살짝 거칠게, 최대 ±1.2px).
 *  노이즈는 필터 영역 왼쪽 위 96×96 조각만 계산하고(feTurbulence 의 x·y 를 비우면 필터 영역 원점) feTile 로 깐다 — 예전엔
 *  도식 전체 넓이의 펄린 노이즈를 매 프레임 다시 계산해 도식 화면 렌더가 두 배 이상 느렸다. 결정적이고 모양은 같다. */
export const ChalkFilter: React.FC<{id: string; on: boolean}> = ({id, on}) =>
  on ? (
    <defs>
      <filter id={id} x="-5%" y="-5%" width="110%" height="110%">
        <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="7" width="96" height="96"
          stitchTiles="stitch" result="t" />
        <feTile in="t" result="n" />
        <feDisplacementMap in="SourceGraphic" in2="n" scale="2.4" xChannelSelector="R" yChannelSelector="G" />
      </filter>
    </defs>
  ) : null;
