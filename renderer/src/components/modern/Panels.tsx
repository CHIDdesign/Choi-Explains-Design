import React from 'react';
import {interpolate} from 'remotion';
import {LONG, tween} from '../../design/motion';
import {surface as mkSurface} from '../../design/surfaces';
import type {Theme} from '../../design/tokens';
import {FONT, softShadow} from '../../design/tokens';
import type {Brand, Episode, Graphic} from '../../lib/types';
import type {TemplateProps} from '../graphics/common';
import {Credit} from '../layout/Editorial';
import {CONCEPT_TEMPLATES, ConceptContent, MediaContent, plateBox} from '../longform/Plates';
import {boardCard, slideIn, slideOut, STAGE} from '../longform/Stage';
import {modernColors, Pill} from './Modern';

/**
 * 디자인 v4 판·메모: 화자 옆 흰 둥근 카드(부드러운 그림자). 종이 메모(PaperNote)·크림 보드 판(BoardPanel)의 v4 판.
 *  ModernPlate : pip/overlay — 얼굴 반대편 카드(개념은 ConceptContent, 사진·스톡은 MediaContent)
 *  ModernPanel : split — 화자 판 옆 작업대 열의 카드(머리줄 = 챕터 이름 칩)
 */
type PlateProps = {g: Graphic; frame: number; dur: number; W: number; theme: Theme; faceX: number; label?: string};

export const ModernPlate: React.FC<PlateProps> = ({g, frame, dur, W, theme, faceX, label}) => {
  const {b, right, s} = plateBox(g, faceX, W);
  const c = modernColors(theme);
  const media = g.template === 'photo' || g.template === 'broll';
  const pad = Math.round((media ? 16 : 34) * s);
  const from = right ? 'right' : 'left';
  return (
    <div style={{position: 'absolute', left: b.x, top: b.y, width: b.w, height: b.h, ...slideIn(frame, LONG.boardIn, from, 40),
      ...slideOut(frame, dur, from)}}>
      <div style={{position: 'absolute', inset: 0, borderRadius: Math.round(26 * s), background: c.card, border: `1px solid ${c.line}`,
        boxShadow: softShadow(3)}} />
      <div style={{position: 'absolute', left: pad, top: pad, width: b.w - pad * 2, height: b.h - pad * 2}}>
        {media ? (
          <MediaContent data={g.data} template={g.template} frame={frame} dur={dur} w={b.w - pad * 2} h={b.h - pad * 2} s={s}
            radius={Math.round(14 * s)} />
        ) : (
          <ConceptContent template={g.template} data={g.data} frame={frame} dur={dur} theme={theme} w={b.w - pad * 2}
            h={b.h - pad * 2} s={s} mode="plate" label={label} />
        )}
      </div>
    </div>
  );
};

export const ModernPanel: React.FC<{g: Graphic; Comp: React.FC<TemplateProps>; frame: number; dur: number; fps: number;
  theme: Theme; brand: Brand; episode: Episode; W: number; H: number; panelSide: 'left' | 'right'; chapterTag: string}>
  = ({g, Comp, frame, dur, fps, theme, brand, episode, W, H, panelSide, chapterTag}) => {
  const card = boardCard(panelSide, W, H);
  const from = panelSide === 'right' ? 'right' : 'left';
  const c = modernColors(theme);
  const s = {...mkSurface(theme, 'modern'), bg: c.card};
  const pad = STAGE.pad;
  const headH = 40;
  const innerX = pad;
  const innerY = pad + headH + 22;
  const innerW = card.w - pad * 2;
  const innerH = card.h - innerY - pad - 24;
  const media = g.template === 'photo' || g.template === 'broll';
  const concept = CONCEPT_TEMPLATES.has(g.template);
  const credit = g.data.credit || (g.template === 'quote' ? '' : g.data.source) || '';
  const common = {id: g.id, data: g.data, fps, theme, brand, episode, layout: g.layout, surface: s};
  const scale = innerW / 700 * 0.86;
  return (
    <div style={{position: 'absolute', left: card.x, top: card.y, width: card.w, height: card.h,
      ...slideIn(frame, LONG.boardIn, from, 48), ...slideOut(frame, dur, from)}}>
      <div style={{position: 'absolute', inset: 0, borderRadius: 28, background: c.card, border: `1px solid ${c.line}`,
        boxShadow: softShadow(3)}} />
      <div style={{position: 'absolute', left: innerX, top: pad, height: headH, display: 'flex', alignItems: 'center'}}>
        {chapterTag ? <Pill text={chapterTag} c={c} frame={frame} delay={4} size={18} icon="dot" fill="tint" /> : null}
      </div>
      <div style={{position: 'absolute', left: innerX, top: innerY, width: innerW, height: innerH}}>
        {concept ? (
          <ConceptContent template={g.template} data={g.data} frame={frame} dur={dur} theme={theme} w={innerW} h={innerH}
            s={scale} mode="board" />
        ) : media ? (
          <MediaContent data={g.data} template={g.template} frame={frame} dur={dur} w={innerW} h={innerH} s={scale} radius={16} />
        ) : (
          <div style={{position: 'absolute', inset: 0, opacity: tween(frame, 8, 12),
            translate: `0 ${interpolate(tween(frame, 8, 14, 'outQuint'), [0, 1], [14, 0])}px`}}>
            <Comp {...common} frame={frame} dur={dur} box={{w: innerW, h: innerH}} />
          </div>
        )}
      </div>
      {credit && !media ? (
        <div style={{position: 'absolute', right: pad, bottom: pad - 6, opacity: tween(frame, 10, 12)}}>
          <Credit text={credit} color={c.inkSoft} size={15} />
        </div>
      ) : null}
      <span style={{display: 'none', fontFamily: FONT.sans}} />
    </div>
  );
};
