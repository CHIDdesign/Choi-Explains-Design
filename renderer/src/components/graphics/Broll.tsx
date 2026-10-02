import React from 'react';
import {Img, interpolate, OffthreadVideo, staticFile} from 'remotion';
import {EASE, tween} from '../../design/motion';
import {FONT} from '../../design/tokens';
import {Credit} from '../layout/Editorial';
import type {TemplateProps} from './common';
import {CornerCredit} from '../longform/Note';
import {CollageScene} from '../press/CollageScene';
import {GRADE_QUOTE, QuoteOverlay} from '../press/Press';
import {CutoutScene, FootageText, modernColors, Pill} from '../modern/Modern';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/**
 * 스톡 B-roll(Pixabay·Unsplash·Coverr·Pexels 영상/사진) — "Keep it stupid cinematic": 꽉 찬 화면, 아주 느린 푸시인, 작은 ▣ 크레딧.
 * 사진은 켄번즈(방향 지정), 영상은 1.00→1.04 푸시인. 패널 레이아웃에서는 액자형.
 */
export const BrollCard: React.FC<TemplateProps> = ({id, data, frame, dur, fps, surface, box, layout, compact, theme}) => {
  if (!data.src) return null;
  // 디자인 v4: 오려 낸 사진은 밝은 무대 위 오린 장면(큰 글자 + 칩), 그 밖의 콜라주 지시는 전면 사진 + 영상 위 글자
  if (layout === 'fullscreen' && data.kind !== 'video' && data.cut) {
    return <CutoutScene src={data.cut} w={data.w ?? 1600} h={data.h ?? 1067} cutout title={data.display || ''}
      chips={[data.title || ''].filter(Boolean)} year={data.year} theme={theme} frame={frame} dur={dur} W={box.w} H={box.h} />;
  }
  void CollageScene;
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
        <div style={{position: 'absolute', inset: 0, scale: `${scale}`, translate: `${tx}% 0`,
          filter: data.quote ? GRADE_QUOTE : undefined}}>{media}</div>
        <div style={{position: 'absolute', inset: 0, background:
          'radial-gradient(120% 100% at 50% 45%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.35) 100%)'}} />
        {data.quote ? <QuoteOverlay text={data.quote} frame={frame} W={box.w} H={box.h} />
          : data.display ? <FootageText kicker={data.title} text={data.display} frame={frame} W={box.w} H={box.h} accent={theme.accentLight} />
          : data.title ? (
            <div style={{position: 'absolute', left: 72, top: 60}}>
              <Pill text={data.title} c={modernColors(theme)} frame={frame} delay={8} size={28} icon="dot" />
            </div>
          ) : null}
        {data.keyword && frame >= (data.keyword_at ?? 0) * fps ? (
          <FootageText kicker={data.keyword_sub} text={data.keyword} frame={frame - (data.keyword_at ?? 0) * fps} W={box.w} H={box.h}
            accent={theme.accentLight} />
        ) : null}
        <span style={{display: 'none'}}>{id}</span>
        <CornerCredit text={data.credit || ''} opacity={tween(frame, 12, 12)} />
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
