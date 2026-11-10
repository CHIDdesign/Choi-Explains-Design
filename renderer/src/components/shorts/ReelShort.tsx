import React, {useMemo} from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';
import {cameraAt, punchFactor} from '../../compositions/LongForm';
import {surface as mkSurface} from '../../design/surfaces';
import {FONT, makeTheme, MAT, TEXT_SHADOW} from '../../design/tokens';
import {fitSize} from '../../lib/fit';
import {sampleFace, toFrame} from '../../lib/time';
import type {Graphic, ShortProps} from '../../lib/types';
import {LivePeek} from '../fx/LivePeek';
import {LongCaptions} from '../captions/LongCaptions';
import {TEMPLATE_COMPONENTS} from '../graphics';
import {Annotated} from '../longform/Stage';
import {ModernStage} from '../modern/Modern';
import {TalkingHead, videoBoxFor} from '../TalkingHead';

/**
 * 숏폼(1080×1920) 디자인 v5: 화자 또는 자료가 화면 전체, 위 두 줄 고딕 제목, 아래 상자 자막. 카드·코너 마크 없음.
 * 안전 영역: 제목 y 120~330(머리 위) · 얹힌 글자 y 1120~1300(고정 띠) · 자막은 그 아래, 전면 종이일 때는 카드 아래 — 얼굴은 비워 둔다.
 */
const W = 1080;
const H = 1920;
const FULL = {x: 0, y: 0, w: W, h: H};
const CAPTION_BOTTOM = {over: 506, paper: 330, list: 700};
const TALL_FORMS = new Set(['list', 'process', 'compare']);     // 세로 화면 배치를 자기가 아는 템플릿
const WORD_TEMPLATES = new Set(['keyword', 'definition', 'quote', 'stat', 'stamp', 'cutout_stack', 'lower_third']);   // 화자·자료 위에 얹히는 것 — 바닥판을 깔지 않는다
const isMedia = (g: Graphic) => g.template === 'photo' || g.template === 'broll' || g.template === 'evidence' || g.template === 'keyword_montage';

const Slide: React.FC<{g: Graphic; props: ShortProps; theme: ReturnType<typeof makeTheme>; fps: number}> = ({g, props, theme, fps}) => {
  const frame = useCurrentFrame();
  const Comp = TEMPLATE_COMPONENTS[g.template];
  if (!Comp) return null;
  const dur = Math.max(1, toFrame(g.end, fps) - toFrame(g.start, fps));
  const media = isMedia(g);
  const words = WORD_TEMPLATES.has(g.template);
  const surface = mkSurface(theme, 'modern');
  const common = {id: g.id, data: g.data, frame, dur, fps, theme, surface, brand: props.brand, episode: props.episode};
  if (media || words || g.template === 'collage') return <Comp {...common} layout={words ? 'overlay' : 'fullscreen'} box={{w: W, h: H}} />;
  // 도식·목록·모션: 제목 아래부터 프레임 중앙을 채운다
  const box = {w: W - 96, h: 1060};
  return (
    <>
      <ModernStage />
      <div style={{position: 'absolute', left: 48, top: 430, width: box.w, height: box.h}}>
        <Comp {...common} layout="split" compact={!TALL_FORMS.has(g.template)} box={box} />
      </div>
    </>
  );
};

export const ReelShort: React.FC<ShortProps> = (props) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const t = frame / fps;
  const theme = useMemo(() => makeTheme(props.brand), [props.brand]);
  const zoom = cameraAt(props.camera ?? [], t).zoom * punchFactor(props.punches, t);
  const box = videoBoxFor(FULL, sampleFace(props.face, t), zoom, 'center', 0.46);
  const lines = props.hookTitle.split('\n').filter(Boolean).slice(0, 2);
  const size = Math.min(84, ...lines.map((l) => fitSize(l, 900, 84, 52, -0.02)));
  const hl = props.hookHighlight;
  const paper = props.graphics.find((g) => t >= g.start && t < g.end && !isMedia(g) && !WORD_TEMPLATES.has(g.template));
  const onPaper = !!paper;     // 밝은 종이 전면: 제목은 잉크색, 스크림 없음
  return (
    <AbsoluteFill style={{background: '#000'}}>
      <TalkingHead clips={props.clips} fps={fps} region={FULL} box={box} />
      {props.graphics.map((g) => {
        const from = toFrame(g.start, fps);
        return (
          <Sequence key={g.id} from={from} durationInFrames={Math.max(1, toFrame(g.end, fps) - from)} name={`${g.template} ${g.id}`}>
            <Slide g={g} props={props} theme={theme} fps={fps} />
          </Sequence>
        );
      })}
      {onPaper ? null : <div style={{position: 'absolute', left: 0, top: 0, width: W, height: 440,
        background: 'linear-gradient(180deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0.42) 62%, rgba(0,0,0,0) 100%)'}} />}
      <div style={{position: 'absolute', left: 90, width: 900, top: 120, textAlign: 'center', textShadow: onPaper ? undefined : TEXT_SHADOW}}>
        {lines.map((l, i) => (
          <div key={i} style={{fontFamily: FONT.sans, fontWeight: 800, fontSize: size, lineHeight: 1.22, letterSpacing: '-0.02em', whiteSpace: 'nowrap'}}>
            <Annotated text={l} accent={hl && l.includes(hl) ? hl : null} p={1} color={onPaper ? MAT.ink : '#FFFFFF'} underline={theme.accent} />
          </div>
        ))}
      </div>
      <LongCaptions cues={props.captions} t={t} frameW={W} bottom={!paper ? CAPTION_BOTTOM.over : paper.template === 'list' ? CAPTION_BOTTOM.list : CAPTION_BOTTOM.paper} size={52} />
      {props.progressBar ? (
        <div style={{position: 'absolute', left: 0, bottom: 0, height: 6, width: (W * frame) / Math.max(1, durationInFrames), background: theme.accent}} />
      ) : null}
      <LivePeek every={props.peekEvery} />
    </AbsoluteFill>
  );
};
