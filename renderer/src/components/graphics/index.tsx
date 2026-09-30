import React from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {EASE_IN_OUT, EASE_OUT, enter, exit} from '../../lib/anim';
import {surface as mkSurface, surfaceFor, TEMPLATE_LABEL} from '../../design/surfaces';
import type {Theme} from '../../design/tokens';
import {GRID} from '../../design/tokens';
import type {Brand, Episode, Graphic, Skin, TemplateName} from '../../lib/types';
import {RunningHeader} from '../layout/Editorial';
import {ChapterCard, DefinitionCard, KeywordCard, LowerThird, QuoteCard, StatCard, TitleCard} from './Cards';
import type {TemplateProps} from './common';
import {CycleDiagram, DoubleDiamond, MatrixDiagram, ProcessDiagram, PyramidDiagram, VennDiagram} from './Diagrams';
import {CompareCard, ListCard, TimelineCard} from './Lists';
import {PhotoCard} from './Photo';
import {BrollCard} from './Broll';
import {MotionScene} from '../motion/MotionScene';
import {HtmlCard} from '../card/HtmlCard';
import {PaperGraphic, referenceGraphic} from '../paper/PaperGraphic';
import {ConceptCard, FramedMedia} from '../paper/Collage';
import {hashSeed, LabelTag, SourceCredit} from '../paper/Paper';

export const TEMPLATE_COMPONENTS: Record<TemplateName, React.FC<TemplateProps>> = {
  chapter: ChapterCard,
  keyword: KeywordCard,
  definition: DefinitionCard,
  quote: QuoteCard,
  list: ListCard,
  process: ProcessDiagram,
  cycle: CycleDiagram,
  double_diamond: DoubleDiamond,
  matrix: MatrixDiagram,
  compare: CompareCard,
  timeline: TimelineCard,
  stat: StatCard,
  venn: VennDiagram,
  pyramid: PyramidDiagram,
  photo: PhotoCard,
  motion: (p) => (p.data.spec ? <MotionScene spec={p.data.spec} frame={p.frame} fps={p.fps} dur={p.dur} box={p.box}
    surface={p.surface} id={p.id} /> : null),
  card: HtmlCard,
  broll: BrollCard,
  title: TitleCard,
  lower_third: LowerThird,
};

export const SPLIT_SPEAKER = 0.36; // 칠판 패널 레이아웃에서 화자 영역 비율

type Props = {
  g: Graphic;
  frame: number;
  dur: number;
  fps: number;
  theme: Theme;
  brand: Brand;
  episode: Episode;
  W: number;
  H: number;
  panelSide: 'left' | 'right';
  pageLabel: string;
  skin?: Skin;
  paperTexture?: string;
  chapterTag?: string;
  faceX?: number;
};

/**
 * 한 그래픽을 스킨·레이아웃에 맞게 배치. paper 스킨은 PaperGraphic 이 전부 맡는다.
 * classic: 레퍼런스 부분(referenceGraphic — 얼굴 위 사진 액자·개념 텍스트, 타이틀 구도)이 먼저,
 * 나머지는 풀스크린 / 칠판 패널(개념 카드 글 위계·찢어진 사진 액자) / 오버레이.
 */
export const GraphicLayer: React.FC<Props> = ({g, frame, dur, fps, theme, brand, episode, W, H, panelSide, pageLabel,
  skin, paperTexture, chapterTag = '', faceX = 0.5}) => {
  const Comp = TEMPLATE_COMPONENTS[g.template];
  if (!Comp) return null;
  // 자유 HTML 카드는 자기 배경·타이포를 다 가지고 있으니 스킨과 무관하게 아래 풀스크린/패널 경로로
  if (g.template !== 'card' && (g.skin ?? (skin === 'paper' ? 'paper' : 'classic')) === 'paper') {
    return <PaperGraphic g={g} Comp={Comp} frame={frame} dur={dur} fps={fps} theme={theme} brand={brand}
      episode={episode} W={W} H={H} panelSide={panelSide} chapterTag={chapterTag} faceX={faceX}
      paperTexture={paperTexture} />;
  }
  // 기본 스타일 위에 사용자 레퍼런스에서 가져온 부분: 얼굴 위 사진 액자·개념 텍스트, 타이틀 구도(글 왼쪽 + 화자 액자)
  const ref = referenceGraphic({g, frame, dur, W, H, panelSide, chapterTag, faceX, brand, episode, theme, paperTexture});
  if (ref) {
    return g.template === 'title' ? <AbsoluteFill style={{background: theme.ink}}>{ref}</AbsoluteFill> : ref;
  }
  const concept = ['keyword', 'definition', 'quote', 'stat'].includes(g.template);
  const media = g.template === 'photo' ? g.data.image : g.template === 'broll' ? g.data.src : undefined;
  const credit = g.data.credit || (g.template === 'quote' ? '' : g.data.source) || '';
  const specBg = g.template === 'motion' ? g.data.spec?.bg : undefined;
  const sName = specBg && specBg !== 'transparent' ? specBg : surfaceFor(g.template, g.layout);
  const s = mkSurface(theme, sName);
  const pIn = enter(frame, 0, 14, EASE_OUT);
  const pOut = exit(frame, dur, 10, EASE_IN_OUT);
  const headerH = GRID.headerH;
  const common = {id: g.id, data: g.data, fps, theme, brand, episode, layout: g.layout, surface: s};

  if (g.template === 'lower_third') {
    return <Comp {...common} frame={frame} dur={dur} box={{w: W, h: H}} />;
  }

  if (g.layout === 'split') {
    const pw = W * (1 - SPLIT_SPEAKER);
    const x = panelSide === 'right' ? W - pw : 0;
    const clip = panelSide === 'right'
      ? `inset(0 0 0 ${(1 - pIn) * 100}%)`
      : `inset(0 ${(1 - pIn) * 100}% 0 0)`;
    const pad = 72;
    return (
      <div style={{position: 'absolute', left: x, top: 0, width: pw, height: H, clipPath: clip, opacity: pOut,
        background: `radial-gradient(120% 90% at 50% 45%, ${s.bg} 0%, ${theme.boardEdge === s.bg ? s.bg : '#141514'} 100%)`,
        boxShadow: 'inset 0 0 120px rgba(0,0,0,0.45)'}}>
        <div style={{position: 'absolute', left: pad, right: pad, top: 34, display: 'flex', justifyContent: 'space-between',
          fontFamily: '"Pretendard", sans-serif', fontSize: 17, fontWeight: 500, color: s.dim,
          opacity: enter(frame, 4, 12)}}>
          <span>{brand.name}</span>
          <span>( {TEMPLATE_LABEL[g.template]} )</span>
        </div>
        <div style={{position: 'absolute', left: pad, top: 70, width: pw - pad * 2, height: 1, background: s.rule,
          opacity: enter(frame, 6, 12)}} />
        <div style={{position: 'absolute', left: pad, top: 118, width: pw - pad * 2, height: H - 118 - 170}}>
          {concept ? (
            // 레퍼런스의 글 위계: 라벨 태그 → 한 낱말만 강조색인 헤드라인 → 본문 → 회색 주석
            <ConceptCard template={g.template} data={g.data} label={chapterTag} frame={frame} dur={dur}
              box={{x: 0, y: 40, w: pw - pad * 2, h: H - 118 - 170 - 40}} />
          ) : media ? (
            <>
              {g.data.title ? <div style={{opacity: enter(frame, 2, 12)}}><LabelTag text={g.data.title} /></div> : null}
              <FramedMedia src={media} kind={g.template === 'broll' ? g.data.kind : 'photo'} frame={frame} dur={dur}
                seed={hashSeed(g.id)} b={{x: 0, y: 96, w: pw - pad * 2, h: Math.round((pw - pad * 2) * 0.58)}} />
            </>
          ) : (
            <Comp {...common} frame={frame} dur={dur} box={{w: pw - pad * 2, h: H - 118 - 170}} />
          )}
        </div>
        {credit ? <SourceCredit text={credit} top={H - 150} right={pad} opacity={enter(frame, 8, 12)} /> : null}
      </div>
    );
  }

  if (g.layout === 'overlay') {
    const scrim = Math.min(pIn, pOut);
    const m = GRID.margin + 24;
    return (
      <AbsoluteFill>
        <AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(0,0,0,0.25) 0%, rgba(0,0,0,0.55) 55%, rgba(0,0,0,0.7) 100%)',
          opacity: scrim}} />
        <div style={{position: 'absolute', left: m, top: 80, width: W - m * 2, height: H - 80 - 190}}>
          <Comp {...common} frame={frame} dur={dur} box={{w: W - m * 2, h: H - 80 - 190}} />
        </div>
      </AbsoluteFill>
    );
  }

  // fullscreen (pip·overlay 의 사진·개념 카드는 위 referenceGraphic 이 먼저 처리)
  const clipIn = `inset(${(1 - pIn) * 100}% 0 0 0)`;
  const clipOut = `inset(0 0 ${(1 - pOut) * 100}% 0)`;
  const clip = frame < dur / 2 ? clipIn : clipOut;
  // 카드는 자기 캔버스(1920×1080)를 통째로 그린다 — 머리글·여백 없이
  const noHeader = g.template === 'photo' || g.template === 'title' || g.template === 'broll' || g.template === 'card';
  const m = GRID.margin + 24;
  const top = noHeader ? 0 : headerH + 64;
  const bottom = noHeader ? 0 : 170;
  const innerW = noHeader ? W : W - m * 2;
  const innerH = H - top - bottom;
  return (
    <AbsoluteFill style={{clipPath: clip, background: s.bg}}>
      {!noHeader ? (
        <RunningHeader surface={s} frame={frame} width={W}
          cells={[brand.name, episode.title, brand.year, pageLabel || TEMPLATE_LABEL[g.template]]} />
      ) : null}
      <div style={{position: 'absolute', left: noHeader ? 0 : m, top, width: innerW, height: innerH,
        translate: `0 ${interpolate(pIn, [0, 1], [24, 0])}px`}}>
        <Comp {...common} frame={frame} dur={dur} box={{w: innerW, h: innerH}} />
      </div>
      {credit && !noHeader ? <SourceCredit text={credit} top={62} right={48} opacity={enter(frame, 8, 12)} /> : null}
    </AbsoluteFill>
  );
};
