import React, {useLayoutEffect, useMemo, useRef, useState} from 'react';
import {continueRender, delayRender} from 'remotion';
import gsap from 'gsap';
import {compileCard} from '../../../vendor/hyperframes/card-anim.mjs';
import type {CompiledCard} from '../../../vendor/hyperframes/card-anim.mjs';
import {FONT, rgba, NOTE} from '../../design/tokens';
import type {Theme} from '../../design/tokens';
import type {Surface} from '../../design/surfaces';
import type {CardSpec} from '../../lib/types';
import type {TemplateProps} from '../graphics/common';

/**
 * 자유 HTML 카드(HyperFrames talking-head-recut 카드 규약 호환 — renderer/vendor/hyperframes/NOTICE.md).
 * 모션 디자이너가 쓴 HTML + 스코프 CSS + data-anim 선언을 붙이고, 매 프레임 GSAP 타임라인을 seek 한다.
 * 카드는 정해진 캔버스(card.w × card.h)로 쓰고 여기서 상자에 맞춰 축소한다. 호스트의 등장·퇴장은 GraphicLayer 가 맡는다.
 */
export const HtmlCard: React.FC<TemplateProps> = (p) => (p.data.card ? <CardBody {...p} card={p.data.card} /> : null);

/** 카드 CSS 가 쓰는 채널 토큰(변수) — prompts/card_dsl.md 의 표와 같아야 한다 */
// 한 재질(docs/upgrade/06 3-1, F-10): 카드의 '흰 바탕'·'잉크 바탕'은 순백(#FFF)·순흑(#111)이 아니라 메모·로고 카드와 같은
// 크림 종이(NOTE.paper)·따뜻한 잉크(NOTE.ink) — 한 영상에 전면 배경색이 셋을 넘지 않게(게이트 B9)
export const cardVars = (theme: Theme, surface: Surface): Record<string, string> => ({
  '--bg': surface.bg === 'transparent' ? 'transparent' : NOTE.paper,
  '--paper': NOTE.paper,
  '--paper-line': theme.paperLine,
  '--ink': NOTE.ink,
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
  '--white': NOTE.paper,
  '--font-head': FONT.display,
  '--font-body': FONT.sans,
  '--font-serif': FONT.serif,
  '--font-latin': FONT.latin,
  '--font-heavy': FONT.heavy,
  '--font-round': FONT.round,
  '--font-hand': FONT.hand,
  '--font-numeral': FONT.numeral,
  '--font-mono': FONT.mono,
});

/** 카드 조각(내부 HTML + 스코프 CSS) → 마운트할 문자열. .card 는 호스트(작성 캔버스)를 꽉 채운다 — 안 그러면 .root 의 height:100% 가 내용 높이가 된다 */
export const wrapCard = (card: CardSpec): string =>
  `<div class="card" data-card-id="${card.id}"><style>.card[data-card-id="${card.id}"]{position:absolute;left:0;top:0;width:100%;height:100%;overflow:hidden}` +
  `.card[data-card-id="${card.id}"] *{box-sizing:border-box}${card.css}</style>${card.html}</div>`;

const FAMILIES: [RegExp, string][] = [
  [/pretendard|--font-head|--font-body|--font-mono/i, 'Pretendard'],
  [/black han sans|--font-heavy/i, 'Black Han Sans'],
  [/jua|--font-round/i, 'Jua'],
  [/nanum pen script|--font-hand/i, 'Nanum Pen Script'],
  [/playfair display|--font-numeral/i, 'Playfair Display'],
  [/noto serif kr|--font-serif|serif/i, 'Noto Serif KR'],
  [/anton|--font-latin/i, 'Anton'],
];

const CardBody: React.FC<TemplateProps & {card: CardSpec}> = ({id, card, frame, fps, dur, box, theme, surface}) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const compiled = useRef<CompiledCard | null>(null);
  const [handle] = useState(() => delayRender(`card ${id}`));
  const released = useRef(false);
  const html = useMemo(() => wrapCard(card), [card]);
  const w = card.w || 1920;
  const h = card.h || 1080;
  const scale = Math.min(box.w / w, box.h / h);

  useLayoutEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    el.innerHTML = html;
    compiled.current = compileCard(gsap, el, {fps, duration: dur / fps});
    compiled.current.seek(frame / fps);
    // 카드 글꼴(분할 웹폰트 포함)이 이 글자들을 다 받을 때까지 첫 프레임을 멈춘다 — 조용한 폴백 글꼴 렌더 방지
    const text = el.textContent || '가';
    const fams = FAMILIES.filter(([re]) => re.test(card.css + card.html)).map(([, f]) => f);
    const release = () => {
      if (!released.current) {
        released.current = true;
        continueRender(handle);
      }
    };
    Promise.all(fams.flatMap((f) => ['400', '700'].map((wgt) => document.fonts.load(`${wgt} 40px "${f}"`, text))))
      .then(() => document.fonts.ready)
      .then(release, release);
    const t = setTimeout(release, 8000);
    return () => {
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
