import React from 'react';
import {Img, interpolate, OffthreadVideo, staticFile} from 'remotion';
import {DUR, STAGGER, tween, tweenOut} from '../../design/motion';
import {FONT} from '../../design/tokens';
import {fitBlock, fitSize, wrap} from '../../lib/fit';
import type {GraphicData, PipPlacement, TemplateName} from '../../lib/types';
import {AccentText, LabelTag, PAPER, TornFrame} from './Paper';
import type {Box} from './Paper';

/** 부드러운 등장: 살짝 아래에서 떠오르며 선명해짐(교육 영상용 — 튀지 않게) */
const rise = (frame: number, delay: number, dist = 18, dur: number = DUR.slow): React.CSSProperties => {
  const p = tween(frame, delay, dur, 'outCubic');
  return {opacity: p, translate: `0 ${interpolate(p, [0, 1], [dist, 0])}px`};
};

/** 개념 카드가 담는 글(템플릿별로 헤드라인·본문·주석을 고른다) */
export const conceptText = (template: TemplateName, d: GraphicData): {
  head: string; body: string; note: string; big?: boolean; quote?: boolean;
} => {
  switch (template) {
    case 'definition':
      return {head: d.title || '', body: d.body || '', note: d.subtitle || d.source || ''};
    case 'quote':
      return {head: d.body ? `“${d.body}”` : d.title || '', body: '',
        note: [d.author, d.source].filter(Boolean).join(', '), quote: true};
    case 'stat':
      return {head: d.title || '', body: d.body || '', note: d.subtitle || d.source || '', big: true};
    case 'keyword':
    default:
      return {head: d.title || '', body: d.body || d.subtitle || '', note: d.source || ''};
  }
};

/**
 * 개념 카드(레퍼런스 1 왼쪽): 흰 라벨 태그 → 큰 헤드라인(한 낱말 주황) → 본문 → 회색 괄호 주석.
 * box 는 글이 들어갈 영역(1920 기준 약 x 150~1010).
 */
export const ConceptCard: React.FC<{template: TemplateName; data: GraphicData; label: string; frame: number;
  dur: number; box: Box; align?: 'left' | 'center'}> = ({template, data, label, frame, dur, box, align = 'left'}) => {
  const {head, body, note, big, quote} = conceptText(template, data);
  const out = tweenOut(frame, dur, 9);
  const maxHead = big ? 150 : quote ? 64 : 104;
  const {size, lines} = fitBlock(head, box.w, box.h * (body ? 0.42 : 0.6), maxHead, 44, 1.18, quote ? 4 : 2, -0.02);
  const bodyLines = body ? wrap(body, 30, box.w, 4) : [];
  return (
    <div style={{position: 'absolute', left: box.x, top: box.y, width: box.w, height: box.h, opacity: out,
      display: 'flex', flexDirection: 'column', alignItems: align === 'center' ? 'center' : 'flex-start',
      textAlign: align}}>
      {label ? <div style={rise(frame, 0, 12, DUR.normal)}><LabelTag text={label} /></div> : null}
      <div style={{marginTop: size * 0.34}}>
        {lines.map((l, i) => (
          <div key={i} style={{overflow: 'hidden', paddingBottom: '0.06em'}}>
            <div style={{fontFamily: quote ? FONT.serif : FONT.display, fontWeight: quote ? 500 : 400, fontSize: size,
              lineHeight: 1.18, letterSpacing: quote ? '-0.01em' : '-0.035em', whiteSpace: 'nowrap',
              ...rise(frame, 5 + i * STAGGER.line, size * 0.5, DUR.reveal)}}>
              {quote ? <span style={{color: PAPER.white}}>{l}</span> : <AccentText text={l} accent={
                lines.length > 1 && i < lines.length - 1 ? null : data.accent} />}
            </div>
          </div>
        ))}
      </div>
      {bodyLines.length ? (
        <div style={{marginTop: 26, fontFamily: FONT.sans, fontWeight: 400, fontSize: 30, lineHeight: 1.5,
          color: PAPER.body, letterSpacing: '-0.01em', ...rise(frame, 12, 12)}}>
          {bodyLines.map((l, i) => <div key={i}>{l}</div>)}
        </div>
      ) : null}
      {note ? (
        <div style={{marginTop: 20, fontFamily: FONT.sans, fontWeight: 400, fontSize: 23, color: PAPER.note,
          ...rise(frame, 16, 10)}}>( {note} )</div>
      ) : null}
    </div>
  );
};

/** 개념 텍스트(레퍼런스 3): 검정 라벨 + 큰 굵은 흰 글씨(그림자) — 얼굴 옆 빈 공간에 */
export const DisplayText: React.FC<{label?: string; text: string; accent?: string; frame: number; dur: number;
  x: number; y: number; w: number; align: 'left' | 'right'; size?: number; delay?: number; note?: string}> = ({label,
  text, accent, frame, dur, x, y, w, align, size = 84, delay = 0, note}) => {
  const lines = wrap(text, size, w, 2).slice(0, 2);
  const s = Math.min(size, ...lines.map((l) => fitSize(l, w, size, 44, -0.03)));
  const out = tweenOut(frame, dur, 9);
  return (
    <div style={{position: 'absolute', left: x, top: y, width: w, display: 'flex', flexDirection: 'column',
      alignItems: align === 'right' ? 'flex-end' : 'flex-start', opacity: out}}>
      {label ? <div style={{...rise(frame, delay, 10, DUR.normal), marginBottom: 12}}>
        <LabelTag text={label} variant="black" size={30} /></div> : null}
      {lines.map((l, i) => (
        <div key={i} style={{fontFamily: FONT.display, fontWeight: 900, fontSize: s, lineHeight: 1.12,
          letterSpacing: '-0.04em', color: PAPER.white, whiteSpace: 'nowrap', textAlign: align,
          textShadow: '0 3px 0 rgba(0,0,0,0.55), 0 10px 30px rgba(0,0,0,0.55)',
          ...rise(frame, delay + 4 + i * STAGGER.line, 20, DUR.slow)}}>
          <AccentText text={l} accent={i === lines.length - 1 ? accent : null} accentColor={PAPER.accent} />
        </div>
      ))}
      {note ? (
        <div style={{marginTop: 10, fontFamily: FONT.sans, fontWeight: 500, fontSize: 24, color: PAPER.white,
          opacity: 0.8, textShadow: '0 2px 8px rgba(0,0,0,0.6)', whiteSpace: 'nowrap',
          ...rise(frame, delay + 12, 10, DUR.normal)}}>( {note} )</div>
      ) : null}
    </div>
  );
};

/** 사진/스톡을 찢어진 액자에 넣어 띄운다(레퍼런스 3). 매우 느린 켄번즈. */
export const FramedMedia: React.FC<{src: string; kind?: 'video' | 'photo'; b: Box; frame: number; dur: number;
  seed: number; enterDelay?: number; rotate?: number}> = ({src, kind = 'photo', b, frame, dur, seed, enterDelay = 0,
  rotate = 0}) => {
  // 롱폼(종이 챕터): 살짝 아래에서 천천히 떠오른다(교육 영상용, 튀지 않게). 숏폼 카드의 드롭인은 ReelShort 가 따로 한다
  const p = tween(frame, enterDelay, DUR.slow, 'outCubic');
  const out = tweenOut(frame, dur, 10);
  const push = interpolate(frame, [0, Math.max(1, dur)], [1.0, 1.06]);
  const isVideo = kind === 'video' || /\.(mp4|webm|mov)$/i.test(src);
  return (
    <div style={{position: 'absolute', inset: 0, opacity: Math.min(p, out),
      translate: `0 ${interpolate(p, [0, 1], [18, 0])}px`}}>
      <TornFrame b={b} seed={seed} rotate={rotate}>
        {isVideo ? (
          <OffthreadVideo src={staticFile(src)} muted style={{width: '100%', height: '100%', objectFit: 'cover',
            scale: `${push}`}} />
        ) : (
          <Img src={staticFile(src)} style={{width: '100%', height: '100%', objectFit: 'cover', scale: `${push}`}} />
        )}
      </TornFrame>
    </div>
  );
};

/** 사진 PIP 배치: 얼굴 반대편 위쪽(레퍼런스 3: x 1150~1860, y 76~624).
 * pip(파이프라인이 얼굴 트랙으로 정한 빈 쪽·크기)이 있으면 그대로 — 얼굴을 덮지 않는다. 없으면 faceX 의 반대편. */
export const pipBoxes = (faceX: number, W = 1920, pip?: PipPlacement) => {
  const w = pip?.w ?? 700;
  const h = pip?.h ?? 520;
  const right = pip ? pip.side !== 'left' : faceX < 0.5;
  const b: Box = right ? {x: W - 60 - w, y: 84, w, h} : {x: 60, y: 84, w, h};
  const textW = Math.max(420, Math.min(760, w + 60));
  return {b, right, textX: right ? W - 60 - textW : 60, textW};
};
