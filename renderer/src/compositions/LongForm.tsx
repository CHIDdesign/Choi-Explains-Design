import React, {useMemo} from 'react';
import {ModernStage, SpeakerFrame} from '../components/modern/Modern';
import {ModernEndCard} from '../components/modern/Titles';
import {AbsoluteFill, Audio, interpolate, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {GraphicLayer} from '../components/graphics';
import {CaptionScrim, LongCaptions} from '../components/captions/LongCaptions';
import {ScreenLook} from '../components/fx/ScreenLook';
import {CalloutLayer} from '../components/captions/Callout';
import {Grain, Vignette} from '../components/fx/Grain';
import {LivePeek} from '../components/fx/LivePeek';
import {PaperEndCard} from '../components/layout/EndCard';
import {PAPER, PaperBg, RoughBorder, SourceCredit, TornFrame} from '../components/paper/Paper';
import {paperSpeakerBox} from '../components/paper/PaperGraphic';
import {boardCard, ContextStrip, speakerCard, stripOpacity} from '../components/longform/Stage';
import {TransitionStage, transitionState} from '../components/fx/Transitions';
import {lerpBox, lerpRect, TalkingHead, videoBoxFor} from '../components/TalkingHead';
import type {Rect} from '../components/TalkingHead';
import {ensureFonts, useFontForText, useFontGuard} from '../design/fonts';
import {EASE} from '../design/motion';
import {makeTheme, MODERN} from '../design/tokens';
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
 * 강조 밀기: 핵심어(t)에 맞춰 카메라를 아주 천천히 당겼다가 아주 천천히 푼다(2026-10-04 채널 주인: '확대·이완이 너무 빨라
 * 가벼워 보인다 — 교양 있고 차분하고 딥하게'). from 부터 in 초에 걸쳐 당기고, end 에서 out 초 앞부터 푼다(사인 가감속).
 * 창이 짧으면 두 시간을 비율대로 줄인다. 예전 cut(한 프레임 펀치인)·ease(5프레임)도 같은 느린 밀기로 그린다.
 */
const sineInOut = (x: number) => 0.5 - 0.5 * Math.cos(Math.PI * Math.min(1, Math.max(0, x)));
export const punchFactor = (punches: Punch[], t: number, fps = 30): number => {
  void fps;
  let f = 1;
  for (const p of punches) {
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
    const k = Math.min(sineInOut((t - a) / inD), sineInOut((p.end - t) / outD));
    f = Math.max(f, 1 + p.amount * k);
  }
  return f;
};

const SEQ_SKIP = 16; // 시퀀스 둘째 샷부터 건너뛸 등장 프레임(등장 14~16f 가 끝난 상태로 컷)
const COVER_PAD = 1.0; // 전체화면 그래픽 앞뒤로 화자 영상을 계속 그리는 여유(초) — 등장·퇴장·전환이 이 안에서 끝난다
// 전면 그래픽끼리 이 간격(초) 이하로 이어지면 한 덮개로 본다: 사이에 화자를 그리지 않고, 앞 그래픽은 퇴장 없이 컷으로 넘기며,
// 접합부 아래에는 무대판을 깐다 — 2026-10-03: 전면→전면 전환의 디졸브 몇 프레임 동안 화자 얼굴이 비쳤다
const ABUT = 0.5;
// 모니터 질감을 얹지 않는 전면 그래픽: 실물 자료(사진·스톡·증거 — 자료의 색과 결을 지킨다)·타이틀(화자 액자가 들어 있다)
const LOOK_SKIP = new Set(['photo', 'broll', 'evidence', 'title', 'lower_third']);

const GraphicSeq: React.FC<{
  g: Graphic;
  dur: number;
  props: LongFormProps;
  theme: ReturnType<typeof makeTheme>;
  pageLabel: string;
  chapterTag: string;
  faceX: number;
}> = ({g, dur, props, theme, pageLabel, chapterTag, faceX}) => {
  // 시퀀스의 둘째 샷부터는 등장이 끝난 상태로 시작한다(같은 틀 안의 컷 — 샷마다 등장 애니메이션을 되풀이하지 않는다)
  const skip = g.seq && g.seq.index > 0 ? SEQ_SKIP : 0;
  const frame = useCurrentFrame() + skip;
  const {fps, width, height} = useVideoConfig();
  return (
    <GraphicLayer g={g} frame={frame} dur={dur + skip} fps={fps} theme={theme} brand={props.brand} episode={props.episode}
      W={width} H={height} panelSide={props.panelSide} pageLabel={pageLabel} skin={props.skin}
      paperTexture={props.paperTexture} chapterTag={chapterTag} faceX={faceX} />
  );
};

// 장면 안무(2026-10-04 채널 주인: 'PPT 장면 전환·페이드 금지 — 요소가 흩어지거나 재사용되거나, 확대·축소 등 모션그래픽 방식으로.
// 가장 싫은 것은 페이드되는 요소끼리 겹치는 것'). 모션 디자인의 장면 전환은 나가는 요소 · 남는(공유) 요소 · 들어오는 요소의
// 안무다(Material motion choreography). 두 장면이 반투명으로 겹치는 프레임은 없다 — 컷은 움직임의 한가운데에 둔다.
//  · 얼굴 → 그래픽: 원형 열기(화자 얼굴 자리에서 원이 자라며 그래픽이 열린다)
//  · 그래픽 → 그래픽: 카드는 요소가 각자 방향으로 흩어져 나가고(data-carry 요소는 남아 다음 장면이 이어 받는다) 컷 → 다음 장면이
//    모여든다 / 그 밖의 그래픽은 다이브(확대하며 빨려 들어감 + 움직임 흐림) → 컷 → 다음 장면이 확대된 채 내려앉는다
//  · 그래픽 → 얼굴: 요소가 흩어지며 그래픽이 원으로 닫혀 화자에게 돌아간다
const IRIS_IN = 18;
const IRIS_OUT = 14;
const DIVE = 12;
const SETTLE = 14;
const SCATTER = 18;
type ChoreoPlan = {inKind: 'iris' | 'settle' | 'none'; outKind: 'iris' | 'dive' | 'none'; inX: number; outX: number; faceY: number};
const Choreo: React.FC<{plan: ChoreoPlan; dur: number; W: number; H: number; children: React.ReactNode}> = ({plan, dur, W, H, children}) => {
  const f = useCurrentFrame();
  const style: React.CSSProperties = {};
  const cl = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
  // 원형 열기·닫기의 중심 = 그때 화자 얼굴 자리(그래픽이 화자에게서 나오고 화자에게 돌아간다)
  const closing = plan.outKind === 'iris' && f >= dur - IRIS_OUT;
  const cx = closing ? plan.outX : plan.inX;
  const cy = plan.faceY;
  const reach = Math.hypot(Math.max(cx, W - cx), Math.max(cy, H - cy)) + 4;
  let r = -1;
  if (plan.inKind === 'iris' && f < IRIS_IN) r = reach * interpolate(f, [0, IRIS_IN], [0, 1], {...cl, easing: EASE.enterLarge});
  if (closing) r = reach * (1 - interpolate(f, [dur - IRIS_OUT, dur - 1], [0, 1], {...cl, easing: EASE.exit}));
  if (r >= 0) style.clipPath = `circle(${Math.max(0, r).toFixed(1)}px at ${cx.toFixed(0)}px ${cy.toFixed(0)}px)`;
  if (plan.inKind === 'settle' && f < SETTLE) {
    const q = interpolate(f, [0, SETTLE], [0, 1], {...cl, easing: EASE.enterLarge});
    style.transform = `scale(${(1.18 - 0.18 * q).toFixed(4)})`;
    if (q < 0.97) style.filter = `blur(${((1 - q) * 9).toFixed(2)}px)`;
  }
  if (plan.outKind === 'dive' && f >= dur - DIVE) {
    const q = interpolate(f, [dur - DIVE, dur - 1], [0, 1], {...cl, easing: EASE.exit});
    style.transform = `scale(${(1 + 0.38 * q).toFixed(4)})`;
    if (q > 0.03) style.filter = `blur(${(q * 11).toFixed(2)}px)`;
  }
  return <AbsoluteFill style={{...style, transformOrigin: '50% 50%'}}>{children}</AbsoluteFill>;
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
  // 시작 순서로 그린다(나중 그래픽이 위) — 이어 받기에서 뒤 그래픽이 앞 그래픽 위로 떠오른다
  const over = useMemo(() => props.graphics.filter((g) => !isUnder(g)).sort((a, b) => a.start - b.start), [props.graphics, fallback]);

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
      radius = Math.max(radius, 28 * p);
    } else if (p > 0) {
      let target: Rect;
      let tBox;
      if (span.kind === 'split') {
        // 롱폼 무대(classic): 화자는 둥근 화자 판(40/96 여백, 반경 22)에, 옆에 보드 판 — 잉크 위 두 장의 판
        target = speakerCard(props.panelSide, W, H);
        tBox = videoBoxFor(target, face, 1.04 * punchFactor(props.punches, t, fps), 'center', 0.42);
        const bc = boardCard(props.panelSide, W, H);
        capCenter = W / 2 + (bc.x + bc.w / 2 - W / 2) * p;
        radius = 24 * p;    // 디자인 v4: 화자도 둥근 흰 카드 안에
        border = `1px solid rgba(18,19,21,${0.12 * p})`;
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

  // 화면 좌표의 얼굴(줌·리프레이밍·패널 축소 반영) — 콜아웃은 이 위치를 피해 놓는다(예전엔 원본 좌표라 확대·이동 때 겹쳤다)
  const screenFace = {t, x: (box.tx + face.x * box.w) / W, y: (box.ty + face.y * box.h) / H, s: (face.s * box.h) / H};

  // ---- 챕터 ----
  const ci = lastIndexAtOrBefore(props.chapters, t, (c) => c.start);
  const chapter = ci >= 0 ? props.chapters[ci] : null;
  const chapterLook: Look = chapter?.look ?? fallback;
  const pageFor = (g: Graphic) => {
    const k = lastIndexAtOrBefore(props.chapters, g.start, (c) => c.start);
    return k >= 0 ? `ch ${props.chapters[k].number}` : '';
  };
  const fullscreenActive = props.graphics.some((g) => g.layout === 'fullscreen' && t >= g.start && t < g.end);
  // 챕터 카드·타이틀 ±0.3초(전환이 걸리는 동안)에도 스트립을 숨긴다
  const coverActive = props.graphics.some((g) => (g.template === 'chapter' || g.template === 'title')
    && t >= g.start - 0.3 && t < g.end + 0.3);
  // 화면 위 소제목 바가 떠 있는 동안도(같은 자리) 스트립을 숨긴다
  const topBarActive = props.graphics.some((g) => g.pip?.side === 'top' && t >= g.start - 0.2 && t < g.end + 0.2);
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
  // 퇴장 순서(docs/upgrade/06 F-8): 화자가 판·액자에서 돌아오는 마지막 12(종이 15)프레임 전에 그래픽이 먼저 사라진다 —
  // 예전엔 반투명해진 도식이 커지는 얼굴 위에 겹쳤다. 화자가 돌아오는 구간의 마지막 그래픽에만(이어지는 그래픽은 그대로)
  const exitLead = (g: Graphic) => {
    const sp = spans.find((x) => Math.abs(x.end - g.end) < 1e-3 && g.start >= x.start - 1e-3);
    return sp ? (sp.look === 'paper' ? 15 : 12) : 0;
  };
  // 화자를 완전히 덮는 전면 그래픽(불투명 바탕)인가 — faceCovered·coverSpans·abutNext 가 같은 기준을 쓴다
  const isCover = (g: Graphic) => g.layout === 'fullscreen' && g.template !== 'title' && g.template !== 'lower_third'
    && (g.template === 'card' || g.template === 'motion' || g.template === 'evidence' || lookOf(g) !== 'paper');
  // 바로 뒤에 다른 전면 그래픽이 ABUT 초 안에 이어지면 퇴장을 생략한다(앞 그래픽이 끝 프레임까지 그대로 있다가 컷)
  const abutNext = (g: Graphic) => isCover(g) && props.graphics.some((o) => o !== g && isCover(o)
    && o.start >= g.end - 1e-3 && o.start - g.end <= ABUT);
  // 바로 앞에서 ABUT 초 안에 끝나는 전면 그래픽(장면 안무의 앞 장면)
  const prevCover = (g: Graphic) => (isCover(g) ? props.graphics.filter((o) => o !== g && isCover(o)
    && o.start < g.start - 1e-3 && o.end <= g.start + 1e-3 && g.start - o.end <= ABUT).sort((a, b) => b.end - a.end)[0] : undefined);
  const seq = (g: Graphic) => {
    const from = toFrame(g.start, fps);
    const dur = Math.max(1, toFrame(g.end, fps) - from);
    const next = abutNext(g);
    if (!isCover(g)) {
      const shown = Math.max(Math.min(dur, 8), dur - exitLead(g));
      return (
        <Sequence key={g.id} from={from} durationInFrames={dur} name={`${g.template} ${g.id}`}>
          <GraphicSeq g={g} dur={shown} props={props} theme={theme} pageLabel={pageFor(g)} chapterTag={tagFor(g)}
            faceX={sampleFace(props.face, g.start + 0.3).x} />
        </Sequence>
      );
    }
    // 전면 그래픽: 장면 안무가 들고 나기를 맡는다(이 층의 페이드·쓸기 끔). 카드는 나갈 때 요소가 흩어진다
    const prev = prevCover(g);
    const isCard = g.template === 'card';
    const fIn = sampleFace(props.face, g.start + 0.1);
    const fOut = sampleFace(props.face, g.end - 0.1);
    const plan: ChoreoPlan = {
      inKind: prev ? (prev.template === 'card' ? 'none' : 'settle') : 'iris',
      outKind: next ? (isCard ? 'none' : 'dive') : 'iris',
      inX: fIn.x * W, outX: fOut.x * W, faceY: 0.42 * H,
    };
    const scatter = isCard && dur > SCATTER + 12;
    const skip = g.seq && g.seq.index > 0 ? SEQ_SKIP : 0;     // GraphicSeq 가 시퀀스 둘째 샷부터 프레임을 앞당긴다
    const data = {...g.data, __choreo: true,
      ...(scatter ? {__exit: {at: Math.max(0, (dur - SCATTER + skip) / fps), dur: SCATTER / fps}} : {})};
    const gg = {...g, data} as Graphic;
    return (
      <Sequence key={g.id} from={from} durationInFrames={dur} name={`${g.template} ${g.id}`}>
        <Choreo plan={plan} dur={dur} W={W} H={H}>
          <GraphicSeq g={gg} dur={next ? dur + Math.round(fps) : dur} props={props} theme={theme} pageLabel={pageFor(g)}
            chapterTag={tagFor(g)} faceX={sampleFace(props.face, g.start + 0.3).x} />
        </Choreo>
      </Sequence>
    );
  };

  // 화자를 완전히 덮는 전체화면 그래픽(롱폼 무대의 리포트 페이지·사진·스톡·챕터 카드·자유 카드 — 모두 불투명 바탕)의
  // 가운데 동안은 화자 영상을 그리지 않는다: 보이지 않는 프레임을 뽑고 합성하던 비용(사진 구간 렌더 1.8 → 3.0fps 실측).
  // 들어오고 나가는 애니메이션·전환이 걸리는 앞뒤 1초는 그대로 그린다. 종이 모양 그래픽은 경로가 여럿이라 모션 장면
  // (불투명 종이 페이지)만 넣는다
  // 이어지는 전면 그래픽(틈 ABUT 초 이하)은 한 덮개로 합친다 — 접합부에서도 화자를 그리지 않는다
  const coverSpans = useMemo(() => {
    const out: {start: number; end: number}[] = [];
    for (const g of props.graphics.filter(isCover).sort((a, b) => a.start - b.start)) {
      const last = out[out.length - 1];
      if (last && g.start - last.end <= ABUT) last.end = Math.max(last.end, g.end);
      else out.push({start: g.start, end: g.end});
    }
    return out;
  }, [props.graphics, fallback]);
  const faceCovered = coverSpans.some((s) => s.end - s.start > 2 * COVER_PAD + 0.2
    && t >= s.start + COVER_PAD && t < s.end - COVER_PAD);
  // 모니터 질감(ScreenLook)은 디자인한 전면 그래픽(카드·모션·챕터·개념 판) 동안만 — 화자·사진·스톡·자막에는 얹지 않는다.
  // 이어지는 전면 그래픽은 한 덮개로, 들어오고 나갈 때 0.35초에 걸쳐 켜고 끈다
  const lookSpans = useMemo(() => {
    const out: {start: number; end: number}[] = [];
    if (!props.screenLook) return out;
    for (const g of props.graphics.filter((x) => isCover(x) && !LOOK_SKIP.has(x.template)).sort((a, b) => a.start - b.start)) {
      const last = out[out.length - 1];
      if (last && g.start - last.end <= ABUT) last.end = Math.max(last.end, g.end);
      else out.push({start: g.start, end: g.end});
    }
    return out;
  }, [props.graphics, props.screenLook, fallback]);
  const lookOpacity = lookSpans.reduce((m, sp) => (t < sp.start || t >= sp.end ? m
    : Math.max(m, Math.min(1, (t - sp.start) / 0.35, (sp.end - t) / 0.35))), 0);
  // 지금 보이는 전면 그래픽의 바탕이 어두운가(카드: 렌더 전 검사가 잰 바탕 밝기 · 모션: spec.bg)
  const lookDark = (() => {
    const g = props.graphics.filter((x) => isCover(x) && !LOOK_SKIP.has(x.template) && t >= x.start && t < x.end)
      .sort((a, b) => b.start - a.start)[0];
    if (!g) return false;
    if (g.template === 'card') return !!g.data.card?.dark;
    if (g.template === 'motion') return ['ink', 'dark', 'black', 'charcoal'].includes(String(g.data.spec?.bg ?? ''));
    return false;
  })();
  const endStart = props.endcard ? toFrame(props.endcard.start, fps) : Infinity;
  const tx = transitionState(props.transitions ?? [], t, W, H, theme);

  return (
    <AbsoluteFill style={{background: MODERN.bg}}>
      <TransitionStage tx={tx}>
        {/* 디자인 v4: 화자가 판으로 줄어들 때 뒤는 모던 밝은 무대 */}
        {region !== full || faceCovered ? <ModernStage theme={theme} frame={frame} /> : null}
        {under.map(seq)}
        {paperP > 0 && frame < endStart ? (
          <>
            {paperFill ? <PaperBg src={props.paperTexture} opacity={Math.min(1, paperP * 1.6)} /> : null}
            {paperBorder > 0 ? <RoughBorder opacity={paperBorder} /> : null}
            {paperFill ? <TornFrame b={region} opacity={Math.min(1, paperP * 2)} seed={7} />
              : <SpeakerFrame x={region.x} y={region.y} w={region.w} h={region.h} opacity={Math.min(1, paperP * 2)} />}
            {cam.framed > 0.5 && chapter && !span ? (
              <SourceCredit text={`( ${chapter.number} ) ${chapter.title}`} raw opacity={cam.framed} />
            ) : null}
          </>
        ) : null}
        {frame < endStart && !faceCovered ? (
          <TalkingHead clips={props.clips} fps={fps} region={region} box={box} radius={radius} border={border}
            shadow={radius > 0} />
        ) : null}
        {region === full ? <Vignette strength={0.22} /> : null}
        {props.showChapterLabel && chapter && ci >= 0 && !fullscreenActive && !span && paperP === 0
          && frame < endStart && !coverActive && !topBarActive ? (
          // 컨텍스트 스트립(롱폼 무대): 지금 챕터 번호·제목 + 챕터 눈금 — 전체화면·보드·타이틀·챕터 카드 동안은 숨김
          <ContextStrip chapters={props.chapters} index={ci} t={t} total={props.duration} theme={theme}
            opacity={stripOpacity(frame, toFrame(chapter.start + 3.2, fps))} />
        ) : null}
        {over.map(seq)}
        {props.screenLook ? <ScreenLook frame={frame} strength={props.screenLook} opacity={lookOpacity} dark={lookDark} /> : null}
        <CalloutLayer items={props.callouts ?? []} t={t} fps={fps} W={W} H={H} theme={theme} look={chapterLook}
          face={screenFace} zoom={1} />
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
  // 디자인 v4: 밝은 무대 + '다음 이야기에서 만나요' + 챕터 목록 + 다음 영상·구독·재생목록 자리
  if (props.skin !== 'paper') {
    return <ModernEndCard frame={frame} brand={props.brand} episode={props.episode} chapters={props.chapters} theme={theme}
      W={width} H={height} />;
  }
  return <PaperEndCard frame={frame} brand={props.brand} episode={props.episode} chapters={props.chapters}
    texture={props.paperTexture} W={width} H={height} />;
};
