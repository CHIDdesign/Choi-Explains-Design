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

const vars = {
  '--bg': '#F5F2EA', '--paper': '#F5F2EA', '--paper-line': '#D9D6CF', '--ink': '#26211E', '--ink-soft': '#1C1C1C',
  '--muted': 'rgba(28, 28, 28, 0.7)', '--accent': '#E8682C', '--accent-deep': '#9E4720', '--accent-light': '#EC7F52',
  '--accent-soft': 'rgba(232, 104, 44, 0.32)', '--board': '#1A1C1B', '--board-edge': '#2A2D2B', '--chalk': '#F1ECDD',
  '--chalk-dim': 'rgba(241, 236, 221, 0.58)', '--white': '#F5F2EA',   // HtmlCard.tsx cardVars 와 같게(크림 종이·따뜻한 잉크)
  '--font-head': '"Gowun Batang", "Noto Serif KR", "Pretendard", serif', '--font-body': '"Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif',
  '--font-serif': '"Gowun Batang", "Noto Serif KR", "Nanum Myeongjo", serif', '--font-latin': '"Anton", "Pretendard", sans-serif',
  '--font-editorial': '"Song Myung", "Gowun Batang", "Noto Serif KR", serif', '--font-poster': '"Song Myung", "Gowun Batang", serif',
  '--font-italic': '"Instrument Serif", "Playfair Display", serif',
  '--font-heavy': '"Black Han Sans", "Pretendard", sans-serif', '--font-round': '"Jua", "Pretendard", sans-serif',
  '--font-hand': '"Nanum Pen Script", "Pretendard", cursive', '--font-numeral': '"Playfair Display", "Gowun Batang", serif',
  '--font-mono': '"Pretendard", monospace',
};

const fontFaces = () => {
  const pub = pathToFileURL(path.join(root, 'public', 'fonts') + path.sep).href;
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

const harness = (card, animSrc, gsapSrc) => {
  const {css, links} = fontFaces();
  const varCss = Object.entries(vars).map(([k, v]) => `${k}:${v};`).join('');
  const bg = card.layout === 'overlay' ? '#6b6b6b' : '#EFEAE0';
  return `<!doctype html><html><head><meta charset="utf-8">${links}
<style>${css}
html,body{margin:0;padding:0;background:${bg};}
#stage{position:relative;width:${card.w}px;height:${card.h}px;overflow:hidden;}
.card-host{${varCss}position:absolute;left:0;top:0;width:${card.w}px;height:${card.h}px;color:var(--ink);font-family:var(--font-body);line-height:1.25;}
.card[data-card-id="${card.id}"]{position:absolute;left:0;top:0;width:100%;height:100%;overflow:hidden}
.card[data-card-id="${card.id}"] *{box-sizing:border-box}
${card.css}
</style></head><body>
<div id="stage"><div class="card-host"><div class="card" data-card-id="${card.id}">${card.html}</div></div></div>
<script>window.__errors=[];window.addEventListener('error',(e)=>{window.__errors.push(String(e.message||e));});</script>
<script>${gsapSrc}</script>
<script>${animSrc}
window.__compileCard = (root, opts) => compileCard(window.gsap, root, opts);</script>
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
    compiled = window.__compileCard(root, {fps: opts.fps, duration: opts.duration});
    for (const p of compiled.problems || []) push(p.split(':')[0], p);
    compiled.seek(opts.settle);
  } catch (e) {
    push('runtime_error', 'compile: ' + (e && e.message ? e.message : e));
  }
  for (const e of window.__errors || []) push('runtime_error', e);
  out.metrics.anims = compiled ? compiled.kinds : [];
  out.metrics.timeline = compiled ? Number(compiled.duration.toFixed(2)) : 0;
  if (compiled && compiled.duration > opts.duration - 1.0 + 0.01) {
    push('anim_ends_too_late', `timeline ${compiled.duration.toFixed(2)}s > card ${opts.duration.toFixed(2)}s − 1.0`);
  }

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
      if (ao === 'visible') continue;
      const A = a.getBoundingClientRect();
      const clipped = rects.some((r) => r.width > 0 && (r.right > A.right + 2 || r.bottom > A.bottom + 2 || r.left < A.left - 2 || r.top < A.top - 2));
      if (clipped) push('text_overflow', `text clipped by ${desc(a)} (${Math.round(A.width)}×${Math.round(A.height)})`, sel);
      break;
    }
    // 대비
    const fg = parse(cs.color);
    const bg = effectiveBg(el);
    if (fg && bg) {
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
  const chromiumOptions = {gl: job.gl || (process.platform === 'win32' ? 'angle' : 'swangle')};
  const browser = await openBrowser('chrome', {browserExecutable: job.browserExecutable || null, chromiumOptions});
  const results = {};
  try {
    for (const card of job.cards || []) {
      const file = path.join(outDir, `${card.id}.html`);
      fs.writeFileSync(file, harness(card, animSrc, gsapSrc));
      const page = await browser.newPage({context: () => null, logLevel: 'error', indent: false, pageIndex: 0,
        onBrowserLog: null, onLog: () => undefined});
      let res;
      try {
        await page.setViewport({width: card.w, height: card.h, deviceScaleFactor: 1});
        await page.goto({url: pathToFileURL(file).href, timeout: 20000});
        res = await page.evaluate(audit, {fps: card.fps || 30, duration: card.duration || 8, settle: card.settle || 2,
          minFont: MIN_FONT_PX, contrastBody: CONTRAST_BODY, contrastLarge: CONTRAST_LARGE, firstFrame: FIRST_FRAME_SHARE,
          captionZone: card.layout === 'split' ? 0 : CAPTION_ZONE_PX});
      } catch (e) {
        res = {problems: [{code: 'runtime_error', detail: String(e && e.message ? e.message : e), selector: ''}], metrics: {}};
      } finally {
        await page.close().catch(() => undefined);
      }
      res.ok = res.problems.length === 0;
      results[card.id] = res;
      emit({type: 'card', id: card.id, ok: res.ok, problems: res.problems, metrics: res.metrics});
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
