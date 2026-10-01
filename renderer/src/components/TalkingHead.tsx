import React from 'react';
import {Freeze, interpolate, OffthreadVideo, Sequence, staticFile, useCurrentFrame} from 'remotion';
import {lerp} from '../lib/anim';
import {toFrame} from '../lib/time';
import type {Clip, FaceSample} from '../lib/types';

export type Rect = {x: number; y: number; w: number; h: number};
export type VideoBox = {w: number; h: number; tx: number; ty: number};

export const lerpRect = (a: Rect, b: Rect, t: number): Rect => ({
  x: lerp(a.x, b.x, t),
  y: lerp(a.y, b.y, t),
  w: lerp(a.w, b.w, t),
  h: lerp(a.h, b.h, t),
});

export const lerpBox = (a: VideoBox, b: VideoBox, t: number): VideoBox => ({
  w: lerp(a.w, b.w, t),
  h: lerp(a.h, b.h, t),
  tx: lerp(a.tx, b.tx, t),
  ty: lerp(a.ty, b.ty, t),
});

/**
 * 16:9 영상을 region 안에 cover 로 배치하고 얼굴 기준으로 줌.
 * - anchor: 얼굴 위치를 고정한 채 확대(롱폼 풀프레임 — 원래 구도 유지)
 * - center: 얼굴을 region 가로 중앙, 세로 anchorY 지점에 둔다(칠판 패널 화자 열, 숏폼 세로 크롭)
 */
export const videoBoxFor = (
  region: Rect,
  face: FaceSample,
  zoom: number,
  mode: 'anchor' | 'center',
  anchorY = 0.42,
  aspect = 16 / 9,
): VideoBox => {
  const baseW = Math.max(region.w, region.h * aspect);
  const baseH = baseW / aspect;
  const w = baseW * zoom;
  const h = baseH * zoom;
  let tx: number;
  let ty: number;
  if (mode === 'anchor') {
    const bx = region.x + (region.w - baseW) / 2;
    const by = region.y + (region.h - baseH) / 2;
    const px = bx + face.x * baseW;
    const py = by + (face.y - 0.04) * baseH;
    tx = px - face.x * w;
    ty = py - (face.y - 0.04) * h;
  } else {
    tx = region.x + region.w / 2 - face.x * w;
    ty = region.y + region.h * anchorY - face.y * h;
  }
  // region 을 항상 덮도록
  tx = Math.min(region.x, Math.max(region.x + region.w - w, tx));
  ty = Math.min(region.y, Math.max(region.y + region.h - h, ty));
  return {w, h, tx, ty};
};

const FILL: React.CSSProperties = {position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover'};

/** 소프트 컷: 앞 장면의 마지막 프레임을 멈춰 두고 몇 프레임에 걸쳐 걷어낸다(같은 프레이밍 점프컷의 '튐'을 줄임). */
const SoftCut: React.FC<{src: string; srcFrame: number; frames: number}> = ({src, srcFrame, frames}) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, frames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <Freeze frame={0}>
      <OffthreadVideo src={staticFile(src)} trimBefore={Math.max(0, srcFrame)} muted style={{...FILL, opacity: o}} />
    </Freeze>
  );
};

export const TalkingHead: React.FC<{
  clips: Clip[];
  fps: number;
  region: Rect;
  box: VideoBox;
  radius?: number;
  border?: string;
  shadow?: boolean;
  filter?: string;
}> = ({clips, fps, region, box, radius = 0, border, shadow, filter}) => {
  return (
    <div
      style={{
        position: 'absolute',
        left: region.x,
        top: region.y,
        width: region.w,
        height: region.h,
        overflow: 'hidden',
        borderRadius: radius,
        outline: border,
        boxShadow: shadow ? '0 18px 60px rgba(0,0,0,0.45)' : undefined,
        background: '#000',
      }}
    >
      <div style={{position: 'absolute', left: box.tx - region.x, top: box.ty - region.y, width: box.w, height: box.h,
        filter}}>
        {clips.map((c, i) => {
          const from = toFrame(c.start, fps);
          const to = toFrame(c.start + c.dur, fps);
          if (to <= from) return null;
          const prev = i > 0 ? clips[i - 1] : null;
          const softFrames = prev && c.soft ? Math.min(Math.max(2, Math.round(c.soft * fps)), to - from) : 0;
          // 앞 클립이 화면에 마지막으로 보여 준 원본 프레임
          const prevLast = prev
            ? toFrame(prev.srcStart, fps) + (toFrame(prev.start + prev.dur, fps) - toFrame(prev.start, fps)) - 1
            : 0;
          return (
            <Sequence key={i} from={from} durationInFrames={to - from} layout="none" name={`clip ${i}`}>
              <OffthreadVideo src={staticFile(c.src)} trimBefore={toFrame(c.srcStart, fps)} muted style={FILL} />
              {prev && softFrames > 0 ? (
                <Sequence durationInFrames={softFrames} layout="none" name={`soft ${i}`}>
                  <SoftCut src={prev.src} srcFrame={prevLast} frames={softFrames} />
                </Sequence>
              ) : null}
            </Sequence>
          );
        })}
      </div>
    </div>
  );
};
