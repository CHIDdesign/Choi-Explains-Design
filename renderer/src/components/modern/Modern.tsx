import React from 'react';
import {interpolate} from 'remotion';
import {EASE, overlayStyle, paperSettle} from '../../design/motion';
import {FONT, MAT, SLOT_TYPE, TEXT_SHADOW} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import type {MapFn} from '../../lib/crop';
import {balanceLines, estWidth, fitSize} from '../../lib/fit';
import {GrainLayer, TexBackdrop, texFill, useMaterials} from '../material/Texture';
import type {TexName} from '../material/Texture';
import {Attach} from '../material/Marks';
import {Sheet} from '../material/Sheet';
import {hashSeed} from '../paper/Paper';

/**
 * 디자인 v5.1 글자 슬롯(docs/디자인_v5_토크쇼.md) — 자리와 모양이 정해져 있고 영상마다 새로 짓지 않는다.
 * 얹히는 글자는 올라오거나 옆에서 밀려오며 페이드 + 블러(overlayStyle), 종이는 놓인다(paperSettle). 정착하면 멈춘다.
 */

/** 무대: 양피지(그 위 흰 메모가 도드라지는 톤) 또는 어두운 책상 + 입자(글자 아래) */
/** 같은 물건을 둔 채 바탕 종이만 바꾸는 하드 컷의 종이(LongForm) */
export const PaperGround = React.createContext<TexName | null>(null);

export const ModernStage: React.FC<{dark?: boolean; seed?: number}> = ({dark = false, seed = 1}) => {
  useMaterials();
  const ground = React.useContext(PaperGround);
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <TexBackdrop name={dark ? 'desk' : ground ?? 'parchment'} seed={dark ? 2 : seed} />
      <GrainLayer opacity={dark ? 0.1 : 0.06} />
    </div>
  );
};

const WORD_GAP = 3;

/** 큰 글자의 등장: 어절마다 올라오며 선명해진다(overlayStyle 9f, 3f 간격). 글자를 마스크로 자르면 등장 중에 받침이 잘려 다른 글자로 읽힌다. 나갈 때는 함께 */
export const WordRise: React.FC<{lines: string[]; frame: number; dur?: number}> = ({lines, frame, dur}) => {
  let n = -1;
  return (
    <>
      {lines.map((l, k) => (
        <div key={k} style={{whiteSpace: 'nowrap'}}>
          {l.split(' ').map((w, i) => {
            n += 1;
            const d = n * WORD_GAP;
            return <React.Fragment key={i}>{i ? ' ' : null}<span style={{display: 'inline-block', ...overlayStyle(frame - d, dur === undefined ? undefined : dur - d)}}>{w}</span></React.Fragment>;
          })}
        </div>
      ))}
    </>
  );
};

/** 세로 화면(숏폼)이면 얼굴·옷깃을 피한 고정 띠(y 1120~1300)에 놓는다 */
export const lowerSlot = (box: {w: number; h: number}) => (box.h > box.w ? 620 : 150);

/** 챕터 배지(좌상단): 화면 가장자리에서 접혀 나온 숲색 종이 탭, 끝은 찢겼다 */
export const ChapterBadge: React.FC<{title: string; frame: number; dur?: number}> = ({title, frame, dur}) => {
  const size = SLOT_TYPE.band + 4;
  const w = 84 + estWidth(title, size, -0.02) + 58;
  const h = 92;
  return (
    <div style={{position: 'absolute', left: 0, top: 50, ...overlayStyle(frame, dur, 'left')}}>
      <div style={{position: 'absolute', left: 0, top: h - 3, width: 0, height: 0, borderTop: '17px solid #0F2A21', borderLeft: '46px solid transparent'}} />
      <Sheet x={-12} w={w} h={h} tex="forest" seed={hashSeed(title)} rotate={-0.5} origin="0 50%" liftLevel={1.4} torn={{right: true}} amp={10} fibre={3}>
        <div style={{position: 'absolute', left: 0, top: 0, width: 62, height: h,
          background: 'linear-gradient(90deg, rgba(0,0,0,0.34) 0%, rgba(0,0,0,0.1) 78%, rgba(255,255,255,0.16) 90%, rgba(0,0,0,0.2) 100%)'}} />
        <div style={{position: 'absolute', left: 84, top: 0, height: h, display: 'flex', alignItems: 'center', whiteSpace: 'nowrap'}}>
          <span style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: size, lineHeight: 1, letterSpacing: '-0.02em', color: '#FFFFFF'}}>{title}</span>
        </div>
      </Sheet>
    </div>
  );
};

/** 오늘의 주제(우상단): 흰 메모 + 주황 테이프, 살짝 기울어 붙는다. 아래 변은 찢겼다 */
export const TopicMemo: React.FC<{title: string; frame: number; dur?: number; label?: string}> = ({title, frame, dur, label = '오늘의 주제'}) => {
  const size = 46;
  const lines = balanceLines(title, size, 560, 2, -0.02);
  const w = Math.max(360, Math.max(...lines.map((l) => estWidth(l, size, -0.02))) + 96);
  const h = 104 + lines.length * size * 1.26 + 26;
  const seed = hashSeed(title);
  const m = paperSettle(frame, 1.7);
  const st = overlayStyle(Math.max(frame, 20), dur);    // 등장은 종이가 놓이는 것으로, 퇴장만 페이드 + 블러
  return (
    <div style={{position: 'absolute', right: 66, top: 62, width: w, height: h, opacity: st.opacity, filter: st.filter}}>
      <Sheet w={w} h={h} tex="memo" seed={seed} m={m} torn={{bottom: true}} amp={12}>
        <div style={{position: 'absolute', left: 44, top: 32, fontFamily: FONT.pen, fontSize: 54, lineHeight: 1, color: MAT.forest, whiteSpace: 'nowrap'}}>{label}</div>
        <div style={{position: 'absolute', left: 44, top: 92, fontFamily: FONT.sans, fontWeight: 800, fontSize: size, lineHeight: 1.26, letterSpacing: '-0.02em', color: MAT.ink}}>
          {lines.map((l, i) => <div key={i} style={{whiteSpace: 'nowrap'}}>{l}</div>)}
        </div>
        <Attach w={w} seed={seed} always tw={176} th={46} />
      </Sheet>
    </div>
  );
};

/** 용어 정의(좌하단): 숲색 머리표(찢긴 끝) + 불투명한 차콜 본문(흐린 유리 상자는 앱 UI 다), 영문 원어만 기울임 */
export const DefinitionSlot: React.FC<{title: string; en?: string; body?: string; frame: number; dur?: number; box: {w: number; h: number}}> = ({title, en, body, frame, dur, box}) => {
  const size = SLOT_TYPE.definition;
  const bodySize = size * SLOT_TYPE.bandBody;
  const tall = box.h > box.w;
  const lines = balanceLines(body || '', bodySize, tall ? box.w - 200 : 468, tall ? 2 : 3, -0.015);      // 가로 화면: 자막 위에 검은 막대로 쌓이지 않게 폭 540 안에서 줄을 나눈다
  const headW = estWidth(title, size, -0.02) + (en ? estWidth(en, size * 0.74) * 0.86 + 34 : 0) + 104;
  const headH = Math.round(size * 1.92);
  const seed = hashSeed(title);
  return (
    <div style={{position: 'absolute', left: 64, bottom: tall ? lowerSlot(box) : 200, display: 'flex', flexDirection: 'column', alignItems: 'flex-start', ...overlayStyle(frame, dur, 'left')}}>
      <div style={{position: 'relative', width: headW, height: headH, zIndex: 1, marginBottom: -1}}>
        <Sheet w={headW} h={headH} tex="forest" seed={seed} rotate={-0.4} origin="0 100%" liftLevel={1.2} torn={{right: true}} amp={10} fibre={3}>
          <div style={{position: 'absolute', left: 36, top: 0, height: headH, display: 'flex', alignItems: 'center', gap: 16, whiteSpace: 'nowrap'}}>
            <span style={{fontFamily: FONT.sans, fontWeight: 800, fontSize: size, lineHeight: 1, letterSpacing: '-0.02em', color: '#FFFFFF'}}>{title}</span>
            {en ? <span style={{fontFamily: FONT.italic, fontStyle: 'italic', fontSize: size * 0.74, lineHeight: 1, color: MAT.mint}}>{en}</span> : null}
          </div>
        </Sheet>
      </div>
      {lines.length ? (
        <div style={{background: 'rgba(30,33,36,0.92)', padding: '22px 36px 26px', fontFamily: FONT.sans, fontWeight: 500, fontSize: bodySize, lineHeight: 1.42, letterSpacing: '-0.015em', color: '#FFFFFF'}}>
          {lines.map((l, i) => <div key={i} style={{whiteSpace: 'nowrap'}}>{l}</div>)}
        </div>
      ) : null}
    </div>
  );
};

/** 핵심어: 흰 고딕 800, 프레임 높이 약 8%, 판 없이 부드러운 그림자. 화자 위에서는 얼굴 아래(가슴 높이)에 놓는다. 어절마다 올라오며 선명해진다 */
export const CenterWord: React.FC<{text: string; sub?: string; W: number; H: number; frame: number; dur?: number; y?: number; color?: string;
  shadow?: boolean; scale?: number; veil?: boolean}> = ({text, sub, W, H, frame, dur, y = 0.66, color = '#FFFFFF', shadow = true, scale = 1, veil = true}) => {
  const size = fitSize(text, W * 0.86, Math.min(W, H) * 0.08 * scale, SLOT_TYPE.keywordMin, -0.02);
  const subSize = Math.max(SLOT_TYPE.keywordSubMin, size * SLOT_TYPE.keywordSub);
  const veilW = Math.max(estWidth(text, size, -0.02) * 1.4, sub ? estWidth(sub, subSize, -0.01) * 1.25 : 0) + 160;
  const veilH = size * 1.16 + (sub ? size * 0.2 + subSize * 1.3 : 0) + 160;     // 글자 높이 + 페더 80px 씩: 평평한 가운데가 보조 줄까지 덮고 얼굴에는 닿지 않는다
  const flat = Math.round(100 * (1 - 160 / veilH));
  return (
    <div style={{position: 'absolute', left: 0, width: W, top: H * y, translate: '0 -50%', textAlign: 'center'}}>
      <div style={{textShadow: shadow ? '0 1px 3px rgba(0,0,0,0.55), 0 3px 18px rgba(0,0,0,0.6)' : undefined, color}}>
        {shadow && veil ? <div style={{position: 'absolute', left: '50%', top: '50%', width: veilW, height: veilH, translate: '-50% -50%', opacity: overlayStyle(frame, dur).opacity,
          background: `radial-gradient(closest-side, rgba(0,0,0,0.4) ${flat}%, rgba(0,0,0,0.14) ${Math.round(flat + (100 - flat) * 0.6)}%, rgba(0,0,0,0))`}} /> : null}
        <div style={{position: 'relative', fontFamily: FONT.sans, fontWeight: 800, fontSize: size, lineHeight: 1.16, letterSpacing: '-0.02em'}}><WordRise lines={[text]} frame={frame} dur={dur} /></div>
        {sub ? <div style={{position: 'relative', marginTop: size * 0.2, fontFamily: FONT.sans, fontWeight: 500, fontSize: subSize, lineHeight: 1.3, letterSpacing: '-0.01em', whiteSpace: 'nowrap',
          ...overlayStyle(frame - text.split(' ').length * WORD_GAP, dur)}}>{sub}</div> : null}
      </div>
    </div>
  );
};

/** 인물·기관 슈퍼(좌하단): 왼쪽 세로선 + 이름 + 소속, 판 없이 그림자만 */
export const Super: React.FC<{name: string; sub?: string; theme: Theme; box: {w: number; h: number}; frame: number; dur?: number; on?: SuperOn}> = ({name, sub, theme, box, frame, dur, on}) => {
  const white = !on;                 // 그늘진 자료·화자 위: 흰 글자 + 그림자 · 밝은 자료 위: 잉크 글자, 얼룩덜룩하면 종이 라벨
  const ink = on === 'paper' ? MAT.ink : '#1A1916';
  return (
    <div style={{position: 'absolute', left: 64, bottom: lowerSlot(box), display: 'flex', alignItems: 'stretch', gap: 20, textShadow: white ? TEXT_SHADOW : undefined, maxWidth: box.w - 128,
      ...(on === 'paper' ? {...texFill('memo', hashSeed(name), 480, 140), padding: '12px 26px 14px 16px', boxShadow: '1px 2px 3px rgba(0,0,0,0.35), 3px 8px 16px rgba(0,0,0,0.18)'} : null),
      ...overlayStyle(frame, dur, 'left')}}>
      <div style={{width: 6, background: theme.accent, boxShadow: white ? '1px 2px 5px rgba(0,0,0,0.45)' : undefined}} />
      <div style={{padding: '2px 0'}}>
        <div style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: SLOT_TYPE.superName, lineHeight: 1.2, letterSpacing: '-0.02em', color: white ? '#FFFFFF' : ink, whiteSpace: 'nowrap'}}>{name}</div>
        {sub ? <div style={{marginTop: 4, fontFamily: FONT.sans, fontWeight: 500, fontSize: SLOT_TYPE.superSub, lineHeight: 1.3, color: white ? 'rgba(255,255,255,0.94)' : ink, whiteSpace: 'nowrap'}}>{sub}</div> : null}
      </div>
    </div>
  );
};

export type SuperOn = 'ink' | 'paper' | undefined;
const SUPER_LIGHT = 0.5;              // 이보다 밝으면 흰 글자가 그림자에 기대게 된다
const SUPER_BUSY = 0.3;               // 슈퍼 자리의 밝기 폭 — 이보다 얼룩덜룩하면 글자만 얹을 수 없다

/** 슈퍼가 놓일 자리의 밝기로 글자 모양을 고른다(data.safe.lum = 사진 분석의 휘도 격자, map = 크롭 반영). 격자가 없으면 지금처럼 흰 글자 */
export const superOn = (grid: number[][] | undefined, map: MapFn | null, box: {w: number; h: number}, name = '', sub = ''): SuperOn => {
  if (!grid?.length || !map || !name) return undefined;
  const right = superRight(name, sub) + 20;
  const [bottom, top] = [box.h - lowerSlot(box), box.h - lowerSlot(box) - (sub ? 96 : 58)];
  const vals: number[] = [];
  grid.forEach((row, r) => row.forEach((v, c) => {
    const [x, y] = map((c + 0.5) / row.length, (r + 0.5) / grid.length);
    if (x >= 56 && x <= right && y >= top - 8 && y <= bottom + 8) vals.push(v);
  }));
  if (!vals.length) return undefined;
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
  if (mean < SUPER_LIGHT) return undefined;
  return Math.max(...vals) - Math.min(...vals) > SUPER_BUSY || mean < 0.62 ? 'paper' : 'ink';
};

/** 슈퍼 글자의 오른쪽 끝(x) — 뒤에 밝은 종이를 깔 때 피하는 값 */
export const superRight = (name = '', sub = '') => (name ? 90 + Math.max(estWidth(name, SLOT_TYPE.superName, -0.02), estWidth(sub, SLOT_TYPE.superSub)) + 36 : 0);

/** 인용: 뒤의 자료·화자를 흐리고 어둡게 → 큰 따옴표 + 명조(여기와 제호에만) + 원전. 줄은 뜻이 끊기는 곳에서 나눈다 */
export const QuoteSlot: React.FC<{text: string; who?: string; W: number; H: number; frame: number; dur?: number; accent?: string}> = ({text, who, W, H, frame, dur, accent = MAT.orange}) => {
  const size = Math.round(Math.min(W, H) * SLOT_TYPE.quote);
  const lines = balanceLines(text, size, W * 0.68, 4, -0.01);
  const dim = interpolate(frame, [0, 10], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: EASE.enter});
  return (
    <div style={{position: 'absolute', inset: 0}}>
      <div style={{position: 'absolute', inset: 0, opacity: dur !== undefined && frame > dur - 7 ? Math.max(0, (dur - frame) / 7) : dim, backdropFilter: 'blur(22px) brightness(0.42) saturate(0.7)',
        WebkitBackdropFilter: 'blur(22px) brightness(0.42) saturate(0.7)'}} />
      <div style={{position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', paddingBottom: H * 0.06, ...overlayStyle(frame - 3, dur === undefined ? undefined : dur - 3)}}>
        <div style={{position: 'relative'}}>
          <div style={{position: 'absolute', left: -Math.min(W, H) * 0.056, top: -Math.min(W, H) * 0.098, fontFamily: FONT.quote, fontWeight: 700, fontSize: Math.min(W, H) * 0.13, lineHeight: 1, color: accent, textShadow: '0 4px 24px rgba(0,0,0,0.35)'}}>“</div>
          <div style={{fontFamily: FONT.quote, fontWeight: 700, fontSize: size, lineHeight: 1.5, letterSpacing: '-0.01em', color: '#FFFFFF', textShadow: '0 2px 20px rgba(0,0,0,0.4)'}}>
            {lines.map((l, i) => <div key={i} style={{whiteSpace: 'nowrap'}}>{l}</div>)}
          </div>
          {who ? (
            <div style={{marginTop: size * 0.62, display: 'flex', alignItems: 'center', gap: size * 0.32, fontFamily: FONT.sans, fontWeight: 500, fontSize: size * SLOT_TYPE.quoteWho, letterSpacing: '-0.01em', color: 'rgba(255,255,255,0.86)'}}>
              <span style={{width: size * 0.7, height: 2, background: 'rgba(255,255,255,0.55)'}} />{who}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
};

/** 조각 전환 중에는 LongForm 이 출처를 대신 쓴다 — 두 장이 함께 보일 때 어느 기관을 쓸지는 화면 점유율로 정한다 */
export const CreditOn = React.createContext(true);

/** 우하단 출처: 자료 위에 늘, 어디서나 같은 종이 칩(맨글자는 그림 톤에 따라 읽히다 말다 한다). 세로형은 자막 아래. inFrame = 액자 아래 여백에 잉크색으로.
 *  아주 작고 옅게(채널 주인 2026-11-11: "출처가 아주 작고 얕게나마") — 읽으려면 읽히되 그림을 가리지 않는다 */
export const CornerCredit: React.FC<{text: string; tall?: boolean; bottom?: number; inFrame?: boolean}> = ({text, tall = false, bottom = tall ? 260 : 40, inFrame = false}) => {
  const on = React.useContext(CreditOn);
  if (!text || !on) return null;
  const line = text.startsWith('출처') ? text : `출처: ${text}`;
  return (
    <div style={{position: 'absolute', right: inFrame ? 24 : 32, bottom: inFrame ? bottom : Math.round(bottom * 0.6), fontFamily: FONT.sans, fontWeight: 500, fontSize: tall ? 20 : SLOT_TYPE.credit, letterSpacing: '-0.01em', color: MAT.ink, opacity: 0.72,
      ...(inFrame ? {lineHeight: 1, whiteSpace: 'nowrap'} : {lineHeight: 1.15, wordBreak: 'keep-all', textAlign: 'right', boxSizing: 'border-box', maxWidth: 'calc(100% - 64px)', background: 'rgba(251,249,243,0.6)', padding: '3px 8px 4px'})}}>{line}</div>
  );
};
