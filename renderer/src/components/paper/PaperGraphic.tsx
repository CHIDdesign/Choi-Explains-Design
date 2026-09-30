import React from 'react';
import {interpolate} from 'remotion';
import {DUR, tween, tweenOut} from '../../design/motion';
import {surface as mkSurface, TEMPLATE_LABEL} from '../../design/surfaces';
import type {Theme} from '../../design/tokens';
import {FONT} from '../../design/tokens';
import {fitBlock} from '../../lib/fit';
import type {Brand, Episode, Graphic} from '../../lib/types';
import type {TemplateProps} from '../graphics/common';
import {ConceptCard, conceptText, DisplayText, FramedMedia, pipBoxes} from './Collage';
import {AccentText, hashSeed, LabelTag, PAPER, PaperBg, RoughBorder, SourceCredit} from './Paper';
import type {Box} from './Paper';

const CONCEPT = new Set(['keyword', 'definition', 'quote', 'stat']);

/** 종이 스킨에서 화자 액자 위치(레퍼런스 1: 글은 왼쪽, 화자 액자는 오른쪽 위) — panelSide = 글이 놓이는 쪽 */
export const paperSpeakerBox = (panelSide: 'left' | 'right', W = 1920): Box =>
  panelSide === 'left' ? PAPER.speaker : {...PAPER.speaker, x: W - PAPER.speaker.x - PAPER.speaker.w};

const textBoxFor = (panelSide: 'left' | 'right'): Box =>
  panelSide === 'left' ? {x: 156, y: 222, w: 860, h: 740} : {x: 904, y: 222, w: 860, h: 740};

type Props = {
  g: Graphic;
  Comp: React.FC<TemplateProps>;
  frame: number;
  dur: number;
  fps: number;
  theme: Theme;
  brand: Brand;
  episode: Episode;
  W: number;
  H: number;
  panelSide: 'left' | 'right';
  chapterTag: string; // "1. 챕터 제목"
  faceX: number; // 그래픽이 뜨는 순간 얼굴 가로 위치(0~1)
  paperTexture?: string;
};

/** 종이 콜라주 스킨의 그래픽 배치 */
export const PaperGraphic: React.FC<Props> = ({g, Comp, frame, dur, fps, theme, brand, episode, W, H, panelSide,
  chapterTag, faceX, paperTexture}) => {
  const s = mkSurface(theme, 'crumple');
  const common = {id: g.id, data: g.data, fps, theme, brand, episode, layout: g.layout, surface: s};
  const seed = hashSeed(g.id);
  const media = g.template === 'photo' ? g.data.image : g.template === 'broll' ? g.data.src : undefined;
  const mediaKind = g.template === 'broll' ? g.data.kind : 'photo';
  const credit = g.data.credit || (g.template === 'quote' ? '' : g.data.source) || '';
  const label = chapterTag || TEMPLATE_LABEL[g.template];

  if (g.template === 'lower_third') {
    return <Comp {...common} frame={frame} dur={dur} box={{w: W, h: H}} />;
  }

  // ---- 얼굴 위에 띄우기(레퍼런스 3): 사진은 찢어진 액자 + 검정 라벨 + 큰 개념 텍스트, 글은 개념 텍스트만 ----
  if (g.layout === 'pip' || g.layout === 'overlay') {
    const {b, right, textX, textW} = pipBoxes(faceX, W);
    if (media) {
      return (
        <>
          <FramedMedia src={media} kind={mediaKind} b={b} frame={frame} dur={dur} seed={seed} />
          <DisplayText label={g.data.body || ''} text={g.data.title || ''} accent={g.data.accent} frame={frame}
            dur={dur} x={textX} y={b.y + b.h + 20} w={textW} align={right ? 'right' : 'left'} size={76} delay={6} />
          {g.data.credit ? <SourceCredit text={g.data.credit} opacity={tween(frame, 8, 12)} top={34}
            right={right ? 60 : W - 60 - b.w} /> : null}
        </>
      );
    }
    if (CONCEPT.has(g.template)) {
      const {head, body} = conceptText(g.template, g.data);
      return (
        <DisplayText label={body || label} text={head} accent={g.data.accent} frame={frame} dur={dur} x={textX}
          y={H * 0.26} w={textW} align={right ? 'right' : 'left'} size={g.template === 'stat' ? 150 : 96} />
      );
    }
  }

  // ---- 타이틀: 화자는 액자에(LongForm), 왼쪽에 에피소드 개념 카드 ----
  if (g.template === 'title') {
    const box = textBoxFor(panelSide);
    const tag = [episode.number ? `EP. ${episode.number}` : '', episode.series].filter(Boolean).join(' · ');
    return (
      <>
        <ConceptCard template="keyword" frame={frame} dur={dur} box={box} label={tag || brand.name}
          data={{...g.data, title: g.data.title || episode.title, body: episode.subtitle || g.data.subtitle || '',
            source: [brand.presenter, brand.presenterTitle].filter(Boolean).join(' · ')}} />
        <SourceCredit text={brand.name} raw opacity={tween(frame, 8, 12) * tweenOut(frame, dur, 9)} />
      </>
    );
  }

  // ---- 화자 액자 + 글(레퍼런스 1) ----
  if (g.layout === 'split') {
    const box = textBoxFor(panelSide);
    if (CONCEPT.has(g.template)) {
      return <ConceptCard template={g.template} data={g.data} label={label} frame={frame} dur={dur} box={box} />;
    }
    const out = tweenOut(frame, dur, 9);
    if (media) {
      const mb: Box = {x: box.x, y: box.y + 84, w: box.w, h: Math.round(box.w * 0.62)};
      return (
        <div style={{position: 'absolute', inset: 0, opacity: out}}>
          <div style={{position: 'absolute', left: box.x, top: box.y, opacity: tween(frame, 0, DUR.normal)}}>
            <LabelTag text={g.data.title || label} />
          </div>
          <FramedMedia src={media} kind={mediaKind} b={mb} frame={frame} dur={dur} seed={seed} enterDelay={4} />
          {g.data.body ? (
            <div style={{position: 'absolute', left: box.x, top: mb.y + mb.h + 34, width: box.w, fontFamily: FONT.sans,
              fontSize: 28, color: PAPER.body, opacity: tween(frame, 12, 12)}}>{g.data.body}</div>
          ) : null}
        </div>
      );
    }
    return (
      <div style={{position: 'absolute', inset: 0, opacity: out}}>
        <div style={{position: 'absolute', left: box.x, top: box.y, opacity: tween(frame, 0, DUR.normal)}}>
          <LabelTag text={label} />
        </div>
        <div style={{position: 'absolute', left: box.x, top: box.y + 96, width: box.w, height: box.h - 96,
          opacity: tween(frame, 3, DUR.slow), translate: `0 ${interpolate(tween(frame, 3, DUR.slow), [0, 1], [16, 0])}px`}}>
          <Comp {...common} frame={frame} dur={dur} box={{w: box.w, h: box.h - 96}} />
        </div>
      </div>
    );
  }

  // ---- 전면(종이 한 장) ----
  const pIn = tween(frame, 0, DUR.slow, 'outCubic');
  const pOut = tweenOut(frame, dur, 10);
  const page = (children: React.ReactNode, border = true) => (
    <div style={{position: 'absolute', inset: 0, opacity: Math.min(pIn, pOut)}}>
      <PaperBg src={paperTexture} />
      {border ? <RoughBorder seed={seed % 7 + 1} /> : null}
      {children}
      <SourceCredit text={credit} opacity={tween(frame, 8, 12)} />
    </div>
  );

  if (media) {
    const b: Box = {x: 120, y: 112, w: W - 240, h: H - 250};
    return page(
      <>
        <FramedMedia src={media} kind={mediaKind} b={b} frame={frame} dur={dur} seed={seed} />
        {g.data.title ? (
          <div style={{position: 'absolute', left: b.x - 22, top: b.y + b.h - 18, opacity: tween(frame, 8, 12)}}>
            <LabelTag text={g.data.body ? `${g.data.title} · ${g.data.body}` : g.data.title} variant="black" />
          </div>
        ) : null}
      </>, false);
  }

  if (g.template === 'chapter') {
    const title = g.data.title || '';
    const {size, lines} = fitBlock(title, W * 0.72, H * 0.4, 150, 80, 1.12, 2, -0.03);
    return page(
      <div style={{position: 'absolute', left: 156, top: H * 0.3}}>
        <div style={{opacity: tween(frame, 2, DUR.normal)}}>
          <LabelTag text={g.data.number ? `CHAPTER ${g.data.number}` : 'CHAPTER'} />
        </div>
        <div style={{marginTop: 34}}>
          {lines.map((l, i) => (
            <div key={i} style={{overflow: 'hidden'}}>
              <div style={{fontFamily: FONT.display, fontWeight: 400, fontSize: size, lineHeight: 1.12,
                letterSpacing: '-0.04em', whiteSpace: 'nowrap',
                translate: `0 ${interpolate(tween(frame, 6 + i * 3, DUR.reveal, 'outExpo'), [0, 1], [100, 0])}%`}}>
                <AccentText text={l} accent={i === lines.length - 1 ? g.data.accent : null} />
              </div>
            </div>
          ))}
        </div>
        {g.data.subtitle ? (
          <div style={{marginTop: 24, fontFamily: FONT.sans, fontSize: 32, color: PAPER.body,
            opacity: tween(frame, 14, 12)}}>{g.data.subtitle}</div>
        ) : null}
      </div>);
  }

  if (CONCEPT.has(g.template)) {
    return page(<ConceptCard template={g.template} data={g.data} label={label} frame={frame} dur={dur}
      box={{x: 156, y: 230, w: W - 312, h: H - 380}} />);
  }

  // 도식·목록·모션: 흰 라벨 태그 + 템플릿(종이 표면)
  const inner: Box = {x: 156, y: 236, w: W - 312, h: H - 236 - 150};
  return page(
    <>
      <div style={{position: 'absolute', left: inner.x, top: 150, opacity: tween(frame, 2, DUR.normal)}}>
        <LabelTag text={label} />
      </div>
      <div style={{position: 'absolute', left: inner.x, top: inner.y, width: inner.w, height: inner.h,
        translate: `0 ${interpolate(pIn, [0, 1], [18, 0])}px`}}>
        <Comp {...common} frame={frame} dur={dur} box={{w: inner.w, h: inner.h}} />
      </div>
    </>);
};
