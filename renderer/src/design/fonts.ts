import {loadFont} from '@remotion/fonts';
import {continueRender, delayRender, staticFile} from 'remotion';
import {useEffect, useState} from 'react';
// 인용 카드용 명조(유니코드 범위별 분할 파일 → 필요한 글자만 로드)
import '@fontsource/noto-serif-kr/500.css';
import '@fontsource/noto-serif-kr/700.css';

let loaded = false;

export const ensureFonts = () => {
  if (loaded) return;
  loaded = true;
  const weights: [string, string][] = [
    ['Regular', '400'],
    ['Medium', '500'],
    ['SemiBold', '600'],
    ['Bold', '700'],
    ['ExtraBold', '800'],
    ['Black', '900'],
  ];
  for (const [name, weight] of weights) {
    loadFont({family: 'Pretendard', url: staticFile(`fonts/Pretendard-${name}.woff2`), weight});
  }
  loadFont({family: 'Anton', url: staticFile('fonts/Anton-Regular.woff2'), weight: '400'});
  // 서체 역할표(docs/롱폼_무대_디자인.md 6장). 한글 subset(korean)을 먼저, 라틴 파일은 라틴 범위만 — 라틴 글자는 뒤에 선언한
  // 라틴 face 가 이기고, 한글은 korean face 로 떨어진다
  const LATIN = 'U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+2074, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD';
  for (const [family, file] of [['Jua', 'Jua'], ['Black Han Sans', 'BlackHanSans'], ['Nanum Pen Script', 'NanumPenScript']]) {
    loadFont({family, url: staticFile(`fonts/${file}-korean.woff2`), weight: '400'});
    loadFont({family, url: staticFile(`fonts/${file}-latin.woff2`), weight: '400', unicodeRange: LATIN});
  }
  loadFont({family: 'Playfair Display', url: staticFile('fonts/PlayfairDisplay-Bold.woff2'), weight: '700'});
  loadFont({family: 'Playfair Display', url: staticFile('fonts/PlayfairDisplay-BoldItalic.woff2'), weight: '700',
    style: 'italic'});
  // 디자인 v3(종이 콜라주) — 예술적인 세리프
  loadFont({family: 'Playfair Display', url: staticFile('fonts/PlayfairDisplay-Italic.woff2'), weight: '400', style: 'italic'});
  loadFont({family: 'Playfair Display', url: staticFile('fonts/PlayfairDisplay-BlackItalic.woff2'), weight: '900',
    style: 'italic'});
  loadFont({family: 'Instrument Serif', url: staticFile('fonts/InstrumentSerif-Regular.woff2'), weight: '400'});
  loadFont({family: 'Instrument Serif', url: staticFile('fonts/InstrumentSerif-Italic.woff2'), weight: '400', style: 'italic'});
  for (const w of ['400', '700']) {
    loadFont({family: 'Gowun Batang', url: staticFile(`fonts/GowunBatang-${w}-korean.woff2`), weight: w});
    loadFont({family: 'Gowun Batang', url: staticFile(`fonts/GowunBatang-${w}-latin.woff2`), weight: w, unicodeRange: LATIN});
  }
  for (const w of ['300', '700', '800']) {
    loadFont({family: 'Hahmlet', url: staticFile(`fonts/Hahmlet-${w}-korean.woff2`), weight: w});
    loadFont({family: 'Hahmlet', url: staticFile(`fonts/Hahmlet-${w}-latin.woff2`), weight: w, unicodeRange: LATIN});
  }
  // 'Press Serif' = 고운바탕 700 을 모든 굵기에 — 굵기를 따로 주지 않던 메모·콜아웃 자리가 가는 명조로 떨어지지 않게
  for (const w of ['400', '700']) {
    loadFont({family: 'Press Serif', url: staticFile('fonts/GowunBatang-700-korean.woff2'), weight: w});
    loadFont({family: 'Press Serif', url: staticFile('fonts/GowunBatang-700-latin.woff2'), weight: w, unicodeRange: LATIN});
  }
  loadFont({family: 'Song Myung', url: staticFile('fonts/SongMyung-korean.woff2'), weight: '400'});
  loadFont({family: 'Song Myung', url: staticFile('fonts/SongMyung-latin.woff2'), weight: '400', unicodeRange: LATIN});
};

/**
 * 폰트 로드 단언(HyperFrames `font_family_without_font_face` 의 렌더 시점판): 번들 서체(Pretendard·Anton·Jua·Black Han Sans·
 * Nanum Pen Script·Playfair Display)가 실제로 로드되지 않았으면 렌더를 **실패**시킨다. 예전엔 조용히 맑은 고딕·기본 산세리프로 렌더돼 결과물에서만 드러났다.
 * 컴포지션 루트에서 한 번 부른다.
 */
export const useFontGuard = () => {
  const [handle] = useState(() => delayRender('font guard'));
  const [err, setErr] = useState('');
  useEffect(() => {
    let done = false;
    const finish = (e = '') => {
      if (done) return;
      done = true;
      if (e) setErr(e);
      continueRender(handle);
    };
    const loaded = (family: string) => {
      let ok = false;
      document.fonts.forEach((f) => {
        if (f.family.replace(/["']/g, '').toLowerCase() === family.toLowerCase() && f.status === 'loaded') ok = true;
      });
      return ok;
    };
    // loadFont 는 비동기로 FontFace 를 만들므로 document.fonts.ready 만 믿으면 아직 등록 전일 수 있다 → 폴링
    const want = ['Pretendard', 'Anton', 'Jua', 'Black Han Sans', 'Nanum Pen Script', 'Playfair Display', 'Instrument Serif',
      'Gowun Batang', 'Hahmlet', 'Song Myung', 'Press Serif'];
    const started = Date.now();
    const tick = () => {
      const missing = want.filter((f) => !loaded(f));
      if (!missing.length) return finish('');
      if (Date.now() - started > 15000) {
        return finish(`폰트 로드 실패: ${missing.join(', ')} — renderer/public/fonts 를 확인하세요`);
      }
      timer = window.setTimeout(tick, 100);
    };
    let timer = window.setTimeout(tick, 0);
    return () => clearTimeout(timer);
  }, [handle]);
  if (err) throw new Error(err);
};

/** 분할 웹폰트(명조)가 특정 텍스트의 글리프를 다 받을 때까지 렌더를 멈춘다. */
export const useFontForText = (fontSpec: string, text: string) => {
  const [handle] = useState(() => delayRender(`font ${fontSpec}`));
  useEffect(() => {
    let done = false;
    const finish = () => {
      if (!done) {
        done = true;
        continueRender(handle);
      }
    };
    document.fonts
      .load(fontSpec, text || '가')
      .then(finish)
      .catch(finish);
    const t = setTimeout(finish, 8000);
    return () => clearTimeout(t);
  }, [fontSpec, text, handle]);
};
