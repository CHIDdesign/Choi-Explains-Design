import React from 'react';
import {interpolate} from 'remotion';
import {EASE, tween} from '../../design/motion';
import {FONT} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import type {CaptionWord, EmType} from '../../lib/types';

export const emOf = (w: CaptionWord): EmType | null => {
  if (!w.em) return null;
  if (w.em === true) return /\d/.test(w.text) ? 'number' : 'keyword';
  return w.em;
};

type Props = {
  word: CaptionWord;
  t: number; // 현재 시각(초, 편집 타임라인)
  fps: number;
  theme: Theme;
  baseColor: string;
  onDark?: boolean;
};

/**
 * 강조 단어 — 말하는 순간(word.start)에 맞춰 발동.
 *  keyword  : 강조색 + 밑줄이 왼→오 스윕(8f, ease-out-quint)
 *  term     : 형광 마커 블록이 스윕(7f), 글자는 잉크색으로 반전
 *  number   : Anton 숫자 1.12배 + 살짝 팝(ease-out-back)
 *  contrast : 속이 빈 외곽선 글자(대비어)
 */
// 한국어 조사·어미: 강조는 어간에만 주고 조사는 본문색으로 둔다(어포던스|라고, 85%|를)
const TAIL = /(이라고|라고|이란|란|에서는|에서|으로는|으로|로는|로|에게|까지|부터|처럼|보다|이에요|예요|입니다|이다|이죠|죠|이며|이고|하고|과|와|은|는|이|가|을|를|의|에|도|만|요)$/;

export const splitTail = (text: string): [string, string] => {
  const punct = text.match(/[.,!?…]+$/)?.[0] ?? '';
  const body = punct ? text.slice(0, -punct.length) : text;
  const m = body.match(TAIL);
  if (m && body.length - m[0].length >= 2) {
    return [body.slice(0, body.length - m[0].length), m[0] + punct];
  }
  return [body, punct];
};

export const EmWord: React.FC<Props> = ({word, t, fps, theme, baseColor, onDark = true}) => {
  const type = emOf(word);
  if (!type) return <span style={{color: baseColor}}>{word.text}</span>;
  const [stem, tail] = splitTail(word.text);
  const inner = <EmStem word={{...word, text: stem}} type={type} t={t} fps={fps} theme={theme} baseColor={baseColor}
    onDark={onDark} />;
  return tail ? <>{inner}<span style={{color: baseColor}}>{tail}</span></> : inner;
};

const EmStem: React.FC<Props & {type: EmType}> = ({word, type, t, fps, theme, baseColor, onDark = true}) => {
  const f = (t - word.start) * fps; // 단어 시작 기준 프레임
  const accent = onDark ? theme.accentLight : theme.accent;
  if (type === 'keyword') {
    const p = tween(f, -2, 8, 'outQuint');
    return (
      <span style={{position: 'relative', display: 'inline-block'}}>
        <span style={{color: p > 0 ? accent : baseColor}}>{word.text}</span>
        <span style={{position: 'absolute', left: '-0.02em', right: '-0.02em', bottom: '-0.04em', height: '0.075em',
          background: accent, transformOrigin: 'left center', scale: `${p} 1`, borderRadius: 2}} />
      </span>
    );
  }
  if (type === 'term') {
    const p = tween(f, -2, 7, 'outQuint');
    return (
      <span style={{position: 'relative', display: 'inline-block', padding: '0 0.08em'}}>
        <span style={{position: 'absolute', left: '-0.02em', right: '-0.02em', top: '0.1em', bottom: '0.02em',
          background: accent, transformOrigin: 'left center', scale: `${p} 1`, borderRadius: 3}} />
        <span style={{position: 'relative', color: p > 0.55 ? '#111111' : baseColor,
          textShadow: p > 0.55 ? 'none' : undefined}}>{word.text}</span>
      </span>
    );
  }
  if (type === 'number') {
    const p = interpolate(f, [-2, 8], [0.86, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
      easing: EASE.outBack});
    return (
      <span style={{display: 'inline-block', fontFamily: FONT.latin, fontWeight: 400, fontSize: '1.12em',
        letterSpacing: '0.005em', color: f >= -2 ? accent : baseColor, scale: `${p}`, lineHeight: 1}}>
        {word.text}
      </span>
    );
  }
  // contrast
  return (
    <span style={{color: 'transparent', WebkitTextStroke: `1.4px ${baseColor}`, textShadow: 'none'}}>{word.text}</span>
  );
};
