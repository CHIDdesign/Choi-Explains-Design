/**
 * 미리 만든 노이즈 타일(256×256, data URL) — 입자·잉크 번짐을 SVG feTurbulence 대신 타일 배경으로.
 * feTurbulence 는 화면 전체를 매 프레임 다시 계산해 렌더가 두 배 느렸다. 타일은 탭마다 한 번 만들고 위치만 옮긴다.
 */
import {useEffect, useState} from 'react';
import {continueRender, delayRender} from 'remotion';

const cache = new Map<string, string>();
const decoded = new Map<string, Promise<void>>();

const xorshift = (seed: number) => {
  let s = (seed * 2654435761) >>> 0 || 1;
  return () => {
    s ^= s << 13;
    s >>>= 0;
    s ^= s >>> 17;
    s ^= s << 5;
    s >>>= 0;
    return s / 4294967296;
  };
};

/** spread: 회색 값의 퍼짐(0~1), alpha: 0~1 */
export const noiseTile = (seed = 1, spread = 0.5, alpha = 0.5, size = 256): string => {
  const key = `${seed}:${spread}:${alpha}:${size}`;
  const hit = cache.get(key);
  if (hit) return hit;
  if (typeof document === 'undefined') return '';
  const c = document.createElement('canvas');
  c.width = size;
  c.height = size;
  const ctx = c.getContext('2d');
  if (!ctx) return '';
  const img = ctx.createImageData(size, size);
  const r = xorshift(seed);
  const a = Math.round(alpha * 255);
  for (let i = 0; i < size * size; i++) {
    // 두 난수 평균(삼각 분포) — 가운데가 두텁고 끝이 얇아 필름 입자처럼 보인다
    const v = Math.round(255 * Math.min(1, Math.max(0, 0.5 + (r() + r() - 1) * spread)));
    img.data[i * 4] = v;
    img.data[i * 4 + 1] = v;
    img.data[i * 4 + 2] = v;
    img.data[i * 4 + 3] = a;
  }
  ctx.putImageData(img, 0, 0);
  const url = c.toDataURL('image/png');
  cache.set(key, url);
  return url;
};

/** 프레임마다 타일 위치를 옮겨 입자가 움직이게(같은 프레임은 늘 같은 위치 — 렌더 결정적) */
export const grainOffset = (frame: number, size = 256): string => {
  const k = frame % 6;
  return `${(k * 97) % size}px ${(k * 61 + 37) % size}px`;
};

/** 잉크가 덜 묻은 자리: 불투명한 판에서 뭉친 얼룩과 잔점을 뚫어 낸 마스크 타일(도장·문서의 잉크 번짐) */
export const inkTile = (seed = 5, size = 512): string => {
  const key = `ink:${seed}:${size}`;
  const hit = cache.get(key);
  if (hit) return hit;
  if (typeof document === 'undefined') return '';
  const c = document.createElement('canvas');
  c.width = size;
  c.height = size;
  const ctx = c.getContext('2d');
  if (!ctx) return '';
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, size, size);
  ctx.globalCompositeOperation = 'destination-out';
  const r = xorshift(seed);
  for (let b = 0; b < 14; b++) {       // 뭉친 얼룩: 한 자리에 작은 점을 많이
    const bx = r() * size;
    const by = r() * size;
    const spread = 8 + r() * 34;
    for (let i = 0; i < 90; i++) {
      ctx.globalAlpha = 0.35 + r() * 0.65;
      ctx.beginPath();
      ctx.arc(bx + (r() + r() - 1) * spread, by + (r() + r() - 1) * spread, 0.4 + r() * r() * 1.4, 0, Math.PI * 2);      // 굵은 획(12px)의 15% 안 — 구멍이 크면 작은 글자가 부서진다
      ctx.fill();
    }
  }
  for (let i = 0; i < size * size * 0.006; i++) {      // 고른 잔점
    ctx.globalAlpha = 0.4 + r() * 0.6;
    ctx.beginPath();
    ctx.arc(r() * size, r() * size, 0.4 + r() * 1.1, 0, Math.PI * 2);
    ctx.fill();
  }
  const url = c.toDataURL('image/png');
  cache.set(key, url);
  return url;
};

/** 만든 타일(data URL)을 첫 사용 때 디코딩까지 기다린다(첫 프레임에 빠지지 않게) */
export const useTileUrl = (url: string): string => {
  const [handle] = useState(() => (url ? delayRender(`tile ${url.length}`) : null));
  useEffect(() => {
    if (handle === null) return;
    let p = decoded.get(url);
    if (!p) {
      const img = new Image();
      img.src = url;
      p = img.decode().catch(() => undefined);
      decoded.set(url, p);
    }
    p.then(() => continueRender(handle));
  }, [handle, url]);
  return url;
};

export const useNoiseTile = (seed = 1, spread = 0.5, alpha = 0.5): string => useTileUrl(noiseTile(seed, spread, alpha));
