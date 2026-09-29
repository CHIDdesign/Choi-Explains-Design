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
