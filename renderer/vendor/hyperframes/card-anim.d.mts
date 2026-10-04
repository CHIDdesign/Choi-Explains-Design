export type CompiledCard = {
  timeline: {kill(): void; duration(): number};
  duration: number;
  settle: number;      // 떠다니기·나가기를 뺀 등장이 끝나는 시각
  seek: (t: number) => void;
  kinds: string[];
  problems: string[];
};
export type CardLibs = {SplitText?: unknown; CustomEase?: unknown; drawSVG?: boolean; morphSVG?: boolean; motionPath?: boolean};
export function compileCard(gsap: unknown, root: Element,
  opts?: {fps?: number; duration?: number; timeline?: string; libs?: CardLibs; exit?: {at: number; dur: number}}): CompiledCard;
export function parseCamera(raw: string | undefined, problems: string[]): {t: number; x: number; y: number; z: number}[];
export const CARD_ANIM_KINDS: string[];
