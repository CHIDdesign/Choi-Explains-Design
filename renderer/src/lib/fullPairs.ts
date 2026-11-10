/** 맞붙은 전면 그래픽 사이의 전환을 고른다. 화자 ↔ 자료는 하드 컷이 사양이라 여기 오지 않는다. */
export type FullFrame = {id: string; start: number; end: number; cover: boolean; still: boolean; held: string};

const GROUNDS = ['newsprint', 'memo', 'parchment'] as const;

/** 같은 물건(held)을 둔 채 바탕 종이만 바꾸는 하드 컷(뒤 id → 종이 · 묶음의 첫 장 id — 시드를 같게 해 물건이 그대로 있게). 첫 장은 기본 양피지라 둘째부터 */
export const paperSwaps = (gs: FullFrame[], abut: number): Record<string, {paper: (typeof GROUNDS)[number]; first: string}> => {
  const out: Record<string, {paper: (typeof GROUNDS)[number]; first: string}> = {};
  let last: FullFrame | null = null;
  let n = 0;
  let first = '';
  for (const g of gs) {
    if (!g.cover) continue;
    n = last && g.held && g.held === last.held && g.start - last.end <= abut ? n + 1 : 0;
    if (!n) first = g.id;
    else out[g.id] = {paper: GROUNDS[(n - 1) % GROUNDS.length], first};
    last = g;
  }
  return out;
};

/** 전면 자료 정지 사진끼리의 세로 밀기(뒤 id → 앞 id): 영상당 max 번, gap 초 이상 떨어져서 — 잦으면 슬라이드 쇼가 된다 */
export const pushPairs = (gs: FullFrame[], abut: number, max = 3, gap = 40): Record<string, string> => {
  const out: Record<string, string> = {};
  let last: FullFrame | null = null;
  let at = -Infinity;
  for (const g of gs) {
    if (!g.cover) continue;
    if (g.still && last?.still && g.start - last.end <= abut && g.start - at >= gap && Object.keys(out).length < max) {
      out[g.id] = last.id;
      at = g.start;
    }
    last = g;
  }
  return out;
};
