import React from 'react';
import {interpolate} from 'remotion';
import {DUR, EASE, exitFrames, tween, tweenOut} from '../../design/motion';
import {FONT} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {lastIndexAtOrBefore} from '../../lib/time';
import type {CaptionCue, LongCaptionPreset} from '../../lib/types';
import {EmWord, splitTail} from './Emphasis';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

type Props = {
  cues: CaptionCue[];
  t: number;
  fps: number;
  theme: Theme;
  preset: LongCaptionPreset;
  centerX?: number;
  frameW?: number;
  bottom?: number;
  plain?: boolean; // 화면에 글자 그래픽이 있을 때: 강조 없이
};

/**
 * 롱폼 자막 프리셋
 *  editorial   : 배경 없이 흰 글자 + 부드러운 그림자, 줄 단위 마스크 슬라이드업(짧게). 기본값.
 *  documentary : 왼쪽 정렬 + 강조색 세로 바. 넷플릭스 다큐 톤.
 *  glass       : 반투명 유리 알약(backdrop blur). 모던·애플 톤.
 *  boxed       : 줄마다 잉크 박스, 왼쪽 강조색 엣지. 뉴스·리포트 톤.
 *  paper       : 사용자 템플릿 — 흰 종이 박스 + 검은 글자, 핵심어 어간만 굵게. 한두 마디씩 빠르게 바뀐다.
 * 공통: 강조어 1개(밑줄 스윕/형광 마커/숫자), 이어지는 큐는 애니메이션 없이 교체(과잉 모션 방지).
 */
export const LongCaptions: React.FC<Props> = ({cues, t, fps, theme, preset, centerX, frameW = 1920, bottom = 70,
  plain = false}) => {
  const i = lastIndexAtOrBefore(cues, t, (c) => c.start);
  if (i < 0) return null;
  const cue = cues[i];
  if (t >= cue.end) return null;
  const prev = i > 0 ? cues[i - 1] : null;
  const next = i + 1 < cues.length ? cues[i + 1] : null;
  const joinPrev = !!prev && cue.start - prev.end < 0.08;
  const joinNext = !!next && next.start - cue.end < 0.08;
  const local = (t - cue.start) * fps;
  const remain = (cue.end - t) * fps;
  const enterDur = joinPrev ? 3 : DUR.fast;
  const pIn = tween(local, 0, enterDur, 'outExpo');
  const pOut = joinNext ? 1 : tweenOut(-remain, 0, exitFrames(DUR.fast));
  const cx = centerX ?? frameW / 2;

  const words = (line: CaptionCue['lines'][number], base = '#ffffff') =>
    line.map((w, wi) => (
      <React.Fragment key={wi}>
        {wi > 0 ? ' ' : ''}
        <EmWord word={plain ? {...w, em: undefined} : w} t={t} fps={fps} theme={theme} baseColor={base} />
      </React.Fragment>
    ));

  if (preset === 'paper') {
    return <PaperCaption cue={cue} local={local} remain={remain} joinPrev={joinPrev} joinNext={joinNext}
      left={cx - frameW / 2} width={frameW} bottom={bottom} plain={plain} />;
  }

  if (cue.style === 'impact' && !plain) {
    // 강조 자막: 크게, 가운데, 굵게 — 펀치인·효과음과 같은 순간에 '툭' 튀어나온다
    const pop = tween(local, 0, 7, 'outBack');
    return (
      <div style={{position: 'absolute', left: cx - frameW / 2, width: frameW, bottom: bottom + 36, display: 'flex',
        flexDirection: 'column', alignItems: 'center', opacity: Math.min(tween(local, 0, 3, 'outQuint'), pOut),
        scale: `${interpolate(pop, [0, 1], [1.16, 1])}`, transformOrigin: '50% 100%'}}>
        {cue.lines.map((line, li) => (
          <div key={li} style={{fontFamily: FONT.sans, fontWeight: 800, fontSize: 76, lineHeight: 1.2,
            letterSpacing: '-0.025em', color: '#fff', whiteSpace: 'nowrap',
            textShadow: '0 2px 3px rgba(0,0,0,0.6), 0 8px 30px rgba(0,0,0,0.55)'}}>
            {words(line)}
          </div>
        ))}
      </div>
    );
  }

  if (preset === 'documentary') {
    const barP = tween(local, 0, joinPrev ? 1 : DUR.normal, 'outQuint');
    return (
      <div style={{position: 'absolute', left: 120, bottom: bottom + 24, maxWidth: 1180, display: 'flex', gap: 20,
        opacity: Math.min(joinPrev ? 1 : pIn, pOut)}}>
        <div style={{width: 3, alignSelf: 'stretch', background: theme.accent, transformOrigin: 'top', scale: `1 ${barP}`}} />
        <div style={{display: 'flex', flexDirection: 'column', gap: 2}}>
          {cue.lines.map((line, li) => (
            <div key={li} style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: 40, lineHeight: 1.38,
              letterSpacing: '-0.008em', color: '#fff', whiteSpace: 'nowrap',
              textShadow: '0 1px 2px rgba(0,0,0,0.6), 0 3px 14px rgba(0,0,0,0.45)'}}>
              {words(line)}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (preset === 'glass') {
    const scale = interpolate(pIn, [0, 1], [0.985, 1]);
    return (
      <div style={{position: 'absolute', left: cx - frameW / 2, width: frameW, bottom, display: 'flex',
        justifyContent: 'center', opacity: Math.min(joinPrev ? 1 : pIn, pOut)}}>
        <div style={{padding: '12px 28px 14px', borderRadius: 18, background: 'rgba(18,18,18,0.36)',
          backdropFilter: 'blur(18px) saturate(140%)', WebkitBackdropFilter: 'blur(18px) saturate(140%)',
          border: '1px solid rgba(255,255,255,0.16)', boxShadow: '0 10px 34px rgba(0,0,0,0.22)',
          scale: `${joinPrev ? 1 : scale}`, display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
          {cue.lines.map((line, li) => (
            <div key={li} style={{fontFamily: FONT.sans, fontWeight: 600, fontSize: 42, lineHeight: 1.36,
              letterSpacing: '-0.012em', color: '#fff', whiteSpace: 'nowrap',
              opacity: joinPrev ? interpolate(local, [0, 3], [0.2, 1], clamp) : 1}}>
              {words(line)}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (preset === 'boxed') {
    return (
      <div style={{position: 'absolute', left: cx - frameW / 2, width: frameW, bottom, display: 'flex',
        flexDirection: 'column', alignItems: 'center', gap: 6, opacity: pOut}}>
        {cue.lines.map((line, li) => {
          const p = joinPrev ? 1 : tween(local, li * 2, DUR.fast, 'outQuint');
          return (
            <div key={li} style={{position: 'relative', padding: '4px 16px 6px', background: 'rgba(12,12,12,0.84)',
              borderLeft: li === 0 ? `4px solid ${theme.accent}` : '4px solid transparent',
              clipPath: `inset(0 ${(1 - p) * 100}% 0 0)`, fontFamily: FONT.sans, fontWeight: 600, fontSize: 42,
              lineHeight: 1.34, letterSpacing: '-0.01em', color: '#fff', whiteSpace: 'nowrap'}}>
              {words(line)}
            </div>
          );
        })}
      </div>
    );
  }

  // editorial (기본)
  return (
    <div style={{position: 'absolute', left: cx - frameW / 2, width: frameW, bottom, display: 'flex',
      flexDirection: 'column', alignItems: 'center', gap: 2, opacity: pOut,
      translate: `0 ${interpolate(pOut, [0, 1], [-8, 0])}px`}}>
      {cue.lines.map((line, li) => {
        const p = joinPrev ? interpolate(local, [0, 3], [0.35, 1], clamp)
          : interpolate(local, [li * 2, li * 2 + DUR.fast], [0, 1], {...clamp, easing: EASE.outExpo});
        return (
          <div key={li} style={{overflow: 'hidden', padding: '0 6px 0.14em'}}>
            <div style={{fontFamily: FONT.sans, fontWeight: 600, fontSize: 44, lineHeight: 1.34,
              letterSpacing: '-0.012em', color: '#fff', whiteSpace: 'nowrap',
              textShadow: '0 1px 2px rgba(0,0,0,0.55), 0 4px 18px rgba(0,0,0,0.42)',
              translate: joinPrev ? undefined : `0 ${interpolate(p, [0, 1], [42, 0])}%`, opacity: p}}>
              {words(line)}
            </div>
          </div>
        );
      })}
    </div>
  );
};

/** 자막 가독성용 하단 그라데이션 스크림(박스 없이도 읽히게) */
export const CaptionScrim: React.FC<{height?: number; strength?: number}> = ({height = 280, strength = 0.38}) => (
  <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height, pointerEvents: 'none',
    background: `linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,${strength * 0.55}) 55%, rgba(0,0,0,${strength}) 100%)`}} />
);

/** 흰 종이 박스 자막(사용자 템플릿). 짧은 청크가 빠르게 바뀌므로 움직임은 2프레임 페이드뿐. */
export const PaperCaption: React.FC<{cue: CaptionCue; local: number; remain: number; joinPrev: boolean;
  joinNext: boolean; left: number; width: number; bottom: number; plain?: boolean; size?: number}> = (
  {cue, local, remain, joinPrev, joinNext, left, width, bottom, plain = false, size = 46}) => {
  const op = Math.min(joinPrev ? 1 : interpolate(local, [0, 2], [0, 1], clamp),
    joinNext ? 1 : interpolate(remain, [0, 2], [0, 1], clamp));
  return (
    <div style={{position: 'absolute', left, width, bottom, display: 'flex', justifyContent: 'center', opacity: op}}>
      <div style={{background: '#fbfaf5', border: '2px solid #1a1a1a', padding: `${size * 0.12}px ${size * 0.46}px ${size * 0.17}px`,
        fontFamily: FONT.sans, fontWeight: 500, fontSize: size, lineHeight: 1.3, letterSpacing: '-0.01em',
        color: '#171717', whiteSpace: 'nowrap', boxShadow: '0 4px 16px rgba(0,0,0,0.28)'}}>
        {cue.lines.map((line, li) => (
          <div key={li}>
            {line.map((w, wi) => {
              const [stem, tail] = w.em && !plain ? splitTail(w.text) : [w.text, ''];
              return (
                <React.Fragment key={wi}>
                  {wi > 0 ? ' ' : ''}
                  {w.em && !plain ? <><span style={{fontWeight: 900}}>{stem}</span>{tail}</> : w.text}
                </React.Fragment>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
};
