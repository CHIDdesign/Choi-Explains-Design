import React from 'react';
import {interpolate} from 'remotion';
import {DUR, springIn, tweenOut} from '../../design/motion';
import {FONT} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {fitSize} from '../../lib/fit';
import type {Callout} from '../../lib/types';

/**
 * 키워드 콜아웃 — 셜록현준 롱폼의 강조 방식(자막과 별도 레이어).
 * 화자 반대편 빈 공간(x 55~95%, y 30~55%)에 굵은 2줄, 핵심어 하나만 강조색, 위에 작은 맥락 라벨.
 * 등장은 스프링 팝(약 12f), 퇴장은 페이드(8f).
 */
export const CalloutLayer: React.FC<{items: Callout[]; t: number; fps: number; W: number; H: number; theme: Theme}> = ({
  items,
  t,
  fps,
  W,
  H,
  theme,
}) => {
  const c = items.find((x) => t >= x.start && t < x.end);
  if (!c) return null;
  const f = (t - c.start) * fps;
  const remain = (c.end - t) * fps;
  const pop = springIn(f, fps, 0, 'stiff');
  const out = tweenOut(-remain, 0, DUR.fast, 'inCubic');
  const lines = c.text.split('\n').filter(Boolean).slice(0, 2);
  const boxW = W * 0.4;
  const size = Math.min(92, ...lines.map((l) => fitSize(l, boxW, 92, 56, -0.03)));
  const left = c.side === 'right' ? W * 0.55 : W * 0.05;
  const renderLine = (l: string) => {
    if (!c.highlight || !l.includes(c.highlight)) return l;
    const [a, ...rest] = l.split(c.highlight);
    return (
      <>
        {a}
        <span style={{color: theme.accentLight}}>{c.highlight}</span>
        {rest.join(c.highlight)}
      </>
    );
  };
  return (
    <div style={{position: 'absolute', left, top: H * 0.3, width: boxW, display: 'flex', flexDirection: 'column',
      alignItems: c.side === 'right' ? 'flex-start' : 'flex-end', opacity: Math.min(1, pop * 1.4) * out,
      scale: `${interpolate(pop, [0, 1], [0.9, 1])}`, transformOrigin: c.side === 'right' ? '0% 50%' : '100% 50%'}}>
      {c.label ? (
        <div style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: 26, color: '#111', background: theme.accent,
          padding: '4px 12px 5px', marginBottom: 14, letterSpacing: '-0.01em'}}>
          {c.label}
        </div>
      ) : null}
      {lines.map((l, i) => (
        <div key={i} style={{fontFamily: FONT.display, fontWeight: 800, fontSize: size, lineHeight: 1.14,
          letterSpacing: '-0.035em', color: '#fff', whiteSpace: 'nowrap', paintOrder: 'stroke fill',
          WebkitTextStroke: '8px rgba(10,10,10,0.9)', textShadow: '0 6px 28px rgba(0,0,0,0.45)',
          textAlign: c.side === 'right' ? 'left' : 'right'}}>
          {renderLine(l)}
        </div>
      ))}
    </div>
  );
};
