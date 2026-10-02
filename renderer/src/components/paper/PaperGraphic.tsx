import React from 'react';
import {interpolate} from 'remotion';
import {DUR, tween, tweenOut} from '../../design/motion';
import {surface as mkSurface, TEMPLATE_LABEL} from '../../design/surfaces';
import type {Theme} from '../../design/tokens';
import {FONT} from '../../design/tokens';
import type {Brand, Episode, Graphic} from '../../lib/types';
import type {TemplateProps} from '../graphics/common';
import {ConceptCard, conceptText, DisplayText, FramedMedia, pipBoxes} from './Collage';
import {hashSeed, LabelTag, PAPER, PaperBg, RoughBorder, SourceCredit} from './Paper';
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

  const ref = referenceGraphic({g, frame, dur, W, H, panelSide, chapterTag, faceX, brand, episode, theme, paperTexture});
  if (ref) return ref;

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

export type RefArgs = {g: Graphic; frame: number; dur: number; W: number; H: number; panelSide: 'left' | 'right';
  chapterTag: string; faceX: number; brand: Brand; episode: Episode; theme: Theme; paperTexture?: string};

/**
 * 사용자 레퍼런스에서 가져온 부분 — 기본(classic) 스타일에도 그대로 쓰인다.
 *  · 얼굴 위 사진·스톡: 찢어진 흰 액자 + 검정 라벨 + 큰 개념 텍스트(레퍼런스 3), 화자는 그대로
 *  · 얼굴 옆 키워드·정의·숫자·인용: 개념 텍스트(레퍼런스 3, 종이 챕터)
 *  · 타이틀: 왼쪽 개념 카드(라벨 태그 → 주황 한 낱말 헤드라인 → 부제 → 회색 주석) + 오른쪽 화자 액자(레퍼런스 1)
 */
export const referenceGraphic = ({g, frame, dur, W, H, panelSide, chapterTag, faceX, brand, episode, theme,
  paperTexture}: RefArgs): React.ReactElement | null => {
  const seed = hashSeed(g.id);
  const media = g.template === 'photo' ? g.data.image : g.template === 'broll' ? g.data.src : undefined;
  const mediaKind = g.template === 'broll' ? g.data.kind : 'photo';
  const label = chapterTag || TEMPLATE_LABEL[g.template];
  if (g.layout === 'pip' || g.layout === 'overlay') {
    const {b, right, textX, textW} = pipBoxes(faceX, W, g.pip);
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
      // 얼굴 옆 개념 텍스트(레퍼런스 3): 검정 라벨 + 큰 굵은 흰 글씨 — 종이 챕터의 언어(classic 챕터는 longform/Plates)
      const {head, body, note} = conceptText(g.template, g.data);
      return (
        <DisplayText label={body || label} text={head} accent={g.data.accent} frame={frame} dur={dur} x={textX}
          y={b.y + 8} w={textW} align={right ? 'right' : 'left'} size={g.template === 'stat' ? 120 : 84} delay={2}
          note={note} />
      );
    }
  }
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
  return null;
};
