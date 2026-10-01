/*
 * data-anim 선언 → GSAP 일시정지 타임라인 (HyperFrames talking-head-recut 카드 규약, NOTICE.md 참고)
 *
 * 이 파일은 두 곳에서 쓴다.
 *  1) Remotion 컴포넌트(HtmlCard.tsx)가 ESM 으로 import
 *  2) 렌더 전 검사(scripts/check.mjs)가 헤드리스 Chrome 페이지에 고전 스크립트로 주입(마지막 export 줄만 떼어 냄)
 * 그래서 import 가 없고, gsap 은 인자로 받는다.
 *
 * 결정론: 모든 트윈은 lazy:false, 타임라인은 paused, 값은 seek(t) 로만 정해진다. count-up 은 콜백 대신 seek 뒤에 직접 쓴다.
 */

const KINDS = ['fade-in', 'fade-out', 'slide-in', 'kinetic-chars', 'typewriter', 'count-up', 'draw-path', 'grow-x', 'grow-y',
  'scale-pop', 'blur-in', 'mask-reveal', 'morph-to', 'highlight', 'stagger-in', 'pulse'];

const EASES = new Set(['power1.out', 'power2.out', 'power3.out', 'power4.out', 'power2.in', 'power2.inOut', 'power3.inOut',
  'expo.out', 'back.out(1.6)', 'back.out(1.2)', 'sine.inOut', 'none']);

// morph-to 가 건드릴 수 있는 속성(레이아웃을 깨거나 스크립트를 부르는 것은 막는다)
const MORPH_KEYS = new Set(['x', 'y', 'scale', 'scaleX', 'scaleY', 'rotate', 'opacity', 'width', 'height', 'backgroundColor',
  'color', 'letterSpacing', 'borderRadius', 'filter', 'left', 'top', 'padding', 'fontSize', 'strokeDashoffset', 'fill',
  'stroke', 'skewX', 'skewY', 'xPercent', 'yPercent', 'clipPath', 'backgroundSize', 'borderColor', 'boxShadow']);

const num = (v, d) => {
  const f = parseFloat(v);
  return Number.isFinite(f) ? f : d;
};
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

const fmtNumber = (v, fmt, prefix, suffix) => {
  let s;
  if (fmt === ',d') s = Math.round(v).toLocaleString('en-US');
  else if (/^\.\dg?f$/.test(fmt || '')) s = v.toFixed(parseInt(fmt[1], 10));
  else s = String(Math.round(v));
  return (prefix || '') + s + (suffix || '');
};

/** kinetic-chars / typewriter 용: 글자마다 <span class="char"> 로 감싼다(이미 .char 가 있으면 그대로). 공백은 남긴다. */
const splitChars = (el) => {
  if (el.querySelector('.char')) return;
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const n of nodes) {
    const text = n.nodeValue || '';
    if (!text.trim()) continue;
    const frag = document.createDocumentFragment();
    for (const ch of Array.from(text)) {
      if (/\s/.test(ch)) {
        frag.appendChild(document.createTextNode(ch));
      } else {
        const s = document.createElement('span');
        s.className = 'char';
        s.style.display = 'inline-block';
        s.textContent = ch;
        frag.appendChild(s);
      }
    }
    n.parentNode.replaceChild(frag, n);
  }
};

/**
 * @param gsap  GSAP 전역(모듈 import 또는 window.gsap)
 * @param root  카드 루트(.card) 또는 그 조상
 * @param opts  {fps, duration}
 * @returns {{timeline, duration, seek(t), kinds: string[], problems: string[]}}
 */
function compileCard(gsap, root, opts) {
  const fps = (opts && opts.fps) || 30;
  const total = (opts && opts.duration) || 0;
  const q = (t) => Math.round(t * fps) / fps;
  const tl = gsap.timeline({paused: true});
  const counters = [];
  const kinds = [];
  const problems = [];
  const base = {lazy: false};
  const easeOf = (el, d) => {
    const e = el.dataset.animEase;
    return e && EASES.has(e) ? e : d;
  };

  const els = Array.from(root.querySelectorAll('[data-anim]'));
  els.forEach((el, i) => {
    const kind = el.dataset.anim;
    if (!KINDS.includes(kind)) {
      problems.push(`anim_unknown_kind:${kind}`);
      return;
    }
    const at = q(clamp(num(el.dataset.animAt, 0), 0, 60));
    const D = clamp(num(el.dataset.animDuration, 0.5), 0.05, 4);
    const stagger = clamp(num(el.dataset.animStagger, kind === 'typewriter' ? 0.06 : 0.04), 0.005, 0.5);
    kinds.push(kind);
    if (total && at > total + 0.01) problems.push(`anim_starts_after_card_end:${kind}@${at.toFixed(2)}`);
    // .card 루트 자체는 호스트(React)가 등장·퇴장을 맡는다 — 카드 안 요소만 움직인다
    if (el.classList.contains('card')) {
      problems.push('anim_on_card_root');
      return;
    }
    switch (kind) {
      case 'fade-in':
        tl.fromTo(el, {opacity: 0}, {...base, opacity: 1, duration: D, ease: easeOf(el, 'power2.out')}, at);
        break;
      case 'fade-out':
        tl.to(el, {...base, opacity: 0, duration: D, ease: easeOf(el, 'power2.in')}, at);
        break;
      case 'slide-in': {
        const from = el.dataset.animFrom || 'left';
        const dist = clamp(num(el.dataset.animDistance, 80), 0, 600);
        const v = from === 'left' ? {x: -dist} : from === 'right' ? {x: dist} : from === 'top' ? {y: -dist} : {y: dist};
        tl.fromTo(el, {opacity: 0, ...v}, {...base, opacity: 1, x: 0, y: 0, duration: D, ease: easeOf(el, 'power2.out')}, at);
        break;
      }
      case 'kinetic-chars':
      case 'typewriter': {
        splitChars(el);
        const chars = el.querySelectorAll('.char');
        if (!chars.length) break;
        const pop = kind === 'kinetic-chars' && (el.dataset.animPattern || 'pop') === 'pop';
        tl.fromTo(chars, pop ? {opacity: 0, y: 8, scale: 0.8} : {opacity: 0},
          {...base, opacity: 1, y: 0, scale: 1, duration: D, ease: easeOf(el, 'power2.out'), stagger}, at);
        break;
      }
      case 'count-up': {
        const from = num(el.dataset.animFrom, 0);
        const to = num(el.dataset.animTo, num(el.textContent, 100));
        const fmt = el.dataset.animFormat || '.0f';
        const prefix = el.dataset.animPrefix || '';
        const suffix = el.dataset.animSuffix || '';
        const o = {v: from};
        el.textContent = fmtNumber(from, fmt, prefix, suffix);
        tl.to(o, {...base, v: to, duration: D, ease: easeOf(el, 'power2.out')}, at);
        counters.push({el, o, fmt, prefix, suffix});
        break;
      }
      case 'draw-path': {
        const paths = el.tagName.toLowerCase() === 'path' ? [el] : Array.from(el.querySelectorAll('path'));
        for (const p of paths) {
          let L = 1000;
          try {
            L = p.getTotalLength() || 1000;
          } catch (_e) {
            /* 아직 레이아웃 전 */
          }
          tl.fromTo(p, {strokeDasharray: L, strokeDashoffset: L},
            {...base, strokeDashoffset: 0, duration: D, ease: easeOf(el, 'power2.inOut')}, at);
        }
        break;
      }
      case 'grow-x': {
        const w = clamp(num(el.dataset.animTargetW, el.getBoundingClientRect().width || 200), 0, 4000);
        tl.fromTo(el, {width: 0}, {...base, width: w, duration: D, ease: easeOf(el, 'power2.out')}, at);
        break;
      }
      case 'grow-y': {
        const h = clamp(num(el.dataset.animTargetH, el.getBoundingClientRect().height || 200), 0, 4000);
        tl.fromTo(el, {height: 0}, {...base, height: h, duration: D, ease: easeOf(el, 'power2.out')}, at);
        break;
      }
      case 'scale-pop':
        tl.fromTo(el, {opacity: 0, scale: 0.6}, {...base, opacity: 1, scale: 1, duration: D, ease: easeOf(el, 'back.out(1.6)')}, at);
        break;
      case 'blur-in':
        tl.fromTo(el, {opacity: 0, filter: 'blur(14px)'}, {...base, opacity: 1, filter: 'blur(0px)', duration: D,
          ease: easeOf(el, 'power2.out')}, at);
        break;
      case 'mask-reveal': {
        const dir = el.dataset.animDirection || 'left';
        const from = dir === 'left' ? 'inset(0 100% 0 0)' : dir === 'right' ? 'inset(0 0 0 100%)'
          : dir === 'top' ? 'inset(0 0 100% 0)' : 'inset(100% 0 0 0)';
        tl.fromTo(el, {clipPath: from}, {...base, clipPath: 'inset(0 0 0 0)', duration: D, ease: easeOf(el, 'power2.inOut')}, at);
        break;
      }
      case 'morph-to': {
        let props = {};
        try {
          props = JSON.parse(el.dataset.animProps || '{}');
        } catch (_e) {
          problems.push('anim_morph_props_invalid_json');
          break;
        }
        const safe = {};
        for (const k of Object.keys(props || {})) {
          if (MORPH_KEYS.has(k) && (typeof props[k] === 'number' || typeof props[k] === 'string')) safe[k] = props[k];
        }
        if (Object.keys(safe).length) tl.to(el, {...base, ...safe, duration: D, ease: easeOf(el, 'power2.inOut')}, at);
        break;
      }
      case 'highlight': {
        // 형광펜: 배경 그라데이션이 왼쪽에서 채워진다. 요소에 배경이 없으면 채널 강조색으로 깐다.
        const cs = getComputedStyle(el);
        if (!cs.backgroundImage || cs.backgroundImage === 'none') {
          el.style.backgroundImage = 'linear-gradient(transparent 58%, var(--accent-soft, rgba(232, 104, 44, 0.35)) 58%)';
        }
        el.style.backgroundRepeat = 'no-repeat';
        el.style.webkitBoxDecorationBreak = 'clone';
        el.style.boxDecorationBreak = 'clone';
        tl.fromTo(el, {backgroundSize: '0% 100%'}, {...base, backgroundSize: '100% 100%', duration: D,
          ease: easeOf(el, 'power2.inOut')}, at);
        break;
      }
      case 'stagger-in': {
        const kids = Array.from(el.children);
        if (!kids.length) break;
        tl.fromTo(kids, {opacity: 0, y: 18}, {...base, opacity: 1, y: 0, duration: D, ease: easeOf(el, 'power2.out'),
          stagger: clamp(num(el.dataset.animStagger, 0.09), 0.02, 0.6)}, at);
        break;
      }
      case 'pulse':
        tl.fromTo(el, {scale: 1}, {...base, scale: clamp(num(el.dataset.animScale, 1.05), 1, 1.3), duration: D / 2,
          ease: 'sine.inOut', yoyo: true, repeat: 1}, at);
        break;
      default:
        break;
    }
    void i;
  });

  const dur = tl.duration();
  const seek = (t) => {
    const tt = clamp(t, 0, Math.max(dur, 0.0001));
    tl.pause(tt, true);
    // 시작 전 상태를 위해 0 으로도 한 번 렌더된 뒤 tt 로 — GSAP 은 pause(time) 에서 즉시 렌더한다
    for (const c of counters) c.el.textContent = fmtNumber(c.o.v, c.fmt, c.prefix, c.suffix);
  };
  return {timeline: tl, duration: dur, seek, kinds, problems};
}

export {compileCard, KINDS as CARD_ANIM_KINDS};
