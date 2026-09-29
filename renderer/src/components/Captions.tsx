import React from 'react';
import {interpolate} from 'remotion';
import {lastIndexAtOrBefore} from '../lib/time';
import type {CaptionCue} from '../lib/types';
import {FONT} from '../design/tokens';
import type {Theme} from '../design/tokens';

const activeCue = (cues: CaptionCue[], t: number): CaptionCue | null => {
  const i = lastIndexAtOrBefore(cues, t, (c) => c.start);
  if (i < 0) return null;
  const c = cues[i];
  return t < c.end ? c : null;
};

/** 롱폼 자막 — 하단 중앙, 최대 2줄, 강조어 1개 강조색 */
export const LongCaptions: React.FC<{
  cues: CaptionCue[];
  t: number;
  fps: number;
  theme: Theme;
  style: 'shadow' | 'box';
  bottom?: number;
  centerX?: number; // 칠판 패널이 열려 있으면 패널 가운데로
  frameW?: number;
}> = ({cues, t, fps, theme, style, bottom = 64, centerX, frameW = 1920}) => {
  const cue = activeCue(cues, t);
  if (!cue) return null;
  const local = (t - cue.start) * fps;
  const remain = (cue.end - t) * fps;
  const op = Math.min(interpolate(local, [0, 3], [0, 1], {extrapolateRight: 'clamp'}),
    interpolate(remain, [0, 3], [0, 1], {extrapolateRight: 'clamp'}));
  const size = 46;
  return (
    <div style={{position: 'absolute', left: (centerX ?? frameW / 2) - frameW / 2, width: frameW, bottom, display: 'flex',
      flexDirection: 'column', alignItems: 'center', gap: style === 'box' ? 6 : 2, opacity: op}}>
      {cue.lines.map((line, li) => (
        <div key={li} style={{
          fontFamily: FONT.sans,
          fontWeight: 600,
          fontSize: size,
          lineHeight: 1.32,
          letterSpacing: '-0.01em',
          color: '#fff',
          textAlign: 'center',
          padding: style === 'box' ? '4px 16px' : 0,
          background: style === 'box' ? 'rgba(10,10,10,0.62)' : undefined,
          textShadow: style === 'shadow' ? '0 0 2px rgba(0,0,0,0.9), 0 2px 10px rgba(0,0,0,0.75), 0 0 22px rgba(0,0,0,0.35)' : undefined,
          WebkitTextStroke: style === 'shadow' ? '0.6px rgba(0,0,0,0.55)' : undefined,
          whiteSpace: 'nowrap',
        }}>
          {line.map((w, wi) => (
            <span key={wi} style={{color: w.em ? theme.captionAccent : '#fff', fontWeight: w.em ? 800 : 600}}>
              {wi > 0 ? ' ' : ''}{w.text}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
};

/** 숏폼 자막 — 1~3어절 청크, 굵고 크게, 강조어만 색. 튀는 애니메이션 없이 100→104% 미세 팝. */
export const ShortCaptions: React.FC<{
  cues: CaptionCue[];
  t: number;
  fps: number;
  theme: Theme;
  y: number;
  width: number;
}> = ({cues, t, fps, theme, y, width}) => {
  const cue = activeCue(cues, t);
  if (!cue) return null;
  const local = (t - cue.start) * fps;
  const pop = interpolate(local, [0, 2.5, 5], [0.96, 1.04, 1], {extrapolateRight: 'clamp'});
  const text = cue.lines.map((l) => l.map((w) => w.text).join(' ')).join(' ');
  const size = text.length > 12 ? 66 : 74;
  return (
    <div style={{position: 'absolute', left: 65, width: width - 65 - 140, top: y, display: 'flex',
      flexDirection: 'column', alignItems: 'center', scale: `${pop}`}}>
      {cue.lines.map((line, li) => (
        <div key={li} style={{fontFamily: FONT.sans, fontWeight: 800, fontSize: size, lineHeight: 1.18,
          letterSpacing: '-0.02em', textAlign: 'center', color: '#fff', paintOrder: 'stroke fill',
          WebkitTextStroke: '10px #0A0A0A', textShadow: '0 6px 18px rgba(0,0,0,0.45)', whiteSpace: 'nowrap'}}>
          {line.map((w, wi) => (
            <span key={wi} style={{color: w.em ? theme.captionAccent : '#fff'}}>{wi > 0 ? ' ' : ''}{w.text}</span>
          ))}
        </div>
      ))}
    </div>
  );
};
