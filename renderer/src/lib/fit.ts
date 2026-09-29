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

/** 어절 단위 줄바꿈(한국어: 공백 기준). 최대 줄 수를 넘으면 마지막 줄에 합침. */
export const wrap = (text: string, size: number, maxW: number, maxLines = 3, tracking = 0): string[] => {
  const words = text.split(/\s+/).filter(Boolean);
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
    head.push(lines.slice(maxLines - 1).join(' '));
    return head;
  }
  return lines;
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
