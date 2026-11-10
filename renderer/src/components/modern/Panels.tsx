import React from 'react';
import {OffthreadVideo, staticFile} from 'remotion';
import {paperSettle} from '../../design/motion';
import {surface as mkSurface} from '../../design/surfaces';
import type {Theme} from '../../design/tokens';
import {liftDrop} from '../../design/tokens';
import type {Brand, Episode, Graphic} from '../../lib/types';
import type {TemplateProps} from '../graphics/common';
import {CutoutFrame} from '../material/Cutout';
import {Attach} from '../material/Marks';
import {Sheet} from '../material/Sheet';
import {GrainLayer} from '../material/Texture';
import {boardCard} from '../longform/Stage';
import {pipBoxes} from '../paper/Collage';
import {hashSeed} from '../paper/Paper';
import {CornerCredit} from './Modern';

/**
 * 디자인 v5.1 자리:
 *  ModernPlate : pip — 얼굴 반대편에 테이프로 붙은 오림 사진
 *  ModernPanel : split — 화자 칸 위로 찢긴 가장자리가 겹치는 양피지(비교할 때만)
 */
export const ModernPlate: React.FC<{g: Graphic; frame: number; W: number; faceX: number}> = ({g, frame, W, faceX}) => {
  const {b} = pipBoxes(faceX, W, g.pip);
  const src = g.template === 'broll' ? g.data.src : g.data.image;
  if (!src) return null;
  const credit = g.data.credit || '';
  const foot = credit ? 34 : 0;                    // 책장 위 작은 글자는 안 읽힌다 — 액자 아래 여백에 적는다
  const h = Math.round(b.w * 0.66) + foot;
  const seed = hashSeed(g.id);
  const rest = (seed % 2 ? 1 : -1) * (1 + (seed % 7) * 0.22);
  const m = paperSettle(frame, rest);
  const video = g.template === 'broll' && g.data.kind === 'video';
  return (
    <div style={{position: 'absolute', left: b.x, top: b.y, width: b.w, height: h, opacity: m.opacity, translate: `0 ${m.y}px`, scale: `${m.scale}`}}>
      {video ? (
        <div style={{position: 'absolute', inset: 0, rotate: `${m.rotate}deg`, filter: liftDrop(m.elev), border: '12px solid #FBF9F3', borderBottomWidth: 12 + foot, boxSizing: 'border-box', background: '#111'}}>
          <OffthreadVideo src={staticFile(src)} muted style={{width: '100%', height: '100%', objectFit: 'cover', display: 'block'}} />
          <CornerCredit text={credit} inFrame bottom={1 - foot} />
        </div>
      ) : (
        <CutoutFrame src={src} w={b.w} h={h} seed={seed} rotate={m.rotate} level={m.elev} foot={foot}>
          <CornerCredit text={credit} inFrame bottom={13} />
        </CutoutFrame>
      )}
      <Attach w={b.w} seed={seed} tw={148} th={42} />
    </div>
  );
};

export const ModernPanel: React.FC<{g: Graphic; Comp: React.FC<TemplateProps>; frame: number; dur: number; fps: number;
  theme: Theme; brand: Brand; episode: Episode; W: number; H: number; panelSide: 'left' | 'right'}>
  = ({g, Comp, frame, dur, fps, theme, brand, episode, W, H, panelSide}) => {
  const card = boardCard(panelSide, W, H);
  const media = g.template === 'photo' || g.template === 'broll';
  const pad = media ? 0 : 72;
  const bottom = media ? 0 : 150;   // 자막 자리
  const w = card.w - pad * 2;
  const h = card.h - pad - bottom;
  const body = (
    <div style={{position: 'absolute', left: pad, top: pad, width: w, height: h}}>
      <Comp id={g.id} data={g.data} fps={fps} theme={theme} brand={brand} episode={episode} layout={g.layout}
        surface={mkSurface(theme, 'modern')} frame={frame} dur={dur} box={{w, h}} />
    </div>
  );
  if (media) return <div style={{position: 'absolute', left: card.x, top: card.y, width: card.w, height: card.h, overflow: 'hidden'}}>{body}</div>;
  const over = 26;   // 찢긴 변이 화자 칸 위로 겹치는 폭
  const x = panelSide === 'right' ? card.x - over : card.x;
  return (
    <Sheet x={x} y={-10} w={card.w + over} h={card.h + 20} tex="parchment" seed={hashSeed(g.id)} liftLevel={2.4} torn={panelSide === 'right' ? {left: true} : {right: true}} amp={15}>
      <GrainLayer opacity={0.06} />
      <div style={{position: 'absolute', left: panelSide === 'right' ? over : 0, top: 10, width: card.w, height: card.h}}>{body}</div>
    </Sheet>
  );
};
