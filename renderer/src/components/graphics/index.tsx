import React from 'react';
import {AbsoluteFill} from 'remotion';
import {surface as mkSurface, surfaceFor, surfaceForSpecBg} from '../../design/surfaces';
import type {Theme} from '../../design/tokens';
import {GRID} from '../../design/tokens';
import type {Brand, Episode, Graphic, Skin, TemplateName} from '../../lib/types';
import {ChapterCard, CollageCard, CutoutStackCard, DefinitionCard, KeywordCard, KeywordMontageCard, LowerThird, QuoteCard, StampCard, StatCard, TitleCard} from './Cards';
import type {TemplateProps} from './common';
import {CycleDiagram, DoubleDiamond, MatrixDiagram, ProcessDiagram, PyramidDiagram, VennDiagram} from './Diagrams';
import {CompareCard, ListCard, TimelineCard} from './Lists';
import {PhotoCard} from './Photo';
import {BrollCard} from './Broll';
import {EvidenceCard} from '../longform/Evidence';
import {MotionScene} from '../motion/MotionScene';
import {HtmlCard} from '../card/HtmlCard';
import {PaperGraphic} from '../paper/PaperGraphic';
import {ChapterBadge, CornerCredit, ModernStage, TopicMemo} from '../modern/Modern';
import {ModernChapter, ModernTitle} from '../modern/Titles';
import {ModernPanel, ModernPlate} from '../modern/Panels';
import {Sheet} from '../material/Sheet';
import {hashSeed} from '../paper/Paper';

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
  evidence: EvidenceCard,
  title: TitleCard,
  lower_third: LowerThird,
  stamp: StampCard,
  cutout_stack: CutoutStackCard,
  collage: CollageCard,
  keyword_montage: KeywordMontageCard,
};

// 자기 자리에 정해진 모양으로 그리는 슬롯 — 레이아웃과 상관없이 화면 전체 좌표로 받는다(판·칸 안에 넣지 않는다)
const SLOT_TEMPLATES: ReadonlySet<string> = new Set(['definition', 'quote', 'lower_third', 'stamp', 'cutout_stack']);
const CONCEPT_TEMPLATES: ReadonlySet<string> = new Set(['keyword', 'definition', 'quote', 'stat']);
/** 글자 슬롯은 나란히 놓지 않는다 — 분할은 비교할 때만 */
export const isSplit = (g: Graphic) => g.layout === 'split' && !CONCEPT_TEMPLATES.has(g.template);

const IDENT_SEC = 3.4; // 아이덴트 최대 길이(초) — 뒤는 화자로 컷

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
  skin?: Skin;
  paperTexture?: string;
  chapterTag?: string;
  faceX?: number;
};

/**
 * 한 그래픽을 슬롯·레이아웃에 맞게 배치(디자인 v5, docs/디자인_v5_토크쇼.md). paper 스킨(시험용)은 PaperGraphic 이 맡는다.
 * 전면 자료는 끊어 넣고(등장·퇴장 없음), 글자는 정해진 자리에만.
 */
export const GraphicLayer: React.FC<Props> = ({g, frame, dur, fps, theme, brand, episode, W, H, panelSide,
  skin, paperTexture, chapterTag = '', faceX = 0.5}) => {
  const Comp = TEMPLATE_COMPONENTS[g.template];
  if (!Comp) return null;
  if (g.template === 'evidence' || g.template === 'collage' || g.template === 'keyword_montage') {
    return (
      <AbsoluteFill>
        <Comp id={g.id} data={g.data} fps={fps} theme={theme} brand={brand} episode={episode} layout={g.layout}
          surface={mkSurface(theme, 'modern')} frame={frame} dur={dur} box={{w: W, h: H}} />
      </AbsoluteFill>
    );
  }
  if (g.template !== 'card' && g.template !== 'chapter' && (g.skin ?? (skin === 'paper' ? 'paper' : 'classic')) === 'paper') {
    return <PaperGraphic g={g} Comp={Comp} frame={frame} dur={dur} fps={fps} theme={theme} brand={brand}
      episode={episode} W={W} H={H} panelSide={panelSide} chapterTag={chapterTag} faceX={faceX}
      paperTexture={paperTexture} />;
  }
  if (g.template === 'title') {
    const ident = Math.min(dur, Math.round(IDENT_SEC * fps));
    return frame < ident ? <ModernTitle data={g.data} theme={theme} W={W} H={H} brand={brand} episode={episode} frame={frame} dur={ident} fps={fps} /> : null;
  }
  if (g.template === 'chapter') {
    if (g.layout === 'fullscreen') return <><ModernChapter data={g.data} theme={theme} W={W} H={H} frame={frame} /><CornerCredit text={g.data.credit || ''} tall={H > W} /></>;
    // 화자 위 챕터 = 좌상단 논증 배지
    return <ChapterBadge title={g.data.title || ''} frame={frame} dur={dur} />;
  }
  const specBg = g.template === 'motion' ? g.data.spec?.bg : undefined;
  const s = mkSurface(theme, surfaceForSpecBg(specBg) ?? surfaceFor(g.template, g.layout));
  const common = {id: g.id, data: g.data, fps, theme, brand, episode, layout: g.layout, surface: s, faceX};

  if (SLOT_TEMPLATES.has(g.template)) return <Comp {...common} frame={frame} dur={dur} box={{w: W, h: H}} />;
  const concept = CONCEPT_TEMPLATES.has(g.template);
  const onHost = concept ? g.layout !== 'fullscreen' : g.layout === 'pip' || g.layout === 'overlay';
  if (onHost) {
    // 짧은 키워드가 머리 위 자리(pip.side top)를 받으면 우상단 '한 줄 정리' 메모
    if (g.pip?.side === 'top' && g.template === 'keyword') {
      return <TopicMemo title={g.data.title || ''} frame={frame} dur={dur} label="한 줄 정리" />;
    }
    if (concept) return <Comp {...common} layout="overlay" frame={frame} dur={dur} box={{w: W, h: H}} />;
    if (g.template === 'photo' || g.template === 'broll') return <ModernPlate g={g} frame={frame} W={W} faceX={faceX} />;
  }
  if (g.layout === 'split') {
    return <ModernPanel g={g} Comp={Comp} frame={frame} dur={dur} fps={fps} theme={theme} brand={brand} episode={episode}
      W={W} H={H} panelSide={panelSide} />;
  }
  if (g.layout === 'overlay') {
    // 도식·목록을 화자 위에: 큰 양피지 한 장을 놓고 그 위에 그린다(연필 선은 종이 위에서만 읽힌다)
    const m = GRID.margin + 24;
    const box = {w: W - m * 2, h: H - 80 - 190};
    return (
      <AbsoluteFill>
        <Sheet x={m - 44} y={38} w={box.w + 88} h={box.h + 74} tex="parchment" seed={hashSeed(g.id)} rotate={-0.5} liftLevel={3} />
        <div style={{position: 'absolute', left: m, top: 80, width: box.w, height: box.h}}>
          <Comp {...common} surface={mkSurface(theme, 'modern')} frame={frame} dur={dur} box={box} />
        </div>
        <CornerCredit text={g.data.credit || ''} />
      </AbsoluteFill>
    );
  }

  // fullscreen — 사진·스톡·카드는 자기 면 전체, 도식은 평면 + 여백(아래 170px 는 자막 자리)
  const noPad = g.template === 'photo' || g.template === 'broll' || g.template === 'card';
  const m = noPad ? 0 : GRID.margin + 24;
  const top = noPad ? 0 : 72;
  const box = {w: W - m * 2, h: H - top - (noPad ? 0 : 170)};
  const credit = g.data.credit || g.data.source || '';
  return (
    <AbsoluteFill>
      {noPad ? null : <ModernStage dark={s.name === 'dark'} seed={hashSeed(g.id)} />}
      <div style={{position: 'absolute', left: m, top, width: box.w, height: box.h}}>
        <Comp {...common} frame={frame} dur={dur} box={box} />
      </div>
      {credit && !noPad ? <CornerCredit text={credit} tall={box.h > box.w} /> : null}
    </AbsoluteFill>
  );
};
