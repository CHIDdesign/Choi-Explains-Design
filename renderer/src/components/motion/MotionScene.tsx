import React from 'react';
import {Img, interpolate, staticFile} from 'remotion';
import {DUR, EASE, exitFrames, STAGGER} from '../../design/motion';
import type {EaseName} from '../../design/motion';
import {FONT} from '../../design/tokens';
import type {Surface} from '../../design/surfaces';
import type {MotionColor, MotionEl, MotionKey, MotionSpec} from '../../lib/types';
import {ChalkFilter, ParenLabel} from '../layout/Editorial';
import {hashSeed, TornFrame} from '../paper/Paper';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

type Ctx = {frame: number; fps: number; W: number; H: number; surface: Surface; total: number; id: string};

const colorOf = (c: MotionColor | 'none' | undefined, s: Surface, fallback: string): string => {
  switch (c) {
    case 'fg':
      return s.fg;
    case 'dim':
      return s.dim;
    case 'faint':
      return s.faint;
    case 'accent':
      return s.accent;
    case 'bg':
      return s.bg;
    case 'white':
      return '#ffffff';
    case 'ink':
      return '#111111';
    case 'none':
      return 'none';
    default:
      return fallback;
  }
};

const easeOf = (e?: string): EaseName => (e === 'inOut' ? 'inOutCubic' : e === 'back' ? 'outBack' : e === 'linear' ? 'linear' : 'outQuint');

/** 키프레임 보간 — 시작 상태(요소의 x/y, 배율 1)를 암묵적으로 넣고, 화면 안 이동은 ease-in-out(animate-skill) */
const sampleKeys = (keys: MotionKey[] | undefined, t: number, base: Required<MotionKey>) => {
  const out: {x?: number; y?: number; scale?: number; rotate?: number; opacity?: number} = {};
  if (!keys || keys.length === 0) return out;
  for (const prop of ['x', 'y', 'scale', 'rotate', 'opacity'] as const) {
    const given = keys.filter((k) => typeof k[prop] === 'number').sort((a, b) => a.t - b.t);
    if (given.length === 0) continue;
    const ks = given[0].t > base.t ? [{t: base.t, v: base[prop]}, ...given.map((k) => ({t: k.t, v: k[prop] as number}))]
      : given.map((k) => ({t: k.t, v: k[prop] as number}));
    if (t <= ks[0].t) {
      out[prop] = ks[0].v;
      continue;
    }
    if (t >= ks[ks.length - 1].t) {
      out[prop] = ks[ks.length - 1].v;
      continue;
    }
    for (let i = 0; i < ks.length - 1; i++) {
      if (t >= ks[i].t && t <= ks[i + 1].t) {
        out[prop] = interpolate(t, [ks[i].t, ks[i + 1].t], [ks[i].v, ks[i + 1].v], {...clamp, easing: EASE.inOutCubic});
        break;
      }
    }
  }
  return out;
};

const elementState = (el: MotionEl, c: Ctx) => {
  const t = c.frame / c.fps;
  const at = el.at ?? 0;
  const enterF = Math.max(1, Math.round((el.dur ?? DUR.normal / 30) * c.fps));
  const local = c.frame - at * c.fps;
  const pIn = interpolate(local, [0, enterF], [0, 1], {...clamp, easing: EASE[easeOf(el.ease)]});
  const outAt = el.out !== undefined ? el.out * c.fps : c.total;
  const exitF = exitFrames(enterF);
  const pOut = el.out !== undefined ? interpolate(c.frame, [outAt - exitF, outAt], [1, 0], {...clamp, easing: EASE.inCubic}) : 1;
  const k = sampleKeys(el.keys, t, {t: at, x: el.x, y: el.y, scale: 1, rotate: 0, opacity: el.opacity ?? 1});
  const x = ((k.x ?? el.x) / 100) * c.W;
  const y = ((k.y ?? el.y) / 100) * c.H;
  let dx = 0;
  let dy = 0;
  let scale = k.scale ?? 1;
  let opacity = (k.opacity ?? el.opacity ?? 1) * pOut;
  const enter = el.enter ?? (el.type === 'line' || el.type === 'arrow' || el.type === 'path' ? 'draw' : el.type === 'text' ? 'mask' : 'up');
  const dist = c.H * 0.04;
  switch (enter) {
    case 'fade':
      opacity *= pIn;
      break;
    case 'up':
      dy = (1 - pIn) * dist;
      opacity *= pIn;
      break;
    case 'down':
      dy = -(1 - pIn) * dist;
      opacity *= pIn;
      break;
    case 'left':
      dx = (1 - pIn) * dist;
      opacity *= pIn;
      break;
    case 'right':
      dx = -(1 - pIn) * dist;
      opacity *= pIn;
      break;
    case 'scale':
      scale *= interpolate(pIn, [0, 1], [0.86, 1]);
      opacity *= pIn;
      break;
    case 'pop': {
      const pp = interpolate(local, [0, enterF], [0, 1], {...clamp, easing: EASE.outBack});
      scale *= interpolate(pp, [0, 1], [0.55, 1]);
      opacity *= Math.min(1, pIn * 2);
      break;
    }
    case 'none':
      opacity *= local >= 0 ? 1 : 0;
      break;
    default:
      // mask / draw 는 요소별로 처리
      opacity *= local >= 0 ? 1 : 0;
  }
  return {x, y, dx, dy, scale, rotate: k.rotate ?? 0, opacity, pIn, local, enter, visible: local >= 0 && c.frame <= outAt};
};

const Wrap: React.FC<{st: ReturnType<typeof elementState>; anchor?: string; children: React.ReactNode}> = ({st, anchor,
  children}) => {
  const tx = anchor === 'left' ? '0%' : anchor === 'right' ? '-100%' : '-50%';
  return (
    <div style={{position: 'absolute', left: st.x + st.dx, top: st.y + st.dy, translate: `${tx} -50%`,
      scale: `${st.scale}`, rotate: `${st.rotate}deg`, opacity: st.opacity, transformOrigin: 'center'}}>
      {children}
    </div>
  );
};

const TextEl: React.FC<{el: Extract<MotionEl, {type: 'text'}>; c: Ctx}> = ({el, c}) => {
  const st = elementState(el, c);
  if (!st.visible) return null;
  const size = (el.size / 100) * c.H;
  const font = el.font === 'serif' ? FONT.serif : el.font === 'latin' ? FONT.latin : FONT.display;
  const color = colorOf(el.color, c.surface, c.surface.fg);
  const maxW = el.maxWidth ? (el.maxWidth / 100) * c.W : undefined;
  const style: React.CSSProperties = {fontFamily: font, fontWeight: el.font === 'latin' ? 400 : el.weight ?? 800,
    fontSize: size, lineHeight: 1.12, letterSpacing: size > 60 ? '-0.04em' : '-0.02em', color, textAlign: el.align ?? 'center',
    maxWidth: maxW, whiteSpace: maxW ? 'normal' : 'nowrap', wordBreak: 'keep-all'};
  const reveal = el.reveal ?? (st.enter === 'mask' ? 'words' : 'none');
  const hl = el.highlight;
  const paint = (txt: string, key?: React.Key) => {
    if (!hl || !txt.includes(hl)) return <React.Fragment key={key}>{txt}</React.Fragment>;
    const [a, ...rest] = txt.split(hl);
    return (
      <React.Fragment key={key}>
        {a}
        <span style={{color: c.surface.accent}}>{hl}</span>
        {rest.join(hl)}
      </React.Fragment>
    );
  };
  if (reveal === 'none' || st.enter !== 'mask') {
    return <Wrap st={st} anchor={el.anchor}><div style={style}>{paint(el.text)}</div></Wrap>;
  }
  const units = reveal === 'chars' ? Array.from(el.text) : reveal === 'lines' ? el.text.split('\n') : el.text.split(/(\s+)/);
  const step = reveal === 'chars' ? STAGGER.char : reveal === 'lines' ? STAGGER.line * 2 : STAGGER.word;
  let idx = 0;
  return (
    <Wrap st={st} anchor={el.anchor}>
      <div style={{...style, display: reveal === 'lines' ? 'flex' : 'block', flexDirection: 'column'}}>
        {units.map((u, i) => {
          if (/^\s+$/.test(u)) return <span key={i}>{u}</span>;
          const d = idx++ * step;
          const p = interpolate(st.local, [d, d + DUR.normal], [0, 1], {...clamp, easing: EASE.outExpo});
          return (
            <span key={i} style={{display: 'inline-block', overflow: 'hidden', verticalAlign: 'top', paddingBottom: '0.06em'}}>
              <span style={{display: 'inline-block', translate: `0 ${(1 - p) * 105}%`}}>
                {highlightUnit(u, hl, c.surface.accent)}
              </span>
            </span>
          );
        })}
      </div>
    </Wrap>
  );
};

const highlightUnit = (u: string, hl: string | undefined, accent: string): React.ReactNode => {
  if (!hl) return u;
  // 여러 단어 강조("한 무리")도 단어별로 칠한다. 조사는 본문색(무리|로)
  const hit = hl.split(/\s+/).filter(Boolean).find((hw) => u.includes(hw));
  if (!hit) return u;
  const [a, ...rest] = u.split(hit);
  return (
    <>
      {a}
      <span style={{color: accent}}>{hit}</span>
      {rest.join(hit)}
    </>
  );
};

const ShapeEl: React.FC<{el: MotionEl; c: Ctx}> = ({el, c}) => {
  const st = elementState(el, c);
  if (!st.visible) return null;
  const s = c.surface;
  const draw = st.enter === 'draw' ? st.pIn : 1;
  const filter = s.chalk ? `url(#chalk-${c.id})` : undefined;
  const px = (v: number) => (v / 100) * c.W;
  const py = (v: number) => (v / 100) * c.H;
  let node: React.ReactNode = null;
  if (el.type === 'rect') {
    const w = px(el.w);
    const h = py(el.h);
    node = (
      <rect x={st.x + st.dx - w / 2} y={st.y + st.dy - h / 2} width={w} height={h} rx={el.radius ?? 0}
        fill={colorOf(el.fill, s, 'none')} stroke={colorOf(el.stroke, s, s.fg)} strokeWidth={el.strokeWidth ?? 3}
        pathLength={1} strokeDasharray={st.enter === 'draw' ? 1 : undefined} strokeDashoffset={st.enter === 'draw' ? 1 - draw : undefined}
        fillOpacity={st.enter === 'draw' ? draw : 1} />
    );
  } else if (el.type === 'circle') {
    node = (
      <circle cx={st.x + st.dx} cy={st.y + st.dy} r={px(el.r)} fill={colorOf(el.fill, s, 'none')}
        stroke={colorOf(el.stroke, s, s.fg)} strokeWidth={el.strokeWidth ?? 3} pathLength={1}
        strokeDasharray={st.enter === 'draw' ? 1 : undefined} strokeDashoffset={st.enter === 'draw' ? 1 - draw : undefined} />
    );
  } else if (el.type === 'line' || el.type === 'arrow') {
    const x1 = st.x + st.dx;
    const y1 = st.y + st.dy;
    const x2 = px(el.x2) + st.dx;
    const y2 = py(el.y2) + st.dy;
    const mx = (x1 + x2) / 2;
    const my = (y1 + y2) / 2;
    const len = Math.hypot(x2 - x1, y2 - y1) || 1;
    const curve = el.curve ?? 0;
    const cx = mx - ((y2 - y1) / len) * curve * len * 0.5;
    const cy = my + ((x2 - x1) / len) * curve * len * 0.5;
    const d = curve ? `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}` : `M ${x1} ${y1} L ${x2} ${y2}`;
    const stroke = colorOf(el.color, s, s.fg);
    const ang = Math.atan2(y2 - (curve ? cy : y1), x2 - (curve ? cx : x1));
    const ah = 14 + (el.strokeWidth ?? 3) * 2;
    node = (
      <g>
        <path d={d} fill="none" stroke={stroke} strokeWidth={el.strokeWidth ?? 3} strokeLinecap="round" pathLength={1}
          strokeDasharray={el.dashed ? '0.02 0.02' : 1} strokeDashoffset={el.dashed ? 0 : 1 - draw}
          opacity={el.dashed ? draw : 1} />
        {el.type === 'arrow' && draw > 0.92 ? (
          <path d={`M ${x2 - ah * Math.cos(ang - 0.45)} ${y2 - ah * Math.sin(ang - 0.45)} L ${x2} ${y2} L ${x2 - ah * Math.cos(ang + 0.45)} ${y2 - ah * Math.sin(ang + 0.45)}`}
            fill="none" stroke={stroke} strokeWidth={el.strokeWidth ?? 3} strokeLinecap="round" strokeLinejoin="round" />
        ) : null}
      </g>
    );
  } else if (el.type === 'path') {
    // d 는 0~100 좌표계 → 상자 크기로 스케일
    node = (
      <g transform={`translate(${st.dx} ${st.dy}) scale(${c.W / 100} ${c.H / 100})`}>
        <path d={el.d} fill={colorOf(el.fill, s, 'none')} stroke={colorOf(el.stroke, s, s.fg)}
          strokeWidth={(el.strokeWidth ?? 3) / (c.W / 100)} vectorEffect="non-scaling-stroke" pathLength={1}
          strokeDasharray={st.enter === 'draw' ? 1 : undefined} strokeDashoffset={st.enter === 'draw' ? 1 - draw : undefined} />
      </g>
    );
  } else if (el.type === 'dots') {
    const rows = Math.ceil(el.count / Math.max(1, el.cols));
    const gap = px(el.gap);
    const r = px(el.r);
    const ox = st.x + st.dx - ((el.cols - 1) * gap) / 2;
    const oy = st.y + st.dy - ((rows - 1) * gap) / 2;
    node = (
      <g>
        {Array.from({length: el.count}).map((_, i) => {
          const col = i % el.cols;
          const row = Math.floor(i / el.cols);
          const di = interpolate(st.local, [i * 1.2, i * 1.2 + DUR.fast], [0, 1], {...clamp, easing: EASE.outQuint});
          const on = el.highlight?.includes(i);
          // 무리 재배치: 같은 행 안에서 그룹 사이 간격을 벌린다
          let gx = ox + col * gap;
          if (el.groups && el.groups.length > 1 && el.groupAt !== undefined) {
            let acc = 0;
            let gi = 0;
            for (; gi < el.groups.length; gi++) {
              if (col < acc + el.groups[gi]) break;
              acc += el.groups[gi];
            }
            const extra = px(el.groupGap ?? el.gap * 1.6);
            const center = ((el.groups.length - 1) * extra) / 2;
            const gp = interpolate(c.frame / c.fps, [el.groupAt, el.groupAt + 0.8], [0, 1], {...clamp, easing: EASE.inOutCubic});
            gx += (gi * extra - center) * gp;
          }
          return <circle key={i} cx={gx} cy={oy + row * gap} r={r * di}
            fill={on ? s.accent : colorOf(el.fill, s, s.fg)} />;
        })}
      </g>
    );
  }
  if (!node) return null;
  return (
    <svg width={c.W} height={c.H} style={{position: 'absolute', inset: 0, overflow: 'visible',
      opacity: st.opacity}}>
      <g filter={filter} transform={st.scale !== 1 || st.rotate ? `rotate(${st.rotate} ${st.x} ${st.y}) translate(${st.x} ${st.y}) scale(${st.scale}) translate(${-st.x} ${-st.y})` : undefined}>
        {node}
      </g>
    </svg>
  );
};

const CounterEl: React.FC<{el: Extract<MotionEl, {type: 'counter'}>; c: Ctx}> = ({el, c}) => {
  const st = elementState({...el, enter: el.enter ?? 'up'}, c);
  if (!st.visible) return null;
  const durF = Math.max(1, Math.round((el.dur ?? 1.2) * c.fps));
  const v = interpolate(st.local, [0, durF], [el.from, el.to], {...clamp, easing: EASE.outCubic});
  const txt = `${el.prefix ?? ''}${v.toFixed(el.decimals ?? 0)}${el.suffix ?? ''}`;
  return (
    <Wrap st={st} anchor={el.anchor}>
      <div style={{fontFamily: FONT.latin, fontSize: (el.size / 100) * c.H, lineHeight: 1,
        color: colorOf(el.color, c.surface, c.surface.accent), fontVariantNumeric: 'tabular-nums'}}>{txt}</div>
    </Wrap>
  );
};

const BarEl: React.FC<{el: Extract<MotionEl, {type: 'bar'}>; c: Ctx}> = ({el, c}) => {
  const st = elementState({...el, enter: el.enter ?? 'fade'}, c);
  if (!st.visible) return null;
  const w = (el.w / 100) * c.W;
  const h = (el.h / 100) * c.H;
  const durF = Math.max(1, Math.round((el.dur ?? 0.9) * c.fps));
  const p = interpolate(st.local, [0, durF], [0, Math.max(0, Math.min(1, el.value))], {...clamp, easing: EASE.outQuint});
  return (
    <div style={{position: 'absolute', left: st.x + st.dx, top: st.y + st.dy - h / 2, width: w, opacity: st.opacity}}>
      {el.label ? <div style={{fontFamily: FONT.sans, fontWeight: 600, fontSize: Math.max(18, h * 0.8), color: c.surface.fg,
        marginBottom: 8}}>{el.label}</div> : null}
      <div style={{width: w, height: h, background: c.surface.faint, borderRadius: h / 2, overflow: 'hidden'}}>
        <div style={{width: w * p, height: h, background: colorOf(el.color, c.surface, c.surface.accent), borderRadius: h / 2}} />
      </div>
    </div>
  );
};

const ImageEl: React.FC<{el: Extract<MotionEl, {type: 'image'}>; c: Ctx}> = ({el, c}) => {
  const st = elementState({...el, enter: el.enter ?? 'scale'}, c);
  // 'pixabay:' 는 스톡 단계에서 파일로 바뀌어야 한다(못 구했으면 그리지 않음)
  if (!st.visible || !el.src || el.src.startsWith('pixabay:')) return null;
  const w = (el.w / 100) * c.W;
  const h = (el.h / 100) * c.H;
  const cutout = el.frame === 'cutout' || (!el.frame && el.src.endsWith('.png'));
  if (el.frame === 'torn') {
    // 종이 콜라주: 찢어진 흰 테두리 액자(레퍼런스 3)
    return (
      <Wrap st={st} anchor={el.anchor}>
        <div style={{position: 'relative', width: w, height: h}}>
          <TornFrame b={{x: 0, y: 0, w, h}} seed={hashSeed(el.src)}>
            <Img src={staticFile(el.src)} style={{width: '100%', height: '100%', objectFit: 'cover', display: 'block'}} />
          </TornFrame>
        </div>
      </Wrap>
    );
  }
  return (
    <Wrap st={st} anchor={el.anchor}>
      <Img src={staticFile(el.src)} style={{width: w, height: h, objectFit: cutout ? 'contain' : 'cover',
        borderRadius: el.radius ?? 0, display: 'block',
        filter: cutout ? 'drop-shadow(0 10px 18px rgba(0,0,0,0.45))' : undefined}} />
    </Wrap>
  );
};

/** MotionSpec 장면 렌더러 — 모션 디자이너 에이전트의 JSON 을 프레임 단위로 애니메이션 */
export const MotionScene: React.FC<{spec: MotionSpec; frame: number; fps: number; dur: number; box: {w: number; h: number};
  surface: Surface; id: string}> = ({spec, frame, fps, dur, box, surface, id}) => {
  const c: Ctx = {frame, fps, W: box.w, H: box.h, surface, total: dur, id};
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <svg width={0} height={0} style={{position: 'absolute'}}>
        <ChalkFilter id={`chalk-${id}`} on={surface.chalk} />
      </svg>
      {spec.grid ? (
        <svg width={box.w} height={box.h} style={{position: 'absolute', inset: 0, opacity: 0.5}}>
          {Array.from({length: 13}).map((_, i) => (
            <line key={i} x1={(box.w / 12) * i} y1={0} x2={(box.w / 12) * i} y2={box.h} stroke={surface.faint} strokeWidth={1} />
          ))}
        </svg>
      ) : null}
      {spec.label ? (
        <div style={{position: 'absolute', left: 0, top: -6}}>
          <ParenLabel text={spec.label} surface={surface} frame={frame} size={22} />
        </div>
      ) : null}
      {spec.elements.map((el, i) => {
        switch (el.type) {
          case 'text':
            return <TextEl key={i} el={el} c={c} />;
          case 'counter':
            return <CounterEl key={i} el={el} c={c} />;
          case 'bar':
            return <BarEl key={i} el={el} c={c} />;
          case 'image':
            return <ImageEl key={i} el={el} c={c} />;
          default:
            return <ShapeEl key={i} el={el} c={c} />;
        }
      })}
    </div>
  );
};
