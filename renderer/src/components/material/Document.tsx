import React from 'react';
import {Img, interpolate} from 'remotion';
import {EASE, photoPush} from '../../design/motion';
import {FONT, MAT} from '../../design/tokens';
import type {MapFn, Rect} from '../../lib/crop';
import type {Archive, EvidenceAsset, NBox} from '../../lib/types';
import {Attach, Highlighter} from './Marks';
import {Sheet} from './Sheet';
import {GrainLayer, texFill, useInkOnPaper, useMaterials} from './Texture';

const TILT = -1.4;
const PAPER_H = {doc: 0.82, print: 800 / 1080};   // 네 변과 그림자가 다 보이게: 문서는 자막 위(y 925)에서 끝나고, 인화지는 3% 푸시까지 그 안에
const DOC_MARGIN = 0.08;   // 스캔은 여백을 잘라 오므로 글이 종이 끝까지 찬다 — 문서는 종이 폭의 8% 를 둘레에 둔다
const DOC_ZOOM = 1.25;     // 책상이 화면의 63% 면 빈 면을 보게 된다: 통째로 놓인 뒤 밀려 들어가 위아래가 프레임 밖으로 나간다
const BLEED = 60;          // 밀려 들어간 종이의 끝은 프레임 밖 60px 이상(자막 상자에 아래 변이 맞닿는 접선을 만들지 않는다)
const CAPTION_Y = 925;
const MARK_ROOM = 240;     // 표시한 줄 아래로 남겨야 할 종이(확대 뒤) — 그보다 낮은 줄이면 종이를 밖으로 내보내지 않고 자막 위에서 끝낸다
const LINE_PX = 46;        // 핵심 줄의 글자 높이 목표
const ZOOM_MAX = 1.6;
const PRINT_SEED = 4;

/**
 * 문서·세로 자료: 구김 있는 인쇄물이 통째로 책상 위에 놓여 있고(print 텍스처를 곱해 접힌 자국이 글자에 내린다) 형광펜이 말에 맞춰 줄을 쓸어 간다.
 * lines = 밑줄 칠 줄(문서 기준 0~1). lineAt = 줄마다 시작 초(말에 맞춘 값, 없으면 0.5초부터 순서대로). 문서는 첫 0.7초 통째로(네 변과 그림자) 보인 뒤 표시한 줄 쪽으로 밀려 들어간다.
 * markY = 밑줄은 아니지만 화면에 있어야 할 표시의 높이(문서 기준 0~1).
 */
export const DeskDocument: React.FC<{asset: EvidenceAsset; lines?: NBox[]; lineAt?: number[]; markY?: number; W: number; H: number; frame: number; dur: number; fps: number; accent?: string; clearLeft?: number;
  children?: (map: MapFn, view: Rect) => React.ReactNode}> = ({asset, lines = [], lineAt, markY, W, H, frame, dur, fps, accent = MAT.orange, clearLeft = 0, children}) => {
  useMaterials();
  const doc = asset.kind === 'document';
  const r = doc ? DOC_MARGIN / (1 - 2 * DOC_MARGIN) : 0;                     // 그림 폭에 대한 여백의 비
  const aw = Math.max(1, asset.w);
  const k = Math.min(W * 0.66 / (aw * (1 + 2 * r)), (H * (doc ? PAPER_H.doc : PAPER_H.print)) / (Math.max(1, asset.h) + 2 * r * aw));
  const w = aw * k;
  const h = asset.h * k;
  const m = r * w;
  const paperW = w + 2 * m;
  const paperH = h + 2 * m;
  const top = Math.max(16, (H - 130 - paperH) / 2);
  const f0 = Math.round(0.5 * fps);
  const left = (W - paperW) / 2 + W * 0.04;
  const rad = (TILT * Math.PI) / 180;
  const sheetX = Math.min(left - 60, Math.max(left - 330, clearLeft));     // 슈퍼의 흰 글자는 어두운 책상 위에 남는다
  const map: MapFn = (nx, ny) => {     // 문서는 기울어져 놓여 있다 — 좌표도 같이 돌린다
    const dx = (nx - 0.5) * w;
    const dy = (ny - 0.5) * h;
    return [left + paperW / 2 + dx * Math.cos(rad) - dy * Math.sin(rad), top + paperH / 2 + dx * Math.sin(rad) + dy * Math.cos(rad)];
  };
  const key = doc ? lines[0] : undefined;
  const ny = key ? key[1] + key[3] / 2 : doc ? markY : undefined;
  const oy = ny !== undefined ? top + m + ny * h : top + paperH * 0.42;
  const bleed = Math.max(DOC_ZOOM, (H + 2 * BLEED) / paperH);
  const keep = (top + paperH + 1 - oy) > 0 ? (CAPTION_Y - oy) / (top + paperH - oy) : DOC_ZOOM;
  const base = bleed <= ZOOM_MAX && (top + paperH - oy) * bleed >= (ny === undefined ? 0 : MARK_ROOM) ? bleed : Math.max(1, Math.min(DOC_ZOOM, keep));
  const zoom = !doc ? 1 : key ? Math.max(base, Math.min(ZOOM_MAX, LINE_PX / Math.max(1, key[3] * h))) : base;
  const zp = doc ? interpolate(frame, [0.7 * fps, 2 * fps], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: EASE.move}) : 0;
  const ox = left + paperW / 2;
  const paperTop = oy + (top - oy) * zoom;
  const paperBot = oy + (top + paperH - oy) * zoom;
  const ty = doc && paperBot - paperTop > H ? Math.min(-paperTop - BLEED, Math.max(H - paperBot + BLEED, H * 0.42 - oy)) : 0;       // 줄을 위쪽 42% 로 데려오되 종이 끝이 프레임 안에 들어오지 않게
  const view: Rect = {x: ox - ox / zoom, y: oy - (oy + ty) / zoom, w: W / zoom, h: H / zoom};
  const ink = useInkOnPaper(asset.src, doc, {w: paperW, h: paperH, seed: PRINT_SEED}, {x: m, y: m, w, h});
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', ...texFill('desk')}}>
      <GrainLayer opacity={0.1} />
      <div style={{position: 'absolute', inset: 0, translate: `0 ${(ty * zp).toFixed(2)}px`, scale: `${photoPush(frame, dur) * (1 + (zoom - 1) * zp)}`, transformOrigin: doc ? `${ox}px ${oy}px` : '50% 42%'}}>
        {doc ? null : <Sheet x={sheetX} y={-70} w={left + paperW + 290 - sheetX} h={1250} tex="graph" seed={7} rotate={-0.7} liftLevel={3} torn={{left: true}} amp={16} />}{/* 세로 사진은 평평한 책상 한가운데에 슬라이드처럼 놓이지 않는다: 모눈 작업지 위의 인화지 */}
        <div style={{position: 'absolute', left, top, width: paperW, height: paperH, rotate: `${TILT}deg`, boxShadow: doc ? '0 18px 40px rgba(0,0,0,0.55), 0 2px 3px rgba(0,0,0,0.6)' : '3px 16px 30px rgba(40,34,24,0.42), 0 1px 2px rgba(40,34,24,0.55)', background: doc ? MAT.parchment : MAT.memo}}>
          <Img src={ink} style={{position: 'absolute', left: m, top: m, width: w, height: h, display: 'block', mixBlendMode: doc ? 'multiply' : undefined, opacity: doc ? 0.86 : 1}} />{/* 잉크는 종이에 곱해진다 — 위에 얹힌 활자처럼 보이지 않게 */}
          <div style={{position: 'absolute', inset: 0, ...texFill('print', PRINT_SEED, paperW, paperH), mixBlendMode: 'multiply', opacity: doc ? 1 : 0.5}} />
          <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(115deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0) 42%, rgba(24,20,16,0.12) 100%)'}} />
          {lines.map(([x, y, lw, lh], i) => {
            const at = lineAt?.[i] !== undefined ? lineAt[i] * fps : f0 + i * 6;
            const p = interpolate(frame, [at, at + 12], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
            return <Highlighter key={i} x={m + x * w} y={m + y * h - lh * h * 0.12} w={lw * w} h={lh * h * 1.24} p={p} color={accent} />;
          })}
        </div>
        {children?.(map, view)}
      </div>
    </div>
  );
};

/** 자료 카드: 책상 위 목록 카드(논문·책·못 구한 자료의 서지) */
export const ArchiveSheet: React.FC<{archive: Archive; fallbackLabel?: string; W: number; H: number; seed?: number}> = ({archive, fallbackLabel = '', W, H, seed = 3}) => {
  useMaterials();
  const k = W / 1920;
  const label = archive.label || fallbackLabel;
  const rows = archive.rows ?? [];
  const cw = 1320;
  const ch = 620;
  return (
    <div style={{position: 'absolute', left: 0, top: (H - 1080 * k) / 2, width: 1920, height: 1080, scale: `${k}`, transformOrigin: '0 0', overflow: 'hidden', ...texFill('desk')}}>
      <GrainLayer opacity={0.1} />
      <Sheet x={300} y={170} w={cw} h={ch} tex="parchment" seed={seed} rotate={-1.2} liftLevel={2.8} style={{wordBreak: 'keep-all'}}>
        <div style={{position: 'absolute', left: 0, right: 0, top: 64, height: 3, background: MAT.orange, opacity: 0.7}} />
        {label ? <div style={{position: 'absolute', left: 92, top: 96, fontFamily: FONT.pen, fontSize: 56, lineHeight: 1, color: MAT.forest}}>{label}</div> : null}
        <div style={{position: 'absolute', left: 92, right: 92, top: 172, fontFamily: FONT.sans, fontWeight: 800, fontSize: 68, lineHeight: 1.24, letterSpacing: '-0.02em', color: MAT.ink}}>{archive.title}</div>
        <div style={{position: 'absolute', left: 92, right: 92, bottom: 66}}>
          {rows.map((r, i) => (
            <div key={i} style={{display: 'flex', gap: 28, fontFamily: FONT.sans, fontWeight: 500, fontSize: 38, lineHeight: 1.56, color: MAT.ink}}>
              <span style={{width: 130, flex: 'none', fontWeight: 700, color: MAT.forest}}>{r.k}</span>
              <span>{r.v}</span>
            </div>
          ))}
        </div>
        <Attach w={cw} seed={seed} tw={200} th={52} />
      </Sheet>
    </div>
  );
};
