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
  'scale-pop', 'blur-in', 'mask-reveal', 'morph-to', 'highlight', 'stagger-in', 'pulse',
  // GSAP 3.13+ 무료 플러그인(2026-10-04 채널 주인: "PPT 같다" — Jitter 수준의 움직임): 마스크 안에서 올라오는 어절·줄·글자
  // (SplitText), 선이 그려지는 도식(DrawSVG), 모양이 다른 모양으로 바뀜(MorphSVG), 경로를 따라 이동(MotionPath)
  'split-words', 'split-lines', 'split-chars', 'draw-svg', 'morph-svg', 'follow-path'];
const SEL_RE = /^[#.][A-Za-z][A-Za-z0-9_-]{0,40}$/;
let CE_N = 0; // CustomEase 이름은 전역이라 카드마다 겹치지 않게
/** SplitText 마스크 상자에 숨 쉴 자리를 준다 — 큰 제목의 글자 윗부분·아랫부분(받침·영문 디센더)이 상자에 잘리지 않게
 * 위아래 0.16em·좌우 0.06/0.12em 넓히고 같은 만큼 음수 여백으로 자리를 되돌린다(배치 불변). 검사(check.mjs)는 이 표시가 있는 상자를 잘림으로 보지 않는다. */
const markMasks = (parts) => {
  for (const p of parts || []) {
    const m = p && p.parentElement;
    if (!m || m.dataset.splitMask) continue;
    const cs = getComputedStyle(m);
    if (cs.overflow === 'visible' && cs.clipPath === 'none') continue;
    m.dataset.splitMask = '1';
    m.style.paddingTop = '0.16em';
    m.style.paddingBottom = '0.16em';
    m.style.marginTop = '-0.16em';
    m.style.marginBottom = '-0.16em';
    // 이탤릭(기울어진 글자)은 오른쪽으로 삐져나온다 — 좌우도 조금(2026-10-04 렌더: '30년'의 '년'이 잘림)
    m.style.paddingLeft = '0.06em';
    m.style.paddingRight = '0.12em';
    m.style.marginLeft = '-0.06em';
    m.style.marginRight = '-0.12em';
  }
};
const SPLIT_KEYS = ['type', 'mask', 'wordsClass', 'charsClass', 'linesClass', 'smartWrap', 'reduceWhiteSpace'];

const EASES = new Set(['power1.out', 'power2.out', 'power3.out', 'power4.out', 'power2.in', 'power2.inOut', 'power3.inOut',
  'expo.out', 'back.out(1.6)', 'back.out(1.2)', 'sine.inOut', 'sine.out', 'none']);

// 되튐 금지(2026-10-04 채널 주인: '바운시한 느낌은 싫다 — 떠다니듯 젠틀하게'). 디자이너가 back·elastic·bounce 나 되튀는 사용자
// 곡선을 써도 렌더에서는 부드러운 감속으로 바꾼다(검사·렌더가 같은 엔진이라 둘 다 같은 움직임)
const gentleEase = (e) => {
  if (typeof e !== 'string') return e;
  const s = e.toLowerCase();
  if (!/back|elastic|bounce|rough|steps/.test(s)) return e;
  if (s.includes('inout')) return 'power2.inOut';
  if (/\.in\b|\.in\(|\.in$/.test(s)) return 'power2.in';
  return 'power3.out';
};
const gentleVars = (v) => {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return v;
  const o = Object.assign({}, v);
  if ('ease' in o) o.ease = gentleEase(o.ease);
  if ('yoyoEase' in o) o.yoyoEase = typeof o.yoyoEase === 'string' ? gentleEase(o.yoyoEase) : o.yoyoEase;
  if (o.stagger && typeof o.stagger === 'object' && 'ease' in o.stagger) o.stagger = Object.assign({}, o.stagger, {ease: gentleEase(o.stagger.ease)});
  return o;
};
// 사용자 곡선(CustomEase 경로)의 y 가 0~1 밖이면 되튐 — 채널 곡선으로 바꾼다
const overshoots = (data) => {
  const nums = (data.match(/-?\d*\.?\d+(?:e-?\d+)?/gi) || []).map(Number);
  for (let i = 1; i < nums.length; i += 2) if (nums[i] > 1.0005 || nums[i] < -0.0005) return true;
  return false;
};
// tl 의 트윈 메서드를 감싸 되튐 이징을 고친다(체이닝도 감싼 쪽을 돌려준다)
const gentleTimeline = (tl) => {
  const wrap = new Proxy(tl, {
    get(target, prop) {
      const v = Reflect.get(target, prop);
      if (typeof v !== 'function') return v;
      if (prop === 'to' || prop === 'from') {
        return (t, vars, pos) => { const r = target[prop](t, gentleVars(vars), pos); return r === target ? wrap : r; };
      }
      if (prop === 'fromTo') {
        return (t, a, b, pos) => { const r = target.fromTo(t, gentleVars(a), gentleVars(b), pos); return r === target ? wrap : r; };
      }
      return (...args) => { const r = v.apply(target, args); return r === target ? wrap : r; };
    },
  });
  return wrap;
};

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
 * @param {{fps?: number, duration?: number, timeline?: string}} opts  timeline = 직접 쓴 GSAP 코드(fn(tl, q, gsap, ctx) 본문)
 * @returns {{timeline, duration, seek(t), kinds: string[], problems: string[]}}
 */
function compileCard(gsap, root, opts) {
  // libs = {SplitText, CustomEase, drawSVG, morphSVG, motionPath} — 호스트(HtmlCard·check.mjs)가 등록한 플러그인. 없으면 예전 방식으로 대체
  const libs = (opts && opts.libs) || {};
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
    return gentleEase(e && EASES.has(e) ? e : d);
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
        // 되튐 없이 떠오르듯(예전 0.6 → back.out)
        tl.fromTo(el, {opacity: 0, scale: 0.86, y: 14}, {...base, opacity: 1, scale: 1, y: 0, duration: Math.max(D, 0.7),
          ease: easeOf(el, 'power3.out')}, at);
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
      case 'split-words':
      case 'split-lines':
      case 'split-chars': {
        // 마스크(넘침 감춤) 안에서 아래로부터 올라온다 — 잘린 자리가 보이지 않아 '찍힌' 글자처럼 선다
        const unit = kind === 'split-words' ? 'words' : kind === 'split-lines' ? 'lines' : 'chars';
        let parts = [];
        if (libs.SplitText) {
          const sp = new libs.SplitText(el, {type: unit === 'lines' ? 'lines' : unit === 'words' ? 'words' : 'words,chars',
            mask: unit, aria: 'none'});
          parts = sp[unit] || [];
          markMasks(parts);
        } else {
          splitChars(el);
          parts = Array.from(el.querySelectorAll('.char'));
        }
        if (!parts.length) break;
        const st = clamp(num(el.dataset.animStagger, unit === 'chars' ? 0.025 : unit === 'words' ? 0.06 : 0.1), 0.005, 0.5);
        tl.fromTo(parts, {yPercent: 110, opacity: unit === 'chars' ? 0 : 1},
          {...base, yPercent: 0, opacity: 1, duration: D, ease: easeOf(el, 'expo.out'), stagger: st}, at);
        break;
      }
      case 'draw-svg': {
        const shapes = /^(path|line|polyline|polygon|circle|ellipse|rect)$/i.test(el.tagName) ? [el]
          : Array.from(el.querySelectorAll('path, line, polyline, polygon, circle, ellipse, rect'));
        if (!shapes.length) break;
        const origin = el.dataset.animOrigin || 'start';
        const from = origin === 'center' ? '50% 50%' : origin === 'end' ? '100% 100%' : '0% 0%';
        const st = clamp(num(el.dataset.animStagger, 0.08), 0, 0.5);
        if (libs.drawSVG) {
          tl.fromTo(shapes, {drawSVG: from}, {...base, drawSVG: '0% 100%', duration: D, ease: easeOf(el, 'power2.inOut'),
            stagger: st}, at);
        } else {
          shapes.forEach((p, k) => {
            let L = 1000;
            try {
              L = p.getTotalLength() || 1000;
            } catch (_e) {
              /* 레이아웃 전 */
            }
            tl.fromTo(p, {strokeDasharray: L, strokeDashoffset: L},
              {...base, strokeDashoffset: 0, duration: D, ease: easeOf(el, 'power2.inOut')}, at + k * st);
          });
        }
        break;
      }
      case 'morph-svg': {
        const sel = el.dataset.animTarget || '';
        const target = SEL_RE.test(sel) ? root.querySelector(sel) : null;
        if (!target) {
          problems.push('anim_morph_target_missing:' + sel);
          break;
        }
        if (libs.morphSVG) {
          tl.to(el, {...base, morphSVG: target, duration: D, ease: easeOf(el, 'power2.inOut')}, at);
        } else {
          tl.to(el, {...base, opacity: 0, duration: D / 2}, at).fromTo(target, {opacity: 0}, {...base, opacity: 1, duration: D / 2},
            at + D / 2);
        }
        break;
      }
      case 'follow-path': {
        const sel = el.dataset.animPath || '';
        const path = SEL_RE.test(sel) ? root.querySelector(sel) : null;
        if (!path) {
          problems.push('anim_path_missing:' + sel);
          break;
        }
        if (libs.motionPath) {
          tl.fromTo(el, {opacity: 0}, {...base, opacity: 1, duration: 0.2}, at);
          tl.fromTo(el, {motionPath: {path, align: path, alignOrigin: [0.5, 0.5], start: 0, end: 0}},
            {...base, motionPath: {path, align: path, alignOrigin: [0.5, 0.5], start: 0, end: 1},
              duration: D, ease: easeOf(el, 'power2.inOut')}, at);
        } else {
          tl.fromTo(el, {opacity: 0}, {...base, opacity: 1, duration: D, ease: easeOf(el, 'power2.out')}, at);
        }
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

  // 떠다니는 움직임(data-float="px", 선택 data-float-at · data-float-period): 등장이 끝난 뒤 카드 끝까지 느린 사인으로 오르내림·
  // 아주 작은 기울기. 요소마다 위상·주기를 달리해 함께 숨 쉬듯(같은 박자로 출렁이지 않게). 진폭 상한 14px(마지막 1초 검사 16px 아래)
  // 떠다니기·흩어짐은 자기 하위 타임라인에 — '정착'(등장이 끝나는 시각)을 잴 때 빼려고(카드 끝까지 이어지므로)
  const ambient = [];
  if (total) {
    const ft = gsap.timeline();
    tl.add(ft, 0);
    ambient.push(ft);
    Array.from(root.querySelectorAll('[data-float]')).forEach((el, i) => {
      if (el.classList.contains('card')) return;
      const amp = clamp(num(el.dataset.float, 6), 2, 14);
      const at0 = clamp(num(el.dataset.floatAt, 0.9), 0, Math.max(0, total - 0.5));
      const period = clamp(num(el.dataset.floatPeriod, 5.2 + (i % 4) * 0.55), 2.5, 12);
      const half = period / 2;
      const n = Math.max(1, Math.ceil((total - at0) / half));
      const dir = i % 2 ? -1 : 1;
      ft.to(el, {...base, y: `+=${(dir * amp).toFixed(1)}`, rotation: dir * Math.min(1.2, amp / 10), duration: half,
        ease: 'sine.inOut', yoyo: true, repeat: n - 1}, at0 + (i % 3) * 0.37);
      kinds.push('float');
    });
  }

  // 디자인 v4 — 모션 디자이너·시그니처 빌더가 직접 쓴 GSAP 타임라인(docs/디자인_v4_모던모션.md 6절, card_dsl.md 7절).
  // 같은 일시정지 타임라인 tl 위에만 트윈을 얹는다(seek 가 전부 제어 → 결정론). 전역·네트워크·시계·난수는 이름을 가려 undefined 로.
  if (opts && typeof opts.timeline === 'string' && opts.timeline.trim()) {
    runTimeline(gsap, gentleTimeline(tl), root, opts.timeline, {duration: opts.duration || 8, fps: opts.fps || 30,
      w: root.getBoundingClientRect().width, h: root.getBoundingClientRect().height}, problems, libs);
  }
  // 나가기 안무(LongForm 이 정한다 — opts.exit = {at, dur}): 요소들이 각자의 방향(화면 가운데에서 자기 자리 쪽)으로 흩어져
  // 화면 밖으로 날아간다. data-carry 요소(다음 장면이 같은 자리에서 이어 받는 요소)는 그대로 남는다. 페이드 겹침 없음 —
  // 투명도는 날아가는 끝에서만 내린다(2026-10-04 채널 주인: 'PPT 장면 전환·페이드되는 요소끼리 겹치는 것 금지')
  if (opts && opts.exit && opts.exit.dur > 0) {
    const et = gsap.timeline();
    tl.add(et, 0);
    ambient.push(et);
    scatterExit(et, root, Number(opts.exit.at) || 0, Number(opts.exit.dur));
  }
  const dur = tl.duration();
  // 정착: 떠다니기·흩어짐과 장식(aria-hidden — 뒤에 깔린 큰 연도의 느린 흐름 등)만 움직이는 트윈을 뺀 마지막 등장·강조가
  // 끝나는 시각(검수 스틸·읽기 시간·미리보기 칸이 쓴다)
  const decorOnly = (c) => typeof c.targets === 'function' && c.targets().length > 0
    && c.targets().every((t) => t && t.closest && t.closest('[aria-hidden="true"]'));
  let settle = 0;
  for (const c of tl.getChildren(false, true, true)) {
    if (!ambient.includes(c) && !decorOnly(c)) settle = Math.max(settle, c.endTime());
  }
  const seek = (t) => {
    const tt = clamp(t, 0, Math.max(dur, 0.0001));
    tl.pause(tt, true);
    // 시작 전 상태를 위해 0 으로도 한 번 렌더된 뒤 tt 로 — GSAP 은 pause(time) 에서 즉시 렌더한다
    for (const c of counters) c.el.textContent = fmtNumber(c.o.v, c.fmt, c.prefix, c.suffix);
  };
  return {timeline: tl, duration: dur, settle: Math.min(settle, dur), seek, kinds, problems};
}

/** 흩어지며 나가기: 보이는 단위(자기 글자·그림·채운 면이 있는 가장 바깥 요소)를 모아 화면 가운데에서 바깥 방향으로 날린다.
 *  화면의 55% 넘는 면(바탕)과 data-carry 는 남는다. 가운데 것부터 차례로(0.025초 간격), 가속(power3.in) — 되튐 없음. */
function scatterExit(tl, root, at, dur) {
  const R = root.getBoundingClientRect();
  if (!R.width || !R.height) return;
  const cx = R.left + R.width / 2;
  const cy = R.top + R.height / 2;
  const canvas = R.width * R.height;
  const isUnit = (el) => {
    if (el.closest('[data-carry]')) return false;
    const tag = el.tagName.toLowerCase();
    if (tag === 'style' || tag === 'br') return false;
    const r = el.getBoundingClientRect();
    if (r.width * r.height <= 4 || r.width * r.height > 0.55 * canvas) return false;
    if (tag === 'svg' || tag === 'img') return true;
    if (el.closest('svg') && tag !== 'svg') return false;      // SVG 안은 SVG 통째로
    if (Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.nodeValue.trim())) return true;
    const cs = getComputedStyle(el);
    const bg = cs.backgroundColor;
    return (bg && bg !== 'transparent' && !/rgba\([^)]*,\s*0\)$/.test(bg)) || cs.backgroundImage !== 'none';
  };
  const all = Array.from(root.querySelectorAll('*')).filter(isUnit);
  const set = new Set(all);
  const units = all.filter((el) => { for (let p = el.parentElement; p && p !== root; p = p.parentElement) if (set.has(p)) return false; return true; });
  const items = units.map((el) => {
    const r = el.getBoundingClientRect();
    return {el, x: r.left + r.width / 2 - cx, y: r.top + r.height / 2 - cy, size: Math.max(r.width, r.height)};
  }).sort((a, b) => Math.hypot(a.x, a.y) - Math.hypot(b.x, b.y));
  items.forEach((it, i) => {
    let vx = it.x;
    let vy = it.y;
    let n = Math.hypot(vx, vy);
    if (n < 8) { vx = Math.cos(i * 2.399); vy = Math.sin(i * 2.399); n = 1; }   // 가운데 것은 황금각으로 방향을 나눈다
    vx /= n; vy /= n;
    const dist = 0.55 * Math.max(R.width, R.height) + it.size * 0.6;
    const t0 = at + Math.min(0.25, i * 0.025);
    const d = Math.max(0.2, dur - (t0 - at));
    const rot = ((i * 37) % 17 - 8) * 1.2;
    tl.to(it.el, {x: `+=${(vx * dist).toFixed(1)}`, y: `+=${(vy * dist).toFixed(1)}`, rotation: `+=${rot.toFixed(1)}`,
      scale: 0.92, duration: d, ease: 'power3.in', lazy: false, immediateRender: false}, t0);
    tl.to(it.el, {opacity: 0, duration: d * 0.3, ease: 'power1.in', lazy: false, immediateRender: false}, t0 + d * 0.7);
  });
}

/** 자유 타임라인 실행: fn(tl, q, gsap, ctx). q(sel) = 카드 안 요소 배열, gsap = 안전한 부분집합(utils·parseEase·nested timeline). */
function runTimeline(gsapLib, tl, root, code, ctx, problems, libs) {
  libs = libs || {};
  const q = (sel) => Array.from(root.querySelectorAll(sel));
  const targets = (t) => (typeof t === 'string' ? q(t) : Array.isArray(t) ? t : t ? [t] : []);
  const utils = {};
  for (const k of ['interpolate', 'mapRange', 'clamp', 'wrap', 'wrapYoyo', 'snap', 'normalize', 'pipe', 'unitize', 'toArray',
    'distribute', 'splitColor', 'getUnit', 'selector']) {
    if (gsapLib.utils && typeof gsapLib.utils[k] === 'function') utils[k] = gsapLib.utils[k];
  }
  const safe = {
    utils,
    parseEase: gsapLib.parseEase,
    // gsap.timeline() 은 부모 tl 에 붙은 하위 타임라인을 돌려준다(따로 돌아가는 전역 타임라인 금지)
    timeline: (vars) => {
      const v = Object.assign({}, vars || {});
      const at = v.at;
      delete v.at;
      delete v.onUpdate; delete v.onComplete; delete v.onStart; delete v.onRepeat;
      const sub = gsapLib.timeline(gentleVars(v.defaults ? Object.assign(v, {defaults: gentleVars(v.defaults)}) : v));
      tl.add(sub, at === undefined ? '+=0' : at);
      return gentleTimeline(sub);
    },
    to: (t, v, p) => tl.to(t, gentleVars(v), p), from: (t, v, p) => tl.from(t, gentleVars(v), p),
    fromTo: (t, a, b, p) => tl.fromTo(t, gentleVars(a), gentleVars(b), p), set: (...a) => tl.set(...a),
    // SplitText: gsap.splitText('.headline', {type: 'words', mask: 'words'}) → {chars, words, lines}(카드 안 요소만, 콜백 옵션 없음)
    splitText: (t, vars) => {
      const els = targets(t);
      const v = {aria: 'none'};
      for (const k of SPLIT_KEYS) if (vars && vars[k] !== undefined) v[k] = vars[k];
      if (!libs.SplitText || !els.length) {
        problems.push('timeline_split_unavailable');
        return {chars: [], words: els, lines: els};
      }
      const sp = new libs.SplitText(els, v);
      if (v.mask) markMasks(sp[v.mask] || []);
      return {chars: sp.chars || [], words: sp.words || [], lines: sp.lines || []};
    },
    // CustomEase: gsap.customEase('M0,0 C0.2,0 0.1,1 1,1') → ease 이름(트윈의 ease 에 그대로)
    customEase: (data) => {
      if (!libs.CustomEase || typeof data !== 'string' || data.length > 400) return 'power2.out';
      if (overshoots(data)) return 'power3.out';      // 되튀는 곡선은 쓰지 않는다
      const id = 'choiEase' + (CE_N++);
      libs.CustomEase.create(id, data);
      return id;
    },
    // drawSVG · morphSVG · motionPath 는 트윈 값으로 쓴다(tl.fromTo(q('path'), {drawSVG: '0%'}, {drawSVG: '100%'}))
    plugins: {drawSVG: Boolean(libs.drawSVG), morphSVG: Boolean(libs.morphSVG), motionPath: Boolean(libs.motionPath)},
  };
  const before = tl.getChildren(true, true, true).length;   // 길이가 아니라 트윈 수로 — 기존 길이 안에 얹은 트윈도 '추가'다
  try {
    // strict 모드에서는 'eval'·'arguments' 를 매개변수 이름으로 못 쓴다 — eval 은 정화 단계(card.py TIMELINE_FORBIDDEN)가 막는다
    const fn = new Function('tl', 'q', 'gsap', 'ctx', 'window', 'document', 'globalThis', 'self', 'fetch', 'XMLHttpRequest',
      'WebSocket', 'setTimeout', 'setInterval', 'requestAnimationFrame', 'Function', 'Date', 'location', 'navigator',
      'localStorage', 'parent', 'top', "'use strict';\n" + code);
    fn(tl, q, safe, ctx);
  } catch (e) {
    problems.push('timeline_runtime_error:' + String(e && e.message ? e.message : e).slice(0, 160));
    return;
  }
  // 콜백 트윈은 결정론을 깬다 — 혹시 들어왔으면 떼어 낸다
  for (const child of tl.getChildren(true, true, true)) {
    const v = child.vars || {};
    for (const k of ['onUpdate', 'onComplete', 'onStart', 'onRepeat', 'onReverseComplete']) {
      if (v[k]) {
        v[k] = null;
        problems.push('timeline_callback_removed:' + k);
      }
    }
  }
  if (tl.getChildren(true, true, true).length === before) problems.push('timeline_added_nothing');
  tl.pause(0, true);
}

export {compileCard, KINDS as CARD_ANIM_KINDS};
