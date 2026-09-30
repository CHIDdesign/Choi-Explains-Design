import React, {useMemo} from 'react';
import {AbsoluteFill, Img, interpolate, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {cameraAt, punchFactor} from '../../compositions/LongForm';
import {DUR, tween} from '../../design/motion';
import {surface as mkSurface, TEMPLATE_LABEL} from '../../design/surfaces';
import {FONT, makeTheme, rgba} from '../../design/tokens';
import {fitSize, wrap} from '../../lib/fit';
import {lastIndexAtOrBefore, sampleFace, toFrame} from '../../lib/time';
import type {CaptionCue, Graphic, ShortBeat, ShortProps} from '../../lib/types';
import {LivePeek} from '../fx/LivePeek';
import {TEMPLATE_COMPONENTS} from '../graphics';
import {conceptText} from '../paper/Collage';
import {hashSeed, pickAccent, seeded} from '../paper/Paper';
import {TalkingHead, videoBoxFor} from '../TalkingHead';
import type {Rect} from '../TalkingHead';

/**
 * 릴스식 숏폼(1080×1920) — 사용자가 참고로 보낸 릴스(hongik.man 등)의 구성을 옮김:
 *  · 위(약 43%): 밝은 배경 위 큰 둥근 카드 한 장 — 말하는 내용에 맞춰 사진·스톡·도식·개념 텍스트로 계속 바뀐다
 *  · 아래: 화자 얼굴 전체 폭
 *  · 이음새: 한두 마디씩 아주 굵은 흰 자막(검은 외곽선·그림자)
 *  · 첫 2.2초(사진·스톡이 있을 때만): 흰 화면에 카드 여러 장이 부채꼴로 겹치고 큰 제목(훅) → 카드가 위로 모이며
 *    얼굴이 올라온다. 없으면 첫 프레임부터 위 카드 + 얼굴
 *  · 개념 텍스트의 핵심어에는 형광펜(다른 참고 릴스)
 */
const SEAM = 830;
const FACE: Rect = {x: 0, y: SEAM, w: 1080, h: 1920 - SEAM};
const CARD = {x: 50, y: 70, w: 980, h: 720};
const BG = '#F5F5F3';
const INK = '#17181C';

type Slide = {start: number; end: number; kind: 'graphic' | 'beat' | 'title'; g?: Graphic; b?: ShortBeat};

const mediaOf = (g?: Graphic) => (!g ? undefined : g.template === 'photo' ? g.data.image
  : g.template === 'broll' ? g.data.src : undefined);
const CONCEPT = new Set(['keyword', 'definition', 'quote', 'stat']);

/** 카드 순서: 그래픽 > 개념 텍스트 > (빈 곳은) 앞 카드를 이어서 보여 준다 — 위 카드가 비지 않게 */
export const buildSlides = (graphics: Graphic[], beats: ShortBeat[], total: number, heroEnd: number): Slide[] => {
  const raw: Slide[] = [
    ...graphics.map((g) => ({start: g.start, end: g.end, kind: 'graphic' as const, g})),
    ...beats.filter((b) => !graphics.some((g) => b.start < g.end && b.end > g.start))
      .map((b) => ({start: b.start, end: b.end, kind: 'beat' as const, b})),
  ].filter((s) => s.end > heroEnd).sort((a, b) => a.start - b.start);
  const out: Slide[] = [];
  let cur = heroEnd;
  if (!raw.length || raw[0].start > heroEnd + 0.3) {
    out.push({start: heroEnd, end: raw.length ? raw[0].start : total, kind: 'title'});
  }
  for (const s of raw) {
    const start = Math.max(s.start, cur);
    if (out.length && start - out[out.length - 1].end < 1.2) out[out.length - 1].end = start;   // 짧은 빈틈은 앞 카드로
    out.push({...s, start});
    cur = s.end;
  }
  if (out.length) out[out.length - 1].end = Math.max(out[out.length - 1].end, total);
  for (let i = 0; i + 1 < out.length; i++) out[i].end = Math.max(out[i].end, out[i + 1].start);
  return out;
};

const Marker: React.FC<{text: string; p: number; color: string}> = ({text, p, color}) => (
  <span style={{backgroundImage: `linear-gradient(transparent 58%, ${color} 58%, ${color} 92%, transparent 92%)`,
    backgroundSize: `${Math.max(0, Math.min(1, p)) * 100}% 100%`, backgroundRepeat: 'no-repeat'}}>{text}</span>
);

const Highlighted: React.FC<{text: string; accent?: string | null; p: number; color: string}> = ({text, accent, p,
  color}) => {
  const a = pickAccent(text, accent);
  const i = a ? text.indexOf(a) : -1;
  if (i < 0) return <>{text}</>;
  return <>{text.slice(0, i)}<Marker text={a} p={p} color={color} />{text.slice(i + a.length)}</>;
};

const MediaFill: React.FC<{src: string; video: boolean; f: number; dur: number}> = ({src, video, f, dur}) => {
  const push = interpolate(f, [0, Math.max(1, dur)], [1.0, 1.06], {extrapolateRight: 'clamp'});
  const st: React.CSSProperties = {width: '100%', height: '100%', objectFit: 'cover', scale: `${push}`};
  return video ? <OffthreadVideo src={staticFile(src)} muted style={st} /> : <Img src={staticFile(src)} style={st} />;
};

/** 위 카드 한 장의 내용 */
const CardContent: React.FC<{s: Slide; f: number; fps: number; props: ShortProps;
  theme: ReturnType<typeof makeTheme>; marker: string}> = ({s, f, fps, props, theme, marker}) => {
  const dur = Math.max(1, (s.end - s.start) * fps);
  const g = s.g;
  const src = mediaOf(g);
  if (g && src) {
    const video = g.template === 'broll' && (g.data.kind === 'video' || /\.(mp4|webm|mov)$/i.test(src));
    return (
      <>
        <MediaFill src={src} video={video} f={f} dur={dur} />
        {g.data.title ? (
          <div style={{position: 'absolute', left: 28, bottom: 26, background: 'rgba(17,17,20,0.82)', color: '#fff',
            fontFamily: FONT.sans, fontWeight: 700, fontSize: 32, padding: '6px 16px 8px', borderRadius: 12,
            opacity: tween(f, 8, 10)}}>{g.data.title}</div>
        ) : null}
      </>
    );
  }
  if (g && !CONCEPT.has(g.template)) {
    // 도식·목록·모션: 어두운 앱 화면 같은 카드(참고 릴스의 어두운 UI 카드)
    const Comp = TEMPLATE_COMPONENTS[g.template];
    if (!Comp) return null;
    const surf = mkSurface(theme, 'ink');
    return (
      <div style={{position: 'absolute', inset: 0, background: INK}}>
        <div style={{position: 'absolute', left: 30, top: 22, display: 'flex', gap: 10}}>
          {['#FF5F57', '#FEBC2E', '#28C840'].map((c) => <span key={c} style={{width: 14, height: 14, borderRadius: 7,
            background: c, display: 'inline-block', opacity: 0.9}} />)}
        </div>
        <div style={{position: 'absolute', left: 0, right: 0, top: 16, textAlign: 'center', fontFamily: FONT.sans,
          fontWeight: 600, fontSize: 22, color: 'rgba(255,255,255,0.6)'}}>{TEMPLATE_LABEL[g.template]}</div>
        <div style={{position: 'absolute', left: 50, top: 70, width: CARD.w - 100, height: CARD.h - 110}}>
          <Comp id={g.id} data={g.data} frame={f} dur={dur} fps={fps} theme={theme} surface={surf}
            box={{w: CARD.w - 100, h: CARD.h - 110}} layout="split" brand={props.brand} episode={props.episode} />
        </div>
      </div>
    );
  }
  // 개념 텍스트(키워드·정의·숫자 또는 beats) / 제목: 흰 카드 + 짙은 굵은 글씨 + 형광펜
  let label = '';
  let head = '';
  let body = '';
  let accent: string | undefined;
  if (g) {
    const c = conceptText(g.template, g.data);
    label = TEMPLATE_LABEL[g.template];
    head = c.head;
    body = c.body;
    accent = g.data.accent;
  } else if (s.b) {
    label = s.b.label || '';
    head = s.b.text;
    accent = s.b.accent;
  } else {
    label = props.seriesLabel;
    head = props.hookTitle.replace(/\n/g, ' ');
    accent = props.hookHighlight || undefined;
  }
  const lines = wrap(head, 110, CARD.w - 120, 3).slice(0, 3);
  const size = Math.min(118, ...lines.map((l) => fitSize(l, CARD.w - 120, 118, 60, -0.045)));
  return (
    <div style={{position: 'absolute', inset: 0, background: '#FFFFFF', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', padding: '0 60px', textAlign: 'center'}}>
      {label ? <div style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: 32, color: theme.accent, marginBottom: 18,
        opacity: tween(f, 2, 10)}}>{label}</div> : null}
      {lines.map((l, i) => (
        <div key={i} style={{fontFamily: FONT.display, fontWeight: 800, fontSize: size, lineHeight: 1.18,
          letterSpacing: '-0.045em', color: INK, whiteSpace: 'nowrap',
          opacity: tween(f, 3 + i * 3, 12), translate: `0 ${interpolate(tween(f, 3 + i * 3, 14), [0, 1], [18, 0])}px`}}>
          <Highlighted text={l} accent={i === lines.length - 1 ? accent : null} p={tween(f, 12 + i * 3, 14)}
            color={marker} />
        </div>
      ))}
      {body ? <div style={{marginTop: 22, fontFamily: FONT.sans, fontWeight: 500, fontSize: 38, lineHeight: 1.4,
        color: '#5A5A60', opacity: tween(f, 10, 12)}}>{wrap(body, 38, CARD.w - 120, 2).map((l, i) => <div key={i}>{l}</div>)}</div>
        : null}
    </div>
  );
};

/** 제목 형광펜: 지정한 강조어가 있으면 그 낱말만, 없으면 마지막 줄의 마지막 어절만 */
const titleAccent = (props: ShortProps, line: string, i: number, n: number): string | null | undefined => {
  const h = props.hookHighlight;
  if (h && props.hookTitle.includes(h)) return line.includes(h) ? h : null;
  return i === n - 1 ? undefined : null;
};

/** 한두 마디씩, 아주 굵은 흰 글씨 + 검은 외곽선·그림자(참고 릴스 자막) */
const SeamCaption: React.FC<{cues: CaptionCue[]; t: number; fps: number; y: number; accent: string}> = ({cues, t, fps,
  y, accent}) => {
  const i = lastIndexAtOrBefore(cues, t, (c) => c.start);
  if (i < 0 || t >= cues[i].end || cues[i].hidden) return null;
  const cue = cues[i];
  const words = cue.lines.flat();
  const text = words.map((w) => w.text).join(' ');
  const size = Math.min(112, fitSize(text, 960, 112, 64, -0.03));
  const f = (t - cue.start) * fps;
  const pop = interpolate(tween(f, 0, 4, 'outCubic'), [0, 1], [0.92, 1]);
  return (
    <div style={{position: 'absolute', left: 0, width: 1080, top: y - size * 0.62, textAlign: 'center',
      whiteSpace: 'nowrap', scale: `${pop}`}}>
      {words.map((w, k) => (
        <span key={k} style={{fontFamily: FONT.display, fontWeight: 900, fontSize: size, letterSpacing: '-0.035em',
          color: w.em ? accent : '#FFFFFF', paintOrder: 'stroke fill', WebkitTextStroke: `${size * 0.1}px #111`,
          textShadow: '0 6px 0 rgba(0,0,0,0.45), 0 12px 26px rgba(0,0,0,0.35)'}}>
          {w.text}{k < words.length - 1 ? ' ' : ''}
        </span>
      ))}
    </div>
  );
};

/** 첫 장면: 흰 화면에 카드가 부채꼴로 겹치고 큰 제목 */
const Hero: React.FC<{props: ShortProps; frame: number; fps: number; out: number; marker: string}> = ({props, frame,
  fps, out, marker}) => {
  const cards = props.graphics.filter((g) => mediaOf(g)).slice(0, 3);
  const lines = props.hookTitle.split('\n').filter(Boolean).slice(0, 2);
  const size = Math.min(132, ...lines.map((l) => fitSize(l, 960, 132, 72, -0.04)));
  const tilts = [-7, 5, -2];
  return (
    <AbsoluteFill style={{background: BG, opacity: out}}>
      {cards.map((g, i) => {
        const p = tween(frame, i * 4, DUR.slow, 'outCubic');
        const w = 760;
        const h = 500;
        const src = mediaOf(g)!;
        return (
          <div key={g.id} style={{position: 'absolute', left: 540 - w / 2 + (i - 1) * 70, top: 470 + i * 26, width: w,
            height: h, borderRadius: 26, overflow: 'hidden', boxShadow: '0 30px 70px rgba(0,0,0,0.28)', background: '#ddd',
            rotate: `${interpolate(p, [0, 1], [tilts[i] + 8, tilts[i]])}deg`, opacity: p,
            translate: `0 ${interpolate(p, [0, 1], [80, 0])}px`}}>
            {g.template === 'broll' && g.data.kind === 'video'
              ? <OffthreadVideo src={staticFile(src)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
              : <Img src={staticFile(src)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />}
          </div>
        );
      })}
      <div style={{position: 'absolute', left: 0, width: 1080, top: cards.length ? 1130 : 700, textAlign: 'center'}}>
        {props.seriesLabel ? <div style={{fontFamily: FONT.sans, fontWeight: 700, fontSize: 34,
          color: '#6B6B70', marginBottom: 20}}>{props.seriesLabel}</div> : null}
        {lines.map((l, i) => (
          <div key={i} style={{fontFamily: FONT.display, fontWeight: 900, fontSize: size, lineHeight: 1.16,
            letterSpacing: '-0.04em', color: INK, whiteSpace: 'nowrap',
            translate: `0 ${interpolate(tween(frame, 2 + i * 3, 12), [0, 1], [24, 0])}px`,
            opacity: tween(frame, 2 + i * 3, 10)}}>
            <Highlighted text={l} accent={titleAccent(props, l, i, lines.length)} p={tween(frame, 10 + i * 4, 14)}
              color={marker} />
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

export const ReelShort: React.FC<ShortProps> = (props) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const t = frame / fps;
  const theme = useMemo(() => makeTheme(props.brand), [props.brand]);
  const marker = rgba(theme.accent, 0.3);
  const face = sampleFace(props.face, t);
  const zoom = cameraAt(props.camera ?? [], t).zoom * punchFactor(props.punches, t, fps);
  // 사진·스톡이 있으면 첫 2.2초는 부채꼴 카드 + 큰 제목, 없으면 첫 프레임부터 위 카드 + 얼굴
  const heroEnd = props.graphics.some((g) => mediaOf(g)) ? 2.2 : 0;
  const total = durationInFrames / fps;
  const slides = useMemo(() => buildSlides(props.graphics, props.beats ?? [], total, heroEnd),
    [props.graphics, props.beats, total]);
  // 첫 장면 → 본 구성: 0.6초에 걸쳐 흰 화면이 걷히고 얼굴이 아래에서 올라온다
  const k = heroEnd > 0 ? tween(frame, toFrame(heroEnd, fps), 18, 'inOutCubic') : 1;
  const faceRegion: Rect = {...FACE, y: SEAM + (1 - k) * 260};
  const box = videoBoxFor(faceRegion, face, zoom, 'center', 0.40);
  const si = lastIndexAtOrBefore(slides, t, (s) => s.start);

  return (
    <AbsoluteFill style={{background: BG}}>
      <div style={{position: 'absolute', left: 0, top: 0, width: 1080, height: SEAM + 40,
        background: `linear-gradient(180deg, #E9E9E6 0%, ${BG} 18%, ${BG} 100%)`}} />
      {/* 위 카드: 새 카드가 살짝 아래에서 올라오며 앞 카드를 덮는다 */}
      {slides.map((s, i) => {
        if (i < si - 1 || i > si) return null;
        const f = (t - s.start) * fps;
        const p = tween(f, 0, 14, 'outCubic');
        const seedTilt = (seeded(hashSeed(`${i}${s.start}`))() - 0.5) * 1.2;
        const leaving = i < si;
        return (
          <div key={`${i}-${s.start}`} style={{position: 'absolute', left: CARD.x, top: CARD.y, width: CARD.w, height: CARD.h,
            borderRadius: 30, overflow: 'hidden', boxShadow: '0 26px 60px rgba(0,0,0,0.22)', background: '#fff',
            opacity: leaving ? 1 : p * k, rotate: `${leaving ? 0 : interpolate(p, [0, 1], [seedTilt + 1.5, 0])}deg`,
            scale: `${leaving ? interpolate(tween((t - slides[si].start) * fps, 0, 14), [0, 1], [1, 0.96]) : interpolate(p, [0, 1], [0.97, 1])}`,
            translate: `0 ${leaving ? 0 : interpolate(p, [0, 1], [40, 0])}px`}}>
            <CardContent s={s} f={f} fps={fps} props={props} theme={theme} marker={marker} />
          </div>
        );
      })}
      <div style={{opacity: k}}>
        <TalkingHead clips={props.clips} fps={fps} region={faceRegion} box={box} />
      </div>
      {heroEnd > 0 && frame < toFrame(heroEnd, fps) + 18 ? <Hero props={props} frame={frame} fps={fps} out={1 - k} marker={marker} />
        : null}
      <SeamCaption cues={props.captions} t={t} fps={fps} y={k > 0.5 ? SEAM + 70 : 1740} accent={theme.accent} />
      {props.progressBar ? (
        <div style={{position: 'absolute', left: 0, bottom: 0, height: 6, width: (1080 * frame) / Math.max(1, durationInFrames),
          background: theme.accent, opacity: 0.85}} />
      ) : null}
      <LivePeek every={props.peekEvery} />
    </AbsoluteFill>
  );
};
