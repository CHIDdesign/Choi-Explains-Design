import React from 'react';
import {Img, staticFile} from 'remotion';
import {photoPush} from '../../design/motion';
import {MODERN} from '../../design/tokens';
import type {TemplateProps} from './common';
import {coverMap, tooSoft} from '../../lib/crop';
import {DeskDocument} from '../material/Document';
import {PhotoOverlays} from '../material/Overlays';
import {CenterWord, CornerCredit, Super, superOn, superRight} from '../modern/Modern';

/** 자료 사진 — 각진 풀블리드, 약한 3% 푸시, 우하단 출처. 로고·세로 사진 여백판도 같은 자리에 그대로. 접힌 키워드는 keyword_at 부터 */
export const PhotoCard: React.FC<TemplateProps> = ({data, frame, dur, fps, box, theme}) => {
  if (!data.image) return null;
  const src = staticFile(data.image);
  const plate = data.logo || data.mat;
  // 사진 분석(studio/vision/compose.py): 얼굴이 잘리면 초점을 얼굴로(objectPosition), 그래도면 통째로(contain)
  const [px, py] = data.focus && data.focus.length >= 2 ? data.focus : [0.5, 0.5];
  const contain = !plate && (data.fit === 'contain' || tooSoft(data.w, data.h, box.w, box.h, data.safe?.soft));
  const print = contain && !!data.w && !!data.h;    // 통째로 보여야 하는 자료는 책상 위 인쇄물로(세로 자료는 한 가지 방식)
  const slam = data.keyword && frame >= (data.keyword_at ?? 0) * fps;
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: plate ? MODERN.bg : '#0B0B0B'}}>
      {print ? (
        <DeskDocument asset={{src: data.image, kind: 'photo', w: data.w as number, h: data.h as number}} W={box.w} H={box.h} frame={frame} dur={dur} fps={fps} clearLeft={superRight(data.title, data.body)}>
          {(m, v) => <PhotoOverlays data={data} map={m} W={box.w} H={box.h} frame={frame} fps={fps} grain={false} marks={!slam} onDesk view={v} />}
        </DeskDocument>
      ) : (
        <div style={{position: 'absolute', inset: 0, scale: `${contain ? 1 : photoPush(frame, dur)}`}}>
          <Img src={src} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: contain ? 'contain' : 'cover',
            objectPosition: `${(px * 100).toFixed(1)}% ${(py * 100).toFixed(1)}%`}} />
          <PhotoOverlays data={data} map={coverMap(data.w, data.h, box.w, box.h, px, py, contain ? 'contain' : 'cover')} W={box.w} H={box.h} frame={frame} fps={fps} grain={!plate} marks={!slam} />
        </div>
      )}
      {data.title && !slam ? <Super name={data.title} sub={data.body} theme={theme} box={box} frame={frame} on={print ? undefined : superOn(data.safe?.lum, coverMap(data.w, data.h, box.w, box.h, px, py, contain ? 'contain' : 'cover'), box, data.title, data.body)} /> : null}
      {slam ? <div style={{position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.4)'}} /> : null}
      {slam ? <CenterWord text={data.keyword!} sub={data.keyword_sub} W={box.w} H={box.h} frame={frame - (data.keyword_at ?? 0) * fps} y={0.46} /> : null}
      <CornerCredit text={data.credit || ''} tall={box.h > box.w} />
    </div>
  );
};
