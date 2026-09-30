import React, {useMemo} from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {GraphicLayer, SPLIT_SPEAKER} from '../components/graphics';
import {CaptionScrim, LongCaptions} from '../components/captions/LongCaptions';
import {CalloutLayer} from '../components/captions/Callout';
import {Grain, Vignette} from '../components/fx/Grain';
import {LivePeek} from '../components/fx/LivePeek';
import {PaperEndCard} from '../components/layout/EndCard';
import {PAPER, PaperBg, RoughBorder, SourceCredit, TornFrame} from '../components/paper/Paper';
import {paperSpeakerBox} from '../components/paper/PaperGraphic';
import {TransitionStage, transitionState} from '../components/fx/Transitions';
import {lerpBox, lerpRect, TalkingHead, videoBoxFor} from '../components/TalkingHead';
import type {Rect} from '../components/TalkingHead';
import {ensureFonts, useFontForText, useFontGuard} from '../design/fonts';
import {CAMERA, EASE} from '../design/motion';
import {FONT, makeTheme} from '../design/tokens';
import {enter, exit} from '../lib/anim';
import {lastIndexAtOrBefore, sampleFace, sampleKeyframes, toFrame} from '../lib/time';
import type {CameraShot, Graphic, Look, LongFormProps, Punch} from '../lib/types';

ensureFonts();

type RegionSpan = {start: number; end: number; kind: 'split' | 'pip' | 'title'; look: Look};

/**
 * 화자 영역이 바뀌는 구간(split 패널 · 타이틀, pipOverlay=false 일 때만 pip). 거의 붙어 있는 같은 종류는 하나로 합쳐
 * 들락날락하지 않게. 기본(pipOverlay=true)은 pip 에서도 화자가 화면 전체에 그대로 남는다.
 */
export const buildRegionSpans = (graphics: Graphic[], pipOverlay = true, fallback: Look = 'classic'): RegionSpan[] => {
  const spans: RegionSpan[] = [];
  const sorted = [...graphics].sort((a, b) => a.start - b.start);
  for (const g of sorted) {
    // pip 는 화자를 그대로 두고 사진 액자만 띄운다(사용자 레퍼런스 3) — 예전엔 화자가 구석 작은 창으로 줄었다
    const kind = g.template === 'title' ? 'title' : g.layout === 'split' ? 'split'
      : g.layout === 'pip' && !pipOverlay ? 'pip' : null;
    if (!kind) continue;
    const look = g.skin ?? fallback;
    const last = spans[spans.length - 1];
    if (last && last.kind === kind && last.look === look && g.start - last.end < 1.0) {
      last.end = Math.max(last.end, g.end);
    } else {
      spans.push({start: g.start, end: g.end, kind, look});
    }
  }
  return spans;
};

export const cameraAt = (shots: CameraShot[], t: number): {zoom: number; x: number; framed: number} => {
  const i = lastIndexAtOrBefore(shots, t, (s) => s.start);
  if (i < 0) return {zoom: 1, x: 0, framed: 0};
  const s = shots[i];
  const fr = s.framed ? 1 : 0;
  if (t > s.end) return {zoom: s.zoomEnd, x: s.x ?? 0, framed: fr};
  const f = s.end > s.start ? (t - s.start) / (s.end - s.start) : 0;
  // 샷 안의 느린 푸시인은 가감속(inOut)으로 — 선형이면 시작/끝에서 '툭' 걸린다
  const cur = {zoom: s.zoom + (s.zoomEnd - s.zoom) * EASE.inOutCubic(f), x: s.x ?? 0, framed: fr};
  const g = s.glide ?? 0;
  if (g > 0 && i > 0 && t < s.start + g) {
    // 컷 대신 앞 샷의 마지막 프레이밍에서 천천히 옮겨 온다(교육 영상용 젠틀 리프레이밍)
    const p = shots[i - 1];
    const k = EASE.inOutCubic(Math.max(0, (t - s.start) / g));
    const pf = p.framed ? 1 : 0;
    return {zoom: p.zoomEnd + (cur.zoom - p.zoomEnd) * k, x: (p.x ?? 0) + (cur.x - (p.x ?? 0)) * k,
      framed: pf + (fr - pf) * k};
  }
  return cur;
};

export const cameraZoom = (shots: CameraShot[], t: number): number => cameraAt(shots, t).zoom;

/**
 * 강조 줌: 강조 순간 카메라를 살짝 당긴다.
 *  glide — 0.7초에 걸쳐 천천히 당기고 0.9초에 걸쳐 풀림. 편집 문법 엔진(롱폼·숏폼)이 쓰는 스타일
 *  ease  — 5프레임 동안 빠르게 당기고 끝에서 8프레임에 걸쳐 풀림(렌더러에만 남음)
 *  cut   — 한 프레임에 확, 문장 끝에서 하드컷으로 복귀(렌더러에만 남음)
 */
export const punchFactor = (punches: Punch[], t: number, fps = 30): number => {
  let f = 1;
  for (const p of punches) {
    if (t < p.t || t >= p.end) continue;
    let k = 1;
    if (p.style === 'glide') {
      // 교육 영상용: 0.7초에 걸쳐 천천히 당기고 0.9초에 걸쳐 풀린다(튀지 않게)
      const inP = Math.min(1, (t - p.t) / 0.7);
      const outP = Math.min(1, (p.end - t) / 0.9);
      k = Math.min(EASE.inOutCubic(inP), EASE.inOutCubic(outP));
    } else if (p.style === 'ease') {
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
  chapterTag: string;
  faceX: number;
}> = ({g, dur, props, theme, pageLabel, chapterTag, faceX}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  return (
    <GraphicLayer g={g} frame={frame} dur={dur} fps={fps} theme={theme} brand={props.brand} episode={props.episode}
      W={width} H={height} panelSide={props.panelSide} pageLabel={pageLabel} skin={props.skin}
      paperTexture={props.paperTexture} chapterTag={chapterTag} faceX={faceX} />
  );
};

export const LongForm: React.FC<LongFormProps> = (props) => {
  useFontGuard();
  // 두 층 강조 자막의 앞말(명조)에 쓰일 글자를 렌더 전에 받아 둔다
  useFontForText('700 40px "Noto Serif KR"', useMemo(() => Array.from(new Set(props.captions
    .filter((c) => c.style === 'stack' || c.style === 'impact').flatMap((c) => c.lines.flat().map((w) => w.text))
    .join('').split(''))).join('') || '가', [props.captions]));
  const frame = useCurrentFrame();
  const {fps, width: W, height: H} = useVideoConfig();
  const t = frame / fps;
  const theme = useMemo(() => makeTheme(props.brand), [props.brand]);
  // 하이브리드: 그래픽·챕터마다 모양(look)이 정해져 온다. 없으면 props.skin 하나로
  const fallback: Look = props.skin === 'paper' ? 'paper' : 'classic';
  const lookOf = (g: Graphic): Look => g.skin ?? fallback;
  const spans = useMemo(() => buildRegionSpans(props.graphics, true, fallback), [props.graphics, fallback]);
  const isUnder = (g: Graphic) => lookOf(g) !== 'paper' && g.template === 'title';
  const under = useMemo(() => props.graphics.filter(isUnder), [props.graphics, fallback]);
  const over = useMemo(() => props.graphics.filter((g) => !isUnder(g)), [props.graphics, fallback]);

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
  // 화자를 찢어진 액자에 담는 정도(0~1) — 타이틀 구간(두 스킨), 종이 스킨은 split 패널 구간·액자 샷도(레퍼런스 1·2)
  let paperP = 0;
  let paperBorder = 0;
  let paperFill = false; // 화자 액자 뒤를 구겨진 종이로 채울지(종이 모양 구간·액자 샷)
  if (cam.framed > 0 && props.skin !== 'classic') {   // 액자 샷은 종이 챕터에서만 만들어진다
    const target = PAPER.framed;
    region = lerpRect(full, target, cam.framed);
    box = lerpBox(box, videoBoxFor(target, face, zoom, 'anchor'), cam.framed);
    paperP = cam.framed;
    paperFill = true;
  }
  const si = lastIndexAtOrBefore(spans, t, (s) => s.start);
  const span = si >= 0 && t < spans[si].end + 0.5 ? spans[si] : null;
  if (span) {
    // 종이 스킨은 천천히(0.7초) 액자로 들어가고 0.5초에 걸쳐 돌아온다
    const paperSpan = span.look === 'paper';
    const p = paperSpan
      ? Math.min(enter(frame, toFrame(span.start, fps), 21, EASE.inOutCubic), exit(frame, toFrame(span.end, fps), 15))
      : Math.min(enter(frame, toFrame(span.start, fps), 16), exit(frame, toFrame(span.end, fps), 12));
    // 타이틀은 두 스킨 모두 '글 왼쪽 + 화자 액자 오른쪽'(레퍼런스 1) — 예전엔 가운데 작은 화자 창이 제목 글자를 가렸다
    if (p > 0 && (span.kind === 'title' || (paperSpan && span.kind === 'split'))) {
      const target = paperSpeakerBox(props.panelSide, W);
      const tBox = videoBoxFor(target, face, 1.02 * punchFactor(props.punches, t, fps), 'center', 0.42);
      region = lerpRect(region, target, p);
      box = lerpBox(box, tBox, p);
      paperP = Math.max(paperP, p);
      paperBorder = paperSpan ? p : 0;
      paperFill = paperSpan;
    } else if (p > 0) {
      let target: Rect;
      let tBox;
      if (span.kind === 'split') {
        const cw = W * SPLIT_SPEAKER;
        target = props.panelSide === 'right' ? {x: 0, y: 0, w: cw, h: H} : {x: W - cw, y: 0, w: cw, h: H};
        tBox = videoBoxFor(target, face, 1.04 * punchFactor(props.punches, t, fps), 'center', 0.4);
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
  const chapterLook: Look = chapter?.look ?? fallback;
  const pageFor = (g: Graphic) => {
    const k = lastIndexAtOrBefore(props.chapters, g.start, (c) => c.start);
    return k >= 0 ? `ch ${props.chapters[k].number}` : '';
  };
  const fullscreenActive = props.graphics.some((g) => g.layout === 'fullscreen' && t >= g.start && t < g.end);
  // 화면에 글자 그래픽이 떠 있으면 자막 강조는 끈다(강조색은 화면당 한 곳)
  const textGraphicActive = props.graphics.some((g) => t >= g.start && t < g.end
    && !['lower_third', 'broll', 'photo', 'title'].includes(g.template));

  const tagFor = (g: Graphic) => {
    const k = lastIndexAtOrBefore(props.chapters, g.start + 0.05, (c) => c.start);
    if (k < 0) return '';
    const c = props.chapters[k];
    const n = parseInt(c.number, 10);
    return Number.isFinite(n) ? `${n}. ${c.title}` : c.title;
  };
  const seq = (g: Graphic) => {
    const from = toFrame(g.start, fps);
    const dur = Math.max(1, toFrame(g.end, fps) - from);
    return (
      <Sequence key={g.id} from={from} durationInFrames={dur} name={`${g.template} ${g.id}`}>
        <GraphicSeq g={g} dur={dur} props={props} theme={theme} pageLabel={pageFor(g)} chapterTag={tagFor(g)}
          faceX={sampleFace(props.face, g.start + 0.3).x} />
      </Sequence>
    );
  };

  const endStart = props.endcard ? toFrame(props.endcard.start, fps) : Infinity;
  const tx = transitionState(props.transitions ?? [], t, W, H, theme);

  return (
    <AbsoluteFill style={{background: theme.ink}}>
      <TransitionStage tx={tx}>
        {under.map(seq)}
        {paperP > 0 && frame < endStart ? (
          <>
            {paperFill ? <PaperBg src={props.paperTexture} opacity={Math.min(1, paperP * 1.6)} /> : null}
            {paperBorder > 0 ? <RoughBorder opacity={paperBorder} /> : null}
            <TornFrame b={region} opacity={Math.min(1, paperP * 2)} seed={7} />
            {cam.framed > 0.5 && chapter && !span ? (
              <SourceCredit text={`( ${chapter.number} ) ${chapter.title}`} raw opacity={cam.framed} />
            ) : null}
          </>
        ) : null}
        {frame < endStart ? (
          <TalkingHead clips={props.clips} fps={fps} region={region} box={box} radius={radius} border={border}
            shadow={radius > 0} />
        ) : null}
        {region === full ? <Vignette strength={0.22} /> : null}
        {chapterLook === 'paper' && props.showChapterLabel && chapter && paperP === 0 && !span
          && !props.graphics.some((g) => t >= g.start - 0.3 && t < g.end + 0.3) ? (
          <SourceCredit text={`( ${chapter.number} ) ${chapter.title}`} raw
            opacity={enter(frame, toFrame(chapter.start + 3.2, fps), 14) * 0.9} />
        ) : null}
        {chapterLook !== 'paper' && props.showChapterLabel && chapter && !fullscreenActive && !span
          && !props.graphics.some((g) => t >= g.start - 0.3 && t < g.end + 0.3 && g.layout !== 'split') ? (
          <div style={{position: 'absolute', left: 72, top: 56, fontFamily: FONT.sans, fontSize: 21, fontWeight: 600,
            color: 'rgba(255,255,255,0.88)', textShadow: '0 1px 8px rgba(0,0,0,0.55)', letterSpacing: '0.01em',
            opacity: enter(frame, toFrame(chapter.start + 3.2, fps), 14) * 0.9}}>
            ( {chapter.number} ) {chapter.title}
          </div>
        ) : null}
        {over.map(seq)}
        <CalloutLayer items={props.callouts ?? []} t={t} fps={fps} W={W} H={H} theme={theme} paper
          face={face} zoom={zoom} />
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
      <LivePeek every={props.peekEvery} />

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
  // 두 스킨 모두 '오늘의 정리 + 다음 영상 자리'(예전 엔드카드는 빈 칸 두 개뿐이라 비어 보였다)
  return <PaperEndCard frame={frame} brand={props.brand} episode={props.episode} chapters={props.chapters}
    texture={props.skin !== 'classic' ? props.paperTexture : undefined} plain={props.skin === 'classic'}
    bg={props.skin === 'classic' ? theme.ink : undefined} W={width} H={height} />;
};
