import React, {useEffect, useState} from 'react';
import {continueRender, delayRender, staticFile} from 'remotion';
import {grainOffset, useNoiseTile} from '../../lib/noise';
import {seeded} from '../paper/Paper';

/** 재질 키트 텍스처(studio/render/assets.py make_textures → public/fx/tex/<이름>.jpg, 1920×1080). 조명을 받은 높이맵이라 CSS 로 흉내 내지 않는다. */
export type TexName = 'eggshell' | 'parchment' | 'memo' | 'kraft' | 'gray' | 'graph' | 'newsprint' | 'newsblur' | 'print' | 'forest' | 'blueprint' | 'desk';

/** 파일을 못 읽었을 때의 평면색 — 텍스처 하나 때문에 렌더가 멈추지 않는다 */
const FLAT: Record<TexName, string> = {eggshell: '#F4F3EE', parchment: '#EFE9DC', memo: '#FBF9F3', kraft: '#B89B72', gray: '#CDC9C3', graph: '#F2F2EA',
  newsprint: '#DED6C2', newsblur: '#D2CAB8', print: '#F0EDE5', forest: '#1F4D3E', blueprint: '#2B4A5E', desk: '#3A352E'};
const NAMES = Object.keys(FLAT) as TexName[];
const TW = 1920;
const TH = 1080;

const url = (name: TexName) => staticFile(`fx/tex/${name}.jpg`);
const kept: HTMLImageElement[] = [];   // 참조를 쥐고 있어야 CSS 배경이 디코딩된 그림을 그대로 쓴다
let ready: Promise<unknown> | null = null;

/** 첫 사용 때 텍스처를 모두 받아 디코딩할 때까지 렌더를 잡아 둔다(탭마다 한 번) */
export const useMaterials = () => {
  const [handle] = useState(() => delayRender('material textures'));
  useEffect(() => {
    ready = ready ?? Promise.all(NAMES.map((n) => {
      const img = new Image();
      img.src = url(n);
      kept.push(img);
      return img.decode().catch(() => undefined);
    }));
    ready.then(() => continueRender(handle));
  }, [handle]);
};

/** 조각이 텍스처의 어느 자리를 쓰는가 */
const texAt = (seed: number, w?: number, h?: number) => {
  const k = w && h ? Math.max(1, w / TW, h / TH) : 1;
  const r = seeded(seed + 0.5);
  return {k, dx: w ? Math.max(0, TW * k - w) * r() : 0, dy: h ? Math.max(0, TH * k - h) * r() : 0};
};

/** 종이 조각의 배경: 시드마다 텍스처의 다른 자리를 쓴다(조각이 텍스처 안에 온전히 들어가게). w·h 를 안 주면 화면 전체 */
export const texFill = (name: TexName, seed = 1, w?: number, h?: number): React.CSSProperties => {
  const {k, dx, dy} = texAt(seed, w, h);
  return {backgroundColor: FLAT[name], backgroundImage: `url(${url(name)})`, backgroundRepeat: 'no-repeat',
    backgroundSize: w && h ? `${TW * k}px ${TH * k}px` : 'cover', backgroundPosition: w && h ? `${-Math.round(dx)}px ${-Math.round(dy)}px` : '50% 50%'};
};

const INK_SHIFT = 2.6;     // 종이 구김이 활자를 미는 폭(화면 px)
const inkBakes = new Map<string, Promise<string>>();

const loadImage = (u: string) => new Promise<HTMLImageElement>((ok, no) => {
  const i = new Image();
  i.onload = () => ok(i);
  i.onerror = no;
  i.src = u;
});

/** 문서 그림의 바탕을 희게 펴고(곱하기에서 사각 경계가 남지 않게) 활자를 종이의 음영만큼 민 사본. rect = 그림이 놓이는 종이 안 자리 */
const bakeInk = async (src: string, paper: {w: number; h: number; seed: number}, rect: {x: number; y: number; w: number; h: number}): Promise<string> => {
  const [img, tex] = await Promise.all([loadImage(staticFile(src)), loadImage(url('print'))]);
  const s = Math.min(1, 1800 / Math.max(img.width, img.height));
  const [cw, ch] = [Math.round(img.width * s), Math.round(img.height * s)];
  const canvas = (draw: (c: CanvasRenderingContext2D) => void) => {
    const c = document.createElement('canvas');
    c.width = cw;
    c.height = ch;
    const ctx = c.getContext('2d', {willReadFrequently: true}) as CanvasRenderingContext2D;
    draw(ctx);
    return ctx;
  };
  const px = cw / rect.w;                 // 화면 1px 이 사본에서 몇 칸인가
  const {k, dx, dy} = texAt(paper.seed, paper.w, paper.h);
  const a = canvas((c) => c.drawImage(img, 0, 0, cw, ch)).getImageData(0, 0, cw, ch).data;
  const m = canvas((c) => {
    c.filter = `blur(${(1.6 * px).toFixed(1)}px)`;                 // 입자까지 따라가면 글자 가장자리가 지글거린다 — 구김만
    c.drawImage(tex, (dx + rect.x) / k, (dy + rect.y) / k, rect.w / k, rect.h / k, 0, 0, cw, ch);
  }).getImageData(0, 0, cw, ch).data;
  const gain = [0, 1, 2].map((j) => {             // 채널마다 바탕(문서는 대부분이 바탕이니 중앙값)을 흰색으로 — 누런 스캔이 종이 위에 사각형으로 남지 않게
    const v: number[] = [];
    for (let i = j; i < a.length; i += 256) v.push(a[i]);
    return Math.min(1.6, 252 / Math.max(120, v.sort((p, q) => p - q)[v.length >> 1]));
  });
  let sum = 0;
  for (let i = 0; i < m.length; i += 64) sum += m[i + 1];
  const mean = sum / (m.length / 64);
  const out = canvas((c) => c.fillRect(0, 0, 0, 0));
  const res = out.createImageData(cw, ch);
  const d = res.data;
  for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) {
    const o = (y * cw + x) * 4;
    const v = Math.max(-1, Math.min(1, (m[o + 1] - mean) / 26)) * INK_SHIFT * px;      // 음영은 빛 쪽 기울기다: 빛 방향(위 왼쪽)을 따라 민다
    const fx = Math.max(0, Math.min(cw - 1.001, x - v * 0.6));
    const fy = Math.max(0, Math.min(ch - 1.001, y - v * 0.8));
    const [x0, y0, u, w] = [Math.floor(fx), Math.floor(fy), fx - Math.floor(fx), fy - Math.floor(fy)];
    const p = (y0 * cw + x0) * 4;
    const [r, b, c] = [p + 4, p + cw * 4, p + cw * 4 + 4];
    for (let j = 0; j < 3; j++) {
      d[o + j] = Math.min(255, gain[j] * ((a[p + j] * (1 - u) + a[r + j] * u) * (1 - w) + (a[b + j] * (1 - u) + a[c + j] * u) * w));
    }
    d[o + 3] = 255;
  }
  out.putImageData(res, 0, 0);
  return new Promise((ok, no) => out.canvas.toBlob((blob) => (blob ? ok(URL.createObjectURL(blob)) : no(new Error('blob'))), 'image/jpeg', 0.94));
};

/** 구겨진 종이 위 문서의 글자층: 처음 쓸 때 탭마다 한 번 굽는다 — 프레임마다 필터를 돌리지 않는다. 못 구우면 원본 */
export const useInkOnPaper = (src: string, on: boolean, paper: {w: number; h: number; seed: number}, rect: {x: number; y: number; w: number; h: number}): string => {
  const [baked, setBaked] = useState('');
  const [handle] = useState(() => (on ? delayRender(`ink ${src}`) : null));
  useEffect(() => {
    if (!on) return;
    const key = `${src}|${paper.w.toFixed(1)}|${paper.h.toFixed(1)}|${paper.seed}`;
    const job = inkBakes.get(key) ?? bakeInk(src, paper, rect).catch(() => staticFile(src));
    inkBakes.set(key, job);
    job.then(setBaked);
  }, [src, on]);
  useEffect(() => {
    if (baked && handle !== null) continueRender(handle);
  }, [baked, handle]);
  return baked || staticFile(src);
};

/** 전면 바탕: 124% 로 키워 시드마다 다른 자리·각도·방향을 쓴다 — 모든 보드의 같은 자리에 같은 구김이 있으면 깔아 놓은 배경 그림으로 읽힌다 */
export const TexBackdrop: React.FC<{name: TexName; seed?: number}> = ({name, seed = 1}) => {
  const r = seeded(seed + 0.5);
  const slack = () => `${((r() - 0.5) * 12).toFixed(2)}%`;      // 여유 12% 에서 ±2.5° 회전 몫을 뺀 만큼(자기 크기의 ±6%)
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden'}}>
      <div style={{position: 'absolute', inset: '-12%', ...texFill(name), translate: `${slack()} ${slack()}`, rotate: `${((r() - 0.5) * 5).toFixed(2)}deg`, scale: `${seed % 2 ? -1 : 1} ${(seed >> 1) % 2 ? -1 : 1}`}} />
    </div>
  );
};

/** 입자 층 — 언제나 글자 아래. 화자 영상 위에는 깔지 않는다. frame 을 주면 입자가 살아 움직인다(사진·영상), 종이는 멈춰 있다 */
export const GrainLayer: React.FC<{opacity?: number; frame?: number; blend?: React.CSSProperties['mixBlendMode']}> = ({opacity = 0.16, frame,
  blend = 'overlay'}) => {
  const tile = useNoiseTile(3, 0.55, 1);
  return (
    <div style={{position: 'absolute', inset: 0, pointerEvents: 'none', opacity, mixBlendMode: blend, backgroundImage: `url(${tile})`,
      backgroundSize: '256px 256px', backgroundPosition: frame === undefined ? '0 0' : grainOffset(Math.floor(frame / 2))}} />
  );
};
