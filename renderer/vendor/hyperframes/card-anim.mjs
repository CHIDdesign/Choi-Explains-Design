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
  'stroke', 'xPercent', 'yPercent', 'clipPath', 'backgroundSize', 'borderColor', 'boxShadow']);

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

/** 결정적 난수 — renderer/src/components/paper/Paper.tsx seeded 와 같은 수열 */
const seeded = (seed) => {
  let s = (Math.floor(seed * 9973) ^ 0x5bd1e995) >>> 0 || 1;
  return () => {
    s ^= s << 13;
    s >>>= 0;
    s ^= s >>> 17;
    s ^= s << 5;
    s >>>= 0;
    return s / 4294967296;
  };
};

/** 값 노이즈 n 개(주기 period 칸) */
const noise1 = (r, n, period) => {
  const c = Array.from({length: Math.ceil(n / period) + 3}, () => r());
  return Array.from({length: n}, (_, i) => {
    const u = i / period;
    const a = Math.floor(u);
    const t = u - a;
    return c[a] + (c[a + 1] - c[a]) * t * t * (3 - 2 * t);
  });
};

/**
 * 찢긴 종이의 윤곽: outer(섬유 단면의 바깥선) · mid(섬유가 겉장으로 스미는 선) · inner(겉장이 끝나는 선). 찢긴 변만 흔들리고 나머지는 재단선 그대로.
 * 파인 곳은 안쪽으로만 — 종이 상자 밖으로 나가지 않는다. 섬유 폭은 2~fibre px 로 구간마다 다르다 — 폭이 고르면 흰 획으로 보인다.
 * 변 끝 20px 에서 흔들림이 0 으로 모인다 — 옆 변과 어긋나 모서리에 뿔이 나지 않게.
 */
const tornPaths = (w, h, torn, seed, amp = 11, fibre = Math.min(14, amp * 1.4)) => {
  const outer = [];
  const mid = [];
  const inner = [];
  const side = (x0, y0, x1, y1, nx, ny, on, s) => {
    const len = Math.hypot(x1 - x0, y1 - y0);
    if (!on) {
      for (const l of [outer, mid, inner]) l.push(`${x0} ${y0}`);
      return;
    }
    const r = seeded(seed * 7 + s);
    const n = Math.max(3, Math.round(len / 3) + 1);
    const a = noise1(r, n, Math.max(9, Math.min(42, n * 0.34)));   // 짧은 변에서도 굴곡이 한두 번은 보이게
    const b = noise1(r, n, 9);
    const c = noise1(r, n, 3);
    const d = noise1(r, n, 13);
    const e = noise1(r, n, 3);
    for (let i = 0; i < n; i++) {
      const t = i / (n - 1);
      const end = Math.min(1, (Math.min(t, 1 - t) * len) / 20);
      const o = amp * (a[i] * 0.6 + b[i] * 0.28 + c[i] * 0.12) * end;
      const q = (Math.min(2, fibre) + Math.max(0, fibre - 2) * clamp((d[i] - 0.25) / 0.5, 0, 1) ** 1.3 * (0.75 + 0.25 * e[i])) * end;
      const x = x0 + (x1 - x0) * t;
      const y = y0 + (y1 - y0) * t;
      const at = (v) => `${(x + nx * v).toFixed(1)} ${(y + ny * v).toFixed(1)}`;
      outer.push(at(o));
      mid.push(at(o + q * 0.5));
      inner.push(at(o + q));
    }
  };
  side(0, 0, w, 0, 0, 1, torn.top, 1);
  side(w, 0, w, h, -1, 0, torn.right, 2);
  side(w, h, 0, h, 0, -1, torn.bottom, 3);
  side(0, h, 0, 0, 1, 0, torn.left, 4);
  const d = (l) => `M ${l.join(' L ')} Z`;
  return {outer: d(outer), mid: d(mid), inner: d(inner)};
};

// 재질(card_dsl.md): data-surface · data-torn · data-tape. 텍스처는 미리 구운 파일이라 저자 CSS 의 url() 금지는 그대로다.
// 색은 material/Texture.tsx FLAT 과 같다 — 파일을 못 읽어도 렌더는 간다
const SURFACES = {eggshell: '#F4F3EE', parchment: '#EFE9DC', memo: '#FBF9F3', kraft: '#B89B72', graph: '#F2F2EA', newsprint: '#DED6C2',
  desk: '#262220'};

function applySurfaces(root, url) {
  const W = root.offsetWidth || 1920;
  const H = root.offsetHeight || 1080;
  Array.from(root.querySelectorAll('[data-surface]')).forEach((el, i) => {
    const name = el.dataset.surface;
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    if (!SURFACES[name] || !w || !h) return;
    const seed = i + 1;
    const tex = (n, sd) => {
      const k = Math.max(1, w / 1920, h / 1080);
      const r = seeded(sd + 0.5);
      return {backgroundColor: SURFACES[n], backgroundImage: url ? `url("${url(n)}")` : 'none', backgroundRepeat: 'no-repeat',
        backgroundSize: `${1920 * k}px ${1080 * k}px`,
        backgroundPosition: `${-Math.round((1920 * k - w) * r())}px ${-Math.round((1080 * k - h) * r())}px`};
    };
    if (w >= 0.9 * W && h >= 0.9 * H) {          // 카드 전체를 덮는 바탕 — 들뜨지 않는다
      Object.assign(el.style, tex(name, seed));
      return;
    }
    if (getComputedStyle(el).position === 'static') el.style.position = 'relative';
    el.dataset.sheet = '1';
    el.style.isolation = 'isolate';              // 글자 아래(z-index −1)에 재질 층을 깐다
    const layer = (style) => {
      const d = document.createElement('div');
      d.dataset.mat = '1';
      Object.assign(d.style, {position: 'absolute', inset: '0', zIndex: '-1', pointerEvents: 'none'}, style);
      return d;
    };
    const layers = [];
    const edges = (el.dataset.torn || '').split(/\s+/).filter(Boolean);
    if (edges.length) {
      const p = tornPaths(w, h, Object.fromEntries(edges.map((e) => [e, true])), seed);
      el.style.filter = 'var(--lift-drop-2)';
      layers.push(layer({...tex('memo', seed + 2), backgroundColor: '#EFE6D2', backgroundBlendMode: 'multiply', clipPath: `path('${p.outer}')`}),
        layer({...tex(name, seed), clipPath: `path('${p.mid}')`, opacity: '0.45'}),
        layer({...tex(name, seed), clipPath: `path('${p.inner}')`}));
    } else {
      // 아래 모서리가 들려 그림자가 벌어진다 — 평면 카드처럼 보이지 않게
      const corner = (side, deg) => layer({inset: 'auto', [side]: '10px', bottom: '10px', width: '46%', height: '26px', rotate: `${deg}deg`,
        boxShadow: '0 18px 20px rgba(34,30,26,0.36)'});
      layers.push(corner('left', -1.6), corner('right', 1.6), layer({...tex(name, seed), boxShadow: 'var(--lift-2)'}));
    }
    el.prepend(...layers);
    if ('tape' in el.dataset) {
      const r = seeded(seed + 0.3);
      const teeth = (edge, dir) => Array.from({length: 7}, (_, k) =>
        `${(edge + dir * (k % 2 ? 1.5 + r() * 2.2 : r() * 0.8)).toFixed(1)}% ${(k / 6 * 100).toFixed(1)}%`);
      const tw = clamp(w * 0.3, 96, 190);
      const t = document.createElement('div');
      t.dataset.mat = '1';
      Object.assign(t.style, {position: 'absolute', left: `${(w - tw) / 2 + (r() - 0.5) * w * 0.12}px`, top: '-20px', width: `${tw}px`, height: '40px',
        rotate: `${-4 + r() * 8}deg`, opacity: '0.72', mixBlendMode: 'multiply', pointerEvents: 'none'});
      const face = document.createElement('div');
      face.dataset.mat = '1';
      Object.assign(face.style, {position: 'absolute', inset: '0', clipPath: `polygon(${[...teeth(0, 1), ...teeth(100, -1).reverse()].join(', ')})`,
        background: '#FC5400'});
      t.append(face);
      el.append(t);
    }
  });
}

/**
 * @param gsap  GSAP 전역(모듈 import 또는 window.gsap)
 * @param root  카드 루트(.card) 또는 그 조상
 * @param {{fps?: number, duration?: number, timeline?: string, surfaceUrl?: (name: string) => string}} opts  timeline = 직접 쓴 GSAP 코드(fn(tl, q, gsap, ctx) 본문)
 * @returns {{timeline, duration, seek(t), kinds: string[], problems: string[]}}
 */
function compileCard(gsap, root, opts) {
  applySurfaces(root, opts && opts.surfaceUrl);
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
        tl.fromTo(el, {opacity: 0, y: 14, filter: 'blur(8px)'}, {...base, opacity: 1, y: 0, filter: 'blur(0px)', duration: D,
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
        const kids = Array.from(el.children).filter((c) => !c.dataset.mat);
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

  // 한 세계 + 카메라(Promptible remotion-motion-graphics-skill 'cinematic-camera' 의 문법 — MIT; 코드는 우리 것):
  // 패널이 허공에 하나씩 뜨는 대신 캔버스보다 큰 장면 하나([data-world])를 짓고 카메라가 그 위를 움직인다.
  // data-camera='[{"t":0,"x":960,"y":540,"z":1.6}, {"t":1.8,"x":960,"y":540,"z":1.6}, {"t":3,"x":2300,"y":540,"z":0.7}, …]'
  // (t 초 · x,y = 초점의 세계 좌표 px · z = 배율). 같은 자리의 키가 이어지면 홀드, 바뀌면 그 사이 이동(power2.inOut).
  // 세계 요소의 변환: translate(W/2 − x·z, H/2 − y·z) scale(z), 원점 0 0 → 초점이 캔버스 가운데에 온다.
  const world = root.querySelector('[data-world]');
  if (world) {
    const keys = parseCamera(world.dataset.camera, problems);
    if (keys.length) {
      const W = root.offsetWidth || 1920;
      const H = root.offsetHeight || 1080;
      const ease = gentleEase(world.dataset.cameraEase && EASES.has(world.dataset.cameraEase) ? world.dataset.cameraEase : 'power2.inOut');
      const at = (k) => ({x: W / 2 - k.x * k.z, y: H / 2 - k.y * k.z, scale: k.z});
      tl.set(world, {...base, transformOrigin: '0 0', ...at(keys[0])}, 0);
      for (let k = 1; k < keys.length; k++) {
        const a = keys[k - 1];
        const b = keys[k];
        const d = Math.max(1 / fps, q(b.t) - q(a.t));
        if (a.x === b.x && a.y === b.y && a.z === b.z) continue;     // 홀드
        tl.to(world, {...base, ...at(b), duration: d, ease}, q(a.t));
      }
      kinds.push('camera');
    }
  }

  // 디자인 v4 — 모션 디자이너·시그니처 빌더가 직접 쓴 GSAP 타임라인(docs/디자인_v4_모던모션.md 6절, card_dsl.md 7절).
  // 같은 일시정지 타임라인 tl 위에만 트윈을 얹는다(seek 가 전부 제어 → 결정론). 전역·네트워크·시계·난수는 이름을 가려 undefined 로.
  if (opts && typeof opts.timeline === 'string' && opts.timeline.trim()) {
    runTimeline(gsap, gentleTimeline(tl), root, opts.timeline, {duration: opts.duration || 8, fps: opts.fps || 30,
      w: root.getBoundingClientRect().width, h: root.getBoundingClientRect().height}, problems, libs);
  }
  const dur = tl.duration();
  // 정착: 장식(aria-hidden)만 움직이는 트윈을 뺀 마지막 등장·강조가
  // 끝나는 시각(검수 스틸·읽기 시간·미리보기 칸이 쓴다)
  const decorOnly = (c) => typeof c.targets === 'function' && c.targets().length > 0
    && c.targets().every((t) => t && t.closest && t.closest('[aria-hidden="true"]'));
  let settle = 0;
  for (const c of tl.getChildren(false, true, true)) {
    if (!decorOnly(c)) settle = Math.max(settle, c.endTime());
  }
  const seek = (t) => {
    const tt = clamp(t, 0, Math.max(dur, 0.0001));
    tl.pause(tt, true);
    // 시작 전 상태를 위해 0 으로도 한 번 렌더된 뒤 tt 로 — GSAP 은 pause(time) 에서 즉시 렌더한다
    for (const c of counters) c.el.textContent = fmtNumber(c.o.v, c.fmt, c.prefix, c.suffix);
  };
  return {timeline: tl, duration: dur, settle: Math.min(settle, dur), seek, kinds, problems};
}

/** data-camera 키 목록 → [{t, x, y, z}] (시간순, 범위 안으로 — 잘못된 JSON·모양이면 problems 에 적고 빈 배열). studio/motion/card.py
 *  clean_camera 와 같은 범위. 16개까지. */
function parseCamera(raw, problems) {
  if (!raw) return [];
  let arr;
  try {
    arr = JSON.parse(raw);
  } catch (_e) {
    problems.push('anim_camera_invalid:json');
    return [];
  }
  if (!Array.isArray(arr)) {
    problems.push('anim_camera_invalid:not_list');
    return [];
  }
  const keys = [];
  for (const k of arr.slice(0, 16)) {
    if (!k || typeof k !== 'object') continue;
    keys.push({t: clamp(num(k.t, 0), 0, 60), x: clamp(num(k.x, 0), -20000, 20000), y: clamp(num(k.y, 0), -20000, 20000),
      z: clamp(num(k.z, 1), 0.25, 4)});
  }
  keys.sort((a, b) => a.t - b.t);
  if (keys.length < 2) problems.push('anim_camera_invalid:needs_two_keys');
  return keys.length >= 2 ? keys : [];
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

export {compileCard, parseCamera, tornPaths, KINDS as CARD_ANIM_KINDS};
