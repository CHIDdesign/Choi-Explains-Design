import React, {useMemo} from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {EASE} from '../../design/motion';
import {lift, liftDrop, MAT} from '../../design/tokens';
import type {LiftOn} from '../../design/tokens';
import {EXPAND_SEC, expandRect} from '../../lib/crop';
import type {Pt} from '../../lib/crop';
import {tornPaths} from '../../../vendor/hyperframes/card-anim.mjs';
import {seeded} from '../paper/Paper';
import {texFill, useMaterials} from './Texture';
import type {TexName} from './Texture';

export type Edges = {top?: boolean; right?: boolean; bottom?: boolean; left?: boolean};
export {tornPaths};

/** 시드로 한 변을 찢는다(네 변이 레이저로 자른 직사각형이면 종이 채움을 넣은 PPT 도형이다). seed + i·5 로 부르면 이웃한 카드는 서로 다른 변 */
export const tornFor = (seed: number): Edges => ({[(['top', 'right', 'bottom', 'left'] as const)[Math.floor(Math.abs(seed)) % 4]]: true});

/** 모서리 하나가 2~3px 들렸다(시드로 어느 쪽인지): 그쪽만 그림자가 벌어진다. 위 왼쪽 모서리는 빛 쪽이라 그림자가 안 생긴다 */
const CornerLift: React.FC<{level: number; seed: number; rgb: string}> = ({level, seed, rgb}) => {
  const r = seeded(seed + 0.83);
  const a = (0.2 + 0.08 * level).toFixed(2);
  const pick = Math.floor(r() * 3);
  const up = 2 + r();
  const style: React.CSSProperties = pick === 2
    ? {right: 8, top: 10, width: 22, height: '42%', rotate: '1.4deg', boxShadow: `${up + 3 * level}px ${up + 2 * level}px ${10 + 4 * level}px rgba(${rgb},${a})`}
    : {[pick ? 'right' : 'left']: 10, bottom: 8, width: '42%', height: 24, rotate: `${pick ? 1.5 : -1.5}deg`, boxShadow: `0 ${up + 4 * level}px ${10 + 4 * level}px rgba(${rgb},${a})`};
  return <div style={{position: 'absolute', ...style}} />;
};

/**
 * 종이 한 장. 접촉 그림자 + 넓은 부드러운 그림자로 들떠 있고, torn 을 주면 그 변이 찢겨 흰 섬유 단면이 보인다. 글자는 children — 재질 층 위에 놓인다.
 * m: paperSettle 결과(놓이는 움직임). 없으면 rotate·liftLevel 그대로.
 */
export const Sheet: React.FC<{x?: number; y?: number; w: number; h: number; tex?: TexName; seed?: number; rotate?: number; liftLevel?: number;
  torn?: Edges; amp?: number; fibre?: number; m?: {opacity: number; rotate: number; y: number; scale: number; elev: number}; origin?: string; on?: LiftOn;
  style?: React.CSSProperties; children?: React.ReactNode}> = ({x = 0, y = 0, w, h, tex = 'memo', seed = 1, rotate = 0, liftLevel = 2, torn,
  amp = 11, fibre, m, origin, on = 'photo', style, children}) => {
  useMaterials();
  const paths = useMemo(() => (torn ? tornPaths(w, h, torn, seed, amp, fibre) : null), [w, h, torn?.top, torn?.right, torn?.bottom, torn?.left, seed, amp, fibre]);
  const level = m?.elev ?? liftLevel;
  const k = 0.7 + seeded(seed + 0.19)() * 0.6;
  return (
    <div style={{position: 'absolute', left: x, top: y, width: w, height: h, rotate: `${m?.rotate ?? rotate}deg`, opacity: m?.opacity ?? 1,
      translate: m ? `0 ${m.y}px` : undefined, scale: m ? `${m.scale}` : undefined, transformOrigin: origin,
      filter: paths ? liftDrop(level, k, on) : undefined, ...style}}>
      {on === 'dark' ? null : <CornerLift level={level} seed={seed} rgb={on === 'board' ? '60,50,35' : '0,0,0'} />}
      {paths ? <div style={{position: 'absolute', inset: 0, ...texFill('memo', seed + 2, w, h), backgroundColor: MAT.fibre, backgroundBlendMode: 'multiply', clipPath: `path('${paths.outer}')`}} /> : null}
      {paths ? <div style={{position: 'absolute', inset: 0, ...texFill(tex, seed, w, h), clipPath: `path('${paths.mid}')`, opacity: 0.45}} /> : null}
      <div style={{position: 'absolute', inset: 0, ...texFill(tex, seed, w, h), clipPath: paths ? `path('${paths.inner}')` : undefined,
        boxShadow: paths ? undefined : lift(level, k, on)}} />
      {children}
    </div>
  );
};

/**
 * 조각이 화면이 되는 전환: 다음 전면 그래픽이 종이 테두리를 두른 작은 인화지로 앞 장면 위에 놓였다가 화면 전체로 펼쳐진다.
 * 앞 장면은 그 밑에 멈춰 있고(LongForm), 다음 장면은 제 시각에 시작한다 — 타임라인 길이는 그대로.
 */
export const PieceExpand: React.FC<{frame: number; fps: number; W: number; H: number; at: Pt; seed: number; children: React.ReactNode}> = ({frame, fps, W, H, at, seed, children}) => {
  useMaterials();
  const n = Math.round(EXPAND_SEC * fps);
  const on = frame < n;
  const p = interpolate(frame, [0, n], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: EASE.expand});
  const r = expandRect(p, W, H, at);
  const rim = 14 * (1 - p);
  const rad = (r.a * Math.PI) / 180;
  const [cx, cy] = [r.x + r.w / 2, r.y + r.h / 2];
  const corner = ([u, v]: number[]) => {
    const [dx, dy] = [(u * r.w) / 2, (v * r.h) / 2];
    return `${(cx + dx * Math.cos(rad) - dy * Math.sin(rad)).toFixed(1)}px ${(cy + dx * Math.sin(rad) + dy * Math.cos(rad)).toFixed(1)}px`;
  };
  return (
    <>
      {on ? <div style={{position: 'absolute', left: r.x - rim, top: r.y - rim, width: r.w + 2 * rim, height: r.h + 2 * rim, rotate: `${r.a}deg`, boxShadow: lift(3, 1, 'photo'), ...texFill('memo', seed, W, H)}} /> : null}
      <AbsoluteFill style={{clipPath: on ? `polygon(${[[-1, -1], [1, -1], [1, 1], [-1, 1]].map(corner).join(', ')})` : undefined}}>{children}</AbsoluteFill>
    </>
  );
};
