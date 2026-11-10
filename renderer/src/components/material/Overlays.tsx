import React from 'react';
import {interpolate} from 'remotion';
import {EASE, paperSettle, stampIn} from '../../design/motion';
import {FONT, MAT} from '../../design/tokens';
import type {LiftOn} from '../../design/tokens';
import {arrowTail, brightSpot, catmullRom, countUp, dimensionLine, endsVisible, figureAt, firstHit, lumAlong, placeNear, safeSlot, snapOpaque, targetRect} from '../../lib/crop';
import type {MapFn, Pt, Rect} from '../../lib/crop';
import {balanceLines, estWidth} from '../../lib/fit';
import type {GraphicData, Overlay} from '../../lib/types';
import {CutoutFrame, useAlphaGrid} from './Cutout';
import type {AlphaGrid} from './Cutout';
import {Attach, bend, PencilArrow, PencilStroke, ringPts, Stamp} from './Marks';
import {Sheet} from './Sheet';
import {GrainLayer} from './Texture';

/**
 * 이미지 위 그래픽 층(docs/디자인_v5_토크쇼.md): 바탕 처리(data.tone) · 표시(data.overlays) · 입자.
 * 좌표는 그림을 본 비전 선택이 준 이미지 정규화 좌표뿐 — map(크롭 반영)을 거쳐 그린다. map 이 없거나 대상이 잘려 나갔으면 글이 있는 것만 빈 쪽에.
 * 바탕 처리는 backdrop-filter 한 겹이라 영상도 한 번만 디코딩한다. 등장 뒤에는 멈춘다.
 */

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const TONE = {desaturate: 'grayscale(0.92) contrast(1.05)', darken: 'brightness(0.55)', blur: 'blur(22px) brightness(0.42)'} as const;
const GRAY = 'grayscale(0.95) brightness(0.86)';
const DEFOCUS = 'blur(7px) brightness(0.55)';    // 건물 윤곽이 남을 만큼만
const LINE = '#14120F';
const FOCUS_BOTTOM = 930 / 1080;                 // 초점 창은 자막 위에서 끝난다
const TIP = 3;                                   // 지시점은 대상 경계에 닿는다(4px 안)
const FIG = 64;                                  // 치수선의 수치
const TICK = {photo: 11, doc: 9};                // 끝 틱의 절반(전체 22 · 문서 18px)
const DIM_EDGE = 'rgba(30,33,36,0.75)';          // 치수선 어두운 외곽 1.5px — 밝은 도면에서도 폰 크기에서 선이 남는다
const DOC_FIG = 52;                              // 문서 여백 메모의 수치
const DOC_GAP = 30;                              // 본문 오른쪽 끝에서 메모까지

type Placed = Overlay & {f: number; seed: number; t: Rect | null; tag: Rect | null; lines: string[]; tail?: Pt; tight?: boolean; plate?: boolean};

const MAX_MARKS = 3;
/** 한 화면 3개까지: 글이 달린 표시는 표시 + 종이 표찰 둘로 센다(plan.py clean_overlays 와 같은 규칙). 말에 착지한 것부터 */
const withinBudget = (list: Overlay[]): Overlay[] => {
  const weight = (o: Overlay) => (o.text && !['label', 'memo', 'stamp', 'dimension'].includes(o.kind) ? 2 : 1);
  const keep = new Set<Overlay>();
  let used = 0;
  for (const o of [...list].sort((a, b) => Number(a.at === undefined) - Number(b.at === undefined))) {
    if (used + weight(o) <= MAX_MARKS) {
      keep.add(o);
      used += weight(o);
    }
  }
  return list.filter((o) => keep.has(o));
};

const center = (r: Rect): Pt => [r.x + r.w / 2, r.y + r.h / 2];
const nearestEdge = (r: Rect, [x, y]: Pt): Pt => [Math.min(Math.max(x, r.x), r.x + r.w), Math.min(Math.max(y, r.y), r.y + r.h)];
const rectPath = (r: Rect) => `M${r.x.toFixed(1)} ${r.y.toFixed(1)}H${(r.x + r.w).toFixed(1)}V${(r.y + r.h).toFixed(1)}H${r.x.toFixed(1)}Z`;
const shape = (o: Placed, map: MapFn | null): string => o.kind === 'outline' && o.poly?.length && map
  ? catmullRom(o.poly.map(([x, y]) => map(x, y))) : rectPath(o.t as Rect);
const land = (f: number, n = 10) => interpolate(f, [0, n], [0, 1], {...clamp, easing: EASE.enter});
const inside = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), Math.max(lo, hi));

const memoSize = (text: string) => {
  const lines = balanceLines(text, 60 * 0.8, 400, 2, 0);
  return {lines, w: Math.max(250, Math.max(...lines.map((l) => estWidth(l, 60 * 0.8))) + 104), h: 74 + lines.length * 66};
};
const labelSize = (text: string) => ({lines: [text], w: estWidth(text, 38, -0.02) + 44, h: 68});

/** 충격파: 고리 둘이 한 번 퍼져 사라지고, 점 + 얇은 고리 하나만 남아 멈춘다 */
const Impact: React.FC<{t: Rect; f: number}> = ({t, f}) => {
  const [cx, cy] = center(t);
  const r = Math.max(84, Math.min(170, Math.max(t.w, t.h) * 0.62));
  const p = land(f, 8);
  return (
    <g fill="none" stroke={MAT.orange} strokeLinecap="round">
      {[0, 7].map((d) => {
        const q = interpolate(f, [d, d + 20], [0, 1], {...clamp, easing: EASE.enter});
        return q > 0 && q < 1 ? <circle key={d} cx={cx} cy={cy} r={r * (0.35 + 1.75 * q)} strokeWidth={2 + 10 * (1 - q)} strokeOpacity={(1 - q) * 0.9} /> : null;
      })}
      <circle cx={cx} cy={cy} r={r * 0.62} strokeWidth={2.5} strokeOpacity={0.6 * p} />
      <circle cx={cx} cy={cy} r={8} fill={MAT.orange} stroke="none" opacity={p} />
    </g>
  );
};

const RING_SAFE = 48;
/** 손으로 돌린 원의 반지름 — 화면 안전선 안에서. tight = 문서의 줄: 세로 지름을 줄 높이의 1.6배 안으로(위아래 줄을 가로지르지 않게) */
const ring = (t: Rect, W: number, H: number, tight = false) => {
  const [cx, cy] = center(t);
  return {cx, cy, rx: Math.max(30, Math.min(Math.max(46, t.w * 0.6), cx - RING_SAFE, W - cx - RING_SAFE)),
    ry: tight ? Math.max(9, t.h * 0.8) : Math.max(30, Math.min(Math.max(40, t.h * 0.62), cy - RING_SAFE, H - cy - RING_SAFE))};
};

const cutRest = (seed: number) => (seed % 2 ? 1.6 : -1.6);

/** 오림 그림이 놓일 자리: 대상 가운데에, 화면·자막 안쪽으로 */
const pasteRect = (o: Placed, W: number, H: number): Rect => {
  const t = o.t as Rect;
  const aspect = o.w && o.h ? o.w / o.h : 1.3;
  const h = Math.min(H * 0.62, Math.max(320, Math.min(640, t.w || 440)) / aspect);
  const w = h * aspect;
  const [cx, cy] = center(t);
  return {x: Math.min(W - w - 48, Math.max(48, cx - w / 2)), y: Math.min(H - h - 150, Math.max(48, cy - h / 2)), w, h};
};

/** 표시가 실제로 차지하는 자리 — 종이 표찰이 이것을 피한다 */
const footprint = (o: Placed, W: number, H: number): Rect => {
  const t = o.t as Rect;
  if (o.kind === 'circle') {
    const r = ring(t, W, H, o.tight);
    return {x: r.cx - r.rx, y: r.cy - r.ry, w: 2 * r.rx, h: 2 * r.ry};
  }
  if (o.kind === 'cutout') return pasteRect(o, W, H);
  if (o.kind === 'stamp') return {x: t.x + t.w / 2 - 170, y: t.y + t.h / 2 - 90, w: 340, h: 180};
  if (o.kind === 'dimension') return {x: t.x - 40, y: t.y - FIG * 1.6, w: t.w + 80, h: t.h + FIG * 3.2};
  return t.w || t.h ? t : {x: t.x - 120, y: t.y - 120, w: 240, h: 240};
};

const Stroke: React.FC<{o: Placed; map: MapFn | null; W: number; H: number}> = ({o, map, W, H}) => {
  const t = o.t as Rect;
  const p = land(o.f, 11);
  if (o.kind === 'outline') {
    if (p <= 0) return null;
    const line = {d: shape(o, map), pathLength: 1, fill: 'none', strokeLinejoin: 'round', strokeLinecap: 'round', strokeDasharray: `${p} 1`} as const;
    return <><path {...line} stroke={MAT.eggshell} strokeOpacity={0.6} strokeWidth={6} /><path {...line} stroke={MAT.orange} strokeWidth={3.5} /></>;     // 밝은 케이싱: 어두운 강 위에서도 선이 안 묻힌다
  }
  if (o.kind === 'circle') {
    const {cx, cy, rx, ry} = ring(t, W, H, o.tight);
    // 끊김 없는 한 획: 시작과 끝이 둘레 위에서 16° 겹치며 나란히 지나가고 양 끝은 가늘다(같은 굵기로 겹치면 혹이 된다). 어긋남 ±1.5% + 흔들림 1.5% = 반지름의 3% 안
    return <PencilStroke pts={ringPts(cx, cy, rx, ry, -100, 376, 96, 0.03)} p={p} color={MAT.orange} width={5.5} seed={o.seed} wobble={Math.min(2.4, Math.min(rx, ry) * 0.012)} marker tips={0.32} />;
  }
  if (o.kind === 'arrow') {
    const tail = o.tail as Pt;
    const [tipX, tipY] = t.w || t.h ? nearestEdge({x: t.x - 10, y: t.y - 10, w: t.w + 20, h: t.h + 20}, tail) : [t.x, t.y];
    return <PencilArrow pts={[tail, bend(tail, [tipX, tipY]), [tipX, tipY]]} p={p} color={MAT.orange} width={6} seed={o.seed} head={34} marker />;
  }
  return null;
};

/** 초점 창: 가는 종이색 선 + 창이 떠 보이는 그림자 */
const FocusFrame: React.FC<{r: Rect; p: number}> = ({r, p}) => (
  <div style={{position: 'absolute', left: r.x - 2, top: r.y - 2, width: r.w + 4, height: r.h + 4, boxSizing: 'border-box', border: `2px solid ${MAT.eggshell}`, boxShadow: '0 10px 30px rgba(0,0,0,0.5)', opacity: p}} />
);

/** 지시점: 대상 경계 바로 밖 */
const tipOf = (o: Placed, map: MapFn | null, W: number, H: number, alpha?: AlphaGrid | null): Pt => {
  const t = o.t as Rect;
  const from = center(o.tag as Rect);
  if (o.kind === 'cutout') {                       // 오린 그림의 상자 가장자리는 비어 있다 — 몸통 안쪽을 찍는다
    const r = pasteRect(o, W, H);
    const fit = alpha ? Math.min(r.w / alpha.aspect, r.h) : 0;     // 파일 비율이 달라 상자 안에 contain 으로 놓인다
    const inside = alpha ? snapOpaque(alpha.cells, {x: r.x + (r.w - fit * alpha.aspect) / 2, y: r.y + (r.h - fit) / 2, w: fit * alpha.aspect, h: fit}, from) : null;
    const [cx, cy] = center(r);
    if (inside) {                                  // 그림은 놓일 때 기울어 있다 — 기울기만큼 함께 돌린다
      const a = (cutRest(o.seed) * Math.PI) / 180;
      const [dx, dy] = [inside[0] - cx, inside[1] - cy];
      return [cx + dx * Math.cos(a) - dy * Math.sin(a), cy + dx * Math.sin(a) + dy * Math.cos(a)];
    }
    const edge = nearestEdge(r, from);
    return [cx + (edge[0] - cx) * 0.5, cy + (edge[1] - cy) * 0.5];
  }
  let e: Pt;
  if (o.kind === 'outline' && o.poly?.length && map) e = firstHit(from, center(t), o.poly.map(([x, y]) => map(x, y))) ?? nearestEdge(t, from);
  else if (o.kind === 'circle') {
    const {cx, cy, rx, ry} = ring(t, W, H, o.tight);
    const s = 1 / (Math.hypot((from[0] - cx) / rx, (from[1] - cy) / ry) || 1);
    e = [cx + (from[0] - cx) * s, cy + (from[1] - cy) * s];
  } else {
    e = nearestEdge(t, from);
    if (from[0] < t.x || from[0] > t.x + t.w) e = [e[0], t.y + t.h / 2];     // 옆에서 오는 지시선은 표시한 줄의 한가운데로
  }
  const d = Math.hypot(from[0] - e[0], from[1] - e[1]) || 1;
  return [e[0] + ((from[0] - e[0]) / d) * TIP, e[1] + ((from[1] - e[1]) / d) * TIP];
};

/** 지시선 + 점: 라벨의 종이에서 대상까지 */
const Leader: React.FC<{o: Placed; map: MapFn | null; W: number; H: number}> = ({o, map, W, H}) => {
  const alpha = useAlphaGrid(o.kind === 'cutout' && o.cut ? o.image : undefined);
  const c = tipOf(o, map, W, H, alpha);
  const from = nearestEdge(o.tag as Rect, c);
  const p = land(o.f, 8);
  const x = from[0] + (c[0] - from[0]) * p;
  const y = from[1] + (c[1] - from[1]) * p;
  return (
    <g fill="none">
      <line x1={from[0]} y1={from[1]} x2={x} y2={y} stroke={LINE} strokeOpacity={0.5} strokeWidth={4.6} />
      <line x1={from[0]} y1={from[1]} x2={x} y2={y} stroke={MAT.memo} strokeWidth={2} />
      <circle cx={x} cy={y} r={9} stroke={LINE} strokeOpacity={0.45} strokeWidth={5} />
      <circle cx={x} cy={y} r={9} stroke={MAT.orange} strokeWidth={2.6} />
      <circle cx={x} cy={y} r={2.6} fill={MAT.orange} />
    </g>
  );
};

const Tag: React.FC<{o: Placed; on: LiftOn}> = ({o, on}) => {
  const r = o.tag as Rect;
  const memo = o.kind === 'memo' || !o.t;     // 가리킬 곳을 모르는 글은 지시선 없는 라벨(UI 칩)이 아니라 테이프로 붙인 쪽지로
  const m = paperSettle(o.f, (o.seed % 2 ? 1 : -1) * (memo ? 2.2 : 1.2));
  if (memo) {
    return (
      <Sheet x={r.x} y={r.y} w={r.w} h={r.h} tex="memo" seed={o.seed} m={m} on={on} torn={{bottom: true}} amp={9}>
        <div style={{position: 'absolute', left: 0, right: 0, top: 34, textAlign: 'center', fontFamily: FONT.pen, fontSize: 60, lineHeight: '66px', color: MAT.ink, wordBreak: 'keep-all'}}>
          {o.lines.map((l, i) => <div key={i} style={{whiteSpace: 'nowrap'}}>{l}</div>)}
        </div>
        <Attach w={r.w} seed={o.seed} always tw={140} th={40} />
      </Sheet>
    );
  }
  return (
    <Sheet x={r.x} y={r.y} w={r.w} h={r.h} tex="memo" seed={o.seed} m={m} on={on} torn={{[r.x + r.w / 2 < center(o.t as Rect)[0] ? 'left' : 'right']: true}} amp={7}>
      <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: FONT.sans, fontWeight: 700, fontSize: 38,
        letterSpacing: '-0.02em', color: MAT.ink, whiteSpace: 'nowrap'}}>{o.text}</div>
    </Sheet>
  );
};

/** 치수선: 끝 틱이 달린 실선이 한쪽 끝에서 다른 끝으로 그어지고 수치가 함께 세어 올라가 멈춘다. 사진 위는 어두운 외곽을 두른 선(밝은 도면이면 주황), 문서 위는 연필 + 여백의 메모 */
const Dimension: React.FC<{o: Placed; map: MapFn; W: number; H: number; pencil: boolean; grid?: number[][]; view: Rect}> = ({o, map, W, H, pencil, grid, view}) => {
  const [[ax, ay], [bx, by]] = o.poly as [number, number][];
  const z = H / view.h;
  const tickLen = (pencil ? TICK.doc : TICK.photo) / z;
  const box = o.box?.length === 4 && o.box[3] > 0 ? o.box : null;
  const [a, b] = dimensionLine(map(ax, ay), map(bx, by), view, H, tickLen, pencil ? {doc: true, bottom: box ? map(ax, box[1] + box[3])[1] : undefined} : {top: box ? map(ax, box[1])[1] : undefined});
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
  const [nx, ny] = [(-(b[1] - a[1]) / len) * tickLen, ((b[0] - a[0]) / len) * tickLen];
  const p = land(o.f, 16);
  const tip: Pt = [a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p];
  const tick = ([x, y]: Pt): [Pt, Pt] => [[x + nx, y + ny], [x - nx, y - ny]];
  const segs: [Pt, Pt][] = [[a, tip], tick(a), tick(tip)];
  const text = o.text as string;
  const docFig = DOC_FIG / z;
  const [lw, lh] = [estWidth(text, docFig, -0.02) + 44 / z, docFig * 1.1 + 22 / z];
  const margin = inside(DOC_GAP / z + Math.max(map(1, ay)[0], Math.max(a[0], b[0])), view.x + 24 / z, view.x + view.w - 24 / z - lw);        // 문서: 글자 표시는 본문 줄 위에 놓지 않고 오른쪽 여백으로 — 확대돼 여백이 프레임 밖이면 프레임 안쪽 끝으로
  const [fx, fy] = pencil ? [margin + lw / 2, (a[1] + b[1]) / 2] : figureAt(a, b, estWidth(text, FIG, -0.02), FIG * 1.1, W, H);
  const hair = (stroke: string, width: number, opacity = 1) => segs.map(([u, v], i) => <line key={i} x1={u[0]} y1={u[1]} x2={v[0]} y2={v[1]} stroke={stroke} strokeWidth={width} strokeOpacity={opacity} />);
  const light = !pencil && !!grid && (lumAlong(grid, o.poly![0], o.poly![1]) >= 0.5 || grid.flat().reduce((s, v) => s + v, 0) / (grid.length * grid.length) >= 0.45);     // 밝은 자료 위에서 흰 글자는 그림자에 기대게 된다. 한 그림의 치수선은 같은 색으로
  return (
    <>
      <svg width={W} height={H} style={{position: 'absolute', inset: 0, overflow: 'visible', mixBlendMode: pencil ? 'multiply' : undefined}}>
        {pencil ? segs.map(([u, v], i) => <PencilStroke key={i} pts={[u, v]} color={MAT.orange} width={i ? 2.8 : 4} seed={o.seed + i} wobble={0.8} still />)
          : <>{hair(DIM_EDGE, 6.5)}{hair(light ? MAT.orange : MAT.memo, 3.5)}</>}
      </svg>
      {pencil ? (
        <Sheet x={fx - lw / 2} y={fy - lh / 2} w={lw} h={lh} tex="memo" seed={o.seed} m={paperSettle(o.f, -1.2)} on="board">{/* 본문 줄 위에 숫자를 바로 쓰면 읽히지 않는다 */}
          <div style={{position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: FONT.sans, fontWeight: 800, fontSize: docFig, letterSpacing: '-0.02em', color: MAT.ink, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums'}}>{countUp(text, land(o.f, 18))}</div>
        </Sheet>
      ) : (
        <div style={{position: 'absolute', left: fx, top: fy, translate: '-50% -50%', opacity: interpolate(o.f, [0, 4], [0, 1], clamp), fontSize: FIG, lineHeight: 1.1, whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums', fontFamily: FONT.sans, fontWeight: 800, letterSpacing: '-0.02em',
          ...(light ? {color: MAT.ink, textShadow: '0 0 3px rgba(251,249,243,0.9), 0 0 14px rgba(251,249,243,0.8)'} : {color: '#FFFFFF', textShadow: '0 1px 3px rgba(0,0,0,0.75), 0 2px 16px rgba(0,0,0,0.55)'})}}>{countUp(text, land(o.f, 18))}</div>
      )}
    </>
  );
};

/** 오림 그림: 대상 자리에 흰 테두리로 놓인다 */
const Pasted: React.FC<{o: Placed; W: number; H: number}> = ({o, W, H}) => {
  const r = pasteRect(o, W, H);
  const m = paperSettle(o.f, cutRest(o.seed));
  return (
    <div style={{position: 'absolute', left: r.x, top: r.y, opacity: m.opacity, translate: `0 ${m.y}px`, scale: `${m.scale}`}}>
      <CutoutFrame src={o.image as string} w={r.w} h={r.h} seed={o.seed} rotate={m.rotate} level={m.elev} cut={o.cut} />
    </div>
  );
};

/** view = 그려지는 층 좌표에서 화면에 실제로 보이는 곳(문서가 밀려 들어간 끝 상태) — 종이 표찰이 프레임 밖으로 나가지 않게 */
export const PhotoOverlays: React.FC<{data: GraphicData; map: MapFn | null; W: number; H: number; frame: number; fps: number; grain?: boolean; marks?: boolean; onDesk?: boolean; view?: Rect}> = ({data, map, W, H,
  frame, fps, grain = true, marks = true, onDesk = false, view}) => {
  const taken: Rect[] = [];
  const v = view ?? {x: 0, y: 0, w: W, h: H};
  const local = (q: Rect): Rect => ({...q, x: q.x - v.x, y: q.y - v.y});
  const screen = (q: Rect): Rect => ({...q, x: q.x + v.x, y: q.y + v.y});
  const docPaper = onDesk && data.assets?.[0]?.kind === 'document';     // 문서는 hero 로도 책상에 놓인다 — treatment 가 아니라 그려지는 것을 본다
  const grid = data.safe?.lum;
  const on: LiftOn = data.safe?.dim ? 'dark' : 'photo';
  const [px0, py0] = onDesk && map ? map(0, 0) : [0, 0];
  const [px1, py1] = onDesk && map ? map(1, 1) : [W, H];
  const paper: Rect = {x: px0, y: py0, w: px1 - px0, h: py1 - py0};
  const placed: Placed[] = (marks ? withinBudget((data.overlays ?? []).filter((o) => o.kind !== 'highlight' && o.kind !== 'expand')) : []).map((o, i) => {   // highlight 는 문서 종이에 칠한다(DeskDocument) · expand 는 전환(LongForm)
    const t = o.kind === 'dimension' && map && o.poly?.length === 2 && !endsVisible(o.poly, map, v) ? null : targetRect(o, map, W, H);
    if (t && o.kind === 'focus') t.h = Math.max(60, Math.min(t.h, H * FOCUS_BOTTOM - t.y));
    const base = {...o, f: frame - Math.round((o.at ?? 0) * fps), seed: i * 5 + 3, t, tag: null, lines: [], tight: docPaper};
    if (o.kind !== 'stamp' || !t || !grid || !map) return base;
    const [hx, hy] = [estWidth(o.text as string, 72) + 120, 170];
    const near = o.point ?? [(o.box?.[0] ?? 0.5) + (o.box?.[2] ?? 0) / 2, (o.box?.[1] ?? 0.5) + (o.box?.[3] ?? 0) / 2];
    const spot = brightSpot(grid, map, near, hx, hy, W, H);       // 어두운 건물 위에서 도장은 뭉개진다 — 밝은 자리에 찍고, 없으면 도장 뒤에 종이를 깐다
    return spot ? {...base, t: {x: spot[0], y: spot[1], w: 0, h: 0}} : {...base, plate: true};
  });
  for (const o of placed) if (o.t) taken.push(footprint(o, W, H));
  for (const o of placed) {       // 대상을 모두 잡은 뒤에 종이를 놓는다 — 종이가 다른 표시의 대상을 가리지 않게
    if (!o.text || o.kind === 'stamp' || (o.kind === 'dimension' && o.t)) continue;
    const size = o.kind === 'memo' || !o.t ? memoSize(o.text) : labelSize(o.text);
    o.lines = size.lines;
    if (o.t) {
      const fp = footprint(o, W, H);
      o.tag = screen(placeNear(local(onDesk ? {...fp, x: paper.x, w: paper.w} : fp), size.w, size.h, taken.map(local), v.w, v.h, o.kind === 'memo' ? 22 : 60, onDesk, onDesk ? undefined : data.safe?.side));   // 책상 위 인쇄물: 표찰은 인쇄물을 가리지 않고 책상으로
    } else o.tag = screen(safeSlot(data.safe?.side, size.w, size.h, taken.map(local), v.w, v.h));
    taken.push(o.tag);
  }
  for (const o of placed) if (o.kind === 'arrow' && o.t) o.tail = o.tag ? nearestEdge(o.tag, center(o.t)) : arrowTail(o.t, taken, W, H);
  const keyed = placed.filter((o) => o.t && (o.kind === 'outline' || o.kind === 'focus'));
  const outlines = keyed.filter((o) => o.kind === 'outline');
  const focus = keyed.find((o) => o.kind === 'focus');
  const veils: {filter: string; f: number; holes: Placed[]}[] = [];
  // 메모가 있으면 바탕을 흐리지 않는다 — 메모 뒤를 흐리면 어두운 사진의 불빛이 번져 안개가 되고, 전체를 흐리면 그림이 사라진다
  if (data.tone && TONE[data.tone] && !(data.tone === 'blur' && placed.some((o) => o.kind === 'memo' && o.tag))) veils.push({filter: TONE[data.tone], f: frame, holes: keyed});
  if (outlines.length && data.tone !== 'desaturate') veils.push({filter: GRAY, f: outlines[0].f, holes: outlines});
  if (focus) veils.push({filter: DEFOCUS, f: focus.f, holes: [focus]});
  const live = placed.filter((o) => o.f >= 0);
  const ink = live.filter((o) => o.t && o.kind !== 'focus' && o.kind !== 'impact' && o.kind !== 'dimension');
  return (
    <>
      {veils.map((v, i) => {
        if (v.f < 0) return null;
        return (
          <div key={i} style={{position: 'absolute', inset: 0, opacity: interpolate(v.f, [0, 9], [0, 1], clamp), backdropFilter: v.filter, WebkitBackdropFilter: v.filter,
            clipPath: v.holes.length ? `path(evenodd, "M0 0H${W}V${H}H0Z ${v.holes.map((o) => shape(o, map)).join(' ')}")` : undefined}} />
        );
      })}
      {grain ? <GrainLayer frame={frame} opacity={0.14} /> : null}
      {ink.length ? (
        <svg width={W} height={H} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
          {ink.map((o, i) => <Stroke key={i} o={o} map={map} W={W} H={H} />)}
        </svg>
      ) : null}
      {live.filter((o) => o.t && o.kind === 'focus').map((o, i) => <FocusFrame key={i} r={o.t as Rect} p={land(o.f, 11)} />)}
      {live.length ? (
        <svg width={W} height={H} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
          {live.filter((o) => o.t && o.kind === 'impact').map((o, i) => <Impact key={i} t={o.t as Rect} f={o.f} />)}
          {live.filter((o) => o.t && o.tag && o.kind !== 'memo' && o.kind !== 'arrow' && o.kind !== 'cutout').map((o, i) => <Leader key={i} o={o} map={map} W={W} H={H} />)}
        </svg>
      ) : null}
      {map ? live.filter((o) => o.t && o.kind === 'dimension' && o.poly?.length === 2).map((o, i) => <Dimension key={i} o={o} map={map} W={W} H={H} pencil={docPaper} grid={grid} view={v} />) : null}
      {live.filter((o) => o.t && o.kind === 'cutout' && o.image).map((o, i) => <Pasted key={i} o={o} W={W} H={H} />)}
      {live.some((o) => o.t && o.tag && o.kind === 'cutout') ? ( // 지시점이 오림 위에 찍힌다 — 오림보다 나중에
        <svg width={W} height={H} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
          {live.filter((o) => o.t && o.tag && o.kind === 'cutout').map((o, i) => <Leader key={i} o={o} map={map} W={W} H={H} />)}
        </svg>
      ) : null}
      {live.filter((o) => o.t && o.kind === 'stamp' && o.text).map((o, i) => {
        const hw = estWidth(o.text as string, 72) / 2 + 60;     // 도장은 종이 안에만 찍힌다(테두리·기울기 몫 60)
        return <Stamp key={i} text={o.text as string} sub={o.sub} size={72} seed={o.seed} m={stampIn(o.f)} onPaper plate={o.plate} style={{position: 'absolute', translate: '-50% -50%',
          left: inside(center(o.t as Rect)[0], paper.x + hw, paper.x + paper.w - hw), top: inside(center(o.t as Rect)[1], paper.y + 70, paper.y + paper.h - 70)}} />;
      })}
      {live.filter((o) => o.tag).map((o, i) => <Tag key={i} o={o} on={on} />)}
    </>
  );
};
