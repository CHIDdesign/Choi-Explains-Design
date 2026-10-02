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

/**
 * 레퍼런스 채널식 레터박스 제목(검정 바탕 위, y 180~395): 2줄 고정, 1줄 흰색 · 2줄 강조색, 초굵은 고딕.
 * 강조어가 있으면 그 단어만 강조색(두 줄 모두 흰색 + 핵심 명사만 강조).
 */
export const WindowTitle: React.FC<{text: string; highlight: string; frame: number; theme: Theme; width: number}> = ({
  text,
  highlight,
  frame,
  theme,
  width,
}) => {
  const lines = text.split('\n').filter(Boolean).slice(0, 2);
  const maxW = width - 90;
  const size = Math.min(96, ...lines.map((l) => fitSize(l, maxW, 96, 60, -0.035)));
  const p = enter(frame, 0, 6, EASE_OUT);
  const lineColor = (i: number) => (lines.length === 2 && i === 1 && !(highlight && lines.join('').includes(highlight))
    ? theme.accent : '#fff');
  const renderLine = (l: string) => {
    if (!highlight || !l.includes(highlight)) return l;
    const [a, ...rest] = l.split(highlight);
    return (
      <>
        {a}
        <span style={{color: theme.accent}}>{highlight}</span>
        {rest.join(highlight)}
      </>
    );
  };
  const top = lines.length === 1 ? 240 : 182;
  return (
    <div style={{position: 'absolute', left: 45, width: maxW, top, display: 'flex', flexDirection: 'column',
      alignItems: 'center', opacity: interpolate(p, [0, 1], [0.85, 1])}}>
      {lines.map((l, i) => (
        <div key={i} style={{fontFamily: FONT.display, fontWeight: 900, fontSize: size, lineHeight: 1.13,
          letterSpacing: '-0.035em', color: lineColor(i), textAlign: 'center', whiteSpace: 'nowrap'}}>
          {renderLine(l)}
        </div>
      ))}
    </div>
  );
};
