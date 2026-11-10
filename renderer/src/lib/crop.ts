// 그림 위 그래픽의 자리 계산(런타임 의존성 없음 — tests/test_overlays.py 가 node 로 직접 읽는다).
export type Pt = [number, number];
export type Rect = {x: number; y: number; w: number; h: number};
/** 이미지 정규화 좌표(0~1) → 상자 픽셀 */
export type MapFn = (nx: number, ny: number) => Pt;
type Coords = {box?: number[]; point?: number[]; poly?: number[][]};

/** object-fit·object-position 이 실제로 그리는 자리. 크기를 모르면 null(좌표를 쓰지 않는다) */
export const coverMap = (imgW: number | undefined, imgH: number | undefined, boxW: number, boxH: number, posX = 0.5, posY = 0.5,
  fit: 'cover' | 'contain' = 'cover'): MapFn | null => {
  if (!imgW || !imgH || imgW <= 0 || imgH <= 0) return null;
  const s = fit === 'cover' ? Math.max(boxW / imgW, boxH / imgH) : Math.min(boxW / imgW, boxH / imgH);
  const ox = (boxW - imgW * s) * posX;
  const oy = (boxH - imgH * s) * posY;
  return (nx, ny) => [ox + nx * imgW * s, oy + ny * imgH * s];
};

/** 표시 대상의 화면 상자. 좌표가 없거나 대상의 가운데가 크롭으로 잘려 나갔으면 null — 엉뚱한 것에 표시하지 않는다 */
export const targetRect = (o: Coords, map: MapFn | null, W: number, H: number): Rect | null => {
  if (!map) return null;
  const norm = o.poly?.length ? o.poly
    : o.box?.length === 4 ? [[o.box[0], o.box[1]], [o.box[0] + o.box[2], o.box[1] + o.box[3]]]
      : o.point?.length === 2 ? [o.point] : [];
  if (!norm.length) return null;
  const pts = norm.map(([x, y]) => map(x, y));
  const x0 = Math.min(...pts.map((p) => p[0]));
  const y0 = Math.min(...pts.map((p) => p[1]));
  const r = {x: x0, y: y0, w: Math.max(...pts.map((p) => p[0])) - x0, h: Math.max(...pts.map((p) => p[1])) - y0};
  const cx = r.x + r.w / 2;
  const cy = r.y + r.h / 2;
  return cx >= 0 && cx <= W && cy >= 0 && cy <= H ? r : null;
};

/** 치수선의 두 끝이 다 보이는가 — 끝 틱이 잘린 선에 전체 길이 수치를 붙이지 않는다(잘리면 메모로) */
export const endsVisible = (poly: number[][], map: MapFn, v: Rect): boolean => poly.every(([nx, ny]) => {
  const [x, y] = map(nx, ny);
  return x >= v.x && x <= v.x + v.w && y >= v.y && y <= v.y + v.h;
});

/** 닫힌 윤곽 → 모든 꼭짓점을 지나는 Catmull-Rom 곡선(SVG 경로) */
export const catmullRom = (pts: Pt[]): string => {
  const n = pts.length;
  const at = (i: number) => pts[(i + n) % n];
  const f = (v: number) => v.toFixed(1);
  return `M${f(pts[0][0])} ${f(pts[0][1])}${pts.map((p, i) => {
    const [a, b, c] = [at(i - 1), at(i + 1), at(i + 2)];
    return `C${f(p[0] + (b[0] - a[0]) / 6)} ${f(p[1] + (b[1] - a[1]) / 6)} ${f(b[0] - (c[0] - p[0]) / 6)} ${f(b[1] - (c[1] - p[1]) / 6)} ${f(b[0])} ${f(b[1])}`;
  }).join('')}Z`;
};

/** 선분 a→b 가 닫힌 윤곽과 처음 만나는 점 */
export const firstHit = (a: Pt, b: Pt, poly: Pt[]): Pt | null => {
  const [dx, dy] = [b[0] - a[0], b[1] - a[1]];
  let best = Infinity;
  poly.forEach((p, i) => {
    const q = poly[(i + 1) % poly.length];
    const [ex, ey] = [q[0] - p[0], q[1] - p[1]];
    const den = dx * ey - dy * ex;
    if (!den) return;
    const t = ((p[0] - a[0]) * ey - (p[1] - a[1]) * ex) / den;
    const u = ((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / den;
    if (t >= 0 && t <= 1 && u >= 0 && u <= 1) best = Math.min(best, t);
  });
  return best === Infinity ? null : [a[0] + dx * best, a[1] + dy * best];
};

const MARGIN = {x: 56, top: 56, bottom: 190};   // 아래는 자막·출처 자리
const hits = (a: Rect, b: Rect, pad = 14) => a.x < b.x + b.w + pad && b.x < a.x + a.w + pad && a.y < b.y + b.h + pad && b.y < a.y + a.h + pad;
const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), Math.max(lo, hi));

/** 종이 표찰 자리: 대상 옆 네 방향 중 화면 안에 들어가고 이미 놓인 것과 겹치지 않는 첫 곳(side = 그림의 빈 쪽, 없으면 화면 안쪽 방향 먼저) */
export const placeNear = (t: Rect, w: number, h: number, taken: Rect[], W: number, H: number, gap = 60, outward = false, side?: string): Rect => {
  const cx = t.x + t.w / 2 - w / 2;
  const cy = t.y + t.h / 2 - h / 2;
  const right = {x: t.x + t.w + gap, y: cy};
  const left = {x: t.x - gap - w, y: cy};
  const above = {x: cx, y: t.y - gap - h};
  const below = {x: cx, y: t.y + t.h + gap};
  const [a, b] = (side === 'left' || side === 'right' ? side === 'right' : (t.x + t.w / 2 < W / 2) !== outward) ? [right, left] : [left, right];
  const order = outward ? [a, b, above, below] : [a, above, below, b];   // outward: 책상 위 인쇄물 — 표찰이 그림 밖 책상으로 나가게
  const fits = (p: {x: number; y: number}) => p.x >= MARGIN.x && p.x + w <= W - MARGIN.x && p.y >= MARGIN.top && p.y + h <= H - MARGIN.bottom;
  const p = order.find((c) => fits(c) && !taken.some((q) => hits({...c, w, h}, q))) ?? order.find(fits) ?? order[0];
  const out = {x: clamp(p.x, MARGIN.x, W - MARGIN.x - w), y: clamp(p.y, MARGIN.top, H - MARGIN.bottom - h), w, h};
  if (!hits(out, t, 0)) return out;
  // 자리가 없어 대상 위로 밀려 왔으면, 대상에서 먼 화면 가장자리로 — 표찰이 가리키는 것을 가리면 안 된다
  const edges = [{...out, x: MARGIN.x}, {...out, x: W - MARGIN.x - w}, {...out, y: MARGIN.top}, {...out, y: H - MARGIN.bottom - h}];
  return edges.find((c) => !hits(c, t, 0)) ?? out;
};

/** 치수선 수치의 자리(글자 상자의 가운데): 선 가운데에서 위쪽(세로선이면 오른쪽)으로 비켜나고, 화면 밖이면 반대쪽 */
export const figureAt = (a: Pt, b: Pt, w: number, h: number, W: number, H: number): Pt => {
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
  let [nx, ny] = [-(b[1] - a[1]) / len, (b[0] - a[0]) / len];
  if (ny > 0.2 || (Math.abs(ny) <= 0.2 && nx < 0)) [nx, ny] = [-nx, -ny];
  const off = 18 + (Math.abs(nx) * w) / 2 + (Math.abs(ny) * h) / 2;
  const at = (s: number): Pt => [(a[0] + b[0]) / 2 + nx * off * s, (a[1] + b[1]) / 2 + ny * off * s];
  const fits = ([x, y]: Pt) => x - w / 2 >= MARGIN.x && x + w / 2 <= W - MARGIN.x && y - h / 2 >= MARGIN.top && y + h / 2 <= H - MARGIN.bottom;
  const [x, y] = fits(at(1)) ? at(1) : at(-1);
  return [clamp(x, MARGIN.x + w / 2, W - MARGIN.x - w / 2), clamp(y, MARGIN.top + h / 2, H - MARGIN.bottom - h / 2)];
};

const CAPTION_CLEAR = 925;     // 치수선은 자막 위 30px 안으로 내려오지 않는다

/**
 * 치수선의 자리(층 좌표). view = 층에서 화면에 보이는 곳(문서는 밀려 들어가 있다).
 * 문서 위(doc): 그 줄 기준선 12px 아래로 — 글자를 취소선처럼 긋지 않는다. bottom = 줄 상자 아래 변(모르면 줄 가운데로 보고 글자 반 높이를 더한다).
 * 사진 위: 낮으면 가로선은 대상 위쪽(top)으로, 세로·대각선이나 top 을 모르면 자막 위까지만 올린다. 위 끝은 화면 밖으로 나가지 않는다.
 */
export const dimensionLine = (a: Pt, b: Pt, view: Rect, H: number, tick: number, o: {doc?: boolean; top?: number; bottom?: number} = {}): [Pt, Pt] => {
  const z = H / view.h;
  const low = Math.max(a[1], b[1]);
  const limit = view.y + CAPTION_CLEAR / z - tick;
  const flat = Math.abs(b[0] - a[0]) >= Math.abs(b[1] - a[1]);
  const up = low <= limit ? 0 : flat && o.top !== undefined ? o.top - 28 / z - low : limit - low;
  const dy = o.doc ? (o.bottom ?? low + 10 / z) - low + 12 / z : Math.max(up, Math.min(0, view.y + tick - Math.min(a[1], b[1])));
  return [[a[0], a[1] + dy], [b[0], b[1] + dy]];
};

/** 전면으로 키우면 안 되는 그림인가: 표시 크기가 원본의 1.5배를 넘거나 윤곽이 번진 그림(soft = compose.py 실측) — AI 업스케일처럼 보인다 */
export const tooSoft = (w: number | undefined, h: number | undefined, W: number, H: number, soft = false) => soft || (!!w && !!h && Math.max(W / w, H / h) > 1.5);

/** 오린 그림 안의 지시점: from 에 가장 가까운, 둘레에서 inset px 안쪽의 불투명한 곳. grid = 알파(0~1) 격자, r = 그림의 화면 상자. 그런 곳이 없으면 null */
export const snapOpaque = (grid: number[][], r: Rect, from: Pt, inset = 8): Pt | null => {
  const [rows, cols] = [grid.length, grid[0]?.length ?? 0];
  const [cw, ch] = [r.w / Math.max(1, cols), r.h / Math.max(1, rows)];
  const [di, dj] = [Math.ceil(inset / ch), Math.ceil(inset / cw)];
  const solid = (i: number, j: number) => (grid[i]?.[j] ?? 0) > 0.5;
  let best: Pt | null = null;
  let dist = Infinity;
  for (let i = 0; i < rows; i++) for (let j = 0; j < cols; j++) {
    if (!solid(i, j) || !solid(i - di, j) || !solid(i + di, j) || !solid(i, j - dj) || !solid(i, j + dj)) continue;
    const p: Pt = [r.x + (j + 0.5) * cw, r.y + (i + 0.5) * ch];
    const d = Math.hypot(p[0] - from[0], p[1] - from[1]);
    if (d < dist) {
      best = p;
      dist = d;
    }
  }
  return best;
};

/** 글 속 첫 숫자를 q(0~1)만큼까지 센다 — 자릿수·쉼표는 원문 그대로, 끝에서는 원문 */
export const countUp = (text: string, q: number): string => q >= 1 ? text : text.replace(/\d[\d,]*(\.\d+)?/, (m) => {
  const v = (parseFloat(m.replace(/,/g, '')) * q).toFixed(m.split('.')[1]?.length ?? 0);
  return m.includes(',') ? v.replace(/\B(?=(\d{3})+(?!\d))/g, ',') : v;
});

export const EXPAND_SEC = 0.6;
/** 조각이 화면이 되는 전환의 짝(뒤 id → 앞 id): 전면끼리 맞붙은 곳만(화자 ↔ 자료는 하드 컷이 사양), 영상당 max 번까지 */
export const expandPairs = (gs: {id: string; start: number; end: number; cover: boolean; expand: boolean}[], abut: number, max = 2): Record<string, string> => {
  const out: Record<string, string> = {};
  let last: {id: string; end: number} | null = null;
  for (const g of gs) {
    if (g.expand && g.cover && last && g.start - last.end <= abut && Object.keys(out).length < max) out[g.id] = last.id;
    if (g.cover) last = g;
  }
  return out;
};

/** 전환 중 조각의 자리(p 0→1): 대상 둘레의 작은 인화지 → 화면 전체, 기울기는 풀린다 */
export const expandRect = (p: number, W: number, H: number, at: Pt, from = 0.3, tilt = -2.2): Rect & {a: number} => {
  const [w0, h0] = [W * from, H * from];
  const x0 = clamp(at[0] - w0 / 2, 96, W - 96 - w0);
  const y0 = clamp(at[1] - h0 / 2, 96, H - 240 - h0);
  return {x: x0 * (1 - p), y: y0 * (1 - p), w: w0 + (W - w0) * p, h: h0 + (H - h0) * p, a: tilt * (1 - p)};
};

/** 전환 중 우하단 출처: 새 자료가 화면의 절반을 넘는 프레임에서 바뀌고, 그 전에 둘 다 크게 보이면 두 기관을 한 줄로 */
export const expandCredit = (share: number, before: string, after: string): string => {
  if (share >= 0.5 || !before) return after;
  return share >= 0.25 && after && after !== before ? `${before} · ${after}` : before;
};

/** 휘도 격자(그림 좌표)에서 선분 a→b 를 따라 잰 평균 */
export const lumAlong = (grid: number[][], a: number[], b: number[]): number => {
  const n = grid.length;
  const at = (v: number) => Math.min(n - 1, Math.max(0, Math.floor(v * n)));
  let sum = 0;
  for (let i = 0; i <= 8; i++) sum += grid[at(a[1] + ((b[1] - a[1]) * i) / 8)][at(a[0] + ((b[0] - a[0]) * i) / 8)];
  return sum / 9;
};

/** 도장 자리(화면 좌표): near(그림 좌표)에서 가장 가까우면서 fw×fh 안 평균 휘도가 min 이상이고 화면·자막 안쪽인 곳. 없으면 null(메모로 대체) */
export const brightSpot = (grid: number[][], map: MapFn, near: number[], fw: number, fh: number, W: number, H: number, min = 0.45): Pt | null => {
  const n = grid.length;
  const [x0, y0] = map(0, 0);
  const [x1, y1] = map(1, 1);
  const hw = Math.ceil((fw / 2 / Math.max(1, x1 - x0)) * n);
  const hh = Math.ceil((fh / 2 / Math.max(1, y1 - y0)) * n);
  const [tx, ty] = map(near[0], near[1]);
  let best: Pt | null = null;
  let dist = Infinity;
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) {
    const [x, y] = map((c + 0.5) / n, (r + 0.5) / n);
    if (x - fw / 2 < MARGIN.x || x + fw / 2 > W - MARGIN.x || y - fh / 2 < MARGIN.top || y + fh / 2 > H - MARGIN.bottom) continue;
    const d = Math.hypot(x - tx, y - ty);
    if (d >= dist) continue;
    let sum = 0;
    let k = 0;
    let low = 1;
    for (let i = Math.max(0, r - hh); i <= Math.min(n - 1, r + hh); i++) for (let j = Math.max(0, c - hw); j <= Math.min(n - 1, c + hw); j++) {
      sum += grid[i][j];
      low = Math.min(low, grid[i][j]);
      k++;
    }
    if (sum / k >= min && low >= min * 0.9) {       // 평균만 보면 절반이 어두운 건물에 걸린다
      best = [x, y];
      dist = d;
    }
  }
  return best;
};

/** 화살표 꼬리: 대상에서 화면 가운데 쪽으로 — 다른 표시·종이에 걸리면 돌려 본다 */
export const arrowTail = (t: Rect, taken: Rect[], W: number, H: number, reach = 250): Pt => {
  const cx = t.x + t.w / 2;
  const cy = t.y + t.h / 2;
  const base = Math.atan2(H * 0.42 - cy, W * 0.5 - cx);
  const r = reach + Math.max(t.w, t.h) / 2;
  const at = (turn: number): Pt => [cx + Math.cos(base + turn) * r, cy + Math.sin(base + turn) * r];
  const free = [0, 0.9, -0.9, 1.8, -1.8].map(at).find(([x, y]) => x >= MARGIN.x && x <= W - MARGIN.x && y >= MARGIN.top && y <= H - MARGIN.bottom
    && !taken.some((q) => hits({x, y, w: 0, h: 0}, q, 30)));
  return free ?? at(0);
};

/** 좌표가 없는 메모·라벨: 그림의 빈 쪽(safe.side) 위에서부터, 이미 놓인 것 아래로 */
export const safeSlot = (side: string | undefined, w: number, h: number, taken: Rect[], W: number, H: number): Rect => {
  const x = side === 'left' ? MARGIN.x + 16 : W - MARGIN.x - 16 - w;
  let y = 96;
  while (y + h + 24 <= H - MARGIN.bottom && taken.some((q) => hits({x, y, w, h}, q))) y += 24;
  return {x, y, w, h};
};
