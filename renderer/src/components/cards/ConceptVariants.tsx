import React from 'react';
import {interpolate} from 'remotion';
import {tween} from '../../design/motion';
import {FONT, MODERN, softShadow} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {fitSize, wrap} from '../../lib/fit';
import {accentFont} from '../modern/Modern';
import {pickAccent} from '../paper/Paper';

/**
 * 숏폼 개념 카드 세 가지 — ReelShort 위 카드 **전용**(롱폼은 자기 언어를 쓴다). 디자인 v4 모던 모션(2026-10-02):
 *  0 = 흰 UI 카드: 작은 알약 라벨 + 자간 좁힌 굵은 산세리프 헤드라인, 강조 어절 하나는 이탤릭 세리프(짙은 디자인 색)
 *  1 = 밝은 무대: 헤드라인 둘레 코너 마크 넷 + 가는 대문자 라벨, 흐림 → 선명
 *  2 = 어두운 카드(차콜): 흰 헤드라인 + 디자인 색 강조 어절 + 흐린 주석
 * 크기는 980×720 카드 기준이고 `scale` 로 줄일 수 있다. 종이 질감·형광펜·명조 본문은 쓰지 않는다.
 */
export const INK = MODERN.ink;

/** 강조 어절: 디자인 색으로 드러난다(p 0→1 로 색이 차오름). 예전 형광펜 마커의 자리 — API 는 그대로 */
export const Marker: React.FC<{text: string; p: number; color: string}> = ({text, p, color}) => {
  const f = accentFont(text);
  return (
    <span style={{color, opacity: 0.35 + 0.65 * Math.max(0, Math.min(1, p)), fontFamily: f.font, fontWeight: f.weight,
      fontStyle: f.skew ? undefined : 'italic', display: 'inline-block', transform: f.skew ? 'skewX(-8deg)' : undefined,
      letterSpacing: '-0.01em'}}>{text}</span>
  );
};

export const Highlighted: React.FC<{text: string; accent?: string | null; p: number; color: string}> = ({text, accent, p,
  color}) => {
  const a = pickAccent(text, accent);
  const i = a ? text.indexOf(a) : -1;
  if (i < 0) return <>{text}</>;
  return <>{text.slice(0, i)}<Marker text={a} p={p} color={color} />{text.slice(i + a.length)}</>;
};

/** 줄바꿈이 마지막 줄에 한 낱말만 남기지 않게(고아 줄 금지): 크기를 조금씩 줄여 한 줄이 되거나 줄 길이가 고르게 될 때까지 */
export const balancedWrap = (text: string, size: number, maxW: number, maxLines = 3): {lines: string[]; size: number} => {
  let s = size;
  for (let i = 0; i < 6; i++) {
    const lines = wrap(text, s, maxW, maxLines).slice(0, maxLines);
    if (lines.length <= 1) return {lines, size: s};
    const last = lines[lines.length - 1].replace(/\s/g, '').length;
    const first = lines[0].replace(/\s/g, '').length;
    if (last >= Math.max(3, first * 0.45)) return {lines, size: s};
    s *= 0.88;
  }
  return {lines: wrap(text, s, maxW, maxLines).slice(0, maxLines), size: s};
};

const NUMERIC = /^[\d.,%+\-−~:/\s]+[\d%]$/;

export type ConceptCardProps = {
  label: string;
  head: string;
  body?: string;
  accent?: string;
  big?: boolean; // 숫자 한 방(stat): 헤드라인을 훨씬 크게
  f: number; // 카드 시작 기준 프레임
  w: number; // 카드 안쪽 폭(px)
  theme: Theme;
  marker: string; // 강조 어절 색(v4: 짙은 디자인 색)
  variant?: number; // 0 | 1 | 2
  paperTexture?: string; // (v3 호환 — 쓰지 않는다)
  scale?: number; // 980 폭 기준 배율
  align?: 'center' | 'left';
};

/** 작은 알약 라벨(v4 칩) */
const PillLabel: React.FC<{text: string; scale: number; dark: boolean; theme: Theme; p: number}> = ({text, scale, dark,
  theme, p}) => (
  <div style={{display: 'inline-block', fontFamily: FONT.sans, fontWeight: 600, fontSize: 26 * scale, lineHeight: 1,
    letterSpacing: '0.04em', padding: `${12 * scale}px ${20 * scale}px`, borderRadius: 999,
    background: dark ? 'rgba(244,244,242,0.12)' : theme.accentTint, color: dark ? MODERN.darkInk : theme.accentDeep,
    opacity: p, translate: `0 ${interpolate(p, [0, 1], [8, 0])}px`}}>{text}</div>
);

export const ConceptCardBody: React.FC<ConceptCardProps> = ({label, head, body, accent, big = false, f, w, theme,
  marker, variant = 0, scale = 1, align = 'center'}) => {
  const pad = Math.round(64 * scale);
  const innerW = w - pad * 2;
  const numeric = NUMERIC.test(head.trim());
  const maxHead = (big ? 210 : 118) * scale;
  const {lines} = balancedWrap(head, (big ? 200 : 110) * scale, innerW, 3);
  const size = Math.min(maxHead, ...lines.map((l) => fitSize(l, innerW, maxHead, 56 * scale, -0.035)));
  const headFont = numeric ? FONT.numeral : FONT.sans;
  const bodyLines = body ? wrap(body, 34 * scale, innerW, 2) : [];
  const dark = variant === 2;
  const ink = dark ? MODERN.darkInk : MODERN.ink;
  const soft = dark ? MODERN.darkSoft : MODERN.inkSoft;
  const accentColor = dark ? theme.accent : marker;
  const flex: React.CSSProperties = {position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
    alignItems: align === 'center' ? 'center' : 'flex-start', justifyContent: 'center', padding: `0 ${pad}px`,
    textAlign: align};
  const headline = lines.map((l, i) => {
    const p = tween(f, 3 + i * 3, 12);
    const blur = variant === 1 ? `blur(${interpolate(p, [0, 1], [8, 0])}px)` : undefined;
    return (
      <div key={i} style={{fontFamily: headFont, fontWeight: numeric ? 900 : 800, fontSize: size, lineHeight: 1.08,
        letterSpacing: numeric ? '-0.05em' : '-0.035em', color: ink, whiteSpace: 'nowrap', opacity: p, filter: blur,
        translate: variant === 1 ? undefined : `0 ${interpolate(tween(f, 3 + i * 3, 14), [0, 1], [18, 0])}px`}}>
        <Highlighted text={l} accent={i === lines.length - 1 ? accent : null} p={tween(f, 10 + i * 3, 14)} color={accentColor} />
      </div>
    );
  });
  const bodyEl = bodyLines.length ? (
    <div style={{marginTop: 22 * scale, fontFamily: FONT.sans, fontWeight: 500, fontSize: 34 * scale, lineHeight: 1.45,
      color: soft, opacity: tween(f, 10, 12)}}>{bodyLines.map((l, i) => <div key={i}>{l}</div>)}</div>
  ) : null;
  if (variant === 1) {
    // 밝은 무대 + 코너 마크: 헤드라인 덩어리 둘레에 작은 네모 넷(v4 CornerMarks 의 숏폼 판)
    const mk = 14 * scale;
    const p = tween(f, 2, 12);
    const corner = (x: 'left' | 'right', y: 'top' | 'bottom') => (
      <div style={{position: 'absolute', [x]: pad - 36 * scale, [y]: 150 * scale, width: mk, height: mk,
        border: `2px solid ${theme.accentDeep}`, opacity: p}} />
    );
    return (
      <div style={{position: 'absolute', inset: 0, background: MODERN.bg}}>
        {corner('left', 'top')}{corner('right', 'top')}{corner('left', 'bottom')}{corner('right', 'bottom')}
        <div style={flex}>
          {label ? <div style={{fontFamily: FONT.sans, fontWeight: 600, fontSize: 24 * scale, letterSpacing: '0.14em',
            color: soft, marginBottom: 20 * scale, opacity: tween(f, 2, 10)}}>{label.toUpperCase()}</div> : null}
          {headline}
          {bodyEl}
        </div>
      </div>
    );
  }
  return (
    <div style={{...flex, background: dark ? MODERN.dark : MODERN.card}}>
      {label ? <div style={{marginBottom: 22 * scale}}>
        <PillLabel text={label} scale={scale} dark={dark} theme={theme} p={tween(f, 2, 10)} /></div> : null}
      {headline}
      {bodyEl}
      {dark ? null : <div style={{position: 'absolute', inset: 0, borderRadius: 'inherit', boxShadow: softShadow(1),
        pointerEvents: 'none', opacity: 0}} />}
    </div>
  );
};
