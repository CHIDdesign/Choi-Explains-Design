import React from 'react';
import {interpolate} from 'remotion';
import {tween, tweenOut} from '../../design/motion';
import {FONT} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {fitBlock} from '../../lib/fit';
import type {Brand, Episode, GraphicData} from '../../lib/types';
import {Highlighter, PaperStage, PrintText, pressColors} from './Press';

/**
 * 디자인 v3 길잡이 부품(영상 안에서 한 가지 모양): 챕터 카드 · 타이틀.
 * 큰 숫자는 이탤릭 세리프(Playfair 900 italic, 인쇄 얼룩), 제목은 송명(예술적인 명조), 주장은 고운바탕, 작은 킥커는 Instrument Serif 이탤릭.
 */
const Rise: React.FC<{frame: number; delay: number; children: React.ReactNode; style?: React.CSSProperties}> = ({frame,
  delay, children, style}) => {
  const p = tween(frame, delay, 16, 'enterText');
  return (
    <div style={{overflow: 'hidden', paddingBottom: '0.08em', ...style}}>
      <div style={{translate: `0 ${interpolate(p, [0, 1], [105, 0])}%`}}>{children}</div>
    </div>
  );
};

export const CollageChapter: React.FC<{data: GraphicData; frame: number; dur: number; theme: Theme; W: number;
  H: number}> = ({data, frame, dur, theme, W, H}) => {
  const c = pressColors(theme);
  const k = W / 1920;
  const num = data.number || '01';
  const title = data.title || '';
  const map = (data.items || []).slice(0, 7);
  const cur = typeof data.highlight === 'number' ? data.highlight : -1;
  const {size, lines} = fitBlock(title, W * 0.5, H * 0.34, 118 * k, 64 * k, 1.12, 3, -0.03);
  const numSize = Math.min(H * 0.62, 470 * k);
  const out = tweenOut(frame, dur, 10);
  return (
    <div style={{position: 'absolute', inset: 0, opacity: out}}>
      <PaperStage theme={theme} frame={frame} />
      <div style={{position: 'absolute', left: 120 * k, top: H * 0.5 - numSize * 0.62,
        opacity: tween(frame, 0, 8), translate: `${interpolate(tween(frame, 0, 22, 'enterLarge'), [0, 1], [-30 * k, 0])}px 0`}}>
        <PrintText text={num} size={numSize} color={c.deep} font={FONT.numeral} weight={900} italic seed={31} density={0.035}
          paper={c.paper} letterSpacing="-0.03em" lineHeight={1} />
      </div>
      <div style={{position: 'absolute', left: W * 0.43, top: H * 0.17, width: W * 0.5}}>
        <Rise frame={frame} delay={4}>
          <div style={{fontFamily: FONT.italic, fontStyle: 'italic', fontSize: 40 * k, color: c.deep, letterSpacing: '0.01em'}}>
            Chapter {num}
          </div>
        </Rise>
        <div style={{height: 3, background: c.deep, width: W * 0.5 * tween(frame, 8, 14, 'enter'), margin: `${18 * k}px 0 ${30 * k}px`,
          opacity: 0.85}} />
        {lines.map((l, i) => (
          <Rise key={i} frame={frame} delay={10 + i * 3}>
            <div style={{fontFamily: FONT.editorial, fontWeight: 400, fontSize: size, lineHeight: 1.18, color: c.ink,
              letterSpacing: '-0.02em', whiteSpace: 'nowrap'}}>{l}</div>
          </Rise>
        ))}
        {data.subtitle ? (
          <Rise frame={frame} delay={16} style={{marginTop: 22 * k}}>
            <div style={{fontFamily: FONT.serif, fontWeight: 400, fontSize: 38 * k, lineHeight: 1.45, color: c.inkSoft}}>
              {data.subtitle}
            </div>
          </Rise>
        ) : null}
        {map.length > 1 ? (
          <div style={{marginTop: 40 * k, display: 'flex', flexDirection: 'column', gap: 8 * k}}>
            {map.map((m, i) => {
              const on = i === cur;
              const p = tween(frame, 20 + i * 3, 12, 'enter');
              return (
                <div key={i} style={{position: 'relative', display: 'flex', alignItems: 'baseline', gap: 16 * k,
                  opacity: p * (on ? 1 : 0.5), translate: `${interpolate(p, [0, 1], [12, 0])}px 0`}}>
                  {on ? <Highlighter x={-10 * k} y={4 * k} w={W * 0.36} h={40 * k} theme={theme}
                    p={tween(frame, 26 + i * 3, 12, 'enter')} /> : null}
                  <span style={{position: 'relative', fontFamily: FONT.numeral, fontStyle: 'italic', fontWeight: 700,
                    fontSize: 30 * k, color: c.deep, width: 44 * k}}>{String(i + 1).padStart(2, '0')}</span>
                  <span style={{position: 'relative', fontFamily: FONT.sans, fontWeight: on ? 600 : 400, fontSize: 30 * k,
                    color: c.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: W * 0.4}}>{m}</span>
                </div>
              );
            })}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export const CollageTitle: React.FC<{data: GraphicData; frame: number; dur: number; theme: Theme; W: number; H: number;
  brand: Brand; episode: Episode; textW: number; left: number}> = ({data, frame, dur, theme, W, H, brand, episode,
  textW, left}) => {
  const c = pressColors(theme);
  const k = W / 1920;
  const title = data.title || episode.title;
  const {size, lines} = fitBlock(title, textW, H * 0.44, 132 * k, 70 * k, 1.12, 3, -0.03);
  const kicker = [episode.number ? `Episode ${episode.number}` : '', episode.series].filter(Boolean).join(' · ');
  const out = tweenOut(frame, dur, 10);
  const sub = episode.subtitle || data.subtitle || '';
  return (
    <div style={{position: 'absolute', inset: 0, opacity: out}}>
      <div style={{position: 'absolute', left, top: H * 0.24, width: textW}}>
        {kicker ? (
          <Rise frame={frame} delay={2}>
            <div style={{fontFamily: FONT.italic, fontStyle: 'italic', fontSize: 42 * k, color: c.deep}}>{kicker}</div>
          </Rise>
        ) : null}
        <div style={{height: 22 * k}} />
        {lines.map((l, i) => (
          <Rise key={i} frame={frame} delay={6 + i * 3}>
            <div style={{fontFamily: FONT.editorial, fontWeight: 400, fontSize: size, lineHeight: 1.18, color: c.ink,
              letterSpacing: '-0.02em', whiteSpace: 'nowrap'}}>{l}</div>
          </Rise>
        ))}
        {sub ? (
          <Rise frame={frame} delay={14} style={{marginTop: 26 * k}}>
            <div style={{fontFamily: FONT.serif, fontWeight: 400, fontSize: 40 * k, lineHeight: 1.45, color: c.inkSoft}}>{sub}</div>
          </Rise>
        ) : null}
        <div style={{marginTop: 40 * k, display: 'flex', alignItems: 'center', gap: 16 * k, opacity: tween(frame, 18, 12)}}>
          <div style={{width: 56 * k, height: 3, background: c.deep}} />
          <div style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: 28 * k, color: c.ink}}>
            {[brand.presenter, brand.presenterTitle].filter(Boolean).join(' · ')}
          </div>
        </div>
      </div>
      <div style={{position: 'absolute', right: 48 * k, bottom: 30 * k, fontFamily: FONT.italic, fontStyle: 'italic',
        fontSize: 26 * k, color: c.inkSoft, opacity: tween(frame, 10, 12)}}>{brand.name}</div>
    </div>
  );
};
