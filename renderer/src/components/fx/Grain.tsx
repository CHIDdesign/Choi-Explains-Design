import React from 'react';
import {AbsoluteFill, Img, staticFile} from 'remotion';

/** 아날로그 질감(Musicbed 2026 'Analog Aesthetics'): 미리 만든 노이즈 타일을 2프레임마다 교체 */
export const Grain: React.FC<{frame: number; frames: string[]; opacity: number}> = ({frame, frames, opacity}) => {
  if (!frames.length || opacity <= 0) return null;
  const src = frames[Math.floor(frame / 2) % frames.length];
  return (
    <AbsoluteFill style={{pointerEvents: 'none', mixBlendMode: 'overlay', opacity}}>
      <Img src={staticFile(src)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
    </AbsoluteFill>
  );
};

export const Vignette: React.FC<{strength?: number}> = ({strength = 0.35}) => (
  <AbsoluteFill style={{pointerEvents: 'none',
    background: `radial-gradient(120% 100% at 50% 45%, rgba(0,0,0,0) 55%, rgba(0,0,0,${strength}) 100%)`}} />
);
