import React from 'react';
import {interpolate} from 'remotion';
import {enter, revealAt} from '../../lib/anim';
import {fitBlock, fitSize} from '../../lib/fit';
import {FONT} from '../../design/tokens';
import {DrawRule, MaskLine, ParenLabel} from '../layout/Editorial';
import type {TemplateProps} from './common';
import {modernColors} from '../modern/Modern';
import {softShadow} from '../../design/tokens';

const Title: React.FC<{text: string; label: string} & Pick<TemplateProps, 'frame' | 'surface' | 'box' | 'compact'>> = ({
  text,
  label,
  frame,
  surface,
  box,
  compact,
}) => {
  if (!text) return null;
  const size = fitSize(text, box.w * 0.9, compact ? 54 : 72, 34, -0.03);
  return (
    <div style={{marginBottom: compact ? 18 : 34}}>
      {!compact ? <ParenLabel text={label} surface={surface} frame={frame} size={22} /> : null}
      {!compact ? <div style={{height: 12}} /> : null}
      <MaskLine frame={frame} delay={2}>
        <div style={{fontFamily: FONT.display, fontWeight: 800, fontSize: size, letterSpacing: '-0.03em',
          color: surface.fg, lineHeight: 1.1}}>{text}</div>
      </MaskLine>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 목록 — 말하는 속도에 맞춰 하나씩. 지금 말하는 항목만 또렷하게.
// ---------------------------------------------------------------------------
export const ListCard: React.FC<TemplateProps> = (props) => {
  const {data, frame, dur, surface, box, compact, theme} = props;
  const items = (data.items || []).slice(0, 6);
  const n = items.length;
  const titleH = data.title ? (compact ? 70 : 150) : 0;
  const rowH = Math.min((box.h - titleH) / Math.max(1, n), compact ? 86 : 120);
  const size = Math.min(rowH * 0.46, compact ? 40 : 52);
  const lastShown = items.reduce((acc, _, i) => (frame >= revealAt(i, n, dur) ? i : acc), -1);
  if (surface.name === 'modern' || surface.name === 'dark') {
    // 디자인 v4(레퍼런스 'Project Pricing'): 둥근 행(옅은 디자인 색) + 번호, 지금 말하는 행은 흰 카드 + 그림자
    const c = modernColors(theme, surface.name === 'dark');
    const gap = Math.round(rowH * 0.12);
    const h = rowH - gap;
    return (
      <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
        <Title text={data.title || ''} label="정리" {...props} />
        <div style={{display: 'flex', flexDirection: 'column', gap}}>
          {items.map((it, i) => {
            const at = revealAt(i, n, dur);
            const p = enter(frame, at, 14);
            const active = i === lastShown;
            return (
              <div key={i} style={{height: h, borderRadius: h * 0.34, background: active ? c.card : c.cardTint, border: `1px solid ${c.line}`,
                boxShadow: active ? softShadow(2, c.dark) : undefined, display: 'flex', alignItems: 'center', gap: size * 0.7,
                padding: `0 ${size * 0.7}px`, opacity: p * (active ? 1 : 0.62), translate: `0 ${interpolate(p, [0, 1], [14, 0])}px`}}>
                <span style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: size * 0.72, color: active ? c.accent : c.inkSoft,
                  width: size * 1.3, letterSpacing: '-0.02em', fontVariantNumeric: 'tabular-nums'}}>{String(i + 1).padStart(2, '0')}</span>
                <span style={{fontFamily: FONT.sans, fontWeight: active ? 700 : 500, fontSize: size * 0.92, color: c.ink, letterSpacing: '-0.02em',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>{it}</span>
              </div>
            );
          })}
        </div>
      </div>
    );
  }
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
      <Title text={data.title || ''} label="정리" {...props} />
      {items.map((it, i) => {
        const at = revealAt(i, n, dur);
        const p = enter(frame, at, 14);
        const active = i === lastShown;
        return (
          <div key={i} style={{height: rowH, display: 'flex', flexDirection: 'column', justifyContent: 'center',
            opacity: p * (active ? 1 : 0.5), translate: `${interpolate(p, [0, 1], [24, 0])}px 0`}}>
            <div style={{display: 'flex', alignItems: 'baseline', gap: size * 0.9}}>
              <div style={{fontFamily: FONT.latin, fontSize: size * 1.05, color: active ? surface.accent : surface.dim,
                width: size * 1.6}}>{String(i + 1).padStart(2, '0')}</div>
              <div style={{fontFamily: FONT.sans, fontWeight: active ? 700 : 500, fontSize: size, color: surface.fg,
                letterSpacing: '-0.01em'}}>{it}</div>
            </div>
            <div style={{marginTop: rowH * 0.18}}>
              <DrawRule frame={frame} delay={at + 2} color={surface.rule} />
            </div>
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 비교 A vs B
// ---------------------------------------------------------------------------
export const CompareCard: React.FC<TemplateProps> = (props) => {
  const {data, frame, dur, surface, box, compact} = props;
  const a = (data.items || []).slice(0, 4);
  const b = (data.items_b || []).slice(0, 4);
  const colW = box.w * 0.42;
  const headSize = Math.min(fitSize(data.title || '', colW, compact ? 64 : 96, 36, -0.04),
    fitSize(data.title_b || '', colW, compact ? 64 : 96, 36, -0.04));
  const itemSize = compact ? 32 : 40;
  const half = dur * 0.45;
  const col = (head: string, items: string[], start: number, align: 'left' | 'right', hot: boolean) => (
    <div style={{width: colW, textAlign: align}}>
      <MaskLine frame={frame} delay={start}>
        <div style={{fontFamily: FONT.display, fontWeight: 900, fontSize: headSize, letterSpacing: '-0.04em',
          color: hot ? surface.accent : surface.fg, lineHeight: 1.05}}>{head}</div>
      </MaskLine>
      <div style={{height: compact ? 14 : 26}} />
      <DrawRule frame={frame} delay={start + 4} color={surface.rule} />
      <div style={{height: compact ? 12 : 22}} />
      {items.map((it, i) => (
        <MaskLine key={i} frame={frame} delay={start + 8 + i * 6}>
          <div style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: itemSize, lineHeight: 1.6, color: surface.fg}}>
            {it}
          </div>
        </MaskLine>
      ))}
    </div>
  );
  return (
    <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
      {data.subtitle ? (
        <div style={{marginBottom: compact ? 16 : 40}}>
          <ParenLabel text={data.subtitle} surface={surface} frame={frame} size={compact ? 22 : 28} />
        </div>
      ) : null}
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', position: 'relative'}}>
        {col(data.title || 'A', a, 2, 'left', false)}
        <div style={{position: 'absolute', left: '50%', top: 0, translate: '-50% 0', fontFamily: FONT.latin,
          fontSize: compact ? 44 : 64, color: surface.dim, opacity: enter(frame, 6, 12)}}>VS</div>
        {col(data.title_b || 'B', b, Math.round(half * 0.35), 'right', true)}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 연표
// ---------------------------------------------------------------------------
export const TimelineCard: React.FC<TemplateProps> = (props) => {
  const {data, frame, dur, surface, box, compact} = props;
  const items = (data.items || []).slice(0, 6).map((s) => {
    const [y, ...rest] = s.split('|');
    return rest.length ? {year: y.trim(), label: rest.join('|').trim()} : {year: '', label: s.trim()};
  });
  const n = items.length;
  const lineY = box.h * (compact ? 0.52 : 0.55);
  const lineP = enter(frame, 4, Math.max(20, dur * 0.25));
  const slot = box.w / Math.max(1, n);
  const lastShown = items.reduce((acc, _, i) => (frame >= revealAt(i, n, dur) ? i : acc), -1);
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <div style={{position: 'absolute', top: 0, left: 0, right: 0}}>
        <Title text={data.title || ''} label="연표" {...props} />
      </div>
      <div style={{position: 'absolute', left: 0, top: lineY, width: box.w, height: 2, background: surface.fg,
        transformOrigin: 'left', scale: `${lineP} 1`}} />
      {items.map((it, i) => {
        const at = revealAt(i, n, dur);
        const p = enter(frame, at, 14);
        const active = i === lastShown;
        const x = slot * i + slot * 0.1;
        const labelBlock = fitBlock(it.label, slot * 0.86, 140, compact ? 30 : 36, 20, 1.3, 3);
        return (
          <div key={i} style={{position: 'absolute', left: x, top: 0, width: slot * 0.86, opacity: p}}>
            <div style={{position: 'absolute', top: lineY - (compact ? 74 : 104), fontFamily: FONT.latin,
              fontSize: compact ? 52 : 76, color: active ? surface.accent : surface.fg, lineHeight: 1}}>{it.year}</div>
            <div style={{position: 'absolute', top: lineY - 9, left: 0, width: 18, height: 18, borderRadius: 9,
              background: active ? surface.accent : surface.bg, border: `2px solid ${active ? surface.accent : surface.fg}`}} />
            <div style={{position: 'absolute', top: lineY + 34, fontFamily: FONT.sans, fontWeight: active ? 700 : 500,
              fontSize: labelBlock.size, lineHeight: 1.3, color: surface.fg}}>
              {labelBlock.lines.map((l, k) => <div key={k}>{l}</div>)}
            </div>
          </div>
        );
      })}
    </div>
  );
};
