import React from 'react';
import {Img, interpolate, staticFile} from 'remotion';
import {EASE, placeIn, tween} from '../../design/motion';
import {FONT, mix, paperDropShadow, paperRotate, paperShadow} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {grainOffset, speckleTile, useNoiseTile, useTileUrl} from '../../lib/noise';

/**
 * 프레스 킷 — 디자인 v3 '종이 콜라주'(운영자 레퍼런스, docs/디자인_v3_종이콜라주.md): 크림 종이 무대 · 인쇄 얼룩이 있는 굵은
 * 한글 · 이탤릭 세리프 연도 · 오려 낸 망점 사진 + 바닥 타원 · 형광펜 · 문서 장 · 영상 위 명조 인용.
 * 모든 질감은 정적(타일·그라데이션) — 프레임마다 바뀌는 필터 없음(렌더 속도 규칙). 움직임은 tween/placeIn 만.
 */

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

/** 종이 무대 팔레트: 크림 종이(위) → 디자인 색이 아주 옅게 번진 종이(아래) · 웜 잉크 · 짙은 색 · 옅은 색 */
export const pressColors = (theme: Theme) => {
  const paper = '#ECEAE1';
  return {
    paper,
    paperLow: mix(paper, theme.accentTint, 0.3),
    paperLight: '#F6F4EE',
    ink: '#24211E',
    inkSoft: 'rgba(36,33,30,0.72)',
    deep: theme.accentDeep,
    mid: theme.accent,
    tint: theme.accentTint,
  };
};

const hexRgb = (hex: string): [number, number, number] => {
  const m = hex.replace('#', '').match(/^([0-9a-f]{6})$/i);
  if (!m) return [236, 234, 225];
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

/** 종이 무대: 크림 → 옅은 디자인 색 그라데이션 + 종이 입자 + 가장자리 아주 옅은 그늘 */
export const PaperStage: React.FC<{theme: Theme; frame?: number; grain?: number}> = ({theme, frame = 0, grain = 0.11}) => {
  const c = pressColors(theme);
  const tile = useNoiseTile(11, 0.36, 0.5);
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden',
      background: `linear-gradient(180deg, ${c.paper} 0%, ${c.paper} 46%, ${c.paperLow} 100%)`}}>
      <div style={{position: 'absolute', inset: 0, opacity: grain, mixBlendMode: 'multiply',
        backgroundImage: `url(${tile})`, backgroundSize: '256px 256px', backgroundPosition: grainOffset(Math.floor(frame / 3))}} />
      <div style={{position: 'absolute', inset: 0, background:
        'radial-gradient(130% 115% at 50% 42%, rgba(0,0,0,0) 62%, rgba(36,33,30,0.10) 100%)'}} />
    </div>
  );
};

/** 인쇄 얼룩이 있는 큰 글자(레퍼런스 '설계안 채택'): 글자 모양 안에만 종이색 점 — background-clip: text */
export const PrintText: React.FC<{text: string; size: number; color: string; font?: string; weight?: number;
  italic?: boolean; seed?: number; density?: number; paper?: string; letterSpacing?: string; lineHeight?: number;
  style?: React.CSSProperties}> = ({text, size, color, font = FONT.heavy, weight = 400, italic = false, seed = 5,
  density = 0.05, paper = '#ECEAE1', letterSpacing = '-0.01em', lineHeight = 1.02, style}) => {
  const sp = useTileUrl(speckleTile(seed, density, hexRgb(paper)));
  const tile = Math.max(96, Math.round(size * 1.2));
  return (
    <span style={{fontFamily: font, fontWeight: weight, fontStyle: italic ? 'italic' : 'normal', fontSize: size, lineHeight,
      letterSpacing, whiteSpace: 'pre', color: 'transparent',
      backgroundImage: `url(${sp}), linear-gradient(${color}, ${color})`,
      backgroundSize: `${tile}px ${tile}px, 100% 100%`, WebkitBackgroundClip: 'text', backgroundClip: 'text',
      paddingRight: italic ? size * 0.08 : 0, ...style}}>
      {text}
    </span>
  );
};

/** 망점 무늬(정적) — 색 면·사진 위에 곱하기로 */
export const halftone = (color: string, size = 6, dot = 1.1) =>
  `radial-gradient(${color} ${dot}px, transparent ${dot + 0.45}px) 0 0 / ${size}px ${size}px`;

/** 바닥 타원(레퍼런스 1번: 오린 판화 아래 초록 타원) — 옅은 색 + 아래쪽이 짙은 망점 */
export const Ground: React.FC<{cx: number; cy: number; w: number; h: number; theme: Theme; p: number}> = ({cx, cy, w, h,
  theme, p}) => {
  const c = pressColors(theme);
  return (
    <div style={{position: 'absolute', left: cx - w / 2, top: cy - h / 2, width: w, height: h, borderRadius: '50%',
      background: `${halftone(mix(c.deep, '#000000', 0.1), 7, 1.25)}, linear-gradient(180deg, ${c.mid} 0%, ${mix(c.mid, c.deep, 0.35)} 100%)`,
      backgroundBlendMode: 'multiply', opacity: 0.92 * Math.min(1, p * 1.4), scale: `${interpolate(p, [0, 1], [0.55, 1])} ${interpolate(p, [0, 1], [0.3, 1])}`}} />
  );
};

/** 오려 낸 사진·판화: 흑백 + 대비 + 망점(이미지 알파 안에만) + 오른쪽 아래 그림자. cutout 이 아니면 종이 테두리 프린트로 */
export const CutoutImage: React.FC<{src: string; w: number; h: number; cutout: boolean; mono?: boolean;
  theme: Theme; seed?: number}> = ({src, w, h, cutout, mono = true, theme, seed = 1}) => {
  const c = pressColors(theme);
  const file = staticFile(src);
  const filter = mono ? 'grayscale(1) contrast(1.18) brightness(1.03)' : 'saturate(0.8) contrast(1.06)';
  if (!cutout) {
    return (
      <div style={{width: w, height: h, padding: 14, boxSizing: 'border-box', background: c.paperLight, boxShadow: paperShadow(2),
        rotate: `${paperRotate(seed, 'photo')}deg`, position: 'relative'}}>
        <div style={{position: 'relative', width: '100%', height: '100%', overflow: 'hidden'}}>
          <Img src={file} style={{width: '100%', height: '100%', objectFit: 'cover', filter}} />
          {mono ? <div style={{position: 'absolute', inset: 0, background: halftone('rgba(36,33,30,0.28)', 5, 0.9),
            mixBlendMode: 'multiply'}} /> : null}
        </div>
      </div>
    );
  }
  const mask: React.CSSProperties = {WebkitMaskImage: `url(${file})`, maskImage: `url(${file})`,
    WebkitMaskSize: 'contain', maskSize: 'contain', WebkitMaskRepeat: 'no-repeat', maskRepeat: 'no-repeat',
    WebkitMaskPosition: 'center', maskPosition: 'center'};
  return (
    <div style={{position: 'relative', width: w, height: h, filter: paperDropShadow(2)}}>
      <Img src={file} style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', filter}} />
      {mono ? <div style={{position: 'absolute', inset: 0, background: halftone('rgba(36,33,30,0.30)', 5, 0.95),
        mixBlendMode: 'multiply', ...mask}} /> : null}
    </div>
  );
};

/** 이탤릭 세리프 연도(레퍼런스 '1853') — 아래에서 마스크로 올라온다 */
export const YearNumeral: React.FC<{text: string; size: number; color: string; frame: number; delay?: number;
  print?: boolean; paper?: string}> = ({text, size, color, frame, delay = 2, print = true, paper}) => {
  const p = tween(frame, delay, 14, 'enterText');
  return (
    <div style={{overflow: 'hidden', paddingBottom: size * 0.08, paddingRight: size * 0.12}}>
      <div style={{translate: `0 ${interpolate(p, [0, 1], [105, 0])}%`, lineHeight: 1}}>
        {print ? <PrintText text={text} size={size} color={color} font={FONT.numeral} weight={900} italic seed={13}
          density={0.03} paper={paper} letterSpacing="-0.02em" lineHeight={1} />
          : <span style={{fontFamily: FONT.numeral, fontWeight: 900, fontStyle: 'italic', fontSize: size, color,
            letterSpacing: '-0.02em'}}>{text}</span>}
      </div>
    </div>
  );
};

/** 형광펜 한 줄(레퍼런스 2번 'CENTRAL PARK.'): 옅은 색 + 망점, 왼→오 쓸기, 살짝 기울게 */
export const Highlighter: React.FC<{x: number; y: number; w: number; h: number; theme: Theme; p: number;
  rotate?: number}> = ({x, y, w, h, theme, p, rotate = -0.5}) => {
  const c = pressColors(theme);
  return (
    <div style={{position: 'absolute', left: x, top: y, width: w, height: h, rotate: `${rotate}deg`,
      clipPath: `inset(-4% ${((1 - p) * 100).toFixed(2)}% -4% 0)`, mixBlendMode: 'multiply',
      background: `${halftone(mix(c.tint, c.deep, 0.25), 5, 0.9)}, ${c.tint}`}} />
  );
};

/** 이름표(레퍼런스 3번 '프레더릭 로 옴스테드'): 옅은 색 상자 + 짙은 색 굵은 글자, 왼→오로 열린다 */
export const NameChip: React.FC<{text: string; theme: Theme; frame: number; delay?: number; size?: number}> = ({text,
  theme, frame, delay = 18, size = 40}) => {
  const c = pressColors(theme);
  const p = tween(frame, delay, 12, 'enter');
  return (
    <div style={{display: 'inline-block', padding: `${size * 0.16}px ${size * 0.42}px ${size * 0.2}px`,
      background: `${halftone(mix(c.tint, c.deep, 0.2), 5, 0.8)}, ${c.tint}`, clipPath: `inset(0 ${((1 - p) * 100).toFixed(1)}% 0 0)`}}>
      <PrintText text={text} size={size} color={c.deep} font={FONT.heavy} seed={21} density={0.03} paper={c.tint}
        lineHeight={1.1} letterSpacing="0" />
    </div>
  );
};

/** 문서·스캔 한 장: 종이 테두리 없이 그림자 + 시드 각도, 붙이기로 내려앉는다 */
export const DocSheet: React.FC<{src: string; w: number; h: number; frame: number; delay?: number; seed?: number;
  fit?: 'cover' | 'contain'}> = ({src, w, h, frame, delay = 10, seed = 3, fit = 'cover'}) => {
  const rest = paperRotate(seed, 'note') * 0.6;
  const a = placeIn(Math.max(0, frame - delay), rest, 11);
  return (
    <div style={{width: w, height: h, opacity: frame >= delay ? a.opacity : 0, scale: `${a.scale}`,
      translate: `0 ${a.translateY}px`, rotate: `${a.rotate}deg`, boxShadow: paperShadow(a.elev)}}>
      <Img src={staticFile(src)} style={{width: '100%', height: '100%', objectFit: fit, display: 'block',
        filter: 'saturate(0.85) contrast(1.04)'}} />
    </div>
  );
};

/** 영상 위 명조 인용(레퍼런스 5·6번): 어둡게 그레이딩한 화면 + 가운데 고운바탕, 줄마다 올라온다 */
export const QuoteOverlay: React.FC<{text: string; frame: number; W: number; H: number; delay?: number}> = ({text, frame,
  W, H, delay = 8}) => {
  const lines = text.split('\n').filter(Boolean);
  const size = Math.round(Math.min(78 * (W / 1920), (W * 0.66) / Math.max(8, Math.max(...lines.map((l) => l.length)) * 0.95)));
  return (
    <>
      <div style={{position: 'absolute', inset: 0, background:
        'radial-gradient(90% 80% at 50% 45%, rgba(10,12,12,0.38) 0%, rgba(10,12,12,0.58) 100%)'}} />
      <div style={{position: 'absolute', left: W * 0.14, right: W * 0.14, top: 0, bottom: H * 0.12, display: 'flex',
        flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: size * 0.28}}>
        {lines.map((l, i) => {
          const p = tween(frame, delay + i * 5, 16, 'enterText');
          return (
            <div key={i} style={{fontFamily: FONT.serif, fontWeight: 400, fontSize: size, lineHeight: 1.32, color: '#F4F1E8',
              textAlign: 'center', letterSpacing: '-0.01em', opacity: p, translate: `0 ${interpolate(p, [0, 1], [18, 0])}px`,
              textShadow: '0 2px 18px rgba(0,0,0,0.45)'}}>{l}</div>
          );
        })}
      </div>
    </>
  );
};

/** 영상·사진 그레이딩(인용 장면): 정적 필터 — 채도 조금 낮추고 어둡게 */
export const GRADE_QUOTE = 'saturate(0.82) brightness(0.78) contrast(1.06)';

/** 큰 글자가 화면 안에서 아주 느리게 미끄러지는 시차(배경 글자 < 사진) */
export const parallax = (frame: number, dur: number, amount: number) =>
  interpolate(frame, [0, Math.max(1, dur)], [0, amount], {...clamp, easing: EASE.move});
