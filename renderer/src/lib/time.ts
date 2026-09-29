import type {FaceSample, Keyframe} from './types';

export const toFrame = (sec: number, fps: number) => Math.round(sec * fps);

/** 정렬된 배열에서 t 이하의 마지막 인덱스 */
export const lastIndexAtOrBefore = <T,>(arr: T[], t: number, key: (x: T) => number): number => {
  let lo = 0;
  let hi = arr.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (key(arr[mid]) <= t) {
      ans = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return ans;
};

export const sampleKeyframes = (kfs: Keyframe[], t: number, fallback = 0): number => {
  if (!kfs.length) return fallback;
  const i = lastIndexAtOrBefore(kfs, t, (k) => k.t);
  if (i < 0) return kfs[0].v;
  if (i >= kfs.length - 1) return kfs[kfs.length - 1].v;
  const a = kfs[i];
  const b = kfs[i + 1];
  const f = b.t === a.t ? 0 : (t - a.t) / (b.t - a.t);
  return a.v + (b.v - a.v) * f;
};

export const sampleFace = (face: FaceSample[], t: number): FaceSample => {
  if (!face.length) return {t, x: 0.5, y: 0.42, s: 0.28};
  const i = lastIndexAtOrBefore(face, t, (f) => f.t);
  if (i < 0) return face[0];
  if (i >= face.length - 1) return face[face.length - 1];
  const a = face[i];
  const b = face[i + 1];
  const f = b.t === a.t ? 0 : Math.min(1, Math.max(0, (t - a.t) / (b.t - a.t)));
  return {t, x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f, s: a.s + (b.s - a.s) * f};
};
