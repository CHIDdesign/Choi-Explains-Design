import React from 'react';
import {interpolate} from 'remotion';
import {enter, revealAt} from '../../lib/anim';
import {fitBlock, fitSize} from '../../lib/fit';
import {FONT} from '../../design/tokens';
import {ChalkFilter, MaskLine, ParenLabel} from '../layout/Editorial';
import type {TemplateProps} from './common';

const DiagramTitle: React.FC<{text: string; label: string} & TemplateProps> = ({text, label, frame, surface, box,
  compact}) => {
  if (!text) return null;
  const size = fitSize(text, box.w * 0.9, compact ? 50 : 64, 30, -0.03);
  return (
    <div style={{position: 'absolute', top: 0, left: 0, right: 0}}>
      {!compact ? <ParenLabel text={label} surface={surface} frame={frame} size={22} /> : null}
      <MaskLine frame={frame} delay={2} style={{marginTop: compact ? 0 : 10}}>
        <div style={{fontFamily: FONT.display, fontWeight: 800, fontSize: size, letterSpacing: '-0.03em',
          color: surface.fg}}>{text}</div>
      </MaskLine>
    </div>
  );
};

const titleSpace = (props: TemplateProps) => (props.data.title ? (props.compact ? 70 : 130) : 0);

/** 현재 강조 인덱스: highlight 지정이 있으면 그것, 없으면 -1 */
const hl = (props: TemplateProps) =>
  typeof props.data.highlight === 'number' && props.data.highlight >= 0 ? props.data.highlight : -1;

// ---------------------------------------------------------------------------
// 단계 프로세스 — 선으로 이어진 노드, 현재 단계 강조
// ---------------------------------------------------------------------------
export const ProcessDiagram: React.FC<TemplateProps> = (props) => {
  const {data, frame, dur, surface, box, id, compact} = props;
  const items = (data.items || []).slice(0, 7);
  const n = Math.max(1, items.length);
  const top = titleSpace(props);
  const h = box.h - top;
  const cy = top + h * 0.42;
  const slot = box.w / n;
  const r = Math.min(slot * 0.3, h * 0.2, compact ? 62 : 86);
  const active = hl(props);
  const lineP = enter(frame, 4, Math.max(18, dur * 0.3));
  const labelSize = Math.min(fitSize(items.reduce((a, b) => (a.length > b.length ? a : b), ''), slot * 0.9,
    compact ? 34 : 42, 20), compact ? 34 : 42);
  const fid = `chalk-${id}`;
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <DiagramTitle text={data.title || ''} label="프로세스" {...props} />
      <svg width={box.w} height={box.h} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
        <ChalkFilter id={fid} on={surface.chalk} />
        <g filter={surface.chalk ? `url(#${fid})` : undefined}>
          <line x1={slot / 2} y1={cy} x2={slot / 2 + (box.w - slot) * lineP} y2={cy} stroke={surface.dim}
            strokeWidth={3} />
          {items.map((_, i) => {
            const at = active >= 0 ? 6 + i * 4 : revealAt(i, n, dur, 6) * 0.6;
            const p = enter(frame, at, 14);
            const cx = slot * i + slot / 2;
            const on = i === active;
            return (
              <g key={i} opacity={p}>
                <circle cx={cx} cy={cy} r={r * interpolate(p, [0, 1], [0.6, 1])}
                  fill={on ? surface.accent : surface.bg} stroke={on ? surface.accent : surface.fg} strokeWidth={3} />
                {i < n - 1 ? (
                  <path d={`M ${cx + r + slot * 0.08} ${cy} l ${slot - 2 * r - slot * 0.22} 0 m -14 -10 l 14 10 l -14 10`}
                    stroke={surface.fg} strokeWidth={3} fill="none" opacity={enter(frame, at + 6, 10)} />
                ) : null}
              </g>
            );
          })}
        </g>
        {items.map((_, i) => {
          const cx = slot * i + slot / 2;
          const on = i === active;
          return (
            <text key={`n${i}`} x={cx} y={cy + r * 0.22} textAnchor="middle" fontFamily="Anton" fontSize={r * 0.72}
              fill={on ? surface.bg : surface.fg} opacity={enter(frame, 8 + i * 4, 12)}>{i + 1}</text>
          );
        })}
      </svg>
      {items.map((it, i) => {
        const cx = slot * i + slot / 2;
        const on = i === active;
        return (
          <div key={i} style={{position: 'absolute', left: cx - slot * 0.46, width: slot * 0.92, top: cy + r + 28,
            textAlign: 'center', fontFamily: FONT.sans, fontSize: labelSize, fontWeight: on ? 800 : 500,
            color: on ? surface.accent : surface.fg, opacity: enter(frame, 10 + i * 4, 12) * (active >= 0 && !on ? 0.7 : 1),
            lineHeight: 1.25}}>{it}</div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 순환 구조
// ---------------------------------------------------------------------------
export const CycleDiagram: React.FC<TemplateProps> = (props) => {
  const {data, frame, dur, surface, box, id, compact} = props;
  const items = (data.items || []).slice(0, 6);
  const n = Math.max(2, items.length);
  const top = titleSpace(props);
  const h = box.h - top;
  const cx = box.w / 2;
  const cy = top + h / 2;
  const R = Math.min(h * 0.36, box.w * 0.3);
  const node = Math.min(R * 0.36, compact ? 70 : 92);
  const active = hl(props);
  const fid = `chalk-${id}`;
  const rot = interpolate(frame, [0, dur], [0, 8]);
  const pos = (i: number) => {
    const a = (-90 + (360 / n) * i) * (Math.PI / 180);
    return [cx + R * Math.cos(a), cy + R * Math.sin(a)];
  };
  const arcP = enter(frame, 4, Math.max(24, dur * 0.35));
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <DiagramTitle text={data.title || ''} label="순환" {...props} />
      <svg width={box.w} height={box.h} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
        <ChalkFilter id={fid} on={surface.chalk} />
        <g filter={surface.chalk ? `url(#${fid})` : undefined}>
          <circle cx={cx} cy={cy} r={R} fill="none" stroke={surface.dim} strokeWidth={3} pathLength={1}
            strokeDasharray={1} strokeDashoffset={1 - arcP} transform={`rotate(${-90 + rot} ${cx} ${cy})`} />
          {items.map((_, i) => {
            // 원 위의 화살촉(시계 방향)
            const a = (-90 + (360 / n) * (i + 0.5)) * (Math.PI / 180);
            const x = cx + R * Math.cos(a);
            const y = cy + R * Math.sin(a);
            const deg = (a * 180) / Math.PI + 90;
            return (
              <path key={i} d="M -12 -9 L 0 0 L -12 9" transform={`translate(${x} ${y}) rotate(${deg})`}
                stroke={surface.fg} strokeWidth={3} fill="none" opacity={enter(frame, 10 + i * 3, 10)} />
            );
          })}
        </g>
      </svg>
      {items.map((it, i) => {
        const [x, y] = pos(i);
        const on = i === active;
        const p = enter(frame, active >= 0 ? 6 + i * 3 : revealAt(i, n, dur, 6) * 0.6, 14);
        const lab = fitBlock(it, node * 2.6, node * 1.6, compact ? 32 : 38, 18, 1.2, 2);
        return (
          <div key={i} style={{position: 'absolute', left: x - node * 1.3, top: y - node * 0.62, width: node * 2.6,
            height: node * 1.24, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center',
            background: on ? surface.accent : surface.bg, border: `3px solid ${on ? surface.accent : surface.fg}`,
            borderRadius: node * 0.62, opacity: p, scale: `${interpolate(p, [0, 1], [0.85, 1])}`,
            fontFamily: FONT.sans, fontWeight: on ? 800 : 600, fontSize: lab.size, lineHeight: 1.2,
            color: on ? surface.bg : surface.fg, boxSizing: 'border-box', padding: 8}}>
            <div>{lab.lines.map((l, k) => <div key={k}>{l}</div>)}</div>
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 더블 다이아몬드 (Design Council, 2005)
// ---------------------------------------------------------------------------
export const DoubleDiamond: React.FC<TemplateProps> = (props) => {
  const {data, frame, dur, surface, box, id, compact} = props;
  const labels = (data.items && data.items.length === 4 ? data.items : ['발견', '정의', '개발', '전달']);
  const phases = ['발산', '수렴', '발산', '수렴'];
  const top = titleSpace(props);
  const h = box.h - top;
  const W = box.w;
  const midY = top + h * (compact ? 0.47 : 0.44);
  const dh = Math.min(h * (compact ? 0.24 : 0.34), W * 0.14);
  const phaseGap = compact ? 40 : 62;
  const x0 = W * 0.02;
  const x4 = W * 0.98;
  const q = (x4 - x0) / 4;
  const xs = [x0, x0 + q, x0 + 2 * q, x0 + 3 * q, x4];
  const active = hl(props);
  const fid = `chalk-${id}`;
  const d1 = `M ${xs[0]} ${midY} L ${xs[1]} ${midY - dh} L ${xs[2]} ${midY} L ${xs[1]} ${midY + dh} Z`;
  const d2 = `M ${xs[2]} ${midY} L ${xs[3]} ${midY - dh} L ${xs[4]} ${midY} L ${xs[3]} ${midY + dh} Z`;
  const quarter = (i: number) => {
    // i번째 사분(삼각형) 영역
    const a = xs[i];
    const b = xs[i + 1];
    const peakLeft = i % 2 === 0; // 발산: 왼쪽 점 → 오른쪽 넓음
    return peakLeft
      ? `M ${a} ${midY} L ${b} ${midY - dh} L ${b} ${midY + dh} Z`
      : `M ${a} ${midY - dh} L ${b} ${midY} L ${a} ${midY + dh} Z`;
  };
  const drawP1 = enter(frame, 4, Math.max(20, dur * 0.22));
  const drawP2 = enter(frame, 10, Math.max(20, dur * 0.22));
  const labelSize = compact ? 34 : 44;
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <DiagramTitle text={data.title || '더블 다이아몬드'} label="Double Diamond · Design Council" {...props} />
      <svg width={W} height={box.h} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
        <ChalkFilter id={fid} on={surface.chalk} />
        {active >= 0 ? (
          <path d={quarter(active)} fill={surface.accent} fillOpacity={0.36} opacity={enter(frame, 12, 14)} />
        ) : null}
        <g filter={surface.chalk ? `url(#${fid})` : undefined} fill="none" stroke={surface.fg} strokeWidth={3.5}>
          <path d={d1} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - drawP1} />
          <path d={d2} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - drawP2} />
          {[1, 2, 3].map((k) => (
            <line key={k} x1={xs[k]} y1={midY - dh - 30} x2={xs[k]} y2={midY + dh + 30} stroke={surface.dim}
              strokeWidth={2} strokeDasharray="6 10" opacity={enter(frame, 14 + k * 2, 10)} />
          ))}
        </g>
      </svg>
      {labels.map((l, i) => {
        const on = i === active;
        const cx = (xs[i] + xs[i + 1]) / 2;
        return (
          <React.Fragment key={i}>
            <div style={{position: 'absolute', left: cx - q / 2, width: q, top: midY - dh - phaseGap, textAlign: 'center',
              fontFamily: FONT.sans, fontSize: compact ? 20 : 24, fontWeight: 500, color: surface.dim,
              opacity: enter(frame, 16 + i * 3, 12)}}>{phases[i]}</div>
            <div style={{position: 'absolute', left: cx - q / 2, width: q, top: midY + dh + (compact ? 18 : 30), textAlign: 'center',
              fontFamily: FONT.sans, fontSize: labelSize, fontWeight: on ? 800 : 600,
              color: on ? surface.accent : surface.fg, opacity: enter(frame, 18 + i * 3, 12)}}>{l}</div>
            {!compact ? (
              <div style={{position: 'absolute', left: cx - q / 2, width: q, top: midY + dh + 30 + labelSize * 1.35,
                textAlign: 'center', fontFamily: FONT.latin, fontSize: 22, color: surface.dim,
                opacity: enter(frame, 20 + i * 3, 12)}}>
                {['DISCOVER', 'DEFINE', 'DEVELOP', 'DELIVER'][i]}
              </div>
            ) : null}
          </React.Fragment>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 2x2 매트릭스
// ---------------------------------------------------------------------------
export const MatrixDiagram: React.FC<TemplateProps> = (props) => {
  const {data, frame, surface, box, id, compact} = props;
  const quads = (data.items || []).slice(0, 4);
  const axes = data.items_b || [];
  const top = titleSpace(props);
  const size = Math.min(box.h - top - 40, box.w * 0.62);
  const x0 = (box.w - size) / 2;
  const y0 = top + (box.h - top - size) / 2;
  const active = hl(props);
  const fid = `chalk-${id}`;
  const p = enter(frame, 4, 18);
  const cell = size / 2;
  const qpos = [[0, 0], [1, 0], [0, 1], [1, 1]];
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <DiagramTitle text={data.title || ''} label="매트릭스" {...props} />
      <svg width={box.w} height={box.h} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
        <ChalkFilter id={fid} on={surface.chalk} />
        {active >= 0 && active < 4 ? (
          <rect x={x0 + qpos[active][0] * cell + 6} y={y0 + qpos[active][1] * cell + 6} width={cell - 12}
            height={cell - 12} fill={surface.accent} opacity={0.3 * enter(frame, 14, 12)} />
        ) : null}
        <g filter={surface.chalk ? `url(#${fid})` : undefined} stroke={surface.fg} strokeWidth={3} fill="none">
          <line x1={x0} y1={y0 + cell} x2={x0 + size * p} y2={y0 + cell} />
          <line x1={x0 + cell} y1={y0 + size} x2={x0 + cell} y2={y0 + size - size * p} />
          <path d={`M ${x0 + size - 16} ${y0 + cell - 10} L ${x0 + size} ${y0 + cell} L ${x0 + size - 16} ${y0 + cell + 10}`}
            opacity={p} />
          <path d={`M ${x0 + cell - 10} ${y0 + 16} L ${x0 + cell} ${y0} L ${x0 + cell + 10} ${y0 + 16}`} opacity={p} />
        </g>
      </svg>
      {quads.map((qd, i) => {
        const on = i === active;
        const lab = fitBlock(qd, cell * 0.8, cell * 0.6, compact ? 34 : 44, 18, 1.25, 3);
        return (
          <div key={i} style={{position: 'absolute', left: x0 + qpos[i][0] * cell, top: y0 + qpos[i][1] * cell,
            width: cell, height: cell, display: 'flex', alignItems: 'center', justifyContent: 'center',
            textAlign: 'center', fontFamily: FONT.sans, fontSize: lab.size, fontWeight: on ? 800 : 600,
            color: on ? surface.accent : surface.fg, opacity: enter(frame, 10 + i * 4, 12), lineHeight: 1.25}}>
            <div>{lab.lines.map((l, k) => <div key={k}>{l}</div>)}</div>
          </div>
        );
      })}
      {axes.length >= 4 ? (
        <>
          <div style={{position: 'absolute', left: x0 - 12, top: y0 + cell + 12, translate: '-100% 0',
            fontFamily: FONT.sans, fontSize: 22, color: surface.dim}}>{axes[0]}</div>
          <div style={{position: 'absolute', left: x0 + size + 12, top: y0 + cell + 12, fontFamily: FONT.sans,
            fontSize: 22, color: surface.dim}}>{axes[1]}</div>
          <div style={{position: 'absolute', left: x0 + cell + 14, top: y0 + size - 30, fontFamily: FONT.sans,
            fontSize: 22, color: surface.dim}}>{axes[2]}</div>
          <div style={{position: 'absolute', left: x0 + cell + 22, top: y0 - 4, fontFamily: FONT.sans, fontSize: 22,
            color: surface.dim}}>{axes[3]}</div>
        </>
      ) : null}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 벤 다이어그램
// ---------------------------------------------------------------------------
export const VennDiagram: React.FC<TemplateProps> = (props) => {
  const {data, frame, surface, box, id, compact} = props;
  const items = (data.items || []).slice(0, 3);
  const n = items.length >= 3 ? 3 : 2;
  const top = titleSpace(props);
  const h = box.h - top;
  const cx = box.w / 2;
  const cy = top + h / 2 + (n === 3 ? 10 : 0);
  const r = Math.min(h * (n === 3 ? 0.3 : 0.36), box.w * 0.22);
  const off = r * 0.62;
  const centers: [number, number][] = n === 3
    ? [[cx - off, cy - off * 0.55], [cx + off, cy - off * 0.55], [cx, cy + off * 0.75]]
    : [[cx - off, cy], [cx + off, cy]];
  const fid = `chalk-${id}`;
  const labSize = compact ? 32 : 40;
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <DiagramTitle text={data.title || ''} label="교집합" {...props} />
      <svg width={box.w} height={box.h} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
        <ChalkFilter id={fid} on={surface.chalk} />
        <g filter={surface.chalk ? `url(#${fid})` : undefined}>
          {centers.map(([x, y], i) => {
            const p = enter(frame, 4 + i * 6, 18);
            return (
              <circle key={i} cx={x} cy={y} r={r} fill={surface.fg} fillOpacity={0.06 * p} stroke={surface.fg}
                strokeWidth={3} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - p} />
            );
          })}
        </g>
        <circle cx={n === 3 ? cx : cx} cy={n === 3 ? cy - off * 0.1 : cy} r={r * 0.2} fill={surface.accent}
          opacity={0.9 * enter(frame, 20, 12)} />
      </svg>
      {centers.map(([x, y], i) => {
        const dx = x - cx;
        const dy = y - cy;
        const lx = x + dx * 0.55;
        const ly = y + dy * 0.55;
        return (
          <div key={i} style={{position: 'absolute', left: lx - r * 0.7, top: ly - labSize * 0.7, width: r * 1.4,
            textAlign: 'center', fontFamily: FONT.sans, fontSize: labSize, fontWeight: 700, color: surface.fg,
            opacity: enter(frame, 10 + i * 6, 12)}}>{items[i]}</div>
        );
      })}
      {data.body ? (
        <div style={{position: 'absolute', left: cx - r, width: r * 2, top: (n === 3 ? cy - off * 0.1 : cy) + r * 0.28,
          textAlign: 'center', fontFamily: FONT.sans, fontSize: compact ? 26 : 30, fontWeight: 800, color: surface.accent,
          opacity: enter(frame, 24, 12)}}>{data.body}</div>
      ) : null}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 피라미드(아래→위)
// ---------------------------------------------------------------------------
export const PyramidDiagram: React.FC<TemplateProps> = (props) => {
  const {data, frame, dur, surface, box, compact} = props;
  const items = (data.items || []).slice(0, 5);
  const n = Math.max(1, items.length);
  const top = titleSpace(props);
  const h = box.h - top - 20;
  const baseW = Math.min(box.w * 0.72, h * 1.5);
  const layerH = h / n;
  const cx = box.w / 2;
  const active = hl(props);
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <DiagramTitle text={data.title || ''} label="위계" {...props} />
      {items.map((it, i) => {
        // i=0 이 가장 아래
        const level = i;
        const wBottom = baseW * (1 - level / n);
        const wTop = baseW * (1 - (level + 1) / n);
        const y = top + h - (level + 1) * layerH;
        const on = i === active;
        const p = enter(frame, active >= 0 ? 4 + i * 5 : revealAt(i, n, dur, 4) * 0.6, 14);
        const clip = `polygon(${(baseW - wTop) / 2}px 0, ${(baseW + wTop) / 2}px 0, ${(baseW + wBottom) / 2}px 100%, ${(baseW - wBottom) / 2}px 100%)`;
        return (
          <div key={i} style={{position: 'absolute', left: cx - baseW / 2, top: y + 3, width: baseW, height: layerH - 6,
            clipPath: clip, background: on ? surface.accent : i % 2 ? surface.faint : 'rgba(255,255,255,0.06)',
            border: 'none', opacity: p, translate: `0 ${interpolate(p, [0, 1], [20, 0])}px`,
            display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: FONT.sans,
            fontSize: Math.min(layerH * 0.34, compact ? 32 : 40), fontWeight: on ? 800 : 600,
            color: on ? surface.bg : surface.fg, outline: `2px solid ${surface.rule}`}}>
            {it}
          </div>
        );
      })}
    </div>
  );
};
