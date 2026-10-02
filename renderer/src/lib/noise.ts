/**
 * 미리 만든 노이즈 타일(256×256 회색 PNG, data URL) — 필름 입자·종이 섬유를 SVG feTurbulence 대신 타일 배경으로.
 * feTurbulence 는 화면 전체를 매 프레임 다시 계산해(시드가 같아도 캐시되지 않음) 자료 사진 구간 렌더가 두 배 느렸다
 * (1920×1080 기준 1.2 → 2.4fps 실측). 타일은 탭마다 한 번 만들고, 프레임마다 위치만 옮겨 입자가 살아 움직인다.
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

/** spread: 회색 값의 퍼짐(0~1, 0.5 ≈ feTurbulence fractalNoise 한 옥타브), alpha: 0~1 (feTurbulence 알파 평균 ≈ 0.5) */
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

/** 컴포넌트용: 타일 URL + 첫 사용 때 디코딩이 끝날 때까지 렌더를 잡아 둔다(탭마다 한 번 — 첫 프레임에 입자가 빠지지 않게) */
export const useNoiseTile = (seed = 1, spread = 0.5, alpha = 0.5): string => {
  const url = noiseTile(seed, spread, alpha);
  const [handle] = useState(() => (url ? delayRender(`noise tile ${seed}`) : null));
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

/**
 * 인쇄 얼룩(리소·오래된 활판 — 디자인 v3 '종이 콜라주'): 투명 바탕에 종이색 점이 드문드문. 굵은 글자 위에 같은 글자 모양으로
 * 잘라 얹으면(background-clip: text) 잉크가 덜 묻은 자리처럼 보인다. 점 크기·밀도는 시드로 고정(렌더 결정적).
 */
export const speckleTile = (seed = 5, density = 0.05, color: [number, number, number] = [236, 233, 222], size = 256): string => {
  const key = `sp:${seed}:${density}:${color.join(',')}:${size}`;
  const hit = cache.get(key);
  if (hit) return hit;
  if (typeof document === 'undefined') return '';
  const c = document.createElement('canvas');
  c.width = size;
  c.height = size;
  const ctx = c.getContext('2d');
  if (!ctx) return '';
  const r = xorshift(seed);
  const n = Math.round(size * size * density * 0.08);
  for (let i = 0; i < n; i++) {
    const x = r() * size;
    const y = r() * size;
    const rad = 0.5 + r() * r() * 2.4;
    ctx.fillStyle = `rgba(${color[0]},${color[1]},${color[2]},${(0.55 + r() * 0.45).toFixed(2)})`;
    ctx.beginPath();
    ctx.arc(x, y, rad, 0, Math.PI * 2);
    ctx.fill();
  }
  const url = c.toDataURL('image/png');
  cache.set(key, url);
  return url;
};

/** 만든 타일(data URL)을 첫 사용 때 디코딩까지 기다린다 — useNoiseTile 과 같은 방식 */
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
