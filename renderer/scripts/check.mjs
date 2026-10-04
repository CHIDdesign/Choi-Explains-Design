// 자유 HTML 카드의 렌더 전 검사(HyperFrames `check` 의 우리 판 — renderer/vendor/hyperframes/NOTICE.md).
//   node scripts/check.mjs <job.json>
// job.json:
// {
//   "browserExecutable": "", "gl": "",
//   "outDir": "<하네스 HTML·결과를 둘 폴더>",
//   "cards": [{"id": "g3", "html": "<.card 안쪽>", "css": "<스코프 CSS>", "w": 1920, "h": 1080, "fps": 30,
//              "duration": 7.0, "settle": 3.1, "layout": "fullscreen", "text": "…"}]
// }
// 카드마다 실제 Chrome(렌더와 같은 것)에 붙여 settle 시각으로 seek 한 뒤 검사한다:
//   runtime_error · anim_*(컴파일러) · font_not_loaded · font_family_not_bundled · text_overflow · outside_canvas ·
//   text_too_small · low_contrast. 결과는 stdout 에 JSON 한 줄씩({"type":"card", ...}) 과 outDir/check.json.
//   걸린 카드는 정착 시각의 화면을 outDir/<id>.jpg 로 찍어 `shot` 에 넘긴다(카드 디자이너가 보고 고친다).
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL, fileURLToPath} from 'node:url';
import {openBrowser} from '@remotion/renderer';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const emit = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');

const MIN_FONT_PX = 28; // 라벨 최소(docs/upgrade/06 4-1 · 7-2 — 예전 26)
const FIRST_FRAME_SHARE = 0.35; // 게이트 C4: 0.5초 프레임의 잉크 ≥ 정착 프레임의 35%
const CAPTION_ZONE_PX = 170; // 전체 화면·오버레이 카드 아래 자막 자리(LongCaptions paper 상자가 y≈920–1000 에 놓인다)
const CONTRAST_BODY = 4.5;
const CONTRAST_LARGE = 3.0;

// HtmlCard.tsx cardVars(디자인 v4)와 같은 값 — 검사와 렌더의 글꼴·색이 다르면 넘침·대비 판정이 틀린다
// (2026-10-04: 여기만 v3(제목 고운바탕·크림 흰색·옛 주황)로 남아 있었다). 테마는 ember(#FC5400) 기준
const SANS = '"Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif';
const ITALIC = '"Instrument Serif", "Playfair Display", serif';
const vars = {
  '--bg': '#F7F8F6', '--paper': '#F7F8F6', '--paper-line': 'rgba(18,19,21,0.10)', '--ink': '#121315', '--ink-soft': '#1C1C1C',
  '--muted': 'rgba(28, 28, 28, 0.7)', '--accent': '#FC5400', '--accent-deep': '#D94600', '--accent-light': '#FD732E',
  '--accent-soft': 'rgba(252, 84, 0, 0.32)', '--board': '#1A1C1B', '--board-edge': '#2A2D2B', '--chalk': '#F1ECDD',
  '--chalk-dim': 'rgba(241, 236, 221, 0.58)', '--white': '#FFFFFF',
  '--font-head': SANS, '--font-body': SANS, '--font-serif': SANS, '--font-latin': SANS, '--font-editorial': SANS,
  '--font-poster': SANS, '--font-italic': ITALIC, '--font-heavy': SANS, '--font-round': SANS, '--font-hand': ITALIC,
  '--font-numeral': ITALIC, '--font-mono': SANS,
};

const fontFaces = () => {
  // 번들 원본(assets/fonts, npm postinstall 이 채움)에서 읽는다 — public/fonts 는 렌더 번들 단계가 만드니 첫 실행의 카드 검사 때는 없다(2026-10-02 실제 실행에서 발견)
  const pub = pathToFileURL(path.join(root, 'assets', 'fonts') + path.sep).href;
  const w = [['Regular', 400], ['Medium', 500], ['SemiBold', 600], ['Bold', 700], ['ExtraBold', 800], ['Black', 900]];
  const faces = w.map(([n, wt]) => `@font-face{font-family:"Pretendard";font-weight:${wt};src:url("${pub}Pretendard-${n}.woff2") format("woff2");}`);
  faces.push(`@font-face{font-family:"Anton";font-weight:400;src:url("${pub}Anton-Regular.woff2") format("woff2");}`);
  for (const [fam, file] of [['Jua', 'Jua'], ['Black Han Sans', 'BlackHanSans'], ['Nanum Pen Script', 'NanumPenScript']]) {
    faces.push(`@font-face{font-family:"${fam}";font-weight:400;src:url("${pub}${file}-korean.woff2") format("woff2");}`);
    faces.push(`@font-face{font-family:"${fam}";font-weight:400;src:url("${pub}${file}-latin.woff2") format("woff2");unicode-range:U+0000-00FF,U+2000-206F,U+20AC,U+2122,U+2212;}`);
  }
  faces.push(`@font-face{font-family:"Playfair Display";font-weight:700;src:url("${pub}PlayfairDisplay-Bold.woff2") format("woff2");}`);
  faces.push(`@font-face{font-family:"Playfair Display";font-weight:700;font-style:italic;src:url("${pub}PlayfairDisplay-BoldItalic.woff2") format("woff2");}`);
  faces.push(`@font-face{font-family:"Playfair Display";font-weight:400;font-style:italic;src:url("${pub}PlayfairDisplay-Italic.woff2") format("woff2");}`);
  faces.push(`@font-face{font-family:"Playfair Display";font-weight:900;font-style:italic;src:url("${pub}PlayfairDisplay-BlackItalic.woff2") format("woff2");}`);
  faces.push(`@font-face{font-family:"Instrument Serif";font-weight:400;src:url("${pub}InstrumentSerif-Regular.woff2") format("woff2");}`);
  faces.push(`@font-face{font-family:"Instrument Serif";font-weight:400;font-style:italic;src:url("${pub}InstrumentSerif-Italic.woff2") format("woff2");}`);
  const LAT = 'unicode-range:U+0000-00FF,U+2000-206F,U+20AC,U+2122,U+2212;';
  for (const [fam, file, ws] of [['Gowun Batang', 'GowunBatang', ['400', '700']], ['Hahmlet', 'Hahmlet', ['300', '700', '800']]]) {
    for (const wt of ws) {
      faces.push(`@font-face{font-family:"${fam}";font-weight:${wt};src:url("${pub}${file}-${wt}-korean.woff2") format("woff2");}`);
      faces.push(`@font-face{font-family:"${fam}";font-weight:${wt};src:url("${pub}${file}-${wt}-latin.woff2") format("woff2");${LAT}}`);
    }
  }
  faces.push(`@font-face{font-family:"Song Myung";font-weight:400;src:url("${pub}SongMyung-korean.woff2") format("woff2");}`);
  for (const wt of ['400', '700']) {
    faces.push(`@font-face{font-family:"Press Serif";font-weight:${wt};src:url("${pub}GowunBatang-700-korean.woff2") format("woff2");}`);
  }
  faces.push(`@font-face{font-family:"Song Myung";font-weight:400;src:url("${pub}SongMyung-latin.woff2") format("woff2");${LAT}}`);
  const serif = path.join(root, 'node_modules', '@fontsource', 'noto-serif-kr');
  const links = ['500', '700'].filter((x) => fs.existsSync(path.join(serif, `${x}.css`)))
    .map((x) => `<link rel="stylesheet" href="${pathToFileURL(path.join(serif, `${x}.css`)).href}">`);
  return {css: faces.join('\n'), links: links.join('\n')};
};

const harness = (card, animSrc, gsapSrc, pluginSrc) => {
  const {css, links} = fontFaces();
  const varCss = Object.entries(vars).map(([k, v]) => `${k}:${v};`).join('');
  const bg = card.layout === 'overlay' ? '#6b6b6b' : '#EFEAE0';
  return `<!doctype html><html><head><meta charset="utf-8">${links}
<style>${css}
html,body{margin:0;padding:0;background:${bg};}
#stage{position:relative;width:${card.w}px;height:${card.h}px;overflow:hidden;}
.card-host{${varCss}position:absolute;left:0;top:0;width:${card.w}px;height:${card.h}px;color:var(--ink);font-family:var(--font-body);line-height:1.25;}
.card[data-card-id="${card.id}"]{position:absolute;left:0;top:0;width:100%;height:100%;overflow:hidden;word-break:keep-all;overflow-wrap:break-word}
.card[data-card-id="${card.id}"] *{box-sizing:border-box}
${card.css}
</style></head><body>
<div id="stage"><div class="card-host"><div class="card" data-card-id="${card.id}">${card.html}</div></div></div>
<script>window.__errors=[];window.addEventListener('error',(e)=>{window.__errors.push(String(e.message||e));});
window.__cardTimeline=${JSON.stringify(card.timeline || '')};</script>
<script>${gsapSrc}</script>
<script>${pluginSrc}
gsap.registerPlugin(SplitText, CustomEase, DrawSVGPlugin, MorphSVGPlugin, MotionPathPlugin);
window.__libs = {SplitText, CustomEase, drawSVG: true, morphSVG: true, motionPath: true};</script>
<script>${animSrc}
window.__compileCard = (root, opts) => compileCard(window.gsap, root, Object.assign({libs: window.__libs}, opts));</script>
</body></html>`;
};

// 페이지 안에서 도는 검사(직렬화되어 evaluate 로 들어간다)
const audit = async (opts) => {
  const out = {problems: [], metrics: {}};
  const push = (code, detail, sel) => out.problems.push({code, detail: String(detail || ''), selector: sel || ''});
  const root = document.querySelector('.card');
  if (!root) {
    push('runtime_error', 'card root missing');
    return out;
  }
  // 글꼴: 카드 글자로 로드 요청 뒤 확인
  const text = root.textContent || '가';
  const fams = ['Pretendard', 'Noto Serif KR', 'Anton', 'Jua', 'Black Han Sans', 'Nanum Pen Script', 'Playfair Display',
    'Instrument Serif', 'Gowun Batang', 'Hahmlet', 'Song Myung', 'Press Serif'];
  try {
    await Promise.all(fams.flatMap((f) => ['400', '700'].map((w) => document.fonts.load(`${w} 40px "${f}"`, text))));
    await document.fonts.ready;
  } catch (e) {
    push('runtime_error', 'font load: ' + e);
  }
  // 타임라인 컴파일·seek
  let compiled = null;
  try {
    compiled = window.__compileCard(root, {fps: opts.fps, duration: opts.duration, timeline: window.__cardTimeline || ''});
    window.__compiled = compiled;   // 디버그용(미리보기 칸은 페이지를 새로 열어 찍는다)
    for (const p of compiled.problems || []) push(p.split(':')[0], p);
    // 정착 = 선언(data-anim)이 끝난 때와 타임라인 전체가 끝난 때 중 늦은 쪽 — 직접 쓴 타임라인만 있는 카드를 0.3초(움직이는 중)에
    // 재서 마스크 아래 글자를 '잘림'으로 보던 것(2026-10-04)
    opts.settle = Math.min(opts.duration - 0.05, Math.max(opts.settle, compiled.duration + 0.05));
    compiled.seek(opts.settle);
    out.metrics.settle = Number(opts.settle.toFixed(2));
  } catch (e) {
    push('runtime_error', 'compile: ' + (e && e.message ? e.message : e));
  }
  for (const e of window.__errors || []) push('runtime_error', e);
  out.metrics.anims = compiled ? compiled.kinds : [];
  out.metrics.timeline = compiled ? Number(compiled.duration.toFixed(2)) : 0;
  // 마지막 1초는 읽히게 멈춰 있어야 한다 — 다만 머무는 동안의 느린 흐름(Jitter 템플릿의 기본: 몇 px 떠오름·아주 느린 확대)은
  // 멈춤으로 본다. 타임라인이 길면 아래(잉크 검사 뒤)에서 마지막 1초의 실제 움직임을 잰다(2026-10-04: 5.6초 장면에 5.5초 흐름)
  const lateTail = !!(compiled && compiled.duration > opts.duration - 1.0 + 0.01);

  const R = root.getBoundingClientRect();
  const parse = (c) => {
    const m = c && c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map((x) => parseFloat(x));
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  };
  const lum = ({r, g, b}) => {
    const f = (v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const ratio = (a, b) => {
    const la = lum(a), lb = lum(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  };
  const blend = (fg, bg) => ({r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1});
  const effectiveBg = (el) => {
    // 조상 중 첫 불투명 배경색(그라데이션 배경은 '알 수 없음' → null)
    let e = el;
    while (e && e !== document.body) {
      const cs = getComputedStyle(e);
      const bgc = parse(cs.backgroundColor);
      if (cs.backgroundImage && cs.backgroundImage !== 'none' && (!bgc || bgc.a < 0.99)) return null;
      if (bgc && bgc.a >= 0.99) return bgc;
      if (bgc && bgc.a > 0) {
        const under = effectiveBg(e.parentElement);
        return under ? blend(bgc, under) : null;
      }
      e = e.parentElement;
    }
    return parse(getComputedStyle(document.body).backgroundColor);
  };
  const desc = (el) => {
    const id = el.id ? '#' + el.id : '';
    const cls = el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '';
    return (el.tagName.toLowerCase() + id + cls).slice(0, 60);
  };
  const visible = (el) => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    if (parseFloat(cs.opacity) < 0.05) return false;
    return true;
  };
  // 글자 요소(직접 텍스트 노드를 가진 요소)
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const textEls = new Set();
  let chars = 0;
  while (walker.nextNode()) {
    const n = walker.currentNode;
    if (!n.nodeValue || !n.nodeValue.trim()) continue;
    const el = n.parentElement;
    if (!el || el.closest('style')) continue;
    if (!visible(el)) continue;
    chars += n.nodeValue.trim().length;
    textEls.add(el);
  }
  out.metrics.chars = chars;
  out.metrics.text_elements = textEls.size;
  const seenSmall = new Set();
  for (const el of textEls) {
    const cs = getComputedStyle(el);
    const fs = parseFloat(cs.fontSize);
    const sel = desc(el);
    const fam = (cs.fontFamily || '').split(',')[0].replace(/["']/g, '').trim();
    if (fam && !/^(pretendard|noto serif kr|anton|jua|black han sans|nanum pen script|playfair display|instrument serif|gowun batang|hahmlet|song myung|press serif|serif|sans-serif|cursive|monospace|system-ui|ui-serif|ui-sans-serif|ui-monospace)$/i.test(fam)) {
      push('font_family_not_bundled', fam, sel);
    } else if (fam && !/^(serif|sans-serif|cursive|monospace|system-ui|ui-serif|ui-sans-serif|ui-monospace)$/i.test(fam)) {
      const w = cs.fontWeight === 'bold' ? '700' : cs.fontWeight;
      if (!document.fonts.check(`${w} ${Math.round(fs)}px "${fam}"`)) push('font_not_loaded', `${fam} ${w}`, sel);
    }
    if (fs < opts.minFont && !seenSmall.has(sel)) {
      seenSmall.add(sel);
      push('text_too_small', `${fs.toFixed(0)}px < ${opts.minFont}px`, sel);
    }
    // 넘침: 글자 상자가 캔버스 밖이거나, 상자가 고정 크기이고 내용이 더 클 때
    const rects = Array.from(el.getClientRects());
    const outside = rects.some((r) => r.width > 0 && (r.left < R.left - 2 || r.right > R.right + 2 || r.top < R.top - 2 || r.bottom > R.bottom + 2));
    if (outside) push('outside_canvas', 'text box leaves the canvas', sel);
    // 자막 자리(전체 화면·오버레이 카드의 아래 170px)에는 글자를 두지 않는다 — 자막이 위에 얹힌다
    if (opts.captionZone > 0 && rects.some((r) => r.width > 0 && r.bottom > R.bottom - opts.captionZone)) {
      push('text_in_caption_zone', `text within bottom ${opts.captionZone}px (caption area)`, sel);
    }
    if (cs.overflow !== 'visible' && (el.scrollWidth > el.clientWidth + 2 || el.scrollHeight > el.clientHeight + 2)) {
      push('text_overflow', `content ${el.scrollWidth}×${el.scrollHeight} > box ${el.clientWidth}×${el.clientHeight}`, sel);
    }
    // 잘림: overflow:hidden 인 조상 상자 밖으로 글자 상자가 나가면(글이 상자보다 길다)
    for (let a = el.parentElement; a && a !== root; a = a.parentElement) {
      const ao = getComputedStyle(a).overflow;
      if (ao === 'visible' || a.dataset.splitMask) continue;   // SplitText 마스크는 일부러 자르는 상자(정착하면 안에 다 들어온다)
      const A = a.getBoundingClientRect();
      const clipped = rects.some((r) => r.width > 0 && (r.right > A.right + 2 || r.bottom > A.bottom + 2 || r.left < A.left - 2 || r.top < A.top - 2));
      if (clipped) push('text_overflow', `text clipped by ${desc(a)} (${Math.round(A.width)}×${Math.round(A.height)})`, sel);
      break;
    }
    // 대비 — aria-hidden="true" 안의 글자는 장식(뒤에 깔린 큰 연도·워터마크)이라 대비를 재지 않는다(읽으라고 둔 글이 아니다)
    const fg = parse(cs.color);
    const bg = effectiveBg(el);
    if (fg && bg && !el.closest('[aria-hidden="true"]')) {
      const fgb = fg.a < 0.99 ? blend(fg, bg) : fg;
      const rt = ratio(fgb, bg);
      const large = fs >= 40 || (fs >= 32 && parseInt(cs.fontWeight, 10) >= 700);
      const need = large ? opts.contrastLarge : opts.contrastBody;
      if (rt < need) push('low_contrast', `${rt.toFixed(2)}:1 < ${need}:1 (${cs.color} on ${bg ? `rgb(${Math.round(bg.r)},${Math.round(bg.g)},${Math.round(bg.b)})` : '?'})`, sel);
    }
  }
  // 요소가 캔버스를 크게 벗어나는지(장식은 살짝 나갈 수 있다 → 절반 이상 밖이면)
  for (const el of root.querySelectorAll('*')) {
    if (el.closest('style') || !visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    const ix = Math.max(0, Math.min(r.right, R.right) - Math.max(r.left, R.left));
    const iy = Math.max(0, Math.min(r.bottom, R.bottom) - Math.max(r.top, R.top));
    if (ix * iy < 0.5 * r.width * r.height && !textEls.has(el)) push('outside_canvas', 'element mostly outside canvas', desc(el));
  }
  // 게이트 C4(docs/upgrade/06 F-6 · 06c P1-4): 시작 0.5초 프레임이 정착 프레임의 35% 이상 차 있어야 한다(빈 판 2~3초 금지).
  // 잉크 = 보이는 글자·그림·채운 면의 상자 넓이(유효 불투명도로 가중, 캔버스의 60% 넘는 배경 면은 뺀다)
  const opacityOf = (el) => {
    let o = 1;
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden') return 0;
      o *= parseFloat(cs.opacity);
    }
    return o;
  };
  const inkNow = () => {
    let sum = 0;
    const canvas = R.width * R.height;
    for (const el of root.querySelectorAll('*')) {
      if (el.closest('style')) continue;
      const tag = el.tagName.toLowerCase();
      const hasText = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.nodeValue.trim());
      const bgc = parse(getComputedStyle(el).backgroundColor);
      const media = tag === 'img' || tag === 'svg';
      if (!hasText && !media && !(bgc && bgc.a > 0.5)) continue;
      const r = el.getBoundingClientRect();
      const ix = Math.max(0, Math.min(r.right, R.right) - Math.max(r.left, R.left));
      const iy = Math.max(0, Math.min(r.bottom, R.bottom) - Math.max(r.top, R.top));
      const a = ix * iy;
      if (a <= 0 || (!hasText && a > 0.6 * canvas)) continue;
      const o = opacityOf(el);
      if (o > 0.12) sum += a * Math.min(1, o);
    }
    return sum;
  };
  if (compiled) {
    try {
      const inkSettle = inkNow();
      compiled.seek(Math.min(0.5, opts.settle));
      const ink05 = inkNow();
      compiled.seek(opts.settle);
      out.metrics.ink_at_0_5s = inkSettle > 0 ? Number((ink05 / inkSettle).toFixed(2)) : 1;
      if (inkSettle > 0 && ink05 < opts.firstFrame * inkSettle) {
        push('anim_first_frame_empty', `0.5s frame ink ${(100 * ink05 / inkSettle).toFixed(0)}% of settled (< ${Math.round(opts.firstFrame * 100)}%)`);
      }
    } catch (e) {
      push('runtime_error', 'first-frame check: ' + (e && e.message ? e.message : e));
    }
  }
  if (compiled && lateTail) {
    // 마지막 1초(카드 끝 −1.0초 → −0.05초)에 보이는 요소가 얼마나 움직이나: 중심 이동 · 크기 · 불투명도 · 선 그리기(dashoffset)
    try {
      const snap = () => {
        const m = new Map();
        for (const el of root.querySelectorAll('*')) {
          if (el.closest('style')) continue;
          const tag = el.tagName.toLowerCase();
          const hasText = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.nodeValue.trim());
          const inSvg = !!el.closest('svg') && tag !== 'svg';
          const bgc = parse(getComputedStyle(el).backgroundColor);
          if (!hasText && !inSvg && tag !== 'img' && tag !== 'svg' && !(bgc && bgc.a > 0.5)) continue;
          const r = el.getBoundingClientRect();
          const cs = getComputedStyle(el);
          m.set(el, {x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height, o: opacityOf(el),
            d: parseFloat(cs.strokeDashoffset) || 0, text: hasText});
        }
        return m;
      };
      const t0 = Math.max(0, opts.duration - 1.0);
      compiled.seek(t0);
      const a = snap();
      compiled.seek(Math.max(t0, opts.duration - 0.05));
      const b = snap();
      let worst = null;
      const note = (el, why, v) => {
        if (!worst || v > worst.v) worst = {el, why, v};
      };
      for (const [el, p] of a) {
        const q = b.get(el);
        if (!q || (p.o < 0.12 && q.o < 0.12)) continue;
        const move = Math.hypot(q.x - p.x, q.y - p.y);
        // 크기 변화는 긴 변 기준(가는 선이 조금 돌면 짧은 변이 몇 배가 된다 — 움직임이 아니다)
        const grow = Math.max(Math.abs(q.w - p.w), Math.abs(q.h - p.h)) / Math.max(p.w, p.h, 1);
        if (move > 16) note(el, `moves ${move.toFixed(0)}px`, move / 16);
        if (grow > 0.04 && Math.max(p.w, p.h) > 24) note(el, `scales ${(100 * grow).toFixed(0)}%`, grow / 0.04);
        if (Math.abs(q.o - p.o) > 0.15) note(el, `opacity ${p.o.toFixed(2)}→${q.o.toFixed(2)}`, Math.abs(q.o - p.o) / 0.15);
        if (Math.abs(q.d - p.d) > 4) note(el, `stroke still drawing`, Math.abs(q.d - p.d) / 4);
      }
      out.metrics.tail = worst ? worst.why : 'drift';
      if (worst) {
        push('anim_ends_too_late', `timeline ${compiled.duration.toFixed(2)}s, card ${opts.duration.toFixed(2)}s: last 1s not settled (${worst.why})`, desc(worst.el));
      }
      compiled.seek(opts.settle);
    } catch (e) {
      push('runtime_error', 'tail check: ' + (e && e.message ? e.message : e));
    }
  }
  // 같은 코드·요소 중복 정리
  const seen = new Set();
  out.problems = out.problems.filter((p) => {
    const k = p.code + '|' + p.selector + '|' + p.detail.slice(0, 40);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  return out;
};

const main = async () => {
  const jobFile = process.argv[2];
  const job = JSON.parse(fs.readFileSync(jobFile, 'utf-8'));
  const outDir = job.outDir || path.dirname(jobFile);
  fs.mkdirSync(outDir, {recursive: true});
  const animSrc = fs.readFileSync(path.join(root, 'vendor', 'hyperframes', 'card-anim.mjs'), 'utf-8')
    .replace(/^export\s+\{[^}]*\};?\s*$/m, '');
  const gsapSrc = fs.readFileSync(path.join(root, 'node_modules', 'gsap', 'dist', 'gsap.min.js'), 'utf-8');
  // 렌더(HtmlCard.tsx)와 같은 플러그인 — 검사와 렌더가 다르면 검사가 통과시킨 카드가 렌더에서 깨진다
  const pluginSrc = ['SplitText', 'CustomEase', 'DrawSVGPlugin', 'MorphSVGPlugin', 'MotionPathPlugin']
    .map((n) => fs.readFileSync(path.join(root, 'node_modules', 'gsap', 'dist', `${n}.min.js`), 'utf-8')).join('\n');
  const chromiumOptions = {gl: job.gl || (process.platform === 'win32' ? 'angle' : 'swangle')};
  const browser = await openBrowser('chrome', {browserExecutable: job.browserExecutable || null, chromiumOptions});
  const results = {};
  try {
    for (const card of job.cards || []) {
      const file = path.join(outDir, `${card.id}.html`);
      fs.writeFileSync(file, harness(card, animSrc, gsapSrc, pluginSrc));
      const page = await browser.newPage({context: () => null, logLevel: 'error', indent: false, pageIndex: 0,
        onBrowserLog: null, onLog: () => undefined});
      let res;
      try {
        await page.setViewport({width: card.w, height: card.h, deviceScaleFactor: 1});
        await page.goto({url: pathToFileURL(file).href, timeout: 20000});
        res = await page.evaluate(audit, {fps: card.fps || 30, duration: card.duration || 8, settle: card.settle || 2,
          minFont: MIN_FONT_PX, contrastBody: CONTRAST_BODY, contrastLarge: CONTRAST_LARGE, firstFrame: FIRST_FRAME_SHARE,
          captionZone: card.layout === 'split' ? 0 : CAPTION_ZONE_PX});
        // 미리보기(shots: 카드 시작 기준 초 목록) — 스타일 프레임·시안 경쟁이 렌더 없이 같은 Chrome 으로 장면을 본다(정착 화면 + 움직임 칸)
        // 'auto' = 정착 시각을 잰 뒤 정한다: 0.5초 · 정착의 35% · 70% · 정착 · 머무는 끝(드리프트) — 시간 순서, 정착 화면은 넷째
        const settleAt = (res && res.metrics && res.metrics.settle) || card.settle || 2;
        const dur = card.duration || 8;
        const shotTimes = card.shots === 'auto'
          ? [0.5, 0.35 * settleAt, 0.7 * settleAt, settleAt, Math.max(settleAt, dur - 0.35)]
            .map((t) => Number(Math.min(dur - 0.05, Math.max(0, t)).toFixed(2)))
            .filter((t, k, a) => k === 0 || t - a[k - 1] > 0.1)      // 정착이 끝 무렵이면 같은 칸이 겹친다
          : (Array.isArray(card.shots) ? card.shots : []);
        // 미리보기 칸은 칸마다 페이지를 새로 열어(새 문서) 그 시각으로 한 번만 seek 해서 찍는다. 같은 문서에서 찍고 → 뒤로 seek →
        // 다시 찍으면 DOM 은 맞는데 그림은 지난 래스터 타일이 섞인다(2026-10-04: 아직 안 나온 주석 글자·제목 유령·검은 띠 —
        // Remotion 렌더는 깨끗했다). 두 애니메이션 프레임을 기다린 뒤 Remotion 과 같은 옵션(captureBeyondViewport)으로 찍는다
        const capture = async (t, f) => {
          await page.goto({url: pathToFileURL(file).href, timeout: 20000});
          await page.evaluate(async (o) => {
            const root = document.querySelector('.card');
            const text = root ? root.textContent || '가' : '가';
            const fams = ['Pretendard', 'Noto Serif KR', 'Anton', 'Jua', 'Black Han Sans', 'Nanum Pen Script', 'Playfair Display',
              'Instrument Serif', 'Gowun Batang', 'Hahmlet', 'Song Myung', 'Press Serif'];
            try {
              await Promise.all(fams.flatMap((fm) => ['400', '700'].map((w) => document.fonts.load(`${w} 40px "${fm}"`, text))));
              await document.fonts.ready;
            } catch (e) { /* 글꼴 문제는 검사가 따로 적는다 */ }
            const c = window.__compileCard(root, {fps: o.fps, duration: o.duration, timeline: window.__cardTimeline || ''});
            c.seek(o.t);
            await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(true))));
          }, {fps: card.fps || 30, duration: dur, t});
          const {value} = await page._client().send('Page.captureScreenshot', {
            format: 'jpeg', quality: 86, fromSurface: true, captureBeyondViewport: true, clip: {x: 0, y: 0, width: card.w, height: card.h, scale: 1},
          });
          fs.writeFileSync(f, Buffer.from(value.data, 'base64'));
        };
        if (res && shotTimes.length) {
          res.shots = [];
          const times = Array.from(new Set(shotTimes.slice(0, 8).map((x) => Number(x) || 0))).sort((a, b) => a - b);
          for (let k = 0; k < times.length; k++) {
            const f = path.join(outDir, `${card.id}_s${k}.jpg`);
            try {
              await capture(times[k], f);
              res.shots.push({t: times[k], path: f});
            } catch (e) {
              /* 한 장 실패는 건너뛴다 */
            }
          }
        }
        // 걸린 카드는 정착 시각의 화면을 찍어 둔다 — 카드 디자이너가 오류 목록만이 아니라 실제 모습을 보고 고친다
        if (res && res.problems && res.problems.length) {
          const near = (res.shots || []).find((x) => Math.abs(x.t - settleAt) < 0.06);
          if (near) {
            res.shot = near.path;
          } else {
            try {
              res.shot = path.join(outDir, `${card.id}.jpg`);
              await capture(settleAt, res.shot);
            } catch (e) {
              res.shot = '';
            }
          }
        }
      } catch (e) {
        res = {problems: [{code: 'runtime_error', detail: String(e && e.message ? e.message : e), selector: ''}], metrics: {}};
      } finally {
        await page.close().catch(() => undefined);
      }
      res.ok = res.problems.length === 0;
      results[card.id] = res;
      emit({type: 'card', id: card.id, ok: res.ok, problems: res.problems, metrics: res.metrics, shot: res.shot || '',
        shots: res.shots || []});
    }
  } finally {
    await browser.close({silent: true}).catch(() => undefined);
  }
  fs.writeFileSync(path.join(outDir, 'check.json'), JSON.stringify(results, null, 1));
  emit({type: 'finished', n: Object.keys(results).length});
};

main().catch((e) => {
  emit({type: 'error', message: String(e && e.stack ? e.stack : e)});
  process.exit(1);
});
