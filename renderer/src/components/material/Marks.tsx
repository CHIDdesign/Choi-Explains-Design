import React, {useMemo} from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {collageStep} from '../../design/motion';
import {FONT, MAT, rgba} from '../../design/tokens';
import {inkTile, useTileUrl} from '../../lib/noise';
import {seeded} from '../paper/Paper';

export type Pt = [number, number];

// ─────────────────────────────────────────────────────────────────────────────
// 붙이는 것: 테이프 · 핀

/** 마스킹 테이프: 아래 종이 결이 비치는 띠(곱하기), 짧은 변은 손으로 끊은 톱니 */
export const Tape: React.FC<{x: number; y: number; w?: number; h?: number; rotate?: number; color?: string; seed?: number; onDark?: boolean}> = ({x, y,
  w = 150, h = 40, rotate = -3, color = MAT.orange, seed = 1, onDark = false}) => {
  const clip = useMemo(() => {
    const r = seeded(seed + 0.3);
    const teeth = (edge: number, dir: number) => Array.from({length: 7}, (_, i) => {
      const y1 = (i / 6) * 100;
      return `${(edge + dir * (i % 2 ? 1.5 + r() * 2.2 : r() * 0.8)).toFixed(1)}% ${y1.toFixed(1)}%`;
    });
    return `polygon(${[...teeth(0, 1), ...teeth(100, -1).reverse()].join(', ')})`;
  }, [seed]);
  return <div style={{position: 'absolute', left: x, top: y, width: w, height: h, rotate: `${rotate}deg`, clipPath: clip, background: color, opacity: 0.72, mixBlendMode: onDark ? undefined : 'multiply'}} />;   // 짙은 종이 위에서 곱하면 검은 덩어리가 된다
};

/** 종이 클립(선 그림 — 3D 그라디언트 금지): 위 변에 물린다 */
const Clip: React.FC<{x: number; rotate: number}> = ({x, rotate}) => {
  const d = 'M14 34 V80 a8 8 0 0 0 16 0 V18 a12 12 0 0 0 -24 0 V92 a16 16 0 0 0 32 0 V30';
  return (
    <svg width={44} height={112} viewBox="0 0 44 112" fill="none" strokeLinecap="round" style={{position: 'absolute', left: x - 22, top: -34, rotate: `${rotate}deg`, overflow: 'visible'}}>
      <path d={d} stroke="rgba(34,30,26,0.35)" strokeWidth={4} transform="translate(1.5 2.5)" />
      <path d={d} stroke="#85837D" strokeWidth={4} />
      <path d={d} stroke="#D6D4CE" strokeWidth={1.2} />
    </svg>
  );
};

const MASKING = '#D9CCA8';    // 크림색 마스킹 테이프

/**
 * 종이를 붙이는 수단은 시드로 나눈다: 테이프 35% · 그림자로만 놓임 50% · 클립 15%. 테이프는 가운데를 피해 위 변 양쪽 또는 모서리 대각, 각도 -14~+9°, 길이·폭·색이 다르다.
 * 모든 종이의 가운데에 같은 테이프를 붙이면 틱이 된다. always = 테이프가 사양인 템플릿(오늘의 주제·사진 위 메모) — 그 색은 주황. clip = 위 변의 그 자리(0~1)에 클립을 무조건.
 */
export const Attach: React.FC<{w: number; seed: number; always?: boolean; tw?: number; th?: number; clip?: number}> = ({w, seed, always = false, tw = 160, th = 44, clip}) => {
  const r = seeded(seed + 0.61);
  const kind = r();
  if (clip !== undefined) return <Clip x={w * clip} rotate={-6 + r() * 12} />;
  const u = r() < 0.5 ? 0.16 + r() * 0.22 : 0.62 + r() * 0.22;
  const deg = -14 + r() * 23;
  if (!always && kind >= 0.35 && kind < 0.85) return null;
  if (!always && kind >= 0.85) return <Clip x={w * u} rotate={deg * 0.4} />;
  const len = tw * (0.74 + r() * 0.46);
  const high = th * (0.84 + r() * 0.28);
  const color = always || r() < 0.45 ? MAT.orange : MASKING;
  if (r() < 0.3) {
    const right = r() < 0.5;
    return <Tape x={right ? w - len * 0.62 : -len * 0.38} y={-high * 0.1} w={len} h={high} rotate={right ? 38 : -38} seed={seed} color={color} />;
  }
  return <Tape x={w * u - len / 2} y={-high / 2} w={len} h={high} rotate={deg} seed={seed} color={color} />;
};

// ─────────────────────────────────────────────────────────────────────────────
// 강조: 형광펜 · 연필

/** 형광펜 한 줄: 왼→오로 쓸린다(p 0→1). 종이에 곱해져 글자가 비친다 */
export const Highlighter: React.FC<{x: number; y: number; w: number; h: number; p: number; color?: string; rotate?: number; style?: React.CSSProperties}> = ({x, y, w, h, p,
  color = MAT.orange, rotate = -0.25, style}) => (
  <div style={{position: 'absolute', left: x, top: y, width: w, height: h, rotate: `${rotate}deg`, mixBlendMode: 'multiply', borderRadius: '2px 7px 3px 5px / 3px 6px 2px 4px',
    background: `linear-gradient(180deg, ${rgba(color, 0.42)} 0%, ${rgba(color, 0.5)} 55%, ${rgba(color, 0.4)} 100%)`,
    clipPath: `inset(-2px ${((1 - Math.max(0, Math.min(1, p))) * 100).toFixed(2)}% -2px -2px)`, ...style}} />
);

const smooth = (r: () => number, n: number, period: number): number[] => {
  const c = Array.from({length: Math.ceil(n / period) + 3}, () => r() * 2 - 1);
  return Array.from({length: n}, (_, i) => {
    const u = i / period;
    const a = Math.floor(u);
    const t = u - a;
    return c[a] + (c[a + 1] - c[a]) * t * t * (3 - 2 * t);
  });
};

/** 꺾은선을 고른 간격으로 다시 찍고 수직으로 천천히 흔든다 — 손으로 그은 선 */
export const handDrawn = (pts: Pt[], seed: number, wobble = 1.5, step = 10): Pt[] => {
  const out: Pt[] = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i];
    const [bx, by] = pts[i + 1];
    const n = Math.max(1, Math.round(Math.hypot(bx - ax, by - ay) / step));
    for (let k = 0; k < n; k++) out.push([ax + ((bx - ax) * k) / n, ay + ((by - ay) * k) / n]);
  }
  out.push(pts[pts.length - 1]);
  const r = seeded(seed + 0.7);
  const dn = smooth(r, out.length, 7);
  const fine = smooth(r, out.length, 2.2);
  return out.map(([x, y], i) => {
    const [px, py] = out[Math.max(0, i - 1)];
    const [qx, qy] = out[Math.min(out.length - 1, i + 1)];
    const len = Math.hypot(qx - px, qy - py) || 1;
    const w = dn[i] * wobble + fine[i] * wobble * 0.22;
    return [x - ((qy - py) / len) * w, y + ((qx - px) / len) * w];
  });
};

const toD = (pts: Pt[]) => `M ${pts.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(' L ')}`;

/**
 * 연필 선(svg 안에서): 굵은 심(폭 100%, 90%) + 한 번 더 지나간 가는 선(폭 50%, 40%, 더 크게 흔들림). 흔들림은 초당 8번 바뀐다. p 만큼만 그려진다.
 * still = 이중 선은 그대로 두고 흔들림만 멈춘다(정착하면 멈춰야 하는 표시). marker = 사진 위 표식: 끊김도 덧선도 떨림도 없는 불투명한 한 획. tips = 양 끝의 굵기 비(붓이 들리는 끝 — 원의 겹침이 혹이 되지 않게)
 */
export const PencilStroke: React.FC<{pts: Pt[]; p?: number; color?: string; width?: number; seed?: number; wobble?: number; taper?: number; marker?: boolean; tips?: number; still?: boolean}> = ({pts, p = 1, color = MAT.graphite, width = 3,
  seed = 1, wobble = 1.5, taper = 1, marker = false, tips = 1, still = false}) => {
  const key = pts.map(([x, y]) => `${Math.round(x)},${Math.round(y)}`).join(' ');
  const {fps} = useVideoConfig();
  const phase = marker || still ? 0 : (collageStep(useCurrentFrame(), fps) % 4) * 7.3;
  const a = useMemo(() => handDrawn(pts, seed + phase, wobble), [key, seed, wobble, phase]);
  const b = useMemo(() => handDrawn(pts, seed + 11 + phase, wobble * 1.9), [key, seed, wobble, phase]);
  const k = Math.max(0, Math.min(1, p));
  if (k <= 0) return null;
  const cut = (l: Pt[]) => l.slice(0, Math.max(2, Math.round(l.length * k)));
  const n = cut(a).length;
  const alpha = marker ? 1 : 0.9;
  const edge = (u: number) => tips + (1 - tips) * Math.min(1, Math.min(u, 1 - u) / 0.1);
  const at = (u: number) => width * (1 + (taper - 1) * u) * edge(u);
  return (
    <g fill="none" stroke={color} strokeLinecap="round" strokeLinejoin="round">
      {taper === 1 && tips === 1 ? <path d={toD(cut(a))} strokeWidth={width} strokeOpacity={alpha} strokeDasharray={marker ? undefined : '31 0.9 47 1.4 19 0.7'} />
        : Array.from({length: Math.ceil((n - 1) / 3)}, (_, i) => (   // 토막마다 굵기를 달리한다 — 둥근 끝이 이음새를 덮는다
          <path key={i} d={toD(a.slice(i * 3, Math.min(n, i * 3 + 4)))} strokeWidth={at((i * 3) / a.length)} strokeOpacity={alpha} />))}
      {marker ? null : <path d={toD(cut(b))} strokeWidth={width * 0.5} strokeOpacity={0.4} />}
    </g>
  );
};

/** 호·원의 점(손으로 돌린 원처럼 시작과 끝이 조금 어긋난다) */
export const ringPts = (cx: number, cy: number, rx: number, ry: number, from = -100, sweep = 372, n = 56, drift = 0.018): Pt[] =>
  Array.from({length: n + 1}, (_, i) => {
    const t = i / n;
    const a = ((from + sweep * t) * Math.PI) / 180;
    const k = 1 + drift * (t - 0.5);
    return [cx + Math.cos(a) * rx * k, cy + Math.sin(a) * ry * k];
  });

/** 화살표의 제어점: 현을 수직으로 k(12~18%)만큼 민다 */
export const bend = ([ax, ay]: Pt, [bx, by]: Pt, k = 0.15): Pt => [(ax + bx) / 2 + (by - ay) * k, (ay + by) / 2 - (bx - ax) * k];

const quad = ([a, c, b]: Pt[], n = 24): Pt[] => Array.from({length: n + 1}, (_, i) => {
  const t = i / n;
  const u = 1 - t;
  return [u * u * a[0] + 2 * u * t * c[0] + t * t * b[0], u * u * a[1] + 2 * u * t * c[1] + t * t * b[1]];
});

/** 연필 화살표: pts = [시작, 끝] 직선 또는 [시작, 제어점, 끝] 곡선 하나(가운데서 꺾이면 번개 모양이다), 끝으로 갈수록 가늘다. 화살촉 두 획은 몸통이 다 그려진 뒤 */
export const PencilArrow: React.FC<{pts: Pt[]; p?: number; color?: string; width?: number; seed?: number; head?: number; marker?: boolean}> = ({pts, p = 1, color = MAT.graphite, width = 3, seed = 1,
  head = 20, marker = false}) => {
  const line = pts.length === 3 ? quad(pts) : pts;
  const [ax, ay] = line[line.length - 2];
  const [bx, by] = line[line.length - 1];
  const a = Math.atan2(by - ay, bx - ax);
  const wing = (s: number): Pt => [bx - Math.cos(a + s * 0.5) * head, by - Math.sin(a + s * 0.5) * head];
  const hp = Math.max(0, Math.min(1, (p - 0.75) / 0.25));
  return (
    <>
      <PencilStroke pts={line} p={Math.min(1, p / 0.75)} color={color} width={width} seed={seed} taper={0.64} marker={marker} />
      <PencilStroke pts={[wing(1), [bx, by], wing(-1)]} p={hp} color={color} width={width * 0.64} seed={seed + 3} wobble={0.5} marker={marker} />
    </>
  );
};

/** 다각형을 채우는 해치 선(짧은 획의 끝이 고르지 않다) */
export const hatchSegments = (poly: Pt[], gap = 11, deg = -56, seed = 1): [Pt, Pt][] => {
  const a = (deg * Math.PI) / 180;
  const ca = Math.cos(a);
  const sa = Math.sin(a);
  const rot = poly.map(([x, y]): Pt => [x * ca + y * sa, -x * sa + y * ca]);
  const ys = rot.map((p) => p[1]);
  const r = seeded(seed + 0.9);
  const out: [Pt, Pt][] = [];
  for (let y = Math.min(...ys) + gap / 2; y < Math.max(...ys); y += gap * (0.82 + r() * 0.36)) {
    const xs: number[] = [];
    rot.forEach(([x0, y0], i) => {
      const [x1, y1] = rot[(i + 1) % rot.length];
      if ((y0 <= y) !== (y1 <= y)) xs.push(x0 + ((y - y0) / (y1 - y0)) * (x1 - x0));
    });
    xs.sort((p, q) => p - q);
    for (let i = 0; i + 1 < xs.length; i += 2) {
      const u0 = xs[i] + r() * 7 - 2;
      const u1 = xs[i + 1] - r() * 7 + 2;
      if (u1 > u0) out.push([[u0 * ca - y * sa, u0 * sa + y * ca], [u1 * ca - y * sa, u1 * sa + y * ca]]);
    }
  }
  return out;
};

/** 해치 채우기(svg 안에서): p 만큼의 획이 차례로 그어진다 */
export const Hatch: React.FC<{poly: Pt[]; gap?: number; deg?: number; color?: string; width?: number; p?: number; seed?: number}> = ({poly, gap = 11, deg = -56,
  color = MAT.graphite, width = 2, p = 1, seed = 1}) => {
  const key = poly.map(([x, y]) => `${Math.round(x)},${Math.round(y)}`).join(' ');
  const segs = useMemo(() => hatchSegments(poly, gap, deg, seed), [key, gap, deg, seed]);
  const n = Math.round(segs.length * Math.max(0, Math.min(1, p)));
  return (
    <g stroke={color} strokeWidth={width} strokeLinecap="round" strokeOpacity={0.62}>
      {segs.slice(0, n).map(([[x0, y0], [x1, y1]], i) => <line key={i} x1={x0} y1={y0} x2={x1} y2={y1} />)}
    </g>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// 도장

/**
 * 잉크가 고르지 않게 묻은 도장: 이중 테두리 + 글자, 마스크 타일로 군데군데 비었다. m: stampIn 결과.
 * onPaper 면 종이에 곱해지고, 사진 위에서는 그대로 찍힌다.
 */
export const Stamp: React.FC<{text: string; sub?: string; size?: number; color?: string; rotate?: number; seed?: number; onPaper?: boolean; plate?: boolean;
  m?: {opacity: number; scale: number}; style?: React.CSSProperties}> = ({text, sub, size = 76, color = MAT.stamp, rotate = -11, seed = 5, onPaper = false, plate = false, m, style}) => {
  const mask = useTileUrl(inkTile(seed));
  const layer = (blend: React.CSSProperties['mixBlendMode'], k: number, pad = false) => {
    const ink = pad ? 'transparent' : color;       // pad: 같은 크기의 종이 라벨(밝은 면이 없을 때 도장 뒤에 깐다)
    return (
    <div style={{display: 'inline-block', rotate: `${rotate}deg`, opacity: (m?.opacity ?? 1) * k, scale: m ? `${m.scale}` : undefined,
      mixBlendMode: blend, ...style}}>
      <div style={{...(pad ? {background: MAT.eggshell} : {WebkitMaskImage: `url(${mask})`, maskImage: `url(${mask})`, WebkitMaskSize: '512px 512px', maskSize: '512px 512px'}),
        border: `${size * 0.075}px solid ${ink}`, borderRadius: size * 0.16, padding: size * 0.075}}>
        <div style={{border: `${size * 0.028}px solid ${ink}`, borderRadius: size * 0.09, padding: `${size * 0.16}px ${size * 0.42}px ${size * 0.2}px`, textAlign: 'center',
          color: ink, fontFamily: FONT.sans, wordBreak: 'keep-all'}}>
          <div style={{fontWeight: 900, fontSize: size, lineHeight: 1.05, letterSpacing: '0.02em', whiteSpace: 'nowrap'}}>{text}</div>
          {sub ? <div style={{marginTop: size * 0.12, fontWeight: 800, fontSize: Math.max(36, size * 0.4), letterSpacing: '0.04em', whiteSpace: 'nowrap'}}>{sub}</div> : null}
        </div>
      </div>
    </div>
    );
  };
  // 곱하기만으로는 어두운 그림 위에서 글자가 사라진다 — 같은 도장을 옅게 한 번 더 찍는다(종이 위에서는 잉크색이 그대로다)
  return onPaper ? <>{plate ? layer('normal', 0.82, true) : null}{layer('multiply', 0.92)}{layer('normal', 0.42)}</> : layer('normal', 0.96);
};
