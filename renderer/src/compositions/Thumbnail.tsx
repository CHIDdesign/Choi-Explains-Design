import React, {useMemo} from 'react';
import {AbsoluteFill, Img, staticFile} from 'remotion';
import {ensureFonts, useFontGuard} from '../design/fonts';
import {FONT, makeTheme} from '../design/tokens';
import {fitBlock} from '../lib/fit';
import type {ThumbnailProps} from '../lib/types';

ensureFonts();

const Highlighted: React.FC<{line: string; highlight: string; color: string}> = ({line, highlight, color}) => {
  if (!highlight || !line.includes(highlight)) return <>{line}</>;
  const [a, ...rest] = line.split(highlight);
  return (
    <>
      {a}
      <span style={{color}}>{highlight}</span>
      {rest.join(highlight)}
    </>
  );
};

/** 썸네일 3종 — signal(리포트 표지색) / ink(어두운 사진 + 흰 글자) / photo(사진 + 글자 박스) */
export const Thumbnail: React.FC<ThumbnailProps> = (props) => {
  useFontGuard();
  const {width: W, height: H, brand, image, text, highlight, variant, faceX} = props;
  const theme = useMemo(() => makeTheme(brand), [brand]);
  const raw = text.replace(/\\n/g, '\n');
  const lines = raw.split('\n').filter(Boolean);
  const joined = lines.join(' ');

  if (variant === 'signal') {
    const panelW = W * 0.56;
    const fit = lines.length > 1
      ? {size: Math.min(...lines.map((l) => fitBlock(l, panelW - 90, H, 170, 60, 1, 1, -0.05).size)), lines}
      : fitBlock(joined, panelW - 90, H * 0.8, 170, 60, 1.0, 3, -0.05);
    return (
      <AbsoluteFill style={{background: theme.accent}}>
        {image ? (
          <Img src={staticFile(image)} style={{position: 'absolute', right: 0, top: 0, width: W - panelW + 40, height: H,
            objectFit: 'cover', objectPosition: `${Math.round(faceX * 100)}% 40%`}} />
        ) : null}
        <div style={{position: 'absolute', left: 0, top: 0, width: panelW, height: H, background: theme.accent,
          clipPath: 'polygon(0 0, 100% 0, 92% 100%, 0 100%)'}} />
        <div style={{position: 'absolute', left: 48, top: 30, fontFamily: FONT.sans, fontSize: 20, fontWeight: 600,
          color: theme.accentDeep}}>{brand.name}</div>
        <div style={{position: 'absolute', left: 44, top: 0, bottom: 0, width: panelW - 70, display: 'flex',
          flexDirection: 'column', justifyContent: 'center'}}>
          {fit.lines.map((l, i) => (
            <div key={i} style={{fontFamily: FONT.display, fontWeight: 900, fontSize: fit.size, lineHeight: 1.02,
              letterSpacing: '-0.05em', color: '#111', whiteSpace: 'nowrap'}}>
              <Highlighted line={l} highlight={highlight} color="#fff" />
            </div>
          ))}
        </div>
      </AbsoluteFill>
    );
  }

  if (variant === 'ink') {
    const fit = lines.length > 1
      ? {size: Math.min(...lines.map((l) => fitBlock(l, W * 0.56, H, 160, 60, 1, 1, -0.05).size)), lines}
      : fitBlock(joined, W * 0.56, H * 0.8, 160, 60, 1.02, 3, -0.05);
    return (
      <AbsoluteFill style={{background: theme.ink}}>
        {image ? (
          <Img src={staticFile(image)} style={{position: 'absolute', inset: 0, width: '100%', height: '100%',
            objectFit: 'cover', objectPosition: `${Math.round(faceX * 100)}% 40%`, filter: 'contrast(1.05) saturate(0.9)'}} />
        ) : null}
        <AbsoluteFill style={{background: faceX > 0.5
          ? 'linear-gradient(90deg, rgba(10,10,10,0.92) 0%, rgba(10,10,10,0.75) 45%, rgba(10,10,10,0) 75%)'
          : 'linear-gradient(270deg, rgba(10,10,10,0.92) 0%, rgba(10,10,10,0.75) 45%, rgba(10,10,10,0) 75%)'}} />
        <div style={{position: 'absolute', [faceX > 0.5 ? 'left' : 'right']: 56, top: 0, bottom: 0, width: W * 0.58,
          display: 'flex', flexDirection: 'column', justifyContent: 'center',
          alignItems: faceX > 0.5 ? 'flex-start' : 'flex-end'}}>
          <div style={{width: 64, height: 10, background: theme.accent, marginBottom: 22}} />
          {fit.lines.map((l, i) => (
            <div key={i} style={{fontFamily: FONT.display, fontWeight: 900, fontSize: fit.size, lineHeight: 1.04,
              letterSpacing: '-0.05em', color: '#fff', whiteSpace: 'nowrap',
              textAlign: faceX > 0.5 ? 'left' : 'right'}}>
              <Highlighted line={l} highlight={highlight} color={theme.accentLight} />
            </div>
          ))}
        </div>
      </AbsoluteFill>
    );
  }

  // photo
  const fit = fitBlock(joined, W * 0.8, H * 0.4, 120, 50, 1.1, 2, -0.04);
  return (
    <AbsoluteFill style={{background: '#000'}}>
      {image ? (
        <Img src={staticFile(image)} style={{position: 'absolute', inset: 0, width: '100%', height: '100%',
          objectFit: 'cover', objectPosition: `${Math.round(faceX * 100)}% 35%`}} />
      ) : null}
      <div style={{position: 'absolute', left: 40, bottom: 40, display: 'flex', flexDirection: 'column',
        alignItems: 'flex-start', gap: 8}}>
        {fit.lines.map((l, i) => (
          <div key={i} style={{background: i === fit.lines.length - 1 ? theme.accent : '#111', padding: '4px 18px 10px',
            fontFamily: FONT.display, fontWeight: 900, fontSize: fit.size, lineHeight: 1.08, letterSpacing: '-0.04em',
            color: '#fff', whiteSpace: 'nowrap'}}>{l}</div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
