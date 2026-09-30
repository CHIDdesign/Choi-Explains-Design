import React from 'react';
import {interpolate} from 'remotion';
import {DUR, LONG, tween} from '../../design/motion';
import type {Theme} from '../../design/tokens';
import {FONT} from '../../design/tokens';
import type {Chapter} from '../../lib/types';
import type {Rect} from '../TalkingHead';
import {pickAccent} from '../paper/Paper';

/**
 * 롱폼 무대(Stage) — 16:9 강의 화면의 그리드·부품(docs/롱폼_무대_디자인.md).
 * 숏폼(세로 스택·카드 교체)과 달리 가로로 나누고(화자 열 + 작업대 열) 요소가 같은 자리에 머문다.
 * 모션 시그니처: 바깥 가장자리에서 안으로 쓸어 들어오기 + 괘선 그리기 + 줄 마스크 슬라이드. 형광펜·드롭인·팝 없음.
 */
export const STAGE = {
  margin: 72,     // 좌우 여백(콜아웃·로어서드·스트립)
  top: 84,        // 플레이트·액자 상단 기준선
  speaker: 0.36,  // 화자 열 비율(보드가 열릴 때)
  edge: 40,       // 두 장의 판 바깥 여백
  cardTop: 84,    // 판 위 여백
  cardBottom: 150, // 판 아래 여백 — 자막 띠(bottom 70)가 판을 덮지 않게
  gap: 48,        // 화자 판 ↔ 보드 판
  radius: 22,
  pad: 56,        // 보드 안쪽 여백
  grid: 28,       // 보드 점 격자 간격
  stripTop: 30,
} as const;

/** 화자 판(보드가 열릴 때 화자가 들어가는 둥근 창). panelSide = 보드(글)가 놓이는 쪽 */
export const speakerCard = (panelSide: 'left' | 'right', W = 1920, H = 1080): Rect => {
  const col = Math.round(W * STAGE.speaker);
  const w = col - STAGE.edge * 2;
  const h = H - STAGE.cardTop - STAGE.cardBottom;
  return panelSide === 'right' ? {x: STAGE.edge, y: STAGE.cardTop, w, h}
    : {x: W - col + STAGE.edge, y: STAGE.cardTop, w, h};
};

/** 보드 판(작업대 열) */
export const boardCard = (panelSide: 'left' | 'right', W = 1920, H = 1080): Rect => {
  const col = Math.round(W * STAGE.speaker);
  const x0 = panelSide === 'right' ? col - STAGE.edge + STAGE.gap : STAGE.edge;
  const w = W - col - STAGE.gap;
  return {x: x0, y: STAGE.cardTop, w, h: H - STAGE.cardTop - STAGE.cardBottom};
};

/** 바깥 가장자리에서 안으로 쓸어 들어오는 clip-path(p 0→1). from = 요소가 붙어 있는 바깥쪽 */
export const wipeFrom = (p: number, from: 'left' | 'right' | 'top'): string => {
  const k = Math.max(0, Math.min(1, p));
  const r = ((1 - k) * 100).toFixed(2);
  if (from === 'right') return `inset(0 0 0 ${r}%)`;
  if (from === 'left') return `inset(0 ${r}% 0 0)`;
  return `inset(0 0 ${r}% 0)`;
};

/** 플레이트·보드 진입: 쓸어 들어옴 + 바깥쪽에서 살짝 밀려 들어옴 */
export const slideIn = (frame: number, dur: number, from: 'left' | 'right' | 'top', dist = 36): React.CSSProperties => {
  const p = tween(frame, 0, dur, 'outQuint');
  const d = interpolate(p, [0, 1], [dist, 0]);
  return {
    clipPath: wipeFrom(p, from),
    translate: from === 'right' ? `${d}px 0` : from === 'left' ? `${-d}px 0` : `0 ${-d}px`,
  };
};

/** 퇴장(진입의 75%): 페이드 + 바깥쪽으로 8px */
export const slideOut = (frame: number, total: number, from: 'left' | 'right' | 'top'): React.CSSProperties => {
  const p = interpolate(frame, [total - LONG.out, total], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const d = (1 - p) * 8;
  return {opacity: p, translate: from === 'right' ? `${d}px 0` : from === 'left' ? `${-d}px 0` : `0 ${-d}px`};
};

/** 강조색 라벨 칩(강조색 바탕 + 잉크 글씨) */
export const LabelChip: React.FC<{text: string; theme: Theme; size?: number; opacity?: number; dim?: boolean}> = ({
  text, theme, size = 20, opacity = 1, dim = false}) => (
  <span style={{display: 'inline-block', fontFamily: FONT.sans, fontWeight: 700, fontSize: size, lineHeight: 1.2,
    letterSpacing: '0.01em', whiteSpace: 'nowrap', color: dim ? 'rgba(255,255,255,0.72)' : '#111111',
    background: dim ? 'rgba(255,255,255,0.1)' : theme.accent, borderRadius: size * 0.22,
    padding: `${size * 0.18}px ${size * 0.5}px ${size * 0.22}px`, opacity}}>{text}</span>
);

/** 괘선이 왼→오로 그려짐(롱폼 시그니처) */
export const Rule: React.FC<{frame: number; delay?: number; color: string; thick?: number; width?: number | string}> = ({
  frame, delay = 0, color, thick = 1, width = '100%'}) => (
  <div style={{width, height: thick, background: color, transformOrigin: 'left center',
    scale: `${tween(frame, delay, LONG.rule, 'outQuint')} 1`}} />
);

/** 마스크 안에서 아래→위로 올라오는 줄(줄 스태거 3f) */
export const RiseLine: React.FC<{frame: number; delay: number; children: React.ReactNode; style?: React.CSSProperties;
  dur?: number}> = ({frame, delay, children, style, dur = LONG.line}) => {
  const p = tween(frame, delay, dur, 'outExpo');
  return (
    <div style={{overflow: 'hidden', paddingBottom: '0.1em', marginBottom: '-0.1em', ...style}}>
      <div style={{translate: `0 ${interpolate(p, [0, 1], [105, 0])}%`, opacity: interpolate(p, [0, 0.25, 1], [0, 1, 1])}}>
        {children}
      </div>
    </div>
  );
};

/**
 * 헤드라인 한 줄: 강조 낱말은 강조색 + 밑줄이 왼→오로 쓸린다(p 0→1). 숏폼의 형광펜과 다른 롱폼 주석 언어.
 * accent 가 null 이면 강조 없음, undefined 면 마지막 어절(조사 뗀 어간).
 */
export const Annotated: React.FC<{text: string; accent?: string | null; p: number; color: string; accentColor: string;
  thick?: string}> = ({text, accent, p, color, accentColor, thick = '0.07em'}) => {
  const a = pickAccent(text, accent);
  const i = a ? text.lastIndexOf(a) : -1;
  if (i < 0) return <span style={{color}}>{text}</span>;
  const k = Math.max(0, Math.min(1, p));
  return (
    <span style={{color}}>
      {text.slice(0, i)}
      <span style={{position: 'relative', display: 'inline-block', color: k > 0 ? accentColor : color}}>
        {a}
        <span style={{position: 'absolute', left: '-0.02em', right: '-0.02em', bottom: '-0.02em', height: thick,
          background: accentColor, borderRadius: 2, transformOrigin: 'left center', scale: `${k} 1`}} />
      </span>
      {text.slice(i + a.length)}
    </span>
  );
};

/** 보드 판의 희미한 점 격자(강의 노트 종이) */
export const DotGrid: React.FC<{color?: string; gap?: number; opacity?: number}> = ({color = 'rgba(241,236,221,0.16)',
  gap = STAGE.grid, opacity = 1}) => (
  <div style={{position: 'absolute', inset: 0, opacity, pointerEvents: 'none',
    backgroundImage: `radial-gradient(${color} 1.1px, transparent 1.3px)`, backgroundSize: `${gap}px ${gap}px`,
    backgroundPosition: '14px 14px',
    maskImage: 'radial-gradient(120% 100% at 50% 50%, #000 40%, rgba(0,0,0,0.35) 100%)',
    WebkitMaskImage: 'radial-gradient(120% 100% at 50% 50%, #000 40%, rgba(0,0,0,0.35) 100%)'}} />
);

/**
 * 상단 컨텍스트 스트립 — 시청자가 '지금 어디쯤인지' 늘 안다: `02` + 챕터 제목 + 챕터 눈금
 * (지난 챕터 흰 50% · 지금 챕터는 강조색이 진행률만큼 · 다음 18%). 전체화면·보드·타이틀·챕터 카드 동안은 호출한 쪽이 숨긴다.
 */
export const ContextStrip: React.FC<{chapters: Chapter[]; index: number; t: number; total: number; theme: Theme;
  opacity: number; x?: number; y?: number}> = ({chapters, index, t, total, theme, opacity, x = STAGE.margin,
  y = STAGE.stripTop}) => {
  if (index < 0 || opacity <= 0) return null;
  const c = chapters[index];
  const next = index + 1 < chapters.length ? chapters[index + 1].start : total;
  const prog = next > c.start ? Math.max(0, Math.min(1, (t - c.start) / (next - c.start))) : 1;
  const n = parseInt(c.number, 10);
  const tickW = 26;
  return (
    <div style={{position: 'absolute', left: x, top: y, display: 'flex', alignItems: 'center', gap: 14, opacity,
      textShadow: '0 1px 6px rgba(0,0,0,0.55)'}}>
      <span style={{fontFamily: FONT.latin, fontSize: 24, lineHeight: 1, color: theme.accentLight, letterSpacing: '0.02em'}}>
        {Number.isFinite(n) ? String(n).padStart(2, '0') : c.number}
      </span>
      <span style={{fontFamily: FONT.sans, fontWeight: 600, fontSize: 20, lineHeight: 1, color: 'rgba(255,255,255,0.9)',
        letterSpacing: '-0.01em', whiteSpace: 'nowrap'}}>{c.title}</span>
      {chapters.length > 1 ? (
        <span style={{display: 'flex', gap: 5, marginLeft: 6, alignItems: 'center'}}>
          {chapters.map((_, i) => (
            <span key={i} style={{position: 'relative', width: tickW, height: 3, borderRadius: 2,
              background: i < index ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.18)', overflow: 'hidden'}}>
              {i === index ? <span style={{position: 'absolute', left: 0, top: 0, bottom: 0, width: `${prog * 100}%`,
                background: theme.accentLight}} /> : null}
            </span>
          ))}
        </span>
      ) : null}
    </div>
  );
};

/** 스트립·플레이트 공통 페이드(챕터 시작 3.2초 뒤) */
export const stripOpacity = (frame: number, startFrame: number) => tween(frame, startFrame, DUR.normal) * 0.92;
