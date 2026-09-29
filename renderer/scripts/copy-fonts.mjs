// Copies the OFL font files shipped in npm packages into assets/fonts so that
// the Python side can place them in each job's public folder.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const out = path.join(root, 'assets', 'fonts');
fs.mkdirSync(out, {recursive: true});
// Studio 기본 미리보기(public/)에서도 쓰도록
const pubFonts = path.join(root, 'public', 'fonts');
fs.mkdirSync(pubFonts, {recursive: true});

const copies = [];
const pretendardDir = path.join(root, 'node_modules', 'pretendard', 'dist', 'web', 'static', 'woff2');
for (const w of ['Regular', 'Medium', 'SemiBold', 'Bold', 'ExtraBold', 'Black']) {
  copies.push([path.join(pretendardDir, `Pretendard-${w}.woff2`), `Pretendard-${w}.woff2`]);
}
const antonDir = path.join(root, 'node_modules', '@fontsource', 'anton', 'files');
copies.push([path.join(antonDir, 'anton-latin-400-normal.woff2'), 'Anton-Regular.woff2']);

// 데스크톱 프로그램(PySide6) 화면용 OTF — Qt 는 woff2 를 읽지 못한다
const uiOut = path.join(out, 'ui');
fs.mkdirSync(uiOut, {recursive: true});
const otfDir = path.join(root, 'node_modules', 'pretendard', 'dist', 'public', 'static');
for (const w of ['Regular', 'Medium', 'SemiBold', 'Bold']) {
  const src = path.join(otfDir, `Pretendard-${w}.otf`);
  if (fs.existsSync(src)) fs.copyFileSync(src, path.join(uiOut, `Pretendard-${w}.otf`));
}

let ok = 0;
for (const [src, name] of copies) {
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, path.join(out, name));
    fs.copyFileSync(src, path.join(pubFonts, name));
    ok++;
  } else {
    console.warn(`[copy-fonts] missing: ${src}`);
  }
}
console.log(`[copy-fonts] copied ${ok}/${copies.length} font files to ${out}`);
