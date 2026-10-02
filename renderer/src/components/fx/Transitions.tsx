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
