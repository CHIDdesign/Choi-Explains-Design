import React, {useMemo} from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {ShortCaptions} from '../components/Captions';
import {Grain} from '../components/fx/Grain';
import {TEMPLATE_COMPONENTS} from '../components/graphics';
import {HookTitle} from '../components/shorts/HookTitle';
import {lerpBox, lerpRect, TalkingHead, videoBoxFor} from '../components/TalkingHead';
import type {Rect} from '../components/TalkingHead';
import {ensureFonts} from '../design/fonts';
import {surface as mkSurface} from '../design/surfaces';
import {makeTheme} from '../design/tokens';
import {enter, exit} from '../lib/anim';
import {lastIndexAtOrBefore, sampleFace, sampleKeyframes, toFrame} from '../lib/time';
import type {Graphic, ShortProps} from '../lib/types';
import {punchFactor} from './LongForm';

ensureFonts();

// 1080×1920 세이프존(메타/틱톡 통합 보수값): x 65–940, y 270–1248
const PANEL_L3: Rect = {x: 0, y: 590, w: 1080, h: 450}; // 상단 도식 패널(L3)
const FACE_L3: Rect = {x: 0, y: 1040, w: 1080, h: 880};
const FRAMED: Rect = {x: 0, y: 600, w: 1080, h: 608}; // L2: 가운데 16:9 (y 600–1208)

const PanelGraphic: React.FC<{g: Graphic; dur: number; theme: ReturnType<typeof makeTheme>; props: ShortProps}> = ({
  g,
  dur,
  theme,
  props,
}) => {
  // 풀프레임(L3): 훅 타이틀과 얼굴 사이 패널 / 3단(L2): 가운데 16:9 프레임을 도식이 대신 채움
  const PANEL = props.layout === 'framed' ? FRAMED : PANEL_L3;
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const Comp = TEMPLATE_COMPONENTS[g.template];
  if (!Comp) return null;
  const s = mkSurface(theme, g.template === 'photo' ? 'photo' : 'board');
  const pIn = enter(frame, 0, 10);
  const pOut = exit(frame, dur, 8);
  const pad = 60;
  return (
    <div style={{position: 'absolute', left: PANEL.x, top: PANEL.y, width: PANEL.w, height: PANEL.h,
      background: s.bg, clipPath: `inset(0 0 ${(1 - pIn) * 100}% 0)`, opacity: pOut,
      boxShadow: 'inset 0 0 80px rgba(0,0,0,0.4)'}}>
      <div style={{position: 'absolute', left: pad, top: 28, right: pad, height: PANEL.h - 56}}>
        <Comp id={g.id} data={g.data} frame={frame} dur={dur} fps={fps} theme={theme} surface={s}
          box={{w: PANEL.w - pad * 2, h: PANEL.h - 56}} layout="split" brand={props.brand} episode={props.episode}
          compact />
      </div>
    </div>
  );
};

export const Short: React.FC<ShortProps> = (props) => {
  const frame = useCurrentFrame();
  const {fps, width: W, height: H, durationInFrames} = useVideoConfig();
  const t = frame / fps;
  const theme = useMemo(() => makeTheme(props.brand), [props.brand]);
  const face = sampleFace(props.face, t);
  const punch = punchFactor(props.punches, t);

  const gi = lastIndexAtOrBefore(props.graphics, t, (g) => g.start);
  const g = gi >= 0 && t < props.graphics[gi].end ? props.graphics[gi] : null;

  let region: Rect;
  let box;
  if (props.layout === 'framed') {
    region = FRAMED;
    box = videoBoxFor(FRAMED, face, punch, 'anchor');
  } else {
    const full: Rect = {x: 0, y: 0, w: W, h: H};
    region = full;
    box = videoBoxFor(full, face, punch, 'center', 0.46);
    if (g) {
      const p = Math.min(enter(frame, toFrame(g.start, fps), 10), exit(frame, toFrame(g.end, fps), 8));
      region = lerpRect(full, FACE_L3, p);
      box = lerpBox(box, videoBoxFor(FACE_L3, face, punch, 'center', 0.42), p);
    }
  }

  return (
    <AbsoluteFill style={{background: theme.ink}}>
      {props.layout === 'framed' ? (
        <AbsoluteFill style={{background: `radial-gradient(90% 60% at 50% 50%, #1d1d1d 0%, ${theme.ink} 100%)`}} />
      ) : null}
      <TalkingHead clips={props.clips} fps={fps} region={region} box={box} />
      {props.layout === 'full' ? (
        <AbsoluteFill style={{background:
          'linear-gradient(180deg, rgba(0,0,0,0.62) 0%, rgba(0,0,0,0.25) 26%, rgba(0,0,0,0) 38%, rgba(0,0,0,0) 55%, rgba(0,0,0,0.35) 72%, rgba(0,0,0,0.0) 100%)'}} />
      ) : null}
      {props.graphics.map((gr) => {
        const from = toFrame(gr.start, fps);
        const dur = Math.max(1, toFrame(gr.end, fps) - from);
        return (
          <Sequence key={gr.id} from={from} durationInFrames={dur} name={`${gr.template} ${gr.id}`}>
            <PanelGraphic g={gr} dur={dur} theme={theme} props={props} />
          </Sequence>
        );
      })}
      <HookTitle text={props.hookTitle} highlight={props.hookHighlight} series={props.seriesLabel} frame={frame}
        theme={theme} width={W} />
      <ShortCaptions cues={props.captions} t={t} fps={fps} theme={theme} y={g && props.layout === 'full' ? 1090 : 1110}
        width={W} />
      {props.progressBar ? (
        <div style={{position: 'absolute', left: 0, top: 0, height: 6, width: (W * frame) / Math.max(1, durationInFrames),
          background: theme.accent, opacity: 0.8}} />
      ) : null}
      <Grain frame={frame} frames={props.grainFrames} opacity={props.grain} />
      {props.voice ? <Audio src={staticFile(props.voice.src)} volume={props.voice.volume} /> : null}
      {props.bgm ? (
        <Audio src={staticFile(props.bgm.src)} loop={props.bgm.loop}
          volume={(f) => sampleKeyframes(props.bgm!.envelope, f / fps, 0.08)} />
      ) : null}
      {props.sfx.map((s, i) => (
        <Sequence key={`sfx${i}`} from={toFrame(s.t, fps)} durationInFrames={fps * 2} name="sfx">
          <Audio src={staticFile(s.src)} volume={s.volume} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
