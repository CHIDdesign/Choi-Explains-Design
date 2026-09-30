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

/**
 * 폰트 로드 단언(HyperFrames `font_family_without_font_face` 의 렌더 시점판): Pretendard·Anton 이 실제로 로드되지 않았으면
 * 렌더를 **실패**시킨다. 예전엔 조용히 맑은 고딕·기본 산세리프로 렌더돼 결과물에서만 드러났다.
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
    const want = ['Pretendard', 'Anton'];
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
