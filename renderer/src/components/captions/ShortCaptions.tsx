import React from 'react';
import {interpolate} from 'remotion';
import {EASE, tween, tweenOut} from '../../design/motion';
import {FONT} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {lastIndexAtOrBefore} from '../../lib/time';
import type {CaptionCue, CaptionWord, ShortCaptionPreset} from '../../lib/types';
import {emOf, EmWord} from './Emphasis';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

type Props = {
  cues: CaptionCue[];
  t: number;
  fps: number;
  theme: Theme;
  preset: ShortCaptionPreset;
  y: number;
  width: number;
};

/**
 * 숏폼 자막 프리셋 (세이프존 x 65–940)
 *  kinetic : 말하는 순간 단어가 마스크 안에서 올라오며 쌓임(ease-out-expo 6f). 강조어는 형광 마커/숫자. 기본값.
 *  clean   : 청크 전체가 보이고, 말한 단어만 100% · 아직 안 한 단어 42% (카라오케 톤, 모션 최소)
 *  boxed   : 둥근 잉크 박스 + 지금 말하는 단어 뒤로 강조색 알약이 이동
 * 원칙: 청크당 강조 1개, 과한 흔들림/바운스 금지, 퇴장은 진입의 75%.
 */
export const ShortCaptions: React.FC<Props> = ({cues, t, fps, theme, preset, y, width}) => {
  const i = lastIndexAtOrBefore(cues, t, (c) => c.start);
  if (i < 0) return null;
  const cue = cues[i];
  if (t >= cue.end) return null;
  const words: CaptionWord[] = cue.lines.flat();
  const text = words.map((w) => w.text).join(' ');
  const size = text.length > 12 ? 68 : 78;
  const remain = (cue.end - t) * fps;
  const out = tweenOut(-remain, 0, 4, 'inCubic');
  const left = 65;
  const w = width - 65 - 140;
  const baseStyle: React.CSSProperties = {fontFamily: FONT.sans, fontWeight: 800, fontSize: size, lineHeight: 1.16,
    letterSpacing: '-0.025em', whiteSpace: 'nowrap'};

  if (preset === 'bar') {
    // 셜록현준 숏폼 자막: 창 안 하단, 불투명 검정 박스 한 줄, 흰 SemiBold 약 48px, 강조어 노랑(#FFE14D)
    const pIn = tween((t - cue.start) * fps, 0, 3, 'outQuint');
    return (
      <div style={{position: 'absolute', left: 0, width, top: y, display: 'flex', justifyContent: 'center',
        opacity: Math.min(pIn, out)}}>
        <div style={{background: 'rgba(0,0,0,0.92)', padding: '8px 18px 10px', borderRadius: 4,
          fontFamily: FONT.sans, fontWeight: 600, fontSize: text.length > 16 ? 44 : 50, lineHeight: 1.2,
          letterSpacing: '-0.015em', whiteSpace: 'nowrap', color: '#fff'}}>
          {words.map((wd, k) => (
            <React.Fragment key={k}>
              {k > 0 ? ' ' : ''}
              <span style={{color: emOf(wd) ? '#FFE14D' : '#fff'}}>{wd.text}</span>
            </React.Fragment>
          ))}
        </div>
      </div>
    );
  }

  if (preset === 'clean') {
    return (
      <div style={{position: 'absolute', left, width: w, top: y, display: 'flex', justifyContent: 'center',
        flexWrap: 'wrap', gap: `0 ${Math.round(size * 0.26)}px`, opacity: out}}>
        {words.map((wd, k) => {
          const on = interpolate((t - wd.start) * fps, [-1, 2], [0.42, 1], clamp);
          return (
            <span key={k} style={{...baseStyle, fontWeight: 700, color: '#fff', opacity: on,
              textShadow: '0 2px 4px rgba(0,0,0,0.35), 0 6px 26px rgba(0,0,0,0.5)'}}>
              <EmWord word={wd} t={t} fps={fps} theme={theme} baseColor="#fff" />
            </span>
          );
        })}
      </div>
    );
  }

  if (preset === 'boxed') {
    const pIn = tween((t - cue.start) * fps, 0, 6, 'outQuint');
    const activeIdx = words.reduce((acc, wd, k) => (t >= wd.start - 0.03 ? k : acc), 0);
    return (
      <div style={{position: 'absolute', left, width: w, top: y, display: 'flex', justifyContent: 'center',
        opacity: Math.min(pIn, out)}}>
        <div style={{display: 'flex', gap: `0 ${Math.round(size * 0.12)}px`, padding: '14px 26px 18px', borderRadius: 18,
          background: 'rgba(14,14,14,0.88)', scale: `${interpolate(pIn, [0, 1], [0.96, 1])}`,
          boxShadow: '0 12px 36px rgba(0,0,0,0.35)'}}>
          {words.map((wd, k) => {
            const active = k === activeIdx;
            const em = emOf(wd);
            return (
              <span key={k} style={{...baseStyle, fontSize: size * 0.92, position: 'relative', padding: '0 0.14em',
                color: active ? '#111' : em ? theme.captionAccent : '#fff'}}>
                {active ? <span style={{position: 'absolute', inset: '0.06em -0.02em 0.02em', borderRadius: 10,
                  background: theme.accentLight}} /> : null}
                <span style={{position: 'relative'}}>{wd.text}</span>
              </span>
            );
          })}
        </div>
      </div>
    );
  }

  // kinetic (기본): 말하는 순간 단어가 올라와 쌓인다
  return (
    <div style={{position: 'absolute', left, width: w, top: y, display: 'flex', justifyContent: 'center',
      flexWrap: 'wrap', gap: `0 ${Math.round(size * 0.22)}px`, opacity: out,
      translate: `0 ${interpolate(out, [0, 1], [-10, 0])}px`}}>
      {words.map((wd, k) => {
        const appear = Math.min(wd.start, cue.start + k * 0.07);
        const p = interpolate((t - appear) * fps, [0, 6], [0, 1], {...clamp, easing: EASE.outExpo});
        return (
          <span key={k} style={{display: 'inline-block', overflow: 'hidden', padding: '0.04em 0.04em 0.12em'}}>
            <span style={{...baseStyle, display: 'inline-block', color: '#fff', opacity: p,
              translate: `0 ${interpolate(p, [0, 1], [85, 0])}%`, paintOrder: 'stroke fill',
              WebkitTextStroke: '3px rgba(0,0,0,0.35)',
              textShadow: '0 3px 6px rgba(0,0,0,0.3), 0 8px 30px rgba(0,0,0,0.5)'}}>
              <EmWord word={wd} t={t} fps={fps} theme={theme} baseColor="#fff" />
            </span>
          </span>
        );
      })}
    </div>
  );
};
