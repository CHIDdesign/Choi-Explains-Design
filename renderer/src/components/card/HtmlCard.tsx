import React, {useLayoutEffect, useMemo, useRef, useState} from 'react';
import {continueRender, delayRender, staticFile} from 'remotion';
import gsap from 'gsap';
import {CustomEase} from 'gsap/CustomEase';
import {DrawSVGPlugin} from 'gsap/DrawSVGPlugin';
import {MorphSVGPlugin} from 'gsap/MorphSVGPlugin';
import {MotionPathPlugin} from 'gsap/MotionPathPlugin';
import {SplitText} from 'gsap/SplitText';
import {compileCard} from '../../../vendor/hyperframes/card-anim.mjs';
import type {CompiledCard} from '../../../vendor/hyperframes/card-anim.mjs';
import {FONT, rgba, MODERN, lift, liftDrop} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import {useMaterials} from '../material/Texture';
import type {Surface} from '../../design/surfaces';
import type {CardSpec} from '../../lib/types';
import type {TemplateProps} from '../graphics/common';

/**
 * 자유 HTML 카드(HyperFrames talking-head-recut 카드 규약 호환 — renderer/vendor/hyperframes/NOTICE.md).
 * 모션 디자이너가 쓴 HTML + 스코프 CSS + data-anim 선언을 붙이고, 매 프레임 GSAP 타임라인을 seek 한다.
 * 카드는 정해진 캔버스(card.w × card.h)로 쓰고 여기서 상자에 맞춰 축소한다. 호스트의 등장·퇴장은 GraphicLayer 가 맡는다.
 */
export const HtmlCard: React.FC<TemplateProps> = (p) => (p.data.card ? <CardBody {...p} card={p.data.card} /> : null);

// GSAP 3.13+ 의 무료 플러그인(마스크 글자 분할 · 선 그리기 · 모양 바꾸기 · 경로 이동 · 사용자 이징) — card_dsl.md 의 split-*·draw-svg·
// morph-svg·follow-path 와 timeline 의 gsap.splitText·gsap.customEase. check.mjs 도 같은 것을 등록한다(검사와 렌더가 같아야 한다)
gsap.registerPlugin(SplitText, CustomEase, DrawSVGPlugin, MorphSVGPlugin, MotionPathPlugin);
export const CARD_LIBS = {SplitText, CustomEase, drawSVG: true, morphSVG: true, motionPath: true};

/** 카드 CSS 가 쓰는 채널 토큰(변수) — prompts/card_dsl.md 의 표와 같아야 한다 */
export const cardVars = (theme: Theme, surface: Surface): Record<string, string> => ({
  // 디자인 v5: 카드의 바탕·잉크는 평면 면 값
  '--bg': surface.bg === 'transparent' ? 'transparent' : MODERN.bg,
  '--paper': MODERN.bg,
  '--paper-line': MODERN.line,
  '--ink': MODERN.ink,
  '--ink-soft': theme.inkSoft,
  '--muted': 'rgba(28, 28, 28, 0.7)',
  '--accent': theme.accent,
  '--accent-deep': theme.accentDeep,
  '--accent-light': theme.accentLight,
  '--accent-soft': rgba(theme.accent, 0.32),
  '--board': theme.board,
  '--board-edge': theme.boardEdge,
  '--chalk': theme.chalk,
  '--chalk-dim': theme.chalkDim,
  '--white': MODERN.card,
  '--band': theme.band,
  '--font-head': FONT.display,
  '--font-body': FONT.sans,
  '--font-serif': FONT.serif,
  '--font-latin': FONT.latin,
  '--font-heavy': FONT.heavy,
  '--font-round': FONT.memo,
  '--font-hand': FONT.hand,
  '--font-numeral': FONT.numeral,
  '--font-editorial': FONT.editorial,
  '--font-poster': FONT.poster,
  '--font-italic': FONT.italic,
  '--font-mono': FONT.mono,
  '--font-pen': FONT.pen,
  '--font-quote': FONT.quote,
  '--lift-1': lift(1, 1, 'board'),
  '--lift-2': lift(2, 1, 'board'),
  '--lift-3': lift(3, 1, 'board'),
  '--lift-drop-2': liftDrop(2, 1, 'board'),
});

const surfaceUrl = (name: string) => staticFile(`fx/tex/${name}.jpg`);

/** 카드 조각(내부 HTML + 스코프 CSS) → 마운트할 문자열. .card 는 호스트(작성 캔버스)를 꽉 채운다 — 안 그러면 .root 의 height:100% 가 내용 높이가 된다 */
// 한국어 줄바꿈은 어절 단위(keep-all) — 기본값은 음절마다 끊어 '그 특 / 징'처럼 낱말 가운데서 줄이 바뀐다(2026-10-04 렌더 확인)
export const wrapCard = (card: CardSpec): string =>
  `<div class="card" data-card-id="${card.id}"><style>.card[data-card-id="${card.id}"]{position:absolute;left:0;top:0;width:100%;height:100%;overflow:hidden;word-break:keep-all;overflow-wrap:break-word}` +
  `.card[data-card-id="${card.id}"] *{box-sizing:border-box}${card.css}</style>` +
  // 카드의 images/… 는 작업 public 폴더 기준 — 렌더 페이지 주소로 풀면 404 다(staticFile 만이 번들 경로를 안다)
  card.html.replace(/(<img\b[^>]*?\bsrc=")([^"]+)"/g, (_m, a, src) => `${a}${staticFile(src)}"`) + '</div>';

const FAMILIES: [RegExp, string][] = [
  [/pretendard|--font-body|--font-mono/i, 'Pretendard'],
  [/black han sans|--font-heavy/i, 'Black Han Sans'],
  [/jua|--font-round/i, 'Jua'],
  [/nanum pen script|--font-hand|--font-pen/i, 'Nanum Pen Script'],
  [/playfair display|--font-numeral/i, 'Playfair Display'],
  [/instrument serif|--font-italic/i, 'Instrument Serif'],
  [/hahmlet/i, 'Hahmlet'],
  [/song myung|--font-poster|--font-editorial/i, 'Song Myung'],
  [/gowun batang|--font-serif|--font-head|--font-quote/i, 'Gowun Batang'],
  [/noto serif kr|serif/i, 'Noto Serif KR'],
  [/anton|--font-latin/i, 'Anton'],
];

const CardBody: React.FC<TemplateProps & {card: CardSpec}> = ({id, card, frame, fps, dur, box, theme, surface}) => {
  useMaterials();
  const hostRef = useRef<HTMLDivElement>(null);
  const compiled = useRef<CompiledCard | null>(null);
  const [handle] = useState(() => delayRender(`card ${id}`));
  const released = useRef(false);
  const html = useMemo(() => wrapCard(card), [card]);
  const w = card.w || 1920;
  const h = card.h || 1080;
  const scale = Math.min(box.w / w, box.h / h);

  const frameRef = useRef(frame);
  frameRef.current = frame;
  useLayoutEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    el.innerHTML = html;
    // 카드 글꼴(분할 웹폰트 포함)이 이 글자들을 다 받을 때까지 첫 프레임을 멈춘다 — 조용한 폴백 글꼴 렌더 방지.
    // 타임라인은 글꼴을 받은 뒤에 짓는다 — SplitText 가 줄을 나누려면 실제 글꼴의 줄바꿈이어야 한다
    const text = el.textContent || '가';
    const fams = FAMILIES.filter(([re]) => re.test(card.css + card.html)).map(([, f]) => f);
    let alive = true;
    const build = () => {
      if (!alive || compiled.current) return;
      compiled.current = compileCard(gsap, el, {fps, duration: dur / fps, timeline: card.timeline || '', libs: CARD_LIBS, surfaceUrl});
      compiled.current.seek(frameRef.current / fps);
    };
    const release = () => {
      build();
      if (!released.current) {
        released.current = true;
        continueRender(handle);
      }
    };
    const imgs = Array.from(el.querySelectorAll('img')).map((i) => i.decode().catch(() => undefined));
    Promise.all([...imgs, ...fams.flatMap((f) => ['400', '700'].map((wgt) => document.fonts.load(`${wgt} 40px "${f}"`, text)))])
      .then(() => document.fonts.ready)
      .then(release, release);
    const t = setTimeout(release, 8000);
    return () => {
      alive = false;
      clearTimeout(t);
      compiled.current?.timeline.kill();
      compiled.current = null;
    };
    // frame 은 아래 effect 가 맡는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [html, fps, dur]);

  useLayoutEffect(() => {
    compiled.current?.seek(frame / fps);
  }, [frame, fps]);

  const vars = cardVars(theme, surface) as React.CSSProperties;
  return (
    <div style={{position: 'absolute', left: 0, top: 0, width: box.w, height: box.h, overflow: 'hidden'}}>
      <div
        ref={hostRef}
        className="card-host"
        style={{...vars, position: 'absolute', left: (box.w - w * scale) / 2, top: (box.h - h * scale) / 2, width: w, height: h,
          transform: `scale(${scale})`, transformOrigin: 'top left', color: theme.ink, fontFamily: FONT.sans,
          lineHeight: 1.25}}
      />
    </div>
  );
};
