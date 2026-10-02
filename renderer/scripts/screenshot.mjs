// 화면 캡처(자료 조달 v2 — docs/upgrade/03 3절 screenshot, C 등급: 설정 allow_quote 가 켜졌을 때만 파이프라인이 부른다).
//   node scripts/screenshot.mjs <job.json>
// job.json: {"browserExecutable": "", "gl": "", "shots": [{"id": "s1", "url": "https://…", "out": "<경로>.jpg",
//            "width": 1440, "height": 900, "maxHeight": 6000}]}
// 렌더와 같은 Chrome 으로 페이지를 열고 2초 기다린 뒤 문서 높이(최대 maxHeight)까지 한 장으로 찍는다.
// 결과는 stdout 에 JSON 한 줄씩({"type":"shot", id, ok, w, h, error}).
import fs from 'node:fs';
import path from 'node:path';
import {openBrowser} from '@remotion/renderer';

const emit = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const main = async () => {
  const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf-8'));
  const chromiumOptions = {gl: job.gl || (process.platform === 'win32' ? 'angle' : 'swangle')};
  const browser = await openBrowser('chrome', {browserExecutable: job.browserExecutable || null, chromiumOptions});
  try {
    for (const s of job.shots || []) {
      const w = s.width || 1440;
      const page = await browser.newPage({context: () => null, logLevel: 'error', indent: false, pageIndex: 0,
        onBrowserLog: null, onLog: () => undefined});
      try {
        await page.setViewport({width: w, height: s.height || 900, deviceScaleFactor: 1});
        await page.goto({url: s.url, timeout: 30000});
        await sleep(2000);
        const docH = await page.evaluate(() => Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0));
        const h = Math.max(s.height || 900, Math.min(Number(docH) || 900, s.maxHeight || 6000));
        const {value} = await page._client().send('Page.captureScreenshot', {
          format: 'jpeg', quality: 88, captureBeyondViewport: true, fromSurface: true,
          clip: {x: 0, y: 0, width: w, height: h, scale: 1},
        });
        fs.mkdirSync(path.dirname(s.out), {recursive: true});
        fs.writeFileSync(s.out, Buffer.from(value.data, 'base64'));
        emit({type: 'shot', id: s.id, ok: true, w, h});
      } catch (e) {
        emit({type: 'shot', id: s.id, ok: false, error: String(e && e.message ? e.message : e).slice(0, 300)});
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
