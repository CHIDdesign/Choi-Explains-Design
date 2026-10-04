import React from 'react';
import {AbsoluteFill} from 'remotion';
import {grainOffset, useNoiseTile} from '../../lib/noise';

/**
 * 모니터 질감(채널 주인 2026-10-04 레퍼런스 릴스: "그래픽 위에 약간의 노이즈와 모니터 화면 같은 처리 — 레트로하면서도 디지털",
 * "개체마다 살짝의 빛과 아주 약간의 블러"). 그 영상을 픽셀 단위로 확대해 본 것을 층으로 옮겼다:
 *  1. 아주 약간의 흐림(초점이 살짝 무른 화면) — 뒤 그림을 backdrop-filter 로 0.5~0.7px
 *  2. 개체마다 번지는 빛(블룸·할레이션) — 크게 흐린 뒤 그림을 screen 으로 얹는다(밝은 개체 둘레에 빛, 어두운 바탕일수록 잘 보인다)
 *  3. 서브픽셀 격자 — 세로 RGB 줄(4px 주기) + 옅은 가로 주사선
 *  4. 움직이는 입자(노이즈 타일을 프레임마다 옮김) · 5. 비네트 · 6. 아주 작은 깜빡임
 * 모두 합성기 층(CSS)이라 매 프레임 바뀌는 SVG 필터·화면 전체 feTurbulence 를 쓰지 않는다(렌더 속도 규칙).
 * strength 0 = 없음, 1 = 기본. opacity 는 전면 그래픽의 등장·퇴장에 맞춰 LongForm 이 준다. dark = 어두운 판(빛 번짐을 screen 으로).
 */
export const ScreenLook: React.FC<{frame: number; strength: number; opacity: number; dark?: boolean; seed?: number}> = ({
  frame, strength, opacity, dark = false, seed = 11,
}) => {
  const tile = useNoiseTile(seed, 0.55, 0.6);
  if (strength <= 0 || opacity <= 0.001) return null;
  // 켜고 끄는 정도(opacity)를 바깥 층에 걸면 안 된다 — 불투명도 < 1 인 조상은 자식을 격리해 soft-light·screen 이 아래 그래픽과
  // 섞이지 않고 회녹색 막으로 칠해진다(2026-10-04 실측). 층마다 자기 세기에 곱한다
  const s = Math.min(1.6, strength) * Math.min(1, Math.max(0, opacity));
  // 결정적인 작은 깜빡임(±0.6%): 같은 프레임은 늘 같은 값
  const flick = 0.006 * s * Math.sin(frame * 12.9898 + seed * 78.233);
  const layer: React.CSSProperties = {position: 'absolute', inset: 0, pointerEvents: 'none'};
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      {/* 1. 아주 약간의 흐림 */}
      <div style={{...layer, backdropFilter: `blur(${(0.6 * s).toFixed(2)}px)`, WebkitBackdropFilter: `blur(${(0.6 * s).toFixed(2)}px)`}} />
      {/* 2. 개체마다 번지는 빛 — 어두운 판: 밝은 곳을 키운 흐린 사본을 screen 으로(밝은 개체 둘레에 빛) ·
             밝은 판: screen 은 어두운 글자를 회색으로 띄우므로 soft-light 로 부드럽게만 */}
      {dark ? (
        <div style={{...layer, mixBlendMode: 'screen', opacity: 0.34 * s,
          backdropFilter: `blur(${Math.round(14 * s)}px) contrast(1.6) brightness(0.9) saturate(1.1) sepia(0.12)`,
          WebkitBackdropFilter: `blur(${Math.round(14 * s)}px) contrast(1.6) brightness(0.9) saturate(1.1) sepia(0.12)`}} />
      ) : (
        <div style={{...layer, mixBlendMode: 'soft-light', opacity: 0.26 * s,
          backdropFilter: `blur(${Math.round(12 * s)}px) saturate(1.15)`,
          WebkitBackdropFilter: `blur(${Math.round(12 * s)}px) saturate(1.15)`}} />
      )}
      {/* 3. 서브픽셀 격자(세로 RGB) + 주사선(가로) — soft-light 라 순백·순흑은 그대로(흰 판이 묻히지 않게), 줄 색의 평균은
             중성 회색(색이 틀어지지 않게 — 2026-10-04 채널 주인: '노이즈가 너무 푸르다', 따뜻함은 아래 한 겹으로만) */}
      <div style={{...layer, mixBlendMode: 'soft-light', opacity: (dark ? 0.5 : 0.38) * s,
        backgroundImage: 'linear-gradient(90deg, rgb(198,120,120) 0 25%, rgb(120,190,120) 25% 50%, rgb(120,120,194) 50% 75%, rgb(72,72,72) 75% 100%)',
        backgroundSize: '4px 100%'}} />
      <div style={{...layer, mixBlendMode: 'soft-light', opacity: (dark ? 0.5 : 0.35) * s,
        backgroundImage: 'repeating-linear-gradient(0deg, rgba(40,30,24,1) 0 1px, rgba(128,128,128,1) 1px 4px)'}} />
      {/* 따뜻한 기운(soft-light — 흰색·검은색은 그대로) */}
      <div style={{...layer, mixBlendMode: 'soft-light', opacity: 0.18 * s, background: 'rgb(176,128,92)'}} />
      {/* 4. 입자 */}
      {tile ? (
        <div style={{...layer, mixBlendMode: 'overlay', opacity: 0.22 * s, backgroundImage: `url(${tile})`,
          backgroundSize: '256px 256px', backgroundPosition: grainOffset(frame)}} />
      ) : null}
      {/* 5. 비네트 · 6. 깜빡임 */}
      <div style={{...layer, background: `radial-gradient(115% 95% at 50% 48%, rgba(0,0,0,0) 58%, rgba(24,10,4,${((dark ? 0.32 : 0.16) * s).toFixed(2)}) 100%)`}} />
      <div style={{...layer, background: flick > 0 ? '#ffffff' : '#000000', opacity: Math.abs(flick)}} />
    </AbsoluteFill>
  );
};
