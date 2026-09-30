import React from 'react';
import {AbsoluteFill} from 'remotion';
import {enter} from '../../lib/anim';
import {FONT} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import type {Brand, Chapter, Episode} from '../../lib/types';
import {DUR, STAGGER, tween} from '../../design/motion';
import {AccentText, LabelTag, PAPER, PaperBg, RoughBorder, SourceCredit, TornFrame} from '../paper/Paper';
import type {Box} from '../paper/Paper';
import {DrawRule, MaskLine} from './Editorial';

/**
 * 예전 classic 엔드카드(리포트 마지막 페이지 "One last word."). 유튜브 최종 화면 요소 자리 2개 확보.
 * 지금 LongForm 은 두 스킨 모두 아래 PaperEndCard(오늘의 정리)를 쓴다.
 */
export const EndCard: React.FC<{frame: number; theme: Theme; brand: Brand; episode: Episode; W: number; H: number}> = ({
  frame,
  theme,
  brand,
  episode,
  W,
  H,
}) => {
  const p = enter(frame, 0, 16);
  const slot = (x: number, label: string, delay: number) => (
    <div style={{position: 'absolute', left: x, top: H * 0.3, width: 560, height: 315,
      border: '1.5px solid rgba(255,255,255,0.28)', opacity: enter(frame, delay, 14), display: 'flex',
      alignItems: 'flex-end', padding: 18, boxSizing: 'border-box', fontFamily: FONT.sans, fontSize: 18,
      color: 'rgba(255,255,255,0.5)'}}>( {label} )</div>
  );
  return (
    <AbsoluteFill style={{background: theme.ink, clipPath: `inset(${(1 - p) * 100}% 0 0 0)`}}>
      <div style={{position: 'absolute', left: 96, top: 72, right: 96}}>
        <DrawRule frame={frame} delay={4} color="rgba(255,255,255,0.25)" />
        <div style={{display: 'flex', justifyContent: 'space-between', marginTop: 14, fontFamily: FONT.sans,
          fontSize: 18, color: 'rgba(255,255,255,0.6)'}}>
          <span>{brand.name}</span>
          <span>{episode.title}</span>
          <span>{brand.year}</span>
        </div>
      </div>
      {slot(W - 96 - 560 * 2 - 40, '다음 영상', 10)}
      {slot(W - 96 - 560, '추천 영상', 14)}
      <div style={{position: 'absolute', left: 96, bottom: 120}}>
        <MaskLine frame={frame} delay={6}>
          <div style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: 26, color: 'rgba(255,255,255,0.6)'}}>
            One last word.
          </div>
        </MaskLine>
        <MaskLine frame={frame} delay={10}>
          <div style={{fontFamily: FONT.display, fontWeight: 900, fontSize: 96, letterSpacing: '-0.04em', color: '#fff',
            lineHeight: 1.05}}>다음 이야기에서</div>
        </MaskLine>
        <MaskLine frame={frame} delay={14}>
          <div style={{fontFamily: FONT.display, fontWeight: 900, fontSize: 96, letterSpacing: '-0.04em',
            color: theme.accent, lineHeight: 1.05}}>만나요.</div>
        </MaskLine>
      </div>
    </AbsoluteFill>
  );
};

/**
 * 엔드카드(두 스킨 공통): 왼쪽에 오늘의 정리(챕터) + 인사, 오른쪽에 유튜브 최종 화면 요소 자리 2개(찢어진 액자).
 * classic 은 plain(단색 bg, 거친 테두리 없음), 종이 스킨은 구겨진 종이 texture + 거친 테두리.
 * 예전 엔드카드는 빈 칸 두 개뿐이라 15초가 비어 보였다.
 */
export const PaperEndCard: React.FC<{frame: number; brand: Brand; episode: Episode; chapters: Chapter[];
  texture?: string; plain?: boolean; bg?: string; W: number; H: number}> = ({frame, brand, episode, chapters, texture,
  plain, bg, W}) => {
  const rows = chapters.slice(0, 6);
  const slot = (b: Box, label: string, delay: number) => {
    const p = tween(frame, delay, DUR.slow, 'outCubic');
    return (
      <div style={{position: 'absolute', inset: 0, opacity: p, translate: `0 ${(1 - p) * 20}px`}}>
        <TornFrame b={b} seed={delay * 3 + 1}>
          <div style={{width: '100%', height: '100%', background: '#1B1B1F', display: 'flex', alignItems: 'center',
            justifyContent: 'center', fontFamily: FONT.sans, fontSize: 26, color: 'rgba(244,244,245,0.45)'}}>
            ( {label} )
          </div>
        </TornFrame>
      </div>
    );
  };
  return (
    <AbsoluteFill style={{opacity: tween(frame, 0, DUR.slow)}}>
      <PaperBg src={texture} style={bg ? {background: bg} : undefined} />
      {plain ? null : <RoughBorder seed={4} />}
      <SourceCredit text={brand.name} raw />
      <div style={{position: 'absolute', left: 156, top: 200, width: 820}}>
        <div style={{opacity: tween(frame, 4, DUR.normal)}}><LabelTag text="오늘의 정리" /></div>
        <div style={{marginTop: 34}}>
          {rows.map((c, i) => (
            <div key={i} style={{display: 'flex', gap: 22, alignItems: 'baseline', fontFamily: FONT.sans, fontSize: 36,
              lineHeight: 1.6, color: PAPER.white, opacity: tween(frame, 8 + i * STAGGER.item, DUR.normal),
              translate: `0 ${(1 - tween(frame, 8 + i * STAGGER.item, DUR.normal)) * 14}px`}}>
              <span style={{color: PAPER.accent, fontWeight: 700, width: 54}}>{c.number}</span>
              <span style={{fontWeight: 400}}>{c.title}</span>
            </div>
          ))}
        </div>
        <div style={{marginTop: 70, fontFamily: FONT.display, fontSize: 84, fontWeight: 400, letterSpacing: '-0.035em',
          lineHeight: 1.15, opacity: tween(frame, 20, DUR.reveal), whiteSpace: 'nowrap'}}>
          <AccentText text="다음 이야기에서 만나요." accent="만나요" />
        </div>
        <div style={{marginTop: 18, fontFamily: FONT.sans, fontSize: 24, color: PAPER.note,
          opacity: tween(frame, 26, DUR.normal)}}>( {episode.title} )</div>
      </div>
      {slot({x: W - 156 - 640, y: 176, w: 640, h: 360}, '다음 영상', 10)}
      {slot({x: W - 156 - 640, y: 596, w: 640, h: 360}, '추천 영상', 14)}
    </AbsoluteFill>
  );
};
