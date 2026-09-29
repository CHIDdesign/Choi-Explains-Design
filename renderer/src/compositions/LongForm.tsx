import React, {useMemo} from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {GraphicLayer, SPLIT_SPEAKER} from '../components/graphics';
import {CaptionScrim, LongCaptions} from '../components/captions/LongCaptions';
import {CalloutLayer} from '../components/captions/Callout';
import {Grain, Vignette} from '../components/fx/Grain';
import {EndCard} from '../components/layout/EndCard';
import {TransitionStage, transitionState} from '../components/fx/Transitions';
import {lerpBox, lerpRect, TalkingHead, videoBoxFor} from '../components/TalkingHead';
import type {Rect} from '../components/TalkingHead';
import {ensureFonts} from '../design/fonts';
import {CAMERA, EASE} from '../design/motion';
import {FONT, makeTheme} from '../design/tokens';
import {enter, exit} from '../lib/anim';
import {lastIndexAtOrBefore, sampleFace, sampleKeyframes, toFrame} from '../lib/time';
import type {CameraShot, Graphic, LongFormProps, Punch} from '../lib/types';

ensureFonts();

type RegionSpan = {start: number; end: number; kind: 'split' | 'pip' | 'title'};

/** 화자 영역이 바뀌는 구간(칠판 패널/PiP/타이틀). 거의 붙어 있는 같은 종류는 하나로 합쳐 들락날락하지 않게. */
export const buildRegionSpans = (graphics: Graphic[]): RegionSpan[] => {
  const spans: RegionSpan[] = [];
  const sorted = [...graphics].sort((a, b) => a.start - b.start);
  for (const g of sorted) {
    const kind = g.template === 'title' ? 'title' : g.layout === 'split' ? 'split' : g.layout === 'pip' ? 'pip' : null;
    if (!kind) continue;
    const last = spans[spans.length - 1];
    if (last && last.kind === kind && g.start - last.end < 1.0) {
      last.end = Math.max(last.end, g.end);
    } else {
      spans.push({start: g.start, end: g.end, kind});
    }
  }
  return spans;
};

export const cameraAt = (shots: CameraShot[], t: number): {zoom: number; x: number} => {
  const i = lastIndexAtOrBefore(shots, t, (s) => s.start);
  if (i < 0) return {zoom: 1, x: 0};
  const s = shots[i];
  if (t > s.end) return {zoom: s.zoomEnd, x: s.x ?? 0};
  const f = s.end > s.start ? (t - s.start) / (s.end - s.start) : 0;
  // 샷 안의 느린 푸시인은 가감속(inOut)으로 — 선형이면 시작/끝에서 '툭' 걸린다
  return {zoom: s.zoom + (s.zoomEnd - s.zoom) * EASE.inOutCubic(f), x: s.x ?? 0};
};

export const cameraZoom = (shots: CameraShot[], t: number): number => cameraAt(shots, t).zoom;

/**
 * 펀치인: 강조 순간 카메라를 한 단계 당긴다.
 *  cut  — 한 프레임에 확(2캠 편집 느낌, 문장 끝에서 하드컷으로 복귀)
 *  ease — 5프레임 동안 빠르게 당기고 끝에서 8프레임에 걸쳐 풀림(웃음·여운)
 */
export const punchFactor = (punches: Punch[], t: number, fps = 30): number => {
  let f = 1;
  for (const p of punches) {
    if (t < p.t || t >= p.end) continue;
    let k = 1;
    if (p.style === 'ease') {
      const inP = Math.min(1, ((t - p.t) * fps) / CAMERA.punchIn);
      const outP = Math.min(1, ((p.end - t) * fps) / CAMERA.punchOut);
      k = Math.min(EASE.outCubic(inP), EASE.inOutCubic(outP));
    }
    f = Math.max(f, 1 + p.amount * k);
  }
  return f;
};

const GraphicSeq: React.FC<{
  g: Graphic;
  dur: number;
  props: LongFormProps;
  theme: ReturnType<typeof makeTheme>;
  pageLabel: string;
}> = ({g, dur, props, theme, pageLabel}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  return (
    <GraphicLayer g={g} frame={frame} dur={dur} fps={fps} theme={theme} brand={props.brand} episode={props.episode}
      W={width} H={height} panelSide={props.panelSide} pageLabel={pageLabel} />
  );
};

export const LongForm: React.FC<LongFormProps> = (props) => {
  const frame = useCurrentFrame();
  const {fps, width: W, height: H} = useVideoConfig();
  const t = frame / fps;
  const theme = useMemo(() => makeTheme(props.brand), [props.brand]);
  const spans = useMemo(() => buildRegionSpans(props.graphics), [props.graphics]);
  const under = useMemo(() => props.graphics.filter((g) => g.template === 'title' || g.layout === 'pip'), [props.graphics]);
  const over = useMemo(() => props.graphics.filter((g) => !(g.template === 'title' || g.layout === 'pip')), [props.graphics]);

  // ---- 카메라 ----
  const face = sampleFace(props.face, t);
  const cam = cameraAt(props.camera, t);
  const zoom = cam.zoom * punchFactor(props.punches, t, fps);
  const full: Rect = {x: 0, y: 0, w: W, h: H};
  let region = full;
  let box = videoBoxFor(full, face, zoom, 'anchor');
  if (cam.x) {
    // 타이트 샷은 얼굴을 x(화면 폭 비율)만큼 옆으로 — 3분할 구도. 확대 여유 안에서만(화면은 항상 덮음)
    box = {...box, tx: Math.min(0, Math.max(W - box.w, box.tx + cam.x * W))};
  }
  let radius = 0;
  let border: string | undefined;
  let capCenter = W / 2;
  const si = lastIndexAtOrBefore(spans, t, (s) => s.start);
  const span = si >= 0 && t < spans[si].end + 0.5 ? spans[si] : null;
  if (span) {
    const p = Math.min(enter(frame, toFrame(span.start, fps), 16), exit(frame, toFrame(span.end, fps), 12));
    if (p > 0) {
      let target: Rect;
      let tBox;
      if (span.kind === 'split') {
        const cw = W * SPLIT_SPEAKER;
        target = props.panelSide === 'right' ? {x: 0, y: 0, w: cw, h: H} : {x: W - cw, y: 0, w: cw, h: H};
        tBox = videoBoxFor(target, face, 1.04 * punchFactor(props.punches, t), 'center', 0.4);
        const panelCenter = props.panelSide === 'right' ? cw + (W - cw) / 2 : (W - cw) / 2;
        capCenter = W / 2 + (panelCenter - W / 2) * p;
      } else if (span.kind === 'pip') {
        target = {x: W - 96 - 520, y: H - 96 - 292 - 70, w: 520, h: 292};
        tBox = videoBoxFor(target, face, 1.0, 'anchor');
        radius = 10 * p;
        border = `2px solid rgba(255,255,255,${0.85 * p})`;
      } else {
        target = {x: W / 2 - 250, y: H / 2 - 141, w: 500, h: 281};
        tBox = videoBoxFor(target, face, 1.0, 'anchor');
      }
      region = lerpRect(full, target, p);
      box = lerpBox(box, tBox, p);
    }
  }

  // ---- 챕터 ----
  const ci = lastIndexAtOrBefore(props.chapters, t, (c) => c.start);
  const chapter = ci >= 0 ? props.chapters[ci] : null;
  const pageFor = (g: Graphic) => {
    const k = lastIndexAtOrBefore(props.chapters, g.start, (c) => c.start);
    return k >= 0 ? `ch ${props.chapters[k].number}` : '';
  };
  const fullscreenActive = props.graphics.some((g) => g.layout === 'fullscreen' && t >= g.start && t < g.end);
  // 화면에 글자 그래픽이 떠 있으면 자막 강조는 끈다(강조색은 화면당 한 곳)
  const textGraphicActive = props.graphics.some((g) => t >= g.start && t < g.end
    && !['lower_third', 'broll', 'photo', 'title'].includes(g.template));

  const seq = (g: Graphic) => {
    const from = toFrame(g.start, fps);
    const dur = Math.max(1, toFrame(g.end, fps) - from);
    return (
      <Sequence key={g.id} from={from} durationInFrames={dur} name={`${g.template} ${g.id}`}>
        <GraphicSeq g={g} dur={dur} props={props} theme={theme} pageLabel={pageFor(g)} />
      </Sequence>
    );
  };

  const endStart = props.endcard ? toFrame(props.endcard.start, fps) : Infinity;
  const tx = transitionState(props.transitions ?? [], t, W, H, theme);

  return (
    <AbsoluteFill style={{background: theme.ink}}>
      <TransitionStage tx={tx}>
        {under.map(seq)}
        {frame < endStart ? (
          <TalkingHead clips={props.clips} fps={fps} region={region} box={box} radius={radius} border={border}
            shadow={radius > 0} />
        ) : null}
        {region === full ? <Vignette strength={0.22} /> : null}
        {props.showChapterLabel && chapter && !fullscreenActive && !span ? (
          <div style={{position: 'absolute', left: 72, top: 56, fontFamily: FONT.sans, fontSize: 21, fontWeight: 600,
            color: 'rgba(255,255,255,0.88)', textShadow: '0 1px 8px rgba(0,0,0,0.55)', letterSpacing: '0.01em',
            opacity: enter(frame, toFrame(chapter.start + 3.2, fps), 14) * 0.9}}>
            ( {chapter.number} ) {chapter.title}
          </div>
        ) : null}
        {over.map(seq)}
        <CalloutLayer items={props.callouts ?? []} t={t} fps={fps} W={W} H={H} theme={theme} />
      </TransitionStage>
      {props.captionPreset === 'editorial' || props.captionPreset === 'documentary' ? <CaptionScrim /> : null}
      {tx.hideCaptions ? null : (
        <LongCaptions cues={props.captions} t={t} fps={fps} theme={theme} preset={props.captionPreset}
          centerX={capCenter} frameW={W} plain={textGraphicActive} />
      )}
      {props.endcard ? (
        <Sequence from={endStart} durationInFrames={Math.max(1, toFrame(props.endcard.dur, fps))} name="endcard">
          <EndCardSeq theme={theme} props={props} />
        </Sequence>
      ) : null}
      <Grain frame={frame} frames={props.grainFrames} opacity={props.grain} />

      {props.voice ? <Audio src={staticFile(props.voice.src)} volume={props.voice.volume} /> : null}
      {props.bgm ? (
        <Audio src={staticFile(props.bgm.src)} loop={props.bgm.loop}
          volume={(f) => sampleKeyframes(props.bgm!.envelope, f / fps, 0.1)} />
      ) : null}
      {props.sfx.map((s, i) => (
        <Sequence key={`sfx${i}`} from={toFrame(s.t, fps)} durationInFrames={fps * 2} name="sfx">
          <Audio src={staticFile(s.src)} volume={s.volume} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

const EndCardSeq: React.FC<{theme: ReturnType<typeof makeTheme>; props: LongFormProps}> = ({theme, props}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  return <EndCard frame={frame} theme={theme} brand={props.brand} episode={props.episode} W={width} H={height} />;
};
