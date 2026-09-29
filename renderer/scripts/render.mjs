// Python 파이프라인이 호출하는 렌더 드라이버.
//   node scripts/render.mjs <job.json>
// job.json:
// {
//   "publicDir": "<폰트·그레인·이미지 등 작은 파일 폴더>",
//   "bundleDir": "<번들 출력 폴더(작업 폴더 안)>",
//   "links": [{"src": "<큰 미디어 원본>", "dst": "media/proxy.mp4"}],   // 번들 public 안에 하드링크(실패 시 복사)
//   "browserExecutable": "", "gl": "angle", "concurrency": 0,
//   "renders": [{"kind": "video"|"still", "composition": "LongForm", "props": "<props.json>",
//                "output": "<out.mp4>", "scale": 1, "crf": 18, "x264Preset": "medium", "encoder": "auto"}]
// }
// stdout 으로 JSON 한 줄씩 진행 상황을 보낸다.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {renderMedia, renderStill, selectComposition} from '@remotion/renderer';

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

const main = async () => {
  const jobPath = process.argv[2];
  if (!jobPath) throw new Error('usage: node scripts/render.mjs <job.json>');
  const job = JSON.parse(fs.readFileSync(jobPath, 'utf-8'));
  const entryPoint = path.join(root, 'src', 'index.ts');

  emit({type: 'stage', stage: 'bundle'});
  const serveUrl = await bundle({
    entryPoint,
    publicDir: job.publicDir,
    outDir: job.bundleDir,
    onProgress: (p) => emit({type: 'bundle', progress: p / 100}),
  });

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

  for (let i = 0; i < job.renders.length; i++) {
    const r = job.renders[i];
    const inputProps = JSON.parse(fs.readFileSync(r.props, 'utf-8'));
    emit({type: 'start', index: i, composition: r.composition, output: r.output});
    const composition = await selectComposition({serveUrl, id: r.composition, inputProps, browserExecutable,
      chromiumOptions});
    fs.mkdirSync(path.dirname(r.output), {recursive: true});
    if (r.kind === 'still') {
      await renderStill({composition, serveUrl, output: r.output, inputProps, browserExecutable, chromiumOptions,
        scale: r.scale || 1, imageFormat: r.output.endsWith('.png') ? 'png' : 'jpeg', jpegQuality: 92, overwrite: true});
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
  emit({type: 'finished'});
};

main().catch((err) => {
  emit({type: 'error', message: String(err && err.stack ? err.stack : err)});
  process.exit(1);
});
