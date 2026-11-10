import React from 'react';
import type {Rect} from '../TalkingHead';
import {pickAccent} from '../paper/Paper';

/** 롱폼 칸 나누기와 글 부품(분할은 비교할 때만, docs/디자인_v5_토크쇼.md) */
export const STAGE = {
  margin: 72,     // 좌우 여백(콜아웃)
  speaker: 0.42,  // 화자 칸 비율(분할 때)
} as const;

/** 화자 칸(분할 때). panelSide = 보드(글)가 놓이는 쪽. 맞붙은 두 칸 — 여백·둥근 판 없음 */
export const speakerCard = (panelSide: 'left' | 'right', W = 1920, H = 1080): Rect => {
  const w = Math.round(W * STAGE.speaker);
  return panelSide === 'right' ? {x: 0, y: 0, w, h: H} : {x: W - w, y: 0, w, h: H};
};

/** 보드 칸 */
export const boardCard = (panelSide: 'left' | 'right', W = 1920, H = 1080): Rect => {
  const w = Math.round(W * STAGE.speaker);
  return {x: panelSide === 'right' ? w : 0, y: 0, w: W - w, h: H};
};

/** 글 한 줄: 강조 낱말 아래에 오렌지 형광 밑줄이 왼→오로 쓸린다(p 0→1). accent 가 null 이면 없음, undefined 면 마지막 어절 */
export const Annotated: React.FC<{text: string; accent?: string | null; p: number; color: string; underline: string}> = ({text, accent, p,
  color, underline}) => {
  const a = pickAccent(text, accent);
  const i = a ? text.lastIndexOf(a) : -1;
  if (i < 0) return <span style={{color}}>{text}</span>;
  return (
    <span style={{color}}>
      {text.slice(0, i)}
      <span style={{position: 'relative', display: 'inline-block'}}>
        {a}
        <span style={{position: 'absolute', left: '-0.02em', right: '-0.02em', bottom: '-0.04em', height: '0.08em', background: underline,
          transformOrigin: 'left center', scale: `${Math.max(0, Math.min(1, p))} 1`}} />
      </span>
      {text.slice(i + a.length)}
    </span>
  );
};
