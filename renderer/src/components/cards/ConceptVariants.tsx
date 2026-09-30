import React from 'react';
import {interpolate} from 'remotion';
import {tween} from '../../design/motion';
import {FONT} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {fitSize, wrap} from '../../lib/fit';
import {warmOf} from '../captions/Stack';
import {AccentText, LabelTag, PaperBg, pickAccent} from '../paper/Paper';

/**
 * 숏폼 개념 카드 세 가지(참고 릴스에서 옮긴 카드 언어) — ReelShort 위 카드 **전용**. 롱폼은 자기 언어(components/longform/,
 * docs/롱폼_무대_디자인.md)를 쓰고 이 카드를 옮겨 오지 않는다.
 *  0 = 흰 카드 + 짙은 굵은 고딕 + 형광펜(핵심어 아래 마커가 쓸리듯 칠해진다)
 *  1 = 크림 카드 + 기울인 명조 라벨 + 큰 명조 헤드라인(한 낱말만 따뜻한 강조색), 흐림 → 선명
 *  2 = 구겨진 짙은 종이 + 흰 라벨 태그 + 흰 헤드라인(한 낱말만 주황) + 회색 주석
 * 크기는 980×720 카드 기준이고 `scale` 로 줄일 수 있다.
 */
export const INK = '#17181C';

export const Marker: React.FC<{text: string; p: number; color: string}> = ({text, p, color}) => (
  <span style={{backgroundImage: `linear-gradient(transparent 58%, ${color} 58%, ${color} 92%, transparent 92%)`,
    backgroundSize: `${Math.max(0, Math.min(1, p)) * 100}% 100%`, backgroundRepeat: 'no-repeat'}}>{text}</span>
);

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
  big?: boolean; // 숫자 한 방(stat): 헤드라인을 훨씬 크게(숫자는 Anton)
  f: number; // 카드 시작 기준 프레임
  w: number; // 카드 안쪽 폭(px)
  theme: Theme;
  marker: string; // 형광펜 색(rgba)
  variant?: number; // 0 | 1 | 2
  paperTexture?: string;
  scale?: number; // 980 폭 기준 배율
  align?: 'center' | 'left';
};

export const ConceptCardBody: React.FC<ConceptCardProps> = ({label, head, body, accent, big = false, f, w, theme,
  marker, variant = 0, paperTexture, scale = 1, align = 'center'}) => {
  const pad = Math.round((variant === 0 ? 60 : 70) * scale);
  const innerW = w - pad * 2;
  const numeric = NUMERIC.test(head.trim());
  const maxHead = (big ? 210 : 118) * scale;
  const {lines} = balancedWrap(head, (big ? 200 : 110) * scale, innerW, 3);
  const size = Math.min(maxHead, ...lines.map((l) => fitSize(l, innerW, maxHead, 56 * scale, -0.045)));
  const headFont = numeric ? FONT.latin : FONT.display;
  const bodyLines = body ? wrap(body, 36 * scale, innerW, 2) : [];
  const flex: React.CSSProperties = {position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
    alignItems: align === 'center' ? 'center' : 'flex-start', justifyContent: 'center', padding: `0 ${pad}px`,
    textAlign: align};
  if (variant === 2) {
    const ps = Math.min(maxHead, ...lines.map((l) => fitSize(l, innerW, maxHead, 56 * scale, -0.035)));
    return (
      <div style={{position: 'absolute', inset: 0}}>
        <PaperBg src={paperTexture} />
        <div style={{...flex, alignItems: 'flex-start', textAlign: 'left'}}>
          {label ? <div style={{opacity: tween(f, 2, 10), marginBottom: 22 * scale}}>
            <LabelTag text={label} size={34 * scale} /></div> : null}
          {lines.map((l, i) => (
            <div key={i} style={{fontFamily: headFont, fontWeight: numeric ? 400 : 500, fontSize: ps, lineHeight: 1.16,
              letterSpacing: '-0.04em', whiteSpace: 'nowrap', opacity: tween(f, 3 + i * 3, 12),
              translate: `0 ${interpolate(tween(f, 3 + i * 3, 14), [0, 1], [16, 0])}px`}}>
              <AccentText text={l} accent={i === lines.length - 1 ? accent : null} />
            </div>
          ))}
          {bodyLines.length ? <div style={{marginTop: 20 * scale, fontFamily: FONT.sans, fontSize: 36 * scale,
            lineHeight: 1.45, color: 'rgba(244,244,245,0.9)', opacity: tween(f, 10, 12)}}>
            {bodyLines.map((l, i) => <div key={i}>{l}</div>)}</div> : null}
        </div>
      </div>
    );
  }
  if (variant === 1) {
    const serifSize = Math.min(maxHead, ...lines.map((l) => fitSize(l, innerW, maxHead, 56 * scale, -0.02)));
    const a = pickAccent(lines[lines.length - 1] ?? '', accent);
    return (
      <div style={{...flex, background: '#FBF7F0'}}>
        {label ? <div style={{fontFamily: FONT.serif, fontStyle: 'italic', fontWeight: 700, fontSize: 38 * scale,
          color: warmOf(theme.accent), marginBottom: 14 * scale, opacity: tween(f, 2, 10)}}>{label}</div> : null}
        {lines.map((l, i) => {
          const last = i === lines.length - 1;
          const k = last && a ? l.indexOf(a) : -1;
          const p = tween(f, 3 + i * 3, 12);
          return (
            <div key={i} style={{fontFamily: numeric ? FONT.latin : FONT.serif, fontWeight: 700, fontSize: serifSize, lineHeight: 1.22,
              letterSpacing: '-0.02em', color: INK, whiteSpace: 'nowrap', opacity: p,
              filter: `blur(${interpolate(p, [0, 1], [8, 0])}px)`}}>
              {k < 0 ? l : <>{l.slice(0, k)}<span style={{color: theme.accent}}>{a}</span>{l.slice(k + a.length)}</>}
            </div>
          );
        })}
        {bodyLines.length ? <div style={{marginTop: 22 * scale, fontFamily: FONT.serif, fontStyle: 'italic',
          fontWeight: 500, fontSize: 36 * scale, lineHeight: 1.45, color: '#6A625A', opacity: tween(f, 10, 12)}}>
          {bodyLines.map((l, i) => <div key={i}>{l}</div>)}</div> : null}
      </div>
    );
  }
  return (
    <div style={{...flex, background: '#FFFFFF'}}>
      {label ? <div style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: 32 * scale, color: theme.accent,
        marginBottom: 18 * scale, opacity: tween(f, 2, 10)}}>{label}</div> : null}
      {lines.map((l, i) => (
        <div key={i} style={{fontFamily: headFont, fontWeight: numeric ? 400 : 800, fontSize: size, lineHeight: 1.18,
          letterSpacing: numeric ? '0' : '-0.045em', color: INK, whiteSpace: 'nowrap',
          opacity: tween(f, 3 + i * 3, 12), translate: `0 ${interpolate(tween(f, 3 + i * 3, 14), [0, 1], [18, 0])}px`}}>
          <Highlighted text={l} accent={i === lines.length - 1 ? accent : null} p={tween(f, 12 + i * 3, 14)}
            color={marker} />
        </div>
      ))}
      {bodyLines.length ? <div style={{marginTop: 22 * scale, fontFamily: FONT.sans, fontWeight: 500,
        fontSize: 38 * scale, lineHeight: 1.4, color: '#5A5A60', opacity: tween(f, 10, 12)}}>
        {bodyLines.map((l, i) => <div key={i}>{l}</div>)}</div> : null}
    </div>
  );
};
