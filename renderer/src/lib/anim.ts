import {Easing, interpolate} from 'remotion';

// 모션 원칙: 절제된 에디토리얼 모션. 빠르게 들어오고(expo-out) 조용히 사라진다.
export const EASE_OUT = Easing.bezier(0.16, 1, 0.3, 1);
export const EASE_IN_OUT = Easing.bezier(0.65, 0, 0.35, 1);
export const EASE_IN = Easing.bezier(0.7, 0, 0.84, 0);

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/** 0→1 진입 진행도 */
export const enter = (frame: number, start: number, dur: number, easing = EASE_OUT) =>
  interpolate(frame, [start, start + Math.max(1, dur)], [0, 1], {...clamp, easing});

/** 1→0 퇴장 진행도(끝 프레임 기준) */
export const exit = (frame: number, end: number, dur: number, easing = EASE_IN_OUT) =>
  interpolate(frame, [end - Math.max(1, dur), end], [1, 0], {...clamp, easing});

/** 진입과 퇴장을 합친 가시성 */
export const presence = (frame: number, total: number, inDur = 14, outDur = 10) =>
  Math.min(enter(frame, 0, inDur), exit(frame, total, outDur));

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export const stagger = (frame: number, index: number, start: number, gap: number, dur: number) =>
  enter(frame, start + index * gap, dur);

/** 목록이 말하는 속도에 맞춰 순서대로 드러나도록: 전체 길이를 항목 수로 분배 */
export const revealAt = (index: number, count: number, totalFrames: number, lead = 10) => {
  const usable = Math.max(1, totalFrames * 0.72 - lead);
  return lead + (usable / Math.max(1, count)) * index;
};
