# Tooling research: Windows talking-head auto-editor (verified 2026-09-29)

Legend: **[V]** = verified this session against a primary source (package registry JSON, source code at a release tag, official docs source); **[K]** = from prior knowledge, could NOT be re-verified this session (egress to that site blocked / web-search budget exhausted). Blocked sites: remotion.dev (used GitHub doc sources instead), helpx.adobe.com, *.wikimedia.org / mediawiki.org, api.openverse.org, api.pexels.com / pexels.com, gyan.dev, docs.nvidia.com.

---

## A. Remotion

### Versions [V]
- `remotion` / `@remotion/renderer` / `@remotion/bundler` / `@remotion/media` / `@remotion/fonts` / `@remotion/captions` / `@remotion/licensing`: **4.0.530** (published 2026-09-29; npm `latest`). Remotion ships a patch roughly every 2-4 days; pin one exact version for ALL `@remotion/*` packages (mismatches break). An `alpha` tag `4.1.0-alpha12` exists; v5.0 is pending (docs mention "removed in Remotion 5.0").
  - Source: https://registry.npmjs.org/remotion

### Programmatic render API [V]
Sources: https://github.com/remotion-dev/remotion/tree/main/packages/docs/docs (bundle.mdx, renderer/render-media.mdx, renderer/select-composition.mdx, renderer/render-still.mdx) and packages/renderer/src/options/*.tsx

```ts
import {bundle} from '@remotion/bundler';
import {selectComposition, renderMedia, renderStill, ensureBrowser, makeCancelSignal} from '@remotion/renderer';

await ensureBrowser();                       // downloads Chrome Headless Shell if missing
const serveUrl = await bundle({
  entryPoint: path.resolve('remotion/src/index.ts'),
  publicDir: 'D:/job123/public',             // optional; default <rootDir>/public
  rootDir: path.resolve('remotion'),         // dir containing package.json w/ remotion
  webpackOverride: (c) => c,                 // reducer; not called if rspack:true
  onProgress: (pct) => {},                   // 0..100
  // also: outDir, enableCaching, publicPath (default './' since 4.0.497), rspack, rspackOverride,
  // bundlerOverride (4.0.498+), onPublicDirCopyProgress, onSymlinkDetected, ignoreRegisterRootWarning
});
const composition = await selectComposition({serveUrl, id: 'Main', inputProps});
const {slowestFrames} = await renderMedia({
  composition, serveUrl, codec: 'h264', outputLocation: 'out.mp4', inputProps,
  crf: 18,                       // NOT allowed together with hardwareAcceleration -> use videoBitrate
  x264Preset: 'medium',          // ultrafast..placebo; h264/h264-mkv/h264-ts only; default 'medium'
  audioBitrate: '320k',          // FFmpeg -b:a syntax; default 320k
  videoBitrate: null,            // e.g. '12M'
  concurrency: '50%',            // number | '50%' | null (default = half of CPU threads)
  hardwareAcceleration: 'disable', // 'disable' | 'if-possible' | 'required'
  browserExecutable: null,
  chromiumOptions: {gl: 'angle'},  // 'angle'|'egl'|'swiftshader'|'swangle'|'vulkan'|'angle-egl'; v4 default null (Chrome decides)
  chromeMode: 'headless-shell',    // or 'chrome-for-testing'
  imageFormat: 'jpeg', jpegQuality: 80,
  mediaCacheSizeInBytes: null,     // cache for @remotion/media
  offthreadVideoCacheSizeInBytes: null, offthreadVideoThreads: null,
  timeoutInMilliseconds: 30000, logLevel: 'info',
  cancelSignal, onBrowserLog, onStart: ({frameCount, parallelEncoding, resolvedConcurrency}) => {},
  onProgress: ({renderedFrames, encodedFrames, encodedDoneIn, renderedDoneIn, renderEstimatedTime, progress, stitchStage}) => {},
  // progress: 0..1; stitchStage: 'encoding' | 'muxing'
  frameRange: null,                // number | [a,b] | [a,null] (4.0.421+) | [[a,b],[c,d]] concat ranges (4.0.502+)
  licenseKey: undefined, isProduction: true, // only relevant for Company License holders
});
await renderStill({composition, serveUrl, output: 'thumb.png', frame: 30, inputProps, imageFormat: 'png'});
```
- `RenderMediaProgress` type = `{renderedFrames, encodedFrames, encodedDoneIn: number|null, renderedDoneIn: number|null, renderEstimatedTime: number, progress: number, stitchStage}` (source packages/renderer/src/render-media.ts).
- `selectComposition` `inputProps`: optional in v4, **required in v5**.
- Return of renderMedia (v4): `{buffer, slowestFrames, contentType}`.
- **NEW vs 2024: NVENC hardware encoding on Windows/Linux since 4.0.484** (`hardwareAcceleration: 'if-possible'`, H.264/H.265 only). Remotion's bundled FFmpeg on Windows x64 includes `h264_nvenc`/`hevc_nvenc`. `crf` is incompatible with HW accel; docs suggest `videoBitrate` (e.g. `8M` for 1080p ≈ software size). Verbose log shows `Encoder: h264_nvenc, hardware accelerated: true`. (docs/hardware-acceleration.mdx)
- `gl` default: `null` in v4 (Chrome decides); `'angle'` planned default for v5. For GPU-heavy CSS (blur, shadows, gradients) and alpha-video decoding, set `gl: 'angle'`; default headless config has no WebGL.
- `npx remotion browser ensure` / `ensureBrowser()` download Chrome Headless Shell to `node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe`; pinned Chrome **149.0.7790.0** since 4.0.452; a `VERSION` file triggers re-download on mismatch. Docs discourage `browserExecutable` overrides with other Chrome versions.

### `<Video>`/`<Audio>` from `@remotion/media` vs `<OffthreadVideo>` [V]
Sources: docs/video-tags.mdx, docs/media/video.mdx, docs/media/fallback.mdx, docs/media/support.mdx, docs/offthreadvideo.mdx
- **2026 recommendation: `<Video>`/`<Audio>` from `@remotion/media` for new code** ("the recommended component"). Based on Mediabunny + WebCodecs; frame-perfect; partial download; "Fastest" render speed. `<OffthreadVideo>` (Rust+FFmpeg extractor) remains, and is the automatic **fallback** when decode fails (e.g. H.265 during render, unsupported container, CORS, alpha without WebGL). The old `remotion` `<Video>` is renamed **`<Html5Video>`** (`Video` still exported from `remotion` as the old tag — don't confuse the imports).
- For long local MP4s: use **H.264 (+AAC) in .mp4/.mov**. Avoid .mkv/.webm for audio-heavy long files (Matroska requires decoding all audio up to the extraction point). Log line on fallback: `Cannot decode /public/x.mp4, falling back to <OffthreadVideo>`. Use `disallowFallbackToOffthreadVideo` to fail instead.
- Props (`@remotion/media` `<Video>`): `src`, `from` (4.0.446), `durationInFrames` (4.0.446), `trimBefore`, ~~`trimAfter`~~ (**deprecated** in favor of `durationInFrames`, PR #11685), `volume` (number or callback `(mediaFrame) => number`; callback frame starts at 0 when media starts), `playbackRate` (changes pitch in this path), `muted`, `loop`, `loopVolumeCurveBehavior` ('repeat'|'extend'), `style`, `objectFit` ('contain' default|'cover'|'fill'|'none'|'scale-down'; CSS object-fit not supported), `cropLeft/Right/Top/Bottom` (4.0.500), `effects` (4.0.464), `premountFor`/`postmountFor` (4.0.495), `name`, `showInTimeline`, `onError` (return `'fallback'|'fail'`), `onVideoFrame`, `audioStreamIndex`, `toneFrequency`, `requestInit` (4.0.465), `headless`, `fallbackOffthreadVideoProps`, `disallowFallbackToOffthreadVideo`, `delayRenderTimeoutInMilliseconds`, `delayRenderRetries`, `maxCanvasSinkFrameSize` (4.0.530), `debugOverlay`.
- `<OffthreadVideo>`: `startFrom`/`endAt` → renamed `trimBefore`/`trimAfter` in **4.0.319**; `trimAfter` now also deprecated; `durationInFrames` added in **4.0.530** (today).
- Note inconsistency: the official Agent Skills text still teaches `trimBefore` + `trimAfter`; API docs mark `trimAfter` deprecated. Prefer `trimBefore` + `durationInFrames` (source frames).
- CORS: assets must be CORS-enabled **or** served via `staticFile()` (same origin).

### Fonts [V]
- `@remotion/fonts` (4.0.164+): `loadFont({family, url, format?, weight?, style?, display?, stretch?, unicodeRange?, featureSettings?, ascentOverride?, descentOverride?, lineGapOverride?}): Promise<void>`; blocks the render until loaded (uses delayRender internally). `format` is one of `woff2|woff|opentype|truetype`, auto-derived from extension. Load each weight separately with the same `family`.
  ```ts
  import {loadFont} from '@remotion/fonts'; import {staticFile} from 'remotion';
  await Promise.all([
    loadFont({family: 'Pretendard', url: staticFile('fonts/Pretendard-Regular.woff2'), weight: '400'}),
    loadFont({family: 'Pretendard', url: staticFile('fonts/Pretendard-Bold.woff2'), weight: '700'}),
  ]);
  ```
- Importing `.woff/.woff2/.otf/.ttf/.eot` via webpack **works** (bundler rule `test: /\.(woff(2)?|otf|ttf|eot)(\?v=\d+\.\d+\.\d+)?$/, type: 'asset/resource'` in packages/bundler/src/shared-bundler-config.ts) — `import url from './font.woff2'` gives a URL you can pass to `loadFont`. Docs "recommend against" import-style assets (2 GB limit, dynamic-import quirks) and prefer `staticFile()`. Bundling fonts via import is actually fine for fixed app fonts; use public dir for user-chosen fonts.
- Korean fonts are large; subset to woff2 and use `@remotion/layout-utils` `measureText()/fitText()` only after fonts load.

### calculateMetadata [V]
```ts
const calculateMetadata: CalculateMetadataFunction<Props> =
  async ({props, defaultProps, abortSignal, compositionId, isRendering}) => ({
    durationInFrames, width, height, fps, props,
    defaultCodec, defaultOutName, defaultVideoImageFormat, defaultPixelFormat, defaultProResProfile, defaultSampleRate,
  });
<Composition ... calculateMetadata={calculateMetadata} />
```
Runs once (in a separate tab, during `selectComposition`), must be JSON-serializable, must finish within the delayRender timeout.

### staticFile + custom publicDir [V]
- `bundle()` **copies** `publicDir` (default `<rootDir>/public`) into `<bundleOutDir>/public`; `staticFile('x.mp4')` → `${window.remotion_staticBase}/x.mp4` (i.e. `./public/x.mp4` relative to bundle since publicPath default `./`). So `staticFile` paths are relative to the publicDir root, regardless of where it lives on disk.
- **Windows: public dir is always copied, never symlinked** (`symlinkPublicDir` "has no effect on Windows" — packages/bundler/src/bundle.ts). Copying multi-GB talking-head footage on every bundle is slow → bundle once, then per job place (copy/hard-link) the intermediate MP4 into `<bundleDir>/public/` (docs: "if you use the SSR APIs, you can add assets to the public folder that is inside the bundle after the fact"). Alternative: serve a folder over HTTP with CORS (`npx serve --cors`, or `serve-handler`) and pass a URL.
- `staticFile()` encodes with `encodeURIComponent` (don't pre-encode) and **rejects** absolute paths (`C:`, `D:`, `/Users`…), `./`, `../`, and `public/` prefixes.

### License [V]
Source: https://github.com/remotion-dev/remotion/blob/main/LICENSE.md, docs/license/faq.mdx
- **Free License**: individuals (personal or commercial), for-profit orgs with **≤3 people**, non-profits, evaluation. No feature differences. Automations/SaaS allowed under Free License if eligible.
- Company License: "Remotion for Creators" $25/month per person; "Remotion for Automators" $0.01 per render, min $100/month. Code calling `renderMedia()`/`renderStill()`/`npx remotion render` etc. = automation. Disallowed for everyone: selling/relicensing a derivative of Remotion itself. If you distribute the app to companies >3 people, **they** would need a license.

### Windows gotchas
- [V] Chrome Headless Shell is supported on Windows x64 (win64). Run `ensureBrowser()` at app startup / installer time so first render doesn't stall.
- [V] H.265 sources fall back to OffthreadVideo; Chrome-for-Testing mode reportedly lacked H.264 decode in one third-party app issue (OpenChatCut #162) — stay on default `headless-shell`.
- [V third-party] Common Windows failures: invoking `npx` from Python must use `npx.cmd` (or `node node_modules/@remotion/cli/remotion-cli.js`) / `shell=True`; path backslash escaping; capture full stderr (gkyla/yonru.clip #199). Prefer calling your own `render.mjs` with `node` and exchanging JSON via files/stdout.
- [K] Long paths: keep the Remotion project + node_modules at a short path (e.g. `C:\AppName\remotion`) or enable `LongPathsEnabled`; not specifically documented by Remotion (unverified).
- [K] Windows Defender real-time scanning of node_modules / temp frames slows renders; consider exclusion for the work dir.

### Remotion Agent Skills (official) [V]
- Yes: `remotion-dev/skills` (generated from `packages/skills` in the monorepo; version 4.0.530). Install: `npx skills add remotion-dev/skills` (also offered in `bun create video`). Skills: `/remotion-best-practices` (router), `/remotion-create`, `/remotion-markup`, `/remotion-studio`, `/remotion-render`, `/remotion-maps`, `/remotion-captions`, `/remotion-saas`, `/remotion-interactivity`, `/remotion-docs`, `/remotion-upgrade`, `/remotion-multimedia`.
- Key rules (near-verbatim):
  - Animation: "Drive animations using `useCurrentFrame()` and `interpolate()`. CSS `transition` or `animation` will not render correctly… Tailwind animation class will not render correctly." Use `Easing.bezier()` / `Easing.spring({damping: 200})`; always `extrapolateLeft/Right: 'clamp'`; for scale use `output: 'perceptual-scale'`; multiple keyframes take an easing array of n-1; `posterize: 3` for stepped motion. Keep `interpolate()` inline in `style`; prefer CSS `scale`/`translate`/`rotate` properties over `transform` strings (Studio-editable). New `Interactive.Div` wrappers make elements editable in Studio.
  - Media: "Add video and audio using `<Video>` and `<Audio>` from `@remotion/media`." Images via `<CanvasImage>`; GIF/APNG/WebP/AVIF via `<AnimatedImage>`. Clips: put timing props inline (`from`, `durationInFrames`, `trimBefore`); use `<Series>` for back-to-back clips, `<TransitionSeries>` for transitions. Install packages with `npx remotion add @remotion/media` (keeps versions matched).
  - Fonts: "Google Fonts … is the recommended way"; local fonts via `@remotion/fonts` `loadFont()` with `staticFile()`; `await Promise.all([...])` per weight.
  - Captions: all captions as JSON in `@remotion/captions` `Caption` type `{text, startMs, endMs, timestampMs: number|null, confidence: number|null, pageBreakAfter?}`; "captions are whitespace sensitive… include spaces in the `text` field before each word"; display with the copy-paste "Basic Captions" element; transcription suggested via `@remotion/whisper-webgpu` (you use faster-whisper instead — just convert to `Caption[]`).
  - FFmpeg: use `npx remotion ffmpeg` / `npx remotion ffprobe` (bundled); prefer non-destructive trims via `trimBefore`; if trimming with FFmpeg "You MUST re-encode". Silence detection recipe: `loudnorm=print_format=json` → take `input_thresh` → `silencedetect=noise=${THRESH}dB:d=0.5`.
  - Performance (docs, not skills): GPU-accelerated content in headless needs `--gl`; OffthreadVideo `transparent` only if needed; `toneMapped:false` is faster; `mediaCacheSizeInBytes`; don't call `bundle()` per render (anti-pattern).
  - Workflow: don't render unless explicitly asked; preview in Studio; "Preserve user changes".
  - Sources: https://raw.githubusercontent.com/remotion-dev/skills/main/README.md ; https://github.com/remotion-dev/remotion/tree/main/packages/skills/skills

---

## B. faster-whisper

### Versions [V]
- **faster-whisper 1.2.1** (PyPI, 2025-10-31) — still the latest in Sept 2026 (no release in ~11 months; master unchanged version). Requires `ctranslate2>=4.0,<5`, `onnxruntime>=1.14,<2`, `av>=11`, `tokenizers`, `huggingface-hub>=0.21`.
- **CTranslate2 4.8.2** (2026-08-31). Windows wheels cp39–cp314 (incl. free-threaded 3.14t).
  - 4.5.0: cuDNN 9 only. 4.6.1: Python 3.14, CUDA 12.4. 4.6.2: **INT8 disabled on sm120 (RTX 50-series Blackwell)** → use `compute_type="float16"`. 4.6.3: CUDA 12.8 support, **pure-CUDA Conv1d makes cuDNN optional**. 4.7.0: AMD ROCm.
  - Windows wheel build script: CUDA **12.8**, `-DWITH_CUDA=ON -DWITH_CUDNN=OFF -DCUDA_DYNAMIC_LOADING=ON` (python/tools/prepare_build_environment_windows.sh). Wheel ships `ctranslate2.dll`, `libiomp5md.dll`, a small `cudnn64_9.dll`, but **no cuBLAS**.
  - Sources: https://pypi.org/pypi/ctranslate2/json ; https://github.com/OpenNMT/CTranslate2/blob/master/CHANGELOG.md

### Signatures [V] (v1.2.1 tag, faster_whisper/transcribe.py)
```python
WhisperModel(model_size_or_path: str, device="auto", device_index=0, compute_type="default",
             cpu_threads=0, num_workers=1, download_root=None, local_files_only=False,
             files=None, revision=None, use_auth_token=None, **model_kwargs)

WhisperModel.transcribe(audio, language=None, task="transcribe", log_progress=False,
    beam_size=5, best_of=5, patience=1, length_penalty=1, repetition_penalty=1,
    no_repeat_ngram_size=0, temperature=[0.0,0.2,0.4,0.6,0.8,1.0],
    compression_ratio_threshold=2.4, log_prob_threshold=-1.0, no_speech_threshold=0.6,
    condition_on_previous_text=True, prompt_reset_on_temperature=0.5,
    initial_prompt=None, prefix=None, suppress_blank=True, suppress_tokens=[-1],
    without_timestamps=False, max_initial_timestamp=1.0, word_timestamps=False,
    prepend_punctuations="\"'“¿([{-", append_punctuations="\"'.。,，!！?？:：”)]}、",
    multilingual=False, vad_filter=False, vad_parameters=None, max_new_tokens=None,
    chunk_length=None, clip_timestamps="0", hallucination_silence_threshold=None,
    hotwords=None, language_detection_threshold=0.5, language_detection_segments=1)
  -> (Iterable[Segment], TranscriptionInfo)      # segments is a lazy generator
BatchedInferencePipeline(model).transcribe(..., vad_filter=True, batch_size=8, without_timestamps=True, clip_timestamps: list[dict]|None, ...)
```
- `Segment(id, seek, start, end, text, tokens, avg_logprob, compression_ratio, no_speech_prob, words: list[Word]|None, temperature)`; `Word(start, end, word, probability)`. Use `dataclasses.asdict` (`_asdict` deprecated).
- `initial_prompt` (sequential): prompt "for the first window"; `hotwords`: "Hint phrases… Has no effect if prefix is not None" (encoded into the prompt). `hallucination_silence_threshold` only works with `word_timestamps=True`. `clip_timestamps` makes `vad_filter` ignored.
- Korean word timestamps: words are split **on spaces** for Korean (only zh/ja/th/lo/my/yue use unicode splitting) → you get eojeol-level (space-delimited) words, good for cut lists (faster_whisper/tokenizer.py).

### Model names [V] (faster_whisper/utils.py `_MODELS`)
`tiny(.en)`, `base(.en)`, `small(.en)`, `medium(.en)`, `large-v1`, `large-v2`, `large-v3`, `large` (=large-v3), `distil-large-v2`, `distil-medium.en`, `distil-small.en`, `distil-large-v3`, `distil-large-v3.5` (→ `distil-whisper/distil-large-v3.5-ct2`), `large-v3-turbo` and `turbo` (→ `mobiuslabsgmbh/faster-whisper-large-v3-turbo`).
- Korean quality [K/partly V]: distil-* models are English-only → not for Korean. turbo = large-v3 with 4 decoder layers (vs 32): much faster, "minor quality degradation", larger degradation reported for some languages (Thai, Cantonese). No authoritative Korean CER comparison found; recommend `large-v3` (float16) as quality default, `turbo` as fast option; community Korean fine-tunes of turbo exist (e.g. `ghost613/whisper-large-v3-turbo-korean`, need CT2 conversion). Use `language="ko"` (skip detection), `condition_on_previous_text=False` to reduce repetition loops, `vad_filter=True`, and `initial_prompt`/`hotwords` for names/jargon.

### Silero VAD inside the package [V]
- Wheel contains `faster_whisper/assets/silero_vad_v6.onnx` (Silero **v6** since 1.2.1; run via onnxruntime CPUExecutionProvider).
- Direct API: `from faster_whisper.vad import VadOptions, get_speech_timestamps, get_vad_model, collect_chunks`; `from faster_whisper import decode_audio`.
  ```python
  audio = decode_audio("in.wav", sampling_rate=16000)          # float32 mono
  ts = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=300, speech_pad_ms=100))
  # -> [{'start': sample_idx, 'end': sample_idx}, ...]  (divide by 16000 for seconds)
  ```
- `VadOptions` fields in 1.2.1: `threshold=0.5`, `neg_threshold=None` (→ max(threshold-0.15, 0.01)), `min_speech_duration_ms=0`, `max_speech_duration_s=inf`, `min_silence_duration_ms=2000`, `speech_pad_ms=400`. (Master adds unreleased `min_silence_at_max_speech=98`, `use_max_poss_sil_at_max_speech=True`.) `get_speech_timestamps(audio, vad_options=None, sampling_rate=16000, **kwargs)`.

### Windows CUDA setup [V + community]
- README: GPU needs cuBLAS for CUDA 12 and cuDNN 9 for CUDA 12; pip method documented as "Linux only"; Windows suggestion = Purfview's `whisper-standalone-win` libs archive on PATH.
- Practical Windows recipe (verified wheel contents): `pip install faster-whisper nvidia-cublas-cu12` (12.9.2.10 has win_amd64 wheel: `nvidia/cublas/bin/cublas64_12.dll`, `cublasLt64_12.dll`). With CT2 ≥4.6.3 Windows wheels built `WITH_CUDNN=OFF`, cuDNN should not be needed (add `nvidia-cudnn-cu12==9.*` only if you hit a cudnn error — unverified edge). CTranslate2 loads cuBLAS lazily (`LoadLibrary`), so errors like `Library cublas64_12.dll is not found or cannot be loaded` often appear **at the first `transcribe()`**, not at model load. Before importing/constructing the model:
  ```python
  import os, sys, glob, ctypes, site
  _dll_handles = []
  for sp in site.getsitepackages() + [site.getusersitepackages()]:
      for d in glob.glob(os.path.join(sp, "nvidia", "*", "bin")):
          _dll_handles.append(os.add_dll_directory(d))      # keep handles alive
          os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]
  # optional belt-and-braces: preload by full path
  # ctypes.WinDLL(r"...\nvidia\cublas\bin\cublasLt64_12.dll"); ctypes.WinDLL(r"...\cublas64_12.dll")
  ```
  In a PyInstaller build, ship the two cuBLAS DLLs (~770 MB) next to the exe or in `_internal`.
- NVIDIA driver must support CUDA 12.8 runtime (R570+) [K].
- Sources: https://github.com/SYSTRAN/faster-whisper (README, v1.2.1 tag), https://github.com/SYSTRAN/faster-whisper/issues/1276, https://github.com/NousResearch/hermes-agent/pull/110679, https://github.com/jaredrhod/backtalk/issues/28

### WhisperX [V]
- Maintained: **whisperx 3.8.6** (PyPI, 2026-05-25). Depends on `faster-whisper>=1.2.0`, `ctranslate2>=4.5.0`, `pyannote-audio>=4.0.0`, **`torch~=2.8.0`, torchaudio~=2.8.0**, `transformers>=4.48`, `huggingface-hub<1.0`.
- Korean alignment supported: `DEFAULT_ALIGN_MODELS_HF["ko"] = "kresnik/wav2vec2-large-xlsr-korean"` (whisperx/alignment.py). Heavy dependency (PyTorch) vs plain faster-whisper word timestamps; useful if you need tighter word boundaries for cuts.

---

## C. Face detection

### OpenCV YuNet [V]
- Signature (4.x and 5.x headers identical):
  ```cpp
  static Ptr<FaceDetectorYN> create(const String& model, const String& config, const Size& input_size,
      float score_threshold = 0.9f, float nms_threshold = 0.3f, int top_k = 5000,
      int backend_id = 0, int target_id = 0);
  // overload: create(const String& framework, const std::vector<uchar>& bufferModel,
  //                  const std::vector<uchar>& bufferConfig, const Size& input_size, ...same defaults)
  ```
  Python: `det = cv2.FaceDetectorYN.create(model=path, config="", input_size=(w, h), score_threshold=0.9, nms_threshold=0.3, top_k=5000, backend_id=0, target_id=0)`; `det.setInputSize((w, h))`; `retval, faces = det.detect(bgr)`; `faces` is `None` or N×15: `[x, y, w, h, re_x, re_y, le_x, le_y, nose_x, nose_y, rmouth_x, rmouth_y, lmouth_x, lmouth_y, score]`.
- **NEW: opencv-python 5.0.0.93 (2026-07-02) is now the default `pip install opencv-python`**; 4.x line continues (4.14.0.94, 2026-07-29).
- Model files in opencv_zoo `models/face_detection_yunet/`:
  - **`face_detection_yunet_2026may.onnx`** — new default (demo.py default), dynamic H/W input, needed for OpenCV 5.x ONNX Runtime engine (`OPENCV_FORCE_DNN_ENGINE=4`).
  - `face_detection_yunet_2023mar.onnx` — fixed input shape; fine on OpenCV 4.x DNN (call `setInputSize` to frame size).
  - `face_detection_yunet_2023mar_int8.onnx`, `face_detection_yunet_2023mar_int8bq.onnx` (block-quantized).
  - Raw download (Git LFS, tested HTTP 200): `https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2026may.onnx` (229,738 B) and `.../face_detection_yunet_2023mar.onnx` (232,589 B). (`raw.githubusercontent.com` returns only the LFS pointer; `github.com/.../raw/...` redirects to media.githubusercontent.)
  - Detects faces ~10×10 to 300×300 px — downscale 1080p/4K frames (e.g. to 640 wide) before detection.
- License: **MIT** (Copyright (c) 2020 Shiqi Yu). Demo asserts OpenCV ≥ 4.10.0.
- Source: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet ; opencv/opencv modules/objdetect/include/opencv2/objdetect/face.hpp

### MediaPipe [V]
- Latest **mediapipe 1.0.1** (2026-08-14). **`mp.solutions` (incl. `mp.solutions.face_detection`) is gone**: the 1.0.1 and 0.10.30/0.10.31 Windows wheels contain no `mediapipe/python/solutions/`; last wheel with `solutions/face_detection.py` is **0.10.21** (2025-02-06). `mediapipe/__init__.py` now only exposes `tasks`, `Image`, `ImageFormat` → use `mediapipe.tasks.python.vision.FaceDetector` (+ a `.tflite` model, e.g. BlazeFace short-range). YuNet is the simpler dependency.

---

## D. FFmpeg

- **Latest release: FFmpeg 9.0.2** (tags n9.0 → released 2026-08-04 "Lei"; n9.0.1; n9.0.2 ~2026-09-19). 8.1.3 is latest 8.x. [V tags via git ls-remote; dates from news]
- **`-filter_complex_script`**: deprecated in **7.0** (runtime warning: `-filter_complex_script is deprecated, use -/filter_complex <file> instead`), still present in 7.1 and 8.x (`FFMPEG_OPT_FILTER_SCRIPT`), **removed in 9.0** (absent from n9.0.2 `fftools/ffmpeg_opt.c`). Same for `-filter_script`.
  - Replacement (doc/fftools-common-opts.texi): "add a forward slash '/' immediately before the option name… `ffmpeg -i INPUT -/filter:v filter.script OUTPUT`". So: `ffmpeg -i in.mp4 -/filter_complex cuts.txt -map "[v]" -map "[a]" ...`. Works for any option taking an argument (e.g. `-/vf`, `-/af`). Supported since 7.0.
- **NVENC changes in 9.0** [V source]: "Remove deprecated NVENC options and support for pre-11.1 SDK versions". In 9.0.2 `h264_nvenc`: `-preset` accepts only `p1`–`p7` (default p4) plus `slow`/`medium`/`fast`; legacy `hp, hq, bd, ll, llhq, llhp, lossless, losslesshp` presets removed; `-rc` only `constqp|vbr|cbr` (`vbr_hq`, `cbr_hq`, `cbr_ld_hq`, `vbr_minqp`, `ll_2pass_*` removed; `-2pass` removed → use `-multipass disabled|qres|fullres`). `-tune hq|ll|ull|lossless` (default hq). Setting `-cq N` alone switches rc to VBR and **zeroes average bitrate** (only `-maxrate` honored), so `-b:v 0` is now redundant but harmless.
- Driver requirement comes from nv-codec-headers used at build: SDK 12.0 → driver ≥551.76 (Win); SDK 13.0 → ≥570; SDK 13.1 (current master) → **≥610**. Error "Driver does not support the required nvenc API version" = update driver. [V headers README]
- **Windows install** [V winget manifests]: `winget install Gyan.FFmpeg` → **full** build 9.0.2 (ReleaseDate 2026-09-20; zip from github.com/GyanD/codexffmpeg; portable aliases ffmpeg/ffprobe/ffplay). Also `Gyan.FFmpeg.Essentials` (currently 9.0.1), `Gyan.FFmpeg.Shared`, `BtbN.FFmpeg.GPL` (nightly) / `BtbN.FFmpeg.GPL.9`, `BtbN.FFmpeg.LGPL`. Gyan essentials & full and BtbN GPL builds include `h264_nvenc`/`hevc_nvenc` [K — gyan.dev blocked; confirm with `ffmpeg -hide_banner -encoders | findstr nvenc`]. For an app, bundle a pinned BtbN/Gyan build rather than relying on PATH; GPL builds include x264 (licensing of your distribution applies).
- **HQ intermediate (edit-friendly) NVENC settings** (FFmpeg ≥7, valid on 9.x):
  ```
  ffmpeg -hide_banner -y -i src.mp4 -/filter_complex cuts.txt -map "[v]" -map "[a]" ^
    -c:v h264_nvenc -preset p6 -tune hq -rc vbr -cq 18 -b:v 0 -maxrate 50M -bufsize 100M ^
    -spatial-aq 1 -temporal-aq 1 -rc-lookahead 32 -bf 3 -b_ref_mode middle -multipass fullres ^
    -g 30 -profile:v high -pix_fmt yuv420p ^
    -c:a aac -b:a 320k -ar 48000 -movflags +faststart out.mp4
  ```
  - `p5`–`p7` = slow/slower/slowest (quality ↑); `p6`/`p7` + `-multipass fullres` for near-x264-medium quality. `-cq` 16–20 for visually lossless 1080p intermediates. Short GOP (`-g` = 1 s) + `+faststart` helps Remotion `<Video>` seeking/range requests with concurrency. Use yuv420p 8-bit H.264 so `@remotion/media` decodes via WebCodecs (H.265/10-bit risks fallback). Frame-accurate cuts require re-encoding (never `-c copy` for cut points).

---

## E. Premiere Pro FCP7 XML

- Premiere Pro import of FCP7 XML (xmeml) [K — helpx.adobe.com blocked, search budget exhausted]: still supported via File > Import (.xml) and File > Export > Final Cut Pro XML in Premiere Pro 2025 (v25.x); I found no deprecation notice, but could not re-verify for 2026 releases. Premiere reads xmeml `version="4"` or `"5"`; it ignores unsupported effects.
- Apple spec (developer.apple.com FCP XML reference) [V]:
  - `pathurl`: "must start with `file://localhost` or `file:///`"; non-URL characters %-escaped (RFC 2396). Premiere's own Windows exports use `file://localhost/C%3a/Users/.../clip.mp4` [K]; `file:///C:/...` also generally imports. Percent-encode spaces and UTF-8 (Korean) characters: e.g. Python `"file://localhost/" + urllib.parse.quote(path.replace("\\","/"), safe="/")` (this yields `C%3A`, fine).
  - `clipitem` required: `name`, `duration`, `rate`, `start`, `end` (+ `in`, `out`, `file`, `link`, `sourcetrack`, `marker`). `file` required: `duration`, `rate`, and `name` or `pathurl`; reuse by `<file id="file-1"/>` after first full definition. `marker` required: `name`, `in`, `out`; optional `comment`, `color` (`red/green/blue/alpha`); parents: clip, clipitem, sequence. `rate` = `timebase` + `ntsc` (29.97 → timebase 30, ntsc TRUE). `link` = `linkclipref` (+ `mediatype`, `trackindex`, `clipindex`, `groupindex`).
- Minimal skeleton (one source, one cut; repeat clipitems per kept segment; timeline `start/end` contiguous, source `in/out` from cut list; `end-start == out-in`):
  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE xmeml>
  <xmeml version="4">
   <sequence id="sequence-1">
    <name>AutoEdit</name><duration>300</duration>
    <rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate>
    <media>
     <video>
      <format><samplecharacteristics><rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate>
        <width>1920</width><height>1080</height><pixelaspectratio>square</pixelaspectratio></samplecharacteristics></format>
      <track>
       <clipitem id="clipitem-v1">
        <name>take1.mp4</name><enabled>TRUE</enabled><duration>54000</duration>
        <rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate>
        <start>0</start><end>300</end><in>150</in><out>450</out>
        <file id="file-1">
         <name>take1.mp4</name>
         <pathurl>file://localhost/C%3a/Videos/take1.mp4</pathurl>
         <rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate><duration>54000</duration>
         <media><video><samplecharacteristics><width>1920</width><height>1080</height></samplecharacteristics></video>
                <audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics><channelcount>2</channelcount></audio></media>
        </file>
        <link><linkclipref>clipitem-v1</linkclipref><mediatype>video</mediatype><trackindex>1</trackindex><clipindex>1</clipindex></link>
        <link><linkclipref>clipitem-a1</linkclipref><mediatype>audio</mediatype><trackindex>1</trackindex><clipindex>1</clipindex><groupindex>1</groupindex></link>
       </clipitem>
      </track>
     </video>
     <audio>
      <track>
       <clipitem id="clipitem-a1">
        <name>take1.mp4</name><enabled>TRUE</enabled><duration>54000</duration>
        <rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate>
        <start>0</start><end>300</end><in>150</in><out>450</out>
        <file id="file-1"/>
        <sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>
        <link><linkclipref>clipitem-v1</linkclipref><mediatype>video</mediatype><trackindex>1</trackindex><clipindex>1</clipindex></link>
        <link><linkclipref>clipitem-a1</linkclipref><mediatype>audio</mediatype><trackindex>1</trackindex><clipindex>1</clipindex><groupindex>1</groupindex></link>
       </clipitem>
      </track>
     </audio>
    </media>
    <marker><name>Topic</name><comment>설명 시작</comment><in>120</in><out>-1</out></marker>
   </sequence>
  </xmeml>
  ```
  [K] Stereo handling: FCP7 treated audio clipitems as mono channels; some generators emit two audio tracks (trackindex 1 & 2) for L/R. Test import in the target Premiere version with a stereo and a mono source. Use `<out>-1</out>` for point markers (FCP7 convention) [K].
- OpenTimelineIO [V]: `opentimelineio` 0.18.1 (2025-11-09); FCP7 adapter is the separate plugin **`otio-fcp-adapter` 1.0.0** (2023-07; repo HEAD active) — install via `pip install opentimelineio-plugins` (0.18.1 bundles otio-fcp-adapter, aaf, cmx3600, etc.) or `pip install otio-fcp-adapter`. Supports clips, multiple video tracks, audio tracks, gaps, markers, nesting; **no transitions/effects/speed**. Writes `xmeml version="4"`; `pathurl` = `ExternalReference.target_url` verbatim (you must build the `file://localhost/...` URL yourself); markers written as `name/in/out` only (comments need `marker.metadata["fcp_xml"]`). Good alternative for correctness/validation; hand-rolled XML gives you control over link/stereo details. Can also emit EDL/AAF via other adapters.

---

## F. Image/video sources

### Wikimedia Commons API (endpoint `https://commons.wikimedia.org/w/api.php`)
- Query [K for exact behavior; field names V from CommonsMetadata source]:
  ```
  GET /w/api.php?action=query&format=json&formatversion=2
      &generator=search&gsrsearch=<keyword> filetype:bitmap&gsrnamespace=6&gsrlimit=20
      &prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=1920
      &iiextmetadatafilter=LicenseShortName|LicenseUrl|License|UsageTerms|AttributionRequired|Artist|Credit|Copyrighted|Restrictions|ImageDescription|ObjectName
      &iiextmetadatalanguage=ko
  ```
  - Namespace 6 = File. `gsrsearch` supports CirrusSearch keywords (`filetype:bitmap|drawing|video`, `fileres:>1000`, `haswbstatement:`). Response: `query.pages[].imageinfo[0].url` (original), `.thumburl` (sized by `iiurlwidth`), `.descriptionurl`, `.extmetadata.<Field>.value`.
  - extmetadata fields (from mediawiki-extensions-CommonsMetadata src/DataCollector.php, TemplateParser.php): `LicenseShortName`, `LicenseUrl`, `License`, `UsageTerms`, `AttributionRequired` ("true"/"false" strings), `Attribution`, `Artist` (**HTML** — strip tags), `Credit` (HTML), `Copyrighted`, `Restrictions`, `ImageDescription`, `ObjectName`, `DateTimeOriginal`, `NonFree`, `Permission`, `Categories`, `AuthorCount`, `Assessments`. Each value is `{value, source, hidden}`.
  - Filter to free licenses (CC0, PD, CC BY, CC BY-SA) and store attribution text = Artist + LicenseShortName + LicenseUrl + descriptionurl.
- User-Agent policy [K — meta.wikimedia.org blocked]: send a descriptive `User-Agent` identifying the tool plus contact (URL or email), e.g. `ChoiAutoEdit/0.3 (https://github.com/you/app; you@example.com) python-httpx/0.x`; generic/missing UAs may get 403. Make requests serially, add `maxlag=5`, respect `Retry-After`, cache results.

### Openverse [V from source; endpoint behavior K]
- Anonymous access **allowed** (client docs: "If credentials are not passed… requests will proceed anonymously"). Endpoint: `GET https://api.openverse.org/v1/images/?q=<query>&license_type=commercial,modification&page_size=20&page=1` (also `/v1/audio/`; params incl. `license`, `license_type`, `source`, `extension`, `aspect_ratio`, `size`, `category`, `mature`). Anonymous limits in code: **max `page_size` 20**, max 240 results depth; default throttles `anon_burst 5/hour`, `anon_sustained 100/day` (env-overridable; production values unverified) vs OAuth2 client-credentials `100/min`, `10000/day`. Register via `POST /v1/auth_tokens/register/` then `POST /v1/auth_tokens/token/` (client_credentials) [K].
- Result fields: `id, title, foreign_landing_url, url, creator, creator_url, license, license_version, license_url, provider, source, category, filesize, filetype, tags, attribution, fields_matched, mature, width/height (images), thumbnail`. `attribution` is a ready-made credit string.
- Source: https://github.com/WordPress/openverse (api/conf/settings/rest_framework.py, api/api/constants/restricted_features.py, api/api/serializers/media_serializers.py)

### Pexels [V endpoint/header from official client; policy K]
- `GET https://api.pexels.com/videos/search?query=<q>&orientation=landscape|portrait|square&size=large|medium|small&locale=ko-KR&page=1&per_page=15` (max 80) — header **`Authorization: <API_KEY>`** (no "Bearer"). Also `/videos/popular`, `/videos/videos/:id`; photos at `https://api.pexels.com/v1/search`. Response video: `id, width, height, url, image, duration, user{id,name,url}, video_files[{id, quality: "hd"|"sd"|"hls" (per client types), file_type, width, height, fps, link}], video_pictures[]`. Filter params in client: `min_width, max_width, min_duration, max_duration`.
- Rate limit [K]: 200 requests/hour, 20,000/month by default; headers `X-Ratelimit-Limit/Remaining/Reset`.
- License [K]: Pexels License — free for commercial/personal use, attribution not required (appreciated); may modify. Not allowed: selling unaltered copies, redistributing on other stock/wallpaper platforms, implying endorsement by depicted people/brands, offensive use of identifiable people. API terms ask apps to show a prominent "Photos/Videos provided by Pexels" link and credit the creator where possible.
- Source: https://github.com/pexels/pexels-javascript (src/constants.ts, src/createFetchWrapper.ts, src/types.ts)

---

## G. Anthropic Python SDK — guaranteed JSON [V from bundled claude-api skill, cached 2026-09-25; PyPI]
- SDK: **`anthropic` 1.9.0** (PyPI, 2026-09-28). 1.x is on `httpx2`, Python ≥3.10.
- **Structured outputs are GA — no beta header.** Canonical request param: `output_config={"format": {"type": "json_schema", "schema": {...}}}` on `client.messages.create()`. The old top-level `output_format` param is **deprecated** on `create()`; the SDK helper `client.messages.parse(..., output_format=PydanticModel)` still takes `output_format` and returns `response.parsed_output`.
  ```python
  from pydantic import BaseModel
  class CutPlan(BaseModel):
      keep: list[dict]
      titles: list[str]
  resp = client.messages.parse(model="claude-opus-5-5", max_tokens=16000,
                               messages=[{"role": "user", "content": prompt}],
                               output_format=CutPlan)
  plan = resp.parsed_output

  # raw schema:
  resp = client.messages.create(model="claude-opus-5-5", max_tokens=16000, messages=[...],
      output_config={"format": {"type": "json_schema", "schema": {
          "type": "object", "properties": {...}, "required": [...], "additionalProperties": False}}})
  data = json.loads(next(b.text for b in resp.content if b.type == "text"))
  ```
- **Strict tool use**: `"strict": True` at top level of the tool definition (sibling of `name`/`description`/`input_schema`); every object needs `additionalProperties: false` + `required`. No beta header. (Java tool runner still needs `structured-outputs-2025-11-13` beta.)
- Schema limits: no recursive schemas, no `minimum/maximum/multipleOf`, no `minLength/maxLength`; supported: basic types, `enum`, `const`, `anyOf`, `allOf`, `$ref/$defs`, string formats (`date-time, date, email, uri, uuid`…). Python/TS SDKs strip unsupported constraints and validate client-side. First use of a new schema has a compile latency; cached 24 h. Incompatible with citations and assistant prefill; works with batches, streaming, thinking. On `stop_reason == "refusal"` or `"max_tokens"` the output may not match — always check `stop_reason`.
- Supported models: Claude Fable 5/5.1, Mythos 5/5.1, Opus 5.5, Opus 5, Opus 4.8, Sonnet 5.5, Sonnet 5, Haiku 4.5 (+ legacy Opus 4.5/4.1). Default model per skill: `claude-opus-5-5`. On Opus 5.5 / Sonnet 5.5 / Fable 5.1, forced `tool_choice` (`any`/`tool`) returns 400 → use structured outputs or `auto` + `strict: true` instead of the old "force a tool to get JSON" trick.
