import React, {useMemo} from 'react';
import {AbsoluteFill, interpolate, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {DUR, tween, tweenOut} from '../../design/motion';
import {surface as mkSurface, TEMPLATE_LABEL} from '../../design/surfaces';
import {FONT, makeTheme} from '../../design/tokens';
import {fitSize, wrap} from '../../lib/fit';
import {lastIndexAtOrBefore, sampleFace, toFrame} from '../../lib/time';
import type {Graphic, ShortBeat, ShortProps} from '../../lib/types';
import {ShortCaptions} from '../captions/ShortCaptions';
import {LivePeek} from '../fx/LivePeek';
import {TransitionStage, transitionState} from '../fx/Transitions';
import {TEMPLATE_COMPONENTS} from '../graphics';
import {lerpBox, lerpRect, TalkingHead, videoBoxFor} from '../TalkingHead';
import type {Rect} from '../TalkingHead';
import {cameraAt, punchFactor} from '../../compositions/LongForm';
import {conceptText, FramedMedia} from './Collage';
import {AccentText, hashSeed, LabelTag, PAPER, PaperBg, TornFrame} from './Paper';

/**
 * 종이 스킨 숏폼(1080×1920) — 롱폼을 잘라 붙인 화면이 아니라 세로 전용 구성.
 *  위: 시리즈 라벨 + 2줄 훅 제목(한 낱말 주황) — 첫 프레임부터
 *  가운데: 찢어진 액자 창(화자). 도식·사진이 나오면 창을 차지하고 화자는 아래 작은 액자로 물러난다
 *  창 아래: 한두 마디 자막(흰 종이 박스)
 *  아래: 3~5초마다 바뀌는 개념 텍스트(검정 라벨 + 큰 글씨) — 빈 하단이 없게
 */
export const SHORT_WIN: Rect = {x: 60, y: 470, w: 960, h: 800};
const SHORT_SMALL: Rect = {x: 610, y: 1368, w: 410, h: 272};
const CAPTION_Y = 1262;

const media = (g: Graphic) => (g.template === 'photo' ? g.data.image : g.template === 'broll' ? g.data.src : undefined);

const WindowGraphic: React.FC<{g: Graphic; dur: number; props: ShortProps; theme: ReturnType<typeof makeTheme>}> = ({
  g, dur, props, theme}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const src = media(g);
  if (src) {
    return <FramedMedia src={src} kind={g.template === 'broll' ? g.data.kind : 'photo'} b={SHORT_WIN} frame={frame}
      dur={dur} seed={hashSeed(g.id)} />;
  }
  const Comp = TEMPLATE_COMPONENTS[g.template];
  if (!Comp) return null;
  const s = mkSurface(theme, 'crumple');
  const p = Math.min(tween(frame, 4, DUR.slow, 'outCubic'), tweenOut(frame, dur, 9));
  const concept = ['keyword', 'definition', 'quote', 'stat'].includes(g.template);
  if (concept) {
    const {head, body, note} = conceptText(g.template, g.data);
    const lines = wrap(head, 104, SHORT_WIN.w - 60, 3);
    const size = Math.min(110, ...lines.map((l) => fitSize(l, SHORT_WIN.w - 60, 110, 56, -0.03)));
    return (
      <div style={{position: 'absolute', left: SHORT_WIN.x + 30, top: SHORT_WIN.y + 40, width: SHORT_WIN.w - 60,
        opacity: p, translate: `0 ${interpolate(p, [0, 1], [20, 0])}px`}}>
        <LabelTag text={TEMPLATE_LABEL[g.template] || '개념'} />
        <div style={{marginTop: 30}}>
          {lines.map((l, i) => (
            <div key={i} style={{fontFamily: FONT.display, fontWeight: 500, fontSize: size, lineHeight: 1.16,
              letterSpacing: '-0.04em', whiteSpace: 'nowrap'}}>
              <AccentText text={l} accent={i === lines.length - 1 ? g.data.accent : null} />
            </div>
          ))}
        </div>
        {body ? <div style={{marginTop: 28, fontFamily: FONT.sans, fontSize: 40, lineHeight: 1.45, color: PAPER.body}}>
          {wrap(body, 40, SHORT_WIN.w - 60, 3).map((l, i) => <div key={i}>{l}</div>)}</div> : null}
        {note ? <div style={{marginTop: 18, fontFamily: FONT.sans, fontSize: 30, color: PAPER.note}}>( {note} )</div> : null}
      </div>
    );
  }
  return (
    <div style={{position: 'absolute', left: SHORT_WIN.x + 20, top: SHORT_WIN.y + 20, width: SHORT_WIN.w - 40,
      height: SHORT_WIN.h - 40, opacity: p, translate: `0 ${interpolate(p, [0, 1], [18, 0])}px`}}>
      <Comp id={g.id} data={g.data} frame={frame} dur={dur} fps={fps} theme={theme} surface={s}
        box={{w: SHORT_WIN.w - 40, h: SHORT_WIN.h - 40}} layout="split" brand={props.brand} episode={props.episode} />
    </div>
  );
};

/** 하단 개념 텍스트(레퍼런스 3의 '검정 라벨 + 큰 글씨'를 세로 화면 가운데 정렬로) */
const BeatText: React.FC<{b: ShortBeat; t: number; fps: number; W: number}> = ({b, t, fps, W}) => {
  const f = (t - b.start) * fps;
  const p = Math.min(tween(f, 0, DUR.slow, 'outCubic'), tweenOut(f, (b.end - b.start) * fps, 8));
  if (p <= 0) return null;
  const maxW = W - 140;
  const lines = wrap(b.text, 84, maxW, 2).slice(0, 2);
  const size = Math.min(84, ...lines.map((l) => fitSize(l, maxW, 84, 48, -0.035)));
  return (
    <div style={{position: 'absolute', left: 70, width: maxW, top: 1372, display: 'flex', flexDirection: 'column',
      alignItems: 'center', opacity: p, translate: `0 ${interpolate(p, [0, 1], [18, 0])}px`}}>
      {b.label ? <div style={{marginBottom: 14}}><LabelTag text={b.label} variant="black" size={32} /></div> : null}
      {lines.map((l, i) => (
        <div key={i} style={{fontFamily: FONT.display, fontWeight: 900, fontSize: size, lineHeight: 1.14,
          letterSpacing: '-0.04em', color: PAPER.white, whiteSpace: 'nowrap', textAlign: 'center',
          textShadow: '0 3px 0 rgba(0,0,0,0.5), 0 10px 26px rgba(0,0,0,0.45)'}}>
          <AccentText text={l} accent={i === lines.length - 1 ? b.accent : null} />
        </div>
      ))}
    </div>
  );
};

const PaperHookTitle: React.FC<{text: string; highlight: string; series: string; frame: number; W: number}> = ({
  text, highlight, series, frame, W}) => {
  const lines = text.split('\n').filter(Boolean).slice(0, 2);
  const maxW = W - 120;
  const size = Math.min(96, ...lines.map((l) => fitSize(l, maxW, 96, 60, -0.04)));
  const p = tween(frame, 0, 10, 'outCubic');
  return (
    <div style={{position: 'absolute', left: 60, width: maxW, top: 150, display: 'flex', flexDirection: 'column',
      alignItems: 'center'}}>
      {series ? <div style={{marginBottom: 22, opacity: interpolate(p, [0, 1], [0.5, 1])}}>
        <LabelTag text={series} size={30} /></div> : null}
      {lines.map((l, i) => (
        <div key={i} style={{fontFamily: FONT.display, fontWeight: 800, fontSize: size, lineHeight: 1.14,
          letterSpacing: '-0.045em', color: PAPER.white, whiteSpace: 'nowrap', textAlign: 'center',
          opacity: interpolate(p, [0, 1], [0.4, 1]), translate: `0 ${interpolate(p, [0, 1], [10, 0])}px`}}>
          <AccentText text={l} accent={highlight && l.includes(highlight) ? highlight : i === lines.length - 1
            ? undefined : null} />
        </div>
      ))}
    </div>
  );
};

export const PaperShort: React.FC<ShortProps> = (props) => {
  const frame = useCurrentFrame();
  const {fps, width: W, height: H, durationInFrames} = useVideoConfig();
  const t = frame / fps;
  const theme = useMemo(() => makeTheme(props.brand), [props.brand]);
  const face = sampleFace(props.face, t);
  const zoom = cameraAt(props.camera ?? [], t).zoom * punchFactor(props.punches, t, fps);
  const tx = transitionState(props.transitions ?? [], t, W, H, theme);
  const gi = lastIndexAtOrBefore(props.graphics, t, (g) => g.start);
  const g = gi >= 0 && t < props.graphics[gi].end + 0.6 ? props.graphics[gi] : null;
  // 도식·사진이 창을 차지하면 화자는 아래 작은 액자로(0.6초에 걸쳐 천천히)
  const gp = g ? Math.min(tween(frame, toFrame(g.start, fps), 18, 'inOutCubic'),
    tweenOut(frame, toFrame(g.end, fps), 14, 'inOutCubic')) : 0;
  const winBox = videoBoxFor(SHORT_WIN, face, zoom, 'center', 0.42);
  const region = lerpRect(SHORT_WIN, SHORT_SMALL, gp);
  const box = lerpBox(winBox, videoBoxFor(SHORT_SMALL, face, 1.08, 'center', 0.42), gp);
  const bi = lastIndexAtOrBefore(props.beats ?? [], t, (b) => b.start);
  const beat = bi >= 0 && t < (props.beats ?? [])[bi].end ? (props.beats ?? [])[bi] : null;

  return (
    <AbsoluteFill style={{background: PAPER.bg}}>
      <PaperBg src={props.paperTexture} />
      <PaperHookTitle text={props.hookTitle} highlight={props.hookHighlight} series={props.seriesLabel} frame={frame}
        W={W} />
      <TransitionStage tx={tx}>
        {/* 창(화자) — 그래픽이 오면 화자 액자가 작아지며 아래로 */}
        <TornFrame b={region} seed={11} />
        <TalkingHead clips={props.clips} fps={fps} region={region} box={box} />
        {props.graphics.map((gr) => {
          const from = toFrame(gr.start, fps);
          const dur = Math.max(1, toFrame(gr.end, fps) - from);
          return (
            <Sequence key={gr.id} from={from} durationInFrames={dur} name={`${gr.template} ${gr.id}`}>
              <WindowGraphic g={gr} dur={dur} props={props} theme={theme} />
            </Sequence>
          );
        })}
      </TransitionStage>
      {g && gp > 0.02 ? (
        <div style={{position: 'absolute', left: 64, top: 1400, width: 520, opacity: gp}}>
          <LabelTag text={(media(g) ? g.data.title : '') || `( ${TEMPLATE_LABEL[g.template]} )`} variant="black"
            size={32} />
        </div>
      ) : null}
      {beat && gp < 0.05 ? <BeatText b={beat} t={t} fps={fps} W={W} /> : null}
      {tx.hideCaptions ? null : (
        <ShortCaptions cues={props.captions} t={t} fps={fps} theme={theme} preset="paper" y={CAPTION_Y} width={W} />
      )}
      <div style={{position: 'absolute', left: 0, width: W, top: 1680, textAlign: 'center', fontFamily: FONT.sans,
        fontWeight: 600, fontSize: 24, letterSpacing: '0.08em', color: 'rgba(244,244,245,0.55)'}}>
        {props.brand.name}
      </div>
      {props.progressBar ? (
        <div style={{position: 'absolute', left: 0, top: 0, height: 6, width: (W * frame) / Math.max(1, durationInFrames),
          background: PAPER.accent, opacity: 0.9}} />
      ) : null}
      <LivePeek every={props.peekEvery} />
    </AbsoluteFill>
  );
};
