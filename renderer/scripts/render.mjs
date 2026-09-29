// Python 파이프라인이 호출하는 렌더 드라이버.
//   node scripts/render.mjs <job.json>
// job.json:
// {
//   "publicDir": "<폰트·그레인·이미지 등 작은 파일 폴더>",
//   "bundleDir": "<번들 출력 폴더(작업 폴더 안)>",
//   "links": [{"src": "<큰 미디어 원본>", "dst": "media/proxy.mp4"}],   // 번들 public 안에 하드링크(실패 시 복사)
//   "browserExecutable": "", "gl": "angle", "concurrency": 0,
//   "reuseBundle": false,   // true 면 소스가 바뀌지 않았을 때 이전 번들을 재사용(검수 스틸 → 본 렌더)
//   "renders": [{"kind": "video"|"still"|"frames", "composition": "LongForm", "props": "<props.json>",
//                "output": "<out.mp4>", "scale": 1, "crf": 18, "x264Preset": "medium", "encoder": "auto",
//                "frame": 0,                                   // still: 뽑을 프레임
//                "frames": [{"frame": 120, "output": "<a.jpg>"}]  // frames: 같은 props 로 여러 장
//   }]
// }
// stdout 으로 JSON 한 줄씩 진행 상황을 보낸다.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {openBrowser, renderMedia, renderStill, selectComposition} from '@remotion/renderer';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const emit = (obj) => process.stdout.write(JSON.stringify(obj) + '\n');

const linkOrCopy = (src, dst) => {
  fs.mkdirSync(path.dirname(dst), {recursive: true});
  try {
    if (fs.existsSync(dst)) {
      const a = fs.statSync(src);
      const b = fs.statSync(dst);
      if (a.size === b.size && Math.abs(a.mtimeMs - b.mtimeMs) < 2000) return 'exists';
      fs.rmSync(dst);
    }
  } catch {
    /* 무시 */
  }
  try {
    fs.linkSync(src, dst);
    return 'link';
  } catch {
    fs.copyFileSync(src, dst);
    return 'copy';
  }
};

// 렌더러 소스가 바뀌었는지 판단하는 도장(파일 경로 + 수정 시각 + 크기)
const sourceStamp = () => {
  const parts = [];
  const walk = (dir) => {
    for (const e of fs.readdirSync(dir, {withFileTypes: true})) {
      const f = path.join(dir, e.name);
      if (e.isDirectory()) walk(f);
      else {
        const st = fs.statSync(f);
        parts.push(`${path.relative(root, f)}:${Math.round(st.mtimeMs)}:${st.size}`);
      }
    }
  };
  walk(path.join(root, 'src'));
  for (const f of ['package.json', 'remotion.config.ts']) {
    const full = path.join(root, f);
    if (fs.existsSync(full)) parts.push(`${f}:${Math.round(fs.statSync(full).mtimeMs)}`);
  }
  return parts.sort().join('|');
};

// 작은 파일(public_src)을 번들 public 에 동기화(재사용한 번들에 새 이미지·B-roll 반영)
const syncDir = (src, dst) => {
  if (!src || !fs.existsSync(src)) return 0;
  let n = 0;
  for (const e of fs.readdirSync(src, {withFileTypes: true})) {
    const a = path.join(src, e.name);
    const b = path.join(dst, e.name);
    if (e.isDirectory()) {
      n += syncDir(a, b);
      continue;
    }
    let same = false;
    try {
      same = fs.existsSync(b) && fs.statSync(a).size === fs.statSync(b).size
        && fs.statSync(a).mtimeMs <= fs.statSync(b).mtimeMs + 2000;
    } catch {
      same = false;
    }
    if (!same) {
      linkOrCopy(a, b);
      n++;
    }
  }
  return n;
};

const main = async () => {
  const jobPath = process.argv[2];
  if (!jobPath) throw new Error('usage: node scripts/render.mjs <job.json>');
  const job = JSON.parse(fs.readFileSync(jobPath, 'utf-8'));
  const entryPoint = path.join(root, 'src', 'index.ts');

  const stampFile = path.join(job.bundleDir, '.choi-stamp');
  const stamp = sourceStamp();
  let serveUrl;
  if (job.reuseBundle && fs.existsSync(path.join(job.bundleDir, 'index.html')) && fs.existsSync(stampFile)
      && fs.readFileSync(stampFile, 'utf-8') === stamp) {
    serveUrl = job.bundleDir;
    const n = syncDir(job.publicDir, path.join(serveUrl, 'public'));
    emit({type: 'log', message: `bundle reused (${n} public files synced)`});
    emit({type: 'bundle', progress: 1});
  } else {
    emit({type: 'stage', stage: 'bundle'});
    serveUrl = await bundle({
      entryPoint,
      publicDir: job.publicDir,
      outDir: job.bundleDir,
      onProgress: (p) => emit({type: 'bundle', progress: p / 100}),
    });
    fs.writeFileSync(stampFile, stamp);
  }

  // 큰 미디어는 번들 뒤에 하드링크(Windows 는 bundle 이 public 을 통째로 복사하므로)
  const pub = path.join(serveUrl, 'public');
  for (const l of job.links || []) {
    const how = linkOrCopy(l.src, path.join(pub, l.dst));
    emit({type: 'log', message: `media ${l.dst} (${how})`});
  }

  const chromiumOptions = {gl: job.gl || (process.platform === 'win32' ? 'angle' : 'swangle')};
  const browserExecutable = job.browserExecutable || null;
  const cpu = os.cpus().length;
  const concurrency = job.concurrency && job.concurrency > 0 ? job.concurrency : Math.max(1, Math.min(8, Math.floor(cpu / 2)));

  // 브라우저 하나를 모든 렌더가 공유(스틸 여러 장을 뽑을 때 크게 빨라짐)
  const browser = await openBrowser('chrome', {browserExecutable, chromiumOptions});
  const still = async (composition, inputProps, frame, output, scale) => {
    fs.mkdirSync(path.dirname(output), {recursive: true});
    await renderStill({composition, serveUrl, output, inputProps, browserExecutable, chromiumOptions,
      puppeteerInstance: browser, frame: Math.max(0, Math.min(composition.durationInFrames - 1, Math.round(frame || 0))),
      scale: scale || 1, imageFormat: output.endsWith('.png') ? 'png' : 'jpeg', jpegQuality: 90, overwrite: true});
  };

  for (let i = 0; i < job.renders.length; i++) {
    const r = job.renders[i];
    const inputProps = JSON.parse(fs.readFileSync(r.props, 'utf-8'));
    emit({type: 'start', index: i, composition: r.composition, output: r.output});
    const composition = await selectComposition({serveUrl, id: r.composition, inputProps, browserExecutable,
      chromiumOptions, puppeteerInstance: browser});
    fs.mkdirSync(path.dirname(r.output), {recursive: true});
    if (r.kind === 'still') {
      await still(composition, inputProps, r.frame || 0, r.output, r.scale);
      emit({type: 'done', index: i, output: r.output});
      continue;
    }
    if (r.kind === 'frames') {
      const list = r.frames || [];
      for (let k = 0; k < list.length; k++) {
        await still(composition, inputProps, list[k].frame, list[k].output, r.scale);
        emit({type: 'progress', index: i, progress: (k + 1) / list.length});
      }
      emit({type: 'done', index: i, output: r.output});
      continue;
    }
    const useGpu = r.encoder === 'gpu' || (r.encoder !== 'cpu' && process.platform === 'win32');
    const quality = useGpu
      ? {hardwareAcceleration: 'if-possible', videoBitrate: r.videoBitrate || (composition.height * (r.scale || 1) >= 2000 ? '40M' : '16M')}
      : {crf: r.crf ?? 18, x264Preset: r.x264Preset || 'medium'};
    let last = -1;
    await renderMedia({
      composition,
      serveUrl,
      codec: 'h264',
      outputLocation: r.output,
      inputProps,
      browserExecutable,
      chromiumOptions,
      puppeteerInstance: browser,
      concurrency,
      scale: r.scale || 1,
      imageFormat: 'jpeg',
      jpegQuality: 92,
      audioCodec: 'aac',
      audioBitrate: '320k',
      pixelFormat: 'yuv420p',
      overwrite: true,
      offthreadVideoCacheSizeInBytes: 2 * 1024 * 1024 * 1024,
      ...quality,
      onProgress: ({progress, renderedFrames, encodedFrames, stitchStage}) => {
        const p = Math.round(progress * 1000) / 1000;
        if (p !== last) {
          last = p;
          emit({type: 'progress', index: i, progress: p, renderedFrames, encodedFrames, stage: stitchStage});
        }
      },
    });
    emit({type: 'done', index: i, output: r.output});
  }
  await browser.close({silent: true}).catch(() => undefined);
  emit({type: 'finished'});
};

main().catch((err) => {
  emit({type: 'error', message: String(err && err.stack ? err.stack : err)});
  process.exit(1);
});
