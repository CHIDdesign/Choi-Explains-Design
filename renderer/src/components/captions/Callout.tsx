import React from 'react';
import {interpolate} from 'remotion';
import {DUR, LONG, springIn, tween, tweenOut} from '../../design/motion';
import {FONT} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {fitSize} from '../../lib/fit';
import type {Callout, FaceSample} from '../../lib/types';
import {Annotated, LabelChip, RiseLine, STAGE} from '../longform/Stage';
import {AccentText, LabelTag, PAPER} from '../paper/Paper';

/**
 * 키워드 콜아웃 — 셜록현준 롱폼의 강조 방식(자막과 별도 레이어).
 * 화자 반대편, 얼굴(머리 폭 + 여유)을 피한 빈 공간에 굵은 2줄, 핵심어 하나만 강조색, 위에 맥락 라벨. 자리가 없으면 띄우지 않는다.
 *  classic(롱폼 무대): 강조색 칩 라벨 + 굵은 흰 글씨, 핵심어는 강조색 + **밑줄 스윕**(주석 언어), 줄 마스크 슬라이드
 *  paper(사용자 템플릿, 레퍼런스 3): 검정 라벨 + 굵은 흰 글씨(그림자), 핵심어 주황, 부드럽게 떠오른다
 * 형광펜·팝은 숏폼 언어라 쓰지 않는다. 퇴장은 페이드.
 */
export const CalloutLayer: React.FC<{items: Callout[]; t: number; fps: number; W: number; H: number; theme: Theme;
  look?: 'paper' | 'classic'; face?: FaceSample; zoom?: number}> = ({items, t, fps, W, H, theme, look = 'classic', face,
  zoom = 1}) => {
  const c = items.find((x) => t >= x.start && t < x.end);
  if (!c) return null;
  const f = (t - c.start) * fps;
  const remain = (c.end - t) * fps;
  const out = tweenOut(-remain, 0, DUR.fast, 'inCubic');
  const lines = c.text.split('\n').filter(Boolean).slice(0, 2);
  // 얼굴(머리 폭 + 여유)을 피한 빈 공간 안에만 둔다 — 예전엔 화면 55% 지점 고정이라 얼굴 위로 겹쳤다
  const faceHalf = face ? face.s * H * 0.8 * zoom * 1.1 + 50 : 0;
  const margin = STAGE.margin;
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
  const size = Math.min(96, ...lines.map((l) => fitSize(l, boxW, 96, 48, -0.03)));
  const accentOf = (l: string, i: number) => c.highlight ? (l.includes(c.highlight) ? c.highlight : null)
    : i === lines.length - 1 ? undefined : null;
  if (look === 'paper') {
    const pop = springIn(f, fps, 0, 'gentle');
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
            <AccentText text={l} accent={accentOf(l, i)} accentColor={PAPER.accent} />
          </div>
        ))}
      </div>
    );
  }
  // classic: 롱폼 무대의 주석 — 칩 라벨 + 줄 마스크 슬라이드 + 핵심어 밑줄 스윕
  return (
    <div style={{position: 'absolute', left, top: H * 0.28, width: boxW, display: 'flex', flexDirection: 'column',
      alignItems: c.side === 'right' ? 'flex-start' : 'flex-end', opacity: out}}>
      {c.label ? <div style={{marginBottom: 16, opacity: tween(f, 0, 8)}}>
        <LabelChip text={c.label} theme={theme} size={24} /></div> : null}
      {lines.map((l, i) => (
        <RiseLine key={i} frame={f} delay={2 + i * 3} dur={LONG.underline}>
          <div style={{fontFamily: FONT.display, fontWeight: 900, fontSize: size, lineHeight: 1.12,
            letterSpacing: '-0.04em', whiteSpace: 'nowrap', textAlign: c.side === 'right' ? 'left' : 'right',
            textShadow: '0 2px 2px rgba(0,0,0,0.5), 0 10px 30px rgba(0,0,0,0.55)'}}>
            <Annotated text={l} accent={accentOf(l, i)} p={tween(f, 12 + i * 3, LONG.underline, 'outQuint')}
              color="#FFFFFF" accentColor={theme.accentLight} thick="0.065em" />
          </div>
        </RiseLine>
      ))}
    </div>
  );
};
