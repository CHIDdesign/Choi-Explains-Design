import React, {useEffect, useMemo, useState} from 'react';
import {continueRender, delayRender, Img, staticFile} from 'remotion';
import {paperSettle} from '../../design/motion';
import {FONT, liftDrop, MAT} from '../../design/tokens';
import {estWidth, fitSize} from '../../lib/fit';
import type {Cutout as CutoutData} from '../../lib/types';
import {seeded} from '../paper/Paper';
import {Sheet} from './Sheet';

/** 가위로 오린 사각형: 네 모서리가 조금씩 어긋난 다각형(%) */
const cutClip = (seed: number, loose = 1) => {
  const r = seeded(seed + 0.2);
  const j = () => (r() * 1.1 * loose).toFixed(2);
  return `polygon(${j()}% ${j()}%, ${(100 - +j()).toFixed(2)}% ${j()}%, ${(100 - +j()).toFixed(2)}% ${(100 - +j()).toFixed(2)}%, ${j()}% ${(100 - +j()).toFixed(2)}%)`;
};

/** 방향마다 5.2 ± 0.8px — 폭이 고르면 포토샵 획으로 보이고, 두꺼우면 다리 사이가 메워져 스티커가 된다 */
const RING = Array.from({length: 16}, (_, i) => {
  const r = 5.2 + 0.8 * Math.sin(i * 2.399);
  return [Math.cos((i * Math.PI) / 8) * r, Math.sin((i * Math.PI) / 8) * r];
});
const CUT_SHADOW = 'drop-shadow(1px 2px 3px rgba(0,0,0,0.35)) drop-shadow(8px 12px 24px rgba(0,0,0,0.18))';    // 접촉 + 넓은 그림자, 빛은 위 왼쪽

/** 오림의 흰 테두리: 알파를 둘레 16방향으로 밀어 합친다 — drop-shadow 를 잇달아 걸면 방향마다 두께가 달라 덩어리진다 */
const StickerEdge: React.FC = () => (
  <svg width={0} height={0} style={{position: 'absolute'}}>
    <filter id="cut-edge" x="-20%" y="-20%" width="140%" height="140%" colorInterpolationFilters="sRGB">
      {RING.map(([dx, dy], i) => <feOffset key={i} in="SourceAlpha" dx={dx} dy={dy} result={`e${i}`} />)}
      <feMerge result="grown">{RING.map((_, i) => <feMergeNode key={i} in={`e${i}`} />)}<feMergeNode in="SourceAlpha" /></feMerge>
      <feFlood floodColor="#F6F2E8" />
      <feComposite in2="grown" operator="in" result="edge" />
      <feMerge><feMergeNode in="edge" /><feMergeNode in="SourceGraphic" /></feMerge>
    </filter>
  </svg>
);

const ALPHA_N = 128;
export type AlphaGrid = {cells: number[][]; aspect: number};
const alphas = new Map<string, AlphaGrid | null>();

/** 오린 PNG 의 알파 격자와 실제 비율(처음 한 번 읽는다 — 오린 파일은 원본 사진과 비율이 다르다). 못 읽으면 null — 지시점은 상자 기준으로 돌아간다 */
export const useAlphaGrid = (src?: string): AlphaGrid | null => {
  const [grid, setGrid] = useState(() => (src ? alphas.get(src) ?? null : null));
  const [handle] = useState(() => (src && !alphas.has(src) ? delayRender(`alpha ${src}`) : null));
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (handle === null || !src) return;
    const finish = (g: AlphaGrid | null) => {
      alphas.set(src, g);
      setGrid(g);
      setDone(true);
    };
    const img = new Image();
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = ALPHA_N;
      c.height = ALPHA_N;
      const ctx = c.getContext('2d');
      if (!ctx) return finish(null);
      ctx.drawImage(img, 0, 0, ALPHA_N, ALPHA_N);
      const a = ctx.getImageData(0, 0, ALPHA_N, ALPHA_N).data;
      finish({cells: Array.from({length: ALPHA_N}, (_, i) => Array.from({length: ALPHA_N}, (_v, j) => a[(i * ALPHA_N + j) * 4 + 3] / 255)), aspect: img.width / img.height});
    };
    img.onerror = () => finish(null);
    img.src = staticFile(src);
  }, [handle, src]);
  useEffect(() => {
    if (done && handle !== null) continueRender(handle);
  }, [done, handle]);
  return grid;
};

/**
 * 오림 액자: 흰 테두리 + 두 겹 그림자. cut=true 는 이미 오려 낸 PNG(알파) — 테두리는 그림 윤곽을 따라간다. foot = 아래 여백을 그만큼 더 둔다(출처를 적는 자리).
 */
export const CutoutFrame: React.FC<{src: string; w: number; h: number; seed?: number; rotate?: number; border?: number; level?: number; cut?: boolean;
  fit?: 'cover' | 'contain'; focus?: string; foot?: number; style?: React.CSSProperties; children?: React.ReactNode}> = ({src, w, h, seed = 1, rotate = 0, border = 12, level = 2, cut = false,
  fit = 'cover', focus = '50% 50%', foot = 0, style, children}) => {
  const outer = useMemo(() => cutClip(seed), [seed]);
  const file = staticFile(src);
  if (cut) {
    return (
      <div style={{width: w, height: h, rotate: `${rotate}deg`, filter: CUT_SHADOW, ...style}}>
        <StickerEdge />
        <Img src={file} style={{width: '100%', height: '100%', objectFit: 'contain', filter: 'url(#cut-edge)'}} />
        {children}
      </div>
    );
  }
  return (
    <div style={{position: 'relative', width: w, height: h, rotate: `${rotate}deg`, filter: liftDrop(level), ...style}}>
      <div style={{position: 'absolute', inset: 0, clipPath: outer, background: MAT.memo}}>
        <div style={{position: 'absolute', inset: border, bottom: border + foot, overflow: 'hidden', background: fit === 'contain' ? MAT.memo : MAT.charcoal}}>
          <Img src={file} style={{width: '100%', height: '100%', objectFit: fit, objectPosition: focus, display: 'block'}} />
        </div>
      </div>
      {children}
    </div>
  );
};

/**
 * 오림 스택(템플릿 cutout_stack): 오른쪽 위에서 아래로 흰 테두리 오림 그림이 말에 맞춰 하나씩 내려앉는다.
 * data.cutouts[i].at = 그래픽 시작 기준 초(없으면 고르게), label 은 그림 아래 종이 표찰(그림 폭 안). 오림과 액자를 섞지 않는다 — 한 장이라도 못 오렸으면 전부 액자.
 */
export const CutoutStack: React.FC<{items: CutoutData[]; frame: number; dur: number; fps: number; box: {w: number; h: number}; side?: 'left' | 'right'}> = ({items, frame, dur, fps, box,
  side = 'right'}) => {
  const list = items.slice(0, 4);
  const n = list.length;
  const vertical = box.h > box.w;
  const w = vertical ? 420 : n >= 4 ? 380 : 450;
  const top = vertical ? 300 : 60;
  const bottom = vertical ? 860 : 200;         // 자막 자리 위(y 900 안)에서 표찰까지 끝난다
  const usable = box.h - top - bottom;
  const sticker = list.every((it) => it.cut);
  const h = Math.round(Math.min(w * 0.72, usable / Math.max(1, n) - 26));     // 아래 칸이 표찰을 가리지 않게
  const gap = n > 1 ? (usable - h) / (n - 1) : 0;
  return (
    <div style={{position: 'absolute', inset: 0}}>
      {list.map((it, i) => {
        const r = seeded(i + 41.5);
        const rest = (i % 2 ? 1 : -1) * (1.4 + r() * 1.8);
        const at = it.at !== undefined ? it.at * fps : (i * Math.max(14, dur * 0.72)) / Math.max(1, n);
        const f = frame - at;
        if (f < 0) return null;
        const m = paperSettle(f, rest);
        const shift = r() * 46 * (i % 2 ? 1 : 0.4);    // 안쪽으로만 어긋난다 — 다른 요소처럼 가장자리 64px 안에
        const iw = it.w && it.h ? Math.min(w, Math.round(h * (it.w / it.h))) : w;    // 세로 물건을 가로 칸에 cover 로 넣으면 머리가 잘린다
        const x = side === 'right' ? box.w - 64 - iw - 10 - shift : 64 + 10 + shift;
        return (
          <div key={it.image + i} style={{position: 'absolute', left: x, top: top + i * gap, width: iw, height: h, opacity: m.opacity, translate: `0 ${m.y}px`, scale: `${m.scale}`}}>
            <CutoutFrame src={it.image} w={iw} h={h} seed={i * 3 + 5} rotate={m.rotate} level={m.elev} cut={sticker} fit={it.cut && !sticker ? 'contain' : 'cover'} focus={it.focus} />
            {it.label ? (() => {
              const size = fitSize(it.label, iw - 32, 36, 28, -0.02);
              const lw = Math.min(iw, estWidth(it.label, size, -0.02) + 48);
              return (
                <Sheet x={i % 2 ? 0 : iw - lw} y={h - 40} w={lw} h={60} tex="memo" seed={i + 9} rotate={i % 2 ? -1.5 : 1.2} liftLevel={1.4} torn={{[i % 2 ? 'right' : 'left']: true}} amp={6}>
                  <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: FONT.sans, fontWeight: 700, fontSize: size,
                    letterSpacing: '-0.02em', color: MAT.ink, whiteSpace: 'nowrap'}}>{it.label}</div>
                </Sheet>
              );
            })() : null}
          </div>
        );
      })}
    </div>
  );
};
