// 폰트 로딩 전에도 동작하는 근사 폭 계산(Pretendard 기준). 레이아웃 결정용.
const charWidth = (ch: string): number => {
  const c = ch.charCodeAt(0);
  if (c >= 0xac00 && c <= 0xd7a3) return 0.94; // 한글 음절
  if (c >= 0x3131 && c <= 0x318e) return 0.8;
  if (ch === ' ') return 0.26;
  if (/[0-9]/.test(ch)) return 0.6;
  if (/[A-Z]/.test(ch)) return 0.66;
  if (/[a-z]/.test(ch)) return 0.54;
  if (/[.,'’:;!|]/.test(ch)) return 0.28;
  return 0.6;
};

export const estWidth = (text: string, size: number, tracking = 0): number => {
  let w = 0;
  for (const ch of text) w += charWidth(ch) + tracking;
  return w * size;
};

export const fitSize = (text: string, maxW: number, maxSize: number, minSize = 12, tracking = 0) => {
  const unit = estWidth(text, 1, tracking) || 1;
  return Math.max(minSize, Math.min(maxSize, maxW / unit));
};

/** 한 어절이 줄보다 길면 글자 단위로 나눈다(띄어쓰기 없는 긴 제목·합성어) */
const splitLong = (w: string, size: number, maxW: number, tracking: number): string[] => {
  if (estWidth(w, size, tracking) <= maxW) return [w];
  const out: string[] = [];
  let cur = '';
  for (const ch of w) {
    if (cur && estWidth(cur + ch, size, tracking) > maxW) {
      out.push(cur);
      cur = ch;
    } else cur += ch;
  }
  if (cur) out.push(cur);
  return out;
};

/** 줄 끝을 말줄임(…)으로 — 폭 안에 들어갈 때까지 뒤에서 글자를 뺀다 */
const ellipsize = (line: string, size: number, maxW: number, tracking: number): string => {
  let t = line;
  while (t.length > 1 && estWidth(t + '…', size, tracking) > maxW) t = t.slice(0, -1);
  return t.trimEnd() + '…';
};

/** 어절 단위 줄바꿈(한국어: 공백 기준). 최대 줄 수를 넘으면 마지막 줄을 말줄임으로 — 예전엔 남은 글을 모두 마지막
 *  줄에 이어 붙여(nowrap) 상자 밖으로 나가거나 잘렸다. 줄보다 긴 어절은 글자 단위로 나눈다. */
export const wrap = (text: string, size: number, maxW: number, maxLines = 3, tracking = 0): string[] => {
  const words = text.split(/\s+/).filter(Boolean).flatMap((w) => splitLong(w, size, maxW, tracking));
  const lines: string[] = [];
  let cur = '';
  for (const w of words) {
    const test = cur ? cur + ' ' + w : w;
    if (estWidth(test, size, tracking) <= maxW || !cur) {
      cur = test;
    } else {
      lines.push(cur);
      cur = w;
    }
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines) {
    const head = lines.slice(0, maxLines - 1);
    head.push(ellipsize(lines.slice(maxLines - 1).join(' '), size, maxW, tracking));
    return head;
  }
  return lines;
};

// 뒤에서 끊으면 안 되는 관형사(바로 뒤 낱말에 붙는다) — '그 / 다음에는' 같은 줄바꿈을 막는다
const HOLD_NEXT = /^(그|이|저|한|두|세|네|새|옛|첫|온|각|매|몇|어느|무슨|어떤|모든|이런|그런|저런|아무|다른|여러)$/;
// 앞말에 붙는 의존 명사 — 이 앞에서 끊으면 '면적 / 중' 처럼 읽힌다
const HOLD_PREV = /^(중|때|것\S{0,2}|수|등|뿐|데|바|줄|듯|채|만큼|대로|및)$/;
const breakCost = (w: string, next = ''): number => {
  if (HOLD_PREV.test(next)) return 4;
  if (/[,.!?:;…]["'”’)]?$/.test(w)) return -0.7;
  if (/(지만|는데|으며|하며|하고|해서|니까|라면|다면|므로|도록)$/.test(w)) return -0.28;
  if (HOLD_NEXT.test(w)) return 4;
  return /의$/.test(w) ? 0.5 : 0;
};

/** 어절 단위 줄 나누기(DP): 줄 길이를 고르게, 구두점·이음 어미 뒤에서 끊고 관형사 뒤에서는 끊지 않는다. 필요한 최소 줄 수를 쓴다. */
export const balanceLines = (text: string, size: number, maxW: number, maxLines = 3, tracking = 0): string[] => {
  const words = text.split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const widthOf = (i: number, j: number) => estWidth(words.slice(i, j).join(' '), size, tracking);
  const need = Math.min(maxLines, Math.max(1, Math.ceil(widthOf(0, words.length) / maxW)));
  for (let n = need; n <= maxLines; n++) {
    const target = widthOf(0, words.length) / n;
    const best: Map<number, {cost: number; prev: number}>[] = Array.from({length: n + 1}, () => new Map());
    best[0].set(0, {cost: 0, prev: -1});
    for (let line = 1; line <= n; line++) {
      for (const [i, {cost}] of best[line - 1]) {
        for (let j = i + 1; j <= words.length; j++) {
          const w = widthOf(i, j);
          if (w > maxW * 1.02 && j > i + 1) break;
          const atEnd = j === words.length;
          if (atEnd !== (line === n)) continue;
          const dev = (w - target) / target;
          const c = cost + dev * dev + (atEnd ? 0 : breakCost(words[j - 1], words[j]));
          const hit = best[line].get(j);
          if (!hit || c < hit.cost) best[line].set(j, {cost: c, prev: i});
        }
      }
    }
    if (best[n].has(words.length)) {
      const out: string[] = [];
      let j = words.length;
      for (let line = n; line >= 1; line--) {
        const i = best[line].get(j)!.prev;
        out.unshift(words.slice(i, j).join(' '));
        j = i;
      }
      return out;
    }
  }
  return wrap(text, size, maxW, maxLines, tracking);
};

/** 여러 줄 텍스트가 상자에 들어가는 가장 큰 크기 */
export const fitBlock = (text: string, maxW: number, maxH: number, maxSize: number, minSize: number,
  lineHeight = 1.2, maxLines = 3, tracking = 0): {size: number; lines: string[]} => {
  for (let s = maxSize; s >= minSize; s -= 2) {
    const lines = wrap(text, s, maxW, 99, tracking);
    if (lines.length <= maxLines && lines.length * s * lineHeight <= maxH &&
      lines.every((l) => estWidth(l, s, tracking) <= maxW * 1.02)) {
      return {size: s, lines};
    }
  }
  return {size: minSize, lines: wrap(text, minSize, maxW, maxLines, tracking)};
};
