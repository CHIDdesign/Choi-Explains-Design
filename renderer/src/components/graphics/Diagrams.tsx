import React, {useMemo} from 'react';
import {enter, revealAt} from '../../lib/anim';
import {fitBlock, fitSize} from '../../lib/fit';
import {paperSettle} from '../../design/motion';
import {FONT, MAT} from '../../design/tokens';
import {bend, Hatch, PencilArrow, PencilStroke, ringPts} from '../material/Marks';
import type {Pt} from '../material/Marks';
import {Sheet, tornFor} from '../material/Sheet';
import type {Edges} from '../material/Sheet';
import {hashSeed} from '../paper/Paper';
import {BOARD_CY, boardKey, boardRot, boardRow, boardScale, BoardTitle, fullBoard, KeyScrap} from './Lists';
import type {TemplateProps} from './common';

// 디자인 v5.1 도식 보드: 양피지 위 연필 선·해치, 항목은 크기·각도가 다른 종이 표찰. 말하는 단계의 표찰만 숲색으로 바뀐다.

const titleSpace = (props: TemplateProps) => (props.data.title ? (props.compact ? 76 : 124) : 0);

/** 현재 강조 인덱스: 단계 그래픽(stepAt)이면 지금 프레임까지 말한 마지막 단계 — 강조가 그 낱말에서 바뀐다
 * (docs/upgrade/05 6-5: 단계마다 그래픽을 새로 띄우면 강조가 말보다 4~6초 늦었다). 아니면 highlight, 없으면 -1. */
const hl = (props: TemplateProps) => {
  const steps = props.data.stepAt;
  if (steps && steps.length) {
    const t = props.frame / props.fps;
    let cur = -1;
    for (const s of steps) {
      if (t >= s.t) cur = s.index;
    }
    return cur;
  }
  return typeof props.data.highlight === 'number' && props.data.highlight >= 0 ? props.data.highlight : -1;
};

/** 강조 모드인가(항목을 한꺼번에 세우고 강조만 옮김) — 단계 그래픽은 첫 단계 전에도 강조 모드 그대로(중간에 등장 방식이 바뀌지 않게) */
const stepped = (props: TemplateProps) =>
  (props.data.stepAt?.length ?? 0) > 0 || (typeof props.data.highlight === 'number' && props.data.highlight >= 0);

const seedRot = (seed: number, i: number, span = 1.5) => {
  const u = Math.abs(Math.sin((seed + i) * 12.9898) * 43758.5453) % 1;
  const v = (u * 2 - 1) * span;
  return Math.abs(v) < 0.6 ? (v < 0 ? -0.6 : 0.6) : v;
};

type Card = {cx: number; cy: number; w: number; h: number; rot: number};

/** 기울어진 카드 위의 점: ux·uy 는 -1(왼·위) ~ 1(오른·아래) */
const onCard = (c: Card, ux: number, uy: number): Pt => {
  const a = (c.rot * Math.PI) / 180;
  const [dx, dy] = [(ux * c.w) / 2, (uy * c.h) / 2];
  return [c.cx + dx * Math.cos(a) - dy * Math.sin(a), c.cy + dx * Math.sin(a) + dy * Math.cos(a)];
};

const insideCard = (c: Card, [x, y]: Pt) => {
  const a = (-c.rot * Math.PI) / 180;
  const [dx, dy] = [x - c.cx, y - c.cy];
  return Math.abs(dx * Math.cos(a) - dy * Math.sin(a)) <= c.w / 2 + 1 && Math.abs(dx * Math.sin(a) + dy * Math.cos(a)) <= c.h / 2 + 1;
};

const between = (v: number) => Math.min(0.85, Math.max(-0.85, v));

/** 겹쳐 놓인 이웃 사이의 화살표: 앞 카드의 위·아래 변에서 나와 뒤 카드의 왼 변에 닿는다(세로 배치면 옆 변에서 나와 윗변에). 카드가 겹치는 틈으로는 지나가지 않는다 */
const hook = (a: Card, b: Card, tall: boolean): Pt[] => {
  if (tall) {
    const s = Math.sign(b.cx - a.cx) || 1;
    const start = onCard(a, s, 0.55);
    const end = onCard(b, between(((a.cx + (s * a.w) / 2 + b.cx + (s * b.w) / 2) / 2 - b.cx) / (b.w / 2)), -1);
    return [start, [end[0], start[1]], end];
  }
  const s = Math.sign(b.cy - a.cy) || 1;
  const start = onCard(a, 0.6, s);
  const end = onCard(b, -1, between(((a.cy + (s * a.h) / 2 + b.cy + (s * b.h) / 2) / 2 - b.cy) / (b.h / 2)));
  return [start, [start[0], end[1]], end];
};

/** 지금 단계 표찰 뒤로 삐져나오는 연필 해치(도면의 그림자) */
const shade = (c: Card): Pt[] => ([[-1, -1], [1, -1], [1, 1], [-1, 1]] as const).map(([u, v]): Pt => {
  const [x, y] = onCard(c, u, v);
  return [x + 20, y + 20];
});

/** 종이 표찰: on 이면 숲색 종이 + 흰 글자. 글은 왼쪽 아래 — 가운데 정렬 라벨은 SmartArt 다 */
const Tag: React.FC<{c: Card; seed: number; i: number; on: boolean; frame: number; at: number; top?: boolean; torn: Edges; amp?: number; outer?: Pt;
  children: (fg: string, sub: string) => React.ReactNode}> = ({c, seed, i, on, frame, at, top = false, torn, amp = 9, outer, children}) => {
  if (frame < at) return null;
  const m = paperSettle(frame - at, c.rot, 11, 14, on ? 2.4 : 1.8);
  return (
    <Sheet x={c.cx - c.w / 2} y={c.cy - c.h / 2} w={c.w} h={c.h} tex={on ? 'forest' : 'memo'} seed={seed + i * 5} m={m} torn={torn} amp={amp} on="board" style={{zIndex: top ? 3 : 1}}>
      <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: outer?.[0] === 1 ? 'flex-end' : 'flex-start', justifyContent: outer?.[1] === -1 ? 'flex-start' : 'flex-end', wordBreak: 'keep-all', padding: '22px 30px', boxSizing: 'border-box', textAlign: outer?.[0] === 1 ? 'right' : 'left'}}>
        {children(on ? '#FFFFFF' : MAT.ink, on ? MAT.mint : MAT.forest)}
      </div>
    </Sheet>
  );
};

const Lines: React.FC<{text: string; maxW: number; maxH: number; size: number; color: string; on: boolean; min?: number}> = ({text, maxW, maxH, size, color, on, min = 28}) => {
  const b = fitBlock(text, maxW, maxH, size, min, 1.22, 3, -0.025);
  return (
    <div style={{fontFamily: FONT.sans, fontWeight: on ? 800 : 700, fontSize: b.size, lineHeight: 1.22, letterSpacing: '-0.025em', color}}>
      {b.lines.map((l, i) => <div key={i} style={{whiteSpace: 'nowrap'}}>{l}</div>)}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 단계 프로세스 — 크기가 다른 표찰이 어긋나게 겹치고, 연필 화살표가 가장자리에서 가장자리로 잇는다
// ---------------------------------------------------------------------------
export const ProcessDiagram: React.FC<TemplateProps> = (props) => {
  const {data, frame, dur, box, id, compact} = props;
  const items = (data.items || []).slice(0, 7);
  const n = Math.max(1, items.length);
  const top = titleSpace(props);
  const h = box.h - top;
  const seed = hashSeed(id);
  const tall = box.h > box.w;
  const key = boardKey(data, n);
  const scale = items.map((_, i) => boardScale(seed, i, key));
  const run = boardRow(scale, tall ? h : box.w, 12 + (seed % 13), tall ? 300 : compact ? 250 : 470);
  const active = hl(props);
  const cardH = (i: number) => (i === key ? 200 : 176);        // 숫자와 낱말만 있는 카드는 내용 높이로 — 큰 빈 카드는 종이를 입힌 PPT 다
  const cards: Card[] = items.map((_, i) => {
    const [p, len] = run[i];
    const rot = boardRot(seed, i);
    if (tall) {
      const w = Math.min(box.w * 0.86, len * 2.4);
      return {cx: i % 2 ? box.w - w / 2 : w / 2, cy: top + p + len / 2, w, h: cardH(i), rot};
    }
    return {cx: p + len / 2, cy: top + h * 0.53 + (i % 2 ? -1 : 1) * h * 0.13, w: len, h: compact ? len * 0.8 : cardH(i), rot};      // 첫 표찰이 낮아야 왼쪽 위 제목 메모와 안 부딪친다
  });
  const at = (i: number) => (stepped(props) ? 4 + i * 5 : revealAt(i, n, dur, 6) * 0.7);
  const NUM = 127;                                              // 큰 숫자 칸(왼쪽 여백 30 + 숫자 75 + 사이 22)
  const room = (i: number, c: Card) => (i === key && data.scraps?.length ? Math.min(230, c.w * 0.42) : 28);    // 핵심 카드의 오른쪽은 실물 조각 자리
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <BoardTitle text={data.title || ''} note={data.subtitle} frame={frame} box={box} compact={compact} />
      <svg width={box.w} height={box.h} style={{position: 'absolute', inset: 0, overflow: 'visible', mixBlendMode: 'multiply'}}>
        {active >= 0 && active < n ? <Hatch key={active} poly={shade(cards[active])} gap={9} width={2.2} p={enter(frame, 6, 12)} seed={seed + active} /> : null}
        {cards.slice(0, -1).map((c, i) => <PencilArrow key={i} pts={hook(c, cards[i + 1], tall)} p={enter(frame, at(i + 1) - 2, 12)} width={4} seed={seed + i} head={22} />)}
      </svg>
      {items.map((it, i) => {
        const c = cards[i];
        return (
          <Tag key={i} c={c} seed={seed} i={i} on={i === active} frame={frame} at={at(i)} top={i === key} torn={tall ? {bottom: true} : {[i % 2 ? 'top' : 'bottom']: true}}>
            {(fg, sub) => (
              <>
                {compact ? <div style={{position: 'absolute', left: 30, top: 22, fontFamily: FONT.sans, fontWeight: 900, fontSize: 52 * Math.min(1.25, scale[i]), lineHeight: 1, letterSpacing: '-0.02em', color: sub, fontVariantNumeric: 'tabular-nums'}}>{i + 1}</div> : (
                  <div style={{position: 'absolute', left: 30, top: 0, bottom: 0, display: 'flex', alignItems: 'center', fontFamily: FONT.sans, fontWeight: 900, fontSize: 110, lineHeight: 1, letterSpacing: '-0.02em', color: sub, fontVariantNumeric: 'tabular-nums'}}>{i + 1}</div>
                )}
                {compact ? <Lines text={it} maxW={c.w - 64} maxH={c.h * 0.46} size={32 * Math.min(1.3, scale[i])} color={fg} on={i === active} /> : (
                  <div style={{position: 'absolute', left: NUM, right: room(i, c), top: 0, bottom: 0, display: 'flex', alignItems: 'center'}}>
                    <Lines text={it} maxW={c.w - NUM - room(i, c)} maxH={c.h - 44} size={(tall ? 60 : 50) * Math.min(1.3, scale[i])} color={fg} on={i === active} />
                  </div>
                )}
                {i === key ? <KeyScrap data={data} frame={frame - at(i) - 6} cw={c.w} seed={seed} over={i === n - 1 ? 0.2 : 0} below={!tall && i % 2 === 0 && i < n - 1 ? c.h : undefined} /> : null}
              </>
            )}
          </Tag>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 순환 구조 — 표찰 사이를 연필 호가 가장자리에서 가장자리로 잇는다(원 위 표찰은 겹치면 호가 지나갈 자리가 없다)
// ---------------------------------------------------------------------------
export const CycleDiagram: React.FC<TemplateProps> = (props) => {
  const {data, frame, box, id, compact} = props;
  const items = (data.items || []).slice(0, 6);
  const n = Math.max(2, items.length);
  const top = titleSpace(props);
  const h = box.h - top;
  const cx = box.w / 2;
  const big = fullBoard(box, compact);
  const cy = big ? BOARD_CY : top + h / 2;
  const R = Math.min(h * (big ? 0.385 : 0.37), box.w * 0.3);
  const seed = hashSeed(id);
  const active = hl(props);
  const key = boardKey(data, n);
  const ell = (deg: number): Pt => [cx + R * 1.28 * Math.cos((deg * Math.PI) / 180), cy + R * Math.sin((deg * Math.PI) / 180)];
  const deg = (i: number) => -90 + (360 / n) * i;
  const cards: Card[] = items.map((_, i) => {
    const k = boardScale(seed, i, key);
    const [x, y] = ell(deg(i));
    return {cx: x, cy: y, w: Math.min(R * 0.95, compact ? 210 : 300) * k * (big ? 1.13 : 1), h: big ? (i === key ? 200 : 170) : (compact ? 92 : 124) * k, rot: boardRot(seed, i)};
  });
  const arc = (i: number): Pt[] => {
    const out: Pt[] = [];
    for (let a = deg(i); a <= deg(i + 1); a += 1.5) {
      const p = ell(a);
      if (!insideCard(cards[i], p) && !insideCard(cards[(i + 1) % n], p)) out.push(p);
    }
    return out;
  };
  const at = (i: number) => (stepped(props) ? 4 + i * 4 : 4 + i * 9);
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <BoardTitle text={data.title || ''} note={data.subtitle} frame={frame} box={box} compact={compact} />
      <svg width={box.w} height={box.h} style={{position: 'absolute', inset: 0, overflow: 'visible', mixBlendMode: 'multiply'}}>
        {active >= 0 && active < n ? <Hatch key={active} poly={shade(cards[active])} gap={9} width={2.2} p={enter(frame, 6, 12)} seed={seed + active} /> : null}
        {items.map((_, i) => {
          const pts = arc(i);
          return pts.length >= 4 ? <PencilArrow key={i} pts={pts} p={enter(frame, at(i) + 4, 14)} width={4} seed={seed + i * 3} head={22} /> : null;
        })}
      </svg>
      {items.map((it, i) => (
        <Tag key={i} c={cards[i]} seed={seed} i={i} on={i === active} frame={frame} at={at(i)} top={i === key} torn={tornFor(seed + i * 5)} amp={6}>
          {(fg) => (
            <>
              <Lines text={it} maxW={cards[i].w - 60} maxH={cards[i].h - 40} size={(compact ? 32 : 46) * Math.min(1.3, boardScale(seed, i, key))} color={fg} on={i === active} />
              {i === key ? <KeyScrap data={data} frame={frame - at(i) - 6} cw={cards[i].w} seed={seed} over={0.5} /> : null}
            </>
          )}
        </Tag>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 더블 다이아몬드 (Design Council, 2005) — 연필 윤곽, 지금 단계에 해치
// ---------------------------------------------------------------------------
export const DoubleDiamond: React.FC<TemplateProps> = (props) => {
  const {data, frame, dur, box, id, compact} = props;
  const labels = (data.items && data.items.length === 4 ? data.items : ['발견', '정의', '개발', '전달']);
  const phases = ['발산', '수렴', '발산', '수렴'];
  const top = titleSpace(props);
  const h = box.h - top;
  const W = box.w;
  const midY = top + h * (compact ? 0.46 : 0.47);        // 왼쪽 위 제목 메모와 첫 '발산' 사이를 띄운다
  const dh = Math.min(h * (compact ? 0.24 : 0.32), W * 0.14);
  const x0 = W * 0.02;
  const q = (W * 0.96) / 4;
  const xs = [x0, x0 + q, x0 + 2 * q, x0 + 3 * q, x0 + 4 * q];
  const active = hl(props);
  const seed = hashSeed(id);
  const diamond = (a: number, b: number, c: number): Pt[] => [[a, midY], [b, midY - dh], [c, midY], [b, midY + dh], [a, midY]];
  const quarter = (i: number): Pt[] => (i % 2 === 0
    ? [[xs[i], midY], [xs[i + 1], midY - dh], [xs[i + 1], midY + dh]]
    : [[xs[i], midY - dh], [xs[i + 1], midY], [xs[i], midY + dh]]);
  const drawP1 = enter(frame, 4, Math.max(20, dur * 0.22));
  const drawP2 = enter(frame, 10, Math.max(20, dur * 0.22));
  const labelSize = compact ? 36 : 52;
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <BoardTitle text={data.title || '더블 다이아몬드'} note={data.subtitle} frame={frame} box={box} compact={compact} />
      <svg width={W} height={box.h} style={{position: 'absolute', inset: 0, overflow: 'visible', mixBlendMode: 'multiply'}}>
        {active >= 0 ? <Hatch key={active} poly={quarter(active)} gap={13} color={MAT.orange} width={3} p={enter(frame, 8, 14)} seed={seed + active} /> : null}
        <PencilStroke pts={diamond(xs[0], xs[1], xs[2])} p={drawP1} width={4.4} seed={seed} />
        <PencilStroke pts={diamond(xs[2], xs[3], xs[4])} p={drawP2} width={4.4} seed={seed + 3} />
        {[1, 2, 3].map((k) => <PencilStroke key={k} pts={[[xs[k], midY - dh - 30], [xs[k], midY + dh + 30]]} p={enter(frame, 14 + k * 2, 10)} width={1.8} seed={seed + k * 7} wobble={0.9} />)}
      </svg>
      {labels.map((l, i) => {
        const on = i === active;
        const cx = (xs[i] + xs[i + 1]) / 2;
        return (
          <React.Fragment key={i}>
            <div style={{position: 'absolute', left: cx - q / 2, width: q, top: midY - dh - (compact ? 54 : 84), textAlign: 'center', fontFamily: FONT.pen, fontSize: compact ? 40 : 62, lineHeight: 1, color: MAT.graphite,
              opacity: enter(frame, 16 + i * 3, 10)}}>{phases[i]}</div>
            <div style={{position: 'absolute', left: cx - q / 2, width: q, top: midY + dh + (compact ? 22 : 38), textAlign: 'center', fontFamily: FONT.sans, fontSize: labelSize, fontWeight: on ? 900 : 700, lineHeight: 1.1, letterSpacing: '-0.02em',
              color: on ? MAT.orange : MAT.ink, opacity: enter(frame, 18 + i * 3, 10)}}>{l}</div>
            {!compact ? (
              <div style={{position: 'absolute', left: cx - q / 2, width: q, top: midY + dh + 38 + labelSize * 1.2, textAlign: 'center', fontFamily: FONT.sans, fontWeight: 600, fontSize: 28, letterSpacing: '0.08em', color: MAT.inkSoft,
                opacity: enter(frame, 20 + i * 3, 10)}}>{['DISCOVER', 'DEFINE', 'DEVELOP', 'DELIVER'][i]}</div>
            ) : null}
          </React.Fragment>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 2x2 매트릭스 — 연필 십자축 위에 네 장이 가운데서 겹쳐 놓인다
// ---------------------------------------------------------------------------
export const MatrixDiagram: React.FC<TemplateProps> = (props) => {
  const {data, frame, box, id, compact} = props;
  const quads = (data.items || []).slice(0, 4);
  const axes = data.items_b || [];
  const top = titleSpace(props);
  const big = fullBoard(box, compact);
  const hgt = box.h - top - (big ? 48 : 16);
  const size = Math.min(hgt, box.w * 0.72);
  const wide = Math.min(box.w * 0.72, size * 1.5);
  const x0 = (box.w - wide) / 2;
  const y0 = big ? BOARD_CY - size / 2 : top + (box.h - top - size) / 2;
  const active = hl(props);
  const seed = hashSeed(id);
  const key = boardKey(data, quads.length || 1);
  const p = enter(frame, 4, 18);
  const [mx, my] = [x0 + wide / 2, y0 + size / 2];
  const ov = (12 + (seed % 13)) / 2;
  const reach = big ? 190 : 74;      // 카드 밖으로 축이 나오는 길이 — 축 이름이 그 끝에 붙는다(전면: 핵심 카드 밖까지)
  const qpos: Pt[] = [[-1, -1], [1, -1], [-1, 1], [1, 1]];
  const axisLabel = (text: string, style: React.CSSProperties, i: number) => (
    <div style={{position: 'absolute', fontFamily: FONT.pen, fontSize: compact ? 40 : 60, lineHeight: 1, color: MAT.graphite, whiteSpace: 'nowrap', opacity: enter(frame, 16 + i * 2, 10), ...style}}>{text}</div>
  );
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <BoardTitle text={data.title || ''} note={data.subtitle} frame={frame} box={box} compact={compact} />
      <svg width={box.w} height={box.h} style={{position: 'absolute', inset: 0, overflow: 'visible', mixBlendMode: 'multiply'}}>
        <PencilArrow pts={[[x0 - reach, my], [x0 + wide + reach, my]]} p={p} width={4} seed={seed} />
        <PencilArrow pts={[[mx, y0 + size + 28], [mx, y0 - 30]]} p={p} width={4} seed={seed + 2} />
      </svg>
      {quads.map((qd, i) => {
        const on = i === active;
        const k = boardScale(seed, i, key);
        const [w, h] = [wide * (big ? 0.475 : 0.42) * k, big ? (i === key ? 200 : 176) : size * 0.385 * k];
        const c: Card = {cx: mx + qpos[i][0] * (w / 2 - ov), cy: my + qpos[i][1] * (h / 2 - ov), w, h, rot: boardRot(seed, i)};
        return (
          <Tag key={i} c={c} seed={seed} i={i} on={on} frame={frame} at={8 + i * 4} top={i === key} torn={tornFor(seed + i * 5)} outer={qpos[i]}>{/* 글은 바깥 모서리 — 가운데는 이웃과 겹친다 */}
            {(fg) => (
              <>
                <Lines text={qd} maxW={w - 64} maxH={h - 44} size={(compact ? 34 : 46) * Math.min(1.3, k)} color={fg} on={on} />
                {i === key ? <KeyScrap data={data} frame={frame - 8 - i * 4 - 6} cw={w} seed={seed} over={0} rise={0.12} pin={qpos[i][0] > 0 ? 0.18 : 0.82} /> : null}
              </>
            )}
          </Tag>
        );
      })}
      {axes.length >= 4 ? (
        <>
          {axisLabel(axes[0], {right: box.w - x0 + reach + 12, top: my - 30}, 0)}
          {axisLabel(axes[1], {left: x0 + wide + reach + 12, top: my - 30}, 1)}
          {axisLabel(axes[2], {left: mx + 16, top: y0 + size - 24}, 2)}
          {axisLabel(axes[3], {left: mx + 18, top: y0 - 42}, 3)}
        </>
      ) : null}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 벤 다이어그램 — 연필 원, 겹치는 곳에 주황 해치
// ---------------------------------------------------------------------------
export const VennDiagram: React.FC<TemplateProps> = (props) => {
  const {data, frame, box, id, compact} = props;
  const items = (data.items || []).slice(0, 3);
  const n = items.length >= 3 ? 3 : 2;
  const top = titleSpace(props);
  const h = box.h - top;
  const cx = box.w / 2;
  const big = fullBoard(box, compact);
  const r = Math.min(h * (n === 3 ? 0.3 : 0.38), box.w * 0.22) * (big ? 1.13 : 1);
  const off = r * 0.62;
  const cy = big ? BOARD_CY - (n === 3 ? off * 0.1 : 0) : top + h / 2 + (n === 3 ? 10 : 0);
  const seed = hashSeed(id);
  const centers: Pt[] = n === 3
    ? [[cx - off, cy - off * 0.55], [cx + off, cy - off * 0.55], [cx, cy + off * 0.75]]
    : [[cx - off, cy], [cx + off, cy]];
  // 모든 원이 겹치는 영역: 각 원의 호 중 나머지 원 안에 있는 점들
  const lens = useMemo<Pt[]>(() => {
    const pts: Pt[] = [];
    centers.forEach(([x, y], k) => {
      for (let a = 0; a < 360; a += 3) {
        const px = x + r * Math.cos((a * Math.PI) / 180);
        const py = y + r * Math.sin((a * Math.PI) / 180);
        if (centers.every(([ox, oy], j) => j === k || Math.hypot(px - ox, py - oy) <= r)) pts.push([px, py]);
      }
    });
    const mx = pts.reduce((s, p) => s + p[0], 0) / Math.max(1, pts.length);
    const my = pts.reduce((s, p) => s + p[1], 0) / Math.max(1, pts.length);
    return pts.sort((a, b) => Math.atan2(a[1] - my, a[0] - mx) - Math.atan2(b[1] - my, b[0] - mx));
  }, [n, r, cx, cy]);
  const lensC: Pt = [lens.reduce((t, p) => t + p[0], 0) / Math.max(1, lens.length), lens.reduce((t, p) => t + p[1], 0) / Math.max(1, lens.length)];
  const labSize = compact ? 34 : 54;
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <BoardTitle text={data.title || ''} note={data.subtitle} frame={frame} box={box} compact={compact} />
      <svg width={box.w} height={box.h} style={{position: 'absolute', inset: 0, overflow: 'visible', mixBlendMode: 'multiply'}}>
        <Hatch poly={lens} gap={11} color={MAT.orange} width={3} p={enter(frame, 22, 16)} seed={seed} />
        {centers.map(([x, y], i) => <PencilStroke key={i} pts={ringPts(x, y, r, r, -100 + i * 60)} p={enter(frame, 4 + i * 6, 18)} width={4.2} seed={seed + i} />)}
      </svg>
      {centers.map(([x, y], i) => {
        const dx = x - cx;
        const dy = y - cy;
        return (
          <div key={i} style={{position: 'absolute', left: x + dx * 0.62 - r * 0.8, top: y + dy * 0.62 - labSize * 0.7, width: r * 1.6, textAlign: 'center', fontFamily: FONT.sans, fontSize: labSize, fontWeight: 800, letterSpacing: '-0.02em', color: MAT.ink,
            opacity: enter(frame, 10 + i * 6, 12)}}>{items[i]}</div>
        );
      })}
      {data.body && lens.length ? (
        <>
          <svg width={box.w} height={box.h} style={{position: 'absolute', inset: 0, overflow: 'visible', mixBlendMode: 'multiply'}}>
            <PencilArrow pts={[[cx + off + r + 44, cy - r * 0.2], bend([cx + off + r + 44, cy - r * 0.2], [lensC[0] + 16, lensC[1]]), [lensC[0] + 16, lensC[1]]]} p={enter(frame, 26, 12)} color={MAT.orange} width={4} seed={seed + 9} head={24} />
          </svg>
          <div style={{position: 'absolute', left: cx + off + r + 60, top: cy - r * 0.2 - 36, fontFamily: FONT.sans, fontSize: compact ? 38 : 60, fontWeight: 900, letterSpacing: '-0.02em', color: MAT.orange, whiteSpace: 'nowrap', opacity: enter(frame, 30, 10)}}>{data.body}</div>
        </>
      ) : null}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 피라미드(아래→위) — 층층이 쌓은 찢긴 종이 띠
// ---------------------------------------------------------------------------
export const PyramidDiagram: React.FC<TemplateProps> = (props) => {
  const {data, frame, dur, box, compact, id} = props;
  const items = (data.items || []).slice(0, 5);
  const n = Math.max(1, items.length);
  const top = titleSpace(props);
  const h = box.h - top - 12;
  const baseW = Math.min(box.w * 0.82, h * 2);
  const layerH = h / n;
  const cx = box.w / 2;
  const active = hl(props);
  const seed = hashSeed(id);
  const tex = ['kraft', 'parchment', 'memo'] as const;
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <BoardTitle text={data.title || ''} note={data.subtitle} frame={frame} box={box} compact={compact} />
      {items.map((it, i) => {
        const w = baseW * (1 - (i / n) * 0.86);
        const y = top + h - (i + 1) * layerH;
        const on = i === active;
        const at = stepped(props) ? 4 + i * 5 : revealAt(i, n, dur, 4) * 0.6;
        if (frame < at) return null;
        const fg = on ? '#FFFFFF' : MAT.ink;
        return (
          <Sheet key={i} x={cx - w / 2} y={y + 3} w={w} h={layerH + 8} tex={on ? 'forest' : tex[i % 3]} seed={seed + i * 3} m={paperSettle(frame - at, seedRot(seed, i, 0.8), 10, 12)} torn={{left: true, right: true}} amp={12} on="board">
            <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: FONT.sans, fontSize: Math.min(layerH * 0.42, fitSize(it, w - 70, compact ? 34 : 50, 28, -0.02)), fontWeight: on ? 900 : 700, letterSpacing: '-0.02em', color: fg, whiteSpace: 'nowrap'}}>{it}</div>
          </Sheet>
        );
      })}
    </div>
  );
};
