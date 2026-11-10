import React from 'react';
import {AbsoluteFill, interpolate} from 'remotion';
import {EASE} from '../../design/motion';
import {HOUSE} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import type {Transition} from '../../lib/types';

/**
 * 장면 전환 — 컷 지점(t)을 가운데 두고, 나가는 장면은 가속하며(ease-in) 빠지고
 * 들어오는 장면은 감속하며(ease-out) 안착한다. 두 장면을 겹칠 필요가 없어
 * 얼굴 ↔ 모션그래픽 ↔ B-roll 어느 조합에도 같은 방식으로 쓴다(에디터들이 쓰는 '컷 중심 전환 프리셋' 방식).
 *
 *  whip  : 방향성 모션 블러 + 살짝 밀림(휩 팬)        — 화제 전환, 빠른 흐름
 *  zoom  : 확대하며 빨려 들어가고 확대된 채로 풀림     — 개념 속으로 들어갈 때
 *  blur  : 부드러운 초점 이탈(소프트 디졸브 대용)       — 차분한 장면 연결
 *  push  : 위/아래로 살짝 밀며 페이드                   — 목록·단계 넘김
 *  flash : 노출이 확 올라갔다 내려옴                    — 강한 반전·공개
 *  dip   : 잉크색으로 잠깐 암전                         — 큰 챕터 경계
 *  wipe  : 브랜드 컬러 면이 화면을 쓸고 지나감          — 챕터 카드 진입
 *  leak  : 따뜻한 빛샘(라이트 리크)이 스쳐 지나감       — 인트로·감성 전환
 *
 * 교육 영상용 젠틀 편집: 편집 문법 엔진(studio/edit/grammar.py)은 blur·push·wipe·leak 만 만든다.
 * whip·zoom·flash·dip 은 렌더러에만 남아 있다(예전 계획·수동 props 호환).
 */

export type TxState = {
  style: React.CSSProperties;
  blurX: number;
  blurY: number;
  overlay: React.ReactNode;
  hideCaptions: boolean;
};

const IDLE: TxState = {style: {}, blurX: 0, blurY: 0, overlay: null, hideCaptions: false};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const activeTransition = (list: Transition[], t: number): Transition | null => {
  for (const tr of list) {
    if (Math.abs(t - tr.t) < tr.dur / 2) return tr;
  }
  return null;
};

export const transitionState = (list: Transition[], t: number, W: number, H: number, theme: Theme): TxState => {
  const tr = activeTransition(list, t);
  if (!tr) return IDLE;
  const half = tr.dur / 2;
  const p = (t - tr.t) / half; // -1 → 0(컷) → 1
  const out = p < 0;
  // e: 컷에 가까울수록 1(가장 강함)
  const e = out ? EASE.inExpo(1 + p) : 1 - EASE.outExpo(p);
  const sign = tr.dir === 'right' || tr.dir === 'down' ? 1 : -1;
  const side = out ? 1 : -1; // 나가는 장면은 진행 방향으로, 들어오는 장면은 반대편에서
  switch (tr.type) {
    case 'whip': {
      const horizontal = tr.dir !== 'up' && tr.dir !== 'down';
      const d = sign * side * (horizontal ? W : H) * 0.09 * e;
      return {
        style: {transform: `${horizontal ? `translateX(${d}px)` : `translateY(${d}px)`} scale(${1 + 0.14 * e})`},
        blurX: horizontal ? 60 * e : 0,
        blurY: horizontal ? 0 : 60 * e,
        overlay: null,
        hideCaptions: e > 0.35,
      };
    }
    case 'zoom': {
      // 절제된 줌스루: 1.00 → 1.12, 블러 σ 6 (과하면 싸 보인다)
      const scale = out ? 1 + 0.12 * e : 1 + 0.08 * e;
      return {
        style: {transform: `scale(${scale})`, filter: `brightness(${1 + 0.08 * e})`},
        blurX: 6 * e,
        blurY: 6 * e,
        overlay: null,
        hideCaptions: e > 0.35,
      };
    }
    case 'blur':
      // 블러 디졸브: σ 0 → 20 → 0 px
      return {style: {transform: `scale(${1 + 0.03 * e})`, filter: `brightness(${1 - 0.08 * e})`}, blurX: 20 * e,
        blurY: 20 * e, overlay: null, hideCaptions: e > 0.5};
    case 'push': {
      const d = sign * side * H * 0.05 * e;
      return {
        style: {transform: `translateY(${d}px)`, opacity: 1 - 0.55 * e},
        blurX: 0,
        blurY: 12 * e,
        overlay: <AbsoluteFill style={{background: theme.ink, opacity: 0.35 * e}} />,
        hideCaptions: e > 0.5,
      };
    }
    case 'flash':
      return {
        style: {filter: `brightness(${1 + 1.4 * e})`},
        blurX: 0,
        blurY: 0,
        overlay: <AbsoluteFill style={{background: '#fff', opacity: 0.85 * e ** 1.6}} />,
        hideCaptions: e > 0.6,
      };
    case 'dip':
      return {style: {}, blurX: 0, blurY: 0, overlay: <AbsoluteFill style={{background: tr.color || theme.ink, opacity: e}} />,
        hideCaptions: e > 0.4};
    case 'wipe': {
      // 나갈 때: 면이 왼쪽에서 들어와 화면을 덮고, 들어올 때: 오른쪽으로 빠지며 새 장면을 드러냄
      const k = out ? EASE.inOutCubic(1 + p) : EASE.inOutCubic(p);
      const x = out ? interpolate(k, [0, 1], [-1.02, 0], clamp) : interpolate(k, [0, 1], [0, 1.02], clamp);
      const edge = out ? 1 : -1;
      // F-14(docs/upgrade/06): 면은 하우스 종이, 앞 가장자리 24px 만 시그널 — 주황 전면이 검토 시트에 잡혔다
      const col = HOUSE.paper;
      return {
        style: {},
        blurX: 0,
        blurY: 0,
        overlay: (
          <AbsoluteFill style={{pointerEvents: 'none', overflow: 'hidden'}}>
            <div style={{position: 'absolute', top: 0, bottom: 0, width: W * 1.02, left: x * W, background: col}} />
            <div style={{position: 'absolute', top: 0, bottom: 0, width: 24, background: tr.color || theme.accent,
              left: x * W + (edge > 0 ? W * 1.02 - 24 : 0)}} />
          </AbsoluteFill>
        ),
        hideCaptions: Math.abs(x) < 0.55,
      };
    }
    case 'leak': {
      const drift = interpolate(p, [-1, 1], [-0.35, 0.35]);
      return {
        style: {filter: `brightness(${1 + 0.3 * e}) saturate(${1 + 0.2 * e})`},
        blurX: 4 * e,
        blurY: 4 * e,
        overlay: (
          <AbsoluteFill style={{pointerEvents: 'none', mixBlendMode: 'screen', opacity: 0.6 * e}}>
            <AbsoluteFill style={{background: `radial-gradient(55% 80% at ${50 + drift * 100}% 40%, rgba(255,150,60,0.95) 0%, rgba(255,90,30,0.55) 35%, rgba(0,0,0,0) 70%)`}} />
            <AbsoluteFill style={{background: `radial-gradient(40% 60% at ${30 - drift * 80}% 70%, rgba(255,60,90,0.6) 0%, rgba(0,0,0,0) 65%)`}} />
          </AbsoluteFill>
        ),
        hideCaptions: e > 0.5,
      };
    }
    default:
      return IDLE;
  }
};

export const PUSH_SEC = 0.4;

/** 전면 자료 사이 세로 밀기(영상당 몇 번) — 앞 장은 멈춘 채 위로 나가고 다음 장이 아래에서 붙어 올라온다. 앞 장을 그만큼 더 그릴 뿐 타임라인 길이는 그대로. */
export const PushSlide: React.FC<{frame: number; fps: number; H: number; leaving: boolean; children: React.ReactNode}> = ({frame, fps, H, leaving, children}) => {
  const p = interpolate(frame, [0, Math.round(PUSH_SEC * fps)], [0, 1], {...clamp, easing: EASE.inOutCubic});
  return <AbsoluteFill style={{transform: `translateY(${(leaving ? -p : 1 - p) * H}px)`}}>{children}</AbsoluteFill>;
};

const RIP_FRAMES = 12;

const ripEdge = (H: number, seed: number) => {
  const c = Array.from({length: 40}, (_, i) => Math.abs(Math.sin((i + 1) * (seed + 3.7) * 12.9898) * 43758.5453) % 1);
  const at = (u: number) => {
    const a = Math.floor(u);
    const t = u - a;
    return c[a % 40] + (c[(a + 1) % 40] - c[a % 40]) * t * t * (3 - 2 * t);
  };
  return Array.from({length: Math.ceil(H / 4) + 1}, (_, i) => {
    const y = i * 4;
    return {y, o: at(y / 90 + 1) * 46 + at(y / 18 + 9) * 16 + at(y / 5 + 17) * 6, w: 5 + at(y / 26 + 23) * 15 + at(y / 6 + 31) * 4};
  });
};

/**
 * 종이 찢기 전환 — 아이덴트에 들고날 때만(영상당 1~2회). children 이 찢긴 선을 따라 드러났다가 찢겨 나간다. 그래픽 자기 길이 안에서 일어나 타임라인 길이는 그대로다.
 * 선 주변 그림자는 선 근처만 덮는 띠 하나를 흐린 것 — 전면 블러 필터를 프레임마다 돌리지 않는다. 띠를 겹치면 등고선처럼 계단이 보인다.
 */
export const PaperRip: React.FC<{frame: number; dur: number; W: number; H: number; seed?: number; children: React.ReactNode}> = ({frame, dur, W, H, seed = 2, children}) => {
  const entering = frame < RIP_FRAMES;
  const leaving = frame >= dur - RIP_FRAMES;
  if (!entering && !leaving) return <>{children}</>;
  const p = entering ? EASE.inOutCubic(Math.max(0, frame) / RIP_FRAMES) : EASE.inOutCubic(Math.min(1, (frame - (dur - RIP_FRAMES)) / RIP_FRAMES));
  const slant = W * 0.09;
  const X = -slant - 90 + (W + 2 * slant + 180) * p;
  const edge = ripEdge(H, entering ? seed : seed + 5).map((e) => ({...e, x: X + slant * (e.y / H - 0.5) * 2 + e.o}));
  const line = edge.map((e) => `${e.x.toFixed(1)} ${e.y}`).join(' L ');
  const clip = entering ? `path('M -2 -2 L ${line} L -2 ${H + 2} Z')` : `path('M ${W + 2} -2 L ${line} L ${W + 2} ${H + 2} Z')`;
  const dir = entering ? -1 : 1;
  const rim = edge.map((e) => `${(e.x + dir * e.w).toFixed(1)} ${e.y}`).reverse().join(' L ');
  const pad = slant + 100;
  const local = edge.map((e) => `${(e.x - X + pad).toFixed(1)} ${e.y}`).join(' L ');
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{clipPath: clip}}>{children}</AbsoluteFill>
      <svg width={2 * pad + 70} height={H} style={{position: 'absolute', left: X - pad, top: 0, pointerEvents: 'none', filter: 'blur(12px)'}}>
        <path d={`M ${local}`} fill="none" stroke="rgb(20,16,12)" strokeOpacity={0.42} strokeWidth={30} />
      </svg>
      <svg width={W} height={H} style={{position: 'absolute', inset: 0, pointerEvents: 'none'}}>
        <path d={`M ${line} L ${rim} Z`} fill="#FBF8F0" />
      </svg>
    </AbsoluteFill>
  );
};

/** 방향성 블러(SVG) — CSS blur() 는 한 방향 블러가 없어서 필터를 매 프레임 갱신한다. */
export const TransitionFilter: React.FC<{id: string; blurX: number; blurY: number}> = ({id, blurX, blurY}) => (
  <svg width={0} height={0} style={{position: 'absolute'}}>
    <defs>
      <filter id={id} x="-15%" y="-15%" width="130%" height="130%" colorInterpolationFilters="sRGB">
        <feGaussianBlur stdDeviation={`${blurX.toFixed(2)} ${blurY.toFixed(2)}`} edgeMode="duplicate" />
      </filter>
    </defs>
  </svg>
);

/** 장면(얼굴·그래픽) 전체를 감싸 전환을 입힌다. 자막·엔드카드는 바깥에 둔다. */
export const TransitionStage: React.FC<{
  tx: TxState;
  id?: string;
  children: React.ReactNode;
}> = ({tx, id = 'tx-blur', children}) => {
  const blur = tx.blurX > 0.3 || tx.blurY > 0.3;
  const filters = [blur ? `url(#${id})` : '', (tx.style.filter as string) || ''].filter(Boolean).join(' ');
  return (
    <>
      {blur ? <TransitionFilter id={id} blurX={tx.blurX} blurY={tx.blurY} /> : null}
      <AbsoluteFill style={{...tx.style, filter: filters || undefined, transformOrigin: '50% 50%'}}>
        {children}
      </AbsoluteFill>
      {tx.overlay}
    </>
  );
};
