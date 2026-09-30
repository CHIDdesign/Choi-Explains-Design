import React from 'react';
import {interpolate} from 'remotion';
import {DUR, springIn, tweenOut} from '../../design/motion';
import {FONT} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {fitSize} from '../../lib/fit';
import type {Callout, FaceSample} from '../../lib/types';
import {AccentText, LabelTag, PAPER} from '../paper/Paper';

/**
 * 키워드 콜아웃 — 셜록현준 롱폼의 강조 방식(자막과 별도 레이어).
 * 화자 반대편, 얼굴(머리 폭 + 여유)을 피한 빈 공간에 굵은 2줄, 핵심어 하나만 강조색, 위에 맥락 라벨. 자리가 없으면 띄우지 않는다.
 * paper(롱폼은 두 스킨 모두 이것): 레퍼런스 3 — 검정 라벨 + 굵은 흰 글씨(그림자), 부드러운 스프링으로 떠오른다.
 * 그 밖: 예전 스타일(강조색 라벨 + 스프링 팝). 퇴장은 페이드.
 */
export const CalloutLayer: React.FC<{items: Callout[]; t: number; fps: number; W: number; H: number; theme: Theme;
  paper?: boolean; face?: FaceSample; zoom?: number}> = ({items, t, fps, W, H, theme, paper, face, zoom = 1}) => {
  const c = items.find((x) => t >= x.start && t < x.end);
  if (!c) return null;
  const f = (t - c.start) * fps;
  const remain = (c.end - t) * fps;
  const pop = springIn(f, fps, 0, paper ? 'gentle' : 'stiff');
  const out = tweenOut(-remain, 0, DUR.fast, 'inCubic');
  const lines = c.text.split('\n').filter(Boolean).slice(0, 2);
  // 얼굴(머리 폭 + 여유)을 피한 빈 공간 안에만 둔다 — 예전엔 화면 55% 지점 고정이라 얼굴 위로 겹쳤다
  const faceHalf = face ? face.s * H * 0.8 * zoom * 1.1 + 50 : 0;
  const margin = 70;
  let left = c.side === 'right' ? W * 0.55 : margin;
  let boxW = W * 0.4;
  if (face) {
    if (c.side === 'right') {
      left = Math.max(W * 0.5, face.x * W + faceHalf);
      boxW = W - margin - left;
    } else {
      boxW = Math.min(W * 0.45, face.x * W - faceHalf - margin);
    }
  }
  if (boxW < W * 0.2) return null; // 자리가 없으면 띄우지 않는다(얼굴 위 글씨 금지)
  const size = Math.min(paper ? 96 : 92, ...lines.map((l) => fitSize(l, boxW, paper ? 96 : 92, 48, -0.03)));
  if (paper) {
    // 레퍼런스 3: 검정 라벨 + 굵은 흰 글씨(그림자), 핵심어 하나만 주황. 천천히 떠오른다.
    const k = interpolate(pop, [0, 1], [0, 1], {extrapolateRight: 'clamp'});
    return (
      <div style={{position: 'absolute', left, top: H * 0.28, width: boxW, display: 'flex', flexDirection: 'column',
        alignItems: c.side === 'right' ? 'flex-start' : 'flex-end', opacity: k * out,
        translate: `0 ${interpolate(k, [0, 1], [22, 0])}px`}}>
        {c.label ? <div style={{marginBottom: 14}}><LabelTag text={c.label} variant="black" size={30} /></div> : null}
        {lines.map((l, i) => (
          <div key={i} style={{fontFamily: FONT.display, fontWeight: 900, fontSize: size, lineHeight: 1.12,
            letterSpacing: '-0.04em', color: PAPER.white, whiteSpace: 'nowrap',
            textAlign: c.side === 'right' ? 'left' : 'right',
            textShadow: '0 3px 0 rgba(0,0,0,0.55), 0 10px 30px rgba(0,0,0,0.55)'}}>
            <AccentText text={l} accent={c.highlight ? (l.includes(c.highlight) ? c.highlight : null)
              : i === lines.length - 1 ? undefined : null} />
          </div>
        ))}
      </div>
    );
  }
  const renderLine = (l: string) => {
    if (!c.highlight || !l.includes(c.highlight)) return l;
    const [a, ...rest] = l.split(c.highlight);
    return (
      <>
        {a}
        <span style={{color: theme.accentLight}}>{c.highlight}</span>
        {rest.join(c.highlight)}
      </>
    );
  };
  return (
    <div style={{position: 'absolute', left, top: H * 0.3, width: boxW, display: 'flex', flexDirection: 'column',
      alignItems: c.side === 'right' ? 'flex-start' : 'flex-end', opacity: Math.min(1, pop * 1.4) * out,
      scale: `${interpolate(pop, [0, 1], [0.9, 1])}`, transformOrigin: c.side === 'right' ? '0% 50%' : '100% 50%'}}>
      {c.label ? (
        <div style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: 26, color: '#111', background: theme.accent,
          padding: '4px 12px 5px', marginBottom: 14, letterSpacing: '-0.01em'}}>
          {c.label}
        </div>
      ) : null}
      {lines.map((l, i) => (
        <div key={i} style={{fontFamily: FONT.display, fontWeight: 800, fontSize: size, lineHeight: 1.14,
          letterSpacing: '-0.035em', color: '#fff', whiteSpace: 'nowrap', paintOrder: 'stroke fill',
          WebkitTextStroke: '8px rgba(10,10,10,0.9)', textShadow: '0 6px 28px rgba(0,0,0,0.45)',
          textAlign: c.side === 'right' ? 'left' : 'right'}}>
          {renderLine(l)}
        </div>
      ))}
    </div>
  );
};
