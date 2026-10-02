import React from 'react';
import {interpolate} from 'remotion';
import {LONG, tween, tweenOut} from '../../design/motion';
import type {Theme} from '../../design/tokens';
import type {EvidenceAsset, GraphicData} from '../../lib/types';
import {CornerCredit} from '../longform/Note';
import {CutoutImage, DocSheet, Ground, NameChip, PaperStage, PrintText, YearNumeral, parallax, pressColors} from './Press';

/**
 * 콜라주 장면(디자인 v3, 운영자 레퍼런스 1·3·4번) — 크림 종이 위:
 *   이탤릭 세리프 연도(위) · 인쇄 얼룩 큰 글자(가운데, 사진 뒤) · 오려 낸 망점 사진 + 바닥 타원(또는 종이 테두리 프린트) ·
 *   옆에 겹친 문서 한 장 · 이름표 · 우하단 출처.
 * 안무: 연도 마스크(2f) → 큰 글자 떠오름(4f) → 바닥 타원 펴짐(6f) → 사진 붙이기(8f) → 문서 붙이기(14f) → 이름표(18f).
 * 전체가 아주 느리게 다가오고(3.5%) 큰 글자는 반대로 미끄러진다(시차). 아래 170px 자막 자리는 비운다.
 */
export const YEAR_RE = /(1[5-9]\d\d|20[0-4]\d)/;

export const CollageScene: React.FC<{id: string; data: GraphicData; frame: number; dur: number; theme: Theme;
  W: number; H: number}> = ({id, data, frame, dur, theme, W, H}) => {
  const c = pressColors(theme);
  const k = W / 1920;
  const assets: EvidenceAsset[] = data.assets ?? [];
  const main = assets[0];
  const second = assets[1];
  const year = data.year || ((data.caption || '').match(YEAR_RE) || [])[1] || '';
  const display = (data.display || '').trim();
  const out = tweenOut(frame, dur, LONG.out);
  const push = interpolate(frame, [0, Math.max(1, dur)], [1, 1.035], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const isCut = !!main?.cut;
  // 구도: 오린 사진 + 큰 글자 = 가운데(사진이 글자 앞, 좁게 — 레퍼런스 3번) · 프린트 + 큰 글자 = 글자 왼쪽, 사진 오른쪽(살짝 겹침)
  //       · 큰 글자 없음 = 가운데 사진
  const side = !!display && !!main && !isCut;
  const boxH = H * (display ? 0.6 : 0.64);
  const ar = main && main.w && main.h ? main.w / main.h : 1.2;
  const boxW = Math.min(W * (side ? 0.36 : display ? 0.22 : second ? 0.4 : 0.46), boxH * ar);
  const mainH = Math.min(boxH, boxW / ar);
  const bottom = H * 0.8;
  const cx = side ? W * 0.68 : second ? W * 0.43 : W * 0.5;
  const pGround = tween(frame, 6, 14, 'enterLarge');
  const pDisp = tween(frame, 4, 16, 'enterLarge');
  const dispW = side ? W * 0.56 : W * 0.86;
  const dispSize = display ? Math.min(250 * k, dispW / Math.max(2, display.length * 1.02)) : 0;
  const dispTop = side ? H * 0.5 - dispSize * 0.5 : H * 0.52 - dispSize * 0.55;
  const textAlign = side ? 'flex-start' : 'center';
  const textLeft = side ? W * 0.07 : 0;
  return (
    <div style={{position: 'absolute', inset: 0, opacity: out, overflow: 'hidden'}}>
      <PaperStage theme={theme} frame={frame} />
      <div style={{position: 'absolute', inset: 0, scale: `${push}`, transformOrigin: '50% 58%'}}>
        {year ? (
          <div style={{position: 'absolute', left: textLeft, right: 0, top: side ? dispTop - 170 * k : H * (display ? 0.075 : 0.1),
            display: 'flex', justifyContent: textAlign, translate: `${parallax(frame, dur, -14 * k)}px 0`}}>
            <YearNumeral text={year} size={(side ? 130 : display ? 150 : main ? 260 : 300) * k} color={c.deep} frame={frame} paper={c.paper} />
          </div>
        ) : null}
        {display ? (
          <div style={{position: 'absolute', left: textLeft, right: 0, top: dispTop, display: 'flex',
            justifyContent: textAlign, opacity: Math.min(1, pDisp * 1.3),
            translate: `${parallax(frame, dur, 18 * k)}px ${interpolate(pDisp, [0, 1], [26 * k, 0])}px`}}>
            <PrintText text={display} size={dispSize} color={c.deep} seed={hashOf(id)} paper={c.paper} letterSpacing="0.01em" />
          </div>
        ) : null}
        {second ? (
          <div style={{position: 'absolute', left: W * 0.6, top: bottom - Math.min(H * 0.5, (W * 0.24) / Math.max(0.4,
            (second.w || 3) / (second.h || 4))) - H * 0.02}}>
            <DocSheet src={second.src} w={W * 0.24} h={Math.min(H * 0.5, (W * 0.24) / Math.max(0.4, (second.w || 3) / (second.h || 4)))}
              frame={frame} delay={14} seed={hashOf(id) + 3} fit="contain" />
          </div>
        ) : null}
        {main && isCut ? <Ground cx={cx} cy={bottom - H * 0.012} w={boxW * 1.32} h={H * 0.13} theme={theme} p={pGround} /> : null}
        {main ? (
          <PlacedMedia frame={frame} delay={8} x={cx - boxW / 2} y={bottom - mainH} w={boxW} h={mainH}>
            <CutoutImage src={isCut ? main.cut! : main.src} w={boxW} h={mainH} cutout={isCut}
              mono={main.kind !== 'document' && main.kind !== 'logo'} theme={theme} seed={hashOf(id)} />
          </PlacedMedia>
        ) : null}
        {data.title ? (
          <div style={{position: 'absolute', left: cx + boxW * 0.08, top: bottom - 30 * k}}>
            <NameChip text={data.title} theme={theme} frame={frame} delay={18} size={40 * k} />
          </div>
        ) : null}
      </div>
      <CornerCredit text={data.credit || ''} onPaper opacity={tween(frame, 12, 12)} />
    </div>
  );
};

const PlacedMedia: React.FC<{frame: number; delay: number; x: number; y: number; w: number; h: number;
  children: React.ReactNode}> = ({frame, delay, x, y, w, h, children}) => {
  const p = tween(frame, delay, 12, 'enter');
  return (
    <div style={{position: 'absolute', left: x, top: y, width: w, height: h, opacity: frame >= delay ? Math.min(1, p * 2) : 0,
      translate: `0 ${interpolate(p, [0, 1], [-22, 0])}px`, scale: `${interpolate(p, [0, 1], [1.03, 1])}`,
      transformOrigin: '50% 100%'}}>
      {children}
    </div>
  );
};

const hashOf = (s: string) => {
  let h = 7;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 9973;
  return h;
};
