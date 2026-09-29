import React from 'react';
import {interpolate} from 'remotion';
import {EASE_OUT, enter} from '../../lib/anim';
import {fitSize} from '../../lib/fit';
import {FONT} from '../../design/tokens';
import type {Theme} from '../../design/tokens';

/** 숏폼 상단 훅 타이틀 — 0초부터 끝까지 고정. 세이프존 y 270~560, 줄당 8~12자, 강조어 1개. */
export const HookTitle: React.FC<{
  text: string;
  highlight: string;
  series: string;
  frame: number;
  theme: Theme;
  width: number;
}> = ({text, highlight, series, frame, theme, width}) => {
  const lines = text.split('\n').filter(Boolean).slice(0, 2);
  const maxW = width - 65 - 140;
  const size = Math.min(...lines.map((l) => fitSize(l, maxW, 104, 64, -0.04)));
  const p = enter(frame, 0, 8, EASE_OUT); // 첫 프레임부터 거의 다 보이도록 아주 짧게
  const renderLine = (l: string) => {
    if (!highlight || !l.includes(highlight)) return l;
    const [a, ...rest] = l.split(highlight);
    return (
      <>
        {a}
        <span style={{color: theme.captionAccent}}>{highlight}</span>
        {rest.join(highlight)}
      </>
    );
  };
  return (
    <div style={{position: 'absolute', left: 65, width: maxW, top: 250, display: 'flex', flexDirection: 'column',
      alignItems: 'center'}}>
      {series ? (
        <div style={{fontFamily: FONT.sans, fontSize: 26, fontWeight: 600, color: 'rgba(255,255,255,0.9)',
          letterSpacing: '0.04em', marginBottom: 14, textShadow: '0 2px 10px rgba(0,0,0,0.6)',
          opacity: interpolate(p, [0, 1], [0.6, 1])}}>
          <span style={{display: 'inline-block', width: 12, height: 12, background: theme.accent, marginRight: 10,
            translate: '0 -2px'}} />
          {series}
        </div>
      ) : null}
      {lines.map((l, i) => (
        <div key={i} style={{fontFamily: FONT.display, fontWeight: 900, fontSize: size, lineHeight: 1.12,
          letterSpacing: '-0.04em', color: '#fff', textAlign: 'center', paintOrder: 'stroke fill',
          WebkitTextStroke: '12px #0A0A0A', textShadow: '0 8px 24px rgba(0,0,0,0.35)', whiteSpace: 'nowrap',
          scale: `${interpolate(p, [0, 1], [0.97, 1])}`}}>
          {renderLine(l)}
        </div>
      ))}
    </div>
  );
};
