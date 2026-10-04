import React from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {EASE_IN_OUT, EASE_OUT, enter, exit} from '../../lib/anim';
import {surface as mkSurface, surfaceFor, surfaceForSpecBg, TEMPLATE_LABEL} from '../../design/surfaces';
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
import {EvidenceCard} from '../longform/Evidence';
import {MotionScene} from '../motion/MotionScene';
import {PaperStage} from '../press/Press';
import {HtmlCard} from '../card/HtmlCard';
import {PaperGraphic, textBoxFor} from '../paper/PaperGraphic';
import {RecapBoard} from '../longform/Board';
import {CONCEPT_TEMPLATES} from '../longform/Plates';
import {SourceCredit} from '../paper/Paper';
import {CornerLabels, ModernStage, modernColors, Pill} from '../modern/Modern';
import {ModernChapter, ModernTitle} from '../modern/Titles';
import {ModernPanel, ModernPlate} from '../modern/Panels';

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
  // 증거 자료는 자기 종이·창·캡션을 다 가진 전면 그래픽 — 스킨·레이아웃과 무관하게 화면 전체(03b 3절 EvidenceFrame)
  if (g.template === 'evidence') {
    const s0 = mkSurface(theme, 'modern');
    return (
      <AbsoluteFill>
        <Comp id={g.id} data={g.data} fps={fps} theme={theme} brand={brand} episode={episode} layout={g.layout}
          surface={s0} frame={frame} dur={dur} box={{w: W, h: H}} />
      </AbsoluteFill>
    );
  }
  // 자유 HTML 카드는 자기 배경·타이포를 다 가지고 있으니 스킨과 무관하게 아래 풀스크린/패널 경로로.
  // 챕터 카드는 길잡이 부품이라 영상 안에서 한 가지 모양(F-11, docs/upgrade/06) — 종이 챕터도 같은 카드
  if (g.template !== 'card' && g.template !== 'chapter' && (g.skin ?? (skin === 'paper' ? 'paper' : 'classic')) === 'paper') {
    return <PaperGraphic g={g} Comp={Comp} frame={frame} dur={dur} fps={fps} theme={theme} brand={brand}
      episode={episode} W={W} H={H} panelSide={panelSide} chapterTag={chapterTag} faceX={faceX}
      paperTexture={paperTexture} />;
  }
  // 타이틀은 두 스킨 공통 구도(글 왼쪽 + 화자 액자 오른쪽) — 디자인 v3: 크림 종이 무대 위 명조 타이틀
  if (g.template === 'title') {
    const tb = textBoxFor(panelSide);
    return (
      <AbsoluteFill>
        <ModernStage theme={theme} frame={frame} />
        <ModernTitle data={g.data} frame={frame} dur={dur} theme={theme} W={W} H={H} brand={brand} episode={episode}
          textW={tb.w} left={tb.x} />
      </AbsoluteFill>
    );
  }
  // 챕터 카드(길잡이 부품 — 한 가지 모양): 이탤릭 세리프 번호 + 송명 제목 + 목차
  if (g.template === 'chapter') {
    const choreoCh = Boolean((g.data as {__choreo?: boolean}).__choreo);   // 장면 안무가 들고 나기를 맡으면 페이드 없음
    return (
      <AbsoluteFill style={{opacity: choreoCh ? undefined : Math.min(enter(frame, 0, 8, EASE_OUT), exit(frame, dur, 10, EASE_IN_OUT))}}>
        <ModernChapter data={g.data} frame={frame} dur={dur} theme={theme} W={W} H={H} />
      </AbsoluteFill>
    );
  }
  const concept = CONCEPT_TEMPLATES.has(g.template);
  const media = g.template === 'photo' ? g.data.image : g.template === 'broll' ? g.data.src : undefined;
  const credit = g.data.credit || (g.template === 'quote' ? '' : g.data.source) || '';
  const specBg = g.template === 'motion' ? g.data.spec?.bg : undefined;
  const sName = surfaceForSpecBg(specBg) ?? surfaceFor(g.template, g.layout);
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
      // 디자인 v4: 화면 위 소제목은 알약 칩 하나(종이 소제목 바 대신)
      return (
        <div style={{position: 'absolute', left: '50%', top: 44, translate: '-50% 0', opacity: Math.min(pIn, pOut)}}>
          <Pill text={g.data.title || ''} c={modernColors(theme)} frame={frame} delay={0} size={30} icon="dot" />
        </div>
      );
    }
    if (media || concept) return <ModernPlate g={g} frame={frame} dur={dur} W={W} theme={theme} faceX={faceX} />;
  }

  // 보드 판(화자 판 옆 작업대 열)
  if (g.layout === 'split') {
    return <ModernPanel g={g} Comp={Comp} frame={frame} dur={dur} fps={fps} theme={theme} brand={brand} episode={episode}
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
  // 모션 장면은 '모션 그래픽만의 장면' — 리포트 페이지(러닝 헤더·출처 줄) 없이 화면 전체가 모션의 무대.
  // 얼굴은 나오지 않는다(채널 주인: 모션이 주인공인 장면은 모션만으로 충분하다). 아래 170px 는 자막 자리로 비운다
  const stage = g.template === 'motion';
  const m = GRID.margin + 24;
  const top = noHeader ? 0 : stage ? 72 : headerH + 64;
  const bottom = noHeader ? 0 : 170;
  const innerW = noHeader ? W : W - m * 2;
  const innerH = H - top - bottom;
  // 디자인 v3 종이 콜라주: 리포트 머리글·위에서 내려오는 쓸기 대신 종이 무대가 8프레임에 깔리고 내용이 올라온다
  const collage = s.name === 'collage';
  // 디자인 v4: 모던 무대(밝은/어두운) + 모서리 작은 라벨(챕터 이름 · 브랜드) — 러닝 헤더·쓸기 없음
  const modern = s.name === 'modern' || s.name === 'dark';
  // 전면 영상·사진·카드는 6프레임 디졸브로 들어온다(위에서 내려오는 쓸기는 들어오는 동안 뒤의 화자를 드러낸다)
  const fade = collage || modern || noHeader;
  // 장면 안무(LongForm 의 원형 열기·흩어지기·다이브)가 들고 나기를 맡으면 이 층의 페이드·쓸기는 끈다 — 두 장면이 반투명으로
  // 겹치는 순간이 없게(2026-10-04 채널 주인: '페이드되는 요소끼리 겹치는 것이 가장 싫다')
  const choreo = Boolean((g.data as {__choreo?: boolean}).__choreo);
  return (
    <AbsoluteFill style={{clipPath: fade || choreo ? undefined : clip, background: collage || modern ? undefined : s.bg,
      opacity: fade && !choreo ? Math.min(enter(frame, 0, collage || modern ? 8 : 6, EASE_OUT), pOut) : undefined}}>
      {collage ? <PaperStage theme={theme} frame={frame} /> : null}
      {modern && !noHeader ? <ModernStage theme={theme} frame={frame} dark={s.name === 'dark'} /> : null}
      {modern && !noHeader ? <CornerLabels frame={frame} W={W} H={H} c={modernColors(theme, s.name === 'dark')} tl={chapterTag}
        br={brand.name} /> : null}
      {!noHeader && !stage && !collage && !modern ? (
        <RunningHeader surface={s} frame={frame} width={W}
          cells={[brand.name, episode.title, brand.year, pageLabel || TEMPLATE_LABEL[g.template]]} />
      ) : null}
      <div style={{position: 'absolute', left: noHeader ? 0 : m, top, width: innerW, height: innerH,
        translate: noHeader ? undefined : `0 ${interpolate(pIn, [0, 1], [24, 0])}px`}}>
        <Comp {...common} frame={frame} dur={dur} box={{w: innerW, h: innerH}} />
      </div>
      {credit && !noHeader ? <SourceCredit text={credit} top={62} right={48} opacity={enter(frame, 8, 12)} /> : null}
    </AbsoluteFill>
  );
};
