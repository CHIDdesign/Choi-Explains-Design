import React from 'react';
import {Img, interpolate, OffthreadVideo, staticFile} from 'remotion';
import {EASE, LONG, tween, tweenOut} from '../../design/motion';
import {FONT, NOTE} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {fitBlock, fitSize, wrap} from '../../lib/fit';
import type {Graphic, GraphicData, TemplateName} from '../../lib/types';
import {Credit} from '../layout/Editorial';
import {pipBoxes} from '../paper/Collage';
import {hashSeed} from '../paper/Paper';
import type {Box} from '../paper/Paper';
import {Badge, PaperNote, ReverseLine} from './Note';
import {Annotated, RiseLine, Rule} from './Stage';

/**
 * 얼굴 옆 종이 메모(롱폼 무대 재질 v2, classic 챕터) — 화자 반대편 상단 기준선에 놓이는 위가 찢긴 크림 메모.
 *  ConceptPlate : 배지 → (키워드) 보조문 + 핵심 줄 **반전 상자** / (정의) 용어 + 영문 + 괘선 + 풀이 / (숫자) Anton 카운트업
 *                 / (인용) 명조 + 큰 따옴표
 *  MediaPlate   : 종이 위에 붙인 사진·스톡(아주 느린 푸시) + 아래 캡션 줄(이름 · 설명 · ▣ 출처)
 * 같은 내용을 보드 판(split) 안에서는 mode="board" 로 크게 그린다(BoardPanel).
 */
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const CONCEPT_TEMPLATES: ReadonlySet<string> = new Set(['keyword', 'definition', 'quote', 'stat']);

const ROLE: Record<string, string> = {keyword: '키워드', definition: '정의', quote: '인용', stat: '숫자'};
const REVERSE_MAX = 14; // 이보다 짧은 키워드는 반전 상자 한 줄로

/** "85%" → {n: 85, prefix: '', suffix: '%', decimals: 0} — 카운트업할 수 있는 숫자면 값을 돌려준다 */
export const parseNumber = (s: string): {n: number; prefix: string; suffix: string; decimals: number; grouped: boolean}
  | null => {
  const m = s.trim().match(/^([^\d\-−+]*)([+\-−]?\d[\d,]*(?:\.\d+)?)(.*)$/);
  if (!m) return null;
  const raw = m[2].replace(/,/g, '').replace('−', '-');
  const n = parseFloat(raw);
  if (!Number.isFinite(n)) return null;
  const decimals = (raw.split('.')[1] || '').length;
  return {n, prefix: m[1], suffix: m[3], decimals, grouped: m[2].includes(',')};
};

const fmt = (v: number, decimals: number, grouped: boolean) => {
  const s = v.toFixed(decimals);
  if (!grouped) return s;
  const [a, b] = s.split('.');
  return a.replace(/\B(?=(\d{3})+(?!\d))/g, ',') + (b ? '.' + b : '');
};

type ContentProps = {
  template: TemplateName;
  data: GraphicData;
  frame: number;
  dur: number;
  theme: Theme;
  w: number; // 안쪽 폭
  h: number; // 안쪽 높이
  s: number; // 배율(메모 700 기준 1, 보드 1.3 안팎)
  mode: 'plate' | 'board';
  label?: string; // 배지에 쓸 역할 라벨(없으면 템플릿 역할)
};

/** 개념 내용(키워드·정의·숫자·인용) — 메모와 보드가 같이 쓴다. 색은 종이 위 잉크, 강조는 시그널 한 곳 */
export const ConceptContent: React.FC<ContentProps> = ({template, data, frame, dur, theme, w, h, s, mode, label}) => {
  const fg = NOTE.ink;
  const dim = NOTE.inkSoft;
  const note = NOTE.note;
  const rule = NOTE.rule;
  const accent = theme.accent;
  // 배지 = 이 조각의 역할 라벨(모션 디자이너가 body 에 쓴 "이유·예시·결론…"), 없으면 템플릿 역할. 키워드의 subtitle 은 보조문 줄
  const chip = label || (template === 'keyword' ? data.body || ROLE.keyword : ROLE[template]);
  const chipSize = Math.round((mode === 'board' ? 22 : 20) * s);
  const headMax = (mode === 'board' ? 92 : 60) * s;
  const headMin = 30 * s;
  const bodySize = Math.round((mode === 'board' ? 34 : 26) * s);
  const noteSize = Math.round((mode === 'board' ? 22 : 19) * s);
  const gapS = Math.round(14 * s);
  const out = tweenOut(frame, dur, LONG.out);
  const col: React.CSSProperties = {position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
    justifyContent: 'center', opacity: out};
  const header = (
    <div style={{display: 'flex', alignItems: 'center', gap: 12 * s, opacity: tween(frame, 2, 10)}}>
      <Badge text={chip} size={chipSize} />
    </div>
  );
  const ruleEl = <div style={{marginTop: gapS}}><Rule frame={frame} delay={4} color={rule} /></div>;
  const foot = (text: string, delay = 16) => text ? (
    <div style={{marginTop: gapS, fontFamily: FONT.sans, fontWeight: 500, fontSize: noteSize, color: note,
      opacity: tween(frame, delay, 10), whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>( {text} )</div>
  ) : null;

  if (template === 'stat') {
    const num = data.title || '';
    const parsed = parseNumber(num);
    const p = interpolate(frame, [4, 4 + LONG.count], [0, 1], {...clamp, easing: EASE.outExpo});
    const shown = parsed ? `${parsed.prefix}${fmt(parsed.n * p, parsed.decimals, parsed.grouped)}${parsed.suffix}` : num;
    const numSize = Math.min((mode === 'board' ? 220 : 132) * s, fitSize(num, w * 0.52, (mode === 'board' ? 220 : 132) * s, 60 * s));
    const land = interpolate(frame, [4 + LONG.count, 4 + LONG.count + 6], [1, 1.03], clamp)
      * interpolate(frame, [4 + LONG.count + 6, 4 + LONG.count + 12], [1, 1 / 1.03], clamp);
    const body = fitBlock(data.body || '', w - numSize * 0.5 - w * 0.5, h * 0.5, bodySize * 1.15, bodySize * 0.8, 1.35, 3);
    return (
      <div style={col}>
        {header}
        <div style={{display: 'flex', alignItems: 'center', gap: 28 * s, marginTop: gapS}}>
          <div style={{fontFamily: FONT.latin, fontSize: numSize, lineHeight: 1, color: accent,
            letterSpacing: '0.005em', fontVariantNumeric: 'tabular-nums', scale: `${land}`, transformOrigin: '0% 60%',
            opacity: tween(frame, 3, 8), whiteSpace: 'nowrap'}}>{shown}</div>
          <div style={{display: 'flex', flexDirection: 'column'}}>
            {body.lines.map((l, i) => (
              <RiseLine key={i} frame={frame} delay={8 + i * 3}>
                <div style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: body.size, lineHeight: 1.3, color: fg,
                  letterSpacing: '-0.02em', whiteSpace: 'nowrap'}}>{l}</div>
              </RiseLine>
            ))}
          </div>
        </div>
        {foot(data.subtitle || data.source || '')}
      </div>
    );
  }

  if (template === 'quote') {
    const text = data.body || data.title || '';
    const qSize = Math.min((mode === 'board' ? 56 : 34) * s, fitBlock(text, w, h * 0.6, (mode === 'board' ? 56 : 34) * s,
      22 * s, 1.5, 4).size);
    const lines = wrap(text, qSize, w * 0.96, 4);
    const who = [data.author, data.source].filter(Boolean).join(' · ');
    return (
      <div style={col}>
        {header}
        <div style={{position: 'relative', marginTop: gapS * 1.4, paddingLeft: qSize * 1.1}}>
          <div style={{position: 'absolute', left: -qSize * 0.08, top: -qSize * 0.42, fontFamily: FONT.latin,
            fontSize: qSize * 2.6, lineHeight: 1, color: accent, opacity: 0.9 * tween(frame, 4, 10)}}>“</div>
          {lines.map((l, i) => (
            <RiseLine key={i} frame={frame} delay={6 + i * 3}>
              <div style={{fontFamily: FONT.serif, fontWeight: 500, fontSize: qSize, lineHeight: 1.5, color: fg,
                letterSpacing: '-0.01em', whiteSpace: 'nowrap'}}>{l}</div>
            </RiseLine>
          ))}
        </div>
        {who ? (
          <div style={{display: 'flex', alignItems: 'center', gap: 14 * s, marginTop: gapS * 1.3,
            opacity: tween(frame, 12 + lines.length * 3, 10)}}>
            <Rule frame={frame} delay={12 + lines.length * 3} color={accent} thick={2} width={40 * s} />
            <div style={{fontFamily: FONT.sans, fontWeight: 600, fontSize: noteSize * 1.1, color: dim,
              whiteSpace: 'nowrap'}}>{who}</div>
          </div>
        ) : null}
      </div>
    );
  }

  if (template === 'keyword' && (data.title || '').length <= REVERSE_MAX && !data.accent) {
    // 레퍼런스의 '강조 박스 문구': 보조문은 그대로, 핵심 줄만 시그널 반전 상자
    const title = data.title || '';
    const sub = data.subtitle || '';
    const size = Math.min(headMax * 0.86, fitSize(title, w * 0.96, headMax * 0.86, headMin, -0.035));
    return (
      <div style={col}>
        {header}
        {sub ? (
          <RiseLine frame={frame} delay={5}>
            <div style={{marginTop: gapS * 1.1, fontFamily: FONT.sans, fontWeight: 600, fontSize: bodySize, lineHeight: 1.4,
              color: dim, letterSpacing: '-0.01em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>{sub}</div>
          </RiseLine>
        ) : null}
        <div style={{marginTop: sub ? gapS * 0.6 : gapS * 1.2}}>
          <ReverseLine text={title} size={size} bg={accent} p={tween(frame, sub ? 9 : 6, 9, 'outQuint')} />
        </div>
        {foot(data.source || '', 16)}
      </div>
    );
  }

  // keyword(긴 제목·강조어 지정) · definition
  const head = data.title || '';
  const hb = fitBlock(head, w, h * (template === 'definition' ? 0.34 : 0.5), headMax, headMin, 1.16, 2, -0.035);
  const eng = template === 'definition' ? data.subtitle || '' : '';
  const bodyText = template === 'definition' ? data.body || '' : data.subtitle || '';
  const bodyLines = bodyText ? wrap(bodyText, bodySize, w, 3) : [];
  const nHead = hb.lines.length;
  return (
    <div style={col}>
      {header}
      <div style={{marginTop: gapS * 1.2, display: 'flex', flexDirection: 'column'}}>
        {hb.lines.map((l, i) => (
          <RiseLine key={i} frame={frame} delay={6 + i * 3}>
            <div style={{fontFamily: FONT.display, fontWeight: 900, fontSize: hb.size, lineHeight: 1.16,
              letterSpacing: '-0.035em', whiteSpace: 'nowrap'}}>
              <Annotated text={l} accent={i === nHead - 1 ? data.accent : null}
                p={tween(frame, 14 + i * 3, LONG.underline, 'outQuint')} color={fg} accentColor={accent} />
              {eng && i === nHead - 1 ? (
                <span style={{fontFamily: FONT.serif, fontStyle: 'italic', fontWeight: 500, fontSize: hb.size * 0.42,
                  color: accent, marginLeft: hb.size * 0.3, letterSpacing: '0', verticalAlign: 'baseline',
                  opacity: tween(frame, 10, 10)}}>{eng}</span>
              ) : null}
            </div>
          </RiseLine>
        ))}
      </div>
      {template === 'definition' ? ruleEl : null}
      {bodyLines.length ? (
        <div style={{marginTop: gapS, display: 'flex', flexDirection: 'column'}}>
          {bodyLines.map((l, i) => (
            <RiseLine key={i} frame={frame} delay={12 + nHead * 3 + i * 3}>
              <div style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: bodySize, lineHeight: 1.45, color: dim,
                letterSpacing: '-0.01em', whiteSpace: 'nowrap'}}>{l}</div>
            </RiseLine>
          ))}
        </div>
      ) : null}
      {foot(data.source || '', 18 + nHead * 3)}
    </div>
  );
};

/** 사진·스톡 내용: 종이 위에 붙인 미디어(아주 느린 푸시) + 캡션 줄(잉크) */
export const MediaContent: React.FC<{data: GraphicData; template: TemplateName; frame: number; dur: number; w: number;
  h: number; s: number; radius?: number; onPaper?: boolean}> = ({data, template, frame, dur, w, h, s, radius,
  onPaper = true}) => {
  const src = template === 'broll' ? data.src : data.image;
  if (!src) return null;
  const isVideo = template === 'broll' && (data.kind === 'video' || /\.(mp4|webm|mov)$/i.test(src));
  const kb = data.kenburns ?? 'in';
  const prog = interpolate(frame, [0, Math.max(1, dur)], [0, 1], clamp);
  const scale = isVideo ? 1 + 0.04 * prog : kb === 'out' ? 1.07 - 0.05 * prog : 1.02 + 0.05 * prog;
  const tx = kb === 'left' ? -2 * prog : kb === 'right' ? 2 * prog : 0;
  const capH = data.title || data.body || data.credit ? Math.round(58 * s) : 0;
  const mediaH = h - capH;
  const p = tween(frame, 0, 12, 'outQuint');
  const st: React.CSSProperties = {position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover'};
  const fg = onPaper ? NOTE.ink : '#fff';
  const dim = onPaper ? NOTE.inkSoft : 'rgba(255,255,255,0.66)';
  const credit = onPaper ? NOTE.note : 'rgba(255,255,255,0.55)';
  return (
    <div style={{position: 'absolute', inset: 0, opacity: tweenOut(frame, dur, LONG.out)}}>
      <div style={{position: 'absolute', left: 0, top: 0, width: w, height: mediaH, overflow: 'hidden',
        borderRadius: radius ?? Math.round(4 * s), background: '#0B0B0B', boxShadow: onPaper ? '0 6px 16px rgba(0,0,0,0.22)' : undefined,
        scale: `${interpolate(p, [0, 1], [1.03, 1])}`, transformOrigin: '50% 50%'}}>
        <div style={{position: 'absolute', inset: 0, scale: `${scale}`, translate: `${tx}% 0`}}>
          {isVideo ? <OffthreadVideo src={staticFile(src)} muted style={st} /> : <Img src={staticFile(src)} style={st} />}
        </div>
      </div>
      {capH ? (
        <div style={{position: 'absolute', left: 0, right: 0, top: mediaH, height: capH, display: 'flex',
          alignItems: 'center', justifyContent: 'space-between', gap: 16 * s}}>
          <RiseLine frame={frame} delay={8}>
            <div style={{display: 'flex', alignItems: 'baseline', gap: 12 * s, whiteSpace: 'nowrap'}}>
              {data.title ? <span style={{fontFamily: FONT.sans, fontWeight: 800, fontSize: Math.round(26 * s),
                color: fg, letterSpacing: '-0.02em'}}>{data.title}</span> : null}
              {data.body ? <span style={{fontFamily: FONT.sans, fontWeight: 500, fontSize: Math.round(20 * s),
                color: dim}}>{data.body}</span> : null}
            </div>
          </RiseLine>
          {data.credit ? <div style={{opacity: tween(frame, 12, 10), flexShrink: 0}}>
            <Credit text={data.credit} color={credit} size={Math.round(15 * s)} /></div> : null}
        </div>
      ) : null}
    </div>
  );
};

/** 메모 자리·크기: 파이프라인이 얼굴 트랙으로 정한 빈 쪽(g.pip), 없으면 faceX 반대편 */
export const plateBox = (g: Graphic, faceX: number, W: number): {b: Box; right: boolean; s: number} => {
  const {b, right} = pipBoxes(faceX, W, g.pip);
  const media = g.template === 'photo' || g.template === 'broll';
  const h = Math.round(b.w * (media ? 0.78 : g.template === 'quote' ? 0.64 : 0.56));
  return {b: {...b, h}, right, s: b.w / 700};
};

type PlateProps = {g: Graphic; frame: number; dur: number; W: number; theme: Theme; faceX: number; label?: string};

/** 종이 메모(개념) */
export const ConceptPlate: React.FC<PlateProps> = ({g, frame, dur, W, theme, faceX, label}) => {
  const {b, right, s} = plateBox(g, faceX, W);
  const from = right ? 'right' : 'left';
  const pad = Math.round(36 * s);
  return (
    <PaperNote x={b.x} y={b.y} w={b.w} h={b.h} frame={frame} dur={dur} from={from} theme={theme} seed={hashSeed(g.id)}
      pad={pad} id={g.id}>
      <ConceptContent template={g.template} data={g.data} frame={frame} dur={dur} theme={theme} w={b.w - pad * 2}
        h={b.h - pad * 2 - 6} s={s} mode="plate" label={label} />
    </PaperNote>
  );
};

/** 종이 위에 붙인 사진·스톡 */
export const MediaPlate: React.FC<PlateProps> = ({g, frame, dur, W, theme, faceX}) => {
  const {b, right, s} = plateBox(g, faceX, W);
  const from = right ? 'right' : 'left';
  const pad = Math.round(22 * s);
  return (
    <PaperNote x={b.x} y={b.y} w={b.w} h={b.h} frame={frame} dur={dur} from={from} theme={theme} seed={hashSeed(g.id)}
      pad={pad} id={g.id}>
      <MediaContent data={g.data} template={g.template} frame={frame} dur={dur} w={b.w - pad * 2} h={b.h - pad * 2 - 6}
        s={s} />
    </PaperNote>
  );
};
