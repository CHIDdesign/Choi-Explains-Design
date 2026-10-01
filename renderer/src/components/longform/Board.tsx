import React from 'react';
import {interpolate} from 'remotion';
import {LONG, tween, tweenOut} from '../../design/motion';
import {surface as mkSurface, TEMPLATE_LABEL} from '../../design/surfaces';
import type {Theme} from '../../design/tokens';
import {FONT, NOTE} from '../../design/tokens';
import {fitBlock} from '../../lib/fit';
import type {Brand, Episode, Graphic} from '../../lib/types';
import type {TemplateProps} from '../graphics/common';
import {Credit} from '../layout/Editorial';
import {Badge, Halftone, PaperFiber} from './Note';
import {CONCEPT_TEMPLATES, ConceptContent, MediaContent} from './Plates';
import {boardCard, DotGrid, RiseLine, Rule, slideIn, slideOut, STAGE} from './Stage';

/**
 * 보드 판(롱폼 무대의 split, classic 챕터) — 화자 판 옆 작업대 열에 놓이는 **크림 종이 판**(재질 v2).
 * 하프톤 점 + 머리줄(챕터 배지 · 템플릿 라벨) + 괘선 + 내용 + 바닥줄(브랜드 · 출처), 왼쪽 시그널 바.
 * 바깥 가장자리에서 안으로 쓸어 들어온다(18f). 개념·사진은 메모와 같은 내용 부품을 크게, 도식·목록·모션은 템플릿(종이 표면) 그대로.
 */
export const BoardPanel: React.FC<{g: Graphic; Comp: React.FC<TemplateProps>; frame: number; dur: number; fps: number;
  theme: Theme; brand: Brand; episode: Episode; W: number; H: number; panelSide: 'left' | 'right'; chapterTag: string}>
  = ({g, Comp, frame, dur, fps, theme, brand, episode, W, H, panelSide, chapterTag}) => {
  const card = boardCard(panelSide, W, H);
  const from = panelSide === 'right' ? 'right' : 'left';
  const s = {...mkSurface(theme, 'paper'), bg: NOTE.paper, fg: NOTE.ink, dim: NOTE.inkSoft, rule: NOTE.rule};
  const pad = STAGE.pad;
  const headH = 34;
  const footH = 30;
  const innerX = pad;
  const innerY = pad + headH + 26;
  const innerW = card.w - pad * 2;
  const innerH = card.h - innerY - pad - footH;
  const media = g.template === 'photo' || g.template === 'broll';
  const concept = CONCEPT_TEMPLATES.has(g.template);
  const credit = g.data.credit || (g.template === 'quote' ? '' : g.data.source) || '';
  const common = {id: g.id, data: g.data, fps, theme, brand, episode, layout: g.layout, surface: s};
  const scale = innerW / 700 * 0.86;
  return (
    <div style={{position: 'absolute', left: card.x, top: card.y, width: card.w, height: card.h,
      ...slideIn(frame, LONG.boardIn, from, 48), ...slideOut(frame, dur, from)}}>
      <div style={{position: 'absolute', inset: 0, borderRadius: STAGE.radius, overflow: 'hidden', background: s.bg,
        boxShadow: '0 24px 70px rgba(0,0,0,0.38)'}}>
        <Halftone opacity={0.5} />
        <PaperFiber id={`board-${g.id}`} opacity={0.12} />
        <DotGrid opacity={tween(frame, 6, 16) * 0.9} color={NOTE.dots} />
        <div style={{position: 'absolute', left: 0, top: 0, bottom: 0, width: 6, background: theme.accent,
          transformOrigin: 'top', scale: `1 ${tween(frame, 4, 16, 'outQuint')}`}} />
      </div>
      {/* 머리줄: 챕터 배지 · 템플릿 라벨 */}
      <div style={{position: 'absolute', left: innerX, right: pad, top: pad, height: headH, display: 'flex',
        alignItems: 'center', justifyContent: 'space-between', opacity: tween(frame, 4, 10)}}>
        <Badge text={chapterTag || brand.name} size={20} />
        <span style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: 18, color: s.dim, letterSpacing: '0.02em'}}>
          ( {TEMPLATE_LABEL[g.template] || g.template} )
        </span>
      </div>
      <div style={{position: 'absolute', left: innerX, width: innerW, top: pad + headH + 12}}>
        <Rule frame={frame} delay={6} color={s.rule} />
      </div>
      {/* 내용 */}
      <div style={{position: 'absolute', left: innerX, top: innerY, width: innerW, height: innerH}}>
        {concept ? (
          <ConceptContent template={g.template} data={g.data} frame={frame} dur={dur} theme={theme} w={innerW}
            h={innerH} s={scale} mode="board" />
        ) : media ? (
          <MediaContent data={g.data} template={g.template} frame={frame} dur={dur} w={innerW} h={innerH} s={scale}
            radius={6} />
        ) : (
          <div style={{position: 'absolute', inset: 0, opacity: tween(frame, 8, 12),
            translate: `0 ${interpolate(tween(frame, 8, 14, 'outQuint'), [0, 1], [14, 0])}px`}}>
            <Comp {...common} frame={frame} dur={dur} box={{w: innerW, h: innerH}} />
          </div>
        )}
      </div>
      {/* 바닥줄 */}
      <div style={{position: 'absolute', left: innerX, right: pad, bottom: pad - 8, height: footH, display: 'flex',
        alignItems: 'center', justifyContent: 'space-between', opacity: tween(frame, 10, 12)}}>
        <span style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: 16, color: s.dim, letterSpacing: '0.04em'}}>
          {brand.name}
        </span>
        {credit && !media ? <Credit text={credit} color={s.dim} size={15} /> : null}
      </div>
    </div>
  );
};

/**
 * 챕터 정리 보드(템플릿 recap, 자동) — 챕터 끝 7초: 챕터 주장(헤드라인) → 번호 붙은 핵심 개념 2~4줄.
 * 목록 템플릿과 달리 한꺼번에 보이는 '정리'다(줄마다 5f 스태거).
 */
export const RecapBoard: React.FC<TemplateProps> = ({data, frame, dur, surface, box, theme}) => {
  const items = (data.items || []).slice(0, 4);
  const n = items.length;
  const title = data.title || '';
  const label = data.subtitle || '이번 챕터 정리';
  const hb = fitBlock(title, box.w, box.h * 0.3, 60, 34, 1.18, 2, -0.035);
  const rowH = Math.min(96, (box.h - hb.lines.length * hb.size * 1.18 - 100) / Math.max(1, n));
  const itemSize = Math.min(40, rowH * 0.42);
  const out = tweenOut(frame, dur, LONG.out);
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center',
      opacity: out}}>
      <div style={{opacity: tween(frame, 2, 10)}}><Badge text={label} size={22} accent={theme.accent} /></div>
      <div style={{marginTop: 18, display: 'flex', flexDirection: 'column'}}>
        {hb.lines.map((l, i) => (
          <RiseLine key={i} frame={frame} delay={5 + i * 3}>
            <div style={{fontFamily: FONT.serif, fontWeight: 700, fontSize: hb.size * 0.96, lineHeight: 1.26,
              letterSpacing: '-0.02em', color: surface.fg, whiteSpace: 'nowrap'}}>{l}</div>
          </RiseLine>
        ))}
      </div>
      <div style={{marginTop: 26}}><Rule frame={frame} delay={8} color={surface.rule} /></div>
      <div style={{marginTop: 8}}>
        {items.map((it, i) => {
          const p = tween(frame, 12 + i * 5, 14, 'outQuint');
          return (
            <div key={i} style={{height: rowH, display: 'flex', alignItems: 'center', gap: 24,
              borderBottom: i < n - 1 ? `1px solid ${surface.rule}` : 'none', opacity: p,
              translate: `${interpolate(p, [0, 1], [18, 0])}px 0`}}>
              <span style={{fontFamily: FONT.latin, fontSize: itemSize * 1.05, lineHeight: 1, color: surface.accent,
                width: itemSize * 1.5, flexShrink: 0}}>{String(i + 1).padStart(2, '0')}</span>
              <span style={{fontFamily: FONT.sans, fontWeight: 600, fontSize: itemSize, color: surface.fg,
                letterSpacing: '-0.015em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>{it}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
