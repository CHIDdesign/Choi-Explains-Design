import React from 'react';
import {enter, revealAt} from '../../lib/anim';
import {estWidth, fitBlock, fitSize} from '../../lib/fit';
import {paperSettle} from '../../design/motion';
import {FONT, MAT} from '../../design/tokens';
import type {GraphicData} from '../../lib/types';
import {CutoutFrame} from '../material/Cutout';
import {Attach, Highlighter, PencilStroke} from '../material/Marks';
import type {Pt} from '../material/Marks';
import {Sheet, tornFor} from '../material/Sheet';
import {hashSeed} from '../paper/Paper';
import type {TemplateProps} from './common';

/** estWidth 는 줄바꿈을 넉넉히 잡으려고 한글을 크게 잰다 — 실제 Pretendard 800 글자 폭은 약 0.91배 */
export const GLYPH_K = 0.91;

/** 보드의 제목: 좌상단에 테이프로 붙인 흰 메모 — 키커 + 굵은 제목 + 주황 밑줄의 머리글은 PPT 다 */
export const BoardTitle: React.FC<{text: string; frame: number; box: {w: number; h: number}; compact?: boolean; note?: string}> = ({text, frame, box, compact, note}) => {
  if (!text) return null;
  const size = fitSize(text, box.w * 0.62 - 96, compact ? 44 : 56, 34, -0.02);
  const noteSize = size * 0.8;
  const w = Math.max(estWidth(text, size, -0.02) * GLYPH_K, note ? estWidth(note, noteSize) * 0.74 : 0) + 96;
  const h = size * 1.2 + (note ? noteSize * 1.16 : 0) + 56;
  const seed = hashSeed(text);
  return (
    <Sheet w={w} h={h} tex="memo" seed={seed} m={paperSettle(frame - 2, -1.6)} torn={{bottom: true}} amp={8} on="board" style={{zIndex: 5}}>
      <div style={{position: 'absolute', left: 46, top: 28, fontFamily: FONT.sans, fontWeight: 800, fontSize: size, lineHeight: 1.2, letterSpacing: '-0.02em', color: MAT.ink, whiteSpace: 'nowrap'}}>{text}</div>
      {note ? <div style={{position: 'absolute', left: 48, top: 28 + size * 1.2, fontFamily: FONT.pen, fontSize: noteSize, lineHeight: 1.16, color: MAT.graphite, whiteSpace: 'nowrap'}}>{note}</div> : null}
      <Attach w={w} seed={seed} always tw={130} th={38} />
    </Sheet>
  );
};

export const boardU = (seed: number, i: number) => Math.abs(Math.sin((seed + i) * 12.9898) * 43758.5453) % 1;
/** 보드의 핵심 카드: 지정한 강조 → 마지막 단계 → 끝 항목(결론) */
export const boardKey = (data: GraphicData, n: number) => {
  if (typeof data.highlight === 'number' && data.highlight >= 0 && data.highlight < n) return data.highlight;
  const last = data.stepAt?.[data.stepAt.length - 1]?.index;
  return last !== undefined && last >= 0 && last < n ? last : n - 1;
};
/** 카드 크기: 핵심 1.35배, 나머지 0.85~1.0배 */
export const boardScale = (seed: number, i: number, key: number) => (i === key ? 1.35 : 0.85 + 0.15 * boardU(seed, i));
/** 카드 각도: ±1.5~2.5° */
export const boardRot = (seed: number, i: number) => (boardU(seed, i + 7) < 0.5 ? -1 : 1) * (1.5 + boardU(seed, i + 13));
/** 전면 보드(상자 y 72~910)의 내용 중심: 제목 아래 ~ 자막 위의 가운데, 화면 y 570 */
export const BOARD_CY = 498;
export const fullBoard = (box: {w: number; h: number}, compact?: boolean) => !compact && box.w > 1200;
/** 크기가 다른 카드를 이웃과 overlap 만큼 겹쳐 avail 안에 한 줄로 놓는다: 카드마다 [시작, 길이] */
export const boardRow = (scale: number[], avail: number, overlap: number, cap: number): [number, number][] => {
  const sum = scale.reduce((a, b) => a + b, 0);
  const base = Math.min(cap, (avail + overlap * (scale.length - 1)) / sum);
  let at = Math.max(0, (avail - base * sum + overlap * (scale.length - 1)) / 2);
  return scale.map((k) => {
    const r: [number, number] = [at, base * k];
    at += base * k - overlap;
    return r;
  });
};

/** 핵심 카드에 붙는 그 영상의 실물 오림(data.scraps[0], 긴 변 200~280px). 없으면 클립으로 집는다(pin = 위 변의 자리) — 보드에서 고정된 종이는 제목과 이 카드뿐이다. below = 카드 높이를 주면 아래 변에 걸친다(화살표가 윗변에서 나갈 때) */
export const KeyScrap: React.FC<{data: GraphicData; frame: number; cw: number; seed: number; over?: number; rise?: number; below?: number; pin?: number}> = ({data, frame, cw, seed, over = 0.2, rise = 0.42, below, pin = 0.82}) => {
  const s = data.scraps?.[0];
  if (frame < 0) return null;
  if (!s) return <Attach w={cw} seed={seed} clip={pin} />;
  const a = s.w && s.h ? s.w / s.h : 1.3;
  const L = Math.max(200, Math.min(280, cw * 0.5));
  const [w, h] = a >= 1 ? [L, L / a] : [L * a, L];
  const m = paperSettle(frame, seed % 2 ? 3 : -3);
  return (
    <div style={{position: 'absolute', left: cw - w * (1 - over), top: below !== undefined ? below - h * 0.85 : -h * rise, opacity: m.opacity, translate: `0 ${m.y}px`, scale: `${m.scale}`}}>
      <CutoutFrame src={s.image} w={w} h={h} seed={seed} rotate={m.rotate} level={m.elev} cut={s.cut} />
    </div>
  );
};

// ---------------------------------------------------------------------------
// 목록 — 크기가 다른 종이 띠가 어긋나게 겹쳐 쌓인다. 말하는 항목에 형광펜이 쓸린다
// ---------------------------------------------------------------------------
export const ListCard: React.FC<TemplateProps> = (props) => {
  const {data, frame, dur, box, compact, id} = props;
  const items = (data.items || []).slice(0, 6);
  const n = Math.max(1, items.length);
  const wide = !compact && box.w > 1200;
  const tall = box.h > box.w;
  const seed = hashSeed(id);
  const key = boardKey(data, n);
  const top = data.title ? (compact ? 86 : 132) : 8;
  const run = boardRow(items.map((_, i) => boardScale(seed, i, key)), tall ? 530 : wide ? 2 * (BOARD_CY - top) : box.h - top, 12 + (seed % 13), tall ? 176 : compact ? 110 : 214);     // 숏폼: 가장 낮은 행도 150px, 세로 중심 화면 y 820(상자 위 430)
  const lastShown = items.reduce((acc, _, i) => (frame >= revealAt(i, n, dur) ? i : acc), -1);
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <BoardTitle text={data.title || ''} note={data.subtitle} frame={frame} box={box} compact={compact} />
      {items.map((it, i) => {
        const at = revealAt(i, n, dur);
        if (frame < at) return null;
        const [p, h] = run[i];
        const isKey = i === key;
        const active = i === lastShown;
        const w = tall ? 1000 * (isKey ? 1 : 0.9 + 0.08 * boardU(seed, i + 3)) : box.w * (wide ? 0.74 : 0.92) * (isKey ? 1.08 : 0.84 + 0.16 * boardU(seed, i + 3));
        const x = (box.w - w) * (wide ? (i % 2 ? 0.62 : 0.3) : i % 2 ? 0.9 : 0.08);
        const room = w - 90 - Math.min(h * 0.4, 68) * 1.7;
        const b = fitBlock(it, room, h - 36, tall ? 68 : compact ? 40 : isKey ? 74 : 65, tall ? 56 : 28, 1.18, h > 170 ? 2 : 1, -0.025);
        return (
          <React.Fragment key={i}>
            {isKey ? <Sheet x={x + 22} y={top + p + 14} w={w - 12} h={h} tex="kraft" seed={seed + 2} m={paperSettle(frame - at, 1.8, 11, 14, 1.6)} torn={{right: true}} amp={12} on="board" style={{zIndex: 2}} /> : null}
            <Sheet x={x} y={top + p} w={w} h={h} tex="memo" seed={seed + i * 5} m={paperSettle(frame - at, boardRot(seed, i))} torn={{[i % 2 ? 'right' : 'bottom']: true}} amp={9} on="board" style={{zIndex: isKey ? 3 : 1}}>
              <div style={{position: 'absolute', left: 44, right: 36, top: 0, bottom: 0, display: 'flex', alignItems: 'center', gap: 26}}>
                <div style={{fontFamily: FONT.sans, fontWeight: 900, fontSize: b.size * 1.2, lineHeight: 1, flex: 'none', color: active ? MAT.orange : 'rgba(34,33,30,0.38)', fontVariantNumeric: 'tabular-nums'}}>{i + 1}</div>
                <div style={{position: 'relative', fontFamily: FONT.sans, fontWeight: active ? 800 : 600, fontSize: b.size, lineHeight: 1.18, letterSpacing: '-0.025em', color: MAT.ink}}>
                  {active ? <Highlighter x={-8} y={b.size * 0.56} w={estWidth(b.lines[0], b.size, -0.025) + 16} h={b.size * 0.56} p={enter(frame, at + 3, 12)} /> : null}
                  {b.lines.map((l, k) => <div key={k} style={{position: 'relative', whiteSpace: 'nowrap'}}>{l}</div>)}
                </div>
              </div>
              {isKey ? <KeyScrap data={data} frame={frame - at - 6} cw={w} seed={seed} /> : null}
            </Sheet>
          </React.Fragment>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 비교 A vs B — 어긋나게 겹친 두 장
// ---------------------------------------------------------------------------
export const CompareCard: React.FC<TemplateProps> = (props) => {
  const {data, frame, dur, box, compact, id} = props;
  const a = (data.items || []).slice(0, 4);
  const b = (data.items_b || []).slice(0, 4);
  const seed = hashSeed(id);
  const tall = box.h > box.w;
  const top = data.subtitle ? (compact ? 86 : 132) : 0;
  const full = fullBoard(box, compact);
  const cw = full ? (box.w + 24) / 2 : box.w * (tall ? 0.92 : 0.54);       // 전면: 두 장이 24px 겹친다
  const headSize = Math.min(fitSize(data.title || '', cw - 120, compact ? 66 : 140, 36, -0.02), fitSize(data.title_b || '', cw - 120, compact ? 66 : 140, 36, -0.02));
  const itemSize = compact ? 32 : 56;
  const itemTop = compact ? 112 : tall ? 170 : full ? 252 : 226;
  const rowGap = itemSize * (tall ? 1.5 : 1.72);
  const ch = tall ? (box.h - top + 30) / 2 : Math.min(box.h - top - 44, itemTop + Math.max(a.length, b.length) * rowGap + 64);
  const y0 = full ? Math.max(10, BOARD_CY - top - (ch + 24) / 2) : 10;
  const half = Math.round(dur * 0.16);
  const col = (head: string, items: string[], start: number, x: number, y: number, tex: 'memo' | 'forest', rest: number, s: number) => {
    const m = paperSettle(frame - start, rest, 12);
    const fg = tex === 'forest' ? '#FFFFFF' : MAT.ink;
    return (
      <Sheet x={x} y={y} w={cw} h={ch} tex={tex} seed={s} m={m} torn={tornFor(s)} amp={9} on="board">
        <div style={{position: 'absolute', left: 60, top: compact ? 34 : 54, fontFamily: FONT.sans, fontWeight: 900, fontSize: headSize, lineHeight: 1.05, letterSpacing: '-0.02em', color: fg, whiteSpace: 'nowrap'}}>{head}</div>
        {items.map((it, i) => (
          <div key={i} style={{position: 'absolute', left: 60, right: 40, top: itemTop + i * rowGap, fontFamily: FONT.sans, fontWeight: 500, fontSize: Math.min(itemSize, fitSize(it, cw - 100, itemSize, 28, -0.02)), lineHeight: 1.2, letterSpacing: '-0.02em', color: fg,
            whiteSpace: 'nowrap', opacity: enter(frame, start + 8 + i * 5, 10)}}>{it}</div>
        ))}
        {tex === 'forest' ? <Attach w={cw} seed={s} clip={0.86} /> : null}
      </Sheet>
    );
  };
  return (
    <div style={{position: 'absolute', inset: 0}}>
      {data.subtitle ? <BoardTitle text={data.subtitle} frame={frame} box={box} compact={compact} /> : null}
      <div style={{position: 'absolute', left: 0, top, width: box.w, height: box.h - top}}>
        {col(data.title || 'A', a, 2, 0, y0, 'memo', -1.6, seed)}
        {col(data.title_b || 'B', b, 2 + half, box.w - cw, tall ? ch - 20 : y0 + 24, 'forest', 1.9, seed + 5)}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 연표 — 연필 축을 사이에 두고 번갈아 놓인 크기가 다른 종이 표찰, 이웃과 모서리가 겹친다
// ---------------------------------------------------------------------------
export const TimelineCard: React.FC<TemplateProps> = (props) => {
  const {data, frame, dur, box, compact, id} = props;
  const items = (data.items || []).slice(0, 6).map((s) => {
    const [y, ...rest] = s.split('|');
    return rest.length ? {year: y.trim(), label: rest.join('|').trim()} : {year: '', label: s.trim()};
  });
  const n = Math.max(1, items.length);
  const seed = hashSeed(id);
  const key = boardKey(data, n);
  const titleH = data.title ? (compact ? 86 : 132) : 0;
  const lineY = fullBoard(box, compact) ? BOARD_CY : titleH + (box.h - titleH) * (compact ? 0.52 : 0.44);
  const lineP = enter(frame, 4, Math.max(20, dur * 0.25));
  const scale = items.map((_, i) => boardScale(seed, i, key));
  const run = boardRow(scale, box.w, 12 + (seed % 13), compact ? 300 : 480);
  const baseH = Math.min((box.h - titleH) * 0.34, compact ? 140 : 222);
  const lastShown = items.reduce((acc, _, i) => (frame >= revealAt(i, n, dur) ? i : acc), -1);
  const axis: Pt[] = [[0, lineY], [box.w * 0.5, lineY - 4], [box.w, lineY + 3]];
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <BoardTitle text={data.title || ''} note={data.subtitle} frame={frame} box={box} compact={compact} />
      <svg width={box.w} height={box.h} style={{position: 'absolute', inset: 0, overflow: 'visible', mixBlendMode: 'multiply', zIndex: 0}}>
        <PencilStroke pts={axis} p={lineP} width={4} seed={seed} />
      </svg>
      {items.map((it, i) => {
        const at = revealAt(i, n, dur);
        if (frame < at) return null;
        const active = i === lastShown;
        const [x, tagW] = run[i];
        const tagH = compact ? baseH * scale[i] : i === key ? 200 : 176;     // 연도와 낱말만 있는 표찰은 내용 높이로
        const up = i % 2 === 0;
        const y = compact ? (up ? lineY + 8 - tagH : lineY - 8) : up ? lineY - 14 - tagH : lineY + 14;     // 축은 표찰 밑으로 지나간다 — 전면에서는 축이 보이게 띄운다
        const labelBlock = fitBlock(it.label, tagW - 56, compact ? tagH * 0.46 : tagH - 122, (compact ? 30 : 42) * Math.min(1.2, scale[i]), 28, 1.26, 2, -0.02);
        const fg = active ? '#FFFFFF' : MAT.ink;
        return (
          <Sheet key={i} x={x} y={y} w={tagW} h={tagH} tex={active ? 'forest' : 'memo'} seed={seed + i * 5} m={paperSettle(frame - at, boardRot(seed, i), 10)} torn={tornFor(seed + i * 5)} amp={7} on="board" style={{zIndex: i === key ? 2 : 1}}>
            <div style={{position: 'absolute', left: 28, top: compact ? 22 : 14, fontFamily: FONT.sans, fontWeight: 900, fontSize: compact ? 48 * Math.min(1.25, scale[i]) : fitSize(it.year, tagW - 56 - (i === key && data.scraps?.length ? Math.max(200, Math.min(280, tagW * 0.5)) : 0), 104, 60, -0.02), lineHeight: 1, letterSpacing: '-0.02em', color: active ? MAT.mint : MAT.forest, fontVariantNumeric: 'tabular-nums'}}>{it.year}</div>
            <div style={{position: 'absolute', left: 28, right: 26, bottom: compact ? 24 : 16, fontFamily: FONT.sans, fontWeight: active ? 700 : 600, fontSize: labelBlock.size, lineHeight: 1.28, letterSpacing: '-0.02em', color: fg}}>
              {labelBlock.lines.map((l, k) => <div key={k}>{l}</div>)}
            </div>
            {i === key ? <KeyScrap data={data} frame={frame - at - 6} cw={tagW} seed={seed} over={0} /> : null}
          </Sheet>
        );
      })}
    </div>
  );
};
