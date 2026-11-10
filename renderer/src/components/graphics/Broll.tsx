import React from 'react';
import {Img, OffthreadVideo, staticFile} from 'remotion';
import {photoPush} from '../../design/motion';
import type {TemplateProps} from './common';
import {coverMap, tooSoft} from '../../lib/crop';
import {DeskDocument} from '../material/Document';
import {PhotoOverlays} from '../material/Overlays';
import {CenterWord, CornerCredit, QuoteSlot, Super, superOn, superRight} from '../modern/Modern';

/** 스톡 영상·사진 — 각진 풀블리드, 약한 3% 푸시, 우하단 출처 */
export const BrollCard: React.FC<TemplateProps> = ({data, frame, dur, fps, box, theme}) => {
  if (!data.src) return null;
  const src = staticFile(data.src);
  const video = data.kind === 'video';
  // 사진 분석(studio/vision/compose.py): 얼굴 초점·통째 보기(영상은 분석하지 않는다)
  const [px, py] = data.focus && data.focus.length >= 2 ? data.focus : [0.5, 0.5];
  const contain = !video && (data.fit === 'contain' || tooSoft(data.w, data.h, box.w, box.h, data.safe?.soft));
  const print = contain && !!data.w && !!data.h;    // 통째로 보여야 하는 자료는 책상 위 인쇄물로(세로 자료는 한 가지 방식)
  const word = data.keyword && frame >= (data.keyword_at ?? 0) * fps ? data.keyword : data.display;
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: '#000'}}>
      {print ? (
        <DeskDocument asset={{src: data.src, kind: 'photo', w: data.w as number, h: data.h as number}} W={box.w} H={box.h} frame={frame} dur={dur} fps={fps} clearLeft={superRight(data.title)}>
          {(m, v) => <PhotoOverlays data={data} map={m} W={box.w} H={box.h} frame={frame} fps={fps} grain={false} marks={!word && !data.quote} onDesk view={v} />}
        </DeskDocument>
      ) : <div style={{position: 'absolute', inset: 0, scale: `${contain ? 1 : photoPush(frame, dur)}`}}>
        {video ? <OffthreadVideo src={src} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
          : <Img src={src} style={{width: '100%', height: '100%', objectFit: contain ? 'contain' : 'cover', objectPosition: `${(px * 100).toFixed(1)}% ${(py * 100).toFixed(1)}%`}} />}
        <PhotoOverlays data={data} map={video ? null : coverMap(data.w, data.h, box.w, box.h, px, py, contain ? 'contain' : 'cover')} W={box.w} H={box.h} frame={frame} fps={fps}
          marks={!word && !data.quote} />
      </div>}
      {word ? <div style={{position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.4)'}} /> : null}
      {data.quote ? <QuoteSlot text={data.quote} W={box.w} H={box.h} frame={frame} />
        : word ? <CenterWord text={word} sub={data.keyword ? data.keyword_sub : data.title} W={box.w} H={box.h} y={0.46}
          frame={data.keyword ? frame - (data.keyword_at ?? 0) * fps : frame} />
          : data.title ? <Super name={data.title} theme={theme} box={box} frame={frame} on={video || print ? undefined : superOn(data.safe?.lum, coverMap(data.w, data.h, box.w, box.h, px, py, contain ? 'contain' : 'cover'), box, data.title)} /> : null}
      <CornerCredit text={data.credit || ''} tall={box.h > box.w} />
    </div>
  );
};
