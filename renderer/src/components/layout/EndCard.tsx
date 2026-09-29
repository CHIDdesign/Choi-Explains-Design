import React from 'react';
import {AbsoluteFill} from 'remotion';
import {enter} from '../../lib/anim';
import {FONT} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import type {Brand, Episode} from '../../lib/types';
import {DrawRule, MaskLine} from './Editorial';

/** 엔드카드(리포트 마지막 페이지 "One last word."). 유튜브 최종 화면 요소 자리 2개 확보. */
export const EndCard: React.FC<{frame: number; theme: Theme; brand: Brand; episode: Episode; W: number; H: number}> = ({
  frame,
  theme,
  brand,
  episode,
  W,
  H,
}) => {
  const p = enter(frame, 0, 16);
  const slot = (x: number, label: string, delay: number) => (
    <div style={{position: 'absolute', left: x, top: H * 0.3, width: 560, height: 315,
      border: '1.5px solid rgba(255,255,255,0.28)', opacity: enter(frame, delay, 14), display: 'flex',
      alignItems: 'flex-end', padding: 18, boxSizing: 'border-box', fontFamily: FONT.sans, fontSize: 18,
      color: 'rgba(255,255,255,0.5)'}}>( {label} )</div>
  );
  return (
    <AbsoluteFill style={{background: theme.ink, clipPath: `inset(${(1 - p) * 100}% 0 0 0)`}}>
      <div style={{position: 'absolute', left: 96, top: 72, right: 96}}>
        <DrawRule frame={frame} delay={4} color="rgba(255,255,255,0.25)" />
        <div style={{display: 'flex', justifyContent: 'space-between', marginTop: 14, fontFamily: FONT.sans,
          fontSize: 18, color: 'rgba(255,255,255,0.6)'}}>
          <span>{brand.name}</span>
          <span>{episode.title}</span>
          <span>{brand.year}</span>
        </div>
      </div>
      {slot(W - 96 - 560 * 2 - 40, '다음 영상', 10)}
      {slot(W - 96 - 560, '추천 영상', 14)}
      <div style={{position: 'absolute', left: 96, bottom: 120}}>
        <MaskLine frame={frame} delay={6}>
          <div style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: 26, color: 'rgba(255,255,255,0.6)'}}>
            One last word.
          </div>
        </MaskLine>
        <MaskLine frame={frame} delay={10}>
          <div style={{fontFamily: FONT.display, fontWeight: 900, fontSize: 96, letterSpacing: '-0.04em', color: '#fff',
            lineHeight: 1.05}}>다음 이야기에서</div>
        </MaskLine>
        <MaskLine frame={frame} delay={14}>
          <div style={{fontFamily: FONT.display, fontWeight: 900, fontSize: 96, letterSpacing: '-0.04em',
            color: theme.accent, lineHeight: 1.05}}>만나요.</div>
        </MaskLine>
      </div>
    </AbsoluteFill>
  );
};
