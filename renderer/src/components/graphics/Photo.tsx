import React from 'react';
import {Img, interpolate, staticFile} from 'remotion';
import {enter, exit} from '../../lib/anim';
import {FONT, NOTE} from '../../design/tokens';
import {Credit, MaskLine} from '../layout/Editorial';
import type {TemplateProps} from './common';
import {CornerCredit, FilmLook, KeywordSlam} from '../longform/Note';

/** 자료 사진 — 풀스크린은 아주 느린 푸시인(최대 105%) + 필름 룩 + 우하단 출처, 접힌 키워드가 있으면 keyword_at 부터
 *  어두워지며 키워드 슬램(레퍼런스: 같은 사진이 이어진 채 큰 키워드). 패널은 액자형 */
export const PhotoCard: React.FC<TemplateProps> = ({id, data, frame, dur, fps, surface, box, layout, compact, theme}) => {
  if (!data.image) return null;
  const src = staticFile(data.image);
  const push = interpolate(frame, [0, dur], [1.0, 1.05]);
  const p = enter(frame, 0, 14);
  const out = exit(frame, dur, 10);
  if (layout === 'fullscreen' || layout === 'pip') {
    // 브랜드 로고 카드·세로 사진 여백 액자: 크림 종이 위 — 사진용 어둠·필름 입자 없이 아주 느린 푸시, 이름은 잉크색 가운데 아래
    if (data.logo || data.mat) {
      return (
        <div style={{position: 'absolute', inset: 0, opacity: out, overflow: 'hidden', background: NOTE.paper}}>
          <Img src={src} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover',
            scale: `${interpolate(frame, [0, dur], [0.98, 1.02])}`, translate: '0 -6%', opacity: p}} />
          {data.title ? (
            <div style={{position: 'absolute', left: 0, right: 0, bottom: 196, display: 'flex',
              flexDirection: 'column', alignItems: 'center', gap: 8}}>
              <MaskLine frame={frame} delay={8}>
                <div style={{fontFamily: FONT.display, fontWeight: 800, fontSize: 44, color: NOTE.ink,
                  letterSpacing: '-0.02em'}}>{data.title}</div>
              </MaskLine>
              {data.body ? (
                <MaskLine frame={frame} delay={12}>
                  <div style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: 26, color: NOTE.inkSoft}}>{data.body}</div>
                </MaskLine>
              ) : null}
            </div>
          ) : null}
          <CornerCredit text={data.credit || ''} opacity={enter(frame, 10, 12)} onPaper />
        </div>
      );
    }
    return (
      <div style={{position: 'absolute', inset: 0, opacity: out, overflow: 'hidden', background: '#0B0B0B'}}>
        <Img src={src} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover',
          scale: `${push}`, opacity: p}} />
        <div style={{position: 'absolute', inset: 0, background:
          'linear-gradient(180deg, rgba(0,0,0,0.35) 0%, rgba(0,0,0,0) 22%, rgba(0,0,0,0) 62%, rgba(0,0,0,0.55) 100%)'}} />
        {data.title ? (
          <div style={{position: 'absolute', left: 72, top: 60}}>
            <MaskLine frame={frame} delay={6}>
              <div style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: 34, color: '#fff',
                textShadow: '0 2px 14px rgba(0,0,0,0.4)'}}>{data.title}</div>
            </MaskLine>
            {data.body ? (
              <MaskLine frame={frame} delay={10}>
                <div style={{marginTop: 6, fontFamily: FONT.sans, fontWeight: 500, fontSize: 24,
                  color: 'rgba(255,255,255,0.85)'}}>{data.body}</div>
              </MaskLine>
            ) : null}
          </div>
        ) : null}
        <FilmLook frame={frame} id={id} strength={0.9} />
        {data.keyword && frame >= (data.keyword_at ?? 0) * fps ? (
          <KeywordSlam keyword={data.keyword} sub={data.keyword_sub} f={frame - (data.keyword_at ?? 0) * fps} W={box.w}
            theme={theme} />
        ) : null}
        <CornerCredit text={data.credit || ''} opacity={enter(frame, 10, 12)} />
      </div>
    );
  }
  // split(패널) / classic 숏폼 창·패널(compact)
  const frameH = box.h * (compact ? 0.9 : 0.74);
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center',
      opacity: out}}>
      <div style={{position: 'relative', width: '100%', height: frameH, overflow: 'hidden', background: '#000',
        clipPath: `inset(0 ${interpolate(p, [0, 1], [100, 0])}% 0 0)`}}>
        <Img src={src} style={{width: '100%', height: '100%', objectFit: 'cover', scale: `${push}`}} />
      </div>
      {!compact ? (
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 20}}>
          <div style={{fontFamily: FONT.sans, fontSize: 32, fontWeight: 700, color: surface.fg,
            opacity: enter(frame, 8, 12)}}>{data.title}{data.body ? <span style={{fontWeight: 500, color: surface.dim,
              marginLeft: 16, fontSize: 26}}>{data.body}</span> : null}</div>
          {data.credit ? <Credit text={data.credit} color={surface.dim} size={15} /> : null}
        </div>
      ) : null}
    </div>
  );
};
