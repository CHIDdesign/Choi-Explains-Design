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
import {BoardPanel, RecapBoard} from '../longform/Board';
import {CONCEPT_TEMPLATES, ConceptPlate, MediaPlate} from '../longform/Plates';
import {SectionBar} from '../longform/Note';
import {hashSeed, SourceCredit} from '../paper/Paper';

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
  recap: RecapBoard,
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
 * 한 그래픽을 스킨·레이아웃에 맞게 배치. paper 스킨(사용자 템플릿)은 PaperGraphic 이 전부 맡는다.
 * classic = 롱폼 무대(components/longform/, docs/롱폼_무대_디자인.md):
 *   pip/overlay → 얼굴 반대편 플레이트(개념은 유리 플레이트, 사진·스톡은 미디어 플레이트),
 *   split → 보드 판(화자 판 옆), fullscreen → 리포트 페이지(러닝 헤더), 타이틀은 두 스킨 공통 구도.
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
  // 타이틀은 두 스킨 공통 구도(글 왼쪽 + 화자 액자 오른쪽)
  if (g.template === 'title') {
    const ref = referenceGraphic({g, frame, dur, W, H, panelSide, chapterTag, faceX, brand, episode, theme, paperTexture});
    return <AbsoluteFill style={{background: theme.ink}}>{ref}</AbsoluteFill>;
  }
  const concept = CONCEPT_TEMPLATES.has(g.template);
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

  // 얼굴 반대편 종이 메모(롱폼 무대 재질 v2): 개념은 메모, 사진·스톡은 종이 위 사진 — 화자는 그대로.
  // 짧은 키워드는 화면 위 소제목 바(파이프라인이 머리 위가 비었을 때 pip.side='top' 으로)
  if (g.layout === 'pip' || g.layout === 'overlay') {
    if (g.pip?.side === 'top' && g.template === 'keyword') {
      return <SectionBar text={g.data.title || ''} frame={frame} dur={dur} W={W} theme={theme} seed={hashSeed(g.id)}
        maxW={g.pip.w} />;
    }
    if (media) return <MediaPlate g={g} frame={frame} dur={dur} W={W} theme={theme} faceX={faceX} />;
    if (concept) return <ConceptPlate g={g} frame={frame} dur={dur} W={W} theme={theme} faceX={faceX} />;
  }

  // 보드 판(화자 판 옆 작업대 열)
  if (g.layout === 'split') {
    return <BoardPanel g={g} Comp={Comp} frame={frame} dur={dur} fps={fps} theme={theme} brand={brand} episode={episode}
      W={W} H={H} panelSide={panelSide} chapterTag={chapterTag} />;
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

  // fullscreen — 리포트 페이지(러닝 헤더 + 템플릿)
  const clipIn = `inset(${(1 - pIn) * 100}% 0 0 0)`;
  const clipOut = `inset(0 0 ${(1 - pOut) * 100}% 0)`;
  const clip = frame < dur / 2 ? clipIn : clipOut;
  // 카드는 자기 캔버스(1920×1080)를 통째로 그린다 — 머리글·여백 없이
  const noHeader = g.template === 'photo' || g.template === 'broll' || g.template === 'card';
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
