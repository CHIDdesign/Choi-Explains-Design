import React from 'react';
import {Img, interpolate, OffthreadVideo, staticFile} from 'remotion';
import {EASE, tween} from '../../design/motion';
import {FONT} from '../../design/tokens';
import {Credit, MaskLine} from '../layout/Editorial';
import type {TemplateProps} from './common';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/**
 * 스톡 B-roll(Pixabay·Unsplash·Coverr·Pexels 영상/사진) — "Keep it stupid cinematic": 꽉 찬 화면, 아주 느린 푸시인, 작은 ▣ 크레딧.
 * 사진은 켄번즈(방향 지정), 영상은 1.00→1.04 푸시인. 패널 레이아웃에서는 액자형.
 */
export const BrollCard: React.FC<TemplateProps> = ({data, frame, dur, surface, box, layout, compact}) => {
  if (!data.src) return null;
  const src = staticFile(data.src);
  const pIn = tween(frame, 0, 10, 'outQuint');
  const kb = data.kenburns ?? 'in';
  const prog = interpolate(frame, [0, dur], [0, 1], {...clamp, easing: EASE.linear});
  const scale = data.kind === 'video' ? 1 + 0.04 * prog : kb === 'out' ? 1.08 - 0.06 * prog : 1.02 + 0.06 * prog;
  const tx = kb === 'left' ? -2.5 * prog : kb === 'right' ? 2.5 * prog : 0;
  const media = data.kind === 'video'
    ? <OffthreadVideo src={src} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
    : <Img src={src} style={{width: '100%', height: '100%', objectFit: 'cover'}} />;
  if (layout === 'fullscreen' || layout === 'pip') {
    return (
      <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: '#000'}}>
        <div style={{position: 'absolute', inset: 0, scale: `${scale}`, translate: `${tx}% 0`}}>{media}</div>
        <div style={{position: 'absolute', inset: 0, background:
          'radial-gradient(120% 100% at 50% 45%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.35) 100%)'}} />
        {data.title ? (
          <div style={{position: 'absolute', left: 72, top: 60}}>
            <MaskLine frame={frame} delay={8}>
              <div style={{fontFamily: FONT.sans, fontWeight: 600, fontSize: 26, color: 'rgba(255,255,255,0.92)',
                textShadow: '0 2px 12px rgba(0,0,0,0.5)'}}>( {data.title} )</div>
            </MaskLine>
          </div>
        ) : null}
        {data.credit ? (
          <div style={{position: 'absolute', right: 72, top: 64, opacity: tween(frame, 12, 12)}}>
            <Credit text={data.credit} color="rgba(255,255,255,0.8)" size={15} />
          </div>
        ) : null}
      </div>
    );
  }
  const h = box.h * (compact ? 0.92 : 0.76);
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
      <div style={{position: 'relative', width: '100%', height: h, overflow: 'hidden', background: '#000',
        clipPath: `inset(0 ${(1 - pIn) * 100}% 0 0)`, borderRadius: 4}}>
        <div style={{position: 'absolute', inset: 0, scale: `${scale}`, translate: `${tx}% 0`}}>{media}</div>
      </div>
      {!compact && (data.title || data.credit) ? (
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 18}}>
          <div style={{fontFamily: FONT.sans, fontSize: 28, fontWeight: 600, color: surface.fg, opacity: tween(frame, 8, 10)}}>
            {data.title}
          </div>
          {data.credit ? <Credit text={data.credit} color={surface.dim} size={15} /> : null}
        </div>
      ) : null}
    </div>
  );
};
