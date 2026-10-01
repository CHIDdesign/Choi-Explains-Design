import React from 'react';
import {interpolate} from 'remotion';
import {tween, tweenOut} from '../../design/motion';
import {FONT, mix} from '../../design/tokens';
import {fitSize} from '../../lib/fit';
import type {CaptionCue, CaptionWord} from '../../lib/types';
import {emOf} from './Emphasis';

/**
 * 두 층 강조 자막 — 참고 채널(Nick Saraev 숏폼) 실측을 한국어로 옮김:
 *  · 윗줄(앞말): 기울인 명조(Noto Serif KR, 기울임은 브라우저 합성), 흰색 + 부드러운 번짐 그림자
 *  · 아랫줄(핵심어): 아주 굵은 고딕(숫자면 Anton), 밝은 크림 → 따뜻한 주황 그라데이션
 *  · 핵심어는 그 단어가 들리는 순간 4프레임에 걸쳐 흐림 12px → 0, 10px 떠오르며 등장하고, 윗줄은 살짝 올라가며 0.9 배로
 *  · 상자·외곽선·이모지 없음(그림자 번짐만). 끝나면 4프레임 페이드
 * 평범한 자막은 이 위계를 쓰지 않는다 — 몇 초에 한 번, 핵심어가 있는 한 마디에만(과하면 강조가 사라진다).
 */
export type StackParts = {lead: string; key: string; keyStart: number; number: boolean};

/** 큐 → (앞말, 핵심어부터 끝까지, 핵심어가 시작되는 시각, 숫자인가). 앞말이 없으면 prevText 를 앞말로 쓸 수 있다. */
export const stackParts = (cue: CaptionCue, prevText = ''): StackParts => {
  const words: CaptionWord[] = cue.lines.flat();
  let k = words.findIndex((w) => !!emOf(w));
  if (k < 0) k = words.length - 1;
  const lead = words.slice(0, k).map((w) => w.text).join(' ') || prevText;
  const key = words.slice(k).map((w) => w.text).join(' ').replace(/[.,!?…]+$/, '');
  return {lead, key, keyStart: k > 0 ? words[k].start : cue.start, number: emOf(words[k]) === 'number'};
};

export const warmOf = (accent: string) => mix(accent, '#FFC48A', 0.55);

export const StackCaption: React.FC<{
  parts: StackParts;
  local: number; // 큐 시작 기준 프레임
  remain: number; // 큐 끝까지 남은 프레임
  fps: number;
  cueStart: number;
  accent: string;
  x: number;
  width: number;
  bottom: number; // 아랫줄 바닥 위치(px, 화면 아래 기준)
  size?: number; // 핵심어 최대 크기
  onLight?: boolean; // 밝은 배경 위(숏폼 첫 장면): 짙은 글씨 + 강조색 핵심어
}> = ({parts, local, remain, fps, cueStart, accent, x, width, bottom, size = 108, onLight = false}) => {
  const kf = Math.max(0, (parts.keyStart - cueStart) * fps - 1); // 단어보다 1프레임 먼저(실측)
  const pk = tween(local, kf, 4, 'outCubic');
  const out = tweenOut(-remain, 0, 4);
  const keySize = Math.min(size, fitSize(parts.key, width * 0.86, size, 48, -0.03));
  const leadSize = Math.min(keySize * 0.56, fitSize(parts.lead, width * 0.86, keySize * 0.56, 28, -0.01));
  const lift = tween(local, kf, 6, 'outCubic');
  const warm = warmOf(accent);
  const glow = onLight ? '' : 'drop-shadow(0 2px 3px rgba(0,0,0,0.35)) drop-shadow(0 0 14px rgba(0,0,0,0.5))';
  return (
    <div style={{position: 'absolute', left: x, width, bottom, display: 'flex', flexDirection: 'column',
      alignItems: 'center', opacity: out, pointerEvents: 'none'}}>
      {parts.lead ? (
        <div style={{fontFamily: FONT.serif, fontStyle: 'italic', fontWeight: 700, fontSize: leadSize, lineHeight: 1.1,
          letterSpacing: '-0.01em', color: onLight ? '#3A3A40' : '#FFFFFF', whiteSpace: 'nowrap',
          marginBottom: -keySize * 0.12, textShadow: onLight ? undefined : '0 2px 3px rgba(0,0,0,0.35), 0 0 16px rgba(0,0,0,0.55)',
          translate: `0 ${interpolate(lift, [0, 1], [keySize * 0.25, -keySize * 0.06])}px`,
          scale: `${interpolate(lift, [0, 1], [1, 0.9])}`, zIndex: 1}}>
          {parts.lead}
        </div>
      ) : null}
      <div style={{opacity: pk, translate: `0 ${interpolate(pk, [0, 1], [10, 0])}px`,
        filter: `blur(${interpolate(pk, [0, 1], [12, 0])}px) ${glow}`}}>
        <span style={{fontFamily: parts.number ? FONT.latin : FONT.heavy, fontWeight: 400,
          fontSize: parts.number ? keySize * 1.12 : keySize, lineHeight: 1.1, letterSpacing: parts.number ? '0' : '-0.01em',
          whiteSpace: 'nowrap', color: onLight ? accent : 'transparent',
          backgroundImage: onLight ? undefined : `linear-gradient(180deg, #FFF6EA 12%, ${warm} 92%)`,
          WebkitBackgroundClip: onLight ? undefined : 'text', backgroundClip: onLight ? undefined : 'text'}}>
          {parts.key}
        </span>
      </div>
    </div>
  );
};
