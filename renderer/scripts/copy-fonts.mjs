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
// 서체 역할표(docs/롱폼_무대_디자인.md 6장): 둥근 메모체 Jua · 한 방 Black Han Sans · 손글씨 Nanum Pen Script ·
// 이탤릭 세리프 숫자 Playfair Display — 모두 OFL, 한글은 subset 한 파일(korean) + 라틴 한 파일
const fs4 = (pkg, file, name) => copies.push([path.join(root, 'node_modules', '@fontsource', pkg, 'files', file), name]);
fs4('jua', 'jua-korean-400-normal.woff2', 'Jua-korean.woff2');
fs4('jua', 'jua-latin-400-normal.woff2', 'Jua-latin.woff2');
fs4('black-han-sans', 'black-han-sans-korean-400-normal.woff2', 'BlackHanSans-korean.woff2');
fs4('black-han-sans', 'black-han-sans-latin-400-normal.woff2', 'BlackHanSans-latin.woff2');
fs4('nanum-pen-script', 'nanum-pen-script-korean-400-normal.woff2', 'NanumPenScript-korean.woff2');
fs4('nanum-pen-script', 'nanum-pen-script-latin-400-normal.woff2', 'NanumPenScript-latin.woff2');
fs4('playfair-display', 'playfair-display-latin-700-italic.woff2', 'PlayfairDisplay-BoldItalic.woff2');
fs4('playfair-display', 'playfair-display-latin-700-normal.woff2', 'PlayfairDisplay-Bold.woff2');
// 디자인 v3(종이 콜라주): 예술적인 세리프 — 이탤릭 연도(Playfair 400·900 italic) · 영문 이탤릭(Instrument Serif) ·
// 한글 명조(고운바탕 = 문장·인용·제목, 함렛 = 정밀한 큰 제목, 송명 = 포스터 같은 한 방). 모두 OFL
fs4('playfair-display', 'playfair-display-latin-400-italic.woff2', 'PlayfairDisplay-Italic.woff2');
fs4('playfair-display', 'playfair-display-latin-900-italic.woff2', 'PlayfairDisplay-BlackItalic.woff2');
fs4('instrument-serif', 'instrument-serif-latin-400-normal.woff2', 'InstrumentSerif-Regular.woff2');
fs4('instrument-serif', 'instrument-serif-latin-400-italic.woff2', 'InstrumentSerif-Italic.woff2');
for (const w of ['400', '700']) {
  fs4('gowun-batang', `gowun-batang-korean-${w}-normal.woff2`, `GowunBatang-${w}-korean.woff2`);
  fs4('gowun-batang', `gowun-batang-latin-${w}-normal.woff2`, `GowunBatang-${w}-latin.woff2`);
}
for (const w of ['300', '700', '800']) {
  fs4('hahmlet', `hahmlet-korean-${w}-normal.woff2`, `Hahmlet-${w}-korean.woff2`);
  fs4('hahmlet', `hahmlet-latin-${w}-normal.woff2`, `Hahmlet-${w}-latin.woff2`);
}
fs4('song-myung', 'song-myung-korean-400-normal.woff2', 'SongMyung-korean.woff2');
fs4('song-myung', 'song-myung-latin-400-normal.woff2', 'SongMyung-latin.woff2');

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
