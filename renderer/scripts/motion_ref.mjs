// 모션 레퍼런스 캡처(docs/upgrade/14 — Jitter 등 공개 템플릿 갤러리의 '움직임'을 Claude 가 보고 우리 카드로 다시 짓는다).
//   node scripts/motion_ref.mjs <job.json>
// job.json: {"browserExecutable": "", "gl": "", "refs": [{"id": "r1", "url": "https://jitter.video/template/…/",
//            "outDir": "<폴더>", "frames": 8, "every": 450}]}
// 렌더와 같은 Chrome 으로 페이지를 열고, 화면에서 가장 큰 미리보기(video·canvas·iframe·큰 이미지)를 찾아 그 영역만
// every ms 간격으로 frames 장 찍는다(f00.jpg …). 파일을 내려받거나 템플릿을 쓰지 않는다 — 움직임을 보는 참고 프레임뿐.
// 결과는 stdout 에 JSON 한 줄씩({"type":"ref", id, ok, n, box, error}).
import fs from 'node:fs';
import path from 'node:path';
import {openBrowser} from '@remotion/renderer';

const emit = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const findPreview = () => {
  const els = [...document.querySelectorAll('video, canvas, iframe, img, [class*="player"], [class*="preview"]')];
  let best = null;
  let area = 0;
  for (const el of els) {
    const r = el.getBoundingClientRect();
    const a = r.width * r.height;
    if (r.width >= 320 && r.height >= 180 && r.top < window.innerHeight && a > area) {
      area = a;
      best = {x: Math.max(0, r.left), y: Math.max(0, r.top + window.scrollY), width: Math.min(r.width, window.innerWidth),
        height: Math.min(r.height, 1200), tag: el.tagName.toLowerCase()};
    }
  }
  return best;
};

const main = async () => {
  const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf-8'));
  // ignoreCertErrors: 시험 환경(프록시 인증서)용 — 실제 작업은 끈 채로
  const chromiumOptions = {gl: job.gl || (process.platform === 'win32' ? 'angle' : 'swangle'),
    ignoreCertificateErrors: Boolean(job.ignoreCertErrors)};
  const browser = await openBrowser('chrome', {browserExecutable: job.browserExecutable || null, chromiumOptions});
  try {
    for (const r of job.refs || []) {
      const page = await browser.newPage({context: () => null, logLevel: 'error', indent: false, pageIndex: 0,
        onBrowserLog: null, onLog: () => undefined});
      try {
        await page.setViewport({width: 1440, height: 900, deviceScaleFactor: 1});
        await page.goto({url: r.url, timeout: 30000});
        await sleep(2500);
        const box = (await page.evaluate(findPreview)) || {x: 0, y: 0, width: 1440, height: 900, tag: 'page'};
        fs.mkdirSync(r.outDir, {recursive: true});
        const n = Math.max(2, Math.min(16, r.frames || 8));
        for (let i = 0; i < n; i++) {
          const {value} = await page._client().send('Page.captureScreenshot', {
            format: 'jpeg', quality: 82, captureBeyondViewport: true, fromSurface: true,
            clip: {x: box.x, y: box.y, width: box.width, height: box.height, scale: Math.min(1, 640 / box.width)},
          });
          fs.writeFileSync(path.join(r.outDir, `f${String(i).padStart(2, '0')}.jpg`), Buffer.from(value.data, 'base64'));
          await sleep(r.every || 450);
        }
        emit({type: 'ref', id: r.id, ok: true, n, box});
      } catch (e) {
        emit({type: 'ref', id: r.id, ok: false, error: String(e && e.message ? e.message : e).slice(0, 300)});
      } finally {
        await page.close().catch(() => undefined);
      }
    }
  } finally {
    await browser.close({silent: true}).catch(() => undefined);
  }
  emit({type: 'finished'});
};

main().catch((e) => {
  emit({type: 'error', message: String(e && e.stack ? e.stack : e)});
  process.exit(1);
});
