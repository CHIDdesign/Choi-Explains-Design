import React, {useMemo} from 'react';
import {CornerCredit, CreditOn, ModernStage, PaperGround} from '../components/modern/Modern';
import {ModernEndCard} from '../components/modern/Titles';
import {AbsoluteFill, Audio, interpolate, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {GraphicLayer, isSplit} from '../components/graphics';
import {focusPoint} from '../components/longform/Evidence';
import {LongCaptions} from '../components/captions/LongCaptions';
import {CalloutLayer} from '../components/captions/Callout';
import {LivePeek} from '../components/fx/LivePeek';
import {PaperEndCard} from '../components/layout/EndCard';
import {PieceExpand} from '../components/material/Sheet';
import {hashSeed, PAPER, PaperBg, RoughBorder, SourceCredit, TornFrame} from '../components/paper/Paper';
import {paperSpeakerBox} from '../components/paper/PaperGraphic';
import {speakerCard} from '../components/longform/Stage';
import {PUSH_SEC, PushSlide, TransitionStage, transitionState} from '../components/fx/Transitions';
import {lerpBox, lerpRect, TalkingHead, videoBoxFor} from '../components/TalkingHead';
import type {Rect} from '../components/TalkingHead';
import {ensureFonts, useFontGuard} from '../design/fonts';
import {EASE} from '../design/motion';
import {makeTheme, MODERN} from '../design/tokens';
import type {TexName} from '../components/material/Texture';
import {enter, exit} from '../lib/anim';
import {EXPAND_SEC, expandCredit, expandPairs, expandRect} from '../lib/crop';
import {paperSwaps, pushPairs} from '../lib/fullPairs';
import {lastIndexAtOrBefore, sampleFace, sampleKeyframes, toFrame} from '../lib/time';
import type {CameraShot, Graphic, Look, LongFormProps, Punch} from '../lib/types';

ensureFonts();

type RegionSpan = {start: number; end: number; kind: 'split' | 'title'; look: Look};

/** 화자 영역이 바뀌는 구간(분할 칸 · 종이 스킨 타이틀). 거의 붙어 있는 같은 종류는 하나로 합쳐 들락날락하지 않게. */
export const buildRegionSpans = (graphics: Graphic[], fallback: Look = 'classic'): RegionSpan[] => {
  const spans: RegionSpan[] = [];
  const sorted = [...graphics].sort((a, b) => a.start - b.start);
  for (const g of sorted) {
    const look = g.skin ?? fallback;
    const kind = g.template === 'title' && look === 'paper' ? 'title' : isSplit(g) ? 'split' : null;
    if (!kind) continue;
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
    // 컷 대신 앞 샷의 마지막 프레이밍에서 천천히 옮겨 온다 — 화자 젠틀 줌(push_in·pull_out, 되튐 없음)
    const p = shots[i - 1];
    const k = EASE.inOutCubic(Math.max(0, (t - s.start) / g));
    const pf = p.framed ? 1 : 0;
    return {zoom: p.zoomEnd + (cur.zoom - p.zoomEnd) * k, x: (p.x ?? 0) + (cur.x - (p.x ?? 0)) * k,
      framed: pf + (fr - pf) * k};
  }
  return cur;
};

export const cameraZoom = (shots: CameraShot[], t: number): number => cameraAt(shots, t).zoom;

/** 강조 크롭: style glide(편집 층이 보낼 때만)는 from 부터 in 초에 걸쳐 당기고 end 앞 out 초에 푼다. 그 밖에는 t~end 동안 점프(하드 컷). */
const sineInOut = (x: number) => 0.5 - 0.5 * Math.cos(Math.PI * Math.min(1, Math.max(0, x)));
export const punchFactor = (punches: Punch[], t: number): number => {
  let f = 1;
  for (const p of punches) {
    if (p.style !== 'glide') {
      if (t >= p.t && t < p.end) f = Math.max(f, 1 + p.amount);
      continue;
    }
    const a = p.from ?? p.t;
    if (t < a || t >= p.end) continue;
    const len = Math.max(0.1, p.end - a);
    let inD = p.in ?? 2.6;
    let outD = p.out ?? 3.0;
    if (inD + outD > len) {
      const r = len / (inD + outD);
      inD *= r;
      outD *= r;
    }
    f = Math.max(f, 1 + p.amount * Math.min(sineInOut((t - a) / inD), sineInOut((p.end - t) / outD)));
  }
  return f;
};

const SEQ_SKIP = 16; // 시퀀스 둘째 샷부터 건너뛸 등장 프레임(등장 14~16f 가 끝난 상태로 컷)
const COVER_PAD = 0.1; // 전면 그래픽 앞뒤로 화자 영상을 그리는 여유(초) — 하드 컷이라 짧다
// 전면 그래픽끼리 이 간격(초) 이하로 이어지면 한 덮개로 본다: 사이에 화자를 그리지 않고 접합부 아래에는 무대판을 깐다
const ABUT = 0.5;

const onWords = (g: Graphic) => g.template === 'card' || g.template === 'motion' || !!g.data.overlays?.length || !!g.data.stepAt?.length || !!g.data.cutouts?.length || g.data.keyword_at !== undefined;   // 낱말에 맞춘 시각은 GraphicSeq 의 frame 기준이다

/** 바탕 종이 위에 그려지는 전면 도식의 물건 표식(같으면 '같은 물건') — 사진·카드·타이틀은 바탕이 따로 없다 */
const heldObject = (g: Graphic) => {
  const key = g.data.motif || g.data.title;
  return !key || onWords(g) || ['photo', 'broll', 'evidence', 'chapter', 'title'].includes(g.template) ? '' : `${g.template}:${key}`;
};

const isStill = (g: Graphic) => g.layout === 'fullscreen' && (g.template === 'photo' || (g.template === 'broll' && g.data.kind === 'photo')
  || (g.template === 'evidence' && !!g.data.assets?.length && g.data.assets.every((a) => a.kind !== 'video')));

const GraphicSeq: React.FC<{
  g: Graphic;
  dur: number;
  props: LongFormProps;
  theme: ReturnType<typeof makeTheme>;
  chapterTag: string;
  faceX: number;
  freeze?: number; // 뒤 조각이 펼쳐지는 동안 이 프레임에 멈춰 있다
  expand?: boolean;
  before?: Graphic; // 조각이 펼쳐지는 동안 밑에 있는 앞 그래픽
  swap?: {paper: TexName; first: string}; // 같은 물건을 둔 채 바탕 종이만 바꾼다(first = 묶음 첫 장의 id — 시드가 같아야 물건이 그대로다)
  pushOut?: number; // 이 프레임부터 위로 밀려 나간다
  pushIn?: boolean; // 아래에서 밀고 들어온다
}> = ({g, dur, props, theme, chapterTag, faceX, freeze = Infinity, expand = false, before, swap, pushOut, pushIn}) => {
  // 시퀀스의 둘째 샷부터는 등장이 끝난 상태로 시작한다(같은 틀 안의 컷 — 샷마다 등장 애니메이션을 되풀이하지 않는다)
  const d = g.data;
  const skip = g.seq && g.seq.index > 0 && !onWords(g) ? SEQ_SKIP : 0;
  const raw = useCurrentFrame();
  const frame = swap ? dur : Math.min(raw, freeze) + skip;   // 바탕만 바뀌는 컷: 물건은 다 놓인 채 움직이지 않는다
  const {fps, width, height} = useVideoConfig();
  const n = Math.round(EXPAND_SEC * fps);
  const layer = (
    <PaperGround.Provider value={swap?.paper ?? null}>
      <CreditOn.Provider value={(raw <= freeze || pushOut !== undefined) && !(expand && raw < n)}>
        <GraphicLayer g={swap ? {...g, id: swap.first} : g} frame={frame} dur={dur + skip} fps={fps} theme={theme} brand={props.brand} episode={props.episode}
          W={width} H={height} panelSide={props.panelSide} skin={props.skin}
          paperTexture={props.paperTexture} chapterTag={chapterTag} faceX={faceX} />
      </CreditOn.Provider>
    </PaperGround.Provider>
  );
  if (pushOut !== undefined || pushIn) return <PushSlide frame={pushIn ? raw : raw - pushOut!} fps={fps} H={height} leaving={!pushIn}>{layer}</PushSlide>;
  if (!expand) return layer;
  const at: [number, number] = focusPoint(d, width, height) ?? (d.focus ? [d.focus[0] * width, d.focus[1] * height] : [width * 0.58, height * 0.42]);
  const r = expandRect(interpolate(raw, [0, n], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: EASE.expand}), width, height, at);
  const share = (r.w * r.h) / (width * height);
  const creditOf = (x?: Graphic) => x?.data.credit || x?.data.assets?.[0]?.credit || '';
  return (
    <>
      <PieceExpand frame={raw} fps={fps} W={width} H={height} at={at} seed={hashSeed(g.id)}>{layer}</PieceExpand>
      {raw < n ? <CornerCredit text={expandCredit(share, creditOf(before), creditOf(g))} /> : null}
    </>
  );
};

export const LongForm: React.FC<LongFormProps> = (props) => {
  useFontGuard();
  const frame = useCurrentFrame();
  const {fps, width: W, height: H} = useVideoConfig();
  const t = frame / fps;
  const theme = useMemo(() => makeTheme(props.brand), [props.brand]);
  // 하이브리드: 그래픽·챕터마다 모양(look)이 정해져 온다. 없으면 props.skin 하나로
  const fallback: Look = props.skin === 'paper' ? 'paper' : 'classic';
  const lookOf = (g: Graphic): Look => g.skin ?? fallback;
  const spans = useMemo(() => buildRegionSpans(props.graphics, fallback), [props.graphics, fallback]);
  // 시작 순서로 그린다(나중 그래픽이 위)
  const over = useMemo(() => [...props.graphics].sort((a, b) => a.start - b.start), [props.graphics]);

  // ---- 카메라 ----
  const face = sampleFace(props.face, t);
  const cam = cameraAt(props.camera, t);
  const punch = punchFactor(props.punches, t);
  const zoom = cam.zoom * punch;
  const full: Rect = {x: 0, y: 0, w: W, h: H};
  let region = full;
  let box = videoBoxFor(full, face, zoom, 'anchor');
  if (cam.x) {
    // 타이트 샷은 얼굴을 x(화면 폭 비율)만큼 옆으로 — 3분할 구도. 확대 여유 안에서만(화면은 항상 덮음)
    box = {...box, tx: Math.min(0, Math.max(W - box.w, box.tx + cam.x * W))};
  }
  // 화자를 찢어진 액자에 담는 정도(0~1) — 종이 스킨(시험용)만
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
  const span = si >= 0 && t < spans[si].end + (spans[si].look === 'paper' ? 0.5 : 0) ? spans[si] : null;
  if (span?.look === 'paper') {
    const p = Math.min(enter(frame, toFrame(span.start, fps), 21, EASE.inOutCubic), exit(frame, toFrame(span.end, fps), 15));
    if (p > 0) {
      const target = paperSpeakerBox(props.panelSide, W);
      region = lerpRect(region, target, p);
      box = lerpBox(box, videoBoxFor(target, face, 1.02 * punch, 'center', 0.42), p);
      paperP = Math.max(paperP, p);
      paperBorder = p;
      paperFill = true;
    }
  } else if (span) {
    // 분할: 화자 칸과 자료 칸이 맞붙는다 — 컷으로 바뀐다
    region = speakerCard(props.panelSide, W, H);
    box = videoBoxFor(region, face, 1.0 * punch, 'center', 0.42);
  }

  // 화면 좌표의 얼굴(줌·리프레이밍·칸 축소 반영) — 콜아웃은 이 위치를 피해 놓는다
  const screenFace = {t, x: (box.tx + face.x * box.w) / W, y: (box.ty + face.y * box.h) / H, s: (face.s * box.h) / H};

  // ---- 챕터 ----
  const ci = lastIndexAtOrBefore(props.chapters, t, (c) => c.start);
  const chapter = ci >= 0 ? props.chapters[ci] : null;
  const chapterLook: Look = chapter?.look ?? fallback;

  const tagFor = (g: Graphic) => {
    const k = lastIndexAtOrBefore(props.chapters, g.start + 0.05, (c) => c.start);
    if (k < 0) return '';
    const c = props.chapters[k];
    const n = parseInt(c.number, 10);
    return Number.isFinite(n) ? `${n}. ${c.title}` : c.title;
  };
  // 종이 스킨: 화자가 액자에서 돌아오는 마지막 15프레임 전에 그래픽이 먼저 사라진다
  const exitLead = (g: Graphic) => (spans.some((x) => x.look === 'paper' && Math.abs(x.end - g.end) < 1e-3 && g.start >= x.start - 1e-3) ? 15 : 0);
  // 화자를 완전히 덮는 전면 그래픽(불투명 바탕)인가. 인용·정의·슈퍼·아이덴트는 화자 위에 얹힌다
  const isCover = (g: Graphic) => g.layout === 'fullscreen' && !['title', 'lower_third', 'quote', 'definition'].includes(g.template)
    && (g.template === 'card' || g.template === 'motion' || g.template === 'evidence' || lookOf(g) !== 'paper');
  const seq = (g: Graphic) => {
    const from = toFrame(g.start, fps);
    const dur = Math.max(1, toFrame(g.end, fps) - from);
    const next = over.find((b) => expands[b.id] === g.id || pushes[b.id] === g.id);
    const pushing = !!next && pushes[next.id] === g.id;
    const held = next ? Math.max(0, toFrame(next.start, fps) + Math.round((pushing ? PUSH_SEC : EXPAND_SEC) * fps) - from - dur) : 0;
    return (
      <Sequence key={g.id} from={from} durationInFrames={dur + held} name={`${g.template} ${g.id}`}>
        <GraphicSeq g={g} dur={Math.max(Math.min(dur, 8), dur - exitLead(g))} props={props} theme={theme} chapterTag={tagFor(g)}
          faceX={sampleFace(props.face, g.start + 0.3).x} freeze={held ? dur - 1 : undefined} expand={g.id in expands} before={over.find((b) => b.id === expands[g.id])}
          swap={swaps[g.id]} pushOut={pushing ? toFrame(next!.start, fps) - from : undefined} pushIn={g.id in pushes} />
      </Sequence>
    );
  };

  // 화자를 완전히 덮는 전면 그래픽의 가운데 동안은 화자 영상을 그리지 않는다(보이지 않는 프레임을 뽑는 비용).
  // 이어지는 전면 그래픽(틈 ABUT 초 이하)은 한 덮개로 합친다
  const coverSpans = useMemo(() => {
    const out: {start: number; end: number}[] = [];
    for (const g of props.graphics.filter(isCover).sort((a, b) => a.start - b.start)) {
      const last = out[out.length - 1];
      if (last && g.start - last.end <= ABUT) last.end = Math.max(last.end, g.end);
      else out.push({start: g.start, end: g.end});
    }
    return out;
  }, [props.graphics, fallback]);
  // 드문 전환(조각이 화면이 된다): 맞붙은 전면끼리만 — 앞 그래픽은 펼쳐지는 동안 밑에 멈춰 있어 타임라인 길이는 그대로
  const expands = useMemo(() => expandPairs(over.map((g) => ({id: g.id, start: g.start, end: g.end, cover: isCover(g), expand: !!g.data.overlays?.some((o) => o.kind === 'expand')})), ABUT), [over, fallback]);
  // 맞붙은 전면끼리의 다른 두 전환: 같은 물건은 바탕 종이만 하드 컷, 자료 정지 사진끼리는 드문 세로 밀기
  const fullFrames = useMemo(() => over.map((g) => ({id: g.id, start: g.start, end: g.end, cover: isCover(g), still: isStill(g) && !(g.id in expands), held: heldObject(g)})), [over, expands, fallback]);
  const swaps = useMemo(() => paperSwaps(fullFrames, ABUT), [fullFrames]);
  const pushes = useMemo(() => pushPairs(fullFrames, ABUT), [fullFrames]);
  const faceCovered = coverSpans.some((s) => s.end - s.start > 2 * COVER_PAD + 0.2
    && t >= s.start + COVER_PAD && t < s.end - COVER_PAD);
  const endStart = props.endcard ? toFrame(props.endcard.start, fps) : Infinity;
  const tx = transitionState(props.transitions ?? [], t, W, H, theme);

  return (
    <AbsoluteFill style={{background: MODERN.bg}}>
      <TransitionStage tx={tx}>
        {faceCovered ? <ModernStage dark /> : null}
        {paperP > 0 && frame < endStart ? (
          <>
            {paperFill ? <PaperBg src={props.paperTexture} opacity={Math.min(1, paperP * 1.6)} /> : null}
            {paperBorder > 0 ? <RoughBorder opacity={paperBorder} /> : null}
            {paperFill ? <TornFrame b={region} opacity={Math.min(1, paperP * 2)} seed={7} /> : null}
            {cam.framed > 0.5 && chapter && !span ? (
              <SourceCredit text={`( ${chapter.number} ) ${chapter.title}`} raw opacity={cam.framed} />
            ) : null}
          </>
        ) : null}
        {frame < endStart && !faceCovered ? <TalkingHead clips={props.clips} fps={fps} region={region} box={box} /> : null}
        {over.map(seq)}
        <CalloutLayer items={props.callouts ?? []} t={t} fps={fps} W={W} H={H} theme={theme} look={chapterLook}
          face={screenFace} zoom={1} />
      </TransitionStage>
      {tx.hideCaptions ? null : span ? <LongCaptions cues={props.captions} t={t} left={region.x} frameW={region.w} minSize={30} /> : <LongCaptions cues={props.captions} t={t} frameW={W} />}{/* 분할: 찢긴 이음새를 가로지르지 않게 화자 칸 안으로 */}
      {props.endcard ? (
        <Sequence from={endStart} durationInFrames={Math.max(1, toFrame(props.endcard.dur, fps))} name="endcard">
          <EndCardSeq props={props} />
        </Sequence>
      ) : null}
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

const EndCardSeq: React.FC<{props: LongFormProps}> = ({props}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  if (props.skin !== 'paper') return <ModernEndCard brand={props.brand} W={width} H={height} />;
  return <PaperEndCard frame={frame} brand={props.brand} episode={props.episode} chapters={props.chapters}
    texture={props.paperTexture} W={width} H={height} />;
};
