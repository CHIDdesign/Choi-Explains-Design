import React from 'react';
import {interpolate} from 'remotion';
import {tween, tweenOut} from '../../design/motion';
import {FONT, softShadow} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {fitBlock} from '../../lib/fit';
import type {Brand, Chapter, Episode, GraphicData} from '../../lib/types';
import {BigNumeral, CornerLabels, Headline, ModernStage, modernColors, Pill} from './Modern';

/**
 * 디자인 v4 길잡이 부품(영상 안에서 한 가지 모양): 타이틀 · 챕터 카드 · 엔드카드.
 * 밝은 무대 + 자간 좁힌 굵은 헤드라인(어절마다 등장) + 알약 칩 + 모서리 작은 라벨. 큰 숫자는 Pretendard 900.
 */

export const ModernTitle: React.FC<{data: GraphicData; frame: number; dur: number; theme: Theme; W: number; H: number;
  brand: Brand; episode: Episode; textW: number; left: number}> = ({data, frame, dur, theme, W, H, brand, episode, textW,
  left}) => {
  const c = modernColors(theme);
  const k = W / 1920;
  const title = data.title || episode.title;
  const {size, lines} = fitBlock(title.replace(/\*/g, ''), textW, H * 0.44, 128 * k, 68 * k, 1.06, 3, -0.035);
  const kicker = [episode.number ? `EP ${episode.number}` : '', episode.series].filter(Boolean).join(' · ');
  const out = tweenOut(frame, dur, 10);
  const sub = episode.subtitle || data.subtitle || '';
  // 어절의 *강조* 표시는 줄 나눔 뒤에도 살린다
  const accentWords = new Set(title.split(/\s+/).filter((w) => /^\*.+\*[.,!?…]*$/.test(w)).map((w) => w.replace(/\*/g, '')));
  const text = lines.map((l) => l.split(/\s+/).map((w) => accentWords.has(w) ? `*${w}*` : w).join(' ')).join('\n');
  return (
    <div style={{position: 'absolute', inset: 0, opacity: out}}>
      <CornerLabels frame={frame} W={W} H={H} c={c} tl={brand.name} tr={episode.series || brand.presenterTitle}
        bl={brand.year} br={brand.presenter} />
      <div style={{position: 'absolute', left, top: 0, bottom: H * 0.1, width: textW, display: 'flex', flexDirection: 'column',
        justifyContent: 'center'}}>
        {kicker ? <div><Pill text={kicker} c={c} frame={frame} delay={2} size={24 * k} icon="dot" fill="tint" /></div> : null}
        <div style={{height: 26 * k}} />
        <Headline text={text} size={size} color={c.ink} accentColor={c.deep} frame={frame} delay={6} />
        {sub ? (
          <div style={{marginTop: 26 * k, overflow: 'hidden'}}>
            <div style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: 36 * k, lineHeight: 1.4, color: c.inkSoft,
              letterSpacing: '-0.015em', translate: `0 ${interpolate(tween(frame, 16, 14, 'enterText'), [0, 1], [105, 0])}%`}}>{sub}</div>
          </div>
        ) : null}
        <div style={{marginTop: 38 * k, display: 'flex', alignItems: 'center', gap: 14 * k, opacity: tween(frame, 20, 12)}}>
          <div style={{width: 44 * k, height: 3, background: c.accent, borderRadius: 2}} />
          <div style={{fontFamily: FONT.sans, fontWeight: 600, fontSize: 26 * k, color: c.ink, letterSpacing: '-0.01em'}}>
            {[brand.presenter, brand.presenterTitle].filter(Boolean).join(' · ')}
          </div>
        </div>
      </div>
    </div>
  );
};

export const ModernChapter: React.FC<{data: GraphicData; frame: number; dur: number; theme: Theme; W: number; H: number}>
  = ({data, frame, dur, theme, W, H}) => {
  const c = modernColors(theme);
  const k = W / 1920;
  const num = data.number || '01';
  const title = data.title || '';
  const map = (data.items || []).slice(0, 7);
  const cur = typeof data.highlight === 'number' ? data.highlight : -1;
  const {size, lines} = fitBlock(title.replace(/\*/g, ''), W * 0.5, H * 0.32, 112 * k, 60 * k, 1.06, 3, -0.035);
  const out = tweenOut(frame, dur, 10);
  return (
    <div style={{position: 'absolute', inset: 0, opacity: out}}>
      <ModernStage theme={theme} frame={frame} />
      <CornerLabels frame={frame} W={W} H={H} c={c} tl={`${num} / ${map.length ? String(map.length).padStart(2, '0') : ''}`.replace(/ \/ $/, '')}
        tr={data.subtitle ? '' : ''} />
      <div style={{position: 'absolute', left: 120 * k, top: H * 0.5, translate: '0 -56%'}}>
        <BigNumeral text={num} size={Math.min(H * 0.56, 430 * k)} c={c} frame={frame} delay={0} color={c.deep} />
      </div>
      <div style={{position: 'absolute', left: W * 0.43, top: 0, bottom: H * 0.1, width: W * 0.5, display: 'flex', flexDirection: 'column',
        justifyContent: 'center'}}>
        <div><Pill text={`챕터 ${num}`} c={c} frame={frame} delay={3} size={24 * k} icon="dot" fill="tint" /></div>
        <div style={{height: 24 * k}} />
        <Headline text={lines.join('\n')} size={size} color={c.ink} accentColor={c.deep} frame={frame} delay={8} />
        {data.subtitle ? (
          <div style={{marginTop: 22 * k, overflow: 'hidden'}}>
            <div style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: 34 * k, lineHeight: 1.45, color: c.inkSoft,
              translate: `0 ${interpolate(tween(frame, 18, 14, 'enterText'), [0, 1], [105, 0])}%`}}>{data.subtitle}</div>
          </div>
        ) : null}
        {map.length > 1 ? (
          <div style={{marginTop: 34 * k, display: 'flex', flexWrap: 'wrap', gap: 10 * k, maxWidth: W * 0.5}}>
            {map.map((m, i) => (
              <Pill key={i} text={`${String(i + 1).padStart(2, '0')}  ${m}`} c={c} frame={frame} delay={22 + i * 3} size={20 * k}
                icon="none" fill={i === cur ? 'accent' : 'card'} style={{opacity: i === cur ? 1 : 0.7}} />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export const ModernEndCard: React.FC<{frame: number; brand: Brand; episode: Episode; chapters: Chapter[]; theme: Theme; W: number;
  H: number}> = ({frame, brand, episode, chapters, theme, W, H}) => {
  const c = modernColors(theme);
  const k = W / 1920;
  const rows = chapters.slice(0, 5);
  const slot = (x: number, y: number, w: number, h: number, label: string, delay: number) => {
    const p = tween(frame, delay, 16, 'enterLarge');
    return (
      <div style={{position: 'absolute', left: x, top: y, width: w, height: h, borderRadius: 24 * k, background: c.card,
        border: `1px solid ${c.line}`, boxShadow: softShadow(2), opacity: p, translate: `0 ${(1 - p) * 24}px`, display: 'flex',
        alignItems: 'center', justifyContent: 'center', fontFamily: FONT.sans, fontWeight: 600, fontSize: 24 * k, color: c.inkSoft}}>
        {label}
      </div>
    );
  };
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <ModernStage theme={theme} frame={frame} />
      <CornerLabels frame={frame} W={W} H={H} c={c} tl={brand.name} tr={episode.series || ''} bl={brand.year} br={brand.presenter} />
      <div style={{position: 'absolute', left: 120 * k, top: H * 0.16, width: W * 0.42}}>
        <Headline text={'다음 이야기에서\n*만나요.*'} size={92 * k} color={c.ink} accentColor={c.deep} frame={frame} delay={4} />
        <div style={{marginTop: 30 * k, display: 'flex', flexDirection: 'column', gap: 10 * k}}>
          {rows.map((ch, i) => (
            <div key={i} style={{display: 'flex', alignItems: 'baseline', gap: 14 * k, opacity: tween(frame, 18 + i * 3, 10),
              translate: `${interpolate(tween(frame, 18 + i * 3, 12, 'enter'), [0, 1], [12, 0])}px 0`}}>
              <span style={{fontFamily: FONT.italic, fontStyle: 'italic', fontSize: 26 * k, color: c.deep, width: 44 * k}}>{ch.number}</span>
              <span style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: 26 * k, color: c.ink, letterSpacing: '-0.01em',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: W * 0.36}}>{ch.title}</span>
            </div>
          ))}
        </div>
      </div>
      {slot(W * 0.58, H * 0.2, W * 0.34, H * 0.34, '다음 영상', 8)}
      {slot(W * 0.58, H * 0.58, W * 0.16, H * 0.24, '구독', 12)}
      {slot(W * 0.76, H * 0.58, W * 0.16, H * 0.24, '재생목록', 15)}
    </div>
  );
};
